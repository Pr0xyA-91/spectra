#!/usr/bin/env python3
"""SPECTRA Web Server POST handlers for GitHub auth/issues, Local AI, offsets, prefs, and updates."""

import os
import re
import copy
import uuid
import time
import json
import platform
from typing import Dict, Any, List, Optional

import serial_io
import stats_collector as sc
import profiles_db
import spectra_probe
import updater
from version import __version__, __build__, __edition__

from spectra_web import state as _wstate
from spectra_web.state import (
    _session_lock,
    _capture_cache_lock,
    _cached_captures,
    _written_capture_paths,
    _debug_log_lock,
    _debug_log_buffer,
    long_hardware_operation,
    shutdown_for_restart,
    touch_heartbeat,
)
from spectra_web.security import invalidate_debug_ai_cache, is_valid_port, log_debug_event
from spectra_web.sensors import _canonical_port, compute_advisor_health
from spectra_web.prefs import save_ui_prefs


def _parse_eeprom_words_map(raw_words: Any) -> Dict[int, int]:
    """Convert an EEPROM dict keyed by hex strings or ints into {int_addr: int_val}."""
    out: Dict[int, int] = {}
    if not isinstance(raw_words, dict):
        return out
    for k, v in raw_words.items():
        if isinstance(v, bool):
            continue
        try:
            k_str = str(k).strip().lower()
            addr = int(k_str, 16) if k_str.startswith("0x") else (int(k_str, 16) if any(c in "abcdef" for c in k_str) else int(k_str, 10))
            if isinstance(v, int):
                val = v
            else:
                v_str = str(v).strip().lower()
                val = int(v_str, 16) if v_str.startswith("0x") else int(v_str, 10)
            if 0 <= addr <= 0xFFFF and 0 <= val <= 0xFFFF:
                out[addr] = val
        except (TypeError, ValueError):
            continue
    return out


def _expected_full_eeprom_words(sess: Any = None, ty_str: str = "") -> int:
    """Return expected word count for a full EEPROM sweep (512 for 4-digit, 256 for 2-digit, 48 for Smart Connect)."""
    if sess is not None:
        conn = getattr(sess, "conn", None)
        if conn is not None and getattr(conn, "_is_smart_connect", False):
            return 48
        if getattr(sess, "address_width", 4) == 2:
            return 256
    ty_up = str(ty_str or (getattr(sess, "ef_code", "") if sess is not None else "") or "").upper()
    try:
        from spectra_stats.calibration import TWO_DIGIT_ADDRESS_EFS
        if any(ty_up.startswith(prefix) for prefix in TWO_DIGIT_ADDRESS_EFS):
            return 256
    except Exception:
        pass
    return 512


def _is_partial_eeprom(eeprom_words: Any, sess: Any = None, ty_str: str = "") -> bool:
    """Return True when eeprom_words is missing or only contains a partial (~72-word) interrogation snapshot."""
    if not isinstance(eeprom_words, dict) or not eeprom_words:
        return True
    return len(eeprom_words) < _expected_full_eeprom_words(sess, ty_str)


def _merge_eeprom_into_session(sess: Any, raw_words: Any) -> int:
    """Merge swept/cached EEPROM words into an active JuraStatsSession.last_eeprom dictionary."""
    if sess is None or not raw_words:
        return 0
    parsed = _parse_eeprom_words_map(raw_words)
    if not parsed:
        return 0
    if not isinstance(getattr(sess, "last_eeprom", None), dict):
        sess.last_eeprom = {}
    sess.last_eeprom.update(parsed)
    return len(parsed)


class PostCloudAiRoutesMixin:
    """GitHub, Local AI, community offsets, UI preferences, and self-updater POST handlers."""

    def _post_github(self, url, data: Dict[str, Any]) -> bool:
        if url.path == "/api/upload-capture":
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
                abs_p = os.path.abspath(str(file_path))
                with _capture_cache_lock:
                    is_known_written = abs_p in _written_capture_paths
                if not is_known_written:
                    self._send_json({"success": False, "error": "Access denied: file_path must be a SPECTRA-recorded capture bundle."}, status=403)
                    return True
                if not os.path.isfile(abs_p):
                    self._send_json({"success": False, "error": f"File not found: {abs_p}"})
                    return True
                try:
                    with open(abs_p, "r", encoding="utf-8") as f:
                        bundle = json.load(f)
                except Exception as e:
                    self._send_json({"success": False, "error": f"Failed to read capture bundle: {e}"})
                    return True
            elif bundle is None:
                self._send_json({"success": False, "error": "Missing 'capture_id', 'file_path', or 'capture_data'"})
                return True

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
            return True

        # 20. API: GitHub OAuth Device Flow & Token Management
        elif url.path == "/api/github/auth/device/start":
            try:
                import github_auth
                res = github_auth.start_device_flow()
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/github/auth/device/poll":
            try:
                import github_auth
                device_code = data.get("device_code", "").strip()
                interval = int(data.get("interval", 5))
                res = github_auth.poll_device_flow(device_code, interval=interval)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/github/auth/token":
            try:
                import github_auth
                tok = data.get("token", "").strip()
                res = github_auth.set_pat(tok)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/github/auth/logout":
            try:
                import github_auth
                res = github_auth.logout()
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/github/report_issue":
            try:
                import github_auth

                raw_title = str(data.get("title") or "").strip()
                raw_desc = str(data.get("description") or "").strip()
                category = str(data.get("category") or "bug").strip().lower()
                include_env = bool(data.get("include_env", True))
                include_logs = bool(data.get("include_logs", False))
                mode = str(data.get("mode") or "api").strip().lower()
                machine_ctx = data.get("machine_context") if isinstance(data.get("machine_context"), dict) else {}

                if not raw_title or not raw_desc:
                    self._send_json(
                        {"success": False, "error": "Both issue title and description are required."},
                        status=400,
                    )
                    return True

                category_map = {
                    "bug": ("Bug Report", ["bug", "user-report"]),
                    "hardware": ("Machine / Protocol Support", ["hardware", "user-report"]),
                    "enhancement": ("Feature Request", ["enhancement", "user-report"]),
                    "ui": ("UI / Translation", ["ui", "user-report"]),
                }
                cat_title, labels = category_map.get(category, ("Bug Report", ["bug", "user-report"]))

                sections: List[str] = [
                    f"### Category\n{cat_title}",
                    f"### Description\n{github_auth.sanitize_issue_text(raw_desc, max_chars=24000)}",
                ]

                if include_env:
                    try:
                        import offset_db_sync
                        _odb_st = offset_db_sync.get_offset_db_status()
                        odb_ver = str(_odb_st.get("offset_db_version") or f"bundled-{__build__}")
                        odb_src = str(_odb_st.get("source") or "bundled_factory")
                    except Exception:
                        odb_ver = f"bundled-{__build__}"
                        odb_src = "bundled_factory"
                    env_lines = [
                        "### Environment & Machine Context",
                        f"- **SPECTRA Build**: `Build {__build__}` ({__edition__})",
                        f"- **Offset DB Version**: `{github_auth.sanitize_issue_text(odb_ver, 64)}` ({odb_src})",
                        f"- **OS / Platform**: `{platform.system()} {platform.release()} ({platform.machine()})`",
                        f"- **Python**: `{platform.python_version()}`",
                    ]
                    m_model = str(machine_ctx.get("model") or "").strip()[:100]
                    m_ef = str(machine_ctx.get("ef_code") or "").strip()[:40]
                    m_proto = str(machine_ctx.get("protocol") or "").strip()[:80]
                    m_port_type = str(machine_ctx.get("port_type") or "").strip()[:60]
                    if m_model:
                        env_lines.append(f"- **Machine Model**: `{github_auth.sanitize_issue_text(m_model, 100)}`")
                    if m_ef:
                        env_lines.append(f"- **EF Code**: `{github_auth.sanitize_issue_text(m_ef, 40)}`")
                    if m_proto:
                        env_lines.append(f"- **Protocol**: `{github_auth.sanitize_issue_text(m_proto, 80)}`")
                    if m_port_type:
                        env_lines.append(f"- **Connection Type**: `{github_auth.sanitize_issue_text(m_port_type, 60)}`")
                    sections.append("\n".join(env_lines))

                if include_logs:
                    with _debug_log_lock:
                        tail = list(_debug_log_buffer)[-25:]
                    if tail:
                        formatted_logs = []
                        for entry in tail:
                            ts = entry.get("ts") or entry.get("time") or ""
                            lvl = entry.get("level") or "INFO"
                            src = entry.get("source") or "SYS"
                            msg = entry.get("message") or ""
                            formatted_logs.append(f"[{ts}] [{lvl}] [{src}] {msg}")
                        sanitized_logs = github_auth.sanitize_issue_text("\n".join(formatted_logs), max_chars=4000)
                        sections.append(
                            "### Recent Debug Log (Sanitized)\n"
                            "<details>\n<summary>Last 25 log entries</summary>\n\n"
                            f"```text\n{sanitized_logs}\n```\n</details>"
                        )

                full_body = "\n\n".join(sections) + "\n"
                if mode == "url_only":
                    web_url = github_auth.build_github_issue_web_url(raw_title, full_body, labels=labels)
                    self._send_json({
                        "success": True,
                        "web_url": web_url,
                        "repo": github_auth.get_issues_repo(),
                    })
                    return True

                res = github_auth.create_github_issue(raw_title, full_body, labels=labels)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return True

        return False

    def _post_ai_and_offsets(self, url, data: Dict[str, Any]) -> bool:
        # 21. API: Central Local AI Toggle & Feature Endpoints (Default OFF)
        if url.path == "/api/ai/toggle":
            try:
                import spectra_ai
                enabled = bool(data.get("enabled", False))
                model = data.get("model")
                auto_unload = data.get("auto_unload")
                res = spectra_ai.set_ai_enabled(
                    enabled,
                    model=model,
                    auto_unload=auto_unload,
                    require_installed_model=True,
                    start_runtime=True,
                )
                invalidate_debug_ai_cache()
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/ai/config":
            try:
                import spectra_ai
                model = data.get("model")
                auto_unload = data.get("auto_unload")
                res = spectra_ai.update_ai_config(model=model, auto_unload=auto_unload)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/mapper/ai_suggest":
            try:
                import spectra_ai
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first.", "suggestions": []})
                    return True
                candidates = data.get("candidates") or []
                context_regs = data.get("context_registers") or []
                with _session_lock:
                    cached_model = (_wstate._last_stats_cache or {}).get("machine_model") if isinstance(_wstate._last_stats_cache, dict) else None
                machine_model = data.get("machine_model") or cached_model or "Coffee Machine"
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
            return True

        elif url.path == "/api/advisor/ai_triage":
            try:
                import spectra_ai
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return True
                with _session_lock:
                    cached_sensor = copy.deepcopy(_wstate._last_sensor_payload) if isinstance(_wstate._last_sensor_payload, dict) else None
                    cached_stats = copy.deepcopy(_wstate._last_stats_cache) if isinstance(_wstate._last_stats_cache, dict) else None
                telemetry = data.get("telemetry") or cached_sensor or {}
                stats_summary = data.get("stats") or cached_stats or {}
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
            return True

        elif url.path == "/api/service_report/ai_summary":
            try:
                import spectra_ai
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return True
                with _session_lock:
                    cached_stats = copy.deepcopy(_wstate._last_stats_cache) if isinstance(_wstate._last_stats_cache, dict) else None
                summary = data.get("stats") or cached_stats
                if not summary:
                    self._send_json({"success": False, "error": "Interrogate machine first before generating service summary."})
                    return True
                score, _ = compute_advisor_health(summary, {})
                model = data.get("model")
                lang = str(data.get("lang") or "en").strip().lower()
                res = spectra_ai.generate_customer_service_summary(summary, score, model=model, lang=lang)
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        # 22. API: Local AI EEPROM Offset Calibration from J.O.E. Reference
        elif url.path == "/api/ai/calibrate_offsets":
            try:
                import spectra_ai
                import spectra_probe
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return True

                capture_id = str(data.get("capture_id") or "").strip()
                bundle = data.get("bundle") or data.get("capture_data")
                port = str(data.get("port") or _wstate._current_port or "").strip()
                joe_csv = str(data.get("joe_csv") or "").strip()
                model = data.get("model")

                if not isinstance(bundle, dict) and capture_id:
                    with _capture_cache_lock:
                        bundle = _cached_captures.get(capture_id)

                if not isinstance(bundle, dict) or _is_partial_eeprom(bundle.get("eeprom_words"), _wstate._active_session):
                    if not port or not is_valid_port(port):
                        if not isinstance(bundle, dict):
                            self._send_json({"success": False, "error": "No captured EEPROM bundle or valid serial port provided."})
                            return True
                    else:
                        norm_port = _canonical_port(port)
                        joe_data = spectra_probe.parse_joe_csv_text(joe_csv) if joe_csv else {}
                        with long_hardware_operation(), _session_lock:
                            safe_conn = _wstate._active_session.conn if (_wstate._active_session and _canonical_port(_wstate._current_port) == norm_port and _wstate._active_session.conn and _wstate._active_session.conn.is_open) else None
                            owns = False
                            if safe_conn is None:
                                safe_conn = serial_io.JuraSerialConnection(norm_port)
                                owns = True
                            try:
                                swept = spectra_probe.capture_machine_bundle(
                                    safe_conn,
                                    joe_data=joe_data,
                                    on_progress=lambda *_a: touch_heartbeat(),
                                    use_ollama=True,
                                    ollama_model=model,
                                )
                            finally:
                                if owns:
                                    safe_conn.close()
                            if isinstance(swept, dict) and swept.get("eeprom_words"):
                                if not isinstance(bundle, dict) or len(swept["eeprom_words"]) >= len(bundle.get("eeprom_words") or {}):
                                    bundle = swept
                                if _wstate._active_session is not None and _canonical_port(_wstate._current_port) == norm_port:
                                    _merge_eeprom_into_session(_wstate._active_session, swept["eeprom_words"])

                # Inject J.O.E. CSV if user attached it after capturing EEPROM dump
                if joe_csv and not (bundle.get("joe_ground_truth") or {}).get("products"):
                    joe_data = spectra_probe.parse_joe_csv_text(joe_csv)
                    bundle = dict(bundle)
                    bundle["joe_ground_truth"] = joe_data

                ident_b = bundle.get("identity") if isinstance(bundle.get("identity"), dict) else {}
                u_model = str(data.get("user_model_name") or "").strip()
                u_art = str(data.get("user_article_number") or "").strip()
                u_serial = str(data.get("user_serial_number") or "").strip()
                u_market = str(data.get("user_market_region") or "").strip()
                if u_model or u_art or u_serial or u_market:
                    ident_b = dict(ident_b)
                    if u_model:
                        ident_b["model_name"] = u_model
                    if u_art:
                        ident_b["article_number"] = u_art
                    if u_serial:
                        ident_b["serial_number"] = u_serial
                    if u_market:
                        ident_b["market_region"] = u_market
                    bundle = dict(bundle)
                    bundle["identity"] = ident_b

                res = spectra_ai.calibrate_eeprom_offsets_from_joe(bundle, model=model)
                if res.get("success") and res.get("override"):
                    ov = dict(res["override"])
                    if u_model:
                        ov["model_name"] = u_model
                    if u_art:
                        ov["article_number"] = u_art
                    if u_serial:
                        ov["serial_number"] = u_serial
                    if u_market:
                        ov["market_region"] = u_market
                    res["override"] = ov
                    bundle = dict(bundle)
                    bundle["ai_offset_fix"] = ov
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
            return True

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

                if isinstance(override, dict):
                    override = dict(override)
                    for fk in ("model_name", "article_number", "serial_number", "market_region"):
                        fval = str(data.get(fk) or "").strip()
                        if fval:
                            override[fk] = fval
                    if not str(override.get("ef_code") or "").strip():
                        sess_ef = ""
                        with _session_lock:
                            if _wstate._active_session is not None:
                                sess_ef = str(getattr(_wstate._active_session, "ef_code", "") or "").strip()
                            if not sess_ef and isinstance(_wstate._last_stats_cache, dict):
                                sess_ef = str(_wstate._last_stats_cache.get("ef_code") or "").strip()
                        if sess_ef:
                            override["ef_code"] = sess_ef

                has_identity_fields = isinstance(override, dict) and any(
                    str(override.get(k) or "").strip()
                    for k in ("model_name", "article_number", "serial_number")
                )
                if not isinstance(override, dict) or (
                    not override.get("products") and not override.get("maintenance") and not has_identity_fields
                ):
                    self._send_json({"success": False, "error": "No valid EEPROM offset or identity override data provided."})
                    return True

                saved = profiles_db.save_eeprom_offset_override(
                    override,
                    model_key=data.get("model_key"),
                )

                updated_stats = None
                with _session_lock:
                    if _wstate._active_session is not None:
                        if capture_id:
                            with _capture_cache_lock:
                                cb = _cached_captures.get(capture_id) or {}
                            _merge_eeprom_into_session(_wstate._active_session, cb.get("eeprom_words"))
                        if isinstance(data.get("eeprom_words"), dict):
                            _merge_eeprom_into_session(_wstate._active_session, data.get("eeprom_words"))
                        if _wstate._active_session.apply_local_offset_override(override_data=saved):
                            updated_stats = _wstate._active_session.get_structured_summary()
                            score, cards = compute_advisor_health(updated_stats, {})
                            updated_stats["health_score"] = score
                            updated_stats["advisor_cards"] = cards
                            _wstate._last_stats_cache = updated_stats

                    if updated_stats is None and isinstance(_wstate._last_stats_cache, dict):
                        new_cache = copy.deepcopy(_wstate._last_stats_cache)
                        if saved.get("model_name"):
                            new_cache["machine_model"] = saved["model_name"]
                            new_cache["appliance_type"] = saved["model_name"]
                        if saved.get("article_number"):
                            new_cache["article_number"] = saved["article_number"]
                        if saved.get("serial_number"):
                            new_cache["serial_number"] = saved["serial_number"]
                        if saved.get("market_region"):
                            new_cache["market_region"] = saved["market_region"]

                        cached_words: Dict[int, int] = {}
                        if capture_id:
                            with _capture_cache_lock:
                                cb = _cached_captures.get(capture_id) or {}
                            cached_words.update(_parse_eeprom_words_map(cb.get("eeprom_words")))
                        if isinstance(data.get("eeprom_words"), dict):
                            cached_words.update(_parse_eeprom_words_map(data.get("eeprom_words")))

                        if saved.get("products"):
                            new_bevs = []
                            total_preps = 0
                            coffee_cups = 0
                            for idx, p in enumerate(saved["products"], start=1):
                                code = int(p.get("code") or idx)
                                pname = str(p.get("name") or f"Product #{code}")
                                is_dbl = bool(p.get("is_double", False))
                                addr_raw = p.get("addr") if p.get("addr") is not None else p.get("addr_hex")
                                try:
                                    addr_i = int(str(addr_raw), 16) if str(addr_raw).lower().startswith("0x") else int(addr_raw)
                                except Exception:
                                    addr_i = None
                                cnt = cached_words.get(addr_i, p.get("eeprom_val", p.get("joe_count", 0))) if addr_i is not None else p.get("eeprom_val", p.get("joe_count", 0))
                                cnt_i = int(cnt or 0)
                                total_preps += cnt_i
                                if not sc.is_non_coffee_product(pname, code):
                                    coffee_cups += (cnt_i * 2) if is_dbl else cnt_i
                                new_bevs.append({
                                    "code": code,
                                    "name": pname,
                                    "count": cnt_i,
                                    "is_double": is_dbl,
                                    "active": True,
                                })
                            new_cache["beverages"] = new_bevs
                            new_cache["total_preparations"] = total_preps
                            new_cache["total_cups"] = coffee_cups

                        if saved.get("maintenance"):
                            new_maint = []
                            for idx, m in enumerate(saved["maintenance"]):
                                mname = str(m.get("name") or "Maintenance")
                                addr_raw = m.get("addr") if m.get("addr") is not None else m.get("addr_hex")
                                try:
                                    addr_i = int(str(addr_raw), 16) if str(addr_raw).lower().startswith("0x") else int(addr_raw)
                                except Exception:
                                    addr_i = None
                                mcnt = cached_words.get(addr_i, m.get("eeprom_val", m.get("joe_count", 0))) if addr_i is not None else m.get("eeprom_val", m.get("joe_count", 0))
                                mcnt_i = int(mcnt or 0)
                                new_maint.append({
                                    "index": idx,
                                    "label": mname,
                                    "name": mname,
                                    "count": mcnt_i,
                                    "percentage": None,
                                    "percent": None,
                                })
                            new_cache["maintenance"] = new_maint

                        _wstate._last_stats_cache = new_cache
                        updated_stats = copy.deepcopy(new_cache)

                updated_bundle = None
                if capture_id:
                    with _capture_cache_lock:
                        if capture_id in _cached_captures and isinstance(_cached_captures[capture_id], dict):
                            _cached_captures[capture_id]["ai_offset_fix"] = saved
                            if isinstance(_cached_captures[capture_id].get("identity"), dict):
                                for fk in ("model_name", "article_number", "serial_number", "market_region"):
                                    if saved.get(fk):
                                        _cached_captures[capture_id]["identity"][fk] = saved[fk]
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
            return True

        elif url.path == "/api/offsets/delete":
            try:
                key = str(data.get("key") or "").strip()
                removed = profiles_db.delete_eeprom_offset_override(key) if key else False
                self._send_json({"success": True, "removed": removed, "overrides": profiles_db.list_eeprom_offset_overrides()})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        # 24. API: Calibrate EEPROM Offsets from Uploaded CSV, .txt Notes, or Screenshot (Overview Flow)
        elif url.path in ("/api/offsets/calibrate_upload", "/api/offsets/calibrate"):
            try:
                import spectra_ai
                import spectra_probe
                if not spectra_ai.is_ai_enabled():
                    self._send_json({"success": False, "error": "Local AI is turned OFF. Enable Local AI first."})
                    return True

                file_name = str(data.get("file_name") or ("manual_notes.txt" if data.get("user_notes") else "reference.csv")).strip()
                csv_text = data.get("csv_text")
                image_b64 = data.get("image_b64")
                user_notes = str(data.get("user_notes") or "").strip()
                user_model_name = str(data.get("user_model_name") or "").strip()
                user_article_number = str(data.get("user_article_number") or "").strip()
                user_serial_number = str(data.get("user_serial_number") or "").strip()
                user_market_region = str(data.get("user_market_region") or "").strip()
                port = str(data.get("port") or _wstate._current_port or "").strip()
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

                sess_snapshot = None
                with _session_lock:
                    sess = _wstate._active_session
                    sess_snapshot = sess
                    if sess is not None:
                        if not port and getattr(sess, "port_name", ""):
                            port = str(sess.port_name).strip()
                        if eeprom_words is None and getattr(sess, "last_eeprom", None):
                            eeprom_words = {f"0x{k:04X}": v for k, v in sess.last_eeprom.items()}
                        ty_str = ty_str or str(sess.ef_code or "")
                        model_name = model_name or str(sess.model_family or "")
                        article_number = article_number or str((sess.telemetry or {}).get("article_number") or "")

                # Overview flow MUST sweep the full 512-word (or 256-word 2-digit) EEPROM whenever
                # we only have a partial (~72-word) interrogation snapshot and counter ground-truth was supplied.
                has_counter_input = bool(
                    (isinstance(csv_text, str) and csv_text.strip())
                    or bool(image_b64)
                    or bool(user_notes)
                )
                need_full_sweep = has_counter_input and _is_partial_eeprom(eeprom_words, sess_snapshot, ty_str)

                if need_full_sweep and port and is_valid_port(port):
                    norm_port = _canonical_port(port)
                    swept_bundle = None
                    try:
                        with long_hardware_operation(), _session_lock:
                            safe_conn = (
                                _wstate._active_session.conn
                                if (
                                    _wstate._active_session
                                    and _canonical_port(_wstate._current_port) == norm_port
                                    and _wstate._active_session.conn
                                    and _wstate._active_session.conn.is_open
                                )
                                else None
                            )
                            owns = False
                            if safe_conn is None:
                                safe_conn = serial_io.JuraSerialConnection(norm_port)
                                owns = True
                            try:
                                swept_bundle = spectra_probe.capture_machine_bundle(
                                    safe_conn,
                                    joe_data={},
                                    on_progress=lambda *_a: touch_heartbeat(),
                                    use_ollama=False,
                                )
                            finally:
                                if owns:
                                    safe_conn.close()
                            if isinstance(swept_bundle, dict) and swept_bundle.get("eeprom_words"):
                                if _wstate._active_session is not None and (
                                    not _wstate._current_port or _canonical_port(_wstate._current_port) == norm_port
                                ):
                                    _merge_eeprom_into_session(_wstate._active_session, swept_bundle["eeprom_words"])
                    except Exception as sweep_err:
                        log_debug_event(
                            "WARN",
                            "API",
                            f"Overview full EEPROM sweep fallback to cached session words: {sweep_err}",
                        )
                        swept_bundle = None

                    if isinstance(swept_bundle, dict) and swept_bundle.get("eeprom_words"):
                        if not isinstance(eeprom_words, dict) or len(swept_bundle["eeprom_words"]) >= len(eeprom_words):
                            bundle = swept_bundle
                            eeprom_words = swept_bundle["eeprom_words"]
                            ident = swept_bundle.get("identity") or {}
                            ty_str = str(ident.get("ef_code") or (swept_bundle.get("gateways") or {}).get("TY:") or ty_str or "")
                            model_name = str(ident.get("model_name") or model_name or "")
                            article_number = str(ident.get("article_number") or article_number or "")

                if eeprom_words is None:
                    if user_model_name or user_article_number or user_serial_number or user_market_region:
                        eeprom_words = {}
                    else:
                        self._send_json({"success": False, "error": "Interrogate a connected machine first or attach a valid serial port."})
                        return True

                with _session_lock:
                    stats_snapshot = copy.deepcopy(_wstate._last_stats_cache) if isinstance(_wstate._last_stats_cache, dict) else None
                if isinstance(stats_snapshot, dict):
                    ty_str = ty_str or str(stats_snapshot.get("ef_code") or "")
                    model_name = model_name or str(stats_snapshot.get("model_name") or stats_snapshot.get("model_family") or "")
                    article_number = article_number or str(stats_snapshot.get("article_number") or "")

                res = spectra_ai.calibrate_offsets_from_upload(
                    eeprom_words=eeprom_words,
                    file_name=file_name,
                    csv_text=csv_text,
                    image_b64=image_b64,
                    ty_str=ty_str,
                    model_name=model_name,
                    article_number=article_number,
                    current_stats=stats_snapshot,
                    model=model,
                    user_notes=user_notes or None,
                    user_model_name=user_model_name or None,
                    user_article_number=user_article_number or None,
                    user_serial_number=user_serial_number or None,
                    user_market_region=user_market_region or None,
                )

                if res.get("success") and res.get("override"):
                    ov = res["override"]
                    res_ident = {
                        "manufacturer": "Jura",
                        "ef_code": ov.get("ef_code") or ty_str,
                        "model_name": ov.get("model_name") or model_name or "Unknown",
                        "article_number": ov.get("article_number") or article_number or "unknown",
                        "serial_number": ov.get("serial_number") or "",
                        "market_region": ov.get("market_region") or "",
                    }
                    if not isinstance(bundle, dict):
                        bundle = {
                            "metadata": {
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "spectra_build": __build__,
                                "probe_version": "1.1.0",
                                "port": port or "UNKNOWN",
                            },
                            "identity": res_ident,
                            "gateways": {"TY:": res_ident["ef_code"]},
                            "eeprom_words": eeprom_words,
                        }
                    else:
                        bundle = dict(bundle)
                        if not isinstance(bundle.get("metadata"), dict):
                            bundle["metadata"] = {
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "spectra_build": __build__,
                                "probe_version": "1.1.0",
                                "port": port or "UNKNOWN",
                            }
                        if not isinstance(bundle.get("gateways"), dict):
                            bundle["gateways"] = {"TY:": res_ident["ef_code"]}
                        merged_ident = dict(bundle.get("identity") or {})
                        merged_ident.update({k: v for k, v in res_ident.items() if v})
                        bundle["identity"] = merged_ident
                        bundle["eeprom_words"] = eeprom_words
                    if isinstance(res.get("joe_data"), dict) and not (bundle.get("joe_ground_truth") or {}).get("products"):
                        bundle["joe_ground_truth"] = res["joe_data"]
                    bundle["ai_offset_fix"] = ov
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
            return True

        # 25. API: Import Offset Patch (.json) into Unified Machine Library
        elif url.path == "/api/machines/import":
            try:
                import machine_library
                raw_patch = data.get("patch") or data.get("payload") or data
                ok, msg, saved = machine_library.import_offset_patch(raw_patch, model_key=data.get("model_key"))
                if not ok:
                    self._send_json({"success": False, "error": msg})
                    return True

                updated_stats = None
                with _session_lock:
                    if _wstate._active_session is not None and getattr(_wstate._active_session, "last_eeprom", None):
                        if _wstate._active_session.apply_local_offset_override():
                            updated_stats = _wstate._active_session.get_structured_summary()
                            score, cards = compute_advisor_health(updated_stats, {})
                            updated_stats["health_score"] = score
                            updated_stats["advisor_cards"] = cards
                            _wstate._last_stats_cache = updated_stats
                    stats_snapshot = copy.deepcopy(_wstate._last_stats_cache) if isinstance(_wstate._last_stats_cache, dict) else {}

                ef = str(stats_snapshot.get("ef_code") or "")
                art = str(stats_snapshot.get("article_number") or "")
                mdl = str(stats_snapshot.get("model_name") or stats_snapshot.get("model_family") or "")
                catalog = machine_library.list_machines(detected_ef=ef, detected_art=art, detected_model=mdl)
                catalog["success"] = True
                catalog["message"] = msg
                catalog["saved"] = saved
                catalog["updated_stats"] = updated_stats
                self._send_json(catalog)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

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
                    return True

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
                        return True
                    if not saved_path:
                        self._send_json({"success": False, "cancelled": True, "error": "Export cancelled by user."})
                        return True
                    with open(saved_path, "w", encoding="utf-8") as f:
                        f.write(patch_json)
                    self._send_json({
                        "success": True,
                        "saved_path": saved_path,
                        "filename": os.path.basename(saved_path),
                        "patch": patch,
                    })
                    return True

                self._send_json({
                    "success": True,
                    "filename": filename,
                    "patch_json": patch_json,
                    "patch": patch,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

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
                    return True

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
            return True

        elif url.path == "/api/offsets_db/sync":
            try:
                import offset_db_sync
                res = offset_db_sync.sync_offset_db()
                updated_stats = None
                if res.get("success"):
                    with _session_lock:
                        if _wstate._active_session is not None and getattr(_wstate._active_session, "last_eeprom", None):
                            if _wstate._active_session.apply_local_offset_override():
                                updated_stats = _wstate._active_session.get_structured_summary()
                                score, cards = compute_advisor_health(updated_stats, {})
                                updated_stats["health_score"] = score
                                updated_stats["advisor_cards"] = cards
                                _wstate._last_stats_cache = updated_stats
                if updated_stats is not None:
                    res["updated_stats"] = updated_stats
                self._send_json(res)
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        return False

    def _post_prefs_and_update(self, url, data: Dict[str, Any]) -> bool:
        # 28. API: Persist Host UI Preferences (Onboarding Seen & Language)
        if url.path == "/api/ui_prefs":
            try:
                prefs = save_ui_prefs(data if isinstance(data, dict) else {})
                self._send_json({"success": True, "prefs": prefs})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        # 29. API: Trigger Self-Update & Cancel Active Download
        elif url.path == "/api/update/apply":
            try:
                res = updater.start_self_update(on_before_restart=shutdown_for_restart)
                self._send_json({"success": bool(res.get("ok")), **res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        elif url.path == "/api/update/cancel":
            try:
                res = updater.cancel_self_update()
                self._send_json({"success": bool(res.get("ok")), **res})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return True

        return False
