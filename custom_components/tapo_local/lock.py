"""Lock entity for TP-Link Local."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .dl100_backend import DL100LocalDevice
from .entity import TPLinkLocalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DL100 lock entity."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock:
        async_add_entities([TPLinkDL100Lock(coordinator)])


class TPLinkDL100Lock(TPLinkLocalEntity, LockEntity):
    """Tapo DL100 lock controlled over the restored local DLKLAP session."""

    def __init__(self, coordinator: TPLinkLocalCoordinator) -> None:
        super().__init__(coordinator, key="lock", name=None)
        self._attr_icon = "mdi:lock"

    @property
    def is_locked(self) -> bool | None:
        status = self.coordinator.sysinfo.get("lock_status")
        if status == 0:
            return True
        if status == 1:
            return False
        return None

    @property
    def is_jammed(self) -> bool | None:
        status = self.coordinator.sysinfo.get("lock_status")
        return status in (3, 4) if status is not None else None

    async def async_lock(self, **kwargs) -> None:
        device = self.coordinator.device
        assert isinstance(device, DL100LocalDevice)
        await device.set_lock(True)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs) -> None:
        device = self.coordinator.device
        assert isinstance(device, DL100LocalDevice)
        await device.set_lock(False)
        await self.coordinator.async_request_refresh()
