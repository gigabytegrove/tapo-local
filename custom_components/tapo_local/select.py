"""Select entities for TP-Link Local."""

from __future__ import annotations

from enum import Enum

from kasa import Feature

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .kasa_feature_entity import MANUAL_FEATURE_IDS, TPLinkKasaFeatureEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up choice features exposed by python-kasa."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock:
        async_add_entities([])
        return
    entities: list[SelectEntity] = []

    if coordinator.device.get_feature("pir_range"):
        entities.append(TPLinkPirRangeSelect(coordinator))

    for feature_id, feature in coordinator.device.features.items():
        if feature_id in MANUAL_FEATURE_IDS or feature.type != Feature.Type.Choice:
            continue
        entities.append(TPLinkFeatureSelect(coordinator, feature_id))

    async_add_entities(entities)


class TPLinkFeatureSelect(TPLinkKasaFeatureEntity, SelectEntity):
    """A python-kasa Choice feature."""

    @property
    def options(self) -> list[str]:
        feature = self.feature
        return list(feature.choices or []) if feature else []

    @property
    def current_option(self) -> str | None:
        value = self.feature_value
        if value is None:
            return None
        if isinstance(value, Enum):
            if value.name in self.options:
                return value.name
            value = value.value
        value = str(value)
        return value if value in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.async_set_feature(option)


class TPLinkPirRangeSelect(TPLinkFeatureSelect):
    """KS200M PIR range, preserving the existing entity id."""

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "pir_range", key="pir_range", name="PIR range")
