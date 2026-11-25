#!/usr/bin/env python3
"""SPECTRA Web Server GET API route handlers organized by domain."""

import os
import time
import json
import copy
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, List

import serial_io
import stats_collector as sc
import profiles_db
import spectra_probe
import gui_widgets
import updater
import report_archive
from version import __version__, __build__, __edition__

from spectra_web import state as _wstate
from spectra_web.state import (
    _SERVER_BOOT_ID,
    _session_lock,
    _debug_log_lock,
    _debug_log_buffer,
    _capture_cache_lock,
    _written_capture_paths,
    _get_sidecar_nonce,
    long_hardware_operation,
    touch_heartbeat,
)
from spectra_web.security import (
    _is_allowed_hmi_path,
    build_export_filename,
    get_debug_diagnostics,
    is_valid_port,
    log_debug_event,
    sanitize_filename_prefix,
)
from spectra_web.prefs import load_ui_prefs
from spectra_web.sensors import (
    _canonical_port,
    _decode_raw_sensors,
    _get_or_create_mapper,
    compute_advisor_health,
    serialize_register_entry,
)


class GetRoutesMixin:
    """Domain-grouped GET endpoint handlers mixed into SpectraApiHandler."""

    def _get_telemetry_and_exports(self, url, params) -> bool:
        # 1. API: List Serial Ports
        if url.path == "/api/ports":
            ports = serial_io.list_serial_ports()
            self._send_json(ports)
            return True

        # 2. API: Live Sensors & Microswitches
        if url.path == "/api/sensors":
            port = params.get("port", [""])[0].strip()
            fast_poll = params.get("fast", ["1"])[0] == "1"
            manufacturer = params.get("manufacturer", ["auto"])[0].strip().lower() or "auto"

            if not port:
                self._send_json({"error": "No serial port specified", "switches": [], "sensors": []})
                return True
            if not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "switches": [], "sensors": []})
                return True

            norm_port = _canonical_port(port)
            with _session_lock:
                try:
                    if _wstate._active_session is None or _canonical_port(_wstate._current_port) != norm_port:
                        if _wstate._active_session is not None:
                            try:
                                _wstate._active_session.close()
                            except Exception:
                                pass
                        _wstate._active_session = sc.JuraStatsSession(port_name=norm_port)
                        _wstate._current_port = norm_port
                        _wstate._consecutive_sensor_errors = 0
                        _wstate._last_sensor_payload = None

                    if _wstate._active_session.conn is not None and not _wstate._active_session.conn.is_open:
                        try:
                            _wstate._active_session.conn.close()
                        except Exception:
                            pass
                        _wstate._active_session.conn = None

                    if _wstate._active_session.conn is None or not _wstate._active_session.conn.is_open:
                        _wstate._active_session.conn = serial_io.JuraSerialConnection(norm_port)

                    eff_mfr = manufacturer
                    if eff_mfr == "auto":
                        p_up = port.upper()
                        if "NIVONA" in p_up:
                            eff_mfr = "nivona"
                        elif "LAMANTI-KL" in p_up or "KALERM" in p_up:
                            eff_mfr = "lamanti-kl"
                        elif "LAMANTI-JN" in p_up or "JETINNO" in p_up:
                            eff_mfr = "lamanti-jn"
                        elif getattr(_wstate._active_session, "detected_vendor", None):
                            eff_mfr = str(getattr(_wstate._active_session, "detected_vendor")).lower()

                    data = sc.query_live_sensors(
                        port_name=norm_port,
                        conn=_wstate._active_session.conn,
                        profile=_wstate._active_session.profile,
                        is_legacy=_wstate._active_session.is_legacy_cleartext,
                        fast_poll=fast_poll,
                        manufacturer=eff_mfr,
                    )

                    if isinstance(data, dict):
                        data.setdefault("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
                        data.setdefault("port", norm_port)

                    if data.get("error"):
                        raise IOError(str(data["error"]))

                    _wstate._consecutive_sensor_errors = 0
                    _wstate._last_sensor_payload = data
                except Exception as e:
                    _wstate._consecutive_sensor_errors += 1
                    err_msg = str(e)
                    is_fatal_disconnect = (
                        isinstance(e, (FileNotFoundError, PermissionError))
                        or "SerialException" in type(e).__name__
                        or "denied" in err_msg.lower()
                        or "does not exist" in err_msg.lower()
                        or "serial port is not open" in err_msg.lower()
                        or "enodev" in err_msg.lower()
                        or "input/output error" in err_msg.lower()
                        or "errno 5" in err_msg.lower()
                        or "errno 19" in err_msg.lower()
                    )

                    if is_fatal_disconnect or _wstate._consecutive_sensor_errors >= 3 or _wstate._last_sensor_payload is None:
                        # Full tear-down on fatal disconnect or sustained errors (>= 3)
                        if _wstate._active_session is not None:
                            try:
                                _wstate._active_session.close()
                            except Exception:
                                pass
                            _wstate._active_session = None
                        data = {
                            "error": err_msg,
                            "timestamp": time.strftime("%H:%M:%S"),
                            "switches": [],
                            "sensors": [],
                            "telemetry": {},
                        }
                    else:
                        # Debounce transient jitter / timeout: keep session alive and return last valid telemetry
                        data = copy.deepcopy(_wstate._last_sensor_payload)
                        data["timestamp"] = time.strftime("%H:%M:%S")
                        data["transient_retry"] = _wstate._consecutive_sensor_errors

            self._send_json(data)
            return True

        # 3. API: Full Interrogation & Statistics
        elif url.path == "/api/stats":
            port = params.get("port", [""])[0].strip()
            self._handle_stats_request(port)
            return True

        # 4. API: Optical Bean Threshold Calibration Info
        elif url.path == "/api/calibration":
            calib = sc.get_optical_bean_calibration()
            self._send_json(calib)
            return True

        # 4b. API: List Local EEPROM Offset Overrides
        elif url.path == "/api/offsets/overrides":
            try:
                self._send_json({"success": True, "overrides": profiles_db.list_eeprom_offset_overrides()})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "overrides": {}})
            return True

        # 4c. API: Unified Machine Library (Built-in Profiles + Model Specs + Local Overrides)
        elif url.path == "/api/machines":
            try:
                import machine_library
                ef = params.get("ef", [""])[0].strip()
                art = params.get("art", [""])[0].strip()
                mdl = params.get("model", [""])[0].strip()
                if not (ef or art or mdl):
                    with _session_lock:
                        cached_stats = copy.deepcopy(_wstate._last_stats_cache) if isinstance(_wstate._last_stats_cache, dict) else None
                    if isinstance(cached_stats, dict):
                        ef = str(cached_stats.get("ef_code") or "")
                        art = str(cached_stats.get("article_number") or "")
                        mdl = str(cached_stats.get("model_name") or cached_stats.get("model_family") or "")
                catalog = machine_library.list_machines(
                    detected_ef=ef,
                    detected_art=art,
                    detected_model=mdl,
                )
                catalog["success"] = True
                self._send_json(catalog)
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "machines": []})
            return True

        # 5. API: Branded Service Report (HTML Inspection Certificate)
        elif url.path == "/api/service_report":
            port = params.get("port", [""])[0].strip()
            lang = params.get("lang", ["en"])[0].strip().lower()
            is_cs = lang.startswith("cs")
            include_ai = params.get("ai_summary", ["0"])[0].lower() in ("1", "true", "yes")
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return True

            with _session_lock:
                summary = copy.deepcopy(_wstate._last_stats_cache) if isinstance(_wstate._last_stats_cache, dict) else None
                active_port = _wstate._current_port
            if summary is None or _canonical_port(active_port) != _canonical_port(port):
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
                return True

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

            try:
                telem = summary.get("telemetry") if isinstance(summary.get("telemetry"), dict) else {}
                report_archive.archive_report_async(
                    report_type="service_report",
                    content=html_content,
                    ext="html",
                    manufacturer=str(summary.get("vendor") or "Jura"),
                    model_name=str(summary.get("machine_model") or summary.get("appliance_type") or ""),
                    ef_code=str(summary.get("ef_code") or ""),
                    article_number=str(summary.get("article_number") or telem.get("article_number") or ""),
                    serial_number=str(summary.get("serial_number") or telem.get("serial_number") or ""),
                    total_cups=int(summary.get("total_cups") or 0),
                    health_score=int(score),
                    filename=build_export_filename(
                        "service_report",
                        summary.get("machine_model") or "appliance",
                        time.strftime("%Y%m%d_%H%M%S"),
                        "html",
                    ),
                    summary_text=(ai_summary_data or {}).get("customer_summary", ""),
                )
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._send_security_headers()
            self.end_headers()
            try:
                self.wfile.write(html_content.encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
            return True

        # 6. API: Export Data (JSON, CSV, Plain Text Report, Diagnostic Capture Bundle)
        elif url.path == "/api/export":
            port = params.get("port", [""])[0].strip()
            fmt = params.get("format", ["json"])[0].lower()
            save_dialog = params.get("save_dialog", ["0"])[0].lower() in ("1", "true", "yes")
            prefix = params.get("prefix", [""])[0]

            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port", "success": False})
                return True

            timestamp = time.strftime("%Y%m%d_%H%M%S")

            norm_port = _canonical_port(port)
            if fmt in ("capture", "dump"):
                with long_hardware_operation(), _session_lock:
                    # Full hardware diagnostic capture bundle (raw EEPROM + gateways)
                    safe_conn = _wstate._active_session.conn if (_wstate._active_session and _canonical_port(_wstate._current_port) == norm_port and _wstate._active_session.conn and _wstate._active_session.conn.is_open) else None
                    owns = False
                    if safe_conn is None:
                        safe_conn = serial_io.JuraSerialConnection(norm_port)
                        owns = True
                    try:
                        bundle = spectra_probe.capture_machine_bundle(
                            safe_conn,
                            on_progress=lambda *_a: touch_heartbeat(),
                        )
                    finally:
                        if owns:
                            safe_conn.close()

                    content = json.dumps(bundle, indent=2, ensure_ascii=False)
                    filename = build_export_filename(
                        "capture",
                        bundle.get("identity", {}).get("model_name") or "appliance",
                        timestamp,
                        "json",
                        prefix=prefix,
                    )
                    mime = "application/json; charset=utf-8"
                    ext = "json"
            else:
                with _session_lock:
                    # Resolve active session or fallback session for telemetry
                    session = _wstate._active_session if (_wstate._active_session and _canonical_port(_wstate._current_port) == norm_port) else None
                    if session is None:
                        session = sc.JuraStatsSession(port_name=norm_port)

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

                    filename = build_export_filename(
                        "export",
                        session.model_family or "appliance",
                        timestamp,
                        ext,
                        prefix=prefix,
                    )

            try:
                arc_meta = {}
                if fmt in ("capture", "dump"):
                    arc_ident = bundle.get("identity") or {}
                    arc_meta = {
                        "manufacturer": str(arc_ident.get("manufacturer") or "Jura"),
                        "model_name": str(arc_ident.get("model_name") or ""),
                        "ef_code": str(arc_ident.get("ef_code") or ""),
                        "article_number": str(arc_ident.get("article_number") or ""),
                        "serial_number": str(arc_ident.get("serial_number") or ""),
                    }
                else:
                    arc_meta = {
                        "manufacturer": str(getattr(session, "detected_vendor", None) or "Jura"),
                        "model_name": str(getattr(session, "model_family", "") or ""),
                        "ef_code": str(getattr(session, "ef_code", "") or ""),
                        "article_number": str((getattr(session, "telemetry", {}) or {}).get("article_number") or ""),
                        "serial_number": str((getattr(session, "telemetry", {}) or {}).get("serial_number") or ""),
                        "total_cups": int(getattr(session, "total_cups", 0) or 0),
                    }
                report_archive.archive_report_async(
                    report_type="capture" if fmt in ("capture", "dump") else f"export_{ext}",
                    content=content,
                    ext=ext,
                    ticket_prefix=sanitize_filename_prefix(prefix),
                    filename=filename,
                    **arc_meta,
                )
            except Exception:
                pass

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
                        return True

                    if not saved_path:
                        self._send_json({
                            "success": False,
                            "cancelled": True,
                            "message": "Save cancelled by user.",
                            "content": content,
                            "filename": filename,
                            "mime": mime
                        })
                        return True

                    with open(saved_path, "w", encoding="utf-8", newline="") as f:
                        f.write(content)
                    with _capture_cache_lock:
                        abs_saved = os.path.abspath(saved_path)
                        if abs_saved not in _written_capture_paths:
                            _written_capture_paths.append(abs_saved)
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
                return True

            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self._send_security_headers()
            self.end_headers()
            try:
                self.wfile.write(content.encode("utf-8") if isinstance(content, str) else content)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
            return True

        return False

    def _get_mapper(self, url, params) -> bool:
        # 7. API: Developer Memory Mapper Info [DEV ONLY]
        if url.path == "/api/mapper/info":
            port = params.get("port", [""])[0].strip()
            with long_hardware_operation(), _session_lock:
                try:
                    mapper, err = _get_or_create_mapper(port)
                    if mapper is None:
                        self._send_json({"error": err})
                        return True
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
                except Exception as e:
                    self._send_json({"error": str(e)})
            return True

        # 8. API: Developer Memory Mapper Sweep [DEV ONLY]
        elif url.path == "/api/mapper/sweep":
            port = params.get("port", [""])[0].strip()
            block_param = params.get("block", ["all"])[0].strip()
            self._handle_mapper_sweep_request(port, block_param)
            return True

        # 9. API: Developer Memory Mapper Diff [DEV ONLY]
        elif url.path == "/api/mapper/diff":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                try:
                    mapper, err = _get_or_create_mapper(port)
                    if mapper is None:
                        self._send_json({"error": err, "changed_registers": []})
                        return True
                    diff = mapper.compute_diff(mask_noise=True)
                    diff["changed_registers"] = [serialize_register_entry(r) for r in diff["changed_registers"]]
                    diff["summary"] = mapper.get_summary_stats()
                    self._send_json(diff)
                except Exception as e:
                    self._send_json({"error": str(e), "changed_registers": []})
            return True

        # 10. API: Developer Raw Sensor Telemetry & Field Breakdown [DEV ONLY]
        elif url.path == "/api/mapper/raw_sensors":
            port = params.get("port", [""])[0].strip()
            with _session_lock:
                try:
                    mapper, err = _get_or_create_mapper(port)
                    if mapper is None:
                        self._send_json({"error": err, "frames": {}, "fields": []})
                        return True
                    raw_data = _decode_raw_sensors(mapper)
                    self._send_json(raw_data)
                except Exception as e:
                    self._send_json({"error": str(e), "frames": {}, "fields": []})
            return True

        return False

    def _get_hmi(self, url, params) -> bool:
        # 10b. API: Kalerm HMI Dynamic Local Firmware Discovery
        if url.path == "/api/hmi/discover":
            try:
                import hmi_inspector
                search_dir = params.get("dir", [None])[0]
                allowed, safe_dir = _is_allowed_hmi_path(search_dir)
                if not allowed:
                    self._send_json(
                        {"success": False, "error": "Access denied: HMI discovery directory must reside in ~/Downloads, ~/Desktop, ~/Documents, or an approved browse folder", "targets": []},
                        status=403,
                    )
                    return True
                targets = hmi_inspector.KalermHmiInspector.discover_local_targets(safe_dir if search_dir else None)
                default_dir = os.path.expanduser("~/Downloads")
                self._send_json({
                    "success": True,
                    "targets": targets,
                    "default_dir": default_dir,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "targets": []})
            return True

        # 11. API: Kalerm HMI Info & Metadata
        elif url.path == "/api/hmi/info":
            raw_target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            allowed, target = _is_allowed_hmi_path(raw_target)
            if not allowed:
                self._send_json({"success": False, "error": "Access denied: HMI path outside approved folders"}, status=403)
                return True
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
            return True

        # 12. API: Kalerm HMI Automated Audit Findings
        elif url.path == "/api/hmi/audit":
            raw_target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            allowed, target = _is_allowed_hmi_path(raw_target)
            if not allowed:
                self._send_json({"success": False, "error": "Access denied: HMI path outside approved folders", "findings": []}, status=403)
                return True
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
            return True

        # 12b. API: Kalerm HMI 3-Tier Semantic Hybrid Audit & Glossary
        elif url.path == "/api/hmi/semantic":
            raw_target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            allowed, target = _is_allowed_hmi_path(raw_target)
            if not allowed:
                self._send_json({"success": False, "error": "Access denied: HMI path outside approved folders", "report": None}, status=403)
                return True
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
            return True

        # 12c. API: Kalerm HMI AI System Status & Hardware Profile
        elif url.path in ("/api/hmi/ai_status", "/api/hmi/ai/status"):
            try:
                import hmi_inspector
                status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
                status["semantic_progress"] = hmi_inspector.KalermHmiInspector.get_semantic_scan_progress()
                self._send_json({"success": True, "status": status})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        # 12d. API: Kalerm HMI Ollama Download & Engine Install Streaming Progress
        elif url.path in ("/api/hmi/ollama_progress", "/api/hmi/ollama/progress"):
            try:
                import hmi_inspector
                prog = hmi_inspector.KalermHmiInspector.get_ollama_download_progress()
                self._send_json({"success": True, "progress": prog})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "progress": {}})
            return True

        # 12e. API: Kalerm HMI Deep Semantic Hybrid Scan Streaming Progress
        elif url.path in ("/api/hmi/semantic/progress", "/api/hmi/semantic_progress"):
            try:
                import hmi_inspector
                prog = hmi_inspector.KalermHmiInspector.get_semantic_scan_progress()
                self._send_json({"success": True, "progress": prog})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "progress": {}})
            return True

        # 13. API: Kalerm HMI Languages List
        elif url.path == "/api/hmi/languages":
            raw_target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            allowed, target = _is_allowed_hmi_path(raw_target)
            if not allowed:
                self._send_json({"success": False, "error": "Access denied: HMI path outside approved folders", "languages": []}, status=403)
                return True
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
            return True

        # 14. API: Kalerm HMI Phrases Explorer
        elif url.path == "/api/hmi/phrases":
            raw_target = params.get("path", [""])[0].strip() or os.path.expanduser("~/Downloads")
            allowed, target = _is_allowed_hmi_path(raw_target)
            if not allowed:
                self._send_json({"success": False, "error": "Access denied: HMI path outside approved folders", "phrases": []}, status=403)
                return True
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
            return True

        return False

    def _get_system_and_history(self, url, params) -> bool:
        # API: Hidden Debug & Process Monitor Diagnostics & Ring-Buffer Logs
        if url.path == "/api/debug/status":
            with _debug_log_lock:
                logs_copy = list(_debug_log_buffer)
            err_cnt = sum(1 for x in logs_copy if x.get("level") == "ERROR")
            warn_cnt = sum(1 for x in logs_copy if x.get("level") == "WARN")
            diag = get_debug_diagnostics()
            self._send_json({
                "success": True,
                "build": __build__,
                "version": __version__,
                "offset_db_version": (diag.get("offset_db") or {}).get("offset_db_version", f"bundled-{__build__}"),
                "diagnostics": diag,
                "logs": logs_copy,
                "error_count": err_cnt,
                "warn_count": warn_cnt,
            })
            return True

        elif url.path == "/api/version":
            nonce = _get_sidecar_nonce()
            extra = {"X-Spectra-Nonce": nonce} if nonce else None
            try:
                import offset_db_sync
                odb_st = offset_db_sync.get_offset_db_status()
            except Exception:
                odb_st = {"offset_db_version": f"bundled-{__build__}", "source": "bundled_factory"}
            self._send_json({
                "success": True,
                "build": __build__,
                "version": __version__,
                "edition": __edition__,
                "offset_db_version": odb_st.get("offset_db_version", f"bundled-{__build__}"),
                "offset_db_source": odb_st.get("source", "bundled_factory"),
                "boot_id": _SERVER_BOOT_ID,
                "ui_prefs": load_ui_prefs(),
            }, extra_headers=extra)
            return True

        elif url.path == "/api/offsets_db/status":
            try:
                import offset_db_sync
                st = offset_db_sync.get_offset_db_status()
                self._send_json({"success": True, **st})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "offset_db_version": f"bundled-{__build__}"})
            return True

        elif url.path == "/api/offsets_db/check":
            try:
                import offset_db_sync
                force_val = (params.get("force", ["0"])[0] or "0").lower() in ("1", "true", "yes")
                res = offset_db_sync.check_for_offset_db_updates(force=force_val)
                # Strip raw manifest blob from public API response
                out = {k: v for k, v in res.items() if k != "manifest"}
                self._send_json(out)
            except Exception as e:
                self._send_json({"success": False, "ok": False, "update_available": False, "error": str(e)})
            return True

        elif url.path == "/api/ui_prefs":
            self._send_json({
                "success": True,
                "prefs": load_ui_prefs(),
            })
            return True

        elif url.path == "/api/update/check":
            force_val = (params.get("force", ["0"])[0] or "0").lower() in ("1", "true", "yes")
            info = updater.check_for_updates(force=force_val)
            self._send_json({
                "success": bool(info.get("ok", True)),
                **info,
            })
            return True

        elif url.path == "/api/update/status":
            self._send_json({
                "success": True,
                "boot_id": _SERVER_BOOT_ID,
                **updater.get_update_progress(),
            })
            return True

        elif url.path == "/api/github/auth/status":
            try:
                import github_auth
                self._send_json(github_auth.get_auth_status())
            except Exception as e:
                self._send_json({"authenticated": False, "login": None, "method": None, "device_flow_available": False, "error": str(e)})
            return True

        elif url.path == "/api/ai/status":
            try:
                import spectra_ai
                self._send_json({"success": True, **spectra_ai.get_ai_global_status()})
            except Exception as e:
                self._send_json({"success": False, "ai_enabled": False, "error": str(e)})
            return True

        elif url.path == "/api/reports/history":
            try:
                q_str = params.get("query", [""])[0].strip() or None
                serial_q = params.get("serial", [""])[0].strip() or None
                article_q = params.get("article", [""])[0].strip() or None
                cursor_q = params.get("cursor", [""])[0].strip() or None
                try:
                    lim_q = int(params.get("limit", ["50"])[0])
                except ValueError:
                    lim_q = 50
                res = report_archive.search_reports(
                    query=q_str,
                    serial_number=serial_q,
                    article_number=article_q,
                    limit=lim_q,
                    cursor=cursor_q,
                )
                self._send_json({"success": True, **res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e), "items": []})
            return True

        return False

    def do_GET(self):
        if not self._is_allowed_host():
            self._send_json({"error": "Forbidden host header", "success": False}, status=403)
            return

        url = urlparse(self.path)
        params = parse_qs(url.query)

        if not self._is_allowed_get_request(url.path):
            self._send_json({"error": "Forbidden cross-site API request", "success": False}, status=403)
            return

        if self._get_telemetry_and_exports(url, params):
            return
        if self._get_mapper(url, params):
            return
        if self._get_hmi(url, params):
            return
        if self._get_system_and_history(url, params):
            return

        # Static Assets (Compiled React App in web/dist)
        self._serve_static(url.path)
