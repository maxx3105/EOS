"""Regression checks for the Synology/Victron browser quick setup."""

import pytest

from akkudoktoreos.server.dash.about import _SETUP_SCRIPT
from akkudoktoreos.server.dash.quicksetup import (
    build_quick_setup_updates,
    build_victron_48v_planes,
    quick_setup_state,
)


def test_quick_setup_uses_actual_provider_config_paths():
    """Quick setup must address the real Pydantic config fields."""
    assert '["weather.provider", "OpenMeteo"]' in _SETUP_SCRIPT
    assert '["pvforecast.provider", "PVForecastPVLibVictron"]' in _SETUP_SCRIPT
    assert "weather.weather_provider" not in _SETUP_SCRIPT
    assert "pvforecast.pvforecast_provider" not in _SETUP_SCRIPT


def test_quick_setup_enables_read_only_victron_prediction_stack():
    """The first-run wizard should configure the intended safe prediction stack."""
    expected = (
        '["ems.mode", "PREDICTION"]',
        '["adapter.provider", ["Victron"]]',
        '["adapter.victron.port", 502]',
        '["adapter.victron.unit_id", 100]',
        '["adapter.victron.include_ac_coupled_pv", false]',
        '["prediction.hours", 48]',
    )
    for fragment in expected:
        assert fragment in _SETUP_SCRIPT


def test_victron_48v_profile_matches_installed_pv_groups():
    planes = build_victron_48v_planes(tilt=25, south_azimuth=180, north_azimuth=0)

    assert len(planes) == 4
    assert sum(plane["peakpower"] for plane in planes) == pytest.approx(21.79)

    # Two south 250/100 controllers: 3 x 5 LONGi 435 W each.
    for plane in planes[:2]:
        assert plane["surface_tilt"] == 25
        assert plane["surface_azimuth"] == 180
        assert plane["module_model"] == "435.0"
        assert plane["modules_per_string"] == 5
        assert plane["strings_per_inverter"] == 3
        assert plane["inverter_model"] == "5800"
        assert plane["peakpower"] == pytest.approx(6.525)

    # South 250/60: 1 x 4 LONGi 435 W.
    assert planes[2]["module_model"] == "435.0"
    assert planes[2]["modules_per_string"] == 4
    assert planes[2]["strings_per_inverter"] == 1
    assert planes[2]["inverter_model"] == "3440"
    assert planes[2]["peakpower"] == pytest.approx(1.74)

    # North 250/100: 5 x 5 Peimar 280 W.
    assert planes[3]["surface_azimuth"] == 0
    assert planes[3]["module_model"] == "280.0"
    assert planes[3]["modules_per_string"] == 5
    assert planes[3]["strings_per_inverter"] == 5
    assert planes[3]["inverter_model"] == "5800"
    assert planes[3]["peakpower"] == pytest.approx(7.0)


def test_quick_setup_requires_confirmed_file_save():
    """HTTP 200 from the HTML admin page alone must not count as persisted."""
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
    }
    updates = dict(build_quick_setup_updates(payload))

    assert updates["general/latitude"] == 47.4374
    assert updates["weather/provider"] == "OpenMeteo"
    assert updates["pvforecast/provider"] == "PVForecastPVLibVictron"
    assert updates["adapter/victron/host"] == "192.168.178.150"
    assert updates["adapter/victron/include_ac_coupled_pv"] is False
    assert updates["ems/mode"] == "PREDICTION"
    assert len(updates["pvforecast/planes"]) == 4
    assert sum(plane["peakpower"] for plane in updates["pvforecast/planes"]) == pytest.approx(
        21.79
    )


def test_quick_setup_reads_saved_profile_back():
    planes = build_victron_48v_planes(tilt=25, south_azimuth=180, north_azimuth=0)
    config = {
        "general": {"latitude": 47.4374, "longitude": 15.0036},
        "adapter": {"victron": {"host": "192.168.178.150"}},
        "pvforecast": {"planes": planes},
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
