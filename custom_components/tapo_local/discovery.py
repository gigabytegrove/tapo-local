"""Targeted local TDP discovery for non-XOR identification."""

from __future__ import annotations

import asyncio
import binascii
import json
import os
import socket
import struct
import time
from typing import Any

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
    packet = _build_tdp_packet()

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
    """Query only the supplied host. No cloud or broadcast discovery."""
    return await asyncio.to_thread(_tdp_probe_sync, host)
