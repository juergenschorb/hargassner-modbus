"""Freigabe: Home Assistant gibt den Vorlauf HK2 vor."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import HargassnerConfigEntry
from .entity import HargassnerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: HargassnerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([Hk2WriteSwitch(entry.runtime_data)])


class Hk2WriteSwitch(HargassnerEntity, SwitchEntity, RestoreEntity):
    """Nur wenn an, schreibt HA alle 60 s die Solltemperatur HK2 (Register 6999).

    Nach der Einrichtung aus. Nie gleichzeitig mit Loxone einschalten.
    """

    _attr_icon = "mdi:shield-lock-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hk2_schreiben")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.coordinator.hk2_write_enabled = bool(last and last.state == "on")

    @property
    def is_on(self) -> bool:
        return self.coordinator.hk2_write_enabled

    @property
    def available(self) -> bool:
        return True  # auch ohne Verbindung schaltbar

    @property
    def extra_state_attributes(self):
        lw = self.coordinator.last_write
        if not lw:
            return None
        return {"zuletzt_geschrieben": lw.get("value"), "schreiben_ok": lw.get("ok"), "fehler": lw.get("error")}

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.hk2_write_enabled = True
        self.async_write_ha_state()
        await self.coordinator.async_write_hk2()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.hk2_write_enabled = False
        self.async_write_ha_state()
