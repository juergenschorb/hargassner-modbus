"""Freigabe: Home Assistant gibt den Vorlauf HK1/HK2 vor."""

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
    c = entry.runtime_data
    async_add_entities(
        [HkWriteSwitch(c, hk) for hk in ("hk1", "hk2")] + [HkAutoSwitch(c, hk) for hk in ("hk1", "hk2")]
    )


class HkWriteSwitch(HargassnerEntity, SwitchEntity, RestoreEntity):
    """Nur wenn an, schreibt HA alle 60 s die Solltemperatur des Heizkreises (HK1 6998, HK2 6999).

    Nach der Einrichtung aus. Nie gleichzeitig mit Loxone einschalten, und nur für
    einen Heizkreis, der am Kessel auf „Loxone“ steht.
    """

    _attr_icon = "mdi:shield-lock-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, hk: str) -> None:
        super().__init__(coordinator, f"{hk}_schreiben")
        self._hk = hk

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.coordinator.write_enabled[self._hk] = bool(last and last.state == "on")

    @property
    def is_on(self) -> bool:
        return self.coordinator.write_enabled[self._hk]

    @property
    def available(self) -> bool:
        return True  # auch ohne Verbindung schaltbar

    @property
    def extra_state_attributes(self):
        lw = self.coordinator.last_write[self._hk]
        attrs = {"register": self.coordinator.register(self._hk)}
        if lw:
            attrs |= {"zuletzt_geschrieben": lw.get("value"), "schreiben_ok": lw.get("ok"), "fehler": lw.get("error")}
        return attrs

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.write_enabled[self._hk] = True
        self.async_write_ha_state()
        await self.coordinator.async_write_hk(self._hk)

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.write_enabled[self._hk] = False
        self.async_write_ha_state()


class HkAutoSwitch(HargassnerEntity, SwitchEntity, RestoreEntity):
    """An: berechneten Vorlauf (Heizkurve + Raumbedarf) senden. Aus: manuelle Vorgabe.

    Geschrieben wird nur, wenn zusätzlich „HKx vorgeben“ an ist.
    """

    _attr_icon = "mdi:auto-mode"

    def __init__(self, coordinator, hk: str) -> None:
        super().__init__(coordinator, f"{hk}_automatik")
        self._hk = hk

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.coordinator.auto[self._hk] = bool(last and last.state == "on")

    @property
    def is_on(self) -> bool:
        return self.coordinator.auto[self._hk]

    @property
    def available(self) -> bool:
        return True

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.auto[self._hk] = True
        self.async_write_ha_state()
        await self.coordinator.async_write_hk(self._hk)

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.auto[self._hk] = False
        self.async_write_ha_state()
        await self.coordinator.async_write_hk(self._hk)
