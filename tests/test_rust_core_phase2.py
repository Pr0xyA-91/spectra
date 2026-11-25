import unittest
from datetime import datetime
from unittest.mock import patch

import jura_protocol
import machine_library
import spectra_probe
import spectra_py
import stats_collector


class TestRustCorePhase2(unittest.TestCase):
    def test_wire_codec_roundtrip_and_remainder(self):
        payload = b"TY:\r\n"
        encoded = spectra_py.encode_jura_wire_bytes(payload)
        self.assertEqual(len(encoded), len(payload) * 4)

        # Partial trailing bytes must stay in remainder
        decoded, remainder = spectra_py.decode_jura_wire_bytes(encoded + b"\xff\xee")
        self.assertEqual(decoded, payload)
        self.assertEqual(remainder, b"\xff\xee")

        # Wrapper cross-codec parity (Rust 0x5B carrier and Python 0xDB carrier both decode identically)
        self.assertEqual(jura_protocol.encode_wire(payload), encoded)
        self.assertEqual(jura_protocol.decode_wire(encoded + b"\xff\xee"), (payload, b"\xff\xee"))
        with patch.object(jura_protocol, "HAS_RUST_CORE", False):
            py_encoded = jura_protocol.encode_wire(payload)
            self.assertEqual(len(py_encoded), len(encoded))
            self.assertEqual(spectra_py.decode_jura_wire_bytes(py_encoded), (payload, b""))
            self.assertEqual(jura_protocol.decode_wire(encoded + b"\xff\xee"), (payload, b"\xff\xee"))

    def test_temperature_and_date_word_decoders_and_parity(self):
        self.assertEqual(spectra_py.decode_jura_temperature_word(924), 92.4)
        self.assertEqual(spectra_py.decode_jura_temperature_word(226), 22.6)
        self.assertIsNone(spectra_py.decode_jura_temperature_word(0))
        self.assertIsNone(spectra_py.decode_jura_temperature_word(2050))

        self.assertEqual(stats_collector.decode_jura_temperature("039C"), 92.4)
        self.assertEqual(stats_collector.decode_jura_temperature("00E2"), 22.6)
        with patch.object(stats_collector, "HAS_RUST_CORE", False):
            self.assertEqual(stats_collector.decode_jura_temperature("039C"), 92.4)
            self.assertEqual(stats_collector.decode_jura_temperature("00E2"), 22.6)

        # Packed date: (year - 1990) << 9 | (month << 5) | day -> 2024-02-29 leap year
        leap_word = (34 << 9) | (2 << 5) | 29
        self.assertEqual(spectra_py.decode_jura_date_word(leap_word), (2024, 2, 29))
        self.assertEqual(stats_collector.decode_jura_date(leap_word), datetime(2024, 2, 29))

        # Invalid non-leap-year Feb 29 (2023) returns None
        bad_feb = (33 << 9) | (2 << 5) | 29
        self.assertIsNone(spectra_py.decode_jura_date_word(bad_feb))
        self.assertIsNone(stats_collector.decode_jura_date(bad_feb))

        with patch.object(stats_collector, "HAS_RUST_CORE", False):
            self.assertEqual(stats_collector.decode_jura_date(leap_word), datetime(2024, 2, 29))
            self.assertIsNone(stats_collector.decode_jura_date(bad_feb))

    def test_correlate_with_joe_ranked_and_parity(self):
        # Product category prefers [0x0180..0x018F] over 0x0002
        eeprom_int = {0x0002: 420, 0x0182: 420, 0x0007: 100, 0x0200: 100}
        ranked_prod = spectra_py.correlate_with_joe_ranked(eeprom_int, 420, "product")
        self.assertEqual(ranked_prod, ["0x0182", "0x0002"])

        # Maintenance category prefers [0x0007..0x0009] over 0x0200
        ranked_maint = spectra_py.correlate_with_joe_ranked(eeprom_int, 100, "maintenance")
        self.assertEqual(ranked_maint, ["0x0007", "0x0200"])

        # spectra_probe wrapper parity
        joe_data = {"products": {"Espresso": 420}, "maintenance": {"Cleanings": 100}}
        rust_res = spectra_probe.correlate_with_joe(eeprom_int, joe_data)
        with patch.object(spectra_probe, "HAS_RUST_CORE", False):
            py_res = spectra_probe.correlate_with_joe(eeprom_int, joe_data)
        self.assertEqual(rust_res, py_res)
        self.assertEqual(rust_res["products"][0]["suggested_address"], "0x0182")
        self.assertEqual(rust_res["maintenance"][0]["suggested_address"], "0x0007")

    def test_machine_matching_and_parity(self):
        self.assertTrue(
            spectra_py.machine_matches_connected("EF535M", ["15141"], "Jura WE8", " ef535m ", "", "")
        )
        self.assertTrue(
            spectra_py.machine_matches_connected("EF535M", ["15141"], "Jura WE8", "", "15141", "")
        )
        self.assertTrue(
            spectra_py.machine_matches_connected("EF535M", ["15141"], "WE8", "", "", "Jura WE8 Chrome")
        )
        self.assertFalse(
            spectra_py.machine_matches_connected("EF535M", ["15141"], "WE8", "EF518M", "15084", "Impressa XJ5")
        )

        entry = {
            "ef_code": "EF535M",
            "article_numbers": ["15141"],
            "model_family": "WE8",
        }
        self.assertTrue(machine_library._matches_connected(entry, " ef535m ", "", ""))
        with patch.object(machine_library, "HAS_RUST_CORE", False):
            self.assertTrue(machine_library._matches_connected(entry, " ef535m ", "", ""))
            self.assertFalse(machine_library._matches_connected(entry, "EF999", "", ""))


if __name__ == "__main__":
    unittest.main()
