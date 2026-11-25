#!/usr/bin/env python3
"""
SPECTRA Unified Machine Library & Offset Resolver
=================================================
Single authoritative entry point combining:
  1. Built-in EF / Article profiles (`profiles_data.json`)
  2. Verified model specifications (`docs/models/*.json`)
  3. Local calibrated & imported offset overrides (`~/.config/spectra/eeprom_overrides.json`)

Precedence hierarchy for runtime EEPROM decoding:
  Local Override > Verified Model Spec > Built-in Profile
"""

import copy
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import profiles_db
import version

try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False


SCHEMA_PATCH_V1 = "spectra.offset_patch.v1"

_EMPTY_NORM: Dict[str, List[Dict[str, Any]]] = {
    "products": [],
    "maintenance": [],
    "maintenance_pct": [],
}

_CATALOG_LOCK = threading.Lock()
_CACHED_BASE_CATALOG: Optional[Dict[str, Dict[str, Any]]] = None
_CACHED_CATALOG_SIG: Optional[Tuple[float, float, str, str]] = None
_CACHED_OFFSET_DB_STATUS: Optional[Dict[str, Any]] = None


def invalidate_machine_library_cache() -> None:
    """Clear the cached base machine catalog."""
    global _CACHED_BASE_CATALOG, _CACHED_CATALOG_SIG, _CACHED_OFFSET_DB_STATUS
    with _CATALOG_LOCK:
        _CACHED_BASE_CATALOG = None
        _CACHED_CATALOG_SIG = None
        _CACHED_OFFSET_DB_STATUS = None


def _parse_addr_int(raw: Any) -> Optional[int]:
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    s = str(raw or "").strip().lower()
    if not s:
        return None
    try:
        return int(s, 16) if s.startswith("0x") or any(c in "abcdef" for c in s) else int(s, 10)
    except ValueError:
        return None


def _norm_ef(code: str) -> str:
    return (code or "").strip().upper()


def _norm_str_list(items: Any) -> List[str]:
    if isinstance(items, list):
        return [str(x).strip() for x in items if str(x).strip()]
    if items:
        s = str(items).strip()
        return [s] if s else []
    return []


def _extract_spec_offsets(spec: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Extract normalized register offsets from a verified docs/models JSON spec."""
    custom_regs = spec.get("custom_registers") or {}
    if not isinstance(custom_regs, dict):
        return {"products": [], "maintenance": [], "maintenance_pct": []}

    products: List[Dict[str, Any]] = []
    maintenance: List[Dict[str, Any]] = []
    maint_pct: List[Dict[str, Any]] = []

    maint_tokens = ("clean", "descal", "decalc", "rins", "filter", "grinder", "service", "switch_on")
    for hex_addr, info in custom_regs.items():
        if not isinstance(info, dict):
            continue
        addr_i = _parse_addr_int(hex_addr)
        if addr_i is None:
            continue
        name = str(info.get("name") or hex_addr).strip()
        desc = str(info.get("description") or "").strip()
        low = f"{name} {desc}".lower()
        entry = {
            "name": name,
            "addr": addr_i,
            "addr_hex": f"0x{addr_i:04X}",
            "description": desc,
        }
        if "product" in low or name.lower().startswith(("espresso", "coffee", "ristretto", "cappuccino", "latte", "macchiato", "flat_white", "americano", "ground_coffee", "aroma_boost")):
            products.append(entry)
        elif any(tok in low for tok in maint_tokens):
            maintenance.append(entry)

    return {"products": products, "maintenance": maintenance, "maintenance_pct": maint_pct}


def _extract_override_offsets(ov: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Normalize an EEPROM offset override dictionary into standard lists."""
    def _clean(rows: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict):
                continue
            addr_i = _parse_addr_int(row.get("addr") if "addr" in row else row.get("addr_hex"))
            if addr_i is None:
                continue
            item = {
                "name": str(row.get("name") or f"0x{addr_i:04X}").strip(),
                "addr": addr_i,
                "addr_hex": f"0x{addr_i:04X}",
            }
            if "byte" in row:
                item["byte"] = str(row["byte"]).strip().lower()
            if "joe_count" in row:
                item["joe_count"] = row["joe_count"]
            if "joe_pct" in row:
                item["joe_pct"] = row["joe_pct"]
            out.append(item)
        return out

    return {
        "products": _clean(ov.get("products")),
        "maintenance": _clean(ov.get("maintenance")),
        "maintenance_pct": _clean(ov.get("maintenance_pct")),
    }


def _matches_connected(
    entry: Dict[str, Any],
    detected_ef: str,
    detected_art: str,
    detected_model: str,
) -> bool:
    if HAS_RUST_CORE and _rust_core is not None and hasattr(_rust_core, "machine_matches_connected"):
        try:
            return bool(_rust_core.machine_matches_connected(
                str(entry.get("ef_code") or ""),
                [str(a) for a in (entry.get("article_numbers") or [])],
                str(entry.get("model_family") or ""),
                str(detected_ef or ""),
                str(detected_art or ""),
                str(detected_model or ""),
            ))
        except Exception:
            pass
    det_ef = _norm_ef(detected_ef)
    det_art = (detected_art or "").strip()
    det_model = (detected_model or "").strip().lower()

    if det_ef and entry.get("ef_code", "").upper() == det_ef:
        return True
    if det_art and det_art in entry.get("article_numbers", []):
        return True
    if det_model and entry.get("model_family"):
        mf = entry["model_family"].lower()
        if mf == det_model or mf in det_model or det_model in mf:
            return True
    return False


def _build_base_catalog_cached() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    global _CACHED_BASE_CATALOG, _CACHED_CATALOG_SIG, _CACHED_OFFSET_DB_STATUS

    ov_path = profiles_db.EEPROM_OVERRIDES_FILE
    try:
        ov_mtime = os.stat(ov_path).st_mtime if os.path.exists(ov_path) else -1.0
    except OSError:
        ov_mtime = -1.0

    synced_path = ""
    synced_mtime = -1.0
    try:
        import offset_db_sync
        synced_path = offset_db_sync.SYNCED_OFFSETS_FILE
        if os.path.exists(synced_path):
            synced_mtime = os.stat(synced_path).st_mtime
    except Exception:
        pass

    sig = (ov_mtime, synced_mtime, ov_path, synced_path)
    with _CATALOG_LOCK:
        if _CACHED_BASE_CATALOG is not None and _CACHED_CATALOG_SIG == sig and _CACHED_OFFSET_DB_STATUS is not None:
            return copy.deepcopy(_CACHED_BASE_CATALOG), dict(_CACHED_OFFSET_DB_STATUS)

    profiles = profiles_db.load_profiles() or {}
    specs = profiles_db.load_model_specs() or {}
    overrides = profiles_db.list_eeprom_offset_overrides() or {}

    catalog_by_key: Dict[str, Dict[str, Any]] = {}

    def _get_or_init(key: str, ef_code: str, model_family: str) -> Dict[str, Any]:
        if key not in catalog_by_key:
            catalog_by_key[key] = {
                "id": key,
                "ef_code": ef_code,
                "model_family": model_family or ef_code or key,
                "series": "",
                "manufacturer": "Jura",
                "article_numbers": [],
                "sources": [],
                "active_source": "Built-in Profile",
                "has_verified_spec": False,
                "has_local_override": False,
                "override_key": "",
                "address_width": 4,
                "max_words": 512,
                "product_labels": [],
                "maintenance_labels": [],
                "offsets": {"products": [], "maintenance": [], "maintenance_pct": []},
                "notes": "",
                "is_connected_match": False,
            }
        return catalog_by_key[key]

    # 1. Built-in profiles (profiles_data.json)
    for ef_raw, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        ef = _norm_ef(ef_raw)
        if not ef:
            continue
        entry = _get_or_init(ef, ef, str(prof.get("model_family") or ef))
        if "Built-in Profile" not in entry["sources"]:
            entry["sources"].append("Built-in Profile")
        prods = [p.get("name", "") for p in (prof.get("products") or []) if isinstance(p, dict) and p.get("name")]
        entry["product_labels"] = prods
        entry["maintenance_labels"] = _norm_str_list(prof.get("maintenance_counters"))

    # 2. Verified model specs (docs/models/*.json)
    for spec_key, spec in specs.items():
        if not isinstance(spec, dict):
            continue
        ef = _norm_ef(spec.get("ef_code") or spec_key)
        key = ef or str(spec_key)
        entry = _get_or_init(key, ef, str(spec.get("model_family") or key))
        entry["series"] = str(spec.get("series") or entry["series"] or "")
        entry["has_verified_spec"] = True
        if "Verified Model Spec" not in entry["sources"]:
            entry["sources"].append("Verified Model Spec")
        entry["active_source"] = "Verified Model Spec"
        entry["address_width"] = int(spec.get("address_width") or entry["address_width"])
        entry["max_words"] = int(spec.get("max_words") or entry["max_words"])

        arts = set(entry["article_numbers"])
        if spec.get("article_number"):
            arts.add(str(spec["article_number"]).strip())
        for a in spec.get("article_numbers") or []:
            if str(a).strip():
                arts.add(str(a).strip())
        entry["article_numbers"] = sorted(arts)

        if not entry["product_labels"] and isinstance(spec.get("products"), list):
            entry["product_labels"] = [
                p.get("name", "") for p in spec["products"] if isinstance(p, dict) and p.get("name")
            ]
        if not entry["maintenance_labels"] and spec.get("maintenance_counters"):
            entry["maintenance_labels"] = _norm_str_list(spec.get("maintenance_counters"))

        spec_offsets = _extract_spec_offsets(spec)
        if spec_offsets["products"] or spec_offsets["maintenance"]:
            entry["offsets"] = spec_offsets

    # 2b. Layer 2: Ed25519-Verified Synced Offset DB (~/.config/spectra/synced_offsets_db.json)
    offset_db_status = {"offset_db_version": f"bundled-{version.BUILD_NUMBER}", "source": "bundled_factory"}
    synced_db = None
    try:
        import offset_db_sync
        offset_db_status = offset_db_sync.get_offset_db_status()
        synced_db = offset_db_sync.load_synced_offset_db()
    except Exception:
        synced_db = None

    if synced_db and isinstance(synced_db.get("machines"), dict):
        for mid, sspec in synced_db["machines"].items():
            if not isinstance(sspec, dict):
                continue
            ef = _norm_ef(sspec.get("ef_code") or "")
            arts_in = [str(a).strip() for a in (sspec.get("article_numbers") or []) if str(a).strip()]
            if sspec.get("article_number") and str(sspec["article_number"]).strip() not in arts_in:
                arts_in.append(str(sspec["article_number"]).strip())
            key = str(mid or ef or (f"ART_{arts_in[0]}" if arts_in else "SYNCED"))
            entry = _get_or_init(key, ef, str(sspec.get("model_family") or key))
            entry["series"] = str(sspec.get("series") or entry["series"] or "")
            entry["has_synced_pack"] = True
            entry["has_verified_spec"] = True
            if "Synced Offset DB (Ed25519)" not in entry["sources"]:
                entry["sources"].append("Synced Offset DB (Ed25519)")
            entry["active_source"] = "Synced Offset DB (Ed25519)"
            entry["address_width"] = int(sspec.get("address_width") or entry["address_width"])
            entry["max_words"] = int(sspec.get("max_words") or entry["max_words"])
            arts = set(entry["article_numbers"]) | set(arts_in)
            entry["article_numbers"] = sorted(arts)
            sv = sspec.get("verified_offsets") if isinstance(sspec.get("verified_offsets"), dict) else {}
            sv_offsets = _extract_override_offsets(sv)
            if sv_offsets["products"] or sv_offsets["maintenance"] or sv_offsets["maintenance_pct"]:
                entry["offsets"] = sv_offsets
                entry["product_labels"] = [p["name"] for p in sv_offsets["products"]]
                entry["maintenance_labels"] = [m["name"] for m in sv_offsets["maintenance"]]
            if sspec.get("notes"):
                entry["notes"] = str(sspec["notes"])

    # 3. Layer 1 (Highest): Local calibrated overrides (~/.config/spectra/eeprom_overrides.json)
    for ov_key, ov in overrides.items():
        if not isinstance(ov, dict):
            continue
        ef = _norm_ef(ov.get("ef_code") or "")
        art = str(ov.get("article_number") or "").strip()
        mname = str(ov.get("model_name") or "").strip()

        target_key = ef if ef and ef in catalog_by_key else ""
        if not target_key and art:
            for ck, item in catalog_by_key.items():
                if art in item["article_numbers"]:
                    target_key = ck
                    break
        if not target_key:
            target_key = ef or (f"ART_{art}" if art else ov_key)

        entry = _get_or_init(target_key, ef, mname or target_key)
        entry["has_local_override"] = True
        entry["override_key"] = ov_key
        if "Local Override" not in entry["sources"]:
            entry["sources"].append("Local Override")
        entry["active_source"] = "Local Override"
        if art and art not in entry["article_numbers"]:
            entry["article_numbers"].append(art)
            entry["article_numbers"].sort()
        ov_offsets = _extract_override_offsets(ov)
        if ov_offsets["products"] or ov_offsets["maintenance"] or ov_offsets["maintenance_pct"]:
            entry["offsets"] = ov_offsets
        if ov.get("notes"):
            entry["notes"] = str(ov["notes"])

    with _CATALOG_LOCK:
        _CACHED_BASE_CATALOG = copy.deepcopy(catalog_by_key)
        _CACHED_OFFSET_DB_STATUS = dict(offset_db_status)
        _CACHED_CATALOG_SIG = sig

    return catalog_by_key, offset_db_status


def list_machines(
    detected_ef: str = "",
    detected_art: str = "",
    detected_model: str = "",
) -> Dict[str, Any]:
    """
    Build a unified searchable catalog of every machine across built-in profiles,
    verified model JSON specs, and local user/community offset overrides.
    """
    catalog_by_key, offset_db_status = _build_base_catalog_cached()
    machines = list(catalog_by_key.values())
    active_match = None
    for m in machines:
        m.setdefault("has_synced_pack", False)
        m["product_count"] = len(m["offsets"]["products"]) or len(m["product_labels"])
        m["maintenance_count"] = len(m["offsets"]["maintenance"]) or len(m["maintenance_labels"])
        m["pct_count"] = len(m["offsets"]["maintenance_pct"])
        matched = _matches_connected(m, detected_ef, detected_art, detected_model)
        m["is_connected_match"] = matched
        if matched and (
            active_match is None
            or (m["has_local_override"] and not active_match["has_local_override"])
            or (m["has_synced_pack"] and not active_match.get("has_synced_pack") and not active_match["has_local_override"])
            or (m["has_verified_spec"] and not active_match["has_verified_spec"] and not active_match["has_local_override"])
        ):
            active_match = m

    machines.sort(
        key=lambda x: (
            0 if x["is_connected_match"] else 1,
            0 if x["has_local_override"] else 1,
            0 if x.get("has_synced_pack") else 1,
            0 if x["has_verified_spec"] else 1,
            x["model_family"].lower(),
            x["ef_code"],
        )
    )

    return {
        "total_machines": len(machines),
        "verified_specs_count": sum(1 for m in machines if m["has_verified_spec"]),
        "synced_db_count": sum(1 for m in machines if m.get("has_synced_pack")),
        "local_overrides_count": sum(1 for m in machines if m["has_local_override"]),
        "offset_db_version": offset_db_status.get("offset_db_version", f"bundled-{version.BUILD_NUMBER}"),
        "offset_db_source": offset_db_status.get("source", "bundled_factory"),
        "connected_match": active_match,
        "machines": machines,
    }


def resolve_active_machine(
    ef_code: str = "",
    article_number: str = "",
    model_name: str = "",
) -> Optional[Dict[str, Any]]:
    """Resolve the single best matching machine profile for a connected unit."""
    res = list_machines(
        detected_ef=ef_code,
        detected_art=article_number,
        detected_model=model_name,
    )
    return res.get("connected_match")


def build_offset_patch_payload(
    override: Dict[str, Any],
    identity: Optional[Dict[str, Any]] = None,
    include_eeprom: bool = False,
    eeprom_words: Optional[Dict[Any, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a clean, shareable JSON offset patch (`spectra.offset_patch.v1`) suitable
    for community contribution or manual `.json` file export/import.
    """
    ident = identity if isinstance(identity, dict) else {}
    ef_code = _norm_ef(override.get("ef_code") or ident.get("ef_code") or "")
    art = str(override.get("article_number") or ident.get("article_number") or "").strip()
    model_name = str(override.get("model_name") or ident.get("model_name") or "Unknown").strip()
    serial_num = str(override.get("serial_number") or ident.get("serial_number") or "").strip()
    market_reg = str(override.get("market_region") or ident.get("market_region") or "").strip()
    norms = _extract_override_offsets(override)
    try:
        import offset_db_sync
        odb_ver = offset_db_sync.get_offset_db_version()
    except Exception:
        odb_ver = f"bundled-{version.BUILD_NUMBER}"

    patch: Dict[str, Any] = {
        "schema": SCHEMA_PATCH_V1,
        "build": version.BUILD_NUMBER,
        "offset_db_version": odb_ver,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "identity": {
            "manufacturer": ident.get("manufacturer") or "Jura",
            "ef_code": ef_code,
            "article_number": art,
            "model_name": model_name,
            "serial_number": serial_num,
            "market_region": market_reg,
        },
        "override": {
            "ef_code": ef_code,
            "article_number": art,
            "model_name": model_name,
            "serial_number": serial_num,
            "market_region": market_reg,
            "source": override.get("source") or "ai_joe_calibration",
            "extraction_source": override.get("extraction_source") or "csv_or_screenshot",
            "model_used": override.get("model_used") or "local_ai",
            "products": norms["products"],
            "maintenance": norms["maintenance"],
            "maintenance_pct": norms["maintenance_pct"],
            "notes": str(override.get("notes") or ""),
        },
    }
    if include_eeprom and isinstance(eeprom_words, dict) and eeprom_words:
        patch["eeprom_words"] = eeprom_words
    return patch


def import_offset_patch(raw_payload: Any, model_key: Optional[str] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validate and import a JSON offset patch (`spectra.offset_patch.v1`, capture bundle
    with `ai_offset_fix`, or raw override dict) into the local Machine Library.
    """
    data = raw_payload
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception as e:
            return False, f"Invalid JSON file: {e}", None

    if not isinstance(data, dict):
        return False, "Offset patch must be a JSON object.", None

    candidate = data.get("override") or data.get("ai_offset_fix") or data
    if not isinstance(candidate, dict):
        return False, "No valid offset override section found inside JSON.", None

    ident = data.get("identity") if isinstance(data.get("identity"), dict) else {}
    normalized = _extract_override_offsets(candidate)
    if not normalized["products"] and not normalized["maintenance"] and not normalized["maintenance_pct"]:
        if not any(str(candidate.get(k) or ident.get(k) or "").strip() for k in ("model_name", "article_number", "serial_number")):
            return False, "Offset patch contains zero valid product/maintenance addresses or identity overrides.", None

    override_to_save = {
        "ef_code": _norm_ef(candidate.get("ef_code") or ident.get("ef_code") or ""),
        "article_number": str(candidate.get("article_number") or ident.get("article_number") or "").strip(),
        "model_name": str(candidate.get("model_name") or ident.get("model_name") or "Imported Machine").strip(),
        "serial_number": str(candidate.get("serial_number") or ident.get("serial_number") or "").strip(),
        "market_region": str(candidate.get("market_region") or ident.get("market_region") or "").strip(),
        "source": str(candidate.get("source") or "imported_patch"),
        "extraction_source": str(candidate.get("extraction_source") or "json_patch"),
        "model_used": str(candidate.get("model_used") or "community_patch"),
        "products": normalized["products"],
        "maintenance": normalized["maintenance"],
        "maintenance_pct": normalized["maintenance_pct"],
        "notes": str(candidate.get("notes") or "Imported into SPECTRA Machine Library."),
    }

    saved = profiles_db.save_eeprom_offset_override(override_to_save, model_key=model_key)
    return True, f"Imported offset patch for {override_to_save['model_name'] or override_to_save['ef_code']}.", saved
