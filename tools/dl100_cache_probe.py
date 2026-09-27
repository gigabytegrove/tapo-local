#!/usr/bin/env python3
"""Read-only DL100 control-key persistence test using TP-Link Local itself."""

from __future__ import annotations

import asyncio
import getpass
import json
from pathlib import Path
import sys
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "custom_components"
PKG = CC / "tapo_local"

# Load the protocol package without importing Home Assistant integration setup.
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(CC)]
sys.modules.setdefault("custom_components", custom_components)
tapo_local = types.ModuleType("custom_components.tapo_local")
tapo_local.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", tapo_local)

from custom_components.tapo_local.discovery import async_targeted_tdp_discovery
from custom_components.tapo_local.dlklap import Dl100Device

CACHE_PATH = Path("/tmp/tapo-dl100-control-key.json")


def summarize(state: dict) -> dict:
    info = state.get("sysinfo", {})
    keys = (
        "type",
        "model",
        "lock_status",
        "battery_percentage",
        "at_low_battery",
        "rssi",
        "fw_ver",
        "hw_ver",
    )
    return {key: info.get(key) for key in keys if key in info}


async def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "172.20.0.100"

    print("DL100 CONTROL-KEY PERSISTENCE PROBE")
    print("=" * 72)
    print("READ ONLY: no lock or unlock command is sent.\n")

    discovery = await async_targeted_tdp_discovery(host)
    if not discovery:
        raise RuntimeError("DL100 did not answer targeted local TDP discovery")

    local_device_id = discovery.get("device_id")
    scheme = discovery.get("mgt_encrypt_schm") or {}
    print(json.dumps({
        "device_model": discovery.get("device_model"),
        "device_type": discovery.get("device_type"),
        "encrypt_type": scheme.get("encrypt_type"),
        "local_device_id_present": bool(local_device_id),
    }, indent=2))

    if not local_device_id:
        raise RuntimeError("Local discovery did not return a DL100 device_id")

    email = input("TP-Link/Tapo account email: ").strip()
    password = getpass.getpass("TP-Link/Tapo account password (not echoed): ")
    terminal_uuid = str(uuid.uuid4()).upper()

    print("\nPHASE A: explicit provisioning + local getDeviceInfo")
    provisioner = Dl100Device(
        host,
        username=email,
        password=password,
        device_id=None,
        terminal_uuid=terminal_uuid,
        allow_cloud_bootstrap=True,
    )
    state_a = await provisioner.get_state()
    if not provisioner.device_id:
        raise RuntimeError("Provisioning succeeded but cloud DL100 deviceId was unresolved")
    session_state = provisioner.export_session()
    if not session_state:
        raise RuntimeError("Provisioning succeeded but no local session was retained")

    CACHE_PATH.write_text(json.dumps({
        "host": host,
        "device_id": str(provisioner.device_id),
        "terminal_uuid": terminal_uuid,
        "session": session_state,
    }, indent=2))
    CACHE_PATH.chmod(0o600)

    print("Phase A local read succeeded:")
    print(json.dumps(summarize(state_a), indent=2))

    # Drop the provisioning object and account values. Phase B restores only
    # the encrypted LAN session material, with no credentials and no cloud
    # bootstrap permission.
    del provisioner
    email = password = ""

    print("\nPHASE B: NEW controller using persisted LAN session ONLY")
    cached = json.loads(CACHE_PATH.read_text())
    local_only = Dl100Device(
        host,
        device_id=str(cached["device_id"]),
        terminal_uuid=terminal_uuid,
        session_state=cached["session"],
        allow_cloud_bootstrap=False,
    )
    state_b = await local_only.get_state()

    print("SUCCESS: Phase B resumed the encrypted LAN session with no cloud bootstrap.")
    print(json.dumps(summarize(state_b), indent=2))
    print(f"\nTemporary session cache: {CACHE_PATH} (0600)")
    print("Delete it after the test if you do not want to retain the test copy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
