"""Regression tests for the local Victron Cerbo load-history forecast."""

import numpy as np
import pandas as pd

from akkudoktoreos.measurement.measurement import MeasurementCommonSettings
from akkudoktoreos.prediction.loadvictronhistory import (
    LoadVictronHistory,
    LoadVictronHistoryCommonSettings,
)
from akkudoktoreos.utils.datetimeutil import to_datetime


def test_victron_history_provider_id():
    assert LoadVictronHistory.provider_id() == "LoadVictronHistory"


def test_weighted_median_is_robust_against_single_ev_spike():
    values = np.asarray([650.0, 720.0, 690.0, 11000.0])
    weights = np.ones(4)

    result = LoadVictronHistory._weighted_median(values, weights)

    assert result == 690.0


def test_weighted_median_respects_recency_weights():
    values = np.asarray([500.0, 900.0, 1000.0])
    weights = np.asarray([0.1, 0.4, 1.0])

    result = LoadVictronHistory._weighted_median(values, weights)

    assert result == 1000.0


def test_quarter_hour_alignment():
    timestamp = to_datetime("2026-09-09T08:17:42+02:00")

    assert LoadVictronHistory._floor_interval(timestamp) == to_datetime(
        "2026-09-09T08:15:00+02:00"
    )
    assert LoadVictronHistory._ceil_interval(timestamp) == to_datetime(
        "2026-09-09T08:30:00+02:00"
    )


def test_seasonal_distance_wraps_around_new_year():
    history_index = pd.DatetimeIndex(
        ["2025-12-31T08:00:00+01:00", "2026-01-15T08:00:00+01:00"]
    )
    target = pd.Timestamp("2026-01-01T08:00:00+01:00")

    distance = LoadVictronHistory._circular_day_distance(history_index, target)

    assert distance[0] == 1.0
    assert distance[1] == 14.0


def test_temperature_similarity_halves_every_four_degrees_and_keeps_missing_neutral():
    temperatures = np.asarray([0.0, 4.0, 8.0, np.nan])

    weights = LoadVictronHistory._temperature_similarity_weights(
        temperatures,
        target_temperature_c=0.0,
        half_life_c=4.0,
    )

    np.testing.assert_allclose(weights, [1.0, 0.5, 0.25, 1.0])


def test_seasonal_temperature_defaults_are_enabled_for_victron_history():
    settings = LoadVictronHistoryCommonSettings()

    assert settings.history_days == 90
    assert settings.recency_half_life_days == 21.0
    assert settings.seasonal_weighting is True
    assert settings.seasonal_half_life_days == 45.0
    assert settings.temperature_weighting is True
    assert settings.temperature_half_life_c == 4.0
    assert settings.temperature_history_key == "victron_outdoor_temp_c"


def test_measurement_accepts_local_outdoor_temperature_history():
    settings = MeasurementCommonSettings()

    assert "victron_outdoor_temp_c" in settings.keys


def test_legacy_default_history_window_is_migrated_to_seasonal_profile():
    settings = LoadVictronHistoryCommonSettings.model_validate(
        {
            "history_days": 28,
            "recency_half_life_days": 7.0,
            "recent_window_hours": 6.0,
            "recent_blend": 0.15,
            "min_slot_samples": 2,
        }
    )

    assert settings.history_days == 90
    assert settings.recency_half_life_days == 21.0
    assert settings.seasonal_weighting is True
    assert settings.temperature_weighting is True


def test_explicit_new_history_settings_are_not_migrated():
    settings = LoadVictronHistoryCommonSettings.model_validate(
        {
            "history_days": 28,
            "recency_half_life_days": 7.0,
            "seasonal_weighting": False,
            "temperature_weighting": False,
        }
    )

    assert settings.history_days == 28
    assert settings.recency_half_life_days == 7.0
    assert settings.seasonal_weighting is False
    assert settings.temperature_weighting is False
