"""Test accurate release descriptions and required README details."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "render_release_notes.py"
spec = importlib.util.spec_from_file_location("release_renderer", SRC)
notes = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(notes)


class ReleaseNotesTests(unittest.TestCase):
    def test_manifest_version_has_plain_english_notes(self):
        manifest = json.loads(
            (ROOT / "custom_components/tapo_local/manifest.json")
            .read_text(encoding="utf-8")
        )
        rendered = notes.render_release_notes(
            manifest["version"],
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
        )
        self.assertIn("Tapo Local " + manifest["version"], rendered)
        self.assertIn("## Helpful links", rendered)
        self.assertIn("### Upgrade notes", rendered)

    def test_release_extraction_does_not_leak_other_versions(self):
        source = "## 1.2.0\n\n- New feature\n\n## 1.1.0\n\n- Old feature\n"
        result = notes.render_release_notes("1.2.0", source)
        self.assertIn("New feature", result)
        self.assertNotIn("Old feature", result)

    def test_missing_blank_duplicate_and_invalid_versions_fail(self):
        for version, content in (
            ("1.0.0", "## 2.0.0\n- Other"),
            ("1.0.0", "## 1.0.0\n\n### Fixed\n"),
            ("1.0.0", "## 1.0.0\n- A\n\n## 1.0.0\n- B"),
            ("1.0", "## 1.0.0\n- A"),
            ("1.0.0", "## 1.0.0\n- TODO"),
        ):
            with self.subTest(version=version, content=content):
                with self.assertRaises(ValueError):
                    notes.render_release_notes(version, content)

    def test_ip_address_help_is_accessible_from_readme_and_support(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        support = (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
        guide = ROOT / "docs" / "FIND_DEVICE_IP.md"
        self.assertTrue(guide.is_file())
        text = guide.read_text(encoding="utf-8")
        self.assertIn("docs/FIND_DEVICE_IP.md", readme)
        self.assertIn("docs/FIND_DEVICE_IP.md", support)
        for required in (
            "MAC address", "DHCP", "Connected Devices", "IPv4",
            "Reconfigure", "DL100", "Wi-Fi", "172.20.0.0/16",
            "Device IP address or hostname", "not", "Default Gateway",
        ):
            self.assertIn(required, text)
        self.assertNotIn("redacted.invalid", text)

    def test_readme_contains_required_live_badges_and_dependency(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        third_party = (ROOT / "THIRD_PARTY.md").read_text(encoding="utf-8")
        manifest = json.loads(
            (ROOT / "custom_components/tapo_local/manifest.json")
            .read_text(encoding="utf-8")
        )
        for label in (
            "github/stars/", "github/forks/", "github/issues/",
            "github/v/release/", "github/license/", "paypal.me/gigabytegrove",
            "hacs_repository.svg", "repository-health.yml/badge.svg",
        ):
            self.assertIn(label, readme)
        self.assertIn("python-kasa>=0.11.0.1", readme)
        self.assertIn("python-kasa>=0.11.0.1", manifest["requirements"])
        self.assertIn("0.11.0.1", third_party)
        self.assertNotIn("redacted.invalid", readme)
        self.assertNotIn("redacted.invalid", third_party)


if __name__ == "__main__":
    unittest.main()
