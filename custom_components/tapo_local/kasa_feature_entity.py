"""Helpers for exposing python-kasa Feature objects as Home Assistant entities."""

from __future__ import annotations

from enum import Enum
from typing import Any

from kasa import Feature

from homeassistant.const import EntityCategory

from .coordinator import TPLinkLocalCoordinator
from .entity import TPLinkLocalEntity


MANUAL_FEATURE_IDS = {
    "state",
    "led",
    "pir_enabled",
    "pir_range",
    "pir_triggered",
    "pir_adc_value",
    "pir_percent",
    "rssi",
}


def feature_category(feature: Feature) -> EntityCategory | None:
    """Map python-kasa's category hints to Home Assistant."""
    if feature.category == Feature.Category.Config:
        return EntityCategory.CONFIG
    if feature.category in (Feature.Category.Info, Feature.Category.Debug):
        return EntityCategory.DIAGNOSTIC
    return None


def feature_display_value(value: Any) -> Any:
    """Convert python-kasa values to Home Assistant friendly scalars."""
    if isinstance(value, Enum):
        return value.value if isinstance(value.value, (str, int, float, bool)) else value.name
    return value


class TPLinkKasaFeatureEntity(TPLinkLocalEntity):
    """Base entity backed directly by one python-kasa Feature."""

    def __init__(
        self,
        coordinator: TPLinkLocalCoordinator,
        feature_id: str,
        *,
        key: str | None = None,
        name: str | None | object = ...,
    ) -> None:
        feature = coordinator.device.get_feature(feature_id)
        if feature is None:
            raise ValueError(f"Missing python-kasa feature: {feature_id}")

        resolved_name = feature.name if name is ... else name
        super().__init__(
            coordinator,
            key=key or f"kasa_{feature_id}",
            name=resolved_name,
        )
        self.feature_id = feature_id
        self._attr_icon = feature.icon
        self._attr_entity_category = feature_category(feature)
        if feature.category == Feature.Category.Debug:
            self._attr_entity_registry_enabled_default = False

    @property
    def feature(self) -> Feature | None:
        """Return the live python-kasa feature object."""
        return self.coordinator.device.get_feature(self.feature_id)

    @property
    def feature_value(self) -> Any:
        """Return the latest cached feature value."""
        return self.coordinator.device.feature_value(self.feature_id)

    async def async_set_feature(self, value: Any = None) -> None:
        """Write a feature and refresh the coordinator."""
        await self.coordinator.device.set_feature(self.feature_id, value)
        await self.coordinator.async_request_refresh()
