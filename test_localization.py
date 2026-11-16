import re
import unittest
from pathlib import Path
from unittest.mock import patch

import gui_widgets
import spectra_ai


class TestCzechLocalization(unittest.TestCase):
    def setUp(self):
        self.orig_enabled = spectra_ai._ai_enabled
        self.orig_model = spectra_ai._preferred_model

    def tearDown(self):
        spectra_ai._ai_enabled = self.orig_enabled
        spectra_ai._preferred_model = self.orig_model

    def test_service_report_html_czech(self):
        summary = {
            "machine_model": "Jura IMPRESSA XJ5",
            "total_cups": 1234,
            "beverages": [{"name": "Coffee", "count": 800}],
            "maintenance": [{"label": "Cleanings", "count": 42, "percentage": 55}],
            "telemetry": {"serial_number": "123456"},
        }
        ai_summary = {
            "customer_summary": "Kávovar je ve výborném stavu.",
            "recommended_next_service": "Odvápnění za 3 měsíce.",
        }
        html_cs = gui_widgets.generate_service_report_html(
            summary,
            92,
            [("Kontrola těsnění", True)],
            ai_summary=ai_summary,
            lang="cs",
        )
        self.assertIn('<html lang="cs">', html_cs)
        self.assertIn("Historie připravených nápojů", html_cs)
        self.assertIn("Cykly údržby a hygiena", html_cs)
        self.assertIn("Shrnutí servisu pro zákazníka", html_cs)
        self.assertIn("Doporučený další krok:", html_cs)
        self.assertIn("VÝBORNÝ", html_cs)
        self.assertIn("Káva", html_cs)
        self.assertIn("Čištění", html_cs)

    def test_ai_prompts_respect_czech_lang(self):
        spectra_ai._ai_enabled = True
        captured_prompts = []

        def fake_query(prompt, model, **kwargs):
            captured_prompts.append(prompt)
            return {
                "summary": "Vše je v pořádku.",
                "urgency": "LOW",
                "probable_causes": [],
                "bench_checks": [],
                "customer_summary": "Kávovar funguje správně.",
                "recommended_next_service": "Pravidelné čištění.",
            }, ""

        with patch("spectra_ai._resolve_active_model", return_value=(True, "qwen2.5:0.5b", "")), \
             patch("spectra_ai._query_ollama_json", side_effect=fake_query), \
             patch("spectra_ai._maybe_auto_unload"):
            res_triage = spectra_ai.analyze_fault_triage({"machine_model": "S8"}, {}, lang="cs")
            res_sum = spectra_ai.generate_customer_service_summary({"machine_model": "S8"}, 95, lang="cs")

        self.assertTrue(res_triage["success"])
        self.assertTrue(res_sum["success"])
        self.assertEqual(len(captured_prompts), 2)
        self.assertIn("Czech", captured_prompts[0])
        self.assertIn("Czech", captured_prompts[1])

    def test_frontend_en_and_cs_translation_key_parity(self):
        path = Path(__file__).resolve().parent / "web" / "src" / "i18n" / "translations.js"
        text = path.read_text(encoding="utf-8")

        en_block = re.search(r"\ben:\s*\{(.*?)\n  \},\s*\n\s*cs:", text, re.DOTALL)
        cs_block = re.search(r"\bcs:\s*\{(.*?)\n  \},\s*\n\};", text, re.DOTALL)
        self.assertIsNotNone(en_block)
        self.assertIsNotNone(cs_block)

        key_re = re.compile(r"^\s*([a-zA-Z0-9_]+)\s*:", re.MULTILINE)
        en_keys = set(key_re.findall(en_block.group(1)))
        cs_keys = set(key_re.findall(cs_block.group(1)))

        self.assertEqual(en_keys - cs_keys, set(), f"Missing in cs: {en_keys - cs_keys}")
        self.assertEqual(cs_keys - en_keys, set(), f"Extra in cs: {cs_keys - en_keys}")
        self.assertGreater(len(en_keys), 200)


if __name__ == "__main__":
    unittest.main()
