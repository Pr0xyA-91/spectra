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


if __name__ == "__main__":
    unittest.main()
