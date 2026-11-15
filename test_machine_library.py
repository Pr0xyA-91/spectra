#!/usr/bin/env python3
"""Unit tests for unified SPECTRA Machine Library (`machine_library.py`)."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import machine_library
import profiles_db


class TestMachineLibrary(unittest.TestCase):
    def test_list_machines_precedence_and_connected_match(self):
        with tempfile.TemporaryDirectory() as td:
            ov_path = os.path.join(td, "overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", ov_path):
                profiles_db.save_eeprom_offset_override({
                    "ef_code": "EF634",
                    "article_number": "13500",
                    "model_name": "ENA 7",
                    "products": [{"name": "Espresso", "addr": 0x0000}],
                    "maintenance": [{"name": "Cleaning", "addr": 0x0008}],
                    "notes": "Custom bench override",
                })
                cat = machine_library.list_machines(
                    detected_ef="EF634 V01.31",
                    detected_art="13500",
                    detected_model="ENA 7",
                )

            self.assertGreater(cat["total_machines"], 5)
            self.assertGreaterEqual(cat["verified_specs_count"], 1)
            self.assertEqual(cat["local_overrides_count"], 1)
            match = cat["connected_match"]
            self.assertIsNotNone(match)
            self.assertEqual(match["ef_code"], "EF634")
            self.assertEqual(match["active_source"], "Local Override")
            self.assertTrue(match["is_connected_match"])

    def test_build_and_import_offset_patch_roundtrip(self):
        patch_obj = machine_library.build_offset_patch_payload(
            override={
                "ef_code": "EF525",
                "article_number": "15084",
                "model_name": "Impressa S9 One Touch",
                "products": [{"name": "Espresso", "addr": 0x0010, "joe_count": 250}],
                "maintenance": [{"name": "Descaling", "addr": 0x0024, "joe_count": 5}],
                "notes": "Calibrated via screenshot",
            },
            identity={"ef_code": "EF525", "model_name": "Impressa S9", "serial": "PRIVATE_SERIAL_123"},
        )

        self.assertEqual(patch_obj["schema"], machine_library.SCHEMA_PATCH_V1)
        # Ensure private serial is not leaked in sanitized patch identity
        self.assertNotIn("serial", patch_obj["identity"])

        with tempfile.TemporaryDirectory() as td:
            ov_path = os.path.join(td, "overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", ov_path):
                ok, msg, saved = machine_library.import_offset_patch(json.dumps(patch_obj))
                self.assertTrue(ok, msg)
                self.assertIsNotNone(saved)
                loaded = profiles_db.get_eeprom_offset_override("EF525")
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded["products"][0]["addr"], 0x0010)

    def test_import_rejects_empty_or_invalid_patch(self):
        ok, msg, saved = machine_library.import_offset_patch('{"override": {}}')
        self.assertFalse(ok)
        self.assertIsNone(saved)
        self.assertIn("zero valid", msg)


if __name__ == "__main__":
    unittest.main()
