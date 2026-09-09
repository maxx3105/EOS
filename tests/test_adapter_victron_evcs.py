"""Regression checks for Victron EVCS readout and base-load separation."""

import pytest

from akkudoktoreos.adapter.victron import VictronAdapter, VictronAdapterCommonSettings


def test_evcs_registers_decode_total_power_current_and_status():
    # 3818..3824: L1, L2, L3, total, charging time, current, status
    registers = [3200, 3210, 3190, 9600, 123, 14, 2]

    snapshot = VictronAdapter._decode_evcs_registers(registers)

    assert snapshot["power_w"] == 9600.0
    assert snapshot["current_a"] == 14.0
    assert snapshot["status"] == 2.0


def test_evcs_registers_fall_back_to_phase_sum_when_total_is_invalid():
    registers = [1300, 1400, 1500, 0xFFFF, 0, 6, 2]

    snapshot = VictronAdapter._decode_evcs_registers(registers)

    assert snapshot["power_w"] == 4200.0


def test_base_load_subtracts_both_ev_chargers():
    assert VictronAdapter._calculate_base_load_power(12_500.0, [5_000.0, 4_000.0]) == 3_500.0


def test_base_load_is_never_negative():
    assert VictronAdapter._calculate_base_load_power(1_000.0, [4_000.0]) == 0.0


def test_evcs_settings_keep_unit_ids_explicit_and_read_only():
    settings = VictronAdapterCommonSettings(evcs_unit_ids=[40, 41])

    assert settings.evcs_unit_ids == [40, 41]
    assert settings.base_load_energy_key == "victron_base_load_emr"
    assert settings.evcs_energy_key_prefix == "victron_evcs"


def test_evcs_decoder_rejects_wrong_register_count():
    with pytest.raises(ValueError):
        VictronAdapter._decode_evcs_registers([1, 2, 3])
