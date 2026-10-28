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
        # 1. Cold / standby thermoblock temperature
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
        self.assertNotIn("ambient_temp_c", res["telemetry"])
        self.assertIn("bu_encoder_pos", res["telemetry"])
        self.assertIn("bu_encoder_upper", res["telemetry"])

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

    def test_brew_unit_dynamic_position_zones(self):
        """Test dynamic Brew Unit mechanical zone and stroke percentage evaluation."""
        # 1. Home / Mill Position (RE:0041 target = 229)
        zone, short, pct = sc.evaluate_brew_unit_position(229, 648, mill_target=229, init_ok=True)
        self.assertEqual(zone, "Home / Mill Position")
        self.assertEqual(short, "Home / Mill")
        self.assertEqual(pct, 0)

        # 2. Tamping / Pre-Brew Travel (~380 ticks)
        zone, short, pct = sc.evaluate_brew_unit_position(380, 648, mill_target=229, init_ok=True)
        self.assertEqual(zone, "Tamping / Pre-Brew Travel")
        self.assertEqual(short, "Tamping / Travel")
        self.assertGreater(pct, 20)
        self.assertLess(pct, 50)

        # 3. Brewing / Compression (~579 ticks)
        zone, short, pct = sc.evaluate_brew_unit_position(579, 648, mill_target=229, init_ok=True)
        self.assertEqual(zone, "Brewing / Compression")
        self.assertEqual(short, "Brewing / Compress")
        self.assertGreater(pct, 70)

        # 4. Upper / Eject & Rinse (~646-648 ticks)
        zone, short, pct = sc.evaluate_brew_unit_position(646, 648, mill_target=229, init_ok=True)
        self.assertEqual(zone, "Upper / Eject & Rinse")
        self.assertEqual(short, "Upper / Eject")
        self.assertEqual(pct, 100)

        # 5. Dynamic movement direction indicator
        zone_up, short_up, _ = sc.evaluate_brew_unit_position(350, 648, mill_target=229, delta_ticks=12)
        self.assertIn("Moving ▲", zone_up)
        self.assertIn("Moving ▲", short_up)

        zone_down, short_down, _ = sc.evaluate_brew_unit_position(350, 648, mill_target=229, delta_ticks=-12)
        self.assertIn("Moving ▼", zone_down)
        self.assertIn("Moving ▼", short_down)

        # 6. Position Fault / Not Initialized
        zone_fault, short_fault, pct_fault = sc.evaluate_brew_unit_position(229, 648, init_ok=False)
        self.assertEqual(zone_fault, "Init / Position Fault")
        self.assertEqual(pct_fault, 0)

    def test_bean_hopper_optical_sensor_and_readiness(self):
        """Test optical bean hopper sensor ADC decoding, readiness blocking, and cake measurement."""
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        orig_query = conn.query_ascii

        # 1. Empty Bean Hopper: AS: returns ON_ADC = 0x0700 (1792 decimal > 1680)
        def mock_query_empty(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077206980000,077207000001"
            elif cmd_c == "HZ:":
                # Machine heated, tray inserted, water present, cake thickness = 14 ticks (empty grind)
                return "hz:010001100000,027E,00E2,0000,03C6,0802,3,000000,000E,00"
            return orig_query(cmd, timeout=timeout)
        conn.query_ascii = mock_query_empty

        res_empty = sc.query_live_sensors("mock_bean", conn=conn, fast_poll=False)
        switches_empty = {s["id"]: s for s in res_empty["switches"]}

        # Bean Hopper switch must indicate empty
        self.assertFalse(switches_empty["bean_hopper"]["ok"])
        self.assertEqual(switches_empty["bean_hopper"]["badge"], "FILL BEANS")
        self.assertIn("Fill Beans", switches_empty["bean_hopper"]["status"])

        # Machine readiness must be blocked
        self.assertFalse(switches_empty["machine_ready"]["ok"])
        self.assertEqual(switches_empty["machine_ready"]["badge"], "FILL BEANS")
        self.assertEqual(switches_empty["machine_ready"]["status"], "Not Ready (Fill Beans)")

        # Alert must be generated
        alert_names = [a["name"] for a in res_empty["alerts"]]
        self.assertIn("Fill Beans", alert_names)

        # 2. Charged Bean Hopper: AS: returns ON_ADC = 0x061C (1564 decimal <= 1680)
        def mock_query_full(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077206450000,0772061C0001"
            elif cmd_c == "HZ:":
                # Machine heated, tray inserted, water present, cake thickness = 29 ticks (thick puck)
                return "hz:010001100000,027E,00E2,0000,03C6,0802,3,000000,001D,00"
            return orig_query(cmd, timeout=timeout)
        conn.query_ascii = mock_query_full

        res_full = sc.query_live_sensors("mock_bean", conn=conn, fast_poll=False)
        switches_full = {s["id"]: s for s in res_full["switches"]}

        # Bean Hopper switch must indicate nominal
        self.assertTrue(switches_full["bean_hopper"]["ok"])
        self.assertEqual(switches_full["bean_hopper"]["badge"], "NORMAL")
        self.assertIn("Beans OK", switches_full["bean_hopper"]["status"])

        # Machine readiness must be ready
        self.assertTrue(switches_full["machine_ready"]["ok"])
        self.assertEqual(switches_full["machine_ready"]["badge"], "READY")
        self.assertEqual(switches_full["machine_ready"]["status"], "Ready to Brew / Nominal")

        # Telemetry should capture cake thickness and optical ADCs
        self.assertEqual(res_full["telemetry"]["cake_thickness_ticks"], 29)
        self.assertEqual(res_full["telemetry"]["bean_adcs"], (1605, 1564))

        # Optical Bean Sensor entry should be in diagnostic sensor list
        opt_sensor = next((s for s in res_full["sensors"] if s["id"] == "optical_bean_sensor"), None)
        self.assertIsNotNone(opt_sensor)
        self.assertTrue(opt_sensor["ok"])
        self.assertIn("Reflected IR ADC: 1564", opt_sensor["details"])

    def test_bean_hopper_fast_poll_telemetry(self):
        """Test continuous fast-poll bean hopper detection from active AS: sensor query."""
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        orig_query = conn.query_ascii

        # 1. Fast poll with hopper empty (AS: on_adc = 1792 >= 1710)
        def mock_query_empty(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077206980000,077207000001"
            elif cmd_c == "HZ:":
                return "hz:010001100000,027E,00E2,0000,03C6,0802,3,000000,000E,00"
            return orig_query(cmd, timeout=timeout)
        conn.query_ascii = mock_query_empty

        res_empty = sc.query_live_sensors("mock_fast_bean", conn=conn, fast_poll=True)
        sw_empty = {s["id"]: s for s in res_empty["switches"]}
        self.assertFalse(res_empty["telemetry"]["beans_ok"])
        self.assertFalse(sw_empty["bean_hopper"]["ok"])
        self.assertEqual(sw_empty["bean_hopper"]["badge"], "FILL BEANS")
        self.assertFalse(sw_empty["machine_ready"]["ok"])
        self.assertEqual(sw_empty["machine_ready"]["badge"], "FILL BEANS")
        self.assertEqual(sw_empty["machine_ready"]["status"], "Not Ready (Fill Beans)")
        self.assertIn("Fill Beans", [a["name"] for a in res_empty["alerts"]])

        # 2. Fast poll with hopper charged (AS: on_adc = 1564 < 1710)
        conn_full = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        orig_query_full = conn_full.query_ascii

        def mock_query_full(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077206450000,0772061C0001"
            elif cmd_c == "HZ:":
                return "hz:010001100000,027E,00E2,0000,03C6,0802,3,000000,001D,00"
            return orig_query_full(cmd, timeout=timeout)
        conn_full.query_ascii = mock_query_full

        res_full = sc.query_live_sensors("mock_fast_bean", conn=conn_full, fast_poll=True)
        sw_full = {s["id"]: s for s in res_full["switches"]}
        self.assertTrue(res_full["telemetry"]["beans_ok"])
        self.assertTrue(sw_full["bean_hopper"]["ok"])
        self.assertEqual(sw_full["bean_hopper"]["badge"], "NORMAL")
        self.assertTrue(sw_full["machine_ready"]["ok"])
        self.assertEqual(sw_full["machine_ready"]["badge"], "READY")

    def test_optical_bean_sensor_ambient_light_and_standby_tolerance(self):
        """Test that optical bean detection uses ambient-compensated delta and ignores standby noise."""
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")

        # Case 1: High ambient room light (e.g. hopper lid open under bright light):
        # off_adc = 2244, on_adc = 2328 -> delta = 84 counts (beans present, absorbed IR)
        # Even though on_adc > 1700 (2328), delta <= 89 correctly identifies beans present!
        def mock_ambient(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077308C40000,077309180001"  # 0x08C4=2244, 0x0918=2328 -> delta=84
            elif cmd_c == "HZ:":
                return "hz:010001100000,028A,00E5,006D,03EF,0802,3,000000,001F,00"
            return ""
        conn.query_ascii = mock_ambient

        res_amb = sc.query_live_sensors("mock_amb", conn=conn, fast_poll=True)
        self.assertTrue(res_amb["telemetry"]["beans_ok"])
        sw_amb = {s["id"]: s for s in res_amb["switches"]}
        self.assertTrue(sw_amb["bean_hopper"]["ok"])
        self.assertEqual(sw_amb["bean_hopper"]["badge"], "NORMAL")

        # Case 2: Machine enters standby (floating unpowered ADC noise: off=6103, on=6467 > 3500)
        # Should reject invalid ADCs and preserve cached beans_ok=True
        def mock_standby(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077317D70000,077319430001"  # Floating standby noise
            elif cmd_c == "HZ:":
                return "hz:000000100000,028A,00E6,0000,0202,0802,3,000000,0000,10"
            return ""
        conn.query_ascii = mock_standby

        res_sb = sc.query_live_sensors("mock_standby", conn=conn, fast_poll=True)
        self.assertTrue(res_sb["telemetry"]["beans_ok"])
        sw_sb = {s["id"]: s for s in res_sb["switches"]}
        self.assertTrue(sw_sb["bean_hopper"]["ok"])

        # Case 3: Empty hopper bare terminal reflection (delta >= 96, e.g. 104)
        conn_empty = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        def mock_empty(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077206980000,077207000001"  # 0x0698=1688, 0x0700=1792 -> delta=104 >= 96
            elif cmd_c == "HZ:":
                return "hz:010101100000,028A,00E5,006D,03EF,0802,3,000000,001F,00"
            return ""
        conn_empty.query_ascii = mock_empty

        res_emp = sc.query_live_sensors("mock_empty", conn=conn_empty, fast_poll=True)
        self.assertFalse(res_emp["telemetry"]["beans_ok"])
        sw_emp = {s["id"]: s for s in res_emp["switches"]}
        self.assertFalse(sw_emp["bean_hopper"]["ok"])
        self.assertEqual(sw_emp["bean_hopper"]["badge"], "FILL BEANS")
        self.assertFalse(sw_emp["machine_ready"]["ok"])
        self.assertEqual(sw_emp["machine_ready"]["badge"], "FILL BEANS")
        self.assertTrue(any(a["name"] == "Fill Beans" for a in res_emp["alerts"]))

        # Case 4: IMPRESSA XJ5 (EF518M) live operating condition:
        # HZ[0][3] == '1' during thermal regulation, but hopper is filled with beans (delta=88 <= 92).
        # Live invariant: Optical AS: is the ground truth. Beans MUST be reported OK and ready.
        conn_xj5 = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        def mock_xj5(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                return "as:077205C70000,0772061F0001"  # 0x05C7=1479, 0x061F=1567 -> delta=88 <= 92
            elif cmd_c == "HZ:":
                return "hz:010101100000,0289,00E5,006D,03EE,0802,3,000000,001E,00"
            return ""
        conn_xj5.query_ascii = mock_xj5

        res_xj5 = sc.query_live_sensors("mock_xj5", conn=conn_xj5, fast_poll=True)
        self.assertTrue(res_xj5["telemetry"]["beans_ok"])
        sw_xj5 = {s["id"]: s for s in res_xj5["switches"]}
        self.assertTrue(sw_xj5["bean_hopper"]["ok"])
        self.assertEqual(sw_xj5["bean_hopper"]["badge"], "NORMAL")
        self.assertTrue(sw_xj5["machine_ready"]["ok"])
        self.assertEqual(sw_xj5["machine_ready"]["badge"], "READY")


    def test_ascii_and_smart_connect_counter_mapping(self):
        """Test that ASCII EEPROM mode and Smart Connect mode map maintenance and beverage labels accurately."""
        # 1. ASCII EEPROM Demo (S8)
        sess_ascii = sc.JuraStatsSession("DEMO / SIMULATION (Jura S8)")
        self.assertTrue(sess_ascii.run_interrogation())
        sum_ascii = sess_ascii.get_structured_summary()
        maint_ascii = {m["label"]: m["count"] for m in sum_ascii["maintenance"]}
        self.assertEqual(maint_ascii.get("Cleaning"), 166)
        self.assertEqual(maint_ascii.get("Descaling"), 38)
        self.assertEqual(maint_ascii.get("Rinsing"), 3609)
        self.assertEqual(maint_ascii.get("Filter Change"), 1)
        # Machine is ready to brew, so historical RE:0028 faults should not pollute active alerts
        self.assertEqual(len(sum_ascii["alerts"]), 1)
        self.assertFalse(sum_ascii["alerts"][0]["blocking"])

        # 2. Smart Connect Encrypted Demo (S8 Smart Connect)
        sess_sc = sc.JuraStatsSession("DEMO / SIMULATION (Jura S8 Smart Connect)")
        self.assertTrue(sess_sc.run_interrogation())
        sum_sc = sess_sc.get_structured_summary()
        self.assertIn("Smart Connect", sum_sc["protocol_mode"])
        maint_sc = {m["label"]: (m["count"], m["percentage"]) for m in sum_sc["maintenance"]}
        self.assertEqual(maint_sc.get("Cleaning"), (184, 85))
        self.assertEqual(maint_sc.get("FilterChange"), (2, 25))
        self.assertEqual(maint_sc.get("Decalc"), (41, 95))

    def test_optical_bean_calibration_and_dev_slider(self):
        """Test optical bean sensor threshold calibration and dev branch UI toggle."""
        # 1. Verify default calibration (nominal 99 counts)
        sc.reset_optical_bean_threshold(save=False)
        self.assertEqual(sc.get_optical_bean_threshold(), 99)
        calib = sc.get_optical_bean_calibration()
        self.assertEqual(calib["lower_bound"], 97)
        self.assertEqual(calib["upper_bound"], 101)

        # 2. Delta of 105 with default threshold (99) -> Empty (105 >= 101)
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        orig_query = conn.query_ascii
        def mock_query(cmd, timeout=1.0):
            cmd_c = cmd.strip()
            if cmd_c == "AS:":
                # off_adc = 1600, on_adc = 1705 -> delta = 105
                return "as:077206400000,077206A90001"
            elif cmd_c == "HZ:":
                return "hz:010001100000,027E,00E2,0000,03C6,0802,3,000000,001D,00"
            return orig_query(cmd, timeout=timeout)
        conn.query_ascii = mock_query

        res_default = sc.query_live_sensors("mock_calib", conn=conn, fast_poll=True)
        self.assertFalse(res_default["telemetry"]["beans_ok"])

        # 3. Adjust threshold to 110 (bounds 108 / 112) -> Beans OK (105 <= 108)
        sc.set_optical_bean_threshold(110, save=False)
        self.assertEqual(sc.get_optical_bean_threshold(), 110)
        res_calib = sc.query_live_sensors("mock_calib", conn=conn, fast_poll=True)
        self.assertTrue(res_calib["telemetry"]["beans_ok"])
        self.assertEqual(res_calib["telemetry"]["optical_threshold"], 110)
        self.assertEqual(res_calib["telemetry"]["optical_delta"], 105)

        # 4. Reset threshold back to 99
        sc.reset_optical_bean_threshold(save=False)
        self.assertEqual(sc.get_optical_bean_threshold(), 99)

        # 5. Verify dev branch GUI slider availability
        import gui
        self.assertTrue(gui.is_dev_branch())
        app = gui.JuraDiagApp()
        self.assertTrue(hasattr(app, "card_dev_calib"))
        self.assertEqual(app.scale_bean_threshold.get_value(), 99.0)

        # Changing slider updates calibration
        app.scale_bean_threshold.set_value(120.0)
        self.assertEqual(sc.get_optical_bean_threshold(), 120)
        app._on_reset_bean_calibration_clicked(None)
        self.assertEqual(sc.get_optical_bean_threshold(), 99)
        app.destroy()

    def test_z5_two_digit_addressing_and_ean_decoding(self):
        """Test Top-Tronic 8-bit EEPROM 2-digit addressing, Z5 Gen II identification, and full EAN generation."""
        conn = serial_io.JuraSerialConnection(port_name="DEMO:Z5")

        def mock_z5_query(cmd, timeout=1.0):
            c = cmd.strip()
            if c == "TY:":
                return "ty:EF642M V01.12"
            if c == "TY$:":
                return "ty$:EF642D V01.04"
            if c == "IC:":
                return "ic:230V 50Hz"
            if c == "RT:00":
                return "rt:1ECB112605CE0023005D00D800023D3B005F001800000000000000000000003D"
            if c == "RT:10":
                return "rt:82F1000000E90000000013B70000000000000000000000000000000000000000"
            if c == "RT:20":
                return "rt:00000000003F0000000000000000000000000000000000000000000000000000"
            if c == "RT:30":
                return "rt:07DD000426B90000000000000000000000000000000000000000000000000000"
            if c == "RT:E0":
                # Doubles: 0xE0=91, 0xE1=345, 0xE2=11, 0xE3=1, 0xE4=6, 0xE5=3, 0xE9=0, 0xEA=9957 (0x26E5)
                return "rt:005B0159000B000100060003000000000000000026E500000000000000000000"
            if c == "RE:30":
                return "re:07DD"
            if c == "RE:31":
                return "re:0004"
            if c == "RE:32":
                return "re:26B9"
            if c == "RE:15":
                return "re:13B7"
            if c == "RE:E9":
                return "re:0000"
            if c == "RE:EA":
                return "re:26E5"
            if c == "HZ:":
                return "hz:010001100000,027E,00E2,0000,03C6,0802,3,000000,001D,00"
            if c == "AS:":
                return "as:077206400000,077206450001"
            return None

        conn.query_ascii = mock_z5_query

        session = sc.JuraStatsSession(port_name="mock_z5")
        session.conn = conn
        success = session.run_interrogation()
        self.assertTrue(success)

        summary = session.get_structured_summary()
        telem = summary["telemetry"]

        self.assertEqual(summary["machine_model"], "IMPRESSA Z5 Generation II")
        self.assertEqual(telem["article_number"], "13356")
        self.assertEqual(telem["serial_number"], "20090525002013")
        self.assertEqual(telem["serial_number_word"], 4)
        self.assertEqual(telem["appliance_number"], 2013)
        self.assertEqual(telem["production_date"], "25.5.2009")
        self.assertEqual(telem["appliance_code"], "07DD26B9")
        self.assertEqual(telem["ean_code"], "(01)07610917133567(21)20090525002013")
        self.assertEqual(telem["software_version_display"], "EF642D V01.04")
        self.assertEqual(telem["total_preparations"], 14562)
        self.assertEqual(telem["total_cups"], 15019)
        self.assertEqual(telem["preparations_since_intervention"], 5047)
        self.assertEqual(telem["cups_since_intervention"], 5062)


if __name__ == "__main__":
    unittest.main()
