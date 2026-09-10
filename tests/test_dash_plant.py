"""Regression checks for the compact Victron plant dashboard."""

import pandas as pd
import pytest

from akkudoktoreos.server.dash.plant import (
    ZERO_EXPORT_TOLERANCE_W,
    _battery_text,
    _grid_text,
    _raw_surplus,
    _series_energy_kwh,
)


def test_grid_display_uses_victron_import_positive_convention():
    value, status, warning = _grid_text(125.0)

    assert value == "125 W Bezug"
    assert "Nulleinspeisung" in status
    assert warning is False


def test_small_export_stays_inside_zero_export_tolerance():
    value, status, warning = _grid_text(-30.0)

    assert ZERO_EXPORT_TOLERANCE_W == 50.0
    assert value == "30 W Einspeisung"
    assert "Toleranz" in status
    assert warning is False


def test_larger_instantaneous_export_is_marked_for_review():
    value, status, warning = _grid_text(-120.0)

    assert value == "120 W Einspeisung"
    assert "Rückspeisung" in status
    assert warning is True


def test_battery_display_uses_positive_charging_convention():
    assert _battery_text(3200.0) == "3.20 kW Laden"
    assert _battery_text(-1800.0) == "1.80 kW Entladen"


def test_raw_surplus_never_becomes_negative():
    index = pd.date_range("2026-09-10T10:00:00+02:00", periods=4, freq="15min")
    pv = pd.Series([1000.0, 5000.0, 2000.0, 0.0], index=index)
    load = pd.Series([1500.0, 1000.0, 2500.0, 700.0], index=index)

    surplus = _raw_surplus(pv, load)

    assert surplus.tolist() == [0.0, 4000.0, 0.0, 0.0]


def test_quarter_hour_surplus_energy_is_calculated_in_kwh():
    index = pd.date_range("2026-09-10T10:00:00+02:00", periods=4, freq="15min")
    surplus = pd.Series([4000.0, 4000.0, 4000.0, 4000.0], index=index)

    assert _series_energy_kwh(surplus) == pytest.approx(4.0)
