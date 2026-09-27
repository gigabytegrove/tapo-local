"""Select entities for TP-Link Local."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .entity import TPLinkLocalEntity

RANGE_OPTIONS = ["Far", "Mid", "Near", "Custom"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up selects."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.has_pir:
        async_add_entities([TPLinkPirRangeSelect(coordinator)])


class TPLinkPirRangeSelect(TPLinkLocalEntity, SelectEntity):
    """KS200M PIR range."""

    _attr_options = RANGE_OPTIONS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="pir_range", name="PIR range")
        self._attr_icon = "mdi:motion-sensor"

    @property
    def current_option(self) -> str | None:
        pir_state = self.coordinator.data.get("pir_state") if self.coordinator.data else None
        if not pir_state:
            return None
        if 0 <= pir_state.trigger_index < len(RANGE_OPTIONS):
            return RANGE_OPTIONS[pir_state.trigger_index]
        return None

    async def async_select_option(self, option: str) -> None:
        index = RANGE_OPTIONS.index(option)
        await self.coordinator.device.set_pir_range(index)
        await self.coordinator.async_request_refresh()
