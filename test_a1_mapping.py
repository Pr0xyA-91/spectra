#!/usr/bin/env python3
"""
Unit Tests for Jura A1 (EF509M / Renesas R8C platform) Memory Mapping & Statistics Extraction
Validates:
- 256-word (16 blocks) EEPROM architecture with 2-digit addressing
- Beverage registers: Coffee at 0x0002 (1,954), Espresso at 0x0004 (2,234), Ristretto at 0x0006 (477)
- Total cups parity: 4,665 single preparations == 4,665 total cups (no double-cup dispensing)
- Maintenance registers: Rinses at 0x0007 (4,618), Cleanings at 0x0008 (30), Descalings at 0x0009 (7), Filter at 0x0014 (90)
- Operational telemetry: Water volume at 0x0010 (828.7 L), Descaling agent at 0x0012 (4.8 L), Service counter at 0x0015 (5,043)
- Hardware identification: Appliance number at 0x0030 (45,753), Serial word at 0x0031 (450), Production date at 0x0032 (11.12.2017)
- Hardware Article registers: 0x007E (0x3B) + 0x007F (0x1D) -> 0x3B1D = 15133 (A1 Piano Black)
- GS1 EAN-14 calculation: (01)07610917151332(21)20171211045753
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


class TestA1Mapping(unittest.TestCase):
    """Test suite for Jura A1 memory mapping and telemetry."""

    def test_a1_mock_connection(self):
        """Verify A1 mock serial connection responses."""
        conn = serial_io.JuraSerialConnection("DEMO-A1")
        self.assertEqual(conn.query_ascii("TY:"), "ty:EF509M V01.26")
        self.assertEqual(conn.query_ascii("TL:"), "tl:R8C Loader V1.04")
        self.assertIsNone(conn.query_ascii("TY$:"))
        self.assertEqual(conn.query_ascii("IC:"), "ic:AC03")

        # Test block 0x70 article number registers
        r_70 = conn.query_ascii("RT:70")
        self.assertIsNotNone(r_70)
        self.assertTrue(r_70.endswith("3B001D00"))
        self.assertEqual(conn.query_ascii("RE:7E"), "re:3B00")
        self.assertEqual(conn.query_ascii("RE:7F"), "re:1D00")
        conn.close()

    def test_a1_profile_lookup(self):
        """Verify profile database finds A1 with correct 256-word architecture and article 15133."""
        profile = profiles_db.find_profile("EF509M V01.26")
        self.assertEqual(profile.get("model_family"), "A1")
        self.assertEqual(profile.get("article_number"), "15133")
        self.assertEqual(profile.get("address_width"), 2)
        self.assertEqual(profile.get("max_words"), 256)
        self.assertIn("custom_registers", profile)
        self.assertIn("0004", profile["custom_registers"])
        self.assertEqual(profile["custom_registers"]["0004"]["name"], "Total_Espresso")

    def test_a1_memory_mapper_256_sweep(self):
        """Verify MemoryMapperEngine sweeps 256 words (16 blocks) on A1."""
        conn = serial_io.JuraSerialConnection("DEMO-A1")
        engine = memory_mapper.MemoryMapperEngine(conn)
        self.assertEqual(engine.max_words, 256)
        self.assertEqual(engine.address_width, 2)
        conn.close()

    def test_a1_interrogation_session(self):
        """Verify full interrogation session on Jura A1."""
        session = sc.JuraStatsSession("DEMO-A1")
        ok = session.run_interrogation()
        self.assertTrue(ok, "Interrogation failed on DEMO-A1")

        # Verify model identification
        self.assertEqual(session.model_family, "A1")
        self.assertEqual(session.telemetry["article_number"], "15133")
        self.assertEqual(session.telemetry["appliance_type"], "15133 A1 Piano Black")
        self.assertEqual(session.telemetry["serial_number"], "20171211045753")
        self.assertEqual(session.telemetry["ean_code"], "(01)07610917151332(21)20171211045753")
        self.assertEqual(session.telemetry["production_date"], "11.12.2017")
        self.assertEqual(session.telemetry["software_version_display"], "N/A (Symbol Display)")

        # Verify beverage counters (single-cup parity: preps == cups)
        self.assertEqual(session.total_preparations, 4665)
        self.assertEqual(session.total_cups, 4665)
        self.assertEqual(session.counters[1], 477)    # Ristretto
        self.assertEqual(session.counters[2], 2234)   # Espresso
        self.assertEqual(session.counters[3], 1954)   # Coffee

        # Verify hygiene counters
        self.assertEqual(session.maint_counts[0], 30)    # Cleanings
        self.assertEqual(session.maint_counts[1], 7)     # Descalings
        self.assertEqual(session.maint_counts[2], 4618)  # Rinses
        self.assertEqual(session.maint_counts[3], 90)    # Filter changes

        # Verify operational metrics
        self.assertEqual(session.telemetry["water_dispensed_liters"], 828.7)
        self.assertEqual(session.telemetry["descaling_agent_liters"], 4.8)
        self.assertEqual(session.telemetry["since_last_service_preparations"], 5043)
        self.assertEqual(session.telemetry["grinder_formatted"], "2h 56m 30s")

    def test_a1_gs1_checksum(self):
        """Verify GS1 Modulo-10 checksum algorithm for A1 Article 15133."""
        base_ean = "0761091715133"
        chk = sc.calculate_gs1_check_digit(base_ean)
        self.assertEqual(chk, 2)
        self.assertEqual(f"{base_ean}{chk}", "07610917151332")


if __name__ == "__main__":
    unittest.main()
