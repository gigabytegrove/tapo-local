"""Diagnostics for TP-Link Local."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {
    "deviceId",
    "device_id",
    "mac",
    "mic_mac",
    "alias",
    "latitude_i",
    "longitude_i",
    "credentials_hash",
    "username",
    "password",
    "cookie",
    "local_seed",
    "remote_seed",
    "lmk",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return privacy-safe diagnostics."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
            "host": entry.data.get("host"),
            "model": entry.data.get("model"),
        },
        "state": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
