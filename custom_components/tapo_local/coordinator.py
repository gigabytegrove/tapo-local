"""Data coordinator for Tapo Local."""

from __future__ import annotations

from copy import deepcopy
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
from .dl100_backend import DL100ConnectionError
from .errors import TPLinkLocalRuntimeError

_LOGGER = logging.getLogger(__name__)

# The DL100 is a battery-powered Wi-Fi lock. A single missed LAN poll should not
# immediately make every Home Assistant entity unavailable. Retain the last
# known-good state for two consecutive transport failures, then mark the device
# unavailable on the third miss. Protocol/session failures are never masked.
DL100_CONNECTION_GRACE_POLLS = 2


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
        self._last_good_data: dict[str, Any] | None = None
        self._consecutive_connection_failures = 0

        default_interval = (
            DEFAULT_LOCK_POLL_INTERVAL if self.is_lock else DEFAULT_POLL_INTERVAL
        )
        poll_interval = int(
            entry.options.get(CONF_POLL_INTERVAL, default_interval)
        )

        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"Tapo Local {entry.title}",
            config_entry=entry,
            update_interval=timedelta(seconds=poll_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.device.get_state()
        except DL100ConnectionError as exc:
            if self.is_lock and self._last_good_data is not None:
                self._consecutive_connection_failures += 1
                if self._consecutive_connection_failures <= DL100_CONNECTION_GRACE_POLLS:
                    _LOGGER.warning(
                        "DL100 %s missed local poll %s/%s; retaining last-known "
                        "state: %s",
                        self.entry.title,
                        self._consecutive_connection_failures,
                        DL100_CONNECTION_GRACE_POLLS,
                        exc,
                    )
                    return deepcopy(self._last_good_data)

                _LOGGER.error(
                    "DL100 %s local connection unavailable after %s consecutive "
                    "poll failures: %s",
                    self.entry.title,
                    self._consecutive_connection_failures,
                    exc,
                )
            else:
                _LOGGER.error(
                    "DL100 %s local connection failed before a usable state was "
                    "established: %s",
                    self.entry.title,
                    exc,
                )
            raise UpdateFailed(str(exc)) from exc
        except TPLinkLocalRuntimeError as exc:
            if self.is_lock:
                _LOGGER.error(
                    "DL100 %s protocol/session poll failed; device is being "
                    "marked unavailable: %s",
                    self.entry.title,
                    exc,
                )
            raise UpdateFailed(str(exc)) from exc

        if self.is_lock and self._consecutive_connection_failures:
            _LOGGER.info(
                "DL100 %s local polling recovered after %s missed poll(s)",
                self.entry.title,
                self._consecutive_connection_failures,
            )
        self._consecutive_connection_failures = 0

        self.sysinfo = data["sysinfo"]
        current_model = self.sysinfo.get("model")
        if current_model:
            self.model = str(current_model)

        self.has_pir = (
            False
            if self.is_lock
            else bool(getattr(self.device, "has_pir", False))
        )
        self._last_good_data = deepcopy(data)
        return data
