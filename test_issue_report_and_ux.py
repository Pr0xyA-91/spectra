#!/usr/bin/env python3
"""
Regression tests for:
1. User GitHub issue reporting (`github_auth.create_github_issue`, `sanitize_issue_text`,
   `POST /api/github/report_issue` with sanitized diagnostics & browser fallback).
2. Custom ticket number / filename prefix sanitization and `/api/export` + `/api/export_capture`.
3. Thread-safe UI language preset persistence (`save_ui_prefs` + `App.jsx` race elimination).
4. Translation parity (EN/CS) and top-bar Report Issue + Live Activity pill presence.
"""

import io
import json
import os
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import github_auth
import web_server


class _FakeHTTPResp:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestGitHubIssueReporting(unittest.TestCase):
    def test_sanitize_issue_text_redacts_tokens_and_home_paths(self):
        raw = (
            "Failed auth with ghp_1234567890abcdef1234567890 and github_pat_abcdef1234567890\n"
            "Authorization: Bearer super_secret_token_value\n"
            "Config at /home/alice/projects/spectra and /Users/bob/app and C:\\Users\\Charlie\\AppData\\SPECTRA\n"
        )
        cleaned = github_auth.sanitize_issue_text(raw)
        self.assertNotIn("ghp_1234567890abcdef1234567890", cleaned)
        self.assertNotIn("github_pat_abcdef1234567890", cleaned)
        self.assertNotIn("super_secret_token_value", cleaned)
        self.assertNotIn("/home/alice/", cleaned)
        self.assertNotIn("/Users/bob/", cleaned)
        self.assertNotIn("C:\\Users\\Charlie\\", cleaned)
        self.assertIn("[REDACTED_TOKEN]", cleaned)
        self.assertIn("~/", cleaned)
        self.assertIn("~\\", cleaned)

    def test_create_issue_unauthenticated_returns_prefilled_web_url(self):
        with patch.object(github_auth, "resolve_token", return_value=None):
            res = github_auth.create_github_issue(
                title="Telemetry stuck on Jura E8",
                body="Steps to reproduce: open Tab 02.",
                labels=["bug", "user-report"],
            )
        self.assertFalse(res["success"])
        self.assertTrue(res.get("auth_required"))
        self.assertEqual(res.get("repo"), "Pr0xyA-91/spectra")
        self.assertIn("https://github.com/Pr0xyA-91/spectra/issues/new?", res.get("web_url", ""))
        self.assertIn("Telemetry+stuck+on+Jura+E8", res.get("web_url", ""))

    def test_create_issue_authenticated_and_422_label_fallback(self):
        calls = []

        def fake_urlopen(req, timeout=20, context=None):
            body = json.loads(req.data.decode("utf-8"))
            calls.append(body)
            if "labels" in body:
                raise urllib.error.HTTPError(
                    req.full_url, 422, "Unprocessable Entity", {}, io.BytesIO(b"{}")
                )
            return _FakeHTTPResp({
                "html_url": "https://github.com/Pr0xyA-91/spectra/issues/42",
                "number": 42,
            })

        with patch.object(
            github_auth,
            "resolve_token",
            return_value={"token": "ghp_testtoken1234567890", "login": "tester", "method": "pat"},
        ), patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = github_auth.create_github_issue(
                title="Feature request",
                body="Add ticket number prefix",
                labels=["enhancement", "user-report"],
            )

        self.assertTrue(res["success"])
        self.assertEqual(res["issue_number"], 42)
        self.assertEqual(res["issue_url"], "https://github.com/Pr0xyA-91/spectra/issues/42")
        self.assertEqual(len(calls), 2)
        self.assertIn("labels", calls[0])
        self.assertNotIn("labels", calls[1])


class TestExportFilenamePrefix(unittest.TestCase):
    def test_sanitize_filename_prefix_edge_cases(self):
        self.assertEqual(web_server.sanitize_filename_prefix("TKT-2048"), "TKT-2048")
        self.assertEqual(web_server.sanitize_filename_prefix("Zakázka #42"), "Zakazka_42")
        self.assertEqual(web_server.sanitize_filename_prefix("../../etc/passwd"), "etc_passwd")
        self.assertEqual(web_server.sanitize_filename_prefix('bad<>:"/\\|?*name'), "bad_name")
        self.assertEqual(web_server.sanitize_filename_prefix("CON"), "tkt_CON")
        self.assertEqual(web_server.sanitize_filename_prefix("   ...   "), "")
        self.assertLessEqual(len(web_server.sanitize_filename_prefix("A" * 100)), 48)

    def test_build_export_filename(self):
        self.assertEqual(
            web_server.build_export_filename("export", "Jura E8", "20261119_153000", "json", prefix="WO-1042"),
            "WO-1042_spectra_export_Jura_E8_20261119_153000.json",
        )
        self.assertEqual(
            web_server.build_export_filename("export", "Jura E8", "20261119_153000", "csv", prefix=""),
            "spectra_export_Jura_E8_20261119_153000.csv",
        )


class TestWebServerEndpointsAndPrefs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        cls.port = cls.httpd.server_address[1]
        cls._prev_http_port = web_server._current_http_port
        web_server._current_http_port = cls.port
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        web_server._current_http_port = cls._prev_http_port
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _post_json(self, path: str, payload: dict):
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": self.base,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            return he.code, json.loads(he.read().decode("utf-8"))

    def test_report_issue_endpoint_validation_and_url_only_redaction(self):
        status, body = self._post_json("/api/github/report_issue", {"title": "", "description": "desc"})
        self.assertEqual(status, 400)
        self.assertFalse(body["success"])

        with web_server._debug_log_lock:
            web_server._debug_log_buffer.append({
                "ts": "12:00:00",
                "level": "ERROR",
                "source": "TEST",
                "message": "Leak test ghp_secretvalue1234567890 in /home/secretuser/file.py",
            })

        status, body = self._post_json(
            "/api/github/report_issue",
            {
                "title": "Test bug report",
                "description": "See attached logs",
                "category": "hardware",
                "include_env": True,
                "include_logs": True,
                "mode": "url_only",
                "machine_context": {"model": "Jura E8", "ef_code": "EF533", "protocol": "Plain ASCII"},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        web_url = body["web_url"]
        self.assertTrue(web_url.startswith("https://github.com/Pr0xyA-91/spectra/issues/new?"))
        self.assertNotIn("ghp_secretvalue1234567890", web_url)
        self.assertNotIn("secretuser", web_url)
        self.assertIn("Jura+E8", web_url)

    def test_export_endpoint_applies_custom_ticket_prefix(self):
        url = f"{self.base}/api/export?port=DEMO%20/%20SIMULATION&format=json&save_dialog=0&prefix=TKT-8821"
        with urllib.request.urlopen(url, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            disp = resp.headers.get("Content-Disposition", "")
            self.assertIn('filename="TKT-8821_spectra_export_', disp)
            self.assertTrue(disp.endswith('.json"'))

    def test_concurrent_ui_prefs_save_preserves_both_keys(self):
        with tempfile.TemporaryDirectory() as td:
            prefs_path = str(Path(td) / "ui_prefs.json")
            with patch("web_server.get_ui_prefs_path", return_value=prefs_path):
                errors = []

                def set_lang():
                    try:
                        for _ in range(10):
                            web_server.save_ui_prefs({"lang": "cs"})
                    except Exception as e:
                        errors.append(e)

                def set_onboarding():
                    try:
                        for _ in range(10):
                            web_server.save_ui_prefs({"onboarding_seen": True})
                    except Exception as e:
                        errors.append(e)

                t1 = threading.Thread(target=set_lang)
                t2 = threading.Thread(target=set_onboarding)
                t1.start()
                t2.start()
                t1.join()
                t2.join()

                self.assertEqual(errors, [])
                loaded = web_server.load_ui_prefs()
                self.assertEqual(loaded, {"onboarding_seen": True, "lang": "cs"})


class TestFrontendPersistenceAndI18nInvariants(unittest.TestCase):
    def test_app_jsx_has_no_mount_localstorage_overwrite_race(self):
        app_src = Path(__file__).resolve().parent / "web" / "src" / "App.jsx"
        text = app_src.read_text(encoding="utf-8")
        self.assertIn("handleChangeLang", text)
        self.assertIn("userSelectedLangRef", text)
        self.assertIn("setLang={handleChangeLang}", text)
        # Ensure the old broken `!lsLang` guard is gone
        self.assertNotIn("if (!lsLang", text)

    def test_translations_en_cs_new_keys_present(self):
        tr_path = Path(__file__).resolve().parent / "web" / "src" / "i18n" / "translations.js"
        text = tr_path.read_text(encoding="utf-8")
        for key in (
            "btnReportIssue",
            "activityReading",
            "activityUpdating",
            "activityAiWorking",
            "exportPrefixLabel",
            "issueModalTitle",
            "issueSubmitGithubBtn",
        ):
            matches = re.findall(rf"\b{key}\s*:", text)
            self.assertGreaterEqual(len(matches), 2, f"Expected EN + CS definitions for '{key}'")


if __name__ == "__main__":
    unittest.main()
