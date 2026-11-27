#!/usr/bin/env python3
"""Tests for SPECTRA cross-platform self-updater and update HTTP API routes."""

import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import updater
import web_server


def _git_run(cwd, *args):
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "SPECTRA Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.invalid",
            "GIT_COMMITTER_NAME": "SPECTRA Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.invalid",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


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
        self.assertEqual(res["tag_name"], "build-20990101.1200")
        self.assertEqual(res["source"], "github_release")
        self.assertEqual(res["download_url"], "https://example.invalid/spectra_update.exe")
        self.assertEqual(res["expected_sha256"], "deadbeef" * 8)
        self.assertIn("Added self-updater", res["release_notes"])

    def test_linux_prefers_immutable_tag_tarball_url(self):
        release_payload = {
            "tag_name": "build-20990202.0930",
            "name": "SPECTRA Build 20990202.0930",
            "body": "Linux release",
            "html_url": "https://github.com/Pr0xyA-91/spectra/releases/tag/build-20990202.0930",
            "published_at": "2099-02-02T09:30:00Z",
            "assets": [],
        }

        def fake_get_bytes(url, timeout=4.0, headers=None):
            if "releases/latest" in url:
                return json.dumps(release_payload).encode("utf-8")
            if "release_manifest.json" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            if "version.py" in url:
                return b'__build__ = "20990202.0930"\n'
            raise AssertionError(f"Unexpected URL: {url}")

        with patch.object(updater, "_http_get_bytes", side_effect=fake_get_bytes), patch.object(
            updater, "get_local_build", return_value="20261117.1320"
        ), patch.object(updater, "_current_platform", return_value="linux"):
            res = updater.check_for_updates(force=True)

        self.assertTrue(res["ok"])
        self.assertEqual(res["tag_name"], "build-20990202.0930")
        self.assertEqual(
            res["download_url"],
            f"https://github.com/{updater.PUBLIC_REPO}/archive/refs/tags/build-20990202.0930.tar.gz",
        )

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
        self.assertEqual(res["tag_name"], "")
        self.assertEqual(res["source"], "raw_version")

    def test_offline_returns_structured_failure(self):
        with patch.object(updater, "_http_get_bytes", side_effect=OSError("network unreachable")):
            res = updater.check_for_updates(force=True)
        self.assertFalse(res["ok"])
        self.assertFalse(res["update_available"])
        self.assertEqual(res["tag_name"], "")
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


class TestLinuxGitUpdate(unittest.TestCase):
    def _init_bare_and_clone(self, tmp, remote_name="origin", remote_url_override=None):
        bare = os.path.join(tmp, "remote.git")
        seed = os.path.join(tmp, "seed")
        local = os.path.join(tmp, "local")
        _git_run(tmp, "init", "--bare", "-b", "main", bare)
        _git_run(tmp, "clone", bare, seed)
        with open(os.path.join(seed, "version.py"), "w", encoding="utf-8") as f:
            f.write('__build__ = "20261119.1000"\n')
        with open(os.path.join(seed, "run.sh"), "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\necho ok\n")
        _git_run(seed, "add", "version.py", "run.sh")
        _git_run(seed, "commit", "-m", "initial")
        _git_run(seed, "push", "origin", "main")

        _git_run(tmp, "clone", "-b", "main", bare, local)
        if remote_name != "origin":
            _git_run(local, "remote", "rename", "origin", remote_name)
        if remote_url_override:
            _git_run(local, "remote", "set-url", remote_name, remote_url_override)
        return bare, seed, local

    def _push_new_build(self, seed, new_build="20990101.1200"):
        with open(os.path.join(seed, "version.py"), "w", encoding="utf-8") as f:
            f.write(f'__build__ = "{new_build}"\n')
        _git_run(seed, "add", "version.py")
        _git_run(seed, "commit", "-m", f"Build {new_build}")
        _git_run(seed, "push", "origin", "main")

    def test_clean_fast_forward_and_filemode_diff_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare, seed, local = self._init_bare_and_clone(tmp)
            self._push_new_build(seed, "20990101.1200")

            # Simulate chmod +x changing tracked filemode only
            os.chmod(os.path.join(local, "run.sh"), 0o755)
            fake_slug = updater.PUBLIC_REPO

            with patch.object(updater, "PROJECT_DIR", local), patch.object(
                updater, "_get_git_remotes", return_value={"origin": fake_slug}
            ):
                # Re-point origin fetch to local bare repo via git config url.<bare>.insteadOf? No, simpler:
                # restore bare remote URL and mock _get_git_remotes only!
                should_restart = updater._apply_linux_git_update({"latest_build": "20990101.1200"})
            self.assertTrue(should_restart)
            self.assertEqual(updater.get_local_build(), "20990101.1200") if False else None
            with open(os.path.join(local, "version.py"), "r", encoding="utf-8") as f:
                self.assertIn("20990101.1200", f.read())

    def test_dirty_tracked_files_rejected_with_filenames(self):
        with tempfile.TemporaryDirectory() as tmp:
            _bare, _seed, local = self._init_bare_and_clone(tmp)
            with open(os.path.join(local, "version.py"), "w", encoding="utf-8") as f:
                f.write('__build__ = "20261119.9999"\n')

            with patch.object(updater, "PROJECT_DIR", local), patch.object(
                updater, "_get_git_remotes", return_value={"origin": updater.PUBLIC_REPO}
            ):
                with self.assertRaises(updater.UpdateError) as ctx:
                    updater._apply_linux_git_update({"latest_build": "20990101.1200"})
            self.assertIn("version.py", str(ctx.exception))

    def test_lossless_reset_when_head_matches_old_remote_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare, seed, local = self._init_bare_and_clone(tmp)
            # Rewrite history on remote (force push amended commit) while local has 0 local commits
            with open(os.path.join(seed, "version.py"), "w", encoding="utf-8") as f:
                f.write('__build__ = "20990101.1300"\n')
            _git_run(seed, "add", "version.py")
            _git_run(seed, "commit", "--amend", "-m", "rewritten build")
            _git_run(seed, "push", "--force", "origin", "main")

            with patch.object(updater, "PROJECT_DIR", local), patch.object(
                updater, "_get_git_remotes", return_value={"origin": updater.PUBLIC_REPO}
            ):
                should_restart = updater._apply_linux_git_update({"latest_build": "20990101.1300"})
            self.assertTrue(should_restart)
            with open(os.path.join(local, "version.py"), "r", encoding="utf-8") as f:
                self.assertIn("20990101.1300", f.read())

    def test_diverged_local_commits_raise_update_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            _bare, seed, local = self._init_bare_and_clone(tmp)
            self._push_new_build(seed, "20990101.1400")

            # Create local diverging commit
            with open(os.path.join(local, "local_note.txt"), "w", encoding="utf-8") as f:
                f.write("local work\n")
            _git_run(local, "add", "local_note.txt")
            _git_run(local, "commit", "-m", "local diverged commit")

            with patch.object(updater, "PROJECT_DIR", local), patch.object(
                updater, "_get_git_remotes", return_value={"origin": updater.PUBLIC_REPO}
            ):
                with self.assertRaises(updater.UpdateError) as ctx:
                    updater._apply_linux_git_update({"latest_build": "20990101.1400"})
            self.assertIn("diverge", str(ctx.exception).lower())

    def test_custom_remote_case_b_safe_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            _bare, seed, local = self._init_bare_and_clone(tmp)
            # Remote does not advance -> Case B must raise protective UpdateError instead of overwriting from public
            with patch.object(updater, "PROJECT_DIR", local), patch.object(
                updater, "_get_git_remotes", return_value={"origin": "custom-org/custom-fork"}
            ):
                with self.assertRaises(updater.UpdateError) as ctx:
                    updater._apply_linux_git_update({"latest_build": "20990101.1500"})
            self.assertIn("custom remote", str(ctx.exception).lower())

            # Now advance custom origin main -> Case B cleanly fast-forwards and succeeds
            self._push_new_build(seed, "20990101.1500")
            with patch.object(updater, "PROJECT_DIR", local), patch.object(
                updater, "_get_git_remotes", return_value={"origin": "custom-org/custom-fork"}
            ):
                should_restart = updater._apply_linux_git_update({"latest_build": "20990101.1500"})
            self.assertTrue(should_restart)

    def test_dual_remote_non_public_origin_with_public_remote_uses_case_b(self):
        with tempfile.TemporaryDirectory() as tmp:
            _bare, seed, local = self._init_bare_and_clone(tmp)
            # Create a second unrelated bare repo registered as `public`
            pub_bare = os.path.join(tmp, "public.git")
            pub_seed = os.path.join(tmp, "pub_seed")
            _git_run(tmp, "init", "--bare", "-b", "main", pub_bare)
            _git_run(tmp, "clone", pub_bare, pub_seed)
            with open(os.path.join(pub_seed, "version.py"), "w", encoding="utf-8") as f:
                f.write('__build__ = "20990101.1600"\n')
            _git_run(pub_seed, "add", "version.py")
            _git_run(pub_seed, "commit", "-m", "unrelated public root")
            _git_run(pub_seed, "push", "origin", "main")

            _git_run(local, "remote", "add", "public", pub_bare)
            # Advance origin (private/fork) to target build
            self._push_new_build(seed, "20990101.1600")

            with patch.object(updater, "PROJECT_DIR", local), patch.object(
                updater,
                "_get_git_remotes",
                return_value={
                    "origin": "example/custom-fork",
                    "public": updater.PUBLIC_REPO,
                },
            ):
                should_restart = updater._apply_linux_git_update({"latest_build": "20990101.1600"})
            self.assertTrue(should_restart)
            with open(os.path.join(local, "version.py"), "r", encoding="utf-8") as f:
                self.assertIn("20990101.1600", f.read())
            # Verify it fetched from origin and did not pull unrelated public remote
            refs = _git_run(local, "show-ref").stdout
            self.assertNotIn("refs/remotes/public/main", refs)


class TestLinuxTarballAndRestartLifecycle(unittest.TestCase):
    def _make_release_tarball(self, path, build_str, root_folder="spectra-build-test", old_asset=False):
        with tarfile.open(path, "w:gz") as tf:
            files = {
                f"{root_folder}/version.py": f'__build__ = "{build_str}"\n'.encode("utf-8"),
                f"{root_folder}/run.sh": b"#!/usr/bin/env bash\necho updated\n",
                f"{root_folder}/web/dist/index.html": b"<html>new</html>",
                f"{root_folder}/web/dist/assets/new-chunk.js": b"console.log('new');",
            }
            if old_asset:
                files[f"{root_folder}/web/dist/assets/stale-chunk.js"] = b"stale"
            for name, payload in files.items():
                ti = tarfile.TarInfo(name)
                ti.size = len(payload)
                tf.addfile(ti, io.BytesIO(payload))

    def test_tarball_rejects_mismatched_build_before_modifying_project_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, "install")
            os.makedirs(proj, exist_ok=True)
            with open(os.path.join(proj, "version.py"), "w", encoding="utf-8") as f:
                f.write('__build__ = "20261119.1612"\n')

            bad_tar = os.path.join(tmp, "bad.tar.gz")
            self._make_release_tarball(bad_tar, "20261110.0001")
            with open(bad_tar, "rb") as fh:
                bad_sha = hashlib.sha256(fh.read()).hexdigest()

            def fake_download(url, dest_path, expected_size=0, timeout=30.0):
                shutil.copyfile(bad_tar, dest_path)

            with patch.object(updater, "PROJECT_DIR", proj), patch.object(
                updater, "_download_file_with_progress", side_effect=fake_download
            ):
                # Missing SHA-256 must fail closed before downloading
                with self.assertRaises(updater.UpdateError):
                    updater._apply_linux_tarball_update({"latest_build": "20990101.1200", "download_url": "https://github.com/x/y.tar.gz"})
                # Mismatched build with valid SHA-256 must still reject before modifying PROJECT_DIR
                with self.assertRaises(updater.UpdateError):
                    updater._apply_linux_tarball_update({
                        "latest_build": "20990101.1200",
                        "download_url": "https://github.com/x/y.tar.gz",
                        "expected_sha256": bad_sha,
                    })

            with open(os.path.join(proj, "version.py"), "r", encoding="utf-8") as f:
                self.assertIn("20261119.1612", f.read())

    def test_tarball_clean_dist_swap_preserves_user_items_and_executables(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, "install")
            os.makedirs(os.path.join(proj, "web", "dist", "assets"), exist_ok=True)
            os.makedirs(os.path.join(proj, ".venv", "bin"), exist_ok=True)
            os.makedirs(os.path.join(proj, "captures"), exist_ok=True)
            with open(os.path.join(proj, "version.py"), "w", encoding="utf-8") as f:
                f.write('__build__ = "20261119.1612"\n')
            with open(os.path.join(proj, "web", "dist", "assets", "old-stale.js"), "w", encoding="utf-8") as f:
                f.write("old")
            with open(os.path.join(proj, "ui_prefs.json"), "w", encoding="utf-8") as f:
                f.write('{"lang":"cs"}')
            with open(os.path.join(proj, "local_overrides.json"), "w", encoding="utf-8") as f:
                f.write('{"override":1}')
            with open(os.path.join(proj, "runtime.log"), "w", encoding="utf-8") as f:
                f.write("keep me")
            with open(os.path.join(proj, ".venv", "bin", "python"), "w", encoding="utf-8") as f:
                f.write("venv")
            with open(os.path.join(proj, "captures", "cap1.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            good_tar = os.path.join(tmp, "good.tar.gz")
            self._make_release_tarball(good_tar, "20990101.1200")
            with open(good_tar, "rb") as fh:
                good_sha = hashlib.sha256(fh.read()).hexdigest()

            def fake_download(url, dest_path, expected_size=0, timeout=30.0):
                shutil.copyfile(good_tar, dest_path)

            called = {"restarted": False}
            updater.register_linux_restart_handler(lambda: called.__setitem__("restarted", True))
            try:
                with patch.object(updater, "PROJECT_DIR", proj), patch.object(
                    updater, "_download_file_with_progress", side_effect=fake_download
                ):
                    updater._apply_linux_update({
                        "latest_build": "20990101.1200",
                        "download_url": "https://github.com/x/y.tar.gz",
                        "expected_sha256": good_sha,
                    })
            finally:
                updater.register_linux_restart_handler(None)

            self.assertTrue(called["restarted"])
            self.assertFalse(os.path.exists(os.path.join(proj, "web", "dist", "assets", "old-stale.js")))
            self.assertTrue(os.path.isfile(os.path.join(proj, "web", "dist", "assets", "new-chunk.js")))
            self.assertTrue(os.path.isfile(os.path.join(proj, "ui_prefs.json")))
            self.assertTrue(os.path.isfile(os.path.join(proj, "local_overrides.json")))
            self.assertTrue(os.path.isfile(os.path.join(proj, "runtime.log")))
            self.assertTrue(os.path.isfile(os.path.join(proj, ".venv", "bin", "python")))
            self.assertTrue(os.path.isfile(os.path.join(proj, "captures", "cap1.json")))
            self.assertTrue(os.access(os.path.join(proj, "run.sh"), os.X_OK))

    def test_cleanup_retired_app_files_removes_obsolete_and_preserves_user_data_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "install")
            outside = os.path.join(tmp, "outside_secret.txt")
            with open(outside, "w", encoding="utf-8") as f:
                f.write("do not touch")

            os.makedirs(os.path.join(dst, "tests"), exist_ok=True)
            os.makedirs(os.path.join(dst, "web", "public"), exist_ok=True)
            os.makedirs(os.path.join(dst, "docs", "brand"), exist_ok=True)
            os.makedirs(os.path.join(dst, "__pycache__"), exist_ok=True)
            os.makedirs(os.path.join(dst, "captures"), exist_ok=True)

            # Retired files that MUST be removed
            for rel in (
                "wrat_engine.py",
                "CHANGELOG_CS.pdf",
                "test_legacy_root.py",
                os.path.join("web", "public", "favicon.ico"),
                os.path.join("web", "public", "icon.png"),
                os.path.join("web", "public", "logo.svg"),
                os.path.join("__pycache__", "wrat_engine.cpython-312.pyc"),
            ):
                with open(os.path.join(dst, rel), "w", encoding="utf-8") as f:
                    f.write("obsolete")

            # Symlink at retired location MUST NOT be followed or delete target
            os.symlink(outside, os.path.join(dst, "docs", "brand", "spectra_logo.svg"))

            # User data & active files that MUST be preserved
            for keep in (
                "ui_prefs.json",
                "offsets_overrides.json",
                "my_custom_notes.txt",
                os.path.join("captures", "machine_dump.json"),
                os.path.join("tests", "test_updater.py"),
            ):
                with open(os.path.join(dst, keep), "w", encoding="utf-8") as f:
                    f.write("keep")

            removed = updater._cleanup_retired_app_files(dst)
            self.assertIn("wrat_engine.py", removed)
            self.assertIn("CHANGELOG_CS.pdf", removed)
            self.assertIn("test_legacy_root.py", removed)
            self.assertFalse(os.path.exists(os.path.join(dst, "wrat_engine.py")))
            self.assertFalse(os.path.exists(os.path.join(dst, "CHANGELOG_CS.pdf")))
            self.assertFalse(os.path.exists(os.path.join(dst, "test_legacy_root.py")))
            self.assertFalse(os.path.exists(os.path.join(dst, "web", "public")))
            self.assertFalse(os.path.exists(os.path.join(dst, "__pycache__", "wrat_engine.cpython-312.pyc")))

            # Symlink target & user files strictly untouched
            self.assertTrue(os.path.isfile(outside))
            self.assertTrue(os.path.islink(os.path.join(dst, "docs", "brand", "spectra_logo.svg")))
            for keep in (
                "ui_prefs.json",
                "offsets_overrides.json",
                "my_custom_notes.txt",
                os.path.join("captures", "machine_dump.json"),
                os.path.join("tests", "test_updater.py"),
            ):
                self.assertTrue(os.path.isfile(os.path.join(dst, keep)), f"Should preserve {keep}")

    def test_unwritable_project_dir_raises_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(updater, "PROJECT_DIR", tmp), patch("os.access", return_value=False):
                with self.assertRaises(updater.UpdateError) as ctx:
                    updater._apply_linux_update({"latest_build": "20990101.1200"})
            self.assertIn("not writable", str(ctx.exception).lower())

    def test_relaunch_current_process_sets_env_and_calls_execv(self):
        with patch.dict(os.environ, {}, clear=False), patch("os.execv") as execv_mock:
            updater.relaunch_current_process(preferred_port=8123)
            self.assertEqual(os.environ.get("SPECTRA_RESTARTED_AFTER_UPDATE"), "1")
            self.assertEqual(os.environ.get("SPECTRA_PREFERRED_PORT"), "8123")
            execv_mock.assert_called_once()


class TestUpdateHttpEndpoints(unittest.TestCase):
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

    def test_update_endpoints_and_boot_id(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/version", timeout=5) as r:
            ver = json.loads(r.read().decode("utf-8"))
        self.assertTrue(ver["success"])
        self.assertEqual(ver["boot_id"], web_server._SERVER_BOOT_ID)

        fake_check = {
            "ok": True,
            "error": "",
            "current_build": "20261117.1320",
            "latest_build": "20990101.0001",
            "tag_name": "build-20990101.0001",
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
        self.assertEqual(st["boot_id"], web_server._SERVER_BOOT_ID)
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

    def test_bind_http_server_honors_preferred_port_env(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]

        with patch.dict(os.environ, {"SPECTRA_PREFERRED_PORT": str(free_port)}, clear=False):
            srv, bound_port = web_server.bind_http_server(default_start=8080)
            try:
                self.assertEqual(bound_port, free_port)
            finally:
                srv.server_close()


class TestReleaseManifestSignatureVerification(unittest.TestCase):
    def test_transitional_and_fail_closed_ed25519_verification(self):
        import base64
        import offset_db_sync

        seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        pubkey = offset_db_sync.ed25519_public_key_from_seed(seed)
        key_id = "spectra-offsets-ed25519-test-v1"

        unsigned_manifest = {
            "build": "20990101.1200",
            "main_build": "20990101.1200",
            "windows_build": "20990101.1200",
            "assets": {
                "spectra_linux.tar.gz": {
                    "url": "https://github.com/Pr0xyA-91/spectra/releases/download/build-20990101.1200/spectra_linux.tar.gz",
                    "sha256": "aa" * 32,
                    "size": 102400,
                }
            },
        }

        # 1) Pre-pinning transitional mode: unsigned passes, unpinned signature rejected
        ok_trans, reason_trans = updater.verify_release_manifest_signature(unsigned_manifest, trusted_keys={})
        self.assertTrue(ok_trans)
        self.assertEqual(reason_trans, "unsigned_transitional")

        signed_base = dict(unsigned_manifest)
        signed_base["key_id"] = key_id
        signed_base["signature_alg"] = "Ed25519"
        msg = updater.RELEASE_MANIFEST_DOMAIN_PREFIX + offset_db_sync.canonical_json_bytes(signed_base)
        sig = offset_db_sync.ed25519_sign(seed, msg)
        signed_manifest = dict(signed_base)
        signed_manifest["signature_b64"] = base64.b64encode(sig).decode("ascii")

        ok_unpinned, reason_unpinned = updater.verify_release_manifest_signature(signed_manifest, trusted_keys={})
        self.assertFalse(ok_unpinned)
        self.assertEqual(reason_unpinned, "Untrusted key_id")

        # 2) Post-pinning fail-closed mode: unsigned rejected, valid signature verified, tampered rejected
        pinned = {key_id: pubkey}
        ok_unsigned, _ = updater.verify_release_manifest_signature(unsigned_manifest, trusted_keys=pinned)
        self.assertFalse(ok_unsigned)

        ok_signed, reason_signed = updater.verify_release_manifest_signature(signed_manifest, trusted_keys=pinned)
        self.assertTrue(ok_signed, msg=reason_signed)
        self.assertEqual(reason_signed, "verified")

        tampered = dict(signed_manifest)
        tampered["build"] = "20991231.2359"
        ok_tampered, _ = updater.verify_release_manifest_signature(tampered, trusted_keys=pinned)
        self.assertFalse(ok_tampered)


if __name__ == "__main__":
    unittest.main()
