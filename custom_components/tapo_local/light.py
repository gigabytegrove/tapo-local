"""Light entities for TP-Link Local."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
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
    """Set up lights and dimmers exposed by python-kasa."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock:
        async_add_entities([])
        return

    if coordinator.device.is_light:
        async_add_entities([TPLinkKasaLight(coordinator)])
    else:
        async_add_entities([])


class TPLinkKasaLight(TPLinkLocalEntity, LightEntity):
    """A Kasa/Tapo bulb, light strip, or dimmer."""

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="light", name=None)
        self._attr_icon = "mdi:lightbulb"

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        modes: set[ColorMode] = set()
        device = self.coordinator.device

        if device.get_feature("hsv") is not None:
            modes.add(ColorMode.HS)
        if device.get_feature("color_temperature") is not None:
            modes.add(ColorMode.COLOR_TEMP)
        if not modes and device.get_feature("brightness") is not None:
            modes.add(ColorMode.BRIGHTNESS)
        if not modes:
            modes.add(ColorMode.ONOFF)

        return modes

    @property
    def color_mode(self) -> ColorMode:
        device = self.coordinator.device
        hsv = device.feature_value("hsv")
        color_temp = device.feature_value("color_temperature")

        if ColorMode.HS in self.supported_color_modes and hsv is not None:
            try:
                if float(hsv[1]) > 0:
                    return ColorMode.HS
            except (IndexError, TypeError, ValueError):
                pass

        if (
            ColorMode.COLOR_TEMP in self.supported_color_modes
            and isinstance(color_temp, (int, float))
            and color_temp > 0
        ):
            return ColorMode.COLOR_TEMP

        if ColorMode.HS in self.supported_color_modes:
            return ColorMode.HS
        if ColorMode.COLOR_TEMP in self.supported_color_modes:
            return ColorMode.COLOR_TEMP
        if ColorMode.BRIGHTNESS in self.supported_color_modes:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.device.feature_value("state")
        return bool(state) if state is not None else None

    @property
    def brightness(self) -> int | None:
        value = self.coordinator.device.feature_value("brightness")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return max(0, min(255, round(float(value) * 255 / 100)))

    @property
    def hs_color(self) -> tuple[float, float] | None:
        value = self.coordinator.device.feature_value("hsv")
        if value is None:
            return None
        try:
            return (float(value[0]), float(value[1]))
        except (IndexError, TypeError, ValueError):
            return None

    @property
    def color_temp_kelvin(self) -> int | None:
        value = self.coordinator.device.feature_value("color_temperature")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return int(value) if value > 0 else None

    @property
    def min_color_temp_kelvin(self) -> int | None:
        feature = self.coordinator.device.get_feature("color_temperature")
        if feature is None:
            return None
        return int(feature.minimum_value)

    @property
    def max_color_temp_kelvin(self) -> int | None:
        feature = self.coordinator.device.get_feature("color_temperature")
        if feature is None:
            return None
        return int(feature.maximum_value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        brightness_pct = None
        if brightness is not None:
            brightness_pct = max(
                1,
                min(100, round(int(brightness) * 100 / 255)),
            )

        hs_color = kwargs.get(ATTR_HS_COLOR)
        hue = saturation = None
        if hs_color is not None:
            hue = round(float(hs_color[0]))
            saturation = round(float(hs_color[1]))

        color_temp = kwargs.get(ATTR_COLOR_TEMP_KELVIN)

        transition = kwargs.get(ATTR_TRANSITION)
        transition_ms = (
            max(0, round(float(transition) * 1000))
            if transition is not None
            else None
        )

        await self.coordinator.device.set_light_state(
            on=True,
            brightness=brightness_pct,
            hue=hue,
            saturation=saturation,
            color_temp=int(color_temp) if color_temp is not None else None,
            transition=transition_ms,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        transition = kwargs.get(ATTR_TRANSITION)
        transition_ms = (
            max(0, round(float(transition) * 1000))
            if transition is not None
            else None
        )
        await self.coordinator.device.set_light_state(
            on=False,
            transition=transition_ms,
        )
        await self.coordinator.async_request_refresh()
