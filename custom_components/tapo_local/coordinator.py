"""Data coordinator for TP-Link Local."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_POLL_INTERVAL
from .protocol import (
    TPLinkLocalConnectionError,
    TPLinkLocalDevice,
    TPLinkLocalDeviceError,
    calculate_pir_state,
    normalize_model,
)


class TPLinkLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a supported device entirely over the LAN."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: TPLinkLocalDevice,
    ) -> None:
        self.entry = entry
        self.device = device
        self.sysinfo: dict[str, Any] = {}
        self.model = str(entry.data.get("model", "Unknown"))
        self.model_base = normalize_model(self.model)
        self.has_pir = self.model_base.endswith("M")

        poll_interval = int(entry.options.get("poll_interval", DEFAULT_POLL_INTERVAL))

        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"TP-Link Local {entry.title}",
            config_entry=entry,
            update_interval=timedelta(seconds=poll_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.device.get_state(include_pir=self.has_pir)
        except (TPLinkLocalConnectionError, TPLinkLocalDeviceError) as exc:
            raise UpdateFailed(str(exc)) from exc

        self.sysinfo = data["sysinfo"]
        current_model = self.sysinfo.get("model")
        if current_model:
            self.model = str(current_model)
            self.model_base = normalize_model(self.model)
            self.has_pir = self.model_base.endswith("M")

        if self.has_pir:
            data["pir_state"] = calculate_pir_state(
                data.get("pir_config", {}),
                data.get("pir_adc", {}),
            )

        return data
