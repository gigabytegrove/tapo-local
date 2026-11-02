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


    def test_control_key_15033_is_safe_and_actionable(self):
        with self.assertRaises(auth.DL100ProvisioningError) as caught:
            auth._parse_control_key_response(
                b'{"error_code":15033,"msg":"private user info"}'
            )
        self.assertEqual(caught.exception.stage, "control_key")
        self.assertEqual(caught.exception.code, 15033)
        self.assertNotIn("private user info", str(caught.exception))

    def test_control_key_accepts_64_character_hex_result(self):
        key = "ABCDEF0123456789" * 4
        self.assertEqual(
            auth._parse_control_key_response(
                ('{"result":{"controlKey":"' + key + '"}}').encode()
            ), key
        )

    def test_control_key_missing_reports_only_safe_numeric_code(self):
        with self.assertRaises(auth.DL100ProvisioningError) as caught:
            auth._parse_control_key_response(
                b'{"code":412,"message":"secret do not print"}'
            )
        self.assertEqual(caught.exception.code, 412)
        self.assertNotIn("secret do not print", str(caught.exception))

    def test_control_key_invalid_or_malformed_payload_fails_closed(self):
        for body in (b"not-json", b"[]", b"{}", b'{"result":{"controlKey":"short"}}'):
            with self.subTest(body=body), self.assertRaises(
                auth.DL100ProvisioningError
            ):
                auth._parse_control_key_response(body)

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
            with self.assertRaisesRegex(auth.DL100ProvisioningError, "Multiple or no DL100"):
                auth._resolve_device_id("test-token", None)

    def test_list_owned_dl100s_returns_all_ids_for_multiple_locks(self):
        payload = (
            b'{"error_code":0,"result":{"deviceList":['
            b'{"deviceModel":"DL100(US)","deviceId":"garage-cloud",'
            b'"alias":"Garage Door Lock"},'
            b'{"deviceModel":"DL100(US)","deviceId":"side-cloud",'
            b'"alias":"Side Door"},'
            b'{"deviceModel":"KS200","deviceId":"switch","alias":"Hall"}]}}'
        )
        with patch.object(auth, "_cloud_login", return_value=("token-redacted", "acc")) as login, patch.object(
            auth, "_request", return_value=(200, {}, payload)
        ) as request:
            devices = auth.list_owned_dl100_devices(
                "owner@example.invalid", "password"
            )
        self.assertEqual(
            {d["device_id"] for d in devices},
            {"garage-cloud", "side-cloud"},
        )
        self.assertEqual(len(devices), 2)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(login.call_count, 1)

    def test_owner_device_list_failure_stops_before_any_handshake(self):
        with patch.object(auth, "_cloud_login", return_value=("token", "acc")), patch.object(
            auth, "_request", return_value=(500, {}, b"Internal error")
        ):
            with self.assertRaises(auth.DL100ProvisioningError) as error:
                auth.list_owned_dl100_devices("owner@example.invalid", "password")
        self.assertEqual(error.exception.stage, "cloud_device")

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
