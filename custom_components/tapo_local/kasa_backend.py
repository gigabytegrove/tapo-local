"""python-kasa backend for TP-Link Local.

TP-Link Local owns Home Assistant setup and entity behavior. python-kasa owns
wire-protocol, modules, and feature behavior. Connections are constructed from
explicit DeviceConfig values so runtime never falls back to protocol guessing.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from kasa import Device, DeviceConfig, Feature, Module
from kasa.credentials import Credentials
from kasa.device import Device as KasaDevice
from kasa.deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.exceptions import AuthenticationError, KasaException
from kasa.interfaces.light import LightState

from .errors import TPLinkLocalRuntimeError


class TPLinkLocalBackendError(TPLinkLocalRuntimeError):
    """Base error from the python-kasa backend."""


class TPLinkLocalAuthenticationError(TPLinkLocalBackendError):
    """The device rejected the supplied local authentication material."""


def kasa_device_config(
    host: str,
    timeout: int = 5,
    *,
    device_family: str = DeviceFamily.IotSmartPlugSwitch.value,
    encryption_type: str = DeviceEncryptionType.Xor.value,
    login_version: int | None = None,
    https: bool = False,
    http_port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    credentials_hash: str | None = None,
) -> DeviceConfig:
    """Build an explicit local python-kasa device configuration."""
    credentials = None
    if username is not None or password is not None:
        credentials = Credentials(username or "", password or "")

    return DeviceConfig(
        host=host,
        timeout=timeout,
        credentials=credentials,
        credentials_hash=credentials_hash,
        connection_type=DeviceConnectionParameters.from_values(
            device_family,
            encryption_type,
            login_version=login_version,
            https=https,
            http_port=http_port,
        ),
    )


def xor_device_config(host: str, timeout: int = 5) -> DeviceConfig:
    """Build the deterministic credential-free legacy IOT/XOR config."""
    return kasa_device_config(host, timeout)


def _normalize_feature_value(value: Any) -> Any:
    """Normalize enum values for coordinator snapshots/logging."""
    if isinstance(value, Enum):
        return (
            value.value
            if isinstance(value.value, (str, int, float, bool))
            else value.name
        )
    return value


class KasaLocalChild:
    """Feature adapter for a python-kasa child device such as a strip outlet."""

    is_child = True

    def __init__(self, device: KasaDevice) -> None:
        self._device = device

    @property
    def features(self) -> Mapping[str, Feature]:
        try:
            return self._device.features
        except KasaException:
            return {}

    def get_feature(self, feature_id: str) -> Feature | None:
        return self.features.get(feature_id)

    def feature_value(self, feature_id: str, default: Any = None) -> Any:
        feature = self.get_feature(feature_id)
        if feature is None:
            return default
        try:
            return feature.value
        except (KasaException, ValueError, KeyError, TypeError, AttributeError):
            return default

    async def set_feature(self, feature_id: str, value: Any = None) -> None:
        feature = self.get_feature(feature_id)
        if feature is None:
            raise TPLinkLocalBackendError(
                f"Child device does not expose python-kasa feature '{feature_id}'"
            )
        try:
            await feature.set_value(value)
        except (KasaException, ValueError, TypeError) as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

    @property
    def device_id(self) -> str:
        try:
            return str(self._device.device_id)
        except (KasaException, AttributeError):
            return str(id(self._device))

    @property
    def entity_key(self) -> str:
        return f"child_{self.device_id}"

    @property
    def alias(self) -> str:
        try:
            return str(self._device.alias or self._device.model)
        except (KasaException, AttributeError):
            return "Outlet"

    @property
    def model(self) -> str:
        try:
            return str(self._device.model)
        except (KasaException, AttributeError):
            return "TP-Link child device"

    @property
    def device_type(self) -> str:
        try:
            return self._device.device_type.name
        except (KasaException, AttributeError):
            return "Unknown"


class KasaLocalDevice:
    """Local-only python-kasa adapter with explicit connection parameters."""

    is_child = False

    def __init__(
        self,
        host: str,
        *,
        timeout: int = 5,
        device_family: str = DeviceFamily.IotSmartPlugSwitch.value,
        encryption_type: str = DeviceEncryptionType.Xor.value,
        login_version: int | None = None,
        https: bool = False,
        http_port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        credentials_hash: str | None = None,
    ) -> None:
        self.host = host
        self.timeout = timeout
        self.device_family = device_family
        self.encryption_type = encryption_type
        self.login_version = login_version
        self.https = https
        self.http_port = http_port
        self.username = username
        self.password = password
        self.credentials_hash = credentials_hash
        self._device: KasaDevice | None = None

    def _config(self) -> DeviceConfig:
        return kasa_device_config(
            self.host,
            self.timeout,
            device_family=self.device_family,
            encryption_type=self.encryption_type,
            login_version=self.login_version,
            https=self.https,
            http_port=self.http_port,
            username=self.username,
            password=self.password,
            credentials_hash=self.credentials_hash,
        )

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
    def children(self) -> list[KasaLocalChild]:
        """Expose initialized python-kasa child devices."""
        if self._device is None:
            return []
        try:
            return [KasaLocalChild(child) for child in self._device.children]
        except (KasaException, AttributeError):
            return []

    @property
    def has_pir(self) -> bool:
        """Return whether python-kasa exposed PIR features."""
        features = self.features
        return "pir_enabled" in features or "pir_triggered" in features

    @property
    def is_light(self) -> bool:
        """Return whether the device exposes primary light capabilities."""
        features = self.features
        return any(
            feature_id in features
            for feature_id in ("brightness", "color_temperature", "hsv")
        )

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
        """Connect directly using the explicitly configured local transport."""
        if self._device is not None:
            return self._device

        try:
            self._device = await Device.connect(config=self._config())
        except AuthenticationError as exc:
            raise TPLinkLocalAuthenticationError(str(exc)) from exc
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
        """Connect once and return local identity and capability information."""
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
                "is_light": self.is_light,
                "features": sorted(self.features),
                "children": [
                    {
                        "device_id": child.device_id,
                        "alias": child.alias,
                        "model": child.model,
                        "device_type": child.device_type,
                        "features": sorted(child.features),
                    }
                    for child in self.children
                ],
                "credentials_hash": device.credentials_hash,
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
        except AuthenticationError as exc:
            raise TPLinkLocalAuthenticationError(str(exc)) from exc
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
        except AuthenticationError as exc:
            raise TPLinkLocalAuthenticationError(str(exc)) from exc
        except (KasaException, ValueError, TypeError) as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

    async def set_light_state(
        self,
        *,
        on: bool | None = None,
        brightness: int | None = None,
        hue: int | None = None,
        saturation: int | None = None,
        color_temp: int | None = None,
        transition: int | None = None,
    ) -> None:
        """Set a light/dimmer through python-kasa's public Light module."""
        device = await self.async_connect()
        try:
            light = device.modules.get(Module.Light)
        except (KasaException, AttributeError):
            light = None
        if light is None:
            raise TPLinkLocalBackendError(
                "Device does not expose python-kasa's Light module"
            )

        try:
            await light.set_state(
                LightState(
                    light_on=on,
                    brightness=brightness,
                    hue=hue,
                    saturation=saturation,
                    color_temp=color_temp,
                    transition=transition,
                )
            )
        except AuthenticationError as exc:
            raise TPLinkLocalAuthenticationError(str(exc)) from exc
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
