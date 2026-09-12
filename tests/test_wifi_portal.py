import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
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


class ConnectionSelectionTests(unittest.TestCase):
    def test_known_connections_exclude_setup_and_fallback_profiles(self):
        output = (
            "primary-wifi:802-11-wireless\n"
            "fallback-wifi:802-11-wireless\n"
            "aprsgate-setup-ap:802-11-wireless\n"
            "lo:loopback\n"
        )
        with (
            patch.object(portal, "FALLBACK_CONNECTION", "fallback-wifi"),
            patch.object(
                portal,
                "run_nmcli",
                return_value=SimpleNamespace(returncode=0, stdout=output),
            ),
        ):
            self.assertEqual(["primary-wifi"], portal.known_connections())

    def test_connection_attempt_is_bound_to_portal_device(self):
        result = SimpleNamespace(returncode=0, stdout="")
        with (
            patch.object(portal, "WIFI_DEVICE", "wlan1"),
            patch.object(portal, "known_connections", return_value=["primary-wifi"]),
            patch.object(portal, "is_connected", side_effect=[False, True]),
            patch.object(portal, "run_nmcli", return_value=result) as run_nmcli,
        ):
            self.assertTrue(portal.try_known_connections())
        run_nmcli.assert_called_once_with(
            "connection", "up", "primary-wifi", "ifname", "wlan1"
        )

    def test_connection_loop_stops_when_failover_restores_connectivity(self):
        with (
            patch.object(portal, "known_connections", return_value=["primary-wifi"]),
            patch.object(portal, "is_connected", return_value=True),
            patch.object(portal, "run_nmcli") as run_nmcli,
        ):
            self.assertTrue(portal.try_known_connections())
        run_nmcli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
