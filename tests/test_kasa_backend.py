"""Tests for deterministic python-kasa backend configuration."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest

from kasa.deviceconfig import DeviceEncryptionType, DeviceFamily

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "tapo_local"

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)

pkg = types.ModuleType("custom_components.tapo_local")
pkg.__path__ = [str(PKG)]
sys.modules.setdefault("custom_components.tapo_local", pkg)

backend = importlib.import_module("custom_components.tapo_local.kasa_backend")


class BackendConfigTests(unittest.TestCase):
    def test_switch_config_forces_xor(self) -> None:
        config = backend.xor_device_config("192.0.2.10")
        self.assertEqual(config.host, "192.0.2.10")
        self.assertEqual(
            config.connection_type.device_family,
            DeviceFamily.IotSmartPlugSwitch,
        )
        self.assertEqual(
            config.connection_type.encryption_type,
            DeviceEncryptionType.Xor,
        )
        self.assertIsNone(config.credentials)


if __name__ == "__main__":
    unittest.main()
