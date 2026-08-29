import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


PORTAL_PATH = Path(__file__).parents[1] / "aprsgate_dashboard" / "wifi_portal.py"
SPEC = importlib.util.spec_from_file_location("aprsgate_wifi_portal", PORTAL_PATH)
portal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(portal)


class RuntimeConfigTests(unittest.TestCase):
    def test_setup_password_is_required(self):
        with patch.object(portal, "AP_PASSWORD", ""):
            with self.assertRaisesRegex(RuntimeError, "APRSGATE_SETUP_PASSWORD"):
                portal.validate_runtime_config()

    def test_valid_wpa_passphrase_is_accepted(self):
        with patch.object(portal, "AP_PASSWORD", "x" * 20):
            portal.validate_runtime_config()

    def test_valid_raw_wpa_key_is_accepted(self):
        with patch.object(portal, "AP_PASSWORD", "a" * 64):
            portal.validate_runtime_config()


if __name__ == "__main__":
    unittest.main()
