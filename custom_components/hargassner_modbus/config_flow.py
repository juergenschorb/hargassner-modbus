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
    DEFAULT_HK_MAX,
    DEFAULT_HK_MIN,
    DEFAULT_PORT,
    DEFAULT_UNIT,
    DOMAIN,
    REG_KEEPALIVE,
)
from .modbus import ModbusClient, ModbusError, decode_float

REG_OUTSIDE = 8
REG_BOILER = 82


def _plausible(v: float, lo: float, hi: float) -> bool:
    # falsche Wortreihenfolge ergibt meist winzige Zahlen (z. B. 2e-41) oder Unsinn
    return math.isfinite(v) and lo <= v <= hi and (v == 0 or abs(v) >= 0.01)


async def probe(host: str, port: int, unit: int) -> bool:
    """Verbindung prüfen und Wortreihenfolge der Floats erkennen.

    Gibt word_swap zurück. Außen- und Kesseltemperatur müssen in einer der beiden
    Reihenfolgen plausibel sein; passt beides (oder keins), gilt die Voreinstellung.
    """
    client = ModbusClient(host, port, unit)
    try:
        await client.read_holding(REG_KEEPALIVE, 2)
        outside = await client.read_holding(REG_OUTSIDE, 2)
        boiler = await client.read_holding(REG_BOILER, 2)
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
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            unit = int(user_input[CONF_UNIT])
            await self.async_set_unique_id(f"{host}:{port}:{unit}")
            self._abort_if_unique_id_configured()
            try:
                swap = await probe(host, port, unit)
            except ModbusError:
                errors["base"] = "cannot_connect"
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
                vol.Required(CONF_PORT, default=DEFAULT_PORT): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_UNIT, default=DEFAULT_UNIT): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=247, mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Required(CONF_BOILER_TYPE, default=BOILER_NANO): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[BOILER_NANO, BOILER_ECO], translation_key="boiler_type")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HargassnerOptionsFlow()


class HargassnerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        o = self.config_entry.options
        if user_input is not None:
            data = {
                CONF_WORD_SWAP: bool(user_input[CONF_WORD_SWAP]),
                CONF_BOILER_TYPE: user_input[CONF_BOILER_TYPE],
                CONF_HK1_MIN: int(user_input.get(CONF_HK1_MIN, o.get(CONF_HK1_MIN, DEFAULT_HK_MIN))),
                CONF_HK1_MAX: int(user_input.get(CONF_HK1_MAX, o.get(CONF_HK1_MAX, DEFAULT_HK_MAX))),
                CONF_HK2_MIN: int(user_input[CONF_HK2_MIN]),
                CONF_HK2_MAX: int(user_input[CONF_HK2_MAX]),
                CONF_EXTRAS: bool(user_input[CONF_EXTRAS]),
            }
            if data[CONF_HK1_MIN] >= data[CONF_HK1_MAX] or data[CONF_HK2_MIN] >= data[CONF_HK2_MAX]:
                errors["base"] = "min_max"
            else:
                return self.async_create_entry(data=data)
        temp = selector.NumberSelector(
            selector.NumberSelectorConfig(min=10, max=90, step=1, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_BOILER_TYPE, default=o.get(CONF_BOILER_TYPE, BOILER_NANO)): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[BOILER_NANO, BOILER_ECO], translation_key="boiler_type")
                ),
                vol.Required(CONF_HK1_MIN, default=o.get(CONF_HK1_MIN, DEFAULT_HK_MIN)): temp,
                vol.Required(CONF_HK1_MAX, default=o.get(CONF_HK1_MAX, DEFAULT_HK_MAX)): temp,
                vol.Required(CONF_HK2_MIN, default=o.get(CONF_HK2_MIN, DEFAULT_HK_MIN)): temp,
                vol.Required(CONF_HK2_MAX, default=o.get(CONF_HK2_MAX, DEFAULT_HK_MAX)): temp,
                vol.Required(CONF_EXTRAS, default=o.get(CONF_EXTRAS, False)): bool,
                vol.Required(CONF_WORD_SWAP, default=o.get(CONF_WORD_SWAP, True)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
