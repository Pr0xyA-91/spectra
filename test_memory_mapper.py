#!/usr/bin/env python3
"""
Unit Tests for SPECTRA Developer Memory Mapper & Differential Logic Scope Tool
Validates:
- Register traffic-light categorization (Mapped, Theoretical, Unknown, Blank)
- Complete 512-word EEPROM memory sweeps and block reconstruction
- Baseline snapshot differential detection and bit flip extraction
- Inline mapping persistence into docs/models/<EF>_*.json
- Strict read-only physical appliance safety invariants (no WE:, WT:, DA:)
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

# Ensure repository root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import serial_io
import memory_mapper


class TestMemoryMapperTool(unittest.TestCase):
    """Test suite for developer memory mapping and differential logic scope."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        # Seed test model in tmp_dir
        self.seed_spec = {
            "model_family": "IMPRESSA XJ5 Professional GII",
            "ef_code": "EF518M",
            "series": "IMPRESSA Professional",
            "hardware": {"thermoblocks": 1},
            "custom_registers": {
                "000D": {"name": "Unmapped_0x000D", "description": "Raw 4", "status": "unknown"}
            }
        }
        with open(os.path.join(self.tmp_dir, "EF518M_IMPRESSA_XJ5.json"), "w", encoding="utf-8") as f:
            json.dump(self.seed_spec, f, indent=2)

        self.conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura Impressa XJ5)")
        self.engine = memory_mapper.MemoryMapperEngine(self.conn, models_dir=self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_register_classification(self):
        """Verify 4-tier traffic-light categorization (Mapped, Theoretical, Unknown, Blank)."""
        self.engine.current_eeprom[0x0040] = 1292  # BU_Upper_Limit (Universal)
        self.engine.current_eeprom[0x0020] = 100   # Grinder_Aroma_Ticks (Theoretical)
        self.engine.current_eeprom[0x0120] = 42    # Arbitrary unmapped non-zero (Unknown)
        self.engine.current_eeprom[0x0121] = 0     # Zero register (Blank)

        entries = {r.addr: r for r in self.engine.classify_all()}

        self.assertEqual(entries[0x0040].status, memory_mapper.STATUS_MAPPED)
        self.assertEqual(entries[0x0040].name, "BU_Upper_Limit")

        self.assertEqual(entries[0x0020].status, memory_mapper.STATUS_THEORETICAL)
        self.assertEqual(entries[0x0020].name, "Grinder_Aroma_Ticks")

        self.assertEqual(entries[0x0120].status, memory_mapper.STATUS_UNKNOWN)
        self.assertTrue(entries[0x0120].name.startswith("Unmapped_0x"))

        self.assertEqual(entries[0x0121].status, memory_mapper.STATUS_BLANK)

    def test_full_512_word_sweep(self):
        """Verify complete 512-word sweep (32 blocks) from simulated machine."""
        eeprom = self.engine.sweep_eeprom()
        self.assertEqual(len(eeprom), 512)
        # Verify known block values
        self.assertEqual(eeprom[0x0040], 0x050C)  # 1292 ticks
        self.assertEqual(eeprom[0x0041], 0x00E6)  # 230 ticks

    def test_baseline_and_differential_detection(self):
        """Verify baseline capture and real-time delta and bit-flip detection."""
        self.engine.sweep_eeprom()
        self.engine.capture_baseline()

        # Check no diff initially
        diff_0 = self.engine.compute_diff()
        self.assertEqual(diff_0["total_changed_words"], 0)

        # Simulate change on word 0x0014: baseline 0x0001 -> new 0x0014
        self.conn.set_mock_eeprom_word(0x0014, 0x0014)
        self.engine.sweep_eeprom()
        diff_1 = self.engine.compute_diff()

        self.assertEqual(diff_1["total_changed_words"], 1)
        changed_r = diff_1["changed_registers"][0]
        self.assertEqual(changed_r.addr, 0x0014)
        self.assertEqual(changed_r.val, 0x0014)
        self.assertEqual(changed_r.baseline_val, 0x0001)
        self.assertEqual(changed_r.delta, 19)
        # 0x0001 = 0000 0001, 0x0014 = 0001 0100 -> bit 0 (1->0), bit 2 (0->1), bit 4 (0->1)
        self.assertEqual(sorted(changed_r.bits_flipped), [0, 2, 4])

    def test_map_register_persistence(self):
        """Verify mapping a register persists cleanly into docs/models JSON file and updates status."""
        self.engine.sweep_eeprom()
        stats_before = self.engine.get_summary_stats()

        ok, msg = self.engine.map_register(
            addr=0x0014,
            name="Standby_Auto_Off_Timeout",
            desc="Automatic power-down delay in minutes",
            category="settings",
            unit="min",
            status=memory_mapper.STATUS_MAPPED
        )
        self.assertTrue(ok)
        self.assertIn("Saved 0x0014", msg)

        # Verify in-memory classification immediately reflects change
        entries = {r.addr: r for r in self.engine.classified_registers}
        r = entries[0x0014]
        self.assertEqual(r.status, memory_mapper.STATUS_MAPPED)
        self.assertEqual(r.name, "Standby_Auto_Off_Timeout")
        self.assertEqual(r.unit, "min")

        stats_after = self.engine.get_summary_stats()
        self.assertEqual(stats_after["mapped"], stats_before["mapped"] + 1)

        # Verify disk persistence
        spec_path = os.path.join(self.tmp_dir, "EF518M_IMPRESSA_XJ5.json")
        with open(spec_path, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertIn("0014", disk_data["custom_registers"])
        self.assertEqual(disk_data["custom_registers"]["0014"]["name"], "Standby_Auto_Off_Timeout")

    def test_strict_read_only_safety_invariant(self):
        """Verify tool strictly rejects any write command to protect physical appliance."""
        forbidden_commands = ["WE:00140004", "WT:00001234", "DA:01", "@tw:0102"]
        for cmd in forbidden_commands:
            with self.assertRaises(PermissionError):
                self.engine.query_safe(cmd)


if __name__ == "__main__":
    unittest.main()
