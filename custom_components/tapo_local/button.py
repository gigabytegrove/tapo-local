"""Button entities for TP-Link Local."""

from __future__ import annotations

from kasa import Feature

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .kasa_feature_entity import TPLinkKasaFeatureEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose every python-kasa Action feature."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock:
        async_add_entities([])
        return
    entities = [
        TPLinkFeatureButton(coordinator, feature_id)
        for feature_id, feature in coordinator.device.features.items()
        if feature.type == Feature.Type.Action
    ]
    for child in coordinator.device.children:
        entities.extend(
            TPLinkFeatureButton(coordinator, feature_id, target=child)
            for feature_id, feature in child.features.items()
            if feature.type == Feature.Type.Action
        )
    async_add_entities(entities)


class TPLinkFeatureButton(TPLinkKasaFeatureEntity, ButtonEntity):
    """A python-kasa action exposed as a Home Assistant button."""

    def __init__(
        self,
        coordinator: TPLinkLocalCoordinator,
        feature_id: str,
        *,
        target=None,
    ) -> None:
        super().__init__(coordinator, feature_id, target=target)

    async def async_press(self) -> None:
        await self.async_set_feature(None)
