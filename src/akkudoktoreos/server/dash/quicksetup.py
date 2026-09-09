"""Helpers for the Synology/Victron browser quick setup."""

from __future__ import annotations

from typing import Any


VICTRON_48V_PROFILE_NAME = "48V / 3x MultiPlus-II 10000 / 4x MPPT + HMS-800W-2T AC-out"
PYLONTECH_PROFILE_NAME = "4x US5000 + 1x US3000C + 7x US2000C"
EVCS_PROFILE_NAME = "2x Victron EV Charging Station 32A / 3-phasig / auf 16A begrenzt"
HOYMILES_PROFILE_NAME = "Hoymiles HMS-800W-2T / 2x LONGi 435 W / Ost / AC-out"
HOYMILES_INVERTER_MODEL = "Hoymiles_HMS_800W_2T_AC_OUT"
HOYMILES_MODULE_POWER_W = 435
HOYMILES_MODULE_COUNT = 2
HOYMILES_PEAKPOWER_KW = 0.870
HOYMILES_AC_LIMIT_W = 800
HOYMILES_EFFICIENCY = 0.967
HOYMILES_TILT_DEG = 70.0
HOYMILES_AZIMUTH_DEG = 90.0
PYLONTECH_CAPACITY_WH = 39_552
PYLONTECH_USABLE_95_DOD_WH = 37_574
MULTIPLUS_CONTINUOUS_POWER_W = 8_000
MULTIPLUS_COUNT = 3
MULTIPLUS_CHARGE_POWER_W = 7_350
EVCS_COUNT = 2
EVCS_MAX_CURRENT_A = 16
EVCS_MAX_POWER_W = 11_000
EVCS_UNIT_IDS = [40, 41]
EV_TARGET_SOC_PERCENT = 80
RENAULT_R5_CAPACITY_WH = 52_000
RENAULT_MEGANE_CAPACITY_WH = 60_000
BASE_LOAD_ENERGY_KEY = "victron_base_load_emr"


def _number(payload: dict[str, Any], key: str, label: str) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} ist ungültig.") from exc
    return value


def _number_default(payload: dict[str, Any], key: str, label: str, default: float) -> float:
    try:
        value = float(payload.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} ist ungültig.") from exc
    return value


def _validate_azimuth(value: float, label: str) -> float:
    if not 0 <= value <= 360:
        raise ValueError(f"{label} muss zwischen 0 und 360° liegen.")
    return value


def build_victron_48v_planes(
    *,
    tilt: float = 25.0,
    south_azimuth: float = 180.0,
    north_azimuth: float = 0.0,
    east_tilt: float = HOYMILES_TILT_DEG,
    east_azimuth: float = HOYMILES_AZIMUTH_DEG,
) -> list[dict[str, Any]]:
    """Build four DC-coupled SmartSolar groups plus the AC-out Hoymiles group."""
    if not 0 <= tilt <= 90:
        raise ValueError("Modulneigung muss zwischen 0 und 90° liegen.")
    if not 0 <= east_tilt <= 90:
        raise ValueError("Hoymiles-Modulneigung muss zwischen 0 und 90° liegen.")
    south_azimuth = _validate_azimuth(south_azimuth, "Süd-Azimut")
    north_azimuth = _validate_azimuth(north_azimuth, "Nord-Azimut")
    east_azimuth = _validate_azimuth(east_azimuth, "Hoymiles-Ost-Azimut")

    def dc_plane(
        azimuth: float,
        module_power_w: float,
        modules_per_string: int,
        strings: int,
        mppt_power_w: int,
    ) -> dict[str, Any]:
        return {
            "surface_tilt": tilt,
            "surface_azimuth": azimuth,
            "peakpower": module_power_w * modules_per_string * strings / 1000.0,
            "mountingplace": "building",
            "loss": 0.0,
            "trackingtype": 0,
            "albedo": 0.2,
            "module_model": str(module_power_w),
            "inverter_model": str(mppt_power_w),
            "modules_per_string": modules_per_string,
            "strings_per_inverter": strings,
        }

    hoymiles_plane = {
        "surface_tilt": east_tilt,
        "surface_azimuth": east_azimuth,
        "peakpower": HOYMILES_PEAKPOWER_KW,
        "mountingplace": "building",
        "loss": 0.0,
        "trackingtype": 0,
        "albedo": 0.2,
        "module_model": str(float(HOYMILES_MODULE_POWER_W)),
        # Named model is deliberately distinct from the numeric SmartSolar convention.
        # PVForecastPVLibVictron maps it to an AC microinverter with an 800 W output cap.
        "inverter_model": HOYMILES_INVERTER_MODEL,
        # HMS-800W-2T has two independent MPPT inputs; both modules have the same orientation.
        "modules_per_string": 1,
        "strings_per_inverter": HOYMILES_MODULE_COUNT,
    }

    return [
        dc_plane(south_azimuth, 435.0, 5, 3, 5800),
        dc_plane(south_azimuth, 435.0, 5, 3, 5800),
        dc_plane(south_azimuth, 435.0, 4, 1, 3440),
        dc_plane(north_azimuth, 280.0, 5, 5, 5800),
        hoymiles_plane,
    ]


def build_pylontech_battery(min_soc_percentage: int = 10) -> dict[str, Any]:
    """Build the aggregate Pylontech battery bank used by the three-phase Victron system."""
    if not 0 <= min_soc_percentage <= 100:
        raise ValueError("Mindest-SOC muss zwischen 0 und 100 % liegen.")
    return {
        "device_id": "battery1",
        "capacity_wh": PYLONTECH_CAPACITY_WH,
        "charging_efficiency": 1.0,
        "discharging_efficiency": 1.0,
        "max_charge_power_w": MULTIPLUS_CONTINUOUS_POWER_W * MULTIPLUS_COUNT,
        "min_charge_power_w": 50,
        "min_soc_percentage": min_soc_percentage,
        "max_soc_percentage": 100,
    }


def build_multiplus_inverters() -> list[dict[str, Any]]:
    """Build the three phase MultiPlus-II 48/10000/140-100 devices."""
    return [
        {
            "device_id": f"multiplus-l{phase}",
            "max_power_w": MULTIPLUS_CONTINUOUS_POWER_W,
            "battery_id": "battery1",
            "ac_to_dc_efficiency": 0.95,
            "dc_to_ac_efficiency": 0.95,
            "max_ac_charge_power_w": MULTIPLUS_CHARGE_POWER_W,
        }
        for phase in (1, 2, 3)
    ]


def build_electric_vehicles(
    target_soc_percentage: int = EV_TARGET_SOC_PERCENT,
) -> list[dict[str, Any]]:
    """Build EVs for surplus charging without a fixed departure deadline.

    ``max_soc_percentage`` is used as the preferred upper SOC boundary. No departure time
    is configured because the installation is operated around a rotating four-shift schedule.
    The system remains prediction-only, so these settings do not actuate either EVCS.
    """
    if not 0 <= target_soc_percentage <= 100:
        raise ValueError("EV-Ziel-SOC muss zwischen 0 und 100 % liegen.")

    charge_rates = [0.0, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]

    def vehicle(device_id: str, capacity_wh: int) -> dict[str, Any]:
        return {
            "device_id": device_id,
            "capacity_wh": capacity_wh,
            "charging_efficiency": 1.0,
            "discharging_efficiency": 1.0,
            "max_charge_power_w": EVCS_MAX_POWER_W,
            "min_charge_power_w": 4_100,
            "charge_rates": charge_rates,
            "min_soc_percentage": 0,
            "max_soc_percentage": target_soc_percentage,
        }

    return [
        vehicle("renault-r5", RENAULT_R5_CAPACITY_WH),
        vehicle("renault-megane-e-tech", RENAULT_MEGANE_CAPACITY_WH),
    ]


def build_quick_setup_updates(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    """Validate browser payload and return EOS REST config updates."""
    latitude = _number(payload, "latitude", "Breitengrad")
    longitude = _number(payload, "longitude", "Längengrad")
    if not -90 <= latitude <= 90:
        raise ValueError("Breitengrad muss zwischen -90 und 90 liegen.")
    if not -180 <= longitude <= 180:
        raise ValueError("Längengrad muss zwischen -180 und 180 liegen.")

    cerbo_host = str(payload.get("cerbo_host", "")).strip()
    if not cerbo_host:
        raise ValueError("Bitte die IP-Adresse oder den Hostnamen des Cerbo GX eintragen.")

    tilt = _number(payload, "tilt", "Modulneigung")
    south_azimuth = _number(payload, "south_azimuth", "Süd-Azimut")
    north_azimuth = _number(payload, "north_azimuth", "Nord-Azimut")
    east_tilt = _number_default(payload, "east_tilt", "Hoymiles-Modulneigung", HOYMILES_TILT_DEG)
    east_azimuth = _number_default(
        payload, "east_azimuth", "Hoymiles-Ost-Azimut", HOYMILES_AZIMUTH_DEG
    )
    min_soc = int(_number(payload, "min_soc", "Mindest-SOC / Inselreserve"))
    try:
        ev_target_soc = int(float(payload.get("ev_target_soc", EV_TARGET_SOC_PERCENT)))
    except (TypeError, ValueError) as exc:
        raise ValueError("EV-Ziel-SOC ist ungültig.") from exc
    if not 0 <= ev_target_soc <= 100:
        raise ValueError("EV-Ziel-SOC muss zwischen 0 und 100 % liegen.")

    planes = build_victron_48v_planes(
        tilt=tilt,
        south_azimuth=south_azimuth,
        north_azimuth=north_azimuth,
        east_tilt=east_tilt,
        east_azimuth=east_azimuth,
    )

    return [
        ("general/latitude", latitude),
        ("general/longitude", longitude),
        ("ems/mode", "PREDICTION"),
        ("ems/interval", 300.0),
        ("prediction/hours", 48),
        ("weather/provider", "OpenMeteo"),
        ("pvforecast/provider", "PVForecastPVLibVictron"),
        ("pvforecast/planes", planes),
        ("load/provider", "LoadVictronHistory"),
        ("measurement/load_emr_keys", [BASE_LOAD_ENERGY_KEY]),
        ("adapter/provider", ["Victron"]),
        ("adapter/victron/host", cerbo_host),
        ("adapter/victron/port", 502),
        ("adapter/victron/unit_id", 100),
        ("adapter/victron/timeout_sec", 3.0),
        # The Hoymiles is connected on AC-out and is exposed by the GX system service as
        # AC-coupled PV. Include those values in the total PV meter used for live correction.
        ("adapter/victron/include_ac_coupled_pv", True),
        ("adapter/victron/pv_energy_key", "victron_pv_emr"),
        ("adapter/victron/load_energy_key", "victron_load_emr"),
        ("adapter/victron/base_load_energy_key", BASE_LOAD_ENERGY_KEY),
        ("adapter/victron/evcs_unit_ids", EVCS_UNIT_IDS),
        ("adapter/victron/evcs_energy_key_prefix", "victron_evcs"),
        ("adapter/victron/max_integration_gap_minutes", 15.0),
        ("devices/max_batteries", 1),
        ("devices/batteries", [build_pylontech_battery(min_soc)]),
        ("devices/max_inverters", 3),
        ("devices/inverters", build_multiplus_inverters()),
        ("devices/max_electric_vehicles", 2),
        ("devices/electric_vehicles", build_electric_vehicles(ev_target_soc)),
    ]


def _nested(config: dict[str, Any], *keys: str) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def quick_setup_state(config: dict[str, Any]) -> dict[str, Any]:
    """Extract values shown by the quick setup from the current EOS config."""
    planes = _nested(config, "pvforecast", "planes")
    valid_planes = [plane for plane in planes or [] if isinstance(plane, dict)]
    first_plane = valid_planes[0] if valid_planes else {}
    north_plane = valid_planes[3] if len(valid_planes) >= 4 else {}
    hoymiles_plane = valid_planes[4] if len(valid_planes) >= 5 else {}

    total_peakpower = 0.0
    for plane in valid_planes:
        try:
            total_peakpower += float(plane.get("peakpower") or 0.0)
        except (TypeError, ValueError):
            pass

    batteries = _nested(config, "devices", "batteries")
    battery = batteries[0] if isinstance(batteries, list) and batteries else {}
    inverters = _nested(config, "devices", "inverters")
    inverter_count = len(inverters) if isinstance(inverters, list) else 0
    battery_capacity = battery.get("capacity_wh") if isinstance(battery, dict) else None
    min_soc = battery.get("min_soc_percentage") if isinstance(battery, dict) else None

    evs = _nested(config, "devices", "electric_vehicles")
    valid_evs = [ev for ev in evs or [] if isinstance(ev, dict)]
    ev_by_id = {str(ev.get("device_id")): ev for ev in valid_evs}
    r5 = ev_by_id.get("renault-r5", {})
    megane = ev_by_id.get("renault-megane-e-tech", {})
    r5_target = r5.get("max_soc_percentage")
    megane_target = megane.get("max_soc_percentage")
    ev_target_soc = r5_target if r5_target is not None else EV_TARGET_SOC_PERCENT
    ev_profile_active = (
        r5.get("capacity_wh") == RENAULT_R5_CAPACITY_WH
        and megane.get("capacity_wh") == RENAULT_MEGANE_CAPACITY_WH
        and r5.get("max_charge_power_w") == EVCS_MAX_POWER_W
        and megane.get("max_charge_power_w") == EVCS_MAX_POWER_W
        and r5_target == megane_target
    )

    load_provider = _nested(config, "load", "provider")
    load_keys = _nested(config, "measurement", "load_emr_keys") or []
    evcs_unit_ids = _nested(config, "adapter", "victron", "evcs_unit_ids") or []
    base_load_energy_key = (
        _nested(config, "adapter", "victron", "base_load_energy_key") or BASE_LOAD_ENERGY_KEY
    )
    include_ac_coupled_pv = bool(
        _nested(config, "adapter", "victron", "include_ac_coupled_pv")
    )
    evcs_measurement_active = sorted(evcs_unit_ids) == sorted(EVCS_UNIT_IDS)
    hoymiles_active = (
        hoymiles_plane.get("inverter_model") == HOYMILES_INVERTER_MODEL
        and abs(float(hoymiles_plane.get("peakpower") or 0.0) - HOYMILES_PEAKPOWER_KW) < 0.01
        and hoymiles_plane.get("modules_per_string") == 1
        and hoymiles_plane.get("strings_per_inverter") == 2
        and include_ac_coupled_pv
    )

    return {
        "latitude": _nested(config, "general", "latitude"),
        "longitude": _nested(config, "general", "longitude"),
        "cerbo_host": _nested(config, "adapter", "victron", "host"),
        "tilt": first_plane.get("surface_tilt"),
        "south_azimuth": first_plane.get("surface_azimuth"),
        "north_azimuth": north_plane.get("surface_azimuth"),
        "east_tilt": hoymiles_plane.get("surface_tilt"),
        "east_azimuth": hoymiles_plane.get("surface_azimuth"),
        "plane_count": len(valid_planes),
        "total_peakpower": round(total_peakpower, 3),
        "profile_active": (
            len(valid_planes) == 5
            and abs(total_peakpower - (21.79 + HOYMILES_PEAKPOWER_KW)) < 0.05
            and hoymiles_active
        ),
        "hoymiles_active": hoymiles_active,
        "include_ac_coupled_pv": include_ac_coupled_pv,
        "battery_capacity_wh": battery_capacity,
        "min_soc": min_soc,
        "battery_profile_active": battery_capacity == PYLONTECH_CAPACITY_WH and inverter_count == 3,
        "ev_count": len(valid_evs),
        "ev_target_soc": ev_target_soc,
        "ev_profile_active": ev_profile_active,
        "evcs_unit_ids": evcs_unit_ids,
        "evcs_measurement_active": evcs_measurement_active,
        "load_provider": load_provider,
        "load_forecast_active": (
            load_provider == "LoadVictronHistory" and base_load_energy_key in load_keys
        ),
        "configured": bool(_nested(config, "adapter", "victron", "host")),
    }
