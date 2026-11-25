#!/usr/bin/env python3
"""SPECTRA Memory Mapper legacy GTK3 graphical interface."""

import os
import datetime
import threading
import time
from typing import Dict, List, Optional, Any

import serial_io

try:
    from version import __version__, __build__
except ImportError:
    __build__ = "20261112.1820"
    __version__ = f"Build {__build__}"

from spectra_mapper.models import (
    STATUS_MAPPED,
    STATUS_THEORETICAL,
    STATUS_UNKNOWN,
    STATUS_BLANK,
    RegisterEntry,
)
from spectra_mapper.engine import MemoryMapperEngine

# ============================================================================
# GTK Graphical Interface (MemoryMapperWindow)
# ============================================================================

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib, Pango
    HAS_GTK = True
except Exception:
    HAS_GTK = False


if HAS_GTK:
    class MemoryMapperWindow(Gtk.Window):
        """
        GTK3 Developer Memory Mapper & Differential Scope Window.
        Provides visual register grid, 16-bit binary inspector, live delta pulse,
        and quick-mapping dialog for filling community blanks.
        """

        def __init__(self, parent_app=None, initial_port: Optional[str] = ""):
            super().__init__(title=f"SPECTRA — Developer Memory Mapper & Differential Logic Scope (Build {__build__})")
            self.parent_app = parent_app
            self.initial_port = initial_port

            self.set_default_size(1080, 720)
            self.set_size_request(800, 520)
            self.set_position(Gtk.WindowPosition.CENTER)

            if parent_app and hasattr(parent_app, "get_icon"):
                icon = parent_app.get_icon()
                if icon:
                    self.set_icon(icon)

            self.conn: Optional[serial_io.JuraSerialConnection] = None
            self.engine: Optional[MemoryMapperEngine] = None
            self.engine_lock = threading.Lock()
            self.is_sweeping: bool = False
            self.is_capturing_baseline: bool = False
            self.is_watching: bool = False
            self.watch_thread: Optional[threading.Thread] = None
            self.mask_noise: bool = True
            self.current_filter: str = "all"
            self.search_query: str = ""
            self.current_selected_addr: Optional[int] = None
            self.row_iters: Dict[int, Gtk.TreeIter] = {}
            self.prev_row_values: Dict[int, tuple] = {}

            self._apply_css()
            self._create_ui()
            self.connect("destroy", self._on_destroy)

            # Connect port asynchronously
            if initial_port is not None:
                if initial_port:
                    self._connect_to_port(initial_port)
                else:
                    self._connect_to_port("DEMO / SIMULATION (Jura Impressa XJ5)")

        def _on_destroy(self, *args):
            """Cleanly terminate background threads when window is closed."""
            self.is_watching = False

        def _apply_css(self):
            css_provider = Gtk.CssProvider()
            css = b"""
            window {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: sans-serif;
            }
            .header-box {
                background-color: #181825;
                border-bottom: 1px solid #313244;
                padding: 10px 14px;
            }
            .pill-badge {
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
                transition: all 200ms ease-in-out;
            }
            .pill-badge:hover {
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
            }
            .badge-mapped {
                background-color: #1b382b;
                color: #a6e3a1;
                border: 1px solid #a6e3a1;
            }
            .badge-theor {
                background-color: #3e2b17;
                color: #fab387;
                border: 1px solid #fab387;
            }
            .badge-unknown {
                background-color: #3b1c24;
                color: #f38ba8;
                border: 1px solid #f38ba8;
            }
            .badge-blank {
                background-color: #181825;
                color: #6c7086;
                border: 1px solid #45475a;
            }
            .badge-changed {
                background-color: #1a324b;
                color: #89dceb;
                border: 1px solid #89dceb;
            }

            button {
                border-radius: 6px;
                min-height: 28px;
                transition: all 200ms ease-in-out;
            }

            button.primary-btn {
                background-image: linear-gradient(to bottom, #89b4fa, #74c7ec);
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 16px;
                border: 1px solid #74c7ec;
                min-height: 28px;
                transition: all 200ms ease-in-out;
            }
            button.primary-btn:hover {
                background-image: linear-gradient(to bottom, #b4befe, #89b4fa);
                border-color: #b4befe;
                box-shadow: 0 2px 10px rgba(137, 180, 250, 0.4);
            }
            button.primary-btn:active {
                background-image: linear-gradient(to bottom, #74c7ec, #89b4fa);
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
            }
            button.primary-btn:disabled {
                background-image: none;
                background-color: #313244;
                color: #585b70;
                border: 1px solid #45475a;
                box-shadow: none;
            }

            button.secondary-btn {
                background-color: #24273a;
                background-image: none;
                color: #cdd6f4;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #45475a;
                min-height: 28px;
                font-weight: 500;
                transition: all 200ms ease-in-out;
            }
            button.secondary-btn:hover {
                background-color: #313244;
                border-color: #89b4fa;
                color: #89b4fa;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            }
            button.secondary-btn:active {
                background-color: #181825;
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
            }
            button.secondary-btn:disabled {
                background-color: #1e1e2e;
                color: #585b70;
                border-color: #313244;
                box-shadow: none;
            }

            button.toggle-btn {
                background-color: #24273a;
                background-image: none;
                color: #cdd6f4;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #45475a;
                min-height: 28px;
                font-weight: 500;
                transition: all 200ms ease-in-out;
            }
            button.toggle-btn:hover {
                background-color: #313244;
                border-color: #585b70;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
            }
            button.toggle-btn:checked {
                background-color: #a6e3a1;
                background-image: linear-gradient(to bottom, #a6e3a1, #94e2d5);
                color: #11111b;
                font-weight: bold;
                border: 1px solid #a6e3a1;
                box-shadow: 0 0 12px rgba(166, 227, 161, 0.45);
            }
            button.toggle-btn:checked:hover {
                background-image: linear-gradient(to bottom, #b4befe, #89b4fa);
                border-color: #b4befe;
                color: #11111b;
            }

            button.action-btn {
                background-image: linear-gradient(to bottom, #fab387, #f9e2af);
                color: #11111b;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
                border: 1px solid #fab387;
                min-height: 28px;
                transition: all 200ms ease-in-out;
            }
            button.action-btn:hover {
                background-image: linear-gradient(to bottom, #f9e2af, #fab387);
                border-color: #f9e2af;
                box-shadow: 0 2px 10px rgba(250, 179, 135, 0.4);
            }
            button.action-btn:active {
                background-image: linear-gradient(to bottom, #fab387, #e0a37e);
                box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.4);
            }
            button.action-btn:disabled {
                background-image: none;
                background-color: #313244;
                color: #585b70;
                border-color: #45475a;
                box-shadow: none;
            }

            .filter-pill {
                background-color: #24273a;
                background-image: none;
                color: #a6adc8;
                border: 1px solid #363a4f;
                border-radius: 14px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 500;
                min-height: 26px;
                transition: all 180ms ease-in-out;
            }
            .filter-pill:hover {
                background-color: #313244;
                color: #cdd6f4;
                border-color: #585b70;
            }
            .filter-pill:checked {
                background-color: #89b4fa;
                background-image: linear-gradient(to bottom, #89b4fa, #74c7ec);
                color: #11111b;
                font-weight: bold;
                border-color: #89b4fa;
                box-shadow: 0 0 10px rgba(137, 180, 250, 0.4);
            }

            entry {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px 8px;
                transition: all 200ms ease-in-out;
            }
            entry:focus {
                border-color: #89b4fa;
                box-shadow: 0 0 6px rgba(137, 180, 250, 0.35);
            }

            treeview {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
            }
            treeview:selected {
                background-color: #45475a;
                color: #cdd6f4;
            }

            .bit-btn {
                font-family: monospace;
                font-size: 12px;
                font-weight: bold;
                min-width: 28px;
                padding: 4px 6px;
                border-radius: 4px;
                border: 1px solid #45475a;
                background-color: #181825;
                color: #6c7086;
                transition: all 150ms ease-in-out;
            }
            .bit-btn:hover {
                border-color: #89b4fa;
                color: #cdd6f4;
                background-color: #24273a;
            }
            .bit-on {
                background-color: #1b382b;
                color: #a6e3a1;
                border-color: #a6e3a1;
                box-shadow: 0 0 8px rgba(166, 227, 161, 0.35);
            }
            .bit-flipped {
                background-color: #3e2b17;
                color: #f9e2af;
                border-color: #f9e2af;
                box-shadow: 0 0 10px rgba(249, 226, 175, 0.5);
            }

            textview text {
                background-color: #11111b;
                color: #a6e3a1;
                font-family: monospace;
                font-size: 11px;
            }
            """
            css_provider.load_from_data(css)
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        def _create_ui(self):
            main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self.add(main_vbox)

            # 1. Header Toolbar
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            header_box.get_style_context().add_class("header-box")
            main_vbox.pack_start(header_box, False, False, 0)

            title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl_title = Gtk.Label()
            lbl_title.set_markup("<b><span size='large' color='#89b4fa'>🔬 SPECTRA Memory Mapper</span> <span color='#fab387' size='small'>Dev Logic Scope</span></b>")
            lbl_title.set_xalign(0.0)
            title_vbox.pack_start(lbl_title, False, False, 0)

            self.lbl_subtitle = Gtk.Label(label="Connecting to target machine...")
            self.lbl_subtitle.set_xalign(0.0)
            title_vbox.pack_start(self.lbl_subtitle, False, False, 0)
            header_box.pack_start(title_vbox, False, False, 0)

            # Spacer
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            header_box.pack_start(spacer, True, True, 0)

            # Stats Pills
            self.pill_mapped = Gtk.Label(label="🟢 0 Mapped")
            self.pill_mapped.get_style_context().add_class("pill-badge")
            self.pill_mapped.get_style_context().add_class("badge-mapped")
            header_box.pack_start(self.pill_mapped, False, False, 0)

            self.pill_theor = Gtk.Label(label="🟠 0 Theor.")
            self.pill_theor.get_style_context().add_class("pill-badge")
            self.pill_theor.get_style_context().add_class("badge-theor")
            header_box.pack_start(self.pill_theor, False, False, 0)

            self.pill_unknown = Gtk.Label(label="🔴 0 Unknown")
            self.pill_unknown.get_style_context().add_class("pill-badge")
            self.pill_unknown.get_style_context().add_class("badge-unknown")
            header_box.pack_start(self.pill_unknown, False, False, 0)

            self.pill_blank = Gtk.Label(label="⚪ 0 Blank")
            self.pill_blank.get_style_context().add_class("pill-badge")
            self.pill_blank.get_style_context().add_class("badge-blank")
            header_box.pack_start(self.pill_blank, False, False, 0)

            self.pill_changed = Gtk.Label(label="⚡ 0 Delta")
            self.pill_changed.get_style_context().add_class("pill-badge")
            self.pill_changed.get_style_context().add_class("badge-changed")
            header_box.pack_start(self.pill_changed, False, False, 0)

            # Control Action Buttons
            self.btn_sweep = Gtk.Button(label="⚡ Full Sweep")
            self.btn_sweep.get_style_context().add_class("primary-btn")
            self.btn_sweep.connect("clicked", lambda w: self._on_sweep_clicked())
            header_box.pack_start(self.btn_sweep, False, False, 0)

            self.btn_baseline = Gtk.Button(label="📸 Baseline")
            self.btn_baseline.get_style_context().add_class("secondary-btn")
            self.btn_baseline.set_tooltip_text("Capture current EEPROM values as baseline reference")
            self.btn_baseline.connect("clicked", lambda w: self._on_baseline_clicked())
            header_box.pack_start(self.btn_baseline, False, False, 0)

            self.btn_watch = Gtk.ToggleButton(label="⏱️ Live Diff")
            self.btn_watch.get_style_context().add_class("toggle-btn")
            self.btn_watch.set_tooltip_text("Continuously poll and display real-time memory modifications")
            self.btn_watch.connect("toggled", self._on_watch_toggled)
            header_box.pack_start(self.btn_watch, False, False, 0)

            # 2. Filter & Search Strip
            filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            filter_box.set_border_width(8)
            main_vbox.pack_start(filter_box, False, False, 0)

            lbl_search = Gtk.Label(label="🔍 Filter:")
            filter_box.pack_start(lbl_search, False, False, 0)

            self.search_entry = Gtk.SearchEntry()
            self.search_entry.set_placeholder_text("Address (e.g. 0040) or Name...")
            self.search_entry.connect("search-changed", self._on_search_changed)
            filter_box.pack_start(self.search_entry, True, True, 0)

            # Filter Radio/Pills
            self.filter_buttons = {}
            max_w = self.engine.max_words if self.engine else 512
            for tag, lbl in [("all", f"All ({max_w})"), ("mapped", "🟢 Mapped"), ("theor", "🟠 Theor."),
                             ("unknown", "🔴 Unknown"), ("changed", "⚡ Changed")]:
                btn = Gtk.RadioButton.new_with_label_from_widget(
                    self.filter_buttons.get("all"), lbl
                )
                btn.set_mode(False)
                btn.get_style_context().add_class("filter-pill")
                btn.connect("toggled", self._on_filter_toggled, tag)
                filter_box.pack_start(btn, False, False, 0)
                self.filter_buttons[tag] = btn

            # Map Register Action
            self.btn_map_action = Gtk.Button(label="✏️ Map Register...")
            self.btn_map_action.get_style_context().add_class("action-btn")
            self.btn_map_action.set_tooltip_text("Open mapping editor to name and persist selected register")
            self.btn_map_action.connect("clicked", lambda w: self._on_map_dialog_clicked())
            filter_box.pack_start(self.btn_map_action, False, False, 4)

            # 3. Main TreeView Split Paned
            paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
            paned.set_position(420)
            main_vbox.pack_start(paned, True, True, 0)

            # TreeView & ListStore
            # Store columns: 0: StatusText, 1: AddrHex, 2: ValHex, 3: ValDec, 4: DeltaHex, 5: Name, 6: Desc, 7: Cat, 8: AddrInt, 9: PangoMarkup
            self.store = Gtk.ListStore(str, str, str, str, str, str, str, str, int, str)
            self.tree_filter = self.store.filter_new()
            self.tree_filter.set_visible_func(self._filter_row_visible)

            self.tree = Gtk.TreeView(model=self.tree_filter)
            self.tree.get_selection().connect("changed", self._on_tree_selection_changed)
            self.tree.connect("row-activated", lambda t, p, c: self._on_map_dialog_clicked())

            cols = [
                ("Status", 0, 110),
                ("Address", 1, 80),
                ("Hex", 2, 70),
                ("Dec", 3, 70),
                ("Baseline / Delta", 4, 120),
                ("Register Name", 5, 200),
                ("Description", 6, 260),
                ("Category", 7, 100),
            ]

            for title, col_idx, width in cols:
                renderer = Gtk.CellRendererText()
                if col_idx in (1, 2, 3, 4):
                    renderer.set_property("family", "monospace")
                col = Gtk.TreeViewColumn(title, renderer, markup=9 if col_idx == 0 else col_idx)
                col.set_resizable(True)
                col.set_min_width(width)
                self.tree.append_column(col)

            scrolled_tree = Gtk.ScrolledWindow()
            scrolled_tree.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled_tree.add(self.tree)
            paned.pack1(scrolled_tree, True, False)

            # 4. Bottom Detail & Bitfield Inspector
            bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            bottom_box.set_border_width(10)
            paned.pack2(bottom_box, False, False)

            # Left Inspector Pane (16-bit binary)
            inspector_frame = Gtk.Frame(label="16-Bit Register Bitfield & Data Breakdown")
            inspector_frame.set_hexpand(True)
            bottom_box.pack_start(inspector_frame, True, True, 0)

            insp_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            insp_vbox.set_border_width(8)
            inspector_frame.add(insp_vbox)

            # Bit Indicator Buttons (b15 .. b0)
            bit_grid = Gtk.Grid()
            bit_grid.set_column_spacing(4)
            bit_grid.set_row_spacing(2)
            insp_vbox.pack_start(bit_grid, False, False, 0)

            self.bit_labels = []
            for b in range(15, -1, -1):
                col_pos = 15 - b
                lbl_b = Gtk.Label(label=f"b{b}")
                lbl_b.get_style_context().add_class("card-label")
                bit_grid.attach(lbl_b, col_pos, 0, 1, 1)

                btn_bit = Gtk.Label(label="0")
                btn_bit.get_style_context().add_class("bit-btn")
                btn_bit.set_size_request(28, 24)
                bit_grid.attach(btn_bit, col_pos, 1, 1, 1)
                self.bit_labels.append(btn_bit)

            # Values row
            self.lbl_insp_breakdown = Gtk.Label()
            self.lbl_insp_breakdown.set_markup("Select any register to inspect bitfield and values.")
            self.lbl_insp_breakdown.set_xalign(0.0)
            insp_vbox.pack_start(self.lbl_insp_breakdown, False, False, 0)

            # Right Pane: Differential Event Stream
            log_frame = Gtk.Frame(label="Live Differential Event Scope")
            log_frame.set_size_request(380, -1)
            bottom_box.pack_start(log_frame, False, False, 0)

            scrolled_log = Gtk.ScrolledWindow()
            self.log_buffer = Gtk.TextBuffer()
            self.log_view = Gtk.TextView(buffer=self.log_buffer)
            self.log_view.set_editable(False)
            self.log_view.set_cursor_visible(False)
            scrolled_log.add(self.log_view)
            log_frame.add(scrolled_log)

            self._log_event("Memory Mapper initialized. Ready for sweeps.")

        def _log_event(self, msg: str):
            t = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{t}] {msg}\n"
            GLib.idle_add(self._append_log_text, line)

        def _append_log_text(self, text: str):
            self.log_buffer.insert(self.log_buffer.get_end_iter(), text)
            # Bound buffer to last 200 lines
            if self.log_buffer.get_line_count() > 200:
                start = self.log_buffer.get_start_iter()
                end = self.log_buffer.get_iter_at_line(50)
                self.log_buffer.delete(start, end)
            adj = self.log_view.get_vadjustment()
            if adj:
                adj.set_value(adj.get_upper() - adj.get_page_size())

        def _connect_to_port(self, port_name: str):
            self.lbl_subtitle.set_markup(f"<i>Connecting to {GLib.markup_escape_text(str(port_name))}...</i>")
            self.btn_sweep.set_sensitive(False)
            self.btn_baseline.set_sensitive(False)
            self.btn_watch.set_sensitive(False)
            self.btn_map_action.set_sensitive(False)

            def worker():
                try:
                    with self.engine_lock:
                        self.conn = serial_io.JuraSerialConnection(port_name)
                        self.engine = MemoryMapperEngine(self.conn)
                    GLib.idle_add(self._on_connect_success, port_name)
                except Exception as e:
                    GLib.idle_add(self._on_connect_failed, port_name, str(e))

            threading.Thread(target=worker, daemon=True).start()

        def _on_connect_success(self, port_name: str):
            if not self.engine:
                return
            model_str = f"{self.engine.model_family} ({self.engine.ef_code})"
            spec_str = os.path.basename(self.engine.spec_file_path or 'Draft')
            self.lbl_subtitle.set_markup(
                f"<b>Target:</b> {GLib.markup_escape_text(model_str)} | "
                f"<b>Port:</b> {GLib.markup_escape_text(str(port_name))} | "
                f"<b>Spec:</b> {GLib.markup_escape_text(spec_str)}"
            )
            self._log_event(f"Connected to {model_str} on {port_name}")

            self.btn_sweep.set_sensitive(True)
            self.btn_baseline.set_sensitive(True)
            self.btn_watch.set_sensitive(True)
            self.btn_map_action.set_sensitive(True)

            all_btn = self.filter_buttons.get("all")
            if all_btn:
                all_btn.set_label(f"All ({self.engine.max_words})")

            # Trigger initial background sweep
            self._on_sweep_clicked()

        def _on_connect_failed(self, port_name: str, err: str):
            self.lbl_subtitle.set_markup(f"<span color='#f38ba8'>Connection error: {GLib.markup_escape_text(str(err))}</span>")
            self._log_event(f"Error opening port {port_name}: {err}")
            self.btn_sweep.set_sensitive(True)

        def _on_sweep_clicked(self):
            if self.is_sweeping or not self.engine:
                return
            self.is_sweeping = True
            self.btn_sweep.set_sensitive(False)
            self.btn_sweep.set_label("⏳ Sweeping...")
            self.btn_baseline.set_sensitive(False)

            def worker():
                diff_res = None
                try:
                    with self.engine_lock:
                        self.engine.sweep_eeprom()
                        if not self.engine.baseline_snapshot:
                            self.engine.capture_baseline()
                        diff_res = self.engine.compute_diff(self.mask_noise)
                except Exception as e:
                    self._log_event(f"Sweep error: {e}")
                finally:
                    GLib.idle_add(self._on_sweep_done, diff_res)

            threading.Thread(target=worker, daemon=True).start()

        def _on_sweep_done(self, diff_res):
            self.btn_sweep.set_label("⚡ Full Sweep")
            self.btn_sweep.set_sensitive(True)
            self.btn_baseline.set_sensitive(True)
            self.is_sweeping = False
            if diff_res is not None:
                self._update_tree_model(diff_res)

        def _on_baseline_clicked(self):
            if not self.engine or self.is_sweeping or self.is_capturing_baseline:
                return
            self.is_capturing_baseline = True
            self.btn_baseline.set_sensitive(False)
            self.btn_baseline.set_label("⏳ Capturing...")

            def worker():
                diff = None
                try:
                    with self.engine_lock:
                        self.engine.capture_baseline()
                        diff = self.engine.compute_diff(self.mask_noise)
                except Exception as e:
                    self._log_event(f"Baseline error: {e}")
                finally:
                    GLib.idle_add(self._on_baseline_done, diff)

            threading.Thread(target=worker, daemon=True).start()

        def _on_baseline_done(self, diff):
            self.btn_baseline.set_label("📸 Baseline")
            self.btn_baseline.set_sensitive(True)
            self.is_capturing_baseline = False
            self._log_event("Captured new baseline reference.")
            if diff is not None:
                self._update_tree_model(diff)

        def _on_watch_toggled(self, btn):
            self.is_watching = btn.get_active()
            if self.is_watching:
                self.btn_watch.set_label("🔴 Live Diff [ON]")
                self._log_event("Live Differential Scope watch started.")
                self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
                self.watch_thread.start()
            else:
                self.btn_watch.set_label("⏱️ Live Diff")
                self._log_event("Live Differential Scope watch stopped.")

        def _watch_loop(self):
            while self.is_watching and self.engine:
                time.sleep(0.8)
                if not self.is_watching:
                    break
                # Non-blocking lock to avoid contention with manual sweeps
                acquired = self.engine_lock.acquire(blocking=False)
                if not acquired:
                    continue
                try:
                    self.engine.sweep_eeprom()
                    diff = self.engine.compute_diff(self.mask_noise)
                    changed = diff.get("changed_registers", [])
                    if changed:
                        for r in changed:
                            bits = ", ".join(f"b{b}" for b in r.bits_flipped)
                            self._log_event(f"⚡ 0x{r.hex_addr} ({r.name}): 0x{r.baseline_val:04X} -> 0x{r.val:04X} ({r.delta:+d}) [{bits}]")
                    GLib.idle_add(self._update_tree_model, diff)
                except Exception as e:
                    self._log_event(f"Watch error: {e}")
                    break
                finally:
                    self.engine_lock.release()

        def _get_badge_markup(self, status: str) -> str:
            if status == STATUS_MAPPED:
                return "<span color='#a6e3a1'>● Mapped</span>"
            elif status == STATUS_THEORETICAL:
                return "<span color='#fab387'>▲ Theor.</span>"
            elif status == STATUS_UNKNOWN:
                return "<span color='#f38ba8'>■ Unknown</span>"
            else:
                return "<span color='#6c7086'>○ Blank</span>"

        def _update_tree_model(self, diff_res):
            if not self.engine:
                return

            registers = self.engine.classified_registers
            if not registers:
                return

            # Fast in-place updates: only populate from scratch if row count changed or uninitialized
            if len(self.row_iters) != len(registers):
                self.store.clear()
                self.row_iters.clear()
                self.prev_row_values.clear()

                for r in registers:
                    badge_markup = self._get_badge_markup(r.status)
                    delta_str = f"0x{r.baseline_val:04X} ({r.delta:+d})" if r.is_changed else f"0x{r.baseline_val:04X} (+0)"
                    row_data = [
                        r.status,
                        f"0x{r.hex_addr}",
                        f"0x{r.val:04X}",
                        f"{r.val}",
                        delta_str,
                        r.name,
                        r.desc,
                        r.category,
                        r.addr,
                        badge_markup
                    ]
                    tree_iter = self.store.append(row_data)
                    self.row_iters[r.addr] = tree_iter
                    self.prev_row_values[r.addr] = (r.val, r.baseline_val, r.status, r.name, r.desc, r.is_changed)
                self.tree_filter.refilter()
            else:
                # IN-PLACE MUTATION: only update rows that actually changed!
                had_filter_impact = False
                for r in registers:
                    prev = self.prev_row_values.get(r.addr)
                    curr = (r.val, r.baseline_val, r.status, r.name, r.desc, r.is_changed)
                    if prev != curr:
                        tree_iter = self.row_iters.get(r.addr)
                        if tree_iter:
                            badge_markup = self._get_badge_markup(r.status)
                            delta_str = f"0x{r.baseline_val:04X} ({r.delta:+d})" if r.is_changed else f"0x{r.baseline_val:04X} (+0)"
                            self.store[tree_iter] = [
                                r.status,
                                f"0x{r.hex_addr}",
                                f"0x{r.val:04X}",
                                f"{r.val}",
                                delta_str,
                                r.name,
                                r.desc,
                                r.category,
                                r.addr,
                                badge_markup
                            ]
                            self.prev_row_values[r.addr] = curr
                            if (prev and prev[5] != curr[5]) or self.current_filter in ("changed", "unknown", "theor", "mapped"):
                                had_filter_impact = True

                if had_filter_impact:
                    self.tree_filter.refilter()
                    self._restore_selection()

            # Update scorecards
            stats = self.engine.get_summary_stats()
            self.pill_mapped.set_text(f"🟢 {stats['mapped']} Mapped")
            self.pill_theor.set_text(f"🟠 {stats['theoretical']} Theor.")
            self.pill_unknown.set_text(f"🔴 {stats['unknown']} Unknown")
            self.pill_blank.set_text(f"⚪ {stats['blank']} Blank")
            self.pill_changed.set_text(f"⚡ {stats['changed']} Delta")

            # Live update 16-bit inspector if currently inspected register changed
            if self.current_selected_addr is not None:
                self._update_inspector_for_addr(self.current_selected_addr)

        def _restore_selection(self):
            if self.current_selected_addr is None:
                return
            def find_row(model, path, iter, user_data):
                if model.get_value(iter, 8) == self.current_selected_addr:
                    user_data.append(path)
                    return True
                return False
            found = []
            self.tree_filter.foreach(find_row, found)
            if found:
                self.tree.get_selection().select_path(found[0])

        def _filter_row_visible(self, model, iter, data):
            if not self.engine:
                return True

            status = model.get_value(iter, 0) or ""
            addr_hex = (model.get_value(iter, 1) or "").lower()
            name = (model.get_value(iter, 5) or "").lower()
            desc = (model.get_value(iter, 6) or "").lower()
            delta_str = model.get_value(iter, 4) or ""

            # Search text query
            q = self.search_query.lower()
            if q:
                if q not in addr_hex and q not in name and q not in desc:
                    return False

            # Button filter
            if self.current_filter == "mapped":
                return status == STATUS_MAPPED
            elif self.current_filter == "theor":
                return status == STATUS_THEORETICAL
            elif self.current_filter == "unknown":
                return status == STATUS_UNKNOWN
            elif self.current_filter == "changed":
                return not delta_str.endswith("(+0)")
            return True

        def _on_filter_toggled(self, btn, tag):
            if btn.get_active():
                self.current_filter = tag
                self.tree_filter.refilter()
                self._restore_selection()

        def _on_search_changed(self, entry):
            self.search_query = entry.get_text().strip()
            self.tree_filter.refilter()
            self._restore_selection()

        def _on_tree_selection_changed(self, selection):
            model, tree_iter = selection.get_selected()
            if not tree_iter:
                return
            addr = model.get_value(tree_iter, 8)
            self.current_selected_addr = addr
            self._update_inspector_for_addr(addr)

        def _update_inspector_for_addr(self, addr: int):
            if not self.engine:
                return

            # Find matching RegisterEntry
            r_match = next((r for r in self.engine.classified_registers if r.addr == addr), None)
            if not r_match:
                return

            val = r_match.val
            base_val = r_match.baseline_val
            flipped_bits = r_match.bits_flipped
            name = r_match.name
            desc = r_match.desc

            # Update bit indicator buttons (b15 down to b0)
            for b in range(16):
                idx = 15 - b
                btn = self.bit_labels[idx]
                bit_val = (val >> b) & 1
                btn.set_text(str(bit_val))

                ctx = btn.get_style_context()
                ctx.remove_class("bit-on")
                ctx.remove_class("bit-flipped")

                if b in flipped_bits:
                    ctx.add_class("bit-flipped")
                elif bit_val:
                    ctx.add_class("bit-on")

            hb = (val >> 8) & 0xFF
            lb = val & 0xFF
            signed_val = val if val < 32768 else val - 65536
            c1 = chr(hb) if 32 <= hb <= 126 else "."
            c2 = chr(lb) if 32 <= lb <= 126 else "."

            delta_info = ""
            if r_match.is_changed:
                delta_info = f" | <span color='#89dceb'><b>Delta: {r_match.delta:+d} (Baseline: 0x{base_val:04X})</b></span>"

            markup = (
                f"<b>0x{addr:04X} ({GLib.markup_escape_text(str(name))}):</b> Hex <code>0x{val:04X}</code> | Dec: <code>{val}</code> (Signed: {signed_val}) | "
                f"High Byte: <code>0x{hb:02X}</code> ({hb}) | Low Byte: <code>0x{lb:02X}</code> ({lb}) | ASCII: '<code>{GLib.markup_escape_text(c1 + c2)}</code>'{delta_info}\n"
                f"<span color='#a6adc8'>{GLib.markup_escape_text(str(desc))}</span>"
            )
            self.lbl_insp_breakdown.set_markup(markup)

        def _on_map_dialog_clicked(self):
            selection = self.tree.get_selection()
            model, tree_iter = selection.get_selected()

            # Resilient selection: if None, restore from active address or first row
            if not tree_iter and self.current_selected_addr is not None:
                def find_row(model, path, iter, user_data):
                    if model.get_value(iter, 8) == self.current_selected_addr:
                        user_data.append(iter)
                        return True
                    return False
                found = []
                self.tree_filter.foreach(find_row, found)
                if found:
                    tree_iter = found[0]
                    self.tree.get_selection().select_iter(tree_iter)
                    model = self.tree_filter

            if not tree_iter:
                first_iter = self.tree_filter.get_iter_first()
                if first_iter:
                    tree_iter = first_iter
                    self.tree.get_selection().select_iter(tree_iter)
                    model = self.tree_filter
                else:
                    self._log_event("⚠️ Please select a register in the table before clicking Map Register.")
                    return

            addr = model.get_value(tree_iter, 8)
            val_hex = model.get_value(tree_iter, 2)
            name = model.get_value(tree_iter, 5)
            desc = model.get_value(tree_iter, 6)
            cat = model.get_value(tree_iter, 7)

            dialog = Gtk.Dialog(
                title=f"Map Register 0x{addr:04X} — Persist Model Specification",
                transient_for=self,
                flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                "💾 Save & Persist", Gtk.ResponseType.OK
            )
            dialog.set_default_size(440, 280)

            btn_ok = dialog.get_widget_for_response(Gtk.ResponseType.OK)
            if btn_ok:
                btn_ok.get_style_context().add_class("primary-btn")
            btn_cancel = dialog.get_widget_for_response(Gtk.ResponseType.CANCEL)
            if btn_cancel:
                btn_cancel.get_style_context().add_class("secondary-btn")

            content = dialog.get_content_area()
            content.set_spacing(10)
            content.set_border_width(12)

            grid = Gtk.Grid()
            grid.set_column_spacing(10)
            grid.set_row_spacing(8)
            content.pack_start(grid, True, True, 0)

            grid.attach(Gtk.Label(label="Register Address:"), 0, 0, 1, 1)
            lbl_addr = Gtk.Label(label=f"0x{addr:04X} ({val_hex})")
            lbl_addr.set_xalign(0.0)
            grid.attach(lbl_addr, 1, 0, 1, 1)

            grid.attach(Gtk.Label(label="Identifier Name:"), 0, 1, 1, 1)
            entry_name = Gtk.Entry()
            # If name is generic unmapped, leave empty for easy typing
            default_name = "" if name.startswith("Unmapped_0x") or name.startswith("Blank_0x") else name
            entry_name.set_text(default_name)
            entry_name.set_placeholder_text("e.g. Water_Hardness_dH")
            grid.attach(entry_name, 1, 1, 1, 1)

            grid.attach(Gtk.Label(label="Description:"), 0, 2, 1, 1)
            entry_desc = Gtk.Entry()
            entry_desc.set_text(desc if not desc.startswith("Model-specific") else "")
            entry_desc.set_placeholder_text("e.g. Water hardness level configured by user")
            grid.attach(entry_desc, 1, 2, 1, 1)

            grid.attach(Gtk.Label(label="Category:"), 0, 3, 1, 1)
            combo_cat = Gtk.ComboBoxText()
            for c in ["settings", "counters", "calibration", "hardware", "maintenance", "recipe", "faults", "spdl", "custom"]:
                combo_cat.append_text(c)
            combo_cat.set_active(0)
            grid.attach(combo_cat, 1, 3, 1, 1)

            grid.attach(Gtk.Label(label="Unit:"), 0, 4, 1, 1)
            entry_unit = Gtk.Entry()
            entry_unit.set_placeholder_text("e.g. °dH, dl, ticks, sec")
            grid.attach(entry_unit, 1, 4, 1, 1)

            grid.attach(Gtk.Label(label="Status:"), 0, 5, 1, 1)
            combo_status = Gtk.ComboBoxText()
            combo_status.append_text("🟢 Mapped (Confirmed)")
            combo_status.append_text("🟠 Theoretical (Unconfirmed)")
            combo_status.set_active(0)
            grid.attach(combo_status, 1, 5, 1, 1)

            dialog.show_all()
            resp = dialog.run()

            if resp == Gtk.ResponseType.OK:
                new_name = entry_name.get_text().strip()
                new_desc = entry_desc.get_text().strip()
                new_cat = combo_cat.get_active_text() or "settings"
                new_unit = entry_unit.get_text().strip()
                status_choice = STATUS_MAPPED if combo_status.get_active() == 0 else STATUS_THEORETICAL

                if new_name:
                    with self.engine_lock:
                        ok, msg = self.engine.map_register(
                            addr=addr,
                            name=new_name,
                            desc=new_desc,
                            category=new_cat,
                            unit=new_unit,
                            status=status_choice
                        )
                        diff_res = self.engine.compute_diff(self.mask_noise) if ok else None
                    if ok:
                        self._log_event(f"Mapped 0x{addr:04X} -> {new_name}")
                        self._update_tree_model(diff_res)
                    else:
                        self._log_event(f"Error mapping register: {msg}")

            dialog.destroy()

