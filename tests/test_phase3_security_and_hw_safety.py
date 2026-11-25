#!/usr/bin/env python3
"""
Phase 3 Adversarial Security & Hardware-Safety Regression Suite (F-01 through F-12).
Verifies every remediation across Rust PyO3 FFI, EEPROM restore interlocks,
64-bit Win32 DPAPI ctypes, HTTP CSP & sidecar nonce, ELF32 binary patcher safety,
SQLite archive privacy/Unicode/retention, Linux updater fail-closed SHA-256,
HMI endpoint confinement, and debug log redaction/rotation.
"""

import ctypes
import hashlib
import io
import json
import os
import socket
import stat
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import contrib.restore_eeprom as restore_eeprom_mod
import github_auth
import gui_web
import hmi_inspector
import report_archive
import serial_io
import spectra_app
import updater
import web_server
from drivers.jura.driver import JuraDriver


class TestF01RustPyO3Safety(unittest.TestCase):
    def test_send_hex_rejects_utf8_and_unsafe_frames_on_live_so(self):
        try:
            import spectra_py
        except ImportError:
            self.skipTest("spectra_py.so not built")

        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX unavailable on this platform")

        with tempfile.TemporaryDirectory() as td:
            sock_path = os.path.join(td, "mock_jura.sock")
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(sock_path)
            srv.listen(1)

            def _responder():
                conn, _ = srv.accept()
                try:
                    data = conn.recv(64)
                    if data:
                        conn.sendall(spectra_py.encode_jura_ascii("ty:EF518M V02.20\r\n"))
                finally:
                    conn.close()
                    srv.close()

            t = threading.Thread(target=_responder, daemon=True)
            t.start()
            sess = spectra_py.JuraSession.open_unix_raw(sock_path, "/dev/ttyS1", 0, 1000)

            # Non-ASCII UTF-8 4-byte even string must raise ValueError, NOT PanicException
            with self.assertRaises(ValueError):
                sess.send_hex("€a")

            # Unlisted actuator command must fail Rust strict read-only allowlist
            with self.assertRaises(ValueError):
                sess.send_ascii("FN:01")

            # Disabling safety without explicit lab_confirm_token must raise PermissionError
            with self.assertRaises(PermissionError):
                sess.send_ascii("WE:0030,FFFF", True, False)

            with self.assertRaises(PermissionError):
                sess.send_hex("AA BB CC", None, False)

            # Raw 4:1-encoded destructive WE: frame must be blocked by default
            we_wire = spectra_py.encode_jura_ascii("WE:0030,FFFF\r\n").hex()
            with self.assertRaises(ValueError):
                sess.send_hex(we_wire)

            # Valid read-only TY: succeeds cleanly
            resp = sess.send_ascii("TY:")
            self.assertEqual(resp, "ty:EF518M V02.20")
            t.join(timeout=2.0)


class TestF02EepromRestoreAndLabApiInterlocks(unittest.TestCase):
    def test_query_unsafe_lab_command_requires_token_and_allowlist(self):
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura Impressa XJ5)")
        try:
            with self.assertRaises(PermissionError):
                conn.query_unsafe_lab_command("WE:0010,0005")
            with self.assertRaises(PermissionError):
                conn.query_unsafe_lab_command("AN:", confirm_token=serial_io.LAB_WRITE_CONFIRM_TOKEN)
            with self.assertRaises(PermissionError):
                conn.query_unsafe_lab_command("WE:0010,0005\r\nAN:", confirm_token=serial_io.LAB_WRITE_CONFIRM_TOKEN)

            ok = conn.query_unsafe_lab_command("WE:0010,0005", confirm_token=serial_io.LAB_WRITE_CONFIRM_TOKEN)
            self.assertEqual(ok, "ok:")
            self.assertEqual(conn.query_ascii("RE:0010"), "re:0005")

            # Actuator driver requires explicit confirm_lab_test=True
            drv = JuraDriver()
            self.assertFalse(drv.test_actuator(conn, "enter_test_mode"))
            self.assertTrue(drv.test_actuator(conn, "enter_test_mode", confirm_lab_test=True))
        finally:
            conn.close()

    def test_restore_eeprom_aborts_before_crc_on_partial_failure_and_creates_backup(self):
        sent_lab_cmds = []

        class FakeConn:
            def __init__(self, *args, **kwargs):
                self.is_open = True
                self.mem = {"0010": "0001", "0011": "0002", "0075": "AAAA"}

            def open(self):
                self.is_open = True

            def close(self):
                self.is_open = False

            def query_ascii(self, cmd, timeout=1.0):
                if cmd == "TY:":
                    return "ty:EF518M V02.20"
                if cmd.startswith("RE:"):
                    addr = cmd[3:].upper()
                    return f"re:{self.mem.get(addr, '0000')}"
                return None

            def query_unsafe_lab_command(self, cmd, *, confirm_token="", timeout=1.2):
                assert confirm_token == serial_io.LAB_WRITE_CONFIRM_TOKEN
                sent_lab_cmds.append(cmd)
                # First write succeeds, second write fails verification read-back
                if cmd == "WE:0010,00FF":
                    self.mem["0010"] = "00FF"
                    return "ok:"
                return "err:"

        with tempfile.TemporaryDirectory() as td:
            spec_path = os.path.join(td, "spec.json")
            with open(spec_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "ef_code": "EF518M",
                        "non_zero_eeprom": {
                            "0010": "00FF",
                            "0011": "00EE",
                            "0075": "1234",  # CRC register must be excluded from direct WE:
                        },
                    },
                    f,
                )

            with mock.patch.object(restore_eeprom_mod.serial_io, "JuraSerialConnection", FakeConn):
                # Default dry_run=True writes nothing
                ok_dry = restore_eeprom_mod.restore_eeprom("/dev/ttyUSB0", spec_path)
                self.assertTrue(ok_dry)
                self.assertEqual(sent_lab_cmds, [])

                # Live mode without confirm_lab_write must refuse
                ok_unconfirmed = restore_eeprom_mod.restore_eeprom("/dev/ttyUSB0", spec_path, dry_run=False)
                self.assertFalse(ok_unconfirmed)
                self.assertEqual(sent_lab_cmds, [])

                # Live mode with partial write failure MUST create backup and MUST NOT send AN:0B or WE:0075
                ok_partial = restore_eeprom_mod.restore_eeprom(
                    "/dev/ttyUSB0",
                    spec_path,
                    dry_run=False,
                    inter_write_delay=0.0,
                    confirm_lab_write=True,
                    backup_dir=td,
                    non_interactive_confirm=True,
                )
                self.assertFalse(ok_partial)
                self.assertNotIn("AN:0B", sent_lab_cmds)
                self.assertFalse(any(c.startswith("WE:0075") for c in sent_lab_cmds))
                backups = [p for p in os.listdir(td) if p.startswith("eeprom_prewrite_backup_")]
                self.assertEqual(len(backups), 1)
                if os.name != "nt":
                    mode = stat.S_IMODE(os.stat(os.path.join(td, backups[0])).st_mode)
                    self.assertEqual(mode, 0o600)


class TestF03DpapiCtypesSignatures(unittest.TestCase):
    def test_dpapi_configures_argtypes_restype_and_uses_use_last_error(self):
        fake_crypt32 = mock.MagicMock()
        fake_kernel32 = mock.MagicMock()
        seen_calls = []

        def fake_windll(name, use_last_error=False):
            seen_calls.append((name, use_last_error))
            return fake_crypt32 if name == "crypt32" else fake_kernel32

        class DummyBlob(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        with mock.patch.object(ctypes, "WinDLL", side_effect=fake_windll, create=True):
            c32, k32 = github_auth._get_win32_dpapi_handles(DummyBlob)
        self.assertEqual(seen_calls, [("crypt32", True), ("kernel32", True)])
        self.assertEqual(len(c32.CryptProtectData.argtypes), 7)
        self.assertEqual(len(c32.CryptUnprotectData.argtypes), 7)
        self.assertEqual(k32.LocalFree.argtypes, [ctypes.c_void_p])
        self.assertEqual(k32.LocalFree.restype, ctypes.c_void_p)


class TestF05F06F10F12WebSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = web_server.SpectraThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path: str, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_csp_blocks_inline_scripts_and_version_echoes_sidecar_nonce(self):
        with mock.patch.dict(os.environ, {"SPECTRA_SIDECAR_NONCE": "deadbeef1234567890abcdef12345678"}, clear=False):
            status, _body, hdrs = self._req("/api/version")
        self.assertEqual(status, 200)
        csp = hdrs.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", csp)
        self.assertIn("frame-ancestors 'self'", csp)
        script_part = csp.split("script-src", 1)[1].split(";", 1)[0]
        self.assertNotIn("unsafe-inline", script_part)
        self.assertNotIn("blob:", script_part)
        self.assertNotIn("data:", script_part)
        self.assertEqual(hdrs.get("X-Spectra-Nonce"), "deadbeef1234567890abcdef12345678")

    def test_hmi_read_endpoints_block_etc_passwd_and_root_walk(self):
        for path in (
            "/api/hmi/discover?dir=/",
            "/api/hmi/info?path=/etc/passwd",
            "/api/hmi/audit?path=/etc/passwd",
            "/api/hmi/semantic?path=/etc/passwd",
            "/api/hmi/languages?path=/etc/passwd",
            "/api/hmi/phrases?path=/etc/passwd",
        ):
            status, body, _ = self._req(path)
            self.assertEqual(status, 403, f"Expected 403 for {path}, got {status}: {body}")

    def test_debug_log_and_rotating_log_redact_secrets(self):
        web_server.log_debug_event(
            "ERROR",
            "STDERR",
            "Authorization: Bearer ghp_SuperSecretToken1234567890 failed",
            "SPECTRA_GITHUB_TOKEN=github_pat_ABCDEF1234567890",
        )
        status, body, _ = self._req("/api/debug/status")
        self.assertEqual(status, 200)
        raw = body.decode("utf-8")
        self.assertNotIn("ghp_SuperSecretToken1234567890", raw)
        self.assertNotIn("github_pat_ABCDEF1234567890", raw)
        self.assertIn("[REDACTED]", raw)

        with tempfile.TemporaryDirectory() as td:
            log_file = os.path.join(td, "rot.log")
            stream = spectra_app._RotatingLogStream(log_file, max_bytes=64, backup_count=2)
            stream.write("token=ghp_SecretToken999999999 " + ("A" * 80) + "\n")
            stream.write("second write line\n")
            self.assertTrue(os.path.isfile(f"{log_file}.1"))
            content = Path(f"{log_file}.1").read_text(encoding="utf-8")
            self.assertNotIn("ghp_SecretToken999999999", content)
            self.assertIn("[REDACTED]", content)


class TestF07HmiPatcherPreWriteVerification(unittest.TestCase):
    def test_apply_patches_refuses_nonzero_padding_and_cleans_up_output(self):
        with tempfile.TemporaryDirectory() as td:
            dummy_elf = os.path.join(td, "sample.elf")
            out_elf = os.path.join(td, "sample_patched.elf")
            # 128-byte synthetic image where offset 32..48 is NON-ZERO
            with open(dummy_elf, "wb") as f:
                f.write(b"\x7fELF" + b"\xFF" * 124)

            insp = object.__new__(hmi_inspector.KalermHmiInspector)
            insp.binary_path = dummy_elf
            insp.file_size = 128
            insp.container_type = "ELF32_LVGL"
            insp.sections_by_name = {}
            fake_findings = [
                {
                    "patchable": True,
                    "status": "DETECTED",
                    "patch_meta": {
                        "action": "allocate_rodata_and_repoint_phrase",
                        "locale": "cs-CZ",
                        "key": "test_key",
                        "pad_offset": 32,
                        "slot_file_off": 16,
                        "target_vma": 0x10020,
                        "new_string": "Káva",
                    },
                }
            ]
            with mock.patch.object(insp, "run_audit", return_value=fake_findings):
                with self.assertRaises(RuntimeError) as ctx:
                    insp.apply_patches(out_elf)
            self.assertIn("not all-zero", str(ctx.exception))
            self.assertFalse(os.path.exists(out_elf))


class TestF08ReportArchiveHardening(unittest.TestCase):
    def test_permissions_unicode_fts5_nan_cursor_and_masked_blob_path(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "sub", "reports_index.sqlite3")
            row_id = report_archive.archive_report(
                "service_report",
                content="<html>Čištění mléčného systému — káva OK</html>",
                ext="html",
                serial_number="SN-CZ-01",
                summary_text="Pravidelné čištění mléčného systému a káva v normě",
                db_path=db_path,
            )
            self.assertGreater(row_id, 0)

            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(db_path)).st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(os.stat(db_path).st_mode), 0o600)
                blobs_dir = report_archive.get_blobs_dir(db_path)
                self.assertEqual(stat.S_IMODE(os.stat(blobs_dir).st_mode), 0o700)

            # Unicode Czech query MUST match
            cz = report_archive.search_reports(query="káva čištění", db_path=db_path)
            self.assertEqual(cz["count"], 1)
            item = cz["items"][0]
            self.assertTrue(item["has_blob"])
            self.assertNotIn("blob_path", item)

            # NaN / Inf cursors must be safely ignored
            self.assertIsNone(report_archive._parse_cursor("nan:1"))
            self.assertIsNone(report_archive._parse_cursor("inf:1"))
            self.assertIsNone(report_archive._parse_cursor("-inf:1"))
            self.assertIsNone(report_archive._parse_cursor("1700000000.0:-5"))
            nan_res = report_archive.search_reports(cursor="nan:1", db_path=db_path)
            self.assertEqual(nan_res["count"], 1)


class TestF09LinuxUpdaterFailClosedSha256(unittest.TestCase):
    def test_linux_tarball_update_rejects_missing_or_invalid_sha256(self):
        with self.assertRaises(updater.UpdateError):
            updater._apply_linux_tarball_update({
                "latest_build": "20990101.1200",
                "download_url": "https://github.com/Pr0xyA-91/spectra/releases/download/build-20990101.1200/spectra_linux.tar.gz",
                "expected_sha256": "",
            })
        with self.assertRaises(updater.UpdateError):
            updater._apply_linux_tarball_update({
                "latest_build": "20990101.1200",
                "download_url": "https://github.com/Pr0xyA-91/spectra/releases/download/build-20990101.1200/spectra_linux.tar.gz",
                "expected_sha256": "not-a-valid-sha256",
            })


if __name__ == "__main__":
    unittest.main()
