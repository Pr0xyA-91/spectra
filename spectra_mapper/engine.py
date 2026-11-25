#!/usr/bin/env python3
"""SPECTRA Memory Mapper core EEPROM sweep, classification, and differential engine."""

import os
import re
import json
import time
import datetime
from typing import Dict, List, Tuple, Optional, Any, Set

import serial_io
import profiles_db

try:
    from version import __version__, __build__
except ImportError:
    __build__ = "20261112.1820"
    __version__ = f"Build {__build__}"

# Native Rust Core Acceleration Bridge (spectra_py)
try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False

from spectra_mapper.models import (
    STATUS_MAPPED,
    STATUS_THEORETICAL,
    STATUS_UNKNOWN,
    STATUS_BLANK,
    SAFE_READ_PREFIXES,
    FORBIDDEN_WRITE_COMMANDS,
    TWO_DIGIT_ADDRESS_EFS,
    UNIVERSAL_REGISTERS,
    THEORETICAL_REGISTERS,
    RegisterEntry,
    MemorySnapshot,
)

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# Memory Mapper Engine
# ============================================================================

class MemoryMapperEngine:
    """
    Core engine managing EEPROM sweeps, baseline differentials,
    register classification, and model specification persistence.
    """

    def __init__(self, conn: serial_io.JuraSerialConnection, models_dir: Optional[str] = None):
        self.conn = conn
        self.models_dir = models_dir or os.path.join(SCRIPT_DIR, "docs", "models")
        os.makedirs(self.models_dir, exist_ok=True)

        self.gateways: Dict[str, str] = {}
        self.ef_code: str = "UNKNOWN"
        self.model_family: str = "Jura Appliance"
        self.is_two_digit: bool = False
        self.address_width: int = 4
        self.max_words: int = 512
        self.model_spec: Dict[str, Any] = {}
        self.spec_file_path: Optional[str] = None

        self.current_eeprom: Dict[int, int] = {i: 0 for i in range(512)}
        self.baseline_snapshot: Optional[MemorySnapshot] = None
        self.classified_registers: List[RegisterEntry] = []
        self._consecutive_failed_blocks: int = 0
        self._any_block_succeeded: bool = False

        # Interrogate machine identity on start
        self.refresh_identity()

    def _assert_safe_command(self, cmd: str) -> str:
        """Enforce strict read-only safety invariant via central serial_io validator."""
        return serial_io.validate_readonly_command(cmd)

    def query_safe(self, cmd: str, timeout: float = 1.5) -> Optional[str]:
        """Execute query verifying read-only safety invariant."""
        clean_cmd = self._assert_safe_command(cmd)
        return self.conn.query_ascii(clean_cmd, timeout=timeout)

    def refresh_identity(self):
        """Interrogate identification gateways and load/create model specification."""
        if not getattr(self.conn, "_is_smart_connect", False):
            gateways_to_probe = ["TY:", "TL:", "TY$:", "TL$:", "CS$:", "IC:", "HZ:", "AS:"]
            for idx, g in enumerate(gateways_to_probe):
                try:
                    ans = self.query_safe(g, timeout=1.2)
                    if ans:
                        self.gateways[g] = ans.strip()
                    elif idx == 0 and getattr(self.conn, "wire_mode", None) is None:
                        # TY: failed with wire_mode still None — try Smart Connect immediately instead of stalling on 7 gateways
                        sc_model = self._smart_connect_handshake()
                        if sc_model:
                            self.gateways["@T3:"] = sc_model
                        break
                except Exception:
                    pass

        ty = self.gateways.get("TY:", "") or self.gateways.get("@T3:", "")
        m = re.search(r'(EF[A-Z0-9_]+)', ty.upper())
        if m:
            self.ef_code = m.group(1)
        elif self.conn.is_demo and "XJ5" in self.conn.port_name.upper():
            self.ef_code = "EF518M"
        else:
            self.ef_code = "UNKNOWN"

        profile = profiles_db.find_profile(self.ef_code)
        self.is_two_digit = (
            profile.get("address_width") == 2
            or any(self.ef_code.upper().startswith(p) for p in TWO_DIGIT_ADDRESS_EFS)
        )
        self.address_width = 2 if self.is_two_digit else 4
        self.max_words = profile.get("max_words", 256 if self.is_two_digit else 512)
        self.current_eeprom = {i: 0 for i in range(self.max_words)}

        self._load_or_init_model_spec()

    def _load_or_init_model_spec(self):
        """Find or initialize model specification file in docs/models/."""
        # 1. Search for matching EF file
        found_spec = None
        found_path = None

        if os.path.exists(self.models_dir):
            for fname in os.listdir(self.models_dir):
                if fname.upper().startswith(self.ef_code.upper()) and fname.endswith(".json"):
                    fpath = os.path.join(self.models_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        found_spec = data
                        found_path = fpath
                        break
                    except Exception:
                        pass

        if found_spec:
            self.model_spec = found_spec
            self.spec_file_path = found_path
            self.model_family = found_spec.get("model_family", self.model_family)
        else:
            # Try profiles database
            profile = profiles_db.find_profile(self.ef_code)
            self.model_family = profile.get("model_family", f"Jura Appliance ({self.ef_code})")
            clean_name = re.sub(r'[^A-Za-z0-9_]+', '_', self.model_family).strip('_')
            fname = f"{self.ef_code}_{clean_name}.json"
            self.spec_file_path = os.path.join(self.models_dir, fname)

            self.model_spec = {
                "model_family": self.model_family,
                "ef_code": self.ef_code,
                "display_ef": self.gateways.get("TY$:", "").replace("ty$:", ""),
                "series": profile.get("series", "Jura Appliance"),
                "address_width": self.address_width,
                "max_words": self.max_words,
                "article_numbers": [str(a) for a in profile.get("articles", [])],
                "hardware": {
                    "thermoblocks": 1,
                    "has_steam_heater": False,
                    "has_optical_hopper": bool("AS:" in self.gateways and "as:" in self.gateways["AS:"].lower()),
                    "has_sub_bus": bool("TY$:" in self.gateways),
                    "has_external_plumbing": False,
                    "flowmeter_pulses_per_ml": 2.366
                },
                "custom_registers": {}
            }

    def _smart_connect_handshake(self) -> Optional[str]:
        """Run Smart Connect @T0..@t3 handshake via conn.query_encrypted and return model string if detected."""
        if not hasattr(self.conn, "query_encrypted"):
            return None
        t0 = self.conn.query_encrypted("@T0\r\n", key=0x20, timeout=1.0)
        if not t0:
            return None
        setattr(self.conn, "_is_smart_connect", True)
        self.conn.query_encrypted("@T1\r\n", key=0x21, timeout=0.8)
        t3 = self.conn.query_encrypted("@t2:818000\r\n", key=0x22, timeout=1.0)
        model_str = None
        if t3 and "@T3:" in t3:
            model_str = t3[t3.find("@T3:") + 4:].strip()
            self.conn.query_encrypted("@t3\r\n", key=0x23, timeout=0.6)
        return model_str or "Smart Connect"

    def _smart_connect_sweep_eeprom(self, progress_callback=None) -> bool:
        """Sweep Smart Connect memory banks via @TR:32,00..1F into self.current_eeprom."""
        import jura_protocol as jp
        if not hasattr(self.conn, "query_encrypted"):
            return False

        cached_bank0_resp: Optional[str] = None
        if not getattr(self.conn, "_is_smart_connect", False):
            if not self._smart_connect_handshake():
                return False
        else:
            # Ensure session is active; reuse bank 0 reply if valid so @TR:32,00 is not queried twice
            test_r = self.conn.query_encrypted("@TR:32,00\r\n", key=0x30, timeout=0.8)
            if test_r and jp.parse_tr32(test_r):
                cached_bank0_resp = test_r
            elif not self._smart_connect_handshake():
                return False

        any_bank = False
        consecutive_empty = 0
        for page in range(32):
            if not getattr(self.conn, "is_open", True):
                raise IOError("Serial port disconnected during Smart Connect EEPROM sweep.")
            if progress_callback:
                progress_callback(page + 1, 32, f"Reading Smart Connect Bank 0x{page:02X}...")
            if page == 0 and cached_bank0_resp is not None:
                resp = cached_bank0_resp
            else:
                resp = self.conn.query_encrypted(f"@TR:32,{page:02X}\r\n", key=(0x30 + page) & 0xFF, timeout=0.8)
            if resp:
                parsed = jp.parse_tr32(resp)
                if parsed:
                    any_bank = True
                    consecutive_empty = 0
                    _, words = parsed
                    base = page * 4
                    for idx, w in enumerate(words):
                        self.current_eeprom[base + idx] = w
                    continue
            consecutive_empty += 1
            if page >= 12 and consecutive_empty >= 2:
                break
            if page == 1 and not any_bank and consecutive_empty >= 2:
                break
        return any_bank

    def sweep_eeprom(self, progress_callback=None) -> Dict[int, int]:
        """
        Perform complete EEPROM sweep (16 blocks for 2-digit models, 32/64 blocks for 4-digit models),
        probing first word before 16-word RE: fallback and falling back to Smart Connect @TR:32 if needed.
        """
        if getattr(self.conn, "_is_smart_connect", False):
            if self._smart_connect_sweep_eeprom(progress_callback=progress_callback):
                self.classify_all()
                return dict(self.current_eeprom)

        total_blocks = max(1, self.max_words // 16)
        consecutive_failed_blocks = 0
        any_block_succeeded = False

        for b_idx in range(total_blocks):
            if not getattr(self.conn, "is_open", True):
                raise IOError("Serial port disconnected during EEPROM sweep.")
            blk = b_idx * 16
            blk_str = f"{blk:02X}" if self.address_width == 2 else f"{blk:04X}"
            if progress_callback:
                progress_callback(b_idx + 1, total_blocks, f"Reading Block 0x{blk_str}...")

            cmd = f"RT:{blk_str}"
            try:
                ans = self.query_safe(cmd, timeout=1.5)
            except (IOError, OSError) as exc:
                if not getattr(self.conn, "is_open", True):
                    raise IOError(f"Serial port disconnected at block 0x{blk_str}: {exc}") from exc
                ans = None

            block_success = False
            if ans and ans.lower().startswith("rt:"):
                raw_hex = ans[3:].strip()
                if len(raw_hex) >= 64:
                    if HAS_RUST_CORE and _rust_core is not None:
                        try:
                            words = _rust_core.parse_rt_block(ans)
                            if len(words) == 16:
                                for i, w in enumerate(words):
                                    self.current_eeprom[blk + i] = w
                                block_success = True
                        except Exception:
                            pass
                    if not block_success:
                        parsed_ok = True
                        for i in range(16):
                            w_hex = raw_hex[i * 4: i * 4 + 4]
                            try:
                                self.current_eeprom[blk + i] = int(w_hex, 16)
                            except ValueError:
                                parsed_ok = False
                                break
                        if parsed_ok:
                            block_success = True

            if block_success:
                any_block_succeeded = True
                consecutive_failed_blocks = 0
            else:
                # Probe first word RE:{blk} before looping across remaining 15 words
                first_addr_str = f"{blk:02X}" if self.address_width == 2 else f"{blk:04X}"
                try:
                    first_ans = self.query_safe(f"RE:{first_addr_str}", timeout=1.0)
                except (IOError, OSError) as exc:
                    if not getattr(self.conn, "is_open", True):
                        raise IOError(f"Serial port disconnected at word 0x{first_addr_str}: {exc}") from exc
                    first_ans = None

                if first_ans and first_ans.lower().startswith("re:"):
                    try:
                        self.current_eeprom[blk] = int(first_ans[3:].strip()[:4], 16)
                    except ValueError:
                        self.current_eeprom[blk] = 0x0000
                    consecutive_failed_blocks = 0
                    any_block_succeeded = True
                    for i in range(1, 16):
                        if not getattr(self.conn, "is_open", True):
                            raise IOError("Serial port disconnected during EEPROM sweep.")
                        addr = blk + i
                        addr_str = f"{addr:02X}" if self.address_width == 2 else f"{addr:04X}"
                        try:
                            w_ans = self.query_safe(f"RE:{addr_str}", timeout=1.0)
                        except (IOError, OSError) as exc:
                            if not getattr(self.conn, "is_open", True):
                                raise IOError(f"Serial port disconnected at word 0x{addr_str}: {exc}") from exc
                            w_ans = None
                        if w_ans and w_ans.lower().startswith("re:"):
                            try:
                                self.current_eeprom[addr] = int(w_ans[3:].strip()[:4], 16)
                            except ValueError:
                                self.current_eeprom[addr] = 0x0000
                        else:
                            self.current_eeprom[addr] = 0x0000
                else:
                    for i in range(16):
                        self.current_eeprom[blk + i] = 0x0000
                    consecutive_failed_blocks += 1
                    if (not any_block_succeeded and consecutive_failed_blocks >= 2) or consecutive_failed_blocks >= 3:
                        break

        # Fall back to Smart Connect @TR:32 if initial ASCII blocks failed or returned all zeros
        has_nonzero = any(v not in (0, 0xFFFF) for v in self.current_eeprom.values())
        if (not any_block_succeeded and consecutive_failed_blocks >= 2) or not has_nonzero:
            self._smart_connect_sweep_eeprom(progress_callback=progress_callback)

        self.classify_all()
        return dict(self.current_eeprom)

    def _sweep_block_smart_connect(self, b_idx: int) -> Tuple[List[RegisterEntry], bool, bool]:
        """Sweep 4 consecutive 4-word Smart Connect banks (16 words) for block b_idx.
        Returns (entries, any_bank_succeeded, end_of_table).
        """
        import jura_protocol as jp
        blk = b_idx * 16
        any_bank_ok = False
        consec_sub_fail = 0
        all_sub_failed = True
        for sub in range(4):
            if not getattr(self.conn, "is_open", True):
                raise IOError("Serial port disconnected during block sweep.")
            bank = b_idx * 4 + sub
            resp = self.conn.query_encrypted(f"@TR:32,{bank:02X}\r\n", key=(0x30 + bank) & 0xFF, timeout=0.8)
            parsed = jp.parse_tr32(resp) if resp else None
            if parsed:
                _, words = parsed
                base = blk + sub * 4
                for idx, w in enumerate(words):
                    self.current_eeprom[base + idx] = w
                any_bank_ok = True
                all_sub_failed = False
                consec_sub_fail = 0
            else:
                consec_sub_fail += 1
                if consec_sub_fail >= 2:
                    break
        self.classify_all()
        entries = [r for r in self.classified_registers if blk <= r.addr < blk + 16]
        end_of_table = (b_idx > 0 and all_sub_failed)
        return entries, any_bank_ok, end_of_table

    def sweep_block(self, b_idx: int) -> Dict[str, Any]:
        """Sweep a single 16-word block and return updated registers plus abort_sweep metadata."""
        total_blocks = max(1, self.max_words // 16)
        if b_idx < 0 or b_idx >= total_blocks:
            return {"registers": [], "abort_sweep": False}
        if not getattr(self.conn, "is_open", True):
            raise IOError("Serial port disconnected during block sweep.")

        if b_idx == 0:
            self._consecutive_failed_blocks = 0
            self._any_block_succeeded = False

        if (getattr(self.conn, "_is_smart_connect", False) or getattr(self.conn, "wire_mode", None) == "smart_connect") and hasattr(self.conn, "query_encrypted"):
            entries, ok_sc, end_of_table = self._sweep_block_smart_connect(b_idx)
            if ok_sc:
                self._any_block_succeeded = True
                self._consecutive_failed_blocks = 0
            else:
                self._consecutive_failed_blocks += 1
            if end_of_table:
                return {
                    "registers": entries,
                    "abort_sweep": True,
                    "abort_reason": "Reached end of Smart Connect counter table",
                    "end_of_table": True,
                }
            if not self._any_block_succeeded and self._consecutive_failed_blocks >= 2:
                return {
                    "registers": entries,
                    "abort_sweep": True,
                    "abort_reason": "No ASCII or Smart Connect response from machine — verify probe compatibility/connection",
                }
            return {"registers": entries, "abort_sweep": False}

        blk = b_idx * 16
        blk_str = f"{blk:02X}" if self.address_width == 2 else f"{blk:04X}"
        cmd = f"RT:{blk_str}"
        try:
            ans = self.query_safe(cmd, timeout=1.5)
        except (IOError, OSError) as exc:
            if not getattr(self.conn, "is_open", True):
                raise IOError(f"Serial port disconnected at block 0x{blk_str}: {exc}") from exc
            ans = None

        block_success = False
        if ans and ans.lower().startswith("rt:"):
            raw_hex = ans[3:].strip()
            if len(raw_hex) >= 64:
                parsed_ok = True
                for i in range(16):
                    w_hex = raw_hex[i * 4: i * 4 + 4]
                    try:
                        self.current_eeprom[blk + i] = int(w_hex, 16)
                    except ValueError:
                        parsed_ok = False
                        break
                if parsed_ok:
                    block_success = True

        if not block_success:
            first_addr_str = f"{blk:02X}" if self.address_width == 2 else f"{blk:04X}"
            try:
                first_ans = self.query_safe(f"RE:{first_addr_str}", timeout=1.0)
            except (IOError, OSError) as exc:
                if not getattr(self.conn, "is_open", True):
                    raise IOError(f"Serial port disconnected at word 0x{first_addr_str}: {exc}") from exc
                first_ans = None

            if first_ans and first_ans.lower().startswith("re:"):
                try:
                    self.current_eeprom[blk] = int(first_ans[3:].strip()[:4], 16)
                except ValueError:
                    self.current_eeprom[blk] = 0x0000
                block_success = True
                for i in range(1, 16):
                    if not getattr(self.conn, "is_open", True):
                        raise IOError("Serial port disconnected during block sweep.")
                    addr = blk + i
                    addr_str = f"{addr:02X}" if self.address_width == 2 else f"{addr:04X}"
                    try:
                        w_ans = self.query_safe(f"RE:{addr_str}", timeout=1.0)
                    except (IOError, OSError) as exc:
                        if not getattr(self.conn, "is_open", True):
                            raise IOError(f"Serial port disconnected at word 0x{addr_str}: {exc}") from exc
                        w_ans = None
                    if w_ans and w_ans.lower().startswith("re:"):
                        try:
                            self.current_eeprom[addr] = int(w_ans[3:].strip()[:4], 16)
                        except ValueError:
                            self.current_eeprom[addr] = 0x0000
                    else:
                        self.current_eeprom[addr] = 0x0000
            else:
                for i in range(16):
                    self.current_eeprom[blk + i] = 0x0000

                # On block 0, if ASCII RT: + first RE: both failed, immediately try Smart Connect handshake
                if b_idx == 0 and hasattr(self.conn, "query_encrypted"):
                    sc_model = self._smart_connect_handshake()
                    if sc_model:
                        entries, ok_sc, _ = self._sweep_block_smart_connect(0)
                        if ok_sc:
                            self._any_block_succeeded = True
                            self._consecutive_failed_blocks = 0
                            return {"registers": entries, "abort_sweep": False}

        if block_success:
            self._any_block_succeeded = True
            self._consecutive_failed_blocks = 0
        else:
            self._consecutive_failed_blocks += 1

        self.classify_all()
        entries = [r for r in self.classified_registers if blk <= r.addr < blk + 16]
        if (not self._any_block_succeeded and self._consecutive_failed_blocks >= 2) or self._consecutive_failed_blocks >= 3:
            reason = (
                "No ASCII or Smart Connect response from machine — verify probe compatibility/connection"
                if not self._any_block_succeeded
                else "3 consecutive EEPROM blocks failed — aborting sweep"
            )
            return {
                "registers": entries,
                "abort_sweep": True,
                "abort_reason": reason,
            }
        return {"registers": entries, "abort_sweep": False}

    def capture_baseline(self) -> MemorySnapshot:
        """Capture current EEPROM and volatile telemetry as baseline reference."""
        hz = self.query_safe("HZ:", timeout=1.0)
        as_ans = self.query_safe("AS:", timeout=1.0)
        self.baseline_snapshot = MemorySnapshot(
            timestamp=time.time(),
            eeprom=dict(self.current_eeprom),
            gateways=dict(self.gateways),
            hz_raw=hz,
            as_raw=as_ans
        )
        self.classify_all()
        return self.baseline_snapshot

    def classify_all(self) -> List[RegisterEntry]:
        """Classify all registers according to model spec, universal, theoretical, and unknown tables."""
        custom_regs = self.model_spec.get("custom_registers", {})
        baseline = self.baseline_snapshot.eeprom if self.baseline_snapshot else self.current_eeprom

        entries: List[RegisterEntry] = []
        max_words = getattr(self, "max_words", 512)
        addr_w = getattr(self, "address_width", 4)
        for addr in range(max_words):
            val = self.current_eeprom.get(addr, 0)
            base_val = baseline.get(addr, val)
            hex_addr = f"{addr:02X}" if addr_w == 2 else f"{addr:04X}"
            hex_addr_alt = f"{addr:04X}" if addr_w == 2 else f"{addr:02X}"

            # 1. Check Model Specification custom_registers
            reg_def = custom_regs.get(hex_addr) or custom_regs.get(hex_addr_alt)
            if reg_def:
                c = reg_def
                name = c.get("name", f"Reg_0x{hex_addr}")
                # If name starts with Unmapped_0x, treat as unknown
                if name.startswith("Unmapped_0x"):
                    status = STATUS_UNKNOWN if val != 0 else STATUS_BLANK
                    category = "unmapped" if val != 0 else "blank"
                else:
                    status = c.get("status", STATUS_MAPPED)
                    category = c.get("category", "settings")

                entry = RegisterEntry(
                    addr=addr,
                    val=val,
                    status=status,
                    name=name,
                    desc=c.get("description", ""),
                    category=category,
                    unit=c.get("unit", ""),
                    baseline_val=base_val
                )
            # 2. Universal platform register
            elif addr in UNIVERSAL_REGISTERS:
                u = UNIVERSAL_REGISTERS[addr]
                entry = RegisterEntry(
                    addr=addr,
                    val=val,
                    status=STATUS_MAPPED,
                    name=u["name"],
                    desc=u["desc"],
                    category=u["category"],
                    unit=u["unit"],
                    baseline_val=base_val
                )
            # 3. Theoretical register
            elif addr in THEORETICAL_REGISTERS:
                t = THEORETICAL_REGISTERS[addr]
                entry = RegisterEntry(
                    addr=addr,
                    val=val,
                    status=STATUS_THEORETICAL,
                    name=t["name"],
                    desc=t["desc"],
                    category=t["category"],
                    unit=t["unit"],
                    baseline_val=base_val
                )
            # 4. Unknown active or blank zero
            else:
                if val != 0:
                    entry = RegisterEntry(
                        addr=addr,
                        val=val,
                        status=STATUS_UNKNOWN,
                        name=f"Unmapped_0x{hex_addr}",
                        desc=f"Model-specific active register (0x{val:04X} / {val})",
                        category="unmapped",
                        unit="",
                        baseline_val=base_val
                    )
                else:
                    entry = RegisterEntry(
                        addr=addr,
                        val=0,
                        status=STATUS_BLANK,
                        name=f"Blank_0x{hex_addr}",
                        desc="Unwritten or zero register (0x0000)",
                        category="blank",
                        unit="",
                        baseline_val=base_val
                    )

            entries.append(entry)

        self.classified_registers = entries
        return entries

    def compute_diff(self, mask_noise: bool = True) -> Dict[str, Any]:
        """
        Compare current snapshot with baseline.
        If mask_noise is enabled, suppresses known jitter offsets (e.g., volatile clock noise).
        """
        if not self.baseline_snapshot:
            self.capture_baseline()

        self.classify_all()
        changed: List[RegisterEntry] = []
        total_bit_flips = 0

        for r in self.classified_registers:
            if r.is_changed:
                changed.append(r)
                total_bit_flips += len(r.bits_flipped)

        return {
            "changed_registers": changed,
            "total_changed_words": len(changed),
            "total_bit_flips": total_bit_flips,
            "timestamp": time.time()
        }

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculate mapping coverage metrics."""
        if not self.classified_registers:
            self.classify_all()

        mapped = sum(1 for r in self.classified_registers if r.status == STATUS_MAPPED)
        theoretical = sum(1 for r in self.classified_registers if r.status == STATUS_THEORETICAL)
        unknown = sum(1 for r in self.classified_registers if r.status == STATUS_UNKNOWN)
        blank = sum(1 for r in self.classified_registers if r.status == STATUS_BLANK)
        nonzero = mapped + theoretical + unknown
        coverage_pct = (mapped / nonzero * 100.0) if nonzero > 0 else 100.0

        changed = sum(1 for r in self.classified_registers if r.is_changed)

        return {
            "total_words": getattr(self, "max_words", 512),
            "mapped": mapped,
            "theoretical": theoretical,
            "unknown": unknown,
            "blank": blank,
            "nonzero": nonzero,
            "changed": changed,
            "coverage_pct": round(coverage_pct, 1)
        }

    def map_register(
        self,
        addr: int,
        name: str,
        desc: str,
        category: str = "settings",
        unit: str = "",
        status: str = STATUS_MAPPED
    ) -> Tuple[bool, str]:
        """
        Map a register and persist immediately into docs/models/<EF>_*.json.
        Returns (success, message).
        """
        hex_addr = f"{addr:02X}" if getattr(self, "address_width", 4) == 2 else f"{addr:04X}"
        name = name.strip()
        desc = desc.strip()
        category = category.strip() or "settings"
        unit = unit.strip()

        if not name:
            return False, "Register name cannot be empty."

        if "custom_registers" not in self.model_spec:
            self.model_spec["custom_registers"] = {}

        self.model_spec["custom_registers"][hex_addr] = {
            "name": name,
            "description": desc,
            "category": category,
            "unit": unit,
            "status": status,
            "current_hex": f"0x{self.current_eeprom.get(addr, 0):04X}",
            "current_dec": self.current_eeprom.get(addr, 0),
            "last_updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        }

        # Atomically write to file
        target_path = self.spec_file_path or os.path.join(self.models_dir, f"{self.ef_code}_Model.json")
        tmp_path = target_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.model_spec, f, indent=2)
            os.replace(tmp_path, target_path)
            self.spec_file_path = target_path

            # Invalidate profiles database cache so SPECTRA main app refreshes
            profiles_db.invalidate_model_specs_cache()

            # Refresh local classifications
            self.classify_all()
            return True, f"Saved 0x{hex_addr} ({name}) to {os.path.basename(target_path)}"
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False, f"Failed to save specification: {e}"

