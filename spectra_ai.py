#!/usr/bin/env python3
"""
SPECTRA Central Local AI Orchestrator (Ollama 127.0.0.1:11434)
==============================================================
Provides opt-in, default-OFF local LLM capabilities across SPECTRA:
1. Memory Mapper: EEPROM differential & unknown register labeling
2. Diagnostic Advisor: Live telemetry fault triage & bench checklist
3. Service Receipt: Customer-friendly plain-language inspection summary
4. J.O.E. Correlator: Cross-language beverage/maintenance label matching

Design invariants:
- Default state is strictly OFF (`_ai_enabled = False`) so zero RAM/CPU is used unless opted in.
- User can turn AI OFF at any time via `set_ai_enabled(False)`, cancelling active tasks and
  stopping/unloading the local Ollama model immediately.
- All long-running tasks publish live progress state for the global UI status bar.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import hmi_inspector

AI_CONFIG_FILE = os.path.join(os.path.expanduser("~/.config/spectra"), "ai_config.json")

_ai_lock = threading.Lock()
_ai_enabled: bool = False  # Always strictly OFF on startup so 0 RAM/CPU is used unless opted in
_preferred_model: str = ""
_auto_unload: bool = True
_cancel_epoch: int = 0


def _load_persisted_ai_prefs() -> None:
    global _preferred_model, _auto_unload
    if not os.path.exists(AI_CONFIG_FILE):
        return
    try:
        with open(AI_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            if cfg.get("preferred_model"):
                _preferred_model = str(cfg["preferred_model"]).strip()
            if "auto_unload" in cfg:
                _auto_unload = bool(cfg["auto_unload"])
    except Exception:
        pass


def _save_persisted_ai_prefs(preferred_model: str, auto_unload: bool) -> None:
    try:
        parent = os.path.dirname(AI_CONFIG_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = AI_CONFIG_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(
                {"preferred_model": preferred_model, "auto_unload": bool(auto_unload)},
                f,
                indent=2,
            )
        os.replace(tmp_path, AI_CONFIG_FILE)
    except Exception:
        pass


_load_persisted_ai_prefs()

_task_state: Dict[str, Any] = {
    "active": False,
    "task_id": "",
    "task_label": "",
    "step": "IDLE",
    "detail": "",
    "current": 0,
    "total": 0,
    "percent": 0,
    "eta_seconds": None,
    "model": "",
    "cancel_requested": False,
    "error": "",
    "started_at": 0.0,
}


def is_ai_enabled() -> bool:
    """Return True only when the user has explicitly enabled Local AI."""
    with _ai_lock:
        return bool(_ai_enabled)


def is_cancel_requested() -> bool:
    """Return True if the user turned AI OFF or requested task cancellation."""
    with _ai_lock:
        return bool(_task_state.get("cancel_requested")) or (not _ai_enabled)


def get_cancel_epoch() -> int:
    """Monotonic counter incremented each time the user explicitly turns AI OFF."""
    with _ai_lock:
        return _cancel_epoch


def get_preferred_model() -> str:
    with _ai_lock:
        return _preferred_model


def set_preferred_model(model: Optional[str]) -> None:
    global _preferred_model
    if model is not None:
        with _ai_lock:
            _preferred_model = str(model).strip()
            _save_persisted_ai_prefs(_preferred_model, _auto_unload)


def update_ai_config(model: Optional[str] = None, auto_unload: Optional[bool] = None) -> Dict[str, Any]:
    """Update persistent AI preferences (default model, auto_unload) without changing enabled state."""
    global _preferred_model, _auto_unload
    with _ai_lock:
        if model is not None:
            _preferred_model = str(model).strip()
        if auto_unload is not None:
            _auto_unload = bool(auto_unload)
        _save_persisted_ai_prefs(_preferred_model, _auto_unload)
    return {"success": True, **get_ai_global_status()}


def update_task_progress(
    *,
    active: Optional[bool] = None,
    task_id: Optional[str] = None,
    task_label: Optional[str] = None,
    step: Optional[str] = None,
    detail: Optional[str] = None,
    current: Optional[int] = None,
    total: Optional[int] = None,
    percent: Optional[int] = None,
    eta_seconds: Optional[int] = None,
    model: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Thread-safe update for the global AI progress status bar."""
    with _ai_lock:
        if active is not None:
            _task_state["active"] = bool(active)
            if active and _task_state.get("started_at", 0.0) <= 0.0:
                _task_state["started_at"] = time.time()
                _task_state["cancel_requested"] = False
            elif not active:
                _task_state["started_at"] = 0.0
        if task_id is not None:
            _task_state["task_id"] = task_id
        if task_label is not None:
            _task_state["task_label"] = task_label
        if step is not None:
            _task_state["step"] = step
        if detail is not None:
            _task_state["detail"] = detail
        if current is not None:
            _task_state["current"] = int(current)
        if total is not None:
            _task_state["total"] = int(total)
        if percent is not None:
            _task_state["percent"] = max(0, min(100, int(percent)))
        if eta_seconds is not None:
            _task_state["eta_seconds"] = eta_seconds
        if model is not None:
            _task_state["model"] = model
        if error is not None:
            _task_state["error"] = error


def get_task_progress() -> Dict[str, Any]:
    """Return current global AI task progress, including Firmware Inspector semantic audit if active."""
    with _ai_lock:
        task = dict(_task_state)

    if not task.get("active"):
        sem = hmi_inspector.KalermHmiInspector.get_semantic_scan_progress()
        if sem.get("active"):
            return {
                "active": True,
                "task_id": "semantic_audit",
                "task_label": "Firmware Semantic Audit",
                "step": sem.get("status", "SCANNING"),
                "detail": sem.get("detail_text") or sem.get("phase_label") or "Analyzing firmware localization...",
                "current": int(sem.get("current") or 0),
                "total": int(sem.get("total") or 0),
                "percent": int(round(float(sem.get("percent") or 0))),
                "eta_seconds": sem.get("eta_sec"),
                "model": sem.get("model") or "",
                "cancel_requested": False,
                "error": "",
            }
    return task


def _is_model_in_installed(model_id: str, installed: List[str]) -> bool:
    """Return True when `model_id` matches any locally installed Ollama model tag."""
    target = (model_id or "").strip()
    if not target or not installed:
        return False
    for raw_ins in installed:
        ins = raw_ins.strip()
        if not ins:
            continue
        if ins == target or ins == f"{target}:latest" or ins.startswith(f"{target}:"):
            return True
    return False


def set_ai_enabled(
    enabled: bool,
    model: Optional[str] = None,
    auto_unload: Optional[bool] = None,
    require_installed_model: bool = False,
) -> Dict[str, Any]:
    """
    Enable or disable Local AI globally.
    Turning OFF immediately cancels active AI tasks and stops/unloads the Ollama process.
    When `require_installed_model` is True, refuses to enable AI if 0 models are installed.
    """
    global _ai_enabled, _preferred_model, _auto_unload, _cancel_epoch

    if enabled and require_installed_model:
        sys_status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
        installed = [
            m.get("name") if isinstance(m, dict) else str(m)
            for m in ((sys_status.get("ollama") or {}).get("models") or [])
            if (m.get("name") if isinstance(m, dict) else str(m)).strip()
        ]
        if not installed:
            with _ai_lock:
                _ai_enabled = False
            return {
                "success": False,
                "requires_model_install": True,
                "ai_enabled": False,
                "error": "No local AI model is installed yet. Please download a model first.",
                "preferred_model": get_preferred_model(),
                "status": get_ai_global_status(),
            }

        req_model = str(model).strip() if model is not None else ""
        with _ai_lock:
            candidate = req_model or _preferred_model
            if not _is_model_in_installed(candidate, installed):
                _preferred_model = installed[0]
                _save_persisted_ai_prefs(_preferred_model, _auto_unload)
                model = _preferred_model

    with _ai_lock:
        _ai_enabled = bool(enabled)
        if model is not None and str(model).strip():
            _preferred_model = str(model).strip()
        if auto_unload is not None:
            _auto_unload = bool(auto_unload)
        if model is not None or auto_unload is not None:
            _save_persisted_ai_prefs(_preferred_model, _auto_unload)
        if not _ai_enabled:
            _cancel_epoch += 1
            _task_state["cancel_requested"] = True
            _task_state["active"] = False
            _task_state["step"] = "STOPPED"
            _task_state["detail"] = "Local AI turned off by user."
            _task_state["percent"] = 0
            _task_state["eta_seconds"] = None
        else:
            _task_state["cancel_requested"] = False
            _task_state["error"] = ""

    stop_result = None
    if not enabled:
        try:
            stop_result = hmi_inspector.KalermHmiInspector.control_local_ollama("stop")
        except Exception as e:
            stop_result = {"status": "ERROR", "message": str(e)}

    return {
        "success": True,
        "ai_enabled": is_ai_enabled(),
        "preferred_model": get_preferred_model(),
        "stop_result": stop_result,
        "status": get_ai_global_status(),
    }


def get_ai_global_status() -> Dict[str, Any]:
    """Return full global AI status: opt-in toggle state, active task progress, downloads, and hardware/daemon status."""
    sys_status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
    dl_prog = hmi_inspector.KalermHmiInspector.get_ollama_download_progress()
    task = get_task_progress()
    with _ai_lock:
        enabled = _ai_enabled
        pref_model = _preferred_model
        auto_unl = _auto_unload

    return {
        "ai_enabled": enabled,
        "preferred_model": pref_model or sys_status.get("hardware", {}).get("default_selected_model", ""),
        "auto_unload": auto_unl,
        "task": task,
        "download": dl_prog,
        "system": sys_status,
    }


def _is_vision_model(model_name: str) -> bool:
    low = (model_name or "").lower()
    return any(
        tok in low
        for tok in ("gemma3:4b", "gemma3:12b", "gemma3:27b", "vl", "llava", "minicpm-v", "vision", "moondream", "bakllava")
    )


def _resolve_active_model(
    requested_model: Optional[str] = None,
    require_vision: bool = False,
) -> Tuple[bool, str, Optional[str]]:
    """
    Ensure Local AI is enabled, the local runtime is reachable (starting if installed),
    and select an installed model. Returns (ok, model_name, error_msg).
    """
    if not is_ai_enabled():
        return False, "", "Local AI is currently OFF. Enable Local AI to run this feature."

    cls = hmi_inspector.KalermHmiInspector
    chk = cls.check_local_ollama(timeout=0.5)
    if not chk.get("available"):
        start_res = cls.control_local_ollama("start")
        if start_res.get("status") not in ("ALREADY_RUNNING", "STARTED", "SUCCESS"):
            return False, "", start_res.get("message") or "Local AI runtime is unavailable."
        chk = cls.check_local_ollama(timeout=1.0)

    if not chk.get("available"):
        return False, "", "Local AI runtime on 127.0.0.1:11434 is not responding."

    installed = [m.get("name") if isinstance(m, dict) else str(m) for m in (chk.get("models") or [])]
    installed = [m for m in installed if m]
    if not installed:
        return False, "", "No Local AI models installed. Open Config -> Local AI & Models to pull a model."

    cand = (requested_model or get_preferred_model() or "").strip()
    if require_vision:
        if cand and _is_vision_model(cand):
            for m in installed:
                if m == cand or m.startswith(cand + ":"):
                    return True, m, None
        vision_installed = [m for m in installed if _is_vision_model(m)]
        if vision_installed:
            return True, vision_installed[0], None
        return (
            False,
            "",
            "No vision-capable Local AI model installed (e.g. gemma3:4b). Pull 'gemma3:4b' in Config -> Local AI & Models to read screenshots, or upload a CSV file.",
        )

    if cand and cand in installed:
        return True, cand, None
    if cand:
        # Match prefix (e.g. 'qwen2.5:1.5b' vs 'qwen2.5:1.5b-instruct')
        for m in installed:
            if m == cand or m.startswith(cand + ":"):
                return True, m, None
    return True, installed[0], None


def _parse_json_response(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if "{" in text and "}" in text:
        text = text[text.index("{"):text.rindex("}") + 1]
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _query_ollama_json(
    prompt: str,
    model: str,
    timeout: float = 90.0,
    temperature: float = 0.15,
    images: Optional[List[str]] = None,
    num_ctx: int = 2048,
    num_predict: int = 512,
    max_wall_time: float = 240.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Invoke local AI /api/generate with NDJSON streaming + cancellation support."""
    if is_cancel_requested():
        return None, "Cancelled by user (AI turned off)."

    sys_status = hmi_inspector.KalermHmiInspector.get_ai_system_status()
    threads = int(sys_status.get("hardware", {}).get("recommended_threads", 2) or 2)

    req_body: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "format": "json",
        "options": {
            "num_thread": threads,
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
        "keep_alive": "5m",
    }
    if images:
        req_body["images"] = images

    payload = json.dumps(req_body).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "SPECTRA-Local-AI"},
    )
    t_start = time.time()
    accumulated: List[str] = []
    token_count = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None, f"Local AI HTTP {resp.status}"
            for raw_line in resp:
                if is_cancel_requested():
                    return None, "Cancelled by user (AI turned off)."
                elapsed = time.time() - t_start
                if elapsed > max_wall_time:
                    return None, f"Local AI inference exceeded {int(max_wall_time)}s wall-clock limit."

                line_str = raw_line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                try:
                    chunk = json.loads(line_str)
                except Exception:
                    continue
                if chunk.get("error"):
                    return None, f"Local AI runtime error: {chunk.get('error')}"
                piece = chunk.get("response") or ""
                if piece:
                    accumulated.append(piece)
                    token_count += 1
                    if token_count == 1 or token_count % 8 == 0:
                        update_task_progress(
                            detail=f"Streaming from {model} ({token_count} chunks, {int(elapsed)}s)..."
                        )
                if chunk.get("done"):
                    break

            raw_response = "".join(accumulated).strip()
            if not raw_response:
                return None, "Local AI returned an empty response."
            parsed = _parse_json_response(raw_response)
            return parsed, None
    except urllib.error.HTTPError as he:
        return None, f"Local AI HTTP {he.code}: {he.reason}"
    except Exception as e:
        return None, f"Local AI query error: {e}"


def _maybe_auto_unload(model: str) -> None:
    with _ai_lock:
        should_unload = _auto_unload
    if should_unload and model:
        try:
            hmi_inspector.KalermHmiInspector.control_local_ollama("unload", model)
        except Exception:
            pass


def suggest_eeprom_mappings(
    candidates: List[Dict[str, Any]],
    context_registers: Optional[List[Dict[str, Any]]] = None,
    machine_model: str = "Coffee Machine",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Use local Ollama to suggest register names, categories, units, and bitflag hypotheses
    for changed or unknown EEPROM words in Memory Mapper.
    """
    ok, active_model, err = _resolve_active_model(model)
    if not ok:
        return {"success": False, "error": err, "suggestions": []}

    target_items = list(candidates[:12])
    if not target_items:
        return {"success": False, "error": "No changed or unknown EEPROM registers supplied.", "suggestions": []}

    ctx_lines = []
    for r in (context_registers or [])[:25]:
        ctx_lines.append(
            f"0x{int(r.get('addr', 0)):04X}: val={r.get('val')} name='{r.get('name')}' cat={r.get('category')}"
        )
    ctx_block = "\n".join(ctx_lines) if ctx_lines else "None provided"

    suggestions: List[Dict[str, Any]] = []
    total = len(target_items)
    t0 = time.time()

    update_task_progress(
        active=True,
        task_id="mem_mapper",
        task_label="Memory Mapper AI Labeling",
        step="INITIALIZING",
        detail=f"Analyzing {total} EEPROM register(s) with {active_model}...",
        current=0,
        total=total,
        percent=5,
        eta_seconds=total * 2,
        model=active_model,
        error="",
    )

    try:
        for idx, item in enumerate(target_items):
            if is_cancel_requested():
                return {"success": False, "cancelled": True, "error": "AI turned off by user.", "suggestions": suggestions}

            addr_hex = str(item.get("addr_hex") or f"{int(item.get('addr', 0)):04X}").upper()
            elapsed = time.time() - t0
            eta = int(((elapsed / idx) if idx > 0 else 2.5) * (total - idx))
            pct = int(10 + 85 * (idx / max(1, total)))

            update_task_progress(
                active=True,
                step="ANALYZING_REGISTER",
                detail=f"Register 0x{addr_hex} ({idx + 1}/{total})",
                current=idx + 1,
                total=total,
                percent=pct,
                eta_seconds=max(0, eta),
                model=active_model,
            )

            prompt = (
                f"You are reverse-engineering EEPROM registers on a {machine_model} espresso machine.\n"
                f"Nearby known registers:\n{ctx_block}\n\n"
                f"Target unknown/changed register:\n"
                f"- Address: 0x{addr_hex}\n"
                f"- Current value: {item.get('val')} (hex 0x{int(item.get('val', 0)):04X})\n"
                f"- Previous value: {item.get('prev_val', 'unknown')}\n"
                f"- Bit flips: {item.get('flips', [])}\n"
                f"- Current status: {item.get('status', 'unknown')}\n\n"
                "Respond in JSON only with keys:\n"
                "\"suggested_name\" (concise string), \"category\" (one of: counters, maintenance, settings, alerts, telemetry, system), "
                "\"unit\" (e.g. \"cups\", \"pulses\", \"°C\", \"flags\", \"\"), \"confidence\" (\"low\"|\"medium\"|\"high\"), "
                "\"reasoning\" (1-2 short sentences)."
            )

            parsed, q_err = _query_ollama_json(prompt, active_model)
            if parsed:
                suggestions.append({
                    "addr": item.get("addr"),
                    "addr_hex": addr_hex,
                    "val": item.get("val"),
                    "suggested_name": str(parsed.get("suggested_name") or f"Register 0x{addr_hex}")[:64],
                    "category": str(parsed.get("category") or "settings"),
                    "unit": str(parsed.get("unit") or ""),
                    "confidence": str(parsed.get("confidence") or "low"),
                    "reasoning": str(parsed.get("reasoning") or "Suggested from register delta and nearby memory context."),
                })
            elif q_err and "Cancelled" in q_err:
                return {"success": False, "cancelled": True, "error": q_err, "suggestions": suggestions}

        update_task_progress(active=False, step="COMPLETED", detail=f"Generated {len(suggestions)} register suggestions.", current=total, total=total, percent=100, eta_seconds=0)
        return {"success": True, "model": active_model, "suggestions": suggestions}
    finally:
        _maybe_auto_unload(active_model)
        update_task_progress(active=False)


def analyze_fault_triage(
    telemetry: Dict[str, Any],
    stats_summary: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Use local Ollama to produce a structured technician bench triage summary & check list
    from live machine telemetry and interrogated fault history.
    """
    ok, active_model, err = _resolve_active_model(model)
    if not ok:
        return {"success": False, "error": err}

    is_cs = str(lang).lower().startswith("cs")
    update_task_progress(
        active=True,
        task_id="fault_triage",
        task_label="AI servisní diagnostika" if is_cs else "AI Bench Fault Triage",
        step="ANALYZING_TELEMETRY",
        detail=f"Vyhodnocuji senzory a historii chyb pomocí {active_model}..." if is_cs else f"Evaluating live sensors & fault latch with {active_model}...",
        current=1,
        total=2,
        percent=35,
        eta_seconds=4,
        model=active_model,
        error="",
    )

    try:
        machine_model = (stats_summary or {}).get("machine_model") or telemetry.get("machine_model") or "Coffee Machine"
        compact_ctx = {
            "machine_model": machine_model,
            "machine_ready": telemetry.get("machine_ready"),
            "tb1_temp_c": telemetry.get("heater_coffee_c"),
            "tb2_temp_c": telemetry.get("heater_steam_c"),
            "flow_rate_mls": telemetry.get("flow_rate_mls"),
            "bu_pos": telemetry.get("bu_pos"),
            "switches": [
                {"id": s.get("id"), "ok": s.get("ok"), "status": s.get("status")}
                for s in (telemetry.get("switches") or [])[:10]
            ],
            "alerts": (stats_summary or {}).get("alerts", [])[:8],
            "health_score": (stats_summary or {}).get("health_score"),
            "last_fault_raw": telemetry.get("last_fault_str") or telemetry.get("fault_latch"),
        }

        lang_note = " Write all text values (summary, probable_causes, bench_checks) in natural Czech (čeština)." if is_cs else ""
        prompt = (
            "You are a senior espresso machine bench technician. Analyze this telemetry snapshot and provide practical diagnostic triage.\n"
            f"Telemetry JSON:\n{json.dumps(compact_ctx, ensure_ascii=False)}\n\n"
            "Respond in JSON only with keys:\n"
            "\"summary\" (2-3 sentence diagnosis), "
            "\"urgency\" (\"LOW\"|\"MEDIUM\"|\"HIGH\"), "
            "\"probable_causes\" (array of up to 3 short strings), "
            "\"bench_checks\" (array of up to 4 actionable technician check steps)."
            f"{lang_note}"
        )

        parsed, q_err = _query_ollama_json(prompt, active_model)
        if not parsed:
            return {"success": False, "error": q_err or "Failed to generate fault triage."}

        update_task_progress(active=False, step="COMPLETED", detail="Fault triage complete.", current=2, total=2, percent=100, eta_seconds=0)
        return {
            "success": True,
            "model": active_model,
            "triage": {
                "summary": str(parsed.get("summary") or "Telemetry evaluated."),
                "urgency": str(parsed.get("urgency") or "LOW").upper(),
                "probable_causes": [str(x) for x in (parsed.get("probable_causes") or [])[:4]],
                "bench_checks": [str(x) for x in (parsed.get("bench_checks") or [])[:5]],
            },
        }
    finally:
        _maybe_auto_unload(active_model)
        update_task_progress(active=False)


def generate_customer_service_summary(
    summary: Dict[str, Any],
    health_score: int,
    model: Optional[str] = None,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Generate a concise, jargon-free customer handoff summary for the service inspection certificate.
    """
    ok, active_model, err = _resolve_active_model(model)
    if not ok:
        return {"success": False, "error": err}

    is_cs = str(lang).lower().startswith("cs")
    update_task_progress(
        active=True,
        task_id="service_summary",
        task_label="Zpráva pro zákazníka" if is_cs else "Customer Service Summary",
        step="GENERATING_NOTE",
        detail=f"Píši srozumitelný souhrn pomocí {active_model}..." if is_cs else f"Writing plain-language handoff summary with {active_model}...",
        current=1,
        total=2,
        percent=40,
        eta_seconds=4,
        model=active_model,
        error="",
    )

    try:
        compact = {
            "machine_model": summary.get("machine_model", "Coffee Machine"),
            "total_cups": summary.get("total_cups", 0),
            "health_score": health_score,
            "maintenance": summary.get("maintenance", [])[:6],
            "alerts": summary.get("alerts", [])[:5],
        }
        lang_note = " Write all text values in natural, polite Czech (čeština)." if is_cs else ""
        prompt = (
            "Write a friendly, concise customer service handoff note (no raw hex codes) for an espresso machine inspection certificate.\n"
            f"Inspection data:\n{json.dumps(compact, ensure_ascii=False)}\n\n"
            "Respond in JSON only with keys:\n"
            "\"customer_summary\" (3-4 plain-language sentences), "
            "\"recommended_next_service\" (1 short sentence)."
            f"{lang_note}"
        )
        parsed, q_err = _query_ollama_json(prompt, active_model)
        if not parsed:
            return {"success": False, "error": q_err or "Failed to generate customer summary."}

        update_task_progress(active=False, step="COMPLETED", detail="Customer summary ready.", current=2, total=2, percent=100, eta_seconds=0)
        return {
            "success": True,
            "model": active_model,
            "customer_summary": str(parsed.get("customer_summary") or ""),
            "recommended_next_service": str(parsed.get("recommended_next_service") or ""),
        }
    finally:
        _maybe_auto_unload(active_model)
        update_task_progress(active=False)


def match_joe_labels_with_ai(
    unmatched_labels: List[str],
    canonical_names: List[str],
    model: Optional[str] = None,
) -> Dict[str, str]:
    """
    Optional AI fallback to translate/match localized J.O.E. beverage or maintenance labels
    to canonical SPECTRA counter names. Returns {original_label: canonical_name}.
    """
    if not unmatched_labels or not canonical_names:
        return {}

    ok, active_model, _ = _resolve_active_model(model)
    if not ok:
        return {}

    items = list(unmatched_labels[:20])
    update_task_progress(
        active=True,
        task_id="joe_match",
        task_label="J.O.E. Cross-Language Matching",
        step="MATCHING_LABELS",
        detail=f"Normalizing {len(items)} localized J.O.E. labels with {active_model}...",
        current=1,
        total=2,
        percent=45,
        eta_seconds=4,
        model=active_model,
        error="",
    )

    try:
        prompt = (
            "Map each localized coffee machine beverage/maintenance label to the closest canonical English name from the candidate list, or empty string if none fits.\n"
            f"Unmatched labels: {json.dumps(items, ensure_ascii=False)}\n"
            f"Canonical candidates: {json.dumps(canonical_names[:40], ensure_ascii=False)}\n"
            "Respond in JSON only with a single key \"mappings\" mapping each unmatched label to a canonical candidate string (or \"\")."
        )
        parsed, _ = _query_ollama_json(prompt, active_model)
        raw_map = (parsed or {}).get("mappings")
        out: Dict[str, str] = {}
        if isinstance(raw_map, dict):
            canon_set = set(canonical_names)
            for k, v in raw_map.items():
                if isinstance(k, str) and isinstance(v, str) and v in canon_set:
                    out[k] = v
        update_task_progress(active=False, step="COMPLETED", detail=f"Matched {len(out)} J.O.E. labels.", current=2, total=2, percent=100, eta_seconds=0)
        return out
    finally:
        _maybe_auto_unload(active_model)
        update_task_progress(active=False)


def _parse_eeprom_addr(raw_addr: Any) -> Optional[int]:
    if isinstance(raw_addr, int):
        return raw_addr if raw_addr >= 0 else None
    s = str(raw_addr or "").strip().lower()
    if not s:
        return None
    try:
        return int(s, 16) if s.startswith("0x") or any(c in "abcdef" for c in s) else int(s, 10)
    except ValueError:
        return None


def calibrate_eeprom_offsets_from_joe(
    bundle: Dict[str, Any],
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Use deterministic J.O.E. value correlation + Local Ollama disambiguation to produce
    a verified EEPROM offset map for machines whose counters/maintenance are mis-read.

    Every address returned is verified against actual `eeprom_words` so Ollama cannot
    hallucinate invalid offsets.
    """
    ok, active_model, err = _resolve_active_model(model)
    if not ok:
        return {"success": False, "error": err}

    if not isinstance(bundle, dict):
        return {"success": False, "error": "Invalid capture bundle."}

    raw_words = bundle.get("eeprom_words") or {}
    joe_data = bundle.get("joe_ground_truth") or {}
    if not raw_words:
        return {"success": False, "error": "Capture bundle contains no EEPROM words."}
    if not joe_data or (not joe_data.get("products") and not joe_data.get("maintenance") and not joe_data.get("cockpit")):
        return {"success": False, "error": "Attach a valid J.O.E. CSV export first to calibrate EEPROM offsets."}

    eeprom_int: Dict[int, int] = {}
    for k, v in raw_words.items():
        addr_i = _parse_eeprom_addr(k)
        if addr_i is not None and isinstance(v, int):
            eeprom_int[addr_i] = v

    if not eeprom_int:
        return {"success": False, "error": "Failed to parse EEPROM word table from capture bundle."}

    update_task_progress(
        active=True,
        task_id="offset_calibrate",
        task_label="AI EEPROM Offset Calibration",
        step="CORRELATING_JOE",
        detail=f"Cross-referencing J.O.E. counts against {len(eeprom_int)} EEPROM words...",
        current=1,
        total=3,
        percent=20,
        eta_seconds=6,
        model=active_model,
        error="",
    )

    try:
        if is_cancel_requested():
            return {"success": False, "cancelled": True, "error": "Cancelled by user (AI turned off)."}

        import spectra_probe
        correlations = spectra_probe.correlate_with_joe(
            eeprom_int, joe_data, use_ollama=False
        )

        # Build compact non-zero bank context around known counter blocks
        bank_ranges = [
            range(0x0000, 0x0040),
            range(0x00E0, 0x0100),
            range(0x0160, 0x01F0),
            range(0x0330, 0x0350),
        ]
        bank_words = {}
        for r in bank_ranges:
            for a in r:
                if a in eeprom_int and eeprom_int[a] != 0:
                    bank_words[f"0x{a:04X}"] = eeprom_int[a]

        ident = bundle.get("identity") or {}
        gateways = bundle.get("gateways") or {}
        ty_str = str(gateways.get("TY:") or "").replace("ty:", "").replace("TY:", "").strip()
        model_name = str(ident.get("model_name") or joe_data.get("model_name") or "Unknown Jura").strip()
        article_number = str(ident.get("article_number") or "unknown").strip()

        update_task_progress(
            active=True,
            step="AI_DISAMBIGUATION",
            detail=f"Disambiguating candidate EEPROM banks & percentages with {active_model}...",
            current=2,
            total=3,
            percent=55,
            eta_seconds=4,
            model=active_model,
        )

        prompt_ctx = {
            "machine": {"model_name": model_name, "ef_code": ty_str, "article_number": article_number},
            "joe_product_candidates": [
                {
                    "name": p["name"],
                    "joe_count": p["joe_count"],
                    "candidates": p["candidate_addresses"][:8],
                }
                for p in correlations.get("products", [])[:25]
            ],
            "joe_maintenance_candidates": [
                {
                    "name": m["name"],
                    "joe_count": m["joe_count"],
                    "candidates": m["candidate_addresses"][:8],
                }
                for m in correlations.get("maintenance", [])[:12]
            ],
            "joe_cockpit_pct_candidates": [
                {
                    "label": c["label"],
                    "percent_int": c["percent_int"],
                    "candidates": [
                        {
                            "addr": a_hex,
                            "word_hex": f"0x{eeprom_int[_parse_eeprom_addr(a_hex)]:04X}",
                        }
                        for a_hex in c["candidate_addresses"][:6]
                        if _parse_eeprom_addr(a_hex) in eeprom_int
                    ],
                }
                for c in correlations.get("cockpit", [])[:8]
            ],
            "non_zero_counter_bank_sample": dict(list(bank_words.items())[:80]),
        }

        prompt = (
            "You are calibrating Jura espresso machine EEPROM memory offsets against J.O.E. ground-truth counters.\n"
            "Rules:\n"
            "1. For each product/maintenance item with candidates, pick the SINGLE best hex address belonging to a coherent contiguous bank for this model.\n"
            "2. Do NOT assign the same EEPROM address to two different items unless only 1 candidate exists.\n"
            "3. Set is_double=true for double beverages (e.g. '2 Espressi', '2x Coffee', 'Doppio').\n"
            "4. For cockpit percentages, choose 'byte': 'low' if (word & 0xFF)==percent_int else 'high'.\n"
            f"Input JSON:\n{json.dumps(prompt_ctx, ensure_ascii=False)}\n\n"
            "Respond in JSON only with keys:\n"
            "- \"products\": [{\"name\": str, \"addr\": \"0xXXXX\", \"is_double\": bool, \"reason\": str}]\n"
            "- \"maintenance\": [{\"name\": str, \"addr\": \"0xXXXX\", \"reason\": str}]\n"
            "- \"maintenance_pct\": [{\"name\": str, \"addr\": \"0xXXXX\", \"byte\": \"low\"|\"high\", \"reason\": str}]\n"
            "- \"notes\": short summary string."
        )

        parsed, q_err = _query_ollama_json(prompt, active_model, timeout=60.0)
        if q_err and "Cancelled" in q_err:
            return {"success": False, "cancelled": True, "error": q_err}

        update_task_progress(
            active=True,
            step="VERIFYING_OFFSETS",
            detail="Verifying AI-selected addresses against raw EEPROM ground truth...",
            current=3,
            total=3,
            percent=85,
            eta_seconds=1,
            model=active_model,
        )

        ai_prod_map: Dict[str, Dict[str, Any]] = {}
        for item in (parsed or {}).get("products") or []:
            if isinstance(item, dict) and item.get("name"):
                ai_prod_map[str(item["name"]).strip().lower()] = item

        ai_maint_map: Dict[str, Dict[str, Any]] = {}
        for item in (parsed or {}).get("maintenance") or []:
            if isinstance(item, dict) and item.get("name"):
                ai_maint_map[str(item["name"]).strip().lower()] = item

        ai_pct_map: Dict[str, Dict[str, Any]] = {}
        for item in (parsed or {}).get("maintenance_pct") or []:
            if isinstance(item, dict) and item.get("name"):
                ai_pct_map[str(item["name"]).strip().lower()] = item

        used_addrs = set()
        verified_products: List[Dict[str, Any]] = []
        for idx, p in enumerate(correlations.get("products", []), start=1):
            pname = str(p["name"])
            joe_cnt = int(p["joe_count"])
            cands = [_parse_eeprom_addr(a) for a in p.get("candidate_addresses", [])]
            cands = [a for a in cands if a is not None and a in eeprom_int]

            chosen = None
            ai_choice = ai_prod_map.get(pname.lower())
            reason = "Exact J.O.E. value match"
            if ai_choice:
                ai_addr = _parse_eeprom_addr(ai_choice.get("addr"))
                if ai_addr is not None and ai_addr in eeprom_int:
                    if joe_cnt == 0 or eeprom_int[ai_addr] == joe_cnt:
                        chosen = ai_addr
                        reason = str(ai_choice.get("reason") or "AI bank-aligned match")

            if chosen is None and cands:
                unused = [a for a in cands if a not in used_addrs]
                chosen = unused[0] if unused else cands[0]

            if chosen is None:
                continue

            used_addrs.add(chosen)
            is_dbl = bool((ai_choice or {}).get("is_double")) or bool(
                re.match(r'^\s*(2\s*x?\s+|doppio\b)', pname, re.IGNORECASE)
            )
            verified_products.append({
                "code": idx,
                "name": pname,
                "addr": chosen,
                "addr_hex": f"0x{chosen:04X}",
                "is_double": is_dbl,
                "joe_count": joe_cnt,
                "eeprom_val": eeprom_int[chosen],
                "verified_exact": eeprom_int[chosen] == joe_cnt,
                "confidence": "high" if (len(cands) == 1 or ai_choice) else "medium",
                "reason": reason,
            })

        verified_maint: List[Dict[str, Any]] = []
        for m in correlations.get("maintenance", []):
            mname = str(m["name"])
            joe_cnt = int(m["joe_count"])
            cands = [_parse_eeprom_addr(a) for a in m.get("candidate_addresses", [])]
            cands = [a for a in cands if a is not None and a in eeprom_int]

            chosen = None
            ai_choice = ai_maint_map.get(mname.lower())
            reason = "Exact J.O.E. maintenance match"
            if ai_choice:
                ai_addr = _parse_eeprom_addr(ai_choice.get("addr"))
                if ai_addr is not None and ai_addr in eeprom_int and (joe_cnt == 0 or eeprom_int[ai_addr] == joe_cnt):
                    chosen = ai_addr
                    reason = str(ai_choice.get("reason") or "AI verified maintenance offset")

            if chosen is None and cands:
                unused = [a for a in cands if a not in used_addrs]
                chosen = unused[0] if unused else cands[0]

            if chosen is None:
                continue
            used_addrs.add(chosen)
            verified_maint.append({
                "name": mname,
                "addr": chosen,
                "addr_hex": f"0x{chosen:04X}",
                "joe_count": joe_cnt,
                "eeprom_val": eeprom_int[chosen],
                "verified_exact": eeprom_int[chosen] == joe_cnt,
                "confidence": "high" if (len(cands) == 1 or ai_choice) else "medium",
                "reason": reason,
            })

        verified_pct: List[Dict[str, Any]] = []
        for c in correlations.get("cockpit", []):
            cname = str(c["label"])
            pct_val = int(c["percent_int"])
            cands = [_parse_eeprom_addr(a) for a in c.get("candidate_addresses", [])]
            cands = [a for a in cands if a is not None and a in eeprom_int]

            chosen = None
            chosen_byte = "low"
            ai_choice = ai_pct_map.get(cname.lower())
            if ai_choice:
                ai_addr = _parse_eeprom_addr(ai_choice.get("addr"))
                if ai_addr is not None and ai_addr in eeprom_int:
                    w = eeprom_int[ai_addr]
                    pref_byte = str(ai_choice.get("byte") or "low").lower()
                    if pref_byte == "high" and ((w >> 8) & 0xFF) == pct_val:
                        chosen, chosen_byte = ai_addr, "high"
                    elif (w & 0xFF) == pct_val:
                        chosen, chosen_byte = ai_addr, "low"
                    elif ((w >> 8) & 0xFF) == pct_val:
                        chosen, chosen_byte = ai_addr, "high"

            if chosen is None and cands:
                chosen = cands[0]
                w = eeprom_int[chosen]
                chosen_byte = "low" if (w & 0xFF) == pct_val else "high"

            if chosen is None:
                continue

            verified_pct.append({
                "name": cname,
                "addr": chosen,
                "addr_hex": f"0x{chosen:04X}",
                "byte": chosen_byte,
                "joe_pct": pct_val,
                "eeprom_word_hex": f"0x{eeprom_int[chosen]:04X}",
                "confidence": "high" if (len(cands) == 1 or ai_choice) else "medium",
            })

        override = {
            "source": "ai_joe_calibration",
            "model_used": active_model,
            "ef_code": ty_str,
            "article_number": article_number,
            "model_name": model_name,
            "products": verified_products,
            "maintenance": verified_maint,
            "maintenance_pct": verified_pct,
            "notes": str((parsed or {}).get("notes") or q_err or f"Calibrated {len(verified_products)} beverage and {len(verified_maint)} maintenance offsets against J.O.E. export."),
        }

        update_task_progress(
            active=False,
            step="COMPLETED",
            detail=f"Calibrated {len(verified_products)} beverage + {len(verified_maint)} maintenance offsets.",
            current=3,
            total=3,
            percent=100,
            eta_seconds=0,
        )
        return {
            "success": True,
            "model": active_model,
            "override": override,
            "matched_products": len(verified_products),
            "matched_maintenance": len(verified_maint),
            "matched_pct": len(verified_pct),
            "notes": override["notes"],
        }
    finally:
        _maybe_auto_unload(active_model)
        update_task_progress(active=False)


def _normalize_joe_struct(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize AI/OCR extracted counters and identity fields into canonical spectra_probe J.O.E. dict shape."""
    products: Dict[str, int] = {}
    maintenance: Dict[str, int] = {}
    cockpit: Dict[str, str] = {}
    ident_block = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}

    def _clean_ident(key: str, *aliases: str) -> str:
        for k in (key, *aliases):
            val = raw.get(k) if raw.get(k) is not None else ident_block.get(k)
            s = str(val or "").strip()
            if s and s.lower() not in ("none", "null", "n/a", "unknown", "—"):
                return s
        return ""

    model_name = _clean_ident("model_name", "machine_model", "model", "appliance")
    article_number = _clean_ident("article_number", "model_number", "art_no")
    serial_number = _clean_ident("serial_number", "serial")
    market_region = _clean_ident("market_region", "market", "region", "country")

    def _to_int(v: Any) -> Optional[int]:
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return int(round(v))
        m = re.search(r"-?\d+", str(v or ""))
        return int(m.group(0)) if m else None

    raw_prods = raw.get("products")
    if isinstance(raw_prods, dict):
        for k, v in raw_prods.items():
            cnt = _to_int(v)
            if str(k).strip() and cnt is not None and cnt >= 0:
                products[str(k).strip()] = cnt
    elif isinstance(raw_prods, list):
        for item in raw_prods:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("label") or "").strip()
                cnt = _to_int(item.get("count") if "count" in item else item.get("value"))
                if name and cnt is not None and cnt >= 0:
                    products[name] = cnt

    raw_maint = raw.get("maintenance")
    if isinstance(raw_maint, dict):
        for k, v in raw_maint.items():
            cnt = _to_int(v)
            if str(k).strip() and cnt is not None and cnt >= 0:
                maintenance[str(k).strip()] = cnt
    elif isinstance(raw_maint, list):
        for item in raw_maint:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("label") or "").strip()
                cnt = _to_int(item.get("count") if "count" in item else item.get("value"))
                if name and cnt is not None and cnt >= 0:
                    maintenance[name] = cnt

    raw_cockpit = raw.get("cockpit") if "cockpit" in raw else raw.get("percentages")
    if isinstance(raw_cockpit, dict):
        for k, v in raw_cockpit.items():
            pct = _to_int(v)
            if str(k).strip() and pct is not None and 0 <= pct <= 100:
                cockpit[str(k).strip()] = f"{pct}%"
    elif isinstance(raw_cockpit, list):
        for item in raw_cockpit:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("label") or "").strip()
                pct = _to_int(item.get("percent") if "percent" in item else item.get("value"))
                if name and pct is not None and 0 <= pct <= 100:
                    cockpit[name] = f"{pct}%"

    return {
        "model_name": model_name,
        "article_number": article_number,
        "serial_number": serial_number,
        "market_region": market_region,
        "products": products,
        "maintenance": maintenance,
        "cockpit": cockpit,
    }


def _parse_counters_from_ocr_text(ocr_text: str) -> Dict[str, Any]:
    """Heuristic fallback parser for Tesseract OCR text from J.O.E. / legacy Jura screenshots."""
    products: Dict[str, int] = {}
    maintenance: Dict[str, int] = {}
    cockpit: Dict[str, str] = {}

    maint_kw = ("clean", "decalc", "descal", "filter", "rinse", "milk", "capp", "brew")
    for raw_line in (ocr_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pct_m = re.match(r"^(.{2,45}?)[\s:=\-]+(\d{1,3})\s*%$", line)
        if pct_m:
            lbl = pct_m.group(1).strip(" :-•|")
            val = int(pct_m.group(2))
            if lbl and 0 <= val <= 100:
                cockpit[lbl] = f"{val}%"
            continue
        cnt_m = re.match(r"^(.{2,45}?)[\s:=\-]+(\d[\d,\.]{0,8})$", line)
        if cnt_m:
            lbl = cnt_m.group(1).strip(" :-•|")
            val = int(re.sub(r"[^\d]", "", cnt_m.group(2)))
            if not lbl:
                continue
            if any(k in lbl.lower() for k in maint_kw):
                maintenance[lbl] = val
            else:
                products[lbl] = val

    return {
        "model_name": "",
        "article_number": "",
        "serial_number": "",
        "market_region": "",
        "products": products,
        "maintenance": maintenance,
        "cockpit": cockpit,
    }


def _merge_joe_dicts(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """Merge deterministic parsed J.O.E. dict (primary) with AI-extracted metadata/counters (secondary)."""
    out = {
        "model_name": str(primary.get("model_name") or secondary.get("model_name") or "").strip(),
        "article_number": str(primary.get("article_number") or secondary.get("article_number") or "").strip(),
        "serial_number": str(primary.get("serial_number") or secondary.get("serial_number") or "").strip(),
        "market_region": str(primary.get("market_region") or secondary.get("market_region") or "").strip(),
        "products": dict(secondary.get("products") or {}),
        "maintenance": dict(secondary.get("maintenance") or {}),
        "cockpit": dict(secondary.get("cockpit") or {}),
        "total_products": primary.get("total_products"),
        "raw_lines": list(primary.get("raw_lines") or []),
    }
    out["products"].update(primary.get("products") or {})
    out["maintenance"].update(primary.get("maintenance") or {})
    out["cockpit"].update(primary.get("cockpit") or {})
    return out


def extract_joe_from_text_with_ai(
    raw_text: str,
    model: Optional[str] = None,
    current_identity: Optional[Dict[str, str]] = None,
    auto_unload: bool = True,
) -> Dict[str, Any]:
    """
    Use the active Local AI model to parse unstructured `.txt` reports, J.O.E. text
    snippets, or user machine notes into normalized counters plus US/EU machine identity.
    """
    snippet = (raw_text or "").strip()
    if not snippet:
        return {"success": False, "error": "Uploaded text / notes payload is empty."}

    ok, active_model, err = _resolve_active_model(requested_model=model, require_vision=False)
    if not ok:
        return {"success": False, "error": err}

    cur_ident = current_identity if isinstance(current_identity, dict) else {}
    clipped = snippet[:6000]
    prompt = (
        "You are analyzing a diagnostic text file or technician notes from a Jura espresso machine.\n"
        "Hardware telemetry reported so far (may have wrong US vs EU model variant): "
        f"{json.dumps(cur_ident, ensure_ascii=False)}\n\n"
        "Extract machine identity AND any beverage/maintenance counters from the text below.\n"
        "Respond with ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "model_name": "exact Jura model name e.g. Jura E8 (NA) or WE8 (EA), empty if absent",\n'
        '  "article_number": "5-digit article or model number e.g. 15364, empty if absent",\n'
        '  "serial_number": "serial number string, empty if absent",\n'
        '  "market_region": "US, NA, EU, UK, CH, etc. if indicated (e.g. 120V/60Hz -> US), empty if absent",\n'
        '  "products": [{"name": "Espresso", "count": 123}],\n'
        '  "maintenance": [{"name": "Cleanings", "count": 12}],\n'
        '  "cockpit": [{"name": "Filter", "percent": 80}],\n'
        '  "notes": "short extraction summary"\n'
        "}\n"
        "Rules: use integers for counts/percentages; only extract values explicitly supported by the text.\n\n"
        f"TEXT INPUT:\n{clipped}"
    )

    update_task_progress(
        active=True,
        task_id="text_extract",
        task_label="AI Text & Identity Parsing",
        step="Parsing Diagnostic Text & Identity",
        detail=f"Extracting counters and market identity via {active_model}...",
        current=1,
        total=2,
        percent=35,
        eta_seconds=15,
        model=active_model,
        error="",
    )
    try:
        parsed, q_err = _query_ollama_json(
            prompt,
            active_model,
            timeout=90.0,
            temperature=0.05,
            num_ctx=4096,
            num_predict=768,
        )
        if parsed is None:
            return {"success": False, "error": q_err or "Local AI did not return structured JSON from text."}
        norm = _normalize_joe_struct(parsed)
        return {
            "success": True,
            "method": f"ai_text:{active_model}",
            "model": active_model,
            "joe_data": norm,
            "notes": str(parsed.get("notes") or f"Parsed text via {active_model}."),
        }
    finally:
        if auto_unload:
            _maybe_auto_unload(active_model)
            update_task_progress(active=False)


def extract_joe_from_image_with_ai(
    image_b64: str,
    model: Optional[str] = None,
    auto_unload: bool = True,
) -> Dict[str, Any]:
    """
    Extract beverage counters, maintenance cycle counts, and maintenance percentages
    from a J.O.E. or legacy Jura diagnostic screenshot using a vision-capable Local AI
    model (or local Tesseract OCR fallback).
    """
    import base64
    import binascii

    clean_b64 = (image_b64 or "").strip()
    if "," in clean_b64 and clean_b64.lower().startswith("data:"):
        clean_b64 = clean_b64.split(",", 1)[1].strip()
    if not clean_b64:
        return {"success": False, "error": "Empty image payload provided."}
    try:
        base64.b64decode(clean_b64, validate=True)
    except (ValueError, binascii.Error):
        return {"success": False, "error": "Invalid base64 image payload provided."}

    prompt = (
        "You are reading a screenshot from Jura Operating Experience (J.O.E.) or legacy Jura diagnostic software.\n"
        "Extract ALL visible diagnostic counters AND any visible machine identity (US/EU model variant, article number, serial number) and return ONLY valid JSON with exact schema:\n"
        "{\n"
        '  "model_name": "Jura model name if shown, empty if absent",\n'
        '  "article_number": "model/article number if shown, empty if absent",\n'
        '  "serial_number": "serial number if shown, empty if absent",\n'
        '  "market_region": "US, NA, EU, etc. if indicated, empty if absent",\n'
        '  "products": [{"name": "Espresso", "count": 1234}],\n'
        '  "maintenance": [{"name": "Cleanings", "count": 45}],\n'
        '  "cockpit": [{"name": "Filter", "percent": 65}],\n'
        '  "notes": "short summary"\n'
        "}\n"
        "Rules: use integers for counts and percentages; preserve exact counter labels shown on screen."
    )

    ok_vis, vis_model, vis_err = _resolve_active_model(requested_model=model, require_vision=True)
    if ok_vis:
        update_task_progress(
            active=True,
            task_id="image_extract",
            task_label="Screenshot Counter Extraction",
            step="Extracting Counters from Screenshot",
            detail=f"Analyzing image via {vis_model}...",
            current=1,
            total=2,
            percent=40,
            eta_seconds=25,
            model=vis_model,
            error="",
        )
        try:
            parsed, q_err = _query_ollama_json(
                prompt,
                vis_model,
                timeout=120.0,
                temperature=0.05,
                images=[clean_b64],
                num_ctx=4096,
                num_predict=768,
            )
            if parsed is not None:
                norm = _normalize_joe_struct(parsed)
                total_items = len(norm["products"]) + len(norm["maintenance"]) + len(norm["cockpit"])
                if total_items > 0:
                    return {
                        "success": True,
                        "method": f"vision:{vis_model}",
                        "model": vis_model,
                        "joe_data": norm,
                        "notes": str(parsed.get("notes") or f"Extracted {total_items} counters via {vis_model}."),
                    }
                return {
                    "success": False,
                    "error": "Vision model did not find numeric counters in the screenshot.",
                }
            return {"success": False, "error": q_err or "Failed to extract counters from screenshot."}
        finally:
            if auto_unload:
                _maybe_auto_unload(vis_model)
                update_task_progress(active=False)

    # Optional offline Tesseract OCR fallback if installed cleanly on host
    import base64
    import shutil
    import subprocess
    import tempfile

    tess_bin = shutil.which("tesseract")
    if tess_bin:
        try:
            raw_img = base64.b64decode(clean_b64)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tf.write(raw_img)
                tmp_path = tf.name
            try:
                proc = subprocess.run([tess_bin, tmp_path, "stdout"], capture_output=True, text=True, timeout=20)
                ocr_txt = proc.stdout or ""
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            norm = _parse_counters_from_ocr_text(ocr_txt)
            total_items = len(norm["products"]) + len(norm["maintenance"]) + len(norm["cockpit"])
            if total_items > 0:
                return {
                    "success": True,
                    "method": "ocr:tesseract",
                    "model": "tesseract",
                    "joe_data": norm,
                    "notes": f"Extracted {total_items} counters via Tesseract OCR.",
                }
        except Exception:
            pass

    return {"success": False, "error": vis_err or "Screenshot OCR requires a vision model (e.g. gemma3:4b)."}


def calibrate_offsets_from_upload(
    eeprom_words: Dict[Any, Any],
    file_name: str,
    csv_text: Optional[str] = None,
    image_b64: Optional[str] = None,
    ty_str: str = "",
    model_name: str = "",
    article_number: str = "",
    current_stats: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    user_notes: Optional[str] = None,
    user_model_name: Optional[str] = None,
    user_article_number: Optional[str] = None,
    user_serial_number: Optional[str] = None,
    user_market_region: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified offset & machine-identity calibration from uploaded J.O.E. / Legacy CSV,
    freeform `.txt` export / technician notes, or Screenshot Image.
    Extracts ground-truth counters and US/EU machine identity via Local AI, correlates
    EEPROM words, verifies addresses, and returns a ready-to-apply override + preview.
    """
    import spectra_probe

    fname = (file_name or "").strip()
    lower = fname.lower()
    is_image = bool(image_b64) or lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))
    u_model = str(user_model_name or "").strip()
    u_art = str(user_article_number or "").strip()
    u_serial = str(user_serial_number or "").strip()
    u_market = str(user_market_region or "").strip()
    u_notes = str(user_notes or "").strip()
    hw_serial = str((current_stats or {}).get("serial_number") or "")
    hw_market = str((current_stats or {}).get("country_code") or "")

    extracted_ai_model: Optional[str] = None
    ran_calibration_model: Optional[str] = None
    try:
        if is_image and image_b64:
            ext_res = extract_joe_from_image_with_ai(image_b64, model=model, auto_unload=False)
            if str(ext_res.get("method") or "").startswith("vision:") and ext_res.get("model"):
                extracted_ai_model = str(ext_res.get("model"))
            if not ext_res.get("success"):
                return ext_res
            joe_data = ext_res["joe_data"]
            extraction_source = ext_res.get("method", "vision")
            if u_notes:
                note_parsed = spectra_probe.parse_joe_csv_text(u_notes)
                joe_data = _merge_joe_dicts(joe_data, note_parsed)
        else:
            raw_text = (csv_text or "").strip()
            combined_parts = [p for p in (raw_text, u_notes) if p]
            combined_text = "\n".join(combined_parts).strip()

            has_manual_ident = bool(u_model or u_art or u_serial or u_market)
            if not combined_text and not has_manual_ident:
                return {"success": False, "error": "Uploaded file / notes payload is empty."}

            det_data = spectra_probe.parse_joe_csv_text(combined_text) if combined_text else {
                "model_name": "",
                "article_number": "",
                "serial_number": "",
                "market_region": "",
                "cockpit": {},
                "maintenance": {},
                "products": {},
                "raw_lines": [],
            }
            det_count = (
                len(det_data.get("products", {}))
                + len(det_data.get("maintenance", {}))
                + len(det_data.get("cockpit", {}))
            )
            extraction_source = "txt_parser" if lower.endswith(".txt") else "csv_parser"
            joe_data = det_data

            # Always run Local AI text extraction for `.txt`, freeform user notes, incomplete counters, or missing identity
            should_use_ai_text = bool(combined_text) and (
                lower.endswith(".txt")
                or bool(u_notes)
                or det_count == 0
                or not det_data.get("model_name")
            )
            if should_use_ai_text:
                ai_txt_res = extract_joe_from_text_with_ai(
                    combined_text,
                    model=model,
                    current_identity={
                        "ef_code": ty_str,
                        "model_name": model_name or "",
                        "article_number": article_number or "",
                        "serial_number": hw_serial,
                        "market_region": hw_market,
                    },
                    auto_unload=False,
                )
                if str(ai_txt_res.get("method") or "").startswith("ai_text:") and ai_txt_res.get("model"):
                    extracted_ai_model = str(ai_txt_res.get("model"))
                if ai_txt_res.get("success"):
                    ai_joe = ai_txt_res.get("joe_data") or {}
                    joe_data = _merge_joe_dicts(det_data, ai_joe)
                    ai_items = (
                        len(ai_joe.get("products", {}))
                        + len(ai_joe.get("maintenance", {}))
                        + len(ai_joe.get("cockpit", {}))
                    )
                    if ai_items > 0 or ai_joe.get("model_name") or ai_joe.get("article_number") or ai_joe.get("serial_number"):
                        extraction_source = str(ai_txt_res.get("method") or "ai_text")
                elif det_count == 0 and not has_manual_ident:
                    return ai_txt_res

        total_parsed = (
            len(joe_data.get("products", []))
            + len(joe_data.get("maintenance", []))
            + len(joe_data.get("cockpit", []))
        )

        ai_det_model = str(joe_data.get("model_name") or "").strip()
        ai_det_art = str(joe_data.get("article_number") or "").strip()
        ai_det_serial = str(joe_data.get("serial_number") or "").strip()
        ai_det_market = str(joe_data.get("market_region") or "").strip()

        resolved_model = u_model or ai_det_model or model_name or "Unknown"
        resolved_article = u_art or ai_det_art or article_number or "unknown"
        resolved_serial = u_serial or ai_det_serial or (hw_serial if hw_serial != "N/A" else "")
        resolved_market = u_market or ai_det_market or (hw_market if hw_market != "N/A" else "")
        has_identity_update = bool(
            u_model or u_art or u_serial or u_market or ai_det_model or ai_det_art or ai_det_serial or ai_det_market
        )

        detected_identity = {
            "ef_code": ty_str,
            "model_name": resolved_model,
            "article_number": resolved_article,
            "serial_number": resolved_serial,
            "market_region": resolved_market,
            "ai_detected_model": ai_det_model,
            "ai_detected_article": ai_det_art,
            "ai_detected_serial": ai_det_serial,
            "ai_detected_market": ai_det_market,
        }

        if total_parsed == 0:
            if not has_identity_update:
                return {
                    "success": False,
                    "error": "No readable diagnostic counters or machine identity details were extracted from the uploaded file/notes.",
                }
            # Identity-only override (e.g. user supplied US/EU model name, article #, or serial #)
            override = {
                "source": "ai_identity_override",
                "model_used": model or "manual_or_ai",
                "extraction_source": extraction_source or "identity_input",
                "uploaded_filename": fname or "manual_notes.txt",
                "ef_code": ty_str,
                "model_name": resolved_model,
                "article_number": resolved_article,
                "serial_number": resolved_serial,
                "market_region": resolved_market,
                "identity_only": True,
                "products": [],
                "maintenance": [],
                "maintenance_pct": [],
                "notes": f"Machine identity updated to {resolved_model} (Article {resolved_article}).",
            }
            return {
                "success": True,
                "model": model or "identity_override",
                "extraction_source": override["extraction_source"],
                "detected_identity": detected_identity,
                "joe_summary": {
                    "products_found": 0,
                    "maintenance_found": 0,
                    "cockpit_found": 0,
                    "sample_products": [],
                    "sample_maintenance": [],
                },
                "override": override,
                "preview_before": {
                    "total_preps": (current_stats or {}).get("total_preps"),
                    "products": (current_stats or {}).get("products", []),
                    "maintenance": (current_stats or {}).get("maintenance_counters", {}),
                } if isinstance(current_stats, dict) else {},
                "preview_after": {
                    "total_preps": (current_stats or {}).get("total_preps"),
                    "products": (current_stats or {}).get("products", []),
                    "maintenance_counters": (current_stats or {}).get("maintenance_counters", {}),
                    "maintenance_pct": {},
                } if isinstance(current_stats, dict) else {},
                "matched_products": 0,
                "matched_maintenance": 0,
                "matched_pct": 0,
                "notes": override["notes"],
            }

        bundle = {
            "identity": {
                "ef_code": ty_str,
                "model_name": resolved_model,
                "article_number": resolved_article,
                "serial_number": resolved_serial,
                "market_region": resolved_market,
            },
            "gateways": {
                "TY:": ty_str,
            },
            "eeprom_words": eeprom_words,
            "joe_ground_truth": joe_data,
        }

        cal = calibrate_eeprom_offsets_from_joe(bundle, model=model)
        if cal.get("model"):
            ran_calibration_model = str(cal.get("model"))
        if not cal.get("success"):
            return cal
    finally:
        if extracted_ai_model and extracted_ai_model != ran_calibration_model:
            _maybe_auto_unload(extracted_ai_model)
            update_task_progress(active=False)

    override = cal["override"]
    override["extraction_source"] = extraction_source
    override["uploaded_filename"] = fname or "notes.txt"
    override["model_name"] = resolved_model
    override["article_number"] = resolved_article
    override["serial_number"] = resolved_serial
    override["market_region"] = resolved_market

    eeprom_int: Dict[int, int] = {}
    for k, v in (eeprom_words or {}).items():
        ak = _parse_eeprom_addr(k)
        if ak is not None:
            try:
                eeprom_int[ak] = int(v)
            except Exception:
                pass

    before_counters = {}
    if isinstance(current_stats, dict):
        before_counters = {
            "total_preps": current_stats.get("total_preps"),
            "products": current_stats.get("products", []),
            "maintenance": current_stats.get("maintenance_counters", {}),
        }

    # Build pure After preview directly from calibrated offsets & verified EEPROM words
    after_products = []
    after_total = 0
    for p in override.get("products") or []:
        addr_i = _parse_eeprom_addr(p.get("addr"))
        val = eeprom_int.get(addr_i, p.get("eeprom_val", 0)) if addr_i is not None else p.get("eeprom_val", 0)
        after_total += int(val or 0)
        after_products.append({
            "name": p.get("name", "Product"),
            "addr_hex": p.get("addr_hex") or (f"0x{addr_i:04X}" if addr_i is not None else ""),
            "count": int(val or 0),
            "joe_count": p.get("joe_count"),
        })

    after_maint = {}
    for m in override.get("maintenance") or []:
        addr_i = _parse_eeprom_addr(m.get("addr"))
        val = eeprom_int.get(addr_i, m.get("eeprom_val", 0)) if addr_i is not None else m.get("eeprom_val", 0)
        after_maint[str(m.get("name", "Maintenance"))] = {
            "count": int(val or 0),
            "addr_hex": m.get("addr_hex") or (f"0x{addr_i:04X}" if addr_i is not None else ""),
            "joe_count": m.get("joe_count"),
        }

    after_pct = {}
    for pc in override.get("maintenance_pct") or []:
        after_pct[str(pc.get("name", "Level"))] = {
            "percent": pc.get("joe_pct"),
            "addr_hex": pc.get("addr_hex", ""),
            "byte": pc.get("byte", "low"),
        }

    simulated = {
        "total_preps": after_total,
        "products": after_products,
        "maintenance_counters": after_maint,
        "maintenance_pct": after_pct,
    }

    return {
        "success": True,
        "model": cal.get("model"),
        "extraction_source": extraction_source,
        "detected_identity": detected_identity,
        "joe_summary": {
            "products_found": len(joe_data.get("products", {})),
            "maintenance_found": len(joe_data.get("maintenance", {})),
            "cockpit_found": len(joe_data.get("cockpit", {})),
            "sample_products": [{"name": k, "count": v} for k, v in list((joe_data.get("products") or {}).items())[:8]],
            "sample_maintenance": [{"name": k, "count": v} for k, v in list((joe_data.get("maintenance") or {}).items())[:8]],
        },
        "override": override,
        "preview_before": before_counters,
        "preview_after": simulated,
        "matched_products": cal.get("matched_products", 0),
        "matched_maintenance": cal.get("matched_maintenance", 0),
        "matched_pct": cal.get("matched_pct", 0),
        "notes": cal.get("notes", ""),
    }
