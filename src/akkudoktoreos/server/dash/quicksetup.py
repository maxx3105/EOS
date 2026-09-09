"""Helpers for the Synology/Victron browser quick setup."""

from __future__ import annotations

from typing import Any


VICTRON_48V_PROFILE_NAME = "48V / 3x MultiPlus-II 10000 / 4x MPPT"


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
    """Build the four DC-coupled PV groups of the configured Victron installation.

    The numeric ``inverter_model`` values deliberately select a CEC inverter model close
    to the 48 V MPPT nominal output. PVLib therefore models each MPPT group independently
    and clips it close to the charge-controller limit while EOS still exposes the summed
    result through its normal ``pvforecast_ac_power`` series.
    """
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
        # South: two SmartSolar MPPT 250/100, each with 3 strings x 5 LONGi 435 W.
        plane(south_azimuth, 435.0, 5, 3, 5800),
        plane(south_azimuth, 435.0, 5, 3, 5800),
        # South: one SmartSolar MPPT 250/60 with 1 string x 4 LONGi 435 W.
        plane(south_azimuth, 435.0, 4, 1, 3440),
        # North: one SmartSolar MPPT 250/100 with 5 strings x 5 Peimar 280 W.
        plane(north_azimuth, 280.0, 5, 5, 5800),
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
        # This installation is fully DC-coupled through SmartSolar MPPTs.
        ("adapter/victron/include_ac_coupled_pv", False),
        ("adapter/victron/pv_energy_key", "victron_pv_emr"),
        ("adapter/victron/max_integration_gap_minutes", 15.0),
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
        "configured": bool(_nested(config, "adapter", "victron", "host")),
    }
