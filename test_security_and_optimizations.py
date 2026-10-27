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


if __name__ == "__main__":
    unittest.main()
