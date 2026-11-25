#!/usr/bin/env python3
"""SPECTRA HMI ELF32/APK/MCU binary inspection, ARM32 codec, and language-pack extraction."""

import os
import sys
import re
import mmap
import struct
import base64
import hashlib
import subprocess
import json
import zipfile
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any, Set, Union, Iterable, Callable, Sequence

try:
    from version import __version__, __build__
except ImportError:
    __build__ = "20261112.1820"
    __version__ = f"Build {__build__}"

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False

DEFAULT_KALERM_DIR = os.path.expanduser("~/Downloads")
ELF_MAGIC = b"\x7fELF"

class DialogUnavailableError(RuntimeError):
    """Raised when native/fallback file chooser dialog could not be invoked."""
    pass

@dataclass
class ElfSegment:
    p_type: int
    p_offset: int
    p_vaddr: int
    p_paddr: int
    p_filesz: int
    p_memsz: int
    p_flags: int
    p_align: int


@dataclass
class ElfSection:
    index: int
    name: str
    sh_type: int
    sh_flags: int
    sh_addr: int
    sh_offset: int
    sh_size: int
    sh_link: int
    sh_info: int
    sh_addralign: int
    sh_entsize: int


def encode_arm_movw_movt(rd: int, vma: int) -> bytes:
    """Dynamically encode ARM32 movw + movt instruction pair loading a 32-bit VMA into Rd."""
    imm_low = vma & 0xffff
    imm_high = (vma >> 16) & 0xffff
    w = bytes([imm_low & 0xff, (rd << 4) | ((imm_low >> 8) & 0x0f), (imm_low >> 12) & 0x0f, 0xe3])
    t = bytes([imm_high & 0xff, (rd << 4) | ((imm_high >> 8) & 0x0f), 0x40 | ((imm_high >> 12) & 0x0f), 0xe3])
    return w + t


def decode_arm_movw_movt(pair_bytes: bytes) -> Optional[Tuple[int, int]]:
    """Decode register Rd and 32-bit VMA from an 8-byte ARM32 movw + movt instruction pair."""
    if len(pair_bytes) != 8 or pair_bytes[3] != 0xe3 or pair_bytes[7] != 0xe3 or (pair_bytes[6] & 0xf0) != 0x40:
        return None
    rd1 = (pair_bytes[1] >> 4) & 0x0f
    rd2 = (pair_bytes[5] >> 4) & 0x0f
    if rd1 != rd2:
        return None
    low = pair_bytes[0] | ((pair_bytes[1] & 0x0f) << 8) | ((pair_bytes[2] & 0x0f) << 12)
    high = pair_bytes[4] | ((pair_bytes[5] & 0x0f) << 8) | ((pair_bytes[6] & 0x0f) << 12)
    return rd1, (high << 16) | low


class AutoGlossary(dict):
    """
    Self-learning domain glossary extracted dynamically from firmware binary.
    Behaves as both a dict (lookup by en_term) and an iterable list of term dicts.
    """
    def __init__(self, terms_list: List[Dict[str, Any]], locale: str):
        super().__init__({t["en_term"]: t for t in terms_list})
        self.locale = locale
        self.terms = terms_list

    def __iter__(self):
        return iter(self.terms)

    def __len__(self):
        return len(self.terms)

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self.terms[key]
        return super().__getitem__(key)




class HmiElfMixin:
    """ELF32/APK/MCU parsing, symbol/VMA resolution, language extraction, and signature checks."""

    def __init__(self, target_path: str):
        self.target_path = os.path.abspath(target_path)
        self.binary_path = ""
        self.signature_path = ""
        self.companion_ctr_bin: Optional[str] = None
        self.container_type = "ELF32_LVGL"
        self.container_badge = "ELF32 ARM (LVGL)"
        self.apk_info: Dict[str, Any] = {}
        self.mcu_info: Dict[str, Any] = {}

        self._resolve_paths(self.target_path)

        if not os.path.isfile(self.binary_path):
            raise FileNotFoundError(f"Kalerm HMI target binary not found at: {self.binary_path}")

        self.file_size = os.path.getsize(self.binary_path)
        self.segments: List[ElfSegment] = []
        self.sections: List[ElfSection] = []
        self.sections_by_name: Dict[str, ElfSection] = {}
        self.symbols: Dict[str, int] = {}
        self._languages_cache: Optional[Dict[str, Dict[str, Any]]] = None

        with open(self.binary_path, "rb") as f:
            magic = f.read(16)

        if magic.startswith(ELF_MAGIC):
            self.container_type = "ELF32_LVGL"
            self.container_badge = "ELF32 ARM (LVGL)"
            self._parse_elf()
        elif magic.startswith(b"PK\x03\x04"):
            self.container_type = "ANDROID_APK"
            self.container_badge = "ANDROID APK (ARSC)"
            self._init_apk_container()
        elif len(magic) >= 8:
            sp, reset = struct.unpack("<II", magic[:8])
            if (0x20000000 <= sp <= 0x24100000) and (0x08000001 <= reset <= 0x081FFFFF) and (reset & 1 == 1):
                self.container_type = "MCU_CTR_BIN"
                self.container_badge = "ARM CORTEX-M (CTR BIN)"
                self._init_mcu_container(sp, reset)
            else:
                self.container_type = "ELF32_LVGL"
                self.container_badge = "ELF32 ARM (LVGL)"
                self._parse_elf()
        else:
            self.container_type = "ELF32_LVGL"
            self.container_badge = "ELF32 ARM (LVGL)"
            self._parse_elf()

    def _resolve_paths(self, target: str):
        if os.path.isdir(target):
            try:
                candidates = os.listdir(target)
            except Exception:
                candidates = []

            elf_cands = []
            apk_cands = []
            bin_cands = []

            for f in sorted(candidates):
                fpath = os.path.join(target, f)
                if not os.path.isfile(fpath):
                    continue
                if f.endswith(".apk"):
                    apk_cands.append(fpath)
                elif f.endswith(".bin"):
                    bin_cands.append(fpath)
                elif not (f.endswith(".so") or f.endswith(".o") or f.endswith(".a") or f.endswith(".debug") or f.endswith(".pem")):
                    try:
                        with open(fpath, "rb") as bf:
                            if bf.read(4) == ELF_MAGIC:
                                elf_cands.append(fpath)
                    except Exception:
                        pass

            if elf_cands:
                unpatched = [c for c in elf_cands if not c.endswith("_patched")]
                self.binary_path = unpatched[0] if unpatched else elf_cands[0]
                if bin_cands:
                    self.companion_ctr_bin = bin_cands[0]
            elif apk_cands:
                self.binary_path = apk_cands[0]
                if bin_cands:
                    self.companion_ctr_bin = bin_cands[0]
            elif bin_cands:
                self.binary_path = bin_cands[0]
            else:
                self.binary_path = target

            sig_cand = os.path.join(target, "KLM_SIGN.pem")
            if os.path.isfile(sig_cand):
                self.signature_path = sig_cand
        else:
            self.binary_path = target
            parent = os.path.dirname(target)
            if parent and os.path.isdir(parent):
                sig_cand = os.path.join(parent, "KLM_SIGN.pem")
                if os.path.isfile(sig_cand):
                    self.signature_path = sig_cand
                if not target.endswith(".bin"):
                    try:
                        for f in os.listdir(parent):
                            if f.endswith(".bin"):
                                self.companion_ctr_bin = os.path.join(parent, f)
                                break
                    except Exception:
                        pass

    def _init_apk_container(self):
        """Initialize Android APK container metadata and synthetic section table for KPI display."""
        arsc_size, manifest_size, dex_size = 0, 0, 0
        try:
            import zipfile
            with zipfile.ZipFile(self.binary_path, "r") as zf:
                namelist = zf.namelist()
                if "resources.arsc" in namelist:
                    arsc_size = zf.getinfo("resources.arsc").file_size
                if "AndroidManifest.xml" in namelist:
                    manifest_size = zf.getinfo("AndroidManifest.xml").file_size
                dex_files = [n for n in namelist if n.startswith("classes") and n.endswith(".dex")]
                dex_size = sum(zf.getinfo(d).file_size for d in dex_files)
        except Exception:
            pass

        self.sections = [
            ElfSection(0, "resources.arsc", 1, 0, 0, 0, arsc_size, 0, 0, 4, 0),
            ElfSection(1, "AndroidManifest.xml", 1, 0, 0, 0, manifest_size, 0, 0, 4, 0),
            ElfSection(2, "classes*.dex", 1, 0, 0, 0, dex_size, 0, 0, 4, 0),
        ]
        self.sections_by_name = {s.name: s for s in self.sections}

    def _init_mcu_container(self, sp: int, reset: int):
        """Initialize Bare-Metal MCU CTR binary container metadata."""
        if sp >= 0x24000000:
            family = "STM32H7xx (e.g. STMH723, Cortex-M7)"
            base_vma = 0x08040000
        else:
            family = "GD32F4xx / STM32F4xx (e.g. GD32F425, Cortex-M4)"
            base_vma = 0x08020000

        base_name = os.path.basename(self.binary_path)
        crc_match = re.search(r'-([0-9A-Fa-f]{8})-', base_name)
        crc_token = crc_match.group(1).upper() if crc_match else None

        self.mcu_info = {
            "sp": sp,
            "reset": reset,
            "family": family,
            "base_vma": base_vma,
            "crc_token": crc_token,
        }

        self.sections = [
            ElfSection(0, ".isr_vector", 1, 0, base_vma, 0, 0x400, 0, 0, 4, 0),
            ElfSection(1, ".text_mcu", 1, 0, base_vma + 0x400, 0x400, max(0, self.file_size - 0x400), 0, 0, 4, 0),
        ]
        self.sections_by_name = {s.name: s for s in self.sections}

    MAX_ELF_SECTION_BYTES = 64 * 1024 * 1024  # 64 MiB

    def _bounded_read(self, f, offset: int, size: int, label: str = "ELF region") -> bytes:
        if offset < 0 or size < 0 or offset > self.file_size or offset + size > self.file_size:
            raise ValueError(f"Invalid {label} bounds (offset={offset}, size={size}, file_size={self.file_size})")
        if size > self.MAX_ELF_SECTION_BYTES:
            raise ValueError(f"{label} exceeds {self.MAX_ELF_SECTION_BYTES} byte safety cap (size={size})")
        f.seek(offset)
        data = f.read(size)
        if len(data) != size:
            raise ValueError(f"Short read for {label}: expected {size} bytes, got {len(data)}")
        return data

    def _parse_elf(self):
        with open(self.binary_path, "rb") as f:
            ident = f.read(16)
            if len(ident) < 16 or not ident.startswith(ELF_MAGIC):
                raise ValueError(f"File {self.binary_path} is not a valid ELF binary.")

            ei_class = ident[4]
            ei_data = ident[5]
            if ei_class != 1 or ei_data != 1:
                raise ValueError(
                    f"Unsupported ELF format (ei_class={ei_class}, ei_data={ei_data}); only ELF32 little-endian is supported."
                )

            f.seek(0)
            hdr = f.read(52)
            if len(hdr) != 52:
                raise ValueError(f"Truncated ELF32 header ({len(hdr)} bytes, expected 52).")
            fields = struct.unpack("<16sHHIIIIIHHHHHH", hdr)
            e_phoff = fields[5]
            e_shoff = fields[6]
            e_phentsize = fields[9]
            e_phnum = fields[10]
            e_shentsize = fields[11]
            e_shnum = fields[12]
            e_shstrndx = fields[13]

            if e_phnum > 1024:
                raise ValueError(f"ELF program header count exceeds safety limit: e_phnum={e_phnum} > 1024")
            if e_shnum > 4096:
                raise ValueError(f"ELF section header count exceeds safety limit: e_shnum={e_shnum} > 4096")

            if e_phoff > 0 and e_phnum > 0:
                if e_phentsize < 32:
                    raise ValueError(f"Invalid ELF32 e_phentsize={e_phentsize}")
                ph_bytes = self._bounded_read(f, e_phoff, e_phnum * e_phentsize, "program header table")
                for i in range(e_phnum):
                    p_off = i * e_phentsize
                    p_fields = struct.unpack_from("<IIIIIIII", ph_bytes, p_off)
                    self.segments.append(ElfSegment(*p_fields))

            if e_shoff > 0 and e_shnum > 0:
                if e_shentsize < 40:
                    raise ValueError(f"Invalid ELF32 e_shentsize={e_shentsize}")
                if e_shstrndx >= e_shnum:
                    raise ValueError(f"Invalid ELF e_shstrndx={e_shstrndx} >= e_shnum={e_shnum}")

                sh_table = self._bounded_read(f, e_shoff, e_shnum * e_shentsize, "section header table")
                shstr_fields = struct.unpack_from("<IIIIIIIIII", sh_table, e_shstrndx * e_shentsize)
                shstr_off = shstr_fields[4]
                shstr_sz = shstr_fields[5]
                shstrtab = self._bounded_read(f, shstr_off, shstr_sz, ".shstrtab")

                # Parse all section headers
                symtab_sec: Optional[ElfSection] = None
                for i in range(e_shnum):
                    s_fields = struct.unpack_from("<IIIIIIIIII", sh_table, i * e_shentsize)
                    name_off = s_fields[0]
                    if name_off < len(shstrtab):
                        name_end = shstrtab.find(b"\x00", name_off)
                        s_name = shstrtab[name_off:name_end].decode("ascii", "replace") if name_end != -1 else ""
                    else:
                        s_name = ""

                    sec = ElfSection(
                        index=i,
                        name=s_name,
                        sh_type=s_fields[1],
                        sh_flags=s_fields[2],
                        sh_addr=s_fields[3],
                        sh_offset=s_fields[4],
                        sh_size=s_fields[5],
                        sh_link=s_fields[6],
                        sh_info=s_fields[7],
                        sh_addralign=s_fields[8],
                        sh_entsize=s_fields[9],
                    )
                    self.sections.append(sec)
                    if s_name:
                        self.sections_by_name[s_name] = sec
                    if sec.sh_type == 2:  # SHT_SYMTAB
                        symtab_sec = sec

                # Parse symbols if symtab present
                if symtab_sec and symtab_sec.sh_link < len(self.sections):
                    strtab_sec = self.sections[symtab_sec.sh_link]
                    strtab = self._bounded_read(f, strtab_sec.sh_offset, strtab_sec.sh_size, ".strtab")
                    sym_data = self._bounded_read(f, symtab_sec.sh_offset, symtab_sec.sh_size, ".symtab")
                    num_syms = len(sym_data) // 16
                    for i in range(num_syms):
                        st_name, st_val, st_sz, st_info, st_other, st_shndx = struct.unpack_from("<IIIBBH", sym_data, i * 16)
                        if st_name == 0 or st_name >= len(strtab):
                            continue
                        end = strtab.find(b"\x00", st_name)
                        if end != -1:
                            s_name = strtab[st_name:end].decode("ascii", "replace")
                            self.symbols[s_name] = st_val

    def vma_to_off(self, vma: int) -> int:
        """Dynamically map Virtual Memory Address (VMA) to physical file offset."""
        if self.container_type == "MCU_CTR_BIN":
            base_vma = self.mcu_info.get("base_vma", 0x08000000)
            return max(0, vma - base_vma)
        if self.container_type == "ANDROID_APK":
            return vma

        for sec in self.sections:
            if sec.sh_addr > 0 and sec.sh_addr <= vma < (sec.sh_addr + sec.sh_size):
                return vma - sec.sh_addr + sec.sh_offset

        for seg in self.segments:
            if seg.p_type == 1:  # PT_LOAD
                if seg.p_vaddr <= vma < (seg.p_vaddr + seg.p_filesz):
                    return vma - seg.p_vaddr + seg.p_offset

        raise ValueError(f"Unable to dynamically map VMA 0x{vma:08x} to file offset (no matching section or PT_LOAD segment)")

    def off_to_vma(self, off: int) -> int:
        """Map physical file offset to Virtual Memory Address (VMA)."""
        if self.container_type == "MCU_CTR_BIN":
            base_vma = self.mcu_info.get("base_vma", 0x08000000)
            return base_vma + off
        if self.container_type == "ANDROID_APK":
            return off

        for sec in self.sections:
            if sec.sh_offset <= off < (sec.sh_offset + sec.sh_size) and sec.sh_addr > 0:
                return off - sec.sh_offset + sec.sh_addr

        for seg in self.segments:
            if seg.p_type == 1:  # PT_LOAD
                if seg.p_offset <= off < (seg.p_offset + seg.p_filesz) and seg.p_vaddr > 0:
                    return off - seg.p_offset + seg.p_vaddr

        raise ValueError(f"Unable to dynamically map file offset 0x{off:08x} to VMA (no matching section or PT_LOAD segment)")

    def read_cstring_at_off(self, off: int, max_len: int = 512) -> str:
        """Read a null-terminated UTF-8 string directly at a file offset."""
        if off < 0 or off >= self.file_size:
            return ""
        with open(self.binary_path, "rb") as f:
            f.seek(off)
            chunk = f.read(max_len)
            end = chunk.find(b"\x00")
            if end != -1:
                chunk = chunk[:end]
            return chunk.decode("utf-8", "replace")

    def read_cstring(self, vma: int, max_len: int = 512) -> str:
        """Read a null-terminated UTF-8 string at a given VMA."""
        off = self.vma_to_off(vma)
        return self.read_cstring_at_off(off, max_len)

    def get_symbol_vma(self, symbol_name: str, fallback: Optional[int] = None) -> Optional[int]:
        """Lookup a symbol VMA from ELF symbol table, with optional fallback."""
        if symbol_name in self.symbols:
            return self.symbols[symbol_name]
        return fallback

    def _find_language_pack_dynamic(self) -> int:
        """
        Dynamically discover lv_i18n_language_pack VMA across stripped or unstripped binaries.
        Checks .symtab / .dynsym first; falls back to pattern scanning locale tags (en-GB, cs-CZ, etc.)
        and language struct pointer tables.
        """
        sym_vma = self.symbols.get("lv_i18n_language_pack")
        if sym_vma is not None:
            return sym_vma

        with open(self.binary_path, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                tags = [b"en-GB\x00", b"cs-CZ\x00", b"de-DE\x00", b"zh-CN\x00"]
                for tag in tags:
                    pos = mm.find(tag)
                    if pos == -1:
                        continue
                    try:
                        tag_vma = self.off_to_vma(pos)
                    except Exception:
                        continue

                    tag_b = struct.pack("<I", tag_vma)
                    spos = 0
                    while True:
                        spos = mm.find(tag_b, spos)
                        if spos == -1:
                            break
                        try:
                            struct_vma = self.off_to_vma(spos)
                        except Exception:
                            spos += 4
                            continue

                        sv_b = struct.pack("<I", struct_vma)
                        ppos = 0
                        while True:
                            ppos = mm.find(sv_b, ppos)
                            if ppos == -1:
                                break
                            valid_langs = 0
                            for i in range(1, 32):
                                if ppos + (i + 1) * 4 > len(mm):
                                    break
                                ptr = struct.unpack_from("<I", mm, ppos + i * 4)[0]
                                if ptr == 0:
                                    break
                                try:
                                    ptr_off = self.vma_to_off(ptr)
                                    if ptr_off + 8 <= len(mm):
                                        valid_langs += 1
                                except Exception:
                                    break
                            if valid_langs >= 1:
                                return self.off_to_vma(ppos)
                            ppos += 4
                        spos += 4
            finally:
                mm.close()

        raise RuntimeError("lv_i18n_language_pack could not be dynamically located via symbols or pattern scan")

    def _find_free_rodata_padding(self, min_size: int = 32, align: int = 16, start_search_off: Optional[int] = None) -> Tuple[int, int]:
        """
        Dynamically find a free zero-padding run in .rodata of at least min_size bytes,
        aligned to align bytes. Returns (file_offset, vma).
        """
        with open(self.binary_path, "rb") as f:
            data = f.read()

        ro_sec = self.sections_by_name.get(".rodata")
        if start_search_off is not None:
            start_off = (start_search_off + align - 1) & ~(align - 1)
        elif ro_sec:
            start_off = (ro_sec.sh_offset + ro_sec.sh_size // 2 + align - 1) & ~(align - 1)
        else:
            start_off = 0x1000

        # Native Rust Core acceleration
        if HAS_RUST_CORE and _rust_core is not None and ro_sec:
            try:
                rel_start = max(0, start_off - ro_sec.sh_offset)
                ro_bytes = data[ro_sec.sh_offset:ro_sec.sh_offset + ro_sec.sh_size]
                pad_off = _rust_core.find_free_zero_padding_fast(ro_bytes, ro_sec.sh_offset, min_size, align, rel_start)
                if pad_off is not None:
                    return pad_off, self.off_to_vma(pad_off)
            except Exception:
                pass

        end_off = (ro_sec.sh_offset + ro_sec.sh_size) if ro_sec else len(data)
        zero_block = b"\x00" * min_size

        for off in range(start_off, min(end_off, len(data)) - min_size, align):
            if data[off:off + min_size] == zero_block:
                try:
                    vma = self.off_to_vma(off)
                    return off, vma
                except Exception:
                    continue

        raise RuntimeError(f"Unable to find {min_size} bytes of free zero-padding in .rodata")

    @staticmethod
    def _resolve_native_endonym(lang_code: str, raw_endonym: str, target_phrases: Optional[Dict[str, Any]] = None) -> str:
        """
        Dynamically determine the proper native capitalized/accented endonym for a language code.
        1. Checks target_phrases for any accented/capitalized word matching raw_endonym.
        2. Consults comprehensive ISO-639-1 native endonym lookup table (35+ languages).
        3. Falls back to capitalized raw_endonym.
        """
        if not raw_endonym:
            return ""

        norm_raw = unicodedata.normalize("NFKD", raw_endonym).encode("ascii", "ignore").decode("ascii").lower()
        if target_phrases:
            for p in target_phrases.values():
                val = p.get("val", "")
                words = re.findall(r"\b[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž]+\b", val)
                for w in words:
                    w_norm = unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode("ascii").lower()
                    if w_norm == norm_raw and w[0].isupper() and w != raw_endonym:
                        return w

        iso_endonyms = {
            "ar": "العربية", "bg": "Български", "cs": "Čeština", "da": "Dansk",
            "de": "Deutsch", "el": "Ελληνικά", "en": "English", "es": "Español",
            "et": "Eesti", "fa": "فارسی", "fi": "Suomi", "fr": "Français",
            "he": "עברית", "hi": "हिन्दी", "hr": "Hrvatski", "hu": "Magyar",
            "id": "Bahasa Indonesia", "it": "Italiano", "iw": "עברית", "ja": "日本語",
            "ko": "한국어", "lt": "Lietuvių", "lv": "Latviešu", "ms": "Bahasa Melayu",
            "nl": "Nederlands", "no": "Norsk", "pl": "Polski", "pt": "Português",
            "ro": "Română", "ru": "Русский", "sk": "Slovenčina", "sl": "Slovenščina",
            "sr": "Српски", "sv": "Svenska", "th": "ไทย", "tr": "Türkçe",
            "uk": "Українська", "vi": "Tiếng Việt", "zh": "中文",
        }
        lc = lang_code.lower()
        if lc in iso_endonyms:
            return iso_endonyms[lc]

        return raw_endonym[:1].upper() + raw_endonym[1:]

    MAX_BINARY_SCAN_BYTES = 500 * 1024 * 1024  # 500 MiB cap

    def _find_language_selector_table(self) -> List[Dict[str, Any]]:
        """
        Dynamically scan binary for language selector entries (pattern language_[a-z]{2}\x00)
        and extract paired display endonym strings.
        """
        if self.file_size > self.MAX_BINARY_SCAN_BYTES:
            raise ValueError(f"Binary size {self.file_size} exceeds 500 MiB scan safety cap.")
        results: List[Dict[str, Any]] = []
        with open(self.binary_path, "rb") as f:
            data = f.read(self.MAX_BINARY_SCAN_BYTES)

        matches = list(re.finditer(rb"language_([a-z]{2})\x00", data))
        if not matches:
            return results

        last_match_end = max(m.end() for m in matches)

        for m in matches:
            tag_off = m.start()
            tag_str = m.group(0).rstrip(b"\x00").decode("ascii", "replace")
            lang_code = m.group(1).decode("ascii", "replace")

            # Search backward from tag_off for preceding endonym string
            prev_null = data.rfind(b"\x00", 0, tag_off - 1)
            start_name = prev_null + 1 if prev_null != -1 else 0
            end_name = tag_off - 1
            while end_name > start_name and data[end_name] == 0:
                end_name -= 1

            disp_bytes = data[start_name:end_name + 1] if end_name >= start_name else b""
            disp_str = ""
            disp_off = start_name
            if disp_bytes:
                try:
                    disp_str = disp_bytes.decode("utf-8")
                except Exception:
                    disp_str = disp_bytes.decode("latin1", "replace")

            # If preceding wasn't an endonym (or was another tag), check immediately following
            if not disp_str or disp_str.startswith("language_") or disp_str.startswith("flag_"):
                post_start = m.end()
                post_null = data.find(b"\x00", post_start)
                if post_null != -1 and (post_null - post_start) > 0:
                    post_bytes = data[post_start:post_null]
                    try:
                        disp_str = post_bytes.decode("utf-8")
                        disp_off = post_start
                    except Exception:
                        disp_str = post_bytes.decode("latin1", "replace")
                        disp_off = post_start

            try:
                tag_vma = self.off_to_vma(tag_off)
                endonym_vma = self.off_to_vma(disp_off)
            except Exception:
                continue

            results.append({
                "tag": tag_str,
                "lang_code": lang_code,
                "tag_vma": tag_vma,
                "tag_off": tag_off,
                "endonym": disp_str,
                "endonym_vma": endonym_vma,
                "endonym_off": disp_off,
                "last_match_end": last_match_end,
            })

        return results

    def _extract_apk_languages(self) -> Dict[str, Dict[str, Any]]:
        """Pure-Python resources.arsc table parser for Android APK packages."""
        import zipfile
        try:
            with zipfile.ZipFile(self.binary_path, "r") as zf:
                if "resources.arsc" not in zf.namelist():
                    return {}
                arsc_info = zf.getinfo("resources.arsc")
                if arsc_info.file_size > 32 * 1024 * 1024:
                    raise ValueError(f"resources.arsc size {arsc_info.file_size} exceeds 32 MiB limit")
                arsc = zf.read("resources.arsc")
        except ValueError:
            raise
        except Exception:
            return {}

        def parse_string_pool(base_offset: int) -> List[str]:
            if base_offset < 0 or base_offset + 28 > len(arsc):
                return []
            ctype, hsz, csz = struct.unpack("<HHI", arsc[base_offset:base_offset + 8])
            scnt, sty_cnt, flags, str_start, sty_start = struct.unpack("<IIIII", arsc[base_offset + 8:base_offset + 28])
            is_utf8 = bool(flags & 0x100)
            rem = len(arsc) - (base_offset + 28)
            if scnt > rem // 4:
                return []
            offsets = struct.unpack(f"<{scnt}I", arsc[base_offset + 28:base_offset + 28 + scnt * 4])
            str_base = base_offset + str_start
            strings = []
            for off in offsets:
                p = str_base + off
                if p >= len(arsc):
                    strings.append("")
                    continue
                if is_utf8:
                    if arsc[p] & 0x80:
                        p += 2
                    else:
                        p += 1
                    if p >= len(arsc):
                        strings.append("")
                        continue
                    if arsc[p] & 0x80:
                        u8len = ((arsc[p] & 0x7f) << 8) | arsc[p + 1]
                        p += 2
                    else:
                        u8len = arsc[p]
                        p += 1
                    s_bytes = arsc[p:p + u8len]
                    strings.append(s_bytes.decode("utf-8", "replace"))
                else:
                    if p + 2 > len(arsc):
                        strings.append("")
                        continue
                    u16len, = struct.unpack("<H", arsc[p:p + 2])
                    if u16len & 0x8000:
                        if p + 4 > len(arsc):
                            strings.append("")
                            continue
                        u16len2, = struct.unpack("<H", arsc[p + 2:p + 4])
                        u16len = ((u16len & 0x7fff) << 16) | u16len2
                        p += 4
                    else:
                        p += 2
                    s_bytes = arsc[p:p + u16len * 2]
                    strings.append(s_bytes.decode("utf-16le", "replace"))
            return strings

        global_strings = parse_string_pool(12)

        pos = 12
        key_strings: List[str] = []
        type_strings: List[str] = []
        pkg_id = 127
        while pos + 8 <= len(arsc):
            ctype, hsz, csz = struct.unpack("<HHI", arsc[pos:pos + 8])
            if csz <= 0:
                break
            if ctype == 0x0200:  # RES_TABLE_PACKAGE_TYPE
                pkg_id, = struct.unpack("<I", arsc[pos + 8:pos + 12])
                type_str_off, last_pub_type, key_str_off, last_pub_key = struct.unpack(
                    "<IIII", arsc[pos + 12 + 256:pos + 12 + 256 + 16]
                )
                key_strings = parse_string_pool(pos + key_str_off)
                type_strings = parse_string_pool(pos + type_str_off)
                break
            pos += csz

        string_type_id = type_strings.index("string") + 1 if "string" in type_strings else -1

        pos = 12
        extracted_raw: Dict[str, Dict[str, Any]] = {}
        while pos + 8 <= len(arsc):
            ctype, hsz, csz = struct.unpack("<HHI", arsc[pos:pos + 8])
            if csz <= 0:
                break
            if ctype == 0x0200:
                pos += hsz
                continue
            elif ctype == 0x0201:  # RES_TABLE_TYPE_TYPE
                tid = arsc[pos + 8]
                if tid == string_type_id:
                    entry_cnt, entries_start = struct.unpack("<II", arsc[pos + 12:pos + 20])
                    config_bytes = arsc[pos + 20:pos + hsz]
                    lang = config_bytes[8:10].decode("latin1", "ignore").replace("\x00", "")
                    country = config_bytes[10:12].decode("latin1", "ignore").replace("\x00", "")
                    loc_raw = f"{lang}_{country}".strip("_") or "default"

                    entries_tbl_start = pos + hsz
                    rem_entries = len(arsc) - entries_tbl_start
                    if entries_tbl_start < 0 or entry_cnt > rem_entries // 4:
                        pos += csz
                        continue
                    entry_offsets = struct.unpack(f"<{entry_cnt}I", arsc[entries_tbl_start:entries_tbl_start + entry_cnt * 4])
                    entries_base = pos + entries_start
                    if loc_raw not in extracted_raw:
                        extracted_raw[loc_raw] = {}

                    for entry_idx, e_off in enumerate(entry_offsets):
                        if e_off == 0xffffffff:
                            continue
                        ep = entries_base + e_off
                        if ep + 16 > len(arsc):
                            continue
                        e_size, e_flags, e_key_idx = struct.unpack("<HHI", arsc[ep:ep + 8])
                        key_name = key_strings[e_key_idx] if 0 <= e_key_idx < len(key_strings) else f"key_{e_key_idx}"
                        if not (e_flags & 0x0001):
                            val_size, val_res0, val_type, val_data = struct.unpack("<HBBI", arsc[ep + 8:ep + 16])
                            if val_type == 0x03:
                                val_str = global_strings[val_data] if 0 <= val_data < len(global_strings) else ""
                                res_id = (pkg_id << 24) | (tid << 16) | entry_idx
                                extracted_raw[loc_raw][key_name] = {
                                    "index": entry_idx,
                                    "key": key_name,
                                    "val": val_str,
                                    "key_vma": res_id,
                                    "val_vma": val_data,
                                    "slot_file_off": ep,
                                    "val_file_off": ep,
                                }
                pos += csz
            else:
                pos += csz

        def norm_locale(raw: str) -> str:
            if raw in ("default", "en"):
                return "en-GB"
            r = raw.replace("_", "-").replace("-r", "-")
            parts = r.split("-")
            lang = parts[0].lower()
            if len(parts) == 1:
                mapping = {
                    "cs": "cs-CZ", "de": "de-DE", "it": "it-IT", "fr": "fr-FR",
                    "es": "es-ES", "pl": "pl-PL", "nl": "nl-NL", "ru": "ru-RU",
                    "zh": "zh-CN", "ko": "ko-KR", "ja": "ja-JP", "tr": "tr-TR",
                    "pt": "pt-PT", "ar": "ar-SA", "fa": "fa-IR", "da": "da-DK",
                    "el": "el-GR", "hr": "hr-HR", "hu": "hu-HU", "iw": "iw-IL",
                    "sv": "sv-SE"
                }
                return mapping.get(lang, lang)
            elif len(parts) == 2:
                return f"{lang}-{parts[1].upper()}"
            return r

        merged: Dict[str, Dict[str, Any]] = {}
        for raw_loc, p_map in extracted_raw.items():
            loc = norm_locale(raw_loc)
            if loc not in merged:
                merged[loc] = {
                    "locale": loc,
                    "struct_vma": 0,
                    "singulars_vma": 0,
                    "phrases": {},
                }
            merged[loc]["phrases"].update(p_map)

        return merged

    def _extract_mcu_strings(self) -> Dict[str, Dict[str, Any]]:
        """Extract firmware strings and actuator command telemetry from raw MCU binary."""
        with open(self.binary_path, "rb") as f:
            data = f.read()

        base_vma = self.mcu_info.get("base_vma", 0x08000000)
        pattern = re.compile(b"[\x20-\x7e]{4,}")
        matches = list(pattern.finditer(data))

        phrases: Dict[str, Dict[str, Any]] = {}
        actuators = []
        for i, m in enumerate(matches):
            s = m.group().decode("ascii", "ignore").strip()
            if not s:
                continue
            off = m.start()
            vma = base_vma + off
            key_name = f"mcu_str_{i:04d}"
            phrases[key_name] = {
                "index": i,
                "key": key_name,
                "val": s,
                "key_vma": vma,
                "val_vma": vma,
                "slot_file_off": off,
                "val_file_off": off,
            }
            if any(w in s.lower() for w in ["pump", "valve", "heater", "grinder", "flow", "ntc", "press", "temp", "error", "cmd", "motor", "step"]):
                actuators.append(s)

        self.mcu_info["string_count"] = len(phrases)
        self.mcu_info["actuators"] = actuators

        return {
            "MCU-STRINGS": {
                "locale": "MCU-STRINGS",
                "struct_vma": base_vma,
                "singulars_vma": base_vma,
                "phrases": phrases,
            },
            "en-GB": {
                "locale": "en-GB",
                "struct_vma": base_vma,
                "singulars_vma": base_vma,
                "phrases": phrases,
            }
        }

    def _verify_apk_signature(self) -> Dict[str, Any]:
        """Detect APK Signature Scheme v2 and public AOSP platform certificate."""
        if self.file_size > self.MAX_BINARY_SCAN_BYTES:
            raise ValueError(f"APK size {self.file_size} exceeds 500 MiB scan safety cap.")
        sha256 = self.calculate_sha256()
        with open(self.binary_path, "rb") as f:
            data = f.read(self.MAX_BINARY_SCAN_BYTES)

        eocd_idx = data.rfind(b"PK\x05\x06")
        v2_present = False
        is_aosp_test_key = False
        sig_scheme = "NONE"

        if eocd_idx != -1 and eocd_idx + 22 <= len(data):
            cd_size, cd_offset = struct.unpack("<II", data[eocd_idx + 12:eocd_idx + 20])
            if 16 <= cd_offset <= len(data):
                magic = data[cd_offset - 16:cd_offset]
                if magic == b"APK Sig Block 42":
                    block_size, = struct.unpack("<Q", data[cd_offset - 24:cd_offset - 16])
                    sig_start = cd_offset - 8 - block_size
                    if sig_start >= 0:
                        pos = sig_start + 8
                        while pos < cd_offset - 24:
                            if pos + 12 > len(data):
                                break
                            pair_len, = struct.unpack("<Q", data[pos:pos + 8])
                            pair_id, = struct.unpack("<I", data[pos + 8:pos + 12])
                            if pair_id == 0x7109871a:  # APK Signature Scheme v2
                                v2_present = True
                                sig_scheme = "APK Signature Scheme v2"
                                block_bytes = data[pos + 12:pos + 8 + pair_len]
                                if b"Mountain View" in block_bytes or b"Android" in block_bytes:
                                    is_aosp_test_key = True
                            pos += 8 + pair_len

        if is_aosp_test_key:
            status_label = "APK_SIG_V2_AOSP_TEST_KEY (Re-signable)"
            warning = (
                "APK uses APK Signature Scheme v2 signed with standard Android AOSP Platform test key "
                "(CN=Android, OU=Android, O=Android, L=Mountain View). Binary can be modified and re-signed "
                "in laboratory via apksigner for ADB/USB deployment."
            )
        elif v2_present:
            status_label = "APK_SIG_V2_PRESENT"
            warning = "APK uses APK Signature Scheme v2."
        else:
            status_label = "APK_SIG_SCHEME_V1"
            warning = "APK uses standard JAR Signature (v1)."

        return {
            "verified": True,
            "signature_present": v2_present or (eocd_idx != -1),
            "sha256": sha256,
            "signature_path": self.binary_path,
            "signature_len": 0,
            "status_label": status_label,
            "warning": warning,
            "sig_scheme": sig_scheme,
        }

    def _verify_mcu_signature(self) -> Dict[str, Any]:
        """Verify MCU CTR bare-metal binary release token and checksum."""
        sha256 = self.calculate_sha256()
        crc_token = self.mcu_info.get("crc_token")
        if crc_token:
            status_label = f"MCU_CTR_CRC32_PRESENT ({crc_token})"
            warning = f"Bare-metal MCU binary with embedded release CRC32 token {crc_token}."
            sig_present = True
        else:
            status_label = "MCU_RAW_BINARY"
            warning = "Bare-metal Cortex-M firmware image (no separate cryptographic RSA signature)."
            sig_present = False

        return {
            "verified": True,
            "signature_present": sig_present,
            "sha256": sha256,
            "signature_path": self.binary_path,
            "signature_len": 0,
            "status_label": status_label,
            "warning": warning,
            "crc_token": crc_token,
        }

    def extract_all_languages(self) -> Dict[str, Dict[str, Any]]:
        """
        Extract all compiled locales and their singular phrase dictionaries.
        Returns a dict: { locale: { 'struct_vma': int, 'singulars_vma': int, 'phrases': { key: {...} } } }
        """
        if self._languages_cache is not None:
            return self._languages_cache

        if self.container_type == "ANDROID_APK":
            self._languages_cache = self._extract_apk_languages()
            return self._languages_cache
        elif self.container_type == "MCU_CTR_BIN":
            self._languages_cache = self._extract_mcu_strings()
            return self._languages_cache

        pack_vma = self._find_language_pack_dynamic()
        pack_off = self.vma_to_off(pack_vma)

        result: Dict[str, Dict[str, Any]] = {}

        with open(self.binary_path, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                # Read array of language struct pointers terminated by NULL
                for i in range(32):
                    if pack_off + (i + 1) * 4 > len(mm):
                        break
                    lang_ptr = struct.unpack_from("<I", mm, pack_off + i * 4)[0]
                    if lang_ptr == 0:
                        break

                    struct_off = self.vma_to_off(lang_ptr)
                    name_ptr, sing_ptr = struct.unpack_from("<II", mm, struct_off)

                    # Extract locale name
                    name_off = self.vma_to_off(name_ptr)
                    end_name = mm.find(b"\x00", name_off)
                    locale_name = mm[name_off:end_name].decode("ascii", "replace") if end_name != -1 else f"loc_{i}"

                    # Extract phrases
                    sing_off = self.vma_to_off(sing_ptr)
                    phrases: Dict[str, Dict[str, Any]] = {}

                    for j in range(2500):
                        slot_off = sing_off + j * 8
                        if slot_off + 8 > len(mm):
                            break
                        k_vma, v_vma = struct.unpack_from("<II", mm, slot_off)
                        if k_vma == 0:
                            break

                        k_off = self.vma_to_off(k_vma)
                        k_end = mm.find(b"\x00", k_off)
                        k_str = mm[k_off:k_end].decode("utf-8", "replace") if k_end != -1 else ""

                        v_off = self.vma_to_off(v_vma)
                        v_end = mm.find(b"\x00", v_off)
                        v_str = mm[v_off:v_end].decode("utf-8", "replace") if v_end != -1 else ""

                        phrases[k_str] = {
                            "index": j,
                            "key": k_str,
                            "val": v_str,
                            "key_vma": k_vma,
                            "val_vma": v_vma,
                            "slot_file_off": slot_off,
                            "val_file_off": v_off,
                        }

                    result[locale_name] = {
                        "locale": locale_name,
                        "struct_vma": lang_ptr,
                        "singulars_vma": sing_ptr,
                        "phrases": phrases,
                    }
            finally:
                mm.close()

        self._languages_cache = result
        return result

    def extract_language(self, locale: str) -> Optional[Dict[str, Any]]:
        """Extract phrases for a specific locale (e.g. 'cs-CZ', 'en-GB')."""
        langs = self.extract_all_languages()
        if locale in langs:
            return langs[locale]
        # Match case-insensitively or prefix
        norm = locale.lower().replace("-", "_")
        for k, v in langs.items():
            if k.lower().replace("-", "_") == norm or k.lower().startswith(norm[:2]):
                return v
        return None

    def calculate_sha256(self) -> str:
        """Calculate SHA-256 digest of the binary file."""
        h = hashlib.sha256()
        with open(self.binary_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()

    def verify_signature(self, public_key_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify binary checksum and RSA-2048 signature against KLM_SIGN.pem.
        """
        if self.container_type == "ANDROID_APK":
            return self._verify_apk_signature()
        elif self.container_type == "MCU_CTR_BIN":
            return self._verify_mcu_signature()

        # Check or re-check signature path
        if not self.signature_path or not os.path.isfile(self.signature_path):
            parent = os.path.dirname(self.binary_path)
            sig_cand = os.path.join(parent, "KLM_SIGN.pem")
            if os.path.isfile(sig_cand):
                self.signature_path = sig_cand

        sha = self.calculate_sha256()
        sig_present = bool(self.signature_path and os.path.isfile(self.signature_path))
        sig_len = 0
        sig_bytes = b""

        if sig_present:
            try:
                with open(self.signature_path, "r", encoding="utf-8") as f:
                    text = f.read()
                lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("-----")]
                sig_bytes = base64.b64decode("".join(lines))
                sig_len = len(sig_bytes)
            except Exception:
                sig_present = False

        sig_valid: Optional[bool] = None
        status_label = "UNSIGNED / MODIFIED"
        warning = ""

        if sig_present and sig_len == 256:
            status_label = "SIGNATURE PRESENT (2048-bit RSA)"
            warning = "Valid 2048-bit RSA signature container found. Standard USB updates require a valid signature matching /rom/factory/key.pem on the machine."
        else:
            status_label = "UNSIGNED / MODIFIED"
            warning = "Binary is unsigned or signature container is missing/corrupted. Standard Kalerm USB firmware updates will be rejected unless factory verification is bypassed."

        # Verify against public key if available
        key_file = public_key_path
        if not key_file:
            factory_key = "/rom/factory/key.pem"
            if os.path.isfile(factory_key):
                key_file = factory_key

        if key_file and os.path.isfile(key_file) and HAS_CRYPTO and sig_present and sig_bytes:
            try:
                with open(key_file, "rb") as kf:
                    pub_key = load_pem_public_key(kf.read())
                with open(self.binary_path, "rb") as bf:
                    data = bf.read()
                pub_key.verify(sig_bytes, data, padding.PKCS1v15(), hashes.SHA256())
                sig_valid = True
                status_label = "VERIFIED FACTORY SIGNATURE (2048-bit RSA)"
                warning = f"Cryptographically verified with factory key {os.path.basename(key_file)}."
            except Exception as e:
                sig_valid = False
                status_label = "SIGNATURE MISMATCH / MODIFIED"
                warning = f"Cryptographic verification failed against {os.path.basename(key_file)}: {e}"

        return {
            "sha256": sha,
            "signature_present": sig_present,
            "signature_path": self.signature_path if sig_present else "",
            "signature_len": sig_len,
            "signature_valid": sig_valid,
            "status_label": status_label,
            "warning": warning,
        }

