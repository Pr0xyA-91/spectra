#!/usr/bin/env python3
"""
Regression test for community-verified Jura E60 (EF532M V01.31, Article 15082)
EEPROM offset calibration harvested from docs/models/EF532M_V01_31_E60.json.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import profiles_db
import stats_collector


class TestE60CommunityCalibration(unittest.TestCase):
    def setUp(self):
        profiles_db.invalidate_model_specs_cache()

    def tearDown(self):
        profiles_db.invalidate_model_specs_cache()

    def test_find_profile_loads_e60_verified_offsets_and_sibling_revision(self):
        prof = profiles_db.find_profile("EF532M V01.31")
        self.assertEqual(prof.get("model_family"), "E60")
        self.assertEqual(prof.get("article_number"), "15082")
        verified = prof.get("verified_offsets")
        self.assertIsInstance(verified, dict)
        self.assertEqual(len(verified.get("products", [])), 7)
        self.assertEqual(len(verified.get("maintenance", [])), 6)

        # Sibling firmware minor revision should resolve via base EF532M index
        sibling = profiles_db.find_profile("EF532M V01.32")
        self.assertIsInstance(sibling.get("verified_offsets"), dict)
        self.assertEqual(len(sibling["verified_offsets"].get("products", [])), 7)

    def test_stats_collector_decodes_e60_community_offsets(self):
        # Isolate from any user-local ~/.config/spectra/eeprom_overrides.json
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_overrides = os.path.join(tmpdir, "eeprom_overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", fake_overrides):
                session = stats_collector.JuraStatsSession(port_name="DEMO:E60")
                session.ef_code = "EF532M V01.31"
                session.profile = profiles_db.find_profile(session.ef_code)
                session.model_family = session.profile.get("model_family", "E60")
                session.telemetry = {
                    "serial_number": "LIVE-CONNECTED-SERIAL",
                    "article_number": "15082",
                }

                e60_eeprom = {
                    # 7 beverages
                    0x0180: 2316,   # Espresso
                    0x0182: 650,    # Coffee
                    0x0184: 616,    # Cappuccino
                    0x0187: 3514,   # Portion of milk foam (non-coffee)
                    0x0188: 264,    # Hot water (non-coffee)
                    0x0189: 12309,  # 2 x Espresso (double)
                    0x018B: 78,     # 2 x Coffee (double)
                    # 6 maintenance counters
                    0x0007: 13852,  # Coffee system rinsing operations
                    0x0008: 55,     # Cleaning operations
                    0x0009: 16,     # Descaling operations
                    0x0020: 3627,   # Milk system rinsing operations
                    0x0021: 24,     # Milk system cleaning operations
                    0x0022: 36,     # Filter change
                }

                applied = session.apply_local_offset_override(e60_eeprom, article_num="15082")
                self.assertTrue(applied)

                # Identity of live connected machine must NOT be overwritten
                self.assertEqual(session.telemetry.get("serial_number"), "LIVE-CONNECTED-SERIAL")
                self.assertEqual(session.telemetry.get("article_number"), "15082")

                self.assertIsNotNone(session.offset_override_info)
                self.assertEqual(session.offset_override_info.get("source"), "community_verified")
                self.assertEqual(session.offset_override_info.get("products_mapped"), 7)
                self.assertEqual(session.offset_override_info.get("maintenance_mapped"), 6)

                # 2316 + 650 + 616 + 3514 + 264 + 12309 + 78 = 19747
                self.assertEqual(session.total_preparations, 19747)
                # Coffee cups: 2316 + 650 + 616 + 2*(12309 + 78) = 28356 (excludes milk foam & hot water)
                self.assertEqual(session.total_cups, 28356)

                self.assertEqual(len(session.override_products), 7)
                self.assertEqual(session.counters[1], 2316)
                self.assertEqual(session.counters[2], 650)
                self.assertEqual(session.counters[3], 616)
                self.assertEqual(session.counters[4], 3514)
                self.assertEqual(session.counters[5], 12309)
                self.assertEqual(session.counters[6], 78)
                self.assertEqual(session.counters[7], 264)

                self.assertEqual(session.maint_counts, [55, 36, 16, 13852, 3627, 24])
                self.assertEqual(
                    session.override_maint_labels,
                    [
                        "Cleaning operations",
                        "Filter change",
                        "Descaling operations",
                        "Coffee system rinsing operations",
                        "Milk system rinsing operations",
                        "Milk system cleaning operations",
                    ],
                )

    def test_stats_collector_decodes_we6_community_offsets_and_maint_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_overrides = os.path.join(tmpdir, "eeprom_overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", fake_overrides):
                prof = profiles_db.get_model_spec("15417")
                self.assertIsNotNone(prof)
                self.assertEqual(prof.get("ef_code"), "EF532M V02.03")
                self.assertEqual(prof.get("model_family"), "WE6 (EA)")

                session = stats_collector.JuraStatsSession(port_name="DEMO:WE6")
                session.ef_code = "EF532M V02.03"
                session.profile = profiles_db.find_profile(session.ef_code)
                session.model_family = prof.get("model_family", "WE6 (EA)")
                session.telemetry = {
                    "serial_number": "LIVE-WE6-SERIAL",
                    "article_number": "15417",
                }

                we6_eeprom = {
                    0x0001: 389,    # Ristretto
                    0x0180: 7505,   # Espresso
                    0x0182: 10103,  # Coffee
                    0x0188: 62,     # Hot water (non-coffee)
                    0x0189: 2227,   # 2 x Espresso
                    0x018B: 224,    # 2 x Coffee
                    0x0007: 4216,   # Coffee system rinsing operations
                    0x0008: 33,     # Cleaning operations
                    0x0009: 31,     # Descaling operations
                    0x0022: 3,      # Filter change
                    0x002E: 0x3C64, # Cleaning & Descaling 100% (low byte 0x64 = 100)
                }

                applied = session.apply_local_offset_override(we6_eeprom, article_num="15417")
                self.assertTrue(applied)
                self.assertEqual(session.offset_override_info.get("source"), "community_verified")
                self.assertEqual(session.offset_override_info.get("products_mapped"), 6)
                self.assertEqual(session.offset_override_info.get("maintenance_mapped"), 4)

                # 389 + 7505 + 10103 + 2227 + 62 + 224 = 20510
                self.assertEqual(session.total_preparations, 20510)
                # Coffee cups: 389 + 7505 + 10103 + 2*(2227 + 224) = 22899 (excludes Hot water 62)
                self.assertEqual(session.total_cups, 22899)

                self.assertEqual(session.maint_counts, [33, 3, 31, 4216])
                self.assertEqual(session.maint_pcts, [100, None, 100, None])

    def test_article_first_ef532m_disambiguation_across_sibling_firmware(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_overrides = os.path.join(tmpdir, "eeprom_overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", fake_overrides):
                # Sibling firmware EF532M V02.04 with article 15417 must resolve WE6 (EA), NOT E60
                sess_we6 = stats_collector.JuraStatsSession(port_name="DEMO:WE6")
                sess_we6.ef_code = "EF532M V02.04"
                sess_we6.profile = profiles_db.find_profile("EF532M V02.04")
                sess_we6.telemetry = {"article_number": "15417"}
                we6_eeprom = {
                    0x0001: 10,
                    0x0180: 20,
                    0x0182: 30,
                    0x0188: 5,
                    0x0189: 2,
                    0x018B: 3,
                    0x0007: 100,
                    0x0008: 4,
                    0x0009: 2,
                    0x0022: 1,
                    0x002E: 0x0050,
                }
                self.assertTrue(sess_we6.apply_local_offset_override(we6_eeprom, article_num="15417"))
                self.assertEqual(sess_we6.offset_override_info.get("products_mapped"), 6)
                self.assertEqual(sess_we6.offset_override_info.get("maintenance_mapped"), 4)
                self.assertEqual(sess_we6.total_preparations, 70)
                self.assertEqual(sess_we6.total_cups, 70)

                # Sibling firmware EF532M V01.99 with article 15082 must resolve E60, NOT WE6
                sess_e60 = stats_collector.JuraStatsSession(port_name="DEMO:E60")
                sess_e60.ef_code = "EF532M V01.99"
                sess_e60.profile = profiles_db.find_profile("EF532M V01.99")
                sess_e60.telemetry = {"article_number": "15082"}
                e60_eeprom = {
                    0x0180: 10,
                    0x0182: 20,
                    0x0184: 5,
                    0x0187: 3,
                    0x0188: 2,
                    0x0189: 1,
                    0x018B: 2,
                    0x0007: 50,
                    0x0008: 2,
                    0x0009: 1,
                    0x0020: 12,
                    0x0021: 4,
                    0x0022: 3,
                }
                self.assertTrue(sess_e60.apply_local_offset_override(e60_eeprom, article_num="15082"))
                self.assertEqual(sess_e60.offset_override_info.get("products_mapped"), 7)
                self.assertEqual(sess_e60.offset_override_info.get("maintenance_mapped"), 6)
                self.assertEqual(sess_e60.total_preparations, 43)
                self.assertEqual(sess_e60.total_cups, 41)


if __name__ == "__main__":
    unittest.main()
