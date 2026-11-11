"""Vorgabe Vorlauf-Soll HK1/HK2 (ganze Grad, wie die Hargassner-Schnittstelle erwartet)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerConfigEntry
from .entity import HargassnerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: HargassnerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([HkSetpointNumber(entry.runtime_data, hk) for hk in ("hk1", "hk2")])


class HkSetpointNumber(HargassnerEntity, RestoreNumber):
    """Diesen Wert schickt HA an den Kessel, wenn „HK1/HK2 vorgeben“ an ist.

    Lässt sich von Automationen setzen (number.set_value), z. B. später aus einer Heizkurve.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, coordinator, hk: str) -> None:
        super().__init__(coordinator, f"{hk}_vorlauf_vorgabe")
        self._hk = hk
        lo, hi = coordinator.limits(hk)
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value is not None:
            self.coordinator.setpoint[self._hk] = float(last.native_value)
        elif (state := await self.async_get_last_state()) is not None:
            try:
                self.coordinator.setpoint[self._hk] = float(state.state)
            except ValueError:
                pass

    @property
    def native_value(self):
        return self.coordinator.setpoint[self._hk]

    @property
    def available(self) -> bool:
        return True

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.setpoint[self._hk] = float(round(value))
        self.async_write_ha_state()
        await self.coordinator.async_write_hk(self._hk)
