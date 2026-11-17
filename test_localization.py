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

    def test_ui_prefs_persistence_roundtrip(self):
        """UI preferences (onboarding_seen, lang) persist across restarts and are exposed in /api/version."""
        import json
        import tempfile
        import threading
        import urllib.request
        import web_server

        with tempfile.TemporaryDirectory() as td:
            prefs_file = Path(td) / "ui_prefs.json"
            with patch("web_server.get_ui_prefs_path", return_value=str(prefs_file)):
                default_prefs = web_server.load_ui_prefs()
                self.assertEqual(default_prefs, {"onboarding_seen": False, "lang": "en"})

                saved = web_server.save_ui_prefs({"onboarding_seen": True, "lang": "cs"})
                self.assertEqual(saved, {"onboarding_seen": True, "lang": "cs"})
                self.assertTrue(prefs_file.is_file())
                self.assertEqual(web_server.load_ui_prefs(), {"onboarding_seen": True, "lang": "cs"})

                httpd = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
                port = httpd.server_address[1]
                t = threading.Thread(target=httpd.serve_forever, daemon=True)
                t.start()
                try:
                    base = f"http://127.0.0.1:{port}"
                    ver = json.loads(urllib.request.urlopen(f"{base}/api/version", timeout=3).read())
                    self.assertEqual(ver.get("ui_prefs"), {"onboarding_seen": True, "lang": "cs"})

                    req = urllib.request.Request(
                        f"{base}/api/ui_prefs",
                        data=json.dumps({"onboarding_seen": False, "lang": "en"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    upd = json.loads(urllib.request.urlopen(req, timeout=3).read())
                    self.assertTrue(upd.get("success"))
                    self.assertEqual(upd.get("prefs"), {"onboarding_seen": False, "lang": "en"})
                finally:
                    httpd.shutdown()
                    httpd.server_close()


if __name__ == "__main__":
    unittest.main()
