"""Data coordinator for TP-Link Local."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_POLL_INTERVAL,
    CONF_TRANSPORT,
    DEFAULT_LOCK_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    TRANSPORT_DLKLAP,
)
from .errors import TPLinkLocalRuntimeError

_LOGGER = logging.getLogger(__name__)


class TPLinkLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a device through its deterministic local backend."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: Any,
    ) -> None:
        self.entry = entry
        self.device = device
        self.sysinfo: dict[str, Any] = {}
        self.model = str(entry.data.get("model", "Unknown"))
        self.is_lock = entry.data.get(CONF_TRANSPORT) == TRANSPORT_DLKLAP
        self.has_pir = False

        default_interval = (
            DEFAULT_LOCK_POLL_INTERVAL if self.is_lock else DEFAULT_POLL_INTERVAL
        )
        poll_interval = int(
            entry.options.get(CONF_POLL_INTERVAL, default_interval)
        )

        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"TP-Link Local {entry.title}",
            config_entry=entry,
            update_interval=timedelta(seconds=poll_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.device.get_state()
        except TPLinkLocalRuntimeError as exc:
            raise UpdateFailed(str(exc)) from exc

        self.sysinfo = data["sysinfo"]
        current_model = self.sysinfo.get("model")
        if current_model:
            self.model = str(current_model)

        self.has_pir = (
            False
            if self.is_lock
            else bool(getattr(self.device, "has_pir", False))
        )
        return data
