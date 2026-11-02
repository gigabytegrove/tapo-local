"""Real ConfigFlow discovery step tests with simulated Home Assistant progress."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
import types
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/tapo_local/config_flow.py"
HOST = "host"
SCAN_TARGET = "scan_target"
DISCOVERED_HOST = "discovered_host"


class Vol:
    @staticmethod
    def Required(key):
        return key
    @staticmethod
    def In(values):
        return values
    @staticmethod
    def Schema(schema):
        return schema


def make_flow():
    code = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    original = next(x for x in code.body if isinstance(x, ast.ClassDef) and x.name == "TPLinkLocalConfigFlow")
    selected = ("async_step_user", "async_step_scan", "async_step_discovered", "_discovery_label")
    cls = ast.ClassDef(
        name="TestedFlow", bases=[], keywords=[],
        body=[x for x in original.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name in selected],
        decorator_list=[],
    )
    ns = {
        "Any": object,
        "ConfigFlowResult": dict,
        "CONF_HOST": HOST,
        "CONF_SCAN_TARGET": SCAN_TARGET,
        "CONF_DISCOVERED_HOST": DISCOVERED_HOST,
        "DEFAULT_DISCOVERY_TARGET": "255.255.255.255",
        "USER_SCHEMA": {},
        "vol": Vol,
        "_LOGGER": types.SimpleNamespace(exception=lambda *args: None),
        "asyncio": asyncio,
        "validate_discovery_target": lambda x: x,
        "_valid_reconfigure_host": lambda x: True,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(SOURCE),"exec"),ns)
    return ns["TestedFlow"],ns


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        flow_class, self.ns = make_flow()
        self.flow = flow_class()
        self.flow._discovered = {}
        self.flow._scan_task = None
        self.flow._scan_error = None
        self.flow._configured_on_scan = 0
        self.flow.hass = types.SimpleNamespace(async_create_task=asyncio.create_task)
        self.flow._async_current_entries = lambda: []
        self.flow.async_show_form = lambda **kw: {"type":"form", **kw}
        self.flow.async_abort = lambda **kw: {"type":"abort", **kw}
        self.flow.async_show_progress = lambda **kw: {"type":"progress", **kw}
        self.flow.async_show_progress_done = lambda **kw: {"type":"progress_done", **kw}
        self.progress = []
        self.flow.async_update_progress = self.progress.append
        async def scan(target, *, progress_callback):
            progress_callback(1.0)
            return []
        self.ns["async_scan_local_devices"] = scan

    async def start_scan(self, found):
        async def scan(target, *, progress_callback):
            progress_callback(.5)
            await asyncio.sleep(0)
            progress_callback(1.0)
            return found
        self.ns["async_scan_local_devices"] = scan
        started = await self.flow.async_step_user({HOST:"",SCAN_TARGET:"172.20.0.0/16"})
        self.assertEqual(started["type"], "progress")
        self.assertEqual(started["progress_action"], "scanning")
        await self.flow._scan_task
        done = await self.flow.async_step_scan()
        self.assertEqual(done, {"type":"progress_done","next_step_id":"discovered"})

    async def test_cidr_progress_and_existing_filtered_by_host_and_id(self):
        self.flow._async_current_entries = lambda: [
            types.SimpleNamespace(data={HOST:"172.20.0.31"},unique_id="a"),
            types.SimpleNamespace(data={HOST:"172.20.0.99"},unique_id="b"),
        ]
        await self.start_scan([
            dict(host="172.20.0.31",alias="Already",model="KS200",device_id="a"),
            dict(host="172.20.0.32",alias="Moved",model="KS200",device_id="b"),
            dict(host="172.20.0.33",alias="New",model="KS200",device_id="c"),
        ])
        form = await self.flow.async_step_discovered()
        self.assertEqual(form["type"], "form")
        self.assertEqual(form["description_placeholders"]["already_configured"],"2")
        self.assertEqual(set(form["data_schema"][DISCOVERED_HOST]),{"172.20.0.33"})
        self.assertEqual(self.progress, [.5, 1.0])

    async def test_invalid_selection_not_probed(self):
        self.flow._discovered = {"172.20.0.33":dict(
            host="172.20.0.33",alias="New",model="KS200",device_id="c"
        )}
        result = await self.flow.async_step_discovered({DISCOVERED_HOST:"172.20.0.1"})
        self.assertEqual(result["errors"],{DISCOVERED_HOST:"invalid_selection"})

    async def test_selection_uses_existing_verified_host_setup(self):
        self.flow._discovered = {"172.20.0.33":dict(
            host="172.20.0.33",alias="New",model="KS200",device_id="c"
        )}
        calls = []
        async def verify(data):
            calls.append(data)
            return {"type":"verified"}
        self.flow.async_step_user = verify
        result = await self.flow.async_step_discovered({DISCOVERED_HOST:"172.20.0.33"})
        self.assertEqual(result["type"],"verified")
        self.assertEqual(calls,[{HOST:"172.20.0.33"}])

    async def test_empty_results_allow_retry(self):
        await self.start_scan([])
        result = await self.flow.async_step_discovered()
        self.assertEqual(result["type"],"form")
        self.assertEqual(result["errors"],{"base":"no_devices_found"})

    async def test_scan_error_allows_retry(self):
        async def fail(target, *, progress_callback):
            raise OSError("Network unreachable")
        self.ns["async_scan_local_devices"] = fail
        result = await self.flow.async_step_user({HOST:"",SCAN_TARGET:"172.20.0.0/16"})
        self.assertEqual(result["type"],"progress")
        await asyncio.sleep(0)
        self.assertEqual((await self.flow.async_step_scan())["type"],"progress_done")
        self.assertEqual((await self.flow.async_step_discovered())["errors"],{"base":"scan_failed"})


if __name__ == "__main__":
    unittest.main()
