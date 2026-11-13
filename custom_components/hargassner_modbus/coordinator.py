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
    CONF_HEAT_LIMIT,
    CONF_ROOM_BOOST_MAX,
    CONF_ROOM_GAIN,
    CONF_ROOM_LOWER_MAX,
    DEFAULT_CURVE,
    DEFAULT_HEAT_LIMIT,
    DEFAULT_HK_MAX,
    DEFAULT_HK_MIN,
    DEFAULT_ROOM_BOOST_MAX,
    DEFAULT_ROOM_GAIN,
    DEFAULT_REF_ROOM,
    DEFAULT_REQUEST_MIN,
    DEFAULT_ROOM_LOWER_MAX,
    ROOM_DEADBAND,
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
        # Automatik: statt der manuellen Vorgabe den berechneten Vorlauf senden
        self.auto: dict[str, bool] = {hk: False for hk in HK_SETPOINT_REGS}
        self._unsub_write = None

    @property
    def options(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def register(self, hk: str) -> int:
        return int(self.options.get(f"{hk}_register", HK_SETPOINT_REGS[hk]))

    def limits(self, hk: str) -> tuple[int, int]:
        o = self.options
        return int(o.get(f"{hk}_min", DEFAULT_HK_MIN)), int(o.get(f"{hk}_max", DEFAULT_HK_MAX))

    def compute(self, hk: str) -> dict[str, Any] | None:
        """Vorlauf aus Heizkurve (Außentemperatur vom Kessel) plus Raumbedarf."""
        o = self.options
        data = self.data or {}
        t_out = data.get("aussen_gemittelt")
        if t_out is None:
            t_out = data.get("aussen")
        if t_out is None:
            return None
        c = {k: float(o.get(f"{hk}_{k}", v)) for k, v in DEFAULT_CURVE.items()}
        span = c["out_warm"] - c["out_cold"]
        if span == 0:
            return None
        curve = c["flow_cold"] + (t_out - c["out_cold"]) * (c["flow_warm"] - c["flow_cold"]) / span

        rooms = []
        for eid in o.get(f"{hk}_rooms", []) or []:
            st = self.hass.states.get(eid)
            if st is None or st.state in ("off", "unavailable", "unknown"):
                continue
            try:
                cur = float(st.attributes["current_temperature"])
                tgt = float(st.attributes["temperature"])
            except (KeyError, TypeError, ValueError):
                continue
            rooms.append((round(tgt - cur, 2), st.name, cur, tgt))

        gain = float(o.get(CONF_ROOM_GAIN, DEFAULT_ROOM_GAIN))
        corr = 0.0
        room = None
        reason = "Heizkurve"
        if rooms:
            diff, room, cur, tgt = max(rooms)
            if diff > ROOM_DEADBAND:
                corr = min(gain * diff, float(o.get(CONF_ROOM_BOOST_MAX, DEFAULT_ROOM_BOOST_MAX)))
                reason = f"{room} {diff:.1f} K zu kalt".replace(".", ",")
            elif diff < -ROOM_DEADBAND:
                corr = max(gain * diff, -float(o.get(CONF_ROOM_LOWER_MAX, DEFAULT_ROOM_LOWER_MAX)))
                reason = f"Alle Räume warm (am kältesten {room}, {-diff:.1f} K über Soll)".replace(".", ",")
            else:
                reason = f"Räume auf Soll (am kältesten {room})"

        # Kurve mit dem höchsten Raumsoll verschieben (wie der Heizungsmischer der Loxone):
        # Vorlauf ≈ Raumsoll + Steilheit·(Raumsoll − außen) → je K Raumsoll (1 + Steilheit) K Vorlauf
        shift = 0.0
        target_max = None
        if rooms and o.get(f"{hk}_shift", True):
            target_max = max(r[3] for r in rooms)
            slope = (c["flow_cold"] - c["flow_warm"]) / span
            shift = (1 + slope) * (target_max - float(o.get(f"{hk}_ref_room", DEFAULT_REF_ROOM)))
            if abs(shift) >= 0.5:
                reason += f"; Raumsoll {target_max:.1f} °C: {shift:+.1f} K".replace(".", ",")
        curve_shifted = curve + shift

        lo, hi = self.limits(hk)
        if t_out >= float(o.get(CONF_HEAT_LIMIT, DEFAULT_HEAT_LIMIT)):
            value = lo
            reason = "Heizgrenze erreicht"
        else:
            value = int(round(max(lo, min(hi, curve_shifted + corr))))

        # Zusatzanforderung (z. B. Handtuchheizkörper): Vorlauf mindestens X °C
        requests = []
        for eid in o.get(f"{hk}_request_entities", []) or []:
            st = self.hass.states.get(eid)
            if st is None:
                continue
            active = st.state in ("on", "heat", "open", "active")
            if not active:
                try:
                    active = float(st.state) > 0
                except ValueError:
                    active = False
            if active:
                requests.append(st.name)
        request_min = int(o.get(f"{hk}_request_min", DEFAULT_REQUEST_MIN))
        if requests and value < request_min:
            value = min(hi, request_min)
            reason = f"{', '.join(requests)} an (mind. {request_min} °C)"
        return {
            "value": value,
            "aussen": round(t_out, 1),
            "kurve": round(curve, 1),
            "verschiebung": round(shift, 1),
            "raumsoll_max": target_max,
            "korrektur": round(corr, 1),
            "raum": room,
            "grund": reason,
            "raeume": len(rooms),
            "anforderung": requests or None,
        }

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
                if v is not None and reg.limit is not None and v >= reg.limit:
                    v = None  # Fühler nicht angeschlossen
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
        if self.auto[hk]:
            calc = self.compute(hk)
            setpoint = calc["value"] if calc else None
        else:
            setpoint = self.setpoint[hk]
        if not self.write_enabled[hk] or setpoint is None:
            return
        lo, hi = self.limits(hk)
        value = int(round(max(lo, min(hi, setpoint))))
        try:
            await self.client.write_registers(self.register(hk), [value])
        except ModbusError as err:
            _LOGGER.warning("Vorlauf-Soll %s (%s °C) nicht geschrieben: %s", hk.upper(), value, err)
            self.last_write[hk] = {"ok": False, "value": value, "register": self.register(hk), "error": str(err)}
        else:
            self.last_write[hk] = {"ok": True, "value": value, "register": self.register(hk)}
        self.async_update_listeners()
