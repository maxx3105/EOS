from typing import Any

import requests
from fasthtml.common import A, Button, Div, H2, Input, Label, P, Script

from akkudoktoreos.config.configabc import runtime_environment
from akkudoktoreos.core.coreabc import get_config
from akkudoktoreos.core.version import __version__
from akkudoktoreos.server.dash.markdown import Markdown
from akkudoktoreos.server.dash.quicksetup import quick_setup_state

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

function eosSetupInteger(id, label) {
    const value = eosSetupNumber(id, label);
    if (!Number.isInteger(value) || value < 1) {
        throw new Error(label + " muss eine positive ganze Zahl sein.");
    }
    return value;
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
        const azimuth = eosSetupNumber("eos-setup-azimuth", "Azimut");
        if (tilt < 0 || tilt > 90) throw new Error("Modulneigung muss zwischen 0 und 90° liegen.");
        if (azimuth < 0 || azimuth > 360) throw new Error("Azimut muss zwischen 0 und 360° liegen.");

        const modulePower = eosSetupNumber("eos-setup-module-power", "Modulleistung");
        const modulesPerString = eosSetupInteger("eos-setup-modules-string", "Module pro String");
        const stringsPerInverter = eosSetupInteger("eos-setup-strings", "Strings pro Wechselrichter");
        const inverterPower = eosSetupNumber("eos-setup-inverter-power", "Wechselrichterleistung");

        if (modulePower <= 0 || inverterPower <= 0) throw new Error("Leistungswerte müssen größer als 0 sein.");

        const peakPowerKw = modulePower * modulesPerString * stringsPerInverter / 1000.0;
        const plane = {
            surface_tilt: tilt,
            surface_azimuth: azimuth,
            peakpower: peakPowerKw,
            mountingplace: "building",
            loss: 0.0,
            trackingtype: 0,
            albedo: 0.2,
            module_model: String(modulePower),
            inverter_model: String(inverterPower),
            modules_per_string: modulesPerString,
            strings_per_inverter: stringsPerInverter
        };

        const updates = [
            ["general.latitude", latitude],
            ["general.longitude", longitude],
            ["ems.mode", "PREDICTION"],
            ["ems.interval", 300.0],
            ["prediction.hours", 48],
            ["weather.provider", "OpenMeteo"],
            ["pvforecast.provider", "PVForecastPVLibVictron"],
            ["pvforecast.planes", [plane]],
            ["adapter.provider", ["Victron"]],
            ["adapter.victron.host", cerboHost],
            ["adapter.victron.port", 502],
            ["adapter.victron.unit_id", 100],
            ["adapter.victron.timeout_sec", 3.0],
            ["adapter.victron.include_ac_coupled_pv", true],
            ["adapter.victron.pv_energy_key", "victron_pv_emr"],
            ["adapter.victron.max_integration_gap_minutes", 15.0]
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

        status.textContent = "✓ Dauerhaft gespeichert. Die Seite wird neu geladen und liest die Werte aus EOS zurück …";
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

    return Div(
        H2("Schnelleinrichtung: Synology + Victron Cerbo GX", cls="text-2xl font-bold mb-2"),
        P(
            "Die Felder zeigen die aktuell in EOS gespeicherten Werte. Nach dem Speichern wird die Seite automatisch neu geladen, damit du sofort siehst, was tatsächlich dauerhaft übernommen wurde.",
            cls="mb-2",
        ),
        P(
            "✓ Gespeicherte Cerbo-Konfiguration erkannt." if configured else "Noch keine Cerbo-Konfiguration gespeichert.",
            cls="text-sm mb-4 text-green-700 font-semibold" if configured else "text-sm mb-4 opacity-70",
        ),
        Div(
            H2("1. Standort", cls="text-lg font-semibold mb-2"),
            Div(
                _field("Breitengrad", "eos-setup-latitude", _display_value(state, "latitude", "48.2082"), input_type="number", help_text="Dezimalgrad, z. B. 48.2082"),
                _field("Längengrad", "eos-setup-longitude", _display_value(state, "longitude", "16.3738"), input_type="number", help_text="Dezimalgrad, z. B. 16.3738"),
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("2. Cerbo GX", cls="text-lg font-semibold mb-2"),
            _field(
                "IP-Adresse oder Hostname",
                "eos-setup-cerbo",
                _display_value(state, "cerbo_host", "192.168.1.50"),
                help_text="Am Cerbo Modbus TCP aktivieren; Standard: Port 502, Unit ID 100, möglichst Read-only.",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("3. PV-Anlage – erste Dachfläche", cls="text-lg font-semibold mb-2"),
            P(
                "Für Ost/West oder mehrere Wechselrichter zunächst die wichtigste Fläche eintragen; weitere Flächen können danach unter Config ergänzt werden.",
                cls="text-sm mb-3",
            ),
            Div(
                _field("Modulneigung [°]", "eos-setup-tilt", _display_value(state, "tilt", "30"), input_type="number"),
                _field("Azimut [°]", "eos-setup-azimuth", _display_value(state, "azimuth", "180"), input_type="number", help_text="0=Norden, 90=Osten, 180=Süden, 270=Westen"),
                _field("Modulleistung [Wp]", "eos-setup-module-power", _display_value(state, "module_power", "400"), input_type="number", help_text="EOS wählt ein passendes CEC-Modell nach Leistung."),
                _field("Module pro String", "eos-setup-modules-string", _display_value(state, "modules_per_string", "10"), input_type="number", step="1"),
                _field("Strings pro Wechselrichter", "eos-setup-strings", _display_value(state, "strings_per_inverter", "2"), input_type="number", step="1"),
                _field("Wechselrichterleistung [W]", "eos-setup-inverter-power", _display_value(state, "inverter_power", "8000"), input_type="number", help_text="EOS wählt ein passendes CEC-Wechselrichtermodell nach Leistung."),
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Button(
            "Einrichtung dauerhaft speichern",
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
