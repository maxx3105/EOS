"""Forecast site load from locally collected Victron Cerbo GX measurements."""

from __future__ import annotations

from typing import Any, ClassVar, Optional

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import Field, model_validator

from akkudoktoreos.config.configabc import SettingsBaseModel
from akkudoktoreos.prediction.loadabc import LoadProvider
from akkudoktoreos.utils.datetimeutil import DateTime, to_datetime, to_duration


class LoadVictronHistoryCommonSettings(SettingsBaseModel):
    """Settings for the local Cerbo load-history forecast.

    The provider deliberately avoids fixed weekday/departure assumptions. It learns a robust
    quarter-hour profile from the local non-EV Cerbo load and can additionally weight historical
    samples by outdoor temperature and day-of-year. This keeps the model useful for rotating-shift
    households while allowing seasonal consumers such as heat pumps and pool equipment to emerge
    from the measured load history even before they are separately metered.
    """

    history_days: int = Field(
        default=90,
        ge=2,
        le=365,
        json_schema_extra={"description": "Rolling non-EV Cerbo load history used for forecasting [days]."},
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
        default=21.0,
        ge=1.0,
        le=180.0,
        json_schema_extra={
            "description": "Half life for weighting older matching quarter-hour samples [days]."
        },
    )
    seasonal_weighting: bool = Field(
        default=True,
        json_schema_extra={
            "description": "Weight matching clock-time samples by circular day-of-year distance."
        },
    )
    seasonal_half_life_days: float = Field(
        default=45.0,
        ge=7.0,
        le=183.0,
        json_schema_extra={
            "description": "Half life for day-of-year similarity weighting [days]."
        },
    )
    temperature_weighting: bool = Field(
        default=True,
        json_schema_extra={
            "description": "Use outdoor-temperature similarity when weather data is available."
        },
    )
    temperature_half_life_c: float = Field(
        default=4.0,
        ge=0.5,
        le=20.0,
        json_schema_extra={
            "description": "Outdoor-temperature difference that halves a historic sample weight [°C]."
        },
    )
    temperature_history_key: str = Field(
        default="victron_outdoor_temp_c",
        min_length=1,
        json_schema_extra={
            "description": "Local EOS measurement key used to retain outdoor temperature history [°C]."
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
            "description": "Blend of recent median load into the learned seasonal profile."
        },
    )
    min_slot_samples: int = Field(
        default=2,
        ge=1,
        le=30,
        json_schema_extra={
            "description": "Minimum historic samples for a quarter-hour slot before using its profile."
        },
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_history_defaults(cls, values: Any) -> Any:
        """Upgrade the old 28-day/7-day defaults without overriding deliberate new settings.

        Older Synology/Victron configs may have serialized the former defaults even though the user
        never selected them explicitly. The absence of every new seasonal/temperature field marks
        such a legacy payload. Only that exact legacy default pair is migrated.
        """
        if not isinstance(values, dict):
            return values
        new_fields = {
            "seasonal_weighting",
            "seasonal_half_life_days",
            "temperature_weighting",
            "temperature_half_life_c",
            "temperature_history_key",
        }
        is_legacy_payload = not any(field in values for field in new_fields)
        if (
            is_legacy_payload
            and values.get("history_days") == 28
            and float(values.get("recency_half_life_days", 7.0)) == 7.0
        ):
            migrated = dict(values)
            migrated["history_days"] = 90
            migrated["recency_half_life_days"] = 21.0
            return migrated
        return values


class LoadVictronHistory(LoadProvider):
    """Predict non-EV site load from locally measured Cerbo history.

    Forecast resolution is 15 minutes. For every future slot the provider compares the same local
    quarter-hour from previous days. Candidate loads are combined with a weighted median. Weights
    account for recency, optional day-of-year similarity and optional outdoor-temperature
    similarity. The median remains robust against exceptional household peaks, while EV charging
    is removed earlier by the Victron adapter when ``victron_base_load_emr`` is configured.

    Outdoor temperature is retained locally from the already configured EOS weather forecast. This
    builds a paired load/temperature history without VRM credentials or an additional weather API.
    If temperature data is unavailable, the provider automatically falls back to recency/seasonal
    weighting and continues producing forecasts.
    """

    _interval_minutes: ClassVar[int] = 15
    _weather_temperature_key: ClassVar[str] = "weather_temp_air"

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

    @staticmethod
    def _circular_day_distance(index: pd.DatetimeIndex, target: pd.Timestamp) -> np.ndarray:
        """Return approximate circular day-of-year distance to ``target`` in days."""
        candidate_day = np.asarray(index.dayofyear, dtype=float)
        target_day = float(target.dayofyear)
        direct = np.abs(candidate_day - target_day)
        # 365 is intentionally used as a smooth seasonal circle; a one-day leap-year difference
        # is negligible compared with the multi-week seasonal half-life.
        return np.minimum(direct, 365.0 - np.minimum(direct, 365.0))

    @staticmethod
    def _temperature_similarity_weights(
        temperatures_c: np.ndarray, target_temperature_c: float, half_life_c: float
    ) -> np.ndarray:
        """Return weights whose value halves for every ``half_life_c`` temperature difference."""
        temperatures = np.asarray(temperatures_c, dtype=float)
        weights = np.ones_like(temperatures, dtype=float)
        valid = np.isfinite(temperatures) & np.isfinite(target_temperature_c)
        if np.any(valid):
            delta = np.abs(temperatures[valid] - float(target_temperature_c))
            weights[valid] = np.power(0.5, delta / float(half_life_c))
        return weights

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

    @staticmethod
    def _normalise_series_index(series: pd.Series, timezone: str) -> pd.Series:
        """Return a sorted numeric series with a timezone-aware local DatetimeIndex."""
        if series.empty:
            return pd.Series(dtype=float)
        result = pd.to_numeric(series, errors="coerce").dropna().astype(float)
        index = pd.DatetimeIndex(result.index)
        if index.tz is None:
            index = index.tz_localize(timezone)
        else:
            index = index.tz_convert(timezone)
        result.index = index
        return result[~result.index.duplicated(keep="last")].sort_index()

    async def _weather_temperature_series(
        self, start_datetime: DateTime, end_datetime: DateTime
    ) -> pd.Series:
        """Read temperature from the already updated EOS weather provider/container."""
        try:
            # Local import avoids a module import cycle while prediction providers are created.
            from akkudoktoreos.core.coreabc import get_prediction

            prediction = get_prediction()
            series = await prediction.key_to_raw_series(
                key=self._weather_temperature_key,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                dropna=True,
            )
            return self._normalise_series_index(series, self.config.general.timezone)
        except Exception as exc:
            logger.debug("LoadVictronHistory: outdoor temperature unavailable: {}", exc)
            return pd.Series(dtype=float)

    async def _store_current_outdoor_temperature(self) -> Optional[float]:
        """Persist the current weather temperature so future forecasts can match historic weather."""
        if not self.config.load.victron_history.temperature_weighting:
            return None

        now = to_datetime(in_timezone=self.config.general.timezone)
        weather = await self._weather_temperature_series(
            now.subtract(minutes=30), now.add(minutes=30)
        )
        if weather.empty:
            return None

        target = pd.Timestamp(now)
        offsets = np.abs((weather.index - target).total_seconds())
        nearest_pos = int(np.argmin(offsets))
        temperature_c = float(weather.iloc[nearest_pos])
        if not np.isfinite(temperature_c):
            return None

        key = self.config.load.victron_history.temperature_history_key
        await self.measurement.update_value(now, key, temperature_c)
        return temperature_c

    async def _history_power(self) -> pd.Series:
        """Return completed 15-minute non-EV load intervals as average power in W."""
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

        power_w = np.asarray(energy_kwh, dtype=float) * (60.0 / self._interval_minutes) * 1000.0
        power_w = np.where(np.isfinite(power_w), np.maximum(power_w, 0.0), np.nan)
        index = pd.date_range(
            start=pd.Timestamp(history_start),
            periods=len(power_w),
            freq=f"{self._interval_minutes}min",
        )
        return pd.Series(power_w, index=index, dtype=float).dropna()

    async def _history_temperature(self, history: pd.Series) -> pd.Series:
        """Align locally retained outdoor temperatures to historic 15-minute load intervals."""
        if history.empty or not self.config.load.victron_history.temperature_weighting:
            return pd.Series(index=history.index, dtype=float)

        key = self.config.load.victron_history.temperature_history_key
        try:
            raw = await self.measurement.key_to_raw_series(
                key=key,
                start_datetime=to_datetime(history.index[0], in_timezone=self.config.general.timezone),
                end_datetime=to_datetime(history.index[-1], in_timezone=self.config.general.timezone).add(
                    minutes=self._interval_minutes
                ),
                dropna=True,
            )
        except Exception as exc:
            logger.debug("LoadVictronHistory: no temperature history yet: {}", exc)
            return pd.Series(index=history.index, dtype=float)

        raw = self._normalise_series_index(raw, self.config.general.timezone)
        if raw.empty:
            return pd.Series(index=history.index, dtype=float)

        quarter_hour = raw.resample(f"{self._interval_minutes}min").mean()
        return quarter_hour.reindex(
            pd.DatetimeIndex(history.index),
            method="nearest",
            tolerance=pd.Timedelta(minutes=self._interval_minutes),
        )

    async def _future_temperature(self, target_index: pd.DatetimeIndex) -> pd.Series:
        """Align forecast outdoor temperature to future 15-minute load slots."""
        if len(target_index) == 0 or not self.config.load.victron_history.temperature_weighting:
            return pd.Series(index=target_index, dtype=float)

        start = to_datetime(target_index[0], in_timezone=self.config.general.timezone)
        end = to_datetime(target_index[-1], in_timezone=self.config.general.timezone).add(
            minutes=self._interval_minutes
        )
        weather = await self._weather_temperature_series(start, end)
        if weather.empty:
            return pd.Series(index=target_index, dtype=float)
        return weather.reindex(
            target_index,
            method="nearest",
            tolerance=pd.Timedelta(minutes=self._interval_minutes),
        )

    def _forecast_slot(
        self,
        history: pd.Series,
        target: DateTime,
        recent_median: float,
        history_temperature: Optional[pd.Series] = None,
        target_temperature_c: Optional[float] = None,
    ) -> float:
        """Forecast one quarter hour using time, season and optional temperature similarity."""
        settings = self.config.load.victron_history
        index = pd.DatetimeIndex(history.index)
        target_ts = pd.Timestamp(target)
        same_slot = (index.hour == target_ts.hour) & (index.minute == target_ts.minute)
        candidates = history.loc[same_slot]

        if len(candidates) < settings.min_slot_samples:
            return max(0.0, recent_median)

        candidate_index = pd.DatetimeIndex(candidates.index)
        latest = pd.Timestamp(history.index[-1])
        ages_days = np.asarray(
            [max(0.0, (latest - pd.Timestamp(ts)).total_seconds() / 86400.0) for ts in candidate_index],
            dtype=float,
        )
        weights = np.power(0.5, ages_days / settings.recency_half_life_days)

        if settings.seasonal_weighting:
            seasonal_distance = self._circular_day_distance(candidate_index, target_ts)
            weights *= np.power(0.5, seasonal_distance / settings.seasonal_half_life_days)

        if (
            settings.temperature_weighting
            and history_temperature is not None
            and target_temperature_c is not None
            and np.isfinite(target_temperature_c)
        ):
            candidate_temperature = history_temperature.reindex(candidate_index).to_numpy(dtype=float)
            weights *= self._temperature_similarity_weights(
                candidate_temperature,
                float(target_temperature_c),
                settings.temperature_half_life_c,
            )

        seasonal = self._weighted_median(candidates.to_numpy(dtype=float), weights)
        if not np.isfinite(seasonal):
            seasonal = recent_median

        forecast = (1.0 - settings.recent_blend) * seasonal + settings.recent_blend * recent_median
        return max(0.0, float(forecast))

    async def _update_data(self, force_update: Optional[bool] = False) -> None:
        """Build the configured 15-minute horizon from EV-cleaned Cerbo and weather history."""
        if self.config.load.provider is None:
            self.config.load.provider = self.provider_id()

        current_temperature = await self._store_current_outdoor_temperature()
        history = await self._history_power()
        if history.empty:
            return

        settings = self.config.load.victron_history
        recent_count = max(1, int(round(settings.recent_window_hours * 60 / self._interval_minutes)))
        recent_median = float(history.tail(recent_count).median())
        if not np.isfinite(recent_median):
            return

        start = self._floor_interval(self.ems_start_datetime)
        end = start.add(hours=self.config.prediction.hours)
        target_index = pd.date_range(
            start=pd.Timestamp(start),
            end=pd.Timestamp(end),
            freq=f"{self._interval_minutes}min",
            inclusive="left",
        )
        history_temperature = await self._history_temperature(history)
        future_temperature = await self._future_temperature(target_index)

        count = 0
        for target_ts in target_index:
            target_temperature = future_temperature.get(target_ts, np.nan)
            value = self._forecast_slot(
                history,
                to_datetime(target_ts, in_timezone=self.config.general.timezone),
                recent_median,
                history_temperature=history_temperature,
                target_temperature_c=(
                    float(target_temperature) if np.isfinite(target_temperature) else None
                ),
            )
            await self.update_value(
                to_datetime(target_ts, in_timezone=self.config.general.timezone),
                {"loadforecast_power_w": round(value, 2)},
            )
            count += 1

        self.update_datetime = to_datetime(in_timezone=self.config.general.timezone)
        historic_temp_count = int(history_temperature.notna().sum())
        future_temp_count = int(future_temperature.notna().sum())
        logger.info(
            "LoadVictronHistory: generated {} quarter-hour values from {} historic intervals "
            "(recent median {:.0f} W, temperature history {}/{}, forecast {}/{}, current {} °C)",
            count,
            len(history),
            recent_median,
            historic_temp_count,
            len(history_temperature),
            future_temp_count,
            len(future_temperature),
            f"{current_temperature:.1f}" if current_temperature is not None else "n/a",
        )
