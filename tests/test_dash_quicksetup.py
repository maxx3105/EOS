"""Regression checks for the Synology/Victron browser quick setup."""

from akkudoktoreos.server.dash.about import _SETUP_SCRIPT
from akkudoktoreos.server.dash.quicksetup import build_quick_setup_updates, quick_setup_state


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
        '["adapter.victron.include_ac_coupled_pv", true]',
        '["prediction.hours", 48]',
    )
    for fragment in expected:
        assert fragment in _SETUP_SCRIPT


def test_quick_setup_configures_a_pvlib_plane():
    """A simple single-plane setup must include all PVLib mandatory fields."""
    for field in (
        "surface_tilt",
        "surface_azimuth",
        "module_model",
        "inverter_model",
        "modules_per_string",
        "strings_per_inverter",
    ):
        assert field in _SETUP_SCRIPT


def test_quick_setup_requires_confirmed_file_save():
    """HTTP 200 from the HTML admin page alone must not count as persisted."""
    assert 'saveText.includes("Can not save actual config")' in _SETUP_SCRIPT
    assert '!saveText.includes("Saved configuration to")' in _SETUP_SCRIPT
    assert "window.location.reload()" in _SETUP_SCRIPT


def test_quick_setup_builds_valid_rest_paths():
    payload = {
        "latitude": 48.1,
        "longitude": 16.2,
        "cerbo_host": "192.168.178.20",
        "tilt": 30,
        "azimuth": 180,
        "module_power": 425,
        "modules_per_string": 12,
        "strings_per_inverter": 2,
        "inverter_power": 10000,
    }
    updates = dict(build_quick_setup_updates(payload))

    assert updates["general/latitude"] == 48.1
    assert updates["weather/provider"] == "OpenMeteo"
    assert updates["pvforecast/provider"] == "PVForecastPVLibVictron"
    assert updates["adapter/victron/host"] == "192.168.178.20"
    assert updates["ems/mode"] == "PREDICTION"
    assert updates["pvforecast/planes"][0]["module_model"] == "425.0"


def test_quick_setup_reads_saved_values_back():
    config = {
        "general": {"latitude": 48.1, "longitude": 16.2},
        "adapter": {"victron": {"host": "192.168.178.20"}},
        "pvforecast": {
            "planes": [
                {
                    "surface_tilt": 30.0,
                    "surface_azimuth": 180.0,
                    "module_model": "425",
                    "inverter_model": "10000",
                    "modules_per_string": 12,
                    "strings_per_inverter": 2,
                }
            ]
        },
    }

    state = quick_setup_state(config)
    assert state["configured"] is True
    assert state["cerbo_host"] == "192.168.178.20"
    assert state["module_power"] == 425.0
    assert state["inverter_power"] == 10000.0
