"""Helpers for the Synology/Victron browser quick setup."""

from __future__ import annotations

from typing import Any


def _number(payload: dict[str, Any], key: str, label: str) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} ist ungültig.") from exc
    return value


def _positive_integer(payload: dict[str, Any], key: str, label: str) -> int:
    value = _number(payload, key, label)
    if not value.is_integer() or value < 1:
        raise ValueError(f"{label} muss eine positive ganze Zahl sein.")
    return int(value)


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
    azimuth = _number(payload, "azimuth", "Azimut")
    if not 0 <= tilt <= 90:
        raise ValueError("Modulneigung muss zwischen 0 und 90° liegen.")
    if not 0 <= azimuth <= 360:
        raise ValueError("Azimut muss zwischen 0 und 360° liegen.")

    module_power = _number(payload, "module_power", "Modulleistung")
    inverter_power = _number(payload, "inverter_power", "Wechselrichterleistung")
    if module_power <= 0 or inverter_power <= 0:
        raise ValueError("Leistungswerte müssen größer als 0 sein.")

    modules_per_string = _positive_integer(payload, "modules_per_string", "Module pro String")
    strings_per_inverter = _positive_integer(
        payload, "strings_per_inverter", "Strings pro Wechselrichter"
    )

    plane = {
        "surface_tilt": tilt,
        "surface_azimuth": azimuth,
        "peakpower": module_power * modules_per_string * strings_per_inverter / 1000.0,
        "mountingplace": "building",
        "loss": 0.0,
        "trackingtype": 0,
        "albedo": 0.2,
        "module_model": str(module_power),
        "inverter_model": str(inverter_power),
        "modules_per_string": modules_per_string,
        "strings_per_inverter": strings_per_inverter,
    }

    return [
        ("general/latitude", latitude),
        ("general/longitude", longitude),
        ("ems/mode", "PREDICTION"),
        ("ems/interval", 300.0),
        ("prediction/hours", 48),
        ("weather/provider", "OpenMeteo"),
        ("pvforecast/provider", "PVForecastPVLibVictron"),
        ("pvforecast/planes", [plane]),
        ("adapter/provider", ["Victron"]),
        ("adapter/victron/host", cerbo_host),
        ("adapter/victron/port", 502),
        ("adapter/victron/unit_id", 100),
        ("adapter/victron/timeout_sec", 3.0),
        ("adapter/victron/include_ac_coupled_pv", True),
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


def _numeric_model(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def quick_setup_state(config: dict[str, Any]) -> dict[str, Any]:
    """Extract values shown by the quick setup from the current EOS config."""
    planes = _nested(config, "pvforecast", "planes")
    plane = planes[0] if isinstance(planes, list) and planes and isinstance(planes[0], dict) else {}

    inverter_power = _numeric_model(plane.get("inverter_model"))
    if inverter_power is None:
        inverter_power = plane.get("inverter_paco")

    return {
        "latitude": _nested(config, "general", "latitude"),
        "longitude": _nested(config, "general", "longitude"),
        "cerbo_host": _nested(config, "adapter", "victron", "host"),
        "tilt": plane.get("surface_tilt"),
        "azimuth": plane.get("surface_azimuth"),
        "module_power": _numeric_model(plane.get("module_model")),
        "modules_per_string": plane.get("modules_per_string"),
        "strings_per_inverter": plane.get("strings_per_inverter"),
        "inverter_power": inverter_power,
        "configured": bool(_nested(config, "adapter", "victron", "host")),
    }
