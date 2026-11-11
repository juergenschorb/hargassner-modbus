"""Gemeinsame Basis der Hargassner-Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BOILER_TYPE, BOILER_NANO, DOMAIN
from .coordinator import HargassnerCoordinator


class HargassnerEntity(CoordinatorEntity[HargassnerCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HargassnerCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        model = "Nano-PK" if coordinator.options.get(CONF_BOILER_TYPE, BOILER_NANO) == BOILER_NANO else "Eco-PK"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Hargassner",
            model=model,
            name="Hargassner",
            configuration_url=None,
        )
