#!/usr/bin/env python3
"""
SPECTRA GitHub Authentication Module.
Provides GitHub OAuth Device Flow (for desktop apps with no client secret)
and Personal Access Token (PAT) authentication with secure credential persistence.
"""

import os
import re
import sys
import json
import base64
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

# Override directory for unit tests
_CONFIG_DIR_OVERRIDE: Optional[Path] = None


def get_config_dir() -> Path:
    """Return user configuration directory for SPECTRA."""
    if _CONFIG_DIR_OVERRIDE is not None:
        _CONFIG_DIR_OVERRIDE.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(_CONFIG_DIR_OVERRIDE, 0o700)
            except OSError:
                pass
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
    if os.name != "nt":
        try:
            os.chmod(p, 0o700)
        except OSError:
            pass
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


_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def _get_win32_dpapi_handles(data_blob_cls):
    """Return configured (crypt32, kernel32) DLL handles with 64-bit safe ctypes signatures."""
    import ctypes
    from ctypes import wintypes

    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is not None:
        crypt32 = win_dll("crypt32", use_last_error=True)
        kernel32 = win_dll("kernel32", use_last_error=True)
    else:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

    p_blob = ctypes.POINTER(data_blob_cls)
    for fn_name in ("CryptProtectData", "CryptUnprotectData"):
        fn = getattr(crypt32, fn_name)
        fn.argtypes = [
            p_blob,
            wintypes.LPCWSTR if fn_name == "CryptProtectData" else ctypes.POINTER(wintypes.LPWSTR),
            p_blob,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            p_blob,
        ]
        fn.restype = wintypes.BOOL

    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _dpapi_protect(plaintext: str) -> str:
    """Encrypt UTF-8 plaintext with Windows DPAPI CryptProtectData and return base64."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    raw = plaintext.encode("utf-8")
    in_buf = (ctypes.c_ubyte * max(len(raw), 1))()
    if raw:
        ctypes.memmove(in_buf, raw, len(raw))
    in_blob = DATA_BLOB(len(raw), in_buf if raw else None)
    out_blob = DATA_BLOB()

    crypt32, kernel32 = _get_win32_dpapi_handles(DATA_BLOB)
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        err_code = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0
        raise ctypes.WinError(err_code) if hasattr(ctypes, "WinError") else OSError(f"CryptProtectData failed ({err_code})")
    try:
        enc_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData) if out_blob.cbData else b""
        return base64.b64encode(enc_bytes).decode("ascii")
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def _dpapi_unprotect(cipher_b64: str) -> str:
    """Decrypt base64 Windows DPAPI blob via CryptUnprotectData and return UTF-8 text."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    raw = base64.b64decode(cipher_b64.encode("ascii"))
    in_buf = (ctypes.c_ubyte * max(len(raw), 1))()
    if raw:
        ctypes.memmove(in_buf, raw, len(raw))
    in_blob = DATA_BLOB(len(raw), in_buf if raw else None)
    out_blob = DATA_BLOB()

    crypt32, kernel32 = _get_win32_dpapi_handles(DATA_BLOB)
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    ):
        err_code = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0
        raise ctypes.WinError(err_code) if hasattr(ctypes, "WinError") else OSError(f"CryptUnprotectData failed ({err_code})")
    try:
        dec_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData) if out_blob.cbData else b""
        return dec_bytes.decode("utf-8")
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def _write_auth_payload_atomic(auth_file: Path, payload: Dict[str, Any]) -> None:
    parent = auth_file.parent
    parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass
    with tempfile.NamedTemporaryFile(
        "w",
        dir=str(parent),
        prefix=".github_auth_",
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    ) as f:
        json.dump(payload, f)
        tmp_file = f.name
    try:
        if os.name != "nt":
            try:
                os.chmod(tmp_file, 0o600)
            except OSError:
                pass
        os.replace(tmp_file, str(auth_file))
    except Exception:
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except OSError:
            pass
        raise


def save_stored_token(token: str, login: str, method: str = "token") -> bool:
    """
    Persist authentication token securely.
    Tries keyring first; falls back to DPAPI-encrypted (Windows) or chmod 0600 JSON (POSIX).
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

    # 2. Persist metadata (and protected token only if keyring failed)
    try:
        auth_file = _get_auth_file()
        if keyring_saved:
            payload: Dict[str, Any] = {"login": login, "method": method, "keyring": True}
        elif os.name == "nt":
            payload = {
                "token_dpapi": _dpapi_protect(token),
                "login": login,
                "method": method,
            }
        else:
            payload = {"token": token, "login": login, "method": method}
        _write_auth_payload_atomic(auth_file, payload)
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
            if not isinstance(data, dict):
                return None
            login = str(data.get("login", "user")).strip()
            method = str(data.get("method", "stored"))
            if data.get("token_dpapi"):
                if os.name == "nt":
                    plain = _dpapi_unprotect(str(data["token_dpapi"]))
                    if plain and plain.strip():
                        return {"token": plain.strip(), "login": login, "method": method}
                return None
            t = data.get("token")
            if t and str(t).strip():
                plain_tok = str(t).strip()
                # Auto-migrate legacy plaintext Windows token to DPAPI
                if os.name == "nt":
                    try:
                        migrated = {"token_dpapi": _dpapi_protect(plain_tok), "login": login, "method": method}
                        _write_auth_payload_atomic(auth_file, migrated)
                    except Exception:
                        pass
                return {
                    "token": plain_tok,
                    "login": login,
                    "method": method,
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
    For classic PATs (ghp_/gho_), also verifies that 'public_repo' or 'repo' scope is granted.
    Returns: (is_valid, login_name, error_message)
    """
    if not token or not token.strip():
        return False, None, "Empty token provided."

    clean_token = token.strip()
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {clean_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SPECTRA-Diagnostics",
        },
    )
    try:
        import tls_utils
        with urllib.request.urlopen(req, timeout=timeout, context=tls_utils.get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            login = data.get("login") or "user"
            headers = getattr(resp, "headers", None)
            scopes_hdr = headers.get("X-OAuth-Scopes") if headers is not None and hasattr(headers, "get") else None
            if isinstance(scopes_hdr, str) and clean_token.startswith(("ghp_", "gho_")):
                scopes = {s.strip().lower() for s in scopes_hdr.split(",") if s.strip()}
                if "repo" not in scopes and "public_repo" not in scopes:
                    return (
                        False,
                        None,
                        "GitHub token is missing the 'public_repo' (or 'repo') scope required to create issues and upload captures.",
                    )
            return True, login, None
    except urllib.error.HTTPError as he:
        err_info = _extract_github_http_error(he)
        if he.code == 401:
            detail = f" ({err_info['message']})" if err_info["message"] else ""
            return False, None, f"Invalid GitHub token: 401 Unauthorized{detail}"
        elif he.code == 403:
            detail = err_info["message"] or "Access forbidden or API rate limit exceeded"
            return False, None, f"403 Forbidden: {detail}"
        else:
            detail = err_info["message"] or he.reason
            return False, None, f"GitHub API error {he.code}: {detail}"
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


DEFAULT_ISSUES_REPO = "Pr0xyA-91/spectra"
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TOKEN_REDACT_PATTERNS = (
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)(?:_|%5[Ff])[A-Za-z0-9_%-]{10,}\b"),
    re.compile(r"\bgithub(?:_|%5[Ff])pat(?:_|%5[Ff])[A-Za-z0-9_%-]{10,}\b"),
    re.compile(r"(?i)((?:Proxy-)?Authorization\s*:\s*(?:Bearer|token|Basic)\s+)[^\s\"']+"),
    re.compile(r"(?i)(https?://)([^:@/\s]+:[^@/\s]+)@"),
    re.compile(r"(?i)((?:token|access_token|api_key|password|client_secret)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}&]+"),
)
_USER_PATH_PATTERNS = (
    (re.compile(r"file:///home/[^/\s\"']+(?:/|$)"), "file:///~/"),
    (re.compile(r"/home/[^/\s\"']+(?:/|$)"), "~/"),
    (re.compile(r"/Users/[^/\s\"']+(?:/|$)"), "~/"),
    (re.compile(r"/root(?:/|$)"), "~/"),
    (re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s\"']+(?:\\|$)"), "~\\"),
    (re.compile(r"(?i)[A-Z]:/Users/[^/\s\"']+(?:/|$)"), "~/"),
    (re.compile(r"\\\\[A-Za-z0-9_.-]+\\[^\\\s\"']+(?:\\[^\s\"']*)?"), "\\\\<REDACTED_UNC>"),
)


def get_issues_repo(override: Optional[str] = None) -> str:
    """Return validated GitHub owner/repo target for user issue submissions."""
    for candidate in (override, os.environ.get("SPECTRA_ISSUES_REPO")):
        if candidate:
            cleaned = str(candidate).strip()
            if _REPO_PATTERN.match(cleaned):
                return cleaned
    return DEFAULT_ISSUES_REPO


def sanitize_issue_text(text: str, max_chars: int = 32000) -> str:
    """Redact credentials and local OS user home paths from issue text/log snippets."""
    if not text:
        return ""
    cleaned = str(text).replace("\x00", "")
    for pat in _TOKEN_REDACT_PATTERNS:
        if pat.groups:
            cleaned = pat.sub(r"\1[REDACTED]", cleaned)
        else:
            cleaned = pat.sub("[REDACTED_TOKEN]", cleaned)
    for pat, repl in _USER_PATH_PATTERNS:
        cleaned = pat.sub(lambda _m, r=repl: r, cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "\n\n... [truncated]"
    return cleaned


def build_github_issue_web_url(
    title: str,
    body: str,
    labels: Optional[List[str]] = None,
    repo: Optional[str] = None,
) -> str:
    """Build a safe pre-filled GitHub new-issue URL for browser submission fallback."""
    target_repo = get_issues_repo(repo)
    safe_title = sanitize_issue_text(title, max_chars=200).strip()
    safe_body = sanitize_issue_text(body, max_chars=4800).strip()
    if len(body or "") > 4800:
        safe_body += "\n\n_(Truncated for browser URL length; attach additional logs if needed.)_"
    params: Dict[str, str] = {
        "title": safe_title,
        "body": safe_body,
    }
    clean_labels = [str(lb).strip() for lb in (labels or []) if str(lb).strip()]
    if clean_labels:
        params["labels"] = ",".join(clean_labels[:5])
    return f"https://github.com/{target_repo}/issues/new?{urllib.parse.urlencode(params)}"


def _extract_github_http_error(he: urllib.error.HTTPError) -> Dict[str, Any]:
    """Safely parse GitHub API HTTPError body and headers without leaking secrets."""
    raw_body = ""
    try:
        raw_bytes = he.read()
        if isinstance(raw_bytes, bytes):
            raw_body = raw_bytes.decode("utf-8", errors="ignore")
        elif isinstance(raw_bytes, str):
            raw_body = raw_bytes
    except Exception:
        raw_body = ""

    body_json: Dict[str, Any] = {}
    if raw_body:
        try:
            parsed = json.loads(raw_body)
            if isinstance(parsed, dict):
                body_json = parsed
        except Exception:
            pass

    api_message = sanitize_issue_text(str(body_json.get("message") or "").strip(), max_chars=400)
    errors_raw = body_json.get("errors")
    errors_list = errors_raw if isinstance(errors_raw, list) else []

    headers = getattr(he, "headers", None)

    def _hdr(name: str) -> str:
        if headers is None or not hasattr(headers, "get"):
            return ""
        val = headers.get(name)
        return val.strip() if isinstance(val, str) else ""

    oauth_scopes = _hdr("X-OAuth-Scopes")
    accepted_scopes = _hdr("X-Accepted-OAuth-Scopes")
    rate_remaining = _hdr("X-RateLimit-Remaining")
    retry_after = _hdr("Retry-After")

    msg_lower = api_message.lower()
    is_rate_limit = (
        rate_remaining == "0"
        or bool(retry_after)
        or "rate limit" in msg_lower
    )
    has_label_field_err = any(
        isinstance(item, dict) and str(item.get("field") or "").lower() == "label"
        for item in errors_list
    )
    is_label_error = (
        he.code == 422
        or (
            he.code == 403
            and not is_rate_limit
            and ("label" in msg_lower or has_label_field_err)
        )
    )

    return {
        "code": he.code,
        "reason": str(getattr(he, "reason", "") or ""),
        "message": api_message,
        "errors": errors_list,
        "oauth_scopes": oauth_scopes,
        "accepted_scopes": accepted_scopes,
        "rate_remaining": rate_remaining,
        "retry_after": retry_after,
        "is_rate_limit": is_rate_limit,
        "is_label_error": is_label_error,
    }


def _format_github_http_error(err_info: Dict[str, Any], prefix: str = "GitHub API error") -> str:
    """Format a user-actionable, sanitized GitHub API error string."""
    code = err_info.get("code")
    reason = err_info.get("reason") or ""
    message = err_info.get("message") or ""
    oauth_scopes = err_info.get("oauth_scopes") or ""

    if code == 401:
        if message:
            return f"{prefix} 401: {message} (check or refresh your GitHub sign-in)."
        return f"{prefix} 401: Unauthorized (check or refresh your GitHub sign-in)."
    if code == 403:
        if err_info.get("is_rate_limit"):
            return f"{prefix} 403: {message or 'GitHub API rate limit exceeded'}."
        if message:
            scope_hint = ""
            if oauth_scopes and any(k in message.lower() for k in ("scope", "permission", "accessible")):
                scope_hint = f" [token scopes: {oauth_scopes}]"
            return f"{prefix} 403: {message}{scope_hint}"
        return f"{prefix} 403: Forbidden (insufficient token permissions or rate limit exceeded)."
    return f"{prefix} {code}: {message or reason}"


def create_github_issue(
    title: str,
    body: str,
    labels: Optional[List[str]] = None,
    repo: Optional[str] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """
    Create a GitHub issue on the public SPECTRA repository using the authenticated user's token.
    Never logs or returns tokens, and never opens a browser server-side.
    Always returns a pre-filled `web_url` fallback for unauthenticated or failed submissions.
    """
    target_repo = get_issues_repo(repo)
    safe_title = sanitize_issue_text(title, max_chars=200).strip()
    safe_body = sanitize_issue_text(body, max_chars=32000).strip()
    clean_labels = [str(lb).strip() for lb in (labels or []) if str(lb).strip()][:5]

    if not safe_title:
        return {"success": False, "error": "Issue title is required.", "repo": target_repo}
    if not safe_body:
        return {"success": False, "error": "Issue description is required.", "repo": target_repo}

    web_url = build_github_issue_web_url(safe_title, safe_body, labels=clean_labels, repo=target_repo)

    resolved = resolve_token()
    token = resolved.get("token") if resolved else None
    if not token:
        return {
            "success": False,
            "auth_required": True,
            "error": "Not signed in to GitHub. Sign in via CONFIG -> GitHub or open the pre-filled issue in your browser.",
            "web_url": web_url,
            "repo": target_repo,
        }

    api_url = f"https://api.github.com/repos/{target_repo}/issues"

    def _post_issue(include_labels: bool = True):
        payload: Dict[str, Any] = {
            "title": safe_title,
            "body": safe_body,
        }
        if include_labels and clean_labels:
            payload["labels"] = clean_labels
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "SPECTRA-Diagnostics",
            },
        )
        import tls_utils
        return urllib.request.urlopen(req, timeout=timeout, context=tls_utils.get_ssl_context())

    def _format_success(raw_bytes: bytes) -> Dict[str, Any]:
        resp_data = json.loads(raw_bytes.decode("utf-8"))
        return {
            "success": True,
            "issue_url": resp_data.get("html_url", ""),
            "issue_number": resp_data.get("number"),
            "web_url": web_url,
            "repo": target_repo,
        }

    try:
        with _post_issue(include_labels=True) as resp:
            return _format_success(resp.read())
    except urllib.error.HTTPError as he:
        err_info = _extract_github_http_error(he)
        if clean_labels and err_info["is_label_error"]:
            try:
                with _post_issue(include_labels=False) as resp2:
                    return _format_success(resp2.read())
            except urllib.error.HTTPError as he2:
                err_info2 = _extract_github_http_error(he2)
                return {
                    "success": False,
                    "error": _format_github_http_error(err_info2),
                    "web_url": web_url,
                    "repo": target_repo,
                }
            except Exception as e2:
                return {
                    "success": False,
                    "error": f"GitHub API error on retry: {e2}",
                    "web_url": web_url,
                    "repo": target_repo,
                }
        return {
            "success": False,
            "error": _format_github_http_error(err_info),
            "web_url": web_url,
            "repo": target_repo,
        }
    except urllib.error.URLError as ue:
        return {
            "success": False,
            "error": f"Network error contacting GitHub: {ue.reason}",
            "web_url": web_url,
            "repo": target_repo,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create GitHub issue: {e}",
            "web_url": web_url,
            "repo": target_repo,
        }
