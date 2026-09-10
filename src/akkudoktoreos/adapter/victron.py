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
    load_energy_key: str = Field(
        default="victron_load_emr",
        min_length=1,
        json_schema_extra={
            "description": (
                "EOS measurement key used for the cumulative total site-load counter [kWh]. "
                "This value includes EV charging."
            )
        },
    )
    base_load_energy_key: str = Field(
        default="victron_base_load_emr",
        min_length=1,
        json_schema_extra={
            "description": (
                "EOS measurement key used for site load after subtracting configured EV chargers. "
                "LoadVictronHistory should learn from this counter when EVCS unit IDs are configured."
            )
        },
    )
    evcs_unit_ids: list[int] = Field(
        default_factory=list,
        json_schema_extra={
            "description": (
                "Modbus TCP unit IDs of com.victronenergy.evcharger services exposed by the GX device."
            ),
            "examples": [[40, 41]],
        },
    )
    evcs_energy_key_prefix: str = Field(
        default="victron_evcs",
        min_length=1,
        json_schema_extra={
            "description": (
                "Prefix for locally integrated EVCS energy counters. Unit ID 40 becomes "
                "'<prefix>_40_emr'."
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
                "local PV/load energy counters. Larger gaps are skipped to avoid over-counting "
                "after network or NAS outages."
            )
        },
    )


class VictronAdapter(AdapterProvider):
    """Read-only Cerbo GX adapter for PV feedback and basic system telemetry."""

    _EVCS_FIRST_REGISTER: ClassVar[int] = 3818
    _EVCS_REGISTER_COUNT: ClassVar[int] = 7  # 3818..3824
    _TELEMETRY_KEYS: ClassVar[tuple[str, ...]] = (
        "victron_pv_dc_power_w",
        "victron_pv_ac_out_power_w",
        "victron_pv_total_power_w",
        "victron_site_load_power_w",
        "victron_house_non_ev_power_w",
        "victron_ev_power_w",
        "victron_battery_power_w",
        "victron_grid_power_w",
    )

    connected: bool = Field(default=False)
    last_error: Optional[str] = Field(default=None)
    # ``pv_power_w`` remains the backwards-compatible total PV value used by the
    # existing forecast correction. The split fields expose the physical topology.
    pv_power_w: Optional[float] = Field(default=None)
    pv_dc_power_w: Optional[float] = Field(default=None)
    pv_ac_out_power_w: Optional[float] = Field(default=None)
    pv_ac_input_power_w: Optional[float] = Field(default=None)
    pv_ac_generator_power_w: Optional[float] = Field(default=None)
    grid_power_w: Optional[float] = Field(default=None)
    load_power_w: Optional[float] = Field(default=None)
    base_load_power_w: Optional[float] = Field(default=None)
    house_non_ev_power_w: Optional[float] = Field(default=None)
    battery_power_w: Optional[float] = Field(default=None)
    battery_soc_percent: Optional[float] = Field(default=None)
    ev_total_power_w: Optional[float] = Field(default=None)
    evcs_power_w: dict[int, float] = Field(default_factory=dict)
    evcs_current_a: dict[int, float] = Field(default_factory=dict)
    evcs_status: dict[int, int] = Field(default_factory=dict)
    evcs_errors: dict[int, str] = Field(default_factory=dict)

    _energy_kwh_by_key: dict[str, float] = PrivateAttr(default_factory=dict)
    _last_energy_sample_time_by_key: dict[str, DateTime] = PrivateAttr(default_factory=dict)
    _last_energy_power_w_by_key: dict[str, float] = PrivateAttr(default_factory=dict)

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

    @staticmethod
    def _calculate_base_load_power(site_load_w: float, evcs_powers_w: list[float]) -> float:
        """Return non-EV site load without ever creating a negative base load."""
        return max(0.0, float(site_load_w) - sum(max(0.0, float(v)) for v in evcs_powers_w))

    def _read_holding_registers(
        self, address: int, count: int, *, unit_id: Optional[int] = None
    ) -> list[int]:
        """Read Modbus holding registers using only the Python standard library."""
        settings = self.config.adapter.victron
        if not settings.host:
            raise ValueError("Victron adapter is enabled but adapter.victron.host is not configured")
        if count < 1 or count > 125:
            raise ValueError(f"Invalid Modbus register count: {count}")

        target_unit_id = settings.unit_id if unit_id is None else int(unit_id)
        if target_unit_id < 0 or target_unit_id > 255:
            raise ValueError(f"Invalid Modbus unit ID: {target_unit_id}")

        transaction_id = int(time.monotonic_ns()) & 0xFFFF
        request = struct.pack(
            ">HHHBBHH",
            transaction_id,
            0,
            6,
            target_unit_id,
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
                if response_unit != target_unit_id:
                    raise ConnectionError(
                        f"Unexpected Modbus unit ID from Cerbo GX: expected {target_unit_id}, "
                        f"got {response_unit}"
                    )
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
                f"Cerbo GX Modbus exception {exception_code} on unit {target_unit_id} "
                f"while reading register {address}"
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

    @classmethod
    def _decode_system_registers(
        cls,
        ac_system: list[int],
        battery: list[int],
        dc_pv: list[int],
        *,
        include_ac_coupled_pv: bool,
    ) -> dict[str, Optional[float]]:
        """Decode the relevant ``com.victronenergy.system`` register blocks.

        Register groups are kept explicit so the dashboard can distinguish the four
        SmartSolar DC chargers from AC-coupled PV. For this installation AC-output PV
        is the Hoymiles HMS-800W-2T exposed by Venus OS as a pvinverter at Position 1.
        """
        if len(ac_system) != 15 or len(battery) != 2 or len(dc_pv) != 1:
            raise ValueError("Unexpected Victron system register block size")

        def ac_raw(register: int) -> int:
            return ac_system[register - 808]

        def ac_pv_group(first_register: int) -> Optional[float]:
            return cls._sum_available(
                [
                    float(value) if value is not None else None
                    for value in (
                        cls._decode_uint16(ac_raw(first_register)),
                        cls._decode_uint16(ac_raw(first_register + 1)),
                        cls._decode_uint16(ac_raw(first_register + 2)),
                    )
                ],
                clamp_nonnegative=True,
            )

        pv_ac_out_power = ac_pv_group(808)
        pv_ac_input_power = ac_pv_group(811)
        pv_ac_generator_power = ac_pv_group(814)
        dc_value = cls._decode_uint16(dc_pv[0])
        pv_dc_power = float(dc_value) if dc_value is not None else None

        pv_components: list[Optional[float]] = [pv_dc_power]
        if include_ac_coupled_pv:
            pv_components.extend(
                [pv_ac_out_power, pv_ac_input_power, pv_ac_generator_power]
            )
        pv_power = cls._sum_available(pv_components, clamp_nonnegative=True)

        load_power = cls._sum_available(
            [cls._decode_int16(ac_raw(register)) for register in range(817, 820)]
        )
        grid_power = cls._sum_available(
            [cls._decode_int16(ac_raw(register)) for register in range(820, 823)]
        )
        battery_power = cls._decode_int16(battery[0])
        battery_soc = cls._decode_uint16(battery[1])

        return {
            "pv_power_w": pv_power,
            "pv_dc_power_w": pv_dc_power,
            "pv_ac_out_power_w": pv_ac_out_power,
            "pv_ac_input_power_w": pv_ac_input_power,
            "pv_ac_generator_power_w": pv_ac_generator_power,
            "grid_power_w": grid_power,
            "load_power_w": load_power,
            "battery_power_w": float(battery_power) if battery_power is not None else None,
            "battery_soc_percent": float(battery_soc) if battery_soc is not None else None,
        }

    def _read_system_snapshot(self) -> dict[str, Optional[float]]:
        """Read and decode known com.victronenergy.system register ranges."""
        ac_system = self._read_holding_registers(808, 15)  # 808..822
        battery = self._read_holding_registers(842, 2)  # 842..843
        dc_pv = self._read_holding_registers(850, 1)  # 850
        return self._decode_system_registers(
            ac_system,
            battery,
            dc_pv,
            include_ac_coupled_pv=self.config.adapter.victron.include_ac_coupled_pv,
        )

    @classmethod
    def _decode_evcs_registers(cls, registers: list[int]) -> dict[str, Optional[float]]:
        """Decode EV Charging Station registers 3818..3824.

        3818..3820 are phase powers, 3821 is total power, 3823 is charge current and
        3824 is charger status. All values used here are read-only.
        """
        if len(registers) != cls._EVCS_REGISTER_COUNT:
            raise ValueError(
                f"Expected {cls._EVCS_REGISTER_COUNT} EVCS registers, got {len(registers)}"
            )

        phase_power = [cls._decode_uint16(registers[offset]) for offset in range(3)]
        total_power = cls._decode_uint16(registers[3])
        if total_power is None:
            total_power = cls._sum_available(
                [float(value) if value is not None else None for value in phase_power],
                clamp_nonnegative=True,
            )

        current = cls._decode_uint16(registers[5])
        status = cls._decode_uint16(registers[6])
        return {
            "power_w": float(total_power) if total_power is not None else None,
            "current_a": float(current) if current is not None else None,
            "status": float(status) if status is not None else None,
        }

    def _read_evcs_snapshot(self, unit_id: int) -> dict[str, Optional[float]]:
        """Read one com.victronenergy.evcharger service from the GX Modbus gateway."""
        registers = self._read_holding_registers(
            self._EVCS_FIRST_REGISTER,
            self._EVCS_REGISTER_COUNT,
            unit_id=unit_id,
        )
        return self._decode_evcs_registers(registers)

    def _ensure_pv_measurement_key(self) -> str:
        """Register the generated Victron PV energy counter as a PV production measurement."""
        key = self.config.adapter.victron.pv_energy_key
        keys = self.config.measurement.pv_production_emr_keys
        if keys is None:
            self.config.measurement.pv_production_emr_keys = [key]
        elif key not in keys:
            self.config.measurement.pv_production_emr_keys = [*keys, key]
        return key

    def _ensure_load_forecast_measurement_key(self) -> str:
        """Select total load or EV-cleaned base load as the forecast learning source."""
        settings = self.config.adapter.victron
        desired = settings.base_load_energy_key if settings.evcs_unit_ids else settings.load_energy_key
        current = list(self.config.measurement.load_emr_keys or [])

        # The two counters are alternative representations of the same site load and must never be
        # summed together by Measurement.load_total_kwh(). Preserve unrelated load meters.
        owned = {settings.load_energy_key, settings.base_load_energy_key}
        new_keys = [key for key in current if key not in owned]
        if desired not in new_keys:
            new_keys.append(desired)
        if current != new_keys:
            self.config.measurement.load_emr_keys = new_keys
        return desired

    def _ensure_telemetry_measurement_keys(self) -> None:
        """Keep all plant-dashboard telemetry keys writable after config migrations."""
        current = list(self.config.measurement.telemetry_keys or [])
        updated = list(current)
        for key in self._TELEMETRY_KEYS:
            if key not in updated:
                updated.append(key)
        if updated != current:
            self.config.measurement.telemetry_keys = updated

    def _evcs_energy_key(self, unit_id: int) -> str:
        settings = self.config.adapter.victron
        return f"{settings.evcs_energy_key_prefix}_{unit_id}_emr"

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

    async def _store_telemetry_value(
        self, sample_time: DateTime, key: str, value: Optional[float]
    ) -> None:
        """Store one instantaneous read-only plant telemetry value when available."""
        if value is not None:
            await self.measurement.update_value(sample_time, key, float(value))

    async def _restore_integrated_energy(self, key: str) -> float:
        """Restore a locally integrated cumulative energy counter after a restart."""
        if key in self._energy_kwh_by_key:
            return self._energy_kwh_by_key[key]
        try:
            series = await self.measurement.key_to_raw_series(key=key, dropna=True)
            value = float(series.iloc[-1]) if not series.empty else 0.0
        except (KeyError, TypeError, ValueError):
            value = 0.0
        self._energy_kwh_by_key[key] = value
        return value

    def _break_energy_integration(self, key: str) -> None:
        """Prevent interpolation across an interval whose component measurement was unavailable."""
        self._last_energy_sample_time_by_key.pop(key, None)
        self._last_energy_power_w_by_key.pop(key, None)

    async def _store_integrated_energy(
        self, sample_time: DateTime, key: str, power_w: float, *, label: str
    ) -> None:
        """Integrate power into a restart-safe cumulative local energy meter [kWh]."""
        energy_kwh = await self._restore_integrated_energy(key)
        last_time = self._last_energy_sample_time_by_key.get(key)
        last_power = self._last_energy_power_w_by_key.get(key)

        if last_time is not None and last_power is not None:
            delta_seconds = (sample_time - last_time).total_seconds()
            max_gap_seconds = self.config.adapter.victron.max_integration_gap_minutes * 60.0
            if 0 < delta_seconds <= max_gap_seconds:
                average_power_w = (last_power + power_w) / 2.0
                energy_kwh += average_power_w * delta_seconds / 3_600_000.0
                self._energy_kwh_by_key[key] = energy_kwh
            elif delta_seconds > max_gap_seconds:
                logger.warning(
                    "Skipping {} energy integration over a {:.1f} minute data gap",
                    label,
                    delta_seconds / 60.0,
                )

        await self.measurement.update_value(sample_time, key, energy_kwh)
        self._last_energy_sample_time_by_key[key] = sample_time
        self._last_energy_power_w_by_key[key] = power_w

    async def _store_pv_energy(self, sample_time: DateTime, pv_power_w: float) -> None:
        key = self._ensure_pv_measurement_key()
        await self._store_integrated_energy(sample_time, key, pv_power_w, label="Victron PV")

    async def _store_site_load_energy(self, sample_time: DateTime, load_power_w: float) -> None:
        key = self.config.adapter.victron.load_energy_key
        await self._store_integrated_energy(sample_time, key, load_power_w, label="Victron site load")

    async def _store_base_load_energy(self, sample_time: DateTime, base_load_power_w: float) -> None:
        key = self.config.adapter.victron.base_load_energy_key
        await self._store_integrated_energy(sample_time, key, base_load_power_w, label="Victron base load")

    async def _update_data(self) -> None:
        """Poll the Cerbo GX during the EOS data-acquisition stage."""
        if self.ems.stage() != EnergyManagementStage.DATA_ACQUISITION:
            return

        sample_time = to_datetime(in_timezone=self.config.general.timezone)
        settings = self.config.adapter.victron
        try:
            snapshot = await asyncio.to_thread(self._read_system_snapshot)
            pv_power = snapshot["pv_power_w"]
            if pv_power is None:
                raise ValueError("Cerbo GX returned no usable PV power value")

            self.pv_power_w = float(pv_power)
            self.pv_dc_power_w = snapshot["pv_dc_power_w"]
            self.pv_ac_out_power_w = snapshot["pv_ac_out_power_w"]
            self.pv_ac_input_power_w = snapshot["pv_ac_input_power_w"]
            self.pv_ac_generator_power_w = snapshot["pv_ac_generator_power_w"]
            self.grid_power_w = snapshot["grid_power_w"]
            self.load_power_w = snapshot["load_power_w"]
            self.battery_power_w = snapshot["battery_power_w"]
            self.battery_soc_percent = snapshot["battery_soc_percent"]

            self._ensure_load_forecast_measurement_key()
            self._ensure_telemetry_measurement_keys()
            await self._store_pv_energy(sample_time, self.pv_power_w)
            if self.load_power_w is not None:
                await self._store_site_load_energy(
                    sample_time, max(0.0, float(self.load_power_w))
                )
            await self._store_battery_soc(sample_time, self.battery_soc_percent)

            await self._store_telemetry_value(
                sample_time, "victron_pv_dc_power_w", self.pv_dc_power_w
            )
            await self._store_telemetry_value(
                sample_time, "victron_pv_ac_out_power_w", self.pv_ac_out_power_w
            )
            await self._store_telemetry_value(
                sample_time, "victron_pv_total_power_w", self.pv_power_w
            )
            await self._store_telemetry_value(
                sample_time, "victron_site_load_power_w", self.load_power_w
            )
            await self._store_telemetry_value(
                sample_time, "victron_battery_power_w", self.battery_power_w
            )
            await self._store_telemetry_value(
                sample_time, "victron_grid_power_w", self.grid_power_w
            )

            evcs_power: dict[int, float] = {}
            evcs_current: dict[int, float] = {}
            evcs_status: dict[int, int] = {}
            evcs_errors: dict[int, str] = {}
            unit_ids = list(dict.fromkeys(int(value) for value in settings.evcs_unit_ids))

            for unit_id in unit_ids:
                energy_key = self._evcs_energy_key(unit_id)
                try:
                    evcs = await asyncio.to_thread(self._read_evcs_snapshot, unit_id)
                    power = evcs["power_w"]
                    if power is None:
                        raise ValueError("EVCS returned no usable /Ac/Power value")
                    power = max(0.0, float(power))
                    evcs_power[unit_id] = power
                    if evcs["current_a"] is not None:
                        evcs_current[unit_id] = float(evcs["current_a"])
                    if evcs["status"] is not None:
                        evcs_status[unit_id] = int(evcs["status"])
                    await self._store_integrated_energy(
                        sample_time,
                        energy_key,
                        power,
                        label=f"Victron EVCS unit {unit_id}",
                    )
                except Exception as exc:
                    evcs_errors[unit_id] = str(exc)
                    self._break_energy_integration(energy_key)
                    logger.warning("Victron EVCS unit {} read failed: {}", unit_id, exc)

            self.evcs_power_w = evcs_power
            self.evcs_current_a = evcs_current
            self.evcs_status = evcs_status
            self.evcs_errors = evcs_errors

            base_energy_key = settings.base_load_energy_key
            if unit_ids:
                if self.load_power_w is not None and len(evcs_power) == len(unit_ids):
                    base_load = self._calculate_base_load_power(
                        float(self.load_power_w), list(evcs_power.values())
                    )
                    self.base_load_power_w = base_load
                    self.house_non_ev_power_w = base_load
                    self.ev_total_power_w = float(sum(evcs_power.values()))
                    await self._store_base_load_energy(sample_time, base_load)
                    await self._store_telemetry_value(
                        sample_time, "victron_house_non_ev_power_w", base_load
                    )
                    await self._store_telemetry_value(
                        sample_time, "victron_ev_power_w", self.ev_total_power_w
                    )
                else:
                    # Do not bridge over intervals with an unknown EV component; otherwise an EV
                    # session could leak back into the learned household base load.
                    self.base_load_power_w = None
                    self.house_non_ev_power_w = None
                    self.ev_total_power_w = None
                    self._break_energy_integration(base_energy_key)
            else:
                self.base_load_power_w = (
                    max(0.0, float(self.load_power_w)) if self.load_power_w is not None else None
                )
                self.house_non_ev_power_w = self.base_load_power_w
                self.ev_total_power_w = 0.0
                await self._store_telemetry_value(
                    sample_time, "victron_house_non_ev_power_w", self.house_non_ev_power_w
                )
                await self._store_telemetry_value(sample_time, "victron_ev_power_w", 0.0)

            self.connected = True
            self.last_error = None
            self.update_datetime = sample_time
            ev_total = self.ev_total_power_w
            logger.info(
                "Victron GX: PV={:.0f} W (DC={}, AC-out={}), grid={} W, load={} W, "
                "house-no-EV={} W, EV={} W, battery={} W, SoC={} %",
                self.pv_power_w,
                f"{self.pv_dc_power_w:.0f}" if self.pv_dc_power_w is not None else "n/a",
                f"{self.pv_ac_out_power_w:.0f}"
                if self.pv_ac_out_power_w is not None
                else "n/a",
                f"{self.grid_power_w:.0f}" if self.grid_power_w is not None else "n/a",
                f"{self.load_power_w:.0f}" if self.load_power_w is not None else "n/a",
                f"{self.house_non_ev_power_w:.0f}"
                if self.house_non_ev_power_w is not None
                else "n/a",
                f"{ev_total:.0f}" if ev_total is not None else ("n/a" if unit_ids else "0"),
                f"{self.battery_power_w:.0f}" if self.battery_power_w is not None else "n/a",
                f"{self.battery_soc_percent:.0f}" if self.battery_soc_percent is not None else "n/a",
            )
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            logger.error(f"Victron GX update failed: {exc}")
