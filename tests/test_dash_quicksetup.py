"""Regression checks for the Synology/Victron browser quick setup."""

from akkudoktoreos.server.dash.about import _SETUP_SCRIPT


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
