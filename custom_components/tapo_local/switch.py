"""Switch entities for TP-Link Local."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .entity import TPLinkLocalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up local switch entities."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock:
        return

    entities: list[SwitchEntity] = [
        TPLinkRelaySwitch(coordinator),
        TPLinkLedSwitch(coordinator),
    ]

    if coordinator.has_pir:
        entities.append(TPLinkPirEnabledSwitch(coordinator))

    async_add_entities(entities)


class TPLinkRelaySwitch(TPLinkLocalEntity, SwitchEntity):
    """Main relay."""

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="relay", name=None)
        self._attr_icon = "mdi:light-switch"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.sysinfo.get("relay_state", 0))

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.device.set_relay(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.device.set_relay(False)
        await self.coordinator.async_request_refresh()


class TPLinkLedSwitch(TPLinkLocalEntity, SwitchEntity):
    """Status LED."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="led", name="Status LED")
        self._attr_icon = "mdi:led-on"

    @property
    def is_on(self) -> bool:
        return not bool(self.coordinator.sysinfo.get("led_off", 0))

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.device.set_led(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.device.set_led(False)
        await self.coordinator.async_request_refresh()


class TPLinkPirEnabledSwitch(TPLinkLocalEntity, SwitchEntity):
    """KS200M PIR enable switch."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="pir_enabled", name="PIR")
        self._attr_icon = "mdi:motion-sensor"

    @property
    def is_on(self) -> bool:
        pir_state = self.coordinator.data.get("pir_state") if self.coordinator.data else None
        return bool(pir_state and pir_state.enabled)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.device.set_pir_enabled(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.device.set_pir_enabled(False)
        await self.coordinator.async_request_refresh()
