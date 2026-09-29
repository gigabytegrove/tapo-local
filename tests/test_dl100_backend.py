"""Tests for the DL100 session backend."""

from __future__ import annotations

import asyncio
import base64
import importlib
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

backend = importlib.import_module("custom_components.tapo_local.dl100_backend")


def _state(seq: int = 1234) -> dict:
    return {
        "local_seed": base64.b64encode(b"L" * 16).decode(),
        "remote_seed": base64.b64encode(b"R" * 16).decode(),
        "lmk": base64.b64encode(b"M" * 32).decode(),
        "seq": seq,
        "cookie": "TP_SESSIONID=test-session",
    }


class DL100SessionTests(unittest.TestCase):
    def test_wrapped_probe_cache_import(self) -> None:
        state = _state()
        self.assertEqual(
            backend.extract_session_state({"session": state}),
            state,
        )

    def test_session_export_round_trip(self) -> None:
        original = backend.DL100LocalSession.from_state(_state())
        restored = backend.DL100LocalSession.from_state(original.export())
        self.assertEqual(restored.export(), original.export())

    def test_runtime_has_no_cloud_bootstrap_methods(self) -> None:
        self.assertFalse(hasattr(backend.DL100LocalDevice, "_cloud_login"))
        self.assertFalse(hasattr(backend.DL100LocalDevice, "_handshake0"))
        self.assertFalse(hasattr(backend.DL100LocalDevice, "_fetch_control_key"))


class DL100PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_request_is_not_checkpointed_without_reauth(self) -> None:
        saver = AsyncMock()
        device = backend.DL100LocalDevice(
            "192.0.2.100",
            session_state=_state(500),
            session_saver=saver,
        )

        device._post_sync = lambda body, seq: (403, b"")
        with self.assertRaises(backend.DL100SessionError):
            await device.request("getLockStatus")

        saver.assert_not_awaited()

    async def test_http_403_reauthenticates_and_retries(self) -> None:
        saver = AsyncMock()
        refresher = AsyncMock(return_value=_state(900))
        device = backend.DL100LocalDevice(
            "192.0.2.100",
            session_state=_state(500),
            session_saver=saver,
            session_refresher=refresher,
        )

        # First session is rejected. The fresh session receives a valid
        # encrypted response by delegating response construction to that
        # session's own crypto primitives.
        calls = 0

        def post_sync(body, seq):
            nonlocal calls
            calls += 1
            if calls == 1:
                return 403, b""
            plaintext = b'{"result":{"responses":[{"error_code":0,"result":{"lock_status":0}}]}}'
            seq_bytes = device._session.seq.to_bytes(4, "big")
            iv = device._session.ivb + seq_bytes
            from cryptography.hazmat.primitives import padding
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            padder = padding.PKCS7(128).padder()
            padded = padder.update(plaintext) + padder.finalize()
            enc = Cipher(
                algorithms.AES(device._session.lsk),
                modes.CBC(iv),
            ).encryptor()
            ciphertext = enc.update(padded) + enc.finalize()
            return 200, b"X" * 32 + ciphertext

        device._post_sync = post_sync
        result = await device.request("getLockStatus")

        self.assertEqual(result["lock_status"], 0)
        refresher.assert_awaited_once()
        self.assertGreaterEqual(saver.await_count, 2)


class DL100ControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_lock_uses_local_1_and_verifies_state(self) -> None:
        device = backend.DL100LocalDevice(
            "192.0.2.100",
            session_state=_state(),
        )
        device.request = AsyncMock(
            side_effect=[{}, {"lock_status": 0}]
        )
        with patch.object(backend.asyncio, "sleep", new=AsyncMock()):
            await device.set_lock(True)

        self.assertEqual(
            device.request.await_args_list[0].args,
            (
                "setLockStatus",
                {"lock_status": 0, "sa_user_id": "local_1"},
            ),
        )
        self.assertEqual(
            device.request.await_args_list[1].args,
            ("getLockStatus",),
        )

    async def test_set_unlock_uses_local_1_and_verifies_state(self) -> None:
        device = backend.DL100LocalDevice(
            "192.0.2.100",
            session_state=_state(),
        )
        device.request = AsyncMock(
            side_effect=[{}, {"lock_status": 1}]
        )
        with patch.object(backend.asyncio, "sleep", new=AsyncMock()):
            await device.set_lock(False)

        self.assertEqual(
            device.request.await_args_list[0].args,
            (
                "setLockStatus",
                {"lock_status": 1, "sa_user_id": "local_1"},
            ),
        )
        self.assertEqual(
            device.request.await_args_list[1].args,
            ("getLockStatus",),
        )

    async def test_set_lock_raises_when_physical_state_does_not_change(self) -> None:
        device = backend.DL100LocalDevice(
            "192.0.2.100",
            session_state=_state(),
        )
        device.request = AsyncMock(
            side_effect=[
                {},
                {"lock_status": 1},
                {"lock_status": 1},
                {"lock_status": 1},
            ]
        )
        with patch.object(backend.asyncio, "sleep", new=AsyncMock()):
            with self.assertRaisesRegex(
                backend.DL100LocalError,
                "physical state remained lock_status=1",
            ):
                await device.set_lock(True)


if __name__ == "__main__":
    unittest.main()
