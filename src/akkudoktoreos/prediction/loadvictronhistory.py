"""Forecast site load from locally collected Victron Cerbo GX measurements."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import Field

from akkudoktoreos.config.configabc import SettingsBaseModel
from akkudoktoreos.prediction.loadabc import LoadProvider
from akkudoktoreos.utils.datetimeutil import DateTime, to_datetime, to_duration


class LoadVictronHistoryCommonSettings(SettingsBaseModel):
    """Settings for the local Cerbo load-history forecast.

    The provider intentionally does not assume fixed weekdays or departure times. It learns a
    robust quarter-hour-of-day profile from the locally collected Cerbo load meter and gently
    adapts that profile to the recent load level. This is a better fit for rotating-shift
    households than a fixed standard load profile.
    """

    history_days: int = Field(
        default=28,
        ge=2,
        le=90,
        json_schema_extra={"description": "Rolling Cerbo load history used for forecasting [days]."},
    )
    minimum_history_hours: float = Field(
        default=1.0,
        ge=0.25,
        le=24.0,
        json_schema_extra={
            "description": "Minimum collected load history before a forecast is emitted [hours]."
        },
    )
    recency_half_life_days: float = Field(
        default=7.0,
        ge=1.0,
        le=60.0,
        json_schema_extra={
            "description": "Half life for weighting older matching quarter-hour samples [days]."
        },
    )
    recent_window_hours: float = Field(
        default=6.0,
        ge=1.0,
        le=24.0,
        json_schema_extra={"description": "Recent load window used for level adaptation [hours]."},
    )
    recent_blend: float = Field(
        default=0.15,
        ge=0.0,
        le=0.5,
        json_schema_extra={
            "description": "Blend of recent median load into the learned time-of-day profile."
        },
    )
    min_slot_samples: int = Field(
        default=2,
        ge=1,
        le=14,
        json_schema_extra={
            "description": "Minimum historic samples for a quarter-hour slot before using its profile."
        },
    )


class LoadVictronHistory(LoadProvider):
    """Predict load from the cumulative local Cerbo load-energy measurement.

    Forecast resolution is 15 minutes. For each future slot, the provider uses a recency-weighted
    median of the same local quarter-hour from previous days. Median aggregation deliberately
    suppresses occasional large controllable loads (for example EV charging) so they are less
    likely to be learned as permanent base load. Until enough days are available for a slot, the
    recent median site load is used as a conservative fallback.
    """

    _interval_minutes = 15

    @classmethod
    def provider_id(cls) -> str:
        return "LoadVictronHistory"

    def enabled(self) -> bool:
        """Enable automatically for a Victron installation unless another load provider is chosen."""
        configured = self.config.load.provider
        if configured == self.provider_id():
            return True
        adapter_providers = self.config.adapter.provider or []
        return configured is None and "Victron" in adapter_providers

    @staticmethod
    def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
        """Return a weighted median, ignoring non-finite or non-positive weights."""
        values = np.asarray(values, dtype=float)
        weights = np.asarray(weights, dtype=float)
        valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
        if not np.any(valid):
            return float("nan")
        values = values[valid]
        weights = weights[valid]
        order = np.argsort(values)
        values = values[order]
        weights = weights[order]
        cutoff = weights.sum() * 0.5
        return float(values[np.searchsorted(np.cumsum(weights), cutoff, side="left")])

    @classmethod
    def _floor_interval(cls, timestamp: DateTime) -> DateTime:
        minute = (timestamp.minute // cls._interval_minutes) * cls._interval_minutes
        return timestamp.set(minute=minute, second=0, microsecond=0)

    @classmethod
    def _ceil_interval(cls, timestamp: DateTime) -> DateTime:
        floored = cls._floor_interval(timestamp)
        if timestamp == floored:
            return floored
        return floored.add(minutes=cls._interval_minutes)

    async def _history_power(self) -> pd.Series:
        """Return completed 15-minute site-load intervals as average power in W."""
        keys = self.config.measurement.load_emr_keys or []
        if not keys:
            logger.info("LoadVictronHistory: no load energy measurement key configured yet")
            return pd.Series(dtype=float)

        settings = self.config.load.victron_history
        reference = to_datetime(in_timezone=self.config.general.timezone)
        requested_start = reference.subtract(days=settings.history_days + 1)

        starts: list[DateTime] = []
        ends: list[DateTime] = []
        for key in keys:
            raw = await self.measurement.key_to_raw_series(
                key=key,
                start_datetime=requested_start,
                end_datetime=reference.add(minutes=1),
                dropna=True,
            )
            if raw.empty:
                logger.info("LoadVictronHistory: no Cerbo load measurements available for '{}'", key)
                return pd.Series(dtype=float)
            starts.append(to_datetime(raw.index[0], in_timezone=self.config.general.timezone))
            ends.append(to_datetime(raw.index[-1], in_timezone=self.config.general.timezone))

        # Use only the common meter window. This also keeps the provider correct if more than one
        # load meter is configured in the future.
        history_start = max(max(starts), reference.subtract(days=settings.history_days))
        history_end = min(ends)
        history_start = self._ceil_interval(history_start)
        history_end = self._floor_interval(history_end)
        if history_end <= history_start:
            return pd.Series(dtype=float)

        elapsed_hours = (history_end - history_start).total_seconds() / 3600.0
        if elapsed_hours < settings.minimum_history_hours:
            logger.info(
                "LoadVictronHistory: collecting Cerbo history ({:.2f}/{:.2f} h)",
                elapsed_hours,
                settings.minimum_history_hours,
            )
            return pd.Series(dtype=float)

        interval = to_duration(f"{self._interval_minutes} minutes")
        energy_kwh = await self.measurement.load_total_kwh(
            start_datetime=history_start,
            end_datetime=history_end,
            interval=interval,
        )
        if energy_kwh.size == 0:
            return pd.Series(dtype=float)

        # Average power for a 15-minute interval: kWh * 1000 / 0.25 h.
        power_w = np.asarray(energy_kwh, dtype=float) * (60.0 / self._interval_minutes) * 1000.0
        power_w = np.where(np.isfinite(power_w), np.maximum(power_w, 0.0), np.nan)
        index = pd.date_range(
            start=pd.Timestamp(history_start),
            periods=len(power_w),
            freq=f"{self._interval_minutes}min",
        )
        return pd.Series(power_w, index=index, dtype=float).dropna()

    def _forecast_slot(self, history: pd.Series, target: DateTime, recent_median: float) -> float:
        """Forecast one quarter hour from historic matching clock-time samples."""
        settings = self.config.load.victron_history
        index = pd.DatetimeIndex(history.index)
        target_ts = pd.Timestamp(target)
        same_slot = (index.hour == target_ts.hour) & (index.minute == target_ts.minute)
        candidates = history.loc[same_slot]

        if len(candidates) < settings.min_slot_samples:
            return max(0.0, recent_median)

        latest = pd.Timestamp(history.index[-1])
        ages_days = np.asarray(
            [max(0.0, (latest - pd.Timestamp(ts)).total_seconds() / 86400.0) for ts in candidates.index],
            dtype=float,
        )
        weights = np.power(0.5, ages_days / settings.recency_half_life_days)
        seasonal = self._weighted_median(candidates.to_numpy(dtype=float), weights)
        if not np.isfinite(seasonal):
            seasonal = recent_median

        forecast = (1.0 - settings.recent_blend) * seasonal + settings.recent_blend * recent_median
        return max(0.0, float(forecast))

    async def _update_data(self, force_update: Optional[bool] = False) -> None:
        """Build the configured horizon as a 15-minute forecast from Cerbo history."""
        # Make the automatic selection visible in the live config, but never overwrite a provider
        # explicitly chosen by the user.
        if self.config.load.provider is None:
            self.config.load.provider = self.provider_id()

        history = await self._history_power()
        if history.empty:
            # Do not publish a misleading zero forecast while history is still being collected.
            return

        settings = self.config.load.victron_history
        recent_count = max(1, int(round(settings.recent_window_hours * 60 / self._interval_minutes)))
        recent_median = float(history.tail(recent_count).median())
        if not np.isfinite(recent_median):
            return

        start = self._floor_interval(self.ems_start_datetime)
        end = start.add(hours=self.config.prediction.hours)
        date = start
        count = 0
        while date < end:
            value = self._forecast_slot(history, date, recent_median)
            await self.update_value(date, {"loadforecast_power_w": round(value, 2)})
            date = date.add(minutes=self._interval_minutes)
            count += 1

        self.update_datetime = to_datetime(in_timezone=self.config.general.timezone)
        logger.info(
            "LoadVictronHistory: generated {} quarter-hour values from {} historic intervals "
            "(recent median {:.0f} W)",
            count,
            len(history),
            recent_median,
        )
