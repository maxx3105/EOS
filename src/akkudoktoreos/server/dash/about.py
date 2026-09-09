from typing import Any

import requests
from fasthtml.common import A, Button, Div, H2, Input, Label, P, Script

from akkudoktoreos.config.configabc import runtime_environment
from akkudoktoreos.core.coreabc import get_config
from akkudoktoreos.core.version import __version__
from akkudoktoreos.server.dash.markdown import Markdown
from akkudoktoreos.server.dash.quicksetup import (
    BASE_LOAD_ENERGY_KEY,
    EVCS_MAX_CURRENT_A,
    EVCS_MAX_POWER_W,
    EVCS_PROFILE_NAME,
    EVCS_UNIT_IDS,
    EV_TARGET_SOC_PERCENT,
    HOYMILES_AC_LIMIT_W,
    HOYMILES_AZIMUTH_DEG,
    HOYMILES_EFFICIENCY,
    HOYMILES_PEAKPOWER_KW,
    HOYMILES_PROFILE_NAME,
    HOYMILES_TILT_DEG,
    PYLONTECH_CAPACITY_WH,
    PYLONTECH_PROFILE_NAME,
    PYLONTECH_USABLE_95_DOD_WH,
    RENAULT_MEGANE_CAPACITY_WH,
    RENAULT_R5_CAPACITY_WH,
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

function eosHoymilesPlane(eastTilt, eastAzimuth) {
    return {
        surface_tilt: eastTilt,
        surface_azimuth: eastAzimuth,
        peakpower: 0.870,
        mountingplace: "building",
        loss: 0.0,
        trackingtype: 0,
        albedo: 0.2,
        module_model: "435.0",
        inverter_model: "Hoymiles_HMS_800W_2T_AC_OUT",
        modules_per_string: 1,
        strings_per_inverter: 2
    };
}

function eosBuildVictron48VPlanes(tilt, southAzimuth, northAzimuth, eastTilt, eastAzimuth) {
    return [
        eosVictronPlane(tilt, southAzimuth, 435, 5, 3, 5800),
        eosVictronPlane(tilt, southAzimuth, 435, 5, 3, 5800),
        eosVictronPlane(tilt, southAzimuth, 435, 4, 1, 3440),
        eosVictronPlane(tilt, northAzimuth, 280, 5, 5, 5800),
        eosHoymilesPlane(eastTilt, eastAzimuth)
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

function eosBuildElectricVehicles(targetSoc) {
    const chargeRates = [0.0, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0];
    const vehicle = (deviceId, capacityWh) => ({
        device_id: deviceId,
        capacity_wh: capacityWh,
        charging_efficiency: 1.0,
        discharging_efficiency: 1.0,
        max_charge_power_w: 11000,
        min_charge_power_w: 4100,
        charge_rates: chargeRates,
        min_soc_percentage: 0,
        max_soc_percentage: targetSoc
    });
    return [
        vehicle("renault-r5", 52000),
        vehicle("renault-megane-e-tech", 60000)
    ];
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
        const eastTilt = eosSetupNumber("eos-setup-east-tilt", "Hoymiles-Modulneigung");
        const eastAzimuth = eosSetupNumber("eos-setup-east-azimuth", "Hoymiles-Ost-Azimut");
        if (tilt < 0 || tilt > 90) throw new Error("Modulneigung muss zwischen 0 und 90° liegen.");
        if (eastTilt < 0 || eastTilt > 90) throw new Error("Hoymiles-Modulneigung muss zwischen 0 und 90° liegen.");
        if (southAzimuth < 0 || southAzimuth > 360) throw new Error("Süd-Azimut muss zwischen 0 und 360° liegen.");
        if (northAzimuth < 0 || northAzimuth > 360) throw new Error("Nord-Azimut muss zwischen 0 und 360° liegen.");
        if (eastAzimuth < 0 || eastAzimuth > 360) throw new Error("Hoymiles-Ost-Azimut muss zwischen 0 und 360° liegen.");

        const minSoc = eosSetupNumber("eos-setup-min-soc", "Mindest-SOC / Inselreserve");
        if (!Number.isInteger(minSoc) || minSoc < 0 || minSoc > 100) {
            throw new Error("Inselreserve muss eine ganze Zahl zwischen 0 und 100 % sein.");
        }

        const evTargetSoc = eosSetupNumber("eos-setup-ev-target-soc", "EV-Ziel-SOC");
        if (!Number.isInteger(evTargetSoc) || evTargetSoc < 0 || evTargetSoc > 100) {
            throw new Error("EV-Ziel-SOC muss eine ganze Zahl zwischen 0 und 100 % sein.");
        }

        const planes = eosBuildVictron48VPlanes(tilt, southAzimuth, northAzimuth, eastTilt, eastAzimuth);
        const battery = eosBuildPylontechBattery(minSoc);
        const inverters = eosBuildMultiplusInverters();
        const electricVehicles = eosBuildElectricVehicles(evTargetSoc);

        const updates = [
            ["general.latitude", latitude],
            ["general.longitude", longitude],
            ["ems.mode", "PREDICTION"],
            ["ems.interval", 300.0],
            ["prediction.hours", 48],
            ["weather.provider", "OpenMeteo"],
            ["pvforecast.provider", "PVForecastPVLibVictron"],
            ["pvforecast.planes", planes],
            ["load.provider", "LoadVictronHistory"],
            ["measurement.load_emr_keys", ["victron_base_load_emr"]],
            ["adapter.provider", ["Victron"]],
            ["adapter.victron.host", cerboHost],
            ["adapter.victron.port", 502],
            ["adapter.victron.unit_id", 100],
            ["adapter.victron.timeout_sec", 3.0],
            ["adapter.victron.include_ac_coupled_pv", true],
            ["adapter.victron.pv_energy_key", "victron_pv_emr"],
            ["adapter.victron.load_energy_key", "victron_load_emr"],
            ["adapter.victron.base_load_energy_key", "victron_base_load_emr"],
            ["adapter.victron.evcs_unit_ids", [40, 41]],
            ["adapter.victron.evcs_energy_key_prefix", "victron_evcs"],
            ["adapter.victron.max_integration_gap_minutes", 15.0],
            ["devices.max_batteries", 1],
            ["devices.batteries", [battery]],
            ["devices.max_inverters", 3],
            ["devices.inverters", inverters],
            ["devices.max_electric_vehicles", 2],
            ["devices.electric_vehicles", electricVehicles]
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

        status.textContent = "✓ Dauerhaft gespeichert: 4× SmartSolar DC + Hoymiles AC-out + Batterie/Inselreserve + EVCS-Grundlasttrennung + EV-Überschussziel. Die Seite wird neu geladen …";
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
    state = _current_quick_setup_state()
    configured = bool(state.get("configured"))
    profile_active = bool(state.get("profile_active"))
    hoymiles_active = bool(state.get("hoymiles_active"))
    battery_profile_active = bool(state.get("battery_profile_active"))
    ev_profile_active = bool(state.get("ev_profile_active"))
    evcs_measurement_active = bool(state.get("evcs_measurement_active"))
    ev_target_soc = _display_value(state, "ev_target_soc", str(EV_TARGET_SOC_PERCENT))

    return Div(
        H2("Schnelleinrichtung: Synology + Victron Cerbo GX", cls="text-2xl font-bold mb-2"),
        P("PV, Batterie, MultiPlus und EVs werden als Anlagenprofil verwaltet.", cls="mb-2"),
        P("✓ Gespeicherte Cerbo-Konfiguration erkannt." if configured else "Noch keine Cerbo-Konfiguration gespeichert.", cls="text-sm mb-1 text-green-700 font-semibold" if configured else "text-sm mb-1 opacity-70"),
        P("✓ PV-Profil aktiv: 4× SmartSolar DC + Hoymiles AC-out (22,66 kWp)." if profile_active else "Das erweiterte PV-Profil mit Hoymiles AC-out wird beim nächsten Speichern angewendet.", cls="text-sm mb-1 text-green-700 font-semibold" if profile_active else "text-sm mb-1 opacity-70"),
        P("✓ Hoymiles AC-out wird in der Cerbo-PV-Istleistung berücksichtigt." if hoymiles_active else "Hoymiles AC-out wird beim nächsten Speichern in die PV-Istleistung aufgenommen.", cls="text-sm mb-1 text-green-700 font-semibold" if hoymiles_active else "text-sm mb-1 opacity-70"),
        P("✓ Pylontech-/MultiPlus-Profil aktiv (39,552 kWh)." if battery_profile_active else "Das Batterie-/MultiPlus-Profil wird beim nächsten Speichern angewendet.", cls="text-sm mb-1 text-green-700 font-semibold" if battery_profile_active else "text-sm mb-1 opacity-70"),
        P(f"✓ EV-Profil aktiv: PV-Überschuss bis {ev_target_soc} %, ohne feste Abfahrtszeit." if ev_profile_active else "Das EV-Profil wird beim nächsten Speichern angewendet.", cls="text-sm mb-1 text-green-700 font-semibold" if ev_profile_active else "text-sm mb-1 opacity-70"),
        P(
            f"✓ EVCS-Messung aktiv: Modbus Unit IDs {EVCS_UNIT_IDS[0]} + {EVCS_UNIT_IDS[1]}, Grundlast ohne EV-Laden."
            if evcs_measurement_active
            else "Die EVCS-Grundlasttrennung wird beim nächsten Speichern aktiviert.",
            cls="text-sm mb-4 text-green-700 font-semibold" if evcs_measurement_active else "text-sm mb-4 opacity-70",
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
            _field("IP-Adresse oder Hostname", "eos-setup-cerbo", _display_value(state, "cerbo_host", "192.168.178.150"), help_text="Modbus TCP: Port 502, System Unit ID 100, weiterhin read-only."),
            P("System: 48 V · 3 × MultiPlus-II 48/10000/140-100 · 4× SmartSolar DC-gekoppelt · Hoymiles HMS-800W-2T AC-gekoppelt auf AC-out.", cls="text-sm opacity-80"),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("3. PV-Anlage", cls="text-lg font-semibold mb-2"),
            P(f"Anlagenprofil: {VICTRON_48V_PROFILE_NAME}", cls="font-semibold mb-2"),
            Div(
                _field("Dachneigung Süd/Nord [°]", "eos-setup-tilt", _display_value(state, "tilt", "25"), input_type="number"),
                _field("Süd-Azimut [°]", "eos-setup-south-azimuth", _display_value(state, "south_azimuth", "180"), input_type="number", help_text="180° = Süd"),
                _field("Nord-Azimut [°]", "eos-setup-north-azimuth", _display_value(state, "north_azimuth", "0"), input_type="number", help_text="0° = Nord"),
                cls="grid grid-cols-1 md:grid-cols-3 gap-4",
            ),
            Div(
                _field("Hoymiles-Neigung [°]", "eos-setup-east-tilt", _display_value(state, "east_tilt", str(HOYMILES_TILT_DEG)), input_type="number"),
                _field("Hoymiles-Ost-Azimut [°]", "eos-setup-east-azimuth", _display_value(state, "east_azimuth", str(HOYMILES_AZIMUTH_DEG)), input_type="number", help_text="90° = Ost"),
                cls="grid grid-cols-1 md:grid-cols-2 gap-4",
            ),
            Div(
                P("Süd 1 · MPPT 250/100 · 3 × 5 LONGi 435 W · 6,525 kWp · 5,8 kW"),
                P("Süd 2 · MPPT 250/100 · 3 × 5 LONGi 435 W · 6,525 kWp · 5,8 kW"),
                P("Süd 3 · MPPT 250/60 · 1 × 4 LONGi 435 W · 1,740 kWp · 3,44 kW"),
                P("Nord · MPPT 250/100 · 5 × 5 Peimar 280 W · 7,000 kWp · 5,8 kW"),
                P(f"Ost · {HOYMILES_PROFILE_NAME} · {HOYMILES_PEAKPOWER_KW:.3f} kWp · {HOYMILES_AC_LIMIT_W / 1000:.1f} kW AC · η≈{HOYMILES_EFFICIENCY * 100:.1f} %"),
                P("Gesamt: 61 Module · 22,660 kWp DC-Nennleistung", cls="font-semibold mt-2"),
                cls="border rounded p-3 text-sm space-y-1",
            ),
            P("Der Hoymiles hängt auf AC-out. Sein AC-Ertrag wird zusätzlich zur DC-PV-Leistung der SmartSolar-Regler aus dem Cerbo-Systemwert erfasst; EOS bleibt read-only.", cls="text-xs opacity-70 mt-2"),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("4. Batteriespeicher & Inselreserve", cls="text-lg font-semibold mb-2"),
            P(f"Batterieprofil: {PYLONTECH_PROFILE_NAME}", cls="font-semibold mb-2"),
            Div(
                P("4 × US5000 · 1 × US3000C · 7 × US2000C"),
                P(f"Nominal: {PYLONTECH_CAPACITY_WH / 1000:.3f} kWh"),
                P(f"Bei 95 % DoD rechnerisch nutzbar: {PYLONTECH_USABLE_95_DOD_WH / 1000:.3f} kWh"),
                P("3 × MultiPlus-II: zusammen 24 kW Dauerwirkleistung"),
                cls="border rounded p-3 text-sm space-y-1 mb-3",
            ),
            _field(
                "Mindest-SOC / Inselreserve Hausbatterie [%]",
                "eos-setup-min-soc",
                _display_value(state, "min_soc", "10"),
                input_type="number",
                step="1",
                help_text="Bleibt frei einstellbar. EOS ändert keine Cerbo-/BMS-Schutzgrenzen und steuert das ESS noch nicht aktiv.",
            ),
            cls="border rounded-lg p-4 mb-4",
        ),
        Div(
            H2("5. Elektrofahrzeuge & PV-Überschussladen", cls="text-lg font-semibold mb-2"),
            P(f"Ladeprofil: {EVCS_PROFILE_NAME}", cls="font-semibold mb-2"),
            Div(
                P(f"EVCS A · Modbus Unit ID {EVCS_UNIT_IDS[0]} · 3-phasig · max. {EVCS_MAX_CURRENT_A} A · ca. {EVCS_MAX_POWER_W / 1000:.1f} kW"),
                P(f"EVCS B · Modbus Unit ID {EVCS_UNIT_IDS[1]} · 3-phasig · max. {EVCS_MAX_CURRENT_A} A · ca. {EVCS_MAX_POWER_W / 1000:.1f} kW"),
                P(f"Grundlast-Lernzähler: {BASE_LOAD_ENERGY_KEY} (Gesamtlast minus beide EVCS)"),
                P(f"Renault R5 · vorhanden · {RENAULT_R5_CAPACITY_WH / 1000:.0f} kWh"),
                P(f"Renault Megane E-Tech · vorgesehen · {RENAULT_MEGANE_CAPACITY_WH / 1000:.0f} kWh"),
                P("Keine feste Abfahrtszeit: geeignet für wechselnden 4-Schicht-Betrieb.", cls="font-semibold mt-2"),
                cls="border rounded p-3 text-sm space-y-1 mb-3",
            ),
            _field(
                "PV-Überschuss-Ladeziel [%]",
                "eos-setup-ev-target-soc",
                ev_target_soc,
                input_type="number",
                step="1",
                help_text="Standard 80 %. Später soll nur bei verfügbarem Überschuss bis zu dieser Grenze geladen werden; keine Deadline wird erzwungen.",
            ),
            P("Wichtig: Die Victron EVCS liefert Ladeleistung/-energie, aber nicht automatisch den echten Fahrzeug-SOC. Für eine spätere automatische Abschaltung exakt bei 80 % braucht EOS zusätzlich eine verlässliche Fahrzeug-SOC-Quelle oder eine manuelle SOC-Eingabe.", cls="text-xs opacity-70 mt-2"),
            P("EOS bleibt vorerst PREDICTION/read-only: keine EVCS-Steuerung und kein V2G.", cls="text-xs opacity-70 mt-1"),
            cls="border rounded-lg p-4 mb-4",
        ),
        Button("Anlagenprofil dauerhaft speichern", id="eos-setup-save", type="button", onclick="eosRunQuickSetup()", cls="px-5 py-3 rounded bg-green-700 text-white font-semibold cursor-pointer"),
        A("Prognose öffnen", href="/eosdash/prediction", id="eos-setup-next", style="display:inline-block" if configured else "display:none", cls="ml-3 px-5 py-3 rounded border inline-block"),
        P("", id="eos-setup-status", cls="mt-3 text-sm"),
        Script(_SETUP_SCRIPT),
        cls="border-2 border-green-700 rounded-xl p-5 mb-8",
    )


def About(**kwargs: Any) -> Div:
    return Div(QuickSetup(), Markdown(about_md), **kwargs)