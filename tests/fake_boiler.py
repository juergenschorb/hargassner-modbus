"""Nachgebauter Hargassner-Kessel (Modbus-TCP-Server) für Tests."""

from __future__ import annotations

import asyncio
import struct


def float_regs(v: float, word_swap: bool = True) -> list[int]:
    hi, lo = struct.unpack(">HH", struct.pack(">f", v))
    return [lo, hi] if word_swap else [hi, lo]


class FakeBoiler:
    def __init__(self, values: dict[int, float], word_swap: bool = True, unit: int = 1) -> None:
        self.regs: dict[int, int] = {}
        self.word_swap = word_swap
        self.unit = unit
        self.writes: list[tuple[int, list[int]]] = []
        self.reads: list[int] = []
        self.server: asyncio.base_events.Server | None = None
        self._conns: set[asyncio.StreamWriter] = set()
        for addr, v in values.items():
            self.set(addr, v)

    def set(self, addr: int, v: float) -> None:
        a, b = float_regs(v, self.word_swap)
        self.regs[addr], self.regs[addr + 1] = a, b

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            for w in list(self._conns):
                w.close()
            await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._conns.add(writer)
        try:
            while True:
                head = await reader.readexactly(7)
                tid, _p, length, unit = struct.unpack(">HHHB", head)
                pdu = await reader.readexactly(length - 1)
                fc = pdu[0]
                if unit != self.unit:
                    continue  # falsche Geräteadresse: keine Antwort
                if fc == 3:
                    addr, count = struct.unpack(">HH", pdu[1:5])
                    self.reads.append(addr)
                    if any(a not in self.regs for a in range(addr, addr + count)):
                        resp = bytes([0x83, 2])
                    else:
                        vals = [self.regs[a] for a in range(addr, addr + count)]
                        resp = struct.pack(f">BB{count}H", 3, count * 2, *vals)
                elif fc == 16:
                    addr, count, _n = struct.unpack(">HHB", pdu[1:6])
                    vals = list(struct.unpack(f">{count}H", pdu[6 : 6 + count * 2]))
                    self.writes.append((addr, vals))
                    for i, v in enumerate(vals):
                        self.regs[addr + i] = v
                    resp = struct.pack(">BHH", 16, addr, count)
                else:
                    resp = bytes([fc | 0x80, 1])
                writer.write(struct.pack(">HHHB", tid, 0, len(resp) + 1, unit) + resp)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._conns.discard(writer)
            writer.close()


BOILER_VALUES = {
    6499: 1.0, 8: 4.5, 6: 6.0, 82: 71.5, 84: 72.0, 86: 7.0, 88: 63.0, 126: 128.0, 130: 52.3,
    144: 41.2, 146: 42.0, 178: 1.0, 148: 38.4, 150: 39.0, 180: 9.0, 220: 2350.0, 222: 0.0,
}
