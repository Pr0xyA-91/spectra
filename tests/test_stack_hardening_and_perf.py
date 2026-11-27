#!/usr/bin/env python3
"""
Regression tests for stack-wide security hardening and performance optimizations:
- SEC-01: POSIX flock SerialPortLockedError never falls through to pyserial
- SEC-05: Cross-port localhost Origin rejected, empty Host rejected, Sec-Fetch-Site: cross-site POST rejected
- SEC-06: gui_web compatibility shim & single-file HMI path approval
- SEC-07: Signed release_manifest.json Ed25519 verification & redirect host blocking
- OPT-02: Cached SpectraSession reuse across 1 Hz multi-vendor polls
"""

import base64
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import gui_web
import offset_db_sync as ods
import serial_io
import stats_collector as sc
import updater
import web_server
from spectra_web import security as sec_mod
from spectra_web import state as _wstate


class TestSec01SerialFlockBypass(unittest.TestCase):
    def test_serial_port_locked_error_never_falls_through_to_pyserial(self):
        if not serial_io.HAS_TERMIOS:
            self.skipTest("POSIX termios/fcntl unavailable on this platform")

        with tempfile.NamedTemporaryFile() as tf:
            conn = serial_io.JuraSerialConnection.__new__(serial_io.JuraSerialConnection)
            conn.port_name = tf.name
            conn.raw_port_label = tf.name
            conn.baudrate = 9600
            conn.timeout = 0.5
            conn.fd = None
            conn.py_serial = None
            conn.is_open = False
            conn.is_demo = False

            fake_serial_cls = mock.MagicMock()
            fake_serial_mod = mock.MagicMock(
                Serial=fake_serial_cls,
                EIGHTBITS=8,
                PARITY_NONE="N",
                STOPBITS_ONE=1,
            )
            with mock.patch("serial_io.os.open", return_value=os.dup(tf.fileno())), \
                 mock.patch("serial_io.fcntl.flock", side_effect=BlockingIOError("locked")), \
                 mock.patch("serial_io.time.sleep", return_value=None), \
                 mock.patch("serial_io.time.time", side_effect=[0.0, 0.0, 2.0]), \
                 mock.patch("serial_io.HAS_PYSERIAL", True), \
                 mock.patch.object(serial_io, "serial", fake_serial_mod, create=True):
                with self.assertRaises(serial_io.SerialPortLockedError):
                    conn._open_hardware_port()

            fake_serial_cls.assert_not_called()
            self.assertIsNone(conn.fd)


class TestSec05HttpHostOriginAndSecFetchSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        cls.port = cls.srv.server_address[1]
        cls._prev_port = _wstate._current_http_port
        _wstate._current_http_port = cls.port
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        _wstate._current_http_port = cls._prev_port
        cls.srv.shutdown()
        cls.srv.server_close()

    def _raw_http(self, raw_req: bytes) -> str:
        with socket.create_connection(("127.0.0.1", self.port), timeout=5.0) as sock:
            sock.sendall(raw_req)
            chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
            return b"".join(chunks).decode("utf-8", errors="replace")

    def test_empty_host_rejected_with_403(self):
        resp = self._raw_http(b"GET /api/version HTTP/1.1\r\nConnection: close\r\n\r\n")
        self.assertIn("403", resp.splitlines()[0])

        resp2 = self._raw_http(b"GET /api/version HTTP/1.1\r\nHost:\r\nConnection: close\r\n\r\n")
        self.assertIn("403", resp2.splitlines()[0])

    def test_cross_port_localhost_origin_rejected_unless_dev_cors(self):
        other_port = self.port + 1 if self.port < 65000 else self.port - 1
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/ui_prefs",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{other_port}",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)

    def test_sec_fetch_site_cross_site_post_without_origin_rejected(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/ui_prefs",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Sec-Fetch-Site": "cross-site",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)

    def test_gateway_port_origin_allowed_for_native_shell_proxy(self):
        gw_port = self.port + 2 if self.port < 65000 else self.port - 2
        other_port = self.port + 3 if self.port < 65000 else self.port - 3
        with mock.patch.dict(os.environ, {"SPECTRA_GATEWAY_PORT": str(gw_port)}):
            req_ok = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/ui_prefs",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{gw_port}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_ok, timeout=5) as resp:
                self.assertEqual(resp.status, 200)

            req_bad = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/ui_prefs",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{other_port}",
                },
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_bad, timeout=5)
            self.assertEqual(ctx.exception.code, 403)

    def test_debug_diagnostics_reports_live_ollama_fields(self):
        import hmi_inspector

        fake_proc = mock.MagicMock()
        fake_proc.pid = 43210
        fake_proc.poll.return_value = None
        fake_sys = {
            "ollama": {
                "available": True,
                "models": [{"name": "qwen2.5:1.5b"}],
                "loaded_models": ["qwen2.5:1.5b"],
            },
            "is_managed_process": True,
        }
        sec_mod.invalidate_debug_ai_cache()
        try:
            with mock.patch.object(hmi_inspector.KalermHmiInspector, "get_ai_system_status", return_value=fake_sys), \
                 mock.patch.object(hmi_inspector.KalermHmiInspector, "_ollama_process", fake_proc):
                diag = sec_mod.get_debug_diagnostics()
            self.assertTrue(diag["ollama"]["running"])
            self.assertTrue(diag["ollama"]["managed_by_spectra"])
            self.assertEqual(diag["ollama"]["pid"], 43210)
            self.assertEqual(diag["ollama"]["loaded_models"], ["qwen2.5:1.5b"])
            self.assertEqual(diag["ollama"]["active_model"], "qwen2.5:1.5b")
        finally:
            sec_mod.invalidate_debug_ai_cache()


class TestSec06GuiWebShimAndHmiApproval(unittest.TestCase):
    def test_gui_web_shim_exports_hardened_handler(self):
        self.assertIs(gui_web.SpectraApiHandler, web_server.SpectraApiHandler)
        self.assertIs(gui_web.SpectraWebHandler, web_server.SpectraApiHandler)
        self.assertIs(gui_web.WRATWebHandler, web_server.SpectraApiHandler)
        self.assertIs(gui_web.is_valid_port, web_server.is_valid_port)

    def test_approve_hmi_path_approves_only_selected_file_and_caps_64(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "selected.elf")
            f2 = os.path.join(td, "sibling_secret.elf")
            with open(f1, "wb") as fh:
                fh.write(b"\x7fELF")
            with open(f2, "wb") as fh:
                fh.write(b"\x7fELF")

            with _wstate._hmi_paths_lock:
                orig = set(_wstate._approved_hmi_paths)
                _wstate._approved_hmi_paths.clear()
            try:
                sec_mod._approve_hmi_path(f1)
                ok1, _ = sec_mod._is_allowed_hmi_path(f1)
                ok2, _ = sec_mod._is_allowed_hmi_path(f2)
                self.assertTrue(ok1)
                self.assertFalse(ok2, "Parent directory must NOT be approved for single-file selection")

                for i in range(80):
                    sec_mod._approve_hmi_path(os.path.join(td, f"extra_{i}.elf"))
                with _wstate._hmi_paths_lock:
                    self.assertLessEqual(len(_wstate._approved_hmi_paths), 64)
            finally:
                with _wstate._hmi_paths_lock:
                    _wstate._approved_hmi_paths.clear()
                    _wstate._approved_hmi_paths.update(orig)


class TestSec07ReleaseManifestSigningAndRedirectBlocking(unittest.TestCase):
    def test_verify_release_manifest_signature(self):
        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        pub = ods.ed25519_public_key_from_seed(seed)
        kid = "spectra-rel-v1"
        trusted = {kid: pub}

        unsigned_manifest = {
            "build": "20990101.1200",
            "main_build": "20990101.1200",
            "assets": {},
        }
        # Transitional mode when no trusted keys configured
        ok_t, msg_t = updater.verify_release_manifest_signature(unsigned_manifest, trusted_keys={})
        self.assertTrue(ok_t)
        self.assertEqual(msg_t, "unsigned_transitional")

        # When trusted keys exist, unsigned manifest MUST fail closed
        ok_req, _ = updater.verify_release_manifest_signature(unsigned_manifest, trusted_keys=trusted)
        self.assertFalse(ok_req)

        # Signed manifest succeeds
        signed_payload = dict(unsigned_manifest, key_id=kid)
        sig = ods.ed25519_sign(seed, updater.RELEASE_MANIFEST_DOMAIN_PREFIX + ods.canonical_json_bytes(signed_payload))
        signed_payload["signature_b64"] = base64.b64encode(sig).decode("ascii")
        ok_sig, msg_sig = updater.verify_release_manifest_signature(signed_payload, trusted_keys=trusted)
        self.assertTrue(ok_sig, msg_sig)

        # Tampered signed manifest fails
        tampered = dict(signed_payload, build="20990101.1201")
        ok_bad, _ = updater.verify_release_manifest_signature(tampered, trusted_keys=trusted)
        self.assertFalse(ok_bad)

        # Signed manifest without trusted keys fails closed
        ok_untrusted, _ = updater.verify_release_manifest_signature(signed_payload, trusted_keys={})
        self.assertFalse(ok_untrusted)

    def test_offset_db_redirect_handler_blocks_untrusted_redirect(self):
        handler = ods._SafeRedirectHandler("https://raw.githubusercontent.com/Pr0xyA-91/spectra/main/offsets_db/manifest.json")
        req = urllib.request.Request("https://raw.githubusercontent.com/Pr0xyA-91/spectra/main/offsets_db/manifest.json")
        with self.assertRaises(ValueError):
            handler.redirect_request(req, None, 302, "Found", {}, "https://evil.example/evil.json")
        with self.assertRaises(ValueError):
            handler.redirect_request(req, None, 302, "Found", {}, "http://raw.githubusercontent.com/evil.json")


class TestOpt02CachedSpectraSession(unittest.TestCase):
    def test_query_live_sensors_caches_spectra_session_on_conn(self):
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Nivona NICR768)")
        try:
            with mock.patch("spectra_engine.SpectraSession.initialize_driver", autospec=True, side_effect=lambda s: setattr(s, "driver", mock.MagicMock(read_live_sensors=mock.MagicMock(return_value={"switches": [], "sensors": [], "telemetry": {}})))) as init_mock:
                sc.query_live_sensors(
                    port_name="DEMO / SIMULATION (Nivona NICR768)",
                    conn=conn,
                    fast_poll=True,
                    manufacturer="nivona",
                )
                sc.query_live_sensors(
                    port_name="DEMO / SIMULATION (Nivona NICR768)",
                    conn=conn,
                    fast_poll=True,
                    manufacturer="nivona",
                )
                self.assertEqual(init_mock.call_count, 1)
                self.assertIsNotNone(getattr(conn, "_cached_spectra_session", None))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
