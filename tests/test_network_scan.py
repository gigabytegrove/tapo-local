"""CIDR scanner tests: protocol isolation, bounds, progress and duplicate safety."""

from __future__ import annotations

import asyncio
import importlib
import ipaddress
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "tapo_local"
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)
pkg = types.ModuleType("custom_components.tapo_local")
pkg.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", pkg)
scan = importlib.import_module("custom_components.tapo_local.network_scan")


class CIDRValidationTests(unittest.TestCase):
    def test_accepts_private_cidr_16_and_normalizes(self):
        self.assertEqual(
            scan.validate_discovery_target("172.20.0.0/16"), "172.20.0.0/16"
        )
        self.assertEqual(
            scan.validate_discovery_target("172.20.1.42/16"), "172.20.0.0/16"
        )
        self.assertEqual(scan.validate_discovery_target("10.8.3.0/24"), "10.8.3.0/24")
        self.assertEqual(scan.validate_discovery_target("192.168.0.5"), "192.168.0.5")
        self.assertEqual(scan.validate_discovery_target("255.255.255.255"), "255.255.255.255")

    def test_rejects_public_and_wider_than_16(self):
        for value in ("8.8.8.8", "0.0.0.0/0", "10.0.0.0/8",
                      "172.20.0.0/15", "192.0.2.0/24", "169.254.0.0/16",
                      "127.0.0.1", "172.20.0.0/33", "example.com", "", "::1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scan.validate_discovery_target(value)

    def test_discovery_replies_are_scoped_to_target(self):
        self.assertTrue(scan._allowed_source("172.20.250.1", "172.20.0.0/16"))
        self.assertFalse(scan._allowed_source("172.21.1.1", "172.20.0.0/16"))
        self.assertTrue(scan._allowed_source("172.20.0.99", "172.20.0.99"))
        self.assertFalse(scan._allowed_source("172.20.0.100", "172.20.0.99"))

    def test_legacy_xor_round_trip(self):
        original = b'{"system":{"get_sysinfo":{}}}'
        self.assertEqual(scan._xor_decrypt(scan._xor_encrypt(original)), original)

    def test_modern_tdp_parsing_strips_secrets(self):
        response = {
            "result": {"device_type": "SMART.TAPOLOCK", "device_model": "DL100(US)",
                       "device_id": "lock-1", "nickname": "Front",
                       "secret": "never-include"}
        }
        packet = bytes([2]) + bytes(15) + json.dumps(response).encode()
        found = scan._candidate_from_packet(packet, 20002, "172.20.0.100")
        self.assertEqual(found["model"], "DL100")
        self.assertNotIn("secret", found)

    def test_legacy_response(self):
        info = {"system": {"get_sysinfo": {
            "model": "KS200(US)", "type": "IOT.SMARTPLUGSWITCH",
            "alias": "Hallway", "deviceId": "switch-1"
        }}}
        encoded = scan._xor_encrypt(json.dumps(info).encode())
        self.assertEqual(
            scan._candidate_from_packet(encoded, 9999, "172.20.0.34")["model"],
            "KS200",
        )


class CIDRScanTests(unittest.IsolatedAsyncioTestCase):
    async def test_small_cidr_sends_each_host_with_progress(self):
        sends = []
        progresses = []
        async def send(_sock, host, _probes):
            sends.append(host)
            return 3
        with (patch.object(scan, "_send", side_effect=send),
              patch.object(scan, "HOST_BATCH_SIZE", 2),
              patch.object(scan, "HOSTS_PER_SECOND", 1000),
              patch.object(scan, "REPLY_GRACE_SECONDS", 0)):
            found = await scan.async_scan_local_devices(
                "172.20.0.0/30", progress_callback=progresses.append
            )
        self.assertEqual(sends, ["172.20.0.3", "172.20.0.1", "172.20.0.2"])
        self.assertEqual(found, [])
        self.assertEqual(progresses[-1], 1.0)

    async def test_single_target_emits_unicast(self):
        sends = []
        async def send(_sock, host, _probes):
            sends.append(host)
            return 3
        with patch.object(scan, "_send", side_effect=send), patch.object(scan, "REPLY_GRACE_SECONDS", 0):
            await scan.async_scan_local_devices("172.20.0.34")
        self.assertEqual(sends, ["172.20.0.34", "172.20.0.34"])

    async def test_scan_rejects_excessive_cidr_without_sending(self):
        with patch.object(scan, "_send") as mock_send:
            with self.assertRaises(ValueError):
                await scan.async_scan_local_devices("172.16.0.0/12")
            mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
