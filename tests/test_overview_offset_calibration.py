#!/usr/bin/env python3
"""Regression tests for Step 1: Overview full 512-word EEPROM calibration & apply_local_offset_override."""

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import profiles_db
import spectra_ai
import spectra_probe
import stats_collector as sc
import web_server
from spectra_web import state as _wstate


def _build_512_word_ena8_eeprom() -> dict:
    """Realistic 512-word EEPROM with beverages across both low (0x0000) and high (0x0180..0x018E) banks."""
    mem = {i: 0 for i in range(512)}
    mem[0x0000] = 1090  # Espresso
    mem[0x0001] = 103   # Ristretto
    mem[0x0007] = 6189  # Coffee system rinsing
    mem[0x0008] = 39    # Cleaning
    mem[0x0009] = 2     # Descaling
    mem[0x0022] = 18    # Filter change
    mem[0x0030] = 41515
    mem[0x0032] = 0x3E2D
    # Upper bank (completely missing from a ~72-word partial interrogation)
    mem[0x0180] = 2487  # Coffee
    mem[0x0181] = 23    # Caffe Barista
    mem[0x0182] = 62    # Espresso doppio (2x)
    mem[0x0183] = 8     # Cappuccino
    mem[0x0184] = 14    # Flat white
    mem[0x0185] = 11    # Cortado
    mem[0x0186] = 5     # Portion of milk foam (non-coffee)
    mem[0x0188] = 10    # Hot water (non-coffee)
    mem[0x0189] = 49    # Product with ground coffee
    return mem


class TestOverviewOffsetCalibration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_ov_file = profiles_db.EEPROM_OVERRIDES_FILE
        profiles_db.EEPROM_OVERRIDES_FILE = os.path.join(self._tmp.name, "eeprom_overrides.json")

    def tearDown(self):
        profiles_db.EEPROM_OVERRIDES_FILE = self._orig_ov_file
        self._tmp.cleanup()

    def test_apply_local_offset_override_hex_addrs_and_new_beverages(self):
        """apply_local_offset_override must parse hex addresses, deduplicate codes, and replace/add all beverages."""
        mem = _build_512_word_ena8_eeprom()
        sess = sc.JuraStatsSession(port_name="DEMO:ENA8")
        sess.ef_code = "EF1012M V01.02"
        sess.model_family = "Generic Jura Automatic"
        sess.is_legacy_cleartext = True
        sess.counters = {1: 103, 2: 0}
        sess.total_cups = 103
        sess.total_preparations = 103
        sess.telemetry = {"article_number": "15339", "cups_since_intervention": 103}
        sess.last_eeprom = dict(mem)

        override = {
            "override_key": "EF1012M",
            "ef_code": "EF1012M V01.02",
            "model_name": "ENA 8 (EA)",
            "article_number": "15339",
            "products": [
                {"code": 1, "name": "Espresso", "addr": "0x0000", "is_double": False},
                {"code": 1, "name": "Ristretto", "addr_hex": "0x0001", "is_double": False},  # intentional code collision
                {"name": "Coffee", "addr": 0x0180, "is_double": False},
                {"name": "Caffe Barista", "addr": "0x0181", "is_double": False},
                {"name": "Espresso doppio", "addr": "0x0182", "is_double": True},
                {"name": "Flat white", "addr_hex": "0x0184", "is_double": False},
                {"name": "Cortado", "addr": "0x0185", "is_double": False},
                {"name": "Portion of milk foam", "addr": "0x0186", "is_double": False},
                {"name": "Hot water", "addr": "0x0188", "is_double": False},
            ],
            "maintenance": [
                {"name": "Cleaning operations", "addr": "0x0008"},
                {"name": "Filter change", "addr_hex": "0x0022"},
            ],
        }

        ok = sess.apply_local_offset_override(override_data=override)
        self.assertTrue(ok)
        summary = sess.get_structured_summary()
        bev_map = {b["name"]: b["count"] for b in summary["beverages"]}

        self.assertEqual(len(summary["beverages"]), 9)
        self.assertEqual(bev_map["Espresso"], 1090)
        self.assertEqual(bev_map["Ristretto"], 103)
        self.assertEqual(bev_map["Coffee"], 2487)
        self.assertEqual(bev_map["Caffe Barista"], 23)
        self.assertEqual(bev_map["Espresso doppio"], 62)
        self.assertEqual(bev_map["Flat white"], 14)
        self.assertEqual(bev_map["Cortado"], 11)
        self.assertEqual(bev_map["Portion of milk foam"], 5)
        self.assertEqual(bev_map["Hot water"], 10)

        # Total preparations includes all 9 beverages; total_cups doubles doppio & excludes milk foam + hot water
        expected_preps = 1090 + 103 + 2487 + 23 + 62 + 14 + 11 + 5 + 10
        expected_cups = 1090 + 103 + 2487 + 23 + (62 * 2) + 14 + 11
        self.assertEqual(summary["total_preparations"], expected_preps)
        self.assertEqual(summary["total_cups"], expected_cups)
        self.assertEqual(sess.telemetry["cups_since_intervention"], expected_cups)
        self.assertEqual(len(sess.profile["products"]), 9)

        maint_map = {m["name"]: m["count"] for m in summary["maintenance"]}
        self.assertEqual(maint_map["Cleaning operations"], 39)
        self.assertEqual(maint_map["Filter change"], 18)

    def test_overview_calibrate_sweeps_full_512_words_when_session_is_partial(self):
        """Overview /api/offsets/calibrate_upload and /api/offsets/calibrate must sweep 512 words even when last_eeprom has ~72 words."""
        full_mem = _build_512_word_ena8_eeprom()
        partial_mem = {addr: full_mem[addr] for addr in range(0x0040)}  # 64 words
        for extra in (0x007E, 0x007F, 0x00C3, 0x00DA, 0x00DB, 0x00DC, 0x00E9, 0x00EA):
            partial_mem[extra] = full_mem[extra]
        self.assertEqual(len(partial_mem), 72)

        joe_csv = "\n".join([
            "Model name: ENA 8 (EA)",
            "Article number: 15339",
            "Maintenance counter",
            "Cleaning operations,39",
            "Filter change,18",
            "Product counter",
            "Espresso,1090",
            "Ristretto,103",
            "Coffee,2487",
            "Caffe Barista,23",
            "Espresso doppio,62",
            "Cappuccino,8",
            "Flat white,14",
            "Cortado,11",
            "Portion of milk foam,5",
            "Hot water,10",
            "Product with ground coffee,49",
        ])

        full_bundle = {
            "metadata": {"timestamp": "2026-11-24T10:00:00", "spectra_build": "20261124.1000", "probe_version": "1.1.0", "port": "DEMO:S8"},
            "identity": {"model_name": "ENA 8 (EA)", "article_number": "15339", "ef_code": "EF1012M V01.02", "address_width": 4, "max_words": 512},
            "gateways": {"TY:": "ty:EF1012M V01.02"},
            "eeprom_words": {f"0x{a:04X}": v for a, v in full_mem.items()},
        }

        sess = sc.JuraStatsSession(port_name="DEMO:S8")
        sess.ef_code = "EF1012M V01.02"
        sess.model_family = "Generic Jura Automatic"
        sess.is_legacy_cleartext = True
        sess.last_eeprom = dict(partial_mem)
        sess.address_width = 4
        sess.telemetry = {"article_number": "15339"}

        orig_sess = _wstate._active_session
        orig_port = _wstate._current_port
        orig_cache = _wstate._last_stats_cache

        server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            _wstate._active_session = sess
            _wstate._current_port = "DEMO:S8"
            _wstate._last_stats_cache = {
                "ef_code": "EF1012M V01.02",
                "model_family": "Generic Jura Automatic",
                "article_number": "15339",
                "total_preparations": 1193,
                "beverages": [{"code": 1, "name": "1 Espresso", "count": 103}],
                "maintenance": [],
            }

            with mock.patch.object(spectra_ai, "is_ai_enabled", return_value=True), \
                 mock.patch.object(spectra_ai, "is_cancel_requested", return_value=False), \
                 mock.patch.object(spectra_ai, "_resolve_active_model", return_value=(True, "mock-llm", "")), \
                 mock.patch.object(spectra_ai, "_query_ollama_json", return_value=({}, "")), \
                 mock.patch.object(spectra_ai, "_maybe_auto_unload", return_value=None), \
                 mock.patch.object(spectra_probe, "capture_machine_bundle", return_value=full_bundle) as mock_sweep:

                # 1. Run Overview calibration via /api/offsets/calibrate (alias of /api/offsets/calibrate_upload)
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/offsets/calibrate",
                    data=json.dumps({
                        "file_name": "joe_ena8.csv",
                        "csv_text": joe_csv,
                        "port": "DEMO:S8",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    cal_res = json.loads(resp.read().decode("utf-8"))

                self.assertTrue(cal_res["success"], cal_res)
                self.assertEqual(mock_sweep.call_count, 1)
                self.assertEqual(cal_res["eeprom_words_scanned"], 512)
                self.assertEqual(len(sess.last_eeprom), 512)
                self.assertEqual(cal_res["matched_products"], 11)
                self.assertEqual(cal_res["matched_maintenance"], 2)
                self.assertEqual(cal_res["preview_before"]["total_preps"], 1193)
                matched_names = {p["name"] for p in cal_res["override"]["products"]}
                self.assertIn("Flat white", matched_names)
                self.assertIn("Cortado", matched_names)
                self.assertIn("Caffe Barista", matched_names)
                self.assertIn("Product with ground coffee", matched_names)

                # 2. Simulate partial last_eeprom again before /api/offsets/apply_local to prove unconditional merge from capture_id
                sess.last_eeprom = dict(partial_mem)
                req_apply = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/offsets/apply_local",
                    data=json.dumps({
                        "capture_id": cal_res["capture_id"],
                        "override": cal_res["override"],
                        "port": "DEMO:S8",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req_apply, timeout=10) as resp:
                    apply_res = json.loads(resp.read().decode("utf-8"))

                self.assertTrue(apply_res["success"], apply_res)
                self.assertEqual(len(sess.last_eeprom), 512)
                updated_bevs = {b["name"]: b["count"] for b in apply_res["updated_stats"]["beverages"]}
                self.assertEqual(updated_bevs["Coffee"], 2487)
                self.assertEqual(updated_bevs["Flat white"], 14)
                self.assertEqual(updated_bevs["Cortado"], 11)
                self.assertEqual(updated_bevs["Espresso"], 1090)
                self.assertEqual(updated_bevs["Product with ground coffee"], 49)
        finally:
            server.shutdown()
            server.server_close()
            _wstate._active_session = orig_sess
            _wstate._current_port = orig_port
            _wstate._last_stats_cache = orig_cache


if __name__ == "__main__":
    unittest.main()
