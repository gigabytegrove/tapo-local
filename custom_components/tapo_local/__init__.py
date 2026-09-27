"""TP-Link Local Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SESSION,
    CONF_DEVICE_ID,
    CONF_TERMINAL_UUID,
    CONF_TRANSPORT,
    TRANSPORT_DLKLAP,
)
from .coordinator import TPLinkLocalCoordinator
from .dlklap import Dl100Device
from .protocol import TPLinkLocalDevice

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LOCK,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TP-Link Local from a config entry."""
    if entry.data.get(CONF_TRANSPORT) == TRANSPORT_DLKLAP:
        device = Dl100Device(
            entry.data[CONF_HOST],
            device_id=entry.data[CONF_DEVICE_ID],
            terminal_uuid=entry.data.get(CONF_TERMINAL_UUID),
            session_state=entry.data.get(CONF_SESSION),
        )
    else:
        device = TPLinkLocalDevice(entry.data[CONF_HOST])

    coordinator = TPLinkLocalCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
