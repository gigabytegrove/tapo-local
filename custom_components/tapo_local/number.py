"""Number entities for TP-Link Local."""

from __future__ import annotations

from enum import Enum

from kasa import Feature

from homeassistant.components.number import NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .kasa_feature_entity import TPLinkKasaFeatureEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose every python-kasa Number feature."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock:
        async_add_entities([])
        return
    entities = [
        TPLinkFeatureNumber(coordinator, feature_id)
        for feature_id, feature in coordinator.device.features.items()
        if feature.type == Feature.Type.Number
    ]
    async_add_entities(entities)


class TPLinkFeatureNumber(TPLinkKasaFeatureEntity, NumberEntity):
    """A writable numeric python-kasa feature."""

    def __init__(self, coordinator: TPLinkLocalCoordinator, feature_id: str) -> None:
        super().__init__(coordinator, feature_id)
        feature = self.feature
        if feature is not None:
            self._attr_native_min_value = feature.minimum_value
            self._attr_native_max_value = feature.maximum_value
            unit = feature.unit
            if isinstance(unit, Enum):
                unit = unit.value
            if unit is not None:
                self._attr_native_unit_of_measurement = str(unit)

    @property
    def native_value(self) -> float | None:
        value = self.feature_value
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set_feature(value)
