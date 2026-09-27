"""Native local TP-Link/Kasa protocol implementation.

This module intentionally has no python-kasa dependency.  It implements the
legacy TP-Link XOR framing used by supported Kasa switches on TCP/9999.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import math
import struct
from typing import Any

from .const import DEFAULT_PORT, DEFAULT_TIMEOUT, PIR_MODULE


class TPLinkLocalError(Exception):
    """Base exception for the local protocol."""


class TPLinkLocalConnectionError(TPLinkLocalError):
    """Raised when a device cannot be reached or returns an invalid frame."""


class TPLinkLocalDeviceError(TPLinkLocalError):
    """Raised when a device reports an API error."""


class TPLinkLocalUnsupportedError(TPLinkLocalError):
    """Raised when a reachable device is not supported locally."""


@dataclass(frozen=True, slots=True)
class PIRState:
    """Calculated PIR state."""

    enabled: bool
    adc_value: int
    adc_min: int
    adc_max: int
    trigger_index: int
    threshold: int
    percent: float
    triggered: bool
    cold_time_ms: int


def _xor_encrypt_payload(payload: bytes) -> bytes:
    key = 171
    output = bytearray()
    for byte in payload:
        key ^= byte
        output.append(key)
    return bytes(output)


def _xor_decrypt_payload(payload: bytes) -> bytes:
    key = 171
    output = bytearray()
    for byte in payload:
        plain = key ^ byte
        key = byte
        output.append(plain)
    return bytes(output)


def encode_frame(request: dict[str, Any]) -> bytes:
    """Encode a request as a TP-Link XOR TCP frame."""
    payload = json.dumps(request, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(payload)) + _xor_encrypt_payload(payload)


def decode_payload(payload: bytes) -> dict[str, Any]:
    """Decode an XOR-encrypted JSON payload."""
    try:
        decoded = _xor_decrypt_payload(payload).decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TPLinkLocalConnectionError(
            f"Device returned an invalid XOR/JSON response: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise TPLinkLocalConnectionError("Device response was not a JSON object")
    return value


def normalize_model(model: str | None) -> str:
    """Return model without regional suffix."""
    if not model:
        return "Unknown"
    return model.split("(", 1)[0].strip()


def api_result(response: dict[str, Any], module: str, command: str) -> dict[str, Any]:
    """Extract and validate a module command result."""
    module_data = response.get(module)
    if not isinstance(module_data, dict):
        raise TPLinkLocalDeviceError(f"Missing module response: {module}")
    result = module_data.get(command)
    if not isinstance(result, dict):
        raise TPLinkLocalDeviceError(f"Missing command response: {module}.{command}")
    error_code = result.get("err_code", 0)
    if error_code != 0:
        raise TPLinkLocalDeviceError(
            f"{module}.{command} failed with err_code={error_code}"
        )
    return result


def calculate_pir_state(
    config: dict[str, Any], adc: dict[str, Any]
) -> PIRState | None:
    """Calculate KS200M PIR trigger state from its local ADC API."""
    try:
        enabled = bool(int(config["enable"]))
        adc_min = int(config["min_adc"])
        adc_max = int(config["max_adc"])
        trigger_index = int(config["trigger_index"])
        cold_time_ms = int(config["cold_time"])
        adc_value = int(adc["value"])
        thresholds = config["array"]
        threshold = int(thresholds[trigger_index])
    except (KeyError, TypeError, ValueError, IndexError):
        return None

    # The device exposes a 0..4095 ADC scale. The reference local protocol
    # computes motion from deviation around the scale midpoint and the selected
    # sensitivity threshold.
    adc_mid = math.floor(abs(adc_max - adc_min) / 2)
    pir_value = adc_mid - adc_value

    if pir_value < 0:
        divisor = adc_mid - adc_min
    else:
        divisor = adc_max - adc_mid

    percent = 0.0 if divisor == 0 else (float(pir_value) / divisor) * 100.0
    triggered = enabled and abs(percent) > (100 - threshold)

    return PIRState(
        enabled=enabled,
        adc_value=adc_value,
        adc_min=adc_min,
        adc_max=adc_max,
        trigger_index=trigger_index,
        threshold=threshold,
        percent=percent,
        triggered=triggered,
        cold_time_ms=cold_time_ms,
    )


class TPLinkLocalDevice:
    """A single directly connected TP-Link/Kasa LAN device."""

    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._io_lock = asyncio.Lock()

    async def query(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send one local XOR request and return the JSON response."""
        frame = encode_frame(request)

        async with self._io_lock:
            writer: asyncio.StreamWriter | None = None
            try:
                async with asyncio.timeout(self.timeout):
                    reader, writer = await asyncio.open_connection(
                        self.host, self.port
                    )
                    writer.write(frame)
                    await writer.drain()

                    header = await reader.readexactly(4)
                    response_length = struct.unpack(">I", header)[0]
                    if response_length <= 0 or response_length > 1_048_576:
                        raise TPLinkLocalConnectionError(
                            f"Invalid response length: {response_length}"
                        )

                    payload = await reader.readexactly(response_length)
            except TimeoutError as exc:
                raise TPLinkLocalConnectionError(
                    f"Timed out communicating with {self.host}:{self.port}"
                ) from exc
            except (
                OSError,
                asyncio.IncompleteReadError,
                ConnectionError,
            ) as exc:
                raise TPLinkLocalConnectionError(
                    f"Unable to communicate with {self.host}:{self.port}: {exc}"
                ) from exc
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass

        return decode_payload(payload)

    async def get_sysinfo(self) -> dict[str, Any]:
        """Return system information."""
        response = await self.query({"system": {"get_sysinfo": {}}})
        return api_result(response, "system", "get_sysinfo")

    async def get_state(self, *, include_pir: bool) -> dict[str, Any]:
        """Get the current state in a single local request."""
        request: dict[str, Any] = {"system": {"get_sysinfo": {}}}
        if include_pir:
            request[PIR_MODULE] = {
                "get_config": {},
                "get_adc_value": {},
            }

        response = await self.query(request)
        sysinfo = api_result(response, "system", "get_sysinfo")

        state: dict[str, Any] = {"sysinfo": sysinfo}
        if include_pir:
            state["pir_config"] = api_result(response, PIR_MODULE, "get_config")
            state["pir_adc"] = api_result(response, PIR_MODULE, "get_adc_value")

        return state

    async def set_relay(self, on: bool) -> None:
        """Set the physical relay state."""
        response = await self.query(
            {"system": {"set_relay_state": {"state": int(on)}}}
        )
        api_result(response, "system", "set_relay_state")

    async def set_led(self, on: bool) -> None:
        """Set the status LED state."""
        response = await self.query(
            {"system": {"set_led_off": {"off": int(not on)}}}
        )
        api_result(response, "system", "set_led_off")

    async def set_pir_enabled(self, enabled: bool) -> None:
        """Enable or disable PIR sensing."""
        response = await self.query(
            {PIR_MODULE: {"set_enable": {"enable": int(enabled)}}}
        )
        api_result(response, PIR_MODULE, "set_enable")

    async def set_pir_range(self, index: int) -> None:
        """Set the PIR sensitivity/range index."""
        response = await self.query(
            {PIR_MODULE: {"set_trigger_sens": {"index": int(index)}}}
        )
        api_result(response, PIR_MODULE, "set_trigger_sens")
