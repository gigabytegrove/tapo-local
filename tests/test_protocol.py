"""Protocol unit tests that do not require Home Assistant."""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
import struct
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "tapo_local"

# Import protocol.py without executing custom_components/tapo_local/__init__.py,
# which imports Home Assistant and is intentionally unavailable in this lean CI test.
custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

pkg = types.ModuleType("custom_components.tapo_local")
pkg.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", pkg)

protocol = importlib.import_module("custom_components.tapo_local.protocol")


class ProtocolTests(unittest.TestCase):
    def test_frame_round_trip(self) -> None:
        request = {"system": {"get_sysinfo": {}}}
        frame = protocol.encode_frame(request)
        size = struct.unpack(">I", frame[:4])[0]
        self.assertEqual(
            size,
            len(json.dumps(request, separators=(",", ":")).encode()),
        )
        self.assertEqual(protocol.decode_payload(frame[4:]), request)

    def test_xor_known_round_trip(self) -> None:
        request = {"system": {"set_relay_state": {"state": 1}}}
        frame = protocol.encode_frame(request)
        plain = protocol._xor_decrypt_payload(frame[4:])
        self.assertEqual(json.loads(plain), request)

    def test_model_normalization(self) -> None:
        self.assertEqual(protocol.normalize_model("KS200(US)"), "KS200")
        self.assertEqual(protocol.normalize_model("KS200M(US)"), "KS200M")

    def test_pir_disabled_is_never_triggered(self) -> None:
        state = protocol.calculate_pir_state(
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
        state = protocol.calculate_pir_state(
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


if __name__ == "__main__":
    unittest.main()
