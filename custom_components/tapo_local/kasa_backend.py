"""python-kasa backend for TP-Link Local.

TP-Link Local owns Home Assistant setup and entity behavior. python-kasa owns
wire-protocol and device-module behavior. Connections are constructed with an
explicit DeviceConfig so no discovery or try-all protocol selection is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kasa import Device, DeviceConfig, Module
from kasa.device import Device as KasaDevice
from kasa.deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.exceptions import KasaException
from kasa.iot.modules.motion import Motion, Range


class TPLinkLocalBackendError(Exception):
    """Base error from the python-kasa backend."""


@dataclass(frozen=True, slots=True)
class PirState:
    """Normalized PIR state used by Home Assistant entities."""

    enabled: bool
    adc_value: int
    adc_min: int
    adc_max: int
    trigger_index: int
    threshold: int
    percent: float
    triggered: bool
    cold_time_ms: int


def xor_device_config(host: str, timeout: int = 5) -> DeviceConfig:
    """Build a deterministic local XOR config.

    This bypasses python-kasa discovery and protocol fallback entirely.
    """
    return DeviceConfig(
        host=host,
        timeout=timeout,
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.IotSmartPlugSwitch,
            encryption_type=DeviceEncryptionType.Xor,
        ),
    )


class KasaLocalDevice:
    """Local-only python-kasa adapter for IOT wall switches."""

    def __init__(self, host: str, *, timeout: int = 5) -> None:
        self.host = host
        self.timeout = timeout
        self._device: KasaDevice | None = None

    @property
    def device(self) -> KasaDevice | None:
        """Return the connected python-kasa device."""
        return self._device

    @property
    def has_pir(self) -> bool:
        """Return whether python-kasa exposed the PIR module."""
        return bool(self._device and Module.IotMotion in self._device.modules)

    async def async_connect(self) -> KasaDevice:
        """Connect directly using a forced XOR transport."""
        if self._device is not None:
            return self._device

        try:
            self._device = await Device.connect(
                config=xor_device_config(self.host, self.timeout)
            )
        except KasaException as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc
        except OSError as exc:
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
        """Connect once and return local identity information."""
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
            }
        finally:
            await self.async_disconnect()

    async def get_state(self, *, include_pir: bool) -> dict[str, Any]:
        """Refresh and normalize the device state."""
        new_connection = self._device is None
        device = await self.async_connect()

        try:
            if not new_connection:
                await device.update()
        except KasaException as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc
        except OSError as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

        sysinfo = dict(getattr(device, "sys_info", {}) or {})
        state: dict[str, Any] = {"sysinfo": sysinfo}

        motion = device.modules.get(Module.IotMotion)
        if include_pir and isinstance(motion, Motion):
            pir = motion.pir_state
            state["pir_state"] = PirState(
                enabled=motion.enabled,
                adc_value=motion.adc_value,
                adc_min=motion.adc_min,
                adc_max=motion.adc_max,
                trigger_index=motion.range.value,
                threshold=motion.threshold,
                percent=motion.pir_percent,
                triggered=motion.pir_triggered,
                cold_time_ms=motion.inactivity_timeout,
            )

        return state

    async def set_relay(self, on: bool) -> None:
        """Set relay state through python-kasa."""
        device = await self.async_connect()
        try:
            if on:
                await device.turn_on()
            else:
                await device.turn_off()
        except KasaException as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

    async def set_led(self, on: bool) -> None:
        """Set LED state through python-kasa's LED module."""
        device = await self.async_connect()
        led = device.modules.get(Module.Led)
        if led is None:
            raise TPLinkLocalBackendError("Device does not expose an LED module")
        try:
            await led.set_led(on)
        except KasaException as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

    async def set_pir_enabled(self, enabled: bool) -> None:
        """Enable or disable the KS200M PIR module."""
        motion = await self._motion_module()
        try:
            await motion.set_enabled(enabled)
        except KasaException as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

    async def set_pir_range(self, index: int) -> None:
        """Set KS200M PIR range."""
        motion = await self._motion_module()
        try:
            await motion.set_range(Range(index))
        except (KasaException, ValueError) as exc:
            raise TPLinkLocalBackendError(str(exc)) from exc

    async def _motion_module(self) -> Motion:
        device = await self.async_connect()
        motion = device.modules.get(Module.IotMotion)
        if not isinstance(motion, Motion):
            raise TPLinkLocalBackendError("Device does not expose a PIR module")
        return motion
