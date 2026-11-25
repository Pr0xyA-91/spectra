#!/usr/bin/env python3
"""
Unit and Integration Tests for SPECTRA HMI & Firmware Inspector / Auditor.
Part of SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics.
"""

import os
import sys
import shutil
import struct
import base64
import json
import unittest
import tempfile
from unittest.mock import patch, MagicMock
from typing import Tuple, List, Optional, Dict

# Ensure project root is in path
from hmi_inspector import (
    KalermHmiInspector,
    HAS_GTK,
    DEFAULT_KALERM_DIR,
    encode_arm_movw_movt,
)

if HAS_GTK:
    from hmi_inspector import HmiInspectorDialog


def create_synthetic_elf_binary(
    extra_cs_entries: Optional[List[Tuple[str, str]]] = None,
    extra_en_entries: Optional[List[Tuple[str, str]]] = None,
) -> bytes:
    """
    Constructs a minimal, syntactically valid ELF32 ARM binary fixture
    with .text, .rodata, .data, .symtab, .strtab, and .shstrtab sections,
    embedding an lv_i18n language pack and singular tables with the 4 target bugs.
    """
    buf = bytearray(0x50000)

    # Shstrtab
    shstr = b"\x00.text\x00.rodata\x00.data\x00.symtab\x00.strtab\x00.shstrtab\x00"
    shstr_off = 0x40000
    buf[shstr_off:shstr_off + len(shstr)] = shstr

    # String helper in .rodata
    ro_off = 0x1000
    ro_vma_base = 0x018aba28

    def add_ro_str(s: str) -> int:
        nonlocal ro_off
        start = ro_off
        b = s.encode("utf-8") + b"\x00"
        buf[start:start + len(b)] = b
        ro_off += len(b)
        while ro_off % 4 != 0:
            ro_off += 1
        return ro_vma_base + (start - 0x1000)

    # Locale names
    v_en = add_ro_str("en-GB")
    v_cs = add_ro_str("cs-CZ")
    v_it = add_ro_str("it-IT")

    # Translation keys
    k_milk_sys = add_ro_str("common_milk_frother_system_rinse")
    k_milk_tube = add_ro_str("common_outside_milk_tube_rinse")
    k_milk_sys_lf = add_ro_str("common_milk_frother_system_rinse_lf")
    k_milk_tube_lf = add_ro_str("common_outside_milk_tube_rinse_lf")
    k_temp = add_ro_str("Drink_Temp_High")
    k_temp_low = add_ro_str("Drink_Temp_Low")
    k_screen = add_ro_str("maintain_common_screen")

    # Target values (intentionally defective)
    val_cs_tube_txt = add_ro_str("Proplach externí hadičky na mléko")
    val_cs_sys_txt = add_ro_str("Proplachování systému napěňovače mléka")
    val_cs_tube_lf_txt = add_ro_str("Proplach externí\nhadičky na mléko")
    val_cs_sys_lf_txt = add_ro_str("Proplachování systému\nnapěňovače mléka")

    val_en_tube_txt = add_ro_str("EXTERNAL MILK PIPE RINSING")
    val_en_sys_txt = add_ro_str("Milk frother system rinsing")
    val_en_tube_lf_txt = add_ro_str("EXTERNAL MILK PIPE\nRINSING")

    val_temp_it = add_ro_str("Temperatura alta")
    val_temp_cs = add_ro_str("Vysoká teplota")
    val_temp_low = add_ro_str("Nízká teplota")

    val_screen_typo = add_ro_str("ČIštění obrazovky")
    val_cestina = add_ro_str("cestina")
    tag_cs = add_ro_str("language_cs")

    # .data section for singulars tables
    data_off = 0x10000
    data_vma_base = 0x0676fa78

    cs_tab_off = 0x10100
    cs_tab_vma = data_vma_base + (cs_tab_off - data_off)

    cs_entries = [
        (k_milk_sys, val_cs_tube_txt),     # Defect 1: Inverted frother rinse
        (k_milk_tube, val_cs_sys_txt),    # Inverted tube rinse
        (k_milk_sys_lf, val_cs_tube_lf_txt),
        (k_milk_tube_lf, val_cs_sys_lf_txt),
        (k_temp, val_temp_it),             # Defect 2: Italian leakage
        (k_temp_low, val_temp_low),        # Sibling for orphan recovery
        (k_screen, val_screen_typo),       # Defect 3: Mid-word typo
    ]
    if extra_cs_entries:
        for k_txt, v_txt in extra_cs_entries:
            cs_entries.append((add_ro_str(k_txt), add_ro_str(v_txt)))
    cs_entries.append((0, 0))

    for idx, (k, v) in enumerate(cs_entries):
        struct.pack_into("<II", buf, cs_tab_off + idx * 8, k, v)

    en_tab_off = 0x10300
    en_tab_vma = data_vma_base + (en_tab_off - data_off)
    en_entries = [
        (k_milk_sys, val_en_tube_txt),     # Defect 1: Inverted frother rinse EN
        (k_milk_tube, val_en_sys_txt),
        (k_milk_sys_lf, val_en_tube_lf_txt),
        (k_milk_tube_lf, val_en_sys_txt),
    ]
    if extra_en_entries:
        for k_txt, v_txt in extra_en_entries:
            en_entries.append((add_ro_str(k_txt), add_ro_str(v_txt)))
    en_entries.append((0, 0))
    for idx, (k, v) in enumerate(en_entries):
        struct.pack_into("<II", buf, en_tab_off + idx * 8, k, v)

    it_tab_off = 0x10500
    it_tab_vma = data_vma_base + (it_tab_off - data_off)
    it_entries = [
        (k_temp, val_temp_it),
        (0, 0),
    ]
    for idx, (k, v) in enumerate(it_entries):
        struct.pack_into("<II", buf, it_tab_off + idx * 8, k, v)

    # Structs in rodata
    en_struct_off = ro_off
    en_struct_vma = ro_vma_base + (en_struct_off - 0x1000)
    struct.pack_into("<9I", buf, en_struct_off, v_en, en_tab_vma, 0, 0, 0, 0, 0, 0, 0)
    ro_off += 36

    cs_struct_off = ro_off
    cs_struct_vma = ro_vma_base + (cs_struct_off - 0x1000)
    struct.pack_into("<9I", buf, cs_struct_off, v_cs, cs_tab_vma, 0, 0, 0, 0, 0, 0, 0)
    ro_off += 36

    it_struct_off = ro_off
    it_struct_vma = ro_vma_base + (it_struct_off - 0x1000)
    struct.pack_into("<9I", buf, it_struct_off, v_it, it_tab_vma, 0, 0, 0, 0, 0, 0, 0)
    ro_off += 36

    # Pack array in rodata
    pack_off = ro_off
    pack_vma = ro_vma_base + (pack_off - 0x1000)
    struct.pack_into("<4I", buf, pack_off, en_struct_vma, cs_struct_vma, it_struct_vma, 0)
    ro_off += 16

    # String table for symtab
    strtab = b"\x00lv_i18n_language_pack\x00cs_cz_singulars\x00en_gb_singulars\x00"
    strtab_off = 0x25000
    buf[strtab_off:strtab_off + len(strtab)] = strtab

    # Symtab entries
    symtab_off = 0x20000

    def add_sym(idx, name_idx, val, sz=0, info=1):
        struct.pack_into("<IIIBBH", buf, symtab_off + idx * 16, name_idx, val, sz, info, 0, 1)

    add_sym(0, 0, 0)
    add_sym(1, 1, pack_vma)
    add_sym(2, 23, cs_tab_vma)
    add_sym(3, 39, en_tab_vma)
    symtab_sz = 4 * 16

    # .text at 0x0100 (vma=0x0001c9b0)
    # Defect 4: ARM instructions loading val_cestina
    ins = bytearray()
    ins += encode_arm_movw_movt(1, val_cestina)
    ins += encode_arm_movw_movt(2, val_cestina)
    buf[0x0100:0x0100 + len(ins)] = ins

    # Program headers at 0x0034
    e_phoff = 0x0034

    def phdr(p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align):
        return struct.pack("<IIIIIIII", p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align)

    phdrs = [
        # Segment 1: .text and .rodata
        phdr(1, 0, 0x00010000, 0x00010000, 0x10000, 0x10000, 7, 0x10000),
        # Segment 2: .data
        phdr(1, 0x10000, data_vma_base, data_vma_base, 0x10000, 0x10000, 7, 0x10000),
    ]
    for idx, p in enumerate(phdrs):
        buf[e_phoff + idx * 32:e_phoff + (idx + 1) * 32] = p

    # Section headers at 0x45000
    e_shoff = 0x45000

    def sec_hdr(name_idx, s_type, flags, addr, off, size, link=0, entsize=0):
        return struct.pack("<IIIIIIIIII", name_idx, s_type, flags, addr, off, size, link, 0, 4, entsize)

    secs = [
        sec_hdr(0, 0, 0, 0, 0, 0),
        sec_hdr(1, 1, 6, 0x0001c9b0, 0x0100, 0x0800),            # .text (ALLOC|EXEC)
        sec_hdr(7, 1, 2, ro_vma_base, 0x1000, 0x8000),           # .rodata (ALLOC)
        sec_hdr(15, 1, 3, data_vma_base, 0x10000, 0x8000),        # .data (ALLOC|WRITE)
        sec_hdr(21, 2, 0, 0, symtab_off, symtab_sz, link=5, entsize=16),  # .symtab
        sec_hdr(29, 3, 0, 0, strtab_off, len(strtab)),           # .strtab
        sec_hdr(37, 3, 0, 0, shstr_off, len(shstr)),             # .shstrtab
    ]
    for idx, s in enumerate(secs):
        buf[e_shoff + idx * 40:e_shoff + (idx + 1) * 40] = s

    # ELF Header
    ident = b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8
    hdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        ident, 2, 40, 1, 0x00010000, e_phoff, e_shoff, 0x05000000,
        52, 32, len(phdrs), 40, len(secs), 6
    )
    buf[:len(hdr)] = hdr

    return bytes(buf)


class TestSyntheticHmiInspector(unittest.TestCase):
    """
    Tests engine functions against synthetic ELF32 fixture.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="spectra_test_hmi_")
        self.elf_path = os.path.join(self.temp_dir, "lv_klm_coffee_make_113")
        with open(self.elf_path, "wb") as f:
            f.write(create_synthetic_elf_binary())
        self.inspector = KalermHmiInspector(self.elf_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_elf_section_parsing(self):
        """Verify dynamic ELF32 section headers and VMA-to-offset mapping."""
        self.assertGreaterEqual(len(self.inspector.sections), 6)
        sec_names = [s.name for s in self.inspector.sections]
        self.assertIn(".text", sec_names)
        self.assertIn(".rodata", sec_names)
        self.assertIn(".data", sec_names)
        self.assertIn(".symtab", sec_names)

        # Dynamic mapping verification
        self.assertEqual(self.inspector.vma_to_off(0x0001c9b0), 0x0100)
        self.assertEqual(self.inspector.vma_to_off(0x018aba28), 0x1000)
        self.assertEqual(self.inspector.vma_to_off(0x0676fa78), 0x10000)

        # Reverse mapping verification
        self.assertEqual(self.inspector.off_to_vma(0x0100), 0x0001c9b0)
        self.assertEqual(self.inspector.off_to_vma(0x1000), 0x018aba28)

    def test_symbol_table_parsing(self):
        """Verify dynamic symbol table parsing and address lookup."""
        self.assertIn("lv_i18n_language_pack", self.inspector.symbols)
        self.assertIn("cs_cz_singulars", self.inspector.symbols)
        self.assertIn("en_gb_singulars", self.inspector.symbols)

        pack_vma = self.inspector.get_symbol_vma("lv_i18n_language_pack")
        self.assertIsNotNone(pack_vma)
        self.assertGreater(pack_vma, 0x018aba28)

    def test_extract_languages(self):
        """Verify locale iteration and phrase extraction."""
        langs = self.inspector.extract_all_languages()
        self.assertIn("en-GB", langs)
        self.assertIn("cs-CZ", langs)

        cs_phrases = langs["cs-CZ"]["phrases"]
        self.assertIn("Drink_Temp_High", cs_phrases)
        self.assertIn("maintain_common_screen", cs_phrases)
        self.assertIn("common_milk_frother_system_rinse", cs_phrases)

        # Test single locale accessor
        loc_cs = self.inspector.extract_language("cs-CZ")
        self.assertIsNotNone(loc_cs)
        self.assertEqual(loc_cs["locale"], "cs-CZ")

    def test_audit_detection(self):
        """Verify automated audit detects all 5 synthetic defects."""
        findings = self.inspector.run_audit()
        self.assertEqual(len(findings), 5)

        finding_ids = {f["id"]: f for f in findings}
        self.assertIn("AUDIT-SWAP-cs-CZ-common_milk_frother_system_rinse", finding_ids)
        self.assertIn("AUDIT-SWAP-en-GB-common_milk_frother_system_rinse", finding_ids)
        self.assertIn("AUDIT-LEAK-cs-CZ-Drink_Temp_High", finding_ids)
        self.assertIn("AUDIT-TYPO-cs-CZ-maintain_common_screen", finding_ids)
        self.assertIn("AUDIT-LANG-CASING-CS", finding_ids)

        # Check severities and statuses
        self.assertEqual(finding_ids["AUDIT-SWAP-cs-CZ-common_milk_frother_system_rinse"]["severity"], "CRITICAL")
        self.assertEqual(finding_ids["AUDIT-SWAP-cs-CZ-common_milk_frother_system_rinse"]["status"], "DETECTED")
        self.assertEqual(finding_ids["AUDIT-SWAP-en-GB-common_milk_frother_system_rinse"]["severity"], "CRITICAL")
        self.assertEqual(finding_ids["AUDIT-LEAK-cs-CZ-Drink_Temp_High"]["severity"], "WARNING")
        self.assertEqual(finding_ids["AUDIT-TYPO-cs-CZ-maintain_common_screen"]["severity"], "WARNING")

    def test_apply_patches(self):
        """Verify laboratory binary patching safely fixes all audit issues."""
        out_patch = os.path.join(self.temp_dir, "patched_test_bin")
        res = self.inspector.apply_patches(out_patch)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(os.path.isfile(out_patch))
        self.assertGreaterEqual(len(res["patches_applied"]), 6)

        # Re-inspect patched binary
        patched_insp = KalermHmiInspector(out_patch)
        patched_findings = patched_insp.run_audit()

        for f in patched_findings:
            self.assertEqual(f["status"], "FIXED", f"Expected {f['id']} to be FIXED, got {f['status']}")
            self.assertEqual(f["severity"], "INFO")

    def test_signature_verification(self):
        """Verify SHA-256 computation and RSA signature container status."""
        # Case 1: Unsigned (no signature file)
        sig1 = self.inspector.verify_signature()
        self.assertEqual(len(sig1["sha256"]), 64)
        self.assertFalse(sig1["signature_present"])
        self.assertEqual(sig1["status_label"], "UNSIGNED / MODIFIED")

        # Case 2: Create mock KLM_SIGN.pem with 256 bytes
        mock_sig_path = os.path.join(self.temp_dir, "KLM_SIGN.pem")
        mock_raw = b"\xaa" * 256
        b64_sig = base64.b64encode(mock_raw).decode("ascii")
        with open(mock_sig_path, "w", encoding="utf-8") as f:
            f.write("-----BEGIN SIGNATURE-----\n")
            f.write(b64_sig + "\n")
            f.write("-----END SIGNATURE-----\n")

        sig2 = self.inspector.verify_signature()
        self.assertTrue(sig2["signature_present"])
        self.assertEqual(sig2["signature_len"], 256)
        self.assertEqual(sig2["status_label"], "SIGNATURE PRESENT (2048-bit RSA)")

    def test_report_exports(self):
        """Verify bug report export to Markdown and HTML."""
        md_path = os.path.join(self.temp_dir, "report.md")
        saved_md = self.inspector.export_bug_report(md_path)
        self.assertTrue(os.path.isfile(saved_md))
        with open(saved_md, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("# SPECTRA Firmware Engineering Audit", content)
        self.assertIn("AUDIT-SWAP-cs-CZ-common_milk_frother_system_rinse", content)
        self.assertIn("AUDIT-LEAK-cs-CZ-Drink_Temp_High", content)

        html_path = os.path.join(self.temp_dir, "report.html")
        saved_html = self.inspector.export_bug_report(html_path)
        self.assertTrue(os.path.isfile(saved_html))
        with open(saved_html, "r", encoding="utf-8") as f:
            h_content = f.read()
        self.assertIn("<title>SPECTRA Firmware Engineering Audit</title>", h_content)
        self.assertIn("badge-CRITICAL", h_content)

    def test_heuristic_format_specifier_mismatch(self):
        """Verify Heuristic 2 detects dropped printf specifiers (%d)."""
        bin_path = os.path.join(self.temp_dir, "injected_fmt_bin")
        raw = create_synthetic_elf_binary(
            extra_cs_entries=[("test_timer_key", "Časovač zbývá")],
            extra_en_entries=[("test_timer_key", "Timer remaining %d seconds")],
        )
        with open(bin_path, "wb") as f:
            f.write(raw)
        insp = KalermHmiInspector(bin_path)
        findings = insp.run_audit("cs-CZ")
        f_fmt = next((f for f in findings if f["id"] == "AUDIT-FMT-cs-CZ-test_timer_key"), None)
        self.assertIsNotNone(f_fmt)
        self.assertEqual(f_fmt["severity"], "CRITICAL")
        self.assertEqual(f_fmt["category"], "Format Specifier Mismatch")

    def test_heuristic_double_capital_typo(self):
        """Verify Heuristic 2 detects mid-word uppercase typos across arbitrary keys."""
        bin_path = os.path.join(self.temp_dir, "injected_typo_bin")
        raw = create_synthetic_elf_binary(
            extra_cs_entries=[("custom_beverage_key", "COffee Cream")],
        )
        with open(bin_path, "wb") as f:
            f.write(raw)
        insp = KalermHmiInspector(bin_path)
        findings = insp.run_audit("cs-CZ")
        f_typo = next((f for f in findings if f["id"] == "AUDIT-TYPO-cs-CZ-custom_beverage_key"), None)
        self.assertIsNotNone(f_typo)
        self.assertEqual(f_typo["severity"], "WARNING")
        self.assertEqual(f_typo["category"], "Orthography / Typo")

    def test_heuristic_untranslated_cjk(self):
        """Verify Heuristic 1 detects untranslated CJK glyphs in European locales."""
        bin_path = os.path.join(self.temp_dir, "injected_cjk_bin")
        raw = create_synthetic_elf_binary(
            extra_cs_entries=[("menu_cleaning_label", "Proplachování 冲洗")],
        )
        with open(bin_path, "wb") as f:
            f.write(raw)
        insp = KalermHmiInspector(bin_path)
        findings = insp.run_audit("cs-CZ")
        f_cjk = next((f for f in findings if f["id"] == "AUDIT-CJK-cs-CZ-menu_cleaning_label"), None)
        self.assertIsNotNone(f_cjk)
        self.assertEqual(f_cjk["severity"], "CRITICAL")
        self.assertEqual(f_cjk["category"], "Untranslated CJK String")

    def test_heuristic_polarity_contradiction(self):
        """Verify Heuristic 3 detects opposing key-value temperature polarities."""
        bin_path = os.path.join(self.temp_dir, "injected_polarity_bin")
        raw = create_synthetic_elf_binary(
            extra_cs_entries=[("setting_boiler_temp_high", "Nízká teplota")],
        )
        with open(bin_path, "wb") as f:
            f.write(raw)
        insp = KalermHmiInspector(bin_path)
        findings = insp.run_audit("cs-CZ")
        f_pol = next((f for f in findings if f["id"] == "AUDIT-POLARITY-cs-CZ-setting_boiler_temp_high"), None)
        self.assertIsNotNone(f_pol)
        self.assertEqual(f_pol["severity"], "CRITICAL")
        self.assertEqual(f_pol["category"], "Semantic Polarity Inversion")

    def test_multi_locale_audit_parameter(self):
        """Verify run_audit respects target_locale parameter."""
        findings_en = self.inspector.run_audit("en-GB")
        self.assertTrue(any(f["id"] == "AUDIT-SWAP-en-GB-common_milk_frother_system_rinse" for f in findings_en))

    def test_semantic_substitution_and_allocation_patch(self):
        """
        Verify Tier 1 self-learning glossary detects semantic term contradiction
        and safe binary patcher allocates .rodata space and repoints the phrase slot.
        """
        bin_path = os.path.join(self.temp_dir, "synthetic_semantic_bin")
        extra_cs = [
            ("water_tank_empty", "Nádržka na vodu je prázdná"),
            ("water_filter_replace", "Vyměňte vodní filtr"),
            ("water_level_low", "Nízká hladina vody"),
            ("water_hardness_set", "Nastavení tvrdosti vody"),
            ("milk_temperature_set", "Nastavení teploty mléka"),
            ("milk_frother_clean_tip", "Vyčistěte napěňovač mléka"),
            ("milk_container_empty", "Nádoba na mléko je prázdná"),
            ("milk_tube_insert", "Vložte hadičku na mléko"),
            ("common_milk_system_clean", "Vyčistěte systém vody"),
        ]
        extra_en = [
            ("water_tank_empty", "Water tank empty"),
            ("water_filter_replace", "Replace water filter"),
            ("water_level_low", "Water level low"),
            ("water_hardness_set", "Set water hardness"),
            ("milk_temperature_set", "Set milk temperature"),
            ("milk_frother_clean_tip", "Clean milk frother"),
            ("milk_container_empty", "Milk container empty"),
            ("milk_tube_insert", "Insert milk pipe"),
            ("common_milk_system_clean", "Clean milk system"),
        ]
        raw = create_synthetic_elf_binary(extra_cs_entries=extra_cs, extra_en_entries=extra_en)
        with open(bin_path, "wb") as f:
            f.write(raw)

        insp = KalermHmiInspector(bin_path)

        # 1. Verify glossary learning
        glossary = insp.build_auto_glossary("cs-CZ")
        self.assertIn("water", glossary)
        self.assertIn("milk", glossary)
        self.assertEqual(glossary["water"]["target_term"], "vod")
        self.assertEqual(glossary["milk"]["target_term"], "mlék")

        # 2. Run audit and verify semantic contradiction detection
        findings = insp.run_audit("cs-CZ")
        sem_finding = next((f for f in findings if f["id"] == "AUTO-SEMANTIC-common_milk_system_clean"), None)
        self.assertIsNotNone(sem_finding)
        self.assertEqual(sem_finding["severity"], "HIGH")
        self.assertEqual(sem_finding["category"], "Semantic Term Substitution (Tier 1 Glossary)")
        self.assertEqual(sem_finding["current_val"], "Vyčistěte systém vody")
        self.assertEqual(sem_finding["expected_val"], "Vyčistěte systém mléko")
        self.assertTrue(sem_finding["patchable"])

        meta = sem_finding["patch_meta"]
        self.assertIsNotNone(meta)
        self.assertEqual(meta["action"], "allocate_rodata_and_repoint_phrase")
        self.assertIsNotNone(meta["target_vma"])
        self.assertIsNotNone(meta["pad_offset"])

        # 3. Apply laboratory binary patches
        patched_path = os.path.join(self.temp_dir, "patched_semantic_bin")
        res = insp.apply_patches(patched_path)
        self.assertEqual(res["status"], "SUCCESS")
        alloc_patches = [p for p in res["patches_applied"] if p.get("action") == "allocate_rodata_and_repoint_phrase"]
        self.assertGreaterEqual(len(alloc_patches), 1)
        self.assertEqual(alloc_patches[0]["key"], "common_milk_system_clean")

        # 4. Re-inspect patched binary
        patched_insp = KalermHmiInspector(patched_path)
        patched_langs = patched_insp.extract_all_languages()
        patched_phrase = patched_langs["cs-CZ"]["phrases"]["common_milk_system_clean"]
        self.assertEqual(patched_phrase["val"], "Vyčistěte systém mléko")
        self.assertEqual(patched_phrase["val_vma"], meta["target_vma"])



class TestRealBinaryIntegration(unittest.TestCase):
    """
    Read-only integration test suite executing against the real production
    Kalerm HMI binary (lv_klm_coffee_make_113) if present on disk.
    """

    def setUp(self):
        self.real_dir = DEFAULT_KALERM_DIR
        self.real_bin = os.path.join(self.real_dir, "lv_klm_coffee_make_113")
        self.real_patched = os.path.join(self.real_dir, "lv_klm_coffee_make_113_patched")
        if not os.path.isfile(self.real_bin):
            self.skipTest(f"Production Kalerm binary not found at {self.real_bin}")

        self.inspector = KalermHmiInspector(self.real_bin)

    def test_real_binary_elf_sections(self):
        """Verify ELF32 section offsets on real Kalerm binary."""
        self.assertEqual(self.inspector.vma_to_off(0x0001c9b0), 0x0000c9b0)
        self.assertEqual(self.inspector.vma_to_off(0x018aba28), 0x0189ba28)
        self.assertEqual(self.inspector.vma_to_off(0x0676fa78), 0x0674fa78)
        self.assertEqual(self.inspector.vma_to_off(0x03567fdc), 0x03557fdc)
        self.assertEqual(self.inspector.vma_to_off(0x0678624c), 0x0676624c)

    def test_real_binary_symbols_and_languages(self):
        """Verify dynamic symbol table contains all 19 locales."""
        langs = self.inspector.extract_all_languages()
        self.assertEqual(len(langs), 19)
        expected_locales = [
            "en-GB", "cs-CZ", "da-DK", "de-DE", "el-GR", "es-ES", "fr-FR",
            "hr-HR", "hu-HU", "it-IT", "ja-JP", "ko-KR", "nl-NL", "pl-PL",
            "pt-PT", "ru-RU", "sv-SE", "zh-CN", "zh-TW"
        ]
        for loc in expected_locales:
            self.assertIn(loc, langs)
            self.assertGreaterEqual(len(langs[loc]["phrases"]), 640)

    def test_real_binary_audit_findings(self):
        """Verify audit detects all 4 real-world defect classes in unpatched binary."""
        findings = self.inspector.run_audit()
        finding_map = {f["id"]: f for f in findings}

        # Check inverted milk rinsing in cs-CZ
        f_milk_cs = finding_map.get("AUDIT-SWAP-cs-CZ-common_milk_frother_system_rinse")
        self.assertIsNotNone(f_milk_cs)
        self.assertEqual(f_milk_cs["status"], "DETECTED")
        self.assertEqual(f_milk_cs["current_val"], "Proplach externí hadičky na mléko")

        # Check inverted milk rinsing in en-GB
        f_milk_en = finding_map.get("AUDIT-SWAP-en-GB-common_milk_frother_system_rinse")
        self.assertIsNotNone(f_milk_en)
        self.assertEqual(f_milk_en["status"], "DETECTED")
        self.assertEqual(f_milk_en["current_val"], "EXTERNAL MILK PIPE RINSING")

        # Check Italian leakage
        f_it = finding_map.get("AUDIT-LEAK-cs-CZ-Drink_Temp_High")
        self.assertIsNotNone(f_it)
        self.assertEqual(f_it["status"], "DETECTED")
        self.assertEqual(f_it["current_val"], "Temperatura alta")

        # Check screen cleaning typo
        f_typo = finding_map.get("AUDIT-TYPO-cs-CZ-maintain_common_screen")
        self.assertIsNotNone(f_typo)
        self.assertEqual(f_typo["status"], "DETECTED")
        self.assertEqual(f_typo["current_val"], "ČIštění obrazovky")

        # Check casing
        f_casing = finding_map.get("AUDIT-LANG-CASING-CS")
        self.assertIsNotNone(f_casing)
        self.assertEqual(f_casing["status"], "DETECTED")
        self.assertEqual(f_casing["current_val"], "cestina")

    def test_real_patched_binary_verification(self):
        """Verify real patched binary has all issues marked FIXED and matches SHA-256."""
        if not os.path.isfile(self.real_patched):
            self.skipTest("Real patched binary not found.")

        patched_insp = KalermHmiInspector(self.real_patched)
        sig = patched_insp.verify_signature()
        self.assertEqual(sig["sha256"], "61b28549b6656151af32020060d324895403d49db65c67cd9b6b0fbb8548caf8")

        findings = patched_insp.run_audit()
        for f in findings:
            self.assertEqual(f["status"], "FIXED")

    def test_real_binary_multi_locale_heuristics(self):
        """Verify generalized heuristics on real production binary across locales."""
        # Croatian audit detects dropped %d in clean step
        hr_findings = self.inspector.run_audit("hr-HR")
        f_hr_fmt = next((f for f in hr_findings if f["id"] == "AUDIT-FMT-hr-HR-maintain_clean_step_time_d"), None)
        self.assertIsNotNone(f_hr_fmt)
        self.assertEqual(f_hr_fmt["severity"], "CRITICAL")

        # Dutch audit detects dropped %d in password length
        nl_findings = self.inspector.run_audit("nl-NL")
        f_nl_fmt = next((f for f in nl_findings if f["id"] == "AUDIT-FMT-nl-NL-User_input_password_len"), None)
        self.assertIsNotNone(f_nl_fmt)
        self.assertEqual(f_nl_fmt["severity"], "CRITICAL")

    def test_real_binary_auto_glossary_and_semantic_audit(self):
        """Verify Tier 1 self-learning glossary and Tier 2 semantic audit on real production binary."""
        # Tier 1 Auto-Glossary extraction
        glossary = self.inspector.build_auto_glossary("cs-CZ")
        self.assertGreaterEqual(len(glossary), 100)
        self.assertIn("water", glossary)
        self.assertIn("milk", glossary)
        self.assertIn("valve", glossary)
        self.assertIn("temperature", glossary)
        self.assertIn("clean", glossary)

        self.assertIn("vod", glossary["water"]["target_term"])
        self.assertIn("mlék", glossary["milk"]["target_term"])
        self.assertIn("ventil", glossary["valve"]["target_term"])
        self.assertIn("teplot", glossary["temperature"]["target_term"])
        self.assertIn("čišt", glossary["clean"]["target_term"])

        # Tier 2 Semantic Hybrid Audit execution
        sem_res = self.inspector.run_semantic_audit("cs-CZ")
        self.assertIn("summary", sem_res)
        summary = sem_res["summary"]
        self.assertGreaterEqual(summary["total_phrases"], 600)
        self.assertGreaterEqual(summary["average_alignment"], 0.70)
        self.assertGreaterEqual(len(sem_res["flagged_phrases"]), 1)


class TestHardwareProbeAndOllamaManager(unittest.TestCase):
    """
    Unit tests for Host Hardware Self-Check & Adaptive Model Selector.
    """

    def test_live_hardware_probe(self):
        """Verify dynamic host hardware detection across live hardware without hardcoding."""
        hw = KalermHmiInspector.probe_host_hardware()
        self.assertIn("cpu", hw)
        self.assertIn("memory", hw)
        self.assertIn("gpu", hw)
        self.assertIn("disk", hw)
        self.assertIn("tier", hw)
        self.assertIn("recommended_model", hw)
        self.assertIn("default_selected_model", hw)
        self.assertIn("model_catalog", hw)

        self.assertIn(hw["tier"], {"HIGH_END_GPU", "WORKSTATION_MID", "BALANCED_CPU", "ULTRA_LIGHT_CPU"})
        self.assertGreaterEqual(hw["cpu"]["logical_cores"], 1)
        self.assertGreater(hw["memory"]["ram_total_mb"], 0)
        self.assertGreater(hw["memory"]["ram_available_mb"], 0)
        self.assertGreater(hw["disk"]["disk_free_gb"], 0.0)
        self.assertGreaterEqual(len(hw["model_catalog"]), 6)

        rec_entry = next((m for m in hw["model_catalog"] if m["id"] == hw["recommended_model"]), None)
        self.assertIsNotNone(rec_entry)
        self.assertTrue(rec_entry["is_recommended"])
        self.assertEqual(rec_entry["compatibility"], "RECOMMENDED")

    def test_simulated_hardware_profiles(self):
        """Verify adaptive model recommendations under simulated hardware conditions."""
        # 1. 4 GB Dual-Core Laptop without AVX2 (e.g. Ivy Bridge i5-3320M)
        hw_laptop = KalermHmiInspector.probe_host_hardware(
            override_ram_mb=3500,
            override_avx2=False,
            override_gpu={"has_discrete_gpu": False, "vram_total_mb": 0}
        )
        self.assertEqual(hw_laptop["tier"], "ULTRA_LIGHT_CPU")
        self.assertEqual(hw_laptop["recommended_model"], "qwen2.5:0.5b")
        self.assertTrue(hw_laptop["auto_unload_recommended"])

        # 2. Balanced CPU Host with AVX2 (6 GB available RAM)
        hw_bal = KalermHmiInspector.probe_host_hardware(
            override_ram_mb=6000,
            override_avx2=True,
            override_gpu={"has_discrete_gpu": False, "vram_total_mb": 0}
        )
        self.assertEqual(hw_bal["tier"], "BALANCED_CPU")
        self.assertEqual(hw_bal["recommended_model"], "qwen2.5:1.5b")

        # 3. Workstation Host with AVX2 (12 GB available RAM)
        hw_mid = KalermHmiInspector.probe_host_hardware(
            override_ram_mb=12000,
            override_avx2=True,
            override_gpu={"has_discrete_gpu": False, "vram_total_mb": 0}
        )
        self.assertEqual(hw_mid["tier"], "WORKSTATION_MID")
        self.assertEqual(hw_mid["recommended_model"], "qwen2.5:3b")

        # 4. Workstation with Discrete GPU (12 GB VRAM + 32 GB RAM)
        hw_gpu = KalermHmiInspector.probe_host_hardware(
            override_ram_mb=32000,
            override_gpu={"has_discrete_gpu": True, "vram_total_mb": 12000, "gpu_name": "NVIDIA RTX 4080", "gpu_vendor": "nvidia"}
        )
        self.assertEqual(hw_gpu["tier"], "HIGH_END_GPU")
        self.assertEqual(hw_gpu["recommended_model"], "qwen2.5:7b")
        self.assertFalse(hw_gpu["auto_unload_recommended"])

    def test_ai_system_status_and_control(self):
        """Verify composite AI system status reporting and safe Ollama controller actions."""
        status = KalermHmiInspector.get_ai_system_status()
        self.assertIn("hardware", status)
        self.assertIn("ollama", status)
        self.assertIn("binary_installed", status)
        self.assertIn("binary_path", status)
        self.assertIn("is_managed_process", status)

        # Unload action should never crash even when daemon is offline
        res = KalermHmiInspector.control_local_ollama("unload")
        self.assertEqual(res["status"], "SUCCESS")

        # Unknown action returns structured error
        err_res = KalermHmiInspector.control_local_ollama("invalid_cmd")
        self.assertEqual(err_res["status"], "UNKNOWN_ACTION")

    def test_ollama_streaming_progress_and_cancel(self):
        """Verify real-time download state tracker, progress calculation, and cancel_pull."""
        # Initial progress
        prog = KalermHmiInspector.get_ollama_download_progress()
        self.assertIn("active", prog)
        self.assertIn("status", prog)
        self.assertIn("percent", prog)
        self.assertIn("speed_mbps", prog)
        self.assertIn("eta_sec", prog)

        # Binary discovery should locate installed portable binary
        bin_path = KalermHmiInspector._find_ollama_binary()
        if bin_path:
            self.assertTrue(os.path.isfile(bin_path))
            status = KalermHmiInspector.get_ai_system_status()
            self.assertTrue(status["binary_installed"])

        # Test simulated progress updates
        KalermHmiInspector._update_download_progress(
            active=True,
            status="PULLING_MODEL",
            model="qwen2.5:0.5b",
            completed_bytes=100 * 1024 * 1024,
            total_bytes=400 * 1024 * 1024,
            percent=25.0,
            speed_mbps=12.5,
            eta_sec=24,
        )
        updated = KalermHmiInspector.get_ollama_download_progress()
        self.assertTrue(updated["active"])
        self.assertEqual(updated["status"], "PULLING_MODEL")
        self.assertEqual(updated["percent"], 25.0)
        self.assertEqual(updated["speed_mbps"], 12.5)
        self.assertEqual(updated["eta_sec"], 24)

        # Test cancel_pull action
        cancel_res = KalermHmiInspector.control_local_ollama("cancel_pull")
        self.assertEqual(cancel_res["status"], "CANCEL_REQUESTED")
        with KalermHmiInspector._download_lock:
            self.assertTrue(KalermHmiInspector._download_state["cancel_requested"])

        # Reset download state
        with KalermHmiInspector._download_lock:
            KalermHmiInspector._download_state.update({
                "active": False,
                "status": "IDLE",
                "cancel_requested": False,
            })

    def test_semantic_audit_with_mocked_ollama(self):
        """
        Verify Tier 3 Ollama neural audit loop with mocked response:
        checks tier3_ollama reviews, verdict, confirmed_defects_count,
        and annotates candidate phrases with c['ollama_review'].
        """
        temp_dir = tempfile.mkdtemp(prefix="spectra_test_ollama_audit_")
        try:
            extra_cs = [("common_milk_system_clean", "Vyčistěte systém vody")]
            extra_en = [("common_milk_system_clean", "Clean milk system")]
            raw = create_synthetic_elf_binary(extra_cs_entries=extra_cs, extra_en_entries=extra_en)
            bin_path = os.path.join(temp_dir, "lv_klm_test")
            with open(bin_path, "wb") as f:
                f.write(raw)
            insp = KalermHmiInspector(bin_path)

            with patch.object(KalermHmiInspector, "check_local_ollama") as mock_chk, \
                 patch("urllib.request.urlopen") as mock_url:
                mock_chk.return_value = {"available": True, "models": ["qwen2.5:1.5b"]}

                resp_obj = MagicMock()
                resp_obj.status = 200
                llm_content = {
                    "response": json.dumps({
                        "is_correct": False,
                        "reason": "Water concept used instead of milk.",
                        "suggested_translation": "Vyčistěte systém mléka",
                    })
                }
                resp_obj.read.return_value = json.dumps(llm_content).encode("utf-8")
                resp_obj.__enter__.return_value = resp_obj
                resp_obj.__exit__.return_value = None
                mock_url.return_value = resp_obj

                sem = insp.run_semantic_audit(
                    "cs-CZ",
                    use_ollama=True,
                    auto_unload=True,
                    ollama_model="qwen2.5:1.5b",
                )

                t3 = sem.get("tier3_ollama", {})
                self.assertTrue(t3.get("executed"))
                self.assertEqual(t3.get("active_model"), "qwen2.5:1.5b")
                reviews = t3.get("reviews", [])
                self.assertGreaterEqual(len(reviews), 1)

                r0 = reviews[0]
                self.assertEqual(r0["key"], "common_milk_system_clean")
                self.assertEqual(r0["verdict"], "DEFECT_CONFIRMED")
                self.assertFalse(r0["is_correct"])
                self.assertEqual(r0["suggested_translation"], "Vyčistěte systém mléka")
                self.assertEqual(t3.get("confirmed_defects_count"), 1)
                self.assertEqual(t3.get("verified_ok_count"), 0)
                self.assertTrue(t3.get("ram_unloaded"))

                # Verify c['ollama_review'] on candidate in flagged_phrases
                flagged = sem.get("flagged_phrases", [])
                scanned_c = next((c for c in flagged if c["key"] == "common_milk_system_clean"), None)
                self.assertIsNotNone(scanned_c)
                self.assertIn("ollama_review", scanned_c)
                self.assertEqual(scanned_c["ollama_review"]["verdict"], "DEFECT_CONFIRMED")
                self.assertEqual(scanned_c["suggested_val"], "Vyčistěte systém mléka")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_semantic_audit_ollama_autostart_and_keep_alive(self):
        """
        Verify that run_semantic_audit auto-starts Ollama daemon when offline,
        sends keep_alive: 5m inside candidate loop, and unloads once afterwards.
        """
        temp_dir = tempfile.mkdtemp(prefix="spectra_test_ollama_autostart_")
        try:
            extra_cs = [("common_milk_system_clean", "Vyčistěte systém vody")]
            extra_en = [("common_milk_system_clean", "Clean milk system")]
            raw = create_synthetic_elf_binary(extra_cs_entries=extra_cs, extra_en_entries=extra_en)
            bin_path = os.path.join(temp_dir, "lv_klm_test")
            with open(bin_path, "wb") as f:
                f.write(raw)
            insp = KalermHmiInspector(bin_path)

            call_counts = {"check": 0}
            def fake_check(timeout=0.35):
                call_counts["check"] += 1
                if call_counts["check"] == 1:
                    return {"available": False, "endpoint": "http://127.0.0.1:11434", "models": []}
                return {"available": True, "endpoint": "http://127.0.0.1:11434", "models": ["qwen2.5:1.5b"]}

            with patch.object(KalermHmiInspector, "check_local_ollama", side_effect=fake_check), \
                 patch.object(KalermHmiInspector, "_find_ollama_binary", return_value="/usr/bin/ollama"), \
                 patch.object(KalermHmiInspector, "control_local_ollama") as mock_ctrl, \
                 patch("urllib.request.urlopen") as mock_url:

                resp_obj = MagicMock()
                resp_obj.status = 200
                llm_content = {
                    "response": "```json\n{\"is_correct\": true, \"reason\": \"Correct context.\", \"suggested_translation\": \"Vyčistěte systém vody\"}\n```"
                }
                resp_obj.read.return_value = json.dumps(llm_content).encode("utf-8")
                resp_obj.__enter__.return_value = resp_obj
                resp_obj.__exit__.return_value = None
                mock_url.return_value = resp_obj

                sem = insp.run_semantic_audit(
                    "cs-CZ",
                    use_ollama=True,
                    auto_unload=True,
                    ollama_model="qwen2.5:1.5b",
                )

                # Verify control_local_ollama was called with 'start'
                mock_ctrl.assert_any_call("start")
                # Verify control_local_ollama was called with 'unload' after the loop
                mock_ctrl.assert_any_call("unload", "qwen2.5:1.5b")

                t3 = sem.get("tier3_ollama", {})
                self.assertEqual(t3.get("verified_ok_count"), 1)
                self.assertEqual(t3.get("confirmed_defects_count"), 0)
                reviews = t3.get("reviews", [])
                self.assertEqual(len(reviews), 1)
                self.assertEqual(reviews[0]["verdict"], "VERIFIED_OK")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestRustCoreAcceleration(unittest.TestCase):
    """
    Tests for high-speed zero-panic Rust native acceleration primitives (spectra_py).
    """

    def test_rust_core_module_loaded(self):
        import hmi_inspector
        self.assertTrue(hmi_inspector.HAS_RUST_CORE)
        self.assertIsNotNone(hmi_inspector._rust_core)

    def test_arm_instruction_scanning_and_repointing(self):
        import spectra_py
        target_vma = 0x03567890
        new_vma = 0x03569999

        # Generate a buffer with movw+movt instruction
        enc = encode_arm_movw_movt(2, target_vma)
        buffer = bytearray(64)
        buffer[16:24] = enc

        # Test pattern scanning across any register
        self.assertTrue(spectra_py.has_arm_movw_movt_any_reg(bytes(buffer), target_vma))
        self.assertFalse(spectra_py.has_arm_movw_movt_any_reg(bytes(buffer), 0x11223344))

        # Test repointing
        patched_bytes, count = spectra_py.repoint_arm_movw_movt_all_regs(bytes(buffer), target_vma, new_vma)
        self.assertEqual(count, 1)
        self.assertTrue(spectra_py.has_arm_movw_movt_any_reg(patched_bytes, new_vma))
        self.assertFalse(spectra_py.has_arm_movw_movt_any_reg(patched_bytes, target_vma))

    def test_zero_padding_and_bipartite_swaps(self):
        import spectra_py
        ro_data = bytearray(b"\xFF" * 128)
        ro_data[32:64] = b"\x00" * 32

        # Find 16 bytes aligned to 16
        pad = spectra_py.find_free_zero_padding_fast(bytes(ro_data), 0x2000, 16, 16, 0)
        self.assertEqual(pad, 0x2020)

        # Bipartite token swap detection
        keys = ["rinse_milk_pipe", "rinse_frother_system"]
        key_tokens = [["rinse", "milk", "pipe"], ["rinse", "frother", "system"]]
        val_tokens = [["rinse", "frother", "system"], ["rinse", "milk", "pipe"]]
        pairs = spectra_py.detect_bipartite_token_swaps_fast(keys, key_tokens, val_tokens)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0], (0, 1))

    def test_kalerm_crc_functions(self):
        import spectra_py
        packet = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])
        crc_lo, crc_hi = spectra_py.kalerm_compute_crc(packet)
        full_packet = packet + bytes([crc_lo, crc_hi])
        self.assertTrue(spectra_py.kalerm_verify_crc(full_packet))
        self.assertFalse(spectra_py.kalerm_verify_crc(full_packet[:-1] + b"\x00"))


class TestUniversalContainerInspector(unittest.TestCase):
    """
    Unit tests for Universal Container support: Android APK resources.arsc and ARM Cortex-M CTR .bin firmware.
    """

    def test_synthetic_mcu_ctr_bin_parsing(self):
        """Verify vector table parsing, chip family inference, and string extraction on synthetic MCU image."""
        temp_dir = tempfile.mkdtemp(prefix="spectra_test_mcu_")
        bin_path = os.path.join(temp_dir, "60200099-100-M-CTR-APP-GD32F425-V1.0.0-AABBCCDD-260101.bin")
        try:
            buf = bytearray(2048)
            # Valid Cortex-M4 vector table: SP in SRAM, Reset in Flash
            sp = 0x20004000
            reset = 0x08021001
            struct.pack_into("<II", buf, 0, sp, reset)

            # Embed ASCII actuator strings
            strings_to_embed = [
                b"PUMP_STAT_RUN\x00",
                b"VALVE_CERAMIC_OPEN\x00",
                b"HEATER_NTC_TEMP_ERROR\x00",
                b"FLOWMETER_IMPULSE_OK\x00",
            ]
            cur_off = 0x400
            for s in strings_to_embed:
                buf[cur_off:cur_off + len(s)] = s
                cur_off += len(s) + 4

            with open(bin_path, "wb") as f:
                f.write(buf)

            insp = KalermHmiInspector(bin_path)
            self.assertEqual(insp.container_type, "MCU_CTR_BIN")
            self.assertEqual(insp.container_badge, "ARM CORTEX-M (CTR BIN)")
            self.assertEqual(insp.mcu_info.get("crc_token"), "AABBCCDD")

            sig = insp.verify_signature()
            self.assertTrue(sig.get("signature_present"))
            self.assertIn("AABBCCDD", sig.get("status_label"))

            langs = insp.extract_all_languages()
            self.assertIn("MCU-STRINGS", langs)
            mcu_phrases = langs["MCU-STRINGS"]["phrases"]
            self.assertGreaterEqual(len(mcu_phrases), 4)

            # Check actuator telemetry
            actuators = insp.mcu_info.get("actuators", [])
            self.assertTrue(any("PUMP" in a for a in actuators))
            self.assertTrue(any("VALVE" in a for a in actuators))

            findings = insp.run_audit()
            self.assertEqual(len(findings), 3)
            self.assertTrue(any(f["category"] == "MCU Architecture & Vector Table" for f in findings))
            self.assertTrue(any(f["category"] == "MCU Image CRC Token" for f in findings))
            self.assertTrue(any(f["category"] == "MCU Actuator & Hardware Subsystem" for f in findings))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_real_android_apk_and_companion_detection(self):
        """Test APK detection, signature scheme v2, locale normalization, and companion CTR bin resolution."""
        apk_dir = os.path.expanduser("~/Downloads/X-line_1.9.9HMI")
        if not os.path.isdir(apk_dir):
            self.skipTest(f"Directory {apk_dir} not present on test host")

        insp = KalermHmiInspector(apk_dir)
        self.assertEqual(insp.container_type, "ANDROID_APK")
        self.assertEqual(insp.container_badge, "ANDROID APK (ARSC)")
        self.assertIsNotNone(insp.companion_ctr_bin)
        self.assertTrue(insp.companion_ctr_bin.endswith(".bin"))

        sig = insp.verify_signature()
        self.assertTrue(sig.get("signature_present"))
        self.assertEqual(sig.get("status_label"), "APK_SIG_V2_AOSP_TEST_KEY (Re-signable)")

        langs = insp.extract_all_languages()
        self.assertIn("en-GB", langs)
        self.assertIn("cs-CZ", langs)
        self.assertEqual(len(langs["en-GB"]["phrases"]), 2077)
        self.assertEqual(len(langs["cs-CZ"]["phrases"]), 1562)

        findings = insp.run_audit("cs-CZ")
        self.assertGreater(len(findings), 0)
        # Check corrupted format specifiers and untranslated English leakage are caught
        categories = {f["category"] for f in findings}
        self.assertIn("Corrupted Format Specifier (Runtime Exception Risk)", categories)
        self.assertIn("Translation Coverage Gap", categories)

    def test_real_mcu_ctr_firmware_stm32h723_and_gd32f425(self):
        """Test STM32H723 and GD32F425 CTR bin firmware inspection."""
        stm_bin = os.path.expanduser("~/Downloads/X-line_1.9.9HMI/60200064-134-X-CTR-APP-STMH723-V1.3.4-93180B22-260721.bin")
        gd_bin = os.path.expanduser("~/Downloads/60200075-109-D-CTR-APP-GD32F425-V1.0.9-14C2CD54-260303.bin")

        if os.path.isfile(stm_bin):
            insp_stm = KalermHmiInspector(stm_bin)
            self.assertEqual(insp_stm.container_type, "MCU_CTR_BIN")
            self.assertEqual(insp_stm.mcu_info.get("crc_token"), "93180B22")
            self.assertIn("STM32H7", insp_stm.mcu_info.get("family"))
            findings_stm = insp_stm.run_audit()
            self.assertEqual(len(findings_stm), 3)

        if os.path.isfile(gd_bin):
            insp_gd = KalermHmiInspector(gd_bin)
            self.assertEqual(insp_gd.container_type, "MCU_CTR_BIN")
            self.assertEqual(insp_gd.mcu_info.get("crc_token"), "14C2CD54")
            self.assertIn("GD32F4", insp_gd.mcu_info.get("family"))
            findings_gd = insp_gd.run_audit()
            self.assertEqual(len(findings_gd), 3)


class TestDiscoverLocalTargets(unittest.TestCase):
    """
    Test dynamic zero-hardcoded firmware discovery.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="spectra_test_discover_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_discover_local_targets_synthetic(self):
        import zipfile

        # 1. ARM 32-bit ELF
        elf_path = os.path.join(self.temp_dir, "custom_arm_hmi")
        with open(elf_path, "wb") as f:
            f.write(create_synthetic_elf_binary())

        # 2. Android APK
        apk_path = os.path.join(self.temp_dir, "custom_screen.apk")
        with zipfile.ZipFile(apk_path, "w") as z:
            z.writestr("AndroidManifest.xml", b"<manifest></manifest>")
            z.writestr("resources.arsc", b"ARSC_MOCK_DATA")

        # 3. Cortex-M MCU BIN
        bin_path = os.path.join(self.temp_dir, "ctr_boot.bin")
        mcu_data = struct.pack("<II", 0x20010000, 0x08000101) + b"\x00" * 512
        with open(bin_path, "wb") as f:
            f.write(mcu_data)

        # 4. Dummy files that should be ignored
        with open(os.path.join(self.temp_dir, "readme.txt"), "w") as f:
            f.write("ignore me")
        with open(os.path.join(self.temp_dir, "libtest.so"), "wb") as f:
            f.write(b"\x7fELF\x01\x01\x01\x00")

        targets = KalermHmiInspector.discover_local_targets(search_dirs=[self.temp_dir])
        paths = [t["path"] for t in targets]

        self.assertIn(elf_path, paths)
        self.assertIn(apk_path, paths)
        self.assertIn(bin_path, paths)
        self.assertNotIn(os.path.join(self.temp_dir, "readme.txt"), paths)
        self.assertNotIn(os.path.join(self.temp_dir, "libtest.so"), paths)

        for t in targets:
            if t["path"] == elf_path:
                self.assertEqual(t["container_type"], "ELF32_LVGL")
                self.assertIn("[ELF]", t["label"])
            elif t["path"] == apk_path:
                self.assertEqual(t["container_type"], "ANDROID_APK")
                self.assertIn("[APK]", t["label"])
            elif t["path"] == bin_path:
                self.assertEqual(t["container_type"], "MCU_CTR_BIN")
                self.assertIn("[BIN]", t["label"])

    def test_semantic_scan_progress(self):
        """Verify semantic progress tracking dictionary and getters."""
        prog = KalermHmiInspector.get_semantic_scan_progress()
        self.assertIsInstance(prog, dict)
        self.assertIn("percent", prog)
        self.assertIn("step", prog)
        self.assertIn("active", prog)

        # Test updating progress
        KalermHmiInspector._update_semantic_progress(
            percent=42,
            step="TIER3_OLLAMA",
            current=5,
            total=10,
            detail="Testing progress...",
            eta_seconds=12.5,
            active=True,
        )
        updated = KalermHmiInspector.get_semantic_scan_progress()
        self.assertEqual(updated["percent"], 42)
        self.assertEqual(updated["step"], "TIER3_OLLAMA")
        self.assertEqual(updated["current"], 5)
        self.assertEqual(updated["total"], 10)
        self.assertEqual(updated["detail"], "Testing progress...")
        self.assertEqual(updated["eta_seconds"], 12.5)
        self.assertTrue(updated["active"])

        # Reset back
        KalermHmiInspector._update_semantic_progress(
            percent=0,
            step="IDLE",
            current=0,
            total=0,
            detail="Ready",
            eta_seconds=None,
            active=False,
        )
        reset = KalermHmiInspector.get_semantic_scan_progress()
        self.assertFalse(reset["active"])
        self.assertEqual(reset["percent"], 0)


class TestGtkHmiInspector(unittest.TestCase):
    """
    Test headless instantiation of GTK dialog.
    """

    @unittest.skipUnless(HAS_GTK, "GTK3 is required for GUI tests")
    def test_dialog_instantiation(self):
        temp_dir = tempfile.mkdtemp(prefix="spectra_test_gtk_")
        elf_path = os.path.join(temp_dir, "lv_klm_coffee_make_113")
        try:
            with open(elf_path, "wb") as f:
                f.write(create_synthetic_elf_binary())

            # Instantiate dialog
            dialog = HmiInspectorDialog(initial_path=elf_path)
            self.assertIsNotNone(dialog.inspector)
            self.assertEqual(len(dialog.current_findings), 5)
            dialog.destroy()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
