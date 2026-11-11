"""Störung und Restwärme als Ja/Nein."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerConfigEntry
from .entity import HargassnerEntity

RESTWAERME = 9


async def async_setup_entry(
    hass: HomeAssistant, entry: HargassnerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities([StoerungSensor(c), RestwaermeSensor(c, "hk1"), RestwaermeSensor(c, "hk2")])


class StoerungSensor(HargassnerEntity, BinarySensorEntity):
    """An, wenn der Kessel eine Störungsnummer ungleich 0 meldet."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "stoerung_aktiv")

    @property
    def is_on(self):
        v = (self.coordinator.data or {}).get("stoerung")
        return None if v is None else int(round(v)) != 0

    @property
    def extra_state_attributes(self):
        v = (self.coordinator.data or {}).get("stoerung")
        return {"stoerungsnummer": int(round(v))} if v is not None else None


class RestwaermeSensor(HargassnerEntity, BinarySensorEntity):
    """An, wenn der Heizkreis auf Restwärme steht (Heizkörperventile offen lassen)."""

    _attr_icon = "mdi:heat-wave"

    def __init__(self, coordinator, hk: str) -> None:
        super().__init__(coordinator, f"{hk}_restwaerme")
        self._hk = hk

    @property
    def is_on(self):
        v = (self.coordinator.data or {}).get(f"{self._hk}_zustand")
        return None if v is None else int(round(v)) == RESTWAERME
