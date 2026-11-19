#!/usr/bin/env python3
"""
SPECTRA GitHub Authentication Module.
Provides GitHub OAuth Device Flow (for desktop apps with no client secret)
and Personal Access Token (PAT) authentication with secure credential persistence.
"""

import os
import sys
import json
import shutil
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# Override directory for unit tests
_CONFIG_DIR_OVERRIDE: Optional[Path] = None


def get_config_dir() -> Path:
    """Return user configuration directory for SPECTRA."""
    if _CONFIG_DIR_OVERRIDE is not None:
        _CONFIG_DIR_OVERRIDE.mkdir(parents=True, exist_ok=True)
        return _CONFIG_DIR_OVERRIDE

    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            p = Path(appdata) / "SPECTRA"
        else:
            p = Path.home() / "AppData" / "Roaming" / "SPECTRA"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            p = Path(xdg) / "spectra"
        else:
            p = Path.home() / ".config" / "spectra"

    p.mkdir(parents=True, exist_ok=True)
    return p


def get_client_id() -> Optional[str]:
    """
    Retrieve GitHub OAuth Client ID from environment or user configuration.
    Returns None if not configured (never invents or hardcodes a client ID).
    """
    env_id = os.environ.get("SPECTRA_GITHUB_CLIENT_ID")
    if env_id and env_id.strip():
        return env_id.strip()

    cfg_file = get_config_dir() / "config.json"
    if cfg_file.is_file():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                cid = data.get("github_client_id")
                if cid and str(cid).strip():
                    return str(cid).strip()
        except Exception:
            pass

    return None


def _get_auth_file() -> Path:
    return get_config_dir() / "github_auth.json"


def save_stored_token(token: str, login: str, method: str = "token") -> bool:
    """
    Persist authentication token securely.
    Tries keyring first; falls back to chmod 0600 JSON file in config dir.
    Never logs token.
    """
    token = token.strip()
    login = login.strip()

    # 1. Try keyring
    keyring_saved = False
    try:
        import keyring
        keyring.set_password("spectra", "github_token", token)
        keyring.set_password("spectra", "github_login", login)
        keyring.set_password("spectra", "github_method", method)
        keyring_saved = True
    except Exception:
        keyring_saved = False

    # 2. Persist metadata (and token only if keyring failed) with 0o600 permissions
    try:
        auth_file = _get_auth_file()
        payload = (
            {"login": login, "method": method, "keyring": True}
            if keyring_saved
            else {"token": token, "login": login, "method": method}
        )
        if os.name != "nt":
            tmp_file = f"{auth_file}.tmp.{os.getpid()}"
            fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.chmod(tmp_file, 0o600)
            except Exception:
                pass
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_file, str(auth_file))
        else:
            with open(auth_file, "w", encoding="utf-8") as f:
                json.dump(payload, f)
        return True
    except Exception:
        return keyring_saved


def get_stored_token() -> Optional[Dict[str, str]]:
    """Retrieve stored credentials if available. Never logs token."""
    # 1. Keyring
    try:
        import keyring
        t = keyring.get_password("spectra", "github_token")
        if t and t.strip():
            l = keyring.get_password("spectra", "github_login") or "user"
            m = keyring.get_password("spectra", "github_method") or "stored"
            return {"token": t.strip(), "login": l.strip(), "method": m}
    except Exception:
        pass

    # 2. JSON file fallback
    auth_file = _get_auth_file()
    if auth_file.is_file():
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                t = data.get("token")
                if t and str(t).strip():
                    return {
                        "token": str(t).strip(),
                        "login": str(data.get("login", "user")).strip(),
                        "method": str(data.get("method", "stored"))
                    }
        except Exception:
            pass

    return None


def clear_stored_token() -> None:
    """Clear stored authentication credentials."""
    try:
        import keyring
        for k in ("github_token", "github_login", "github_method"):
            try:
                keyring.delete_password("spectra", k)
            except Exception:
                pass
    except Exception:
        pass

    auth_file = _get_auth_file()
    if auth_file.is_file():
        try:
            auth_file.unlink()
        except Exception:
            pass


def resolve_token() -> Optional[Dict[str, str]]:
    """
    Token resolution order for upload:
    1. stored token (keyring / github_auth.json)
    2. SPECTRA_GITHUB_TOKEN
    3. GITHUB_TOKEN
    4. gh auth token (subprocess, if gh exists, with timeout)
    Returns: {"token": ..., "login": ..., "method": ...} or None.
    """
    # 1. Stored token
    stored = get_stored_token()
    if stored:
        return stored

    # 2. SPECTRA_GITHUB_TOKEN
    spectra_tok = os.environ.get("SPECTRA_GITHUB_TOKEN")
    if spectra_tok and spectra_tok.strip():
        return {"token": spectra_tok.strip(), "login": None, "method": "SPECTRA_GITHUB_TOKEN"}

    # 3. GITHUB_TOKEN
    gh_tok = os.environ.get("GITHUB_TOKEN")
    if gh_tok and gh_tok.strip():
        return {"token": gh_tok.strip(), "login": None, "method": "GITHUB_TOKEN"}

    # 4. gh auth token
    gh_bin = shutil.which("gh")
    if gh_bin:
        try:
            res = subprocess.run([gh_bin, "auth", "token"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                return {"token": res.stdout.strip(), "login": None, "method": "gh_cli"}
        except Exception:
            pass

    return None


def validate_token(token: str, timeout: int = 10) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate token against GET https://api.github.com/user.
    Returns: (is_valid, login_name, error_message)
    """
    if not token or not token.strip():
        return False, None, "Empty token provided."

    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token.strip()}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "SPECTRA-Diagnostics"
        }
    )
    try:
        import tls_utils
        with urllib.request.urlopen(req, timeout=timeout, context=tls_utils.get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            login = data.get("login") or "user"
            return True, login, None
    except urllib.error.HTTPError as he:
        if he.code == 401:
            return False, None, "Invalid GitHub token: 401 Unauthorized"
        elif he.code == 403:
            return False, None, "Access forbidden or API rate limit exceeded: 403 Forbidden"
        else:
            return False, None, f"GitHub API error {he.code}: {he.reason}"
    except urllib.error.URLError as ue:
        return False, None, f"Network error contacting GitHub: {ue.reason}"
    except Exception as e:
        return False, None, f"Token validation failed: {e}"


def set_pat(token: str) -> Dict[str, Any]:
    """Validate and store Personal Access Token."""
    valid, login, err = validate_token(token)
    if not valid:
        return {"success": False, "error": err or "Invalid token"}

    saved = save_stored_token(token, login or "user", method="pat")
    if not saved:
        return {"success": False, "error": "Failed to persist credentials to disk/keyring"}
    return {"success": True, "login": login}


def start_device_flow() -> Dict[str, Any]:
    """
    Initiate GitHub OAuth Device Flow.
    POST https://github.com/login/device/code with client_id and scope.
    """
    client_id = get_client_id()
    if not client_id:
        return {
            "success": False,
            "error": "GitHub Device Flow is unavailable because no Client ID is configured. Please provide a Personal Access Token instead."
        }

    post_data = urllib.parse.urlencode({
        "client_id": client_id,
        "scope": "public_repo gist"
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://github.com/login/device/code",
        data=post_data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "SPECTRA-Diagnostics"
        }
    )
    try:
        import tls_utils
        with urllib.request.urlopen(req, timeout=12, context=tls_utils.get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            device_code = data.get("device_code")
            user_code = data.get("user_code")
            verification_uri = data.get("verification_uri")
            interval = int(data.get("interval", 5))
            expires_in = int(data.get("expires_in", 900))

            if not device_code or not user_code or not verification_uri:
                return {"success": False, "error": "Incomplete response from GitHub device auth endpoint"}

            return {
                "success": True,
                "device_code": device_code,
                "user_code": user_code,
                "verification_uri": verification_uri,
                "interval": interval,
                "expires_in": expires_in
            }
    except urllib.error.HTTPError as he:
        return {"success": False, "error": f"Device authorization error ({he.code}): {he.reason}"}
    except Exception as e:
        return {"success": False, "error": f"Failed to initiate device flow: {e}"}


def poll_device_flow(device_code: str, interval: int = 5) -> Dict[str, Any]:
    """
    Poll GitHub token endpoint for device flow completion.
    POST https://github.com/login/oauth/access_token.
    Respects interval, slow_down, authorization_pending, expired_token, access_denied.
    """
    client_id = get_client_id()
    if not client_id:
        return {"success": False, "error": "No Client ID configured"}

    post_data = urllib.parse.urlencode({
        "client_id": client_id,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://github.com/login/oauth/access_token",
        data=post_data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "SPECTRA-Diagnostics"
        }
    )

    try:
        import tls_utils
        with urllib.request.urlopen(req, timeout=12, context=tls_utils.get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))

            err = data.get("error")
            if err:
                if err == "authorization_pending":
                    return {"success": True, "status": "pending", "interval": interval}
                elif err == "slow_down":
                    new_interval = int(data.get("interval", interval + 5))
                    return {"success": True, "status": "slow_down", "interval": new_interval}
                elif err == "expired_token":
                    return {"success": False, "status": "expired", "error": "Device authorization code expired. Please start over."}
                elif err == "access_denied":
                    return {"success": False, "status": "denied", "error": "Authorization was cancelled or denied on GitHub."}
                else:
                    return {"success": False, "status": err, "error": data.get("error_description", err)}

            access_token = data.get("access_token")
            if not access_token:
                return {"success": False, "error": "No access token in response"}

            valid, login, val_err = validate_token(access_token)
            if not valid:
                return {"success": False, "error": f"Received token could not be verified: {val_err}"}

            save_stored_token(access_token, login or "user", method="device_flow")
            return {
                "success": True,
                "status": "complete",
                "login": login
            }
    except urllib.error.HTTPError as he:
        err_detail = he.reason
        try:
            body_raw = he.read().decode("utf-8", errors="ignore")
            body_json = json.loads(body_raw) if body_raw else {}
            if isinstance(body_json, dict) and (body_json.get("error_description") or body_json.get("error")):
                err_detail = body_json.get("error_description") or body_json.get("error")
        except Exception:
            pass
        return {"success": False, "error": f"Poll request failed ({he.code}): {err_detail}"}
    except Exception as e:
        return {"success": False, "error": f"Device poll failed: {e}"}


def logout() -> Dict[str, Any]:
    """Log out and remove stored authentication credentials."""
    clear_stored_token()
    return {"success": True}


def get_auth_status() -> Dict[str, Any]:
    """
    Return authentication status.
    NEVER includes the token.
    Returns: {authenticated: bool, login: Optional[str], method: Optional[str], device_flow_available: bool}
    """
    resolved = resolve_token()
    has_cid = bool(get_client_id())

    if not resolved:
        return {
            "authenticated": False,
            "login": None,
            "method": None,
            "device_flow_available": has_cid
        }

    login = resolved.get("login")
    if not login:
        valid, fetched_login, err = validate_token(resolved["token"], timeout=5)
        if not valid:
            return {
                "authenticated": False,
                "login": None,
                "method": None,
                "device_flow_available": has_cid,
                "error": err,
            }
        login = fetched_login

    return {
        "authenticated": True,
        "login": login,
        "method": resolved.get("method"),
        "device_flow_available": has_cid
    }
