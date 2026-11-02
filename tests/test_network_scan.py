"""Deterministic tests for bounded, credential-free network discovery."""

from __future__ import annotations

import importlib
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


class NetworkScanTests(unittest.TestCase):
    def test_legacy_xor_packet_round_trip(self):
        plain = b'{"system":{"get_sysinfo":{}}}'
        self.assertEqual(scan._xor_decrypt(scan._xor_encrypt(plain)), plain)

    def test_ipv4_targets_are_bounded_to_private_network(self):
        self.assertEqual(scan.validate_discovery_target("255.255.255.255"), "255.255.255.255")
        self.assertEqual(scan.validate_discovery_target("172.20.0.255"), "172.20.0.255")
        for bad in ("example.org", "172.20.0.0/24", "8.8.8.8", "127.0.0.1", "::1", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                scan.validate_discovery_target(bad)

    def test_modern_tdp_identifies_dl100_without_secrets(self):
        import json
        response = {
            "result": {
                "device_type": "SMART.TAPOLOCK",
                "device_model": "DL100(US)",
                "device_id": "lock-123",
                "nickname": "Front Door",
                "mgt_encrypt_schm": {"encrypt_type": "KLAP"},
            }
        }
        packet = bytes([2]) + bytes(15) + json.dumps(response).encode()
        found = scan._candidate_from_packet(packet, 20002, "192.0.2.4")
        self.assertEqual(found["model"], "DL100")
        self.assertEqual(found["device_id"], "lock-123")
        self.assertNotIn("mgt_encrypt_schm", found)

    def test_legacy_discovery_parses_both_udp_formats(self):
        import json
        data = {"system": {"get_sysinfo": {
            "model": "KS200(US)", "type": "IOT.SMARTPLUGSWITCH",
            "alias": "Kitchen", "deviceId": "switch-123",
        }}}
        packet = scan._xor_encrypt(json.dumps(data).encode())
        for payload in (packet, len(packet).to_bytes(4, "big") + packet):
            found = scan._candidate_from_packet(payload, 9999, "192.0.2.5")
            self.assertEqual(found["model"], "KS200")
            self.assertEqual(found["device_id"], "switch-123")

    def test_rejects_malformed_and_unrelated_responses(self):
        for data in (b"", b"unrelated", bytes([2]) + bytes(15) + b'{"result":{}}'):
            self.assertIsNone(scan._candidate_from_packet(data, 20002, "192.0.2.6"))
        self.assertIsNone(scan._candidate_from_packet(b"not-kasa", 9999, "192.0.2.7"))


if __name__ == "__main__":
    unittest.main()
