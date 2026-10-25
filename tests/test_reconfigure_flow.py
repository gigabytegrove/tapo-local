"""Reconfigure IP address without Home Assistant or live network dependencies.

Extract the real config-flow method via AST and run it with deterministic
entry/device/storage doubles. This exercises its decisions, not a copied
implementation. No cloud call or local-device side effect is performed.
"""

from __future__ import annotations

import ast
import copy
import ipaddress
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "custom_components/tapo_local/config_flow.py"
)

CONF_HOST = "host"
CONF_TRANSPORT = "transport"
CONF_SESSION = "session"
CONF_CREDENTIALS_HASH = "credentials_hash"
CONF_DEVICE_FAMILY = "device_family"
CONF_ENCRYPTION_TYPE = "encryption_type"
CONF_LOGIN_VERSION = "login_version"
CONF_HTTPS = "https"
CONF_HTTP_PORT = "http_port"
DOMAIN = "tapo_local"
TRANSPORT_XOR = "xor"
TRANSPORT_SMART = "smart"
TRANSPORT_DLKLAP = "dlklap"
DL100_SESSION_STORE_VERSION = 2
KASA_CREDENTIAL_STORE_VERSION = 1


class FakeBackendError(Exception):
    """Unable to connect to a local device."""


class FakeAuthError(FakeBackendError):
    """Device refused the saved protocol credentials."""


class FakeDL100ConnectionError(Exception):
    """DL100 unavailable on the LAN."""


class FakeDL100Error(Exception):
    """DL100 rejected a previously authorized session."""


class FakeDependencyError(Exception):
    """Kasa dependency unavailable."""


class WrongDeviceError(Exception):
    """Entry identity mismatch."""


class FakeEntry:
    def __init__(self, transport=TRANSPORT_XOR, unique_id="device-123"):
        self.entry_id = "existing-entry"
        self.unique_id = unique_id
        self.data = {
            CONF_HOST: "192.0.2.10",
            CONF_TRANSPORT: transport,
            "model": "KS200",
            "device_type": "WallSwitch",
        }
        self.options = {"poll_interval": 11}
        if transport == TRANSPORT_SMART:
            self.data.update({
                CONF_DEVICE_FAMILY: "SMART.KASASWITCH",
                CONF_ENCRYPTION_TYPE: "KLAP",
                CONF_LOGIN_VERSION: 2,
                CONF_HTTPS: False,
                CONF_HTTP_PORT: 80,
            })


class FakeVol:
    @staticmethod
    def Required(key, default):
        return (key, default)

    @staticmethod
    def Schema(schema):
        return schema


class FakeConfigValidation:
    string = str


def _extract_real_reconfigure_method() -> type:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    config_cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TPLinkLocalConfigFlow"
    )
    method = next(
        node for node in config_cls.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_step_reconfigure"
    )
    standalone_cls = ast.ClassDef(
        name="RealReconfigureFlow",
        bases=[],
        keywords=[],
        body=[method],
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_valid_reconfigure_host"), standalone_cls], type_ignores=[]))
    return module


class ReconfigureFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = FakeEntry()
        self.storage = {}
        self.saved = []
        self.probed = []
        self.kasa_result = {"device_id": "device-123"}
        self.dl100_result = {"sysinfo": {"device_id": "device-123"}}
        self.kasa_exception = None
        self.dl100_exception = None
        self.dependencies_fail = False
        self.reloads = 0
        self.unique_ids = []
        testcase = self

        class FakeKasa:
            def __init__(self, host, **kwargs):
                testcase.probed.append(("kasa", host, kwargs))

            async def async_probe(self):
                if testcase.kasa_exception:
                    raise testcase.kasa_exception
                return testcase.kasa_result

        class FakeDL100:
            def __init__(self, host, *, session_state):
                testcase.probed.append(("dl100", host, dict(session_state)))

            async def get_state(self):
                if testcase.dl100_exception:
                    raise testcase.dl100_exception
                return testcase.dl100_result

            def export_session(self):
                return {"seq": 123, "secret": "still-private"}

        class FakeStore:
            def __init__(self, hass, version, key, *, private, atomic_writes):
                if not (private and atomic_writes):
                    raise AssertionError("sensitive session must have private atomic storage")
                self.key = key
                testcase.probed.append(("store", key, version))

            async def async_load(self):
                return copy.deepcopy(testcase.storage.get(self.key))

            async def async_save(self, data):
                testcase.storage[self.key] = copy.deepcopy(data)
                testcase.saved.append((self.key, copy.deepcopy(data)))

        async def fake_import_module(hass, module):
            if module.endswith(".kasa_backend"):
                return types.SimpleNamespace(
                    KasaLocalDevice=FakeKasa,
                    TPLinkLocalAuthenticationError=FakeAuthError,
                    TPLinkLocalBackendError=FakeBackendError,
                )
            if module.endswith(".dl100_backend"):
                return types.SimpleNamespace(
                    DL100LocalDevice=FakeDL100,
                    DL100ConnectionError=FakeDL100ConnectionError,
                    DL100LocalError=FakeDL100Error,
                )
            raise AssertionError(f"unexpected module import {module}")

        async def fake_ensure_kasa(hass):
            if testcase.dependencies_fail:
                raise FakeDependencyError()

        package = types.ModuleType("homeassistant")
        helpers = types.ModuleType("homeassistant.helpers")
        storage = types.ModuleType("homeassistant.helpers.storage")
        storage.Store = FakeStore
        package.helpers = helpers
        helpers.storage = storage
        module_names = {
            "homeassistant": package,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.storage": storage,
        }
        patcher = patch.dict(sys.modules, module_names)
        patcher.start()
        self.addCleanup(patcher.stop)

        class DummyLogger:
            def exception(self, *args, **kwargs):
                pass

        ns = {
            "__package__": "custom_components.tapo_local",
            "ipaddress": ipaddress,
            "Any": object,
            "ConfigFlowResult": dict,
            "vol": FakeVol,
            "cv": FakeConfigValidation,
            "_LOGGER": DummyLogger(),
            "CONF_HOST": CONF_HOST,
            "CONF_TRANSPORT": CONF_TRANSPORT,
            "CONF_SESSION": CONF_SESSION,
            "CONF_CREDENTIALS_HASH": CONF_CREDENTIALS_HASH,
            "CONF_DEVICE_FAMILY": CONF_DEVICE_FAMILY,
            "CONF_ENCRYPTION_TYPE": CONF_ENCRYPTION_TYPE,
            "CONF_LOGIN_VERSION": CONF_LOGIN_VERSION,
            "CONF_HTTPS": CONF_HTTPS,
            "CONF_HTTP_PORT": CONF_HTTP_PORT,
            "DOMAIN": DOMAIN,
            "TRANSPORT_XOR": TRANSPORT_XOR,
            "TRANSPORT_SMART": TRANSPORT_SMART,
            "TRANSPORT_DLKLAP": TRANSPORT_DLKLAP,
            "DL100_SESSION_STORE_VERSION": DL100_SESSION_STORE_VERSION,
            "KASA_CREDENTIAL_STORE_VERSION": KASA_CREDENTIAL_STORE_VERSION,
            "TPLinkLocalDependencyError": FakeDependencyError,
            "async_import_module": fake_import_module,
            "async_ensure_kasa": fake_ensure_kasa,
        }
        exec(compile(_extract_real_reconfigure_method(), str(SOURCE), "exec"), ns)
        self.flow = ns["RealReconfigureFlow"]()
        self.flow.hass = object()
        self.flow._get_reconfigure_entry = lambda: testcase.entry

        async def set_id(device_id):
            testcase.unique_ids.append(device_id)

        def verify_id():
            if testcase.unique_ids[-1] != testcase.entry.unique_id:
                raise WrongDeviceError()

        def update(entry, *, data_updates, reload_even_if_entry_is_unchanged=True):
            if entry is not testcase.entry:
                raise AssertionError("reconfigure attempted to replace config entry")
            entry.data.update(data_updates)
            testcase.reloads += int(reload_even_if_entry_is_unchanged)
            return {"type": "abort", "reason": "reconfigure_successful"}

        def form(*, step_id, data_schema, errors):
            return {
                "type": "form", "step_id": step_id,
                "data_schema": data_schema, "errors": errors,
            }

        self.flow.async_set_unique_id = set_id
        self.flow._abort_if_unique_id_mismatch = verify_id
        self.flow.async_update_reload_and_abort = update
        self.flow.async_show_form = form

    async def test_form_prefills_current_host(self):
        response = await self.flow.async_step_reconfigure()
        self.assertEqual(response["step_id"], "reconfigure")
        self.assertEqual(response["data_schema"], {(CONF_HOST, "192.0.2.10"): str})
        self.assertEqual(response["errors"], {})

    async def test_unchanged_host_does_not_probe_or_reload(self):
        result = await self.flow.async_step_reconfigure({CONF_HOST: " 192.0.2.10 "})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(self.reloads, 0)
        self.assertEqual(self.probed, [])

    async def test_legacy_xor_updates_existing_entry_and_preserves_options(self):
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.99"})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(self.entry.entry_id, "existing-entry")
        self.assertEqual(self.entry.data[CONF_HOST], "192.0.2.99")
        self.assertEqual(self.entry.options, {"poll_interval": 11})
        self.assertEqual(self.reloads, 1)
        self.assertEqual(self.unique_ids, ["device-123"])
        self.assertEqual(self.probed, [("kasa", "192.0.2.99", {})])

    async def test_wrong_device_cannot_take_over_existing_entry(self):
        self.kasa_result = {"device_id": "different-device"}
        with self.assertRaises(WrongDeviceError):
            await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.90"})
        self.assertEqual(self.entry.data[CONF_HOST], "192.0.2.10")
        self.assertEqual(self.reloads, 0)

    async def test_failed_connection_keeps_old_host(self):
        self.kasa_exception = FakeBackendError("offline")
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.91"})
        self.assertEqual(result["errors"]["base"], "cannot_connect")
        self.assertEqual(self.entry.data[CONF_HOST], "192.0.2.10")

    async def test_missing_device_identity_is_fail_closed(self):
        self.kasa_result = {"model": "KS200"}
        response = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.91"})
        self.assertEqual(response["errors"]["base"], "device_identity_unavailable")
        self.assertEqual(self.reloads, 0)

    async def test_no_stable_entry_identity_is_fail_closed(self):
        self.entry.unique_id = None
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.92"})
        self.assertEqual(result["errors"]["base"], "device_identity_unavailable")
        self.assertEqual(self.probed, [])

    async def test_invalid_host_does_not_open_network_connection(self):
        for host in ("", " ", "http://192.0.2.20", "192.0.2.5/path", "192.0.2.5 2", "192.0.2.5:80", "switch.local:80"):
            with self.subTest(host=host):
                result = await self.flow.async_step_reconfigure({CONF_HOST: host})
                self.assertEqual(result["errors"][CONF_HOST], "invalid_host")
                self.assertEqual(self.probed, [])

    async def test_ipv6_literal_supported(self):
        result = await self.flow.async_step_reconfigure({CONF_HOST: "2001:db8::55"})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(self.entry.data[CONF_HOST], "2001:db8::55")

    async def test_smart_uses_private_hash_and_retains_transport(self):
        self.entry = FakeEntry(TRANSPORT_SMART)
        key = "tapo_local.kasa_credentials.existing-entry"
        self.storage[key] = {CONF_CREDENTIALS_HASH: "saved-hash"}
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.93"})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(self.probed[0], ("store", key, 1))
        typ, target, kwargs = self.probed[1]
        self.assertEqual((typ, target), ("kasa", "192.0.2.93"))
        self.assertEqual(kwargs["credentials_hash"], "saved-hash")
        self.assertEqual(kwargs["device_family"], "SMART.KASASWITCH")
        self.assertEqual(kwargs["encryption_type"], "KLAP")
        self.assertEqual(kwargs["http_port"], 80)
        self.assertNotIn("password", kwargs)
        self.assertNotIn(CONF_CREDENTIALS_HASH, self.entry.data)
        self.assertEqual(self.reloads, 1)

    async def test_smart_missing_credentials_does_not_update_host(self):
        self.entry = FakeEntry(TRANSPORT_SMART)
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.94"})
        self.assertEqual(result["errors"]["base"], "credentials_hash_unavailable")
        self.assertEqual(self.entry.data[CONF_HOST], "192.0.2.10")
        self.assertEqual(self.reloads, 0)

    async def test_smart_bad_credentials_does_not_update_host(self):
        self.entry = FakeEntry(TRANSPORT_SMART)
        self.entry.data[CONF_CREDENTIALS_HASH] = "old-entry-hash"
        self.kasa_exception = FakeAuthError("rejected")
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.95"})
        self.assertEqual(result["errors"]["base"], "invalid_auth")
        self.assertEqual(self.reloads, 0)

    async def test_smart_dependency_failure_does_not_update_host(self):
        self.entry = FakeEntry(TRANSPORT_SMART)
        self.dependencies_fail = True
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.95"})
        self.assertEqual(result["errors"]["base"], "dependency_unavailable")

    async def test_dl100_persists_advanced_private_session(self):
        self.entry = FakeEntry(TRANSPORT_DLKLAP)
        key = "tapo_local.dl100_session.existing-entry"
        self.storage[key] = {
            CONF_SESSION: {"seq": 50},
            "cloud_username": "private-user",
        }
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.99"})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(self.storage[key][CONF_SESSION]["seq"], 123)
        self.assertEqual(self.storage[key]["cloud_username"], "private-user")
        self.assertEqual(self.entry.data[CONF_HOST], "192.0.2.99")
        self.assertNotIn(CONF_SESSION, self.entry.data)
        self.assertEqual(self.reloads, 1)

    async def test_dl100_wrong_id_does_not_save_or_change_address(self):
        self.entry = FakeEntry(TRANSPORT_DLKLAP)
        self.storage["tapo_local.dl100_session.existing-entry"] = {
            CONF_SESSION: {"seq": 50}
        }
        self.dl100_result = {"sysinfo": {"device_id": "other-lock"}}
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.99"})
        self.assertEqual(result["errors"]["base"], "wrong_device")
        self.assertEqual(self.entry.data[CONF_HOST], "192.0.2.10")
        self.assertEqual(self.saved, [])
        self.assertEqual(self.reloads, 0)

    async def test_dl100_unavailable_does_not_mutate_private_store(self):
        self.entry = FakeEntry(TRANSPORT_DLKLAP)
        self.storage["tapo_local.dl100_session.existing-entry"] = {
            CONF_SESSION: {"seq": 50}
        }
        self.dl100_exception = FakeDL100ConnectionError()
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.99"})
        self.assertEqual(result["errors"]["base"], "cannot_connect")
        self.assertEqual(self.saved, [])
        self.assertEqual(self.entry.data[CONF_HOST], "192.0.2.10")

    async def test_dl100_missing_session_rejected(self):
        self.entry = FakeEntry(TRANSPORT_DLKLAP)
        result = await self.flow.async_step_reconfigure({CONF_HOST: "192.0.2.99"})
        self.assertEqual(result["errors"]["base"], "dl100_session_missing")
        self.assertEqual(self.reloads, 0)


if __name__ == "__main__":
    unittest.main()
