"""Binary sensors for TP-Link Local."""

from __future__ import annotations

from kasa import Feature

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .kasa_feature_entity import MANUAL_FEATURE_IDS, TPLinkKasaFeatureEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up boolean read-only python-kasa features."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []

    if coordinator.device.get_feature("pir_triggered"):
        entities.append(TPLinkMotionBinarySensor(coordinator))

    for feature_id, feature in coordinator.device.features.items():
        if feature_id in MANUAL_FEATURE_IDS:
            continue
        value = coordinator.device.feature_value(feature_id)
        if feature.type == Feature.Type.BinarySensor or (
            feature.type == Feature.Type.Sensor and isinstance(value, bool)
        ):
            entities.append(TPLinkFeatureBinarySensor(coordinator, feature_id))

    async_add_entities(entities)


class TPLinkMotionBinarySensor(TPLinkKasaFeatureEntity, BinarySensorEntity):
    """Calculated live PIR motion state from python-kasa."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "pir_triggered", key="motion", name="Motion")

    @property
    def is_on(self) -> bool:
        return bool(self.feature_value)


class TPLinkFeatureBinarySensor(TPLinkKasaFeatureEntity, BinarySensorEntity):
    """Any additional boolean read-only feature provided by python-kasa."""

    @property
    def is_on(self) -> bool:
        return bool(self.feature_value)
