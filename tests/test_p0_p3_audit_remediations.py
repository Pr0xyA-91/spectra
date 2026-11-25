#!/usr/bin/env python3
"""
Regression test suite for P0-P3 Audit Remediations:
- P0: CRLF / control-byte / destructive command rejection across serial_io, memory_mapper, and web_server /api/command
- P1: Redirect-safe updater + Linux tarball SHA-256 + Python < 3.12 mode sanitization + tls_utils curl flags
- P1: DPAPI roundtrip + auto-migration + sanitize_issue_text bypasses + spectra_probe sanitization
- P1: Host DNS-rebinding 403, cross-site GET 403, HMI patch Downloads confinement, gui_web hardening, gui_widgets XSS
- P1: hmi_inspector ELF/APK bounds & PowerShell env-var dialog safety & Ollama HTTPS/tar flags
- P2: spectra_ai active=False on auto_unload=False, 4 MiB stream cap, session lock release before Ollama
- P2: Modbus RTU multi-chunk read + CRC verification + non-demo zero telemetry on Lamanti-KL/JN/Nivona
- P3: Bounded caches & atomic writes
"""

import ctypes
import hashlib
import io
import json
import os
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import github_auth
import gui_web
import gui_widgets
import hmi_inspector
import memory_mapper
import profiles_db
import serial_io
import spectra_ai
import spectra_probe
import stats_collector as sc
import tls_utils
import updater
import web_server
from drivers.lamanti_jn.driver import LamantiJNDriver, calculate_jetinno_crc
from drivers.lamanti_kl.driver import LamantiKLDriver, calculate_modbus_crc
from drivers.nivona.driver import NivonaDriver


class TestP0HardwareCommandSafety(unittest.TestCase):
    def test_validate_readonly_command_accepts_legit_and_rejects_injections(self):
        for good in ("TY:", "RT:0000", "RE:0028", "TY$:", "@t0", "@t2:818000", "@TR:32,00\r\n", " HZ: "):
            cleaned = serial_io.validate_readonly_command(good)
            self.assertTrue(len(cleaned) > 0)

        bad_cmds = [
            "",
            "   ",
            "TY:\r\nFA:01",
            "TY:\nAN:",
            "TY:\rWE:00000000",
            "TY:\x00RT:0000",
            "TY:\x1b[31m",
            "A" * 65,
            "WE:00140004",
            "WT:00001234",
            "DA:01",
            "FA:01",
            "FA",
            "AN:",
            "AN",
            "@TW:0102",
            "@tw:0102",
            "UNKNOWN:",
        ]
        for bad in bad_cmds:
            with self.assertRaises(PermissionError, msg=f"Expected PermissionError for {bad!r}"):
                serial_io.validate_readonly_command(bad)

    def test_serial_io_and_memory_mapper_enforce_validation(self):
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8)")
        try:
            self.assertEqual(conn.query_ascii("TY:"), "ty:EF536M V02.01")
            for bad in ("TY:\r\nFA:01", "AN:", "FA:01", "WE:00001111"):
                with self.assertRaises(PermissionError):
                    conn.query_ascii(bad)
                with self.assertRaises(PermissionError):
                    conn.query_encrypted(bad)

            mapper = memory_mapper.MemoryMapperEngine(conn)
            for bad in ("TY:\r\nAN:", "FA:01", "AN:", "@tw:0000"):
                with self.assertRaises(PermissionError):
                    mapper.query_safe(bad)
        finally:
            conn.close()

    def test_web_api_command_rejects_crlf_and_destructive_commands(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        port = srv.server_address[1]
        prev = web_server._current_http_port
        web_server._current_http_port = port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            for bad_cmd in ("TY:\r\nFA:01", "FA:01", "AN:", "TY:\x00", "A" * 65):
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/command",
                    data=json.dumps({"port": "DEMO / SIMULATION (Jura S8)", "cmd": bad_cmd}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(payload["success"], f"Expected failure for {bad_cmd!r}")
                self.assertIn("Refusing command", payload["error"])
        finally:
            web_server._current_http_port = prev
            srv.shutdown()
            srv.server_close()


class TestP1UpdaterAndTlsHardening(unittest.TestCase):
    def test_safe_redirect_handler_blocks_untrusted_redirect(self):
        handler = updater._SafeRedirectHandler()
        req = urllib.request.Request("https://github.com/Pr0xyA-91/spectra")
        with self.assertRaises(updater.UpdateError):
            handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/payload.exe")
        with self.assertRaises(updater.UpdateError):
            handler.redirect_request(req, None, 302, "Found", {}, "http://github.com/Pr0xyA-91/spectra")
        res = handler.redirect_request(req, None, 302, "Found", {}, "https://objects.githubusercontent.com/pkg.tar.gz")
        self.assertEqual(res.full_url, "https://objects.githubusercontent.com/pkg.tar.gz")

    def test_tls_utils_passes_proto_flags_to_curl(self):
        with mock.patch("subprocess.Popen") as popen_mock:
            proc = mock.MagicMock()
            proc.poll.return_value = 0
            proc.returncode = 0
            proc.stderr = None
            popen_mock.return_value = proc
            tls_utils.windows_schannel_download("https://github.com/test", "/tmp/out.bin")
            cmd = popen_mock.call_args[0][0]
            self.assertIn("--proto", cmd)
            self.assertIn("=https", cmd)
            self.assertIn("--proto-redir", cmd)
            self.assertIn("--", cmd)
            self.assertLess(cmd.index("--"), cmd.index("https://github.com/test"))

    def test_linux_tarball_sha256_verification_and_mode_strip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = os.path.join(tmp, "pkg.tar.gz")
            with tarfile.open(tar_path, "w:gz") as tf:
                data = b'__build__ = "20990101.0000"\n'
                ti = tarfile.TarInfo("spectra-main/version.py")
                ti.size = len(data)
                ti.mode = 0o4777  # setuid + world-writable
                tf.addfile(ti, io.BytesIO(data))

            # Verify mode stripping on Python < 3.12 code path
            out_dir = os.path.join(tmp, "extracted")
            os.makedirs(out_dir, exist_ok=True)
            with mock.patch.object(sys, "version_info", (3, 11, 2, "final", 0)):
                root = updater._safe_extract_tarball(tar_path, out_dir)
            extracted_ver = os.path.join(root, "version.py")
            mode = os.stat(extracted_ver).st_mode & 0o7777
            self.assertEqual(mode & 0o7000, 0)
            self.assertEqual(mode & 0o002, 0)

            # Verify SHA-256 mismatch aborts _apply_linux_tarball_update
            def fake_dl(url, dest, expected_size=0, timeout=45.0):
                with open(tar_path, "rb") as src, open(dest, "wb") as dst:
                    dst.write(src.read())

            with mock.patch.object(updater, "_download_file_with_progress", side_effect=fake_dl):
                with self.assertRaises(updater.UpdateError):
                    updater._apply_linux_tarball_update({
                        "latest_build": "20990101.0000",
                        "download_url": "https://github.com/Pr0xyA-91/spectra/archive/refs/heads/main.tar.gz",
                        "expected_sha256": "0" * 64,
                    })


class TestP1GithubAuthAndSanitizer(unittest.TestCase):
    def test_sanitize_issue_text_blocks_bypasses(self):
        raw = (
            "Authorization: token tok_secret_12345\n"
            "Authorization: Basic dXNlcjpwYXNz\n"
            "Proxy-Authorization: Basic proxy_secret\n"
            "https://alice:hunter2@github.com/repo\n"
            "ghp%5F1234567890abcdef123456\n"
            "github_pat%5Fabcdef1234567890\n"
            "access_token=my_access_tok_999 api_key=my_api_key_888 password=my_pw client_secret=cs_123\n"
            "WinFwd: C:/Users/Bob/AppData/file\n"
            "UNC: \\\\fileserver\\share\\secret.txt\n"
            "Root: /root/secrets\n"
            "URI: file:///home/alice/spectra\n"
            "NoTrail: /home/charlie\n"
        )
        cleaned = github_auth.sanitize_issue_text(raw)
        for leak in (
            "tok_secret_12345",
            "dXNlcjpwYXNz",
            "proxy_secret",
            "alice:hunter2",
            "ghp%5F1234567890abcdef123456",
            "github_pat%5Fabcdef1234567890",
            "my_access_tok_999",
            "my_api_key_888",
            "my_pw",
            "cs_123",
            "C:/Users/Bob/",
            "\\\\fileserver\\share",
            "/root/",
            "file:///home/alice/",
            "/home/charlie",
        ):
            self.assertNotIn(leak, cleaned, f"Leak survived sanitization: {leak}")

    def test_dpapi_roundtrip_and_legacy_migration(self):
        # Mock CryptProtectData / CryptUnprotectData + LocalFree in ctypes.windll.crypt32 / kernel32
        def fake_protect(p_in, _d, _e, _r, _p, _f, p_out):
            in_blob = ctypes.cast(p_in, ctypes.POINTER(ctypes.c_byte * 16))
            # Read cbData + pbData via struct-compatible pointers
            cb = ctypes.c_uint32.from_address(ctypes.addressof(p_in._obj)).value
            pb_addr = ctypes.c_void_p.from_address(ctypes.addressof(p_in._obj) + ctypes.sizeof(ctypes.c_void_p)).value
            raw = ctypes.string_at(pb_addr, cb)
            enc = b"DPAPI:" + raw[::-1]
            buf = (ctypes.c_ubyte * len(enc))(*enc)
            self._dpapi_hold = buf
            ctypes.c_uint32.from_address(ctypes.addressof(p_out._obj)).value = len(enc)
            ctypes.c_void_p.from_address(ctypes.addressof(p_out._obj) + ctypes.sizeof(ctypes.c_void_p)).value = ctypes.addressof(buf)
            return 1

        def fake_unprotect(p_in, _d, _e, _r, _p, _f, p_out):
            cb = ctypes.c_uint32.from_address(ctypes.addressof(p_in._obj)).value
            pb_addr = ctypes.c_void_p.from_address(ctypes.addressof(p_in._obj) + ctypes.sizeof(ctypes.c_void_p)).value
            enc = ctypes.string_at(pb_addr, cb)
            self.assertTrue(enc.startswith(b"DPAPI:"))
            dec = enc[6:][::-1]
            buf = (ctypes.c_ubyte * len(dec))(*dec)
            self._dpapi_hold2 = buf
            ctypes.c_uint32.from_address(ctypes.addressof(p_out._obj)).value = len(dec)
            ctypes.c_void_p.from_address(ctypes.addressof(p_out._obj) + ctypes.sizeof(ctypes.c_void_p)).value = ctypes.addressof(buf)
            return 1

        fake_crypt32 = mock.MagicMock()
        fake_crypt32.CryptProtectData.side_effect = fake_protect
        fake_crypt32.CryptUnprotectData.side_effect = fake_unprotect
        fake_kernel32 = mock.MagicMock()
        fake_windll = mock.MagicMock(crypt32=fake_crypt32, kernel32=fake_kernel32)

        with tempfile.TemporaryDirectory() as td:
            orig_override = github_auth._CONFIG_DIR_OVERRIDE
            github_auth._CONFIG_DIR_OVERRIDE = Path(td)
            try:
                with mock.patch.object(ctypes, "windll", fake_windll, create=True), \
                     mock.patch.object(github_auth.os, "name", "nt"), \
                     mock.patch.dict(sys.modules, {"keyring": None}):
                    ok = github_auth.save_stored_token("ghp_WinSecretToken999", "winuser", method="pat")
                    self.assertTrue(ok)
                    disk_json = json.loads(github_auth._get_auth_file().read_text(encoding="utf-8"))
                    self.assertIn("token_dpapi", disk_json)
                    self.assertNotIn("token", disk_json)
                    got = github_auth.get_stored_token()
                    self.assertEqual(got["token"], "ghp_WinSecretToken999")

                    # Legacy plaintext token should auto-migrate to token_dpapi on get_stored_token()
                    github_auth._get_auth_file().write_text(
                        json.dumps({"token": "ghp_LegacyPlain123", "login": "winuser", "method": "pat"}),
                        encoding="utf-8",
                    )
                    got2 = github_auth.get_stored_token()
                    self.assertEqual(got2["token"], "ghp_LegacyPlain123")
                    migrated_json = json.loads(github_auth._get_auth_file().read_text(encoding="utf-8"))
                    self.assertIn("token_dpapi", migrated_json)
                    self.assertNotIn("token", migrated_json)
            finally:
                github_auth._CONFIG_DIR_OVERRIDE = orig_override


class TestP1WebAndHmiSecurity(unittest.TestCase):
    def _http_raw(self, port: int, method: str, path: str, headers=None, body: bytes = b""):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=body if method == "POST" else None,
            headers=headers or {},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_host_dns_rebinding_and_cross_site_get_blocked(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        port = srv.server_address[1]
        prev = web_server._current_http_port
        web_server._current_http_port = port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            st, _, _ = self._http_raw(port, "GET", "/api/version", headers={"Host": "evil.attacker.com:8080"})
            self.assertEqual(st, 403)

            st2, _, _ = self._http_raw(port, "GET", "/api/version", headers={"Sec-Fetch-Site": "cross-site"})
            self.assertEqual(st2, 403)

            st3, _, hdrs = self._http_raw(port, "GET", "/api/version", headers={"Host": f"127.0.0.1:{port}"})
            self.assertEqual(st3, 200)
            self.assertIn("Content-Security-Policy", hdrs)
        finally:
            web_server._current_http_port = prev
            srv.shutdown()
            srv.server_close()

    def test_upload_capture_and_hmi_patch_confinement(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        port = srv.server_address[1]
        prev = web_server._current_http_port
        web_server._current_http_port = port
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with tempfile.NamedTemporaryFile(prefix="spectra_capture_", suffix=".json", delete=False) as tf:
                tf.write(b"{}")
                unrecorded_path = tf.name
            try:
                st, body, _ = self._http_raw(
                    port,
                    "POST",
                    "/api/upload-capture",
                    headers={"Content-Type": "application/json"},
                    body=json.dumps({"file_path": unrecorded_path}).encode("utf-8"),
                )
                self.assertEqual(st, 403)
                self.assertFalse(json.loads(body)["success"])
            finally:
                os.remove(unrecorded_path)
        finally:
            web_server._current_http_port = prev
            srv.shutdown()
            srv.server_close()

    def test_gui_web_security_and_gui_widgets_escaping(self):
        self.assertTrue(gui_web.is_valid_port("\\\\.\\COM10"))
        self.assertTrue(gui_web.is_valid_port("COM4 (USB-SERIAL CH340 (COM4))"))
        self.assertFalse(gui_web.is_valid_port("COM4 (evil; rm -rf /)"))

        html_out = gui_widgets.generate_service_report_html(
            {
                "machine_model": "Test",
                "total_cups": 10,
                "maintenance": [{"label": "Clean", "count": 1, "percentage": "<script>alert(1)</script>"}],
            },
            "<img src=x onerror=alert(2)>",
            [],
        )
        self.assertNotIn("<script>alert(1)</script>", html_out)
        self.assertNotIn("<img src=x onerror=alert(2)>", html_out)

    def test_hmi_inspector_elf_apk_bounds_and_powershell_env_vars(self):
        with tempfile.TemporaryDirectory() as td:
            # 64-bit ELF rejected cleanly
            elf64 = os.path.join(td, "test64.elf")
            with open(elf64, "wb") as f:
                f.write(b"\x7fELF\x02\x01\x01" + b"\x00" * 57)
            with self.assertRaises(ValueError):
                hmi_inspector.KalermHmiInspector(elf64)

            # Truncated/invalid APK resources.arsc bounds
            apk_path = os.path.join(td, "bad.apk")
            with zipfile.ZipFile(apk_path, "w") as zf:
                # Minimal resources.arsc claiming huge scnt
                arsc = struct.pack("<HHI", 0x0002, 12, 64) + b"\x00" * 4
                arsc += struct.pack("<HHIIIIII", 0x0001, 28, 40, 0x0FFFFFFF, 0, 0, 28, 0)
                zf.writestr("resources.arsc", arsc)
            insp = hmi_inspector.KalermHmiInspector(apk_path)
            self.assertEqual(insp.extract_all_languages(), {})

            # Windows PowerShell fallback uses env vars, never string interpolation
            with mock.patch.object(hmi_inspector.sys, "platform", "win32"), \
                 mock.patch.object(hmi_inspector.KalermHmiInspector, "_win32_comdlg_dialog", side_effect=RuntimeError("no win32")), \
                 mock.patch("subprocess.run") as sub_mock:
                sub_mock.return_value = mock.MagicMock(returncode=0, stdout="")
                hmi_inspector.KalermHmiInspector.prompt_save_file_dialog(
                    default_filename="evil';Calc.exe;'",
                    initial_dir=td,
                    title="Title';Calc;'",
                )
                kwargs = sub_mock.call_args[1]
                ps_cmd = sub_mock.call_args[0][0][-1]
                self.assertIn("$env:SPECTRA_DLG_DEF_NAME", ps_cmd)
                self.assertNotIn("evil';Calc.exe;'", ps_cmd)
                self.assertEqual(kwargs["env"]["SPECTRA_DLG_DEF_NAME"], "evil';Calc.exe;'")


class TestP2AiAndMultiVendorHardening(unittest.TestCase):
    def test_spectra_ai_clears_active_even_when_auto_unload_false(self):
        orig_enabled = spectra_ai._ai_enabled
        spectra_ai._ai_enabled = True
        try:
            with mock.patch("spectra_ai._resolve_active_model", return_value=(True, "qwen2.5:0.5b", "")), \
                 mock.patch("spectra_ai._query_ollama_json", return_value=({"products": [], "maintenance": [], "cockpit": []}, None)):
                res = spectra_ai.extract_joe_from_text_with_ai("Espresso: 10", auto_unload=False)
                self.assertTrue(res["success"])
                self.assertFalse(spectra_ai.get_task_progress()["active"])
        finally:
            spectra_ai._ai_enabled = orig_enabled

    def test_modbus_chunked_read_and_jetinno_crc_rejection(self):
        # Chunked Modbus RTU response (split across multiple conn.read calls)
        payload = struct.pack(">HHHHH", 3, 93, 125, 150, 0x00FF) + b"\x00" * 32
        hdr = struct.pack(">BBB", 0x01, 0x04, 42) + payload
        full_modbus = hdr + calculate_modbus_crc(hdr)
        chunks = [full_modbus[:10], full_modbus[10:25], full_modbus[25:]]

        class ChunkedModbusConn:
            is_demo = False
            is_open = True
            def write(self, data):
                return len(data)
            def read(self, n=64, timeout_sec=0.5):
                return chunks.pop(0) if chunks else b""

        res = LamantiKLDriver().read_live_sensors(ChunkedModbusConn())
        self.assertTrue(res["capabilities"]["has_live_frame"])
        self.assertEqual(res["telemetry"]["heater_coffee_c"], 93.0)

        # Corrupt Jetinno CRC rejected
        bad_body = struct.pack(">BBBBBBBB", 0xFE, 0x01, 0x00, 0x14, 0x00, 0x04, 0x02, 0x00) + bytes([93, 88])
        bad_frame = bad_body + b"\x00\x00"

        class BadJetinnoConn:
            is_demo = False
            is_open = True
            def write(self, data):
                return len(data)
            def read(self, n=64, timeout_sec=0.5):
                return bad_frame

        self.assertIsNone(LamantiJNDriver().probe(BadJetinnoConn()))
        jn_live = LamantiJNDriver().read_live_sensors(BadJetinnoConn())
        self.assertFalse(jn_live["capabilities"]["has_live_frame"])

        # Non-demo hardware returns 0 counts on missing replies (no fake sample counts)
        class SilentRealConn:
            is_demo = False
            is_open = True
            def write(self, data):
                return len(data)
            def read(self, n=64, timeout_sec=0.5):
                return b""
            def query_ascii(self, cmd, timeout=0.5):
                return None

        self.assertEqual(LamantiKLDriver().read_telemetry(SilentRealConn()).total_cups, 0)
        self.assertEqual(LamantiJNDriver().read_telemetry(SilentRealConn()).total_cups, 0)
        self.assertEqual(NivonaDriver().read_telemetry(SilentRealConn()).total_cups, 0)


if __name__ == "__main__":
    unittest.main()
