"""Victron Cerbo GX adapter using the official local Modbus-TCP interface."""

from __future__ import annotations

import asyncio
import socket
import struct
import time
from typing import ClassVar, Optional

from loguru import logger
from pydantic import Field, PrivateAttr

from akkudoktoreos.adapter.adapterabc import AdapterProvider
from akkudoktoreos.config.configabc import SettingsBaseModel
from akkudoktoreos.core.ems import EnergyManagementStage
from akkudoktoreos.utils.datetimeutil import DateTime, to_datetime


class VictronAdapterCommonSettings(SettingsBaseModel):
    """Settings for a Victron GX device reachable by Modbus TCP."""

    host: Optional[str] = Field(
        default=None,
        json_schema_extra={
            "description": "IP address or hostname of the Victron Cerbo GX / GX device.",
            "examples": ["192.168.1.50"],
        },
    )
    port: int = Field(
        default=502,
        ge=1,
        le=65535,
        json_schema_extra={"description": "Modbus TCP port on the GX device."},
    )
    unit_id: int = Field(
        default=100,
        ge=0,
        le=255,
        json_schema_extra={
            "description": (
                "Victron Modbus unit ID for com.victronenergy.system. "
                "Victron recommends unit ID 100 for overall system values."
            )
        },
    )
    timeout_sec: float = Field(
        default=3.0,
        ge=0.2,
        le=30.0,
        json_schema_extra={"description": "Socket timeout for Modbus TCP requests [seconds]."},
    )
    pv_energy_key: str = Field(
        default="victron_pv_emr",
        min_length=1,
        json_schema_extra={
            "description": (
                "EOS measurement key used for the cumulative PV production counter [kWh]. "
                "The adapter creates this counter by integrating Victron PV power."
            )
        },
    )
    include_ac_coupled_pv: bool = Field(
        default=True,
        json_schema_extra={
            "description": (
                "Include AC-coupled PV from Victron system registers 808-816 in addition "
                "to DC-coupled PV register 850."
            )
        },
    )
    max_integration_gap_minutes: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        json_schema_extra={
            "description": (
                "Maximum gap between two Victron samples that is integrated into the "
                "local PV energy counter. Larger gaps are skipped to avoid over-counting "
                "after network or NAS outages."
            )
        },
    )


class VictronAdapter(AdapterProvider):
    """Read-only Cerbo GX adapter for PV feedback and basic system telemetry."""

    connected: bool = Field(default=False)
    last_error: Optional[str] = Field(default=None)
    pv_power_w: Optional[float] = Field(default=None)
    grid_power_w: Optional[float] = Field(default=None)
    load_power_w: Optional[float] = Field(default=None)
    battery_power_w: Optional[float] = Field(default=None)
    battery_soc_percent: Optional[float] = Field(default=None)

    _last_sample_time: Optional[DateTime] = PrivateAttr(default=None)
    _last_pv_power_w: Optional[float] = PrivateAttr(default=None)
    _pv_energy_kwh: Optional[float] = PrivateAttr(default=None)

    @classmethod
    def provider_id(cls) -> str:
        """Return the unique identifier for the adapter provider."""
        return "Victron"

    @staticmethod
    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        """Receive exactly ``size`` bytes or raise a connection error."""
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("Cerbo GX closed the Modbus TCP connection unexpectedly")
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _decode_uint16(raw: int) -> Optional[int]:
        """Decode an unsigned Victron register and handle the standard invalid sentinel."""
        if raw == 0xFFFF:
            return None
        return raw

    @staticmethod
    def _decode_int16(raw: int) -> Optional[int]:
        """Decode a signed Victron register and handle the standard invalid sentinel."""
        if raw == 0x7FFF:
            return None
        return raw - 0x10000 if raw & 0x8000 else raw

    @staticmethod
    def _sum_available(
        values: list[Optional[float]], *, clamp_nonnegative: bool = False
    ) -> Optional[float]:
        """Sum available values while ignoring unavailable Modbus sentinel values."""
        valid = [value for value in values if value is not None]
        if not valid:
            return None
        if clamp_nonnegative:
            valid = [max(0.0, float(value)) for value in valid]
        return float(sum(valid))

    def _read_holding_registers(self, address: int, count: int) -> list[int]:
        """Read Modbus holding registers using only the Python standard library."""
        settings = self.config.adapter.victron
        if not settings.host:
            raise ValueError("Victron adapter is enabled but adapter.victron.host is not configured")
        if count < 1 or count > 125:
            raise ValueError(f"Invalid Modbus register count: {count}")

        transaction_id = int(time.monotonic_ns()) & 0xFFFF
        request = struct.pack(
            ">HHHBBHH",
            transaction_id,
            0,
            6,
            settings.unit_id,
            3,
            address,
            count,
        )

        try:
            with socket.create_connection(
                (settings.host, settings.port), timeout=settings.timeout_sec
            ) as sock:
                sock.settimeout(settings.timeout_sec)
                sock.sendall(request)
                header = self._recv_exact(sock, 7)
                response_tid, protocol_id, length, response_unit = struct.unpack(">HHHB", header)
                if response_tid != transaction_id:
                    raise ConnectionError("Unexpected Modbus transaction ID from Cerbo GX")
                if protocol_id != 0:
                    raise ConnectionError("Invalid Modbus protocol ID from Cerbo GX")
                if response_unit != settings.unit_id:
                    raise ConnectionError("Unexpected Modbus unit ID from Cerbo GX")
                if length < 3:
                    raise ConnectionError("Truncated Modbus response from Cerbo GX")
                pdu = self._recv_exact(sock, length - 1)
        except OSError as exc:
            raise ConnectionError(
                f"Cannot connect to Victron GX at {settings.host}:{settings.port}: {exc}"
            ) from exc

        function_code = pdu[0]
        if function_code & 0x80:
            exception_code = pdu[1] if len(pdu) > 1 else -1
            raise ConnectionError(
                f"Cerbo GX Modbus exception {exception_code} while reading register {address}"
            )
        if function_code != 3:
            raise ConnectionError(f"Unexpected Modbus function code {function_code}")

        byte_count = pdu[1]
        expected_bytes = count * 2
        if byte_count != expected_bytes or len(pdu[2:]) != expected_bytes:
            raise ConnectionError(
                f"Unexpected Modbus payload size: expected {expected_bytes}, got {byte_count}"
            )
        return list(struct.unpack(f">{count}H", pdu[2:]))

    def _read_system_snapshot(self) -> dict[str, Optional[float]]:
        """Read and decode known com.victronenergy.system register ranges."""
        ac_system = self._read_holding_registers(808, 15)  # 808..822
        battery = self._read_holding_registers(842, 2)  # 842..843
        dc_pv = self._read_holding_registers(850, 1)  # 850

        def ac_raw(register: int) -> int:
            return ac_system[register - 808]

        ac_pv_values: list[Optional[float]] = []
        if self.config.adapter.victron.include_ac_coupled_pv:
            for register in range(808, 817):
                value = self._decode_uint16(ac_raw(register))
                ac_pv_values.append(float(value) if value is not None else None)

        dc_pv_power = self._decode_uint16(dc_pv[0])
        pv_values = ac_pv_values + [float(dc_pv_power) if dc_pv_power is not None else None]
        pv_power = self._sum_available(pv_values, clamp_nonnegative=True)

        load_power = self._sum_available(
            [self._decode_int16(ac_raw(register)) for register in range(817, 820)]
        )
        grid_power = self._sum_available(
            [self._decode_int16(ac_raw(register)) for register in range(820, 823)]
        )
        battery_power = self._decode_int16(battery[0])
        battery_soc = self._decode_uint16(battery[1])

        return {
            "pv_power_w": pv_power,
            "grid_power_w": grid_power,
            "load_power_w": load_power,
            "battery_power_w": float(battery_power) if battery_power is not None else None,
            "battery_soc_percent": float(battery_soc) if battery_soc is not None else None,
        }

    def _ensure_pv_measurement_key(self) -> str:
        """Register the generated Victron PV energy counter as a PV production measurement."""
        key = self.config.adapter.victron.pv_energy_key
        keys = self.config.measurement.pv_production_emr_keys
        if keys is None:
            self.config.measurement.pv_production_emr_keys = [key]
        elif key not in keys:
            self.config.measurement.pv_production_emr_keys = [*keys, key]
        return key

    def _battery_soc_measurement_key(self) -> Optional[str]:
        """Return the EOS SoC measurement key for the configured aggregate battery."""
        batteries = self.config.devices.batteries
        if not batteries:
            return None
        return batteries[0].measurement_key_soc_factor

    async def _store_battery_soc(
        self, sample_time: DateTime, battery_soc_percent: Optional[float]
    ) -> None:
        """Store the Cerbo system SoC as EOS battery SoC factor (0..1)."""
        if battery_soc_percent is None:
            return
        if battery_soc_percent < 0.0 or battery_soc_percent > 100.0:
            logger.warning("Ignoring invalid Victron battery SoC: {} %", battery_soc_percent)
            return
        key = self._battery_soc_measurement_key()
        if key is None:
            return
        await self.measurement.update_value(sample_time, key, battery_soc_percent / 100.0)

    async def _restore_pv_energy(self, key: str) -> float:
        """Restore the latest generated cumulative PV energy value after a restart."""
        if self._pv_energy_kwh is not None:
            return self._pv_energy_kwh
        try:
            series = await self.measurement.key_to_raw_series(key=key, dropna=True)
            self._pv_energy_kwh = float(series.iloc[-1]) if not series.empty else 0.0
        except (KeyError, TypeError, ValueError):
            self._pv_energy_kwh = 0.0
        return self._pv_energy_kwh

    async def _store_pv_energy(self, sample_time: DateTime, pv_power_w: float) -> None:
        """Integrate PV power into the cumulative EOS PV production meter [kWh]."""
        key = self._ensure_pv_measurement_key()
        energy_kwh = await self._restore_pv_energy(key)

        if self._last_sample_time is not None and self._last_pv_power_w is not None:
            delta_seconds = (sample_time - self._last_sample_time).total_seconds()
            max_gap_seconds = self.config.adapter.victron.max_integration_gap_minutes * 60.0
            if 0 < delta_seconds <= max_gap_seconds:
                average_power_w = (self._last_pv_power_w + pv_power_w) / 2.0
                energy_kwh += average_power_w * delta_seconds / 3_600_000.0
                self._pv_energy_kwh = energy_kwh
            elif delta_seconds > max_gap_seconds:
                logger.warning(
                    "Skipping Victron PV energy integration over a {:.1f} minute data gap",
                    delta_seconds / 60.0,
                )

        await self.measurement.update_value(sample_time, key, energy_kwh)
        self._last_sample_time = sample_time
        self._last_pv_power_w = pv_power_w

    async def _update_data(self) -> None:
        """Poll the Cerbo GX during the EOS data-acquisition stage."""
        if self.ems.stage() != EnergyManagementStage.DATA_ACQUISITION:
            return

        sample_time = to_datetime(in_timezone=self.config.general.timezone)
        try:
            snapshot = await asyncio.to_thread(self._read_system_snapshot)
            pv_power = snapshot["pv_power_w"]
            if pv_power is None:
                raise ValueError("Cerbo GX returned no usable PV power value")

            self.pv_power_w = float(pv_power)
            self.grid_power_w = snapshot["grid_power_w"]
            self.load_power_w = snapshot["load_power_w"]
            self.battery_power_w = snapshot["battery_power_w"]
            self.battery_soc_percent = snapshot["battery_soc_percent"]

            await self._store_pv_energy(sample_time, self.pv_power_w)
            await self._store_battery_soc(sample_time, self.battery_soc_percent)

            self.connected = True
            self.last_error = None
            self.update_datetime = sample_time
            logger.info(
                "Victron GX: PV={:.0f} W, grid={} W, load={} W, battery={} W, SoC={} %",
                self.pv_power_w,
                f"{self.grid_power_w:.0f}" if self.grid_power_w is not None else "n/a",
                f"{self.load_power_w:.0f}" if self.load_power_w is not None else "n/a",
                f"{self.battery_power_w:.0f}" if self.battery_power_w is not None else "n/a",
                f"{self.battery_soc_percent:.0f}" if self.battery_soc_percent is not None else "n/a",
            )
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            logger.error(f"Victron GX update failed: {exc}")
