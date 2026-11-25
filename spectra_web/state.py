#!/usr/bin/env python3
"""SPECTRA Web Server shared runtime state, locks, lifecycle helpers, and HTTPServer subclass."""

import os
import sys
import time
import socket
import threading
import collections
from contextlib import contextmanager
from http.server import HTTPServer, ThreadingHTTPServer
from typing import Dict, Any, Optional, List, Set

import stats_collector as sc
import memory_mapper
from version import __version__, __build__, __edition__

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Native Rust Core Acceleration Bridge (spectra_py)
try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False

def _ensure_serial_group():
    """Auto-adopt uucp / dialout group on Linux if member in /etc/group but current session lacks it."""
    if not sys.platform.startswith("linux"):
        return
    import glob
    import shlex
    serial_devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    needs_group = any(not os.access(dev, os.R_OK | os.W_OK) for dev in serial_devs)
    if needs_group:
        try:
            import grp
            user = os.environ.get("USER", "")
            for gname in ("uucp", "dialout"):
                try:
                    g_entry = grp.getgrnam(gname)
                    if user and user in g_entry.gr_mem:
                        args = " ".join(shlex.quote(a) for a in sys.argv)
                        cmd = f"exec {shlex.quote(sys.executable)} {args}"
                        os.execlp("newgrp", "newgrp", gname, "-c", cmd)
                except KeyError:
                    pass
        except Exception:
            pass


# Global Session State
_session_lock = threading.Lock()
_active_session: Optional[sc.JuraStatsSession] = None
_current_port: str = ""
_last_stats_cache: Optional[Dict[str, Any]] = None
_mapper_engine: Optional[memory_mapper.MemoryMapperEngine] = None
_consecutive_sensor_errors: int = 0
_last_sensor_payload: Optional[Dict[str, Any]] = None
_last_heartbeat_time: float = time.time()
_hw_op_lock = threading.Lock()
_active_hw_ops: int = 0
_is_native_webview: bool = False
_shutdown_callbacks: List[Any] = []
_active_httpd: Optional[HTTPServer] = None
_capture_cache_lock = threading.Lock()
_cached_captures: Dict[str, Dict[str, Any]] = {}
_written_capture_paths: collections.deque = collections.deque(maxlen=200)
_CONNECTION_SEMAPHORE = threading.BoundedSemaphore(64)


def touch_heartbeat():
    """Refresh the frontend/operation liveness timestamp."""
    global _last_heartbeat_time
    _last_heartbeat_time = time.time()


@contextmanager
def long_hardware_operation():
    """Marks an active blocking hardware/EEPROM operation so watchdogs never false-trigger."""
    global _active_hw_ops
    with _hw_op_lock:
        _active_hw_ops += 1
    touch_heartbeat()
    try:
        yield
    finally:
        touch_heartbeat()
        with _hw_op_lock:
            _active_hw_ops = max(0, _active_hw_ops - 1)


def cleanup_resources():
    """
    Safely tears down active serial hardware sessions, stops local managed Ollama processes,
    and releases system resources.
    """
    global _active_session, _mapper_engine, _current_port
    with _session_lock:
        if _active_session is not None:
            try:
                _active_session.close()
            except Exception:
                pass
            _active_session = None
        _mapper_engine = None
        _current_port = ""

    try:
        import hmi_inspector
        hmi_inspector.KalermHmiInspector.control_local_ollama("stop")
    except Exception:
        pass


def register_shutdown_callback(cb):
    """Register a callable to be executed when app mode shuts down."""
    if cb not in _shutdown_callbacks:
        _shutdown_callbacks.append(cb)


def shutdown_for_restart():
    """Release serial/Ollama resources, shutdown UI windows, and close HTTP socket before self-update restart."""
    if _current_http_port and _current_http_port > 0:
        os.environ["SPECTRA_PREFERRED_PORT"] = str(_current_http_port)
    cleanup_resources()
    for cb in list(_shutdown_callbacks):
        try:
            cb()
        except Exception:
            pass
    if _active_httpd is not None:
        try:
            _active_httpd.shutdown()
        except Exception:
            pass
        try:
            _active_httpd.server_close()
        except Exception:
            pass


# ============================================================================
# Debug Console & Process Monitor Ring-Buffer Telemetry
# ============================================================================
_server_start_time: float = time.time()
_SERVER_BOOT_ID: str = f"{os.getpid()}-{int(_server_start_time * 1000)}"
_debug_log_buffer: collections.deque = collections.deque(maxlen=500)
_debug_log_lock = threading.Lock()
_debug_log_seq: int = 0
_current_http_port: int = 8080

# Session-approved HMI inspection paths (populated by interactive /api/hmi/browse)
_hmi_paths_lock = threading.Lock()
_approved_hmi_paths: Set[str] = set()


def _get_sidecar_nonce() -> str:
    return (os.environ.get("SPECTRA_SIDECAR_NONCE") or "").strip()



class SpectraThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = (os.name != "nt")
    daemon_threads = True

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        super().server_bind()



def get_dist_dir() -> str:
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "web", "dist")
        if os.path.exists(bundled):
            return bundled
    if getattr(sys, "frozen", False):
        adjacent = os.path.join(os.path.dirname(sys.executable), "web", "dist")
        if os.path.exists(adjacent):
            return adjacent
    return os.path.join(PROJECT_DIR, "web", "dist")

DIST_DIR = get_dist_dir()
CUSTOM_SENSOR_MAPPINGS_FILE = os.path.join(PROJECT_DIR, "docs", "models", "custom_sensor_mappings.json")
