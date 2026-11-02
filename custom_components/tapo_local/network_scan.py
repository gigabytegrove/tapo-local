"""Bounded, one-shot, credential-free UDP discovery for local Tapo/Kasa devices.

Discovery is identification only. ConfigFlow performs all identity checks and
authentication before creating an entry. No cloud requests, ARP scans, or
network-wide host enumeration are used here.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import select
import socket
import time
from typing import Any

from .const import SUPPORTED_LEGACY_DEVICE_TYPES, SUPPORTED_SMART_FAMILIES
from .discovery import _build_tdp_packet

_LOGGER = logging.getLogger(__name__)
DEFAULT_DISCOVERY_TARGET = "255.255.255.255"
SCAN_SECONDS = 4.0
MAX_RESPONSES = 256
_LEGACY_REQUEST = b'{"system":{"get_sysinfo":{}}}'


def validate_discovery_target(target: str) -> str:
    """Only accept private IPv4 targets or the limited broadcast address."""
    try:
        address = ipaddress.IPv4Address(target.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError("Discovery target must be an IPv4 address") from exc
    if str(address) != DEFAULT_DISCOVERY_TARGET and (
        not address.is_private or address.is_loopback or address.is_link_local
    ):
        raise ValueError("Discovery target must be a private-network IPv4 address")
    return str(address)


def _xor_encrypt(data: bytes) -> bytes:
    key = 171
    out = bytearray()
    for value in data:
        cipher = value ^ key
        out.append(cipher)
        key = cipher
    return bytes(out)


def _xor_decrypt(data: bytes) -> bytes:
    key = 171
    out = bytearray()
    for cipher in data:
        plain = cipher ^ key
        out.append(plain)
        key = cipher
    return bytes(out)


def _candidate_from_packet(payload: bytes, source_port: int, host: str) -> dict[str, str] | None:
    """Extract only public identity fields from a protocol-valid discovery reply."""
    if not 0 < len(payload) <= 65535:
        return None
    try:
        if source_port in (20002, 20004):
            if len(payload) < 17 or payload[0] != 2:
                return None
            envelope = json.loads(payload[16:].decode("utf-8"))
            identity = envelope.get("result") if isinstance(envelope, dict) else None
            if not isinstance(identity, dict):
                return None
            family = str(identity.get("device_type") or "")
            if family not in SUPPORTED_SMART_FAMILIES and family != "SMART.TAPOLOCK":
                return None
            model = str(identity.get("device_model") or "").split("(", 1)[0].strip()
            if family == "SMART.TAPOLOCK" and model != "DL100":
                return None
            if not model:
                return None
            device_id = str(identity.get("device_id") or identity.get("deviceId") or "")
            alias = str(identity.get("nickname") or identity.get("alias") or model)
            return {
                "host": host, "model": model, "alias": alias,
                "device_id": device_id, "device_type": family,
            }

        if source_port != 9999:
            return None
        # Older firmware may include the TCP-style four-byte length prefix.
        for raw in (payload, payload[4:] if len(payload) > 4 else b""):
            try:
                envelope = json.loads(_xor_decrypt(raw).decode("utf-8"))
            except (UnicodeError, ValueError):
                continue
            system = envelope.get("system") if isinstance(envelope, dict) else None
            info = system.get("get_sysinfo") if isinstance(system, dict) else None
            if not isinstance(info, dict):
                continue
            model = str(info.get("model") or "").split("(", 1)[0].strip()
            device_type = str(info.get("type") or "")
            if not model or not device_type:
                continue
            # Legacy protocol families vary. A device must still be confirmed
            # by the existing KasaLocalDevice probe before setup.
            if not (
                device_type.startswith("IOT.")
                or device_type in SUPPORTED_LEGACY_DEVICE_TYPES
            ):
                continue
            return {
                "host": host,
                "model": model,
                "alias": str(info.get("alias") or model),
                "device_id": str(info.get("deviceId") or info.get("device_id") or ""),
                "device_type": device_type,
            }
    except (UnicodeError, ValueError, TypeError, AttributeError):
        return None
    return None


def _scan_sync(target: str, duration: float) -> list[dict[str, str]]:
    """Broadcast twice and collect replies with a strict response/time budget."""
    validated = validate_discovery_target(target)
    results: dict[str, dict[str, str]] = {}
    probes = (
        (9999, _xor_encrypt(_LEGACY_REQUEST)),
        (20002, _build_tdp_packet()),
        (20004, _build_tdp_packet()),
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 0))
        deadline = time.monotonic() + duration
        next_send = time.monotonic()
        sends = 0
        received = 0
        while time.monotonic() < deadline and received < MAX_RESPONSES:
            now = time.monotonic()
            if sends < 2 and now >= next_send:
                for port, packet in probes:
                    try:
                        sock.sendto(packet, (validated, port))
                    except OSError as exc:
                        _LOGGER.debug("Discovery send to UDP %d failed: %s", port, exc)
                sends += 1
                next_send = now + duration / 2
            timeout = min(0.25, max(0.0, deadline - time.monotonic()))
            readable, _, _ = select.select([sock], [], [], timeout)
            if not readable:
                continue
            try:
                packet, source = sock.recvfrom(65535)
            except OSError:
                continue
            received += 1
            host, port = source[:2]
            try:
                ipaddress.IPv4Address(host)
            except ValueError:
                continue
            candidate = _candidate_from_packet(packet, port, host)
            if candidate is not None:
                results[host] = candidate
    return sorted(results.values(), key=lambda item: (item["model"], item["host"]))


async def async_scan_local_devices(target: str = DEFAULT_DISCOVERY_TARGET) -> list[dict[str, str]]:
    """Run a single bounded scan without blocking Home Assistant's event loop."""
    validated = validate_discovery_target(target)
    return await asyncio.to_thread(_scan_sync, validated, SCAN_SECONDS)
