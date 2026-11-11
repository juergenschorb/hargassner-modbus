"""Sensoren: Temperaturen, Zustände, Lagerstand, Störung."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HargassnerConfigEntry
from .const import BOILER_NANO, BOILER_STATES, CONF_BOILER_TYPE, CONF_EXTRAS, HK_STATES, READ_REGISTERS, Reg
from .coordinator import HargassnerCoordinator
from .entity import HargassnerEntity

STATE_TABLES = {"hk1_zustand": HK_STATES, "hk2_zustand": HK_STATES}


async def async_setup_entry(
    hass: HomeAssistant, entry: HargassnerConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    extras = bool(coordinator.options.get(CONF_EXTRAS, False))
    entities: list[SensorEntity] = []
    for reg in READ_REGISTERS:
        if reg.extra and not extras:
            continue
        if reg.kind == "code" and reg.key in ("kesselzustand", "hk1_zustand", "hk2_zustand"):
            entities.append(HargassnerStateSensor(coordinator, reg))
            entities.append(HargassnerValueSensor(coordinator, reg, code=True))
        else:
            entities.append(HargassnerValueSensor(coordinator, reg))
    entities.append(HargassnerKeepaliveSensor(coordinator))
    entities += [HargassnerFlowCalcSensor(coordinator, hk) for hk in ("hk1", "hk2")]
    async_add_entities(entities)


class HargassnerValueSensor(HargassnerEntity, SensorEntity):
    """Ein Messwert (float32-Register)."""

    def __init__(self, coordinator: HargassnerCoordinator, reg: Reg, code: bool = False) -> None:
        super().__init__(coordinator, f"{reg.key}_code" if code else reg.key)
        self._reg = reg
        if reg.kind == "temp":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = reg.precision
        elif reg.kind == "percent":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        elif reg.kind == "number":
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        if code:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        v = (self.coordinator.data or {}).get(self._reg.key)
        if v is None:
            return None
        if self._reg.kind == "code":
            return int(round(v))
        return round(v, self._reg.precision) if self._reg.precision else int(round(v))


class HargassnerStateSensor(HargassnerEntity, SensorEntity):
    """Zustand als Text (Kessel, Heizkreise)."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: HargassnerCoordinator, reg: Reg) -> None:
        super().__init__(coordinator, reg.key)
        self._reg = reg
        self._attr_icon = "mdi:fire" if reg.key == "kesselzustand" else "mdi:radiator"

    @property
    def _table(self) -> dict[int, str]:
        if self._reg.key == "kesselzustand":
            return BOILER_STATES[self.coordinator.options.get(CONF_BOILER_TYPE, BOILER_NANO)]
        return STATE_TABLES[self._reg.key]

    @property
    def options(self) -> list[str]:
        return list(dict.fromkeys([*self._table.values(), "Unbekannt"]))

    @property
    def native_value(self):
        v = (self.coordinator.data or {}).get(self._reg.key)
        if v is None:
            return None
        return self._table.get(int(round(v)), "Unbekannt")

    @property
    def extra_state_attributes(self):
        v = (self.coordinator.data or {}).get(self._reg.key)
        return {"code": int(round(v))} if v is not None else None


class HargassnerKeepaliveSensor(HargassnerEntity, SensorEntity):
    """Lebenszeichen (Register 6499), wird alle 10 s gelesen."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator: HargassnerCoordinator) -> None:
        super().__init__(coordinator, "lebenszeichen")

    @property
    def native_value(self):
        v = (self.coordinator.data or {}).get("lebenszeichen")
        return None if v is None else round(v, 2)


class HargassnerFlowCalcSensor(HargassnerEntity, SensorEntity):
    """Berechneter Vorlauf: Heizkurve nach Außentemperatur plus Anhebung/Absenkung nach Raumbedarf."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, coordinator: HargassnerCoordinator, hk: str) -> None:
        super().__init__(coordinator, f"{hk}_vorlauf_berechnet")
        self._hk = hk

    @property
    def native_value(self):
        calc = self.coordinator.compute(self._hk)
        return calc["value"] if calc else None

    @property
    def extra_state_attributes(self):
        calc = self.coordinator.compute(self._hk)
        if not calc:
            return None
        return {k: v for k, v in calc.items() if k != "value"}
