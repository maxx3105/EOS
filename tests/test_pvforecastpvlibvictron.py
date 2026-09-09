"""Tests for the Victron-aware PVLib forecast provider."""

from unittest.mock import patch

import pandas as pd
import pytest

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


def test_numeric_inverter_power_becomes_victron_mppt_output_stage(config_eos):
    """Numeric powers must not select an arbitrary CEC grid inverter."""
    PVForecastPVLibVictron.reset_instance()
    provider = PVForecastPVLibVictron()

    model = provider._get_model("5800", pd.DataFrame(), "inverter")

    assert model is not None
    assert model.name == "Victron_MPPT_5800W"
    assert model["eta_inv_nom"] == pytest.approx(0.985)
    assert model["pdc0"] * model["eta_inv_nom"] == pytest.approx(5800.0)


def test_250_60_numeric_limit_is_preserved(config_eos):
    PVForecastPVLibVictron.reset_instance()
    provider = PVForecastPVLibVictron()

    model = provider._get_model(3440, pd.DataFrame(), "inverter")

    assert model is not None
    assert model["pdc0"] * model["eta_inv_nom"] == pytest.approx(3440.0)


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
