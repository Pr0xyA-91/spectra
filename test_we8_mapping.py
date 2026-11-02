#!/usr/bin/env python3
"""
Unit Tests for Jura WE8 / WE8 (EA) (EF533M / EF535M RL78 platform) Memory Mapping & Statistics Extraction
Validates:
- Article number decoding at 0x007E/0x007F (0x3C3C -> 15420 WE8 (EA))
- Complete 17-beverage register decoding in Block 0x0180 and 0x017F
- Maintenance registers at 0x0007, 0x0008, 0x0009, 0x0020, 0x0021, 0x0022
- Cockpit percentages at 0x0163 (Cleaning 30%), 0x0162 (Descaling 0%), 0x01E1 (Filter 10%)
- Exact numerical parity with official JOE export (WE8.csv)
"""

import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import serial_io
import profiles_db
import stats_collector as sc


class TestWE8Mapping(unittest.TestCase):
    """Test suite for Jura WE8 memory mapping and telemetry."""

    def test_we8_mock_connection(self):
        """Verify WE8 mock serial connection responses."""
        conn = serial_io.JuraSerialConnection("DEMO-WE8")
        self.assertEqual(conn.query_ascii("TY:"), "ty:EF533M V02.09")
        self.assertEqual(conn.query_ascii("TL:"), "tl:BL_RL78 V01.31")
        self.assertEqual(conn.query_ascii("TY$:"), "ty$:EF533D V02.04")
        self.assertEqual(conn.query_ascii("IC:"), "ic:1389")

        # Test block 0x0180 query: 1450, 137, 7233, 117 in hex -> 05AA 0089 1C41 0075
        r_180 = conn.query_ascii("RT:0180")
        self.assertIsNotNone(r_180)
        self.assertTrue(r_180.startswith("rt:05AA00891C410075"))
        conn.close()

    def test_we8_profile_lookup(self):
        """Verify profile database finds WE8 spec and distinguishes from E8."""
        spec = profiles_db.get_model_spec("15420")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.get("model_family"), "WE8")
        self.assertEqual(spec.get("series"), "WE-Line")
        self.assertEqual(spec.get("article_number"), "15420")
        self.assertIn("custom_registers", spec)
        self.assertEqual(spec["custom_registers"]["0180"]["name"], "Total_Espresso")
        self.assertEqual(spec["custom_registers"]["0181"]["name"], "Total_Ristretto")
        self.assertEqual(spec["custom_registers"]["0182"]["name"], "Total_Coffee")

    def test_we8_interrogation_exact_parity(self):
        """Verify full interrogation on WE8 matches JOE export WE8.csv with 100% precision."""
        with sc.JuraStatsSession("DEMO-WE8") as session:
            success = session.run_interrogation()
            self.assertTrue(success)

            # Identification
            self.assertEqual(session.model_family, "WE8 (EA)")
            self.assertEqual(session.telemetry.get("article_number"), "15420")

            # Products: Total: 11,208 preparations, 11,413 cups
            self.assertEqual(session.total_preparations, 11208)
            self.assertEqual(session.total_cups, 11413)

            # All 17 beverages from WE8.csv
            self.assertEqual(session.counters.get(1), 137)     # Ristretto
            self.assertEqual(session.counters.get(2), 1450)    # Espresso
            self.assertEqual(session.counters.get(3), 7233)    # Coffee
            self.assertEqual(session.counters.get(4), 390)     # Cappuccino
            self.assertEqual(session.counters.get(6), 31)      # Macchiato
            self.assertEqual(session.counters.get(7), 50)      # Latte macchiato
            self.assertEqual(session.counters.get(10), 72)     # Portion of milk
            self.assertEqual(session.counters.get(13), 183)    # Hot water
            self.assertEqual(session.counters.get(15), 10)     # Product with ground coffee
            self.assertEqual(session.counters.get(17), 4)      # 2 x Ristretto
            self.assertEqual(session.counters.get(18), 176)    # 2 x Espresso
            self.assertEqual(session.counters.get(19), 20)     # 2 x Coffee
            self.assertEqual(session.counters.get(45), 75)     # Hot water for green tea
            self.assertEqual(session.counters.get(46), 117)    # Flat white
            self.assertEqual(session.counters.get(47), 901)    # Special coffee
            self.assertEqual(session.counters.get(48), 354)    # Espresso doppio
            self.assertEqual(session.counters.get(63), 5)      # 2 x Special coffee

            # Maintenance counters (6 items)
            self.assertEqual(session.maint_counts[0], 74)      # Cleaning
            self.assertEqual(session.maint_counts[1], 0)       # Descaling
            self.assertEqual(session.maint_counts[2], 2268)    # Coffee system rinsing
            self.assertEqual(session.maint_counts[3], 29)      # Filter change
            self.assertEqual(session.maint_counts[4], 775)     # Milk system rinsing
            self.assertEqual(session.maint_counts[5], 377)     # Milk system cleaning

            # Cockpit percentages: [Cleaning, Descaling, Coffee Rinse, Filter Change, Milk Rinse, Milk Clean]
            self.assertEqual(session.maint_pcts[0], 30)   # Cleaning %
            self.assertEqual(session.maint_pcts[1], 0)    # Descaling %
            self.assertIsNone(session.maint_pcts[2])      # Coffee Rinse %
            self.assertEqual(session.maint_pcts[3], 10)   # Filter %


if __name__ == "__main__":
    unittest.main()
