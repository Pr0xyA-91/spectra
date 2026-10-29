#!/usr/bin/env python3
"""
Unit Tests for Jura D4 (EF529M / RL78 platform) Memory Mapping & Statistics Extraction
Validates:
- 1024-word (64 blocks) EEPROM architecture
- Beverage registers in Block 0x0330 (Espresso, Coffee, 2x Espresso, 2x Coffee, Hot water)
- Maintenance registers in Block 0x0000 (Rinses, Cleanings, Descalings, Filter change at 0x000E)
- Operational telemetry in Block 0x0010 (Water volume, Water hardness at 0x0011, Descaling agent, Service counter)
- Identification in Block 0x0030 (Appliance number 52772, Serial word 2, Production date 16.7.2019)
- Exact numerical parity with official JOE export (D4.csv)
"""

import os
import sys
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import serial_io
import profiles_db
import memory_mapper
import stats_collector as sc


class TestD4Mapping(unittest.TestCase):
    """Test suite for Jura D4 memory mapping and telemetry."""

    def test_d4_mock_connection(self):
        """Verify D4 mock serial connection responses."""
        conn = serial_io.JuraSerialConnection("DEMO-D4")
        self.assertEqual(conn.query_ascii("TY:"), "ty:EF529M V01.02")
        self.assertEqual(conn.query_ascii("TL:"), "tl:BL_RL78 V01.30")
        self.assertIsNone(conn.query_ascii("TY$:"))
        self.assertEqual(conn.query_ascii("IC:"), "ic:5700")

        # Test block 0x0330 query
        r_330 = conn.query_ascii("RT:0330")
        self.assertIsNotNone(r_330)
        self.assertTrue(r_330.startswith("rt:080D261B000200030007"))
        conn.close()

    def test_d4_profile_lookup(self):
        """Verify profile database finds D4 with correct 1024-word architecture and article 15221."""
        profile = profiles_db.find_profile("EF529M V01.02")
        self.assertEqual(profile.get("model_family"), "D4")
        self.assertEqual(profile.get("article_number"), "15221")
        self.assertEqual(profile.get("address_width"), 4)
        self.assertEqual(profile.get("max_words"), 1024)
        self.assertIn("custom_registers", profile)
        self.assertIn("0330", profile["custom_registers"])
        self.assertEqual(profile["custom_registers"]["0330"]["name"], "Total_Espresso")

    def test_d4_memory_mapper_1024_sweep(self):
        """Verify MemoryMapperEngine sweeps 1024 words (64 blocks) on D4."""
        conn = serial_io.JuraSerialConnection("DEMO-D4")
        engine = memory_mapper.MemoryMapperEngine(conn)
        self.assertEqual(engine.max_words, 1024)

        eeprom = engine.sweep_eeprom()
        self.assertEqual(len(eeprom), 1024)

        # Check beverage block
        self.assertEqual(eeprom[0x0330], 2061)  # Espresso
        self.assertEqual(eeprom[0x0331], 9755)  # Coffee
        self.assertEqual(eeprom[0x0332], 2)     # 2x Espresso
        self.assertEqual(eeprom[0x0333], 3)     # 2x Coffee
        self.assertEqual(eeprom[0x0334], 7)     # Hot water

        # Check register classification
        entries = {r.addr: r for r in engine.classify_all()}
        self.assertEqual(entries[0x0330].status, memory_mapper.STATUS_MAPPED)
        self.assertEqual(entries[0x0330].name, "Total_Espresso")
        self.assertEqual(entries[0x000E].name, "Total_Filter_Change")
        conn.close()

    def test_d4_interrogation_exact_parity(self):
        """Verify full interrogation on D4 matches JOE export D4.csv with 100% precision."""
        with sc.JuraStatsSession("DEMO-D4") as session:
            success = session.run_interrogation()
            self.assertTrue(success)

            # Identification
            self.assertEqual(session.model_family, "D4")
            self.assertEqual(session.ef_code, "EF529M V01.02")
            self.assertEqual(session.telemetry["article_number"], "15221")
            self.assertEqual(session.telemetry["serial_number"], "20190716052772")
            self.assertEqual(session.telemetry["appliance_number"], 52772)
            self.assertEqual(session.telemetry["production_date"], "16.7.2019")
            self.assertEqual(session.telemetry["water_hardness_dh"], 14)
            self.assertEqual(session.telemetry["ean_code"], "(01)07610917152216(21)20190716052772")

            # Products: Total: 11,828
            self.assertEqual(session.total_preparations, 11828)
            self.assertEqual(session.total_cups, 11833)
            self.assertEqual(session.counters[2], 2061)   # Espresso
            self.assertEqual(session.counters[3], 9755)   # Coffee
            self.assertEqual(session.counters[49], 2)     # 2x Espresso
            self.assertEqual(session.counters[54], 3)     # 2x Coffee
            self.assertEqual(session.counters[13], 7)     # Hot water

            # Maintenance
            self.assertEqual(session.maint_counts[0], 85)     # Cleanings
            self.assertEqual(session.maint_counts[1], 30)     # Descalings
            self.assertEqual(session.maint_counts[2], 15105)  # Rinses
            self.assertEqual(session.maint_counts[3], 1)      # Filter change


if __name__ == "__main__":
    unittest.main()
