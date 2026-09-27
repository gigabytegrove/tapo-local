"""Sensors for TP-Link Local."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTime,
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
    """Set up sensors."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        TPLinkRssiSensor(coordinator),
        TPLinkOnTimeSensor(coordinator),
    ]

    if coordinator.has_pir:
        entities.extend(
            [
                TPLinkPirAdcSensor(coordinator),
                TPLinkPirPercentSensor(coordinator),
            ]
        )

    async_add_entities(entities)


class TPLinkRssiSensor(TPLinkLocalEntity, SensorEntity):
    """Wi-Fi RSSI."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="rssi", name="Wi-Fi signal")

    @property
    def native_value(self):
        return self.coordinator.sysinfo.get("rssi")


class TPLinkOnTimeSensor(TPLinkLocalEntity, SensorEntity):
    """Current relay on-time."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="on_time", name="On time")

    @property
    def native_value(self):
        return self.coordinator.sysinfo.get("on_time")


class TPLinkPirAdcSensor(TPLinkLocalEntity, SensorEntity):
    """Raw PIR ADC value."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="pir_adc", name="PIR ADC")

    @property
    def native_value(self):
        pir_state = self.coordinator.data.get("pir_state") if self.coordinator.data else None
        return pir_state.adc_value if pir_state else None


class TPLinkPirPercentSensor(TPLinkLocalEntity, SensorEntity):
    """Calculated PIR signal percentage."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="pir_percent", name="PIR signal")

    @property
    def native_value(self):
        pir_state = self.coordinator.data.get("pir_state") if self.coordinator.data else None
        return round(pir_state.percent, 2) if pir_state else None
