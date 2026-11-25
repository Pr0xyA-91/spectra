#!/usr/bin/env python3
"""SPECTRA Web Server POST handlers for hardware commands, mapper, HMI, and app lifecycle."""

import os
import sys
import time
import json
import uuid
import threading
from typing import Dict, Any, Optional

import serial_io
import stats_collector as sc
import spectra_probe
import report_archive
from version import __version__, __build__, __edition__

from spectra_web import state as _wstate
from spectra_web.state import (
    PROJECT_DIR,
    _session_lock,
    _capture_cache_lock,
    _cached_captures,
    _written_capture_paths,
    _debug_log_lock,
    _debug_log_buffer,
    _shutdown_callbacks,
    cleanup_resources,
    long_hardware_operation,
    touch_heartbeat,
)
from spectra_web.security import (
    _approve_hmi_path,
    _is_allowed_hmi_path,
    build_export_filename,
    is_valid_port,
    log_debug_event,
    sanitize_filename_prefix,
)
from spectra_web.prefs import (
    reset_custom_sensor_mappings,
    load_custom_sensor_mappings,
    save_custom_sensor_mapping,
)
from spectra_web.sensors import (
    _canonical_port,
    _get_or_create_mapper,
    serialize_register_entry,
)


class PostHardwareRoutesMixin:
    """Hardware, mapper, HMI, and app-lifecycle POST handlers."""

    def _post_hw_and_mapper(self, url, data: Dict[str, Any]) -> bool:
        # 0. API: Full Interrogation & Statistics (POST) & Mapper Sweep (POST)
        if url.path == "/api/stats":
            port = str(data.get("port", "") or "").strip()
            self._handle_stats_request(port)
            return True

        if url.path == "/api/mapper/sweep":
            port = str(data.get("port", "") or "").strip()
            block_param = str(data.get("block", "all") or "all").strip()
            self._handle_mapper_sweep_request(port, block_param)
            return True

        # 1. API: Raw Command Injection (Safe prefixes or hex)
        if url.path == "/api/command":
            port = str(data.get("port", "") or "").strip()
            raw_cmd = data.get("cmd", "")

            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "success": False})
                return True
            if not isinstance(raw_cmd, str) or not raw_cmd.strip():
                self._send_json({"error": "No command specified", "success": False})
                return True
            if any(ord(ch) < 0x20 or ord(ch) >= 0x7F for ch in raw_cmd) or len(raw_cmd) > 64:
                self._send_json({
                    "error": "Refusing command: control characters, newlines, NUL bytes, or length > 64 are forbidden.",
                    "success": False,
                })
                return True

            try:
                cmd = serial_io.validate_readonly_command(raw_cmd)
            except PermissionError as pe:
                self._send_json({
                    "error": f"Refusing command '{raw_cmd.strip()}': {pe}",
                    "success": False,
                })
                return True
            cmd_upper = cmd.upper()

            norm_port = _canonical_port(port)
            with _session_lock:
                try:
                    def _dispatch_cmd(c_obj):
                        if cmd.startswith("@"):
                            enc_key = 0x42 if cmd_upper.startswith("@TF") else 0x20
                            return c_obj.query_encrypted(cmd + "\r\n", key=enc_key, timeout=1.2)
                        return c_obj.query_ascii(cmd, timeout=1.2)

                    if _wstate._active_session is not None and _canonical_port(_wstate._current_port) == norm_port and _wstate._active_session.conn and _wstate._active_session.conn.is_open:
                        resp = _dispatch_cmd(_wstate._active_session.conn)
                    else:
                        conn = serial_io.JuraSerialConnection(norm_port)
                        try:
                            resp = _dispatch_cmd(conn)
                        finally:
                            conn.close()
                    self._send_json({
                        "success": True,
                        "cmd": cmd,
                        "response": resp or "[NO_REPLY]",
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception as e:
                    self._send_json({"error": str(e), "success": False})
            return True

        # 1b. API: Diagnostic Hardware Dump Bundle Capture
        if url.path == "/api/export_capture":
            cached_id = str(data.get("capture_id") or "").strip()
            port = str(data.get("port") or "").strip()
            joe_csv = str(data.get("joe_csv") or "").strip()
            prefix = str(data.get("prefix") or "")
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
                        return True

                    norm_port = _canonical_port(port)
                    joe_data = spectra_probe.parse_joe_csv_text(joe_csv) if joe_csv else {}
                    with long_hardware_operation(), _session_lock:
                        safe_conn = _wstate._active_session.conn if (_wstate._active_session and _canonical_port(_wstate._current_port) == norm_port and _wstate._active_session.conn and _wstate._active_session.conn.is_open) else None
                        owns = False
                        if safe_conn is None:
                            safe_conn = serial_io.JuraSerialConnection(norm_port)
                            owns = True
                        try:
                            bundle = spectra_probe.capture_machine_bundle(
                                safe_conn,
                                joe_data=joe_data,
                                on_progress=lambda *_a: touch_heartbeat(),
                                use_ollama=False,
                            )
                        finally:
                            if owns:
                                safe_conn.close()

                    if use_ollama and joe_data and isinstance(bundle, dict):
                        raw_words = bundle.get("eeprom_words") or {}
                        eeprom_int = {}
                        for k_hex, w_val in raw_words.items():
                            try:
                                addr_i = int(str(k_hex), 16) if str(k_hex).lower().startswith("0x") else int(k_hex)
                                eeprom_int[addr_i] = int(w_val)
                            except Exception:
                                pass
                        bundle["correlations"] = spectra_probe.correlate_with_joe(
                            eeprom_int,
                            joe_data,
                            use_ollama=True,
                            ollama_model=ollama_model,
                        )

                    capture_id = uuid.uuid4().hex[:12]
                    with _capture_cache_lock:
                        _cached_captures[capture_id] = bundle
                        # Keep max 20 captures in memory
                        if len(_cached_captures) > 20:
                            oldest_k = next(iter(_cached_captures))
                            _cached_captures.pop(oldest_k, None)

                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = build_export_filename(
                    "capture",
                    bundle.get("identity", {}).get("model_name") or "appliance",
                    timestamp,
                    "json",
                    prefix=prefix,
                )

                try:
                    c_ident = bundle.get("identity") or {}
                    report_archive.archive_report_async(
                        report_type="capture",
                        content=json.dumps(bundle, indent=2, ensure_ascii=False),
                        ext="json",
                        ticket_prefix=sanitize_filename_prefix(prefix),
                        manufacturer=str(c_ident.get("manufacturer") or "Jura"),
                        model_name=str(c_ident.get("model_name") or ""),
                        ef_code=str(c_ident.get("ef_code") or ""),
                        article_number=str(c_ident.get("article_number") or ""),
                        serial_number=str(c_ident.get("serial_number") or ""),
                        filename=filename,
                    )
                except Exception:
                    pass

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
                            return True

                        if not saved_path:
                            self._send_json({
                                "success": False,
                                "cancelled": True,
                                "message": "Save cancelled by user.",
                                "capture_id": capture_id,
                                "filename": filename,
                                "bundle": bundle
                            })
                            return True

                        with open(saved_path, "w", encoding="utf-8", newline="") as f:
                            json.dump(bundle, f, indent=2, ensure_ascii=False)
                        with _capture_cache_lock:
                            abs_saved = os.path.abspath(saved_path)
                            if abs_saved not in _written_capture_paths:
                                _written_capture_paths.append(abs_saved)
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
                    return True

                self._send_json({
                    "success": True,
                    "capture_id": capture_id,
                    "filename": filename,
                    "bundle": bundle
                })
            except Exception as e:
                self._send_json({"error": str(e), "success": False})
            return True

        # 2. API: Set Optical Bean Sensor Threshold
        elif url.path == "/api/set_threshold":
            try:
                val = int(data.get("threshold", 115))
                new_t = sc.set_optical_bean_threshold(val, save=True)
                self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            except (ValueError, TypeError) as e:
                self._send_json({"success": False, "error": f"Invalid threshold value: {e}"}, status=400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return True

        # 3. API: Reset Optical Bean Sensor Threshold
        elif url.path == "/api/reset_threshold":
            try:
                new_t = sc.reset_optical_bean_threshold(save=True)
                self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return True

        # 4. API: Capture Baseline Reference [DEV ONLY]
        elif url.path == "/api/mapper/baseline":
            try:
                port = str(data.get("port", "") or "").strip()
                with _session_lock:
                    mapper, err = _get_or_create_mapper(port)
                    if mapper is None:
                        self._send_json({"error": err, "success": False})
                        return True
                    snap = mapper.capture_baseline()
                    summary = mapper.get_summary_stats()
                    self._send_json({
                        "success": True,
                        "timestamp": snap.timestamp,
                        "summary": summary
                    })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return True

        # 5. API: Map Register to Model Spec [DEV ONLY]
        elif url.path == "/api/mapper/map_register":
            try:
                port = str(data.get("port", "") or "").strip()
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
                        return True
                    ok, msg = mapper.map_register(addr, name, desc, category, unit, status)
                    self._send_json({
                        "success": ok,
                        "message": msg,
                        "summary": mapper.get_summary_stats(),
                        "registers": [serialize_register_entry(r) for r in mapper.classified_registers]
                    })
            except (ValueError, TypeError) as e:
                self._send_json({"success": False, "error": f"Invalid register payload: {e}"}, status=400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return True

        # 6. API: Map Sensor Field [DEV ONLY]
        elif url.path == "/api/mapper/map_sensor_field":
            try:
                field_key = str(data.get("key", "")).strip()
                if not field_key:
                    self._send_json({"error": "No sensor field key specified", "success": False}, status=400)
                    return True
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
            except (ValueError, TypeError) as e:
                self._send_json({"success": False, "error": f"Invalid sensor field payload: {e}"}, status=400)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return True

        # 7. API: Reset Custom Sensor Mappings to Defaults [DEV ONLY]
        elif url.path == "/api/mapper/reset_sensor_mappings":
            try:
                reset_custom_sensor_mappings()
                self._send_json({
                    "success": True,
                    "mappings": load_custom_sensor_mappings(),
                    "message": "Reset sensor mappings to defaults"
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return True
        return False

    def _post_hmi_and_app(self, url, data: Dict[str, Any]) -> bool:

        if url.path == "/api/hmi/browse":
            try:
                body = data
                initial_dir = body.get("initial_dir") or body.get("dir") or os.path.expanduser("~/Downloads")
                import hmi_inspector
                selected = hmi_inspector.KalermHmiInspector.prompt_file_browser(initial_dir)
                if selected:
                    _approve_hmi_path(selected)
                    self._send_json({"success": True, "path": selected})
                else:
                    self._send_json({"success": False, "cancelled": True})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/hmi/patch":
            try:
                body = data
                downloads_root = os.path.realpath(os.path.expanduser("~/Downloads"))
                raw_target = body.get("path") or downloads_root
                allowed, target = _is_allowed_hmi_path(raw_target)
                if not allowed:
                    self._send_json({"success": False, "error": "Access denied: HMI input path outside approved folders"}, status=403)
                    return True
                out_path = body.get("output_path") or None
                resolved_out: Optional[str] = None
                if out_path is not None:
                    out_str = str(out_path).strip()
                    if not os.path.isabs(out_str):
                        out_str = os.path.join(downloads_root, out_str)
                    resolved_out = os.path.realpath(out_str)
                    try:
                        in_downloads = os.path.commonpath([downloads_root, resolved_out]) == downloads_root
                    except ValueError:
                        in_downloads = False
                    if not in_downloads:
                        self._send_json({"success": False, "error": "Output path must reside inside ~/Downloads"}, status=403)
                        return True

                import hmi_inspector
                inspector = hmi_inspector.KalermHmiInspector(target)
                if resolved_out is None:
                    base, ext = os.path.splitext(os.path.basename(inspector.binary_path))
                    resolved_out = os.path.realpath(os.path.join(downloads_root, f"{base}_patched{ext}"))
                    try:
                        in_downloads = os.path.commonpath([downloads_root, resolved_out]) == downloads_root
                    except ValueError:
                        in_downloads = False
                    if not in_downloads:
                        self._send_json({"success": False, "error": "Output path must reside inside ~/Downloads"}, status=403)
                        return True
                res = inspector.apply_patches(resolved_out)
                self._send_json({"success": True, "result": res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/hmi/export_report":
            try:
                body = data
                downloads_root = os.path.realpath(os.path.expanduser("~/Downloads"))
                raw_target = body.get("path") or downloads_root
                allowed, target = _is_allowed_hmi_path(raw_target)
                if not allowed:
                    self._send_json({"success": False, "error": "Access denied: HMI input path outside approved folders"}, status=403)
                    return True
                fmt = body.get("format") or "md"
                target_locale = body.get("locale") or "cs-CZ"
                out_path = body.get("output_path")
                save_dialog = bool(body.get("save_dialog", False))
                used_save_dialog = False

                import hmi_inspector
                if save_dialog or (not out_path and not any("test" in arg for arg in sys.argv)):
                    def_out = f"SPECTRA_Firmware_Audit_Report_{target_locale}.{fmt}"
                    out_path = hmi_inspector.prompt_save_file_dialog(
                        default_filename=def_out,
                        title="Save SPECTRA Firmware Audit Report"
                    )
                    if not out_path:
                        self._send_json({"success": False, "cancelled": True, "message": "Save cancelled by user."})
                        return True
                    used_save_dialog = True

                if not out_path:
                    out_path = os.path.join(downloads_root, f"SPECTRA_Firmware_Audit_Report_{target_locale}.{fmt}")
                elif not os.path.isabs(str(out_path)):
                    out_path = os.path.join(downloads_root, str(out_path))

                if not used_save_dialog:
                    resolved_out = os.path.realpath(str(out_path))
                    try:
                        in_downloads = os.path.commonpath([downloads_root, resolved_out]) == downloads_root
                    except ValueError:
                        in_downloads = False
                    if not in_downloads:
                        self._send_json({"success": False, "error": "Output path must reside inside ~/Downloads"}, status=403)
                        return True
                    out_path = resolved_out

                inspector = hmi_inspector.KalermHmiInspector(target)
                saved = inspector.export_bug_report(out_path, format_type=fmt, target_locale=target_locale)
                self._send_json({"success": True, "saved_path": saved, "filename": os.path.basename(saved)})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/hmi/semantic":
            try:
                body = data
                raw_target = body.get("path") or os.path.expanduser("~/Downloads")
                allowed, target = _is_allowed_hmi_path(raw_target)
                if not allowed:
                    self._send_json({"success": False, "error": "Access denied: HMI path outside approved folders", "report": None}, status=403)
                    return True
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
            return True

        elif url.path in ("/api/hmi/ollama_control", "/api/hmi/ai/control"):
            try:
                body = data
                action = body.get("action", "")
                model = body.get("model")
                import hmi_inspector
                if action == "stop":
                    try:
                        import spectra_ai
                        res = spectra_ai.set_ai_enabled(False, model=model)
                        stop_res = res.get("stop_result") or {"status": "STOPPED"}
                        self._send_json({"success": True, "is_error": False, "result": stop_res, "ai_status": res["status"]["system"]})
                        return True
                    except Exception:
                        pass
                res = hmi_inspector.KalermHmiInspector.control_local_ollama(action=action, model=model)
                is_error = res.get("status") in ("ERROR", "BINARY_NOT_FOUND", "OLLAMA_OFFLINE", "START_TIMEOUT")
                ai_status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
                self._send_json({"success": not is_error, "is_error": is_error, "result": res, "ai_status": ai_status})
            except Exception as e:
                self._send_json({"success": False, "is_error": True, "error": str(e)})
            return True

        # 16. API: Native App Mode Lifecycle (Heartbeat & Window Closed)
        elif url.path == "/api/app/heartbeat":
            _wstate._last_heartbeat_time = time.time()
            self._send_json({"success": True, "status": "ALIVE"})
            return True

        elif url.path in ("/api/app/window_closed", "/api/app/close"):
            # When running inside legacy pywebview/GTK container, ignore beforeunload beacons
            # unless caller explicitly requests immediate shutdown.
            is_immediate = bool(isinstance(data, dict) and data.get("immediate"))
            if _wstate._is_native_webview and not is_immediate:
                self._send_json({"success": True, "status": "IGNORED_NATIVE_CONTAINER"})
                return True

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
                return True

            close_req_time = time.time()
            self._send_json({"success": True, "status": "TERMINATING"})
            def _deferred_exit_if_not_reloaded():
                # Allow 3.0s grace: if heartbeat received or page active, do not terminate!
                if time.time() - _wstate._last_heartbeat_time < 3.0:
                    return  # Page is still active (download, navigation, or refresh)
                cleanup_resources()
                for cb in list(_shutdown_callbacks):
                    try:
                        cb()
                    except Exception:
                        pass
                os._exit(0)
            threading.Timer(3.0, _deferred_exit_if_not_reloaded).start()
            return True

        # 17. API: Clear Debug Log Buffer
        elif url.path == "/api/debug/clear":
            with _debug_log_lock:
                _debug_log_buffer.clear()
            log_debug_event("INFO", "DEBUG", "Debug log cleared")
            self._send_json({"success": True})
            return True

        # 18. API: Push Frontend Client-Side Error to Debug Buffer
        elif url.path == "/api/debug/client_error":
            msg = data.get("message", "Unknown client-side error")
            details = data.get("details", "")
            src = data.get("source", "FRONTEND")
            log_debug_event("ERROR", src, msg, details)
            self._send_json({"success": True})
            return True

        # 19. API: Upload Telemetry Capture to Community Repository
        return False
