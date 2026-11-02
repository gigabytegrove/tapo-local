"""Safe DL100 provisioning regression tests with no cloud or LAN traffic."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "tapo_local"
cc = types.ModuleType("custom_components")
cc.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", cc)
pkg = types.ModuleType("custom_components.tapo_local")
pkg.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", pkg)
auth = importlib.import_module("custom_components.tapo_local.dl100_auth")


class DL100ProvisioningTests(unittest.TestCase):
    def test_wake_only_opens_tcp_and_retries_refused_connects(self):
        attempts = []
        class Connection:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
        def connect(addr, timeout):
            attempts.append((addr, timeout))
            if len(attempts) < 3:
                raise ConnectionRefusedError("cold radio")
            return Connection()
        with patch.object(auth.socket, "create_connection", side_effect=connect), patch.object(
            auth.time, "sleep"
        ) as sleeper:
            self.assertTrue(auth._wake_lock("172.20.0.100", timeout=0.5))
        self.assertEqual(len(attempts), 3)
        self.assertEqual(attempts[-1], (("172.20.0.100", 80), 0.5))
        self.assertEqual(sleeper.call_count, 2)

    def test_unreachable_wake_does_not_send_handshake_or_raise(self):
        with patch.object(auth.socket, "create_connection", side_effect=OSError), patch.object(
            auth.time, "sleep"
        ):
            self.assertFalse(auth._wake_lock("172.20.0.100"))

    def test_missing_local_id_must_resolve_cloud_device(self):
        reply = b'{"error_code":0,"result":{"deviceList":[{"deviceModel":"DL100(US)","deviceId":"cloud-id"}]}}'
        with patch.object(auth, "_request", return_value=(200, {}, reply)):
            self.assertEqual(
                auth._resolve_device_id("test-token", "172.20.0.100"),
                "cloud-id",
            )

    def test_known_stable_id_avoids_unneeded_cloud_request(self):
        with patch.object(auth, "_request") as request:
            self.assertEqual(auth._resolve_device_id("test-token", "stable-lock-id"), "stable-lock-id")
            request.assert_not_called()

    def test_ambiguous_account_locks_are_not_guessed(self):
        payload = (b'{"error_code":0,"result":{"deviceList":['
            b'{"deviceModel":"DL100","deviceId":"one"},'
            b'{"deviceModel":"DL100","deviceId":"two"}]}}')
        with patch.object(auth, "_request", return_value=(200, {}, payload)):
            with self.assertRaisesRegex(auth.DL100ProvisioningError, "uniquely"):
                auth._resolve_device_id("test-token", None)

    def test_cloud_transport_error_is_classified_and_redacted(self):
        with patch.object(auth, "_cloud_login", side_effect=OSError("secret-password")):
            with self.assertRaises(auth.DL100ProvisioningError) as raised:
                auth.establish_session("172.20.0.100", "owner@example.invalid", "password")
        self.assertEqual(raised.exception.stage, "cloud_login")
        self.assertNotIn("secret-password", str(raised.exception))

    def test_cloud_api_error_is_classified_without_losing_code(self):
        with patch.object(auth, "_cloud_login",
            side_effect=auth.DL100ProvisioningError("login failed with error_code -202")):
            with self.assertRaises(auth.DL100ProvisioningError) as raised:
                auth.establish_session("172.20.0.100", "owner@example.invalid", "password")
        self.assertEqual(raised.exception.stage, "cloud_login")
        self.assertIn("-202", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
