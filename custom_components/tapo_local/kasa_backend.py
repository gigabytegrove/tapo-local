"""python-kasa backend for TP-Link Local.

TP-Link Local owns Home Assistant setup and entity behavior. python-kasa owns
wire-protocol, modules, and feature behavior. Connections are constructed with
an explicit DeviceConfig so the tested KS200/KS200M path never falls back to
protocol guessing or broadcast discovery.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from kasa import Device, DeviceConfig, Feature
from kasa.device import Device as KasaDevice
from kasa.deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.exceptions import KasaException


class TPLinkLocalBackendError(Exception):
    """Base error from the python-kasa backend."""


def xor_device_config(host: str, timeout: int = 5) -> DeviceConfig:
    """Build the deterministic credential-free XOR config for KS200/KS200M."""
    return DeviceConfig(
        host=host,
        timeout=timeout,
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.IotSmartPlugSwitch,
            encryption_type=DeviceEncryptionType.Xor,
        ),
    )


def _normalize_feature_value(value: Any) -> Any:
    """Normalize enum values for coordinator snapshots/logging."""
    if isinstance(value, Enum):
        return value.value if isinstance(value.value, (str, int, float, bool)) else value.name
    return value


class KasaLocalDevice:
    """Local-only python-kasa adapter for the proven IOT/XOR wall-switch path."""

    def __init__(self, host: str, *, timeout: int = 5) -> None:
        self.host = host
        self.timeout = timeout
        self._device: KasaDevice | None = None

    @property
    def device(self) -> KasaDevice | None:
        """Return the connected python-kasa device."""
        return self._device

    @property
    def features(self) -> Mapping[str, Feature]:
        """Expose the complete python-kasa feature map for the connected device."""
        if self._device is None:
            return {}
        try:
            return self._device.features
        except KasaException:
            return {}

    @property
    def has_pir(self) -> bool:
        """Return whether python-kasa exposed PIR features."""
        features = self.features
        return "pir_enabled" in features or "pir_triggered" in features

    def get_feature(self, feature_id: str) -> Feature | None:
        """Return a python-kasa feature by id."""
        return self.features.get(feature_id)

    def feature_value(self, feature_id: str, default: Any = None) -> Any:
        """Read a feature value without making Home Assistant depend on module APIs."""
        feature = self.get_feature(feature_id)
        if feature is None:
            return default
        try:
            return feature.value
        except (KasaException, ValueError, KeyError, TypeError, AttributeError):
            return default

    def feature_snapshot(self) -> dict[str, Any]:
        """Return all readable python-kasa feature values from the latest update."""
        snapshot: dict[str, Any] = {}
        for feature_id, feature in self.features.items():
            try:
                snapshot[feature_id] = _normalize_feature_value(feature.value)
            except (KasaException, ValueError, KeyError, TypeError, AttributeError):
                continue
        return snapshot

    async def async_connect(self) -> KasaDevice:
        """Connect directly using the forced local XOR transport."""
        if self._device is not None:
            return self._device

        try:
            self._device = await Device.connect(
                config=xor_device_config(self.host, self.timeout)
            )
        except (KasaException, OSError) as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

        return self._device

    async def async_disconnect(self) -> None:
        """Close python-kasa resources."""
        if self._device is None:
            return
        try:
            await self._device.disconnect()
        finally:
            self._device = None

    async def async_probe(self) -> dict[str, Any]:
        """Connect once and return local identity and python-kasa feature information."""
        device = await self.async_connect()
        try:
            sysinfo = dict(getattr(device, "sys_info", {}) or {})
            return {
                "model": device.model,
                "alias": device.alias,
                "device_id": device.device_id,
                "device_type": device.device_type.name,
                "sysinfo": sysinfo,
                "has_pir": self.has_pir,
                "features": sorted(self.features),
            }
        finally:
            await self.async_disconnect()

    async def get_state(self) -> dict[str, Any]:
        """Refresh and normalize device state through python-kasa."""
        new_connection = self._device is None
        device = await self.async_connect()

        try:
            if not new_connection:
                await device.update()
        except (KasaException, OSError) as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

        return {
            "sysinfo": dict(getattr(device, "sys_info", {}) or {}),
            "features": self.feature_snapshot(),
        }

    async def set_feature(self, feature_id: str, value: Any = None) -> None:
        """Set or execute a python-kasa feature through its public Feature API."""
        await self.async_connect()
        feature = self.get_feature(feature_id)
        if feature is None:
            raise TPLinkLocalBackendError(
                f"Device does not expose python-kasa feature '{feature_id}'"
            )
        try:
            await feature.set_value(value)
        except (KasaException, ValueError, TypeError) as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

    async def set_relay(self, on: bool) -> None:
        """Set relay state using python-kasa's generic state feature."""
        await self.set_feature("state", on)

    async def set_led(self, on: bool) -> None:
        """Set LED state using python-kasa's LED feature."""
        await self.set_feature("led", on)

    async def set_pir_enabled(self, enabled: bool) -> None:
        """Enable or disable PIR through python-kasa's feature API."""
        await self.set_feature("pir_enabled", enabled)

    async def set_pir_range(self, value: str | int) -> None:
        """Set PIR range through python-kasa's feature API."""
        feature = self.get_feature("pir_range")
        if feature is None:
            await self.async_connect()
            feature = self.get_feature("pir_range")
        if feature is None:
            raise TPLinkLocalBackendError("Device does not expose PIR range")

        if isinstance(value, int):
            choices = feature.choices or []
            try:
                value = choices[value]
            except IndexError as exc:
                raise TPLinkLocalBackendError("Invalid PIR range index") from exc
        await self.set_feature("pir_range", value)
