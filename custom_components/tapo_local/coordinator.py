"""Data coordinator for TP-Link Local."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CONTROL_KEY,
    CONF_POLL_INTERVAL,
    CONF_TRANSPORT,
    DEFAULT_LOCK_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    TRANSPORT_DLKLAP,
)
from .dlklap import Dl100Device, DlklapAuthenticationError, DlklapProtocolError
from .protocol import (
    TPLinkLocalConnectionError,
    TPLinkLocalDevice,
    TPLinkLocalDeviceError,
    calculate_pir_state,
    normalize_model,
)

_LOGGER = logging.getLogger(__name__)


class TPLinkLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a supported device using its selected direct transport."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: TPLinkLocalDevice | Dl100Device,
    ) -> None:
        self.entry = entry
        self.device = device
        self.sysinfo: dict[str, Any] = {}
        self.model = str(entry.data.get("model", "Unknown"))
        self.model_base = normalize_model(self.model)
        self.transport = str(entry.data.get(CONF_TRANSPORT, "xor"))
        self.is_lock = self.transport == TRANSPORT_DLKLAP
        self.has_pir = (not self.is_lock) and self.model_base.endswith("M")

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
            if self.is_lock:
                assert isinstance(self.device, Dl100Device)
                data = await self.device.get_state()
            else:
                assert isinstance(self.device, TPLinkLocalDevice)
                data = await self.device.get_state(include_pir=self.has_pir)
        except (
            TPLinkLocalConnectionError,
            TPLinkLocalDeviceError,
            DlklapAuthenticationError,
            DlklapProtocolError,
        ) as exc:
            raise UpdateFailed(str(exc)) from exc

        self.sysinfo = data["sysinfo"]
        current_model = self.sysinfo.get("model")
        if current_model:
            self.model = str(current_model)
            self.model_base = normalize_model(self.model)
            self.has_pir = (not self.is_lock) and self.model_base.endswith("M")

        if self.has_pir:
            data["pir_state"] = calculate_pir_state(
                data.get("pir_config", {}),
                data.get("pir_adc", {}),
            )

        if self.is_lock and isinstance(self.device, Dl100Device):
            control_key = self.device.control_key
            if control_key and control_key != self.entry.data.get(CONF_CONTROL_KEY):
                self.hass.config_entries.async_update_entry(
                    self.entry,
                    data={**self.entry.data, CONF_CONTROL_KEY: control_key},
                )

        return data
