"""Tests for the Victron Cerbo GX Modbus TCP adapter."""

from unittest.mock import AsyncMock, patch

import pytest

from akkudoktoreos.adapter.victron import VictronAdapter, VictronAdapterCommonSettings
from akkudoktoreos.devices.devices import BatteriesCommonSettings
from akkudoktoreos.utils.datetimeutil import to_datetime


@pytest.fixture
def provider(config_eos):
    """Create a fresh Victron adapter with standard GX system settings."""
    config_eos.adapter.provider = ["Victron"]
    config_eos.adapter.victron.host = "192.0.2.10"
    config_eos.adapter.victron.unit_id = 100
    VictronAdapter.reset_instance()
    return VictronAdapter()


def _ac_registers() -> list[int]:
    """Return a zeroed 808..822 register block."""
    return [0] * 15


def _set_ac(registers: list[int], register: int, value: int) -> None:
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
        ac = _ac_registers()
        _set_ac(ac, 808, 100)
        _set_ac(ac, 811, 200)
        _set_ac(ac, 817, 400)
        _set_ac(ac, 818, 500)
        _set_ac(ac, 819, 600)
        _set_ac(ac, 820, -100)
        _set_ac(ac, 821, 50)
        battery = [(-500) & 0xFFFF, 75]
        dc_pv = [300]

        with patch.object(
            provider,
            "_read_holding_registers",
            side_effect=[ac, battery, dc_pv],
        ) as read_registers:
            snapshot = provider._read_system_snapshot()

        assert read_registers.call_args_list[0].args == (808, 15)
        assert read_registers.call_args_list[1].args == (842, 2)
        assert read_registers.call_args_list[2].args == (850, 1)
        assert snapshot["pv_power_w"] == 600.0
        assert snapshot["load_power_w"] == 1500.0
        assert snapshot["grid_power_w"] == -50.0
        assert snapshot["battery_power_w"] == -500.0
        assert snapshot["battery_soc_percent"] == 75.0

    def test_dc_only_mode(self, provider, config_eos):
        config_eos.adapter.victron.include_ac_coupled_pv = False
        ac = _ac_registers()
        _set_ac(ac, 808, 900)

        with patch.object(
            provider,
            "_read_holding_registers",
            side_effect=[ac, [0, 0], [350]],
        ):
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

    @pytest.mark.asyncio
    async def test_stores_cerbo_soc_for_configured_battery(self, provider, config_eos):
        config_eos.devices.max_batteries = 1
        config_eos.devices.batteries = [
            BatteriesCommonSettings(device_id="battery1", capacity_wh=39552)
        ]
        sample_time = to_datetime("2026-06-01T12:00:00+02:00")

        measurement = provider.measurement
        with patch.object(measurement, "update_value", new=AsyncMock()) as update_value:
            await provider._store_battery_soc(sample_time, 72.0)

        update_value.assert_awaited_once_with(sample_time, "battery1-soc-factor", 0.72)

    @pytest.mark.asyncio
    async def test_ignores_invalid_cerbo_soc(self, provider, config_eos):
        config_eos.devices.max_batteries = 1
        config_eos.devices.batteries = [
            BatteriesCommonSettings(device_id="battery1", capacity_wh=39552)
        ]
        sample_time = to_datetime("2026-06-01T12:00:00+02:00")

        measurement = provider.measurement
        with patch.object(measurement, "update_value", new=AsyncMock()) as update_value:
            await provider._store_battery_soc(sample_time, 120.0)

        update_value.assert_not_awaited()
