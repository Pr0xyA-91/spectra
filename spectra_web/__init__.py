"""SPECTRA Web Server cohesive backend package."""

from spectra_web import state
from spectra_web.state import (
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
)
from spectra_web.security import (
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
)
from spectra_web.prefs import (
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
)
from spectra_web.sensors import (
    serialize_register_entry,
    _canonical_port,
    _get_or_create_mapper,
    _decode_raw_sensors,
    compute_advisor_health,
)
from spectra_web.handler import (
    SpectraApiHandler,
    find_free_port,
    bind_http_server,
    main,
)
