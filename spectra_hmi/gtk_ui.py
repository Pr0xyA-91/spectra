#!/usr/bin/env python3
"""SPECTRA HMI legacy GTK3 visual inspector dialog."""

import os
import threading
from typing import Dict, List, Optional, Any

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib, Pango
    HAS_GTK = True
except Exception:
    HAS_GTK = False

from spectra_hmi.elf_tools import DEFAULT_KALERM_DIR, __build__
from spectra_hmi.inspector import KalermHmiInspector

if HAS_GTK:
    class HmiInspectorDialog(Gtk.Dialog):
        """
        SPECTRA GTK3 Dark Industrial HMI & Firmware Inspector Dialog.
        """

        def __init__(self, parent=None, initial_path: Optional[str] = None):
            super().__init__(
                title=f"SPECTRA — Kalerm HMI Firmware & Translation Auditor (Build {__build__})",
                transient_for=parent,
                modal=True,
                flags=0,
            )
            self.set_default_size(1120, 740)
            self.inspector: Optional[KalermHmiInspector] = None
            self.current_findings: List[Dict[str, Any]] = []

            # Store for Audit Tab:
            # 0: SeverityMarkup, 1: ID, 2: Category, 3: Locale, 4: CurrentVal, 5: ExpectedVal, 6: VmaOffset, 7: StatusMarkup
            self.audit_store = Gtk.ListStore(str, str, str, str, str, str, str, str)

            # Store for Explorer Tab:
            # 0: Index, 1: Key, 2: KeyVma, 3: Val, 4: ValVma, 5: FileOff, 6: EnRef
            self.explorer_store = Gtk.ListStore(int, str, str, str, str, str, str)
            self.explorer_filter = self.explorer_store.filter_new()
            self.explorer_filter.set_visible_func(self._explorer_filter_func)

            self._apply_css()
            self._build_ui()

            # Auto-load initial path or default directory
            load_target = initial_path
            if not load_target and os.path.isdir(DEFAULT_KALERM_DIR):
                load_target = DEFAULT_KALERM_DIR
            if load_target:
                self._load_binary(load_target)

        def _apply_css(self):
            css_provider = Gtk.CssProvider()
            css = b"""
            dialog, window {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            .header-bar {
                background-color: #181825;
                border-bottom: 1px solid #313244;
                padding: 10px 14px;
            }
            .pill-badge {
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            .badge-verified {
                background-color: #1b382b;
                color: #a6e3a1;
                border: 1px solid #a6e3a1;
            }
            .badge-warning {
                background-color: #3e2b17;
                color: #fab387;
                border: 1px solid #fab387;
            }
            .badge-critical {
                background-color: #3b1c24;
                color: #f38ba8;
                border: 1px solid #f38ba8;
            }
            button.primary-btn {
                background-image: linear-gradient(to bottom, #89b4fa, #74c7ec);
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #74c7ec;
            }
            button.action-btn {
                background-color: #313244;
                color: #cdd6f4;
                border-radius: 6px;
                padding: 6px 12px;
                border: 1px solid #45475a;
            }
            button.action-btn:hover {
                background-color: #45475a;
            }
            treeview {
                background-color: #181825;
                color: #cdd6f4;
            }
            treeview:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            """
            try:
                css_provider.load_from_data(css)
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(),
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )
            except Exception:
                pass

        def _build_ui(self):
            content_area = self.get_content_area()
            content_area.set_spacing(0)

            # Top Bar: File Picker, SHA-256, Signature Status
            top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            top_box.get_style_context().add_class("header-bar")
            content_area.pack_start(top_box, False, False, 0)

            row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            top_box.pack_start(row1, False, False, 0)

            lbl_path = Gtk.Label(label="Firmware Binary / Update Directory:")
            row1.pack_start(lbl_path, False, False, 0)

            self.entry_path = Gtk.Entry()
            self.entry_path.set_hexpand(True)
            self.entry_path.set_placeholder_text("Select firmware binary (ELF, .apk, .bin) or update directory...")
            self.entry_path.connect("activate", lambda e: self._load_binary(self.entry_path.get_text()))
            row1.pack_start(self.entry_path, True, True, 0)

            self.btn_browse = Gtk.Button(label="📂 Browse...")
            self.btn_browse.get_style_context().add_class("action-btn")
            self.btn_browse.connect("clicked", self._on_browse_clicked)
            row1.pack_start(self.btn_browse, False, False, 0)

            self.btn_autodetect = Gtk.Button(label="⚡ Auto-Detect V1.2.3")
            self.btn_autodetect.get_style_context().add_class("action-btn")
            self.btn_autodetect.connect("clicked", lambda b: self._load_binary(DEFAULT_KALERM_DIR))
            row1.pack_start(self.btn_autodetect, False, False, 0)

            # Row 2: Status Badges
            row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            top_box.pack_start(row2, False, False, 0)

            self.lbl_sha = Gtk.Label(label="SHA-256: (No binary loaded)")
            self.lbl_sha.get_style_context().add_class("pill-badge")
            self.lbl_sha.set_selectable(True)
            row2.pack_start(self.lbl_sha, False, False, 0)

            self.lbl_sig = Gtk.Label(label="Signature: N/A")
            self.lbl_sig.get_style_context().add_class("pill-badge")
            row2.pack_start(self.lbl_sig, False, False, 0)

            # Main Notebook
            self.notebook = Gtk.Notebook()
            content_area.pack_start(self.notebook, True, True, 0)

            # Tab 1: Audit Tab
            audit_page = self._build_audit_tab()
            self.notebook.append_page(audit_page, Gtk.Label(label="🛡️ Automated Firmware Audit"))

            # Tab 2: Explorer Tab
            explorer_page = self._build_explorer_tab()
            self.notebook.append_page(explorer_page, Gtk.Label(label="🔍 Translation & Pointer Explorer"))

            # Dialog Action Area
            btn_close = self.add_button("Close", Gtk.ResponseType.CLOSE)
            btn_close.get_style_context().add_class("action-btn")
            self.connect("response", lambda d, r: self.destroy())

            self.show_all()

        def _build_audit_tab(self) -> Gtk.Widget:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_border_width(10)

            # Action bar
            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.pack_start(bar, False, False, 0)

            lbl_title = Gtk.Label(label="<b>Firmware Safety &amp; Localization Audit Findings:</b>", use_markup=True)
            bar.pack_start(lbl_title, False, False, 0)

            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            bar.pack_start(spacer, True, True, 0)

            self.btn_patch = Gtk.Button(label="🩹 Patch Binary (Lab Copy)")
            self.btn_patch.get_style_context().add_class("primary-btn")
            self.btn_patch.connect("clicked", self._on_patch_clicked)
            bar.pack_start(self.btn_patch, False, False, 0)

            self.btn_export_report = Gtk.Button(label="📄 Export Bug Report (MD/PDF)")
            self.btn_export_report.get_style_context().add_class("action-btn")
            self.btn_export_report.connect("clicked", self._on_export_report_clicked)
            bar.pack_start(self.btn_export_report, False, False, 0)

            self.btn_refresh_audit = Gtk.Button(label="🔄 Re-Scan")
            self.btn_refresh_audit.get_style_context().add_class("action-btn")
            self.btn_refresh_audit.connect("clicked", lambda b: self._refresh_audit())
            bar.pack_start(self.btn_refresh_audit, False, False, 0)

            # Audit Paned
            paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
            paned.set_position(360)
            box.pack_start(paned, True, True, 0)

            # Audit TreeView
            self.audit_tree = Gtk.TreeView(model=self.audit_store)
            self.audit_tree.get_selection().connect("changed", self._on_audit_selection_changed)

            cols = [
                ("Severity", 0, 90),
                ("Finding ID", 1, 160),
                ("Category", 2, 170),
                ("Locale", 3, 70),
                ("Current Value", 4, 210),
                ("Target Fix", 5, 210),
                ("VMA / Offset", 6, 150),
                ("Status", 7, 90),
            ]
            for title, idx, width in cols:
                renderer = Gtk.CellRendererText()
                if idx in (0, 7):
                    col = Gtk.TreeViewColumn(title, renderer, markup=idx)
                else:
                    if idx in (1, 6):
                        renderer.set_property("family", "monospace")
                    col = Gtk.TreeViewColumn(title, renderer, text=idx)
                col.set_resizable(True)
                col.set_min_width(width)
                self.audit_tree.append_column(col)

            scrolled_audit = Gtk.ScrolledWindow()
            scrolled_audit.add(self.audit_tree)
            paned.pack1(scrolled_audit, True, False)

            # Detail Frame
            detail_frame = Gtk.Frame(label="Technical Root Cause & Remediation Specification")
            paned.pack2(detail_frame, False, False)

            self.lbl_audit_detail = Gtk.Label()
            self.lbl_audit_detail.set_line_wrap(True)
            self.lbl_audit_detail.set_xalign(0.0)
            self.lbl_audit_detail.set_margin_start(10)
            self.lbl_audit_detail.set_margin_end(10)
            self.lbl_audit_detail.set_margin_top(8)
            self.lbl_audit_detail.set_margin_bottom(8)
            self.lbl_audit_detail.set_markup("<i>Select any audit finding above to view technical details.</i>")
            detail_frame.add(self.lbl_audit_detail)

            return box

        def _build_explorer_tab(self) -> Gtk.Widget:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_border_width(10)

            # Filter row
            filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.pack_start(filter_box, False, False, 0)

            lbl_loc = Gtk.Label(label="Locale:")
            filter_box.pack_start(lbl_loc, False, False, 0)

            self.combo_locales = Gtk.ComboBoxText()
            self.combo_locales.connect("changed", self._on_locale_combo_changed)
            filter_box.pack_start(self.combo_locales, False, False, 0)

            lbl_search = Gtk.Label(label="Live Search:")
            filter_box.pack_start(lbl_search, False, False, 0)

            self.search_entry = Gtk.SearchEntry()
            self.search_entry.set_placeholder_text("Filter by key, translated string, or hex address...")
            self.search_entry.connect("search-changed", lambda e: self.explorer_filter.refilter())
            filter_box.pack_start(self.search_entry, True, True, 0)

            self.lbl_phrase_count = Gtk.Label(label="0 phrases")
            self.lbl_phrase_count.get_style_context().add_class("pill-badge")
            filter_box.pack_start(self.lbl_phrase_count, False, False, 0)

            # Explorer TreeView
            self.explorer_tree = Gtk.TreeView(model=self.explorer_filter)
            cols = [
                ("#", 0, 50),
                ("Key Identifier", 1, 220),
                ("Key VMA", 2, 95),
                ("Translation Value", 3, 260),
                ("Value VMA", 4, 95),
                ("File Offset", 5, 95),
                ("English Reference (en-GB)", 6, 260),
            ]
            for title, idx, width in cols:
                renderer = Gtk.CellRendererText()
                if idx in (0, 2, 4, 5):
                    renderer.set_property("family", "monospace")
                col = Gtk.TreeViewColumn(title, renderer, text=idx)
                col.set_resizable(True)
                col.set_min_width(width)
                self.explorer_tree.append_column(col)

            scrolled_exp = Gtk.ScrolledWindow()
            scrolled_exp.add(self.explorer_tree)
            box.pack_start(scrolled_exp, True, True, 0)

            return box

        def _explorer_filter_func(self, model, iter, data):
            query = self.search_entry.get_text().strip().lower()
            if not query:
                return True
            k = model.get_value(iter, 1).lower()
            v = model.get_value(iter, 3).lower()
            ref = model.get_value(iter, 6).lower()
            vma = model.get_value(iter, 4).lower()
            off = model.get_value(iter, 5).lower()
            return (query in k or query in v or query in ref or query in vma or query in off)

        def _on_browse_clicked(self, widget):
            dialog = Gtk.FileChooserDialog(
                title="Select Kalerm HMI Binary or Update Folder",
                parent=self,
                action=Gtk.FileChooserAction.OPEN,
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
            )
            filter_any = Gtk.FileFilter()
            filter_any.set_name("All Files / Binaries")
            filter_any.add_pattern("*")
            dialog.add_filter(filter_any)

            if dialog.run() == Gtk.ResponseType.OK:
                sel = dialog.get_filename()
                if sel:
                    self._load_binary(sel)
            dialog.destroy()

        def _load_binary(self, path: str):
            try:
                self.inspector = KalermHmiInspector(path)
                self.entry_path.set_text(self.inspector.binary_path)
                sig_info = self.inspector.verify_signature()

                sha_short = sig_info["sha256"][:16] + "..."
                self.lbl_sha.set_text(f"SHA-256: {sha_short}")
                self.lbl_sha.set_tooltip_text(sig_info["sha256"])

                sig_label = sig_info["status_label"]
                self.lbl_sig.set_text(f"Signature: {sig_label}")
                ctx = self.lbl_sig.get_style_context()
                ctx.remove_class("badge-verified")
                ctx.remove_class("badge-warning")
                ctx.remove_class("badge-critical")
                if "VERIFIED" in sig_label or "PRESENT" in sig_label:
                    ctx.add_class("badge-verified")
                else:
                    ctx.add_class("badge-critical")
                self.lbl_sig.set_tooltip_text(sig_info["warning"])

                # Populate locales combo
                langs = self.inspector.extract_all_languages()
                self.combo_locales.handler_block_by_func(self._on_locale_combo_changed)
                self.combo_locales.remove_all()
                default_idx = 0
                for i, loc in enumerate(langs.keys()):
                    self.combo_locales.append_text(loc)
                    if loc == "cs-CZ":
                        default_idx = i
                self.combo_locales.set_active(default_idx)
                self.combo_locales.handler_unblock_by_func(self._on_locale_combo_changed)

                self._refresh_audit()
                self._refresh_explorer()
            except Exception as e:
                msg = Gtk.MessageDialog(
                    transient_for=self,
                    modal=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Failed to inspect Kalerm binary",
                )
                msg.format_secondary_text(str(e))
                msg.run()
                msg.destroy()

        def _refresh_audit(self):
            if not self.inspector:
                return
            self.audit_store.clear()
            self.current_findings = self.inspector.run_audit()

            for f in self.current_findings:
                sev = f["severity"]
                if sev == "CRITICAL":
                    sev_m = '<span foreground="#f38ba8" weight="bold">🔴 CRITICAL</span>'
                elif sev == "WARNING":
                    sev_m = '<span foreground="#fab387" weight="bold">🟠 WARNING</span>'
                else:
                    sev_m = '<span foreground="#89b4fa" weight="bold">🔵 INFO</span>'

                st = f["status"]
                if st == "FIXED":
                    st_m = '<span foreground="#a6e3a1" weight="bold">🟢 FIXED</span>'
                else:
                    st_m = '<span foreground="#f38ba8" weight="bold">⚠️ DETECTED</span>'

                vma_off = f"0x{f['vma']:08x} / 0x{f['file_offset']:08x}"
                self.audit_store.append([
                    sev_m,
                    f["id"],
                    f["category"],
                    f["locale"],
                    f["current_val"],
                    f["expected_val"],
                    vma_off,
                    st_m,
                ])

        def _on_audit_selection_changed(self, selection):
            model, iter = selection.get_selected()
            if not iter:
                return
            finding_id = model.get_value(iter, 1)
            for f in self.current_findings:
                if f["id"] == finding_id:
                    text = (
                        f"<b>{f['id']}: {f['key']} ({f['locale']})</b>\n\n"
                        f"<b>Description:</b> {f['description']}\n"
                        f"<b>Current Value:</b> <code>{f['current_val']}</code>\n"
                        f"<b>Expected Value:</b> <code>{f['expected_val']}</code>\n"
                        f"<b>VMA:</b> 0x{f['vma']:08x} | <b>Physical File Offset:</b> 0x{f['file_offset']:08x}\n"
                        f"<b>Patchable:</b> {'Yes (Safe binary pointer repointing)' if f['patchable'] else 'No'}"
                    )
                    self.lbl_audit_detail.set_markup(text)
                    break

        def _on_locale_combo_changed(self, combo):
            self._refresh_explorer()

        def _refresh_explorer(self):
            if not self.inspector:
                return
            loc = self.combo_locales.get_active_text() or "cs-CZ"
            langs = self.inspector.extract_all_languages()
            lang_data = langs.get(loc, {})
            en_phrases = langs.get("en-GB", {}).get("phrases", {})

            self.explorer_store.clear()
            phrases = lang_data.get("phrases", {})
            for k, p in phrases.items():
                en_val = en_phrases.get(k, {}).get("val", "-")
                self.explorer_store.append([
                    p["index"],
                    p["key"],
                    f"0x{p['key_vma']:08x}",
                    p["val"],
                    f"0x{p['val_vma']:08x}",
                    f"0x{p['slot_file_off']:08x}",
                    en_val,
                ])
            self.lbl_phrase_count.set_text(f"{len(phrases)} phrases")

        def _on_patch_clicked(self, widget):
            if not self.inspector:
                return
            default_out = f"{os.path.splitext(self.inspector.binary_path)[0]}_patched"
            dialog = Gtk.FileChooserDialog(
                title="Save Patched Laboratory Binary Copy",
                parent=self,
                action=Gtk.FileChooserAction.SAVE,
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
            )
            dialog.set_current_name(os.path.basename(default_out))

            if dialog.run() == Gtk.ResponseType.OK:
                out_path = dialog.get_filename()
                dialog.destroy()
                if out_path:
                    try:
                        res = self.inspector.apply_patches(out_path)
                        info = Gtk.MessageDialog(
                            transient_for=self,
                            modal=True,
                            message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK,
                            text="Firmware Patched Successfully",
                        )
                        info.format_secondary_text(
                            f"Saved patched lab binary to:\n{res['output_path']}\n\n"
                            f"SHA-256: {res['sha256']}\n"
                            f"Patches applied: {len(res['patches_applied'])} operations.\n\n"
                            "Note: This laboratory binary can be run or tested directly on bench hardware."
                        )
                        info.run()
                        info.destroy()
                        # Auto-load the patched binary to view updated state
                        self._load_binary(out_path)
                    except Exception as e:
                        err = Gtk.MessageDialog(
                            transient_for=self,
                            modal=True,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Failed to patch binary",
                        )
                        err.format_secondary_text(str(e))
                        err.run()
                        err.destroy()
            else:
                dialog.destroy()

        def _on_export_report_clicked(self, widget):
            if not self.inspector:
                return
            dialog = Gtk.FileChooserDialog(
                title="Export Engineering Audit Report",
                parent=self,
                action=Gtk.FileChooserAction.SAVE,
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
            )
            dialog.set_current_name("Kalerm_HMI_Firmware_Audit_Report.md")

            if dialog.run() == Gtk.ResponseType.OK:
                out_path = dialog.get_filename()
                dialog.destroy()
                if out_path:
                    try:
                        saved = self.inspector.export_bug_report(out_path)
                        info = Gtk.MessageDialog(
                            transient_for=self,
                            modal=True,
                            message_type=Gtk.MessageType.INFO,
                            buttons=Gtk.ButtonsType.OK,
                            text="Audit Report Exported",
                        )
                        info.format_secondary_text(f"Report saved to:\n{saved}")
                        info.run()
                        info.destroy()
                    except Exception as e:
                        err = Gtk.MessageDialog(
                            transient_for=self,
                            modal=True,
                            message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.OK,
                            text="Failed to export report",
                        )
                        err.format_secondary_text(str(e))
                        err.run()
                        err.destroy()
            else:
                dialog.destroy()


def launch_hmi_inspector_gui(parent=None, initial_path: Optional[str] = None):
    """Convenience launcher for the GTK3 HMI Inspector Dialog."""
    if not HAS_GTK:
        raise RuntimeError("GTK3 is not available in the current environment.")
    dialog = HmiInspectorDialog(parent=parent, initial_path=initial_path)
    dialog.run()

