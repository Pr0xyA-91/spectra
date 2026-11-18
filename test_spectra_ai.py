#!/usr/bin/env python3
"""
Unit tests for SPECTRA opt-in Local AI orchestration (`spectra_ai.py`),
SPECTRA-themed Firmware Inspector HTML report generation (`hmi_inspector.py`),
and customer AI summary embedding in `gui_widgets.generate_service_report_html`.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import gui_widgets
import hmi_inspector
import spectra_ai
from test_hmi_inspector import create_synthetic_elf_binary


class _FakeHttpResponse(io.BytesIO):
    def __init__(self, payload: dict, status: int = 200):
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class TestSpectraAiOrchestrator(unittest.TestCase):
    def setUp(self):
        with spectra_ai._ai_lock:
            spectra_ai._ai_enabled = False
            spectra_ai._preferred_model = ""
            spectra_ai._auto_unload = True
            spectra_ai._task_state.update({
                "active": False,
                "task_id": "",
                "task_label": "",
                "step": "IDLE",
                "detail": "",
                "current": 0,
                "total": 0,
                "percent": 0,
                "eta_seconds": None,
                "model": "",
                "cancel_requested": False,
                "error": "",
                "started_at": 0.0,
            })

    def tearDown(self):
        with patch.object(hmi_inspector.KalermHmiInspector, "control_local_ollama", return_value={"status": "STOPPED"}):
            spectra_ai.set_ai_enabled(False)

    def test_default_state_is_off(self):
        """AI must default to OFF so it does not consume RAM/CPU on startup."""
        self.assertFalse(spectra_ai.is_ai_enabled())

    def test_resolve_active_model_accepts_control_start_success_status(self):
        """When Ollama daemon is offline and control_local_ollama('start') returns SUCCESS, resolution succeeds."""
        spectra_ai._ai_enabled = True
        calls = {"n": 0}

        def fake_chk(timeout=0.5):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"available": False, "models": []}
            return {"available": True, "models": [{"name": "qwen2.5:1.5b"}]}

        with patch.object(hmi_inspector.KalermHmiInspector, "check_local_ollama", side_effect=fake_chk), patch.object(
            hmi_inspector.KalermHmiInspector,
            "control_local_ollama",
            return_value={"status": "SUCCESS", "message": "Embedded Ollama daemon started"},
        ) as mock_ctrl:
            ok, model_name, err = spectra_ai._resolve_active_model()

        self.assertTrue(ok)
        self.assertEqual(model_name, "qwen2.5:1.5b")
        self.assertIsNone(err)
        mock_ctrl.assert_called_once_with("start")

    def test_update_ai_config_persists_model_without_enabling_ai(self):
        """update_ai_config updates default model and auto_unload while keeping AI OFF."""
        with tempfile.TemporaryDirectory() as td:
            cfg_file = os.path.join(td, "ai_config.json")
            with patch.object(spectra_ai, "AI_CONFIG_FILE", cfg_file), patch.object(
                hmi_inspector.KalermHmiInspector,
                "get_ai_system_status",
                return_value={"hardware": {"default_selected_model": "qwen2.5:0.5b"}},
            ), patch.object(
                hmi_inspector.KalermHmiInspector,
                "get_ollama_download_progress",
                return_value={"active": False},
            ):
                res = spectra_ai.update_ai_config(model="qwen2.5:3b", auto_unload=False)
                self.assertTrue(res["success"])
                self.assertFalse(res["ai_enabled"])
                self.assertEqual(res["preferred_model"], "qwen2.5:3b")
                self.assertFalse(res["auto_unload"])
                with open(cfg_file, "r", encoding="utf-8") as fh:
                    saved = json.load(fh)
                self.assertEqual(saved["preferred_model"], "qwen2.5:3b")
                self.assertFalse(saved["auto_unload"])

    def test_control_local_ollama_delete_model(self):
        """control_local_ollama('delete', model) sends DELETE /api/delete cleanly."""
        captured_reqs = []

        def fake_urlopen(req, timeout=10.0):
            captured_reqs.append((req.full_url, req.get_method(), json.loads(req.data.decode("utf-8"))))
            return _FakeHttpResponse({}, status=200)

        with patch.object(
            hmi_inspector.KalermHmiInspector,
            "check_local_ollama",
            return_value={"available": True, "models": ["qwen2.5:1.5b"]},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"ollama": {"available": True, "models": []}},
        ), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = hmi_inspector.KalermHmiInspector.control_local_ollama("delete", "qwen2.5:1.5b")

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["deleted_model"], "qwen2.5:1.5b")
        self.assertEqual(captured_reqs[0][1], "DELETE")
        self.assertTrue(captured_reqs[0][0].endswith("/api/delete"))
        self.assertEqual(captured_reqs[0][2]["name"], "qwen2.5:1.5b")

    def test_turning_off_cancels_task_and_stops_ollama(self):
        """set_ai_enabled(False) must set cancel_requested, clear active task, and stop Ollama."""
        spectra_ai._ai_enabled = True
        spectra_ai.update_task_progress(active=True, task_id="test_task", percent=55, detail="Running...")
        with patch.object(
            hmi_inspector.KalermHmiInspector,
            "control_local_ollama",
            return_value={"status": "STOPPED"},
        ) as mock_ctrl, patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"default_selected_model": "qwen2.5:1.5b"}},
        ):
            res = spectra_ai.set_ai_enabled(False)

        self.assertTrue(res["success"])
        self.assertFalse(res["ai_enabled"])
        self.assertFalse(spectra_ai.is_ai_enabled())
        self.assertTrue(spectra_ai.is_cancel_requested())
        task = spectra_ai.get_task_progress()
        self.assertFalse(task["active"])
        self.assertEqual(task["step"], "STOPPED")
        mock_ctrl.assert_called_once_with("stop")

    def test_all_ai_features_fail_cleanly_when_off(self):
        """When AI is OFF, all orchestrator endpoints refuse cleanly without touching Ollama."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            reg_res = spectra_ai.suggest_eeprom_mappings([{"addr": 16, "val": 42}])
            triage_res = spectra_ai.analyze_fault_triage({"heater_coffee_c": 92.0})
            sum_res = spectra_ai.generate_customer_service_summary({"total_cups": 100}, 95)
            joe_res = spectra_ai.match_joe_labels_with_ai(["Tasse Kaffee"], ["Coffee"])

        mock_urlopen.assert_not_called()
        self.assertFalse(reg_res["success"])
        self.assertIn("OFF", reg_res["error"])
        self.assertEqual(reg_res["suggestions"], [])
        self.assertFalse(triage_res["success"])
        self.assertIn("OFF", triage_res["error"])
        self.assertFalse(sum_res["success"])
        self.assertIn("OFF", sum_res["error"])
        self.assertEqual(joe_res, {})

    def _mock_ollama_available(self):
        return patch.object(
            hmi_inspector.KalermHmiInspector,
            "check_local_ollama",
            return_value={"available": True, "models": [{"name": "qwen2.5:1.5b"}]},
        )

    def test_suggest_eeprom_mappings_success_and_progress_reset(self):
        spectra_ai._ai_enabled = True
        fake_llm = {
            "response": json.dumps({
                "suggested_name": "Milk Foam Calibration",
                "category": "calibration",
                "unit": "ticks",
                "confidence": "high",
                "reasoning": "Value changed during milk calibration cycle.",
            })
        }
        with self._mock_ollama_available(), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 4}},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "control_local_ollama",
            return_value={"status": "UNLOADED"},
        ), patch("urllib.request.urlopen", return_value=_FakeHttpResponse(fake_llm)):
            res = spectra_ai.suggest_eeprom_mappings(
                candidates=[{"addr": 0x0024, "addr_hex": "0024", "val": 120, "prev_val": 110, "flips": ["b1"]}],
                context_registers=[{"addr": 0x0010, "val": 500, "name": "Espresso Count", "category": "counters"}],
                machine_model="Kalerm K95L",
            )

        self.assertTrue(res["success"])
        self.assertEqual(len(res["suggestions"]), 1)
        self.assertEqual(res["suggestions"][0]["suggested_name"], "Milk Foam Calibration")
        self.assertEqual(res["suggestions"][0]["category"], "calibration")
        self.assertFalse(spectra_ai.get_task_progress()["active"])

    def test_analyze_fault_triage_success_and_progress_reset(self):
        spectra_ai._ai_enabled = True
        fake_llm = {
            "response": json.dumps({
                "summary": "Steam thermoblock temperature is below target setpoint.",
                "urgency": "medium",
                "probable_causes": ["NTC drift", "Triac thermal cutout"],
                "bench_checks": ["Measure TB2 NTC resistance", "Inspect thermal fuse continuity"],
            })
        }
        with self._mock_ollama_available(), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 2}},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "control_local_ollama",
            return_value={"status": "UNLOADED"},
        ), patch("urllib.request.urlopen", return_value=_FakeHttpResponse(fake_llm)):
            res = spectra_ai.analyze_fault_triage(
                telemetry={"heater_coffee_c": 93.0, "heater_steam_c": 41.0, "flow_rate_mls": 0.0},
                stats_summary={"machine_model": "Kalerm K95L", "health_score": 78, "alerts": ["Steam slow"]},
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["triage"]["urgency"], "MEDIUM")
        self.assertEqual(len(res["triage"]["bench_checks"]), 2)
        self.assertFalse(spectra_ai.get_task_progress()["active"])

    def test_generate_customer_service_summary_success(self):
        spectra_ai._ai_enabled = True
        fake_llm = {
            "response": json.dumps({
                "customer_summary": "Your machine completed 1,240 brews and is operating reliably.",
                "recommended_next_service": "Schedule a routine descaling cycle next month.",
            })
        }
        with self._mock_ollama_available(), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 2}},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "control_local_ollama",
            return_value={"status": "UNLOADED"},
        ), patch("urllib.request.urlopen", return_value=_FakeHttpResponse(fake_llm)):
            res = spectra_ai.generate_customer_service_summary(
                summary={"machine_model": "Jura WE8", "total_cups": 1240, "alerts": []},
                health_score=94,
            )

        self.assertTrue(res["success"])
        self.assertIn("1,240", res["customer_summary"])
        self.assertIn("descaling", res["recommended_next_service"])
        self.assertFalse(spectra_ai.get_task_progress()["active"])

    def test_match_joe_labels_with_ai_filters_to_canonical_candidates(self):
        spectra_ai._ai_enabled = True
        fake_llm = {
            "response": json.dumps({
                "mappings": {
                    "Milchschaum": "Milk Foam",
                    "UnknownItem": "NotInCanonicalList",
                }
            })
        }
        with self._mock_ollama_available(), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 2}},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "control_local_ollama",
            return_value={"status": "UNLOADED"},
        ), patch("urllib.request.urlopen", return_value=_FakeHttpResponse(fake_llm)):
            mapped = spectra_ai.match_joe_labels_with_ai(
                ["Milchschaum", "UnknownItem"],
                ["Espresso", "Milk Foam", "Cappuccino"],
            )

        self.assertEqual(mapped, {"Milchschaum": "Milk Foam"})
        self.assertFalse(spectra_ai.get_task_progress()["active"])


class TestSpectraThemedReports(unittest.TestCase):
    def test_firmware_inspector_html_report_spectra_theme_and_container_types(self):
        """export_bug_report HTML uses SPECTRA theme and handles ANDROID_APK / MCU_CTR_BIN without KeyError."""
        raw_elf = create_synthetic_elf_binary(
            extra_cs_entries=[("msg_hello", "Ahoj <Svete>")],
            extra_en_entries=[("msg_hello", "Hello <World>")],
        )
        for ftype in ("ANDROID_APK", "MCU_CTR_BIN", "ELF32_LVGL"):
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as bf:
                bf.write(raw_elf)
                bin_path = bf.name
            with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tf:
                out_path = tf.name
            try:
                insp = hmi_inspector.KalermHmiInspector(bin_path)
                insp.container_type = ftype
                if ftype == "ANDROID_APK":
                    insp.apk_meta = {"sig_scheme": "APK Signature Scheme v2", "cert_count": 1, "min_sdk": "21", "target_sdk": "30"}
                elif ftype == "MCU_CTR_BIN":
                    insp.mcu_meta = {"chip_family": "STM32H7xx", "vector_table_sp": "0x20020000", "reset_handler": "0x08000401"}

                sample_findings = [
                    {
                        "id": "AUDIT-UI-cs-CZ-msg_hello",
                        "severity": "WARNING",
                        "category": "UI Layout",
                        "locale": "cs-CZ",
                        "key": "msg_hello",
                        "current_val": "Hello <World>",
                        "expected_val": "Ahoj",
                        "vma": 0x1000,
                        "file_offset": 0x200,
                        "status": "DETECTED",
                        "description": "Text <clipped>",
                    }
                ]
                with patch.object(insp, "run_audit", return_value=sample_findings):
                    saved_path = insp.export_bug_report(out_path, format_type="html", target_locale="cs-CZ")

                self.assertEqual(os.path.abspath(out_path), saved_path)
                with open(out_path, "r", encoding="utf-8") as fh:
                    html_doc = fh.read()
                self.assertIn("SPECTRA Firmware Inspector Report", html_doc)
                self.assertIn("<title>SPECTRA Firmware Engineering Audit</title>", html_doc)
                self.assertIn("#070709", html_doc)
                self.assertIn("#FCEE09", html_doc)
                self.assertIn("#00F0FF", html_doc)
                # Ensure escaping worked for untrusted binary/XML content
                self.assertIn("Hello &lt;World&gt;", html_doc)
                self.assertIn("Text &lt;clipped&gt;", html_doc)
            finally:
                for p in (bin_path, out_path):
                    if os.path.exists(p):
                        os.unlink(p)

    def test_service_report_html_escapes_optional_ai_summary(self):
        summary = {
            "machine_model": "Jura E8",
            "total_cups": 350,
            "categories": {"Beverages": [{"name": "Espresso", "val": 200}]},
            "maintenance": [],
            "alerts": [],
        }
        html_with_ai = gui_widgets.generate_service_report_html(
            summary=summary,
            health_score=92,
            technician_checklist=[("Verify water hardness", True)],
            ai_summary={
                "customer_summary": "Clean machine <script>alert(1)</script> next week.",
                "recommended_next_service": "Descale <soon>.",
            },
        )
        self.assertIn("Customer Service Summary", html_with_ai)
        self.assertIn("Clean machine &lt;script&gt;alert(1)&lt;/script&gt; next week.", html_with_ai)
        self.assertIn("Descale &lt;soon&gt;.", html_with_ai)

        html_without_ai = gui_widgets.generate_service_report_html(
            summary=summary,
            health_score=92,
            technician_checklist=[("Verify water hardness", True)],
        )
        self.assertNotIn("Customer Service Summary", html_without_ai)


class TestEepromOffsetCalibrationAndReporting(unittest.TestCase):
    def setUp(self):
        with spectra_ai._ai_lock:
            spectra_ai._ai_enabled = False
            spectra_ai._task_state["cancel_requested"] = False

    def tearDown(self):
        with patch.object(hmi_inspector.KalermHmiInspector, "control_local_ollama", return_value={"status": "STOPPED"}):
            spectra_ai.set_ai_enabled(False)

    def test_calibrate_offsets_ground_truth_guardrail_and_local_apply(self):
        import profiles_db
        import spectra_probe
        import stats_collector

        sample_bundle = {
            "identity": {"model_name": "Test Custom Jura", "article_number": "99999"},
            "gateways": {"TY:": "ty:EF999M V01.00"},
            "eeprom_words": {
                "0x0180": 142,   # Espresso
                "0x0182": 85,    # Coffee
                "0x0189": 12,    # 2x Espresso
                "0x0008": 19,    # Cleaning
                "0x0163": 0x0044,  # 68%
                "0x0050": 999,   # Decoy wrong address
            },
            "joe_ground_truth": {
                "model_name": "Test Custom Jura",
                "products": {"Espresso": 142, "Coffee": 85, "2x Espresso": 12},
                "maintenance": {"Cleaning": 19},
                "cockpit": {"Cleaning": "68%"},
            },
        }

        # 1. Refuses cleanly while AI is OFF
        off_res = spectra_ai.calibrate_eeprom_offsets_from_joe(sample_bundle)
        self.assertFalse(off_res["success"])
        self.assertIn("OFF", off_res["error"])

        # 2. When ON, guards against bogus hallucinated address (0x0050 has 999 != 85) and keeps exact match (0x0182)
        spectra_ai._ai_enabled = True
        fake_llm = {
            "response": json.dumps({
                "products": [
                    {"name": "Espresso", "addr": "0x0180", "is_double": False, "reason": "Bank 0x0180"},
                    {"name": "Coffee", "addr": "0x0050", "is_double": False, "reason": "Wrong guess"},
                    {"name": "2x Espresso", "addr": "0x0189", "is_double": True, "reason": "Double bank"},
                ],
                "maintenance": [
                    {"name": "Cleaning", "addr": "0x0008", "reason": "Standard clean counter"},
                ],
                "maintenance_pct": [
                    {"name": "Cleaning", "addr": "0x0163", "byte": "low", "reason": "Low byte equals 68%"},
                ],
                "notes": "Aligned counters to bank 0x0180.",
            })
        }

        with patch.object(
            hmi_inspector.KalermHmiInspector,
            "check_local_ollama",
            return_value={"available": True, "models": [{"name": "qwen2.5:1.5b"}]},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 2}},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "control_local_ollama",
            return_value={"status": "UNLOADED"},
        ), patch("urllib.request.urlopen", return_value=_FakeHttpResponse(fake_llm)):
            cal_res = spectra_ai.calibrate_eeprom_offsets_from_joe(sample_bundle)

        self.assertTrue(cal_res["success"])
        ov = cal_res["override"]
        prod_by_name = {p["name"]: p for p in ov["products"]}
        self.assertEqual(prod_by_name["Espresso"]["addr"], 0x0180)
        # Verify wrong LLM guess 0x0050 was rejected and fell back to exact EEPROM match 0x0182
        self.assertEqual(prod_by_name["Coffee"]["addr"], 0x0182)
        self.assertEqual(prod_by_name["2x Espresso"]["addr"], 0x0189)
        self.assertTrue(prod_by_name["2x Espresso"]["is_double"])
        self.assertEqual(ov["maintenance"][0]["addr"], 0x0008)
        self.assertEqual(ov["maintenance_pct"][0]["joe_pct"], 68)
        self.assertEqual(ov["maintenance_pct"][0]["byte"], "low")

        # 3. Persist locally and apply immediately on a JuraStatsSession
        with tempfile.TemporaryDirectory() as td:
            temp_ov_file = os.path.join(td, "eeprom_overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", temp_ov_file):
                saved = profiles_db.save_eeprom_offset_override(ov)
                self.assertEqual(saved["override_key"], "EF999M")
                fetched = profiles_db.get_eeprom_offset_override("EF999M V01.00", article_number="99999")
                self.assertIsNotNone(fetched)

                sess = stats_collector.JuraStatsSession("MOCK")
                sess.ef_code = "EF999M V01.00"
                sess.model_family = "Test Custom Jura"
                sess.telemetry = {"article_number": "99999"}
                sess.last_eeprom = {0x0180: 142, 0x0182: 85, 0x0189: 12, 0x0008: 19, 0x0163: 0x0044}
                self.assertTrue(sess.apply_local_offset_override())

                summary = sess.get_structured_summary()
                self.assertEqual(summary["total_preparations"], 142 + 85 + 12)
                self.assertEqual(summary["total_cups"], 142 + 85 + (12 * 2))
                self.assertEqual(summary["maintenance"][0]["count"], 19)
                self.assertEqual(summary["maintenance"][0]["percentage"], 68)
                self.assertTrue(summary["offset_override"]["active"])

                self.assertTrue(profiles_db.delete_eeprom_offset_override("EF999M"))
                self.assertIsNone(profiles_db.get_eeprom_offset_override("EF999M V01.00"))

        # 4. Community upload includes Verified Offset Fix section + title tag
        sample_bundle["ai_offset_fix"] = ov
        captured_requests = []

        def fake_urlopen(req, timeout=20, context=None, **kwargs):
            captured_requests.append(json.loads(req.data.decode("utf-8")))
            return _FakeHttpResponse({"html_url": "https://github.com/Pr0xyA-91/spectra-captures/issues/123"})

        import github_auth
        with patch.object(github_auth, "resolve_token", return_value={"token": "ghp_test"}), patch(
            "urllib.request.urlopen", side_effect=fake_urlopen
        ):
            ok, msg, url = spectra_probe.upload_capture_to_community_repo(bundle_data=sample_bundle)

        self.assertTrue(ok)
        self.assertIn("issues/123", url)
        self.assertTrue(captured_requests[0]["title"].startswith("[Offset Fix + Capture]"))
        self.assertIn("Verified EEPROM Offset Fix (Local AI Calibration)", captured_requests[0]["body"])
        self.assertIn("`0x0180`", captured_requests[0]["body"])


class TestStreamingAndVisionCalibration(unittest.TestCase):
    def setUp(self):
        spectra_ai.set_ai_enabled(True)
        with spectra_ai._ai_lock:
            spectra_ai._preferred_model = "gemma3:1b"
            spectra_ai._auto_unload = False

    def tearDown(self):
        with patch.object(hmi_inspector.KalermHmiInspector, "control_local_ollama", return_value={"status": "STOPPED"}):
            spectra_ai.set_ai_enabled(False)

    def test_streaming_ndjson_assembly_and_midstream_cancel(self):
        """_query_ollama_json assembles multi-chunk NDJSON and aborts if cancelled."""
        ndjson_lines = (
            json.dumps({"response": '{"summary": "Heater ', "done": False}) + "\n"
            + json.dumps({"response": 'nominal", "urgency": "low"}', "done": True}) + "\n"
        ).encode("utf-8")

        class _NdjsonResp(io.BytesIO):
            def __init__(self, raw_bytes):
                super().__init__(raw_bytes)
                self.status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()
                return False

        with patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 2}},
        ), patch("urllib.request.urlopen", return_value=_NdjsonResp(ndjson_lines)):
            parsed, err = spectra_ai._query_ollama_json("Test prompt", "gemma3:1b")

        self.assertIsNone(err)
        self.assertEqual(parsed.get("summary"), "Heater nominal")
        self.assertEqual(parsed.get("urgency"), "low")

        # Cancel mid-flight
        with spectra_ai._ai_lock:
            spectra_ai._task_state["cancel_requested"] = True
        parsed2, err2 = spectra_ai._query_ollama_json("Test prompt", "gemma3:1b")
        self.assertIsNone(parsed2)
        self.assertIn("Cancelled", err2)

    def test_extract_joe_from_image_requires_vision_or_uses_gemma3_4b(self):
        """Screenshot extraction uses gemma3:4b when present and passes clean base64 images payload."""
        captured_payloads = []

        class _VisionResp(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=120):
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
            return _VisionResp(
                (json.dumps({
                    "response": json.dumps({
                        "products": [{"name": "Espresso", "count": 412}, {"name": "Coffee", "count": 199}],
                        "maintenance": [{"name": "Cleaning", "count": 14}],
                        "cockpit": [{"name": "Filter", "percent": 80}],
                        "notes": "Read cleanly from legacy service screen",
                    }),
                    "done": True,
                }) + "\n").encode("utf-8")
            )

        with patch.object(
            hmi_inspector.KalermHmiInspector,
            "check_local_ollama",
            return_value={"available": True, "models": [{"name": "gemma3:1b"}, {"name": "gemma3:4b"}]},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 2}},
        ), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = spectra_ai.extract_joe_from_image_with_ai("data:image/png;base64,ZmFrZWltYWdl")

        self.assertTrue(res["success"])
        self.assertEqual(res["model"], "gemma3:4b")
        self.assertEqual(captured_payloads[0]["images"], ["ZmFrZWltYWdl"])
        self.assertEqual(len(res["joe_data"]["products"]), 2)
        self.assertEqual(res["joe_data"]["products"]["Espresso"], 412)

    def test_calibrate_offsets_from_upload_screenshot_preview_diff(self):
        """calibrate_offsets_from_upload correlates screenshot counters and computes before/after diff."""
        fake_eeprom = {"0x0000": 412, "0x0002": 199, "0x0008": 14}
        extracted_joe = {
            "products": {"Espresso": 412, "Coffee": 199},
            "maintenance": {"Cleaning": 14},
            "cockpit": {},
        }

        with patch.object(
            spectra_ai,
            "extract_joe_from_image_with_ai",
            return_value={"success": True, "method": "vision:gemma3:4b", "model": "gemma3:4b", "joe_data": extracted_joe},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "check_local_ollama",
            return_value={"available": True, "models": [{"name": "gemma3:4b"}]},
        ), patch.object(
            hmi_inspector.KalermHmiInspector,
            "get_ai_system_status",
            return_value={"hardware": {"recommended_threads": 2}},
        ), patch.object(
            spectra_ai,
            "_query_ollama_json",
            return_value=({"products": [], "maintenance": [], "notes": "Exact match"}, None),
        ):
            res = spectra_ai.calibrate_offsets_from_upload(
                eeprom_words=fake_eeprom,
                file_name="legacy_service_screen.png",
                image_b64="data:image/png;base64,ZmFrZQ==",
                ty_str="EF634",
                model_name="ENA 7",
                article_number="13500",
                current_stats={"total_preps": 12, "products": [], "maintenance_counters": {}},
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["extraction_source"], "vision:gemma3:4b")
        self.assertEqual(res["matched_products"], 2)
        self.assertEqual(res["matched_maintenance"], 1)
        self.assertEqual(res["preview_before"]["total_preps"], 12)
        self.assertEqual(res["preview_after"]["total_preps"], 412 + 199)


class TestTlsUtilsAndEngineDownload(unittest.TestCase):
    def test_get_ssl_context_enforces_strict_verification(self):
        import ssl
        import tls_utils

        ctx = tls_utils.get_ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_configure_process_tls_env_sets_ca_vars(self):
        import tempfile
        import types
        import tls_utils

        with tempfile.NamedTemporaryFile(suffix=".pem") as tf:
            fake_certifi = types.SimpleNamespace(where=lambda: tf.name)
            env_patch = {}
            with patch.dict(os.environ, env_patch, clear=False), patch.dict(sys.modules, {"certifi": fake_certifi}):
                os.environ.pop("SSL_CERT_FILE", None)
                os.environ.pop("REQUESTS_CA_BUNDLE", None)
                tls_utils.configure_process_tls_env()
                self.assertEqual(os.environ.get("SSL_CERT_FILE"), tf.name)
                self.assertEqual(os.environ.get("REQUESTS_CA_BUNDLE"), tf.name)

    def test_download_engine_archive_schannel_fallback_on_windows_cert_error(self):
        import ssl
        import tempfile
        import urllib.error
        import tls_utils

        tls_err = urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "ollama-windows-amd64.zip")
            with patch("urllib.request.urlopen", side_effect=tls_err), patch.object(
                hmi_inspector.os, "name", "nt"
            ), patch.object(tls_utils, "windows_schannel_download") as schannel_mock:
                ok = hmi_inspector.KalermHmiInspector._download_engine_archive(
                    "https://ollama.com/download/ollama-windows-amd64.zip",
                    dest,
                )
            self.assertTrue(ok)
            schannel_mock.assert_called_once()
            self.assertEqual(
                schannel_mock.call_args.args[:2],
                ("https://ollama.com/download/ollama-windows-amd64.zip", dest),
            )

    def test_download_engine_archive_no_schannel_fallback_on_posix(self):
        import ssl
        import tempfile
        import urllib.error
        import tls_utils

        tls_err = urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "ollama-linux-amd64.tgz")
            with patch("urllib.request.urlopen", side_effect=tls_err), patch.object(
                hmi_inspector.os, "name", "posix"
            ), patch.object(tls_utils, "windows_schannel_download") as schannel_mock:
                with self.assertRaises(urllib.error.URLError):
                    hmi_inspector.KalermHmiInspector._download_engine_archive(
                        "https://ollama.com/download/ollama-linux-amd64.tgz",
                        dest,
                    )
            schannel_mock.assert_not_called()


class TestWin32DialogFocus(unittest.TestCase):
    def test_win32_comdlg_sets_spectra_owner_hwnd_and_enablehook(self):
        import ctypes
        import types

        captured_ofn = {}

        def fake_get_save(ofn_byref):
            # ctypes.byref(struct) wraps struct in _obj on CPython
            ofn = getattr(ofn_byref, "_obj", ofn_byref)
            captured_ofn["hwndOwner"] = ofn.hwndOwner
            captured_ofn["Flags"] = ofn.Flags
            captured_ofn["lpfnHook"] = ofn.lpfnHook
            return 1

        fake_windll = types.SimpleNamespace(
            comdlg32=types.SimpleNamespace(
                GetSaveFileNameW=fake_get_save,
                GetOpenFileNameW=fake_get_save,
                CommDlgExtendedError=lambda: 0,
            )
        )

        with patch.object(ctypes, "windll", fake_windll, create=True), patch.object(
            hmi_inspector.KalermHmiInspector,
            "_find_win32_spectra_owner_hwnd",
            return_value=0x123456,
        ):
            status, chosen = hmi_inspector.KalermHmiInspector._win32_comdlg_dialog(
                is_save=True,
                filter_str="All Files (*.*)\0*.*\0\0",
                initial_dir="/tmp",
                title="Save Export",
                flags=0x00080802,
                default_filename="capture.json",
                default_ext="json",
            )

        self.assertEqual(status, "OK")
        self.assertEqual(chosen, "capture.json")
        self.assertEqual(captured_ofn["hwndOwner"], 0x123456)
        self.assertTrue(captured_ofn["Flags"] & 0x00000020)  # OFN_ENABLEHOOK
        self.assertIsNotNone(captured_ofn["lpfnHook"])


class TestOnDiskModelDetectionAndToggleGuard(unittest.TestCase):
    def tearDown(self):
        with patch.object(hmi_inspector.KalermHmiInspector, "control_local_ollama", return_value={"status": "STOPPED"}):
            spectra_ai.set_ai_enabled(False)

    def test_discover_local_ollama_models_on_disk_when_daemon_stopped(self):
        """Installed Ollama manifests on disk must be reported even when 127.0.0.1:11434 is stopped."""
        with tempfile.TemporaryDirectory() as td:
            manifest_file = os.path.join(td, "manifests", "registry.ollama.ai", "library", "qwen2.5", "0.5b")
            os.makedirs(os.path.dirname(manifest_file), exist_ok=True)
            with open(manifest_file, "w", encoding="utf-8") as fh:
                fh.write('{"schemaVersion": 2}')

            with patch.dict(os.environ, {"OLLAMA_MODELS": td}, clear=False), patch.object(
                os.path, "expanduser", side_effect=lambda p: p.replace("~", td) if "~" in p else p
            ), patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("daemon stopped")):
                chk = hmi_inspector.KalermHmiInspector.check_local_ollama(timeout=0.05)

            self.assertFalse(chk["available"])
            self.assertEqual(chk["models"], ["qwen2.5:0.5b"])

    def test_set_ai_enabled_refuses_when_no_models_installed(self):
        """set_ai_enabled(True, require_installed_model=True) rejects activation if 0 models are installed."""
        with tempfile.TemporaryDirectory() as td:
            cfg_file = os.path.join(td, "ai_config.json")
            empty_status = {"hardware": {"default_selected_model": "qwen2.5:0.5b"}, "ollama": {"available": False, "models": []}}
            with patch.object(spectra_ai, "AI_CONFIG_FILE", cfg_file), patch.object(
                hmi_inspector.KalermHmiInspector, "get_ai_system_status", return_value=empty_status
            ), patch.object(
                hmi_inspector.KalermHmiInspector, "get_ollama_download_progress", return_value={"active": False}
            ):
                res_empty = spectra_ai.set_ai_enabled(True, model="gemma3:1b", require_installed_model=True)
                self.assertFalse(res_empty["success"])
                self.assertTrue(res_empty.get("requires_model_install"))
                self.assertFalse(res_empty["ai_enabled"])
                self.assertFalse(spectra_ai.is_ai_enabled())

                has_model_status = {
                    "hardware": {"default_selected_model": "qwen2.5:0.5b"},
                    "ollama": {"available": False, "models": ["qwen2.5:0.5b"]},
                }
                with patch.object(hmi_inspector.KalermHmiInspector, "get_ai_system_status", return_value=has_model_status):
                    res_ok = spectra_ai.set_ai_enabled(True, model="gemma3:1b", require_installed_model=True)
                    self.assertTrue(res_ok["success"])
                    self.assertTrue(res_ok["ai_enabled"])
                    self.assertEqual(res_ok["preferred_model"], "qwen2.5:0.5b")


class TestTxtCalibrationIdentityAndHarvester(unittest.TestCase):
    """Tests for .txt Local AI extraction, US/EU identity override, and calibration harvesting."""

    def test_calibrate_from_txt_file_extracts_identity_and_offsets(self):
        fake_eeprom = {0x0001: 420, 0x0002: 185, 0x0008: 12}
        # Verify deterministic .txt parser handles numbered beverage labels too
        import spectra_probe
        det = spectra_probe.parse_joe_csv_text("Model Name: Jura E8 (NA)\nSerial Number: SN123\n1 Espresso: 420\n")
        self.assertEqual(det["products"]["1 Espresso"], 420)
        self.assertEqual(det["serial_number"], "SN123")

        txt_report = (
            "Service Export Diagnostics\n"
            "Nameplate says Jura E8 (NA) 120V Art 15364, S/N 20240501001234.\n"
            "Counts reported by customer: 420 Espresso, 185 Coffee, 12 Cleanings.\n"
        )
        ai_txt_reply = {
            "model_name": "Jura E8 (NA)",
            "article_number": "15364",
            "serial_number": "20240501001234",
            "market_region": "US",
            "products": [{"name": "Espresso", "count": 420}, {"name": "Coffee", "count": 185}],
            "maintenance": [{"name": "Cleanings", "count": 12}],
            "cockpit": [],
            "notes": "Parsed US E8 15364 text dump.",
        }
        ai_cal_reply = {
            "products": [
                {"name": "Espresso", "addr": "0x0001", "is_double": False, "reason": "exact match"},
                {"name": "Coffee", "addr": "0x0002", "is_double": False, "reason": "exact match"},
            ],
            "maintenance": [
                {"name": "Cleanings", "addr": "0x0008", "reason": "cleaning match"},
            ],
            "maintenance_pct": [],
            "notes": "Matched US E8 counters",
        }
        with patch.object(spectra_ai, "_resolve_active_model", return_value=(True, "qwen2.5:0.5b", "")), patch.object(
            spectra_ai,
            "is_cancel_requested",
            return_value=False,
        ), patch.object(
            spectra_ai,
            "_query_ollama_json",
            side_effect=[(ai_txt_reply, ""), (ai_cal_reply, "")],
        ), patch.object(spectra_ai, "_maybe_auto_unload"):
            res = spectra_ai.calibrate_offsets_from_upload(
                eeprom_words={f"0x{k:04X}": v for k, v in fake_eeprom.items()},
                file_name="machine_dump.txt",
                csv_text=txt_report,
                ty_str="EF532M",
                model_name="Generic Jura",
                article_number="15000",
                model="qwen2.5:0.5b",
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["detected_identity"]["model_name"], "Jura E8 (NA)")
        self.assertEqual(res["detected_identity"]["article_number"], "15364")
        self.assertEqual(res["detected_identity"]["serial_number"], "20240501001234")
        self.assertEqual(res["detected_identity"]["market_region"], "US")
        self.assertEqual(res["override"]["model_name"], "Jura E8 (NA)")
        self.assertEqual(res["matched_products"], 2)
        self.assertEqual(res["matched_maintenance"], 1)

    def test_identity_only_override_applies_to_stats_session(self):
        import stats_collector
        import profiles_db

        with tempfile.TemporaryDirectory() as td:
            ov_path = os.path.join(td, "overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", ov_path):
                profiles_db.save_eeprom_offset_override({
                    "ef_code": "EF532M",
                    "model_name": "Jura E8 (NA)",
                    "article_number": "15364",
                    "serial_number": "20240501009999",
                    "market_region": "US",
                    "products": [],
                    "maintenance": [],
                })
                sess = stats_collector.JuraStatsSession(port_name="DEMO")
                sess.ef_code = "EF532M"
                sess.model_family = "Generic E8 (EU)"
                sess.telemetry["article_number"] = "15000"
                applied = sess.apply_local_offset_override()
                self.assertTrue(applied)
                summary = sess.get_structured_summary()
                self.assertEqual(summary["machine_model"], "Jura E8 (NA)")
                self.assertEqual(summary["article_number"], "15364")
                self.assertEqual(summary["serial_number"], "20240501009999")
                self.assertEqual(summary["market_region"], "US")

    def test_sync_community_calibrations_harvester(self):
        from contrib import sync_community_calibrations

        with tempfile.TemporaryDirectory() as td:
            models_dir = os.path.join(td, "models")
            issue_file = os.path.join(td, "issues.json")
            patch_obj = {
                "schema": "spectra.offset_patch.v1",
                "identity": {
                    "ef_code": "EF999M",
                    "model_name": "Z10 (NA)",
                    "article_number": "15501",
                    "market_region": "US",
                },
                "override": {
                    "ef_code": "EF999M",
                    "model_name": "Z10 (NA)",
                    "article_number": "15501",
                    "market_region": "US",
                    "products": [{"name": "Espresso", "addr": 1, "addr_hex": "0x0001", "joe_count": 321}],
                    "maintenance": [{"name": "Cleaning", "addr": 8, "addr_hex": "0x0008", "joe_count": 9}],
                },
                "eeprom_words": {"0x0001": 321, "0x0008": 9},
            }
            issues = [
                {
                    "number": 42,
                    "title": "[Offset Fix + Capture] Z10 (NA) (Article 15501)",
                    "body": "### Automated Harvesting Payload\n```json\n" + json.dumps(patch_obj) + "\n```",
                }
            ]
            with open(issue_file, "w", encoding="utf-8") as f:
                json.dump(issues, f)

            res = sync_community_calibrations.sync_calibrations(
                models_dir=models_dir,
                apply_changes=True,
                input_file=issue_file,
            )
            self.assertTrue(res["ok"])
            self.assertEqual(res["verified_calibrations"], 1)
            self.assertEqual(len(res["updated_files"]), 1)
            with open(res["updated_files"][0], "r", encoding="utf-8") as f:
                spec = json.load(f)
            self.assertEqual(spec["ef_code"], "EF999M")
            self.assertIn("15501", spec["article_numbers"])
            self.assertEqual(spec["market_regions"], ["US"])
            self.assertEqual(spec["verified_offsets"]["products"][0]["addr_hex"], "0x0001")

    def test_community_calibration_harvester_create_pr_workflow(self):
        import base64
        from contrib import sync_community_calibrations as sync_mod

        with tempfile.TemporaryDirectory() as td:
            models_dir = os.path.join(td, "models")
            issue_file = os.path.join(td, "issue.json")
            patch_obj = {
                "schema": "spectra.offset_patch.v1",
                "identity": {
                    "ef_code": "EF999M",
                    "model_name": "Jura Z10 (NA)",
                    "article_number": "15501",
                    "market_region": "US",
                },
                "override": {
                    "ef_code": "EF999M",
                    "model_name": "Jura Z10 (NA)",
                    "article_number": "15501",
                    "market_region": "US",
                    "products": [{"name": "Espresso", "addr": 1, "addr_hex": "0x0001", "joe_count": 210}],
                    "maintenance": [{"name": "Cleaning", "addr": 8, "addr_hex": "0x0008", "joe_count": 5}],
                },
                "eeprom_words": {"0x0001": 210, "0x0008": 5},
            }
            issue_payload = {
                "number": 7,
                "title": "[Offset Fix + Capture] Jura Z10 (NA) (15501)",
                "body": "```json\n" + json.dumps(patch_obj) + "\n```",
            }
            with open(issue_file, "w", encoding="utf-8") as f:
                json.dump(issue_payload, f)

            api_calls = []

            def fake_api(method, url, token=None, payload=None):
                api_calls.append((method, url, payload))
                if method == "GET" and url.endswith("/git/ref/heads/main"):
                    return {"object": {"sha": "abc1234567890"}}
                if method == "GET" and "/git/ref/heads/calibrations/" in url:
                    raise RuntimeError("404 Not Found")
                if method == "POST" and url.endswith("/git/refs"):
                    return {"ref": payload["ref"]}
                if method == "GET" and "/contents/docs/models/EF999M_Jura_Z10_NA.json?" in url:
                    raise RuntimeError("404 Not Found")
                if method == "PUT" and url.endswith("/contents/docs/models/EF999M_Jura_Z10_NA.json"):
                    return {"content": {"path": "docs/models/EF999M_Jura_Z10_NA.json"}}
                if method == "GET" and "/pulls?state=open" in url:
                    return []
                if method == "POST" and url.endswith("/pulls"):
                    return {"number": 42, "html_url": "https://github.com/Pr0xyA-91/spectra/pull/42"}
                if method == "POST" and url.endswith("/issues/7/comments"):
                    return {"id": 999}
                raise AssertionError(f"Unexpected GitHub API call: {method} {url}")

            with patch.object(sync_mod, "_github_api_request", side_effect=fake_api):
                res = sync_mod.sync_calibrations(
                    repo="Pr0xyA-91/spectra-captures",
                    models_dir=models_dir,
                    apply_changes=False,
                    input_file=issue_file,
                    token="ghp_test_token",
                    create_pr=True,
                    pr_repo="Pr0xyA-91/spectra",
                    base_branch="main",
                    comment_issues=True,
                )

            self.assertTrue(res["ok"])
            self.assertEqual(res["verified_calibrations"], 1)
            self.assertTrue(res["pull_request"]["created"])
            self.assertEqual(res["pull_request"]["pr_number"], 42)
            self.assertTrue(res["pull_request"]["pr_url"].endswith("/pull/42"))

            put_calls = [c for c in api_calls if c[0] == "PUT" and c[1].endswith("/contents/docs/models/EF999M_Jura_Z10_NA.json")]
            self.assertEqual(len(put_calls), 1)
            committed_spec = json.loads(base64.b64decode(put_calls[0][2]["content"]).decode("utf-8"))
            self.assertEqual(committed_spec["ef_code"], "EF999M")
            self.assertIn("15501", committed_spec["article_numbers"])

            pr_calls = [c for c in api_calls if c[0] == "POST" and c[1].endswith("/pulls")]
            self.assertEqual(len(pr_calls), 1)
            self.assertIn("Refs Pr0xyA-91/spectra-captures#7", pr_calls[0][2]["body"])

            comment_calls = [c for c in api_calls if c[0] == "POST" and c[1].endswith("/issues/7/comments")]
            self.assertEqual(len(comment_calls), 1)
            self.assertIn("[SPECTRA-PR-LINKED]", comment_calls[0][2]["body"])

            # Verify remote issues already linked with [SPECTRA-PR-LINKED] are skipped cleanly
            with patch.object(sync_mod, "_fetch_github_issues", return_value=[issue_payload]), patch.object(
                sync_mod, "_issue_has_pr_marker", return_value=True
            ):
                skip_res = sync_mod.sync_calibrations(
                    repo="Pr0xyA-91/spectra-captures",
                    models_dir=models_dir,
                    apply_changes=False,
                    token="ghp_test_token",
                    create_pr=True,
                )
            self.assertEqual(skip_res["verified_calibrations"], 0)
            self.assertEqual(skip_res["skipped"][0]["issue"], 7)
            self.assertEqual(skip_res["skipped"][0]["reason"], "Already linked to a calibration PR")
            self.assertNotIn("pull_request", skip_res)

    def test_non_coffee_products_excluded_from_total_cups(self):
        import stats_collector
        import profiles_db

        # Verify helper classification rules
        self.assertTrue(stats_collector.is_non_coffee_product("Hot Water"))
        self.assertTrue(stats_collector.is_non_coffee_product("Portion of milk"))
        self.assertTrue(stats_collector.is_non_coffee_product("Milk Foam"))
        self.assertTrue(stats_collector.is_non_coffee_product("Steam"))
        self.assertFalse(stats_collector.is_non_coffee_product("Cappuccino"))
        self.assertFalse(stats_collector.is_non_coffee_product("Latte Macchiato"))
        self.assertFalse(stats_collector.is_non_coffee_product("Espresso"))
        self.assertFalse(stats_collector.is_non_coffee_product("2x Coffee"))

        # Verify apply_local_offset_override excludes steam/milk/water from total_cups
        with tempfile.TemporaryDirectory() as td:
            ov_path = os.path.join(td, "overrides.json")
            with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", ov_path):
                profiles_db.save_eeprom_offset_override({
                    "ef_code": "EF535M",
                    "model_name": "WE8 Test",
                    "products": [
                        {"code": 2, "name": "Espresso", "addr": 1, "is_double": False},
                        {"code": 19, "name": "2x Coffee", "addr": 2, "is_double": True},
                        {"code": 4, "name": "Cappuccino", "addr": 3, "is_double": False},
                        {"code": 7, "name": "Latte Macchiato", "addr": 4, "is_double": False},
                        {"code": 10, "name": "Portion of milk", "addr": 5, "is_double": False},
                        {"code": 8, "name": "Milk Foam", "addr": 6, "is_double": False},
                        {"code": 13, "name": "Hot Water", "addr": 7, "is_double": False},
                        {"code": 25, "name": "Steam", "addr": 8, "is_double": False},
                    ],
                    "maintenance": [],
                })
                sess = stats_collector.JuraStatsSession(port_name="DEMO")
                sess.ef_code = "EF535M"
                sess.model_family = "WE8 Test"
                fake_eeprom = {1: 100, 2: 50, 3: 30, 4: 20, 5: 40, 6: 15, 7: 25, 8: 10}
                applied = sess.apply_local_offset_override(eeprom=fake_eeprom)
                self.assertTrue(applied)
                # total_preparations = 100+50+30+20+40+15+25+10 = 290
                self.assertEqual(sess.total_preparations, 290)
                # total_cups = Espresso(100) + 2xCoffee(50*2) + Capp(30) + Latte(20) = 250 (excludes 40+15+25+10)
                self.assertEqual(sess.total_cups, 250)

    def test_http_offsets_apply_local_and_overrides_endpoints(self):
        import threading
        import urllib.request
        import profiles_db
        import web_server

        with tempfile.TemporaryDirectory() as td:
            ov_path = os.path.join(td, "overrides.json")
            orig_cache = web_server._last_stats_cache
            orig_sess = web_server._active_session
            httpd = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
            port = httpd.server_address[1]
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                web_server._active_session = None
                web_server._last_stats_cache = {"ef_code": "EF532M", "machine_model": "Generic E8"}
                with patch.object(profiles_db, "EEPROM_OVERRIDES_FILE", ov_path):
                    payload = json.dumps({
                        "override": {
                            "ef_code": "EF532M",
                            "model_name": "Jura E8 (NA)",
                            "article_number": "15364",
                            "products": [
                                {"code": 1, "name": "Espresso", "addr": 1, "eeprom_val": 42, "is_double": False},
                                {"code": 13, "name": "Hot Water", "addr": 2, "eeprom_val": 8, "is_double": False},
                            ],
                            "maintenance": [
                                {"name": "Cleaning", "addr": 8, "eeprom_val": 3},
                            ],
                        }
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/offsets/apply_local",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(res["success"])
                    self.assertEqual(res["saved_key"], "EF532M")
                    self.assertEqual(res["updated_stats"]["machine_model"], "Jura E8 (NA)")
                    self.assertEqual(res["updated_stats"]["total_preparations"], 50)
                    self.assertEqual(res["updated_stats"]["total_cups"], 42)

                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/offsets/overrides", timeout=5) as resp:
                        ov_list = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(ov_list["success"])
                    self.assertIn("EF532M", ov_list["overrides"])

                    del_req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/offsets/delete",
                        data=json.dumps({"key": "EF532M"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(del_req, timeout=5) as resp:
                        del_res = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(del_res["success"])
                    self.assertTrue(del_res["removed"])
            finally:
                web_server._last_stats_cache = orig_cache
                web_server._active_session = orig_sess
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
