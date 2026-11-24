"""Tests for Tapo DL130 support on the shared DL100 DLKLAP runtime."""

from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "tapo_local"

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

pkg = types.ModuleType("custom_components.tapo_local")
pkg.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", pkg)

const = importlib.import_module("custom_components.tapo_local.const")
auth = importlib.import_module("custom_components.tapo_local.dl100_auth")
backend = importlib.import_module("custom_components.tapo_local.dl100_backend")
scan = importlib.import_module("custom_components.tapo_local.network_scan")


def _state(seq: int = 1234) -> dict:
    return {
        "local_seed": base64.b64encode(b"L" * 16).decode(),
        "remote_seed": base64.b64encode(b"R" * 16).decode(),
        "lmk": base64.b64encode(b"M" * 32).decode(),
        "seq": seq,
        "cookie": "TP_SESSIONID=test-session",
    }


class LockModelTests(unittest.TestCase):
    def test_base_model_strips_region_suffix(self) -> None:
        self.assertEqual(const.lock_base_model("DL130(US)"), "DL130")
        self.assertEqual(const.lock_base_model(" dl100 (EU) "), "DL100")
        self.assertEqual(const.lock_base_model(None), "")

    def test_supported_models(self) -> None:
        for model in ("DL100", "DL100(US)", "DL130", "DL130(US)", "dl130(us)"):
            with self.subTest(model=model):
                self.assertTrue(const.is_supported_lock_model(model))
        for model in ("", "DL110", "DL1300", "KS200(US)", "XDL130"):
            with self.subTest(model=model):
                self.assertFalse(const.is_supported_lock_model(model))


class DL130DiscoveryTests(unittest.TestCase):
    def _packet(self, model: str) -> bytes:
        response = {
            "result": {
                "device_type": "SMART.TAPOLOCK",
                "device_model": model,
                "device_id": "lock-130",
                "nickname": "Entry Lock",
            }
        }
        return bytes([2]) + bytes(15) + json.dumps(response).encode()

    def test_dl130_tdp_reply_is_a_candidate(self) -> None:
        found = scan._candidate_from_packet(
            self._packet("DL130(US)"), 20002, "172.20.0.130"
        )
        self.assertIsNotNone(found)
        self.assertEqual(found["model"], "DL130")
        self.assertEqual(found["device_type"], "SMART.TAPOLOCK")
        self.assertEqual(found["device_id"], "lock-130")

    def test_unsupported_lock_model_is_ignored(self) -> None:
        self.assertIsNone(
            scan._candidate_from_packet(
                self._packet("DL110(US)"), 20002, "172.20.0.105"
            )
        )


class DL130CloudListTests(unittest.TestCase):
    def test_dl130_is_listed_with_dl100(self) -> None:
        payload = (
            b'{"error_code":0,"result":{"deviceList":['
            b'{"deviceModel":"DL130(US)","deviceId":"front-cloud",'
            b'"alias":"Entry Lock"},'
            b'{"deviceModel":"DL100(US)","deviceId":"side-cloud",'
            b'"alias":"Side Door"},'
            b'{"deviceModel":"KS200","deviceId":"switch","alias":"Hall"}]}}'
        )
        with patch.object(
            auth, "_cloud_login", return_value=("token-redacted", "acc")
        ), patch.object(auth, "_request", return_value=(200, {}, payload)):
            devices = auth.list_owned_dl100_devices(
                "owner@example.invalid", "password"
            )
        by_id = {d["device_id"]: d for d in devices}
        self.assertEqual(set(by_id), {"front-cloud", "side-cloud"})
        self.assertEqual(by_id["front-cloud"]["model"], "DL130(US)")

    def test_base64_cloud_nicknames_are_decoded(self) -> None:
        encoded = base64.b64encode("Front Gate".encode()).decode()
        payload = json.dumps({
            "error_code": 0,
            "result": {"deviceList": [
                {"deviceModel": "DL130(US)", "deviceId": "gate-cloud",
                 "alias": encoded},
                {"deviceModel": "DL100(US)", "deviceId": "plain-cloud",
                 "alias": "Door"},
                {"deviceModel": "DL130(US)", "deviceId": "nameless-cloud"},
            ]},
        }).encode()
        with patch.object(
            auth, "_cloud_login", return_value=("token-redacted", "acc")
        ), patch.object(auth, "_request", return_value=(200, {}, payload)):
            devices = auth.list_owned_dl100_devices(
                "owner@example.invalid", "password"
            )
        by_id = {d["device_id"]: d["alias"] for d in devices}
        self.assertEqual(by_id["gate-cloud"], "Front Gate")
        self.assertEqual(by_id["plain-cloud"], "Door")
        self.assertEqual(by_id["nameless-cloud"], "DL130(US)")

    def test_decode_alias_keeps_non_base64_and_binary_values(self) -> None:
        self.assertEqual(auth._decode_alias("Side Door"), "Side Door")
        self.assertEqual(auth._decode_alias("Main"), "Main")
        binary = base64.b64encode(b"a\x00b").decode()
        self.assertEqual(auth._decode_alias(binary), binary)

    def test_single_dl130_resolves_missing_local_id(self) -> None:
        reply = (
            b'{"error_code":0,"result":{"deviceList":'
            b'[{"deviceModel":"DL130(US)","deviceId":"front-cloud"}]}}'
        )
        with patch.object(auth, "_request", return_value=(200, {}, reply)):
            self.assertEqual(
                auth._resolve_device_id("test-token", "172.20.0.130"),
                "front-cloud",
            )


class DL130BackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_falls_back_to_configured_model(self) -> None:
        device = backend.DL100LocalDevice(
            "192.0.2.130", session_state=_state(), model="DL130(US)"
        )
        device.request = AsyncMock(side_effect=[{"lock_status": 0}, {"battery": 90}])
        state = await device.get_state()
        self.assertEqual(state["sysinfo"]["model"], "DL130(US)")
        self.assertEqual(state["sysinfo"]["mic_type"], "SMART.TAPOLOCK")

    async def test_reported_model_wins_over_configured_model(self) -> None:
        device = backend.DL100LocalDevice(
            "192.0.2.130", session_state=_state(), model="DL130"
        )
        device.request = AsyncMock(
            side_effect=[{"lock_status": 1}, {"model": "DL130(US)"}]
        )
        state = await device.get_state()
        self.assertEqual(state["sysinfo"]["model"], "DL130(US)")

    async def test_default_model_is_still_dl100(self) -> None:
        device = backend.DL100LocalDevice("192.0.2.100", session_state=_state())
        device.request = AsyncMock(side_effect=[{"lock_status": 0}, {}])
        state = await device.get_state()
        self.assertEqual(state["sysinfo"]["model"], "DL100")


if __name__ == "__main__":
    unittest.main()
