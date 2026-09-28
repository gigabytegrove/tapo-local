"""Switch entities for TP-Link Local."""

from __future__ import annotations

from kasa import Feature

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .kasa_feature_entity import MANUAL_FEATURE_IDS, TPLinkKasaFeatureEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch features exposed by python-kasa."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []

    if coordinator.device.get_feature("state"):
        entities.append(TPLinkRelaySwitch(coordinator))
    if coordinator.device.get_feature("led"):
        entities.append(TPLinkLedSwitch(coordinator))
    if coordinator.device.get_feature("pir_enabled"):
        entities.append(TPLinkPirEnabledSwitch(coordinator))

    for feature_id, feature in coordinator.device.features.items():
        if feature_id in MANUAL_FEATURE_IDS or feature.type != Feature.Type.Switch:
            continue
        entities.append(TPLinkFeatureSwitch(coordinator, feature_id))

    async_add_entities(entities)


class _BaseFeatureSwitch(TPLinkKasaFeatureEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return bool(self.feature_value)

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_set_feature(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_set_feature(False)


class TPLinkRelaySwitch(_BaseFeatureSwitch):
    """Main relay, preserving the existing TP-Link Local entity id."""

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "state", key="relay", name=None)
        self._attr_icon = "mdi:light-switch"


class TPLinkLedSwitch(_BaseFeatureSwitch):
    """Status LED, preserving the existing entity id."""

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "led", key="led", name="Status LED")


class TPLinkPirEnabledSwitch(_BaseFeatureSwitch):
    """PIR enable switch, preserving the existing entity id."""

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "pir_enabled", key="pir_enabled", name="PIR")


class TPLinkFeatureSwitch(_BaseFeatureSwitch):
    """Any additional writable boolean feature provided by python-kasa."""

    def __init__(self, coordinator: TPLinkLocalCoordinator, feature_id: str) -> None:
        super().__init__(coordinator, feature_id)
