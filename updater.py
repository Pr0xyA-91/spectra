#!/usr/bin/env python3
"""
SPECTRA Cross-Platform Self-Updater
===================================
Checks `Pr0xyA-91/spectra` (GitHub Releases + raw release metadata/version)
for newer builds (`Build YYYYMMDD.HHMM`) and applies verified in-place updates
across Windows (`spectra_update.exe --silent --relaunch`) and Linux (git ff-only
pull or verified GitHub source tarball extraction + process restart).
"""

import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

import tls_utils


PUBLIC_REPO = (os.environ.get("SPECTRA_UPDATE_REPO", "Pr0xyA-91/spectra") or "").strip() or "Pr0xyA-91/spectra"
GITHUB_API_LATEST_RELEASE = f"https://api.github.com/repos/{PUBLIC_REPO}/releases/latest"
RAW_MANIFEST_URL = f"https://raw.githubusercontent.com/{PUBLIC_REPO}/main/release_manifest.json"
RAW_VERSION_MAIN_URL = f"https://raw.githubusercontent.com/{PUBLIC_REPO}/main/version.py"
RAW_VERSION_WIN_URL = f"https://raw.githubusercontent.com/{PUBLIC_REPO}/windows/version.py"
RAW_WIN_UPDATER_URL = f"https://raw.githubusercontent.com/{PUBLIC_REPO}/windows/dist/spectra_update.exe"
RAW_LINUX_TARBALL_URL = f"https://github.com/{PUBLIC_REPO}/archive/refs/heads/main.tar.gz"
PUBLIC_GIT_URL = f"https://github.com/{PUBLIC_REPO}.git"

WINDOWS_UPDATER_ASSET_NAME = "spectra_update.exe"
MIN_UPDATER_EXE_BYTES = 512 * 1024  # 512 KB sanity floor against HTML/error payloads
CHECK_CACHE_TTL_SEC = 300.0

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

_BUILD_PATTERN = re.compile(r"(\d{8})\.(\d{4})(?:\.(\d+))?")
_VERSION_PY_BUILD_RE = re.compile(r'__build__\s*=\s*["\']([^"\']+)["\']')
_PRESERVED_USER_ITEMS = {
    "ui_prefs.json",
    ".env",
    "captures",
    "models",
    "__pycache__",
    ".git",
}

_state_lock = threading.Lock()
_update_thread: Optional[threading.Thread] = None
_cancel_event = threading.Event()
_cached_check: Optional[Dict[str, Any]] = None
_cached_check_ts: float = 0.0

_update_state: Dict[str, Any] = {
    "status": "idle",
    "percent": 0,
    "bytes_downloaded": 0,
    "total_bytes": 0,
    "message": "",
    "error": "",
    "current_build": "",
    "target_build": "",
    "in_progress": False,
    "restart_required": False,
    "platform": "windows" if (sys.platform.startswith("win") or os.name == "nt") else "linux",
    "started_at": 0.0,
    "finished_at": 0.0,
}


class UpdateError(RuntimeError):
    """Raised when an update download, verification, or apply step fails."""


class UpdateCancelledError(UpdateError):
    """Raised when the user cancels an active update before installation."""


def _current_platform() -> str:
    return "windows" if (sys.platform.startswith("win") or os.name == "nt") else "linux"


def _set_state(**kwargs: Any) -> None:
    with _state_lock:
        _update_state.update(kwargs)


def get_update_progress() -> Dict[str, Any]:
    """Return a thread-safe snapshot of the current self-update progress state."""
    with _state_lock:
        return dict(_update_state)


def parse_build_tuple(build_str: str) -> Tuple[int, ...]:
    """
    Parse a SPECTRA build string (e.g. '20261117.1320' or 'Build 20261117.1320')
    into a comparable integer tuple. Returns () if no build numbers exist.
    """
    text = str(build_str or "").strip()
    if not text:
        return ()
    m = _BUILD_PATTERN.search(text)
    if m:
        groups = [int(g) for g in m.groups() if g is not None]
        return tuple(groups)
    digits = re.findall(r"\d+", text)
    if not digits:
        return ()
    return tuple(int(d) for d in digits[:4])


def extract_build_from_text(text: str) -> str:
    """Extract normalized 'YYYYMMDD.HHMM' build identifier from arbitrary text."""
    raw = str(text or "")
    m_py = _VERSION_PY_BUILD_RE.search(raw)
    if m_py:
        cand = m_py.group(1).strip()
        m_b = _BUILD_PATTERN.search(cand)
        return m_b.group(0) if m_b else cand
    m_b = _BUILD_PATTERN.search(raw)
    return m_b.group(0) if m_b else ""


def is_remote_build_newer(local_build: str, remote_build: str) -> bool:
    """Return True strictly when remote_build parses to a newer build than local_build."""
    local_t = parse_build_tuple(local_build)
    remote_t = parse_build_tuple(remote_build)
    if not local_t or not remote_t:
        return False
    return remote_t > local_t


def get_local_build() -> str:
    """Read the installed build string directly from local version.py or imported module."""
    ver_path = os.path.join(PROJECT_DIR, "version.py")
    if os.path.isfile(ver_path):
        try:
            with open(ver_path, "r", encoding="utf-8", errors="ignore") as f:
                parsed = extract_build_from_text(f.read())
                if parsed:
                    return parsed
        except Exception:
            pass
    try:
        import version
        return str(getattr(version, "__build__", "0")).strip()
    except Exception:
        return "0"


def _http_get_bytes(url: str, timeout: float = 4.0, headers: Optional[Dict[str, str]] = None) -> bytes:
    """Fetch raw bytes over verified HTTPS with Windows SChannel fallback when needed."""
    req_headers = {
        "User-Agent": f"SPECTRA-Updater/{get_local_build() or '0'}",
        "Cache-Control": "no-cache",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    ctx = tls_utils.get_ssl_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        if _current_platform() == "windows" and isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
            tmp_fd, tmp_path = tempfile.mkstemp(prefix="spectra_meta_")
            os.close(tmp_fd)
            try:
                tls_utils.windows_schannel_download(url, tmp_path, timeout_sec=max(timeout, 10.0))
                with open(tmp_path, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        raise


def _fetch_json(url: str, timeout: float = 4.0, accept_github: bool = False) -> Dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json"} if accept_github else {"Accept": "application/json"}
    raw = _http_get_bytes(url, timeout=timeout, headers=headers)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Unexpected JSON root type")
    return data


def _extract_release_notes_snippet(body: str, max_chars: int = 900) -> str:
    text = (body or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _fetch_manifest(url: str, timeout: float) -> Optional[Dict[str, Any]]:
    try:
        return _fetch_json(url, timeout=timeout, accept_github=False)
    except Exception:
        return None


def _select_best_candidate(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    valid = [c for c in candidates if parse_build_tuple(c.get("build", ""))]
    if not valid:
        return None
    valid.sort(key=lambda c: (parse_build_tuple(c["build"]), c.get("priority", 0)), reverse=True)
    return valid[0]


def check_for_updates(force: bool = False, timeout: float = 4.0) -> Dict[str, Any]:
    """
    Query GitHub Releases (`Pr0xyA-91/spectra`), `release_manifest.json`, and raw
    `version.py` to determine whether a newer SPECTRA build is available.
    Never raises uncaught network errors; returns structured status JSON.
    """
    global _cached_check, _cached_check_ts

    now = time.time()
    if not force and _cached_check is not None and (now - _cached_check_ts) < CHECK_CACHE_TTL_SEC:
        snap = dict(_cached_check)
        snap["current_build"] = get_local_build()
        snap["update_available"] = is_remote_build_newer(snap["current_build"], snap.get("latest_build", ""))
        return snap

    platform_name = _current_platform()
    current_build = get_local_build()
    install_mode = (
        "windows_exe"
        if platform_name == "windows"
        else ("linux_git" if os.path.isdir(os.path.join(PROJECT_DIR, ".git")) else "linux_tarball")
    )

    candidates: List[Dict[str, Any]] = []
    errors: List[str] = []
    manifest_data: Optional[Dict[str, Any]] = None
    release_data: Optional[Dict[str, Any]] = None

    # 1. Try GitHub Releases API
    try:
        release_data = _fetch_json(GITHUB_API_LATEST_RELEASE, timeout=timeout, accept_github=True)
        tag_build = extract_build_from_text(str(release_data.get("tag_name") or "")) or extract_build_from_text(
            str(release_data.get("name") or "")
        )
        assets = release_data.get("assets") or []
        win_asset_url = ""
        win_asset_size = 0
        win_asset_sha = ""
        manifest_asset_url = ""

        for asset in assets:
            if not isinstance(asset, dict):
                continue
            aname = str(asset.get("name") or "")
            if aname == WINDOWS_UPDATER_ASSET_NAME:
                win_asset_url = str(asset.get("browser_download_url") or "")
                win_asset_size = int(asset.get("size") or 0)
            elif aname == "release_manifest.json":
                manifest_asset_url = str(asset.get("browser_download_url") or "")

        if manifest_asset_url:
            manifest_data = _fetch_manifest(manifest_asset_url, timeout=min(timeout, 3.5))
            if manifest_data:
                assets_map = manifest_data.get("assets") or {}
                if isinstance(assets_map, dict) and WINDOWS_UPDATER_ASSET_NAME in assets_map:
                    wmeta = assets_map[WINDOWS_UPDATER_ASSET_NAME] or {}
                    win_asset_sha = str(wmeta.get("sha256") or "")
                    if not win_asset_size and wmeta.get("size"):
                        win_asset_size = int(wmeta["size"])

        if tag_build:
            candidates.append(
                {
                    "build": tag_build,
                    "priority": 3,
                    "source": "github_release",
                    "release_name": str(release_data.get("name") or f"Build {tag_build}"),
                    "release_url": str(release_data.get("html_url") or f"https://github.com/{PUBLIC_REPO}/releases"),
                    "release_notes": _extract_release_notes_snippet(str(release_data.get("body") or "")),
                    "published_at": str(release_data.get("published_at") or ""),
                    "download_url": (win_asset_url or RAW_WIN_UPDATER_URL)
                    if platform_name == "windows"
                    else RAW_LINUX_TARBALL_URL,
                    "expected_sha256": win_asset_sha if platform_name == "windows" else "",
                    "expected_size": win_asset_size if platform_name == "windows" else 0,
                }
            )
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            errors.append(f"GitHub Releases HTTP {exc.code}")
    except Exception as exc:
        errors.append(f"GitHub Releases: {exc}")

    # 2. Try raw release_manifest.json from main branch
    if manifest_data is None:
        manifest_data = _fetch_manifest(RAW_MANIFEST_URL, timeout=min(timeout, 3.5))
    if isinstance(manifest_data, dict):
        m_build_key = "windows_build" if platform_name == "windows" else "main_build"
        m_build = extract_build_from_text(str(manifest_data.get(m_build_key) or manifest_data.get("build") or ""))
        if m_build:
            assets_map = manifest_data.get("assets") or {}
            wmeta = assets_map.get(WINDOWS_UPDATER_ASSET_NAME, {}) if isinstance(assets_map, dict) else {}
            candidates.append(
                {
                    "build": m_build,
                    "priority": 2,
                    "source": "release_manifest",
                    "release_name": f"Build {m_build}",
                    "release_url": f"https://github.com/{PUBLIC_REPO}/releases",
                    "release_notes": _extract_release_notes_snippet(str(manifest_data.get("release_notes") or "")),
                    "published_at": str(manifest_data.get("published_at") or ""),
                    "download_url": str(wmeta.get("url") or RAW_WIN_UPDATER_URL)
                    if platform_name == "windows"
                    else RAW_LINUX_TARBALL_URL,
                    "expected_sha256": str(wmeta.get("sha256") or "") if platform_name == "windows" else "",
                    "expected_size": int(wmeta.get("size") or 0) if platform_name == "windows" else 0,
                }
            )

    # 3. Fallback / cross-check raw branch version.py
    raw_ver_url = RAW_VERSION_WIN_URL if platform_name == "windows" else RAW_VERSION_MAIN_URL
    try:
        raw_bytes = _http_get_bytes(raw_ver_url, timeout=min(timeout, 3.5))
        raw_build = extract_build_from_text(raw_bytes.decode("utf-8", errors="ignore"))
        if raw_build:
            candidates.append(
                {
                    "build": raw_build,
                    "priority": 1,
                    "source": "raw_version",
                    "release_name": f"Build {raw_build}",
                    "release_url": f"https://github.com/{PUBLIC_REPO}",
                    "release_notes": "",
                    "published_at": "",
                    "download_url": RAW_WIN_UPDATER_URL if platform_name == "windows" else RAW_LINUX_TARBALL_URL,
                    "expected_sha256": "",
                    "expected_size": 0,
                }
            )
    except Exception as exc:
        errors.append(f"Raw version check: {exc}")

    best = _select_best_candidate(candidates)
    if best is None:
        result = {
            "ok": False,
            "error": "; ".join(errors) if errors else "No remote release metadata available",
            "current_build": current_build,
            "latest_build": "",
            "update_available": False,
            "platform": platform_name,
            "install_mode": install_mode,
            "release_name": "",
            "release_url": f"https://github.com/{PUBLIC_REPO}/releases",
            "release_notes": "",
            "published_at": "",
            "download_url": "",
            "expected_sha256": "",
            "expected_size": 0,
            "checked_at": now,
            "source": "none",
        }
        return result

    latest_build = best["build"]
    update_available = is_remote_build_newer(current_build, latest_build)
    result = {
        "ok": True,
        "error": "",
        "current_build": current_build,
        "latest_build": latest_build,
        "update_available": update_available,
        "platform": platform_name,
        "install_mode": install_mode,
        "release_name": best["release_name"],
        "release_url": best["release_url"],
        "release_notes": best["release_notes"],
        "published_at": best["published_at"],
        "download_url": best["download_url"],
        "expected_sha256": best["expected_sha256"],
        "expected_size": best["expected_size"],
        "checked_at": now,
        "source": best["source"],
    }
    _cached_check = dict(result)
    _cached_check_ts = now
    return result


def verify_windows_updater_binary(
    file_path: str,
    expected_sha256: Optional[str] = None,
    min_bytes: int = MIN_UPDATER_EXE_BYTES,
) -> str:
    """
    Verify that a downloaded Windows updater binary exists, meets the minimum
    payload size floor, starts with a valid PE `MZ` signature, and matches
    expected_sha256 when provided. Returns the computed SHA-256 hex digest.
    """
    if not os.path.isfile(file_path):
        raise UpdateError("Downloaded updater binary not found on disk")

    size = os.path.getsize(file_path)
    if size < min_bytes:
        raise UpdateError(f"Downloaded updater binary is unexpectedly small ({size} bytes)")

    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        header = f.read(2)
        if header != b"MZ":
            raise UpdateError("Downloaded updater binary failed PE header (MZ) verification")
        sha.update(header)
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha.update(chunk)

    actual_sha = sha.hexdigest().lower()
    expected = (expected_sha256 or "").strip().lower()
    if expected and actual_sha != expected:
        raise UpdateError(f"SHA-256 mismatch: expected {expected}, got {actual_sha}")
    return actual_sha


def _download_file_with_progress(
    url: str,
    dest_path: str,
    expected_size: int = 0,
    timeout: float = 30.0,
) -> None:
    """Stream download to dest_path while updating _update_state and checking cancellation."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"SPECTRA-Updater/{get_local_build() or '0'}",
            "Cache-Control": "no-cache",
        },
    )
    ctx = tls_utils.get_ssl_context()

    def _on_schannel_progress(bytes_read: int) -> None:
        pct = 5
        if expected_size > 0:
            pct = min(80, 5 + int((bytes_read / expected_size) * 75))
        _set_state(
            bytes_downloaded=bytes_read,
            total_bytes=expected_size,
            percent=pct,
            message=f"Downloading update... {bytes_read // 1024} KB",
        )

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            content_len = int(resp.headers.get("Content-Length") or expected_size or 0)
            downloaded = 0
            with open(dest_path, "wb") as out:
                while True:
                    if _cancel_event.is_set():
                        raise UpdateCancelledError("Update cancelled by user")
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    pct = 15
                    if content_len > 0:
                        pct = min(80, 5 + int((downloaded / content_len) * 75))
                    _set_state(
                        bytes_downloaded=downloaded,
                        total_bytes=content_len,
                        percent=pct,
                        message=(
                            f"Downloading update... {downloaded // 1024} / {content_len // 1024} KB"
                            if content_len > 0
                            else f"Downloading update... {downloaded // 1024} KB"
                        ),
                    )
    except urllib.error.URLError as exc:
        if _current_platform() == "windows" and isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
            tls_utils.windows_schannel_download(
                url,
                dest_path,
                cancel_check=_cancel_event.is_set,
                progress_cb=_on_schannel_progress,
                timeout_sec=1800.0,
            )
            if _cancel_event.is_set():
                raise UpdateCancelledError("Update cancelled by user")
            return
        raise UpdateError(f"Download failed: {exc}") from exc


def _apply_windows_update(
    info: Dict[str, Any],
    on_before_restart: Optional[Callable[[], None]] = None,
) -> None:
    download_url = str(info.get("download_url") or RAW_WIN_UPDATER_URL)
    target_build = str(info.get("latest_build") or "")
    expected_sha = str(info.get("expected_sha256") or "")
    expected_size = int(info.get("expected_size") or 0)

    stage_dir = tempfile.mkdtemp(prefix="spectra_upd_")
    staged_exe = os.path.join(stage_dir, f"spectra_update_{target_build or 'latest'}.exe")

    _set_state(
        status="downloading",
        percent=5,
        message=f"Downloading Build {target_build} Windows updater...",
        target_build=target_build,
    )
    _download_file_with_progress(download_url, staged_exe, expected_size=expected_size, timeout=30.0)

    if _cancel_event.is_set():
        raise UpdateCancelledError("Update cancelled by user")

    _set_state(status="verifying", percent=85, message="Verifying updater integrity (PE + SHA-256)...")
    verify_windows_updater_binary(staged_exe, expected_sha256=expected_sha or None)

    _set_state(
        status="restarting",
        percent=98,
        restart_required=True,
        message="Launching Windows installer and restarting SPECTRA...",
    )

    spawn_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    cmd = [staged_exe, "--silent", "--relaunch", f"--dir={PROJECT_DIR}"]
    subprocess.Popen(cmd, cwd=stage_dir, close_fds=True, creationflags=spawn_flags)

    time.sleep(0.45)
    if on_before_restart is not None:
        try:
            on_before_restart()
        except Exception:
            pass
    os._exit(0)


def _safe_extract_tarball(tar_path: str, dest_dir: str) -> str:
    """Safely extract GitHub tarball to dest_dir, preventing path traversal, returning root folder."""
    abs_dest = os.path.abspath(dest_dir)
    root_name = ""
    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            if not root_name and "/" in member.name:
                root_name = member.name.split("/", 1)[0]
            target = os.path.abspath(os.path.join(abs_dest, member.name))
            if target != abs_dest and not target.startswith(abs_dest + os.sep):
                raise UpdateError(f"Unsafe tarball member path detected: {member.name}")
            if member.issym() or member.islnk():
                link_target = os.path.abspath(os.path.join(os.path.dirname(target), member.linkname))
                if link_target != abs_dest and not link_target.startswith(abs_dest + os.sep):
                    raise UpdateError(f"Unsafe tarball symlink target detected: {member.name}")
        tf.extractall(abs_dest)
    extracted_root = os.path.join(abs_dest, root_name) if root_name else abs_dest
    if not os.path.isdir(extracted_root):
        raise UpdateError("Extracted update archive root directory not found")
    return extracted_root


def _sync_extracted_tree(src_root: str, dst_root: str) -> None:
    """Copy updated project files from src_root into dst_root while preserving local runtime state."""
    for entry in os.listdir(src_root):
        if entry in _PRESERVED_USER_ITEMS:
            continue
        src_path = os.path.join(src_root, entry)
        dst_path = os.path.join(dst_root, entry)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        else:
            shutil.copy2(src_path, dst_path)


def _apply_linux_update(
    info: Dict[str, Any],
    on_before_restart: Optional[Callable[[], None]] = None,
) -> None:
    target_build = str(info.get("latest_build") or "")
    has_git = os.path.isdir(os.path.join(PROJECT_DIR, ".git")) and bool(shutil.which("git"))

    if has_git:
        _set_state(status="downloading", percent=15, message="Checking repository cleanliness...")
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if dirty.returncode == 0 and dirty.stdout.strip():
            raise UpdateError(
                "Tracked local modifications detected in git repository. Commit or stash changes before auto-updating."
            )

        if _cancel_event.is_set():
            raise UpdateCancelledError("Update cancelled by user")

        _set_state(status="downloading", percent=35, message=f"Fetching Build {target_build} from GitHub...")
        fetch = subprocess.run(
            ["git", "fetch", PUBLIC_GIT_URL, "main"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if fetch.returncode != 0:
            raise UpdateError(f"git fetch failed: {(fetch.stderr or fetch.stdout).strip()}")

        if _cancel_event.is_set():
            raise UpdateCancelledError("Update cancelled by user")

        _set_state(status="applying", percent=75, message="Applying fast-forward update...")
        merge = subprocess.run(
            ["git", "merge", "--ff-only", "FETCH_HEAD"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if merge.returncode != 0:
            raise UpdateError(f"git merge --ff-only failed: {(merge.stderr or merge.stdout).strip()}")
    else:
        stage_dir = tempfile.mkdtemp(prefix="spectra_upd_")
        tar_path = os.path.join(stage_dir, "spectra_main.tar.gz")
        extract_dir = os.path.join(stage_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            _set_state(
                status="downloading",
                percent=10,
                message=f"Downloading Build {target_build} source package...",
            )
            _download_file_with_progress(str(info.get("download_url") or RAW_LINUX_TARBALL_URL), tar_path, timeout=45.0)
            if _cancel_event.is_set():
                raise UpdateCancelledError("Update cancelled by user")
            _set_state(status="verifying", percent=82, message="Extracting and verifying archive...")
            src_root = _safe_extract_tarball(tar_path, extract_dir)
            _set_state(status="applying", percent=92, message="Updating installed SPECTRA files...")
            _sync_extracted_tree(src_root, PROJECT_DIR)
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

    _set_state(
        status="restarting",
        percent=100,
        restart_required=True,
        message=f"Updated to Build {target_build}. Restarting SPECTRA...",
    )
    time.sleep(0.55)
    if on_before_restart is not None:
        try:
            on_before_restart()
        except Exception:
            pass
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _run_self_update(on_before_restart: Optional[Callable[[], None]], check_info: Optional[Dict[str, Any]]) -> None:
    try:
        current_build = get_local_build()
        _set_state(
            status="checking",
            percent=2,
            bytes_downloaded=0,
            total_bytes=0,
            error="",
            current_build=current_build,
            target_build=(check_info or {}).get("latest_build", ""),
            message="Verifying latest release metadata...",
            in_progress=True,
            restart_required=False,
            started_at=time.time(),
            finished_at=0.0,
        )

        info = (
            check_info
            if (check_info and check_info.get("ok") and check_info.get("latest_build"))
            else check_for_updates(force=True, timeout=8.0)
        )

        if _cancel_event.is_set():
            raise UpdateCancelledError("Update cancelled by user")

        if not info.get("ok"):
            raise UpdateError(str(info.get("error") or "Failed to query remote update metadata"))

        if not info.get("update_available"):
            _set_state(
                status="up_to_date",
                percent=100,
                in_progress=False,
                target_build=str(info.get("latest_build") or current_build),
                message=f"Already running latest Build {current_build}",
                finished_at=time.time(),
            )
            return

        if _current_platform() == "windows":
            _apply_windows_update(info, on_before_restart=on_before_restart)
        else:
            _apply_linux_update(info, on_before_restart=on_before_restart)

    except UpdateCancelledError:
        _set_state(
            status="cancelled",
            in_progress=False,
            message="Update cancelled.",
            error="",
            finished_at=time.time(),
        )
    except Exception as exc:
        _set_state(
            status="error",
            in_progress=False,
            restart_required=False,
            error=str(exc),
            message=f"Update failed: {exc}",
            finished_at=time.time(),
        )


def start_self_update(
    on_before_restart: Optional[Callable[[], None]] = None,
    check_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Start a background self-update job if none is currently running.
    Returns immediate job acknowledgment plus current progress state.
    """
    global _update_thread

    with _state_lock:
        if _update_state.get("in_progress") and _update_thread is not None and _update_thread.is_alive():
            return {"ok": False, "error": "An update is already in progress", "state": dict(_update_state)}
        _cancel_event.clear()
        _update_state.update(
            {
                "status": "checking",
                "percent": 1,
                "bytes_downloaded": 0,
                "total_bytes": 0,
                "error": "",
                "current_build": get_local_build(),
                "target_build": str((check_info or {}).get("latest_build") or ""),
                "message": "Starting self-update...",
                "in_progress": True,
                "restart_required": False,
                "started_at": time.time(),
                "finished_at": 0.0,
            }
        )

    _update_thread = threading.Thread(
        target=_run_self_update,
        args=(on_before_restart, check_info),
        daemon=False,
        name="spectra-self-updater",
    )
    _update_thread.start()
    return {"ok": True, "state": get_update_progress()}


def cancel_self_update() -> Dict[str, Any]:
    """Signal an active download/verification step to abort gracefully."""
    snap = get_update_progress()
    if not snap.get("in_progress"):
        return {"ok": False, "error": "No update currently in progress", "state": snap}
    if snap.get("status") in ("applying", "restarting"):
        return {"ok": False, "error": "Update is already applying and cannot be cancelled", "state": snap}
    _cancel_event.set()
    _set_state(message="Cancelling update...")
    return {"ok": True, "state": get_update_progress()}
