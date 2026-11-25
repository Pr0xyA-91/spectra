#!/usr/bin/env python3
"""SPECTRA Web Server security guards, path confinement, filename sanitization, and debug logging."""

import os
import sys
import re
import time
import threading
import unicodedata
from typing import Dict, Any, Optional, Tuple, List

import serial_io
import profiles_db
import updater
from version import __version__, __build__, __edition__

from spectra_web import state as _wstate
from spectra_web.state import (
    PROJECT_DIR,
    HAS_RUST_CORE,
    _session_lock,
    _debug_log_buffer,
    _debug_log_lock,
    _hmi_paths_lock,
    _approved_hmi_paths,
)

_DEBUG_SECRET_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]{10,}|"
    r"(?:Authorization\s*:\s*(?:Bearer|token)\s+)[^\s\"',}]+|"
    r"(?:access_token[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+|"
    r"(?:SPECTRA_GITHUB_TOKEN=)[^\s\"']+)",
    re.IGNORECASE,
)



def _redact_debug_text(text: str) -> str:
    if not text:
        return ""
    cleaned = _DEBUG_SECRET_RE.sub("[REDACTED]", str(text))
    try:
        import github_auth
        cleaned = github_auth.sanitize_issue_text(cleaned)
    except Exception:
        pass
    return cleaned


def _get_allowed_hmi_roots() -> List[str]:
    roots: List[str] = []
    for raw in ("~/Downloads", "~/Desktop", "~/Documents"):
        try:
            roots.append(os.path.realpath(os.path.expanduser(raw)))
        except Exception:
            pass
    extra = (os.environ.get("SPECTRA_HMI_ALLOWED_ROOTS") or "").strip()
    if extra:
        for part in extra.split(os.pathsep):
            p = part.strip()
            if p:
                try:
                    roots.append(os.path.realpath(os.path.expanduser(p)))
                except Exception:
                    pass
    return roots


_MAX_APPROVED_HMI_PATHS = 64


def _approve_hmi_path(selected_path: str) -> None:
    if not selected_path:
        return
    try:
        resolved = os.path.realpath(os.path.expanduser(str(selected_path)))
        if not resolved or resolved in ("/", os.path.sep):
            return
        with _hmi_paths_lock:
            if resolved in _approved_hmi_paths:
                return
            if len(_approved_hmi_paths) >= _MAX_APPROVED_HMI_PATHS:
                _approved_hmi_paths.pop()
            _approved_hmi_paths.add(resolved)
    except Exception:
        pass


def _is_allowed_hmi_path(candidate: Optional[str]) -> Tuple[bool, str]:
    if not candidate or not str(candidate).strip():
        default_dir = os.path.realpath(os.path.expanduser("~/Downloads"))
        return True, default_dir
    try:
        resolved = os.path.realpath(os.path.expanduser(str(candidate).strip()))
    except Exception:
        return False, ""
    if not resolved:
        return False, ""

    allowed_bases = _get_allowed_hmi_roots()
    with _hmi_paths_lock:
        allowed_bases.extend(_approved_hmi_paths)

    for base in allowed_bases:
        if not base:
            continue
        try:
            if os.path.commonpath([base, resolved]) == base:
                return True, resolved
        except ValueError:
            continue
    return False, resolved



def log_debug_event(level: str, source: str, message: str, details: str = "") -> Dict[str, Any]:
    """
    Logs an event into the thread-safe bounded ring-buffer (strictly capped at maxlen=500),
    redacting any accidental tokens or credentials before storage.
    """
    safe_msg = _redact_debug_text(str(message))
    safe_det = _redact_debug_text(str(details)) if details else ""
    with _debug_log_lock:
        _wstate._debug_log_seq += 1
        now = time.time()
        msec = int((now - int(now)) * 1000)
        timestamp = time.strftime("%H:%M:%S", time.localtime(now)) + f".{msec:03d}"
        entry = {
            "id": _wstate._debug_log_seq,
            "timestamp": timestamp,
            "level": str(level).upper(),
            "source": str(source).upper(),
            "message": safe_msg,
            "details": safe_det,
        }
        _debug_log_buffer.append(entry)
        return entry


class TeeStream:
    """Safely mirrors stdout/stderr writes to the bounded ring-buffer logger."""
    def __init__(self, original_stream, source_name: str):
        self.original = original_stream
        self.source = source_name
        self._line_buf = ""
        self._lock = threading.Lock()
        self._in_write = False

    def write(self, s: str):
        try:
            self.original.write(s)
        except Exception:
            pass

        if not s or self._in_write:
            return

        with self._lock:
            self._line_buf += s
            if "\n" in self._line_buf:
                lines = self._line_buf.split("\n")
                self._line_buf = lines[-1]
                for line in lines[:-1]:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    lvl = "INFO"
                    low = stripped.lower()
                    if "error" in low or "exception" in low or "traceback" in low:
                        lvl = "ERROR"
                    elif "[!]" in stripped or "warn" in low:
                        lvl = "WARN"

                    self._in_write = True
                    try:
                        log_debug_event(lvl, self.source, stripped)
                    finally:
                        self._in_write = False

    def flush(self):
        try:
            self.original.flush()
        except Exception:
            pass

    def isatty(self):
        return getattr(self.original, "isatty", lambda: False)()

    def fileno(self):
        return self.original.fileno()


def install_tee_streams():
    """Installs TeeStream only when not running under unit tests to prevent capture collisions."""
    if any("test" in arg or "unittest" in arg or "pytest" in arg for arg in sys.argv):
        return
    if "unittest" in sys.modules:
        return
    if sys.stdout is None:
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            pass
    if sys.stderr is None:
        try:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            pass
    if not isinstance(sys.stdout, TeeStream):
        sys.stdout = TeeStream(sys.stdout, "STDOUT")
    if not isinstance(sys.stderr, TeeStream):
        sys.stderr = TeeStream(sys.stderr, "STDERR")


_DIAG_CACHE_LOCK = threading.Lock()
_DIAG_CACHE_TTL_SEC = 5.0
_DIAG_AI_CACHE: Optional[Dict[str, Any]] = None
_DIAG_CHILDREN_CACHE: Optional[List[Dict[str, Any]]] = None
_DIAG_CACHE_TS: float = 0.0


def get_debug_diagnostics() -> Dict[str, Any]:

    # 1. Core Process Diagnostics
    pid = os.getpid()
    uptime_sec = round(time.time() - _wstate._server_start_time, 1)

    rss_mb = 0.0
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            rss_mb = round(float(parts[1]) / 1024.0, 2)
                        break
        except Exception:
            pass
    elif sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                rss_mb = round(counters.WorkingSetSize / (1024 * 1024), 2)
        except Exception:
            rss_mb = 0.0

    if rss_mb == 0.0:
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            mult = 1.0 / (1024 * 1024) if sys.platform == "darwin" else 1.0 / 1024
            rss_mb = round(usage.ru_maxrss * mult, 2)
        except Exception:
            pass

    # 2. Active Threads List
    threads_list = []
    for t in threading.enumerate():
        threads_list.append({
            "name": t.name,
            "ident": t.ident,
            "daemon": bool(t.daemon),
            "alive": bool(t.is_alive()),
        })

    # 3. Hardware Serial Session
    is_serial_active = False
    driver_name = "None"
    serial_busy = False
    if _session_lock.acquire(timeout=0.05):
        try:
            if _wstate._active_session is not None:
                conn = getattr(_wstate._active_session, "conn", None)
                if conn is not None and getattr(conn, "is_open", False):
                    is_serial_active = True
                prof = getattr(_wstate._active_session, "profile", {})
                driver_name = prof.get("name", "Auto/Jura") if isinstance(prof, dict) else str(prof)
        finally:
            _session_lock.release()
    else:
        serial_busy = True
        is_serial_active = True
        driver_name = "Busy (Hardware I/O)"

    serial_status = {
        "status": "BUSY" if serial_busy else ("ACTIVE" if is_serial_active else "IDLE"),
        "port": _wstate._current_port or "Disconnected",
        "driver": driver_name,
        "error_state": bool(_wstate._consecutive_sensor_errors > 0),
        "consecutive_errors": _wstate._consecutive_sensor_errors,
    }

    # 4. Embedded Ollama AI Engine + 5. OS Child Processes (cached for 5.0s)
    global _DIAG_AI_CACHE, _DIAG_CHILDREN_CACHE, _DIAG_CACHE_TS
    now_mono = time.monotonic()
    with _DIAG_CACHE_LOCK:
        cache_valid = (
            _DIAG_AI_CACHE is not None
            and _DIAG_CHILDREN_CACHE is not None
            and (now_mono - _DIAG_CACHE_TS) < _DIAG_CACHE_TTL_SEC
        )
        if cache_valid:
            ai_status = dict(_DIAG_AI_CACHE)
            child_processes = [dict(c) for c in _DIAG_CHILDREN_CACHE]

    if not cache_valid:
        ai_status = {
            "running": False,
            "managed_by_spectra": False,
            "pid": None,
            "loaded_models": [],
            "endpoint": "http://127.0.0.1:11434",
        }
        try:
            import hmi_inspector
            raw_ai = hmi_inspector.KalermHmiInspector.get_ai_system_status()
            ai_status["running"] = bool(raw_ai.get("running"))
            ai_status["managed_by_spectra"] = bool(raw_ai.get("managed_by_spectra"))
            ai_status["pid"] = raw_ai.get("pid")
            ai_status["loaded_models"] = raw_ai.get("installed_models", [])
            if raw_ai.get("active_model"):
                ai_status["active_model"] = raw_ai.get("active_model")
        except Exception:
            pass

        child_processes = []
        if sys.platform.startswith("linux") and os.path.isdir("/proc"):
            my_pid = os.getpid()
            for entry in os.listdir("/proc"):
                if entry.isdigit():
                    c_pid = int(entry)
                    try:
                        with open(f"/proc/{c_pid}/stat", "r") as f:
                            parts = f.read().split()
                            if len(parts) > 3 and int(parts[3]) == my_pid:
                                state = parts[2]
                                cmdline = ""
                                try:
                                    with open(f"/proc/{c_pid}/cmdline", "rb") as cf:
                                        cmdline = cf.read().replace(b"\x00", b" ").decode("utf-8", "ignore").strip()
                                except Exception:
                                    pass
                                child_processes.append({
                                    "pid": c_pid,
                                    "state": state,
                                    "cmdline": _redact_debug_text(cmdline or parts[1].strip("()")),
                                })
                    except Exception:
                        continue
        elif ai_status.get("managed_by_spectra") and ai_status.get("pid"):
            child_processes.append({
                "pid": ai_status["pid"],
                "state": "RUNNING",
                "cmdline": "ollama serve"
            })

        with _DIAG_CACHE_LOCK:
            _DIAG_AI_CACHE = dict(ai_status)
            _DIAG_CHILDREN_CACHE = [dict(c) for c in child_processes]
            _DIAG_CACHE_TS = time.monotonic()

    offset_db_info: Dict[str, Any] = {
        "offset_db_version": f"bundled-{__build__}",
        "source": "bundled_factory",
        "verified": True,
        "key_id": "bundled",
        "synced_machines_count": 0,
        "bundled_specs_count": 0,
        "trusted_keys_configured": False,
    }
    try:
        import offset_db_sync
        offset_db_info = offset_db_sync.get_offset_db_status()
    except Exception:
        pass

    return {
        "process": {
            "pid": pid,
            "uptime_sec": uptime_sec,
            "rss_mb": rss_mb,
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "rust_core_active": bool(HAS_RUST_CORE),
            "offset_db_version": str(offset_db_info.get("offset_db_version") or f"bundled-{__build__}"),
            "offset_db_source": str(offset_db_info.get("source") or "bundled_factory"),
        },
        "offset_db": offset_db_info,
        "threads": threads_list,
        "serial": serial_status,
        "ollama": ai_status,
        "children": child_processes,
        "http_daemon": {
            "status": "RUNNING",
            "bind": f"127.0.0.1:{_wstate._current_http_port}",
        },
    }


_WIN_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


def sanitize_filename_prefix(raw: Any, max_len: int = 48) -> str:
    """
    Sanitize a user-supplied ticket number or filename prefix for cross-platform safety.
    Transliterates diacritics to ASCII, strips path separators / illegal chars, and blocks reserved names.
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Normalize Unicode diacritics (e.g. Czech 'Zakázka' -> 'Zakazka') for safe HTTP headers & Win32/POSIX paths
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Strip traversal / path separators and replace non-safe characters with underscores
    normalized = normalized.replace("..", "_").replace("/", "_").replace("\\", "_")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized)
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    cleaned = cleaned.strip("._-")
    if not cleaned:
        return ""
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("._-")
    if cleaned.upper() in _WIN_RESERVED_NAMES:
        cleaned = f"tkt_{cleaned}"
    return cleaned


def build_export_filename(kind: str, model_name: Any, timestamp: str, ext: str, prefix: Any = "") -> str:
    """Compose a sanitized export filename with an optional ticket number / custom prefix."""
    safe_model = re.sub(r"[^\w\-_]", "_", str(model_name or "appliance")).strip("_") or "appliance"
    safe_kind = re.sub(r"[^A-Za-z0-9_-]", "", str(kind or "export")) or "export"
    safe_ext = re.sub(r"[^A-Za-z0-9]", "", str(ext or "json")) or "json"
    clean_prefix = sanitize_filename_prefix(prefix)
    base = f"spectra_{safe_kind}_{safe_model}_{timestamp}.{safe_ext}"
    return f"{clean_prefix}_{base}" if clean_prefix else base



def is_valid_port(port: str) -> bool:
    if not port or not isinstance(port, str):
        return False
    p = port.strip()
    if not p or len(p) > 256:
        return False
    if p.startswith("/dev/tty") or p.startswith("/dev/pts/") or p.startswith("/dev/serial/"):
        return not any(ch in p for ch in [";", "&", "|", "`", "$", "..", "\x00", "\n", "\r"])
    if re.fullmatch(r"(?:\\\\\.\\)?COM\d{1,3}(?:\s+\([^;\r\n\x00`|$<>&]{1,200}\))?", p, re.IGNORECASE) and ".." not in p:
        return True
    if "DEMO" in p.upper() or p.lower() in ("mock", "demo"):
        return True
    return False

