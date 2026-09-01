import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


APP_PATH = Path(__file__).parents[1] / "aprsgate_dashboard" / "app.py"
SPEC = importlib.util.spec_from_file_location("aprsgate_dashboard_app", APP_PATH)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class AprsisStatusTests(unittest.TestCase):
    def test_verified_requires_log_confirmation_and_active_socket(self):
        lines = [
            "Now connected to IGate server euro.aprs2.net",
            "# logresp N0CALL-10 verified, server T2TEST",
        ]

        status = app.parse_aprsis(lines, "euro.aprs2.net", "91.210.59.134:14580")

        self.assertEqual("verified", status["state"])
        self.assertTrue(status["connected"])
        self.assertTrue(status["verified"])
        self.assertEqual("T2TEST", status["server"])

    def test_active_socket_survives_rotated_startup_logs(self):
        status = app.parse_aprsis(
            ["[ig] N0CALL-10>APDW17:beacon"],
            "euro.aprs2.net",
            "91.210.59.134:14580",
        )

        self.assertEqual("connected", status["state"])
        self.assertTrue(status["connected"])
        self.assertFalse(status["verified"])
        self.assertEqual("euro.aprs2.net", status["server"])

    def test_old_verified_log_does_not_hide_disconnection(self):
        status = app.parse_aprsis(
            ["# logresp N0CALL-10 verified, server T2OLD"],
            "euro.aprs2.net",
            "",
        )

        self.assertEqual("waiting", status["state"])
        self.assertFalse(status["connected"])
        self.assertFalse(status["verified"])

    def test_socket_detection_uses_configured_port(self):
        sockets = "\n".join([
            "0 0 192.0.2.10:22 192.0.2.20:63047",
            "0 0 192.0.2.10:53172 203.0.113.5:14580",
        ])
        with patch.object(app, "run_command", return_value=(sockets, "", 0)):
            endpoint = app.active_aprsis_socket(14580)

        self.assertEqual("203.0.113.5:14580", endpoint)


class DiagnosticsTests(unittest.TestCase):
    def test_nmcli_parser_preserves_escaped_connection_name(self):
        devices = app.parse_nmcli_devices(
            "wlan1:wifi:connected:Amateur\\:Funk\n"
            "lo:loopback:connected (externally):lo"
        )

        self.assertEqual("Amateur:Funk", devices["wlan1"]["connection"])
        self.assertEqual("loopback", devices["lo"]["type"])

    def test_iw_link_parser_extracts_active_wifi_values(self):
        link = app.parse_iw_link(
            "Connected to 00:11:22:33:44:55 (on wlan1)\n"
            "\tSSID: ExampleNet\n"
            "\tfreq: 2437\n"
            "\tsignal: -48 dBm\n"
            "\ttx bitrate: 72.2 MBit/s"
        )

        self.assertEqual("ExampleNet", link["ssid"])
        self.assertEqual("-48", link["signal_dbm"])
        self.assertEqual("72.2 MBit/s", link["tx_bitrate"])

    def test_throttling_decoder_reports_current_and_historic_flags(self):
        flags = app.decode_throttled("throttled=0x50005")

        self.assertIn("Unterspannung aktuell", flags)
        self.assertIn("Throttling aktuell", flags)
        self.assertIn("Unterspannung seit Start", flags)
        self.assertIn("Throttling seit Start", flags)


class MapPayloadTests(unittest.TestCase):
    def packet(self, source, received_at, latitude, longitude, path=""):
        return {
            "source": source,
            "time": received_at,
            "time_local": received_at[:19].replace("T", " "),
            "latitude": latitude,
            "longitude": longitude,
            "path": path,
            "comment": "test",
            "symbol_table": "/",
            "symbol": ">",
        }

    def test_config_position_is_converted_to_decimal_degrees(self):
        latitude, longitude = app.config_position_decimal("51^30.00N 000^07.00W")

        self.assertAlmostEqual(51.5, latitude, places=6)
        self.assertAlmostEqual(-0.116667, longitude, places=6)

    def test_map_aggregates_latest_station_positions_and_tracks(self):
        packets = [
            self.packet("DL1ABC-9", "2026-08-29T11:45:00+00:00", 49.5, 11.2, "DB0VOX*"),
            self.packet("DL1ABC-9", "2026-08-29T11:30:00+00:00", 49.4, 11.1),
            self.packet("N0CALL-10", "2026-08-29T11:20:00+00:00", 51.5, -0.116667),
            self.packet("OLD-1", "2026-08-27T11:20:00+00:00", 48.0, 10.0),
        ]
        config = {
            "callsign": "N0CALL-10",
            "position": "51^30.00N 000^07.00W",
            "frequency": "144.800 MHz",
            "beacon": "",
            "igate_server": "euro.aprs2.net",
            "igate_port": 14580,
        }
        now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)

        with patch.object(app, "stored_packets_with_latest", return_value=packets), patch.object(
            app, "parse_config", return_value=config
        ):
            payload = app.map_payload(24, now=now)

        self.assertEqual(1, payload["summary"]["station_count"])
        feature = payload["stations"]["features"][0]
        self.assertEqual("DL1ABC-9", feature["properties"]["callsign"])
        self.assertEqual("digipeated", feature["properties"]["reception"])
        self.assertEqual(2, feature["properties"]["packet_count"])
        self.assertEqual(2, len(payload["tracks"]["DL1ABC-9"]))
        self.assertEqual("direct", payload["tracks"]["DL1ABC-9"][0]["reception"])
        self.assertEqual("digipeated", payload["tracks"]["DL1ABC-9"][1]["reception"])

    def test_map_callsign_filter_is_case_insensitive(self):
        packets = [
            self.packet("DL1ABC-9", "2026-08-29T11:45:00+00:00", 49.5, 11.2),
            self.packet("DB0VOX", "2026-08-29T11:44:00+00:00", 49.4, 11.0),
        ]
        config = {
            "callsign": "N0CALL-10",
            "position": "51^30.00N 000^07.00W",
            "frequency": "144.800 MHz",
            "beacon": "",
            "igate_server": "euro.aprs2.net",
            "igate_port": 14580,
        }

        with patch.object(app, "stored_packets_with_latest", return_value=packets), patch.object(
            app, "parse_config", return_value=config
        ):
            payload = app.map_payload(
                24,
                "db0",
                now=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(["DB0VOX"], [
            feature["properties"]["callsign"] for feature in payload["stations"]["features"]
        ])


if __name__ == "__main__":
    unittest.main()
