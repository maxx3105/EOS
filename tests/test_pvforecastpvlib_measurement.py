"""Tests for short-term PVLib forecast correction from PV measurements."""

import pandas as pd
import pytest

from akkudoktoreos.prediction.pvforecastpvlib import PVForecastPVLib


def test_measurement_correction_decays_to_physical_forecast() -> None:
    """Recent PV measurements should affect nowcast strongly and decay with horizon."""
    index = pd.date_range("2026-09-08 10:00", periods=11, freq="15min", tz="Europe/Vienna")
    forecast = pd.DataFrame(
        {"pv_dc_power": 1200.0, "ac_power": 1000.0},
        index=index,
    )
    anchor = pd.Timestamp("2026-09-08 10:30", tz="Europe/Vienna")

    corrected = PVForecastPVLib._apply_measurement_correction(forecast, anchor, 500.0)

    # Past values are untouched.
    assert corrected.loc[index[0], "ac_power"] == 1000.0
    # At the correction anchor the measured/model ratio is applied directly.
    assert corrected.loc[anchor, "ac_power"] == pytest.approx(500.0)
    assert corrected.loc[anchor, "pv_dc_power"] == pytest.approx(600.0)
    # The correction decays towards the original physical forecast.
    assert 500.0 < corrected.loc[index[-1], "ac_power"] < 1000.0


def test_measurement_correction_is_bounded() -> None:
    """A single anomalous measurement must not multiply the forecast without bounds."""
    index = pd.date_range("2026-09-08 10:00", periods=3, freq="15min", tz="Europe/Vienna")
    forecast = pd.DataFrame(
        {"pv_dc_power": 1200.0, "ac_power": 1000.0},
        index=index,
    )
    anchor = index[1]

    corrected_low = PVForecastPVLib._apply_measurement_correction(forecast, anchor, 0.0)
    corrected_high = PVForecastPVLib._apply_measurement_correction(forecast, anchor, 10000.0)

    assert corrected_low.loc[anchor, "ac_power"] == pytest.approx(100.0)
    assert corrected_high.loc[anchor, "ac_power"] == pytest.approx(2000.0)


def test_measurement_correction_skips_low_light() -> None:
    """Near sunrise/sunset a ratio is too unstable, so low modeled power is left unchanged."""
    index = pd.date_range("2026-09-08 06:00", periods=3, freq="15min", tz="Europe/Vienna")
    forecast = pd.DataFrame(
        {"pv_dc_power": 150.0, "ac_power": 100.0},
        index=index,
    )

    corrected = PVForecastPVLib._apply_measurement_correction(forecast, index[1], 20.0)

    pd.testing.assert_frame_equal(corrected, forecast)
