"""Regression checks for Victron EVCS readout and plant telemetry separation."""

import pytest

from akkudoktoreos.adapter.victron import VictronAdapter, VictronAdapterCommonSettings
from akkudoktoreos.measurement.measurement import MeasurementCommonSettings


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


def test_system_registers_split_dc_ac_out_and_total_pv():
    # 808..810 AC-out PV, 811..813 AC-in PV, 814..816 generator PV,
    # 817..819 consumption, 820..822 grid.
    ac_system = [
        100,
        200,
        300,
        10,
        20,
        30,
        1,
        2,
        3,
        400,
        200,
        100,
        50,
        0xFFEC,  # -20 W signed
        30,
    ]

    snapshot = VictronAdapter._decode_system_registers(
        ac_system,
        [2500, 61],
        [5000],
        include_ac_coupled_pv=True,
    )

    assert snapshot["pv_dc_power_w"] == 5000.0
    assert snapshot["pv_ac_out_power_w"] == 600.0
    assert snapshot["pv_ac_input_power_w"] == 60.0
    assert snapshot["pv_ac_generator_power_w"] == 6.0
    assert snapshot["pv_power_w"] == 5666.0
    assert snapshot["load_power_w"] == 700.0
    assert snapshot["grid_power_w"] == 60.0
    assert snapshot["battery_power_w"] == 2500.0
    assert snapshot["battery_soc_percent"] == 61.0


def test_system_total_can_exclude_ac_coupled_pv_without_hiding_split_values():
    ac_system = [100, 200, 300, 0, 0, 0, 0, 0, 0, 400, 200, 100, 50, 50, 50]

    snapshot = VictronAdapter._decode_system_registers(
        ac_system,
        [1000, 50],
        [5000],
        include_ac_coupled_pv=False,
    )

    assert snapshot["pv_dc_power_w"] == 5000.0
    assert snapshot["pv_ac_out_power_w"] == 600.0
    assert snapshot["pv_power_w"] == 5000.0


def test_measurement_defaults_keep_plant_dashboard_telemetry_writable():
    settings = MeasurementCommonSettings()

    assert {
        "victron_pv_dc_power_w",
        "victron_pv_ac_out_power_w",
        "victron_pv_total_power_w",
        "victron_house_non_ev_power_w",
        "victron_ev_power_w",
        "victron_battery_power_w",
        "victron_grid_power_w",
    } <= set(settings.telemetry_keys)


def test_victron_total_and_evcs_energy_counters_are_writable_but_not_load_sources():
    settings = MeasurementCommonSettings(load_emr_keys=["victron_base_load_emr"])

    assert {
        "victron_load_emr",
        "victron_evcs_40_emr",
        "victron_evcs_41_emr",
    } <= set(settings.adapter_energy_keys)
    assert {
        "victron_load_emr",
        "victron_evcs_40_emr",
        "victron_evcs_41_emr",
        "victron_base_load_emr",
    } <= set(settings.keys)
    assert settings.load_emr_keys == ["victron_base_load_emr"]
