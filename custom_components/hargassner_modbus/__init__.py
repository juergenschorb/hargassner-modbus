"""Hargassner Pelletkessel über die Modbus-TCP-Schnittstelle (Loxone-Erweiterung)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_UNIT, DEFAULT_PORT, DEFAULT_UNIT
from .coordinator import HargassnerCoordinator
from .modbus import ModbusClient

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER]

type HargassnerConfigEntry = ConfigEntry[HargassnerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HargassnerConfigEntry) -> bool:
    client = ModbusClient(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.data.get(CONF_UNIT, DEFAULT_UNIT),
    )
    coordinator = HargassnerCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_writer()
    entry.async_on_unload(coordinator.stop_writer)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


# Bis 0.5.0 galten die Schreibregister aus der Anleitung V01 (HK1 6998, HK2 6999).
# Richtig sind die Adressen der Loxone-Vorlage (HK1 6999, HK2 7000).
_OLD_REGS = {"hk1": 6998, "hk2": 6999}
_NEW_REGS = {"hk1": 6999, "hk2": 7000}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        options = dict(entry.options)
        for hk, old in _OLD_REGS.items():
            if options.get(f"{hk}_register") == old:
                options[f"{hk}_register"] = _NEW_REGS[hk]
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    return True


async def _async_reload(hass: HomeAssistant, entry: HargassnerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HargassnerConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.client.close()
    return ok
