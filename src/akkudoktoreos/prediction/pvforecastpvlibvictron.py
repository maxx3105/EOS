"""PVLib forecast with Victron measurement feedback aligned to live 15-minute slots."""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd
from loguru import logger

from akkudoktoreos.core.coreabc import get_measurement
from akkudoktoreos.prediction.pvforecastpvlib import DeviceType, PVForecastPVLib
from akkudoktoreos.utils.datetimeutil import DateTime, to_datetime, to_duration


class PVForecastPVLibVictron(PVForecastPVLib):
    """PVLib provider whose feedback window follows current Victron measurements."""

    # SmartSolar peak efficiency is specified up to 99 %. A slightly conservative
    # nominal conversion efficiency avoids treating the charge controller as lossless;
    # the live Victron feedback then corrects remaining installation-specific bias.
    _mppt_output_efficiency = 0.985

    @classmethod
    def provider_id(cls) -> str:
        """Return the unique provider identifier."""
        return "PVForecastPVLibVictron"

    def _get_model(
        self,
        model_spec: Union[str, int, float],
        database: pd.DataFrame,
        device_type: DeviceType,
    ) -> Optional[pd.Series]:
        """Treat numeric inverter powers as DC-coupled Victron MPPT output stages.

        The base PVLib provider interprets a numeric ``inverter_model`` by selecting a
        similarly sized CEC grid inverter. That is a poor match for short strings on a
        SmartSolar charge controller because an arbitrary CEC inverter may have a much
        higher MPPT voltage window. For the Victron provider, a numeric value therefore
        means *maximum MPPT output power*.

        The output stage is expressed with the Sandia inverter parameter shape, but with
        all voltage-dependent coefficients set to zero. This deliberately makes voltage
        irrelevant and reduces the model to a constant-efficiency power conversion stage
        with a hard ``Paco`` output cap. Using the Sandia shape also keeps PVLib's AC
        result as a one-dimensional power series when the module side uses a CEC
        single-diode model. A PVWatts inverter parameter set would make PVLib apply the
        inverter function to the complete CEC DC dataframe (voltage/current columns too),
        which is not the desired DC-coupled SmartSolar behaviour.

        Named inverter models keep the original behaviour, which preserves compatibility
        with installations that intentionally use an AC-coupled inverter model.
        """
        if device_type == "inverter":
            try:
                mppt_output_power_w = float(model_spec)
            except (TypeError, ValueError):
                return super()._get_model(model_spec, database, device_type)

            if mppt_output_power_w > 0:
                efficiency = self._mppt_output_efficiency
                model = pd.Series(
                    {
                        # With Pso/C0..C3 = 0 the Sandia equation becomes
                        # Pac = Paco / Pdco * Pdc = efficiency * Pdc, clipped at Paco.
                        "Paco": mppt_output_power_w,
                        "Pdco": mppt_output_power_w / efficiency,
                        # Vdco is required by the Sandia parameter schema. Voltage does
                        # not affect the result because all voltage coefficients are zero.
                        "Vdco": 100.0,
                        "Pso": 0.0,
                        "C0": 0.0,
                        "C1": 0.0,
                        "C2": 0.0,
                        "C3": 0.0,
                        "Pnt": 0.0,
                    },
                    name=f"Victron_MPPT_{mppt_output_power_w:.0f}W",
                )
                logger.info(
                    "Using Victron DC-coupled MPPT output model: "
                    f"limit={mppt_output_power_w:.0f} W, efficiency={efficiency:.3f}"
                )
                return model

        return super()._get_model(model_spec, database, device_type)

    def _current_correction_time(self) -> DateTime:
        """Return the real current time instead of EOS' hour-rounded EMS start."""
        return to_datetime(in_timezone=self.config.general.timezone)

    def _align_correction_end(self, timestamp: DateTime) -> DateTime:
        """Floor a timestamp to the provider's 15-minute forecast grid."""
        interval = self._measurement_correction_interval_minutes
        aligned_minute = (timestamp.minute // interval) * interval
        return timestamp.set(minute=aligned_minute, second=0, microsecond=0)

    @classmethod
    def _raw_meter_window_is_complete(
        cls,
        series: pd.Series,
        correction_start: DateTime,
        correction_end: DateTime,
    ) -> bool:
        """Return whether real meter samples cover a correction window without restart gaps.

        ``key_to_array(..., fill_method='time')`` can otherwise synthesize a complete-looking
        15-minute array from only a few samples collected after an EOS/container restart. That
        makes the measured 60-minute energy appear close to zero and incorrectly drives the live
        correction to its minimum factor. Require actual meter coverage near both window edges,
        no raw gap larger than one forecast interval and a monotonically increasing cumulative
        counter before resampling is allowed.
        """
        if series.empty:
            return False

        index = pd.DatetimeIndex(series.index).sort_values()
        start_ts = pd.Timestamp(correction_start)
        end_ts = pd.Timestamp(correction_end)
        tolerance = pd.Timedelta(minutes=cls._measurement_correction_interval_minutes)

        if index[0] > start_ts + tolerance or index[-1] < end_ts:
            return False
        if len(index) > 1 and np.any(np.diff(index.asi8) > tolerance.value):
            return False

        values = pd.to_numeric(series.reindex(index), errors="coerce").to_numpy(dtype=float)
        if np.isnan(values).any():
            return False
        if len(values) > 1 and np.any(np.diff(values) < -1e-6):
            return False
        return True

    async def _apply_measurement_correction(self, df_pvforecast: pd.DataFrame) -> pd.DataFrame:
        """Correct near-term PV forecast using the latest completed Victron 15-minute slot."""
        pv_meter_keys = self.config.measurement.pv_production_emr_keys
        if df_pvforecast.empty or not pv_meter_keys:
            return df_pvforecast

        measurement = get_measurement()
        reference_time = self._current_correction_time()
        search_start = reference_time.subtract(
            minutes=(
                self._measurement_correction_window_minutes
                + self._measurement_correction_max_age_minutes
                + self._measurement_correction_interval_minutes
            )
        )

        latest_meter_datetimes: list[DateTime] = []
        recent_meter_series: dict[str, pd.Series] = {}
        for key in pv_meter_keys:
            series = await measurement.key_to_raw_series(
                key=key,
                start_datetime=search_start,
                end_datetime=reference_time.add(seconds=1),
                dropna=True,
            )
            if series.empty:
                logger.debug(f"Victron PV correction skipped: no recent data for '{key}'")
                return df_pvforecast
            recent_meter_series[key] = series.sort_index()
            latest_meter_datetimes.append(
                to_datetime(series.index[-1], in_timezone=self.config.general.timezone)
            )

        latest_common = min(latest_meter_datetimes)
        correction_end = self._align_correction_end(latest_common)
        age_minutes = (reference_time - correction_end).total_seconds() / 60.0
        if age_minutes < 0 or age_minutes > self._measurement_correction_max_age_minutes:
            logger.debug(
                "Victron PV correction skipped: latest completed common meter slot "
                f"is {age_minutes:.1f} minutes old"
            )
            return df_pvforecast

        interval = to_duration(f"{self._measurement_correction_interval_minutes} minutes")
        correction_start = correction_end.subtract(
            minutes=self._measurement_correction_window_minutes
        )
        expected_intervals = (
            self._measurement_correction_window_minutes
            // self._measurement_correction_interval_minutes
        )
        expected_meter_values = expected_intervals + 1

        measured_energy_kwh = 0.0
        for key in pv_meter_keys:
            raw_series = recent_meter_series[key]
            if not self._raw_meter_window_is_complete(
                raw_series,
                correction_start,
                correction_end,
            ):
                logger.info(
                    "Victron PV correction skipped: waiting for a complete continuous "
                    f"{self._measurement_correction_window_minutes}-minute meter window for '{key}'"
                )
                return df_pvforecast

            meter_values = await measurement.key_to_array(
                key=key,
                start_datetime=correction_start,
                end_datetime=correction_end + interval,
                interval=interval,
                fill_method="time",
                boundary="context",
                align_to_interval=True,
            )
            if meter_values.size != expected_meter_values or any(
                value is None for value in meter_values
            ):
                logger.debug(
                    f"Victron PV correction skipped: incomplete meter window for '{key}'"
                )
                return df_pvforecast

            values = np.asarray(meter_values, dtype=float)
            if np.isnan(values).any():
                logger.debug(f"Victron PV correction skipped: invalid meter values for '{key}'")
                return df_pvforecast

            energy_delta = np.diff(values)
            if np.any(energy_delta < -1e-6):
                logger.warning(f"Victron PV correction skipped: meter reset detected for '{key}'")
                return df_pvforecast
            measured_energy_kwh += float(np.clip(energy_delta, 0.0, None).sum())

        forecast_index = pd.DatetimeIndex(df_pvforecast.index)
        window_mask = (forecast_index >= pd.Timestamp(correction_start)) & (
            forecast_index < pd.Timestamp(correction_end)
        )
        modeled_power_w = df_pvforecast.loc[window_mask, "ac_power"].astype(float)
        if len(modeled_power_w) != expected_intervals:
            logger.debug(
                "Victron PV correction skipped: PVLib history does not cover the full "
                f"{self._measurement_correction_window_minutes}-minute window"
            )
            return df_pvforecast

        interval_hours = self._measurement_correction_interval_minutes / 60.0
        modeled_energy_kwh = float(modeled_power_w.sum()) * interval_hours / 1000.0
        modeled_average_power_w = modeled_energy_kwh * 1000.0 / (
            self._measurement_correction_window_minutes / 60.0
        )
        if (
            modeled_energy_kwh <= 0.0
            or modeled_average_power_w < self._measurement_correction_min_model_power_w
        ):
            logger.debug(
                "Victron PV correction skipped: modeled PV power is too low for a stable ratio"
            )
            return df_pvforecast

        raw_factor = measured_energy_kwh / modeled_energy_kwh
        correction_factor = float(
            np.clip(
                raw_factor,
                self._measurement_correction_min_factor,
                self._measurement_correction_max_factor,
            )
        )

        corrected = df_pvforecast.copy()
        future_mask = forecast_index >= pd.Timestamp(reference_time)
        if not np.any(future_mask):
            return corrected

        elapsed_minutes = np.asarray(
            (forecast_index[future_mask] - pd.Timestamp(correction_end)).total_seconds() / 60.0,
            dtype=float,
        )
        elapsed_minutes = np.maximum(elapsed_minutes, 0.0)
        decay_weight = np.exp(-elapsed_minutes / self._measurement_correction_decay_minutes)
        future_factors = 1.0 + (correction_factor - 1.0) * decay_weight

        corrected.loc[future_mask, "ac_power"] = (
            corrected.loc[future_mask, "ac_power"].to_numpy(dtype=float) * future_factors
        )
        corrected.loc[future_mask, "pv_dc_power"] = (
            corrected.loc[future_mask, "pv_dc_power"].to_numpy(dtype=float) * future_factors
        )
        corrected["ac_power"] = corrected["ac_power"].clip(lower=0.0)
        corrected["pv_dc_power"] = corrected["pv_dc_power"].clip(lower=0.0)

        logger.info(
            "Applied Victron PV correction: "
            f"measured={measured_energy_kwh:.3f} kWh, "
            f"modeled={modeled_energy_kwh:.3f} kWh, "
            f"factor={correction_factor:.3f} (raw={raw_factor:.3f}), "
            f"slot_age={age_minutes:.1f} min"
        )
        return corrected