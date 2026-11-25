#!/usr/bin/env python3
"""SPECTRA HMI laboratory binary patcher (safe zero-padding allocation & ARM movw/movt repointing)."""

import os
import re
import stat
import json
import shutil
import struct
import hashlib
import datetime
import tempfile
from typing import Dict, List, Tuple, Optional, Any

from spectra_hmi.elf_tools import (
    HAS_RUST_CORE,
    _rust_core,
    decode_arm_movw_movt,
    encode_arm_movw_movt,
)


class HmiPatcherMixin:
    """In-place laboratory ELF binary patch application with collision & verification guards."""

    def apply_patches(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Purely generic laboratory binary patcher:
        Executes patches dynamically generated from run_audit findings with zero hardcoded keys,
        strings, or addresses.
        """
        if self.container_type != "ELF32_LVGL":
            raise NotImplementedError(
                f"Binary lab patching is currently supported for ELF32 LVGL binaries (container type: {self.container_type})."
            )

        if not output_path:
            base, ext = os.path.splitext(self.binary_path)
            output_path = f"{base}_patched{ext}"

        output_path = os.path.abspath(output_path)
        if output_path == os.path.abspath(self.binary_path):
            raise ValueError("Refusing to overwrite original factory binary in-place. Provide distinct output_path.")

        if os.path.islink(output_path):
            raise ValueError(f"Refusing to write patched binary to symlink target: {output_path}")

        out_dir = os.path.dirname(output_path) or "."
        os.makedirs(out_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=out_dir, prefix=".spectra_patch_", suffix=".tmp", delete=False) as tf_out:
            staged_output_path = tf_out.name
        try:
            shutil.copyfile(self.binary_path, staged_output_path)
            try:
                os.chmod(staged_output_path, os.stat(self.binary_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except Exception:
                pass
        except Exception:
            try:
                if os.path.exists(staged_output_path):
                    os.unlink(staged_output_path)
            except OSError:
                pass
            raise

        patches_log: List[Dict[str, Any]] = []
        written_ranges: List[Tuple[int, int, str]] = []

        def _claim_range(start: int, length: int, label: str) -> None:
            if start < 0 or length <= 0 or start + length > self.file_size:
                raise RuntimeError(
                    f"ELF patch bounds violation for {label}: offset=0x{start:x}, len={length}, file_size=0x{self.file_size:x}"
                )
            end = start + length
            for prev_start, prev_end, prev_label in written_ranges:
                if start < prev_end and prev_start < end:
                    raise RuntimeError(
                        f"ELF patch collision detected: {label} [0x{start:x}..0x{end:x}) overlaps {prev_label} [0x{prev_start:x}..0x{prev_end:x})"
                    )
            written_ranges.append((start, end, label))

        def _verify_and_write_zero_pad(fh, pad_off: int, payload: bytes, label: str) -> None:
            _claim_range(pad_off, len(payload), label)
            fh.seek(pad_off)
            existing = fh.read(len(payload))
            if len(existing) != len(payload) or any(b != 0 for b in existing):
                raise RuntimeError(
                    f"Refusing to write {label} at 0x{pad_off:x}: target .rodata padding is not all-zero (collision/corruption protection)"
                )
            fh.seek(pad_off)
            fh.write(payload)

        findings = self.run_audit(target_locale="cs-CZ")

        try:
            with open(staged_output_path, "r+b") as f:
                for finding in findings:
                    if not finding.get("patchable") or finding.get("status") != "DETECTED":
                        continue
                    meta = finding.get("patch_meta")
                    if not meta:
                        continue

                    action = meta.get("action")

                    if action == "swap_slots":
                        off1 = meta["slot_off1"]
                        off2 = meta["slot_off2"]
                        vma1 = meta["vma1"]
                        vma2 = meta["vma2"]
                        _claim_range(off1, 4, f"swap_slots:{meta['key1']}")
                        _claim_range(off2, 4, f"swap_slots:{meta['key2']}")
                        f.seek(off1)
                        f.write(struct.pack("<I", vma2))
                        f.seek(off2)
                        f.write(struct.pack("<I", vma1))
                        patches_log.append({
                            "action": "swap_phrase_pointers",
                            "locale": meta["locale"],
                            "keys": f"{meta['key1']} <-> {meta['key2']}",
                            "offset1": off1,
                            "offset2": off2,
                        })

                        if meta.get("companion_lf"):
                            lf = meta["companion_lf"]
                            _claim_range(lf["slot_off1"], 4, f"swap_slots_lf:{lf['key1']}")
                            _claim_range(lf["slot_off2"], 4, f"swap_slots_lf:{lf['key2']}")
                            f.seek(lf["slot_off1"])
                            f.write(struct.pack("<I", lf["vma2"]))
                            f.seek(lf["slot_off2"])
                            f.write(struct.pack("<I", lf["vma1"]))
                            patches_log.append({
                                "action": "swap_phrase_pointers",
                                "locale": meta["locale"],
                                "keys": f"{lf['key1']} <-> {lf['key2']}",
                                "offset1": lf["slot_off1"],
                                "offset2": lf["slot_off2"],
                            })

                    elif action == "repoint_phrase_pointer":
                        slot_off = meta["slot_file_off"]
                        target_vma = meta["target_vma"]
                        _claim_range(slot_off, 4, f"repoint_phrase:{meta['key']}")
                        f.seek(slot_off)
                        f.write(struct.pack("<I", target_vma))
                        patches_log.append({
                            "action": "repoint_phrase_pointer",
                            "locale": meta["locale"],
                            "key": meta["key"],
                            "file_offset": slot_off,
                            "target_vma": f"0x{target_vma:08x}",
                            "new_val": meta.get("new_val", ""),
                        })

                    elif action == "inplace_write":
                        off = meta["offset"]
                        new_bytes = meta["new_bytes"]
                        _claim_range(off, len(new_bytes), f"inplace_write:{meta['key']}")
                        f.seek(off)
                        f.write(new_bytes)
                        patches_log.append({
                            "action": "fix_typo_byte",
                            "locale": meta["locale"],
                            "key": meta["key"],
                            "file_offset": off,
                            "byte_before": f"0x{meta['old_bytes'][0]:02x}",
                            "byte_after": f"0x{meta['new_bytes'][0]:02x}",
                        })

                    elif action == "repoint_language_endonym":
                        pad_off = meta["pad_offset"]
                        new_bytes = (meta["new_string"] + "\0").encode("utf-8")
                        orig_vma = meta["orig_vma"]
                        new_vma = meta["new_vma"]
                        text_sec = self.sections_by_name.get(".text")
                        t_off = text_sec.sh_offset if text_sec else 0
                        t_sz = text_sec.sh_size if text_sec else min(self.file_size, 0x2000000)

                        f.seek(t_off)
                        text_raw = f.read(t_sz)
                        repoint_count = 0

                        if HAS_RUST_CORE and _rust_core is not None:
                            try:
                                patched_bytes, repoint_count = _rust_core.repoint_arm_movw_movt_all_regs(text_raw, orig_vma, new_vma)
                                text_data = bytearray(patched_bytes)
                            except Exception:
                                text_data = bytearray(text_raw)
                        else:
                            text_data = bytearray(text_raw)

                        if repoint_count == 0 and not (HAS_RUST_CORE and _rust_core is not None):
                            for rd in range(16):
                                pat = encode_arm_movw_movt(rd, orig_vma)
                                rep = encode_arm_movw_movt(rd, new_vma)
                                idx = 0
                                while True:
                                    pos = text_data.find(pat, idx)
                                    if pos == -1:
                                        break
                                    text_data[pos:pos + 8] = rep
                                    repoint_count += 1
                                    idx = pos + 8

                        if repoint_count <= 0:
                            raise RuntimeError(
                                f"Refusing to patch language endonym '{meta['new_string']}': zero ARM movw/movt references found for 0x{orig_vma:08x} in .text"
                            )

                        _verify_and_write_zero_pad(
                            f,
                            pad_off,
                            new_bytes,
                            f"repoint_language_endonym:{meta['new_string']}",
                        )
                        patches_log.append({
                            "action": "write_rodata_string",
                            "file_offset": pad_off,
                            "vma": f"0x{new_vma:08x}",
                            "content": meta["new_string"],
                        })

                        f.seek(t_off)
                        f.write(text_data)
                        patches_log.append({
                            "action": "repoint_arm_movw_movt_pairs",
                            "count": repoint_count,
                            "source_vma": f"0x{orig_vma:08x}",
                            "target_vma": f"0x{new_vma:08x}",
                        })

                    elif action == "allocate_rodata_and_repoint_phrase":
                        pad_off = meta["pad_offset"]
                        new_bytes = (meta["new_string"] + "\0").encode("utf-8")
                        slot_off = meta["slot_file_off"]
                        target_vma = meta["target_vma"]
                        _verify_and_write_zero_pad(
                            f,
                            pad_off,
                            new_bytes,
                            f"allocate_rodata:{meta['key']}",
                        )
                        _claim_range(slot_off, 4, f"allocate_rodata_slot:{meta['key']}")
                        f.seek(slot_off)
                        f.write(struct.pack("<I", target_vma))
                        patches_log.append({
                            "action": "allocate_rodata_and_repoint_phrase",
                            "locale": meta["locale"],
                            "key": meta["key"],
                            "pad_offset": pad_off,
                            "slot_file_off": slot_off,
                            "vma": f"0x{target_vma:08x}",
                            "new_val": meta["new_string"],
                        })
            if os.path.islink(output_path):
                raise ValueError(f"Refusing to overwrite symlink target: {output_path}")
            os.replace(staged_output_path, output_path)
        except Exception:
            try:
                if os.path.exists(staged_output_path):
                    os.unlink(staged_output_path)
            except OSError:
                pass
            raise

        h = hashlib.sha256()
        with open(output_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        patched_sha = h.hexdigest()

        manifest_path = f"{output_path}.patch_manifest.json"
        if os.path.islink(manifest_path):
            raise ValueError(f"Refusing to write patch manifest to symlink target: {manifest_path}")
        sig_warning = (
            "LAB PATCH ONLY: Manufacturer cryptographic signature (e.g. KLM_SIGN.pem) is now "
            "INVALID for this modified binary. Verify boot safety on a bench unit before field use."
        )
        manifest_payload = {
            "source_binary": os.path.basename(self.binary_path),
            "output_binary": os.path.basename(output_path),
            "sha256": patched_sha,
            "signature_warning": sig_warning,
            "patches_applied": patches_log,
        }
        try:
            man_dir = os.path.dirname(os.path.abspath(manifest_path)) or "."
            with tempfile.NamedTemporaryFile("w", dir=man_dir, prefix=".patch_manifest_", suffix=".tmp", delete=False, encoding="utf-8") as mf:
                json.dump(manifest_payload, mf, indent=2)
                tmp_manifest = mf.name
            os.replace(tmp_manifest, manifest_path)
        except OSError:
            manifest_path = ""

        return {
            "status": "SUCCESS",
            "output_path": output_path,
            "sha256": patched_sha,
            "patches_applied": patches_log,
            "manifest_path": manifest_path,
            "signature_warning": sig_warning,
        }

