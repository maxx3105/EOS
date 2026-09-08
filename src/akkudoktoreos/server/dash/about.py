from typing import Any

from fasthtml.common import A, Button, Div, H2, Input, Label, P, Script

from akkudoktoreos.config.configabc import runtime_environment
from akkudoktoreos.core.version import __version__
from akkudoktoreos.server.dash.markdown import Markdown

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
    if (!response.ok) {
        const text = await response.text();
        throw new Error(key + ": " + response.status + " " + text.slice(0, 500));
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

        const saveResponse = await fetch("/eosdash/admin", {
            method: "POST",
            headers: {"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            body: new URLSearchParams({category: "configuration", action: "save_to_file"})
        });
        if (!saveResponse.ok) {
            throw new Error("Die Einstellungen wurden gesetzt, konnten aber nicht sofort in die Konfigurationsdatei geschrieben werden.");
        }

        status.textContent = "✓ Einrichtung gespeichert. EOS läuft jetzt im Prediction-Modus mit Open-Meteo, PVLib und Cerbo-GX-Istwertkorrektur.";
        status.className = "mt-3 text-sm text-green-700 font-semibold";
        document.getElementById("eos-setup-next").style.display = "inline-block";
    } catch (error) {
        status.textContent = "Fehler: " + error.message;
        status.className = "mt-3 text-sm text-red-700 font-semibold";
    } finally {
        button.disabled = false;
    }
}
"""


def _field(label: str, input_id: str, value: str, *, input_type: str = "text", help_text: str = "") -> Div:
    return Div(
        Label(label, fr=input_id, cls="font-semibold block mb-1"),
        Input(
            id=input_id,
            value=value,
            type=input_type,
            cls="w-full border rounded px-3 py-2",
        ),
        P(help_text, cls="text-xs opacity-70 mt-1") if help_text else None,
        cls="mb-3",
    )


def QuickSetup() -> Div:
    """Simple first-run setup for the Synology + Victron use case."""
    return Div(
        H2("Schnelleinrichtung: Synology + Victron Cerbo GX", cls="text-2xl font-bold mb-2"),
        P(
            "Für eine typische Anlage genügt diese Seite. Die Werte werden dauerhaft in EOS gespeichert; "
            "eine synology.env-Datei ist dafür nicht mehr nötig.",
            cls="mb-4",
        ),
        Div(
            H2("1. Standort", cls="text-lg font-semibold mb-2"),
            Div(
                _field("Breitengrad", "eos-setup-latitude", "48.2082", input_type="number", help_text="Dezimalgrad, z. B. 48.2082"),
                _field("Längengrad", "eos-setup-longitude", "16.3738", input_type="number", help_text="Dezimalgrad, z. B. 16.3738"),
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("2. Cerbo GX", cls="text-lg font-semibold mb-2"),
            _field(
                "IP-Adresse oder Hostname",
                "eos-setup-cerbo",
                "192.168.1.50",
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
                _field("Modulneigung [°]", "eos-setup-tilt", "30", input_type="number"),
                _field("Azimut [°]", "eos-setup-azimuth", "180", input_type="number", help_text="0=Norden, 90=Osten, 180=Süden, 270=Westen"),
                _field("Modulleistung [Wp]", "eos-setup-module-power", "400", input_type="number", help_text="EOS wählt ein passendes CEC-Modell nach Leistung."),
                _field("Module pro String", "eos-setup-modules-string", "10", input_type="number"),
                _field("Strings pro Wechselrichter", "eos-setup-strings", "2", input_type="number"),
                _field("Wechselrichterleistung [W]", "eos-setup-inverter-power", "8000", input_type="number", help_text="EOS wählt ein passendes CEC-Wechselrichtermodell nach Leistung."),
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Button(
            "Einrichtung speichern",
            id="eos-setup-save",
            type="button",
            onclick="eosRunQuickSetup()",
            cls="px-5 py-3 rounded bg-green-700 text-white font-semibold cursor-pointer",
        ),
        A(
            "Prognose öffnen",
            href="/eosdash/prediction",
            id="eos-setup-next",
            style="display:none",
            cls="ml-3 px-5 py-3 rounded border inline-block",
        ),
        P("", id="eos-setup-status", cls="mt-3 text-sm"),
        Script(_SETUP_SCRIPT),
        cls="border-2 border-green-700 rounded-xl p-5 mb-8",
    )


def About(**kwargs: Any) -> Div:
    return Div(QuickSetup(), Markdown(about_md), **kwargs)
