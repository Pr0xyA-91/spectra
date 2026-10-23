#!/usr/bin/env python3
"""
Unit and integration tests for temperature decoding, operational thermal evaluation,
and dual-heater thermoblock accommodation in W.R.A.T. (Jura Module).
"""

import sys
import time
import unittest

import stats_collector as sc
import serial_io


class TestJuraThermalAndDualHeaters(unittest.TestCase):

    def test_temperature_decoding_precision(self):
        """Test exact 0.1°C resolution decoding across realistic Jura operating ranges."""
        # 1. Cold water / ambient room temperature
        self.assertEqual(sc.decode_jura_temperature("00E2"), 22.6)
        self.assertEqual(sc.decode_jura_temperature(226), 22.6)
        self.assertEqual(sc.decode_jura_temperature("0x00E4"), 22.8)

        # 2. Coffee Thermoblock active brew temperatures (typically ~90°C to 102°C)
        self.assertEqual(sc.decode_jura_temperature("03C4"), 96.4)
        self.assertEqual(sc.decode_jura_temperature("03AE"), 94.2)
        self.assertEqual(sc.decode_jura_temperature("03B6"), 95.0)
        self.assertEqual(sc.decode_jura_temperature("03E3"), 99.5)
        self.assertEqual(sc.decode_jura_temperature("03EE"), 100.6)

        # 3. Steam Thermoblock active steam temperatures (typically ~125°C to 145°C)
        self.assertEqual(sc.decode_jura_temperature("0546"), 135.0)
        self.assertEqual(sc.decode_jura_temperature(1400), 140.0)

        # 4. Inactive circuits / uninstalled secondary thermoblock values
        # Jura microcontrollers return values >= 1900 (e.g. 0x0802 = 2050) when no sensor is installed
        self.assertIsNone(sc.decode_jura_temperature("0802"))
        self.assertIsNone(sc.decode_jura_temperature(2050))
        self.assertIsNone(sc.decode_jura_temperature("0000"))
        self.assertIsNone(sc.decode_jura_temperature(0))
        self.assertIsNone(sc.decode_jura_temperature(None))
        self.assertIsNone(sc.decode_jura_temperature("invalid"))

    def test_thermoblock_status_evaluation(self):
        """Test plain-language operational status categorization."""
        # Coffee Thermoblock
        self.assertEqual(sc.evaluate_thermoblock_status(96.4, is_steam=False), "Ready to Brew")
        self.assertEqual(sc.evaluate_thermoblock_status(90.0, is_steam=False), "Ready to Brew")
        self.assertEqual(sc.evaluate_thermoblock_status(65.0, is_steam=False), "Heating Up (Coffee)")
        self.assertEqual(sc.evaluate_thermoblock_status(22.0, is_steam=False), "Cold / Standby")
        self.assertEqual(sc.evaluate_thermoblock_status(115.0, is_steam=False), "Steam Purge / Hot")
        self.assertEqual(sc.evaluate_thermoblock_status(None, is_steam=False), "Disconnected / Sensor Fault")

        # Steam Thermoblock
        self.assertEqual(sc.evaluate_thermoblock_status(135.0, is_steam=True), "Ready for Steam")
        self.assertEqual(sc.evaluate_thermoblock_status(80.0, is_steam=True), "Heating Up (Steam)")
        self.assertEqual(sc.evaluate_thermoblock_status(22.0, is_steam=True), "Cold / Standby")
        self.assertEqual(sc.evaluate_thermoblock_status(None, is_steam=True), "Not Installed")

    def test_single_heater_interrogation(self):
        """Test single-heater machine telemetry and register mapping."""
        # Simulated S8 (Single heater)
        res = sc.query_live_sensors("DEMO / SIMULATION (Jura S8)")
        self.assertFalse(res["telemetry"]["is_dual_heater"])
        self.assertEqual(res["telemetry"]["heater_count"], 1)
        self.assertEqual(res["telemetry"]["heater_coffee_str"], "95.0 °C")
        self.assertEqual(res["telemetry"]["heater_coffee_status"], "Ready to Brew")
        self.assertEqual(res["telemetry"]["heater_steam_str"], "Not Installed (Single Heater Model)")
        self.assertEqual(res["telemetry"]["heater_steam_status"], "Not Installed")

        # Verify single-heater fault definitions map to Main Relay and Thermal Overheat
        sensor_names = [s["name"] for s in res["sensors"]]
        self.assertIn("Main Power Relay", sensor_names)
        self.assertIn("Thermal Overheat Protection", sensor_names)
        self.assertNotIn("Steam Thermoblock NTC (Short)", sensor_names)

        # Verify single-heater historical counters
        counter_names = list(res["error_counters"].keys())
        self.assertIn("Main Power Relay Faults", counter_names)
        self.assertIn("Thermal Overheat Safety Cutoffs", counter_names)
        self.assertNotIn("Steam Thermoblock NTC Short Circuits", counter_names)

    def test_dual_heater_interrogation(self):
        """Test dual-heater machine telemetry and dynamic register accommodation."""
        # Simulated Z10 (Dual heater: Coffee + Steam thermoblocks)
        res = sc.query_live_sensors("DEMO / SIMULATION (Jura Z10)")
        self.assertTrue(res["telemetry"]["is_dual_heater"])
        self.assertEqual(res["telemetry"]["heater_count"], 2)
        self.assertEqual(res["telemetry"]["heater_coffee_str"], "94.2 °C")
        self.assertEqual(res["telemetry"]["heater_coffee_status"], "Ready to Brew")
        self.assertEqual(res["telemetry"]["heater_steam_str"], "135.0 °C")
        self.assertEqual(res["telemetry"]["heater_steam_status"], "Ready for Steam")

        # Verify dual-heater fault definitions map to Steam NTC sensors
        sensor_names = [s["name"] for s in res["sensors"]]
        self.assertIn("Coffee Thermoblock NTC (Short)", sensor_names)
        self.assertIn("Coffee Thermoblock NTC (Broken)", sensor_names)
        self.assertIn("Steam Thermoblock NTC (Short)", sensor_names)
        self.assertIn("Steam Thermoblock NTC (Broken)", sensor_names)
        self.assertNotIn("Main Power Relay", sensor_names)

        # Verify dual-heater historical counters
        counter_names = list(res["error_counters"].keys())
        self.assertIn("Coffee Thermoblock NTC Short Circuits", counter_names)
        self.assertIn("Steam Thermoblock NTC Short Circuits", counter_names)
        self.assertIn("Steam Thermoblock NTC Broken Errors", counter_names)
        self.assertNotIn("Main Power Relay Faults", counter_names)

    def test_tray_detection_and_machine_readiness(self):
        """Test accurate detection of removed drip tray and readiness lockout."""
        # 1. Tray Removed telemetry payload
        tray_out_conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        orig_query = tray_out_conn.query_ascii

        def mock_query_out(cmd, timeout=1.0):
            if cmd.strip() == "HZ:":
                return "hz:010001100000,027E,00E2,0000,0398,0802,3,100100,0000,10"
            return orig_query(cmd, timeout=timeout)
        tray_out_conn.query_ascii = mock_query_out

        res = sc.query_live_sensors("mock", conn=tray_out_conn)
        switches = {s["id"]: s for s in res["switches"]}
        self.assertFalse(switches["drip_tray"]["ok"])
        self.assertEqual(switches["drip_tray"]["status"], "Tray Missing / Removed")
        self.assertFalse(switches["machine_ready"]["ok"])
        self.assertEqual(switches["machine_ready"]["status"], "Not Ready (Drip Tray Missing)")

        # 2. Tray Inserted telemetry payload (Nominal)
        def mock_query_in(cmd, timeout=1.0):
            if cmd.strip() == "HZ:":
                return "hz:010001100000,027E,00E2,0000,03CE,0802,4,000000,0000,00"
            return orig_query(cmd, timeout=timeout)
        tray_out_conn.query_ascii = mock_query_in

        res2 = sc.query_live_sensors("mock", conn=tray_out_conn)
        switches2 = {s["id"]: s for s in res2["switches"]}
        self.assertTrue(switches2["drip_tray"]["ok"])
        self.assertEqual(switches2["drip_tray"]["status"], "Tray Inserted")
        self.assertTrue(switches2["machine_ready"]["ok"])
        self.assertEqual(switches2["machine_ready"]["status"], "Ready to Brew / Nominal")

    def test_historical_fault_handling_and_machine_readiness(self):
        """Test that historical EEPROM errors (RE:0028, RE:01B4) do not block live physical readiness."""
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        orig_query = conn.query_ascii

        # Machine has historical flowmeter timeouts (RE:01B4 = 0x0103) and latched fault (RE:0028 = 0x0339)
        # But physically it is hot (0x03C6 = 96.6°C), tray inserted, water present, not busy.
        def mock_query(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "HZ:":
                return "hz:010001100000,027E,00E2,0000,03C6,0802,3,000100,0000,00"
            elif cmd_c == "RE:0028":
                return "re:0339"
            elif cmd_c == "RE:01B4":
                return "re:0103"
            elif cmd_c == "RE:00C3":
                return "re:1E32"
            return orig_query(cmd, timeout=timeout)
        conn.query_ascii = mock_query

        # Manual Refresh (fast_poll=False)
        res_manual = sc.query_live_sensors("mock", conn=conn, fast_poll=False)
        switches = {s["id"]: s for s in res_manual["switches"]}
        self.assertTrue(switches["machine_ready"]["ok"])
        self.assertEqual(switches["machine_ready"]["badge"], "READY")
        self.assertEqual(switches["machine_ready"]["status"], "Ready to Brew / Nominal")
        self.assertTrue(switches["hydraulic_system"]["ok"])
        self.assertEqual(switches["hydraulic_system"]["badge"], "NORMAL")
        self.assertEqual(res_manual["telemetry"]["water_hardness_dh"], 30)
        self.assertEqual(res_manual["telemetry"]["total_fm_timeouts"], 4)

        # Fast Poll (fast_poll=True) - water hardness must be omitted to protect GUI card
        res_fast = sc.query_live_sensors("mock", conn=conn, fast_poll=True)
        self.assertNotIn("water_hardness_dh", res_fast["telemetry"])
        switches_fast = {s["id"]: s for s in res_fast["switches"]}
        self.assertTrue(switches_fast["machine_ready"]["ok"])
        self.assertEqual(switches_fast["machine_ready"]["badge"], "READY")

        # Cold / Heating up machine (Coffee TB = 43.0°C) -> Heating Up status
        def mock_query_cold(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "HZ:":
                return "hz:010001100000,027E,00E2,0000,01AE,0802,3,000000,0000,00"
            return orig_query(cmd, timeout=timeout)
        conn.query_ascii = mock_query_cold

        res_cold = sc.query_live_sensors("mock", conn=conn, fast_poll=True)
        switches_cold = {s["id"]: s for s in res_cold["switches"]}
        self.assertFalse(switches_cold["machine_ready"]["ok"])
        self.assertEqual(switches_cold["machine_ready"]["badge"], "HEATING")
        self.assertIn("Heating Up", switches_cold["machine_ready"]["status"])

    def test_live_water_flow_rate_calculation(self):
        """Test calculation of live water flow in ml/s from flowmeter pulse telemetry."""
        flow_conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        orig_query = flow_conn.query_ascii
        current_hz = ["hz:010001100000,027E,00E2,0000,03CE,0802,3,000000,0000,00"]

        def mock_query(cmd, timeout=1.0):
            if cmd.strip() == "HZ:":
                return current_hz[0]
            elif cmd.strip() == "RE:0028":
                return "re:0000"
            return orig_query(cmd, timeout=timeout)
        flow_conn.query_ascii = mock_query

        # 1. Idle state (0 pulses) -> 0.0 ml/s
        res1 = sc.query_live_sensors("mock_flow", conn=flow_conn)
        self.assertEqual(res1["telemetry"]["flow_pulses"], 0)
        self.assertEqual(res1["telemetry"]["flow_rate_ml_s"], 0.0)
        self.assertEqual(res1["telemetry"]["flow_volume_ml"], 0.0)

        # 2. Dispensing state (0x005E = 94 pulses: 94 / 2.366 ~= 39.7 ml)
        # Seed previous sample so dt is exactly controlled to 2.0s
        sc._last_flowmeter_samples["mock_flow"] = (0, time.time() - 2.0, 0.0)
        current_hz[0] = "hz:010001100000,027E,00E2,005E,03CE,0802,3,000000,0000,00"
        res2 = sc.query_live_sensors("mock_flow", conn=flow_conn)
        self.assertEqual(res2["telemetry"]["flow_pulses"], 94)
        self.assertAlmostEqual(res2["telemetry"]["flow_volume_ml"], 39.7, places=1)
        # 39.7 ml / 2.0s = ~19.9 ml/s
        self.assertGreater(res2["telemetry"]["flow_rate_ml_s"], 18.0)
        self.assertLess(res2["telemetry"]["flow_rate_ml_s"], 22.0)

        # Verify flow sensor entry in sensors list
        flow_sensor = next((s for s in res2["sensors"] if s["id"] == "water_flow"), None)
        self.assertIsNotNone(flow_sensor)
        self.assertIn("ml/s", flow_sensor["status"])


if __name__ == "__main__":
    unittest.main()
