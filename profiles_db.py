#!/usr/bin/env python3
"""
Jura Machine Profiles Database Manager
Loads and queries machine profiles (products, maintenance items, alerts)
for over 75 modern Jura coffee machines.
"""

import os
import re
import json

DATA_FILE = os.path.join(os.path.dirname(__file__), "profiles_data.json")
DOCS_MODELS_DIR = os.path.join(os.path.dirname(__file__), "docs", "models")

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
    specs = load_model_specs()
    if not specs or not ef_code_or_art:
        return None
    raw = str(ef_code_or_art).strip().upper()
    if raw in specs:
        return specs[raw]
    m = re.search(r'(EF\w+)', raw)
    if m and m.group(1) in specs:
        return specs[m.group(1)]
    simplified = re.sub(r'V\d+$', '', raw)
    if simplified in specs:
        return specs[simplified]
    for k, v in specs.items():
        if k in raw or raw in k:
            return v
    return None

def find_profile(raw_model_or_ef: str) -> dict:
    """
    Match an EF code (e.g. 'EF536M V02.01', '3C16EF536M V02.01', 'EF1092', 'EF545')
    to the best matching machine profile. Longest matching prefix wins.
    Automatically enriches matched profile with model specification from docs/models/ if present.
    """
    profiles = load_profiles()
    matched_profile = None

    if profiles:
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

        # Check model family substring match
        if matched_profile is None:
            for key, p in profiles.items():
                fam = p.get("model_family", "")
                if fam and fam.upper() in target:
                    matched_profile = dict(p)
                    break

    if matched_profile is None:
        matched_profile = dict(DEFAULT_PROFILE)

    # Dynamic Enrichment: Merge model-specific specifications from docs/models/*.json if available
    spec = get_model_spec(raw_model_or_ef)
    if spec:
        for k in ("hardware", "custom_registers", "recipe_buttons", "article_numbers"):
            if k in spec and k not in matched_profile:
                matched_profile[k] = spec[k]

    return matched_profile

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
