"""Einrichtung über die Oberfläche."""

from __future__ import annotations

import math
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    BOILER_ECO,
    BOILER_NANO,
    CONF_BOILER_TYPE,
    CONF_EXTRAS,
    CONF_HK1_MAX,
    CONF_HK1_MIN,
    CONF_HK2_MAX,
    CONF_HK2_MIN,
    CONF_UNIT,
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
    DEFAULT_REQUEST_MIN,
    DEFAULT_ROOM_LOWER_MAX,
    DEFAULT_PORT,
    DEFAULT_UNIT,
    DOMAIN,
    HK_SETPOINT_REGS,
    REG_KEEPALIVE,
)
import logging

from .modbus import (
    ModbusClient,
    ModbusConnectError,
    ModbusError,
    ModbusExceptionResponse,
    ModbusNoResponse,
    decode_float,
)

_LOGGER = logging.getLogger(__name__)

REG_OUTSIDE = 8
REG_BOILER = 82


def _plausible(v: float, lo: float, hi: float) -> bool:
    # falsche Wortreihenfolge ergibt meist winzige Zahlen (z. B. 2e-41) oder Unsinn
    return math.isfinite(v) and lo <= v <= hi and (v == 0 or abs(v) >= 0.01)


async def probe_any_unit(host: str, port: int, unit: int) -> tuple[bool, int]:
    """Wie probe; antwortet die Geräteadresse nicht, auch 1, 0 und 255 probieren."""
    try:
        return await probe(host, port, unit), unit
    except ModbusNoResponse as first:
        for other in (1, 0, 255):
            if other == unit:
                continue
            try:
                swap = await probe(host, port, other, timeout=3)
            except ModbusNoResponse:
                continue
            _LOGGER.warning("Hargassner antwortet nicht auf Geräteadresse %s, aber auf %s", unit, other)
            return swap, other
        raise first


async def probe(host: str, port: int, unit: int, timeout: float = 6) -> bool:
    """Verbindung prüfen und Wortreihenfolge der Floats erkennen.

    Gibt word_swap zurück. Außen- und Kesseltemperatur müssen in einer der beiden
    Reihenfolgen plausibel sein; passt beides (oder keins), gilt die Voreinstellung.
    """
    client = ModbusClient(host, port, unit, timeout=timeout)
    reg = REG_KEEPALIVE
    try:
        await client.read_holding(REG_KEEPALIVE, 2)
        reg = REG_OUTSIDE
        outside = await client.read_holding(REG_OUTSIDE, 2)
        reg = REG_BOILER
        boiler = await client.read_holding(REG_BOILER, 2)
    except ModbusExceptionResponse as err:
        raise ModbusExceptionResponse(f"Register {reg}: {err}", err.code) from err
    finally:
        await client.close()
    ok = {
        swap: _plausible(decode_float(outside, swap), -45, 55) and _plausible(decode_float(boiler, swap), -10, 110)
        for swap in (True, False)
    }
    if ok[True] != ok[False]:
        return ok[True]
    return True


class HargassnerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        details = ""
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            unit = int(user_input[CONF_UNIT])
            await self.async_set_unique_id(f"{host}:{port}:{unit}")
            self._abort_if_unique_id_configured()
            try:
                swap, unit = await probe_any_unit(host, port, unit)
            except ModbusConnectError as err:
                errors["base"] = "cannot_connect"
                details = str(err)
            except ModbusNoResponse as err:
                errors["base"] = "no_response"
                details = str(err)
            except ModbusExceptionResponse as err:
                errors["base"] = "modbus_exception"
                details = str(err)
            except ModbusError as err:
                errors["base"] = "no_response"
                details = str(err)
            else:
                return self.async_create_entry(
                    title="Hargassner",
                    data={CONF_HOST: host, CONF_PORT: port, CONF_UNIT: unit},
                    options={
                        CONF_WORD_SWAP: swap,
                        CONF_BOILER_TYPE: user_input[CONF_BOILER_TYPE],
                        CONF_HK1_MIN: DEFAULT_HK_MIN,
                        CONF_HK1_MAX: DEFAULT_HK_MAX,
                        CONF_HK2_MIN: DEFAULT_HK_MIN,
                        CONF_HK2_MAX: DEFAULT_HK_MAX,
                        CONF_EXTRAS: False,
                    },
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=int((user_input or {}).get(CONF_PORT, DEFAULT_PORT))): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_UNIT, default=int((user_input or {}).get(CONF_UNIT, DEFAULT_UNIT))): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=247, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_BOILER_TYPE, default=(user_input or {}).get(CONF_BOILER_TYPE, BOILER_NANO)): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[BOILER_NANO, BOILER_ECO], translation_key="boiler_type")
                ),
            }
        )
        if errors:
            _LOGGER.warning("Hargassner: Verbindungstest fehlgeschlagen: %s", details)
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors, description_placeholders={"details": details}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HargassnerOptionsFlow()


class HargassnerOptionsFlow(OptionsFlow):
    """Menü: Allgemein, Heizkreis 1, Heizkreis 2."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["general", "hk1", "hk2"])

    def _save(self, new: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **new})

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        o = self.config_entry.options
        if user_input is not None:
            return self._save(
                {
                    CONF_BOILER_TYPE: user_input[CONF_BOILER_TYPE],
                    CONF_EXTRAS: bool(user_input[CONF_EXTRAS]),
                    CONF_WORD_SWAP: bool(user_input[CONF_WORD_SWAP]),
                    CONF_HEAT_LIMIT: float(user_input[CONF_HEAT_LIMIT]),
                    CONF_ROOM_GAIN: float(user_input[CONF_ROOM_GAIN]),
                    CONF_ROOM_BOOST_MAX: float(user_input[CONF_ROOM_BOOST_MAX]),
                    CONF_ROOM_LOWER_MAX: float(user_input[CONF_ROOM_LOWER_MAX]),
                }
            )

        def num(lo, hi, step, unit):
            return selector.NumberSelector(
                selector.NumberSelectorConfig(min=lo, max=hi, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX)
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_BOILER_TYPE, default=o.get(CONF_BOILER_TYPE, BOILER_NANO)): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[BOILER_NANO, BOILER_ECO], translation_key="boiler_type")
                ),
                vol.Required(CONF_EXTRAS, default=o.get(CONF_EXTRAS, False)): bool,
                vol.Required(CONF_WORD_SWAP, default=o.get(CONF_WORD_SWAP, True)): bool,
                vol.Required(CONF_HEAT_LIMIT, default=o.get(CONF_HEAT_LIMIT, DEFAULT_HEAT_LIMIT)): num(5, 30, 0.5, "°C"),
                vol.Required(CONF_ROOM_GAIN, default=o.get(CONF_ROOM_GAIN, DEFAULT_ROOM_GAIN)): num(0, 10, 0.5, "K/K"),
                vol.Required(CONF_ROOM_BOOST_MAX, default=o.get(CONF_ROOM_BOOST_MAX, DEFAULT_ROOM_BOOST_MAX)): num(0, 30, 1, "K"),
                vol.Required(CONF_ROOM_LOWER_MAX, default=o.get(CONF_ROOM_LOWER_MAX, DEFAULT_ROOM_LOWER_MAX)): num(0, 30, 1, "K"),
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)

    async def _hk_step(self, hk: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        o = self.config_entry.options
        errors: dict[str, str] = {}
        if user_input is not None:
            new = {
                f"{hk}_min": int(user_input["min"]),
                f"{hk}_max": int(user_input["max"]),
                f"{hk}_rooms": list(user_input.get("rooms", [])),
                f"{hk}_request_entities": list(user_input.get("request_entities", [])),
                f"{hk}_request_min": int(user_input.get("request_min", o.get(f"{hk}_request_min", DEFAULT_REQUEST_MIN))),
                f"{hk}_register": int(user_input.get("register", o.get(f"{hk}_register", HK_SETPOINT_REGS[hk]))),
                **{f"{hk}_{k}": float(user_input[k]) for k in DEFAULT_CURVE},
            }
            if new[f"{hk}_min"] >= new[f"{hk}_max"]:
                errors["base"] = "min_max"
            elif new[f"{hk}_out_cold"] >= new[f"{hk}_out_warm"]:
                errors["base"] = "curve"
            else:
                return self._save(new)

        temp = selector.NumberSelector(
            selector.NumberSelectorConfig(min=10, max=90, step=1, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
        )
        outside = selector.NumberSelector(
            selector.NumberSelectorConfig(min=-30, max=30, step=1, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
        )
        schema = vol.Schema(
            {
                vol.Required("register", default=o.get(f"{hk}_register", HK_SETPOINT_REGS[hk])): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=65535, step=1, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required("min", default=o.get(f"{hk}_min", DEFAULT_HK_MIN)): temp,
                vol.Required("max", default=o.get(f"{hk}_max", DEFAULT_HK_MAX)): temp,
                vol.Optional("rooms", default=o.get(f"{hk}_rooms", [])): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate", multiple=True)
                ),
                vol.Optional("request_entities", default=o.get(f"{hk}_request_entities", [])): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["switch", "input_boolean", "binary_sensor", "light", "number", "input_number", "timer"], multiple=True
                    )
                ),
                vol.Required("request_min", default=o.get(f"{hk}_request_min", DEFAULT_REQUEST_MIN)): temp,
                vol.Required("out_cold", default=o.get(f"{hk}_out_cold", DEFAULT_CURVE["out_cold"])): outside,
                vol.Required("flow_cold", default=o.get(f"{hk}_flow_cold", DEFAULT_CURVE["flow_cold"])): temp,
                vol.Required("out_warm", default=o.get(f"{hk}_out_warm", DEFAULT_CURVE["out_warm"])): outside,
                vol.Required("flow_warm", default=o.get(f"{hk}_flow_warm", DEFAULT_CURVE["flow_warm"])): temp,
            }
        )
        return self.async_show_form(step_id=hk, data_schema=schema, errors=errors)

    async def async_step_hk1(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._hk_step("hk1", user_input)

    async def async_step_hk2(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._hk_step("hk2", user_input)
