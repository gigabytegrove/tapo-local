"""Fan entities for TAPO Local."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .entity import TPLinkLocalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up fan controls exposed by python-kasa."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock or not coordinator.device.is_fan:
        async_add_entities([])
        return

    async_add_entities([TAPOLocalFan(coordinator)])


class TAPOLocalFan(TPLinkLocalEntity, FanEntity):
    """A locally controlled Kasa/Tapo fan."""

    _attr_supported_features = FanEntityFeature.SET_SPEED
    _attr_speed_count = 4
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="fan", name="Fan")

    @property
    def is_on(self) -> bool:
        value = self.coordinator.device.feature_value("fan_speed_level", 0)
        try:
            return int(value) > 0
        except (TypeError, ValueError):
            return False

    @property
    def percentage(self) -> int | None:
        value = self.coordinator.device.feature_value("fan_speed_level")
        try:
            level = int(value)
        except (TypeError, ValueError):
            return None
        if level <= 0:
            return 0
        return min(100, level * 25)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on, preserving or selecting a speed."""
        del preset_mode, kwargs
        if percentage is None:
            current = self.coordinator.device.feature_value("fan_speed_level", 0)
            try:
                level = int(current)
            except (TypeError, ValueError):
                level = 0
            if level <= 0:
                level = 1
        else:
            level = max(1, min(4, math.ceil(percentage / 25)))

        await self.coordinator.device.set_feature("fan_speed_level", level)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        del kwargs
        await self.coordinator.device.set_feature("fan_speed_level", 0)
        await self.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed using Home Assistant's 0-100 percentage model."""
        level = 0 if percentage <= 0 else max(1, min(4, math.ceil(percentage / 25)))
        await self.coordinator.device.set_feature("fan_speed_level", level)
        await self.coordinator.async_request_refresh()
