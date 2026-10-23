#!/usr/bin/env python3
"""
Unit and integration tests for temperature decoding, operational thermal evaluation,
and dual-heater thermoblock accommodation in Jura Modern Diag.
"""

import sys
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

        # 2. Tray Inserted telemetry payload
        def mock_query_in(cmd, timeout=1.0):
            if cmd.strip() == "HZ:":
                return "hz:010001100000,027E,00E2,0000,03CE,0802,4,000100,0000,00"
            return orig_query(cmd, timeout=timeout)
        tray_out_conn.query_ascii = mock_query_in

        res2 = sc.query_live_sensors("mock", conn=tray_out_conn)
        switches2 = {s["id"]: s for s in res2["switches"]}
        self.assertTrue(switches2["drip_tray"]["ok"])
        self.assertEqual(switches2["drip_tray"]["status"], "Tray Inserted")
        self.assertTrue(switches2["machine_ready"]["ok"])
        self.assertEqual(switches2["machine_ready"]["status"], "Ready to Brew / Nominal")


if __name__ == "__main__":
    unittest.main()
