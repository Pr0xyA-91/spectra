#!/usr/bin/env python3
"""
SPECTRA Ed25519-Signed Machine Offset Database Sync Engine
==========================================================
Zero-dependency (Python stdlib only) cryptographic verifier and explicit
opt-in synchronizer for signed SPECTRA machine EEPROM offset packs.

Security guarantees:
  1. Pure-stdlib RFC 8032 Ed25519 signature verification (verified against
     official RFC 8032 section 7.1 test vectors) with strict S < L and
     small-order public key rejection.
  2. Domain-separated canonical JSON signing for both manifest and pack.
  3. Constant-time SHA-256 verification of raw downloaded pack bytes.
  4. Strict allowlist schema validation on every machine & register offset
     (rejects unexpected keys, non-int/out-of-range addresses, XSS/HTML/script
     payloads, control characters, secrets, and PII).
  5. Fail-closed verification: never bypasses signature verification, never
     trusts a key embedded in the downloaded file, and NEVER silently overwrites
     without explicit user action.

3-Layer Runtime Precedence:
  Layer 1: Local Technician Override (~/.config/spectra/eeprom_overrides.json)
  Layer 2: Synced Verified Offset Pack (~/.config/spectra/synced_offsets_db.json)
  Layer 3: Bundled Factory Profiles (docs/models/*.json + profiles_data.json)
"""

import base64
import copy
import datetime
import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import tls_utils
import version

# ============================================================================
# Pure-Stdlib RFC 8032 Ed25519 Implementation (Zero External Dependencies)
# ============================================================================

_ED_P = (1 << 255) - 19
_ED_L = (1 << 252) + 27742317777372353535851937790883648493
_ED_D = (-121665 * pow(121666, _ED_P - 2, _ED_P)) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)  # sqrt(-1) mod p

# Base point B = (Bx, By) with By = 4/5 mod p, Bx positive (even)
_ED_BY = (4 * pow(5, _ED_P - 2, _ED_P)) % _ED_P


def _ed_xrecover(y: int) -> Optional[int]:
    """Recover x from y on -x^2 + y^2 = 1 + d*x^2*y^2 (mod p). Returns None if not on curve."""
    y2 = (y * y) % _ED_P
    num = (y2 - 1) % _ED_P
    den = (_ED_D * y2 + 1) % _ED_P
    x2 = (num * pow(den, _ED_P - 2, _ED_P)) % _ED_P
    if x2 == 0:
        return 0
    x = pow(x2, (_ED_P + 3) // 8, _ED_P)
    if (x * x - x2) % _ED_P != 0:
        x = (x * _ED_I) % _ED_P
    if (x * x - x2) % _ED_P != 0:
        return None
    if x & 1:
        x = _ED_P - x
    return x


_ED_BX = _ed_xrecover(_ED_BY)
assert _ED_BX is not None
_ED_B = (_ED_BX, _ED_BY, 1, (_ED_BX * _ED_BY) % _ED_P)
_ED_ZERO = (0, 1, 1, 0)


def _ed_point_add(
    p1: Tuple[int, int, int, int],
    p2: Tuple[int, int, int, int],
) -> Tuple[int, int, int, int]:
    """Complete unified point addition in extended Twisted Edwards coordinates (X, Y, Z, T)."""
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = ((y1 - x1) * (y2 - x2)) % _ED_P
    b = ((y1 + x1) * (y2 + x2)) % _ED_P
    c = (2 * _ED_D * t1 * t2) % _ED_P
    d = (2 * z1 * z2) % _ED_P
    e = (b - a) % _ED_P
    f = (d - c) % _ED_P
    g = (d + c) % _ED_P
    h = (b + a) % _ED_P
    return ((e * f) % _ED_P, (g * h) % _ED_P, (f * g) % _ED_P, (e * h) % _ED_P)


def _ed_point_double(p1: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """Point doubling in extended Twisted Edwards coordinates."""
    x1, y1, z1, _ = p1
    a = (x1 * x1) % _ED_P
    b = (y1 * y1) % _ED_P
    c = (2 * z1 * z1) % _ED_P
    h = (a + b) % _ED_P
    e = (h - ((x1 + y1) * (x1 + y1))) % _ED_P
    g = (a - b) % _ED_P
    f = (c + g) % _ED_P
    return ((e * f) % _ED_P, (g * h) % _ED_P, (f * g) % _ED_P, (e * h) % _ED_P)


_ED_BASE_WINDOW_TABLES: Optional[List[List[Tuple[int, int, int, int]]]] = None


def _get_ed_base_window_tables() -> List[List[Tuple[int, int, int, int]]]:
    global _ED_BASE_WINDOW_TABLES
    if _ED_BASE_WINDOW_TABLES is None:
        tables: List[List[Tuple[int, int, int, int]]] = []
        base = _ED_B
        for _ in range(64):  # 64 x 4-bit nibbles = 256 bits
            tbl: List[Tuple[int, int, int, int]] = [_ED_ZERO]
            acc = _ED_ZERO
            for _j in range(1, 16):
                acc = _ed_point_add(acc, base)
                tbl.append(acc)
            tables.append(tbl)
            for _d in range(4):
                base = _ed_point_double(base)
        _ED_BASE_WINDOW_TABLES = tables
    return _ED_BASE_WINDOW_TABLES


def _ed_scalar_mult_base(scalar: int) -> Tuple[int, int, int, int]:
    """Fixed-base 4-bit windowed scalar multiplication on _ED_B."""
    if scalar <= 0:
        return _ED_ZERO
    tables = _get_ed_base_window_tables()
    res = _ED_ZERO
    k = scalar
    win_idx = 0
    while k > 0 and win_idx < len(tables):
        nib = k & 0xF
        if nib:
            res = _ed_point_add(res, tables[win_idx][nib])
        k >>= 4
        win_idx += 1
    if k > 0:
        # Handle scalars >= 2^256 cleanly
        res = _ed_point_add(res, _ed_scalar_mult(_ed_point_double(tables[-1][8]), k))
    return res


def _ed_scalar_mult(point: Tuple[int, int, int, int], scalar: int) -> Tuple[int, int, int, int]:
    """Windowed scalar multiplication on Edwards25519."""
    if point is _ED_B:
        return _ed_scalar_mult_base(scalar)
    res = _ED_ZERO
    addend = point
    k = scalar
    while k > 0:
        if k & 1:
            res = _ed_point_add(res, addend)
        addend = _ed_point_double(addend)
        k >>= 1
    return res


def _ed_point_equal(
    p1: Tuple[int, int, int, int],
    p2: Tuple[int, int, int, int],
) -> bool:
    """Compare two extended points without field inversion."""
    if (p1[0] * p2[2] - p2[0] * p1[2]) % _ED_P != 0:
        return False
    if (p1[1] * p2[2] - p2[1] * p1[2]) % _ED_P != 0:
        return False
    return True


def _ed_encode_point(point: Tuple[int, int, int, int]) -> bytes:
    """Encode an extended point into 32-byte RFC 8032 compressed representation."""
    x, y, z, _ = point
    zinv = pow(z, _ED_P - 2, _ED_P)
    ax = (x * zinv) % _ED_P
    ay = (y * zinv) % _ED_P
    val = ay | ((ax & 1) << 255)
    return val.to_bytes(32, "little")


def _ed_decode_point(raw: bytes) -> Optional[Tuple[int, int, int, int]]:
    """Decode a 32-byte RFC 8032 compressed point strictly (rejecting y >= p and non-canonical x=0)."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != 32:
        return None
    val = int.from_bytes(raw, "little")
    sign = (val >> 255) & 1
    y = val & ((1 << 255) - 1)
    if y >= _ED_P:
        return None
    x = _ed_xrecover(y)
    if x is None:
        return None
    if x == 0 and sign == 1:
        return None
    if (x & 1) != sign:
        x = _ED_P - x
    return (x, y, 1, (x * y) % _ED_P)


def _ed_is_small_order(point: Tuple[int, int, int, int]) -> bool:
    """Return True if [8]P == O (identity), rejecting low-order public keys."""
    p2 = _ed_point_double(point)
    p4 = _ed_point_double(p2)
    p8 = _ed_point_double(p4)
    return _ed_point_equal(p8, _ED_ZERO)


def ed25519_public_key_from_seed(seed: bytes) -> bytes:
    """Derive 32-byte RFC 8032 Ed25519 public key from a 32-byte secret seed."""
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
        raise ValueError("Ed25519 seed must be exactly 32 bytes")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return _ed_encode_point(_ed_scalar_mult(_ED_B, a))


def ed25519_sign(seed: bytes, message: bytes) -> bytes:
    """Produce a deterministic 64-byte RFC 8032 Ed25519 signature."""
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
        raise ValueError("Ed25519 seed must be exactly 32 bytes")
    if not isinstance(message, (bytes, bytearray)):
        raise ValueError("Ed25519 message must be bytes")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    prefix = h[32:]
    pub = _ed_encode_point(_ed_scalar_mult(_ED_B, a))
    r = int.from_bytes(hashlib.sha512(prefix + bytes(message)).digest(), "little") % _ED_L
    r_bytes = _ed_encode_point(_ed_scalar_mult(_ED_B, r))
    k = int.from_bytes(hashlib.sha512(r_bytes + pub + bytes(message)).digest(), "little") % _ED_L
    s = (r + k * a) % _ED_L
    return r_bytes + s.to_bytes(32, "little")


def ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """
    Strictly verify a 64-byte RFC 8032 Ed25519 signature over `message`.
    Rejects invalid point encodings, small-order public keys, and malleable S >= L.
    """
    try:
        if (
            not isinstance(public_key, (bytes, bytearray))
            or len(public_key) != 32
            or not isinstance(signature, (bytes, bytearray))
            or len(signature) != 64
            or not isinstance(message, (bytes, bytearray))
        ):
            return False

        a_point = _ed_decode_point(bytes(public_key))
        if a_point is None or _ed_is_small_order(a_point):
            return False

        r_bytes = bytes(signature[:32])
        s_int = int.from_bytes(signature[32:], "little")
        if s_int >= _ED_L:
            return False

        r_point = _ed_decode_point(r_bytes)
        if r_point is None:
            return False

        k = int.from_bytes(
            hashlib.sha512(r_bytes + bytes(public_key) + bytes(message)).digest(),
            "little",
        ) % _ED_L

        lhs = _ed_scalar_mult(_ED_B, s_int)
        rhs = _ed_point_add(r_point, _ed_scalar_mult(a_point, k))
        return _ed_point_equal(lhs, rhs)
    except Exception:
        return False


# ============================================================================
# Signed Offset DB Configuration, Schema Constants & Trusted Keys
# ============================================================================

SCHEMA_MANIFEST_V1 = "spectra.offsets_db_manifest.v1"
SCHEMA_PACK_V1 = "spectra.offsets_db_pack.v1"
MANIFEST_DOMAIN_PREFIX = b"SPECTRA-OFFSETS-MANIFEST-V1\n"
PACK_DOMAIN_PREFIX = b"SPECTRA-OFFSETS-PACK-V1\n"

MAX_MANIFEST_BYTES = 256 * 1024       # 256 KB ceiling for manifest
MAX_PACK_BYTES = 2 * 1024 * 1024      # 2 MB ceiling for full signed offset pack
CHECK_CACHE_TTL_SEC = 300.0

OFFSETS_REPO = (
    (os.environ.get("SPECTRA_OFFSETS_REPO") or os.environ.get("SPECTRA_UPDATE_REPO") or "Pr0xyA-91/spectra").strip()
    or "Pr0xyA-91/spectra"
)
DEFAULT_MANIFEST_URL = (
    (os.environ.get("SPECTRA_OFFSETS_MANIFEST_URL") or "").strip()
    or f"https://raw.githubusercontent.com/{OFFSETS_REPO}/main/offsets_db/manifest.json"
)
DEFAULT_PACK_BASE_URL = (
    (os.environ.get("SPECTRA_OFFSETS_BASE_URL") or "").strip()
    or f"https://raw.githubusercontent.com/{OFFSETS_REPO}/main/offsets_db/"
)

SYNCED_OFFSETS_FILE = os.path.join(os.path.expanduser("~/.config/spectra"), "synced_offsets_db.json")
LOCAL_TRUSTED_KEYS_FILE = os.path.join(os.path.expanduser("~/.config/spectra"), "offsets_trusted_keys.json")

# Pinned production Ed25519 public keys (key_id -> 64-char hex or base64 of 32-byte pubkey).
# Maintainer generates keypair locally in `spectra-hub` and pins the public key here before release.
TRUSTED_OFFSET_DB_PUBLIC_KEYS: Dict[str, str] = {}

_ALLOWED_PACK_HOSTS: Set[str] = {
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}

_ALLOWED_MANIFEST_KEYS: Set[str] = {
    "schema",
    "version",
    "published_at",
    "expires_at",
    "key_id",
    "pack_file",
    "pack_url",
    "pack_sha256",
    "pack_size",
    "machine_count",
    "machines_index",
    "changelog",
    "notes",
    "signature_alg",
    "signature_b64",
}

_ALLOWED_MANIFEST_INDEX_KEYS: Set[str] = {
    "id",
    "ef_code",
    "model_family",
    "article_numbers",
    "entry_sha256",
    "products_count",
    "maintenance_count",
    "updated_at",
}

_ALLOWED_PACK_KEYS: Set[str] = {
    "schema",
    "version",
    "published_at",
    "key_id",
    "machines",
    "notes",
    "signature_alg",
    "signature_b64",
}

_ALLOWED_MACHINE_KEYS: Set[str] = {
    "id",
    "ef_code",
    "model_family",
    "series",
    "manufacturer",
    "appliance_type",
    "article_number",
    "article_numbers",
    "address_width",
    "max_words",
    "verified_offsets",
    "products",
    "maintenance_counters",
    "custom_registers",
    "notes",
    "source_issues",
    "updated_at",
}

_ALLOWED_OFFSET_SECTIONS: Set[str] = {"products", "maintenance", "maintenance_pct"}
_ALLOWED_PRODUCT_OFFSET_KEYS: Set[str] = {"code", "name", "addr", "addr_hex", "is_double", "confidence"}
_ALLOWED_MAINT_OFFSET_KEYS: Set[str] = {"name", "addr", "addr_hex", "confidence"}
_ALLOWED_PCT_OFFSET_KEYS: Set[str] = {"name", "addr", "addr_hex", "byte", "confidence"}

_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_VERSION_RE = re.compile(r"^[0-9]{8}\.[0-9]{4}(?:\.[0-9]{1,4})?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_ADDR_RE = re.compile(r"^0x[0-9A-Fa-f]{2,4}$")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_DANGEROUS_TEXT_RE = re.compile(
    r"(?i)(?:<\s*/?\s*(?:script|iframe|svg|object|embed)\b|javascript\s*:|on(?:error|load|click)\s*=|\$\{\{|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)

_SYNC_LOCK = threading.RLock()
_CACHED_PACK: Optional[Dict[str, Any]] = None
_CACHED_PACK_MTIME: float = -1.0
_CACHED_PACK_PATH: str = ""
_CACHED_CHECK: Optional[Dict[str, Any]] = None
_CACHED_CHECK_TS: float = 0.0
_CACHED_LOCAL_KEYS: Optional[Dict[str, bytes]] = None
_CACHED_LOCAL_KEYS_MTIME: float = -1.0
_CACHED_LOCAL_KEYS_PATH: str = ""


def invalidate_offset_db_cache() -> None:
    """Clear in-memory synced Offset DB and remote check caches."""
    global _CACHED_PACK, _CACHED_PACK_MTIME, _CACHED_PACK_PATH, _CACHED_CHECK, _CACHED_CHECK_TS
    global _CACHED_LOCAL_KEYS, _CACHED_LOCAL_KEYS_MTIME, _CACHED_LOCAL_KEYS_PATH
    with _SYNC_LOCK:
        _CACHED_PACK = None
        _CACHED_PACK_MTIME = -1.0
        _CACHED_PACK_PATH = ""
        _CACHED_CHECK = None
        _CACHED_CHECK_TS = 0.0
        _CACHED_LOCAL_KEYS = None
        _CACHED_LOCAL_KEYS_MTIME = -1.0
        _CACHED_LOCAL_KEYS_PATH = ""


# ============================================================================
# Canonical Serialization, Hashing & Key Parsing
# ============================================================================

def canonical_json_bytes(payload: Dict[str, Any], exclude_keys: Sequence[str] = ("signature_b64",)) -> bytes:
    """Produce deterministic UTF-8 JSON bytes for signing or hashing."""
    stripped = {k: v for k, v in payload.items() if k not in exclude_keys}
    return json.dumps(stripped, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_machine_entry_sha256(machine_entry: Dict[str, Any]) -> str:
    """Compute stable SHA-256 fingerprint of a single machine offset entry for diffing."""
    canon = json.dumps(machine_entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def parse_public_key_bytes(raw_key: str) -> Optional[bytes]:
    """Decode a 32-byte Ed25519 public key from 64-char hex or standard base64."""
    s = str(raw_key or "").strip()
    if not s:
        return None
    if re.fullmatch(r"[0-9a-fA-F]{64}", s):
        return bytes.fromhex(s)
    try:
        decoded = base64.b64decode(s, validate=True)
        return decoded if len(decoded) == 32 else None
    except Exception:
        return None


def _load_local_trusted_keys_cached() -> Dict[str, bytes]:
    global _CACHED_LOCAL_KEYS, _CACHED_LOCAL_KEYS_MTIME, _CACHED_LOCAL_KEYS_PATH
    path = LOCAL_TRUSTED_KEYS_FILE
    if not os.path.isfile(path):
        return {}
    try:
        st = os.stat(path)
        if os.name == "posix" and (st.st_mode & 0o022):
            return {}
        with _SYNC_LOCK:
            if (
                _CACHED_LOCAL_KEYS is not None
                and _CACHED_LOCAL_KEYS_PATH == path
                and st.st_mtime == _CACHED_LOCAL_KEYS_MTIME
            ):
                return dict(_CACHED_LOCAL_KEYS)
        with open(path, "r", encoding="utf-8") as fh:
            disk_keys = json.load(fh)
        parsed: Dict[str, bytes] = {}
        if isinstance(disk_keys, dict):
            raw_map = disk_keys.get("keys") if isinstance(disk_keys.get("keys"), dict) else disk_keys
            if isinstance(raw_map, dict):
                for kid, kval in raw_map.items():
                    kid_clean = str(kid or "").strip()
                    kb = parse_public_key_bytes(kval)
                    if kid_clean and kb is not None:
                        parsed[kid_clean] = kb
        with _SYNC_LOCK:
            _CACHED_LOCAL_KEYS = dict(parsed)
            _CACHED_LOCAL_KEYS_MTIME = st.st_mtime
            _CACHED_LOCAL_KEYS_PATH = path
        return parsed
    except Exception:
        return {}


def get_trusted_public_keys(extra_keys: Optional[Dict[str, str]] = None) -> Dict[str, bytes]:
    """
    Assemble trusted Ed25519 public keys from:
      1. Pinned TRUSTED_OFFSET_DB_PUBLIC_KEYS in code
      2. Optional local user keyring (~/.config/spectra/offsets_trusted_keys.json)
      3. Optional env var SPECTRA_OFFSET_DB_PUBKEY (with SPECTRA_OFFSET_DB_KEY_ID)
      4. Explicit extra_keys parameter (for tests)
    Never reads keys from downloaded remote payloads.
    """
    resolved: Dict[str, bytes] = {}

    def _add_map(src: Optional[Dict[str, str]]) -> None:
        if not isinstance(src, dict):
            return
        for kid, kval in src.items():
            kid_clean = str(kid or "").strip()
            kb = parse_public_key_bytes(kval)
            if kid_clean and kb is not None:
                resolved[kid_clean] = kb

    _add_map(TRUSTED_OFFSET_DB_PUBLIC_KEYS)
    resolved.update(_load_local_trusted_keys_cached())

    env_pub = (os.environ.get("SPECTRA_OFFSET_DB_PUBKEY") or "").strip()
    if env_pub:
        env_kid = (os.environ.get("SPECTRA_OFFSET_DB_KEY_ID") or "spectra-offsets-ed25519-2026-v1").strip()
        kb = parse_public_key_bytes(env_pub)
        if kb is not None:
            resolved[env_kid] = kb

    _add_map(extra_keys)
    return resolved


def parse_version_tuple(ver_str: str) -> Optional[Tuple[int, ...]]:
    """Parse YYYYMMDD.HHMM[.patch] into a comparable tuple."""
    s = str(ver_str or "").strip()
    if not _VERSION_RE.fullmatch(s):
        return None
    parts = [int(p) for p in s.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_version_newer(candidate: str, current: str) -> bool:
    """Return True if candidate version is strictly greater than current."""
    cand_t = parse_version_tuple(candidate)
    if cand_t is None:
        return False
    cur_t = parse_version_tuple(current)
    if cur_t is None:
        return True
    return cand_t > cur_t


# ============================================================================
# Strict Allowlist Schema Validation
# ============================================================================

def _validate_safe_string(val: Any, field: str, max_len: int = 160, allow_empty: bool = False) -> Tuple[bool, str]:
    if not isinstance(val, str):
        return False, f"{field} must be a string"
    s = val.strip()
    if not s and not allow_empty:
        return False, f"{field} must not be empty"
    if len(s) > max_len:
        return False, f"{field} exceeds max length ({len(s)} > {max_len})"
    if _CONTROL_CHAR_RE.search(s):
        return False, f"{field} contains forbidden control characters"
    if _DANGEROUS_TEXT_RE.search(s):
        return False, f"{field} failed XSS/secret/poisoning check"
    return True, ""


def _validate_offset_item(item: Any, section: str, path: str) -> Tuple[bool, str]:
    if not isinstance(item, dict):
        return False, f"{path} must be an object"
    allowed = (
        _ALLOWED_PRODUCT_OFFSET_KEYS
        if section == "products"
        else (_ALLOWED_MAINT_OFFSET_KEYS if section == "maintenance" else _ALLOWED_PCT_OFFSET_KEYS)
    )
    extra = set(item.keys()) - allowed
    if extra:
        return False, f"{path} contains disallowed keys: {sorted(extra)}"

    ok, err = _validate_safe_string(item.get("name"), f"{path}.name", max_len=100)
    if not ok:
        return False, err

    addr = item.get("addr")
    if isinstance(addr, bool) or not isinstance(addr, int) or not (0 <= addr <= 0xFFFF):
        return False, f"{path}.addr must be an integer in 0..65535"

    if "addr_hex" in item:
        ah = str(item.get("addr_hex") or "").strip()
        if not _HEX_ADDR_RE.fullmatch(ah) or int(ah, 16) != addr:
            return False, f"{path}.addr_hex ({ah!r}) does not match addr {addr}"

    if section == "products":
        if "is_double" in item and not isinstance(item["is_double"], bool):
            return False, f"{path}.is_double must be boolean"
        if "code" in item and (isinstance(item["code"], bool) or not isinstance(item["code"], int) or not (1 <= item["code"] <= 999)):
            return False, f"{path}.code must be an integer 1..999"

    if section == "maintenance_pct":
        b = str(item.get("byte") or "low").strip().lower()
        if b not in ("low", "high"):
            return False, f"{path}.byte must be 'low' or 'high'"

    if "confidence" in item:
        conf = str(item.get("confidence") or "").strip().lower()
        if conf not in ("high", "medium", "verified", "low"):
            return False, f"{path}.confidence invalid: {conf!r}"

    return True, ""


def validate_machine_entry(machine_id: str, entry: Any) -> Tuple[bool, str]:
    """Enforce strict allowlist schema validation on a single machine entry."""
    ok, err = _validate_safe_string(machine_id, "machine_id", max_len=80)
    if not ok:
        return False, err
    if not isinstance(entry, dict):
        return False, f"machines[{machine_id}] must be an object"
    extra = set(entry.keys()) - _ALLOWED_MACHINE_KEYS
    if extra:
        return False, f"machines[{machine_id}] has disallowed keys: {sorted(extra)}"

    for req_str in ("ef_code", "model_family"):
        ok, err = _validate_safe_string(entry.get(req_str), f"machines[{machine_id}].{req_str}", max_len=100)
        if not ok:
            return False, err

    for opt_str in ("id", "series", "manufacturer", "appliance_type", "article_number", "notes", "updated_at"):
        if opt_str in entry and entry[opt_str] is not None:
            ok, err = _validate_safe_string(entry[opt_str], f"machines[{machine_id}].{opt_str}", max_len=300, allow_empty=True)
            if not ok:
                return False, err

    if "article_numbers" in entry:
        arts = entry["article_numbers"]
        if not isinstance(arts, list) or len(arts) > 32:
            return False, f"machines[{machine_id}].article_numbers must be a list of <= 32 entries"
        for idx, art in enumerate(arts):
            ok, err = _validate_safe_string(str(art), f"machines[{machine_id}].article_numbers[{idx}]", max_len=32)
            if not ok:
                return False, err

    if "address_width" in entry:
        aw = entry["address_width"]
        if isinstance(aw, bool) or aw not in (2, 4):
            return False, f"machines[{machine_id}].address_width must be 2 or 4"

    if "max_words" in entry:
        mw = entry["max_words"]
        if isinstance(mw, bool) or not isinstance(mw, int) or not (64 <= mw <= 4096):
            return False, f"machines[{machine_id}].max_words must be int 64..4096"

    vo = entry.get("verified_offsets")
    if not isinstance(vo, dict):
        return False, f"machines[{machine_id}].verified_offsets must be an object"
    extra_vo = set(vo.keys()) - _ALLOWED_OFFSET_SECTIONS
    if extra_vo:
        return False, f"machines[{machine_id}].verified_offsets has disallowed sections: {sorted(extra_vo)}"

    total_items = 0
    for sec in ("products", "maintenance", "maintenance_pct"):
        rows = vo.get(sec)
        if rows is None:
            continue
        if not isinstance(rows, list) or len(rows) > 96:
            return False, f"machines[{machine_id}].verified_offsets.{sec} must be list of <= 96 items"
        for idx, row in enumerate(rows):
            ok, err = _validate_offset_item(row, sec, f"machines[{machine_id}].verified_offsets.{sec}[{idx}]")
            if not ok:
                return False, err
            total_items += 1

    if total_items == 0:
        return False, f"machines[{machine_id}].verified_offsets contains no offsets"

    return True, ""


def validate_manifest_schema(manifest: Any) -> Tuple[bool, str]:
    """Validate signed manifest JSON strictly against allowlist schema."""
    if not isinstance(manifest, dict):
        return False, "Manifest root must be a JSON object"
    extra = set(manifest.keys()) - _ALLOWED_MANIFEST_KEYS
    if extra:
        return False, f"Manifest contains disallowed keys: {sorted(extra)}"
    if manifest.get("schema") != SCHEMA_MANIFEST_V1:
        return False, f"Unexpected manifest schema: {manifest.get('schema')!r}"
    if parse_version_tuple(str(manifest.get("version") or "")) is None:
        return False, f"Invalid manifest version: {manifest.get('version')!r}"
    if manifest.get("signature_alg") != "Ed25519":
        return False, f"Unsupported signature_alg: {manifest.get('signature_alg')!r}"
    if not _SHA256_RE.fullmatch(str(manifest.get("pack_sha256") or "")):
        return False, "Manifest pack_sha256 must be 64 lowercase hex characters"
    for req_s in ("key_id", "published_at", "signature_b64"):
        ok, err = _validate_safe_string(manifest.get(req_s), f"manifest.{req_s}", max_len=256)
        if not ok:
            return False, err
    pub_at = str(manifest.get("published_at") or "").strip()
    if not _ISO_UTC_RE.fullmatch(pub_at):
        return False, f"manifest.published_at must be ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ), got {pub_at!r}"
    try:
        datetime.datetime.strptime(pub_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False, f"manifest.published_at is not a valid UTC timestamp: {pub_at!r}"
    if "expires_at" in manifest and manifest["expires_at"] is not None:
        exp_at = str(manifest.get("expires_at") or "").strip()
        if not _ISO_UTC_RE.fullmatch(exp_at):
            return False, f"manifest.expires_at must be ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ), got {exp_at!r}"
        try:
            exp_dt = datetime.datetime.strptime(exp_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            return False, f"manifest.expires_at is not a valid UTC timestamp: {exp_at!r}"
        if exp_dt <= datetime.datetime.now(datetime.timezone.utc):
            return False, f"Manifest expired at {exp_at}"
    if "pack_size" in manifest:
        ps = manifest["pack_size"]
        if isinstance(ps, bool) or not isinstance(ps, int) or not (2 <= ps <= MAX_PACK_BYTES):
            return False, "Manifest pack_size out of allowed range"
    idx_list = manifest.get("machines_index")
    if not isinstance(idx_list, list) or len(idx_list) > 1024:
        return False, "Manifest machines_index must be a list of <= 1024 entries"
    for i, row in enumerate(idx_list):
        if not isinstance(row, dict):
            return False, f"manifest.machines_index[{i}] must be an object"
        ex = set(row.keys()) - _ALLOWED_MANIFEST_INDEX_KEYS
        if ex:
            return False, f"manifest.machines_index[{i}] has disallowed keys: {sorted(ex)}"
        for f in ("id", "ef_code", "model_family"):
            ok, err = _validate_safe_string(row.get(f), f"manifest.machines_index[{i}].{f}", max_len=120)
            if not ok:
                return False, err
        if "entry_sha256" in row and not _SHA256_RE.fullmatch(str(row.get("entry_sha256") or "")):
            return False, f"manifest.machines_index[{i}].entry_sha256 invalid"
    return True, ""


def validate_pack_schema(pack: Any) -> Tuple[bool, str]:
    """Validate signed offsets pack JSON strictly against allowlist schema."""
    if not isinstance(pack, dict):
        return False, "Offset pack root must be a JSON object"
    extra = set(pack.keys()) - _ALLOWED_PACK_KEYS
    if extra:
        return False, f"Offset pack contains disallowed keys: {sorted(extra)}"
    if pack.get("schema") != SCHEMA_PACK_V1:
        return False, f"Unexpected pack schema: {pack.get('schema')!r}"
    if parse_version_tuple(str(pack.get("version") or "")) is None:
        return False, f"Invalid pack version: {pack.get('version')!r}"
    if pack.get("signature_alg") != "Ed25519":
        return False, f"Unsupported pack signature_alg: {pack.get('signature_alg')!r}"
    for req_s in ("key_id", "published_at", "signature_b64"):
        ok, err = _validate_safe_string(pack.get(req_s), f"pack.{req_s}", max_len=256)
        if not ok:
            return False, err
    machines = pack.get("machines")
    if not isinstance(machines, dict) or len(machines) > 1024:
        return False, "pack.machines must be an object with <= 1024 entries"
    for mid, mentry in machines.items():
        ok, err = validate_machine_entry(mid, mentry)
        if not ok:
            return False, err
    return True, ""


# ============================================================================
# Cryptographic Verification (Ed25519 + SHA-256 + Anti-Rollback)
# ============================================================================

def verify_signed_manifest(
    manifest: Dict[str, Any],
    trusted_keys: Optional[Dict[str, bytes]] = None,
) -> Tuple[bool, str]:
    """Validate schema and verify Ed25519 signature of a manifest object."""
    ok, err = validate_manifest_schema(manifest)
    if not ok:
        return False, err
    keys = trusted_keys if trusted_keys is not None else get_trusted_public_keys()
    if not keys:
        return False, "No trusted Ed25519 public key configured for Offset DB verification."
    key_id = str(manifest.get("key_id") or "").strip()
    pubkey = keys.get(key_id)
    if pubkey is None:
        return False, f"Untrusted or unknown Offset DB signing key_id: {key_id!r}"
    try:
        sig = base64.b64decode(str(manifest.get("signature_b64") or ""), validate=True)
    except Exception:
        return False, "Malformed base64 Ed25519 signature in manifest."
    msg = MANIFEST_DOMAIN_PREFIX + canonical_json_bytes(manifest)
    if not ed25519_verify(pubkey, msg, sig):
        return False, "Ed25519 manifest signature verification FAILED."
    return True, "Ed25519 manifest signature verified."


def verify_signed_pack(
    raw_pack_bytes: bytes,
    manifest: Dict[str, Any],
    trusted_keys: Optional[Dict[str, bytes]] = None,
    current_synced_version: Optional[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Full fail-closed verification of a downloaded signed offset pack:
      1. Size limit <= 2 MB & exact manifest pack_size match
      2. Constant-time SHA-256 match against manifest.pack_sha256
      3. Strict allowlist schema validation
      4. Version / key_id consistency with signed manifest + anti-rollback check
      5. RFC 8032 Ed25519 signature verification over canonical pack bytes
    """
    if not isinstance(raw_pack_bytes, (bytes, bytearray)):
        return False, "Pack payload must be raw bytes.", None
    if len(raw_pack_bytes) > MAX_PACK_BYTES:
        return False, f"Offset pack exceeds maximum size ({len(raw_pack_bytes)} > {MAX_PACK_BYTES} bytes).", None

    ok_m, err_m = verify_signed_manifest(manifest, trusted_keys=trusted_keys)
    if not ok_m:
        return False, err_m, None

    expected_size = manifest.get("pack_size")
    if isinstance(expected_size, int) and len(raw_pack_bytes) != expected_size:
        return False, f"Offset pack size mismatch (got {len(raw_pack_bytes)}, expected {expected_size}).", None

    actual_sha = hashlib.sha256(raw_pack_bytes).hexdigest()
    expected_sha = str(manifest.get("pack_sha256") or "")
    if not hmac.compare_digest(actual_sha, expected_sha):
        return False, f"Offset pack SHA-256 mismatch (got {actual_sha[:16]}..., expected {expected_sha[:16]}...).", None

    try:
        pack = json.loads(raw_pack_bytes.decode("utf-8"))
    except Exception as exc:
        return False, f"Offset pack is not valid UTF-8 JSON: {exc}", None

    ok_s, err_s = validate_pack_schema(pack)
    if not ok_s:
        return False, err_s, None

    if pack.get("version") != manifest.get("version"):
        return False, "Offset pack version does not match signed manifest version.", None
    if pack.get("key_id") != manifest.get("key_id"):
        return False, "Offset pack key_id does not match signed manifest key_id.", None

    if current_synced_version:
        cur_t = parse_version_tuple(current_synced_version)
        new_t = parse_version_tuple(str(pack.get("version") or ""))
        if cur_t is not None and new_t is not None and new_t < cur_t:
            return False, f"Anti-rollback blocked downgrade from {current_synced_version} to {pack.get('version')}.", None

    keys = trusted_keys if trusted_keys is not None else get_trusted_public_keys()
    pubkey = keys.get(str(pack.get("key_id") or ""))
    if pubkey is None:
        return False, "Untrusted signing key_id on offset pack.", None
    try:
        sig = base64.b64decode(str(pack.get("signature_b64") or ""), validate=True)
    except Exception:
        return False, "Malformed base64 Ed25519 signature in offset pack.", None

    msg = PACK_DOMAIN_PREFIX + canonical_json_bytes(pack)
    if not ed25519_verify(pubkey, msg, sig):
        return False, "Ed25519 offset pack signature verification FAILED.", None

    return True, "Ed25519 signature, SHA-256, and strict schema verified.", pack


# ============================================================================
# Local Synced Store & 3-Layer Lookup Helpers
# ============================================================================

def _verify_stored_pack(pack: Any, trusted_keys: Optional[Dict[str, bytes]] = None) -> bool:
    """Re-verify on-disk synced pack schema & Ed25519 signature before trusting it at runtime."""
    if not isinstance(pack, dict):
        return False
    ok_s, _ = validate_pack_schema(pack)
    if not ok_s:
        return False
    keys = trusted_keys if trusted_keys is not None else get_trusted_public_keys()
    pubkey = keys.get(str(pack.get("key_id") or ""))
    if pubkey is None:
        return False
    try:
        sig = base64.b64decode(str(pack.get("signature_b64") or ""), validate=True)
    except Exception:
        return False
    msg = PACK_DOMAIN_PREFIX + canonical_json_bytes(pack)
    return ed25519_verify(pubkey, msg, sig)


def _load_synced_offset_db_ref(trusted_keys: Optional[Dict[str, bytes]] = None) -> Optional[Dict[str, Any]]:
    """Internal cached loader returning a shared reference when trusted_keys is None (do NOT mutate)."""
    global _CACHED_PACK, _CACHED_PACK_MTIME, _CACHED_PACK_PATH
    with _SYNC_LOCK:
        path = SYNCED_OFFSETS_FILE
        if not os.path.isfile(path):
            _CACHED_PACK = None
            _CACHED_PACK_MTIME = -1.0
            _CACHED_PACK_PATH = path
            return None
        try:
            st = os.stat(path)
            if (
                trusted_keys is None
                and _CACHED_PACK is not None
                and _CACHED_PACK_PATH == path
                and st.st_mtime == _CACHED_PACK_MTIME
            ):
                return _CACHED_PACK
            if st.st_size > MAX_PACK_BYTES:
                return None
            with open(path, "r", encoding="utf-8") as fh:
                wrapper = json.load(fh)
        except Exception:
            return None

        pack = wrapper.get("pack") if isinstance(wrapper, dict) and isinstance(wrapper.get("pack"), dict) else wrapper
        if not _verify_stored_pack(pack, trusted_keys=trusted_keys):
            return None

        result = {
            "version": str(pack.get("version") or ""),
            "published_at": str(pack.get("published_at") or ""),
            "key_id": str(pack.get("key_id") or ""),
            "synced_at": str(wrapper.get("synced_at") or "") if isinstance(wrapper, dict) else "",
            "pack_sha256": str(wrapper.get("pack_sha256") or "") if isinstance(wrapper, dict) else "",
            "machines": pack.get("machines") or {},
            "verified": True,
        }
        if trusted_keys is None:
            _CACHED_PACK = result
            _CACHED_PACK_MTIME = st.st_mtime
            _CACHED_PACK_PATH = path
        return result


def load_synced_offset_db(trusted_keys: Optional[Dict[str, bytes]] = None) -> Optional[Dict[str, Any]]:
    """Load and cryptographically verify `~/.config/spectra/synced_offsets_db.json` (cached by mtime)."""
    ref = _load_synced_offset_db_ref(trusted_keys=trusted_keys)
    return copy.deepcopy(ref) if ref is not None else None


def _norm_ef_token(raw: Optional[str]) -> str:
    txt = str(raw or "").strip().upper()
    m = re.search(r"(EF\w+)", txt)
    return m.group(1) if m else txt


def get_synced_machine_spec(
    ef_code: Optional[str] = None,
    article_number: Optional[str] = None,
    model_name: Optional[str] = None,
    trusted_keys: Optional[Dict[str, bytes]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Layer 2 lookup against the verified synced Offset DB.
    Resolution order: Article Number -> Exact EF string -> Base EF token -> Model Family.
    """
    db = load_synced_offset_db(trusted_keys=trusted_keys)
    if not db or not isinstance(db.get("machines"), dict):
        return None
    machines = db["machines"]

    art_clean = str(article_number or "").strip()
    if art_clean.lower() in ("unknown", "n/a", "none"):
        art_clean = ""
    ef_up = str(ef_code or "").strip().upper()
    ef_base = _norm_ef_token(ef_up)
    mod_low = str(model_name or "").strip().lower()

    matched: Optional[Dict[str, Any]] = None

    # 1. Article-first disambiguation (critical for shared EF chips like EF532M E60 vs WE6)
    if art_clean:
        for _mid, entry in machines.items():
            arts = {str(a).strip() for a in (entry.get("article_numbers") or [])}
            if entry.get("article_number"):
                arts.add(str(entry["article_number"]).strip())
            if art_clean in arts:
                matched = entry
                break

    # 2. Exact EF code + firmware version match
    if matched is None and ef_up:
        for _mid, entry in machines.items():
            if str(entry.get("ef_code") or "").strip().upper() == ef_up:
                matched = entry
                break

    # 3. Base EF token match (e.g. EF1012M)
    if matched is None and ef_base:
        for _mid, entry in machines.items():
            if _norm_ef_token(entry.get("ef_code")) == ef_base:
                matched = entry
                break

    # 4. Exact model family match
    if matched is None and mod_low and mod_low not in ("unknown", "generic jura automatic"):
        for _mid, entry in machines.items():
            if str(entry.get("model_family") or "").strip().lower() == mod_low:
                matched = entry
                break

    if matched is None:
        return None
    out = copy.deepcopy(matched)
    out["_offset_db_version"] = db["version"]
    out["_offset_db_key_id"] = db["key_id"]
    out["_offset_db_source"] = "synced_verified_db"
    return out


def get_offset_db_status(trusted_keys: Optional[Dict[str, bytes]] = None) -> Dict[str, Any]:
    """Return authoritative active Offset DB status & version metadata."""
    import profiles_db

    bundled_specs = profiles_db.load_model_specs() or {}
    unique_bundled = {
        id(v) for v in bundled_specs.values() if isinstance(v, dict)
    }
    keys = trusted_keys if trusted_keys is not None else get_trusted_public_keys()
    synced = _load_synced_offset_db_ref(trusted_keys=trusted_keys)

    if synced:
        return {
            "offset_db_version": synced["version"],
            "source": "synced_verified_db",
            "verified": True,
            "key_id": synced["key_id"],
            "published_at": synced["published_at"],
            "synced_at": synced["synced_at"],
            "synced_machines_count": len(synced.get("machines") or {}),
            "bundled_specs_count": len(unique_bundled),
            "bundled_version": f"bundled-{version.__build__}",
            "trusted_keys_configured": len(keys) > 0,
            "manifest_url": DEFAULT_MANIFEST_URL,
        }

    return {
        "offset_db_version": f"bundled-{version.__build__}",
        "source": "bundled_factory",
        "verified": True,
        "key_id": "bundled",
        "published_at": "",
        "synced_at": "",
        "synced_machines_count": 0,
        "bundled_specs_count": len(unique_bundled),
        "bundled_version": f"bundled-{version.__build__}",
        "trusted_keys_configured": len(keys) > 0,
        "manifest_url": DEFAULT_MANIFEST_URL,
    }


def get_offset_db_version() -> str:
    """Return active Offset DB version string (for Debug Console, Issue Reports, and Exports)."""
    try:
        return str(get_offset_db_status().get("offset_db_version") or f"bundled-{version.__build__}")
    except Exception:
        return f"bundled-{version.__build__}"


# ============================================================================
# Diff Engine & Explicit User-Triggered Sync (No Silent Overwrite)
# ============================================================================

def _collect_local_machine_fingerprints(
    synced_db: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, str], Set[str], Set[str]]:
    """Build local known machine fingerprints (id -> sha256, known articles, known EF codes)."""
    import profiles_db

    by_id: Dict[str, str] = {}
    known_articles: Set[str] = set()
    known_efs: Set[str] = set()

    if synced_db and isinstance(synced_db.get("machines"), dict):
        for mid, entry in synced_db["machines"].items():
            if not isinstance(entry, dict):
                continue
            by_id[mid] = compute_machine_entry_sha256(entry)
            for a in (entry.get("article_numbers") or []):
                known_articles.add(str(a).strip())
            if entry.get("article_number"):
                known_articles.add(str(entry["article_number"]).strip())
            if entry.get("ef_code"):
                known_efs.add(str(entry["ef_code"]).strip().upper())

    # Also include bundled docs/models/*.json verified specs so already-bundled machines aren't falsely flagged "added"
    specs = profiles_db.load_model_specs() or {}
    seen_obj_ids: Set[int] = set()
    for _k, spec in specs.items():
        if not isinstance(spec, dict) or id(spec) in seen_obj_ids:
            continue
        seen_obj_ids.add(id(spec))
        if not isinstance(spec.get("verified_offsets"), dict):
            continue
        for a in (spec.get("article_numbers") or []):
            known_articles.add(str(a).strip())
        if spec.get("article_number"):
            known_articles.add(str(spec["article_number"]).strip())
        if spec.get("ef_code"):
            known_efs.add(str(spec["ef_code"]).strip().upper())

    return by_id, known_articles, known_efs


def compute_machine_diff(
    manifest: Dict[str, Any],
    synced_db: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Determine specifically which machines in a remote signed manifest are added vs updated."""
    local_by_id, known_arts, known_efs = _collect_local_machine_fingerprints(synced_db)
    added: List[Dict[str, Any]] = []
    updated: List[Dict[str, Any]] = []

    for item in manifest.get("machines_index") or []:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "").strip()
        ef = str(item.get("ef_code") or "").strip()
        fam = str(item.get("model_family") or mid).strip()
        arts = [str(a).strip() for a in (item.get("article_numbers") or []) if str(a).strip()]
        r_sha = str(item.get("entry_sha256") or "").strip()
        summary_item = {
            "id": mid,
            "ef_code": ef,
            "model_family": fam,
            "article_numbers": arts,
            "products_count": int(item.get("products_count") or 0),
            "maintenance_count": int(item.get("maintenance_count") or 0),
        }

        if mid in local_by_id:
            if r_sha and local_by_id[mid] != r_sha:
                updated.append(summary_item)
        else:
            already_bundled = bool(
                (arts and any(a in known_arts for a in arts))
                or (ef and ef.upper() in known_efs)
            )
            if already_bundled:
                # Present in bundled factory specs, now superseded/updated by newer signed pack
                updated.append(summary_item)
            else:
                added.append(summary_item)

    return added, updated


def _validate_remote_url(url: str, manifest_url: str) -> Tuple[bool, str]:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme != "https":
        # Allow http strictly for loopback test servers if manifest_url itself is loopback
        m_parsed = urllib.parse.urlparse(manifest_url)
        if parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost") and m_parsed.hostname in ("127.0.0.1", "localhost"):
            return True, ""
        return False, f"Refusing non-HTTPS Offset DB URL: {url!r}"
    m_host = (urllib.parse.urlparse(manifest_url).hostname or "").lower()
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_PACK_HOSTS and host != m_host:
        return False, f"Refusing Offset DB download from non-allowlisted host: {host!r}"
    return True, ""


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every HTTP 3xx redirect target against _validate_remote_url."""

    def __init__(self, manifest_url: str):
        super().__init__()
        self.manifest_url = manifest_url

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ok, err = _validate_remote_url(newurl, self.manifest_url)
        if not ok:
            raise ValueError(err)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_fetch_bytes(url: str, max_bytes: int, timeout: float = 12.0, manifest_url: Optional[str] = None) -> bytes:
    base_url = manifest_url or url
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"SPECTRA-OffsetDB-Sync/Build-{version.__build__}",
        },
    )
    handlers: List[Any] = [_SafeRedirectHandler(base_url)]
    if url.lower().startswith("https://"):
        handlers.append(urllib.request.HTTPSHandler(context=tls_utils.get_ssl_context()))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(req, timeout=timeout) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"Remote response exceeded safety ceiling ({max_bytes:,} bytes).")
    return data


def check_for_offset_db_updates(
    force: bool = False,
    manifest_url: Optional[str] = None,
    trusted_keys: Optional[Dict[str, bytes]] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Read-only check against signed remote `offsets_db/manifest.json`.
    Verifies Ed25519 signature BEFORE reporting update availability and lists
    exact added/updated machines. Writes ZERO files to disk.
    """
    global _CACHED_CHECK, _CACHED_CHECK_TS
    eff_url = (manifest_url or DEFAULT_MANIFEST_URL).strip()
    now = time.time()

    with _SYNC_LOCK:
        if (
            not force
            and manifest_url is None
            and trusted_keys is None
            and _CACHED_CHECK is not None
            and (now - _CACHED_CHECK_TS) < CHECK_CACHE_TTL_SEC
        ):
            return copy.deepcopy(_CACHED_CHECK)

    status = get_offset_db_status(trusted_keys=trusted_keys)
    keys = trusted_keys if trusted_keys is not None else get_trusted_public_keys()
    base_res: Dict[str, Any] = {
        "success": True,
        "ok": False,
        "update_available": False,
        "signature_verified": False,
        "current_version": status["offset_db_version"],
        "current_source": status["source"],
        "latest_version": "",
        "published_at": "",
        "key_id": "",
        "added_machines": [],
        "updated_machines": [],
        "total_remote_machines": 0,
        "trusted_keys_configured": len(keys) > 0,
        "error": "",
    }

    if not keys:
        base_res["error"] = "No trusted Ed25519 signing public key configured yet."
        return base_res

    ok_u, err_u = _validate_remote_url(eff_url, eff_url)
    if not ok_u:
        base_res["error"] = err_u
        return base_res

    try:
        raw_manifest = _http_fetch_bytes(eff_url, max_bytes=MAX_MANIFEST_BYTES, timeout=timeout)
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except urllib.error.HTTPError as he:
        if he.code == 404:
            base_res["ok"] = True
            base_res["error"] = "No remote signed Offset DB published yet."
            return base_res
        base_res["error"] = f"HTTP {he.code} fetching Offset DB manifest."
        return base_res
    except Exception as exc:
        base_res["error"] = f"Unable to reach Offset DB manifest: {exc}"
        return base_res

    ok_sig, sig_msg = verify_signed_manifest(manifest, trusted_keys=keys)
    if not ok_sig:
        base_res["error"] = sig_msg
        return base_res

    synced_db = load_synced_offset_db(trusted_keys=keys)
    added, updated = compute_machine_diff(manifest, synced_db=synced_db)

    latest_ver = str(manifest.get("version") or "")
    current_ver_cmp = synced_db["version"] if synced_db else ""
    version_newer = is_version_newer(latest_ver, current_ver_cmp) if current_ver_cmp else True
    has_changes = bool(added or updated) or (bool(current_ver_cmp) and version_newer)

    res = {
        **base_res,
        "ok": True,
        "signature_verified": True,
        "update_available": bool(version_newer and has_changes),
        "latest_version": latest_ver,
        "published_at": str(manifest.get("published_at") or ""),
        "key_id": str(manifest.get("key_id") or ""),
        "added_machines": added,
        "updated_machines": updated,
        "total_remote_machines": len(manifest.get("machines_index") or []),
        "notes": str(manifest.get("notes") or ""),
        "manifest": manifest,
    }

    with _SYNC_LOCK:
        if manifest_url is None and trusted_keys is None:
            _CACHED_CHECK = copy.deepcopy(res)
            _CACHED_CHECK_TS = now

    return res


def sync_offset_db(
    manifest_url: Optional[str] = None,
    trusted_keys: Optional[Dict[str, bytes]] = None,
    timeout: float = 20.0,
) -> Dict[str, Any]:
    """
    Explicit user-triggered 1-click Machine Offset DB sync.
    Verifies manifest Ed25519 signature, downloads pack, verifies SHA-256 +
    Ed25519 + strict allowlist schema + anti-rollback, and atomically installs
    to `~/.config/spectra/synced_offsets_db.json` (0o600). Never touches Layer 1
    local technician overrides (`eeprom_overrides.json`).
    """
    eff_manifest_url = (manifest_url or DEFAULT_MANIFEST_URL).strip()
    check_res = check_for_offset_db_updates(
        force=True,
        manifest_url=eff_manifest_url,
        trusted_keys=trusted_keys,
        timeout=timeout,
    )
    if not check_res.get("ok") or not check_res.get("signature_verified"):
        return {
            "success": False,
            "error": check_res.get("error") or "Signed Offset DB manifest verification failed.",
            "status": get_offset_db_status(trusted_keys=trusted_keys),
        }

    manifest = check_res.get("manifest")
    if not isinstance(manifest, dict):
        return {
            "success": False,
            "error": "No signed manifest available to sync.",
            "status": get_offset_db_status(trusted_keys=trusted_keys),
        }

    pack_url = str(manifest.get("pack_url") or "").strip()
    if not pack_url:
        pack_file = str(manifest.get("pack_file") or "offsets_pack.json").lstrip("/")
        if "/" in eff_manifest_url:
            pack_url = eff_manifest_url.rsplit("/", 1)[0] + "/" + pack_file
        else:
            pack_url = DEFAULT_PACK_BASE_URL.rstrip("/") + "/" + pack_file

    ok_u, err_u = _validate_remote_url(pack_url, eff_manifest_url)
    if not ok_u:
        return {
            "success": False,
            "error": err_u,
            "status": get_offset_db_status(trusted_keys=trusted_keys),
        }

    try:
        raw_pack = _http_fetch_bytes(pack_url, max_bytes=MAX_PACK_BYTES, timeout=timeout, manifest_url=eff_manifest_url)
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to download signed Offset DB pack: {exc}",
            "status": get_offset_db_status(trusted_keys=trusted_keys),
        }

    existing = load_synced_offset_db(trusted_keys=trusted_keys)
    ok_p, err_p, validated_pack = verify_signed_pack(
        raw_pack,
        manifest,
        trusted_keys=trusted_keys,
        current_synced_version=existing["version"] if existing else None,
    )
    if not ok_p or validated_pack is None:
        return {
            "success": False,
            "error": err_p,
            "status": get_offset_db_status(trusted_keys=trusted_keys),
        }

    synced_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    envelope = {
        "synced_at": synced_at,
        "pack_sha256": hashlib.sha256(raw_pack).hexdigest(),
        "manifest_version": str(manifest.get("version") or ""),
        "pack": validated_pack,
    }

    with _SYNC_LOCK:
        parent = os.path.dirname(SYNCED_OFFSETS_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)
            try:
                os.chmod(parent, 0o700)
            except OSError:
                pass
        tmp_path = f"{SYNCED_OFFSETS_FILE}.tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(envelope, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, SYNCED_OFFSETS_FILE)
        invalidate_offset_db_cache()

    try:
        import profiles_db
        profiles_db.invalidate_model_specs_cache()
    except Exception:
        pass

    new_status = get_offset_db_status(trusted_keys=trusted_keys)
    return {
        "success": True,
        "offset_db_version": new_status["offset_db_version"],
        "key_id": new_status["key_id"],
        "synced_at": synced_at,
        "machines_synced": len(validated_pack.get("machines") or {}),
        "added_machines": check_res.get("added_machines") or [],
        "updated_machines": check_res.get("updated_machines") or [],
        "status": new_status,
        "message": (
            f"Synced verified Machine Offset DB {new_status['offset_db_version']} "
            f"({len(validated_pack.get('machines') or {})} machines, Ed25519 verified)."
        ),
    }
