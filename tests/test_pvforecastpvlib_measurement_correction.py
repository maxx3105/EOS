"""Tests for measured-PV feedback correction of the PVLib forecast."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from akkudoktoreos.core.coreabc import get_ems
from akkudoktoreos.prediction.pvforecastpvlib import PVForecastPVLib
from akkudoktoreos.utils.datetimeutil import to_datetime


@pytest.fixture
def provider(config_eos):
    """Create a PVLib provider with a configured PV production meter."""
    config_eos.pvforecast.provider = "PVForecastPVLib"
    config_eos.measurement.pv_production_emr_keys = ["pv1_emr"]

    PVForecastPVLib.reset_instance()
    pv_provider = PVForecastPVLib()

    get_ems().set_start_datetime(
        to_datetime("2026-06-01 12:00:00+02:00", in_timezone="Europe/Berlin")
    )
    return pv_provider


def _forecast(power_w: float = 1000.0) -> pd.DataFrame:
    """Return a 15-minute forecast spanning one hour history and three hours future."""
    index = pd.date_range(
        "2026-06-01 11:00:00",
        "2026-06-01 15:00:00",
        freq="15min",
        tz="Europe/Berlin",
    )
    return pd.DataFrame(
        {
            "pv_dc_power": np.full(len(index), power_w * 1.2),
            "ac_power": np.full(len(index), power_w),
        },
        index=index,
    )


def _measurement_mock(
    meter_values: list[float], latest: str = "2026-06-01 12:00:00+02:00"
) -> MagicMock:
    """Return a measurement mock with recent raw timestamps and resampled meter values."""
    measurement = MagicMock()
    latest_dt = pd.Timestamp(latest)
    measurement.key_to_raw_series = AsyncMock(
        return_value=pd.Series(
            [meter_values[0], meter_values[-1]],
            index=pd.DatetimeIndex([latest_dt - pd.Timedelta(hours=1), latest_dt]),
        )
    )
    measurement.key_to_array = AsyncMock(return_value=np.asarray(meter_values, dtype=float))
    return measurement


@pytest.mark.asyncio
async def test_measurement_correction_scales_near_term_and_decays(provider):
    """Recent measured underproduction shall reduce near-term forecast and decay over time."""
    forecast = _forecast(1000.0)
    measurement = _measurement_mock([100.0, 100.125, 100.25, 100.375, 100.5])

    with patch(
        "akkudoktoreos.prediction.pvforecastpvlib.get_measurement",
        return_value=measurement,
    ):
        corrected = await provider._apply_measurement_correction(forecast)

    # PVLib predicts 1.0 kWh in the previous hour, while the meter reports 0.5 kWh.
    assert corrected.loc["2026-06-01 12:00:00+02:00", "ac_power"] == pytest.approx(500.0)
    assert corrected.loc["2026-06-01 12:00:00+02:00", "pv_dc_power"] == pytest.approx(600.0)

    # Historic values are never rewritten.
    assert corrected.loc["2026-06-01 11:45:00+02:00", "ac_power"] == pytest.approx(1000.0)

    # Three hours later the correction has decayed substantially back toward the physical forecast.
    expected_factor = 1.0 + (0.5 - 1.0) * np.exp(-1.0)
    assert corrected.loc["2026-06-01 15:00:00+02:00", "ac_power"] == pytest.approx(
        1000.0 * expected_factor
    )


@pytest.mark.asyncio
async def test_measurement_correction_clamps_large_ratio(provider):
    """An extreme measured/model ratio shall be limited to the configured safety bound."""
    forecast = _forecast(1000.0)
    measurement = _measurement_mock([100.0, 100.5, 101.0, 101.5, 102.0])

    with patch(
        "akkudoktoreos.prediction.pvforecastpvlib.get_measurement",
        return_value=measurement,
    ):
        corrected = await provider._apply_measurement_correction(forecast)

    # 2.0 kWh measured vs 1.0 kWh modeled -> raw factor 2.0, clamped to 1.5.
    assert corrected.loc["2026-06-01 12:00:00+02:00", "ac_power"] == pytest.approx(1500.0)


@pytest.mark.asyncio
async def test_measurement_correction_skips_stale_meter(provider):
    """PV meter readings older than the freshness limit shall not alter the forecast."""
    forecast = _forecast(1000.0)
    measurement = _measurement_mock(
        [100.0, 100.125, 100.25, 100.375, 100.5],
        latest="2026-06-01 11:15:00+02:00",
    )

    with patch(
        "akkudoktoreos.prediction.pvforecastpvlib.get_measurement",
        return_value=measurement,
    ):
        corrected = await provider._apply_measurement_correction(forecast)

    pd.testing.assert_frame_equal(corrected, forecast)
    measurement.key_to_array.assert_not_awaited()


@pytest.mark.asyncio
async def test_measurement_correction_skips_meter_reset(provider):
    """A decreasing cumulative energy meter shall be treated as a reset, not production."""
    forecast = _forecast(1000.0)
    measurement = _measurement_mock([100.0, 100.2, 99.0, 99.2, 99.4])

    with patch(
        "akkudoktoreos.prediction.pvforecastpvlib.get_measurement",
        return_value=measurement,
    ):
        corrected = await provider._apply_measurement_correction(forecast)

    pd.testing.assert_frame_equal(corrected, forecast)


@pytest.mark.asyncio
async def test_measurement_correction_skips_low_modeled_power(provider):
    """Low-light periods shall not create unstable correction ratios."""
    forecast = _forecast(100.0)
    measurement = _measurement_mock([100.0, 100.025, 100.05, 100.075, 100.1])

    with patch(
        "akkudoktoreos.prediction.pvforecastpvlib.get_measurement",
        return_value=measurement,
    ):
        corrected = await provider._apply_measurement_correction(forecast)

    pd.testing.assert_frame_equal(corrected, forecast)


@pytest.mark.asyncio
async def test_measurement_correction_is_noop_without_pv_meter_keys(provider, config_eos):
    """Existing installations without PV energy meters shall retain the original forecast."""
    config_eos.measurement.pv_production_emr_keys = None
    forecast = _forecast(1000.0)

    with patch("akkudoktoreos.prediction.pvforecastpvlib.get_measurement") as get_measurement:
        corrected = await provider._apply_measurement_correction(forecast)

    pd.testing.assert_frame_equal(corrected, forecast)
    get_measurement.assert_not_called()
