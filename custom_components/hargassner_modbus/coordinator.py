"""Abfrage und Schreiben für den Hargassner-Kessel."""

from __future__ import annotations

from datetime import timedelta
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_EXTRAS,
    CONF_WORD_SWAP,
    DEFAULT_HK_MAX,
    DEFAULT_HK_MIN,
    DOMAIN,
    HK_SETPOINT_REGS,
    KEEPALIVE_INTERVAL,
    READ_REGISTERS,
    REG_KEEPALIVE,
    VALUES_EVERY,
    WRITE_INTERVAL,
)
from .modbus import ModbusClient, ModbusError, decode_float

_LOGGER = logging.getLogger(__name__)


class HargassnerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Liest alle 10 s das Lebenszeichen, alle 30 s die Messwerte und schreibt HK1/HK2."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ModbusClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=KEEPALIVE_INTERVAL),
            config_entry=entry,
        )
        self.client = client
        self._cycle = 0
        self._values: dict[str, Any] = {}
        # Vorgabe je Heizkreis: von Schalter und Zahl-Entität gesetzt (beide stellen ihren Zustand wieder her)
        self.write_enabled: dict[str, bool] = {hk: False for hk in HK_SETPOINT_REGS}
        self.setpoint: dict[str, float | None] = {hk: None for hk in HK_SETPOINT_REGS}
        self.last_write: dict[str, dict[str, Any]] = {hk: {} for hk in HK_SETPOINT_REGS}
        self._unsub_write = None

    @property
    def options(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def limits(self, hk: str) -> tuple[int, int]:
        o = self.options
        return int(o.get(f"{hk}_min", DEFAULT_HK_MIN)), int(o.get(f"{hk}_max", DEFAULT_HK_MAX))

    async def _async_update_data(self) -> dict[str, Any]:
        swap = bool(self.options.get(CONF_WORD_SWAP, True))
        try:
            keepalive = decode_float(await self.client.read_holding(REG_KEEPALIVE, 2), swap)
        except ModbusError as err:
            raise UpdateFailed(str(err)) from err

        if self._cycle % VALUES_EVERY == 0 or not self._values:
            extras = bool(self.options.get(CONF_EXTRAS, False))
            values: dict[str, Any] = {}
            for reg in READ_REGISTERS:
                if reg.extra and not extras:
                    continue
                try:
                    v = decode_float(await self.client.read_holding(reg.address, 2), swap)
                except ModbusError as err:
                    if not self.client.connected:
                        raise UpdateFailed(str(err)) from err
                    _LOGGER.debug("Register %s nicht lesbar: %s", reg.address, err)
                    v = None
                if v is not None and not math.isfinite(v):
                    v = None
                values[reg.key] = v
            self._values = values
        self._cycle += 1
        return {**self._values, "lebenszeichen": keepalive}

    # ---------- HK1/HK2 schreiben ----------
    @callback
    def start_writer(self) -> None:
        self._unsub_write = async_track_time_interval(
            self.hass, self._write_tick, timedelta(seconds=WRITE_INTERVAL)
        )

    @callback
    def stop_writer(self) -> None:
        if self._unsub_write:
            self._unsub_write()
            self._unsub_write = None

    async def _write_tick(self, _now=None) -> None:
        for hk in HK_SETPOINT_REGS:
            await self.async_write_hk(hk)

    async def async_write_hk(self, hk: str) -> None:
        """Vorlauf-Soll eines Heizkreises senden, aber nur wenn freigegeben."""
        setpoint = self.setpoint[hk]
        if not self.write_enabled[hk] or setpoint is None:
            return
        lo, hi = self.limits(hk)
        value = int(round(max(lo, min(hi, setpoint))))
        try:
            await self.client.write_registers(HK_SETPOINT_REGS[hk], [value])
        except ModbusError as err:
            _LOGGER.warning("Vorlauf-Soll %s (%s °C) nicht geschrieben: %s", hk.upper(), value, err)
            self.last_write[hk] = {"ok": False, "value": value, "error": str(err)}
        else:
            self.last_write[hk] = {"ok": True, "value": value}
        self.async_update_listeners()
