#!/usr/bin/env python3
"""
Regression tests for Tab 02 device-aware telemetry capabilities, honest no-frame handling,
vendor-aware /api/sensors routing, and raw_frames tokenization across all supported protocols.
"""

import json
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import stats_collector as sc
import web_server
from drivers.lamanti_jn.driver import LamantiJNDriver
from drivers.lamanti_kl.driver import LamantiKLDriver
from drivers.nivona.driver import NivonaDriver


class _SilentHardwareConn:
    """Non-demo connection returning no bytes / None to verify honest no-frame handling."""

    def __init__(self, port_name: str = "/dev/ttyUSB0"):
        self.port_name = port_name
        self.is_open = True
        self.is_demo = False
        self.demo_vendor = "hardware"
        self._is_smart_connect = False

    def query_ascii(self, cmd: str, timeout: float = 0.8):
        if cmd == "TY:":
            return "ty:EF533 V01.00"
        return None

    def query_encrypted(self, cmd: str, key: int = 0x42, timeout: float = 1.0):
        return None

    def write(self, data: bytes):
        return len(data)

    def read(self, n: int = 64, timeout_sec: float = 0.8):
        return b""

    def close(self):
        self.is_open = False


class TestTab02TelemetryCapabilities(unittest.TestCase):
    def test_jura_single_dual_and_smart_connect_capabilities(self):
        # Single-heater Jura S8
        s8 = sc.query_live_sensors("DEMO / SIMULATION (Jura S8)", fast_poll=False)
        self.assertEqual(s8["capabilities"]["topology"], "jura_single")
        self.assertTrue(s8["capabilities"]["has_live_frame"])
        self.assertTrue(s8["capabilities"]["has_coffee_temp"])
        self.assertFalse(s8["capabilities"]["has_steam_temp"])
        self.assertEqual(s8["raw_frames"]["primary_cmd"], "HZ:")
        self.assertTrue(len(s8["raw_frames"]["tokens"]) >= 8)

        # Dual-heater Jura Z10
        z10 = sc.query_live_sensors("DEMO / SIMULATION (Jura Z10)", fast_poll=False)
        self.assertEqual(z10["capabilities"]["topology"], "jura_dual")
        self.assertTrue(z10["capabilities"]["has_coffee_temp"])
        self.assertTrue(z10["capabilities"]["has_steam_temp"])
        self.assertIsNotNone(z10["telemetry"]["heater_steam_c"])

        # Smart Connect S8
        sc_res = sc.query_live_sensors("DEMO / SIMULATION (Jura S8 Smart Connect)", fast_poll=False)
        self.assertEqual(sc_res["capabilities"]["topology"], "jura_smart_connect")
        self.assertTrue(sc_res["capabilities"]["has_live_frame"])
        self.assertFalse(sc_res["capabilities"]["has_coffee_temp"])
        self.assertFalse(sc_res["capabilities"]["has_flowmeter"])
        self.assertFalse(sc_res["capabilities"]["has_bu_encoder"])
        self.assertFalse(sc_res["capabilities"]["has_valve_state"])
        self.assertFalse(sc_res["capabilities"]["has_as_shunt"])
        self.assertEqual(sc_res["raw_frames"]["primary_cmd"], "@TF:")

    def test_jura_missing_hz_frame_does_not_claim_ready(self):
        conn = _SilentHardwareConn()
        res = sc.query_live_sensors("/dev/ttyUSB0", conn=conn, fast_poll=True)
        self.assertFalse(res["capabilities"]["has_live_frame"])
        self.assertEqual(res["telemetry"]["machine_state_badge"], "NO FRAME")
        ready_sw = next(s for s in res["switches"] if s["id"] == "machine_ready")
        self.assertFalse(ready_sw["ok"])
        self.assertEqual(ready_sw["badge"], "NO FRAME")

    def test_non_jura_drivers_do_not_fake_temps_on_real_timeout(self):
        dead = _SilentHardwareConn()

        niv = NivonaDriver().read_live_sensors(dead, fast_poll=True)
        self.assertFalse(niv["capabilities"]["has_live_frame"])
        self.assertIsNone(niv["telemetry"]["heater_coffee_c"])
        self.assertEqual(niv["readiness"], "No Live Frame")

        kl = LamantiKLDriver().read_live_sensors(dead, fast_poll=True)
        self.assertFalse(kl["capabilities"]["has_live_frame"])
        self.assertIsNone(kl["telemetry"]["heater_coffee_c"])
        self.assertIsNone(kl["telemetry"]["heater_steam_c"])
        self.assertEqual(kl["readiness"], "No Modbus Reply")

        jn = LamantiJNDriver().read_live_sensors(dead, fast_poll=True)
        self.assertFalse(jn["capabilities"]["has_live_frame"])
        self.assertIsNone(jn["telemetry"]["heater_coffee_c"])
        self.assertIsNone(jn["telemetry"]["heater_steam_c"])
        self.assertIsNone(jn["telemetry"]["pump_pressure_bar"])
        self.assertEqual(jn["readiness"], "No Heartbeat Reply")

    def test_api_sensors_vendor_aware_routing_for_all_demo_topologies(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        port = httpd.server_address[1]
        prev_port = web_server._current_http_port
        web_server._current_http_port = port
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            cases = [
                ("DEMO / SIMULATION (Jura Z10)", "jura_dual"),
                ("DEMO / SIMULATION (Jura S8 Smart Connect)", "jura_smart_connect"),
                ("DEMO / SIMULATION (Nivona NICR768)", "nivona_single"),
                ("DEMO / SIMULATION (Lamanti-KL X680C)", "kalerm_dual"),
                ("DEMO / SIMULATION (Lamanti-JN JL300)", "jetinno_vending"),
            ]
            for demo_port, expected_topo in cases:
                q = urllib.parse.urlencode({"port": demo_port, "fast": "1"})
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sensors?{q}", timeout=10) as resp:
                    self.assertEqual(resp.status, 200)
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(
                        data.get("capabilities", {}).get("topology"),
                        expected_topo,
                        f"Wrong topology for {demo_port}: {data.get('capabilities')}",
                    )
                    self.assertIn("raw_frames", data)
                    self.assertIn("timestamp", data)
        finally:
            web_server._current_http_port = prev_port
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
