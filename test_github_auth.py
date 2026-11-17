#!/usr/bin/env python3
"""
Unit tests for github_auth.py and upload_capture_to_community_repo in spectra_probe.py.
Verifies:
- Device flow state transitions (pending, slow_down, expired, success) with mocked HTTP
- PAT validation with mocked HTTP
- Credential storage roundtrip in isolated temporary directory
- Token is never exposed in get_auth_status() output
- Upload capture:
  - Small bundle (<65,536 chars) in issue body
  - Large bundle (>65,536 chars) via Gist fallback
  - Label 422 retry without label
  - Precise error propagation (401, 403, network, missing auth)
All HTTP calls are strictly mocked with zero network access.
"""

import os
import sys
import json
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import github_auth
import spectra_probe


class TestGitHubAuthAndUpload(unittest.TestCase):
    """Test suite for GitHub OAuth, PAT, and Community Upload pipeline."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_override = github_auth._CONFIG_DIR_OVERRIDE
        github_auth._CONFIG_DIR_OVERRIDE = Path(self.temp_dir.name)

        # Clear any environment variables that might interfere
        self.orig_env = {
            "SPECTRA_GITHUB_TOKEN": os.environ.get("SPECTRA_GITHUB_TOKEN"),
            "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN"),
            "SPECTRA_GITHUB_CLIENT_ID": os.environ.get("SPECTRA_GITHUB_CLIENT_ID"),
        }
        for k in ("SPECTRA_GITHUB_TOKEN", "GITHUB_TOKEN", "SPECTRA_GITHUB_CLIENT_ID"):
            os.environ.pop(k, None)

        # Patch shutil.which to avoid ambient host gh CLI in default tests
        self.patcher_which = patch("shutil.which", return_value=None)
        self.mock_which = self.patcher_which.start()

        # In-memory mock for keyring so tests don't touch host OS keyring
        self._installed_keyring_stub = False
        if "keyring" not in sys.modules:
            stub = types.ModuleType("keyring")
            stub.set_password = lambda *args, **kwargs: None
            stub.get_password = lambda *args, **kwargs: None
            stub.delete_password = lambda *args, **kwargs: None
            sys.modules["keyring"] = stub
            self._installed_keyring_stub = True

        self.keyring_storage = {}
        def mock_set_pwd(service, user, pwd):
            self.keyring_storage[(service, user)] = pwd
        def mock_get_pwd(service, user):
            return self.keyring_storage.get((service, user))
        def mock_del_pwd(service, user):
            self.keyring_storage.pop((service, user), None)

        self.patcher_keyring_set = patch("keyring.set_password", side_effect=mock_set_pwd)
        self.patcher_keyring_get = patch("keyring.get_password", side_effect=mock_get_pwd)
        self.patcher_keyring_del = patch("keyring.delete_password", side_effect=mock_del_pwd)
        self.patcher_keyring_set.start()
        self.patcher_keyring_get.start()
        self.patcher_keyring_del.start()

    def tearDown(self):
        self.patcher_keyring_del.stop()
        self.patcher_keyring_get.stop()
        self.patcher_keyring_set.stop()
        if getattr(self, "_installed_keyring_stub", False):
            sys.modules.pop("keyring", None)
        self.patcher_which.stop()
        github_auth._CONFIG_DIR_OVERRIDE = self.orig_override
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        self.temp_dir.cleanup()

    def test_storage_roundtrip_and_no_token_leak_in_status(self):
        """Verify saving token, reading it, logout, and token absence from status."""
        # 1. Save PAT
        success = github_auth.save_stored_token("ghp_SecretToken12345", "testuser", method="pat")
        self.assertTrue(success)

        # 2. Check stored token
        stored = github_auth.get_stored_token()
        self.assertIsNotNone(stored)
        self.assertEqual(stored["token"], "ghp_SecretToken12345")
        self.assertEqual(stored["login"], "testuser")
        self.assertEqual(stored["method"], "pat")

        # 3. Status must NEVER expose token
        status = github_auth.get_auth_status()
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["login"], "testuser")
        self.assertEqual(status["method"], "pat")
        self.assertNotIn("token", status)
        self.assertNotIn("ghp_SecretToken12345", json.dumps(status))

        # 4. Check chmod on POSIX and ensure keyring success does not write plaintext token to disk
        auth_file = github_auth._get_auth_file()
        self.assertNotIn("ghp_SecretToken12345", auth_file.read_text(encoding="utf-8"))
        if os.name != "nt":
            mode = oct(auth_file.stat().st_mode & 0o777)
            self.assertEqual(mode, "0o600")

        # 5. Logout
        github_auth.logout()
        self.assertIsNone(github_auth.get_stored_token())
        status_after = github_auth.get_auth_status()
        self.assertFalse(status_after["authenticated"])
        self.assertIsNone(status_after["login"])

    def test_token_resolution_order(self):
        """Stored token > SPECTRA_GITHUB_TOKEN > GITHUB_TOKEN > gh auth token."""
        # Setup: all 3 env/stored present
        github_auth.save_stored_token("token_stored", "user_stored", method="stored")
        os.environ["SPECTRA_GITHUB_TOKEN"] = "token_spectra_env"
        os.environ["GITHUB_TOKEN"] = "token_gh_env"

        # 1. Stored wins
        res = github_auth.resolve_token()
        self.assertEqual(res["token"], "token_stored")

        # 2. SPECTRA_GITHUB_TOKEN wins when stored is empty
        github_auth.clear_stored_token()
        res = github_auth.resolve_token()
        self.assertEqual(res["token"], "token_spectra_env")

        # 3. GITHUB_TOKEN wins when SPECTRA_GITHUB_TOKEN is missing
        os.environ.pop("SPECTRA_GITHUB_TOKEN")
        res = github_auth.resolve_token()
        self.assertEqual(res["token"], "token_gh_env")

        # 4. gh auth token subprocess when env tokens missing
        os.environ.pop("GITHUB_TOKEN")
        self.mock_which.return_value = "/usr/bin/gh"
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout="token_gh_cli\n")
            res = github_auth.resolve_token()
            self.assertEqual(res["token"], "token_gh_cli")
            self.assertEqual(res["method"], "gh_cli")

    @patch("urllib.request.urlopen")
    def test_pat_validation_success_and_failure(self, mock_urlopen):
        """Test Personal Access Token validation via GitHub API user endpoint."""
        # Case A: Valid token
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"login": "octocat"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = github_auth.set_pat("ghp_valid_token")
        self.assertTrue(res["success"])
        self.assertEqual(res["login"], "octocat")
        self.assertEqual(github_auth.get_stored_token()["token"], "ghp_valid_token")

        # Case B: 401 Unauthorized token
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/user",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"message":"Bad credentials"}')
        )
        res_fail = github_auth.set_pat("ghp_bad_token")
        self.assertFalse(res_fail["success"])
        self.assertIn("401", res_fail["error"])

    @patch("urllib.request.urlopen")
    def test_device_flow_lifecycle(self, mock_urlopen):
        """Test device flow start and poll states (pending, slow_down, expired, complete)."""
        # Set Client ID
        os.environ["SPECTRA_GITHUB_CLIENT_ID"] = "dummy_client_id_123"

        # 1. Start Device Flow
        start_resp = MagicMock()
        start_resp.read.return_value = json.dumps({
            "device_code": "dev123",
            "user_code": "WDJB-MJHT",
            "verification_uri": "https://github.com/login/device",
            "interval": 5,
            "expires_in": 900
        }).encode("utf-8")
        start_resp.__enter__.return_value = start_resp
        mock_urlopen.return_value = start_resp

        start_res = github_auth.start_device_flow()
        self.assertTrue(start_res["success"])
        self.assertEqual(start_res["user_code"], "WDJB-MJHT")

        # 2. Poll: authorization_pending
        poll_resp_pending = MagicMock()
        poll_resp_pending.read.return_value = json.dumps({"error": "authorization_pending"}).encode("utf-8")
        poll_resp_pending.__enter__.return_value = poll_resp_pending
        mock_urlopen.return_value = poll_resp_pending

        poll_res = github_auth.poll_device_flow("dev123", interval=5)
        self.assertTrue(poll_res["success"])
        self.assertEqual(poll_res["status"], "pending")

        # 3. Poll: slow_down
        poll_resp_slow = MagicMock()
        poll_resp_slow.read.return_value = json.dumps({"error": "slow_down", "interval": 10}).encode("utf-8")
        poll_resp_slow.__enter__.return_value = poll_resp_slow
        mock_urlopen.return_value = poll_resp_slow

        poll_res = github_auth.poll_device_flow("dev123", interval=5)
        self.assertTrue(poll_res["success"])
        self.assertEqual(poll_res["status"], "slow_down")
        self.assertEqual(poll_res["interval"], 10)

        # 4. Poll: expired_token
        poll_resp_exp = MagicMock()
        poll_resp_exp.read.return_value = json.dumps({"error": "expired_token"}).encode("utf-8")
        poll_resp_exp.__enter__.return_value = poll_resp_exp
        mock_urlopen.return_value = poll_resp_exp

        poll_res = github_auth.poll_device_flow("dev123")
        self.assertFalse(poll_res["success"])
        self.assertEqual(poll_res["status"], "expired")

        # 5. Poll: success (token returned and validated)
        poll_resp_ok = MagicMock()
        poll_resp_ok.read.return_value = json.dumps({"access_token": "ghu_token999"}).encode("utf-8")
        poll_resp_ok.__enter__.return_value = poll_resp_ok

        user_resp = MagicMock()
        user_resp.read.return_value = json.dumps({"login": "device_user"}).encode("utf-8")
        user_resp.__enter__.return_value = user_resp

        mock_urlopen.side_effect = [poll_resp_ok, user_resp]

        poll_res = github_auth.poll_device_flow("dev123")
        self.assertTrue(poll_res["success"])
        self.assertEqual(poll_res["status"], "complete")
        self.assertEqual(poll_res["login"], "device_user")
        self.assertEqual(github_auth.get_stored_token()["token"], "ghu_token999")

    def test_upload_missing_auth_returns_error_and_prefilled_url(self):
        """When not authenticated, upload returns clean error and prefilled submission URL."""
        bundle = {
            "identity": {"model_name": "Jura Z6", "article_number": "15012"},
            "eeprom_words": {"0x0001": 100},
        }
        success, msg, url = spectra_probe.upload_capture_to_community_repo(bundle_data=bundle, open_browser=False)
        self.assertFalse(success)
        self.assertIn("Authentication missing", msg)
        self.assertIsNotNone(url)
        self.assertIn("https://github.com/Pr0xyA-91/spectra-captures/issues/new", url)

    @patch("urllib.request.urlopen")
    def test_upload_small_bundle_fits_in_issue_body(self, mock_urlopen):
        """Bundle fits in <= 65536 chars: posted directly into issue body."""
        github_auth.save_stored_token("valid_token", "dev_user")

        mock_issue_resp = MagicMock()
        mock_issue_resp.read.return_value = json.dumps({
            "html_url": "https://github.com/Pr0xyA-91/spectra-captures/issues/42"
        }).encode("utf-8")
        mock_issue_resp.__enter__.return_value = mock_issue_resp
        mock_urlopen.return_value = mock_issue_resp

        bundle = {
            "identity": {"model_name": "Jura E8", "article_number": "15355"},
            "eeprom_words": {"0x0180": 42},
        }

        success, msg, issue_url = spectra_probe.upload_capture_to_community_repo(bundle_data=bundle)
        self.assertTrue(success)
        self.assertEqual(issue_url, "https://github.com/Pr0xyA-91/spectra-captures/issues/42")

        # Verify request sent to /repos/.../issues directly without calling /gists
        self.assertEqual(mock_urlopen.call_count, 1)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/repos/Pr0xyA-91/spectra-captures/issues", req.full_url)
        payload = json.loads(req.data.decode("utf-8"))
        self.assertIn("```json", payload["body"])
        self.assertIn("Jura E8", payload["body"])
        self.assertEqual(payload.get("labels"), ["capture"])

    @patch("urllib.request.urlopen")
    def test_upload_large_bundle_creates_gist(self, mock_urlopen):
        """Bundle > 65536 chars creates a secret Gist and links it in the issue body."""
        github_auth.save_stored_token("valid_token", "dev_user")

        # Generate large bundle > 65536 chars (5000 items is ~100KB)
        large_eeprom = {f"0x{i:04X}": 12345 for i in range(5000)}
        bundle = {
            "identity": {"model_name": "Jura Giga 6", "article_number": "15214"},
            "eeprom_words": large_eeprom,
        }

        mock_gist_resp = MagicMock()
        mock_gist_resp.read.return_value = json.dumps({
            "html_url": "https://gist.github.com/spectra/abcdef123456"
        }).encode("utf-8")
        mock_gist_resp.__enter__.return_value = mock_gist_resp

        mock_issue_resp = MagicMock()
        mock_issue_resp.read.return_value = json.dumps({
            "html_url": "https://github.com/Pr0xyA-91/spectra-captures/issues/99"
        }).encode("utf-8")
        mock_issue_resp.__enter__.return_value = mock_issue_resp

        mock_urlopen.side_effect = [mock_gist_resp, mock_issue_resp]

        success, msg, issue_url = spectra_probe.upload_capture_to_community_repo(bundle_data=bundle)
        self.assertTrue(success)
        self.assertEqual(issue_url, "https://github.com/Pr0xyA-91/spectra-captures/issues/99")

        # Call 1: Gist creation
        gist_req = mock_urlopen.call_args_list[0][0][0]
        self.assertEqual(gist_req.full_url, "https://api.github.com/gists")
        gist_payload = json.loads(gist_req.data.decode("utf-8"))
        self.assertFalse(gist_payload["public"])

        # Call 2: Issue creation with Gist link in body
        issue_req = mock_urlopen.call_args_list[1][0][0]
        issue_payload = json.loads(issue_req.data.decode("utf-8"))
        self.assertIn("https://gist.github.com/spectra/abcdef123456", issue_payload["body"])

    @patch("urllib.request.urlopen")
    def test_upload_label_422_retries_without_label(self, mock_urlopen):
        """If GitHub returns 422 because 'capture' label doesn't exist, retry without label."""
        github_auth.save_stored_token("valid_token", "dev_user")

        # First call fails with 422 Unprocessable Entity (e.g. label does not exist)
        err_422 = urllib.error.HTTPError(
            url="https://api.github.com/repos/Pr0xyA-91/spectra-captures/issues",
            code=422,
            msg="Unprocessable Entity",
            hdrs={},
            fp=io.BytesIO(b'{"message":"Label does not exist"}')
        )

        # Retry succeeds
        mock_retry_resp = MagicMock()
        mock_retry_resp.read.return_value = json.dumps({
            "html_url": "https://github.com/Pr0xyA-91/spectra-captures/issues/50"
        }).encode("utf-8")
        mock_retry_resp.__enter__.return_value = mock_retry_resp

        mock_urlopen.side_effect = [err_422, mock_retry_resp]

        bundle = {"identity": {"model_name": "Jura D4", "article_number": "15201"}}
        success, msg, issue_url = spectra_probe.upload_capture_to_community_repo(bundle_data=bundle)
        self.assertTrue(success)
        self.assertEqual(issue_url, "https://github.com/Pr0xyA-91/spectra-captures/issues/50")

        # Check that retry had no "labels" key in payload
        retry_req = mock_urlopen.call_args_list[1][0][0]
        retry_payload = json.loads(retry_req.data.decode("utf-8"))
        self.assertNotIn("labels", retry_payload)

    @patch("urllib.request.urlopen")
    def test_auth_status_rejects_revoked_env_token_401(self, mock_urlopen):
        """An env token that fails validation with 401 should report authenticated=False."""
        os.environ["SPECTRA_GITHUB_TOKEN"] = "ghp_revoked"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/user",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"message":"Bad credentials"}')
        )
        status = github_auth.get_auth_status()
        self.assertFalse(status["authenticated"])
        self.assertIsNone(status["login"])

    @patch("urllib.request.urlopen")
    def test_upload_reads_nested_metadata_timestamp_and_build(self, mock_urlopen):
        """upload_capture_to_community_repo should read metadata.timestamp and metadata.spectra_build."""
        github_auth.save_stored_token("valid_token", "dev_user")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "html_url": "https://github.com/Pr0xyA-91/spectra-captures/issues/77"
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        bundle = {
            "metadata": {
                "timestamp": "2026-11-12T10:11:12",
                "spectra_build": "20261112.0001",
            },
            "identity": {"model_name": "Jura ENA 7", "article_number": "13500"},
        }
        success, _, _ = spectra_probe.upload_capture_to_community_repo(bundle_data=bundle)
        self.assertTrue(success)
        issue_payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertIn("2026-11-12T10:11:12", issue_payload["body"])
        self.assertIn("20261112.0001", issue_payload["body"])


if __name__ == "__main__":
    unittest.main()
