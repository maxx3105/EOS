"""Tests for the Victron-aware PVLib forecast provider."""

from unittest.mock import patch

import pandas as pd
import pytest
from pvlib.inverter import sandia

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
    assert model["Paco"] == pytest.approx(5800.0)
    assert model["Pdco"] * provider._mppt_output_efficiency == pytest.approx(5800.0)
    assert {"Paco", "Pdco", "Vdco", "Pso", "C0", "C1", "C2", "C3", "Pnt"} <= set(
        model.index
    )
    assert "pdc0" not in model
    assert "eta_inv_nom" not in model


def test_victron_mppt_output_stage_returns_power_series_and_clips(config_eos):
    """CEC DC data must collapse to one AC power series, not a dataframe."""
    PVForecastPVLibVictron.reset_instance()
    provider = PVForecastPVLibVictron()
    model = provider._get_model("5800", pd.DataFrame(), "inverter")
    assert model is not None

    v_dc = pd.Series([100.0, 100.0], index=[0, 1])
    p_dc = pd.Series([1000.0, 10000.0], index=[0, 1])
    ac = sandia(v_dc, p_dc, model)

    assert isinstance(ac, pd.Series)
    assert ac.iloc[0] == pytest.approx(985.0)
    assert ac.iloc[1] == pytest.approx(5800.0)


def test_250_60_numeric_limit_is_preserved(config_eos):
    PVForecastPVLibVictron.reset_instance()
    provider = PVForecastPVLibVictron()

    model = provider._get_model(3440, pd.DataFrame(), "inverter")

    assert model is not None
    assert model["Paco"] == pytest.approx(3440.0)
    assert model["Pdco"] * provider._mppt_output_efficiency == pytest.approx(3440.0)


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


def test_raw_meter_window_accepts_continuous_real_samples():
    start = to_datetime("2026-09-09T09:00:00+02:00")
    end = to_datetime("2026-09-09T10:00:00+02:00")
    index = pd.date_range(start=pd.Timestamp(start), end=pd.Timestamp(end), freq="5min")
    series = pd.Series([float(i) / 100.0 for i in range(len(index))], index=index)

    assert PVForecastPVLibVictron._raw_meter_window_is_complete(series, start, end) is True


def test_raw_meter_window_rejects_partial_window_after_restart():
    start = to_datetime("2026-09-09T09:00:00+02:00")
    end = to_datetime("2026-09-09T10:00:00+02:00")
    index = pd.date_range(
        start=pd.Timestamp("2026-09-09T09:48:00+02:00"),
        end=pd.Timestamp(end),
        freq="5min",
    )
    series = pd.Series([0.0, 0.03, 0.07], index=index)

    assert PVForecastPVLibVictron._raw_meter_window_is_complete(series, start, end) is False


def test_raw_meter_window_rejects_counter_reset():
    start = to_datetime("2026-09-09T09:00:00+02:00")
    end = to_datetime("2026-09-09T10:00:00+02:00")
    index = pd.date_range(start=pd.Timestamp(start), end=pd.Timestamp(end), freq="15min")
    series = pd.Series([3.0, 3.5, 4.0, 0.0, 0.4], index=index)

    assert PVForecastPVLibVictron._raw_meter_window_is_complete(series, start, end) is False
