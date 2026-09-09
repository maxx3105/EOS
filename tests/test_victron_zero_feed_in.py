"""Tests for the Synology/Victron zero-feed-in simulation boundary."""

from akkudoktoreos.devices.genetic import inverter as inverter_module
from akkudoktoreos.optimization.genetic.geneticdevices import InverterParameters


class _FullSelfConsumptionPredictor:
    def calculate_self_consumption(self, consumption: float, generation: float) -> float:
        return 1.0


def _inverter(monkeypatch, zero_feed_in: bool) -> inverter_module.Inverter:
    monkeypatch.setattr(
        inverter_module,
        "get_eos_load_interpolator",
        lambda: _FullSelfConsumptionPredictor(),
    )
    monkeypatch.delenv("EOS_SERVER__EOSDASH_SESSKEY", raising=False)
    if zero_feed_in:
        monkeypatch.setenv("EOS_VICTRON_ZERO_FEED_IN", "1")
    else:
        monkeypatch.delenv("EOS_VICTRON_ZERO_FEED_IN", raising=False)

    return inverter_module.Inverter(
        InverterParameters(device_id="test-inverter", max_power_wh=10_000)
    )


def _surplus_result(inverter: inverter_module.Inverter) -> tuple[float, float, float, float]:
    return inverter.process_energy(
        generation=5_000,
        consumption=1_000,
        hour=0,
    )


def test_default_model_can_export_surplus(monkeypatch):
    inverter = _inverter(monkeypatch, zero_feed_in=False)

    grid_export, grid_import, losses, self_consumption = _surplus_result(inverter)

    assert grid_export == 4_000
    assert grid_import == 0
    assert losses == 0
    assert self_consumption == 1_000


def test_explicit_victron_zero_feed_in_curtailed_instead_of_exported(monkeypatch):
    inverter = _inverter(monkeypatch, zero_feed_in=True)

    grid_export, grid_import, losses, self_consumption = _surplus_result(inverter)

    assert grid_export == 0
    assert grid_import == 0
    assert losses == 4_000
    assert self_consumption == 1_000


def test_existing_synology_victron_profile_enables_zero_feed_in(monkeypatch):
    monkeypatch.setattr(
        inverter_module,
        "get_eos_load_interpolator",
        lambda: _FullSelfConsumptionPredictor(),
    )
    monkeypatch.delenv("EOS_VICTRON_ZERO_FEED_IN", raising=False)
    monkeypatch.setenv(
        "EOS_SERVER__EOSDASH_SESSKEY",
        "eos-victron-synology-local-session",
    )

    inverter = inverter_module.Inverter(
        InverterParameters(device_id="test-inverter", max_power_wh=10_000)
    )
    grid_export, grid_import, losses, self_consumption = _surplus_result(inverter)

    assert grid_export == 0
    assert grid_import == 0
    assert losses == 4_000
    assert self_consumption == 1_000
