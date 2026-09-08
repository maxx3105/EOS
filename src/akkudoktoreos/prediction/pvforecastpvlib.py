"""Calculates pvforecast forecast data using PVLib."""

import bz2
import pickle
from pathlib import Path
from typing import ClassVar, Literal, Optional, Union

import numpy as np
import pandas as pd
from loguru import logger
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import PVSystem, retrieve_sam
from pvlib.solarposition import get_solarposition
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

from akkudoktoreos.config.configabc import SettingsBaseModel
from akkudoktoreos.core.coreabc import PredictionMixin, get_config, get_measurement
from akkudoktoreos.prediction.pvforecastabc import PVForecastProvider
from akkudoktoreos.utils.datetimeutil import to_datetime, to_duration

DeviceType = Literal["module", "inverter"]


# Memory cache for CEC databases
_cec_cache: dict[Path, tuple[int, pd.DataFrame]] = {}


def _cec_modules_path() -> Path:
    """Provide path to the modules database."""
    try:
        return get_config().general.data_folder_path / "cec_modules.pbz2"
    except Exception:
        # Config may not be initialized
        return Path("modules_invalid_dummy_path")


def _cec_inverters_path() -> Path:
    """Provide path to the inverters database."""
    try:
        return get_config().general.data_folder_path / "cec_inverters.pbz2"
    except Exception:
        # Config may not be initialized
        return Path("inverters_invalid_dummy_path")


def _update_cec_database() -> None:
    """Build the EOS CEC module and inverter databases.

    This follows the EMHASS database generation procedure:

    - start with the current SAM database
    - restore models missing from the new SAM database
        but present in the PVLib database
    - add EMHASS custom module/inverter definitions
    - store compressed pickle databases

    Script taken from https://github.com/davidusb-geek/emhass/blob/master/scripts/save_pvlib_module_inverter_database.py
    """
    data_path = Path(__file__).parent.parent / "data"

    logger.info("Reading original outdated database bundled with PVLib")
    cec_modules_old = retrieve_sam("CECMod")
    cec_inverters_old = retrieve_sam("cecinverter")

    # Download from https://github.com/NatLabRockies/SAM/tree/develop/samples/CEC%20Module%20and%20Inverter%20Libraries/CEC%20Modules
    logger.info("Reading downloaded modules database from SAM")
    cec_modules = retrieve_sam(path=str(data_path / "cec_modules.csv"))
    cec_modules = cec_modules.loc[:, ~cec_modules.columns.duplicated()]

    # DOwnload from https://github.com/NatLabRockies/SAM/tree/develop/samples/CEC%20Module%20and%20Inverter%20Libraries/CEC%20Inverters
    logger.info("Reading downloaded inverters database from SAM")
    cec_inverters = retrieve_sam(path=str(data_path / "cec_inverters.csv"))
    cec_inverters = cec_inverters.loc[:, ~cec_inverters.columns.duplicated()]

    # Download from https://github.com/davidusb-geek/emhass/tree/master/src/emhass/data
    logger.info("Reading custom EMHASS database")
    cec_modules_emhass = retrieve_sam(path=str(data_path / "emhass_modules.csv"))
    cec_inverters_emhass = retrieve_sam(path=str(data_path / "emhass_inverters.csv"))

    #
    # Modules
    #

    cols_to_keep = [col for col in cec_modules_old.columns if col not in cec_modules.columns]

    cec_modules = pd.concat(
        [
            cec_modules,
            cec_modules_old[cols_to_keep],
        ],
        axis=1,
    )

    logger.info(f"Copied {len(cols_to_keep)} old PVLib module entries")

    cols_to_keep = [col for col in cec_modules_emhass.columns if col not in cec_modules.columns]

    cec_modules = pd.concat(
        [
            cec_modules,
            cec_modules_emhass[cols_to_keep],
        ],
        axis=1,
    )

    logger.info(f"Copied {len(cols_to_keep)} custom EMHASS module entries")

    #
    # Inverters
    #
    cols_to_keep = [col for col in cec_inverters_old.columns if col not in cec_inverters.columns]

    cec_inverters = pd.concat(
        [
            cec_inverters,
            cec_inverters_old[cols_to_keep],
        ],
        axis=1,
    )

    logger.info(f"Copied {len(cols_to_keep)} old PVLib inverter entries")

    cols_to_keep = [col for col in cec_inverters_emhass.columns if col not in cec_inverters.columns]

    cec_inverters = pd.concat(
        [
            cec_inverters,
            cec_inverters_emhass[cols_to_keep],
        ],
        axis=1,
    )

    logger.info(f"Copied {len(cols_to_keep)} custom EMHASS inverter entries")

    #
    # Save databases
    #
    with bz2.BZ2File(_cec_modules_path(), "wb") as file:
        pickle.dump(cec_modules, file)

    with bz2.BZ2File(_cec_inverters_path(), "wb") as file:
        pickle.dump(cec_inverters, file)

    logger.info(f"CEC databases written: {_cec_modules_path()}, {_cec_inverters_path()}")


def _load_cec_database(path: Path) -> pd.DataFrame:
    """Load a CEC database, reloading only if the file changed.

    If database does not exists it is created.
    """
    if not path.exists():
        # Create databases
        _update_cec_database()

    mtime = path.stat().st_mtime_ns

    cached = _cec_cache.get(path)
    if cached is not None:
        cached_mtime, database = cached
        if cached_mtime == mtime:
            return database

    with bz2.BZ2File(path, "rb") as f:
        database = pickle.load(f)  # noqa: S301

    _cec_cache[path] = (mtime, database)
    return database


def _cec_modules() -> pd.DataFrame:
    """Provide CEC modules database."""
    return _load_cec_database(_cec_modules_path())


def _cec_inverters() -> pd.DataFrame:
    """Provide CEC inverters database."""
    return _load_cec_database(_cec_inverters_path())


class PVForecastPVLibCommonSettings(SettingsBaseModel):
    """Common settings for pvforecast data calculation with PVLib."""

    # Nothing in here


class PVForecastPVLib(PredictionMixin, PVForecastProvider):
    """Calculate PV forecast data using PVLib."""

    _warned_features: ClassVar[set[str]] = set()

    # Measurement feedback is intentionally conservative. It uses one hour of
    # cumulative PV energy-meter readings, skips stale/noisy low-power periods,
    # and lets the correction decay back to the physical forecast over time.
    _measurement_correction_window_minutes: ClassVar[int] = 60
    _measurement_correction_interval_minutes: ClassVar[int] = 15
    _measurement_correction_max_age_minutes: ClassVar[int] = 30
    _measurement_correction_decay_minutes: ClassVar[float] = 180.0
    _measurement_correction_min_model_power_w: ClassVar[float] = 200.0
    _measurement_correction_min_factor: ClassVar[float] = 0.5
    _measurement_correction_max_factor: ClassVar[float] = 1.5

    @classmethod
    def provider_id(cls) -> str:
        """Return the unique identifier for the provider."""
        return "PVForecastPVLib"

    def _warn_once(self, feature: str, message: str) -> None:
        """Log a warning only once for this process."""
        if feature not in self._warned_features:
            self._warned_features.add(feature)
            logger.warning(message)

    def _get_model_power(self, params: pd.Series, device_type: DeviceType) -> Optional[float]:
        """Helper to extract power rating based on device type and available parameters."""
        if device_type == "module":
            if "STC" in params:
                return params["STC"]
            if "I_mp_ref" in params and "V_mp_ref" in params:
                return params["I_mp_ref"] * params["V_mp_ref"]
        elif device_type == "inverter":
            if "Paco" in params:
                return params["Paco"]
            if "Pdco" in params:
                return params["Pdco"]
        return None

    def _find_closest_model(
        self, target_power: float, database: pd.DataFrame, device_type: DeviceType
    ) -> Optional[pd.Series]:
        """Find the model in the database that has a power rating closest to the target_power."""
        closest_model = None
        min_diff = float("inf")
        # Handle DataFrame
        for _, params in database.items():
            power = self._get_model_power(params, device_type)
            if power is not None:
                diff = abs(power - target_power)
                if diff < min_diff:
                    min_diff = diff
                    closest_model = params
        if closest_model is not None:
            # Safely get name if it exists (DataFrame Series usually have a .name attribute)
            model_name = getattr(closest_model, "name", "unknown")
            logger.info(f"Closest {device_type} model to {target_power}W found: {model_name}")
        else:
            logger.warning(f"No suitable {device_type} model found close to {target_power}W")
        return closest_model

    def _get_model(
        self, model_spec: Union[str, int, float], database: pd.DataFrame, device_type: DeviceType
    ) -> Optional[pd.Series]:
        """Retrieve a model from the database by name or by power rating."""
        # If it's a string, try to find it by name
        if isinstance(model_spec, str):
            if model_spec in database:
                return database[model_spec]
            # If not found by name, check if it is a number string (e.g., "300")
            try:
                target_power = float(model_spec)
                return self._find_closest_model(target_power, database, device_type)
            except ValueError:
                # Not a number, fallback to original behavior (will likely raise KeyError later)
                logger.warning(f"{device_type} model '{model_spec}' not found in database.")
                return database[model_spec]
        # If it's a number (int or float), find closest model
        elif isinstance(model_spec, int | float):
            return self._find_closest_model(model_spec, database, device_type)
        else:
            logger.error(f"Invalid type for {device_type} model: {type(model_spec)}")
            return None

    def _calculate_pvlib_power(self, df_weather: pd.DataFrame) -> pd.DataFrame:
        """Simulate PV power generation using PVLib.

        Returns:
            Dataframe with pv_dc_power, ac_power

        Note:
            Taken from emhass
        """
        # Validate weather data
        required = [
            "temp_air",
            "ghi",
            "dni",
            "dhi",
        ]
        missing = df_weather[required].isna().any()
        if missing.any():
            raise ValueError(f"PV weather contains NaN values: {missing[missing].index.tolist()}")
        df_weather[required] = df_weather[required].astype(float)

        # Setting the main parameters of the PV plant
        location = Location(
            latitude=self.config.general.latitude, longitude=self.config.general.longitude
        )
        temp_params = TEMPERATURE_MODEL_PARAMETERS["sapm"]["close_mount_glass_glass"]

        def run_single_config(plane_idx: int) -> pd.DataFrame:
            """Inner helper to run a single simulation configuration.

            Returns:
                Dataframe with times, weather, solar_position, airmass, total_irrad, aoi,
                aoi_modifier, spectral_modifier, and effective_irradiance, cell_temperature,
                dc, ac, losses, diode_params (if dc_model is a single diode model).
            """
            plane = self.config.pvforecast.planes[plane_idx]

            # Check configuration
            # - warnings
            if plane.userhorizon is not None:
                self._warn_once(
                    "userhorizon",
                    f"userhorizon is currently not supported by the {self.provider_id()} provider.",
                )
            if plane.optimalangles:
                self._warn_once(
                    "optimalangles",
                    f"optimalangles is currently not supported by the {self.provider_id()} provider.",
                )
            if plane.loss not in (None, 0):
                self._warn_once(
                    "loss",
                    f"loss is currently not supported by the {self.provider_id()} provider.",
                )
            if plane.trackingtype not in (None, 0):
                self._warn_once(
                    "trackingtype",
                    f"trackingtype is currently not supported by the {self.provider_id()} provider.",
                )
            if plane.inverter_paco is not None:
                self._warn_once(
                    "inverter_paco",
                    f"inverter_paco is currently not supported by the {self.provider_id()} provider.",
                )
            # - mandatory parameters
            if plane.surface_tilt is None:
                raise ValueError(f"Plane {plane_idx}: surface_tilt must be configured.")
            if plane.surface_azimuth is None:
                raise ValueError(f"Plane {plane_idx}: surface_azimuth must be configured.")
            if plane.module_model is None:
                raise ValueError(f"Plane {plane_idx}: module_model must be configured.")
            module = self._get_model(plane.module_model, _cec_modules(), "module")

            if plane.inverter_model is None:
                raise ValueError(f"Plane {plane_idx}: inverter_model must be configured.")
            inverter = self._get_model(plane.inverter_model, _cec_inverters(), "inverter")

            if plane.modules_per_string is None:
                raise ValueError(f"Plane {plane_idx}: modules_per_string must be configured.")

            if plane.strings_per_inverter is None:
                raise ValueError(f"Plane {plane_idx}: strings_per_inverter must be configured.")

            mountingplace = plane.mountingplace.lower() if plane.mountingplace is not None else None
            if mountingplace == "building":
                temp_params = TEMPERATURE_MODEL_PARAMETERS["sapm"]["close_mount_glass_glass"]
            elif mountingplace == "free" or mountingplace is None:
                temp_params = TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
            else:
                raise ValueError(
                    f"Plane {plane_idx}: mountingplace '{plane.mountingplace}' invalid."
                )
            if plane.albedo is None:
                df_weather["albedo"] = 0.2  # Take a default
                self._warn_once(
                    f"Plane {plane_idx}: albedo",
                    f"Plane {plane_idx}: albedo set to 0.2 (was None).",
                )
            else:
                df_weather["albedo"] = plane.albedo

            system = PVSystem(
                surface_tilt=plane.surface_tilt,
                surface_azimuth=plane.surface_azimuth,
                module_parameters=module,
                inverter_parameters=inverter,
                temperature_model_parameters=temp_params,
                modules_per_string=plane.modules_per_string,
                strings_per_inverter=plane.strings_per_inverter,
            )

            mc = ModelChain(system, location, aoi_model="physical")

            # For testing split out parameter preparation
            # mc.prepare_inputs(df_weather)
            # print("surface_tilt:", plane.surface_tilt, type(plane.surface_tilt))
            # print("surface_azimuth:", plane.surface_azimuth, type(plane.surface_azimuth))
            # print("albedo:", plane.albedo, type(plane.albedo))
            # print("weather irradiance")
            # print(df_weather[["ghi", "dni", "dhi"]])
            # print("after prepare_inputs")
            # print("solar position")
            # print(mc.results.solar_position[["zenith", "azimuth"]])
            # print(mc.results.total_irrad)
            # print(mc.results.aoi)
            # print(mc.results.effective_irradiance)

            mc.run_model(df_weather)

            return mc.results

        df_pvforecast = pd.DataFrame(
            {
                "pv_dc_power": 0.0,
                "ac_power": 0.0,
            },
            index=df_weather.index,
        )
        for plane_idx in range(len(self.config.pvforecast.planes)):
            result = run_single_config(plane_idx)
            df_pvforecast["pv_dc_power"] += result.dc["p_mp"].fillna(0.0)
            df_pvforecast["ac_power"] += result.ac.fillna(0.0)

        # replace any negative PV values with zero
        df_pvforecast["pv_dc_power"] = df_pvforecast["pv_dc_power"].clip(lower=0.0)
        df_pvforecast["ac_power"] = df_pvforecast["ac_power"].clip(lower=0.0)

        return df_pvforecast

    async def _apply_measurement_correction(self, df_pvforecast: pd.DataFrame) -> pd.DataFrame:
        """Correct near-term PV forecast using recent measured PV production.

        PV production measurements in EOS are cumulative energy-meter readings in kWh.
        The correction compares measured energy over the latest complete one-hour window
        with the PVLib AC energy predicted for the same window. The resulting ratio is
        bounded and applied to future AC/DC power with an exponential decay back to 1.0.

        If PV meter keys are not configured, measurements are stale/incomplete, a meter
        reset is detected, or modeled power is too low for a stable ratio, the original
        physical forecast is returned unchanged.
        """
        pv_meter_keys = self.config.measurement.pv_production_emr_keys
        if df_pvforecast.empty or not pv_meter_keys:
            return df_pvforecast

        measurement = get_measurement()
        forecast_start = self.ems_start_datetime
        search_start = forecast_start.subtract(
            minutes=(
                self._measurement_correction_window_minutes
                + self._measurement_correction_max_age_minutes
                + self._measurement_correction_interval_minutes
            )
        )

        # Find the newest timestamp that is available for every configured PV meter.
        latest_meter_datetimes = []
        for key in pv_meter_keys:
            series = await measurement.key_to_raw_series(
                key=key,
                start_datetime=search_start,
                end_datetime=forecast_start.add(seconds=1),
                dropna=True,
            )
            if series.empty:
                logger.debug(f"PV measurement correction skipped: no recent data for '{key}'")
                return df_pvforecast
            latest_meter_datetimes.append(
                to_datetime(series.index[-1], in_timezone=self.config.general.timezone)
            )

        correction_end = min(latest_meter_datetimes)
        age_minutes = (forecast_start - correction_end).total_seconds() / 60.0
        if age_minutes < 0 or age_minutes > self._measurement_correction_max_age_minutes:
            logger.debug(
                "PV measurement correction skipped: latest common PV meter reading "
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
            meter_values = await measurement.key_to_array(
                key=key,
                start_datetime=correction_start,
                end_datetime=correction_end + interval,
                interval=interval,
                fill_method="time",
                boundary="context",
            )
            if meter_values.size != expected_meter_values or any(
                value is None for value in meter_values
            ):
                logger.debug(
                    f"PV measurement correction skipped: incomplete meter window for '{key}'"
                )
                return df_pvforecast

            values = np.asarray(meter_values, dtype=float)
            if np.isnan(values).any():
                logger.debug(
                    f"PV measurement correction skipped: invalid meter values for '{key}'"
                )
                return df_pvforecast

            energy_delta = np.diff(values)
            if np.any(energy_delta < -1e-6):
                logger.warning(
                    f"PV measurement correction skipped: meter reset detected for '{key}'"
                )
                return df_pvforecast
            measured_energy_kwh += float(np.clip(energy_delta, 0.0, None).sum())

        forecast_index = pd.DatetimeIndex(df_pvforecast.index)
        window_mask = (forecast_index >= pd.Timestamp(correction_start)) & (
            forecast_index < pd.Timestamp(correction_end)
        )
        modeled_power_w = df_pvforecast.loc[window_mask, "ac_power"].astype(float)
        if len(modeled_power_w) != expected_intervals:
            logger.debug(
                "PV measurement correction skipped: PVLib history does not cover the full "
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
                "PV measurement correction skipped: modeled PV power is too low for a stable ratio"
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
        future_mask = forecast_index >= pd.Timestamp(forecast_start)
        if not np.any(future_mask):
            return corrected

        elapsed_minutes = np.asarray(
            (forecast_index[future_mask] - pd.Timestamp(correction_end)).total_seconds()
            / 60.0,
            dtype=float,
        )
        elapsed_minutes = np.maximum(elapsed_minutes, 0.0)
        decay_weight = np.exp(
            -elapsed_minutes / self._measurement_correction_decay_minutes
        )
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
            "Applied PV measurement correction: "
            f"measured={measured_energy_kwh:.3f} kWh, "
            f"modeled={modeled_energy_kwh:.3f} kWh, "
            f"factor={correction_factor:.3f} (raw={raw_factor:.3f}), "
            f"measurement_age={age_minutes:.1f} min"
        )
        return corrected

    @staticmethod
    def compute_solar_angles(df: pd.DataFrame, latitude: float, longitude: float) -> pd.DataFrame:
        """Compute solar angles (elevation, azimuth) based on timestamps and location.

        :param df: DataFrame with a DateTime index.
        :param latitude: Latitude of the PV system.
        :param longitude: Longitude of the PV system.
        :return: DataFrame with added solar elevation and azimuth.
        """
        df = df.copy()
        solpos = get_solarposition(df.index, latitude, longitude)
        df["solar_elevation"] = solpos["elevation"]
        df["solar_azimuth"] = solpos["azimuth"]
        return df

    @staticmethod
    def add_cyclic_hour_features(df: pd.DataFrame) -> pd.DataFrame:
        """Encode the time of day as a continuous sin/cos pair.

        A raw integer hour feature is piecewise constant: with sub-hourly
        optimization time steps a (linear) regression model then produces a
        discontinuity at every hour boundary, which shows up as a sawtooth in
        the adjusted PV forecast. The cyclic encoding is computed from the
        fractional hour (hour + minute/60) so it evolves smoothly within the
        hour and stays continuous across midnight.

        :param df: DataFrame with a DateTime index.
        :type df: pd.DataFrame
        :return: DataFrame with added hour_sin and hour_cos columns.
        :rtype: pd.DataFrame
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have a DatetimeIndex to compute cyclic hour features.")
        df = df.copy()
        fractional_hour = df.index.hour + df.index.minute / 60.0  # type: ignore[attr-defined]
        df["hour_sin"] = np.sin(2 * np.pi * fractional_hour / 24.0)
        df["hour_cos"] = np.cos(2 * np.pi * fractional_hour / 24.0)
        return df

    async def _update_data(self, force_update: Optional[bool] = False) -> None:
        # Both _sequence_lock and _record_lock are already held by the caller.
        # Use internal sync methods only — never await public async counterparts.

        # Assure we have something to request PV power for.
        if not self.config.pvforecast.planes:
            # No planes for PV
            error_msg = "Requested PV forecast, but no planes configured."
            logger.error(f"Configuration error: {error_msg}")
            raise ValueError(error_msg)

        start_datetime = self.ems_start_datetime.start_of("day")
        end_datetime = self.ems_start_datetime.add(hours=self.config.prediction.hours)

        # Prepare weather data for the PV forecast calculation
        #
        # We need a dataframe with the following columns:
        # - "temp_air"              temperature_2m
        # - "relative_humidity"     relative_humidity_2m
        # - "precipitable_water"    precipitable_water (cm)
        # - "cloud_cover"           cloud_cover
        # - "wind_speed"            wind_speed_10m
        # - "ghi"                   shortwave_radiation_instant
        # - "dhi"                   diffuse_radiation_instant
        # - "dni"                   direct_normal_irradiance_instant
        #
        # Data shall be given in 15-minutes intervals
        keys = [
            "weather_temp_air",
            "weather_relative_humidity",
            "weather_preciptable_water",
            "weather_total_clouds",
            "weather_wind_speed",
            "weather_ghi",
            "weather_dhi",
            "weather_dni",
        ]
        df_weather = await self.prediction.keys_to_dataframe(
            keys=keys,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            interval=to_duration("15 minutes"),
            fill_method="linear",
            resample_method="mean",
            dropna=True,
            boundary="context",
            align_to_interval=True,
        )
        df_weather = df_weather.rename(
            columns={
                "weather_temp_air": "temp_air",
                "weather_relative_humidity": "relative_humidity",
                "weather_preciptable_water": "precipitable_water",
                "weather_total_clouds": "cloud_cover",
                "weather_wind_speed": "wind_speed",
                "weather_ghi": "ghi",
                "weather_dhi": "dhi",
                "weather_dni": "dni",
            }
        )

        # Calculate the PV forecast and correct the near term with measured PV production.
        df_pvforecast = self._calculate_pvlib_power(df_weather)
        df_pvforecast = await self._apply_measurement_correction(df_pvforecast)

        for row in df_pvforecast.itertuples():
            await self._update_value(row.Index, "pvforecast_dc_power", float(row.pv_dc_power))  # type: ignore
            await self._update_value(row.Index, "pvforecast_ac_power", float(row.ac_power))  # type: ignore
