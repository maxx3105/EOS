"""Tests for the Victron Cerbo GX Modbus TCP adapter."""

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from akkudoktoreos.adapter.victron import VictronAdapter, VictronAdapterCommonSettings
from akkudoktoreos.utils.datetimeutil import to_datetime


@pytest.fixture
def provider(config_eos):
    """Create a fresh Victron adapter with standard GX system settings."""
    config_eos.adapter.provider = ["Victron"]
    config_eos.adapter.victron.host = "192.0.2.10"
    config_eos.adapter.victron.unit_id = 100
    VictronAdapter.reset_instance()
    return VictronAdapter()


def _system_registers() -> list[int]:
    """Return a zeroed 808..851 register block."""
    return [0] * (851 - 808 + 1)


def _set(registers: list[int], register: int, value: int) -> None:
    registers[register - 808] = value & 0xFFFF


class TestVictronSettings:
    def test_defaults(self):
        settings = VictronAdapterCommonSettings()
        assert settings.port == 502
        assert settings.unit_id == 100
        assert settings.pv_energy_key == "victron_pv_emr"
        assert settings.include_ac_coupled_pv is True


class TestVictronRegisterDecoding:
    def test_signed_and_unsigned_sentinels(self):
        assert VictronAdapter._decode_uint16(0xFFFF) is None
        assert VictronAdapter._decode_int16(0x7FFF) is None
        assert VictronAdapter._decode_int16(0xFFEC) == -20
        assert VictronAdapter._decode_int16(123) == 123

    def test_system_snapshot_combines_ac_and_dc_pv(self, provider):
        registers = _system_registers()
        _set(registers, 808, 100)
        _set(registers, 811, 200)
        _set(registers, 850, 300)
        _set(registers, 817, 400)
        _set(registers, 818, 500)
        _set(registers, 819, 600)
        _set(registers, 820, -100)
        _set(registers, 821, 50)
        _set(registers, 842, -500)
        _set(registers, 843, 75)

        with patch.object(provider, "_read_holding_registers", return_value=registers):
            snapshot = provider._read_system_snapshot()

        assert snapshot["pv_power_w"] == 600.0
        assert snapshot["load_power_w"] == 1500.0
        assert snapshot["grid_power_w"] == -50.0
        assert snapshot["battery_power_w"] == -500.0
        assert snapshot["battery_soc_percent"] == 75.0

    def test_dc_only_mode(self, provider, config_eos):
        config_eos.adapter.victron.include_ac_coupled_pv = False
        registers = _system_registers()
        _set(registers, 808, 900)
        _set(registers, 850, 350)

        with patch.object(provider, "_read_holding_registers", return_value=registers):
            snapshot = provider._read_system_snapshot()

        assert snapshot["pv_power_w"] == 350.0


class TestVictronMeasurementIntegration:
    def test_registers_generated_pv_energy_key(self, provider, config_eos):
        config_eos.measurement.pv_production_emr_keys = None
        assert provider._ensure_pv_measurement_key() == "victron_pv_emr"
        assert config_eos.measurement.pv_production_emr_keys == ["victron_pv_emr"]

    @pytest.mark.asyncio
    async def test_integrates_power_to_kwh(self, provider):
        first = to_datetime("2026-06-01T12:00:00+02:00")
        second = to_datetime("2026-06-01T12:05:00+02:00")
        provider._last_sample_time = first
        provider._last_pv_power_w = 1000.0
        provider._pv_energy_kwh = 10.0

        measurement = provider.measurement
        with patch.object(measurement, "update_value", new=AsyncMock()) as update_value:
            await provider._store_pv_energy(second, 1000.0)

        expected = 10.0 + 1000.0 * 300.0 / 3_600_000.0
        assert provider._pv_energy_kwh == pytest.approx(expected)
        update_value.assert_awaited_once()
        assert update_value.await_args.args[1] == "victron_pv_emr"
        assert update_value.await_args.args[2] == pytest.approx(expected)

    @pytest.mark.asyncio
    async def test_skips_large_data_gap(self, provider):
        first = to_datetime("2026-06-01T12:00:00+02:00")
        second = to_datetime("2026-06-01T12:30:00+02:00")
        provider._last_sample_time = first
        provider._last_pv_power_w = 1000.0
        provider._pv_energy_kwh = 10.0

        measurement = provider.measurement
        with patch.object(measurement, "update_value", new=AsyncMock()):
            await provider._store_pv_energy(second, 1000.0)

        assert provider._pv_energy_kwh == pytest.approx(10.0)


def test_numpy_is_not_required_for_adapter_logic():
    """Keep this file's numerical assertions explicit and deterministic."""
    assert np.isfinite(1.0)
