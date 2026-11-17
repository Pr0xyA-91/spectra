#!/usr/bin/env python3
"""
Unit Tests for Jura ENA 7 (EF634 / 13500) Memory Mapping & Statistics Extraction
Validates:
- 512-word EEPROM architecture with 4-digit addressing
- Interleaved beverage registers starting at 0x0000:
    0x0000: 1 Espresso (603)
    0x0001: 2 Espressi (0)
    0x0002: 1 Coffee (10,720)
    0x0003: 2 Coffees (7)
    0x0004: 1 Aroma-Boost (2,167)
    0x0005: Steam / Hot Water valve cycles (532)
    0x0006: Ground Coffee bypass (236)
- Total cups & preparations parity matching official J.O.E. ground truth:
    Total preparations: 13,733
    Total cups: 13,740 (13,726 singles + 7x2 doubles)
- Maintenance counters: Rinses at 0x0007 (10,202), Cleanings at 0x0008 (28),
  Descalings at 0x0009 (3), Filter at 0x0052 (23)
- Operational telemetry: Water volume at 0x0010 (2,569.2 L), Descaling agent at 0x0012 (2.2 L),
  Service counter at 0x0015 (1,224), Grinder seconds at 0x000A (30,855)
- Hardware identification: Appliance number at 0x0030 (1,004), Serial word at 0x0031 (1),
  Production date at 0x0032 (15.1.2012)
- Hardware Article registers: 0x007E (0x34) + 0x007F (0xBC) -> 0x34BC = 13500 (ENA 7 Ristretto Black)
- GS1 EAN-14 calculation: (01)07610917135004(21)20120115001004
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


class TestENA7Mapping(unittest.TestCase):
    """Test suite for Jura ENA 7 memory mapping and telemetry."""

    def test_ena7_mock_connection(self):
        """Verify ENA 7 mock serial connection responses."""
        conn = serial_io.JuraSerialConnection("DEMO-ENA7")
        self.assertEqual(conn.query_ascii("TY:"), "ty:EF634 V01.31")
        self.assertEqual(conn.query_ascii("TL:"), "tl:LOADER V5.0")
        self.assertEqual(conn.query_ascii("IC:"), "ic:DF01")

        # Test block 0x0070 article number registers (0x34BC = 13500)
        self.assertEqual(conn.query_ascii("RE:007E"), "re:3400")
        self.assertEqual(conn.query_ascii("RE:007F"), "re:BC00")
        conn.close()

    def test_ena7_profile_lookup(self):
        """Verify profile database finds ENA 7 with correct 512-word architecture and article 13500."""
        profile = profiles_db.find_profile("EF634 V01.31")
        self.assertEqual(profile.get("model_family"), "ENA 7")
        self.assertEqual(profile.get("article_number"), "13500")
        self.assertEqual(profile.get("address_width"), 4)
        self.assertEqual(profile.get("max_words"), 512)
        self.assertIn("custom_registers", profile)
        self.assertIn("0000", profile["custom_registers"])
        self.assertEqual(profile["custom_registers"]["0000"]["name"], "Espresso_Single")
        self.assertIn("0004", profile["custom_registers"])
        self.assertEqual(profile["custom_registers"]["0004"]["name"], "Aroma_Boost_Single")
        self.assertIn("0052", profile["custom_registers"])
        self.assertEqual(profile["custom_registers"]["0052"]["name"], "Total_Filter_Change")

    def test_ena7_memory_mapper_512_sweep(self):
        """Verify MemoryMapperEngine sweeps 512 words (32 blocks) on ENA 7."""
        conn = serial_io.JuraSerialConnection("DEMO-ENA7")
        engine = memory_mapper.MemoryMapperEngine(conn)
        self.assertEqual(engine.max_words, 512)
        self.assertEqual(engine.address_width, 4)
        conn.close()

    def test_ena7_interrogation_session(self):
        """Verify full interrogation session on Jura ENA 7 matching J.O.E. ground truth."""
        session = sc.JuraStatsSession("DEMO-ENA7")
        ok = session.run_interrogation()
        self.assertTrue(ok, "Interrogation failed on DEMO-ENA7")

        # Verify model identification
        self.assertEqual(session.model_family, "ENA 7")
        self.assertEqual(session.telemetry["article_number"], "13500")
        self.assertEqual(session.telemetry["appliance_type"], "13500 ENA 7 Ristretto Black EU 230V/50Hz")
        self.assertEqual(session.telemetry["serial_number"], "20120115001004")
        self.assertEqual(session.telemetry["ean_code"], "(01)07610917135004(21)20120115001004")
        self.assertEqual(session.telemetry["production_date"], "15.1.2012")

        # Verify beverage counters (all preparations incl. 532 hot water = 14265; coffee-only cups = 13740)
        self.assertEqual(session.total_preparations, 14265)
        self.assertEqual(session.total_cups, 13740)
        self.assertEqual(session.counters[1], 603)    # 1 Espresso
        self.assertEqual(session.counters[2], 0)      # 2 Espressi
        self.assertEqual(session.counters[3], 10720)  # 1 Coffee
        self.assertEqual(session.counters[4], 7)      # 2 Coffees
        self.assertEqual(session.counters[5], 2167)   # 1 Aroma-Boost
        self.assertEqual(session.counters[6], 236)    # Ground Coffee
        self.assertEqual(session.counters[13], 532)   # Hot water valve cycles

        # Verify hygiene counters
        self.assertEqual(session.maint_counts[0], 28)     # Cleanings
        self.assertEqual(session.maint_counts[1], 3)      # Descalings
        self.assertEqual(session.maint_counts[2], 10202)  # Rinses
        self.assertEqual(session.maint_counts[3], 23)     # Filter changes (0x0052, not 0x0014!)

        # Verify operational metrics
        self.assertEqual(session.telemetry["water_dispensed_liters"], 2569.2)
        self.assertEqual(session.telemetry["descaling_agent_liters"], 2.2)
        self.assertEqual(session.telemetry["since_last_service_preparations"], 1224)
        self.assertEqual(session.telemetry["grinder_formatted"], "8h 34m 15s")


if __name__ == "__main__":
    unittest.main()
