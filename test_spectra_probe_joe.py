#!/usr/bin/env python3
"""
Unit tests for J.O.E. CSV parsing and EEPROM correlation in spectra_probe.py.
Verifies robust handling of non-numeric product values, thousands separators,
and mixed delimiters.
"""

import os
import sys
import unittest

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import spectra_probe


class TestSpectraProbeJoe(unittest.TestCase):
    """Test parse_joe_csv_lines and correlate_with_joe resilience."""

    def test_parse_joe_csv_lines_with_formatting_and_non_numeric(self):
        csv_data = [
            "Model Name: Jura ENA 8",
            "Article Number: 15493",
            "",
            "Cockpit",
            "Water Filter,Inserted",
            "Descaling,Not Required",
            "",
            "Maintenance Counter",
            "Filter Change,12",
            "Descaling,1 050",
            "Cleaning,1,234",
            "Rinse Cycle,N/A",
            "",
            "Product Counter",
            "Total Number of Products,5,678",
            "1 Espresso,240",
            "2 Espressi,1 234",
            "1 Coffee,1,500",
            "1 Cappuccino,N/A",
            "1 Flat White,---",
            "1 Hot Water,Unknown",
        ]

        parsed = spectra_probe.parse_joe_csv_lines(csv_data)
        self.assertEqual(parsed["model_name"], "Jura ENA 8")
        self.assertEqual(parsed["article_number"], "15493")
        self.assertEqual(parsed["cockpit"]["Water Filter"], "Inserted")

        # Maintenance items
        self.assertEqual(parsed["maintenance"]["Filter Change"], 12)
        self.assertEqual(parsed["maintenance"]["Descaling"], 1050)
        self.assertEqual(parsed["maintenance"]["Cleaning"], 1234)
        self.assertEqual(parsed["maintenance"]["Rinse Cycle"], "N/A")

        # Products items
        self.assertEqual(parsed["total_products"], 5678)
        self.assertEqual(parsed["products"]["1 Espresso"], 240)
        self.assertEqual(parsed["products"]["2 Espressi"], 1234)
        self.assertEqual(parsed["products"]["1 Coffee"], 1500)
        self.assertEqual(parsed["products"]["1 Cappuccino"], "N/A")
        self.assertEqual(parsed["products"]["1 Flat White"], "---")
        self.assertEqual(parsed["products"]["1 Hot Water"], "Unknown")

    def test_correlate_with_joe_non_numeric_product_values_do_not_crash(self):
        # Simulated EEPROM mapping with words
        eeprom = {
            0x0180: 240,   # 1 Espresso
            0x0181: 1234,  # 2 Espressi
            0x0007: 12,    # Filter Change
        }

        joe_data = {
            "products": {
                "1 Espresso": 240,
                "2 Espressi": 1234,
                "1 Cappuccino": "N/A",         # Non-numeric string value
                "1 Flat White": "Unavailable", # Non-numeric string value
                "1 Hot Water": 0,
            },
            "maintenance": {
                "Filter Change": 12,
                "Descaling": "N/A",
            }
        }

        # Should complete successfully without raising TypeError
        correlations = spectra_probe.correlate_with_joe(eeprom, joe_data)

        # 1 Espresso and 2 Espressi counted, string entries skipped
        summary = correlations["summary"]
        self.assertEqual(summary["total_products_checked"], 3)  # 240, 1234, 0
        self.assertEqual(summary["matched_products"], 2)        # 240 at 0x0180, 1234 at 0x0181

        self.assertEqual(summary["total_maint_checked"], 1)     # 12 counted, 'N/A' skipped
        self.assertEqual(summary["matched_maint"], 1)

        # Check matched products list
        matched_names = [p["name"] for p in correlations["products"] if p["matched"]]
        self.assertIn("1 Espresso", matched_names)
        self.assertIn("2 Espressi", matched_names)


if __name__ == "__main__":
    unittest.main()
