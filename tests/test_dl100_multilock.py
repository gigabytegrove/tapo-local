"""Multi-lock onboarding exercises the real config-flow methods, not copies."""

from __future__ import annotations

import ast
import asyncio
from functools import partial
from pathlib import Path
import types
import unittest

PATH = Path(__file__).resolve().parents[1] / "custom_components/tapo_local/config_flow.py"
HOST = "host"
USERNAME = "username"
PASSWORD = "password"
DEVICE_ID = "dl100_device_id"


class Vol:
    @staticmethod
    def Required(name):
        return name

    @staticmethod
    def In(items):
        return items

    @staticmethod
    def Schema(items):
        return items


class ProvisioningError(Exception):
    def __init__(self, message, *, stage=None, code=None):
        super().__init__(message)
        self.stage = stage
        self.code = code


class FakeDL100:
    def __init__(self, host, *, session_state):
        self.host = host

    async def get_state(self):
        return {"sysinfo": {"nickname": "Side Door Lock"}}

    def export_session(self):
        return {"test_session": "advanced"}


def load_methods():
    parsed = ast.parse(PATH.read_text(encoding="utf-8"))
    source_class = next(
        obj for obj in parsed.body
        if isinstance(obj, ast.ClassDef) and obj.name == "TPLinkLocalConfigFlow"
    )
    methods = ("async_step_dl100_credentials", "async_step_dl100_choose")
    klass = ast.ClassDef(
        name="FlowUnderTest", bases=[], keywords=[],
        body=[
            m for m in source_class.body
            if isinstance(m, ast.AsyncFunctionDef) and m.name in methods
        ],
        decorator_list=[],
    )
    assert len(klass.body) == 2
    ns = {
        "Any": object, "ConfigFlowResult": dict,
        "CONF_HOST": HOST, "CONF_USERNAME": USERNAME,
        "CONF_PASSWORD": PASSWORD, "CONF_DL100_DEVICE_ID": DEVICE_ID,
        "CONF_CLOUD_USERNAME": "cloud_username",
        "CONF_CLOUD_PASSWORD": "cloud_password",
        "CONF_TERMINAL_UUID": "terminal_uuid",
        "CONF_SESSION": "session", "CONF_TRANSPORT": "transport",
        "TRANSPORT_DLKLAP": "dlklap",
        "DL100_SESSION_IMPORT": ".storage/imported-session",
        "DL100_CREDENTIALS_SCHEMA": {},
        "vol": Vol, "partial": partial,
        "__package__": "custom_components.tapo_local",
        "_remove_session_import": lambda path: None,
        "_LOGGER": types.SimpleNamespace(
            warning=lambda *args: None, exception=lambda *args: None
        ),
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[klass], type_ignores=[])),
            str(PATH), "exec",
        ), ns,
    )
    return ns["FlowUnderTest"], ns


class DL100MultiLockFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        klass, self.ns = load_methods()
        self.flow = klass()
        self.flow._pending_dl100 = {
            HOST: "172.20.0.100",
            "device_id": "",
            "model": "DL100",
            "device_type": "SMART.TAPOLOCK",
        }
        self.flow._dl100_owner_credentials = None
        self.flow._dl100_owner_candidates = {}
        self.cloud_devices = [
            {"device_id": "garage-cloud", "alias": "Garage Door Lock"},
            {"device_id": "side-cloud", "alias": "Side Door"},
        ]
        self.entries = [
            types.SimpleNamespace(
                data={HOST: "172.20.0.79", DEVICE_ID: "garage-cloud"},
                unique_id="garage-cloud",
            )
        ]
        self.provisioned = []
        self.auth_module = types.SimpleNamespace(
            DL100ProvisioningError=ProvisioningError,
            list_owned_dl100_devices=lambda username, password: self.cloud_devices,
            establish_session=self.provision,
        )
        self.backend_module = types.SimpleNamespace(
            DL100LocalDevice=FakeDL100,
            DL100LocalError=Exception,
        )
        async def importer(hass, path):
            if path.endswith("dl100_auth"):
                return self.auth_module
            if path.endswith("dl100_backend"):
                return self.backend_module
            raise AssertionError(path)
        async def executor(func, *args):
            return func(*args)
        async def set_unique_id(device_id):
            self.unique_id = device_id
        self.ns["async_import_module"] = importer
        self.flow.hass = types.SimpleNamespace(
            async_add_executor_job=executor,
            config=types.SimpleNamespace(path=lambda path: "/tmp/test-import"),
        )
        self.flow._async_current_entries = lambda: self.entries
        self.flow.async_abort = lambda **kw: {"type": "abort", **kw}
        self.flow.async_show_form = lambda **kw: {"type": "form", **kw}
        self.flow.async_create_entry = lambda **kw: {"type": "entry", **kw}
        self.flow.async_set_unique_id = set_unique_id
        self.flow._abort_if_unique_id_configured = lambda **kw: None

    def provision(self, host, username, password, *, device_id):
        self.provisioned.append((host, device_id))
        return {
            "session": {"test_session": "new"},
            "terminal_uuid": "terminal",
            "device_id": device_id,
        }

    async def credentials(self):
        return await self.flow.async_step_dl100_credentials({
            USERNAME: "owner@example.invalid", PASSWORD: "password"
        })

    async def test_second_lock_selected_before_any_handshake(self):
        result = await self.credentials()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "dl100_choose")
        self.assertEqual(
            list(result["data_schema"]["dl100_cloud_device"]),
            ["side-cloud"],
        )
        self.assertEqual(self.provisioned, [])
        chosen = await self.flow.async_step_dl100_choose({
            "dl100_cloud_device": "side-cloud"
        })
        self.assertEqual(chosen["type"], "entry")
        self.assertEqual(chosen["data"][DEVICE_ID], "side-cloud")
        self.assertEqual(self.unique_id, "side-cloud")
        self.assertEqual(self.provisioned, [("172.20.0.100", "side-cloud")])
        self.assertEqual(self.entries[0].unique_id, "garage-cloud")

    async def test_local_id_exactly_matching_cloud_skips_choice(self):
        self.flow._pending_dl100["device_id"] = "side-cloud"
        result = await self.credentials()
        self.assertEqual(result["type"], "entry")
        self.assertEqual(self.provisioned[0][1], "side-cloud")

    async def test_local_id_unknown_does_not_guess(self):
        self.flow._pending_dl100["device_id"] = "not-cloud"
        result = await self.credentials()
        self.assertEqual(result["step_id"], "dl100_choose")
        self.assertEqual(self.provisioned, [])

    async def test_invalid_cloud_choice_never_starts_handshake(self):
        await self.credentials()
        result = await self.flow.async_step_dl100_choose({
            "dl100_cloud_device": "garage-cloud"
        })
        self.assertEqual(result["errors"]["dl100_cloud_device"], "invalid_selection")
        self.assertEqual(self.provisioned, [])

    async def test_racing_duplicate_does_not_steal_existing_session(self):
        await self.credentials()
        self.entries.append(types.SimpleNamespace(
            data={HOST: "172.20.0.200", DEVICE_ID: "side-cloud"},
            unique_id="side-cloud",
        ))
        result = await self.flow.async_step_dl100_choose({
            "dl100_cloud_device": "side-cloud"
        })
        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        self.assertEqual(self.provisioned, [])

    async def test_two_new_locks_are_not_automatically_assigned_by_order(self):
        self.entries.clear()
        result = await self.credentials()
        self.assertEqual(result["step_id"], "dl100_choose")
        self.assertEqual(
            set(result["data_schema"]["dl100_cloud_device"]),
            {"garage-cloud", "side-cloud"},
        )
        self.assertEqual(self.provisioned, [])

    async def test_no_unconfigured_locks_returns_safe_error(self):
        self.entries.append(types.SimpleNamespace(
            data={HOST: "172.20.0.101", DEVICE_ID: "side-cloud"},
            unique_id="side-cloud",
        ))
        result = await self.credentials()
        self.assertEqual(result["type"], "form")
        self.assertEqual(
            result["errors"], {"base": "dl100_no_unconfigured_locks"}
        )
        self.assertEqual(self.provisioned, [])


if __name__ == "__main__":
    unittest.main()
