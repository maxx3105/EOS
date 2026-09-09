"""Regression checks for the Synology/Victron browser quick setup."""

import pytest

from akkudoktoreos.server.dash.about import _SETUP_SCRIPT
from akkudoktoreos.server.dash.quicksetup import (
    BASE_LOAD_ENERGY_KEY,
    EVCS_MAX_POWER_W,
    EVCS_UNIT_IDS,
    EV_TARGET_SOC_PERCENT,
    PYLONTECH_CAPACITY_WH,
    RENAULT_MEGANE_CAPACITY_WH,
    RENAULT_R5_CAPACITY_WH,
    build_electric_vehicles,
    build_multiplus_inverters,
    build_pylontech_battery,
    build_quick_setup_updates,
    build_victron_48v_planes,
    quick_setup_state,
)


def test_quick_setup_uses_actual_provider_config_paths():
    assert '["weather.provider", "OpenMeteo"]' in _SETUP_SCRIPT
    assert '["pvforecast.provider", "PVForecastPVLibVictron"]' in _SETUP_SCRIPT
    assert '["load.provider", "LoadVictronHistory"]' in _SETUP_SCRIPT
    assert "weather.weather_provider" not in _SETUP_SCRIPT
    assert "pvforecast.pvforecast_provider" not in _SETUP_SCRIPT


def test_quick_setup_enables_read_only_victron_prediction_stack():
    expected = (
        '["ems.mode", "PREDICTION"]',
        '["adapter.provider", ["Victron"]]',
        '["adapter.victron.port", 502]',
        '["adapter.victron.unit_id", 100]',
        '["adapter.victron.include_ac_coupled_pv", false]',
        '["adapter.victron.evcs_unit_ids", [40, 41]]',
        '["measurement.load_emr_keys", ["victron_base_load_emr"]]',
        '["prediction.hours", 48]',
        '["devices.max_batteries", 1]',
        '["devices.max_inverters", 3]',
        '["devices.max_electric_vehicles", 2]',
    )
    for fragment in expected:
        assert fragment in _SETUP_SCRIPT


def test_victron_48v_profile_matches_installed_pv_groups():
    planes = build_victron_48v_planes(tilt=25, south_azimuth=180, north_azimuth=0)

    assert len(planes) == 4
    assert sum(plane["peakpower"] for plane in planes) == pytest.approx(21.79)

    for plane in planes[:2]:
        assert plane["surface_tilt"] == 25
        assert plane["surface_azimuth"] == 180
        assert plane["module_model"] == "435.0"
        assert plane["modules_per_string"] == 5
        assert plane["strings_per_inverter"] == 3
        assert plane["inverter_model"] == "5800"
        assert plane["peakpower"] == pytest.approx(6.525)

    assert planes[2]["module_model"] == "435.0"
    assert planes[2]["modules_per_string"] == 4
    assert planes[2]["strings_per_inverter"] == 1
    assert planes[2]["inverter_model"] == "3440"
    assert planes[2]["peakpower"] == pytest.approx(1.74)

    assert planes[3]["surface_azimuth"] == 0
    assert planes[3]["module_model"] == "280.0"
    assert planes[3]["modules_per_string"] == 5
    assert planes[3]["strings_per_inverter"] == 5
    assert planes[3]["inverter_model"] == "5800"
    assert planes[3]["peakpower"] == pytest.approx(7.0)


def test_pylontech_profile_and_multiplus_limits():
    battery = build_pylontech_battery(10)
    assert battery["device_id"] == "battery1"
    assert battery["capacity_wh"] == PYLONTECH_CAPACITY_WH == 39552
    assert battery["min_soc_percentage"] == 10
    assert battery["max_charge_power_w"] == 24000
    assert battery["charging_efficiency"] == 1.0
    assert battery["discharging_efficiency"] == 1.0

    inverters = build_multiplus_inverters()
    assert len(inverters) == 3
    for inverter in inverters:
        assert inverter["battery_id"] == "battery1"
        assert inverter["max_power_w"] == 8000
        assert inverter["max_ac_charge_power_w"] == 7350
        assert inverter["ac_to_dc_efficiency"] == pytest.approx(0.95)
        assert inverter["dc_to_ac_efficiency"] == pytest.approx(0.95)


def test_dual_evcs_renault_profile_defaults_to_80_percent():
    evs = build_electric_vehicles()
    assert len(evs) == 2
    assert EV_TARGET_SOC_PERCENT == 80
    assert EVCS_UNIT_IDS == [40, 41]

    r5, megane = evs
    assert r5["device_id"] == "renault-r5"
    assert r5["capacity_wh"] == RENAULT_R5_CAPACITY_WH == 52000
    assert megane["device_id"] == "renault-megane-e-tech"
    assert megane["capacity_wh"] == RENAULT_MEGANE_CAPACITY_WH == 60000

    for ev in evs:
        assert ev["max_charge_power_w"] == EVCS_MAX_POWER_W == 11000
        assert ev["min_charge_power_w"] == 4100
        assert ev["charge_rates"][0] == 0.0
        assert ev["charge_rates"][-1] == 1.0
        assert ev["max_soc_percentage"] == 80


def test_ev_target_soc_is_configurable_without_departure_schedule():
    evs = build_electric_vehicles(75)
    assert all(ev["max_soc_percentage"] == 75 for ev in evs)


def test_quick_setup_requires_confirmed_file_save():
    assert 'saveText.includes("Can not save actual config")' in _SETUP_SCRIPT
    assert '!saveText.includes("Saved configuration to")' in _SETUP_SCRIPT
    assert "window.location.reload()" in _SETUP_SCRIPT


def test_quick_setup_builds_valid_rest_paths():
    payload = {
        "latitude": 47.4374,
        "longitude": 15.0036,
        "cerbo_host": "192.168.178.150",
        "tilt": 25,
        "south_azimuth": 180,
        "north_azimuth": 0,
        "min_soc": 10,
        "ev_target_soc": 80,
    }
    updates = dict(build_quick_setup_updates(payload))

    assert updates["general/latitude"] == 47.4374
    assert updates["weather/provider"] == "OpenMeteo"
    assert updates["pvforecast/provider"] == "PVForecastPVLibVictron"
    assert updates["load/provider"] == "LoadVictronHistory"
    assert updates["measurement/load_emr_keys"] == [BASE_LOAD_ENERGY_KEY]
    assert updates["adapter/victron/load_energy_key"] == "victron_load_emr"
    assert updates["adapter/victron/base_load_energy_key"] == BASE_LOAD_ENERGY_KEY
    assert updates["adapter/victron/evcs_unit_ids"] == [40, 41]
    assert updates["adapter/victron/evcs_energy_key_prefix"] == "victron_evcs"
    assert updates["adapter/victron/host"] == "192.168.178.150"
    assert updates["adapter/victron/include_ac_coupled_pv"] is False
    assert updates["ems/mode"] == "PREDICTION"
    assert len(updates["pvforecast/planes"]) == 4
    assert sum(plane["peakpower"] for plane in updates["pvforecast/planes"]) == pytest.approx(21.79)
    assert updates["devices/max_batteries"] == 1
    assert updates["devices/batteries"][0]["capacity_wh"] == 39552
    assert updates["devices/batteries"][0]["min_soc_percentage"] == 10
    assert len(updates["devices/inverters"]) == 3
    assert updates["devices/max_electric_vehicles"] == 2
    assert len(updates["devices/electric_vehicles"]) == 2
    assert updates["devices/electric_vehicles"][0]["capacity_wh"] == 52000
    assert updates["devices/electric_vehicles"][1]["capacity_wh"] == 60000
    assert updates["devices/electric_vehicles"][0]["max_soc_percentage"] == 80
    assert updates["devices/electric_vehicles"][1]["max_soc_percentage"] == 80


def test_quick_setup_reads_saved_profile_back():
    planes = build_victron_48v_planes(tilt=25, south_azimuth=180, north_azimuth=0)
    battery = build_pylontech_battery(10)
    inverters = build_multiplus_inverters()
    evs = build_electric_vehicles(80)
    config = {
        "general": {"latitude": 47.4374, "longitude": 15.0036},
        "adapter": {
            "victron": {
                "host": "192.168.178.150",
                "evcs_unit_ids": [40, 41],
                "base_load_energy_key": BASE_LOAD_ENERGY_KEY,
            }
        },
        "pvforecast": {"planes": planes},
        "load": {"provider": "LoadVictronHistory"},
        "measurement": {"load_emr_keys": [BASE_LOAD_ENERGY_KEY]},
        "devices": {
            "batteries": [battery],
            "inverters": inverters,
            "electric_vehicles": evs,
        },
    }

    state = quick_setup_state(config)
    assert state["configured"] is True
    assert state["cerbo_host"] == "192.168.178.150"
    assert state["tilt"] == 25
    assert state["south_azimuth"] == 180
    assert state["north_azimuth"] == 0
    assert state["plane_count"] == 4
    assert state["total_peakpower"] == pytest.approx(21.79)
    assert state["profile_active"] is True
    assert state["battery_capacity_wh"] == 39552
    assert state["min_soc"] == 10
    assert state["battery_profile_active"] is True
    assert state["ev_count"] == 2
    assert state["ev_target_soc"] == 80
    assert state["ev_profile_active"] is True
    assert state["evcs_unit_ids"] == [40, 41]
    assert state["evcs_measurement_active"] is True
    assert state["load_provider"] == "LoadVictronHistory"
    assert state["load_forecast_active"] is True
