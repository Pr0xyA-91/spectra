#!/usr/bin/env python3
"""
Regression test suite for Principal Code Review (Batch B) security/stability fixes
and hardware/Smart Connect (Batch A) protocol fixes.
"""

import io
import json
import os
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import github_auth
import memory_mapper
import serial_io
import spectra_ai
import updater
import web_server
from contrib import sync_community_calibrations as scc


class _LiveTestServerMixin:
    @classmethod
    def _start_server(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        cls.port = cls.server.server_address[1]
        cls._prev_http_port = web_server._current_http_port
        web_server._current_http_port = cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def _stop_server(cls):
        cls.server.shutdown()
        cls.server.server_close()
        web_server._current_http_port = cls._prev_http_port

    def _http(self, method: str, path: str, body: bytes = b"", headers=None):
        req = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body if method == "POST" else None,
            method=method,
            headers=headers or {},
        )
        try:
            with urlopen(req, timeout=5) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except HTTPError as e:
            return e.code, e.read(), dict(e.headers)


class TestWebServerSecurityAndStability(_LiveTestServerMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._start_server()

    @classmethod
    def tearDownClass(cls):
        cls._stop_server()

    def test_port_validation_rejects_invalid_com_and_traversal(self):
        for ok_port in (
            "COM1",
            "COM3",
            "com12",
            "COM25",
            "\\\\.\\COM10",
            "COM3 (USB Serial Port (COM3))",
            "COM4 (USB-SERIAL CH340 (COM4))",
            "COM12 (Silicon Labs CP210x USB to UART Bridge (COM12))",
            "\\\\.\\COM10 (FTDI USB Serial)",
            "/dev/ttyUSB0",
            "DEMO / SIMULATION (Jura S8)",
        ):
            self.assertTrue(web_server.is_valid_port(ok_port), f"Expected valid port: {ok_port!r}")

        for bad_port in (
            "COM_EVIL",
            "COM9999",
            "COM3; whoami",
            "COM3 | calc",
            "COM3 & dir",
            "COM3 (evil; rm -rf /)",
            "COM3 (evil & calc)",
            "COM3 (../etc)",
            "COM3\nInjected",
            "../dev/ttyUSB0",
            "/etc/passwd",
            "",
            None,
        ):
            self.assertFalse(web_server.is_valid_port(bad_port), f"Expected invalid port: {bad_port!r}")

    def test_windows_com_port_normalization_and_session_reuse(self):
        self.assertEqual(serial_io.normalize_port_name("COM12 (USB-SERIAL CH340 (COM12))"), "COM12")
        self.assertEqual(serial_io.normalize_port_name("\\\\.\\COM12 (FTDI)"), "\\\\.\\COM12")
        self.assertEqual(serial_io.normalize_port_name("/dev/ttyUSB0"), "/dev/ttyUSB0")
        self.assertEqual(serial_io.normalize_port_name("  DEMO / SIMULATION (Jura S8)  "), "DEMO / SIMULATION (Jura S8)")

        with mock.patch.object(serial_io.JuraSerialConnection, "_open_hardware_port", return_value=None):
            conn = serial_io.JuraSerialConnection("COM3 (USB Serial Port (COM3))")
            self.assertEqual(conn.port_name, "COM3")
            self.assertEqual(conn.raw_port_label, "COM3 (USB Serial Port (COM3))")

        prev_sess = web_server._active_session
        prev_port = web_server._current_port
        prev_mapper = web_server._mapper_engine
        try:
            web_server._active_session = None
            web_server._current_port = ""
            web_server._mapper_engine = None
            def fake_open(self):
                self.is_open = True

            with mock.patch.object(serial_io.JuraSerialConnection, "_open_hardware_port", fake_open):
                m1, err1 = web_server._get_or_create_mapper("COM3 (USB-SERIAL CH340 (COM3))")
                self.assertIsNone(err1)
                self.assertIsNotNone(m1)
                sess1 = web_server._active_session
                m2, err2 = web_server._get_or_create_mapper("COM3")
                self.assertIsNone(err2)
                self.assertIs(m2, m1)
                self.assertIs(web_server._active_session, sess1)
        finally:
            web_server.cleanup_resources()
            web_server._active_session = prev_sess
            web_server._current_port = prev_port
            web_server._mapper_engine = prev_mapper

    def test_allowed_origins_excludes_null(self):
        handler = web_server.SpectraApiHandler.__new__(web_server.SpectraApiHandler)
        origins = handler._allowed_origins()
        self.assertNotIn("null", origins)
        self.assertIn(f"http://127.0.0.1:{self.port}", origins)

    def test_static_path_traversal_blocked_with_403(self):
        for bad_path in ("/%2e%2e/version.py", "/%2e%2e/%2e%2e/etc/passwd", "/assets/..%2f..%2fversion.py", "/..\\version.py"):
            status, _body, _hdrs = self._http("GET", bad_path)
            self.assertEqual(status, 403, f"Expected 403 for traversal path {bad_path}, got {status}")

    def test_post_rejects_foreign_origin_with_403(self):
        for bad_headers in (
            {"Content-Type": "application/json", "Origin": "https://evil.example"},
            {"Content-Type": "application/json", "Origin": "http://localhost.evil.example:8080"},
            {"Content-Type": "application/json", "Origin": "null"},
            {"Content-Type": "application/json", "Origin": "null", "Sec-Fetch-Site": "cross-site", "Referer": "https://evil.example/"},
        ):
            status, body, _ = self._http(
                "POST",
                "/api/ui_prefs",
                body=b"{}",
                headers=bad_headers,
            )
            self.assertEqual(status, 403, f"Expected 403 for headers {bad_headers}")
            self.assertFalse(json.loads(body)["success"])

    def test_post_allows_linux_loopback_and_webkit_same_origin_headers(self):
        with tempfile.TemporaryDirectory() as td:
            prefs_path = os.path.join(td, "ui_prefs.json")
            with unittest.mock.patch("web_server.get_ui_prefs_path", return_value=prefs_path):
                for ok_headers in (
                    {"Content-Type": "application/json", "Origin": f"http://[::1]:{self.port}"},
                    {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}"},
                    {"Content-Type": "application/json", "Origin": "null", "Referer": f"http://127.0.0.1:{self.port}/?v=1"},
                    {"Content-Type": "application/json", "Origin": "null", "Sec-Fetch-Site": "same-origin"},
                ):
                    status, body, _ = self._http(
                        "POST",
                        "/api/ui_prefs",
                        body=b'{"lang":"cs"}',
                        headers=ok_headers,
                    )
                    self.assertEqual(status, 200, f"Expected 200 for headers {ok_headers}, got {status}")
                    parsed = json.loads(body)
                    self.assertTrue(parsed["success"])
                    self.assertEqual(parsed["prefs"]["lang"], "cs")

                # Arbitrary cross-port loopback Origin (e.g. :5174) must be rejected with 403
                st_xport, _, _ = self._http(
                    "POST",
                    "/api/ui_prefs",
                    body=b'{"lang":"en"}',
                    headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:5174"},
                )
                self.assertEqual(st_xport, 403)

                # Vite dev port 5173 allowed only when SPECTRA_DEV_CORS=1
                with unittest.mock.patch.dict(os.environ, {"SPECTRA_DEV_CORS": "1"}):
                    st_dev, _, _ = self._http(
                        "POST",
                        "/api/ui_prefs",
                        body=b'{"lang":"en"}',
                        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:5173"},
                    )
                    self.assertEqual(st_dev, 200)

    def test_post_rejects_invalid_and_non_object_json_with_400(self):
        for bad_body in (b"{not-json", b"[1, 2, 3]", b'"just-a-string"'):
            status, body, _ = self._http(
                "POST",
                "/api/ui_prefs",
                body=bad_body,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 400, f"Expected 400 for body {bad_body!r}, got {status}")
            self.assertFalse(json.loads(body)["success"])

    def test_set_threshold_invalid_value_returns_400(self):
        status, body, _ = self._http(
            "POST",
            "/api/set_threshold",
            body=json.dumps({"threshold": "not-an-int"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(body)["success"])

    def test_hmi_output_path_outside_downloads_rejected_with_403(self):
        for endpoint in ("/api/hmi/patch", "/api/hmi/export_report"):
            status, body, _ = self._http(
                "POST",
                endpoint,
                body=json.dumps({"output_path": "/tmp/spectra_escape_test.bin"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 403, f"Expected 403 for {endpoint} outside ~/Downloads")
            self.assertFalse(json.loads(body)["success"])

    def test_debug_diagnostics_does_not_block_when_session_lock_held(self):
        acquired = threading.Event()
        release = threading.Event()

        def hold_lock():
            with web_server._session_lock:
                acquired.set()
                release.wait(timeout=3.0)

        t = threading.Thread(target=hold_lock, daemon=True)
        t.start()
        try:
            self.assertTrue(acquired.wait(timeout=1.0))
            t0 = time.monotonic()
            diag = web_server.get_debug_diagnostics()
            elapsed = time.monotonic() - t0
            self.assertLess(elapsed, 0.5)
            self.assertEqual(diag["serial"]["status"], "BUSY")
        finally:
            release.set()
            t.join(timeout=2.0)


class TestUpdaterSecurity(unittest.TestCase):
    def test_verify_windows_updater_binary_requires_sha256_by_default(self):
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tf:
            tf.write(b"MZ" + b"\x00" * 128)
            path = tf.name
        try:
            with self.assertRaises(updater.UpdateError):
                updater.verify_windows_updater_binary(path, expected_sha256="")
        finally:
            os.remove(path)

    def test_validate_download_url_enforces_https_github_allowlist(self):
        updater._validate_download_url("https://github.com/Pr0xyA-91/spectra/releases/download/v1/a.exe")
        updater._validate_download_url("https://objects.githubusercontent.com/some/path")
        with self.assertRaises(updater.UpdateError):
            updater._validate_download_url("http://github.com/Pr0xyA-91/spectra/file.exe")
        with self.assertRaises(updater.UpdateError):
            updater._validate_download_url("https://evil.example/malware.exe")

    def test_safe_extract_tarball_blocks_symlinks_hardlinks_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_sym = os.path.join(tmpdir, "sym.tar.gz")
            with tarfile.open(tar_sym, "w:gz") as tf:
                info = tarfile.TarInfo(name="pkg/evil_link")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tf.addfile(info)
            with self.assertRaises(updater.UpdateError):
                updater._safe_extract_tarball(tar_sym, os.path.join(tmpdir, "out1"))

            tar_lnk = os.path.join(tmpdir, "lnk.tar.gz")
            with tarfile.open(tar_lnk, "w:gz") as tf:
                info = tarfile.TarInfo(name="pkg/hard_link")
                info.type = tarfile.LNKTYPE
                info.linkname = "/etc/passwd"
                tf.addfile(info)
            with self.assertRaises(updater.UpdateError):
                updater._safe_extract_tarball(tar_lnk, os.path.join(tmpdir, "out2"))

            tar_trav = os.path.join(tmpdir, "trav.tar.gz")
            with tarfile.open(tar_trav, "w:gz") as tf:
                data = b"pwned"
                info = tarfile.TarInfo(name="../escape.txt")
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            with self.assertRaises(updater.UpdateError):
                updater._safe_extract_tarball(tar_trav, os.path.join(tmpdir, "out3"))


class TestSpectraAIAndCalibrations(unittest.TestCase):
    def test_parse_counters_from_ocr_text_no_nameerror(self):
        ocr = "Espresso: 120\nCoffee: 45\nCleanings: 8\nFilter: 75%\n"
        parsed = spectra_ai._parse_counters_from_ocr_text(ocr)
        self.assertEqual(parsed["products"].get("Espresso"), 120)
        self.assertEqual(parsed["products"].get("Coffee"), 45)
        self.assertEqual(parsed["maintenance"].get("Cleanings"), 8)
        self.assertEqual(parsed["cockpit"].get("Filter"), "75%")

    def test_extract_image_rejects_invalid_base64_early(self):
        res = spectra_ai.extract_joe_from_image_with_ai("!!!not-base64!!!")
        self.assertFalse(res["success"])
        self.assertIn("base64", res["error"].lower())

    def test_is_model_in_installed_uses_exact_tag_delimiter(self):
        self.assertFalse(spectra_ai._is_model_in_installed("gemma3", ["gemma3n:4b"]))
        self.assertTrue(spectra_ai._is_model_in_installed("gemma3", ["gemma3:4b"]))
        self.assertTrue(spectra_ai._is_model_in_installed("gemma3:4b", ["gemma3:4b"]))

    def test_verify_calibration_patch_requires_eeprom_words_proof(self):
        patch_no_eeprom = {
            "schema": "spectra.offset_patch.v1",
            "identity": {"ef_code": "EF518", "model_name": "XJ5"},
            "override": {
                "products": [{"name": "Espresso", "addr": "0x0001", "joe_count": 42}],
                "maintenance": [],
            },
        }
        ok, reason, _ = scc.verify_calibration_patch(patch_no_eeprom)
        self.assertFalse(ok)
        self.assertIn("eeprom_words", reason.lower())

        patch_with_proof = {
            "schema": "spectra.offset_patch.v1",
            "identity": {"ef_code": "EF518", "model_name": "XJ5"},
            "eeprom_words": {"0x0001": 42},
            "override": {
                "products": [{"name": "Espresso", "addr": "0x0001", "joe_count": 42}],
                "maintenance": [],
            },
        }
        ok2, reason2, _ = scc.verify_calibration_patch(patch_with_proof)
        self.assertTrue(ok2, f"Unexpected verification error: {reason2}")

    def test_md_cell_escapes_pipes_and_newlines(self):
        self.assertEqual(scc._md_cell("A|B\nC\r`D`"), "A B C D")

    def test_issue_has_pr_marker_fails_closed_on_api_error(self):
        with mock.patch.object(scc, "_github_api_request", side_effect=RuntimeError("network down")):
            self.assertTrue(scc._issue_has_pr_marker("owner/repo", 123, "tok"))


class TestGitHubAuthHardening(unittest.TestCase):
    def test_get_auth_status_returns_unauthenticated_on_non_401_failure(self):
        with mock.patch.object(github_auth, "resolve_token", return_value={"token": "gho_fake", "method": "device_flow", "login": ""}), \
             mock.patch.object(github_auth, "validate_token", return_value=(False, "", "Network timeout")):
            st = github_auth.get_auth_status()
            self.assertFalse(st["authenticated"])
            self.assertIn("timeout", st["error"].lower())

    def test_poll_device_flow_parses_http_error_json(self):
        err_body = io.BytesIO(json.dumps({"error": "bad_verification_code", "error_description": "Code expired"}).encode("utf-8"))
        http_err = HTTPError("https://github.com/login/oauth/access_token", 400, "Bad Request", {}, err_body)
        with mock.patch.object(github_auth, "get_client_id", return_value="Iv1.fakeclient"), \
             mock.patch("urllib.request.urlopen", side_effect=http_err):
            res = github_auth.poll_device_flow("dev-code-123", interval=5)
            self.assertFalse(res["success"])
            self.assertIn("Code expired", res["error"])


class TestSmartConnectRawVsWireAndMapperSweepBlock(unittest.TestCase):
    def test_query_encrypted_autodetects_raw_frame_for_jura_usb_box(self):
        import jura_protocol as jp

        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        conn.is_demo = False
        conn.is_open = True
        conn.encrypted_wire_mode = None

        expected_reply = jp.build_encrypted_frame("@t0:EF999M V01.00\r\n", 0x20)
        written = []

        def fake_write(data, inter_byte_delay=0.0):
            written.append((data, inter_byte_delay))
            return len(data)

        def fake_read(max_bytes=512, timeout_sec=None):
            # Official Jura USB box answers raw '&'-frame directly (does NOT understand double 4:1 encoding)
            if written and written[-1][0].startswith(b"&") and len(written[-1][0]) < 40:
                return expected_reply
            return b""

        conn.write = fake_write
        conn.read = fake_read
        conn.drain_rx = lambda: None

        resp = conn.query_encrypted("@T0\r\n", key=0x20, timeout=0.15)
        self.assertIsNotNone(resp)
        self.assertIn("EF999M", resp)
        self.assertEqual(conn.encrypted_wire_mode, "raw_frame")

    def test_mapper_sweep_block_smart_connect_4word_stride_and_abort(self):
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        conn.is_demo = False
        conn.is_open = True
        conn.wire_mode = "smart_connect"

        queried = []

        def fake_enc(cmd, key=0x20, timeout=0.8):
            queried.append(cmd.strip())
            if cmd.startswith("@TR:32,"):
                bank = int(cmd.split(",")[1].strip(), 16)
                if bank < 4:
                    # 4 words per bank
                    vals = [bank * 4 + i + 1 for i in range(4)]
                    return f"@tr:32,{bank:02X}," + "".join(f"{v:04X}" for v in vals)
            return None

        conn.query_encrypted = fake_enc
        conn.query_ascii = lambda *a, **kw: None

        mapper = memory_mapper.MemoryMapperEngine(conn)
        res0 = mapper.sweep_block(0)
        self.assertEqual(len(res0["registers"]), 16)
        self.assertFalse(res0["abort_sweep"])
        self.assertEqual(res0["registers"][0].val, 1)
        self.assertEqual(res0["registers"][15].val, 16)
        self.assertEqual(queried[:4], ["@TR:32,00", "@TR:32,01", "@TR:32,02", "@TR:32,03"])

        # Block 1 has no banks left -> end_of_table + abort_sweep
        res1 = mapper.sweep_block(1)
        self.assertTrue(res1["abort_sweep"])
        self.assertTrue(res1.get("end_of_table"))


if __name__ == "__main__":
    unittest.main()
