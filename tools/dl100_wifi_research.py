#!/usr/bin/env python3
"""Read-only DL100 Wi-Fi research probe.

This tool does not authenticate to TP-Link cloud and does not send lock/unlock
or other state-changing commands.

It maps:
- local TDP identity
- TCP reachability
- harmless HTTP method/endpoint behavior
- optional read-only methods through a previously authorized saved session

The optional saved-session path is for protocol research only. It never creates
or refreshes a cloud-backed session.
"""

from __future__ import annotations

import argparse
import asyncio
import http.client
import json
from pathlib import Path
import socket
import sys
import types
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "custom_components"
PKG = CC / "tapo_local"

# Load research helpers without importing Home Assistant.
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(CC)]
sys.modules.setdefault("custom_components", custom_components)
tapo_local = types.ModuleType("custom_components.tapo_local")
tapo_local.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", tapo_local)

from custom_components.tapo_local.discovery import async_targeted_tdp_discovery

DEFAULT_CACHE = Path("/tmp/tapo-dl100-control-key.json")

SAFE_ENDPOINTS = (
    "/",
    "/app",
    "/app/handshake0",
    "/app/handshake1",
    "/app/handshake2",
    "/app/request",
)

SAFE_METHODS = (
    "getComponentList",
    "getDeviceInfo",
    "getDeviceRunningInfo",
    "getWifiModeStatus",
    "getLockStatus",
)

REDACT_KEYS = {
    "device_id",
    "deviceId",
    "mac",
    "deviceMac",
    "nickname",
    "ssid",
    "ip",
    "latitude",
    "longitude",
    "longitude_i",
    "latitude_i",
    "username",
    "user_id",
    "accountId",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<redacted>" if key in REDACT_KEYS else redact(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def tcp_probe(host: str, port: int, timeout: float = 2.0) -> str:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "open"
    except ConnectionRefusedError:
        return "refused"
    except socket.timeout:
        return "timeout"
    except OSError as exc:
        return f"error:{type(exc).__name__}"


def http_probe(host: str, method: str, path: str) -> dict[str, Any]:
    conn = http.client.HTTPConnection(host, 80, timeout=3)
    try:
        conn.request(method, path, headers={"User-Agent": "tapo-local-research/1"})
        resp = conn.getresponse()
        body = resp.read(512)
        return {
            "method": method,
            "path": path,
            "status": resp.status,
            "content_type": resp.getheader("Content-Type"),
            "content_length": resp.getheader("Content-Length"),
            "allow": resp.getheader("Allow"),
            "body_length_seen": len(body),
            "body_preview": body.decode("utf-8", errors="replace")[:120],
        }
    except Exception as exc:
        return {
            "method": method,
            "path": path,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        conn.close()


async def run_local_surface(host: str) -> None:
    print("DL100 WI-FI LOCAL SURFACE")
    print("=" * 72)
    print("READ ONLY: no account authentication and no lock/unlock commands.\n")

    tdp = await async_targeted_tdp_discovery(host)
    print("TDP")
    print("-" * 72)
    if tdp:
        print(json.dumps(redact(tdp), indent=2, sort_keys=True))
    else:
        print("No targeted TDP response")

    print("\nTCP")
    print("-" * 72)
    for port in (80, 443, 9999):
        print(f"{host}:{port} = {tcp_probe(host, port)}")

    print("\nHTTP ENDPOINT SURFACE")
    print("-" * 72)
    results: list[dict[str, Any]] = []
    for path in SAFE_ENDPOINTS:
        for method in ("HEAD", "GET", "OPTIONS"):
            results.append(http_probe(host, method, path))
    print(json.dumps(results, indent=2))


async def run_saved_session(host: str, cache_path: Path) -> None:
    if not cache_path.exists():
        print(f"\nNo saved session cache found at {cache_path}; skipping session research.")
        return

    # Historical research transport may no longer be part of the runtime
    # integration. Import only if it exists in the checked-out Git history/tree.
    try:
        from custom_components.tapo_local.dlklap import Dl100Device
    except ImportError:
        print(
            "\nSaved-session research module is not present in this checkout. "
            "Use an earlier research commit/worktree if you want to inspect the "
            "already-authorized session. Runtime tapo-local does not depend on it."
        )
        return

    try:
        cached = json.loads(cache_path.read_text())
        session = cached["session"]
        device_id = str(cached["device_id"])
        terminal_uuid = str(cached.get("terminal_uuid") or "")
    except Exception as exc:
        print(f"\nSaved session cache is unreadable: {type(exc).__name__}: {exc}")
        return

    dev = Dl100Device(
        host,
        device_id=device_id,
        terminal_uuid=terminal_uuid or None,
        session_state=session,
        allow_cloud_bootstrap=False,
    )

    print("\nREAD-ONLY METHODS THROUGH EXISTING AUTHORIZED SESSION")
    print("-" * 72)
    for method in SAFE_METHODS:
        try:
            result = await dev.request({"method": method})
            print(f"\n{method}:")
            print(json.dumps(redact(result), indent=2, sort_keys=True))
        except Exception as exc:
            print(f"\n{method}: ERROR {type(exc).__name__}: {exc}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help="DL100 LAN IP/hostname")
    parser.add_argument(
        "--saved-session",
        action="store_true",
        help="also inspect safe read-only methods using an existing saved session",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"saved research session path (default: {DEFAULT_CACHE})",
    )
    args = parser.parse_args()

    await run_local_surface(args.host)
    if args.saved_session:
        await run_saved_session(args.host, args.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
