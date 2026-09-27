"""Pure DLKLAP tests independent of Home Assistant."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "custom_components"
PKG = CC / "tapo_local"
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(CC)]
sys.modules.setdefault("custom_components", custom_components)
tapo_local = types.ModuleType("custom_components.tapo_local")
tapo_local.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", tapo_local)

from custom_components.tapo_local.dlklap import (
    DlklapSession,
    _extract_json_object,
)
from custom_components.tapo_local.discovery import _build_tdp_packet


class DlklapTests(unittest.TestCase):
    def test_extract_prefixed_json(self) -> None:
        value = _extract_json_object(b"\x00\x01\x02\x03" + b'{"a":1,"b":{"c":2}}junk')
        self.assertEqual(value, {"a": 1, "b": {"c": 2}})

    def test_session_encrypt_decrypt_round_trip(self) -> None:
        session = DlklapSession(b"L" * 16, b"R" * 16, b"M" * 32)
        payload, seq = session.encrypt(b'{"hello":"world"}')
        self.assertEqual(seq, session.seq)
        self.assertEqual(session.decrypt(payload), {"hello": "world"})

    def test_session_export_import_preserves_sequence(self) -> None:
        session = DlklapSession(b"L" * 16, b"R" * 16, b"M" * 32)
        session.encrypt(b'{"one":1}')
        state = session.export_state("TP_SESSIONID=abc")
        restored, cookie = DlklapSession.from_state(state)
        self.assertEqual(cookie, "TP_SESSIONID=abc")
        self.assertEqual(restored.seq, session.seq)
        self.assertEqual(restored.local_seed, session.local_seed)
        self.assertEqual(restored.remote_seed, session.remote_seed)
        self.assertEqual(restored.lmk, session.lmk)

    def test_tdp_packet_contains_valid_payload(self) -> None:
        packet = _build_tdp_packet()
        self.assertGreater(len(packet), 16)
        payload = json.loads(packet[16:].decode("utf-8"))
        self.assertIn("rsa_key", payload["params"])
        self.assertTrue(payload["params"]["rsa_key"].startswith("-----BEGIN PUBLIC KEY-----"))


class DlklapLocalFirstTests(unittest.IsolatedAsyncioTestCase):
    async def test_persisted_session_requires_no_cloud_or_handshake(self) -> None:
        from custom_components.tapo_local.dlklap import Dl100Device

        seed_session = DlklapSession(b"L" * 16, b"R" * 16, b"M" * 32)
        state = seed_session.export_state("TP_SESSIONID=abc")
        device = Dl100Device(
            "127.0.0.1",
            device_id="device-id",
            session_state=state,
        )
        device._cloud_login = AsyncMock()
        device._handshake1 = AsyncMock()
        self.assertIsNotNone(device._session)
        self.assertEqual(device._cookie, "TP_SESSIONID=abc")
        device._cloud_login.assert_not_awaited()
        device._handshake1.assert_not_awaited()

    async def test_runtime_never_silently_uses_cloud_without_persisted_session(self) -> None:
        from custom_components.tapo_local.dlklap import (
            Dl100Device,
            DlklapAuthenticationError,
        )

        device = Dl100Device(
            "127.0.0.1",
            username="user@example.com",
            password="secret",
            device_id="device-id",
        )
        device._cloud_login = AsyncMock()

        with self.assertRaises(DlklapAuthenticationError):
            await device._establish_session()

        device._cloud_login.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
