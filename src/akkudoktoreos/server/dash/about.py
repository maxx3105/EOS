from typing import Any

import requests
from fasthtml.common import A, Button, Div, H2, Input, Label, P, Script

from akkudoktoreos.config.configabc import runtime_environment
from akkudoktoreos.core.coreabc import get_config
from akkudoktoreos.core.version import __version__
from akkudoktoreos.server.dash.markdown import Markdown
from akkudoktoreos.server.dash.quicksetup import (
    PYLONTECH_CAPACITY_WH,
    PYLONTECH_PROFILE_NAME,
    PYLONTECH_USABLE_95_DOD_WH,
    VICTRON_48V_PROFILE_NAME,
    quick_setup_state,
)

about_md = f"""![Logo](/eosdash/assets/logo.png)

# Akkudoktor EOSdash

EOS für PV-Prognose, Energiemanagement und Optimierung.

Für die Synology-/Victron-Variante kann die Grundeinrichtung direkt oben im Browser erledigt werden.
Die ausführliche Konfiguration bleibt anschließend unter **Config** verfügbar.

---

## Version

**Akkudoktor-EOS:** {__version__}

**Umgebung:** {runtime_environment()}

**Lizenz:** Apache License

"""

_SETUP_SCRIPT = r"""
async function eosSetupUpdate(key, value) {
    const body = new URLSearchParams({
        action: "update",
        key: key,
        value: JSON.stringify(value)
    });
    const response = await fetch("/eosdash/configuration", {
        method: "PUT",
        headers: {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        body: body
    });
    const text = await response.text();
    if (!response.ok || text.includes("Can not set " + key + " on ")) {
        throw new Error(key + " konnte nicht übernommen werden. " + text.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").slice(0, 700));
    }
}

function eosSetupNumber(id, label) {
    const raw = document.getElementById(id).value.trim();
    const value = Number(raw);
    if (!raw || !Number.isFinite(value)) {
        throw new Error(label + " ist ungültig.");
    }
    return value;
}

function eosVictronPlane(tilt, azimuth, modulePower, modulesPerString, strings, mpptPower) {
    return {
        surface_tilt: tilt,
        surface_azimuth: azimuth,
        peakpower: modulePower * modulesPerString * strings / 1000.0,
        mountingplace: "building",
        loss: 0.0,
        trackingtype: 0,
        albedo: 0.2,
        module_model: String(modulePower),
        inverter_model: String(mpptPower),
        modules_per_string: modulesPerString,
        strings_per_inverter: strings
    };
}

function eosBuildVictron48VPlanes(tilt, southAzimuth, northAzimuth) {
    return [
        eosVictronPlane(tilt, southAzimuth, 435, 5, 3, 5800),
        eosVictronPlane(tilt, southAzimuth, 435, 5, 3, 5800),
        eosVictronPlane(tilt, southAzimuth, 435, 4, 1, 3440),
        eosVictronPlane(tilt, northAzimuth, 280, 5, 5, 5800)
    ];
}

function eosBuildPylontechBattery(minSoc) {
    return {
        device_id: "battery1",
        capacity_wh: 39552,
        charging_efficiency: 1.0,
        discharging_efficiency: 1.0,
        max_charge_power_w: 24000,
        min_charge_power_w: 50,
        min_soc_percentage: minSoc,
        max_soc_percentage: 100
    };
}

function eosBuildMultiplusInverters() {
    return [1, 2, 3].map((phase) => ({
        device_id: "multiplus-l" + phase,
        max_power_w: 8000,
        battery_id: "battery1",
        ac_to_dc_efficiency: 0.95,
        dc_to_ac_efficiency: 0.95,
        max_ac_charge_power_w: 7350
    }));
}

async function eosRunQuickSetup() {
    const status = document.getElementById("eos-setup-status");
    const button = document.getElementById("eos-setup-save");
    button.disabled = true;
    status.textContent = "Einstellungen werden gespeichert …";
    status.className = "mt-3 text-sm";

    try {
        const latitude = eosSetupNumber("eos-setup-latitude", "Breitengrad");
        const longitude = eosSetupNumber("eos-setup-longitude", "Längengrad");
        if (latitude < -90 || latitude > 90) throw new Error("Breitengrad muss zwischen -90 und 90 liegen.");
        if (longitude < -180 || longitude > 180) throw new Error("Längengrad muss zwischen -180 und 180 liegen.");

        const cerboHost = document.getElementById("eos-setup-cerbo").value.trim();
        if (!cerboHost) throw new Error("Bitte die IP-Adresse oder den Hostnamen des Cerbo GX eintragen.");

        const tilt = eosSetupNumber("eos-setup-tilt", "Modulneigung");
        const southAzimuth = eosSetupNumber("eos-setup-south-azimuth", "Süd-Azimut");
        const northAzimuth = eosSetupNumber("eos-setup-north-azimuth", "Nord-Azimut");
        if (tilt < 0 || tilt > 90) throw new Error("Modulneigung muss zwischen 0 und 90° liegen.");
        if (southAzimuth < 0 || southAzimuth > 360) throw new Error("Süd-Azimut muss zwischen 0 und 360° liegen.");
        if (northAzimuth < 0 || northAzimuth > 360) throw new Error("Nord-Azimut muss zwischen 0 und 360° liegen.");

        const minSoc = eosSetupNumber("eos-setup-min-soc", "Mindest-SOC");
        if (!Number.isInteger(minSoc) || minSoc < 0 || minSoc > 100) {
            throw new Error("Mindest-SOC muss eine ganze Zahl zwischen 0 und 100 % sein.");
        }

        const planes = eosBuildVictron48VPlanes(tilt, southAzimuth, northAzimuth);
        const battery = eosBuildPylontechBattery(minSoc);
        const inverters = eosBuildMultiplusInverters();

        const updates = [
            ["general.latitude", latitude],
            ["general.longitude", longitude],
            ["ems.mode", "PREDICTION"],
            ["ems.interval", 300.0],
            ["prediction.hours", 48],
            ["weather.provider", "OpenMeteo"],
            ["pvforecast.provider", "PVForecastPVLibVictron"],
            ["pvforecast.planes", planes],
            ["adapter.provider", ["Victron"]],
            ["adapter.victron.host", cerboHost],
            ["adapter.victron.port", 502],
            ["adapter.victron.unit_id", 100],
            ["adapter.victron.timeout_sec", 3.0],
            ["adapter.victron.include_ac_coupled_pv", false],
            ["adapter.victron.pv_energy_key", "victron_pv_emr"],
            ["adapter.victron.max_integration_gap_minutes", 15.0],
            ["devices.max_batteries", 1],
            ["devices.batteries", [battery]],
            ["devices.max_inverters", 3],
            ["devices.inverters", inverters]
        ];

        for (const [key, value] of updates) {
            status.textContent = "Speichere " + key + " …";
            await eosSetupUpdate(key, value);
        }

        status.textContent = "Schreibe Konfiguration dauerhaft auf die NAS …";
        const saveResponse = await fetch("/eosdash/admin", {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            body: new URLSearchParams({category: "configuration", action: "save_to_file"})
        });
        const saveText = await saveResponse.text();
        if (!saveResponse.ok || saveText.includes("Can not save actual config") || !saveText.includes("Saved configuration to")) {
            throw new Error("Die Werte wurden an EOS übertragen, aber das dauerhafte Schreiben nach /data/config/EOS.config.json konnte nicht bestätigt werden.");
        }

        status.textContent = "✓ Dauerhaft gespeichert: PV 21,79 kWp + Pylontech 39,552 kWh. Die Seite wird neu geladen …";
        status.className = "mt-3 text-sm text-green-700 font-semibold";
        document.getElementById("eos-setup-next").style.display = "inline-block";
        setTimeout(() => window.location.reload(), 1200);
    } catch (error) {
        status.textContent = "Fehler: " + error.message;
        status.className = "mt-3 text-sm text-red-700 font-semibold";
    } finally {
        button.disabled = false;
    }
}
"""


def _field(
    label: str,
    input_id: str,
    value: str,
    *,
    input_type: str = "text",
    help_text: str = "",
    step: str | None = None,
) -> Div:
    input_kwargs: dict[str, Any] = {
        "id": input_id,
        "value": value,
        "type": input_type,
        "cls": "w-full border rounded px-3 py-2",
    }
    if input_type == "number":
        input_kwargs["step"] = step or "any"

    return Div(
        Label(label, fr=input_id, cls="font-semibold block mb-1"),
        Input(**input_kwargs),
        P(help_text, cls="text-xs opacity-70 mt-1") if help_text else None,
        cls="mb-3",
    )


def _current_quick_setup_state() -> dict[str, Any]:
    """Read the effective settings from the running EOS server for display."""
    config_eos = get_config()
    host = str(config_eos.server.host or "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = int(config_eos.server.port or 8503)

    try:
        response = requests.get(f"http://{host}:{port}/v1/config", timeout=5)
        response.raise_for_status()
        return quick_setup_state(response.json())
    except Exception:
        return {}


def _display_value(state: dict[str, Any], key: str, default: str) -> str:
    value = state.get(key)
    return default if value is None or value == "" else str(value)


def QuickSetup() -> Div:
    """Simple first-run setup for the Synology + Victron use case."""
    state = _current_quick_setup_state()
    configured = bool(state.get("configured"))
    profile_active = bool(state.get("profile_active"))
    battery_profile_active = bool(state.get("battery_profile_active"))

    return Div(
        H2("Schnelleinrichtung: Synology + Victron Cerbo GX", cls="text-2xl font-bold mb-2"),
        P(
            "Die Felder zeigen die aktuell in EOS gespeicherten Werte. PV, Batterie und die drei MultiPlus werden als Anlagenprofil verwaltet.",
            cls="mb-2",
        ),
        P(
            "✓ Gespeicherte Cerbo-Konfiguration erkannt." if configured else "Noch keine Cerbo-Konfiguration gespeichert.",
            cls="text-sm mb-1 text-green-700 font-semibold" if configured else "text-sm mb-1 opacity-70",
        ),
        P(
            "✓ 4-MPPT-Profil aktiv (21,79 kWp)." if profile_active else "Das 4-MPPT-Profil wird beim nächsten Speichern angewendet.",
            cls="text-sm mb-1 text-green-700 font-semibold" if profile_active else "text-sm mb-1 opacity-70",
        ),
        P(
            "✓ Pylontech-/MultiPlus-Profil aktiv (39,552 kWh)." if battery_profile_active else "Das Batterie-/MultiPlus-Profil wird beim nächsten Speichern angewendet.",
            cls="text-sm mb-4 text-green-700 font-semibold" if battery_profile_active else "text-sm mb-4 opacity-70",
        ),
        Div(
            H2("1. Standort", cls="text-lg font-semibold mb-2"),
            Div(
                _field("Breitengrad", "eos-setup-latitude", _display_value(state, "latitude", "47.4374107833627"), input_type="number", help_text="Dezimalgrad"),
                _field("Längengrad", "eos-setup-longitude", _display_value(state, "longitude", "15.003592944474134"), input_type="number", help_text="Dezimalgrad"),
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("2. Cerbo GX", cls="text-lg font-semibold mb-2"),
            _field(
                "IP-Adresse oder Hostname",
                "eos-setup-cerbo",
                _display_value(state, "cerbo_host", "192.168.178.150"),
                help_text="Modbus TCP: Port 502, Unit ID 100, möglichst Read-only.",
            ),
            P("System: 48 V · 3 × MultiPlus-II 48/10000/140-100 · PV vollständig DC-gekoppelt.", cls="text-sm opacity-80"),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("3. PV-Anlage", cls="text-lg font-semibold mb-2"),
            P(f"Anlagenprofil: {VICTRON_48V_PROFILE_NAME}", cls="font-semibold mb-2"),
            Div(
                _field("Dachneigung [°]", "eos-setup-tilt", _display_value(state, "tilt", "25"), input_type="number"),
                _field("Süd-Azimut [°]", "eos-setup-south-azimuth", _display_value(state, "south_azimuth", "180"), input_type="number", help_text="180° = Süd"),
                _field("Nord-Azimut [°]", "eos-setup-north-azimuth", _display_value(state, "north_azimuth", "0"), input_type="number", help_text="0° = Nord"),
                cls="grid grid-cols-1 md:grid-cols-3 gap-4",
            ),
            Div(
                P("Süd 1 · MPPT 250/100 · 3 × 5 LONGi LR5-54HTH-435M · 6,525 kWp · 5,8 kW"),
                P("Süd 2 · MPPT 250/100 · 3 × 5 LONGi LR5-54HTH-435M · 6,525 kWp · 5,8 kW"),
                P("Süd 3 · MPPT 250/60  · 1 × 4 LONGi LR5-54HTH-435M · 1,740 kWp · 3,44 kW"),
                P("Nord   · MPPT 250/100 · 5 × 5 Peimar OS280P · 7,000 kWp · 5,8 kW"),
                P("Gesamt: 59 Module · 21,790 kWp", cls="font-semibold mt-2"),
                cls="border rounded p-3 text-sm space-y-1",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("4. Batteriespeicher", cls="text-lg font-semibold mb-2"),
            P(f"Batterieprofil: {PYLONTECH_PROFILE_NAME}", cls="font-semibold mb-2"),
            Div(
                P("4 × Pylontech US5000 · 4,8 kWh = 19,20 kWh"),
                P("1 × Pylontech US3000C · 3,552 kWh"),
                P("7 × Pylontech US2000C · 2,4 kWh = 16,80 kWh"),
                P(f"Nominal: {PYLONTECH_CAPACITY_WH / 1000:.3f} kWh", cls="font-semibold mt-2"),
                P(f"Bei 95 % DoD rechnerisch nutzbar: {PYLONTECH_USABLE_95_DOD_WH / 1000:.3f} kWh"),
                P("3 × MultiPlus-II: 3 × 8 kW Dauerwirkleistung = 24 kW"),
                cls="border rounded p-3 text-sm space-y-1 mb-3",
            ),
            _field(
                "Mindest-SOC für spätere Optimierung [%]",
                "eos-setup-min-soc",
                _display_value(state, "min_soc", "10"),
                input_type="number",
                step="1",
                help_text="Standard 10 %. Die Cerbo-/Pylontech-BMS-Grenzen bleiben unabhängig davon maßgeblich.",
            ),
            P(
                "EOS bleibt vorerst im Modus PREDICTION und schreibt keine ESS-Sollwerte. Die Batterieparameter werden nur für die spätere Simulation vorbereitet.",
                cls="text-xs opacity-70",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Button(
            "Anlagenprofil dauerhaft speichern",
            id="eos-setup-save",
            type="button",
            onclick="eosRunQuickSetup()",
            cls="px-5 py-3 rounded bg-green-700 text-white font-semibold cursor-pointer",
        ),
        A(
            "Prognose öffnen",
            href="/eosdash/prediction",
            id="eos-setup-next",
            style="display:inline-block" if configured else "display:none",
            cls="ml-3 px-5 py-3 rounded border inline-block",
        ),
        P("", id="eos-setup-status", cls="mt-3 text-sm"),
        Script(_SETUP_SCRIPT),
        cls="border-2 border-green-700 rounded-xl p-5 mb-8",
    )


def About(**kwargs: Any) -> Div:
    return Div(QuickSetup(), Markdown(about_md), **kwargs)
