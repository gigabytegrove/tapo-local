"""Binary sensors for TP-Link Local."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .entity import TPLinkLocalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data

    entities: list[BinarySensorEntity] = []
    if coordinator.has_pir:
        entities.append(TPLinkMotionBinarySensor(coordinator))
    if coordinator.is_lock:
        entities.append(TPLinkLowBatteryBinarySensor(coordinator))

    async_add_entities(entities)


class TPLinkMotionBinarySensor(TPLinkLocalEntity, BinarySensorEntity):
    """Calculated live PIR motion state."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="motion", name="Motion")

    @property
    def is_on(self) -> bool:
        pir_state = self.coordinator.data.get("pir_state") if self.coordinator.data else None
        return bool(pir_state and pir_state.triggered)


class TPLinkLowBatteryBinarySensor(TPLinkLocalEntity, BinarySensorEntity):
    """DL100 low-battery warning."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="battery_low", name="Battery low")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.sysinfo.get("at_low_battery", False))

