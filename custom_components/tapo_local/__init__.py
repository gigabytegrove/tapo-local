"""TP-Link Local Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .dependency import TPLinkLocalDependencyError, async_ensure_kasa

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TP-Link Local from a config entry."""
    try:
        await async_ensure_kasa(hass)
    except TPLinkLocalDependencyError as exc:
        raise ConfigEntryNotReady(str(exc)) from exc

    # Import the python-kasa-backed runtime only after dependency preflight.
    from .coordinator import TPLinkLocalCoordinator
    from .kasa_backend import KasaLocalDevice

    device = KasaLocalDevice(entry.data[CONF_HOST])
    coordinator = TPLinkLocalCoordinator(hass, entry, device)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    entry.async_on_unload(device.async_disconnect)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
