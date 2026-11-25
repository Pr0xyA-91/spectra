#!/usr/bin/env python3
"""SPECTRA HMI multi-format audit bug report generator (Markdown, HTML, PDF)."""

import os
import re
import html
import shutil
import base64
import datetime
import tempfile
import subprocess
from typing import Dict, List, Optional, Any

from spectra_hmi.elf_tools import __version__, __build__


def _atomic_write_text(target_path: str, content: str) -> None:
    if os.path.islink(target_path):
        raise ValueError(f"Refusing to write report to symlink target: {target_path}")
    out_dir = os.path.dirname(os.path.abspath(target_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=out_dir, prefix=".spectra_report_", suffix=".tmp", delete=False, encoding="utf-8") as tf:
        tf.write(content)
        tmp_path = tf.name
    try:
        if os.path.islink(target_path):
            raise ValueError(f"Refusing to write report to symlink target: {target_path}")
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


class HmiReportingMixin:
    """Markdown, styled HTML, and LibreOffice PDF report export."""

    def export_bug_report(self, output_path: str, format_type: Optional[str] = None, target_locale: str = "cs-CZ") -> str:
        """
        Generate and export an engineering bug report in Markdown (.md), HTML (.html),
        or PDF (.pdf via headless LibreOffice).
        """
        output_path = os.path.abspath(output_path)
        if os.path.islink(output_path):
            raise ValueError(f"Refusing to write report to symlink target: {output_path}")
        ext = os.path.splitext(output_path)[1].lower()
        if not format_type:
            format_type = ext.lstrip(".") or "md"

        findings = self.run_audit(target_locale=target_locale)
        sig_info = self.verify_signature()

        # Build Markdown document
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_lines = [
            "# SPECTRA Firmware Engineering Audit & Defect Report",
            f"**Target Binary:** `{os.path.basename(self.binary_path)}`  ",
            f"**Binary Path:** `{self.binary_path}`  ",
            f"**File Size:** {self.file_size:,} bytes  ",
            f"**SHA-256 Checksum:** `{sig_info['sha256']}`  ",
            f"**Signature Status:** `{sig_info['status_label']}`  ",
            f"**Audit Timestamp:** {timestamp}  ",
            f"**SPECTRA Auditor:** Build {__build__}  ",
            "",
            "---",
            "",
            "## 1. Executive Summary",
            "",
            (
                f"An automated static firmware and localization audit was conducted on the coffee machine "
                f"firmware binary (`{os.path.basename(self.binary_path)}` [{self.container_type}]). The inspection identified critical logical and "
                "localization discrepancies impacting machine operation, technician maintenance procedures, "
                "and user interface integrity."
            ),
            "",
            "### Audit Findings Summary:",
            "| ID | Severity | Category | Locale | Key | Status |",
            "|---|---|---|---|---|---|",
        ]

        for f in findings:
            md_lines.append(f"| `{f['id']}` | **{f['severity']}** | {f['category']} | `{f['locale']}` | `{f['key']}` | `{f['status']}` |")

        md_lines.extend([
            "",
            "---",
            "",
            "## 2. Technical Findings & Root Cause Analysis",
            "",
        ])

        for f in findings:
            vma_val = f.get("vma")
            off_val = f.get("file_offset")
            vma_str = f"0x{vma_val:08x}" if isinstance(vma_val, int) else str(vma_val or "0x00000000")
            off_str = f"0x{off_val:08x}" if isinstance(off_val, int) else str(off_val or "0x00000000")
            md_lines.extend([
                f"### {f.get('id', 'DEFECT')}: {f.get('key', '')} ({f.get('locale', '')})",
                f"- **Severity:** `{f.get('severity', 'INFO')}`",
                f"- **Category:** {f.get('category', '')}",
                f"- **Current Value:** `{f.get('current_val', '')}`",
                f"- **Expected Value:** `{f.get('expected_val', '')}`",
                f"- **VMA:** `{vma_str}` | **File Offset:** `{off_str}`",
                f"- **Remediation Status:** `{f.get('status', '')}`",
                "",
                f"> **Description:** {f.get('description', '')}",
                "",
            ])

        if self.container_type == "ANDROID_APK":
            sig_container_desc = sig_info.get("sig_scheme", "APK Signature")
        elif self.container_type == "MCU_CTR_BIN":
            sig_container_desc = f"MCU Release CRC32 ({sig_info.get('crc_token') or 'None'})"
        else:
            sig_container_desc = f"2048-bit RSA PKCS#1 v1.5 ({sig_info.get('signature_len', 0)} bytes)"

        md_lines.extend([
            "---",
            "",
            "## 3. Cryptographic Signature & Update Pipeline Warning",
            "",
            f"- **Signature File:** `{sig_info.get('signature_path') or 'None (Not Found)'}`",
            f"- **Signature Container:** {sig_container_desc}",
            f"- **Advisory:** {sig_info.get('warning', '')}",
            "",
            "---",
            "",
            "## 4. Laboratory Binary Patch Verification Matrix",
            "",
            "All identified defects are corrected dynamically via generic bytecode and pointer adjustments:",
            "1. **Semantic Inversion / Token Swaps:** Dynamically swapping `val_vma` pointers between conflicting key pairs.",
            "2. **Cross-Locale Pointer Leakage:** Repointing singulars table slot to unreferenced or recovered target locale string.",
            "3. **Orthography Typos:** In-place correction of erroneous uppercase bytes to lowercase UTF-8 characters.",
            "4. **Native Language Casing:** Injecting proper endonym into dynamically allocated `.rodata` padding and repointing ARM32 `movw/movt` instruction pairs.",
            "",
            "*(Report generated by SPECTRA Firmware Inspector)*",
        ])

        md_content = "\n".join(md_lines)

        if format_type == "md":
            _atomic_write_text(output_path, md_content)
            return output_path

        # Generate SPECTRA-themed HTML report
        esc = html.escape
        safe_bin_name = esc(os.path.basename(self.binary_path))
        safe_bin_path = esc(str(self.binary_path))
        safe_sha = esc(str(sig_info.get("sha256", "")))
        safe_sig_status = esc(str(sig_info.get("status_label", "")))
        safe_sig_path = esc(str(sig_info.get("signature_path") or "None (Not Found)"))
        safe_sig_desc = esc(str(sig_container_desc))
        safe_sig_warn = esc(str(sig_info.get("warning", "")))
        safe_container = esc(str(self.container_type))
        safe_ts = esc(str(timestamp))
        safe_build = esc(str(__build__))

        critical_cnt = sum(1 for item in findings if item.get("severity") == "CRITICAL")
        warning_cnt = sum(1 for item in findings if item.get("severity") == "WARNING")
        fixed_cnt = sum(1 for item in findings if item.get("status") == "FIXED")

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SPECTRA Firmware Engineering Audit</title>
<style>
  :root {{
    --bg-void: #070709;
    --bg-panel: #0E0E12;
    --bg-card: #12131A;
    --border-subtle: rgba(252, 238, 9, 0.22);
    --border-dim: #242633;
    --accent-yellow: #FCEE09;
    --accent-cyan: #00F0FF;
    --accent-crimson: #FF003C;
    --accent-emerald: #00FF66;
    --accent-amber: #F59E0B;
    --text-main: #E4E4E7;
    --text-muted: #A1A1AA;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
    background-color: var(--bg-void);
    color: var(--text-main);
    margin: 0;
    padding: 32px 20px;
  }}
  .report-shell {{
    max-width: 980px;
    margin: 0 auto;
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 10px;
    padding: 32px 36px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.75);
  }}
  .hero-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    border-bottom: 2px solid var(--accent-yellow);
    padding-bottom: 20px;
    margin-bottom: 24px;
  }}
  .hero-brand {{
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .hero-title {{
    margin: 0;
    font-size: 20px;
    font-weight: 900;
    letter-spacing: 0.08em;
    color: var(--accent-yellow);
    text-transform: uppercase;
  }}
  .hero-sub {{
    margin: 3px 0 0 0;
    font-size: 12px;
    color: var(--accent-cyan);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  .build-pill {{
    background: rgba(0, 240, 255, 0.1);
    border: 1px solid rgba(0, 240, 255, 0.45);
    color: var(--accent-cyan);
    padding: 6px 12px;
    border-radius: 6px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
  }}
  .meta-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
  }}
  .meta-card {{
    background: var(--bg-card);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 10px 14px;
  }}
  .meta-label {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    font-weight: 700;
  }}
  .meta-val {{
    margin-top: 4px;
    font-size: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: #FFFFFF;
    word-break: break-all;
  }}
  .kpi-row {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin: 16px 0 22px 0;
  }}
  .kpi-box {{
    background: #090A0F;
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 10px 12px;
    text-align: center;
  }}
  .kpi-num {{
    font-size: 20px;
    font-weight: 900;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  .kpi-lbl {{
    font-size: 10px;
    text-transform: uppercase;
    color: var(--text-muted);
    letter-spacing: 0.06em;
  }}
  h2 {{
    color: var(--accent-cyan);
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    border-bottom: 1px solid var(--border-dim);
    padding-bottom: 6px;
    margin-top: 28px;
  }}
  h3 {{
    color: var(--accent-yellow);
    font-size: 14px;
    margin-top: 20px;
    margin-bottom: 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  code {{
    background-color: #090A0F;
    border: 1px solid #222432;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--accent-cyan);
    font-size: 12px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    background-color: var(--bg-card);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    overflow: hidden;
    font-size: 12px;
  }}
  th, td {{
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-dim);
    text-align: left;
  }}
  th {{
    background-color: #090A0F;
    color: var(--accent-yellow);
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.06em;
  }}
  .finding-card {{
    background: var(--bg-card);
    border: 1px solid var(--border-dim);
    border-left: 3px solid var(--accent-cyan);
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 14px;
  }}
  .finding-card ul {{
    margin: 8px 0;
    padding-left: 18px;
    font-size: 12px;
  }}
  blockquote {{
    border-left: 3px solid var(--accent-yellow);
    padding: 8px 12px;
    margin: 10px 0 0 0;
    color: var(--text-main);
    background-color: #090A0F;
    border-radius: 0 4px 4px 0;
    font-size: 12px;
  }}
  .badge-CRITICAL, .badge-DETECTED {{
    background-color: rgba(255, 0, 60, 0.16);
    border: 1px solid #FF003C;
    color: #FF5C83;
    font-weight: 800;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: ui-monospace, monospace;
  }}
  .badge-WARNING {{
    background-color: rgba(245, 158, 11, 0.16);
    border: 1px solid #F59E0B;
    color: #FBBF24;
    font-weight: 800;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: ui-monospace, monospace;
  }}
  .badge-INFO {{
    background-color: rgba(0, 240, 255, 0.14);
    border: 1px solid #00F0FF;
    color: #00F0FF;
    font-weight: 800;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: ui-monospace, monospace;
  }}
  .badge-FIXED {{
    background-color: rgba(0, 255, 102, 0.14);
    border: 1px solid #00FF66;
    color: #4ADE80;
    font-weight: 800;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: ui-monospace, monospace;
  }}
  .sig-panel {{
    background: var(--bg-card);
    border: 1px solid var(--border-dim);
    border-radius: 6px;
    padding: 14px 16px;
    font-size: 12px;
  }}
  .footer-note {{
    margin-top: 28px;
    padding-top: 14px;
    border-top: 1px solid var(--border-dim);
    font-size: 11px;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
    font-family: ui-monospace, monospace;
  }}
  @media print {{
    body {{ background: #ffffff; color: #0f172a; padding: 0; }}
    .report-shell {{ background: #ffffff; border: none; box-shadow: none; padding: 16px; }}
    .meta-card, .kpi-box, .finding-card, .sig-panel, table {{ background: #f8fafc; border-color: #cbd5e1; color: #0f172a; }}
    th {{ background: #e2e8f0; color: #0f172a; }}
    .hero-title, h2, h3 {{ color: #0f172a; }}
    .meta-val, code, blockquote {{ color: #0f172a; background: #f1f5f9; border-color: #cbd5e1; }}
  }}
</style>
</head>
<body>
<div class="report-shell">
  <div class="hero-header">
    <div class="hero-brand">
      <svg width="38" height="38" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <polygon points="32,6 58,52 6,52" fill="#12131A" stroke="#00F0FF" stroke-width="2.5"/>
        <line x1="4" y1="34" x2="22" y2="34" stroke="#FF003C" stroke-width="2.5"/>
        <line x1="36" y1="28" x2="60" y2="20" stroke="#F59E0B" stroke-width="2"/>
        <line x1="38" y1="34" x2="60" y2="34" stroke="#00FF66" stroke-width="2"/>
        <line x1="36" y1="40" x2="60" y2="48" stroke="#00F0FF" stroke-width="2"/>
      </svg>
      <div>
        <h1 class="hero-title">SPECTRA Firmware Inspector Report</h1>
        <p class="hero-sub">Binary &amp; Localization Audit • Container: {safe_container} • Locale: {esc(str(target_locale))}</p>
      </div>
    </div>
    <div class="build-pill">BUILD {safe_build}</div>
  </div>

  <div class="meta-grid">
    <div class="meta-card"><div class="meta-label">Target Binary</div><div class="meta-val">{safe_bin_name}</div></div>
    <div class="meta-card"><div class="meta-label">File Size</div><div class="meta-val">{self.file_size:,} bytes</div></div>
    <div class="meta-card"><div class="meta-label">Signature Status</div><div class="meta-val">{safe_sig_status}</div></div>
    <div class="meta-card"><div class="meta-label">Audit Timestamp</div><div class="meta-val">{safe_ts}</div></div>
  </div>
  <div class="meta-card" style="margin-bottom: 20px;">
    <div class="meta-label">Binary Path &amp; SHA-256</div>
    <div class="meta-val">{safe_bin_path}<br>SHA-256: {safe_sha}</div>
  </div>

  <h2>1. Executive Summary</h2>
  <p>An automated static firmware and localization audit was conducted on <code>{safe_bin_name}</code> [<code>{safe_container}</code>].</p>
  <div class="kpi-row">
    <div class="kpi-box"><div class="kpi-num" style="color:#00F0FF;">{len(findings)}</div><div class="kpi-lbl">Total Findings</div></div>
    <div class="kpi-box"><div class="kpi-num" style="color:#FF5C83;">{critical_cnt}</div><div class="kpi-lbl">Critical</div></div>
    <div class="kpi-box"><div class="kpi-num" style="color:#FBBF24;">{warning_cnt}</div><div class="kpi-lbl">Warnings</div></div>
    <div class="kpi-box"><div class="kpi-num" style="color:#4ADE80;">{fixed_cnt}</div><div class="kpi-lbl">Patched / Fixed</div></div>
  </div>

  <table>
    <thead>
      <tr><th>ID</th><th>Severity</th><th>Category</th><th>Locale</th><th>Key</th><th>Status</th></tr>
    </thead>
    <tbody>
"""
        for f in findings:
            html_content += f"""      <tr>
        <td><code>{esc(str(f.get('id', 'DEFECT')))}</code></td>
        <td><span class="badge-{esc(str(f.get('severity', 'INFO')))}">{esc(str(f.get('severity', 'INFO')))}</span></td>
        <td>{esc(str(f.get('category', '')))}</td>
        <td><code>{esc(str(f.get('locale', '')))}</code></td>
        <td><code>{esc(str(f.get('key', '')))}</code></td>
        <td><span class="badge-{esc(str(f.get('status', '')))}">{esc(str(f.get('status', '')))}</span></td>
      </tr>\n"""

        html_content += """    </tbody>
  </table>

  <h2>2. Technical Findings &amp; Root Cause Analysis</h2>
"""
        for f in findings:
            vma_val = f.get("vma")
            off_val = f.get("file_offset")
            vma_str = f"0x{vma_val:08x}" if isinstance(vma_val, int) else str(vma_val or "0x00000000")
            off_str = f"0x{off_val:08x}" if isinstance(off_val, int) else str(off_val or "0x00000000")
            html_content += f"""  <div class="finding-card">
    <h3>{esc(str(f.get('id', 'DEFECT')))}: {esc(str(f.get('key', '')))} ({esc(str(f.get('locale', '')))})</h3>
    <ul>
      <li><strong>Severity:</strong> <span class="badge-{esc(str(f.get('severity', 'INFO')))}">{esc(str(f.get('severity', 'INFO')))}</span></li>
      <li><strong>Category:</strong> {esc(str(f.get('category', '')))}</li>
      <li><strong>Current Value:</strong> <code>{esc(str(f.get('current_val', '')))}</code></li>
      <li><strong>Expected Value:</strong> <code>{esc(str(f.get('expected_val', '')))}</code></li>
      <li><strong>VMA / Offset:</strong> <code>{esc(vma_str)}</code> / <code>{esc(off_str)}</code></li>
      <li><strong>Remediation Status:</strong> <span class="badge-{esc(str(f.get('status', '')))}">{esc(str(f.get('status', '')))}</span></li>
    </ul>
    <blockquote>{esc(str(f.get('description', '')))}</blockquote>
  </div>
"""

        html_content += f"""  <h2>3. Cryptographic Signature &amp; Update Pipeline Warning</h2>
  <div class="sig-panel">
    <p style="margin:0 0 6px 0;"><strong>Signature File:</strong> <code>{safe_sig_path}</code></p>
    <p style="margin:0 0 6px 0;"><strong>Signature Container:</strong> {safe_sig_desc}</p>
    <p style="margin:0;"><strong>Advisory:</strong> {safe_sig_warn}</p>
  </div>

  <h2>4. Laboratory Binary Patch Verification Matrix</h2>
  <p>All identified defects can be safely corrected in laboratory binaries via dynamic pointer repointing and instruction updates.</p>

  <div class="footer-note">
    <span>SPECTRA Firmware Inspector</span>
    <span>Build {safe_build}</span>
  </div>
</div>
</body>
</html>
"""

        if format_type == "html":
            _atomic_write_text(output_path, html_content)
            return output_path

        if format_type == "pdf":
            # Convert via headless LibreOffice (cross-platform Linux/Windows/macOS)
            out_dir = os.path.dirname(output_path) or "."
            os.makedirs(out_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
                tf.write(html_content)
                temp_html = tf.name

            try:
                lo_bin = shutil.which("libreoffice") or shutil.which("soffice")
                if not lo_bin and os.name == "nt":
                    for cand in [
                        r"C:\Program Files\LibreOffice\program\soffice.exe",
                        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                    ]:
                        if os.path.isfile(cand):
                            lo_bin = cand
                            break

                lo_cmd = [lo_bin or "libreoffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, temp_html]
                cmd_flags = {"creationflags": 0x08000000} if os.name == "nt" else {}
                subprocess.run(
                    lo_cmd,
                    check=True,
                    capture_output=True,
                    timeout=30,
                    **cmd_flags
                )
                base_temp = os.path.splitext(os.path.basename(temp_html))[0]
                gen_pdf = os.path.join(out_dir, f"{base_temp}.pdf")
                if os.path.isfile(gen_pdf):
                    if os.path.islink(output_path):
                        raise ValueError(f"Refusing to write PDF report to symlink target: {output_path}")
                    os.replace(gen_pdf, output_path)
            except Exception:
                # Fallback to HTML if libreoffice fails
                fallback_html = f"{os.path.splitext(output_path)[0]}.html"
                _atomic_write_text(fallback_html, html_content)
                return fallback_html
            finally:
                if os.path.exists(temp_html):
                    os.unlink(temp_html)

            return output_path

        # Default fallback write markdown
        _atomic_write_text(output_path, md_content)
        return output_path

