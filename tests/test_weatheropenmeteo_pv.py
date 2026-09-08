"""PV-specific regression tests for the Open-Meteo weather provider."""

from akkudoktoreos.prediction.weatheropenmeteo import (
    OPENMETEO_FORECAST_VARIABLES,
    WeatherDataOpenMeteoMapping,
)


def test_openmeteo_pv_request_uses_true_dni() -> None:
    """PV requests must use normal-plane DNI, not horizontal direct radiation."""
    assert "shortwave_radiation" in OPENMETEO_FORECAST_VARIABLES
    assert "diffuse_radiation" in OPENMETEO_FORECAST_VARIABLES
    assert "direct_normal_irradiance" in OPENMETEO_FORECAST_VARIABLES
    assert "direct_radiation" not in OPENMETEO_FORECAST_VARIABLES


def test_openmeteo_true_dni_maps_to_weather_dni() -> None:
    """The Open-Meteo DNI field must map to EOS' Direct Normal Irradiance value."""
    mapping = {key: description for key, description, _ in WeatherDataOpenMeteoMapping}

    assert mapping["direct_normal_irradiance"] == "Direct Normal Irradiance (W/m2)"
