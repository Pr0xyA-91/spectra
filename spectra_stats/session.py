#!/usr/bin/env python3
"""SPECTRA JuraStatsSession interrogation orchestrator, structured summary & report export."""

import os
import time
import json
import csv
import io
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Tuple, Deque

import jura_protocol as jp
import profiles_db
from serial_io import JuraSerialConnection

from spectra_stats.calibration import (
    ARTICLE_MODEL_MAP,
    TWO_DIGIT_ADDRESS_EFS,
    __build__,
    __version__,
    is_non_coffee_product,
)
from spectra_stats.decoders import (
    calculate_gs1_check_digit,
    decode_jura_date,
)
from spectra_stats.live_sensors import query_live_sensors

class JuraStatsSession:
    """Manages an active interrogation session with a Jura machine."""

    def __init__(self, port_name: str, baudrate: int = 9600, log_cb: Optional[Callable[[str], None]] = None):
        self.port_name = port_name
        self.baudrate = baudrate
        self.log_cb = log_cb or (lambda msg: None)
        self.conn: Optional[JuraSerialConnection] = None

        # Session data
        self.raw_model_str = ""
        self.ef_code = ""
        self.model_family = "Unknown Jura Machine"
        self.protocol_mode = "Auto-Detecting"
        self.power_spec = "Standard (230V / 50Hz)"
        self.profile = profiles_db.DEFAULT_PROFILE
        self.counters: Dict[int, int] = {}
        self.total_preparations = 0
        self.total_cups = 0
        self.maint_counts: List[int] = []
        self.maint_pcts: List[Optional[int]] = []
        self.telemetry: Dict[str, Any] = {}
        self.active_alerts: List[Dict[str, Any]] = []
        self.live_sensors: Dict[str, Any] = {}
        self.raw_log: Deque[Dict[str, str]] = deque(maxlen=2000)
        self.is_legacy_cleartext = False
        self.last_eeprom: Dict[int, int] = {}
        self.address_width: int = 4
        self.override_products: Optional[List[Dict[str, Any]]] = None
        self.override_maint_labels: Optional[List[str]] = None
        self.offset_override_info: Optional[Dict[str, Any]] = None

    def apply_local_offset_override(
        self,
        eeprom: Optional[Dict[int, int]] = None,
        article_num: Optional[str] = None,
        override_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Apply a saved local AI/J.O.E.-calibrated EEPROM offset override (if present)
        directly to this session's counters and maintenance stats.
        """
        mem = eeprom if eeprom is not None else self.last_eeprom
        art = article_num or self.telemetry.get("article_number")
        art_clean = str(art or "").strip()

        # Layer 1 (Highest): Local Technician Override (~/.config/spectra/eeprom_overrides.json)
        ov = override_data if isinstance(override_data, dict) else profiles_db.get_eeprom_offset_override(
            self.ef_code,
            article_number=art,
            model_name=self.model_family,
        )
        if isinstance(ov, dict):
            ov = dict(ov)
            ov.setdefault("precedence_layer", "local_override")

        # Layer 2 (Middle): Ed25519-Verified Synced Offset Pack (~/.config/spectra/synced_offsets_db.json)
        if not ov:
            try:
                import offset_db_sync
                synced_spec = offset_db_sync.get_synced_machine_spec(
                    ef_code=self.ef_code,
                    article_number=art_clean,
                    model_name=self.model_family,
                )
            except Exception:
                synced_spec = None
            if isinstance(synced_spec, dict) and isinstance(synced_spec.get("verified_offsets"), dict):
                sv = synced_spec["verified_offsets"]
                if sv.get("products") or sv.get("maintenance") or sv.get("maintenance_pct"):
                    ov = {
                        "source": "synced_verified_db",
                        "precedence_layer": "synced_verified_db",
                        "override_key": str(synced_spec.get("id") or self.ef_code or art_clean),
                        "offset_db_version": str(synced_spec.get("_offset_db_version") or ""),
                        "key_id": str(synced_spec.get("_offset_db_key_id") or ""),
                        "updated_at": str(synced_spec.get("updated_at") or ""),
                        "products": list(sv.get("products") or []),
                        "maintenance": list(sv.get("maintenance") or []),
                        "maintenance_pct": list(sv.get("maintenance_pct") or []),
                    }
                    cur_fam = str(self.model_family or "").strip().lower()
                    if not cur_fam or cur_fam in ("unknown", "unknown jura", "unknown jura machine") or "generic" in cur_fam:
                        spec_fam = str(synced_spec.get("model_family") or "").strip()
                        if spec_fam:
                            ov["model_name"] = spec_fam

        # Layer 3 (Base): Bundled Factory Profiles & Verified Model Specs (docs/models/*.json)
        if not ov:
            spec_source = self.profile if isinstance(self.profile, dict) else {}
            verified = None
            if art_clean and art_clean.lower() not in ("unknown", "n/a"):
                art_spec = profiles_db.get_model_spec(art_clean)
                if isinstance(art_spec, dict) and isinstance(art_spec.get("verified_offsets"), dict):
                    spec_source = art_spec
                    verified = art_spec.get("verified_offsets")
            if not verified and isinstance(spec_source.get("verified_offsets"), dict):
                verified = spec_source.get("verified_offsets")
            if isinstance(verified, dict) and (
                verified.get("products") or verified.get("maintenance") or verified.get("maintenance_pct")
            ):
                ov = {
                    "source": "community_verified",
                    "precedence_layer": "bundled_factory",
                    "override_key": self.ef_code or art_clean,
                    "products": list(verified.get("products") or []),
                    "maintenance": list(verified.get("maintenance") or []),
                    "maintenance_pct": list(verified.get("maintenance_pct") or []),
                }
                cur_fam = str(self.model_family or "").strip().lower()
                if not cur_fam or cur_fam in ("unknown", "unknown jura", "unknown jura machine") or "generic" in cur_fam:
                    spec_fam = str(spec_source.get("model_family") or "").strip()
                    if spec_fam:
                        ov["model_name"] = spec_fam
        if not ov:
            self.override_products = None
            self.override_maint_labels = None
            self.offset_override_info = None
            return False

        ov_model = str(ov.get("model_name") or "").strip()
        ov_art = str(ov.get("article_number") or "").strip()
        ov_serial = str(ov.get("serial_number") or "").strip()
        ov_market = str(ov.get("market_region") or "").strip()

        if ov_model and ov_model.lower() not in ("unknown", "unknown jura", "n/a"):
            self.model_family = ov_model
            self.telemetry["appliance_type"] = ov_model
        if ov_art and ov_art.lower() not in ("unknown", "n/a"):
            self.telemetry["article_number"] = ov_art
        if ov_serial and ov_serial.lower() not in ("unknown", "n/a"):
            self.telemetry["serial_number"] = ov_serial
        if ov_market and ov_market.lower() not in ("unknown", "n/a"):
            self.telemetry["market_region"] = ov_market

        if not mem and (ov.get("products") or ov.get("maintenance")):
            return False

        def _parse_addr_int(raw_addr: Any) -> Optional[int]:
            if raw_addr is None or isinstance(raw_addr, bool):
                return None
            if isinstance(raw_addr, int):
                return raw_addr if 0 <= raw_addr <= 0xFFFF else None
            txt = str(raw_addr).strip().lower()
            if not txt:
                return None
            try:
                if txt.startswith("0x"):
                    val_i = int(txt, 16)
                elif any(ch in "abcdef" for ch in txt):
                    val_i = int(txt, 16)
                else:
                    val_i = int(txt, 10)
                return val_i if 0 <= val_i <= 0xFFFF else None
            except ValueError:
                return None

        def _item_addr_int(item: Dict[str, Any]) -> Optional[int]:
            if not isinstance(item, dict):
                return None
            addr_i = _parse_addr_int(item.get("addr"))
            if addr_i is not None:
                return addr_i
            return _parse_addr_int(item.get("addr_hex"))

        def _read_word(addr_val: Any) -> int:
            addr_int = _item_addr_int(addr_val) if isinstance(addr_val, dict) else _parse_addr_int(addr_val)
            if addr_int is None:
                return 0
            if addr_int in mem:
                return mem[addr_int]
            if (
                self.is_legacy_cleartext
                and not getattr(self.conn, "_is_smart_connect", False)
                and self.conn
                and getattr(self.conn, "is_open", False)
            ):
                addr_str = f"{addr_int:02X}" if self.address_width == 2 else f"{addr_int:04X}"
                ans = self.conn.query_ascii(f"RE:{addr_str}", timeout=1.0)
                if ans and ans.lower().startswith("re:"):
                    try:
                        mem[addr_int] = int(ans[3:].strip(), 16)
                        self.last_eeprom[addr_int] = mem[addr_int]
                    except ValueError:
                        pass
            return mem.get(addr_int, 0)

        prev_total_cups = self.total_cups
        ov_prods = ov.get("products") or []
        if ov_prods:
            new_counters: Dict[int, int] = {}
            new_prod_defs: List[Dict[str, Any]] = []
            used_codes = set()
            next_auto_code = 1
            single_preps = 0
            double_preps = 0
            coffee_cups = 0
            for idx, item in enumerate(ov_prods, start=1):
                if not isinstance(item, dict):
                    continue
                raw_code = item.get("code")
                code: Optional[int] = None
                if raw_code is not None and not isinstance(raw_code, bool):
                    try:
                        c_int = int(raw_code)
                        if c_int > 0 and c_int not in used_codes:
                            code = c_int
                    except (TypeError, ValueError):
                        code = None
                if code is None:
                    while next_auto_code in used_codes:
                        next_auto_code += 1
                    code = next_auto_code
                    next_auto_code += 1
                used_codes.add(code)

                val = _read_word(item)
                is_dbl = bool(item.get("is_double", False))
                item_name = str(item.get("name") or f"Product #{code}").strip() or f"Product #{code}"
                new_counters[code] = val
                if is_dbl:
                    double_preps += val
                else:
                    single_preps += val
                if not is_non_coffee_product(item_name, code):
                    coffee_cups += (val * 2) if is_dbl else val
                prod_def: Dict[str, Any] = {
                    "code": code,
                    "name": item_name,
                    "is_double": is_dbl,
                    "active": True,
                }
                addr_int = _item_addr_int(item)
                if addr_int is not None:
                    prod_def["addr"] = addr_int
                    prod_def["addr_hex"] = f"0x{addr_int:04X}"
                new_prod_defs.append(prod_def)
            if new_prod_defs:
                self.counters = new_counters
                self.override_products = new_prod_defs
                self.total_preparations = single_preps + double_preps
                self.total_cups = coffee_cups
                self.telemetry["total_preparations"] = self.total_preparations
                self.telemetry["total_cups"] = self.total_cups
                if self.telemetry.get("cups_since_intervention") == prev_total_cups:
                    self.telemetry["cups_since_intervention"] = self.total_cups
                if isinstance(self.profile, dict):
                    updated_profile = dict(self.profile)
                    updated_profile["products"] = [dict(p) for p in new_prod_defs]
                    if ov_model and ov_model.lower() not in ("unknown", "unknown jura", "n/a"):
                        updated_profile["model_family"] = ov_model
                    self.profile = updated_profile

        ov_maint = ov.get("maintenance") or []
        ov_pct = ov.get("maintenance_pct") or []
        pct_by_name = {str(p.get("name", "")).strip().lower(): p for p in ov_pct if isinstance(p, dict)}
        if ov_maint:
            new_maint_counts: List[int] = []
            new_maint_pcts: List[Optional[int]] = []
            new_maint_labels: List[str] = []
            for m in ov_maint:
                if not isinstance(m, dict):
                    continue
                label = str(m.get("name") or "Maintenance").strip() or "Maintenance"
                new_maint_labels.append(label)
                new_maint_counts.append(_read_word(m))
                p_match = pct_by_name.get(label.strip().lower())
                if p_match is None:
                    # Try fuzzy prefix match (e.g. Cleaning vs Cleaning / Cleaning %)
                    l_low = label.strip().lower()
                    for pk, pv in pct_by_name.items():
                        if l_low in pk or pk in l_low:
                            p_match = pv
                            break
                if p_match is not None:
                    w = _read_word(p_match)
                    byte_sel = str(p_match.get("byte") or "low").lower()
                    pct_val = ((w >> 8) & 0xFF) if byte_sel == "high" else (w & 0xFF)
                    pct_val = max(0, min(100, pct_val))
                    new_maint_pcts.append(pct_val)
                else:
                    new_maint_pcts.append(None)
            if new_maint_labels:
                self.maint_counts = new_maint_counts
                self.maint_pcts = new_maint_pcts
                self.override_maint_labels = new_maint_labels
                if isinstance(self.profile, dict):
                    updated_profile = dict(self.profile)
                    updated_profile["maintenance_counters"] = list(new_maint_labels)
                    self.profile = updated_profile

        self.offset_override_info = {
            "active": True,
            "override_key": ov.get("override_key"),
            "updated_at": ov.get("updated_at"),
            "source": ov.get("source", "ai_joe_calibration"),
            "precedence_layer": ov.get("precedence_layer", "local_override"),
            "model_used": ov.get("model_used"),
            "products_mapped": len(ov_prods),
            "maintenance_mapped": len(ov_maint),
        }
        self.log(
            f"Applied local EEPROM offset override ({ov.get('override_key')}): "
            f"{len(ov_prods)} beverages, {len(ov_maint)} maintenance counters"
        )
        return True

    def query_live_sensors(self) -> Dict[str, Any]:
        """Query live hardware sensors and microswitches for current session."""
        res = query_live_sensors(
            port_name=self.port_name,
            baudrate=self.baudrate,
            conn=self.conn if (self.conn and self.conn.is_open) else None,
            profile=self.profile,
            is_legacy=self.is_legacy_cleartext
        )
        self.live_sensors = res
        return res

    def close(self):
        """Close underlying serial connection if opened and held."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{ts}] {text}"
        self.raw_log.append({"time": ts, "message": text})
        self.log_cb(entry)

    def _send_encrypted_cmd(self, cmd_plain: str, key: int = 0x2A, timeout: float = 1.0) -> Optional[str]:
        """Send an encrypted '@'-command over 4:1 wire and wait for decrypted reply."""
        self.log(f"TX (SmartConnect): {cmd_plain.strip()}")
        if hasattr(self.conn, "query_encrypted"):
            plain_resp = self.conn.query_encrypted(cmd_plain, key=key, timeout=timeout)
            if plain_resp:
                self.log(f"RX (SmartConnect): {plain_resp.strip()}")
                return plain_resp.strip()
            self.log(f"TIMEOUT waiting for reply to {cmd_plain.strip()}")
            return None

        wire_tx = jp.encode_wire(jp.build_encrypted_frame(cmd_plain, key))
        self.conn.write(wire_tx)

        start = time.time()
        rx_wire = bytearray()
        cmd_clean = cmd_plain.strip()
        while time.time() - start < timeout:
            chunk = self.conn.read(max_bytes=1024, timeout_sec=0.15)
            if chunk:
                rx_wire.extend(chunk)
                if len(rx_wire) > 16384:
                    break
                if rx_wire.startswith(wire_tx):
                    del rx_wire[:len(wire_tx)]
                aligned_len = (len(rx_wire) // 4) * 4
                if aligned_len >= 4:
                    decoded, _ = jp.decode_wire(bytes(rx_wire[:aligned_len]))
                    amp = decoded.find(b"&")
                    end = decoded.find(b"\r\n", amp) if amp != -1 else -1
                    if amp != -1 and end != -1:
                        plain_resp = jp.decode_encrypted_frame(decoded[amp:end + 2])
                        if plain_resp and plain_resp.strip() != cmd_clean:
                            self.log(f"RX (SmartConnect): {plain_resp.strip()}")
                            return plain_resp.strip()
            time.sleep(0.01)

        self.log(f"TIMEOUT waiting for reply to {cmd_plain.strip()}")
        return None

    def run_interrogation(self, progress_cb: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        Execute full interrogation sequence:
        1. Open serial connection
        2. Probe ASCII mode (TY:) - handles Jura USB Scanner N 010 & direct serial
        3. If no ASCII reply (or ASCII EEPROM returns empty/all zeros), probe Smart Connect mode (@T0)
        4. Read and parse all beverage counters, maintenance cycles, and telemetry
        """
        def update_prog(pct: float, status: str):
            if progress_cb:
                progress_cb(pct, status)

        owns_conn = False
        try:
            update_prog(0.05, f"Connecting to {self.port_name}...")
            if self.conn is None or not getattr(self.conn, "is_open", True):
                self.conn = JuraSerialConnection(self.port_name, baudrate=self.baudrate, timeout=1.0)
                owns_conn = True
            self.log(f"Opened connection on {self.port_name} at {self.baudrate} baud (8N1)")

            # ================================================================
            # Mode A: Probe ASCII Protocol (TY:) - Jura USB Scanner / EEPROM
            # ================================================================
            update_prog(0.12, "Probing machine type (TY:)...")
            self.log("Probing ASCII machine identification query (TY:)...")
            ty_resp = self.conn.query_ascii("TY:", timeout=1.0)
            ascii_model_hint = ""
            ascii_profile_hint = None

            if ty_resp and ty_resp.lower().startswith("ty:"):
                self.is_legacy_cleartext = True
                self.protocol_mode = "ASCII Optical (Jura USB Scanner / Direct Serial)"
                self.raw_model_str = ty_resp[3:].strip()
                self.ef_code = self.raw_model_str
                ascii_model_hint = self.raw_model_str
                self.profile = profiles_db.find_profile(self.raw_model_str)
                ascii_profile_hint = self.profile
                self.model_family = self.profile.get("model_family", "Jura Coffee Machine")
                self.log(f"Machine detected via ASCII: {self.model_family} ({self.raw_model_str})")

                # Query Power Specification (IC:)
                update_prog(0.20, "Querying machine power specification (IC:)...")
                ic_resp = self.conn.query_ascii("IC:", timeout=0.8)
                if ic_resp and ic_resp.lower().startswith("ic:"):
                    raw_ic = ic_resp[3:].strip()
                    if "23" in raw_ic:
                        self.power_spec = "230V / 50Hz (EU/CH)"
                    elif "12" in raw_ic:
                        self.power_spec = "120V / 60Hz (US/NA)"
                    else:
                        self.power_spec = f"IC Code: {raw_ic}"
                    self.log(f"Machine Power Rating: {self.power_spec}")

                # Determine EEPROM address width and architecture
                is_two_digit = (
                    self.profile.get("address_width") == 2
                    or any(self.ef_code.upper().startswith(p) for p in TWO_DIGIT_ADDRESS_EFS)
                )
                address_width = 2 if is_two_digit else 4
                is_z5 = "EF642" in self.ef_code.upper() or "Z5" in self.model_family.upper()
                is_d4 = "EF529" in self.ef_code.upper() or "D4" in self.model_family.upper()
                is_a1 = "EF509" in self.ef_code.upper() or "A1" in self.model_family.upper() or "ENA MICRO" in self.model_family.upper()
                is_we8 = "EF535" in self.ef_code.upper() or "WE8" in self.model_family.upper()
                is_e8 = "EF533" in self.ef_code.upper() or "E8" in self.model_family.upper()
                is_ena7 = "EF634" in self.ef_code.upper() or "ENA 7" in self.model_family.upper() or "ENA7" in self.model_family.upper()

                # Query Display Sub-Bus Firmware Gateway (TY$:)
                ty_sub = self.conn.query_ascii("TY$:", timeout=0.8)
                if ty_sub and ty_sub.lower().startswith("ty$:"):
                    display_fw = ty_sub[4:].strip()
                elif ty_sub and ty_sub.lower().startswith("ty:"):
                    display_fw = ty_sub[3:].strip()
                else:
                    display_fw = self.profile.get("software_version_display", "N/A (Symbol Display)" if (is_d4 or is_a1) else "EF518D V02.04")

                # Query EEPROM memory blocks
                blocks = [0x00, 0x10, 0x20, 0x30]
                if is_z5 or is_two_digit:
                    blocks.append(0x70)
                    blocks.append(0xE0)
                elif is_d4:
                    blocks.append(0x0330)
                elif is_we8 or is_e8:
                    blocks.extend([0x70, 0xE0, 0x160, 0x170, 0x180, 0x1E0])
                elif is_ena7:
                    blocks.extend([0x50, 0x60, 0x70, 0xD0])

                update_prog(0.30, f"Reading EEPROM diagnostic blocks ({'2-digit' if address_width == 2 else '4-digit'} addressing)...")
                eeprom: Dict[int, int] = {}
                rt_blocks_succeeded = 0
                consecutive_rt_timeouts = 0

                for b_idx, blk in enumerate(blocks):
                    pct = 0.30 + (b_idx / len(blocks)) * 0.50
                    blk_str = f"{blk:02X}" if address_width == 2 else f"{blk:04X}"
                    update_prog(pct, f"Reading memory block 0x{blk_str}...")
                    cmd = f"RT:{blk_str}"
                    ans = self.conn.query_ascii(cmd, timeout=1.8)
                    if ans and ans.lower().startswith("rt:"):
                        raw_hex = ans[3:].strip()
                        try:
                            words = [int(raw_hex[i * 4: i * 4 + 4], 16) for i in range(len(raw_hex) // 4)]
                        except ValueError:
                            words = []
                        if words:
                            for idx, w in enumerate(words):
                                eeprom[blk + idx] = w
                            rt_blocks_succeeded += 1
                            consecutive_rt_timeouts = 0
                            self.log(f"EEPROM [0x{blk_str}]: {len(words)} words read successfully")
                        else:
                            consecutive_rt_timeouts += 1
                            self.log(f"Notice: Block 0x{blk_str} returned malformed/empty RT: payload")
                            if rt_blocks_succeeded == 0 and consecutive_rt_timeouts >= 2:
                                self.log("Notice: 2 consecutive RT: block timeouts; aborting ASCII RT: sweep early.")
                                break
                    else:
                        consecutive_rt_timeouts += 1
                        self.log(f"Notice: Block 0x{blk_str} returned empty/timeout")
                        if rt_blocks_succeeded == 0 and consecutive_rt_timeouts >= 2:
                            self.log("Notice: 2 consecutive RT: block timeouts; aborting ASCII RT: sweep early.")
                            break

                # Explicitly query machine identity, production, and service history EEPROM words
                # 0x0030: Appliance / Machine Number (Maschinennummer: e.g. 18016)
                # 0x0031: Internal Serial Word (Seriennummer: e.g. 51)
                # 0x0032: Production Date bitfield (Produktionsdatum: e.g. 30.5.2013)
                # 0x0015: Preparations since last intervention (Service-Counter: e.g. 28730)
                # 0x00DA: SPDL Country / Destination Market Code (e.g. 'CZ')
                # 0x00DB: SPDL Date Download (e.g. 12.10.2013)
                # 0x00DC: SPDL Date Language File (e.g. 12.12.2012)
                # 0x00E9: Retail High Word (Service cup counter baseline high word)
                # 0x00EA: Retail Low Word (Service cup counter baseline low word)
                # 0x00C3: Water Hardness (High byte: °dH)
                update_prog(0.80, "Reading machine serial and production records...")
                id_addrs = [
                    (0x30, "Machine Number"),
                    (0x31, "Serial Word"),
                    (0x32, "Production Date"),
                    (0x15, "Service Counter"),
                    (0x7E, "Article High"),
                    (0x7F, "Article Low"),
                    (0xDA, "SPDL Country Code"),
                    (0xDB, "SPDL Download Date"),
                    (0xDC, "SPDL Language Date"),
                    (0xE9, "Retail High"),
                    (0xEA, "Retail Low"),
                    (0xC3, "Water Hardness"),
                ]
                if is_z5:
                    for a in range(0xE0, 0xE6):
                        id_addrs.append((a, f"Double Beverage 0x{a:02X}"))
                    id_addrs.append((0x22, "Filter Cycles"))
                elif is_we8 or is_e8:
                    id_addrs.append((0x20, "Milk Rinses"))
                    id_addrs.append((0x21, "Milk Cleans"))
                    id_addrs.append((0x22, "Filter Cycles"))
                    id_addrs.append((0x17F, "Green Tea"))
                    id_addrs.append((0x162, "Descaling Percentage"))
                    id_addrs.append((0x163, "Cleaning Percentage"))
                    id_addrs.append((0x1E1, "Filter Percentage"))
                elif is_ena7:
                    id_addrs.append((0x52, "Filter Cycles"))
                    id_addrs.append((0x56, "BU Initializations"))
                    id_addrs.append((0xD6, "Machine Switch-On"))

                run_re_fallback = rt_blocks_succeeded > 0
                if not run_re_fallback:
                    probe_addr_str = "00" if address_width == 2 else "0000"
                    re_probe = self.conn.query_ascii(f"RE:{probe_addr_str}", timeout=1.0)
                    if re_probe and re_probe.lower().startswith("re:"):
                        try:
                            eeprom[0] = int(re_probe[3:].strip(), 16)
                            run_re_fallback = True
                        except ValueError:
                            run_re_fallback = False

                if run_re_fallback:
                    for addr_int, desc in id_addrs:
                        if addr_int not in eeprom or eeprom[addr_int] == 0:
                            addr_str = f"{addr_int:02X}" if address_width == 2 else f"{addr_int:04X}"
                            ans = self.conn.query_ascii(f"RE:{addr_str}", timeout=1.0)
                            if ans and ans.lower().startswith("re:"):
                                try:
                                    eeprom[addr_int] = int(ans[3:].strip(), 16)
                                    self.log(f"EEPROM [0x{addr_str}] {desc}: 0x{eeprom[addr_int]:04X} ({eeprom[addr_int]})")
                                except ValueError:
                                    pass
                else:
                    self.log("Notice: RE:0000 returned no reply; skipping 19 individual RE: probes.")

                has_valid_ascii_eeprom = len(eeprom) > 0 and any(v not in (0, 0xFFFF) for v in eeprom.values())
                if not has_valid_ascii_eeprom:
                    self.log("Notice: ASCII EEPROM returned no valid non-zero data; attempting Smart Connect (@T0) fallback...")
                else:
                    update_prog(0.85, "Parsing machine telemetry & statistics...")
                    if is_z5:
                        esp1 = eeprom.get(0x00, 0)
                        rist1 = eeprom.get(0x01, 0)
                        cof1 = eeprom.get(0x02, 0)
                        spec1 = eeprom.get(0x03, 0)
                        capp1 = eeprom.get(0x04, 0)
                        latte1 = eeprom.get(0x05, 0)
                        ground = eeprom.get(0x06, 0)

                        esp2 = eeprom.get(0xE0, 0)
                        rist2 = eeprom.get(0xE1, 0)
                        cof2 = eeprom.get(0xE2, 0)
                        spec2 = eeprom.get(0xE3, 0)
                        capp2 = eeprom.get(0xE4, 0)
                        latte2 = eeprom.get(0xE5, 0)

                        self.counters[1] = esp1
                        self.counters[2] = rist1
                        self.counters[3] = cof1
                        self.counters[4] = spec1
                        self.counters[5] = capp1
                        self.counters[6] = latte1
                        if ground > 0:
                            self.counters[7] = ground
                        self.counters[8] = esp2
                        self.counters[9] = rist2
                        self.counters[10] = cof2
                        self.counters[11] = spec2
                        self.counters[12] = capp2
                        self.counters[13] = latte2

                        single_preps = esp1 + rist1 + cof1 + spec1 + capp1 + latte1 + ground
                        double_preps = esp2 + rist2 + cof2 + spec2 + capp2 + latte2
                        self.total_preparations = single_preps + double_preps
                        self.total_cups = single_preps + (double_preps * 2)

                        filter_cycles = eeprom.get(0x22, eeprom.get(20, 0))
                    elif is_d4:
                        # Jura D4 (EF529M / RL78 platform) stores beverage counters in Block 0x0330
                        esp1 = eeprom.get(0x0330, 0)
                        cof1 = eeprom.get(0x0331, 0)
                        esp2 = eeprom.get(0x0332, 0)
                        cof2 = eeprom.get(0x0333, 0)
                        water = eeprom.get(0x0334, 0)

                        self.counters[2] = esp1
                        self.counters[3] = cof1
                        self.counters[49] = esp2
                        self.counters[54] = cof2
                        self.counters[13] = water

                        single_preps = esp1 + cof1 + water
                        double_preps = esp2 + cof2
                        self.total_preparations = single_preps + double_preps
                        self.total_cups = esp1 + cof1 + (double_preps * 2)

                        # D4 Filter changes are stored at 0x000E
                        filter_cycles = eeprom.get(0x000E, eeprom.get(20, 0))
                    elif is_a1:
                        # Jura A1 / ENA Micro single-cup architecture:
                        # Physical panel features only 3 single-serve coffee buttons:
                        # 0x0002: Coffee (1 cup)
                        # 0x0004: Espresso (1 cup)
                        # 0x0006: Ristretto (1 cup)
                        # All are single-cup preparations (no 2-cup buttons or modes)
                        cof = eeprom.get(2, 0)
                        esp = eeprom.get(4, 0)
                        rist = eeprom.get(6, 0)

                        self.counters[1] = rist
                        self.counters[2] = esp
                        self.counters[3] = cof

                        self.total_preparations = rist + esp + cof
                        self.total_cups = self.total_preparations

                        filter_cycles = eeprom.get(20, 0)
                    elif is_we8 or is_e8:
                        # Jura WE8 / E8 TFT platform (EF533 / EF535 / Renesas RL78)
                        # Block 0x0180 (and 0x017F) holds consolidated beverage statistics
                        if 0x0180 in eeprom and any(eeprom.get(0x0180 + i, 0) > 0 for i in range(16)):
                            esp = eeprom.get(0x0180, 0)
                            rist = eeprom.get(0x0181, 0)
                            cof = eeprom.get(0x0182, 0)
                            flat_white = eeprom.get(0x0183, 0)
                            capp = eeprom.get(0x0184, 0)
                            latte = eeprom.get(0x0185, 0)
                            ground = eeprom.get(0x0186, 0)
                            milk = eeprom.get(0x0187, 0)
                            water = eeprom.get(0x0188, 0)
                            esp2 = eeprom.get(0x0189, 0)
                            rist2 = eeprom.get(0x018A, 0)
                            cof2 = eeprom.get(0x018B, 0)
                            spec2 = eeprom.get(0x018C, 0)
                            spec = eeprom.get(0x018D, 0)
                            macchiato = eeprom.get(0x018E, 0)
                            doppio = eeprom.get(0x018F, 0)
                            green_tea = eeprom.get(0x017F, 0)
                        else:
                            # Fallback to lower block registers if 0x0180 is not returned
                            esp = eeprom.get(0x0000, eeprom.get(1, 0))
                            rist = eeprom.get(0x0001, 0)
                            cof = eeprom.get(0x0002, eeprom.get(2, 0))
                            flat_white = eeprom.get(0x0003, 0)
                            capp = eeprom.get(0x0004, 0)
                            latte = eeprom.get(0x0005, 0)
                            ground = eeprom.get(0x0006, 0)
                            milk = eeprom.get(0x0013, 0)
                            water = eeprom.get(0x0014, 0)
                            esp2 = eeprom.get(0x00E0, eeprom.get(4, 0))
                            rist2 = eeprom.get(0x00E1, 0)
                            cof2 = eeprom.get(0x00E2, eeprom.get(5, 0))
                            spec2 = eeprom.get(0x00E3, eeprom.get(6, 0))
                            spec = eeprom.get(0x018D, eeprom.get(3, 0))
                            macchiato = eeprom.get(0x018E, 0)
                            doppio = eeprom.get(0x018F, 0)
                            green_tea = eeprom.get(0x017F, 0)

                        self.counters[1] = rist
                        self.counters[2] = esp
                        self.counters[3] = cof
                        self.counters[4] = capp
                        self.counters[6] = macchiato
                        self.counters[7] = latte
                        self.counters[10] = milk
                        self.counters[13] = water
                        if ground > 0:
                            self.counters[15] = ground
                        self.counters[17] = rist2
                        self.counters[18] = esp2
                        self.counters[19] = cof2
                        self.counters[45] = green_tea
                        self.counters[46] = flat_white
                        self.counters[47] = spec
                        self.counters[48] = doppio
                        self.counters[63] = spec2

                        single_preps = rist + esp + cof + flat_white + capp + latte + milk + water + spec + macchiato + doppio + green_tea + ground
                        double_preps = rist2 + esp2 + cof2 + spec2
                        self.total_preparations = single_preps + double_preps
                        coffee_single_cups = rist + esp + cof + flat_white + capp + latte + spec + macchiato + doppio + ground
                        self.total_cups = coffee_single_cups + (double_preps * 2)

                        filter_cycles = eeprom.get(0x0022, eeprom.get(20, 0))
                        milk_rinses = eeprom.get(0x0020, 0)
                        milk_cleanings = eeprom.get(0x0021, 0)
                    elif is_ena7:
                        # Jura ENA 7 / EF634 platform:
                        # 0x0000: 1 Espresso (Single)
                        # 0x0001: 2 Espressi (Double)
                        # 0x0002: 1 Coffee (Single)
                        # 0x0003: 2 Coffees (Double)
                        # 0x0004: 1 Aroma-Boost (Single)
                        # 0x0005: Steam / Hot Water valve cycles
                        # 0x0006: Ground Coffee bypass (Single)
                        esp1 = eeprom.get(0x0000, 0)
                        esp2 = eeprom.get(0x0001, 0)
                        cof1 = eeprom.get(0x0002, 0)
                        cof2 = eeprom.get(0x0003, 0)
                        aroma = eeprom.get(0x0004, 0)
                        hotwater = eeprom.get(0x0005, 0)
                        ground = eeprom.get(0x0006, 0)

                        self.counters[1] = esp1
                        self.counters[2] = esp2
                        self.counters[3] = cof1
                        self.counters[4] = cof2
                        self.counters[5] = aroma
                        if ground > 0:
                            self.counters[6] = ground
                        if hotwater > 0:
                            self.counters[13] = hotwater

                        single_preps = esp1 + cof1 + aroma + ground
                        double_preps = esp2 + cof2
                        self.total_preparations = single_preps + double_preps + hotwater
                        self.total_cups = single_preps + (double_preps * 2)

                        filter_cycles = eeprom.get(0x0052, 0)
                    else:
                        # Map standard Jura EEPROM statistics addresses
                        esp1 = eeprom.get(1, 0)
                        cof1 = eeprom.get(2, 0)
                        spec1 = eeprom.get(3, 0)
                        esp2 = eeprom.get(4, 0)
                        cof2 = eeprom.get(5, 0)
                        spec2 = eeprom.get(6, 0)

                        self.counters[1] = esp1
                        self.counters[2] = cof1
                        if spec1 > 0:
                            self.counters[3] = spec1
                        self.counters[4] = esp2
                        self.counters[5] = cof2
                        if spec2 > 0:
                            self.counters[6] = spec2

                        self.total_preparations = esp1 + cof1 + spec1 + esp2 + cof2 + spec2
                        self.total_cups = esp1 + cof1 + spec1 + (esp2 * 2) + (cof2 * 2) + (spec2 * 2)

                        filter_cycles = eeprom.get(20, 0)

                    rinses = eeprom.get(7, 0)
                    cleanings = eeprom.get(8, 0)
                    descalings = eeprom.get(9, 0)
                    grinder_sec = eeprom.get(10, 0)

                    water_dl = eeprom.get(16, 0)
                    decalc_dl = eeprom.get(18, 0)
                    since_serv = eeprom.get(21, 0)
                    water_since_decalc = eeprom.get(31, 0)

                    # Hardware and Serial Identification
                    machine_num = eeprom.get(0x30, 0)
                    serial_word = eeprom.get(0x31, 0)
                    prod_val = eeprom.get(0x32, 0)
                    country_word = eeprom.get(0xDA, 0)
                    spdl_dl_val = eeprom.get(0xDB, 0)
                    spdl_lang_val = eeprom.get(0xDC, 0)
                    since_prep = eeprom.get(0x15, 0)
                    retail_high = eeprom.get(0xE9, 0)
                    retail_low = eeprom.get(0xEA, 0)
                    c3_val = eeprom.get(0xC3, 0)

                    app_code = f"{machine_num:04X}{prod_val:04X}" if (machine_num or prod_val) else "N/A"

                    # Jura Production Date decoding:
                    # 16-bit bitfield: Day (bits 0..4), Month (bits 5..8), Year = 1990 + (bits 9..15)
                    prod_dt = decode_jura_date(prod_val)
                    prod_date_str = f"{prod_dt.day}.{prod_dt.month}.{prod_dt.year}" if prod_dt else "N/A"
                    date_prefix = prod_dt.strftime("%Y%m%d") if prod_dt else ""

                    # Jura 14-digit Serial Number format (GS1 Application Identifier 21):
                    # Formed by YYYYMMDD (Production Date) + 6-digit zero-padded Appliance Number
                    # Example: 20130530 + 018016 -> "20130530018016"
                    if date_prefix and machine_num:
                        serial_number = f"{date_prefix}{machine_num:06d}"
                    elif machine_num:
                        serial_number = f"{machine_num:06d}"
                    else:
                        serial_number = "N/A"

                    # Country Code decoding:
                    # 0x00DA stores two ASCII characters for destination market (e.g. 0x435A -> 'CZ')
                    country_code = "N/A"
                    if country_word and country_word > 0:
                        hi = (country_word >> 8) & 0xFF
                        lo = country_word & 0xFF
                        chars = "".join(chr(c) for c in (hi, lo) if 32 <= c <= 126).strip()
                        if chars:
                            country_code = chars

                    # SPDL Dates:
                    spdl_dl_dt = decode_jura_date(spdl_dl_val)
                    spdl_dl_str = f"{spdl_dl_dt.day}.{spdl_dl_dt.month}.{spdl_dl_dt.year}" if spdl_dl_dt else "N/A"

                    spdl_lang_dt = decode_jura_date(spdl_lang_val)
                    spdl_lang_str = f"{spdl_lang_dt.day}.{spdl_lang_dt.month}.{spdl_lang_dt.year}" if spdl_lang_dt else "N/A"

                    # Water Hardness:
                    if is_d4 and 0x11 in eeprom and eeprom[0x11] > 0:
                        water_hardness = eeprom[0x11]
                    else:
                        water_hardness = (c3_val >> 8) & 0xFF if c3_val else 30

                    # Cups and preparations since last service intervention:
                    retail_ref = (retail_high * 65536) + retail_low
                    cups_since_intervention = max(0, self.total_cups - retail_ref) if (retail_ref > 0 or retail_high or retail_low) else self.total_cups
                    prep_since_intervention = since_prep if since_prep > 0 else since_serv

                    # Article Number and Full EAN Code:
                    # Hardware EEPROM Article Number (words 0x7E/0x7F on EF509/A1/ENA platforms)
                    hw_article = None
                    if 0x7E in eeprom and 0x7F in eeprom:
                        hi_w = eeprom.get(0x7E, 0)
                        lo_w = eeprom.get(0x7F, 0)
                        hi_b = (hi_w >> 8) if (hi_w & 0xFF00) else (hi_w & 0xFF)
                        lo_b = (lo_w >> 8) if (lo_w & 0xFF00) else (lo_w & 0xFF)
                        if hi_b > 0 and lo_b > 0:
                            cand = (hi_b << 8) | lo_b
                            if 10000 <= cand <= 99999:
                                hw_article = str(cand)

                    if hw_article:
                        article_num = hw_article
                        if hw_article in ARTICLE_MODEL_MAP:
                            fam, app_desc, _ = ARTICLE_MODEL_MAP[hw_article]
                            self.model_family = fam
                            app_type = app_desc
                            # If hardware article specifies a refined model (e.g. WE8 vs E8), switch to its profile
                            art_profile = profiles_db.get_model_spec(hw_article) or profiles_db.find_profile(fam)
                            if art_profile and art_profile != profiles_db.DEFAULT_PROFILE:
                                self.profile = art_profile
                        else:
                            art_spec = profiles_db.get_model_spec(hw_article)
                            if isinstance(art_spec, dict):
                                merged_profile = dict(self.profile) if isinstance(self.profile, dict) else {}
                                existing_alerts = merged_profile.get("alerts")
                                for k, v in art_spec.items():
                                    if v is not None:
                                        merged_profile[k] = v
                                if not merged_profile.get("alerts") and existing_alerts:
                                    merged_profile["alerts"] = existing_alerts
                                self.profile = merged_profile
                                spec_fam = str(art_spec.get("model_family") or "").strip()
                                if spec_fam:
                                    self.model_family = spec_fam
                                app_type = str(art_spec.get("appliance_type") or (f"{hw_article} {spec_fam}" if spec_fam else f"{hw_article} {self.model_family}")).strip()
                            else:
                                app_type = f"{hw_article} {self.model_family}"
                    else:
                        article_num = str(self.profile.get("article_number", "13356" if is_z5 else ("15221" if is_d4 else ("15133" if is_a1 else ("13500" if is_ena7 else "13705")))))
                        app_type = self.profile.get("appliance_type", self.model_family)

                    ean_code = "N/A"
                    if article_num and serial_number != "N/A":
                        try:
                            base_ean = f"07610917{int(article_num):05d}"
                            gtin14 = f"{base_ean}{calculate_gs1_check_digit(base_ean)}"
                            ean_code = f"(01){gtin14}(21){serial_number}"
                        except Exception:
                            pass

                    if is_we8 or is_e8:
                        clean_pct = eeprom.get(0x0163, 0) & 0xFF if 0x0163 in eeprom else None
                        decalc_pct = eeprom.get(0x0162, 0) & 0xFF if 0x0162 in eeprom else None
                        filter_pct = eeprom.get(0x01E1, 0) & 0xFF if 0x01E1 in eeprom else None
                        self.maint_counts = [cleanings, descalings, rinses, filter_cycles, milk_rinses, milk_cleanings]
                        self.maint_pcts = [clean_pct, decalc_pct, None, filter_pct, None, None]
                    else:
                        if is_ena7:
                            filter_cycles = eeprom.get(0x0052, 0)
                        self.maint_counts = [cleanings, descalings, rinses, filter_cycles]
                        self.maint_pcts = [None, None, None, None]

                    gh = grinder_sec // 3600
                    gm = (grinder_sec % 3600) // 60
                    gs = grinder_sec % 60

                    self.telemetry = {
                        "serial_number": serial_number,
                        "production_date": prod_date_str,
                        "appliance_number": machine_num,
                        "machine_number": machine_num,
                        "serial_number_word": serial_word,
                        "article_number": article_num,
                        "ean_code": ean_code,
                        "appliance_code": app_code,
                        "appliance_type": app_type,
                        "software_version_display": display_fw,
                        "spdl_download_date": spdl_dl_str,
                        "spdl_country_code": country_code,
                        "spdl_language_date": spdl_lang_str,
                        "water_hardness_dh": water_hardness,
                        "total_cups": self.total_cups,
                        "total_preparations": self.total_preparations,
                        "preparations_since_intervention": prep_since_intervention,
                        "cups_since_intervention": cups_since_intervention,
                        "grinder_seconds": grinder_sec,
                        "grinder_formatted": f"{gh}h {gm}m {gs}s",
                        "water_dispensed_liters": round(water_dl / 10.0, 1),
                        "descaling_agent_liters": round(decalc_dl / 10.0, 1),
                        "since_last_service_preparations": prep_since_intervention,
                        "water_since_decalc_liters": round(water_since_decalc / 10.0, 1),
                        "power_spec": self.power_spec,
                    }

                    # Store swept EEPROM and apply any saved local AI/J.O.E. offset override immediately
                    self.last_eeprom = dict(eeprom)
                    self.address_width = address_width
                    self.apply_local_offset_override(self.last_eeprom, article_num=article_num)

                    # Interrogate Live Hardware Sensors & Switches
                    update_prog(0.96, "Reading live sensors & hardware switches (HZ:, RE:0028)...")
                    self.live_sensors = self.query_live_sensors()
                    if self.live_sensors.get("alerts"):
                        self.active_alerts = []
                        for a in self.live_sensors["alerts"]:
                            name = a.get("name")
                            details = a.get("details", "")
                            msg = a.get("message") or (f"{name}: {details}" if name else str(a))
                            self.active_alerts.append({
                                "bit": 0,
                                "blocking": a.get("blocking", True),
                                "name": msg
                            })
                    else:
                        self.active_alerts = [
                            {"bit": 0, "blocking": False, "name": "System Nominal / Ready to Brew"}
                        ]

                    update_prog(1.0, "Interrogation completed successfully!")
                    self.log(f"ASCII Interrogation successful: {self.total_cups:,} cups read!")
                    return True

            # ================================================================
            # Mode B: Smart Connect Handshake (@T0) - Encrypted 4:1 Wire
            # ================================================================
            self.log("Initiating Smart Connect handshake (@T0)...")
            update_prog(0.20, "Initiating Smart Connect handshake (@T0)...")
            t0_resp = self._send_encrypted_cmd("@T0\r\n", key=0x20, timeout=1.2)

            if not t0_resp:
                if ascii_model_hint:
                    self.log("Notice: Smart Connect (@T0) also returned no reply; returning ASCII identity without valid EEPROM.")
                else:
                    self.log("ERROR: Machine did not respond to ASCII (TY:) or Smart Connect (@T0).")
                return False

            self.is_legacy_cleartext = False
            if self.conn is not None:
                setattr(self.conn, "_is_smart_connect", True)
                if getattr(self.conn, "wire_mode", None) is None:
                    setattr(self.conn, "wire_mode", "smart_connect")
            self.protocol_mode = "Encrypted Smart Connect (@-Protocol)"
            update_prog(0.28, "Sending handshake step 2 (@T1)...")
            t1_resp = self._send_encrypted_cmd("@T1\r\n", key=0x21, timeout=1.2)

            challenge_payload = "01C000"
            if t1_resp and t1_resp.startswith("@T2:"):
                challenge_payload = t1_resp[4:].strip()

            update_prog(0.35, "Answering machine challenge (@t2)...")
            t3_resp = self._send_encrypted_cmd("@t2:818000\r\n", key=0x22, timeout=1.2)

            if t3_resp and "@T3:" in t3_resp:
                idx = t3_resp.find("@T3:")
                self.raw_model_str = t3_resp[idx + 4:].strip()
                self._send_encrypted_cmd("@t3\r\n", key=0x23, timeout=0.6)
            elif ascii_model_hint:
                self.raw_model_str = ascii_model_hint
            else:
                self.raw_model_str = "EF536M V02.01 (Smart Connect)"

            self.profile = profiles_db.find_profile(self.raw_model_str)
            if (self.profile == profiles_db.DEFAULT_PROFILE or not self.profile) and ascii_profile_hint:
                self.profile = ascii_profile_hint
            self.model_family = self.profile.get("model_family", "Modern Jura")
            self.ef_code = self.raw_model_str
            self.log(f"Smart Connect machine identified: {self.model_family} ({self.raw_model_str})")

            # Beverage Counters & EEPROM Banks (@TR:32,00 .. 1F)
            update_prog(0.45, "Reading beverage counters & Smart Connect memory banks...")
            sc_eeprom: Dict[int, int] = {}
            consecutive_tr_empty = 0
            for bank in range(32):
                if bank >= 12 and consecutive_tr_empty >= 2:
                    break
                update_prog(0.45 + (min(bank, 12) / 12.0) * 0.35, f"Reading beverage counters (Bank {bank})...")
                cmd = f"@TR:32,{bank:02X}\r\n"
                resp = self._send_encrypted_cmd(cmd, key=(0x30 + bank) & 0xFF, timeout=0.8)
                if resp:
                    parsed = jp.parse_tr32(resp)
                    if parsed:
                        consecutive_tr_empty = 0
                        _, words = parsed
                        base_addr = bank * 4
                        for w_idx, count_val in enumerate(words):
                            sc_eeprom[base_addr + w_idx] = count_val
                            if bank < 12:
                                code = bank * 4 + w_idx
                                if count_val != 0xFFFF:
                                    self.counters[code] = count_val
                    else:
                        consecutive_tr_empty += 1
                else:
                    consecutive_tr_empty += 1
                    if bank == 1 and consecutive_tr_empty >= 2:
                        break

            self.last_eeprom = dict(sc_eeprom)
            self.address_width = 4

            per_prod = {k: v for k, v in self.counters.items() if k != 0 and v > 0}
            if per_prod:
                prof_by_code = {
                    p.get("code"): p
                    for p in self.profile.get("products", [])
                    if isinstance(p, dict) and p.get("code") is not None
                }
                coffee_cups = 0
                for code, count_val in per_prod.items():
                    p_def = prof_by_code.get(code, {})
                    pname = str(p_def.get("name") or profiles_db.get_product_name(self.profile, code))
                    is_dbl = bool(p_def.get("is_double", False))
                    if not is_non_coffee_product(pname, code):
                        coffee_cups += (count_val * 2) if is_dbl else count_val
                self.total_preparations = self.counters.get(0, sum(per_prod.values()))
                self.total_cups = coffee_cups
            else:
                self.total_preparations = self.counters.get(0, 0)
                self.total_cups = self.total_preparations

            # Maintenance Counters (@TG:43)
            update_prog(0.82, "Reading maintenance counters (@TG:43)...")
            tg43_resp = self._send_encrypted_cmd("@TG:43\r\n", key=0x40, timeout=1.0)
            if tg43_resp:
                mc = jp.parse_tg43(tg43_resp)
                if mc:
                    self.maint_counts = mc
                    self.log(f"Parsed Maintenance Counts: {self.maint_counts}")

            # Maintenance Percentages (@TG:C0)
            update_prog(0.88, "Reading maintenance life percentages (@TG:C0)...")
            tgc0_resp = self._send_encrypted_cmd("@TG:C0\r\n", key=0x41, timeout=1.0)
            if tgc0_resp:
                mp = jp.parse_tgc0(tgc0_resp)
                if mp:
                    self.maint_pcts = mp
                    self.log(f"Parsed Maintenance Percentages: {self.maint_pcts}")

            # Alerts & Telemetry (@TF:)
            update_prog(0.94, "Reading active alerts and system status (@TF:)...")
            tf_resp = self._send_encrypted_cmd("@TF:\r\n", key=0x42, timeout=1.0)
            if tf_resp:
                raw_tf = jp.parse_tf(tf_resp)
                if raw_tf:
                    self.active_alerts = profiles_db.get_active_alerts(self.profile, raw_tf)

            sc_article_num = str(self.profile.get("article_number") or "")
            if not self.telemetry:
                self.telemetry = {
                    "total_cups": self.total_cups,
                    "total_preparations": self.total_preparations,
                    "article_number": sc_article_num or "N/A",
                    "serial_number": "2018041544012" if (self.conn and self.conn.is_demo) else "N/A",
                    "production_date": "15.04.2018" if (self.conn and self.conn.is_demo) else "N/A",
                    "machine_number": 44012 if (self.conn and self.conn.is_demo) else "N/A",
                    "country_code": "EU" if (self.conn and self.conn.is_demo) else "N/A",
                }
            if self.last_eeprom:
                self.apply_local_offset_override(self.last_eeprom, article_num=sc_article_num)

            # Interrogate Live Telemetry & Alerts
            self.live_sensors = self.query_live_sensors()

            update_prog(1.0, "Interrogation successfully completed!")
            self.log("Smart Connect interrogation completed successfully!")
            return True

        except Exception as e:
            self.log(f"EXCEPTION during interrogation: {e}")
            return False
        finally:
            if owns_conn and self.conn:
                self.conn.close()

    def get_structured_summary(self) -> Dict[str, Any]:
        """Produce structured statistics dictionary."""
        grand_total = self.total_cups if self.total_cups is not None else self.total_preparations

        # Build beverage list
        beverage_list = []
        profile_codes = set()
        if self.override_products:
            profile_prods = self.override_products
        else:
            profile_prods = self.profile.get("products", [])
            # In ASCII EEPROM mode, if a generic or unconfigured profile was matched,
            # fall back to classic 6-slot EEPROM beverage descriptors so counts are not mislabeled.
            # But if the matched profile has a specific product list (e.g. Z5 with 13 products), preserve it!
            if self.is_legacy_cleartext and (not profile_prods or self.profile.get("model_family") == "Generic Jura Automatic"):
                profile_prods = [
                    {"code": 1, "name": "1 Espresso", "is_double": False, "active": True},
                    {"code": 2, "name": "1 Coffee", "is_double": False, "active": True},
                    {"code": 3, "name": "1 Special Coffee / Ristretto", "is_double": False, "active": True},
                    {"code": 4, "name": "2 Espressi", "is_double": True, "active": True},
                    {"code": 5, "name": "2 Coffees", "is_double": True, "active": True},
                    {"code": 6, "name": "2 Special Coffees", "is_double": True, "active": True},
                ]

        for p in profile_prods:
            code = p.get("code")
            profile_codes.add(code)
            count = self.counters.get(code, 0)
            beverage_list.append({
                "code": code,
                "name": p.get("name", f"Product #{code}"),
                "count": count,
                "is_double": p.get("is_double", False),
                "active": p.get("active", True)
            })

        # Add any other non-zero counters not in profile
        for code, count in sorted(self.counters.items()):
            if code != 0 and code not in profile_codes and count > 0:
                beverage_list.append({
                    "code": code,
                    "name": profiles_db.get_product_name(self.profile, code),
                    "count": count,
                    "is_double": False,
                    "active": True
                })

        # Build maintenance list
        if self.override_maint_labels:
            mc_labels = self.override_maint_labels
        elif self.is_legacy_cleartext:
            if len(self.maint_counts) == 6:
                mc_labels = ["Cleaning", "Descaling", "Coffee System Rinsing", "Filter Change", "Milk System Rinsing", "Milk System Cleaning"]
            else:
                mc_labels = ["Cleaning", "Descaling", "Rinsing", "Filter Change"]
        else:
            mc_labels = self.profile.get("maintenance_counters", [
                "Cleaning", "FilterChange", "Decalc", "CappuRinse", "CoffeeRinse", "CappuClean"
            ])

        maint_data = []
        for i, label in enumerate(mc_labels):
            cnt = self.maint_counts[i] if i < len(self.maint_counts) else 0
            pct = self.maint_pcts[i] if i < len(self.maint_pcts) else None
            maint_data.append({
                "index": i,
                "label": label,
                "name": label,
                "count": cnt,
                "percentage": pct,
                "percent": pct
            })

        try:
            import offset_db_sync
            _odb_status = offset_db_sync.get_offset_db_status()
            offset_db_version = str(_odb_status.get("offset_db_version") or f"bundled-{__build__}")
            offset_db_source = str(_odb_status.get("source") or "bundled_factory")
        except Exception:
            offset_db_version = f"bundled-{__build__}"
            offset_db_source = "bundled_factory"

        return {
            "spectra_version": f"Build {__build__}",
            "spectra_build": __build__,
            "offset_db_version": offset_db_version,
            "offset_db_source": offset_db_source,
            "timestamp": datetime.now().isoformat(),
            "port": self.port_name,
            "machine_model": self.model_family,
            "appliance_type": self.telemetry.get("appliance_type", self.model_family),
            "article_number": self.telemetry.get("article_number", "N/A"),
            "firmware_string": self.raw_model_str,
            "ef_code": self.ef_code,
            "protocol_mode": self.protocol_mode,
            "power_spec": self.power_spec,
            "serial_number": self.telemetry.get("serial_number", "N/A"),
            "production_date": self.telemetry.get("production_date", "N/A"),
            "machine_number": self.telemetry.get("machine_number", "N/A"),
            "country_code": self.telemetry.get("country_code", "N/A"),
            "market_region": self.telemetry.get("market_region", self.telemetry.get("country_code", "N/A")),
            "total_preparations": self.total_preparations,
            "total_cups": grand_total,
            "beverages": beverage_list,
            "maintenance": maint_data,
            "telemetry": self.telemetry,
            "alerts": self.active_alerts,
            "live_sensors": self.live_sensors,
            "raw_log_entries": len(self.raw_log),
            "offset_override": self.offset_override_info,
        }

    # ========================================================================
    # Exporters
    # ========================================================================

    def export_text_report(self) -> str:
        """
        Generate clean formatted diagnostics report matching
        the classic Jura Service Diagnostics format.
        """
        data = self.get_structured_summary()
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        out = []
        out.append("=" * 78)
        out.append("JURA COFFEE MACHINE DIAGNOSTICS & TELEMETRY REPORT")
        out.append(f"SPECTRA Diagnostics Suite (Build {__build__}) (Hardware Telemetry - Jura Module)")
        out.append(f"Offset DB Version: {data.get('offset_db_version', f'bundled-{__build__}')} ({data.get('offset_db_source', 'bundled_factory')})")
        out.append("=" * 78)
        out.append("")
        out.append(f"Date of diagnosis: {now_str}")
        out.append(f"Connection Port:   {self.port_name} (9600 8N1)")
        out.append("")
        out.append("-" * 78)
        out.append("APPLIANCE IDENTIFICATION & SYSTEM DATA:")
        out.append("-" * 78)
        if self.telemetry and "appliance_type" in self.telemetry:
            out.append(f"Appliance Type:    {self.telemetry['appliance_type']}")
        else:
            out.append(f"Appliance Model:   {data['machine_model']}")
        if self.telemetry and "article_number" in self.telemetry:
            out.append(f"Article Number:    {self.telemetry['article_number']}")
        out.append(f"Software Version:  {data['firmware_string']}")
        if self.telemetry and "software_version_display" in self.telemetry:
            out.append(f"Software Version Display: {self.telemetry['software_version_display']}")
        if self.telemetry and "serial_number" in self.telemetry and self.telemetry["serial_number"] != "N/A":
            out.append(f"Serial Number:     {self.telemetry['serial_number']}")
        if self.telemetry and "serial_number_word" in self.telemetry and self.telemetry["serial_number_word"]:
            out.append(f"Serial Word (ID):  {self.telemetry['serial_number_word']}")
        if self.telemetry and "appliance_number" in self.telemetry:
            out.append(f"Appliance Number:  {self.telemetry['appliance_number']}")
        if self.telemetry and "production_date" in self.telemetry and self.telemetry["production_date"] != "N/A":
            out.append(f"Date of Production:{self.telemetry['production_date']:>14}")
        if self.telemetry and "appliance_code" in self.telemetry and self.telemetry["appliance_code"] != "N/A":
            out.append(f"Appliance Code:    {self.telemetry['appliance_code']}")
        if self.telemetry and "ean_code" in self.telemetry and self.telemetry["ean_code"] != "N/A":
            out.append(f"EAN-Code:          {self.telemetry['ean_code']}")
        out.append(f"Protocol:          {data['protocol_mode']}")
        out.append(f"Power Spec:        {data['power_spec']}")
        if self.telemetry:
            if "spdl_download_date" in self.telemetry and self.telemetry["spdl_download_date"] != "N/A":
                out.append(f"SPDL Date Download:{self.telemetry['spdl_download_date']:>14}")
            if "spdl_country_code" in self.telemetry and self.telemetry["spdl_country_code"] != "N/A":
                out.append(f"SPDL Country Code: {self.telemetry['spdl_country_code']}")
            if "spdl_language_date" in self.telemetry and self.telemetry["spdl_language_date"] != "N/A":
                out.append(f"SPDL Date Lang:    {self.telemetry['spdl_language_date']:>14}")
            if "water_hardness_dh" in self.telemetry:
                out.append(f"Water Hardness:    {self.telemetry['water_hardness_dh']} °dH")
        out.append("")

        out.append("-" * 78)
        out.append("BEVERAGE PREPARATIONS & DISPENSING COUNTERS:")
        out.append("-" * 78)
        out.append(f"   {data['total_cups']:>8}      Total Number of Coffee Cups")
        if self.telemetry and "cups_since_intervention" in self.telemetry:
            out.append(f"   {self.telemetry['cups_since_intervention']:>8}      Total Coffee Cups Since Last Intervention")
        out.append(f"   {data['total_preparations']:>8}      Total Coffee Preparations")
        if self.telemetry and "preparations_since_intervention" in self.telemetry:
            out.append(f"   {self.telemetry['preparations_since_intervention']:>8}      Preparations Since Last Intervention")
        out.append("   " + "-" * 55)

        for bev in sorted(data['beverages'], key=lambda x: x['count'], reverse=True):
            if bev['count'] > 0:
                dbl_str = " (2x Cups)" if bev['is_double'] else ""
                out.append(f"   {bev['count']:>8}      {bev['name']}{dbl_str}")

        unused = [b for b in data['beverages'] if b['count'] == 0]
        if unused:
            out.append("")
            out.append("   Beverages with 0 preparations:")
            for b in unused[:8]:
                out.append(f"          0      {b['name']}")
        out.append("")

        out.append("-" * 78)
        out.append("MAINTENANCE & HYGIENE COUNTERS:")
        out.append("-" * 78)
        for m in data['maintenance']:
            pct_str = f" [Life remaining: {m['percentage']}%]" if m['percentage'] is not None else ""
            out.append(f"   {m['count']:>8}      Total {m['label']}{pct_str}")
        out.append("")

        if self.telemetry:
            out.append("-" * 78)
            out.append("OPERATIONAL TELEMETRY & LIFETIME METRICS:")
            out.append("-" * 78)
            if "grinder_formatted" in self.telemetry:
                out.append(f"   Grinder Operating Time:     {self.telemetry['grinder_formatted']} ({self.telemetry['grinder_seconds']} seconds)")
            if "water_dispensed_liters" in self.telemetry:
                out.append(f"   Total Water Dispensed:      {self.telemetry['water_dispensed_liters']} Liters")
            if "descaling_agent_liters" in self.telemetry:
                out.append(f"   Descaling Agent Consumed:   {self.telemetry['descaling_agent_liters']} Liters")
            if "since_last_service_preparations" in self.telemetry:
                out.append(f"   Cycles Since Last Service:  {self.telemetry['since_last_service_preparations']} preparations")
            out.append("")

        out.append("-" * 78)
        out.append("ACTIVE SYSTEM ALERTS & TELEMETRY:")
        out.append("-" * 78)
        if not data['alerts']:
            out.append("   [OK] System Ready - No Active Faults or Warnings")
        else:
            for alert in data['alerts']:
                status_type = "CRITICAL / BLOCKING" if alert.get('blocking') else "READY / STATUS"
                out.append(f"   [{status_type}] {alert['name']}")
        out.append("")

        # Live Sensors & Hardware Output
        ls = self.live_sensors or data.get("live_sensors")
        if ls and (ls.get("switches") or ls.get("sensors") or ls.get("telemetry")):
            out.append("-" * 78)
            ts = ls.get("timestamp", now_str)
            out.append(f"LIVE HARDWARE SENSORS & TELEMETRY (Read at: {ts}):")
            out.append("-" * 78)

            telem = ls.get("telemetry", {})
            if telem:
                out.append("   [Thermoblock Heaters & Thermal Sensors]")
                is_dual = telem.get("is_dual_heater", False)
                arch_str = "Dual-Heater Model (2 Thermoblocks)" if is_dual else "Single-Heater Model (1 Thermoblock)"
                out.append(f"   * Appliance Architecture        : {arch_str}")
                c_str = telem.get("heater_coffee_str", "N/A")
                c_stat = telem.get("heater_coffee_status", "")
                out.append(f"   * Coffee Thermoblock (TB1)      : {c_str:<12} [{c_stat}]")
                s_str = telem.get("heater_steam_str", "N/A")
                s_stat = telem.get("heater_steam_status", "")
                if is_dual:
                    out.append(f"   * Steam Thermoblock (TB2)       : {s_str:<12} [{s_stat}]")
                else:
                    out.append(f"   * Steam Thermoblock (TB2)       : Not Installed (Single Heater Model)")
                if "bu_encoder_str" in telem and telem["bu_encoder_str"] != "N/A":
                    out.append(f"   * Brew Unit Encoder (Pos / Ref) : {telem['bu_encoder_str']}")
                if "bu_mill_target" in telem:
                    out.append(f"   * Brew Unit Mill Target (RE:0041): {telem['bu_mill_target']} ticks (0x{telem['bu_mill_target']:04X})")
                if "bu_init_count" in telem:
                    out.append(f"   * Brew Unit Init Count (RE:0056): {telem['bu_init_count']} cycles")
                if "loader_version" in telem:
                    out.append(f"   * Main Board Bootloader (TL:)   : {telem['loader_version']}")
                if "display_firmware" in telem:
                    out.append(f"   * Display / Sub-MCU (TY$:)      : {telem['display_firmware']}")
                out.append("")

            if ls.get("switches"):
                out.append("   [Microswitches & Physical Contacts]")
                for sw in ls["switches"]:
                    out.append(f"   * {sw['name']:<30}: {sw['status']} [{sw.get('badge', 'OK')}]")
                out.append("")

            if ls.get("sensors"):
                out.append("   [Diagnostic Component Health & Safety Sensors]")
                for s in ls["sensors"]:
                    out.append(f"   * {s['name']:<32}: {s['status']} ({s['details']})")
                out.append("")

            if ls.get("error_counters"):
                out.append("   [Historical Sensor Trip & Fault Frequency Counters]")
                for c_name, c_cnt in ls["error_counters"].items():
                    out.append(f"   * {c_name:<36}: {c_cnt:>5} events")
                out.append("")

        out.append("=" * 78)
        out.append("END OF DIAGNOSTICS REPORT")
        out.append("=" * 78)
        return "\n".join(out)

    def export_json(self) -> str:
        """Export structured data as JSON string."""
        return json.dumps(self.get_structured_summary(), indent=2, ensure_ascii=False)

    def export_csv(self) -> str:
        """Export counters as CSV string."""
        data = self.get_structured_summary()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Category", "Item Code / Index", "Name / Label", "Value", "Unit / Notes"])
        writer.writerow(["Metadata", 0, "spectra_build", data.get("spectra_build", __build__), ""])
        writer.writerow(["Metadata", 1, "offset_db_version", data.get("offset_db_version", ""), data.get("offset_db_source", "")])
        writer.writerow(["Total", 0, "Grand Total Cups Dispensed", data["total_cups"], "cups"])
        writer.writerow(["Total", 1, "Total Brew Cycles", data["total_preparations"], "cycles"])

        for bev in data["beverages"]:
            writer.writerow(["Beverage", bev["code"], bev["name"], bev["count"], "cups"])

        for m in data["maintenance"]:
            writer.writerow(["Maintenance", m["index"], m["label"], m["count"], f"Life: {m['percentage']}%" if m['percentage'] is not None else ""])

        if self.telemetry:
            for k, v in self.telemetry.items():
                writer.writerow(["Telemetry", 0, k, v, ""])

        for a in data["alerts"]:
            writer.writerow(["Alert", a.get("bit", 0), a["name"], "ACTIVE", "BLOCKING" if a.get("blocking") else "NOTICE"])

        return output.getvalue()

