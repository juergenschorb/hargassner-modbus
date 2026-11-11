"""Schlanker Modbus-TCP-Client für den Hargassner-Kessel.

Nur das, was die Hargassner-Loxone-Schnittstelle braucht:
FC3 (Read Holding Registers) und FC16 (Preset Multiple Registers).
Eigene Umsetzung statt pymodbus, damit es keine Versionskonflikte mit
der Modbus-Integration von Home Assistant gibt.
"""

from __future__ import annotations

import asyncio
import struct


class ModbusError(Exception):
    """Fehler bei der Modbus-Kommunikation."""


class ModbusConnectError(ModbusError):
    """TCP-Verbindung kommt nicht zustande (falsche IP/Port, Proxy läuft nicht)."""


class ModbusNoResponse(ModbusError):
    """Verbunden, aber keine Antwort (z. B. falsche Geräteadresse, Proxy erreicht Kessel nicht)."""


class ModbusExceptionResponse(ModbusError):
    """Kessel antwortet mit einem Modbus-Fehlercode."""

    def __init__(self, msg: str, code: int) -> None:
        super().__init__(msg)
        self.code = code


class ModbusClient:
    """Modbus-TCP-Client mit automatischem Neuverbinden."""

    def __init__(self, host: str, port: int, unit: int, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.unit = unit
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._tid = 0

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def _connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, asyncio.TimeoutError) as err:
            self._reader = self._writer = None
            raise ModbusConnectError(f"Keine Verbindung zu {self.host}:{self.port}: {err}") from err

    async def close(self) -> None:
        writer = self._writer
        self._reader = self._writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _request(self, pdu: bytes) -> bytes:
        """Eine Anfrage senden und das Antwort-PDU (ohne MBAP-Kopf) zurückgeben."""
        async with self._lock:
            for attempt in (1, 2):
                if not self.connected:
                    await self._connect()
                self._tid = (self._tid + 1) % 0x10000
                tid = self._tid
                frame = struct.pack(">HHHB", tid, 0, len(pdu) + 1, self.unit) + pdu
                try:
                    assert self._writer is not None and self._reader is not None
                    self._writer.write(frame)
                    await self._writer.drain()
                    while True:
                        head = await asyncio.wait_for(self._reader.readexactly(7), self.timeout)
                        r_tid, _proto, length, _unit = struct.unpack(">HHHB", head)
                        body = await asyncio.wait_for(self._reader.readexactly(length - 1), self.timeout)
                        if r_tid == tid:
                            break  # alte Antworten (nach Timeout) überspringen
                except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as err:
                    await self.close()
                    if attempt == 2:
                        raise ModbusNoResponse(f"Verbunden mit {self.host}:{self.port}, aber keine Antwort: {err!r}") from err
                    continue
                if body[0] & 0x80:
                    raise ModbusExceptionResponse(
                        f"Kessel meldet Modbus-Fehler {body[1]} (Funktion {body[0] & 0x7F})", body[1]
                    )
                return body
        raise ModbusError("Keine Antwort vom Kessel")  # pragma: no cover

    async def read_holding(self, address: int, count: int) -> list[int]:
        """FC3: Holding-Register lesen."""
        body = await self._request(struct.pack(">BHH", 3, address, count))
        if body[0] != 3 or body[1] != count * 2:
            raise ModbusError(f"Unerwartete Antwort beim Lesen von Register {address}")
        return list(struct.unpack(f">{count}H", body[2 : 2 + count * 2]))

    async def write_registers(self, address: int, values: list[int]) -> None:
        """FC16: mehrere Register schreiben (so schreibt auch Loxone)."""
        count = len(values)
        pdu = struct.pack(f">BHHB{count}H", 16, address, count, count * 2, *values)
        body = await self._request(pdu)
        if body[0] != 16:
            raise ModbusError(f"Unerwartete Antwort beim Schreiben von Register {address}")


def decode_float(regs: list[int], word_swap: bool) -> float:
    """Zwei Register als 32-Bit-Float lesen."""
    hi, lo = (regs[1], regs[0]) if word_swap else (regs[0], regs[1])
    return struct.unpack(">f", struct.pack(">HH", hi, lo))[0]
