"""Data coordinator for TP-Link Local."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
from .kasa_backend import KasaLocalDevice, TPLinkLocalBackendError

_LOGGER = logging.getLogger(__name__)


class TPLinkLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a device through the deterministic python-kasa backend."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: KasaLocalDevice,
    ) -> None:
        self.entry = entry
        self.device = device
        self.sysinfo: dict[str, Any] = {}
        self.model = str(entry.data.get("model", "Unknown"))
        self.has_pir = False

        poll_interval = int(
            entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
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
        except TPLinkLocalBackendError as exc:
            raise UpdateFailed(str(exc)) from exc

        self.sysinfo = data["sysinfo"]
        current_model = self.sysinfo.get("model")
        if current_model:
            self.model = str(current_model)

        self.has_pir = self.device.has_pir
        return data
