"""Protocol unit tests that do not require Home Assistant."""

from __future__ import annotations

import json
import math
import struct
import unittest
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "custom_components"
PKG = CC / "tapo_local"
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(CC)]
sys.modules.setdefault("custom_components", custom_components)
tapo_local = types.ModuleType("custom_components.tapo_local")
tapo_local.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", tapo_local)

from custom_components.tapo_local.protocol import (
    _xor_decrypt_payload,
    calculate_pir_state,
    decode_payload,
    encode_frame,
    normalize_model,
)


class ProtocolTests(unittest.TestCase):
    def test_frame_round_trip(self) -> None:
        request = {"system": {"get_sysinfo": {}}}
        frame = encode_frame(request)
        size = struct.unpack(">I", frame[:4])[0]
        self.assertEqual(size, len(json.dumps(request, separators=(",", ":")).encode()))
        self.assertEqual(decode_payload(frame[4:]), request)

    def test_xor_known_round_trip(self) -> None:
        request = {"system": {"set_relay_state": {"state": 1}}}
        frame = encode_frame(request)
        plain = _xor_decrypt_payload(frame[4:])
        self.assertEqual(json.loads(plain), request)

    def test_model_normalization(self) -> None:
        self.assertEqual(normalize_model("KS200(US)"), "KS200")
        self.assertEqual(normalize_model("KS200M(US)"), "KS200M")

    def test_pir_disabled_is_never_triggered(self) -> None:
        state = calculate_pir_state(
            {
                "array": [80, 50, 20, 0],
                "cold_time": 60000,
                "enable": 0,
                "max_adc": 4095,
                "min_adc": 0,
                "trigger_index": 0,
            },
            {"value": 2056},
        )
        self.assertIsNotNone(state)
        assert state is not None
        self.assertFalse(state.triggered)
        self.assertFalse(state.enabled)
        self.assertEqual(state.adc_value, 2056)

    def test_pir_threshold_calculation(self) -> None:
        state = calculate_pir_state(
            {
                "array": [80, 50, 20, 0],
                "cold_time": 60000,
                "enable": 1,
                "max_adc": 4095,
                "min_adc": 0,
                "trigger_index": 0,
            },
            {"value": 0},
        )
        self.assertIsNotNone(state)
        assert state is not None
        self.assertTrue(state.triggered)
        self.assertEqual(state.threshold, 80)
        self.assertTrue(math.isfinite(state.percent))


class ProtocolNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.received = []

        async def handler(reader, writer):
            try:
                header = await reader.readexactly(4)
                size = struct.unpack(">I", header)[0]
                payload = await reader.readexactly(size)
                request = decode_payload(payload)
                self.received.append(request)

                if request.get("system", {}).get("get_sysinfo") == {}:
                    response = {
                        "system": {
                            "get_sysinfo": {
                                "err_code": 0,
                                "model": "KS200(US)",
                                "relay_state": 1,
                            }
                        }
                    }
                else:
                    response = {
                        "system": {
                            "set_relay_state": {"err_code": 0}
                        }
                    }

                writer.write(encode_frame(response))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        self.server = await __import__("asyncio").start_server(
            handler, "127.0.0.1", 0
        )
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def test_device_query_over_tcp(self) -> None:
        from custom_components.tapo_local.protocol import TPLinkLocalDevice

        device = TPLinkLocalDevice(
            "127.0.0.1", port=self.port, timeout=1.0
        )
        info = await device.get_sysinfo()
        self.assertEqual(info["model"], "KS200(US)")
        self.assertEqual(info["relay_state"], 1)
        self.assertEqual(len(self.received), 1)


if __name__ == "__main__":
    unittest.main()
