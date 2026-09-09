"""Regression tests for the local Victron Cerbo load-history forecast."""

import numpy as np

from akkudoktoreos.prediction.loadvictronhistory import LoadVictronHistory
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
