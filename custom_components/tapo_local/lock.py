"""Lock entity for TP-Link Local."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TPLinkLocalCoordinator
from .dlklap import Dl100Device
from .entity import TPLinkLocalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lock entities."""
    coordinator: TPLinkLocalCoordinator = entry.runtime_data
    if coordinator.is_lock:
        async_add_entities([TPLinkDl100Lock(coordinator)])


class TPLinkDl100Lock(TPLinkLocalEntity, LockEntity):
    """Tapo DL100 lock controlled through native DLKLAP."""

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
        return self.coordinator.sysinfo.get("lock_status") in (3, 4)

    async def async_lock(self, **kwargs) -> None:
        device = self.coordinator.device
        assert isinstance(device, Dl100Device)
        await device.set_lock(True)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs) -> None:
        device = self.coordinator.device
        assert isinstance(device, Dl100Device)
        await device.set_lock(False)
        await self.coordinator.async_request_refresh()
