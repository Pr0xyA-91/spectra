#!/usr/bin/env python3
"""
Jura Machine Profiles Database Manager
Loads and queries machine profiles (products, maintenance items, alerts)
for over 75 modern Jura coffee machines.
"""

import os
import re
import json
import datetime
import threading
from typing import Optional, Dict, Any, List

DATA_FILE = os.path.join(os.path.dirname(__file__), "profiles_data.json")
DOCS_MODELS_DIR = os.path.join(os.path.dirname(__file__), "docs", "models")
EEPROM_OVERRIDES_FILE = os.path.join(os.path.expanduser("~/.config/spectra"), "eeprom_overrides.json")
_OVERRIDES_LOCK = threading.Lock()

# Default fallback profile if machine model is unknown
DEFAULT_PROFILE = {
    "model_family": "Generic Jura Automatic",
    "products": [
        {"code": 1, "name": "Ristretto", "is_double": False, "active": True},
        {"code": 2, "name": "Espresso", "is_double": False, "active": True},
        {"code": 3, "name": "Coffee", "is_double": False, "active": True},
        {"code": 4, "name": "Cappuccino", "is_double": False, "active": True},
        {"code": 5, "name": "Milk Coffee", "is_double": False, "active": True},
        {"code": 6, "name": "Espresso Macchiato", "is_double": False, "active": True},
        {"code": 7, "name": "Latte Macchiato", "is_double": False, "active": True},
        {"code": 8, "name": "Milk Foam", "is_double": False, "active": True},
        {"code": 10, "name": "Milk Portion", "is_double": False, "active": True},
        {"code": 13, "name": "Hot Water", "is_double": False, "active": True},
        {"code": 17, "name": "2 Ristretti", "is_double": True, "active": True},
        {"code": 18, "name": "2 Espressi", "is_double": True, "active": True},
        {"code": 19, "name": "2 Coffees", "is_double": True, "active": True},
        {"code": 45, "name": "Hot Water (Green Tea)", "is_double": False, "active": True},
        {"code": 46, "name": "Flat White", "is_double": False, "active": True},
    ],
    "maintenance_counters": [
        "Cleaning", "FilterChange", "Decalc", "CappuRinse", "CoffeeRinse", "CappuClean"
    ],
    "maintenance_percentages": [
        "Cleaning", "FilterChange", "Decalc"
    ],
    "alerts": [
        {"bit": 0, "blocking": True, "name": "insert tray"},
        {"bit": 1, "blocking": True, "name": "fill water"},
        {"bit": 2, "blocking": True, "name": "empty grounds"},
        {"bit": 3, "blocking": True, "name": "empty tray"},
        {"bit": 4, "blocking": True, "name": "insert coffee bin"},
        {"bit": 10, "blocking": False, "name": "no beans"},
        {"bit": 12, "blocking": False, "name": "heating up"},
        {"bit": 13, "blocking": False, "name": "coffee ready"},
        {"bit": 18, "blocking": False, "name": "coffee rinsing"},
    ]
}

_PROFILES_CACHE = None
_MODEL_SPECS_CACHE = None
_PROFILE_LOOKUP_CACHE = {}
_MODEL_SPEC_LOOKUP_CACHE = {}

def load_profiles() -> dict:
    global _PROFILES_CACHE
    if _PROFILES_CACHE is None:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                _PROFILES_CACHE = json.load(f)
        else:
            _PROFILES_CACHE = {}
    return _PROFILES_CACHE

def load_model_specs() -> dict:
    """Load all structured model specification overrides from docs/models/*.json."""
    global _MODEL_SPECS_CACHE
    if _MODEL_SPECS_CACHE is not None:
        return _MODEL_SPECS_CACHE

    specs = {}
    candidates = [
        DOCS_MODELS_DIR,
        os.path.join(os.path.dirname(__file__), "..", "docs", "models"),
        os.path.join(os.getcwd(), "docs", "models")
    ]
    for d in candidates:
        if os.path.exists(d):
            import glob
            for fpath in glob.glob(os.path.join(d, "*.json")):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    ef = data.get("ef_code")
                    if ef:
                        specs[ef.upper()] = data
                    for art in data.get("article_numbers", []):
                        specs[str(art)] = data
                except Exception:
                    pass
            break
    _MODEL_SPECS_CACHE = specs
    return _MODEL_SPECS_CACHE

def get_model_spec(ef_code_or_art: str) -> Optional[dict]:
    """Retrieve detailed model specification if available in docs/models/."""
    if not ef_code_or_art:
        return None
    cache_key = str(ef_code_or_art).strip().upper()
    if cache_key in _MODEL_SPEC_LOOKUP_CACHE:
        return _MODEL_SPEC_LOOKUP_CACHE[cache_key]

    specs = load_model_specs()
    if not specs:
        _MODEL_SPEC_LOOKUP_CACHE[cache_key] = None
        return None

    raw = cache_key
    spec = None
    if raw in specs:
        spec = specs[raw]
    else:
        m = re.search(r'(EF\w+)', raw)
        if m and m.group(1) in specs:
            spec = specs[m.group(1)]
        else:
            simplified = re.sub(r'V\d+$', '', raw)
            if simplified in specs:
                spec = specs[simplified]
            else:
                for k, v in specs.items():
                    if k in raw or raw in k:
                        spec = v
                        break

    _MODEL_SPEC_LOOKUP_CACHE[cache_key] = spec
    return spec

def find_profile(raw_model_or_ef: str) -> dict:
    """
    Match an EF code (e.g. 'EF536M V02.01', '3C16EF536M V02.01', 'EF1092', 'EF545')
    to the best matching machine profile. Longest matching prefix wins.
    Automatically enriches matched profile with model specification from docs/models/ if present.
    """
    cache_key = str(raw_model_or_ef).strip().upper()
    if cache_key in _PROFILE_LOOKUP_CACHE:
        return dict(_PROFILE_LOOKUP_CACHE[cache_key])

    profiles = load_profiles()
    matched_profile = None

    # 1. Direct match in model specifications (docs/models/*.json) by EF code or Article Number
    spec = get_model_spec(raw_model_or_ef)
    if spec:
        matched_profile = dict(spec)

    if profiles and matched_profile is None:
        # Extract EF code from string if prefixed
        m = re.search(r'(EF\w+)', raw_model_or_ef.upper())
        target = m.group(1) if m else raw_model_or_ef.strip().upper()

        # Exact match first
        if target in profiles:
            matched_profile = dict(profiles[target])

        # Try removing suffixes like V2, _C, PP, etc.
        if matched_profile is None:
            simplified = re.sub(r'V\d+$', '', target)
            simplified = re.sub(r'_C$', '', simplified)
            simplified = re.sub(r'(COFFEEONLY|PP|UL|ULV\d+)$', '', simplified)
            if simplified in profiles:
                matched_profile = dict(profiles[simplified])

        # Longest prefix match
        if matched_profile is None:
            best_key = None
            best_len = 0
            for key in profiles:
                if target.startswith(key.upper()) and len(key) > best_len:
                    best_key = key
                    best_len = len(key)
            if best_key:
                matched_profile = dict(profiles[best_key])

        # Check model family match (exact match first, then word-boundary match)
        if matched_profile is None:
            for key, p in profiles.items():
                fam = p.get("model_family", "")
                if fam and fam.upper() == target:
                    matched_profile = dict(p)
                    break
            if matched_profile is None:
                for key, p in profiles.items():
                    fam = p.get("model_family", "")
                    if fam and re.search(r'\b' + re.escape(fam.upper()) + r'\b', target):
                        matched_profile = dict(p)
                        break

    if matched_profile is None:
        matched_profile = dict(DEFAULT_PROFILE)

    # Dynamic Enrichment: Merge model-specific specifications from docs/models/*.json if available
    spec = get_model_spec(raw_model_or_ef)
    if spec:
        for k in ("model_family", "article_number", "appliance_type", "series", "products", "hardware", "custom_registers", "recipe_buttons", "article_numbers"):
            if k in spec:
                matched_profile[k] = spec[k]

    _PROFILE_LOOKUP_CACHE[cache_key] = matched_profile
    return dict(matched_profile)

def get_product_name(profile: dict, code: int) -> str:
    """Find human-readable product name for a numeric product code."""
    if code == 0:
        return "Grand Total (All Products)"
    for prod in profile.get("products", []):
        if prod.get("code") == code:
            return prod.get("name", f"Product #{code}")
    # Common standard fallbacks
    common = {
        1: "Ristretto",
        2: "Espresso",
        3: "Coffee",
        4: "Cappuccino",
        5: "Milk Coffee",
        6: "Espresso Macchiato",
        7: "Latte Macchiato",
        8: "Milk Foam",
        10: "Milk Portion",
        13: "Hot Water",
        17: "2 Ristretti",
        18: "2 Espressi",
        19: "2 Coffees",
        45: "Green Tea / Special Water",
        46: "Flat White",
        47: "Cortado",
        48: "Caffè Barista",
        49: "Lungo Barista",
        50: "Pot of Coffee",
        70: "Cold Brew Espresso",
        71: "Cold Brew Coffee",
        72: "Cold Brew Cappuccino",
        73: "Cold Brew Latte Macchiato",
        74: "Cold Brew Flat White"
    }
    return common.get(code, f"Product Code {code}")

def get_active_alerts(profile: dict, status_bytes: bytes) -> list:
    """
    Parse an alert bitfield (from @TF:<hex>) against the profile's alert table.
    Bit i = byte (i >> 3), with MSB first (bit 7 >> (i & 7)).
    """
    active = []
    alert_map = {a["bit"]: a for a in profile.get("alerts", [])}

    for bit_idx in range(len(status_bytes) * 8):
        byte_idx = bit_idx >> 3
        bit_in_byte = 7 - (bit_idx & 7)
        if (status_bytes[byte_idx] >> bit_in_byte) & 1:
            if bit_idx in alert_map:
                active.append(alert_map[bit_idx])
            else:
                active.append({
                    "bit": bit_idx,
                    "blocking": False,
                    "name": f"Unknown Alert (bit {bit_idx})"
                })
    return active

def list_supported_models() -> list:
    """Return sorted list of (EF_code, Model_family)."""
    profiles = load_profiles()
    items = []
    for ef, data in profiles.items():
        fam = data.get("model_family", "")
        label = f"{fam} ({ef})" if fam else ef
        items.append((ef, label))
    items.sort(key=lambda x: x[1])
    return items


# ============================================================================
# Local Per-Machine EEPROM Offset Overrides (AI / J.O.E. Calibrated)
# ============================================================================

def _normalize_override_key(raw: Optional[str]) -> str:
    txt = str(raw or "").strip().upper()
    if not txt:
        return ""
    m = re.search(r'(EF\w+)', txt)
    if m:
        return m.group(1)
    return re.sub(r'\s+', '_', txt)


def _read_eeprom_overrides_locked() -> Dict[str, Any]:
    if not os.path.exists(EEPROM_OVERRIDES_FILE):
        return {}
    try:
        with open(EEPROM_OVERRIDES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_eeprom_overrides_locked(data: Dict[str, Any]) -> None:
    parent = os.path.dirname(EEPROM_OVERRIDES_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = EEPROM_OVERRIDES_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, EEPROM_OVERRIDES_FILE)


def list_eeprom_offset_overrides() -> Dict[str, Any]:
    """Return all saved local EEPROM offset overrides keyed by normalized identifier."""
    with _OVERRIDES_LOCK:
        return dict(_read_eeprom_overrides_locked())


def save_eeprom_offset_override(
    override_payload: Dict[str, Any],
    model_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist a local AI/J.O.E.-calibrated EEPROM offset map so stats_collector reads
    this machine accurately immediately on this device.
    """
    if not isinstance(override_payload, dict):
        raise ValueError("override_payload must be a dictionary")

    ef_raw = str(override_payload.get("ef_code") or "").strip()
    art_raw = str(override_payload.get("article_number") or "").strip()
    mod_raw = str(override_payload.get("model_name") or "").strip()
    key = (
        _normalize_override_key(model_key)
        or _normalize_override_key(ef_raw)
        or (art_raw.upper() if art_raw and art_raw.lower() != "unknown" else "")
        or _normalize_override_key(mod_raw)
        or "CUSTOM_MACHINE"
    )

    entry = dict(override_payload)
    entry["override_key"] = key
    entry["updated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    with _OVERRIDES_LOCK:
        all_ov = _read_eeprom_overrides_locked()
        all_ov[key] = entry
        _write_eeprom_overrides_locked(all_ov)

    return entry


def get_eeprom_offset_override(
    raw_model_or_ef: Optional[str] = None,
    article_number: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Find the best matching local EEPROM offset override by EF code, article number, or model name."""
    with _OVERRIDES_LOCK:
        all_ov = _read_eeprom_overrides_locked()
    if not all_ov:
        return None

    candidates: List[str] = []
    for raw in (raw_model_or_ef, article_number, model_name):
        if raw:
            up = str(raw).strip().upper()
            candidates.append(up)
            norm = _normalize_override_key(up)
            if norm and norm not in candidates:
                candidates.append(norm)

    # 1. Exact key match
    for cand in candidates:
        if cand in all_ov:
            return dict(all_ov[cand])

    # 2. Match stored metadata (article_number, ef_code, model_name)
    for k, entry in all_ov.items():
        if not isinstance(entry, dict):
            continue
        stored_art = str(entry.get("article_number") or "").strip().upper()
        stored_ef = _normalize_override_key(entry.get("ef_code"))
        stored_mod = _normalize_override_key(entry.get("model_name"))
        for cand in candidates:
            if stored_art and cand == stored_art:
                return dict(entry)
            if stored_ef and (cand == stored_ef or stored_ef in cand or cand in stored_ef):
                return dict(entry)
            if stored_mod and cand == stored_mod:
                return dict(entry)
    return None


def delete_eeprom_offset_override(model_key: str) -> bool:
    """Remove a saved local EEPROM offset override by key."""
    norm = _normalize_override_key(model_key)
    raw = str(model_key or "").strip().upper()
    with _OVERRIDES_LOCK:
        all_ov = _read_eeprom_overrides_locked()
        removed = False
        for k in (raw, norm):
            if k and k in all_ov:
                del all_ov[k]
                removed = True
        if removed:
            _write_eeprom_overrides_locked(all_ov)
        return removed
