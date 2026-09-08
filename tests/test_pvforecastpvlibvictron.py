"""Tests for the Victron-aware PVLib forecast provider."""

from unittest.mock import patch

from akkudoktoreos.prediction.pvforecast import PVForecastCommonSettings
from akkudoktoreos.prediction.pvforecastpvlibvictron import PVForecastPVLibVictron
from akkudoktoreos.utils.datetimeutil import to_datetime


def test_victron_pvlib_provider_id():
    assert PVForecastPVLibVictron.provider_id() == "PVForecastPVLibVictron"


def test_victron_provider_allowed_during_early_config_validation():
    with patch(
        "akkudoktoreos.prediction.pvforecast.get_prediction",
        side_effect=RuntimeError("Prediction not initialized"),
    ):
        settings = PVForecastCommonSettings(provider="PVForecastPVLibVictron")
    assert settings.provider == "PVForecastPVLibVictron"


def test_aligns_feedback_to_completed_quarter_hour(config_eos):
    PVForecastPVLibVictron.reset_instance()
    provider = PVForecastPVLibVictron()
    timestamp = to_datetime("2026-06-01T12:29:42+02:00")
    aligned = provider._align_correction_end(timestamp)
    assert aligned == to_datetime("2026-06-01T12:15:00+02:00")


def test_alignment_keeps_exact_quarter_hour(config_eos):
    PVForecastPVLibVictron.reset_instance()
    provider = PVForecastPVLibVictron()
    timestamp = to_datetime("2026-06-01T12:30:00+02:00")
    aligned = provider._align_correction_end(timestamp)
    assert aligned == timestamp
