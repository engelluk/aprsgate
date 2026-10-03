import importlib.util
import tempfile
import unittest
from contextlib import nullcontext
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
    def test_offline_signal_overrides_network_manager_connected_state(self):
        with (
            patch.object(portal.os.path, "exists", return_value=True),
            patch.object(portal, "active_ssid", return_value="hechtangels"),
        ):
            self.assertFalse(portal.is_connected())

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

    def test_monitor_leaves_reconnects_to_failover(self):
        class StopMonitor(Exception):
            pass

        with (
            patch.object(portal, "wifi_lock", return_value=nullcontext()),
            patch.object(portal, "is_connected", return_value=False),
            patch.object(portal, "setup_ap_active", return_value=False),
            patch.object(portal, "ensure_setup_ap") as ensure_setup_ap,
            patch.object(portal, "run_nmcli") as run_nmcli,
            patch.object(portal.time, "sleep", side_effect=StopMonitor),
        ):
            with self.assertRaises(StopMonitor):
                portal.monitor_wifi()
        ensure_setup_ap.assert_called_once()
        run_nmcli.assert_not_called()

    def test_new_connection_becomes_failover_primary(self):
        def nmcli(*args, **_kwargs):
            if args[:3] == ("-g", "GENERAL.CONNECTION", "device"):
                return SimpleNamespace(returncode=0, stdout="new-profile\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as directory:
            profile_file = Path(directory) / "primary-profile"
            with (
                patch.object(portal, "PROFILE_FILE", str(profile_file)),
                patch.object(portal, "wifi_lock", return_value=nullcontext()),
                patch.object(portal, "stop_setup_ap"),
                patch.object(portal, "run_nmcli", side_effect=nmcli) as run_nmcli,
            ):
                self.assertEqual("new-ssid", portal.connect_to_network("new-ssid", "secret"))
            self.assertEqual("new-profile\n", profile_file.read_text(encoding="utf-8"))
            run_nmcli.assert_any_call(
                "device", "wifi", "connect", "new-ssid", "ifname", portal.WIFI_DEVICE,
                "password", "secret",
            )


if __name__ == "__main__":
    unittest.main()
