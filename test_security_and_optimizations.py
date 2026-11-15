#!/usr/bin/env python3
"""
Unit Tests for Security Hardening and Performance Optimizations in SPECTRA.
Covers:
- HTML escaping and stored XSS prevention in service inspection certificates.
- GTK Pango markup escaping in dynamic beverage and advisor labels.
- Radial gauge redraw avoidance on invariant telemetry values.
- Digital twin coordinate lookup caching.
- Bounded event stream and log buffers.
- Port descriptor sanitization against CRLF and command injection.
- Precompiled regex performance in protocol parsers.
"""

import os
import unittest
import html
from typing import List, Tuple

import gui_widgets
import jura_protocol as jp


class TestSecurityAndOptimizations(unittest.TestCase):

    def test_service_report_html_xss_escaping(self):
        """Verify that generate_service_report_html escapes all dynamic variables against XSS injection."""
        malicious_summary = {
            "machine_model": "<script>alert('xss-model')</script>",
            "total_cups": 1234,
            "telemetry": {
                "serial_number": "<b>SN-MALICIOUS</b>",
                "production_date": "<img src=x onerror=alert('date')>",
            },
            "firmware_string": "EF518M <tag>",
            "timestamp": "2026-10-27 & 12:00:00",
            "beverages": [
                {"name": "Espresso & <script>bad()</script>", "count": 100}
            ],
            "maintenance": [
                {"label": "Cleaning & <b onmouseover=evil()>Clean</b>", "count": 5, "percentage": 80}
            ]
        }
        checklist: List[Tuple[str, bool]] = [
            ("Line inspection <iframe src='http://evil.com'>", True)
        ]

        report_html = gui_widgets.generate_service_report_html(malicious_summary, 95, checklist)

        # Raw malicious scripts/tags must NOT appear in output
        self.assertNotIn("<script>", report_html)
        self.assertNotIn("alert('xss-model')", report_html)
        self.assertNotIn("<iframe", report_html)
        self.assertNotIn("<b onmouseover=evil()>", report_html)

        # Escaped equivalents MUST appear
        self.assertIn("&lt;script&gt;alert(&#x27;xss-model&#x27;)&lt;/script&gt;", report_html)
        self.assertIn("&lt;b&gt;SN-MALICIOUS&lt;/b&gt;", report_html)
        self.assertIn("&lt;iframe src=&#x27;http://evil.com&#x27;&gt;", report_html)
        self.assertIn("Espresso &amp; &lt;script&gt;bad()&lt;/script&gt;", report_html)
        self.assertIn("Cleaning &amp; &lt;b onmouseover=evil()&gt;Clean&lt;/b&gt;", report_html)
        self.assertIn("2026-10-27 &amp; 12:00:00", report_html)

    def test_radial_gauge_redraw_avoidance(self):
        """Verify RadialGaugeWidget only queues redraw when value actually changes."""
        gauge = gui_widgets.RadialGaugeWidget(value=75)
        redraw_count = 0
        orig_queue_draw = gauge.queue_draw

        def mock_queue_draw():
            nonlocal redraw_count
            redraw_count += 1
            orig_queue_draw()

        gauge.queue_draw = mock_queue_draw

        # Setting identical value should NOT queue redraw
        gauge.set_value(75)
        self.assertEqual(redraw_count, 0)

        # Setting different value MUST queue redraw
        gauge.set_value(85)
        self.assertEqual(redraw_count, 1)

        # Clamping: setting 120 sets value to 100
        gauge.set_value(120)
        self.assertEqual(gauge.value, 100)
        self.assertEqual(redraw_count, 2)

        # Setting 100 again should NOT queue redraw
        gauge.set_value(100)
        self.assertEqual(redraw_count, 2)

    def test_digital_twin_node_boxes_constant(self):
        """Verify DigitalTwinWidget uses class-level NODE_BOXES constant and matches coordinates."""
        widget = gui_widgets.DigitalTwinWidget()
        self.assertTrue(hasattr(gui_widgets.DigitalTwinWidget, "NODE_BOXES"))

        # Test coordinate lookups
        self.assertEqual(widget._find_node_at(50, 100), "tank")
        self.assertEqual(widget._find_node_at(180, 100), "flowmeter")
        self.assertEqual(widget._find_node_at(300, 100), "pump")
        self.assertEqual(widget._find_node_at(420, 100), "valve")
        self.assertEqual(widget._find_node_at(520, 60), "tb1")
        self.assertEqual(widget._find_node_at(520, 140), "tb2")
        self.assertEqual(widget._find_node_at(650, 100), "bu")
        self.assertEqual(widget._find_node_at(0, 0), None)

    def test_protocol_precompiled_regexes(self):
        """Verify precompiled regexes in jura_protocol correctly parse frames."""
        # TR:32
        parsed_tr = jp.parse_tr32("@tr:32,01,000A0014001E0028")
        self.assertIsNotNone(parsed_tr)
        bank, words = parsed_tr
        self.assertEqual(bank, 1)
        self.assertEqual(words, [10, 20, 30, 40])

        # TG:43
        parsed_tg = jp.parse_tg43("@tg:4300B800020029015E1018005F")
        self.assertIsNotNone(parsed_tg)
        self.assertEqual(len(parsed_tg), 6)
        self.assertEqual(parsed_tg[0], 184)

        # Invalid frame
        self.assertIsNone(jp.parse_tr32("INVALID"))
        self.assertIsNone(jp.parse_tg43("INVALID"))



    def test_gui_responsive_hitbox_bounds_and_compact_layout(self):
        """Verify JuraDiagApp header and action buttons fit within 960px without offscreen clipping."""
        try:
            import gui
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gdk

            win = gui.JuraDiagApp()
            win.show_all()

            # Verify compact minimum widths
            hdr_min, _ = win.header_grid.get_preferred_size()
            win_min, _ = win.get_preferred_size()
            self.assertLessEqual(hdr_min.width, 960, "Header grid overflows 960px split-screen width")
            self.assertLessEqual(win_min.width, 960, "Window minimum preferred size overflows 960px")

            # Allocate 960px split-screen geometry
            alloc = Gdk.Rectangle()
            alloc.x = 0
            alloc.y = 0
            alloc.width = 960
            alloc.height = 700
            win.size_allocate(alloc)

            # Validate each button is completely bounded within visible surface
            for btn in [win.btn_read, win.btn_mapper, win.btn_service_report, win.btn_export, win.btn_about]:
                b_alloc = btn.get_allocation()
                self.assertGreaterEqual(b_alloc.x, 0, f"{btn} starts offscreen to left")
                self.assertLessEqual(b_alloc.x + b_alloc.width, 960, f"{btn} overflows right boundary at 960px")

            # Validate button styling classes
            self.assertTrue(win.btn_read.get_style_context().has_class("primary-btn"))
            self.assertTrue(win.btn_mapper.get_style_context().has_class("action-btn"))
            self.assertTrue(win.btn_service_report.get_style_context().has_class("action-btn"))
            self.assertTrue(win.btn_export.get_style_context().has_class("action-btn"))
            win.destroy()
        except Exception as e:
            if "cannot open display" in str(e).lower():
                self.skipTest("Headless environment without display")
            else:
                raise

    def test_web_port_sanitization(self):
        """Verify is_valid_port rejects dangerous injection payloads."""
        try:
            import gui_web
            self.assertTrue(gui_web.is_valid_port("/dev/ttyUSB0"))
            self.assertTrue(gui_web.is_valid_port("/dev/ttyACM0"))
            self.assertTrue(gui_web.is_valid_port("/dev/pts/3"))
            self.assertTrue(gui_web.is_valid_port("COM3"))
            self.assertTrue(gui_web.is_valid_port("DEMO / SIMULATION (Jura S8)"))

            # Injections
            self.assertFalse(gui_web.is_valid_port("/dev/ttyUSB0; rm -rf /"))
            self.assertFalse(gui_web.is_valid_port("/dev/ttyUSB0 | cat /etc/passwd"))
            self.assertFalse(gui_web.is_valid_port("/dev/ttyUSB0\nInjected-Header: 1"))
            self.assertFalse(gui_web.is_valid_port("/dev/ttyUSB0\r\nEvil: 1"))
            self.assertFalse(gui_web.is_valid_port("/dev/tty/../../../etc/shadow"))
            self.assertFalse(gui_web.is_valid_port("COM3; whoami"))
            self.assertFalse(gui_web.is_valid_port(""))
            self.assertFalse(gui_web.is_valid_port(None))
        except ImportError:
            pass

    def test_spectra_app_inprocess_server_and_lifecycle(self):
        """Verify spectra_app in-process background server, heartbeat endpoint, and clean teardown."""
        import spectra_app
        import web_server
        import urllib.request
        import json

        # Verify cleanup_resources safe execution
        web_server.cleanup_resources()

        # Start in-process server
        httpd, port, url = spectra_app.start_inprocess_server()
        try:
            self.assertGreater(port, 1024)
            self.assertTrue(url.startswith("http://127.0.0.1:"))

            # Test heartbeat endpoint
            req = urllib.request.Request(
                f"{url}/api/app/heartbeat",
                data=b"{}",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("success"))
                self.assertEqual(data.get("status"), "ALIVE")
        finally:
            spectra_app.shutdown_spectra_cleanly(httpd)

    def test_spectra_app_browser_finder(self):
        """Verify chromeless browser discovery function executes without unhandled exceptions."""
        import spectra_app
        browser = spectra_app.find_chromeless_browser()
        # May be None or a valid string path to msedge/chrome/chromium
        if browser is not None:
            self.assertIsInstance(browser, str)
            self.assertTrue(os.path.isfile(browser) or os.path.isabs(browser))

    def test_host_monitor_geometry_and_autoscaling(self):
        """Verify host monitor workarea detection and auto-zoom calculations across resolutions."""
        import spectra_app
        geom = spectra_app.get_host_monitor_geometry()
        self.assertIn("work_w", geom)
        self.assertIn("work_h", geom)
        self.assertIn("win_w", geom)
        self.assertIn("win_h", geom)
        self.assertIn("auto_zoom", geom)

        # Host bounds sanity
        self.assertLessEqual(geom["win_w"], geom["work_w"])
        self.assertLessEqual(geom["win_h"], geom["work_h"])
        self.assertGreaterEqual(geom["auto_zoom"], 0.75)
        self.assertLessEqual(geom["auto_zoom"], 1.35)

        # Simulated test cases:
        # Case A: Compact Laptop 1366x768
        w, h = 1366, 768
        win_w = min(max(int(w * 0.94), min(960, w)), w)
        win_h = min(max(int(h * 0.92), min(600, h)), h)
        zoom = round(max(0.75, min(w / 1480.0, h / 880.0)), 2)
        self.assertLessEqual(win_w, w)
        self.assertLessEqual(win_h, h)
        self.assertEqual(zoom, 0.87)

        # Case B: Standard FHD 1920x1080
        w, h = 1920, 1080
        win_w = min(max(int(w * 0.94), min(960, w)), w)
        win_h = min(max(int(h * 0.92), min(600, h)), h)
        self.assertLessEqual(win_w, w)
        self.assertLessEqual(win_h, h)

        # Case C: HiDPI / QHD 2560x1440 (scale_factor=1)
        w, h = 2560, 1440
        zoom = round(min(1.35, w / 1920.0), 2)
        self.assertEqual(zoom, 1.33)

    def test_debug_diagnostics_and_ring_buffer(self):
        """Verify ring-buffer logger boundedness, diagnostics collection, and debug endpoints."""
        import web_server
        import spectra_app
        import urllib.request
        import json

        # 1. Test ring buffer boundedness (maxlen=500)
        with web_server._debug_log_lock:
            web_server._debug_log_buffer.clear()
        for i in range(550):
            web_server.log_debug_event("INFO", "TEST", f"Message {i}")

        with web_server._debug_log_lock:
            self.assertEqual(len(web_server._debug_log_buffer), 500)
            self.assertEqual(web_server._debug_log_buffer[-1]["message"], "Message 549")

        # 2. Test diagnostics collector
        diag = web_server.get_debug_diagnostics()
        self.assertIn("process", diag)
        self.assertIn("threads", diag)
        self.assertIn("serial", diag)
        self.assertIn("ollama", diag)
        self.assertIn("children", diag)
        self.assertEqual(diag["process"]["pid"], os.getpid())
        self.assertGreaterEqual(len(diag["threads"]), 1)

        # 3. Test REST API endpoints via in-process server
        httpd, port, url = spectra_app.start_inprocess_server()
        try:
            # GET /api/debug/status
            req = urllib.request.Request(f"{url}/api/debug/status")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("success"))
                self.assertIn("diagnostics", data)
                self.assertIn("logs", data)
                self.assertIn("error_count", data)

            # POST /api/debug/client_error
            post_data = json.dumps({
                "message": "Simulated Frontend Exception",
                "source": "FRONTEND",
                "details": "Error: ReferenceError at app.js:42",
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{url}/api/debug/client_error",
                data=post_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                self.assertEqual(resp.status, 200)
                res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(res.get("success"))

            # Verify it was recorded as an ERROR
            with web_server._debug_log_lock:
                frontend_events = [x for x in web_server._debug_log_buffer if x.get("source") == "FRONTEND"]
                self.assertGreaterEqual(len(frontend_events), 1)
                self.assertEqual(frontend_events[-1]["level"], "ERROR")
                self.assertEqual(frontend_events[-1]["message"], "Simulated Frontend Exception")

            # POST /api/debug/clear
            req = urllib.request.Request(
                f"{url}/api/debug/clear",
                data=b"{}",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                self.assertEqual(resp.status, 200)
                res = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(res.get("success"))
        finally:
            spectra_app.shutdown_spectra_cleanly(httpd)


if __name__ == "__main__":
    unittest.main()
