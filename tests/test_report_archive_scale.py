#!/usr/bin/env python3
"""
Scale & Performance Benchmark Test for report_archive.py (15,000+ Reports):
- Verifies SQLite WAL mode & PRAGMAs
- Inserts 15,000 synthetic diagnostic reports in a single batch transaction
- Verifies indexed serial_number lookup < 20 ms
- Verifies FTS5 full-text search < 30 ms
- Verifies keyset cursor pagination across pages without duplicates or skips
"""

import os
import sqlite3
import sys
import tempfile
import time
import unittest

import report_archive


class TestReportArchiveScale(unittest.TestCase):
    def test_15000_reports_wal_fts5_indexed_lookup_and_cursor_pagination(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "reports_index.sqlite3")
            report_archive.init_archive(db_path=db_path)

            # Verify WAL journal mode
            conn = sqlite3.connect(db_path)
            try:
                j_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
                self.assertEqual(str(j_mode).lower(), "wal")
            finally:
                conn.close()

            # Insert 15,000 synthetic reports in a single transaction
            base_ts = 1700000000.0
            records = []
            for i in range(15000):
                sn = f"SN-JURA-{i % 500:04d}"
                art = f"15{i % 90:03d}"
                tkt = f"TKT-{i:05d}"
                model = "Jura Z10" if i % 2 == 0 else "Jura WE8"
                summary = (
                    "Descaling valve ultrasonic flush anomaly detected"
                    if i % 75 == 0
                    else f"Routine telemetry check cycle {i}"
                )
                records.append({
                    "created_at": base_ts + i,
                    "report_type": "service_report" if i % 3 == 0 else "export_json",
                    "ticket_prefix": tkt,
                    "manufacturer": "Jura",
                    "model_name": model,
                    "ef_code": "EF545" if i % 2 == 0 else "EF533M",
                    "article_number": art,
                    "serial_number": sn,
                    "total_cups": 1000 + i,
                    "health_score": 80 + (i % 20),
                    "filename": f"{tkt}_spectra_report.html",
                    "blob_sha256": f"{i:064x}",
                    "blob_path": "",
                    "summary_text": summary,
                })

            t_ins0 = time.perf_counter()
            inserted = report_archive.archive_reports_batch(records, db_path=db_path)
            insert_ms = (time.perf_counter() - t_ins0) * 1000.0
            self.assertEqual(inserted, 15000)

            # Warm SQLite page cache once, then benchmark indexed serial lookup (< 20 ms)
            report_archive.search_reports(serial_number="SN-JURA-0042", limit=50, db_path=db_path)
            t_ser0 = time.perf_counter()
            ser_res = report_archive.search_reports(serial_number="SN-JURA-0042", limit=50, db_path=db_path)
            serial_ms = (time.perf_counter() - t_ser0) * 1000.0
            self.assertEqual(ser_res["count"], 30)  # 15000 / 500 = 30
            self.assertLess(serial_ms, 20.0, f"Indexed serial lookup took {serial_ms:.2f} ms")

            # Benchmark FTS5 full-text search (< 30 ms)
            report_archive.search_reports(query="ultrasonic anomaly", limit=50, db_path=db_path)
            t_fts0 = time.perf_counter()
            fts_res = report_archive.search_reports(query="ultrasonic anomaly", limit=50, db_path=db_path)
            fts_ms = (time.perf_counter() - t_fts0) * 1000.0
            self.assertEqual(fts_res["count"], 50)
            self.assertIsNotNone(fts_res["next_cursor"])
            self.assertLess(fts_ms, 30.0, f"FTS5 search took {fts_ms:.2f} ms")

            # Verify cursor pagination returns exact contiguous slices with zero duplicates
            seen_ids = []
            cursor = None
            pages = 0
            while True:
                page = report_archive.search_reports(
                    query="ultrasonic anomaly", limit=60, cursor=cursor, db_path=db_path
                )
                pages += 1
                seen_ids.extend(item["id"] for item in page["items"])
                cursor = page["next_cursor"]
                if not cursor:
                    break
            self.assertEqual(len(seen_ids), 200)  # 15000 / 75 = 200
            self.assertEqual(len(set(seen_ids)), 200)
            self.assertEqual(seen_ids, sorted(seen_ids, reverse=True))
            print(
                f"\n[BENCHMARK 15k] batch_insert={insert_ms:.1f}ms | "
                f"serial_lookup={serial_ms:.2f}ms | fts5_search={fts_ms:.2f}ms | pages={pages}"
            )


if __name__ == "__main__":
    unittest.main()
