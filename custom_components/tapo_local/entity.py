"""Base entity for TP-Link Local."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TPLinkLocalCoordinator


class TPLinkLocalEntity(CoordinatorEntity[TPLinkLocalCoordinator]):
    """Base entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TPLinkLocalCoordinator,
        *,
        key: str,
        name: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{key}"
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        sysinfo = self.coordinator.sysinfo
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.coordinator.entry.unique_id))},
            name=self.coordinator.entry.title,
            manufacturer="TP-Link",
            model=self.coordinator.model,
            sw_version=str(
                sysinfo.get("sw_ver")
                or sysinfo.get("fw_ver")
                or sysinfo.get("firmware_version")
                or ""
            )
            or None,
            hw_version=str(
                sysinfo.get("hw_ver")
                or sysinfo.get("hardware_version")
                or ""
            )
            or None,
        )
