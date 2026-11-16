#!/usr/bin/env python3
"""
SPECTRA — Next-Gen Hardware Telemetry & Logic Board Diagnostics — Web Server
Provides REST APIs for real physical serial adapters (/dev/ttyUSB*, COM*) and simulated mock devices.
Serves the multi-paradigm reactive interface at http://127.0.0.1:8080.
"""

import os
import sys
import re
import time
import json
import socket
import threading
import mimetypes
import collections
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import uuid
from typing import Dict, Any, Optional, Tuple, List, Set

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

# Ensure local modules are importable
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import serial_io
import stats_collector as sc
import gui_widgets
import memory_mapper
import copy
import spectra_probe
from version import __version__, __build__, __edition__

# Native Rust Core Acceleration Bridge (spectra_py)
try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False

# Global Session State
_session_lock = threading.Lock()
_active_session: Optional[sc.JuraStatsSession] = None
_current_port: str = ""
_last_stats_cache: Optional[Dict[str, Any]] = None
_mapper_engine: Optional[memory_mapper.MemoryMapperEngine] = None
_consecutive_sensor_errors: int = 0
_last_sensor_payload: Optional[Dict[str, Any]] = None
_last_heartbeat_time: float = time.time()
_is_native_webview: bool = False
_shutdown_callbacks: List[Any] = []
_capture_cache_lock = threading.Lock()
_cached_captures: Dict[str, Dict[str, Any]] = {}
_written_capture_paths: Set[str] = set()


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


# ============================================================================
# Debug Console & Process Monitor Ring-Buffer Telemetry
# ============================================================================
_server_start_time: float = time.time()
_debug_log_buffer: collections.deque = collections.deque(maxlen=500)
_debug_log_lock = threading.Lock()
_debug_log_seq: int = 0
_current_http_port: int = 8080


def log_debug_event(level: str, source: str, message: str, details: str = "") -> Dict[str, Any]:
    """
    Logs an event into the thread-safe bounded ring-buffer (strictly capped at maxlen=500).
    """
    global _debug_log_seq
    with _debug_log_lock:
        _debug_log_seq += 1
        now = time.time()
        msec = int((now - int(now)) * 1000)
        timestamp = time.strftime("%H:%M:%S", time.localtime(now)) + f".{msec:03d}"
        entry = {
            "id": _debug_log_seq,
            "timestamp": timestamp,
            "level": str(level).upper(),
            "source": str(source).upper(),
            "message": str(message),
            "details": str(details) if details else "",
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


def get_debug_diagnostics() -> Dict[str, Any]:
    global _active_session, _current_port, _consecutive_sensor_errors, _server_start_time, _current_http_port

    # 1. Core Process Diagnostics
    pid = os.getpid()
    uptime_sec = round(time.time() - _server_start_time, 1)

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
    with _session_lock:
        if _active_session is not None:
            conn = getattr(_active_session, "conn", None)
            if conn is not None and getattr(conn, "is_open", False):
                is_serial_active = True
            prof = getattr(_active_session, "profile", {})
            driver_name = prof.get("name", "Auto/Jura") if isinstance(prof, dict) else str(prof)

    serial_status = {
        "status": "ACTIVE" if is_serial_active else "IDLE",
        "port": _current_port or "Disconnected",
        "driver": driver_name,
        "error_state": bool(_consecutive_sensor_errors > 0),
        "consecutive_errors": _consecutive_sensor_errors,
    }

    # 4. Embedded Ollama AI Engine
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

    # 5. OS Child Processes
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
                                "cmdline": cmdline or parts[1].strip("()")
                            })
                except Exception:
                    continue
    elif ai_status.get("managed_by_spectra") and ai_status.get("pid"):
        child_processes.append({
            "pid": ai_status["pid"],
            "state": "RUNNING",
            "cmdline": "ollama serve"
        })

    return {
        "process": {
            "pid": pid,
            "uptime_sec": uptime_sec,
            "rss_mb": rss_mb,
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "rust_core_active": bool(HAS_RUST_CORE),
        },
        "threads": threads_list,
        "serial": serial_status,
        "ollama": ai_status,
        "children": child_processes,
        "http_daemon": {
            "status": "RUNNING",
            "bind": f"127.0.0.1:{_current_http_port}",
        },
    }

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

# ============================================================================
# Developer Raw Sensor Catalog & Value Mapping Infrastructure [DEV ONLY]
# ============================================================================

DEFAULT_SENSOR_MAPPINGS: Dict[str, Dict[str, Any]] = {
    "HZ_0": {
        "frame": "HZ",
        "index": 0,
        "name": "Operating & Safety Bitfield",
        "category": "Status",
        "unit": "flags",
        "scale": 1.0,
        "desc": "12-nibble operational status: BU init, MV busy, Heater ready, MV init"
    },
    "HZ_1": {
        "frame": "HZ",
        "index": 1,
        "name": "BU Upper Limit Encoder Target",
        "category": "Brew Unit",
        "unit": "ticks",
        "scale": 1.0,
        "desc": "Mechanical top travel limit reference ticks (e.g. 0x0289 = 649)"
    },
    "HZ_2": {
        "frame": "HZ",
        "index": 2,
        "name": "BU Current Position Encoder",
        "category": "Brew Unit",
        "unit": "ticks",
        "scale": 1.0,
        "desc": "Real-time optical quadrature encoder ticks from home switch"
    },
    "HZ_3": {
        "frame": "HZ",
        "index": 3,
        "name": "Flowmeter Impulses",
        "category": "Hydraulics",
        "unit": "pulses",
        "scale": 1.0,
        "desc": "Turbine flow pulses in current cycle (~2.366 pulses / ml)"
    },
    "HZ_4": {
        "frame": "HZ",
        "index": 4,
        "name": "Coffee Thermoblock NTC",
        "category": "Thermal",
        "unit": "°C",
        "scale": 0.1,
        "desc": "Coffee Thermoblock temperature (0.1 °C resolution, e.g. 0x03CA = 970 = 97.0°C)"
    },
    "HZ_5": {
        "frame": "HZ",
        "index": 5,
        "name": "Steam Thermoblock NTC",
        "category": "Thermal",
        "unit": "°C",
        "scale": 0.1,
        "desc": "Steam Thermoblock temperature (0.1 °C resolution, if equipped)"
    },
    "HZ_6": {
        "frame": "HZ",
        "index": 6,
        "name": "Rotary Dial Knob",
        "category": "User Interface",
        "unit": "pos",
        "scale": 1.0,
        "desc": "Rotary switch knob selected position index"
    },
    "HZ_7": {
        "frame": "HZ",
        "index": 7,
        "name": "Auxiliary & Microswitch Cuts",
        "category": "Sensors",
        "unit": "bitfield",
        "scale": 1.0,
        "desc": "Chassis microswitches: Drip tray cut, water float cut, zero crossing"
    },
    "HZ_8": {
        "frame": "HZ",
        "index": 8,
        "name": "Front Panel Matrix / Puck Cake",
        "category": "Sensors",
        "unit": "ticks",
        "scale": 1.0,
        "desc": "Key matrix and ground coffee puck cake thickness measurement"
    },
    "HZ_9": {
        "frame": "HZ",
        "index": 9,
        "name": "Spout Dispenser Microswitches",
        "category": "Chassis",
        "unit": "bitfield",
        "scale": 1.0,
        "desc": "Height-adjustable coffee dispenser and drain switch states"
    },
    "AS_0": {
        "frame": "AS",
        "index": 0,
        "name": "Ambient IR Photodiode ADC",
        "category": "Optical Hopper",
        "unit": "counts",
        "scale": 1.0,
        "desc": "Ambient background IR photodiode ADC measurement"
    },
    "AS_1": {
        "frame": "AS",
        "index": 1,
        "name": "Reflected Beam IR Photodiode ADC",
        "category": "Optical Hopper",
        "unit": "counts",
        "scale": 1.0,
        "desc": "Reflected beam IR photodiode ADC measurement"
    },
    "AS_DELTA": {
        "frame": "AS",
        "index": 2,
        "name": "Optical Hopper Differential Delta",
        "category": "Optical Hopper",
        "unit": "counts",
        "scale": 1.0,
        "desc": "Delta between reflected and ambient IR (Threshold: 115 ± 5)"
    },
    "RE_0028": {
        "frame": "RE:0028",
        "index": 0,
        "name": "Hardware Fault Latch Register",
        "category": "Safety",
        "unit": "bitmask",
        "scale": 1.0,
        "desc": "16-bit non-volatile hardware safety lockout latch"
    },
    "CS_0": {
        "frame": "CS",
        "index": 0,
        "name": "Component Triac & Actuator State",
        "category": "Actuators",
        "unit": "bitmask",
        "scale": 1.0,
        "desc": "Triacs, pump, heating elements, and ceramic valve states"
    },
    "IC_0": {
        "frame": "IC",
        "index": 0,
        "name": "MCU Input Bus Line State",
        "category": "Hardware",
        "unit": "bitmask",
        "scale": 1.0,
        "desc": "Microcontroller digital input line status"
    }
}


def load_custom_sensor_mappings() -> Dict[str, Any]:
    mappings = copy.deepcopy(DEFAULT_SENSOR_MAPPINGS)
    if os.path.exists(CUSTOM_SENSOR_MAPPINGS_FILE):
        try:
            with open(CUSTOM_SENSOR_MAPPINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                mappings.update(saved)
        except Exception:
            pass
    return mappings


def save_custom_sensor_mapping(field_key: str, data: Dict[str, Any]) -> bool:
    mappings = load_custom_sensor_mappings()
    if field_key not in mappings:
        mappings[field_key] = {}
    mappings[field_key].update(data)
    try:
        os.makedirs(os.path.dirname(CUSTOM_SENSOR_MAPPINGS_FILE), exist_ok=True)
        tmp = CUSTOM_SENSOR_MAPPINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)
        os.replace(tmp, CUSTOM_SENSOR_MAPPINGS_FILE)
        return True
    except Exception:
        return False


def reset_custom_sensor_mappings() -> bool:
    if os.path.exists(CUSTOM_SENSOR_MAPPINGS_FILE):
        try:
            os.remove(CUSTOM_SENSOR_MAPPINGS_FILE)
            return True
        except Exception:
            return False
    return True


def serialize_register_entry(r: memory_mapper.RegisterEntry) -> Dict[str, Any]:
    return {
        "addr": r.addr,
        "hex_addr": r.hex_addr,
        "val": r.val,
        "val_hex": f"0x{r.val:04X}",
        "val_dec": r.val,
        "status": r.status,
        "name": r.name,
        "desc": r.desc,
        "category": r.category,
        "unit": r.unit,
        "baseline_val": r.baseline_val,
        "baseline_hex": f"0x{r.baseline_val:04X}",
        "delta": r.delta,
        "is_changed": r.is_changed,
        "bits_flipped": r.bits_flipped,
        "high_byte": r.high_byte,
        "low_byte": r.low_byte,
        "signed_val": r.signed_val,
        "ascii_repr": r.ascii_repr,
    }


def _get_or_create_mapper(port: str) -> Tuple[Optional[memory_mapper.MemoryMapperEngine], Optional[str]]:
    global _active_session, _current_port, _mapper_engine
    if not port or not is_valid_port(port):
        return None, "Invalid or missing serial port"

    if _active_session is None or _current_port != port:
        if _active_session is not None:
            try:
                _active_session.close()
            except Exception:
                pass
        _active_session = sc.JuraStatsSession(port_name=port)
        _current_port = port
        _mapper_engine = None

    if _active_session.conn is not None and not _active_session.conn.is_open:
        try:
            _active_session.conn.close()
        except Exception:
            pass
        _active_session.conn = None
        _mapper_engine = None

    if _active_session.conn is None or not _active_session.conn.is_open:
        _active_session.conn = serial_io.JuraSerialConnection(port)
        _mapper_engine = None

    if _mapper_engine is None or _mapper_engine.conn != _active_session.conn:
        _mapper_engine = memory_mapper.MemoryMapperEngine(_active_session.conn)

    return _mapper_engine, None


def _decode_raw_sensors(mapper: memory_mapper.MemoryMapperEngine) -> Dict[str, Any]:
    # Query raw frames safely
    hz_raw = mapper.query_safe("HZ:", timeout=1.2) or ""
    as_raw = mapper.query_safe("AS:", timeout=1.2) or ""
    cs_raw = mapper.query_safe("CS:", timeout=1.2) or ""
    ic_raw = mapper.query_safe("IC:", timeout=1.2) or ""
    r28_raw = mapper.query_safe("RE:0028", timeout=1.2) or ""

    custom_mappings = load_custom_sensor_mappings()
    fields = []

    # 1. HZ: Frame parsing
    hz_clean = hz_raw.strip()
    if hz_clean.lower().startswith("hz:"):
        hz_clean = hz_clean[3:].strip()
    hz_parts = hz_clean.split(",") if hz_clean else []

    for idx, part in enumerate(hz_parts):
        key = f"HZ_{idx}"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        name = cfg.get("name", f"HZ Field {idx}")
        category = cfg.get("category", "General")
        unit = cfg.get("unit", "")
        scale = float(cfg.get("scale", 1.0))
        desc = cfg.get("desc", f"Volatile HZ operational parameter {idx}")
        is_custom = key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)

        raw_hex = part.strip()
        val_dec = None
        val_bin = ""
        scaled_val = None
        formatted = ""

        try:
            val_dec = int(raw_hex, 16)
            bit_len = max(len(raw_hex) * 4, 16)
            val_bin = f"{val_dec:0{bit_len}b}"
            val_bin_spaced = " ".join([val_bin[max(0, i - 4):i] for i in range(len(val_bin), 0, -4)][::-1])
        except ValueError:
            val_bin_spaced = ""

        if val_dec is not None:
            scaled_val = round(val_dec * scale, 2)
            if scale == 0.1:
                formatted = f"{scaled_val:.1f} {unit}".strip()
            elif scale == 1.0:
                formatted = f"{val_dec} {unit}".strip()
            else:
                formatted = f"{scaled_val} {unit}".strip()
        else:
            formatted = raw_hex

        notes = desc
        if idx == 0 and len(raw_hex) >= 7:
            bu_ok = raw_hex[1] == "1" if len(raw_hex) > 1 else False
            mv_busy = raw_hex[2] == "1" if len(raw_hex) > 2 else False
            heat_ready = raw_hex[5] == "1" if len(raw_hex) > 5 else False
            mv_ok = raw_hex[6] == "1" if len(raw_hex) > 6 else False
            notes = f"BU Init: {'OK' if bu_ok else 'Fault'} | Valve: {'Moving' if mv_busy else 'Idle'} | Heater: {'Ready' if heat_ready else 'Heating'} | Valve Init: {'OK' if mv_ok else 'Uninit'}"
        elif idx == 2 and val_dec is not None:
            notes = f"Brew Unit Encoder Position ({val_dec} ticks from home)"
        elif idx == 3 and val_dec is not None:
            vol_ml = round(val_dec / 2.366, 1)
            notes = f"Dispense Cycle Volume: ~{vol_ml} ml ({val_dec} flowmeter pulses)"
        elif idx == 4 and val_dec is not None:
            notes = f"Coffee Thermoblock Temp: {val_dec * 0.1:.1f} °C"
        elif idx == 5 and val_dec is not None:
            notes = f"Steam Thermoblock Temp: {val_dec * 0.1:.1f} °C"
        elif idx == 7 and len(raw_hex) >= 3:
            tray_missing = raw_hex[0] == "1"
            water_low = raw_hex[2] == "1" if len(raw_hex) > 2 else False
            notes = f"Drip Tray: {'MISSING' if tray_missing else 'OK'} | Water Tank: {'EMPTY/LOW' if water_low else 'OK'}"

        fields.append({
            "key": key,
            "frame": "HZ",
            "index": idx,
            "raw_hex": raw_hex,
            "raw_dec": val_dec,
            "raw_bin": val_bin_spaced,
            "name": name,
            "category": category,
            "unit": unit,
            "scale": scale,
            "scaled_val": scaled_val,
            "formatted": formatted,
            "desc": desc,
            "notes": notes,
            "is_custom": is_custom
        })

    # 2. AS: Frame parsing
    as_clean = as_raw.strip()
    if as_clean.lower().startswith("as:"):
        as_clean = as_clean[3:].strip()
    as_parts = as_clean.split(",") if as_clean else []
    off_adc = None
    on_adc = None

    if len(as_parts) >= 2:
        for idx in range(2):
            key = f"AS_{idx}"
            cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
            name = cfg.get("name", f"AS Field {idx}")
            unit = cfg.get("unit", "counts")
            scale = float(cfg.get("scale", 1.0))
            desc = cfg.get("desc", "Optical IR ADC reading")
            raw_hex = as_parts[idx].strip()
            sub_hex = raw_hex[-4:] if len(raw_hex) >= 4 else raw_hex
            try:
                val_dec = int(sub_hex, 16)
                val_bin = f"{val_dec:016b}"
                val_bin_spaced = " ".join([val_bin[max(0, i - 4):i] for i in range(len(val_bin), 0, -4)][::-1])
            except ValueError:
                val_dec = None
                val_bin_spaced = ""

            if idx == 0:
                off_adc = val_dec
                notes = f"Ambient Background IR Light (LED OFF): {val_dec} ADC counts"
            else:
                on_adc = val_dec
                notes = f"Reflected IR Light (LED PULSED ON): {val_dec} ADC counts"

            fields.append({
                "key": key,
                "frame": "AS",
                "index": idx,
                "raw_hex": sub_hex,
                "raw_dec": val_dec,
                "raw_bin": val_bin_spaced,
                "name": name,
                "category": "Optical Hopper",
                "unit": unit,
                "scale": scale,
                "scaled_val": val_dec,
                "formatted": f"{val_dec} {unit}".strip() if val_dec is not None else sub_hex,
                "desc": desc,
                "notes": notes,
                "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
            })

        if off_adc is not None and on_adc is not None:
            delta = on_adc - off_adc
            key = "AS_DELTA"
            cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
            calib = sc.get_optical_bean_calibration()
            thresh = calib.get("threshold", 115)
            hyst = calib.get("hysteresis", 5)
            beans_ok = (delta >= (thresh - hyst))
            notes = f"Differential Delta: {delta} counts | Threshold: {thresh} ± {hyst} | Status: {'BEANS OK (Beam Reflected)' if beans_ok else 'FILL BEANS (Hopper Empty)'}"
            fields.append({
                "key": key,
                "frame": "AS",
                "index": 2,
                "raw_hex": f"{delta & 0xFFFF:04X}",
                "raw_dec": delta,
                "raw_bin": f"{delta & 0xFFFF:016b}",
                "name": cfg.get("name", "Optical Hopper Differential Delta"),
                "category": "Optical Hopper",
                "unit": "counts",
                "scale": 1.0,
                "scaled_val": delta,
                "formatted": f"{delta} counts ({'BEANS OK' if beans_ok else 'FILL BEANS'})",
                "desc": cfg.get("desc", "Differential IR reflection delta"),
                "notes": notes,
                "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
            })

    # 3. RE:0028 Hardware Fault Latch
    r28_clean = r28_raw.strip()
    if r28_clean.lower().startswith("re:"):
        r28_clean = r28_clean[3:].strip()
    if r28_clean:
        try:
            val_r28 = int(r28_clean, 16)
            val_bin = f"{val_r28:016b}"
            val_bin_spaced = " ".join([val_bin[i:i+4] for i in range(0, 16, 4)])
        except ValueError:
            val_r28 = 0
            val_bin_spaced = ""

        fault_active = (val_r28 != 0)
        fault_notes = "Hardware nominal — No faults latched." if not fault_active else f"ACTIVE FAULT LATCH (Bitmask: 0x{val_r28:04X})"
        key = "RE_0028"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        fields.append({
            "key": key,
            "frame": "RE:0028",
            "index": 0,
            "raw_hex": r28_clean,
            "raw_dec": val_r28,
            "raw_bin": val_bin_spaced,
            "name": cfg.get("name", "Hardware Fault Latch Register"),
            "category": "Safety",
            "unit": "bitmask",
            "scale": 1.0,
            "scaled_val": val_r28,
            "formatted": f"0x{val_r28:04X} ({'NOMINAL' if not fault_active else 'FAULT'})",
            "desc": cfg.get("desc", "16-bit non-volatile hardware safety lockout latch"),
            "notes": fault_notes,
            "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
        })

    # 4. CS: Component Status
    cs_clean = cs_raw.strip()
    if cs_clean.lower().startswith("cs:"):
        cs_clean = cs_clean[3:].strip()
    if cs_clean:
        try:
            val_cs = int(cs_clean, 16)
            val_bin = f"{val_cs:016b}"
            val_bin_spaced = " ".join([val_bin[i:i+4] for i in range(0, 16, 4)])
        except ValueError:
            val_cs = 0
            val_bin_spaced = ""
        key = "CS_0"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        fields.append({
            "key": key,
            "frame": "CS",
            "index": 0,
            "raw_hex": cs_clean,
            "raw_dec": val_cs,
            "raw_bin": val_bin_spaced,
            "name": cfg.get("name", "Component Triac & Actuator State"),
            "category": "Actuators",
            "unit": "bitmask",
            "scale": 1.0,
            "scaled_val": val_cs,
            "formatted": f"0x{val_cs:04X}",
            "desc": cfg.get("desc", "Pump, heater triacs, and valve line states"),
            "notes": f"Actuator bitfield: 0x{val_cs:04X}",
            "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
        })

    # 5. IC: Input Bus State
    ic_clean = ic_raw.strip()
    if ic_clean.lower().startswith("ic:"):
        ic_clean = ic_clean[3:].strip()
    if ic_clean:
        try:
            val_ic = int(ic_clean, 16)
            val_bin = f"{val_ic:016b}"
            val_bin_spaced = " ".join([val_bin[i:i+4] for i in range(0, 16, 4)])
        except ValueError:
            val_ic = 0
            val_bin_spaced = ""
        key = "IC_0"
        cfg = custom_mappings.get(key, DEFAULT_SENSOR_MAPPINGS.get(key, {}))
        fields.append({
            "key": key,
            "frame": "IC",
            "index": 0,
            "raw_hex": ic_clean,
            "raw_dec": val_ic,
            "raw_bin": val_bin_spaced,
            "name": cfg.get("name", "MCU Input Bus Line State"),
            "category": "Hardware",
            "unit": "bitmask",
            "scale": 1.0,
            "scaled_val": val_ic,
            "formatted": f"0x{val_ic:04X}",
            "desc": cfg.get("desc", "Microcontroller digital input line status"),
            "notes": f"Input line states: 0x{val_ic:04X}",
            "is_custom": key in custom_mappings and custom_mappings[key] != DEFAULT_SENSOR_MAPPINGS.get(key)
        })

    return {
        "timestamp": time.strftime("%H:%M:%S"),
        "frames": {
            "HZ": hz_raw,
            "AS": as_raw,
            "CS": cs_raw,
            "IC": ic_raw,
            "RE_0028": r28_raw
        },
        "fields": fields,
        "custom_mappings": custom_mappings
    }


def compute_advisor_health(summary: Dict[str, Any], live_sensors: Optional[Dict[str, Any]] = None) -> Tuple[int, List[Dict[str, str]]]:
    """Runs automated heuristic health analysis matching SPECTRA diagnostic engine."""
    score = 95
    cards = []
    telemetry = summary.get("telemetry", {})
    alerts = summary.get("alerts", [])
    maint = summary.get("maintenance", [])
    error_counters = (live_sensors or {}).get("error_counters", {}) if live_sensors else {}

    # 1. Descaling
    decalc_due = False
    decalc_pct = None
    for m in maint:
        lbl = m.get("label", "").lower()
        if "decalc" in lbl or "descal" in lbl:
            decalc_pct = m.get("percentage")
            if decalc_pct is not None and decalc_pct > 80:
                decalc_due = True

    if decalc_due or (decalc_pct is not None and decalc_pct > 75):
        score -= 10
        cards.append({
            "icon": "⚠️",
            "title": "Thermoblock Descaling Recommended",
            "desc": f"Descaling cycle life progress is at {decalc_pct}%. Heatup efficiency is impacted by calcification.",
            "action": "Action: Run complete descaling procedure using Jura 3-phase descaling tablets.",
            "severity": "warn"
        })
    else:
        cards.append({
            "icon": "✓",
            "title": "Hydraulic Calcification Within Margin",
            "desc": f"Thermoblock fluid channel resistance is optimal. Progress: {decalc_pct or 0}%.",
            "action": "Status: Descaling not required at this time.",
            "severity": "ok"
        })

    # 2. Drip Tray Microswitch Bouncing
    tray_trips = error_counters.get("Drip Tray Missing Trips", 0)
    if tray_trips > 10:
        score -= 5
        cards.append({
            "icon": "🔧",
            "title": f"Drip Tray Microswitch Bouncing ({tray_trips} events)",
            "desc": "High switch trip frequency detected. Potential contact oxidation or loose seating springs.",
            "action": "Action: Inspect metal contact leaf springs on tray backplate; clean with isopropyl alcohol.",
            "severity": "info"
        })

    # 3. Active Blocking Alerts
    for a in alerts:
        if a.get("blocking", False):
            score -= 25
            cards.append({
                "icon": "🔴",
                "title": f"Critical Alert: {a.get('name', 'Machine Error')}",
                "desc": "Appliance is in a lockout state preventing beverage preparation.",
                "action": "Action: Review error code resolution guide before clearing EEPROM faults.",
                "severity": "error"
            })

    # 4. Brew Unit Health
    bu_trips = error_counters.get("Brew Unit Timeout Trips", 0)
    if bu_trips > 0:
        score -= 8
        cards.append({
            "icon": "⚠️",
            "title": f"Brew Unit Motor Drive Hesitation ({bu_trips} trips)",
            "desc": "Motor current peaks exceeded threshold during mechanical stroke.",
            "action": "Action: Disassemble brew unit, clean guide rails, and replace silicone O-rings.",
            "severity": "warn"
        })
    else:
        cards.append({
            "icon": "✓",
            "title": "Brew Unit Mechanics in Optimal Tolerance",
            "desc": "Zero encoder jitter recorded. Motor drive torque is within factory specification.",
            "action": "Status: Standard maintenance interval active.",
            "severity": "ok"
        })

    final_score = max(20, min(100, score))
    return final_score, cards


def is_valid_port(port: str) -> bool:
    if not port or not isinstance(port, str):
        return False
    p = port.strip()
    if not p or len(p) > 256:
        return False
    if p.startswith("/dev/tty") or p.startswith("/dev/pts/") or p.startswith("/dev/serial/"):
        return not any(ch in p for ch in [";", "&", "|", "`", "$", "..", "\x00", "\n", "\r"])
    if p.upper().startswith("COM"):
        return not any(ch in p for ch in [";", "&", "|", "`", "$", "..", "\x00", "\n", "\r"])
    if "DEMO" in p.upper() or p.lower() in ("mock", "demo"):
        return True
    return False


class SpectraApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        try:
            msg = format % args
            lvl = "API"
            if len(args) >= 2:
                try:
                    code = int(args[1])
                    if code >= 500:
                        lvl = "ERROR"
                    elif code >= 400:
                        lvl = "WARN"
                except Exception:
                    pass
            log_debug_event(lvl, "API", msg)
        except Exception:
            pass

    def _send_security_headers(self):
        origin = self.headers.get("Origin", "")
        port = _current_http_port or 8080
        allowed_origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "null",
        }
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_security_headers()
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        global _active_session, _current_port, _last_stats_cache
        url = urlparse(self.path)
        params = parse_qs(url.query)

        # 1. API: List Serial Ports
        if url.path == "/api/ports":
            ports = serial_io.list_serial_ports()
            self._send_json(ports)
            return

        # 2. API: Live Sensors & Microswitches
        elif url.path == "/api/sensors":
            port = params.get("port", [""])[0].strip()
            fast_poll = params.get("fast", ["1"])[0] == "1"

            if not port:
                self._send_json({"error": "No serial port specified", "switches": [], "sensors": []})
                return
            if not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "switches": [], "sensors": []})
                return

            with _session_lock:
                global _active_session, _current_port, _consecutive_sensor_errors, _last_sensor_payload
                try:
                    if _active_session is None or _current_port != port:
                        if _active_session is not None:
                            try:
                                _active_session.close()
                            except Exception:
                                pass
                        _active_session = sc.JuraStatsSession(port_name=port)
                        _current_port = port
                        _consecutive_sensor_errors = 0
                        _last_sensor_payload = None

                    if _active_session.conn is not None and not _active_session.conn.is_open:
                        try:
                            _active_session.conn.close()
                        except Exception:
                            pass
                        _active_session.conn = None

                    if _active_session.conn is None or not _active_session.conn.is_open:
                        _active_session.conn = serial_io.JuraSerialConnection(port)

                    data = sc.query_live_sensors(
                        port_name=port,
                        conn=_active_session.conn,
                        profile=_active_session.profile,
                        is_legacy=_active_session.is_legacy_cleartext,
                        fast_poll=fast_poll,
                    )

                    if data.get("error"):
                        raise IOError(str(data["error"]))

                    _consecutive_sensor_errors = 0
                    _last_sensor_payload = data
                except Exception as e:
                    _consecutive_sensor_errors += 1
                    err_msg = str(e)
                    is_fatal_disconnect = (
                        isinstance(e, (FileNotFoundError, PermissionError))
                        or "SerialException" in type(e).__name__
                        or "denied" in err_msg.lower()
                        or "does not exist" in err_msg.lower()
                    )

                    if is_fatal_disconnect or _consecutive_sensor_errors >= 3 or _last_sensor_payload is None:
                        # Full tear-down on fatal disconnect or sustained errors (>= 3)
                        if _active_session is not None:
                            try:
                                _active_session.close()
                            except Exception:
                                pass
                            _active_session = None
                        data = {
                            "error": err_msg,
                            "timestamp": time.strftime("%H:%M:%S"),
                            "switches": [],
                            "sensors": [],
                            "telemetry": {},
                        }
                    else:
                        # Debounce transient jitter / timeout: keep session alive and return last valid telemetry
                        data = copy.deepcopy(_last_sensor_payload)
                        data["timestamp"] = time.strftime("%H:%M:%S")
                        data["transient_retry"] = _consecutive_sensor_errors

            self._send_json(data)
            return

        # 3. API: Full Interrogation & Statistics
        elif url.path == "/api/stats":
            port = params.get("port", [""])[0].strip()
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            with _session_lock:
                try:
                    if _active_session is not None:
                        try:
                            _active_session.close()
                        except Exception:
                            pass
                        _active_session = None
                    
                    sess = sc.JuraStatsSession(port_name=port)
                    sess.run_interrogation()
                    data = sess.get_structured_summary()
                    score, cards = compute_advisor_health(data, {})
                    data["health_score"] = score
                    data["advisor_cards"] = cards
                    _last_stats_cache = data
                    _active_session = sess
                    _current_port = port
                except Exception as e:
                    data = {"error": str(e)}

            self._send_json(data)
            return

        # 4. API: Optical Bean Threshold Calibration Info
        elif url.path == "/api/calibration":
            calib = sc.get_optical_bean_calibration()
            self._send_json(calib)
            return

        # 4b. API: List Local EEPROM Offset Overrides
        elif url.path == "/api/offsets/overrides":
            try:
                self._send_json({"success": True, "overrides": profiles_db.list_eeprom_offset_overrides()})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "overrides": {}})
            return

        # 4c. API: Unified Machine Library (Built-in Profiles + Model Specs + Local Overrides)
        elif url.path == "/api/machines":
            try:
                import machine_library
                ef = params.get("ef", [""])[0].strip()
                art = params.get("art", [""])[0].strip()
                mdl = params.get("model", [""])[0].strip()
                if not (ef or art or mdl) and isinstance(_last_stats_cache, dict):
                    ef = str(_last_stats_cache.get("ef_code") or "")
                    art = str(_last_stats_cache.get("article_number") or "")
                    mdl = str(_last_stats_cache.get("model_name") or _last_stats_cache.get("model_family") or "")
                catalog = machine_library.list_machines(
                    detected_ef=ef,
                    detected_art=art,
                    detected_model=mdl,
                )
                catalog["success"] = True
                self._send_json(catalog)
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "machines": []})
            return

        # 5. API: Branded Service Report (HTML Inspection Certificate)
        elif url.path == "/api/service_report":
            port = params.get("port", [""])[0].strip()
            lang = params.get("lang", ["en"])[0].strip().lower()
            is_cs = lang.startswith("cs")
            include_ai = params.get("ai_summary", ["0"])[0].lower() in ("1", "true", "yes")
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            summary = _last_stats_cache
            if summary is None or _current_port != port:
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._send_security_headers()
                self.end_headers()
                try:
                    msg_html = (
                        "<html><body style='background:#070709;color:#e4e4e7;font-family:monospace;padding:40px;'><h2>Data zatím nebyla načtena</h2><p>Před vygenerováním servisního protokolu nejprve klikněte na Načíst stroj.</p></body></html>"
                        if is_cs
                        else "<html><body style='background:#070709;color:#e4e4e7;font-family:monospace;padding:40px;'><h2>Data Not Read Yet</h2><p>Please interrogate the machine first before generating a service certificate.</p></body></html>"
                    )
                    self.wfile.write(msg_html.encode("utf-8"))
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                    pass
                return

            score, _ = compute_advisor_health(summary, {})
            if is_cs:
                checklist = [
                    ("Vizuální kontrola silikonových hadiček a mosazných spojek", True),
                    ("Kontrola tepelných pojistek a kontinuity (TB1: 0,1 Ω, TB2: 0,1 Ω)", True),
                    ("Provedení odvápnění a ověření impulzů průtokoměru", True),
                    ("Očištění kontaktů mikrospínače odkapní misky", True),
                ]
            else:
                checklist = [
                    ("Visual inspection of silicone pressure lines & brass fittings", True),
                    ("Safety thermal cutoff continuity (TB1: 0.1Ω, TB2: 0.1Ω)", True),
                    ("Descaling cycle execution & flowmeter verification", True),
                    ("Clean microswitch contact leaves on rear chassis", True),
                ]
            ai_summary_data = None
            if include_ai:
                try:
                    import spectra_ai
                    if spectra_ai.is_ai_enabled():
                        ai_res = spectra_ai.generate_customer_service_summary(summary, score, lang=lang)
                        if ai_res.get("success"):
                            ai_summary_data = ai_res
                except Exception:
                    pass
            html_content = gui_widgets.generate_service_report_html(summary, score, checklist, ai_summary=ai_summary_data, lang=lang)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._send_security_headers()
            self.end_headers()
            try:
                self.wfile.write(html_content.encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
            return

        # 6. API: Export Data (JSON, CSV, Plain Text Report, Diagnostic Capture Bundle)
        elif url.path == "/api/export":
            port = params.get("port", [""])[0].strip()
            fmt = params.get("format", ["json"])[0].lower()
            save_dialog = params.get("save_dialog", ["0"])[0].lower() in ("1", "true", "yes")

            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port", "success": False})
                return

            with _session_lock:
                timestamp = time.strftime("%Y%m%d_%H%M%S")

                if fmt in ("capture", "dump"):
                    # Full hardware diagnostic capture bundle (raw EEPROM + gateways)
                    safe_conn = _active_session.conn if (_active_session and _current_port == port and _active_session.conn and _active_session.conn.is_open) else None
                    owns = False
                    if safe_conn is None:
                        safe_conn = serial_io.JuraSerialConnection(port)
                        owns = True
                    try:
                        bundle = spectra_probe.capture_machine_bundle(safe_conn)
                    finally:
                        if owns:
                            safe_conn.close()

                    content = json.dumps(bundle, indent=2, ensure_ascii=False)
                    safe_model = re.sub(r'[^\w\-_]', '_', str(bundle.get("identity", {}).get("model_name") or "appliance"))
                    filename = f"spectra_capture_{safe_model}_{timestamp}.json"
                    mime = "application/json; charset=utf-8"
                    ext = "json"
                else:
                    # Resolve active session or fallback session for telemetry
                    session = _active_session if (_active_session and _current_port == port) else None
                    if session is None:
                        session = sc.JuraStatsSession(port_name=port)

                    safe_model = re.sub(r'[^\w\-_]', '_', str(session.model_family or "appliance"))

                    if fmt == "csv":
                        content = session.export_csv()
                        mime = "text/csv; charset=utf-8"
                        ext = "csv"
                    elif fmt in ("text", "txt"):
                        content = session.export_text_report()
                        mime = "text/plain; charset=utf-8"
                        ext = "txt"
                    else:
                        content = session.export_json()
                        mime = "application/json; charset=utf-8"
                        ext = "json"

                    filename = f"spectra_export_{safe_model}_{timestamp}.{ext}"

            # If user requested OS save dialog, prompt via prompt_save_file_dialog
            if save_dialog:
                try:
                    import hmi_inspector
                    try:
                        saved_path = hmi_inspector.prompt_save_file_dialog(
                            default_filename=filename,
                            title="Save SPECTRA Diagnostic Report"
                        )
                    except getattr(hmi_inspector, "DialogUnavailableError", RuntimeError) as due:
                        self._send_json({
                            "success": False,
                            "dialog_unavailable": True,
                            "error": f"Native file dialog unavailable: {due}",
                            "content": content,
                            "filename": filename,
                            "mime": mime
                        })
                        return

                    if not saved_path:
                        self._send_json({
                            "success": False,
                            "cancelled": True,
                            "message": "Save cancelled by user.",
                            "content": content,
                            "filename": filename,
                            "mime": mime
                        })
                        return

                    with open(saved_path, "w", encoding="utf-8", newline="") as f:
                        f.write(content)
                    with _capture_cache_lock:
                        _written_capture_paths.add(os.path.abspath(saved_path))
                    self._send_json({
                        "success": True,
                        "saved_path": saved_path,
                        "filename": os.path.basename(saved_path),
                        "format": ext
                    })
                except Exception as e:
                    self._send_json({
                        "success": False,
                        "error": f"Failed to export report: {e}",
                        "content": content,
                        "filename": filename,
                        "mime": mime
                    })
                return

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(content.encode("utf-8") if isinstance(content, str) else content)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
            return

        # 7. API: Developer Memory Mapper Info [DEV ONLY]
        elif url.path == "/api/mapper/info":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err})
                    return
                stats = mapper.get_summary_stats()
                self._send_json({
                    "ef_code": mapper.ef_code,
                    "model_family": mapper.model_family,
                    "address_width": mapper.address_width,
                    "max_words": mapper.max_words,
                    "is_two_digit": mapper.is_two_digit,
                    "spec_file": os.path.basename(mapper.spec_file_path or ""),
                    "summary": stats
                })
            return

        # 8. API: Developer Memory Mapper Sweep [DEV ONLY]
        elif url.path == "/api/mapper/sweep":
            port = params.get("port", [""])[0].strip()
            block_param = params.get("block", ["all"])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "registers": []})
                    return
                if block_param == "all" or not block_param.isdigit():
                    mapper.sweep_eeprom()
                    regs = [serialize_register_entry(r) for r in mapper.classified_registers]
                else:
                    b_idx = int(block_param)
                    updated = mapper.sweep_block(b_idx)
                    regs = [serialize_register_entry(r) for r in updated]
                summary = mapper.get_summary_stats()
                self._send_json({
                    "registers": regs,
                    "summary": summary,
                    "timestamp": time.strftime("%H:%M:%S")
                })
            return

        # 9. API: Developer Memory Mapper Diff [DEV ONLY]
        elif url.path == "/api/mapper/diff":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "changed_registers": []})
                    return
                diff = mapper.compute_diff(mask_noise=True)
                diff["changed_registers"] = [serialize_register_entry(r) for r in diff["changed_registers"]]
                diff["summary"] = mapper.get_summary_stats()
                self._send_json(diff)
            return

        # 10. API: Developer Raw Sensor Telemetry & Field Breakdown [DEV ONLY]
        elif url.path == "/api/mapper/raw_sensors":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "frames": {}, "fields": []})
                    return
                raw_data = _decode_raw_sensors(mapper)
                self._send_json(raw_data)
            return

        # 10b. API: Kalerm HMI Dynamic Local Firmware Discovery
        elif url.path == "/api/hmi/discover":
            try:
                import hmi_inspector
                search_dir = params.get("dir", [None])[0]
                targets = hmi_inspector.KalermHmiInspector.discover_local_targets(search_dir)
                default_dir = os.path.expanduser("~/Downloads")
                self._send_json({
                    "success": True,
                    "targets": targets,
                    "default_dir": default_dir,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "targets": []})
            return

        # 11. API: Kalerm HMI Info & Metadata
        elif url.path == "/api/hmi/info":
            target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            try:
                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                sig = inspector.verify_signature()
                self._send_json({
                    "success": True,
                    "binary_path": inspector.binary_path,
                    "file_size": inspector.file_size,
                    "container_type": getattr(inspector, "container_type", "ELF32_LVGL"),
                    "container_badge": getattr(inspector, "container_badge", "ELF32 ARM (LVGL)"),
                    "companion_ctr_bin": getattr(inspector, "companion_ctr_bin", None),
                    "sha256": sig["sha256"],
                    "signature_status": sig["status_label"],
                    "signature_present": sig["signature_present"],
                    "signature_path": sig["signature_path"],
                    "warning": sig["warning"],
                    "sections_count": len(inspector.sections),
                    "symbols_count": len(inspector.symbols),
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 12. API: Kalerm HMI Automated Audit Findings
        elif url.path == "/api/hmi/audit":
            target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            target_locale = params.get("locale", ["cs-CZ"])[0].strip() or "cs-CZ"
            try:
                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                findings = inspector.run_audit(target_locale=target_locale)
                sig = inspector.verify_signature()
                self._send_json({
                    "success": True,
                    "binary_path": inspector.binary_path,
                    "target_locale": target_locale,
                    "sha256": sig["sha256"],
                    "findings": findings,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "findings": []})
            return

        # 12b. API: Kalerm HMI 3-Tier Semantic Hybrid Audit & Glossary
        elif url.path == "/api/hmi/semantic":
            target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            target_locale = params.get("locale", ["cs-CZ"])[0].strip() or "cs-CZ"
            use_ollama = params.get("use_ollama", ["false"])[0].lower() in ("true", "1", "yes")
            ollama_model = params.get("model", [None])[0]
            auto_unload = params.get("auto_unload", ["true"])[0].lower() in ("true", "1", "yes")
            try:
                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                report = inspector.run_semantic_audit(
                    target_locale=target_locale,
                    use_ollama=use_ollama,
                    ollama_model=ollama_model,
                    auto_unload=auto_unload
                )
                self._send_json({"success": True, "report": report})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "report": None})
            return

        # 12c. API: Kalerm HMI AI System Status & Hardware Profile
        elif url.path in ("/api/hmi/ai_status", "/api/hmi/ai/status"):
            try:
                import hmi_inspector
                status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
                status["semantic_progress"] = hmi_inspector.KalermHmiInspector.get_semantic_scan_progress()
                self._send_json({"success": True, "status": status})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 12d. API: Kalerm HMI Ollama Download & Engine Install Streaming Progress
        elif url.path in ("/api/hmi/ollama_progress", "/api/hmi/ollama/progress"):
            try:
                import hmi_inspector
                prog = hmi_inspector.KalermHmiInspector.get_ollama_download_progress()
                self._send_json({"success": True, "progress": prog})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "progress": {}})
            return

        # 12e. API: Kalerm HMI Deep Semantic Hybrid Scan Streaming Progress
        elif url.path in ("/api/hmi/semantic/progress", "/api/hmi/semantic_progress"):
            try:
                import hmi_inspector
                prog = hmi_inspector.KalermHmiInspector.get_semantic_scan_progress()
                self._send_json({"success": True, "progress": prog})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "progress": {}})
            return

        # 13. API: Kalerm HMI Languages List
        elif url.path == "/api/hmi/languages":
            target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            try:
                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                langs = inspector.extract_all_languages()
                summary = [
                    {
                        "locale": loc,
                        "phrase_count": len(data["phrases"]),
                        "struct_vma": f"0x{data.get('struct_vma', 0):08x}",
                        "singulars_vma": f"0x{data.get('singulars_vma', 0):08x}",
                    }
                    for loc, data in langs.items()
                ]
                self._send_json({"success": True, "languages": summary})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "languages": []})
            return

        # 14. API: Kalerm HMI Phrases Explorer
        elif url.path == "/api/hmi/phrases":
            target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            loc = params.get("locale", ["cs-CZ"])[0].strip() or "cs-CZ"
            query = params.get("query", [""])[0].strip().lower()
            try:
                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                langs = inspector.extract_all_languages()
                if loc not in langs and "MCU-STRINGS" in langs:
                    loc = "MCU-STRINGS"
                lang_data = langs.get(loc, {})
                phrases_data = lang_data.get("phrases", {})
                en_phrases = langs.get("en-GB", {}).get("phrases", {})

                result = []
                for k, p in phrases_data.items():
                    if not query or query in k.lower() or query in p["val"].lower():
                        result.append({
                            "index": p["index"],
                            "key": p["key"],
                            "val": p["val"],
                            "key_vma": f"0x{p['key_vma']:08x}",
                            "val_vma": f"0x{p['val_vma']:08x}",
                            "slot_file_off": f"0x{p['slot_file_off']:08x}",
                            "val_file_off": f"0x{p['val_file_off']:08x}",
                            "en_ref": en_phrases.get(k, {}).get("val", "-"),
                        })
                self._send_json({
                    "success": True,
                    "locale": loc,
                    "count": len(result),
                    "phrases": result,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "phrases": []})
            return

        # API: Hidden Debug & Process Monitor Diagnostics & Ring-Buffer Logs
        elif url.path == "/api/debug/status":
            with _debug_log_lock:
                logs_copy = list(_debug_log_buffer)
            err_cnt = sum(1 for x in logs_copy if x.get("level") == "ERROR")
            warn_cnt = sum(1 for x in logs_copy if x.get("level") == "WARN")
            self._send_json({
                "success": True,
                "build": __build__,
                "version": __version__,
                "diagnostics": get_debug_diagnostics(),
                "logs": logs_copy,
                "error_count": err_cnt,
                "warn_count": warn_cnt,
            })
            return

        elif url.path == "/api/version":
            self._send_json({
                "success": True,
                "build": __build__,
                "version": __version__,
                "edition": __edition__,
            })
            return

        elif url.path == "/api/github/auth/status":
            try:
                import github_auth
                self._send_json(github_auth.get_auth_status())
            except Exception as e:
                self._send_json({"authenticated": False, "login": None, "method": None, "device_flow_available": False, "error": str(e)})
            return

        elif url.path == "/api/ai/status":
            try:
                import spectra_ai
                self._send_json({"success": True, **spectra_ai.get_ai_global_status()})
            except Exception as e:
                self._send_json({"success": False, "ai_enabled": False, "error": str(e)})
            return

        # 5. Static Assets (Compiled React App in web/dist)
        self._serve_static(url.path)

    MAX_POST_BODY = 16 * 1024 * 1024  # 16 MB safety limit

    def do_POST(self):
        global _last_stats_cache
        url = urlparse(self.path)
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_json({"error": "Invalid Content-Length header", "success": False}, status=400)
            return

        if content_length < 0 or content_length > self.MAX_POST_BODY:
            self._send_json({"error": "Payload too large or invalid Content-Length", "success": False}, status=413)
            return

        post_body = self.rfile.read(content_length) if content_length > 0 else b""
        data = {}
        if post_body:
            try:
                data = json.loads(post_body.decode("utf-8"))
            except Exception:
                pass

        # 1. API: Raw Command Injection (Safe prefixes or hex)
        if url.path == "/api/command":
            port = data.get("port", "").strip()
            cmd = data.get("cmd", "").strip()

            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "success": False})
                return
            if not cmd:
                self._send_json({"error": "No command specified", "success": False})
                return

            # Safety: Filter allowed diagnostic commands
            SAFE_ASCII = (
                "TY:", "IC:", "HZ:", "CS:", "AS:", "RT:", "RE:", "TL:",
                "TY$:", "TL$:", "TP$:", "T1$:", "T2$:", "T3$:", "TX$:", "TZ$:",
                "EX$:", "CS$:", "HZ$:", "RE$:", "RT$:", "DS$:", "GS$:", "SS$:", "ST$:", "IC$:", "RR$:", "AS$:"
            )
            cmd_upper = cmd.upper()
            if not any(cmd_upper.startswith(prefix) for prefix in SAFE_ASCII):
                self._send_json({
                    "error": f"Refusing command '{cmd}'. Only safe read prefixes {SAFE_ASCII} permitted.",
                    "success": False
                })
                return

            with _session_lock:
                try:
                    if _active_session is not None and _current_port == port and _active_session.conn and _active_session.conn.is_open:
                        resp = _active_session.conn.query_ascii(cmd, timeout=1.2)
                    else:
                        conn = serial_io.JuraSerialConnection(port)
                        resp = conn.query_ascii(cmd, timeout=1.2)
                        conn.close()
                    self._send_json({
                        "success": True,
                        "cmd": cmd,
                        "response": resp or "[NO_REPLY]",
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception as e:
                    self._send_json({"error": str(e), "success": False})
            return

        # 1b. API: Diagnostic Hardware Dump Bundle Capture
        elif url.path == "/api/export_capture":
            cached_id = data.get("capture_id", "").strip()
            port = data.get("port", "").strip()
            joe_csv = data.get("joe_csv", "").strip()
            save_dialog = bool(data.get("save_dialog", False))
            use_ollama = bool(data.get("use_ollama", False))
            ollama_model = data.get("model")

            try:
                bundle = None
                capture_id = ""
                if cached_id:
                    with _capture_cache_lock:
                        if cached_id in _cached_captures:
                            capture_id = cached_id
                            bundle = _cached_captures[cached_id]

                if bundle is None:
                    if not port or not is_valid_port(port):
                        self._send_json({"error": "Invalid or missing serial port", "success": False})
                        return

                    joe_data = spectra_probe.parse_joe_csv_text(joe_csv) if joe_csv else {}
                    with _session_lock:
                        safe_conn = _active_session.conn if (_active_session and _current_port == port and _active_session.conn and _active_session.conn.is_open) else None
                        owns = False
                        if safe_conn is None:
                            safe_conn = serial_io.JuraSerialConnection(port)
                            owns = True
                        try:
                            bundle = spectra_probe.capture_machine_bundle(
                                safe_conn,
                                joe_data=joe_data,
                                use_ollama=use_ollama,
                                ollama_model=ollama_model,
                            )
                        finally:
                            if owns:
                                safe_conn.close()

                    capture_id = uuid.uuid4().hex[:12]
                    with _capture_cache_lock:
                        _cached_captures[capture_id] = bundle
                        # Keep max 20 captures in memory
                        if len(_cached_captures) > 20:
                            oldest_k = next(iter(_cached_captures))
                            _cached_captures.pop(oldest_k, None)

                safe_model = re.sub(r'[^\w\-_]', '_', str(bundle.get("identity", {}).get("model_name") or "appliance"))
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"spectra_capture_{safe_model}_{timestamp}.json"

                if save_dialog:
                    try:
                        import hmi_inspector
                        try:
                            saved_path = hmi_inspector.prompt_save_file_dialog(
                                default_filename=filename,
                                title="Save Full Hardware Diagnostic Dump Bundle"
                            )
                        except getattr(hmi_inspector, "DialogUnavailableError", RuntimeError) as due:
                            self._send_json({
                                "success": False,
                                "dialog_unavailable": True,
                                "error": f"Native file dialog unavailable: {due}",
                                "capture_id": capture_id,
                                "filename": filename,
                                "bundle": bundle
                            })
                            return

                        if not saved_path:
                            self._send_json({
                                "success": False,
                                "cancelled": True,
                                "message": "Save cancelled by user.",
                                "capture_id": capture_id,
                                "filename": filename,
                                "bundle": bundle
                            })
                            return

                        with open(saved_path, "w", encoding="utf-8", newline="") as f:
                            json.dump(bundle, f, indent=2, ensure_ascii=False)
                        with _capture_cache_lock:
                            _written_capture_paths.add(os.path.abspath(saved_path))
                        self._send_json({
                            "success": True,
                            "saved_path": saved_path,
                            "filename": os.path.basename(saved_path),
                            "capture_id": capture_id,
                            "bundle": bundle
                        })
                    except Exception as write_err:
                        self._send_json({
                            "error": f"Failed to save file: {write_err}",
                            "success": False,
                            "capture_id": capture_id,
                            "filename": filename,
                            "bundle": bundle
                        })
                    return

                self._send_json({
                    "success": True,
                    "capture_id": capture_id,
                    "filename": filename,
                    "bundle": bundle
                })
            except Exception as e:
                self._send_json({"error": str(e), "success": False})
            return

        # 2. API: Set Optical Bean Sensor Threshold
        elif url.path == "/api/set_threshold":
            val = int(data.get("threshold", 115))
            new_t = sc.set_optical_bean_threshold(val, save=True)
            self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            return

        # 3. API: Reset Optical Bean Sensor Threshold
        elif url.path == "/api/reset_threshold":
            new_t = sc.reset_optical_bean_threshold(save=True)
            self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            return

        # 4. API: Capture Baseline Reference [DEV ONLY]
        elif url.path == "/api/mapper/baseline":
            port = data.get("port", "").strip()
            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "success": False})
                    return
                snap = mapper.capture_baseline()
                summary = mapper.get_summary_stats()
                self._send_json({
                    "success": True,
                    "timestamp": snap.timestamp,
                    "summary": summary
                })
            return

        # 5. API: Map Register to Model Spec [DEV ONLY]
        elif url.path == "/api/mapper/map_register":
            port = data.get("port", "").strip()
            addr = int(data.get("addr", 0))
            name = str(data.get("name", "")).strip()
            desc = str(data.get("desc", "")).strip()
            category = str(data.get("category", "settings")).strip()
            unit = str(data.get("unit", "")).strip()
            status = str(data.get("status", "mapped")).strip()

            with _session_lock:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "success": False})
                    return
                ok, msg = mapper.map_register(addr, name, desc, category, unit, status)
                self._send_json({
                    "success": ok,
                    "message": msg,
                    "summary": mapper.get_summary_stats(),
                    "registers": [serialize_register_entry(r) for r in mapper.classified_registers]
                })
            return

        # 6. API: Map Sensor Field [DEV ONLY]
        elif url.path == "/api/mapper/map_sensor_field":
            field_key = str(data.get("key", "")).strip()
            if not field_key:
                self._send_json({"error": "No sensor field key specified", "success": False})
                return
            ok = save_custom_sensor_mapping(field_key, {
                "name": str(data.get("name", "")).strip(),
                "category": str(data.get("category", "General")).strip(),
                "unit": str(data.get("unit", "")).strip(),
                "scale": float(data.get("scale", 1.0)),
                "desc": str(data.get("desc", "")).strip(),
            })
            self._send_json({
                "success": ok,
                "mappings": load_custom_sensor_mappings(),
                "message": f"Saved custom mapping for {field_key}"
            })
            return

        # 7. API: Reset Custom Sensor Mappings to Defaults [DEV ONLY]
        elif url.path == "/api/mapper/reset_sensor_mappings":
            reset_custom_sensor_mappings()
            self._send_json({
                "success": True,
                "mappings": load_custom_sensor_mappings(),
                "message": "Reset sensor mappings to defaults"
            })
            return

        elif url.path == "/api/hmi/browse":
            try:
                body = json.loads(post_body.decode("utf-8")) if post_body else {}
                initial_dir = body.get("initial_dir") or body.get("dir") or os.path.expanduser("~/Downloads")
                import hmi_inspector
                selected = hmi_inspector.KalermHmiInspector.prompt_file_browser(initial_dir)
                if selected:
                    self._send_json({"success": True, "path": selected})
                else:
                    self._send_json({"success": False, "cancelled": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/hmi/patch":
            try:
                body = json.loads(post_body.decode("utf-8")) if post_body else {}
                target = body.get("path") or os.path.expanduser("~/Downloads")
                out_path = body.get("output_path") or None
                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                res = inspector.apply_patches(out_path)
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/hmi/export_report":
            try:
                body = json.loads(post_body.decode("utf-8")) if post_body else {}
                target = body.get("path") or os.path.expanduser("~/Downloads")
                fmt = body.get("format") or "md"
                target_locale = body.get("locale") or "cs-CZ"
                out_path = body.get("output_path")
                save_dialog = bool(body.get("save_dialog", False))

                import hmi_inspector
                if save_dialog or (not out_path and not any("test" in arg for arg in sys.argv)):
                    def_out = f"SPECTRA_Firmware_Audit_Report_{target_locale}.{fmt}"
                    out_path = hmi_inspector.prompt_save_file_dialog(
                        default_filename=def_out,
                        title="Save SPECTRA Firmware Audit Report"
                    )
                    if not out_path:
                        self._send_json({"success": False, "cancelled": True, "message": "Save cancelled by user."})
                        return

                if not out_path:
                    out_path = os.path.join(os.path.expanduser("~/Downloads"), f"SPECTRA_Firmware_Audit_Report_{target_locale}.{fmt}")
                elif not os.path.isabs(out_path):
                    out_path = os.path.join(os.path.expanduser("~/Downloads"), out_path)
                inspector = hmi_inspector.KalermHmiInspector(target)
                saved = inspector.export_bug_report(out_path, format_type=fmt, target_locale=target_locale)
                self._send_json({"success": True, "saved_path": saved, "filename": os.path.basename(saved)})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/hmi/semantic":
            try:
                body = json.loads(post_body.decode("utf-8")) if post_body else {}
                target = body.get("path") or os.path.expanduser("~/Downloads")
                target_locale = body.get("locale") or "cs-CZ"
                use_ollama = bool(body.get("use_ollama", False))
                ollama_model = body.get("model")
                auto_unload = bool(body.get("auto_unload", True))
                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                report = inspector.run_semantic_audit(
                    target_locale=target_locale,
                    use_ollama=use_ollama,
                    ollama_model=ollama_model,
                    auto_unload=auto_unload
                )
                self._send_json({"success": True, "report": report})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "report": None})
            return

        elif url.path in ("/api/hmi/ollama_control", "/api/hmi/ai/control"):
            try:
                body = json.loads(post_body.decode("utf-8")) if post_body else {}
                action = body.get("action", "")
                model = body.get("model")
                import hmi_inspector
                if action == "stop":
                    try:
                        import spectra_ai
                        res = spectra_ai.set_ai_enabled(False, model=model)
                        stop_res = res.get("stop_result") or {"status": "STOPPED"}
                        self._send_json({"success": True, "is_error": False, "result": stop_res, "ai_status": res["status"]["system"]})
                        return
                    except Exception:
                        pass
                res = hmi_inspector.KalermHmiInspector.control_local_ollama(action=action, model=model)
                is_error = res.get("status") in ("ERROR", "BINARY_NOT_FOUND", "OLLAMA_OFFLINE", "START_TIMEOUT")
                ai_status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
                self._send_json({"success": not is_error, "is_error": is_error, "result": res, "ai_status": ai_status})
            except Exception as e:
                self._send_json({"success": False, "is_error": True, "error": str(e)})
            return

        # 16. API: Native App Mode Lifecycle (Heartbeat & Window Closed)
        elif url.path == "/api/app/heartbeat":
            global _last_heartbeat_time
            _last_heartbeat_time = time.time()
            self._send_json({"success": True, "status": "ALIVE"})
            return

        elif url.path in ("/api/app/window_closed", "/api/app/close"):
            # When running inside legacy pywebview/GTK container, ignore beforeunload beacons
            # unless caller explicitly requests immediate shutdown.
            is_immediate = bool(isinstance(data, dict) and data.get("immediate"))
            if _is_native_webview and not is_immediate:
                self._send_json({"success": True, "status": "IGNORED_NATIVE_CONTAINER"})
                return

            if is_immediate:
                self._send_json({"success": True, "status": "TERMINATING_IMMEDIATE"})
                def _immediate_exit():
                    cleanup_resources()
                    for cb in list(_shutdown_callbacks):
                        try:
                            cb()
                        except Exception:
                            pass
                    os._exit(0)
                threading.Timer(0.05, _immediate_exit).start()
                return

            close_req_time = time.time()
            self._send_json({"success": True, "status": "TERMINATING"})
            def _deferred_exit_if_not_reloaded():
                # Allow 3.0s grace: if heartbeat received or page active, do not terminate!
                if time.time() - getattr(web_server, "_last_heartbeat_time", 0) < 3.0:
                    return  # Page is still active (download, navigation, or refresh)
                cleanup_resources()
                for cb in list(_shutdown_callbacks):
                    try:
                        cb()
                    except Exception:
                        pass
                os._exit(0)
            threading.Timer(3.0, _deferred_exit_if_not_reloaded).start()
            return

        # 17. API: Clear Debug Log Buffer
        elif url.path == "/api/debug/clear":
            with _debug_log_lock:
                _debug_log_buffer.clear()
            log_debug_event("INFO", "DEBUG", "Debug log cleared")
            self._send_json({"success": True})
            return

        # 18. API: Push Frontend Client-Side Error to Debug Buffer
        elif url.path == "/api/debug/client_error":
            msg = data.get("message", "Unknown client-side error")
            details = data.get("details", "")
            src = data.get("source", "FRONTEND")
            log_debug_event("ERROR", src, msg, details)
            self._send_json({"success": True})
            return

        # 19. API: Upload Telemetry Capture to Community Repository
        elif url.path == "/api/upload-capture":
            capture_id = data.get("capture_id")
            file_path = data.get("file_path")
            raw_data = data.get("capture_data")

            bundle = None
            if capture_id:
                with _capture_cache_lock:
                    bundle = _cached_captures.get(capture_id)
            if bundle is None and raw_data:
                bundle = raw_data
            elif bundle is None and file_path:
                abs_p = os.path.abspath(file_path)
                with _capture_cache_lock:
                    is_known_written = abs_p in _written_capture_paths
                if not is_known_written and not (abs_p.endswith(".json") and os.path.basename(abs_p).startswith("spectra_capture_")):
                    self._send_json({"success": False, "error": "Access denied: file_path must be a SPECTRA-generated capture bundle."})
                    return
                if not os.path.isfile(abs_p):
                    self._send_json({"success": False, "error": f"File not found: {abs_p}"})
                    return
                try:
                    with open(abs_p, "r", encoding="utf-8") as f:
                        bundle = json.load(f)
                except Exception as e:
                    self._send_json({"success": False, "error": f"Failed to read capture bundle: {e}"})
                    return
            elif bundle is None:
                self._send_json({"success": False, "error": "Missing 'capture_id', 'file_path', or 'capture_data'"})
                return

            try:
                import spectra_probe
                success, msg, issue_url = spectra_probe.upload_capture_to_community_repo(
                    bundle_data=bundle,
                    open_browser=False
                )
                self._send_json({
                    "success": success,
                    "message": msg,
                    "url": issue_url
                })
            except Exception as e:
                self._send_json({
                    "success": False,
                    "error": f"Upload failed: {e}",
                    "message": str(e)
                })
            return

        # 20. API: GitHub OAuth Device Flow & Token Management
        elif url.path == "/api/github/auth/device/start":
            try:
                import github_auth
                res = github_auth.start_device_flow()
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/github/auth/device/poll":
            try:
                import github_auth
                device_code = data.get("device_code", "").strip()
                interval = int(data.get("interval", 5))
                res = github_auth.poll_device_flow(device_code, interval=interval)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/github/auth/token":
            try:
                import github_auth
                tok = data.get("token", "").strip()
                res = github_auth.set_pat(tok)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/github/auth/logout":
            try:
                import github_auth
                res = github_auth.logout()
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 21. API: Central Local AI Toggle & Feature Endpoints (Default OFF)
        elif url.path == "/api/ai/toggle":
            try:
                import spectra_ai
                enabled = bool(data.get("enabled", False))
                model = data.get("model")
                auto_unload = data.get("auto_unload")
                res = spectra_ai.set_ai_enabled(enabled, model=model, auto_unload=auto_unload)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/ai/config":
            try:
                import spectra_ai
                model = data.get("model")
                auto_unload = data.get("auto_unload")
                res = spectra_ai.update_ai_config(model=model, auto_unload=auto_unload)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/mapper/ai_suggest":
            try:
                import spectra_ai
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first.", "suggestions": []})
                    return
                candidates = data.get("candidates") or []
                context_regs = data.get("context_registers") or []
                machine_model = data.get("machine_model") or (_last_stats_cache or {}).get("machine_model") or "Coffee Machine"
                model = data.get("model")
                res = spectra_ai.suggest_eeprom_mappings(
                    candidates=candidates,
                    context_registers=context_regs,
                    machine_model=machine_model,
                    model=model,
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "suggestions": []})
            return

        elif url.path == "/api/advisor/ai_triage":
            try:
                import spectra_ai
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return
                telemetry = data.get("telemetry") or _last_sensor_payload or {}
                stats_summary = data.get("stats") or _last_stats_cache or {}
                model = data.get("model")
                lang = str(data.get("lang") or "en").strip().lower()
                res = spectra_ai.analyze_fault_triage(
                    telemetry=telemetry,
                    stats_summary=stats_summary,
                    model=model,
                    lang=lang,
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/service_report/ai_summary":
            try:
                import spectra_ai
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return
                summary = data.get("stats") or _last_stats_cache
                if not summary:
                    self._send_json({"success": False, "error": "Interrogate machine first before generating service summary."})
                    return
                score, _ = compute_advisor_health(summary, {})
                model = data.get("model")
                lang = str(data.get("lang") or "en").strip().lower()
                res = spectra_ai.generate_customer_service_summary(summary, score, model=model, lang=lang)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 22. API: Local AI EEPROM Offset Calibration from J.O.E. Reference
        elif url.path == "/api/ai/calibrate_offsets":
            try:
                import spectra_ai
                import spectra_probe
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return

                capture_id = str(data.get("capture_id") or "").strip()
                bundle = data.get("bundle") or data.get("capture_data")
                port = str(data.get("port") or _current_port or "").strip()
                joe_csv = str(data.get("joe_csv") or "").strip()
                model = data.get("model")

                if not isinstance(bundle, dict) and capture_id:
                    with _capture_cache_lock:
                        bundle = _cached_captures.get(capture_id)

                if not isinstance(bundle, dict):
                    if not port or not is_valid_port(port):
                        self._send_json({"success": False, "error": "No captured EEPROM bundle or valid serial port provided."})
                        return
                    joe_data = spectra_probe.parse_joe_csv_text(joe_csv) if joe_csv else {}
                    with _session_lock:
                        safe_conn = _active_session.conn if (_active_session and _current_port == port and _active_session.conn and _active_session.conn.is_open) else None
                        owns = False
                        if safe_conn is None:
                            safe_conn = serial_io.JuraSerialConnection(port)
                            owns = True
                        try:
                            bundle = spectra_probe.capture_machine_bundle(
                                safe_conn,
                                joe_data=joe_data,
                                use_ollama=True,
                                ollama_model=model,
                            )
                        finally:
                            if owns:
                                safe_conn.close()

                # Inject J.O.E. CSV if user attached it after capturing EEPROM dump
                if joe_csv and not (bundle.get("joe_ground_truth") or {}).get("products"):
                    joe_data = spectra_probe.parse_joe_csv_text(joe_csv)
                    bundle = dict(bundle)
                    bundle["joe_ground_truth"] = joe_data

                res = spectra_ai.calibrate_eeprom_offsets_from_joe(bundle, model=model)
                if res.get("success") and res.get("override"):
                    bundle = dict(bundle)
                    bundle["ai_offset_fix"] = res["override"]
                    if not capture_id:
                        capture_id = uuid.uuid4().hex[:12]
                    with _capture_cache_lock:
                        _cached_captures[capture_id] = bundle
                        if len(_cached_captures) > 20:
                            oldest_k = next(iter(_cached_captures))
                            _cached_captures.pop(oldest_k, None)
                    res["capture_id"] = capture_id
                    res["bundle"] = bundle
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 23. API: Save & Immediately Apply Local EEPROM Offset Override
        elif url.path == "/api/offsets/apply_local":
            try:
                capture_id = str(data.get("capture_id") or "").strip()
                override = data.get("override")
                if not isinstance(override, dict):
                    with _capture_cache_lock:
                        cached_b = _cached_captures.get(capture_id) if capture_id else None
                    if isinstance(cached_b, dict):
                        override = cached_b.get("ai_offset_fix")

                if not isinstance(override, dict) or (not override.get("products") and not override.get("maintenance")):
                    self._send_json({"success": False, "error": "No valid EEPROM offset override data provided."})
                    return

                saved = profiles_db.save_eeprom_offset_override(
                    override,
                    model_key=data.get("model_key"),
                )

                updated_stats = None
                with _session_lock:
                    if _active_session is not None:
                        if not _active_session.last_eeprom and capture_id:
                            with _capture_cache_lock:
                                cb = _cached_captures.get(capture_id) or {}
                            for k, v in (cb.get("eeprom_words") or {}).items():
                                try:
                                    _active_session.last_eeprom[int(str(k), 16) if str(k).lower().startswith("0x") else int(k)] = int(v)
                                except Exception:
                                    pass
                        if _active_session.apply_local_offset_override():
                            updated_stats = _active_session.get_structured_summary()
                            score, cards = compute_advisor_health(updated_stats, {})
                            updated_stats["health_score"] = score
                            updated_stats["advisor_cards"] = cards
                            _last_stats_cache = updated_stats

                updated_bundle = None
                if capture_id:
                    with _capture_cache_lock:
                        if capture_id in _cached_captures and isinstance(_cached_captures[capture_id], dict):
                            _cached_captures[capture_id]["ai_offset_fix"] = saved
                            updated_bundle = _cached_captures[capture_id]

                self._send_json({
                    "success": True,
                    "saved_key": saved.get("override_key"),
                    "override": saved,
                    "updated_stats": updated_stats,
                    "bundle": updated_bundle,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        elif url.path == "/api/offsets/delete":
            try:
                key = str(data.get("key") or "").strip()
                removed = profiles_db.delete_eeprom_offset_override(key) if key else False
                self._send_json({"success": True, "removed": removed, "overrides": profiles_db.list_eeprom_offset_overrides()})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 24. API: Calibrate EEPROM Offsets from Uploaded CSV or Screenshot (Overview Flow)
        elif url.path == "/api/offsets/calibrate_upload":
            try:
                import spectra_ai
                import spectra_probe
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return

                file_name = str(data.get("file_name") or "reference.csv").strip()
                csv_text = data.get("csv_text")
                image_b64 = data.get("image_b64")
                port = str(data.get("port") or _current_port or "").strip()
                capture_id = str(data.get("capture_id") or "").strip()
                bundle = data.get("bundle")
                model = data.get("model")

                eeprom_words = None
                ty_str = ""
                model_name = ""
                article_number = ""

                if isinstance(bundle, dict) and bundle.get("eeprom_words"):
                    eeprom_words = bundle.get("eeprom_words")
                    ident = bundle.get("identity") or {}
                    ty_str = str(ident.get("ef_code") or (bundle.get("gateways") or {}).get("TY:") or "")
                    model_name = str(ident.get("model_name") or "")
                    article_number = str(ident.get("article_number") or "")
                elif capture_id:
                    with _capture_cache_lock:
                        cached_b = _cached_captures.get(capture_id)
                    if isinstance(cached_b, dict) and cached_b.get("eeprom_words"):
                        bundle = cached_b
                        eeprom_words = cached_b.get("eeprom_words")
                        ident = cached_b.get("identity") or {}
                        ty_str = str(ident.get("ef_code") or (cached_b.get("gateways") or {}).get("TY:") or "")
                        model_name = str(ident.get("model_name") or "")
                        article_number = str(ident.get("article_number") or "")

                if eeprom_words is None:
                    with _session_lock:
                        sess = _active_session
                        if sess is not None and getattr(sess, "last_eeprom", None):
                            eeprom_words = {f"0x{k:04X}": v for k, v in sess.last_eeprom.items()}
                            ty_str = str(sess.ef_code or "")
                            model_name = str(sess.model_family or "")
                            article_number = str((sess.telemetry or {}).get("article_number") or "")

                if eeprom_words is None:
                    if not port or not is_valid_port(port):
                        self._send_json({"success": False, "error": "Interrogate a connected machine first or attach a valid serial port."})
                        return
                    with _session_lock:
                        safe_conn = _active_session.conn if (_active_session and _current_port == port and _active_session.conn and _active_session.conn.is_open) else None
                        owns = False
                        if safe_conn is None:
                            safe_conn = serial_io.JuraSerialConnection(port)
                            owns = True
                        try:
                            bundle = spectra_probe.capture_machine_bundle(
                                safe_conn,
                                joe_data={},
                                use_ollama=False,
                            )
                        finally:
                            if owns:
                                safe_conn.close()
                    eeprom_words = bundle.get("eeprom_words") or {}
                    ident = bundle.get("identity") or {}
                    ty_str = str(ident.get("ef_code") or (bundle.get("gateways") or {}).get("TY:") or "")
                    model_name = str(ident.get("model_name") or "")
                    article_number = str(ident.get("article_number") or "")

                if isinstance(_last_stats_cache, dict):
                    ty_str = ty_str or str(_last_stats_cache.get("ef_code") or "")
                    model_name = model_name or str(_last_stats_cache.get("model_name") or _last_stats_cache.get("model_family") or "")
                    article_number = article_number or str(_last_stats_cache.get("article_number") or "")

                res = spectra_ai.calibrate_offsets_from_upload(
                    eeprom_words=eeprom_words,
                    file_name=file_name,
                    csv_text=csv_text,
                    image_b64=image_b64,
                    ty_str=ty_str,
                    model_name=model_name,
                    article_number=article_number,
                    current_stats=_last_stats_cache if isinstance(_last_stats_cache, dict) else None,
                    model=model,
                )

                if res.get("success") and res.get("override"):
                    if not isinstance(bundle, dict):
                        bundle = {
                            "identity": {
                                "manufacturer": "Jura",
                                "ef_code": ty_str,
                                "model_name": model_name or "Unknown",
                                "article_number": article_number or "unknown",
                            },
                            "gateways": {"TY:": ty_str},
                            "eeprom_words": eeprom_words,
                        }
                    else:
                        bundle = dict(bundle)
                    bundle["ai_offset_fix"] = res["override"]
                    if not capture_id:
                        capture_id = uuid.uuid4().hex[:12]
                    with _capture_cache_lock:
                        _cached_captures[capture_id] = bundle
                        if len(_cached_captures) > 20:
                            _cached_captures.pop(next(iter(_cached_captures)), None)
                    res["capture_id"] = capture_id
                    res["bundle"] = bundle

                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 25. API: Import Offset Patch (.json) into Unified Machine Library
        elif url.path == "/api/machines/import":
            try:
                import machine_library
                raw_patch = data.get("patch") or data.get("payload") or data
                ok, msg, saved = machine_library.import_offset_patch(raw_patch, model_key=data.get("model_key"))
                if not ok:
                    self._send_json({"success": False, "error": msg})
                    return

                updated_stats = None
                with _session_lock:
                    if _active_session is not None and getattr(_active_session, "last_eeprom", None):
                        if _active_session.apply_local_offset_override():
                            updated_stats = _active_session.get_structured_summary()
                            score, cards = compute_advisor_health(updated_stats, {})
                            updated_stats["health_score"] = score
                            updated_stats["advisor_cards"] = cards
                            _last_stats_cache = updated_stats

                ef = str((_last_stats_cache or {}).get("ef_code") or "")
                art = str((_last_stats_cache or {}).get("article_number") or "")
                mdl = str((_last_stats_cache or {}).get("model_name") or (_last_stats_cache or {}).get("model_family") or "")
                catalog = machine_library.list_machines(detected_ef=ef, detected_art=art, detected_model=mdl)
                catalog["success"] = True
                catalog["message"] = msg
                catalog["saved"] = saved
                catalog["updated_stats"] = updated_stats
                self._send_json(catalog)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 26. API: Export Sanitized Offset Patch (.json) for Manual Contribution
        elif url.path == "/api/offsets/export_patch":
            try:
                import machine_library
                import hmi_inspector

                capture_id = str(data.get("capture_id") or "").strip()
                override = data.get("override")
                cached_b = None
                if capture_id:
                    with _capture_cache_lock:
                        cached_b = _cached_captures.get(capture_id)
                if not isinstance(override, dict) and isinstance(cached_b, dict):
                    override = cached_b.get("ai_offset_fix")
                if not isinstance(override, dict):
                    self._send_json({"success": False, "error": "No offset patch data provided to export."})
                    return

                identity = data.get("identity") or (cached_b.get("identity") if isinstance(cached_b, dict) else None)
                include_eeprom = bool(data.get("include_eeprom", False))
                eeprom_words = cached_b.get("eeprom_words") if (include_eeprom and isinstance(cached_b, dict)) else None
                patch = machine_library.build_offset_patch_payload(
                    override,
                    identity=identity,
                    include_eeprom=include_eeprom,
                    eeprom_words=eeprom_words,
                )
                patch_json = json.dumps(patch, indent=2, ensure_ascii=False)
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", patch["identity"].get("ef_code") or patch["identity"].get("model_name") or "machine").strip("_") or "machine"
                filename = f"spectra_offset_patch_{safe_name}_{time.strftime('%Y%m%d_%H%M%S')}.json"

                if bool(data.get("save_dialog", True)):
                    try:
                        saved_path = hmi_inspector.prompt_save_file_dialog(
                            default_filename=filename,
                            title="Export SPECTRA Offset Patch JSON",
                        )
                    except getattr(hmi_inspector, "DialogUnavailableError", RuntimeError) as due:
                        self._send_json({
                            "success": False,
                            "dialog_unavailable": True,
                            "error": f"Native file dialog unavailable: {due}",
                            "filename": filename,
                            "patch_json": patch_json,
                            "patch": patch,
                        })
                        return
                    if not saved_path:
                        self._send_json({"success": False, "cancelled": True, "error": "Export cancelled by user."})
                        return
                    with open(saved_path, "w", encoding="utf-8") as f:
                        f.write(patch_json)
                    self._send_json({
                        "success": True,
                        "saved_path": saved_path,
                        "filename": os.path.basename(saved_path),
                        "patch": patch,
                    })
                    return

                self._send_json({
                    "success": True,
                    "filename": filename,
                    "patch_json": patch_json,
                    "patch": patch,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        # 27. API: Contribute Verified Offset Patch to Public Community Repo
        elif url.path == "/api/offsets/contribute":
            try:
                import machine_library
                import spectra_probe

                capture_id = str(data.get("capture_id") or "").strip()
                override = data.get("override")
                bundle = None
                if capture_id:
                    with _capture_cache_lock:
                        bundle = _cached_captures.get(capture_id)

                if isinstance(bundle, dict):
                    bundle = dict(bundle)
                    if isinstance(override, dict):
                        bundle["ai_offset_fix"] = override
                elif isinstance(override, dict):
                    bundle = machine_library.build_offset_patch_payload(override)
                else:
                    self._send_json({"success": False, "error": "No offset patch provided to contribute."})
                    return

                ok, msg, url_out = spectra_probe.upload_capture_to_community_repo(
                    bundle_data=bundle,
                    open_browser=False,
                )
                self._send_json({
                    "success": ok,
                    "message": msg,
                    "url": url_out,
                    "error": "" if ok else msg,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        else:
            self.send_error(404, "Endpoint Not Found")

    def _serve_static(self, req_path: str):
        global _last_heartbeat_time
        _last_heartbeat_time = time.time()
        if not os.path.isdir(DIST_DIR):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            try:
                self.wfile.write(b"<h1>SPECTRA Backend Online</h1><p>Please build the web UI with <code>npm run build</code> inside the <code>web/</code> directory.</p>")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
            return

        clean_path = req_path.lstrip("/")
        if not clean_path or clean_path == "index.html":
            file_path = os.path.join(DIST_DIR, "index.html")
        else:
            file_path = os.path.join(DIST_DIR, clean_path)

        if not os.path.isfile(file_path):
            # Check project root or public assets for favicons/icons
            if clean_path in ("favicon.ico", "icon.png", "icon.ico", "logo.svg"):
                for alt_root in (os.path.join(PROJECT_DIR, "web", "public"), PROJECT_DIR):
                    cand = os.path.join(alt_root, clean_path)
                    if os.path.isfile(cand):
                        file_path = cand
                        break

        if not os.path.isfile(file_path):
            # Fallback to SPA index.html for client-side routing
            file_path = os.path.join(DIST_DIR, "index.html")

        if os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self._send_security_headers()
            self.end_headers()
            try:
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
        else:
            self.send_error(404, "File Not Found")

    def _send_json(self, data: Any, status: int = 200):
        try:
            payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
            pass


def find_free_port(start_port: int = 8080) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def main(auto_open: bool = False):
    global _current_http_port
    _ensure_serial_group()
    install_tee_streams()
    try:
        import tls_utils
        tls_utils.configure_process_tls_env()
    except Exception:
        pass

    requested_port: Optional[int] = None
    no_browser = "--no-browser" in sys.argv or os.environ.get("SPECTRA_NATIVE_SHELL") == "1"
    for idx, arg in enumerate(sys.argv[1:], start=1):
        if arg == "--port" and idx + 1 < len(sys.argv):
            try:
                requested_port = int(sys.argv[idx + 1])
            except ValueError:
                pass
        elif arg.startswith("--port="):
            try:
                requested_port = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    port = requested_port if (requested_port and 0 < requested_port < 65536) else find_free_port(8080)
    _current_http_port = port
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, SpectraApiHandler)

    print("=" * 78)
    print(f"  SPECTRA (Build {__build__}) Hardware Telemetry API & Web Server")
    print("=" * 78)
    print(f"[*] API & Web Service listening on: http://127.0.0.1:{port}")
    print(f"[*] Native Rust Core Acceleration: {'ENABLED (spectra_py)' if HAS_RUST_CORE else 'DISABLED (Pure Python fallback)'}")
    print("[*] Serving Next-Gen Multi-Paradigm UI connected to live hardware adapters.")
    print("=" * 78)

    log_debug_event(
        "INFO",
        "SpectraCore",
        f"Native Rust Acceleration: {'ACTIVE (spectra_py)' if HAS_RUST_CORE else 'INACTIVE (Pure Python fallback)'}"
    )

    # Automatically launch browser on Windows or when auto_open is True or --open is passed,
    # unless explicitly suppressed for native shell hosting (--no-browser / SPECTRA_NATIVE_SHELL=1).
    if not no_browser and (auto_open or sys.platform.startswith("win") or "--open" in sys.argv):
        try:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down SPECTRA API server...")
        cleanup_resources()
        httpd.server_close()


if __name__ == "__main__":
    main()
