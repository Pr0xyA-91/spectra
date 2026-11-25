#!/usr/bin/env python3
"""
SPECTRA — Next-Gen Hardware Telemetry & Logic Board Diagnostics — Web Server.
Backward-compatible facade & CLI entrypoint backed by the `spectra_web` package.
"""

import sys
import types
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler

from version import __version__, __build__, __edition__
from spectra_web import state as _state
from spectra_web import (
    PROJECT_DIR,
    HAS_RUST_CORE,
    _rust_core,
    _session_lock,
    _hw_op_lock,
    _shutdown_callbacks,
    _capture_cache_lock,
    _cached_captures,
    _written_capture_paths,
    _CONNECTION_SEMAPHORE,
    _SERVER_BOOT_ID,
    _debug_log_buffer,
    _debug_log_lock,
    _hmi_paths_lock,
    _approved_hmi_paths,
    SpectraThreadingHTTPServer,
    _ensure_serial_group,
    touch_heartbeat,
    long_hardware_operation,
    cleanup_resources,
    register_shutdown_callback,
    shutdown_for_restart,
    _get_sidecar_nonce,
    get_dist_dir,
    _DEBUG_SECRET_RE,
    _redact_debug_text,
    _get_allowed_hmi_roots,
    _approve_hmi_path,
    _is_allowed_hmi_path,
    log_debug_event,
    TeeStream,
    install_tee_streams,
    get_debug_diagnostics,
    sanitize_filename_prefix,
    build_export_filename,
    is_valid_port,
    CUSTOM_SENSOR_MAPPINGS_FILE,
    DEFAULT_SENSOR_MAPPINGS,
    load_custom_sensor_mappings,
    save_custom_sensor_mapping,
    reset_custom_sensor_mappings,
    _ui_prefs_lock,
    get_ui_prefs_path,
    _load_ui_prefs_unlocked,
    load_ui_prefs,
    save_ui_prefs,
    serialize_register_entry,
    _canonical_port,
    _get_or_create_mapper,
    _decode_raw_sensors,
    compute_advisor_health,
    SpectraApiHandler,
    find_free_port,
    bind_http_server,
    main,
)

_PROXY_STATE_ATTRS = frozenset({
    "_active_session",
    "_current_port",
    "_last_stats_cache",
    "_mapper_engine",
    "_consecutive_sensor_errors",
    "_last_sensor_payload",
    "_last_heartbeat_time",
    "_active_hw_ops",
    "_is_native_webview",
    "_active_httpd",
    "_debug_log_seq",
    "_current_http_port",
    "_server_start_time",
    "DIST_DIR",
})


class _WebServerModule(types.ModuleType):
    """Module proxy keeping scalar runtime state synchronized with `spectra_web.state`."""

    def __getattr__(self, name: str):
        if name in _PROXY_STATE_ATTRS:
            return getattr(_state, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value):
        if name in _PROXY_STATE_ATTRS:
            setattr(_state, name, value)
            return
        super().__setattr__(name, value)

    def __dir__(self):
        return sorted(set(super().__dir__()) | set(_PROXY_STATE_ATTRS))


if __name__ != "__main__":
    _orig = sys.modules.get(__name__)
    if _orig is not None and not isinstance(_orig, _WebServerModule):
        _proxy = _WebServerModule(__name__, __doc__)
        _proxy.__dict__.update(_orig.__dict__)
        for _attr in _PROXY_STATE_ATTRS:
            _proxy.__dict__.pop(_attr, None)
        sys.modules[__name__] = _proxy


if __name__ == "__main__":
    main()
