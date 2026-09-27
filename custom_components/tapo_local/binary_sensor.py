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
    if coordinator.has_pir:
        async_add_entities([TPLinkMotionBinarySensor(coordinator)])


class TPLinkMotionBinarySensor(TPLinkLocalEntity, BinarySensorEntity):
    """Calculated live PIR motion state."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="motion", name="Motion")

    @property
    def is_on(self) -> bool:
        pir_state = self.coordinator.data.get("pir_state") if self.coordinator.data else None
        return bool(pir_state and pir_state.triggered)
