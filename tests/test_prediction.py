import pytest
from pydantic import ValidationError

from akkudoktoreos.core.coreabc import get_prediction
from akkudoktoreos.prediction.elecfeefixed import ElecFeeFixed
from akkudoktoreos.prediction.elecfeeimport import ElecFeeImport
from akkudoktoreos.prediction.elecpriceakkudoktor import ElecPriceAkkudoktor
from akkudoktoreos.prediction.elecpriceenergycharts import ElecPriceEnergyCharts
from akkudoktoreos.prediction.elecpricefixed import ElecPriceFixed
from akkudoktoreos.prediction.elecpriceimport import ElecPriceImport
from akkudoktoreos.prediction.elecpricesmard import ElecPriceSMARD
from akkudoktoreos.prediction.elecpricetibber import ElecPriceTibber
from akkudoktoreos.prediction.feedintariffakkudoktor import FeedInTariffAkkudoktor
from akkudoktoreos.prediction.feedintariffdvhubonline import FeedInTariffDvhubOnline
from akkudoktoreos.prediction.feedintariffenergycharts import FeedInTariffEnergyCharts
from akkudoktoreos.prediction.feedintarifffixed import FeedInTariffFixed
from akkudoktoreos.prediction.feedintariffimport import FeedInTariffImport
from akkudoktoreos.prediction.feedintariffsmard import FeedInTariffSMARD
from akkudoktoreos.prediction.feedintarifftibber import FeedInTariffTibber
from akkudoktoreos.prediction.loadakkudoktor import (
    LoadAkkudoktor,
    LoadAkkudoktorAdjusted,
)
from akkudoktoreos.prediction.loadimport import LoadImport
from akkudoktoreos.prediction.loadvictronhistory import LoadVictronHistory
from akkudoktoreos.prediction.loadvrm import LoadVrm
from akkudoktoreos.prediction.prediction import (
    Prediction,
    PredictionCommonSettings,
)
from akkudoktoreos.prediction.pvforecastakkudoktor import PVForecastAkkudoktor
from akkudoktoreos.prediction.pvforecastforecastsolar import PVForecastForecastSolar
from akkudoktoreos.prediction.pvforecasthomeassistant import PVForecastHomeAssistant
from akkudoktoreos.prediction.pvforecastimport import PVForecastImport
from akkudoktoreos.prediction.pvforecastpvlib import PVForecastPVLib
from akkudoktoreos.prediction.pvforecastpvlibvictron import PVForecastPVLibVictron
from akkudoktoreos.prediction.pvforecastpvnode import PVForecastPVNode
from akkudoktoreos.prediction.pvforecastsolcast import PVForecastSolcast
from akkudoktoreos.prediction.pvforecastvrm import PVForecastVrm
from akkudoktoreos.prediction.weatherbrightsky import WeatherBrightSky
from akkudoktoreos.prediction.weatherclearoutside import WeatherClearOutside
from akkudoktoreos.prediction.weatherimport import WeatherImport
from akkudoktoreos.prediction.weatheropenmeteo import WeatherOpenMeteo


@pytest.fixture
def prediction():
    """All EOS predictions."""
    return get_prediction()


@pytest.fixture
def forecast_providers():
    """Fixture for singleton forecast provider instances."""
    return [
        WeatherBrightSky(),
        WeatherClearOutside(),
        WeatherImport(),
        WeatherOpenMeteo(),
        ElecFeeFixed(),
        ElecFeeImport(),
        ElecPriceAkkudoktor(),
        ElecPriceEnergyCharts(),
        ElecPriceFixed(),
        ElecPriceImport(),
        ElecPriceSMARD(),
        ElecPriceTibber(),
        FeedInTariffAkkudoktor(),
        FeedInTariffDvhubOnline(),
        FeedInTariffEnergyCharts(),
        FeedInTariffFixed(),
        FeedInTariffImport(),
        FeedInTariffSMARD(),
        FeedInTariffTibber(),
        LoadAkkudoktor(),
        LoadAkkudoktorAdjusted(),
        LoadVictronHistory(),
        LoadImport(),
        LoadVrm(),
        PVForecastAkkudoktor(),
        PVForecastForecastSolar(),
        PVForecastHomeAssistant(),
        PVForecastImport(),
        PVForecastPVLib(),
        PVForecastPVLibVictron(),
        PVForecastPVNode(),
        PVForecastSolcast(),
        PVForecastVrm(),
    ]


@pytest.mark.parametrize(
    "field_name, invalid_value, expected_error",
    [
        ("hours", -1, "Input should be greater than or equal to 0"),
        ("historic_hours", -5, "Input should be greater than or equal to 0"),
    ],
)
def test_prediction_common_settings_invalid(field_name, invalid_value, expected_error, config_eos):
    """Test invalid settings for PredictionCommonSettings."""
    valid_data = {
        "hours": 48,
        "historic_hours": 24,
    }
    assert PredictionCommonSettings(**valid_data) is not None
    valid_data[field_name] = invalid_value

    with pytest.raises(ValidationError, match=expected_error):
        PredictionCommonSettings(**valid_data)


def test_initialization(prediction, forecast_providers):
    """Test that Prediction is initialized with the correct providers in sequence."""
    assert isinstance(prediction, Prediction)
    for idx, provider in enumerate(prediction.providers):
        assert provider.provider_id() == forecast_providers[idx].provider_id()


def test_provider_sequence(prediction):
    """Test the provider sequence is maintained in the Prediction instance."""
    expected = [
        WeatherBrightSky,
        WeatherClearOutside,
        WeatherImport,
        WeatherOpenMeteo,
        ElecFeeFixed,
        ElecFeeImport,
        ElecPriceAkkudoktor,
        ElecPriceEnergyCharts,
        ElecPriceFixed,
        ElecPriceImport,
        ElecPriceSMARD,
        ElecPriceTibber,
        FeedInTariffAkkudoktor,
        FeedInTariffDvhubOnline,
        FeedInTariffEnergyCharts,
        FeedInTariffFixed,
        FeedInTariffImport,
        FeedInTariffSMARD,
        FeedInTariffTibber,
        LoadAkkudoktor,
        LoadAkkudoktorAdjusted,
        LoadVictronHistory,
        LoadImport,
        LoadVrm,
        PVForecastAkkudoktor,
        PVForecastForecastSolar,
        PVForecastHomeAssistant,
        PVForecastImport,
        PVForecastPVLib,
        PVForecastPVLibVictron,
        PVForecastPVNode,
        PVForecastSolcast,
        PVForecastVrm,
    ]
    assert len(prediction.providers) == len(expected)
    for provider, expected_type in zip(prediction.providers, expected):
        assert isinstance(provider, expected_type)


def test_provider_by_id(prediction, forecast_providers):
    """Test that provider_by_id method returns the correct provider."""
    for provider in forecast_providers:
        assert prediction.provider_by_id(provider.provider_id()).provider_id() == provider.provider_id()


def test_prediction_repr(prediction):
    """Test that the Prediction instance's representation is correct."""
    result = repr(prediction)
    assert "Prediction([" in result
    expected_names = [
        "ElecFeeFixed",
        "ElecFeeImport",
        "ElecPriceAkkudoktor",
        "ElecPriceEnergyCharts",
        "ElecPriceFixed",
        "ElecPriceImport",
        "ElecPriceSMARD",
        "ElecPriceTibber",
        "FeedInTariffAkkudoktor",
        "FeedInTariffDvhubOnline",
        "FeedInTariffEnergyCharts",
        "FeedInTariffFixed",
        "FeedInTariffImport",
        "FeedInTariffSMARD",
        "FeedInTariffTibber",
        "LoadAkkudoktor",
        "LoadAkkudoktorAdjusted",
        "LoadVictronHistory",
        "LoadImport",
        "LoadVrm",
        "PVForecastAkkudoktor",
        "PVForecastForecastSolar",
        "PVForecastHomeAssistant",
        "PVForecastImport",
        "PVForecastPVLib",
        "PVForecastPVLibVictron",
        "PVForecastPVNode",
        "PVForecastSolcast",
        "PVForecastVrm",
        "WeatherBrightSky",
        "WeatherClearOutside",
        "WeatherImport",
        "WeatherOpenMeteo",
    ]
    for name in expected_names:
        assert name in result


@pytest.mark.asyncio
async def test_empty_providers(prediction, forecast_providers):
    """Test behavior when Prediction does not have providers."""
    providers_bkup = prediction.providers.copy()
    prediction.providers.clear()
    assert prediction.providers == []
    await prediction.update_data()  # Should not raise an error even with no providers
    prediction.providers = providers_bkup
