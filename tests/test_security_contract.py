"""Offline DL100 sensitive-output and dependency security invariants."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class SecurityContracts(unittest.TestCase):
    def test_private_sessions_and_redacted_exceptions(self):
        source = (ROOT / "custom_components/tapo_local/__init__.py").read_text()
        self.assertIn("private=True", source)
        self.assertNotIn("automatic session provisioning failed: {exc}", source)
        self.assertNotIn("local session is invalid: {exc}", source)

    def test_dependency_range(self):
        manifest = json.loads((ROOT / "custom_components/tapo_local/manifest.json").read_text())
        self.assertIn("python-kasa>=0.11.0.1,<0.13.0", manifest["requirements"])

if __name__ == "__main__":
    unittest.main()
