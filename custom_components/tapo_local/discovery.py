"""Local-first discovery helpers for TP-Link Local."""

from __future__ import annotations

import asyncio
import binascii
from dataclasses import dataclass
import json
import os
import socket
import struct
import time
from typing import Any

from .protocol import TPLinkLocalConnectionError, TPLinkLocalDevice, normalize_model

_TDP_DISCOVERY_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAsQHlvpg/kSyR9zerchtW
gUWwaR64Z9AT0fLV1Btw4fSdzkAaZ89dexQDi9z4Y8iaGJ6EZtxskKhh+PSVGErf
SMzdFAy8qS30DVjBOH9nkGwFUBjpkGHgevJ4WQ4Y/b9xegORZNxvKzexph14x8aO
TEvSu37Cz1qklT9PktrZqoHLGIOiaze5qjE5Ki+A6jSutXxWnCV8SNR/EUYX4hI3
MgSK3Rt1XjuUqVEvUKR1538doPIaBc+P1ugKjB/vGOMBQ0R+zwZX4jpMYzRr69yN
jJ+W56LcIquUBIVezxEWXesMHkvraLj7la2TZ2pUiQIyo/oMvrc/0xR6JHa3U1Cl
DQIDAQAB
-----END PUBLIC KEY-----
"""

TDP_PORTS = (20002, 20004)
TDP_TIMEOUT = 1.5
TDP_ATTEMPTS = 4
TDP_RETRY_DELAY = 0.35


@dataclass(frozen=True, slots=True)
class LocalDiscovery:
    """Locally discovered device identity."""

    host: str
    model: str
    model_base: str
    device_type: str
    transport: str
    device_id: str | None = None
    encryption_type: str | None = None
    login_version: int | None = None
    http_port: int | None = None
    sysinfo: dict[str, Any] | None = None
    tdp_result: dict[str, Any] | None = None


def _build_tdp_packet() -> bytes:
    payload = json.dumps(
        {"params": {"rsa_key": _TDP_DISCOVERY_PUBLIC_KEY}},
        separators=(",", ":"),
    ).encode("utf-8")

    header = struct.pack(
        ">BBHHBBII",
        2,
        0,
        1,
        len(payload),
        17,
        0,
        int.from_bytes(os.urandom(4), "big"),
        0x5A6B7C8D,
    )
    packet = bytearray(header + payload)
    packet[12:16] = binascii.crc32(packet).to_bytes(4, "big")
    return bytes(packet)


def _tdp_probe_sync(host: str) -> dict[str, Any] | None:
    """Target one device, allowing sleeping battery devices time to wake."""
    packet = _build_tdp_packet()

    # A short TCP connect is state-neutral and helps wake battery devices such
    # as DL100 before UDP discovery. Failure is harmless; discovery still runs.
    try:
        with socket.create_connection((host, 80), timeout=1.0):
            pass
    except OSError:
        pass

    time.sleep(TDP_RETRY_DELAY)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.25)
    try:
        for attempt in range(TDP_ATTEMPTS):
            for port in TDP_PORTS:
                try:
                    sock.sendto(packet, (host, port))
                except OSError:
                    pass

            deadline = time.monotonic() + TDP_TIMEOUT
            while time.monotonic() < deadline:
                try:
                    response, source = sock.recvfrom(65535)
                except socket.timeout:
                    continue

                if source[0] != host or len(response) < 16:
                    continue

                try:
                    parsed = json.loads(response[16:].decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                if isinstance(parsed, dict) and isinstance(parsed.get("result"), dict):
                    return parsed["result"]

            if attempt + 1 < TDP_ATTEMPTS:
                time.sleep(TDP_RETRY_DELAY)
    finally:
        sock.close()

    return None


async def async_targeted_tdp_discovery(host: str) -> dict[str, Any] | None:
    """Query only the specified host using modern TDP discovery."""
    return await asyncio.to_thread(_tdp_probe_sync, host)


async def async_identify_device(host: str) -> LocalDiscovery:
    """Identify a device without using TP-Link cloud discovery."""
    try:
        sysinfo = await TPLinkLocalDevice(host, timeout=2.0).get_sysinfo()
    except Exception:
        sysinfo = None

    if sysinfo:
        model = str(sysinfo.get("model", "Unknown"))
        return LocalDiscovery(
            host=host,
            model=model,
            model_base=normalize_model(model),
            device_type=str(sysinfo.get("mic_type", sysinfo.get("type", ""))),
            transport="xor",
            device_id=str(
                sysinfo.get("deviceId")
                or sysinfo.get("device_id")
                or sysinfo.get("mac")
                or ""
            )
            or None,
            sysinfo=sysinfo,
        )

    result = await async_targeted_tdp_discovery(host)
    if not result:
        raise TPLinkLocalConnectionError(
            f"Unable to identify {host} using local XOR or targeted TDP discovery"
        )

    scheme = result.get("mgt_encrypt_schm")
    if not isinstance(scheme, dict):
        scheme = {}

    model = str(result.get("device_model") or result.get("model") or "Unknown")
    return LocalDiscovery(
        host=host,
        model=model,
        model_base=normalize_model(model),
        device_type=str(result.get("device_type", "")),
        transport="tdp",
        device_id=str(result.get("device_id") or "") or None,
        encryption_type=str(scheme.get("encrypt_type") or "") or None,
        login_version=int(scheme["lv"]) if scheme.get("lv") is not None else None,
        http_port=int(scheme["http_port"]) if scheme.get("http_port") is not None else None,
        tdp_result=result,
    )
