#!/usr/bin/env python3
"""Tests for SPECTRA cross-platform self-updater and update HTTP API routes."""

import hashlib
import io
import json
import os
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import updater
import web_server


class TestBuildVersionComparison(unittest.TestCase):
    def test_parse_and_compare_builds(self):
        self.assertEqual(updater.parse_build_tuple("20261117.1320"), (20261117, 1320))
        self.assertEqual(updater.parse_build_tuple("Build 20261117.1405"), (20261117, 1405))
        self.assertEqual(updater.parse_build_tuple("build-20261118.0900"), (20261118, 900))
        self.assertEqual(updater.parse_build_tuple(""), ())

        self.assertTrue(updater.is_remote_build_newer("20261117.1320", "20261117.1400"))
        self.assertTrue(updater.is_remote_build_newer("20261117.1320", "20261118.0001"))
        self.assertFalse(updater.is_remote_build_newer("20261117.1320", "20261117.1320"))
        self.assertFalse(updater.is_remote_build_newer("20261117.1320", "20261116.2359"))
        self.assertFalse(updater.is_remote_build_newer("20261117.1320", ""))

    def test_extract_build_from_version_py(self):
        sample = '__version__ = "0.7.0"\n__build__ = "20261117.1455"\n'
        self.assertEqual(updater.extract_build_from_text(sample), "20261117.1455")


class TestCheckForUpdates(unittest.TestCase):
    def setUp(self):
        updater._cached_check = None
        updater._cached_check_ts = 0.0

    def test_github_release_and_manifest_parsing(self):
        release_payload = {
            "tag_name": "build-20990101.1200",
            "name": "SPECTRA Build 20990101.1200",
            "body": "- Added self-updater\n- Fixed bug",
            "html_url": "https://github.com/Pr0xyA-91/spectra/releases/tag/build-20990101.1200",
            "published_at": "2099-01-01T12:00:00Z",
            "assets": [
                {
                    "name": "spectra_update.exe",
                    "browser_download_url": "https://example.invalid/spectra_update.exe",
                    "size": 1234567,
                },
                {
                    "name": "release_manifest.json",
                    "browser_download_url": "https://example.invalid/release_manifest.json",
                    "size": 512,
                },
            ],
        }
        manifest_payload = {
            "build": "20990101.1200",
            "main_build": "20990101.1200",
            "windows_build": "20990101.1200",
            "assets": {
                "spectra_update.exe": {
                    "url": "https://example.invalid/spectra_update.exe",
                    "sha256": "deadbeef" * 8,
                    "size": 1234567,
                }
            },
        }

        def fake_get_bytes(url, timeout=4.0, headers=None):
            if "releases/latest" in url:
                return json.dumps(release_payload).encode("utf-8")
            if "release_manifest.json" in url:
                return json.dumps(manifest_payload).encode("utf-8")
            if "version.py" in url:
                return b'__build__ = "20990101.1200"\n'
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(updater, "_http_get_bytes", side_effect=fake_get_bytes), patch.object(
            updater, "get_local_build", return_value="20261117.1320"
        ), patch.object(updater, "_current_platform", return_value="windows"):
            res = updater.check_for_updates(force=True)

        self.assertTrue(res["ok"])
        self.assertTrue(res["update_available"])
        self.assertEqual(res["latest_build"], "20990101.1200")
        self.assertEqual(res["source"], "github_release")
        self.assertEqual(res["download_url"], "https://example.invalid/spectra_update.exe")
        self.assertEqual(res["expected_sha256"], "deadbeef" * 8)
        self.assertIn("Added self-updater", res["release_notes"])

    def test_raw_version_fallback_when_release_404(self):
        def fake_get_bytes(url, timeout=4.0, headers=None):
            if "releases/latest" in url or "release_manifest.json" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            if "version.py" in url:
                return b'__build__ = "20990102.0830"\n'
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(updater, "_http_get_bytes", side_effect=fake_get_bytes), patch.object(
            updater, "get_local_build", return_value="20261117.1320"
        ), patch.object(updater, "_current_platform", return_value="linux"):
            res = updater.check_for_updates(force=True)

        self.assertTrue(res["ok"])
        self.assertTrue(res["update_available"])
        self.assertEqual(res["latest_build"], "20990102.0830")
        self.assertEqual(res["source"], "raw_version")

    def test_offline_returns_structured_failure(self):
        with patch.object(updater, "_http_get_bytes", side_effect=OSError("network unreachable")):
            res = updater.check_for_updates(force=True)
        self.assertFalse(res["ok"])
        self.assertFalse(res["update_available"])
        self.assertTrue(bool(res["error"]))


class TestBinaryAndTarballSafety(unittest.TestCase):
    def test_verify_windows_updater_binary_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_html = os.path.join(tmp, "bad.exe")
            with open(bad_html, "wb") as f:
                f.write(b"<html>404</html>" * 100)
            with self.assertRaises(updater.UpdateError):
                updater.verify_windows_updater_binary(bad_html, min_bytes=64)

            tiny_mz = os.path.join(tmp, "tiny.exe")
            with open(tiny_mz, "wb") as f:
                f.write(b"MZ" + b"\x00" * 30)
            with self.assertRaises(updater.UpdateError):
                updater.verify_windows_updater_binary(tiny_mz, min_bytes=1024)

            good_exe = os.path.join(tmp, "good.exe")
            payload = b"MZ" + b"\x90" * 2046
            with open(good_exe, "wb") as f:
                f.write(payload)
            expected_sha = hashlib.sha256(payload).hexdigest()

            actual_sha = updater.verify_windows_updater_binary(
                good_exe, expected_sha256=expected_sha.upper(), min_bytes=1024
            )
            self.assertEqual(actual_sha, expected_sha)

            with self.assertRaises(updater.UpdateError):
                updater.verify_windows_updater_binary(good_exe, expected_sha256="0" * 64, min_bytes=1024)

    def test_safe_extract_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = os.path.join(tmp, "evil.tar.gz")
            dest_dir = os.path.join(tmp, "out")
            os.makedirs(dest_dir, exist_ok=True)
            with tarfile.open(tar_path, "w:gz") as tf:
                ti = tarfile.TarInfo("spectra-main/../../outside.txt")
                data = b"pwn"
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))

            with self.assertRaises(updater.UpdateError):
                updater._safe_extract_tarball(tar_path, dest_dir)


class TestUpdateHttpEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpectraApiHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_update_endpoints(self):
        fake_check = {
            "ok": True,
            "error": "",
            "current_build": "20261117.1320",
            "latest_build": "20990101.0001",
            "update_available": True,
            "platform": "linux",
            "install_mode": "linux_git",
            "release_name": "Build 20990101.0001",
            "release_url": "https://github.com/Pr0xyA-91/spectra/releases",
            "release_notes": "Test note",
            "published_at": "",
            "download_url": "",
            "expected_sha256": "",
            "expected_size": 0,
            "checked_at": 0.0,
            "source": "github_release",
        }
        with patch.object(updater, "check_for_updates", return_value=fake_check):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/update/check?force=1", timeout=5) as r:
                chk = json.loads(r.read().decode("utf-8"))
        self.assertTrue(chk["success"])
        self.assertTrue(chk["update_available"])
        self.assertEqual(chk["latest_build"], "20990101.0001")

        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/update/status", timeout=5) as r:
            st = json.loads(r.read().decode("utf-8"))
        self.assertTrue(st["success"])
        self.assertIn("status", st)
        self.assertIn("percent", st)

        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/update/cancel",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            canc = json.loads(r.read().decode("utf-8"))
        self.assertFalse(canc["success"])


if __name__ == "__main__":
    unittest.main()
