"""Sensor entities for TP-Link Local."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from kasa import Feature

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
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
from .kasa_feature_entity import MANUAL_FEATURE_IDS, TPLinkKasaFeatureEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for the selected local backend."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    if coordinator.is_lock:
        entities.append(TPLinkDL100BatterySensor(coordinator))
        if coordinator.sysinfo.get("rssi") is not None:
            entities.append(TPLinkDL100RssiSensor(coordinator))
        async_add_entities(entities)
        return

    if coordinator.device.get_feature("rssi"):
        entities.append(TPLinkRssiSensor(coordinator))

    if "on_time" in coordinator.sysinfo:
        entities.append(TPLinkOnTimeSensor(coordinator))

    if coordinator.device.get_feature("pir_adc_value"):
        entities.append(TPLinkPirAdcSensor(coordinator))
    if coordinator.device.get_feature("pir_percent"):
        entities.append(TPLinkPirPercentSensor(coordinator))

    for feature_id, feature in coordinator.device.features.items():
        if feature_id in MANUAL_FEATURE_IDS or feature.type != Feature.Type.Sensor:
            continue
        value = coordinator.device.feature_value(feature_id)
        if isinstance(value, bool):
            continue
        entities.append(TPLinkFeatureSensor(coordinator, feature_id))

    for child in coordinator.device.children:
        for feature_id, feature in child.features.items():
            if feature.type != Feature.Type.Sensor:
                continue
            value = child.feature_value(feature_id)
            if isinstance(value, bool):
                continue
            entities.append(
                TPLinkFeatureSensor(coordinator, feature_id, target=child)
            )

    async_add_entities(entities)


class TPLinkDL100BatterySensor(TPLinkLocalEntity, SensorEntity):
    """DL100 battery level."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="battery", name="Battery")

    @property
    def native_value(self):
        info = self.coordinator.sysinfo
        for key in ("battery_percentage", "battery_percent", "battery"):
            value = info.get(key)
            if value is not None:
                return value
        return None


class TPLinkDL100RssiSensor(TPLinkLocalEntity, SensorEntity):
    """DL100 Wi-Fi RSSI when supplied by the lock."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="rssi", name="Wi-Fi signal")

    @property
    def native_value(self):
        return self.coordinator.sysinfo.get("rssi")


class TPLinkRssiSensor(TPLinkKasaFeatureEntity, SensorEntity):
    """Wi-Fi RSSI from python-kasa."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "rssi", key="rssi", name="Wi-Fi signal")

    @property
    def native_value(self):
        return self.feature_value


class TPLinkOnTimeSensor(TPLinkLocalEntity, SensorEntity):
    """Current relay on-time from the raw device sysinfo."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="on_time", name="On time")

    @property
    def native_value(self):
        return self.coordinator.sysinfo.get("on_time")


class TPLinkPirAdcSensor(TPLinkKasaFeatureEntity, SensorEntity):
    """Raw PIR ADC value."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "pir_adc_value", key="pir_adc", name="PIR ADC")

    @property
    def native_value(self):
        return self.feature_value


class TPLinkPirPercentSensor(TPLinkKasaFeatureEntity, SensorEntity):
    """Calculated PIR signal percentage."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, "pir_percent", key="pir_percent", name="PIR signal")

    @property
    def native_value(self):
        value = self.feature_value
        return round(float(value), 2) if value is not None else None


class TPLinkFeatureSensor(TPLinkKasaFeatureEntity, SensorEntity):
    """Any additional read-only scalar feature provided by python-kasa."""

    def __init__(
        self,
        coordinator: TPLinkLocalCoordinator,
        feature_id: str,
        *,
        target=None,
    ) -> None:
        super().__init__(coordinator, feature_id, target=target)
        feature = self.feature
        if feature is None:
            return

        unit = feature.unit
        if isinstance(unit, Enum):
            unit = unit.value
        if unit is not None:
            self._attr_native_unit_of_measurement = str(unit)

        value = self.feature_value
        if feature_id == "battery_level":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = PERCENTAGE
        elif feature_id == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        elif feature_id == "humidity":
            self._attr_device_class = SensorDeviceClass.HUMIDITY
            self._attr_native_unit_of_measurement = PERCENTAGE
        elif isinstance(value, datetime):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif isinstance(value, timedelta):
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        value = self.feature_value
        if isinstance(value, Enum):
            return value.value if isinstance(value.value, (str, int, float, bool)) else value.name
        if isinstance(value, timedelta):
            return value.total_seconds()
        if isinstance(value, (str, int, float, date, datetime)) or value is None:
            return value
        return str(value)
