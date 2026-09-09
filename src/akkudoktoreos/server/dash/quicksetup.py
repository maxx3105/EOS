"""Helpers for the Synology/Victron browser quick setup."""

from __future__ import annotations

from typing import Any


VICTRON_48V_PROFILE_NAME = "48V / 3x MultiPlus-II 10000 / 4x MPPT"
PYLONTECH_PROFILE_NAME = "4x US5000 + 1x US3000C + 7x US2000C"
EVCS_PROFILE_NAME = "2x Victron EV Charging Station 32A / 3-phasig / auf 16A begrenzt"
PYLONTECH_CAPACITY_WH = 39_552
PYLONTECH_USABLE_95_DOD_WH = 37_574
MULTIPLUS_CONTINUOUS_POWER_W = 8_000
MULTIPLUS_COUNT = 3
MULTIPLUS_CHARGE_POWER_W = 7_350
EVCS_COUNT = 2
EVCS_MAX_CURRENT_A = 16
EVCS_MAX_POWER_W = 11_000
RENAULT_R5_CAPACITY_WH = 52_000
RENAULT_MEGANE_CAPACITY_WH = 60_000


def _number(payload: dict[str, Any], key: str, label: str) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} ist ungültig.") from exc
    return value


def _validate_azimuth(value: float, label: str) -> float:
    if not 0 <= value <= 360:
        raise ValueError(f"{label} muss zwischen 0 und 360° liegen.")
    return value


def build_victron_48v_planes(
    *, tilt: float = 25.0, south_azimuth: float = 180.0, north_azimuth: float = 0.0
) -> list[dict[str, Any]]:
    """Build the four DC-coupled PV groups of the configured Victron installation."""
    if not 0 <= tilt <= 90:
        raise ValueError("Modulneigung muss zwischen 0 und 90° liegen.")
    south_azimuth = _validate_azimuth(south_azimuth, "Süd-Azimut")
    north_azimuth = _validate_azimuth(north_azimuth, "Nord-Azimut")

    def plane(
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

    return [
        plane(south_azimuth, 435.0, 5, 3, 5800),
        plane(south_azimuth, 435.0, 5, 3, 5800),
        plane(south_azimuth, 435.0, 4, 1, 3440),
        plane(north_azimuth, 280.0, 5, 5, 5800),
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


def build_electric_vehicles() -> list[dict[str, Any]]:
    """Build the two Renault EVs assigned to the 16 A three-phase charging points.

    The charge-rate factors represent useful current steps between roughly 6 A and 16 A.
    The system remains prediction-only, so these settings do not actuate either EVCS.
    """
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
            "max_soc_percentage": 100,
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
    min_soc = int(_number(payload, "min_soc", "Mindest-SOC"))
    planes = build_victron_48v_planes(
        tilt=tilt,
        south_azimuth=south_azimuth,
        north_azimuth=north_azimuth,
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
        ("adapter/provider", ["Victron"]),
        ("adapter/victron/host", cerbo_host),
        ("adapter/victron/port", 502),
        ("adapter/victron/unit_id", 100),
        ("adapter/victron/timeout_sec", 3.0),
        ("adapter/victron/include_ac_coupled_pv", False),
        ("adapter/victron/pv_energy_key", "victron_pv_emr"),
        ("adapter/victron/max_integration_gap_minutes", 15.0),
        ("devices/max_batteries", 1),
        ("devices/batteries", [build_pylontech_battery(min_soc)]),
        ("devices/max_inverters", 3),
        ("devices/inverters", build_multiplus_inverters()),
        ("devices/max_electric_vehicles", 2),
        ("devices/electric_vehicles", build_electric_vehicles()),
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
    last_plane = valid_planes[-1] if valid_planes else {}

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
    ev_profile_active = (
        r5.get("capacity_wh") == RENAULT_R5_CAPACITY_WH
        and megane.get("capacity_wh") == RENAULT_MEGANE_CAPACITY_WH
        and r5.get("max_charge_power_w") == EVCS_MAX_POWER_W
        and megane.get("max_charge_power_w") == EVCS_MAX_POWER_W
    )

    return {
        "latitude": _nested(config, "general", "latitude"),
        "longitude": _nested(config, "general", "longitude"),
        "cerbo_host": _nested(config, "adapter", "victron", "host"),
        "tilt": first_plane.get("surface_tilt"),
        "south_azimuth": first_plane.get("surface_azimuth"),
        "north_azimuth": last_plane.get("surface_azimuth"),
        "plane_count": len(valid_planes),
        "total_peakpower": round(total_peakpower, 3),
        "profile_active": len(valid_planes) == 4 and abs(total_peakpower - 21.79) < 0.05,
        "battery_capacity_wh": battery_capacity,
        "min_soc": min_soc,
        "battery_profile_active": battery_capacity == PYLONTECH_CAPACITY_WH and inverter_count == 3,
        "ev_count": len(valid_evs),
        "ev_profile_active": ev_profile_active,
        "configured": bool(_nested(config, "adapter", "victron", "host")),
    }
