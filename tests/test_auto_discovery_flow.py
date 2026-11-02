"""Exercise the real HA config-flow discovery methods without HA/network access."""

from __future__ import annotations

import ast
from pathlib import Path
import types
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/tapo_local/config_flow.py"
HOST = "host"
SCAN_TARGET = "scan_target"
DISCOVERED_HOST = "discovered_host"


class FakeVol:
    @staticmethod
    def Required(key):
        return key

    @staticmethod
    def In(choices):
        return choices

    @staticmethod
    def Schema(value):
        return value


def load_real_flow():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    original = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TPLinkLocalConfigFlow"
    )
    methods = [
        node for node in original.body
        if (isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name in ("async_step_user", "async_step_discovered", "_discovery_label"))
    ]
    klass = ast.ClassDef(
        name="ActualDiscoveryFlow", bases=[], keywords=[],
        body=methods, decorator_list=[],
    )
    compiled = compile(
        ast.fix_missing_locations(ast.Module(body=[klass], type_ignores=[])),
        str(SOURCE), "exec",
    )
    async def scan(target):
        return []
    namespace = {
        "Any": object,
        "ConfigFlowResult": dict,
        "CONF_HOST": HOST,
        "CONF_SCAN_TARGET": SCAN_TARGET,
        "CONF_DISCOVERED_HOST": DISCOVERED_HOST,
        "DEFAULT_DISCOVERY_TARGET": "255.255.255.255",
        "USER_SCHEMA": {},
        "vol": FakeVol,
        "_LOGGER": types.SimpleNamespace(exception=lambda *args: None),
        "async_scan_local_devices": scan,
        "validate_discovery_target": lambda x: x,
        "_valid_reconfigure_host": lambda x: True,
    }
    exec(compiled, namespace)
    return namespace["ActualDiscoveryFlow"], namespace


class DiscoveryFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        cls, namespace = load_real_flow()
        self.namespace = namespace
        self.flow = cls()
        self.flow._discovered = {}
        self.flow._async_current_entries = lambda: []
        self.flow.async_show_form = lambda **kw: dict(type="form", **kw)
        self.flow.async_abort = lambda **kw: dict(type="abort", **kw)
        self.forwarded = []
        async def forward(data):
            self.forwarded.append(data)
            return {"type": "verified", "host": data[HOST]}
        self.flow.async_step_user_forward = forward

    async def test_discovered_selection_requires_user_confirmation(self):
        self.flow._discovered = {
            "192.0.2.12": {
                "host": "192.0.2.12", "alias": "Kitchen",
                "model": "KS200", "device_id": "123",
            }
        }
        first = await self.flow.async_step_discovered()
        self.assertEqual(first["type"], "form")
        self.assertIn("192.0.2.12", first["data_schema"][DISCOVERED_HOST])
        self.assertEqual(self.forwarded, [])
        async def verify(data):
            return await self.flow.async_step_user_forward(data)
        self.flow.async_step_user = verify
        selected = await self.flow.async_step_discovered({DISCOVERED_HOST: "192.0.2.12"})
        self.assertEqual(selected["type"], "verified")
        self.assertEqual(self.forwarded, [{HOST: "192.0.2.12"}])

    async def test_rejects_addresses_not_in_current_results(self):
        self.flow._discovered = {
            "192.0.2.12": {
                "host": "192.0.2.12", "alias": "Kitchen",
                "model": "KS200", "device_id": "123",
            }
        }
        response = await self.flow.async_step_discovered({DISCOVERED_HOST: "192.0.2.99"})
        self.assertEqual(response["errors"], {DISCOVERED_HOST: "invalid_selection"})
        self.assertEqual(self.forwarded, [])

    async def test_no_results_aborts_selection(self):
        self.assertEqual(
            await self.flow.async_step_discovered(),
            {"type": "abort", "reason": "no_devices_found"},
        )

    async def test_scan_excludes_configured_host_and_stable_identity(self):
        found = [
            dict(host="192.0.2.10", alias="Already here", model="KS200", device_id="A"),
            dict(host="192.0.2.11", alias="Moved", model="KS200", device_id="B"),
            dict(host="192.0.2.12", alias="New", model="KS200", device_id="C"),
        ]
        async def fake_scan(target):
            self.assertEqual(target, "255.255.255.255")
            return found
        self.namespace["async_scan_local_devices"] = fake_scan
        self.flow._async_current_entries = lambda: [
            types.SimpleNamespace(data={HOST: "192.0.2.10"}, unique_id="A"),
            types.SimpleNamespace(data={HOST: "192.0.2.99"}, unique_id="B"),
        ]
        response = await self.flow.async_step_user({HOST: ""})
        self.assertEqual(response["type"], "form")
        self.assertEqual(list(self.flow._discovered), ["192.0.2.12"])

    async def test_scan_without_results_reports_useful_error(self):
        response = await self.flow.async_step_user({HOST: ""})
        self.assertEqual(response["errors"], {"base": "no_devices_found"})

    def test_label_strips_control_characters(self):
        label = self.flow._discovery_label({
            "host": "192.0.2.12",
            "alias": "Kitchen\n\tSwitch",
            "model": "KS200",
        })
        self.assertNotIn("\n", label)
        self.assertIn("KS200", label)


if __name__ == "__main__":
    unittest.main()
