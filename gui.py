#!/usr/bin/env python3
"""
SPECTRA - Universal Hardware Telemetry & Logic Board Diagnostics - Desktop GUI
Multi-Manufacturer Edition (Jura, Nivona, Lamanti-KL / Kalerm, Lamanti-JN / Jetinno)

Includes:
- Interactive Hydraulic & Sensor Digital Twin (Cairo vector schematic)
- Real-Time Thermal & Flow Oscilloscope Strip Chart
- Executive Health Scorecard & Preventative Maintenance Advisor
- Visual Specialty Coffee Recipe & Volume Distribution
- Multi-Manufacturer Protocol Dispatch & WRAT Interrogation Engine
- Branded Customer Service PDF/HTML Inspection Certificate Generator
"""

import sys
import os
import re
import time
import math
import subprocess
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango, GdkPixbuf

import serial_io
import profiles_db
import stats_collector as sc
from spectra_engine import SpectraSession, WRATSession, format_text_summary, format_csv_summary
from drivers import DRIVER_DISPLAY_NAMES
import gui_widgets

try:
    from version import __version__, __build__
except ImportError:
    __version__ = "0.5.1_win"
    __build__ = "20261029.1130"


def is_dev_branch() -> bool:
    """Check if SPECTRA is running on a development branch/build."""
    if os.environ.get("SPECTRA_DEV", "").lower() in ("1", "true"):
        return True
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(repo_dir, "SESSION_NOTES.md")):
        return True
    try:
        import subprocess
        branch = subprocess.check_output(
            ["git", "-C", repo_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return branch in ("main", "multi-manufacturer", "windows", "dev")
    except Exception:
        return False


class JuraDiagApp(Gtk.Window):
    @staticmethod
    def _load_app_icon(size: int = 36) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Load application logo at specified size with graceful fallback.
        Prioritizes vector SVG, falls back to PNG.
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(base_dir, "spectra_logo.svg"),
            os.path.join(base_dir, "icon.png"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                try:
                    return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
                except Exception:
                    continue
        return None

    @property
    def wrat_session(self) -> Optional[SpectraSession]:
        return self._wrat_session

    @wrat_session.setter
    def wrat_session(self, val: Optional[SpectraSession]):
        self._wrat_session = val
        self.session = val

    def __init__(self):
        super().__init__(title=f"SPECTRA — Multi-Manufacturer Telemetry & Diagnostics (v{__version__}, build {__build__})")

        # Dynamic monitor-aware initial sizing
        display = Gdk.Display.get_default()
        mon = display.get_primary_monitor() if display else None
        if display and not mon and display.get_n_monitors() > 0:
            mon = display.get_monitor(0)

        if mon:
            workarea = mon.get_workarea()
            default_w = max(760, min(1080, int(workarea.width * 0.85)))
            default_h = max(520, min(740, int(workarea.height * 0.85)))
        else:
            default_w, default_h = 1020, 680

        self.set_default_size(default_w, default_h)
        self.set_size_request(640, 440)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Set system window & dock icon
        icon_pb = self._load_app_icon(size=64)
        if icon_pb:
            self.set_icon(icon_pb)

        # Responsive layout tracking state
        self._header_compact = None
        self._kpi_compact = None
        self._sensor_compact = None
        self._stream_paused = False

        # Apply dark modern CSS styling
        self._apply_styling()

        self._wrat_session: Optional[SpectraSession] = None
        self.session: Optional[SpectraSession] = None
        self.is_reading = False
        self.is_polling = False
        self.serial_lock = threading.Lock()
        self.auto_poll_active = False
        self.auto_poll_thread: Optional[threading.Thread] = None
        self.selected_port: str = ""
        self._last_live_result: Optional[dict] = None

        # Main Layout Box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # Header Bar
        header = self._create_header_bar()
        main_box.pack_start(header, False, False, 0)

        # Progress / Status Strip
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Ready. Select brand/port and click 'Read Statistics'.")
        self.progress_bar.set_fraction(0.0)
        main_box.pack_start(self.progress_bar, False, False, 4)

        # KPI Summary Scorecards
        kpi_container = self._create_kpi_cards()
        main_box.pack_start(kpi_container, False, False, 6)

        # Main Notebook (Tabs)
        self.notebook = Gtk.Notebook()
        self.notebook.set_tab_pos(Gtk.PositionType.TOP)
        self.notebook.set_scrollable(True)
        main_box.pack_start(self.notebook, True, True, 4)

        # Tab 0: System Health & Analytics (Executive Overview)
        self.overview_tab = self._create_overview_tab()
        self.notebook.append_page(self.overview_tab, Gtk.Label(label="📊 Health & Analytics"))

        # Tab 1: Beverage Counters (Detailed Table)
        self.beverages_tab = self._create_beverages_tab()
        self.notebook.append_page(self.beverages_tab, Gtk.Label(label="☕ Beverage Counters"))

        # Tab 2: Live Digital Twin & Real-time Oscilloscope
        self.sensors_tab = self._create_sensors_tab()
        self.notebook.append_page(self.sensors_tab, Gtk.Label(label="⚡ Live Digital Twin"))

        # Tab 3: Alerts & Status
        self.alerts_tab = self._create_alerts_tab()
        self.notebook.append_page(self.alerts_tab, Gtk.Label(label="⚠️ Machine Alerts & Status"))

        # Tab 4: Maintenance & Care
        self.maint_tab = self._create_maintenance_tab()
        self.notebook.append_page(self.maint_tab, Gtk.Label(label="🧼 Maintenance & Hygiene"))

        # Tab 5: Machine Identity
        self.info_tab = self._create_info_tab()
        self.notebook.append_page(self.info_tab, Gtk.Label(label="ℹ️ Appliance Specs"))

        # Tab 6: Protocol Log
        self.log_tab = self._create_log_tab()
        self.notebook.append_page(self.log_tab, Gtk.Label(label="📜 Communication Console"))

        # Connect top-level window size allocation for responsive reflow
        self.connect("size-allocate", self._on_window_size_allocate)

        # Refresh initial ports
        self._refresh_ports()

    def _apply_styling(self):
        css_provider = Gtk.CssProvider()
        css = b"""
        window {
            background-color: #1e1e2e;
            color: #cdd6f4;
            font-family: sans-serif;
        }
        headerbar, .header-panel {
            background-color: #181825;
            border-bottom: 1px solid #313244;
            padding: 8px 12px;
        }
        .status-pill {
            background-color: #11111b;
            border: 1px solid #313244;
            border-radius: 6px;
            padding: 4px 10px;
        }
        .status-pill.online {
            border-color: #a6e3a1;
        }
        .status-pill.demo {
            border-color: #89b4fa;
        }
        .status-pill.offline {
            border-color: #45475a;
        }
        .card {
            background-color: #24273a;
            border: 1px solid #363a4f;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 3px;
        }
        .card-value {
            font-size: 20px;
            font-weight: bold;
            color: #89b4fa;
        }
        .card-sub {
            font-size: 11px;
            color: #a6e3a1;
            font-weight: 500;
        }
        .card-label {
            font-size: 11px;
            color: #a6adc8;
        }
        button {
            border-radius: 6px;
            min-height: 28px;
        }
        button.primary-btn {
            background: linear-gradient(to bottom, #89b4fa, #74c7ec);
            color: #11111b;
            font-weight: bold;
            border-radius: 6px;
            padding: 6px 16px;
            border: none;
            min-height: 28px;
        }
        button.primary-btn:hover {
            background: #b4befe;
        }
        button.primary-btn:active {
            background: #74c7ec;
        }
        button.primary-btn:disabled {
            background: #313244;
            color: #585b70;
            border: 1px solid #45475a;
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
        button.secondary-btn {
            background-color: #24273a;
            color: #cdd6f4;
            border-radius: 6px;
            padding: 6px 14px;
            border: 1px solid #45475a;
            min-height: 28px;
            font-weight: 500;
        }
        button.secondary-btn:hover {
            background-color: #313244;
            border-color: #585b70;
        }
        button.secondary-btn:active {
            background-color: #1e1e2e;
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
        }
        button.toggle-btn:hover {
            background-color: #313244;
            border-color: #585b70;
        }
        button.toggle-btn:checked {
            background-color: #a6e3a1;
            background-image: linear-gradient(to bottom, #a6e3a1, #94e2d5);
            color: #11111b;
            font-weight: bold;
            border: 1px solid #a6e3a1;
        }
        button.toggle-btn:checked:hover {
            background-color: #b4befe;
            background-image: none;
        }
        progressbar progress {
            background-color: #a6e3a1;
            border-radius: 4px;
        }
        progressbar trough {
            background-color: #313244;
            border-radius: 4px;
            min-height: 14px;
        }
        scale {
            margin: 4px 0px;
        }
        scale trough {
            background-color: #313244;
            border-radius: 4px;
            min-height: 6px;
        }
        scale highlight {
            background-color: #fab387;
            border-radius: 4px;
            min-height: 6px;
        }
        scale slider {
            background-color: #cdd6f4;
            border-radius: 50%;
            min-width: 14px;
            min-height: 14px;
        }
        treeview {
            background-color: #1e1e2e;
            color: #cdd6f4;
            border: 1px solid #313244;
        }
        treeview:selected {
            background-color: #45475a;
            color: #cdd6f4;
        }
        textview text {
            background-color: #11111b;
            color: #a6e3a1;
            font-family: monospace;
        }
        """
        css_provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _create_header_bar(self) -> Gtk.Widget:
        self.header_grid = Gtk.Grid()
        self.header_grid.get_style_context().add_class("header-panel")
        self.header_grid.set_column_spacing(8)
        self.header_grid.set_row_spacing(6)

        # Title & Icon Branding Box
        self.brand_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.brand_box.set_valign(Gtk.Align.CENTER)

        logo_pb = self._load_app_icon(size=34)
        if logo_pb:
            self.logo_img = Gtk.Image.new_from_pixbuf(logo_pb)
            self.logo_img.set_valign(Gtk.Align.CENTER)
            self.brand_box.pack_start(self.logo_img, False, False, 0)
        else:
            self.logo_img = None

        self.title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.title_box.set_valign(Gtk.Align.CENTER)
        app_title = Gtk.Label()
        app_title.set_markup(f"<b><span size='large' color='#89b4fa'>SPECTRA</span> <span size='small' color='#f9e2af'>v{__version__}</span> <span size='x-small' color='#a6adc8'>build {__build__}</span></b>")
        app_title.set_xalign(0.0)
        app_title.set_yalign(0.5)
        self.sub_title = Gtk.Label(label="Universal Hardware Telemetry & Logic Board Diagnostics")
        self.sub_title.get_style_context().add_class("card-label")
        self.sub_title.set_xalign(0.0)
        self.sub_title.set_yalign(0.5)
        self.sub_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub_title.set_no_show_all(True)
        self.title_box.pack_start(app_title, False, False, 0)
        self.title_box.pack_start(self.sub_title, False, False, 0)
        self.brand_box.pack_start(self.title_box, False, False, 0)

        # Manufacturer / Brand Selector
        self.lbl_mfr = Gtk.Label(label="Brand:")
        self.lbl_mfr.set_valign(Gtk.Align.CENTER)

        self.mfr_combo = Gtk.ComboBoxText()
        self.mfr_combo.append("auto", "⚡ Auto-Detect")
        self.mfr_combo.append("jura", "☕ Jura")
        self.mfr_combo.append("nivona", "☕ Nivona")
        self.mfr_combo.append("lamanti-kl", "🏢 Lamanti-KL (Kalerm)")
        self.mfr_combo.append("lamanti-jn", "🥤 Lamanti-JN (Jetinno)")
        self.mfr_combo.set_active_id("auto")
        self.mfr_combo.set_size_request(140, -1)
        self.mfr_combo.set_valign(Gtk.Align.CENTER)

        # Connection Status Pill
        self.status_pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_pill.get_style_context().add_class("status-pill")
        self.status_pill.get_style_context().add_class("offline")
        self.status_pill.set_valign(Gtk.Align.CENTER)

        self.lbl_status_dot = Gtk.Label()
        self.lbl_status_dot.set_markup("<span color='#f38ba8'>●</span>")
        self.status_pill.pack_start(self.lbl_status_dot, False, False, 0)

        status_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.lbl_status_pill_title = Gtk.Label()
        self.lbl_status_pill_title.set_markup("<b><span color='#cdd6f4' size='small'>OFFLINE / DISCONNECTED</span></b>")
        self.lbl_status_pill_title.set_xalign(0.0)
        self.lbl_status_pill_sub = Gtk.Label(label="Select brand/port or demo profile")
        self.lbl_status_pill_sub.get_style_context().add_class("card-label")
        self.lbl_status_pill_sub.set_xalign(0.0)
        status_text_box.pack_start(self.lbl_status_pill_title, False, False, 0)
        status_text_box.pack_start(self.lbl_status_pill_sub, False, False, 0)
        self.status_pill.pack_start(status_text_box, False, False, 0)

        # Port Selector Label & ComboBox
        self.lbl_port = Gtk.Label(label="Port:")
        self.lbl_port.set_valign(Gtk.Align.CENTER)

        self.port_combo = Gtk.ComboBoxText()
        self.port_combo.connect("changed", self._on_port_changed)
        self.port_combo.set_size_request(130, -1)
        self.port_combo.set_valign(Gtk.Align.CENTER)
        for cell in self.port_combo.get_cells():
            cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            cell.set_property("width-chars", 14)
            cell.set_property("max-width-chars", 24)

        # Refresh Ports Button
        self.btn_refresh = Gtk.Button(label="🔄")
        self.btn_refresh.set_tooltip_text("Refresh Serial Ports")
        self.btn_refresh.get_style_context().add_class("secondary-btn")
        self.btn_refresh.set_valign(Gtk.Align.CENTER)
        self.btn_refresh.connect("clicked", lambda w: self._refresh_ports())

        # Spacer
        self.header_spacer = Gtk.Box()
        self.header_spacer.set_hexpand(True)

        # Actions toolbar container for compact mode
        self.actions_row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.actions_row_box.set_valign(Gtk.Align.CENTER)

        # Read Statistics Button
        self.btn_read = Gtk.Button(label="⚡ Read Statistics")
        self.btn_read.get_style_context().add_class("primary-btn")
        self.btn_read.set_valign(Gtk.Align.CENTER)
        self.btn_read.connect("clicked", lambda w: self._on_read_clicked())

        # Memory Mapper Developer Tool Button
        self.btn_mapper = Gtk.Button(label="🔬 Memory Mapper")
        self.btn_mapper.get_style_context().add_class("action-btn")
        self.btn_mapper.set_tooltip_text("Developer Memory Mapper & Differential Scope Tool")
        self.btn_mapper.set_valign(Gtk.Align.CENTER)
        self.btn_mapper.connect("clicked", lambda w: self._on_mapper_clicked())

        # Service Report Button
        self.btn_service_report = Gtk.Button(label="🖨️ Service Receipt")
        self.btn_service_report.get_style_context().add_class("action-btn")
        self.btn_service_report.set_tooltip_text("Generate Branded Customer Service PDF/HTML Inspection Certificate")
        self.btn_service_report.set_valign(Gtk.Align.CENTER)
        self.btn_service_report.connect("clicked", lambda w: self._on_service_report_clicked())

        # Export Report Button
        self.btn_export = Gtk.Button(label="💾 Export")
        self.btn_export.get_style_context().add_class("action-btn")
        self.btn_export.set_tooltip_text("Export Raw JSON / CSV / Text Diagnostic Report")
        self.btn_export.set_valign(Gtk.Align.CENTER)
        self.btn_export.connect("clicked", lambda w: self._on_export_clicked())

        # About Suite Button
        self.btn_about = Gtk.Button(label="ℹ️")
        self.btn_about.get_style_context().add_class("secondary-btn")
        self.btn_about.set_tooltip_text("About SPECTRA")
        self.btn_about.set_valign(Gtk.Align.CENTER)
        self.btn_about.connect("clicked", lambda w: self._on_about_clicked())

        self._update_header_layout(True)
        return self.header_grid

    def _update_header_layout(self, is_compact: bool):
        if self._header_compact == is_compact:
            return
        self._header_compact = is_compact

        for w in [self.brand_box, self.lbl_mfr, self.mfr_combo, self.status_pill, self.lbl_port,
                  self.port_combo, self.btn_refresh, self.header_spacer, self.btn_read,
                  self.btn_mapper, self.btn_service_report, self.btn_export, self.btn_about, self.actions_row_box]:
            p = w.get_parent()
            if p:
                p.remove(w)
        for btn in [self.lbl_mfr, self.mfr_combo, self.btn_read, self.btn_mapper, self.btn_service_report, self.btn_export, self.btn_about]:
            p = btn.get_parent()
            if p:
                p.remove(btn)

        if not is_compact:
            # Single-row desktop layout (wide displays >= 1580px)
            self.header_grid.attach(self.brand_box, 0, 0, 1, 1)
            self.header_grid.attach(self.status_pill, 1, 0, 1, 1)
            self.header_grid.attach(self.lbl_mfr, 2, 0, 1, 1)
            self.header_grid.attach(self.mfr_combo, 3, 0, 1, 1)
            self.header_grid.attach(self.lbl_port, 4, 0, 1, 1)
            self.header_grid.attach(self.port_combo, 5, 0, 1, 1)
            self.header_grid.attach(self.btn_refresh, 6, 0, 1, 1)
            self.header_grid.attach(self.header_spacer, 7, 0, 1, 1)
            self.header_grid.attach(self.btn_read, 8, 0, 1, 1)
            self.header_grid.attach(self.btn_mapper, 9, 0, 1, 1)
            self.header_grid.attach(self.btn_service_report, 10, 0, 1, 1)
            self.header_grid.attach(self.btn_export, 11, 0, 1, 1)
            self.header_grid.attach(self.btn_about, 12, 0, 1, 1)
            self.sub_title.show()
        else:
            # 2-row layout: Row 0 Title + Status + Ports, Row 1 Brand + Actions Toolbar (min_w=942px)
            self.header_grid.attach(self.brand_box, 0, 0, 1, 1)
            self.header_grid.attach(self.status_pill, 1, 0, 1, 1)
            self.header_grid.attach(self.header_spacer, 2, 0, 1, 1)
            self.header_grid.attach(self.lbl_port, 3, 0, 1, 1)
            self.header_grid.attach(self.port_combo, 4, 0, 1, 1)
            self.header_grid.attach(self.btn_refresh, 5, 0, 1, 1)

            for item in [self.lbl_mfr, self.mfr_combo, self.btn_read, self.btn_mapper, self.btn_service_report, self.btn_export, self.btn_about]:
                self.actions_row_box.pack_start(item, False, False, 0)
            self.header_grid.attach(self.actions_row_box, 0, 1, 6, 1)
            self.sub_title.hide()

        self.header_grid.show_all()
        if is_compact:
            self.sub_title.hide()

    def _on_mapper_clicked(self):
        try:
            import memory_mapper
            active_port = self.selected_port or self.port_combo.get_active_text() or ""
            win = memory_mapper.MemoryMapperWindow(parent_app=self, initial_port=active_port)
            win.show_all()
        except Exception as e:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Failed to launch Memory Mapper"
            )
            dialog.format_secondary_text(str(e))
            dialog.run()
            dialog.destroy()
            self.header_grid.attach(self.btn_about, 6, 0, 1, 1)

            self.header_grid.attach(self.lbl_mfr, 0, 1, 1, 1)
            self.header_grid.attach(self.mfr_combo, 1, 1, 1, 1)
            self.header_grid.attach(self.lbl_port, 2, 1, 1, 1)
            self.header_grid.attach(self.port_combo, 3, 1, 1, 1)
            self.header_grid.attach(self.btn_refresh, 4, 1, 1, 1)
            self.sub_title.set_visible(False)

        self.header_grid.show_all()

    def _on_about_clicked(self):
        about = Gtk.AboutDialog(transient_for=self, modal=True)
        about.set_program_name("SPECTRA Multi-Manufacturer")
        about.set_version(f"v{__version__} (build {__build__})")
        about.set_comments(
            "Universal Hardware Telemetry & Logic Board Diagnostics\n"
            "Unified driver architecture supporting Jura, Nivona, Lamanti-KL (Kalerm), and Lamanti-JN (Jetinno)."
        )
        about.set_website("https://github.com/Pr0xyA-91/spectra")
        about.set_website_label("SPECTRA Repository")
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_copyright("© 2026 SPECTRA Hardware Diagnostics Contributors")
        logo_pb = self._load_app_icon(size=96)
        if logo_pb:
            about.set_logo(logo_pb)
        about.run()
        about.destroy()

    def _create_kpi_cards(self) -> Gtk.Widget:
        self.kpi_grid = Gtk.Grid()
        self.kpi_grid.set_column_homogeneous(True)
        self.kpi_grid.set_row_spacing(6)
        self.kpi_grid.set_column_spacing(10)
        self.kpi_grid.set_margin_start(10)
        self.kpi_grid.set_margin_end(10)

        # 1. Machine Health Scorecard (Radial Gauge)
        self.kpi_health_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.kpi_health_card.get_style_context().add_class("card")
        self.radial_gauge = gui_widgets.RadialGaugeWidget(value=None)
        self.kpi_health_card.pack_start(self.radial_gauge, False, False, 0)

        h_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        h_text_box.set_valign(Gtk.Align.CENTER)
        lbl_h_title = Gtk.Label(label="OVERALL HEALTH SCORE")
        lbl_h_title.get_style_context().add_class("card-label")
        lbl_h_title.set_xalign(0.0)

        self.lbl_kpi_health_val = Gtk.Label(label="---")
        self.lbl_kpi_health_val.get_style_context().add_class("card-value")
        self.lbl_kpi_health_val.set_xalign(0.0)

        self.lbl_kpi_health_sub = Gtk.Label(label="Awaiting diagnostic read")
        self.lbl_kpi_health_sub.get_style_context().add_class("card-sub")
        self.lbl_kpi_health_sub.set_xalign(0.0)

        h_text_box.pack_start(lbl_h_title, False, False, 0)
        h_text_box.pack_start(self.lbl_kpi_health_val, False, False, 0)
        h_text_box.pack_start(self.lbl_kpi_health_sub, False, False, 0)
        self.kpi_health_card.pack_start(h_text_box, True, True, 0)

        def make_metric_card(label_text, default_val, default_sub):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            card.get_style_context().add_class("card")
            lbl = Gtk.Label(label=label_text)
            lbl.get_style_context().add_class("card-label")
            lbl.set_xalign(0.0)

            val_lbl = Gtk.Label(label=default_val)
            val_lbl.get_style_context().add_class("card-value")
            val_lbl.set_xalign(0.0)

            sub_lbl = Gtk.Label(label=default_sub)
            sub_lbl.get_style_context().add_class("card-sub")
            sub_lbl.set_xalign(0.0)

            prog = Gtk.ProgressBar()
            prog.set_fraction(0.0)

            card.pack_start(lbl, False, False, 0)
            card.pack_start(val_lbl, False, False, 0)
            card.pack_start(sub_lbl, False, False, 0)
            card.pack_start(prog, False, False, 2)
            return card, val_lbl, sub_lbl, prog

        self.kpi_total_card, self.lbl_kpi_total, self.lbl_kpi_total_sub, self.prog_kpi_total = \
            make_metric_card("TOTAL CUPS PREPARED", "---", "---")

        self.kpi_decalc_card, self.lbl_kpi_decalc, self.lbl_kpi_decalc_sub, self.prog_kpi_decalc = \
            make_metric_card("DESCALING CYCLE STATUS", "---", "---")

        self.kpi_filter_card, self.lbl_kpi_filter, self.lbl_kpi_filter_sub, self.prog_kpi_filter = \
            make_metric_card("WATER FILTER & HYGIENE", "---", "---")

        self.lbl_kpi_model = Gtk.Label(label="No Machine Read")
        self.lbl_kpi_clean = Gtk.Label(label="---")

        self._kpi_cards_list = [self.kpi_health_card, self.kpi_total_card, self.kpi_decalc_card, self.kpi_filter_card]
        self._update_kpi_layout(True)
        return self.kpi_grid

    def _update_kpi_layout(self, is_compact: bool):
        if self._kpi_compact == is_compact:
            return
        self._kpi_compact = is_compact

        for c in self._kpi_cards_list:
            if c.get_parent():
                self.kpi_grid.remove(c)

        if not is_compact:
            self.kpi_grid.attach(self.kpi_health_card, 0, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_total_card, 1, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_decalc_card, 2, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_filter_card, 3, 0, 1, 1)
        else:
            self.kpi_grid.attach(self.kpi_health_card, 0, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_total_card, 1, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_decalc_card, 0, 1, 1, 1)
            self.kpi_grid.attach(self.kpi_filter_card, 1, 1, 1, 1)

        self.kpi_grid.show_all()

    def _create_overview_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(540)
        paned.set_border_width(6)

        self.bev_analytics = gui_widgets.BeverageAnalyticsWidget()
        paned.pack1(self.bev_analytics, True, False)

        self.diag_advisor = gui_widgets.DiagnosticAdvisorWidget()
        paned.pack2(self.diag_advisor, True, False)

        scrolled.add(paned)
        return scrolled

    def _create_beverages_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.bev_store = Gtk.ListStore(int, str, int, str, str)
        self.bev_tree = Gtk.TreeView(model=self.bev_store)

        col_name = Gtk.TreeViewColumn("Beverage Specialty", Gtk.CellRendererText(), text=1)
        col_name.set_sort_column_id(1)
        col_name.set_min_width(160)
        col_name.set_resizable(True)
        col_name.set_expand(True)
        self.bev_tree.append_column(col_name)

        col_count = Gtk.TreeViewColumn("Quantity Prepared", Gtk.CellRendererText(), text=2)
        col_count.set_sort_column_id(2)
        col_count.set_min_width(110)
        col_count.set_resizable(True)
        self.bev_tree.append_column(col_count)

        col_share = Gtk.TreeViewColumn("Share of Total", Gtk.CellRendererText(), text=3)
        col_share.set_sort_column_id(3)
        col_share.set_min_width(90)
        col_share.set_resizable(True)
        self.bev_tree.append_column(col_share)

        col_type = Gtk.TreeViewColumn("Category / Serving", Gtk.CellRendererText(), text=4)
        col_type.set_sort_column_id(4)
        col_type.set_min_width(110)
        col_type.set_resizable(True)
        self.bev_tree.append_column(col_type)

        col_code = Gtk.TreeViewColumn("Product Code", Gtk.CellRendererText(), text=0)
        col_code.set_sort_column_id(0)
        col_code.set_min_width(80)
        col_code.set_resizable(True)
        self.bev_tree.append_column(col_code)

        scrolled.add(self.bev_tree)
        return scrolled

    def _create_sensors_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.sensors_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.sensors_paned.set_border_width(6)
        self.sensors_paned.set_position(620)
        self.sensors_paned.connect("size-allocate", self._on_paned_size_allocate)

        # LEFT SIDE: Interactive Hydraulic Digital Twin & Deep Inspection Box
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_box.set_border_width(4)

        lbl_dt_title = Gtk.Label()
        lbl_dt_title.set_markup("<b><span size='medium' color='#cdd6f4'>HYDRAULIC &amp; SENSOR DIGITAL TWIN</span></b>")
        lbl_dt_title.set_xalign(0.0)
        left_box.pack_start(lbl_dt_title, False, False, 0)

        self.dt_widget = gui_widgets.DigitalTwinWidget(on_node_selected=self._on_node_selected)
        self.dt_widget.set_size_request(-1, 320)
        self.dt_widget.set_vexpand(True)
        left_box.pack_start(self.dt_widget, True, True, 0)

        # Component Telemetry Inspector Card
        self.card_component_inspector = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.card_component_inspector.get_style_context().add_class("card")

        self.lbl_inspect_title = Gtk.Label()
        self.lbl_inspect_title.set_markup("<b><span color='#89b4fa'>SELECTED COMPONENT TELEMETRY: (CLICK A NODE)</span></b>")
        self.lbl_inspect_title.set_xalign(0.0)
        self.card_component_inspector.pack_start(self.lbl_inspect_title, False, False, 2)

        inspect_grid = Gtk.Grid()
        inspect_grid.set_column_homogeneous(True)
        inspect_grid.set_column_spacing(8)

        def make_sub_box(title: str, default_val: str):
            b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            b.get_style_context().add_class("card")
            l_t = Gtk.Label(label=title)
            l_t.get_style_context().add_class("card-label")
            l_t.set_xalign(0.0)
            l_v = Gtk.Label(label=default_val)
            l_v.set_xalign(0.0)
            b.pack_start(l_t, False, False, 0)
            b.pack_start(l_v, False, False, 0)
            return b, l_v

        b1, self.lbl_inspect_v1 = make_sub_box("Primary Telemetry", "---")
        b2, self.lbl_inspect_v2 = make_sub_box("Operating Status", "---")
        b3, self.lbl_inspect_v3 = make_sub_box("Hardware Details", "---")

        inspect_grid.attach(b1, 0, 0, 1, 1)
        inspect_grid.attach(b2, 1, 0, 1, 1)
        inspect_grid.attach(b3, 2, 0, 1, 1)
        self.card_component_inspector.pack_start(inspect_grid, False, False, 2)
        left_box.pack_start(self.card_component_inspector, False, False, 0)

        # Developer Calibration Card (Development branch / build only)
        if is_dev_branch():
            self.card_dev_calib = self._create_dev_calibration_card()
            left_box.pack_start(self.card_dev_calib, False, False, 4)

        self.sensors_paned.pack1(left_box, True, False)

        # RIGHT SIDE: Real-Time Oscilloscope & Event Stream
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_box.set_border_width(4)

        ctrl_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.btn_refresh_sensors = Gtk.Button(label="🔄 Refresh Live")
        self.btn_refresh_sensors.get_style_context().add_class("primary-btn")
        self.btn_refresh_sensors.set_valign(Gtk.Align.CENTER)
        self.btn_refresh_sensors.connect("clicked", self._on_refresh_sensors_clicked)
        ctrl_bar.pack_start(self.btn_refresh_sensors, False, False, 0)

        self.spinner_sensors = Gtk.Spinner()
        self.spinner_sensors.set_valign(Gtk.Align.CENTER)
        ctrl_bar.pack_start(self.spinner_sensors, False, False, 0)

        self.chk_auto_poll = Gtk.ToggleButton(label="⏱️ Live Data (~1s)")
        self.chk_auto_poll.set_tooltip_text("Continuous hardware telemetry stream (~1.0s physical sampling)")
        self.chk_auto_poll.get_style_context().add_class("toggle-btn")
        self.chk_auto_poll.set_valign(Gtk.Align.CENTER)
        self.chk_auto_poll.connect("toggled", self._on_auto_poll_toggled)
        ctrl_bar.pack_start(self.chk_auto_poll, False, False, 0)

        self.lbl_sensors_status = Gtk.Label(label="Ready for telemetry. Click 'Refresh Live' or toggle 'Live Data'.")
        self.lbl_sensors_status.set_xalign(0.0)
        self.lbl_sensors_status.set_valign(Gtk.Align.CENTER)
        self.lbl_sensors_status.set_ellipsize(Pango.EllipsizeMode.END)
        ctrl_bar.pack_start(self.lbl_sensors_status, True, True, 0)
        right_box.pack_start(ctrl_bar, False, False, 0)

        lbl_osc_title = Gtk.Label()
        lbl_osc_title.set_markup("<b><span size='small' color='#cdd6f4'>REAL-TIME OSCILLOSCOPE &amp; STRIP CHART</span></b>")
        lbl_osc_title.set_xalign(0.0)
        right_box.pack_start(lbl_osc_title, False, False, 0)

        self.osc_widget = gui_widgets.OscilloscopeWidget(max_samples=60)
        self.osc_widget.set_size_request(-1, 200)
        right_box.pack_start(self.osc_widget, False, False, 0)

        lbl_stream_title = Gtk.Label()
        lbl_stream_title.set_markup("<b><span size='small' color='#cdd6f4'>REAL-TIME BUS EVENT STREAM &amp; SAFETY LOG</span></b>")
        lbl_stream_title.set_xalign(0.0)
        right_box.pack_start(lbl_stream_title, False, False, 0)

        scrolled_stream = Gtk.ScrolledWindow()
        scrolled_stream.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_stream.set_vexpand(True)

        self.event_stream_view = Gtk.TextView()
        self.event_stream_view.set_editable(False)
        self.event_stream_view.set_cursor_visible(False)
        self.event_stream_view.set_wrap_mode(Gtk.WrapMode.NONE)
        self.event_stream_buffer = self.event_stream_view.get_buffer()
        scrolled_stream.add(self.event_stream_view)
        right_box.pack_start(scrolled_stream, True, True, 0)

        stream_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_clear_st = Gtk.Button(label="Clear Stream")
        btn_clear_st.connect("clicked", lambda w: self.event_stream_buffer.set_text(""))
        stream_btn_box.pack_start(btn_clear_st, False, False, 0)

        self.btn_pause_st = Gtk.Button(label="Pause Stream")
        self.btn_pause_st.connect("clicked", self._on_pause_stream_clicked)
        stream_btn_box.pack_start(self.btn_pause_st, False, False, 0)

        right_box.pack_start(stream_btn_box, False, False, 2)
        self.sensors_paned.pack2(right_box, True, False)

        # Hidden stores & labels to preserve test and API compatibility
        self.live_sensors_store = Gtk.ListStore(str, str, str, str)
        self.live_sensors_tree = Gtk.TreeView(model=self.live_sensors_store)
        self.live_counters_store = Gtk.ListStore(str, int, str)
        self.live_counters_tree = Gtk.TreeView(model=self.live_counters_store)

        self.lbl_live_tank = Gtk.Label(label="---")
        self.lbl_sub_tank = Gtk.Label(label="---")
        self.lbl_live_tray = Gtk.Label(label="---")
        self.lbl_sub_tray = Gtk.Label(label="---")
        self.lbl_live_beans = Gtk.Label(label="---")
        self.lbl_sub_beans = Gtk.Label(label="---")
        self.lbl_live_state = Gtk.Label(label="---")
        self.lbl_sub_state = Gtk.Label(label="---")
        self.lbl_live_bu = Gtk.Label(label="---")
        self.lbl_sub_bu = Gtk.Label(label="---")
        self.lbl_live_coffee_tb = Gtk.Label(label="---")
        self.lbl_sub_coffee_tb = Gtk.Label(label="---")
        self.lbl_live_steam_tb = Gtk.Label(label="---")
        self.lbl_sub_steam_tb = Gtk.Label(label="---")
        self.lbl_live_flow = Gtk.Label(label="---")
        self.lbl_sub_flow = Gtk.Label(label="---")
        self.lbl_live_filter = Gtk.Label(label="---")
        self.lbl_sub_filter = Gtk.Label(label="---")

        scrolled.add(self.sensors_paned)
        return scrolled

    def _create_dev_calibration_card(self) -> Gtk.Widget:
        """Developer calibration card for live optical bean hopper sensor threshold adjustment."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("card")
        card.set_border_width(6)

        # Header row: Title + Dev Badge + Value Label + Reset Button
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_title = Gtk.Label()
        lbl_title.set_markup("<b><span size='small' color='#fab387'>🎛️ OPTICAL BEAN SENSOR SENSITIVITY CALIBRATION</span></b>")
        lbl_title.set_xalign(0.0)
        header_row.pack_start(lbl_title, False, False, 0)

        lbl_badge = Gtk.Label()
        lbl_badge.set_markup("<span size='x-small' background='#313244' color='#f9e2af' weight='bold'> DEV BRANCH </span>")
        header_row.pack_start(lbl_badge, False, False, 0)

        header_spacer = Gtk.Box()
        header_row.pack_start(header_spacer, True, True, 0)

        current_thresh = sc.get_optical_bean_threshold()
        self.lbl_calib_threshold = Gtk.Label()
        self.lbl_calib_threshold.set_markup(f"<b><span color='#fab387'>{current_thresh}</span> counts</b>")
        header_row.pack_start(self.lbl_calib_threshold, False, False, 0)

        btn_reset = Gtk.Button(label="↺ Reset (99)")
        btn_reset.set_tooltip_text("Reset optical bean sensitivity threshold to factory default (99 counts)")
        btn_reset.connect("clicked", self._on_reset_bean_calibration_clicked)
        header_row.pack_start(btn_reset, False, False, 0)

        card.pack_start(header_row, False, False, 0)

        # Slider Row
        slider_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        lbl_min = Gtk.Label()
        lbl_min.set_markup("<span size='x-small' color='#6c7086'>Dark / Dense (40)</span>")
        slider_row.pack_start(lbl_min, False, False, 0)

        self.adj_bean_threshold = Gtk.Adjustment(
            value=float(current_thresh),
            lower=40.0,
            upper=180.0,
            step_increment=1.0,
            page_increment=5.0,
            page_size=0.0
        )
        self.scale_bean_threshold = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=self.adj_bean_threshold
        )
        self.scale_bean_threshold.set_digits(0)
        self.scale_bean_threshold.set_draw_value(False)
        self.scale_bean_threshold.set_hexpand(True)
        self.scale_bean_threshold.add_mark(60, Gtk.PositionType.BOTTOM, "Strong (60)")
        self.scale_bean_threshold.add_mark(99, Gtk.PositionType.BOTTOM, "Nominal (99)")
        self.scale_bean_threshold.add_mark(125, Gtk.PositionType.BOTTOM, "Weak (125)")
        self.scale_bean_threshold.add_mark(150, Gtk.PositionType.BOTTOM, "Bare (150)")

        self.scale_bean_threshold.connect("value-changed", self._on_bean_threshold_changed)
        slider_row.pack_start(self.scale_bean_threshold, True, True, 0)

        lbl_max = Gtk.Label()
        lbl_max.set_markup("<span size='x-small' color='#6c7086'>Bare / Open (180)</span>")
        slider_row.pack_start(lbl_max, False, False, 0)

        card.pack_start(slider_row, False, False, 0)

        # Live status & diagnostic feedback line
        self.lbl_calib_live = Gtk.Label()
        self.lbl_calib_live.set_xalign(0.0)
        self._update_calib_live_label(None)
        card.pack_start(self.lbl_calib_live, False, False, 2)

        return card

    def _on_bean_threshold_changed(self, scale):
        val = int(round(scale.get_value()))
        sc.set_optical_bean_threshold(val)
        if hasattr(self, "lbl_calib_threshold"):
            self.lbl_calib_threshold.set_markup(f"<b><span color='#fab387'>{val}</span> counts</b>")
        self._update_calib_live_label(getattr(self, "_last_live_result", None))
        if getattr(self, "_last_live_result", None):
            last_res = self._last_live_result
            adcs = last_res.get("telemetry", {}).get("bean_adcs")
            if adcs and len(adcs) >= 2:
                delta = adcs[1] - adcs[0]
                lower = val - 2
                upper = val + 2
                if delta <= lower:
                    b_ok = True
                elif delta >= upper:
                    b_ok = False
                else:
                    b_ok = last_res.get("telemetry", {}).get("beans_ok", True)
                last_res.setdefault("telemetry", {})["beans_ok"] = b_ok
                for sw in last_res.get("switches", []):
                    if sw["id"] == "bean_hopper":
                        sw["ok"] = b_ok
                        sw["status"] = "Beans OK / Hopper Charged" if b_ok else "Fill Beans / Hopper Empty"
                        sw["badge"] = "NORMAL" if b_ok else "FILL BEANS"
                self.dt_widget.update_state(last_res.get("telemetry", {}), {sw["id"]: sw for sw in last_res.get("switches", [])})
                if self.dt_widget.selected_node_id:
                    self._on_node_selected(self.dt_widget.selected_node_id)

    def _on_reset_bean_calibration_clicked(self, widget):
        sc.reset_optical_bean_threshold()
        if hasattr(self, "adj_bean_threshold"):
            self.adj_bean_threshold.set_value(99.0)
        if hasattr(self, "lbl_calib_threshold"):
            self.lbl_calib_threshold.set_markup("<b><span color='#fab387'>99</span> counts</b>")
        self._update_calib_live_label(getattr(self, "_last_live_result", None))

    def _update_calib_live_label(self, result: Optional[dict] = None):
        if not hasattr(self, "lbl_calib_live"):
            return
        thresh = sc.get_optical_bean_threshold()
        hyst = 2
        lower = thresh - hyst
        upper = thresh + hyst

        if result and "telemetry" in result:
            telem = result["telemetry"]
            adcs = telem.get("bean_adcs")
            beans_ok = telem.get("beans_ok")
            if adcs and len(adcs) >= 2:
                off_adc, on_adc = adcs[0], adcs[1]
                delta = on_adc - off_adc
                st_color = "#a6e3a1" if beans_ok else "#f38ba8"
                st_text = "🟢 BEANS OK (Hopper Charged)" if beans_ok else "🔴 FILL BEANS (Hopper Empty)"
                self.lbl_calib_live.set_markup(
                    f"<span size='small'>Live Delta: <b>{delta} counts</b> (ON={on_adc}, OFF={off_adc}) • "
                    f"Active Bounds: OK ≤ {lower}, Empty ≥ {upper} • Status: <span color='{st_color}'><b>{st_text}</b></span></span>"
                )
                return

        self.lbl_calib_live.set_markup(
            f"<span size='small' color='#a6adc8'>Threshold: <b>{thresh}</b> counts (Charged ≤ {lower}, Empty ≥ {upper}) • Awaiting live sensor query</span>"
        )

    def _on_pause_stream_clicked(self, widget):
        self._stream_paused = not self._stream_paused
        self.btn_pause_st.set_label("Resume Stream" if self._stream_paused else "Pause Stream")

    def _on_paned_size_allocate(self, paned, allocation):
        target_orient = Gtk.Orientation.VERTICAL if allocation.width < 780 else Gtk.Orientation.HORIZONTAL
        if paned.get_orientation() != target_orient:
            paned.set_orientation(target_orient)
        if target_orient == Gtk.Orientation.HORIZONTAL:
            target_pos = int(allocation.width * 0.58)
            current_pos = paned.get_position()
            if abs(current_pos - target_pos) > 25:
                paned.set_position(target_pos)

    def _on_node_selected(self, node_id: Optional[str]):
        """Update the component telemetry inspector card when a node is clicked, strictly from reported data."""
        if not node_id:
            self.lbl_inspect_title.set_markup("<b><span color='#89b4fa'>SELECTED COMPONENT TELEMETRY: (CLICK A NODE)</span></b>")
            self.lbl_inspect_v1.set_text("---")
            self.lbl_inspect_v2.set_text("---")
            self.lbl_inspect_v3.set_text("---")
            return

        live = getattr(self, "_last_live_result", None) or {}
        telem = live.get("telemetry", {})
        switches_map = {sw["id"]: sw for sw in live.get("switches", [])}
        error_counters = live.get("error_counters", {})
        summary = self.session.get_structured_summary() if self.session else {}
        session_telem = summary.get("telemetry", {}) if summary else {}

        has_data = bool(telem or summary)

        if node_id == "tb1":
            title = "THERMOBLOCK 1 (COFFEE HEATER)"
            if has_data:
                c_temp = telem.get("heater_coffee_str", session_telem.get("heater_coffee_str", "---"))
                status = telem.get("heater_coffee_status", "---")
                ready_flg = "Ready (1)" if telem.get("heater_ready_flag") else ("Heating / Not Ready (0)" if "heater_ready_flag" in telem else "---")
                v1 = f"Live Temperature: {c_temp}"
                v2 = f"Thermal Operating State: {status} • Ready Flag: {ready_flg}"
                ntc_raw = telem.get("heater_coffee_raw")
                v3 = f"NTC Sensor Count: {ntc_raw} (0x{ntc_raw:04X})" if ntc_raw is not None else "---"
            else:
                v1, v2, v3 = "Live Temperature: ---", "Operating State: Awaiting read", "---"

        elif node_id == "tb2":
            title = "THERMOBLOCK 2 (STEAM HEATER)"
            if has_data:
                is_dual = telem.get("is_dual_heater", session_telem.get("is_dual_heater", False))
                if is_dual:
                    s_temp = telem.get("heater_steam_str", "---")
                    s_status = telem.get("heater_steam_status", "---")
                    s_raw = telem.get("heater_steam_raw")
                    v1 = f"Live Temperature: {s_temp}"
                    v2 = f"Thermal Operating State: {s_status}"
                    v3 = f"NTC Sensor Count: {s_raw} (0x{s_raw:04X})" if s_raw is not None else "---"
                else:
                    v1 = "Configuration: Single Heater Model (No Steam Thermoblock)"
                    v2 = "Status: Not Installed (Circuit: Open Pull-Up 0x0802)"
                    v3 = "Hardware Circuit: Single Thermoblock Layout"
            else:
                v1, v2, v3 = "Live Temperature: ---", "Operating State: Awaiting read", "---"

        elif node_id == "flowmeter":
            title = "FLOWMETER (DIGIMESA)"
            if has_data:
                fl = telem.get("flow_rate_ml_s", 0.0)
                pulses = telem.get("flow_pulses", 0)
                vol_ml = telem.get("flow_volume_ml", 0.0)
                tot_l = session_telem.get("water_dispensed_liters", summary.get("water_dispensed_liters"))
                fm_in = telem.get("fm_intake_timeouts", error_counters.get("Flowmeter Intake Timeouts", 0))
                fm_rin = telem.get("fm_rinse_timeouts", error_counters.get("Flowmeter Rinse Timeouts", 0))
                v1 = f"Live Flow Rate: {fl:.1f} ml/s • Current Cycle: {vol_ml:.1f} ml ({pulses} pulses)"
                v2 = f"Lifetime Timeouts: Intake: {fm_in} | Rinse: {fm_rin}"
                v3 = f"Total Lifetime Water Dispensed: {tot_l} L" if tot_l is not None else "Pulse Ratio: 2.366 pulses / ml"
            else:
                v1, v2, v3 = "Live Flow Rate: ---", "Operating State: Awaiting read", "---"

        elif node_id == "pump":
            title = "VIBRATION WATER PUMP"
            if has_data:
                fl = telem.get("flow_rate_ml_s", 0.0)
                state = "Active (Dispensing Fluid)" if fl > 0 else "Idle / Standby"
                v1 = f"Pump Drive State: {state}"
                v2 = f"Measured Fluid Output: {fl:.1f} ml/s"
                v3 = "Hydraulic Pressure Line: Nominal Resistance"
            else:
                v1, v2, v3 = "Pump Drive State: ---", "Fluid Output: ---", "---"

        elif node_id == "valve":
            title = "CERAMIC DISTRIBUTION VALVE"
            if has_data:
                mv_b = telem.get("mv_busy", False)
                mv_i = telem.get("mv_init_ok", True)
                v1 = f"Motor Drive State: {'Moving / Busy' if mv_b else 'Idle / Positioned'}"
                v2 = f"Initialization State: {'Initialized (OK)' if mv_i else 'Fault / Uninitialized'}"
                timeouts = error_counters.get("Ceramic Valve Timeouts", 0)
                pos_faults = error_counters.get("Multiway Valve Position Faults", 0)
                v3 = f"Lifetime Errors: Valve Timeouts: {timeouts} | Position Faults: {pos_faults}"
            else:
                v1, v2, v3 = "Motor Drive State: ---", "Initialization State: ---", "---"

        elif node_id == "bu":
            title = "BREW UNIT DRIVE & ENCODER"
            if has_data:
                pos = telem.get("bu_encoder_pos", "---")
                zone = telem.get("bu_position_state", "---")
                upper = telem.get("bu_encoder_upper", "---")
                target = telem.get("bu_mill_target", "---")
                init_cnt = telem.get("bu_init_count", "---")
                v1 = f"Encoder Position: {pos} ticks ({zone})"
                v2 = f"Calibrated Targets: Mill: {target} ticks | Upper Ref: {upper} ticks"
                bu_pos_err = error_counters.get("Brew Unit Position Faults", 0)
                v3 = f"Initialization Count: {init_cnt} cycles | Position Faults: {bu_pos_err}"
            else:
                v1, v2, v3 = "Encoder Position: ---", "Targets: ---", "---"

        elif node_id == "tank":
            title = "WATER RESERVOIR & SENSOR"
            if has_data:
                sw = switches_map.get("water_tank", {})
                tank_ok = sw.get("ok", True)
                v1 = f"Float / Reed Switch: {'Water Present (OK)' if tank_ok else 'Empty / Missing (Refill)'}"
                claris = telem.get("filter_claris_active", session_telem.get("filter_claris_active"))
                claris_str = "CLARIS Active" if claris is True else ("Bypass Mode" if claris is False else "---")
                hard = telem.get("water_hardness_dh", session_telem.get("water_hardness_dh"))
                v2 = f"Filter System: {claris_str}"
                v3 = f"Configured Water Hardness: {hard} °dH" if hard is not None else "---"
            else:
                v1, v2, v3 = "Float Switch: ---", "Filter System: ---", "---"

        elif node_id == "tray":
            title = "DRIP TRAY & GROUNDS CONTAINER"
            if has_data:
                sw_tr = switches_map.get("drip_tray", {})
                tr_ok = sw_tr.get("ok", True)
                gr_full = telem.get("grounds_full", False)
                v1 = f"Drip Tray Microswitch: {'Inserted (OK)' if tr_ok else 'Missing / Removed'}"
                v2 = f"Grounds Container: {'Full (Empty Waste Container)' if gr_full else 'OK (Inserted & Empty)'}"
                tr_trips = error_counters.get("Drip Tray Missing Trips", 0)
                v3 = f"Historical Trips: Drip Tray Removed {tr_trips} times"
            else:
                v1, v2, v3 = "Drip Tray Microswitch: ---", "Grounds Container: ---", "---"

        elif node_id == "beans":
            title = "OPTICAL BEAN HOPPER SENSOR"
            if has_data:
                sw_b = switches_map.get("bean_hopper", {})
                b_ok = sw_b.get("ok", telem.get("beans_ok"))
                adcs = telem.get("bean_adcs")
                if b_ok is True:
                    b_status_str = "Beans OK (Hopper Charged)"
                elif b_ok is False:
                    b_status_str = "Fill Beans (Hopper Empty)"
                else:
                    b_status_str = "Awaiting Sensor Read"
                v1 = f"Optical Sensor Status: {b_status_str}"
                if adcs and len(adcs) >= 2:
                    delta = adcs[1] - adcs[0]
                    calib = sc.get_optical_bean_calibration()
                    v2 = f"IR ADC Readings: Ambient={adcs[0]}, Reflected={adcs[1]} (Delta: {delta} counts | Threshold: {calib['threshold']} ± {calib['hysteresis']})"
                else:
                    v2 = "IR ADC Readings: Passive Telemetry"
                puck = telem.get("cake_thickness_ticks", 0)
                v3 = f"Last Compressed Cake Thickness: {puck} ticks"
            else:
                v1, v2, v3 = "Optical Sensor Status: ---", "IR ADC Readings: ---", "---"

        elif node_id == "mcu":
            title = "LOGIC BOARD & OPTICAL INTERFACE"
            if has_data:
                fw = summary.get("firmware_string", session_telem.get("firmware_string", "---"))
                dfw = telem.get("display_firmware", session_telem.get("display_firmware", "---"))
                ldr = telem.get("loader_version", session_telem.get("loader_version", "---"))
                port = summary.get("port", getattr(self.session, "port_name", "UART 9600"))
                v1 = f"Main Firmware: {fw}"
                v2 = f"Display Unit MCU: {dfw} • Bootloader: {ldr}"
                v3 = f"Serial Bus: {port} • 9600 Baud 8N1 Optical Loopback"
            else:
                v1, v2, v3 = "Main Firmware: ---", "Display MCU: ---", "---"

        elif node_id == "spout":
            title = "DISPENSER SPOUT"
            v1 = "Fluidic Outlet: Dual Dispenser Spout"
            v2 = "Status: Nominal" if has_data else "Awaiting telemetry"
            v3 = "---"

        else:
            title = "COMPONENT"
            v1, v2, v3 = "---", "---", "---"

        safe_title = GLib.markup_escape_text(title)
        self.lbl_inspect_title.set_markup(f"<b><span color='#89b4fa'>SELECTED COMPONENT TELEMETRY: {safe_title}</span></b>")
        self.lbl_inspect_v1.set_text(v1)
        self.lbl_inspect_v2.set_text(v2)
        self.lbl_inspect_v3.set_text(v3)

    def _create_maintenance_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.maint_store = Gtk.ListStore(str, int, str, int)
        self.maint_tree = Gtk.TreeView(model=self.maint_store)

        col_lbl = Gtk.TreeViewColumn("Maintenance Item / Cycle", Gtk.CellRendererText(), text=0)
        col_lbl.set_min_width(180)
        col_lbl.set_resizable(True)
        col_lbl.set_expand(True)
        self.maint_tree.append_column(col_lbl)

        col_cnt = Gtk.TreeViewColumn("Execution Count", Gtk.CellRendererText(), text=1)
        col_cnt.set_min_width(110)
        col_cnt.set_resizable(True)
        self.maint_tree.append_column(col_cnt)

        cell_prog = Gtk.CellRendererProgress()
        col_prog = Gtk.TreeViewColumn("Cycle Life Progress", cell_prog, value=3, text=2)
        col_prog.set_min_width(160)
        col_prog.set_resizable(True)
        col_prog.set_expand(True)
        self.maint_tree.append_column(col_prog)

        scrolled.add(self.maint_tree)
        return scrolled

    def _create_alerts_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.alerts_store = Gtk.ListStore(str, str, int)
        self.alerts_tree = Gtk.TreeView(model=self.alerts_store)

        col_sev = Gtk.TreeViewColumn("Status / Severity", Gtk.CellRendererText(), text=0)
        col_sev.set_min_width(120)
        col_sev.set_resizable(True)
        self.alerts_tree.append_column(col_sev)

        col_name = Gtk.TreeViewColumn("System Notification / Alert Message", Gtk.CellRendererText(), text=1)
        col_name.set_min_width(200)
        col_name.set_resizable(True)
        col_name.set_expand(True)
        self.alerts_tree.append_column(col_name)

        col_bit = Gtk.TreeViewColumn("Bit Index", Gtk.CellRendererText(), text=2)
        col_bit.set_min_width(70)
        col_bit.set_resizable(True)
        self.alerts_tree.append_column(col_bit)

        scrolled.add(self.alerts_tree)
        return scrolled

    def _create_info_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(8)

        # Hero Brand Banner Card
        hero_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        hero_card.get_style_context().add_class("card")
        hero_card.set_margin_bottom(4)

        hero_pb = self._load_app_icon(size=56)
        if hero_pb:
            hero_img = Gtk.Image.new_from_pixbuf(hero_pb)
            hero_img.set_valign(Gtk.Align.CENTER)
            hero_card.pack_start(hero_img, False, False, 4)

        hero_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        hero_text_box.set_valign(Gtk.Align.CENTER)

        hero_title = Gtk.Label()
        hero_title.set_markup(f"<b><span size='large' color='#89b4fa'>SPECTRA Diagnostic Suite</span> <span size='small' color='#f9e2af'>v{__version__}</span> <span size='x-small' color='#a6adc8'>build {__build__}</span></b>")
        hero_title.set_xalign(0.0)

        hero_desc = Gtk.Label()
        hero_desc.set_markup("<span size='small' color='#a6adc8'>Universal Hardware Telemetry &amp; Logic Board Diagnostics Platform</span>")
        hero_desc.set_xalign(0.0)

        hero_sub = Gtk.Label()
        hero_sub.set_markup("<span size='small' color='#a6e3a1'>● Engine Ready</span>  <span size='small' color='#6c7086'>|</span>  <span size='small' color='#cdd6f4'>Optical / Serial Bus Protocol &amp; Multi-Point Telemetry</span>")
        hero_sub.set_xalign(0.0)

        hero_text_box.pack_start(hero_title, False, False, 0)
        hero_text_box.pack_start(hero_desc, False, False, 0)
        hero_text_box.pack_start(hero_sub, False, False, 0)
        hero_card.pack_start(hero_text_box, True, True, 0)

        box.pack_start(hero_card, False, False, 0)

        tree_scrolled = Gtk.ScrolledWindow()
        tree_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tree_scrolled.set_vexpand(True)

        self.info_store = Gtk.ListStore(str, str)
        self.info_tree = Gtk.TreeView(model=self.info_store)

        col_prop = Gtk.TreeViewColumn("Property", Gtk.CellRendererText(), text=0)
        col_prop.set_min_width(160)
        col_prop.set_resizable(True)
        self.info_tree.append_column(col_prop)

        col_val = Gtk.TreeViewColumn("Value / Diagnostic Telemetry", Gtk.CellRendererText(), text=1)
        col_val.set_min_width(220)
        col_val.set_resizable(True)
        col_val.set_expand(True)
        self.info_tree.append_column(col_val)

        tree_scrolled.add(self.info_tree)
        box.pack_start(tree_scrolled, True, True, 0)

        scrolled.add(box)
        return scrolled

    def _create_log_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_buffer = self.log_view.get_buffer()

        scrolled.add(self.log_view)
        box.pack_start(scrolled, True, True, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_clear = Gtk.Button(label="Clear Log")
        btn_clear.connect("clicked", lambda w: self.log_buffer.set_text(""))
        btn_box.pack_start(btn_clear, False, False, 4)
        box.pack_start(btn_box, False, False, 4)

        return box

    def _on_window_size_allocate(self, widget, allocation):
        header_compact = allocation.width < 1650
        kpi_compact = allocation.width < 1180

        needs_reflow = (
            self._header_compact != header_compact or
            self._kpi_compact != kpi_compact
        )
        if needs_reflow:
            self._pending_reflow = (header_compact, kpi_compact)
            if not getattr(self, "_reflow_scheduled", False):
                self._reflow_scheduled = True
                GLib.idle_add(self._do_pending_reflow)

    def _do_pending_reflow(self):
        self._reflow_scheduled = False
        if hasattr(self, "_pending_reflow") and self._pending_reflow:
            h_comp, k_comp = self._pending_reflow
            self._update_header_layout(h_comp)
            self._update_kpi_layout(k_comp)
            self._pending_reflow = None
        return False

    def _refresh_ports(self):
        self.port_combo.remove_all()
        ports = serial_io.list_serial_ports()
        active_idx = 0
        for idx, p in enumerate(ports):
            self.port_combo.append_text(p)
            if p.startswith("/dev/ttyUSB") or p.startswith("COM"):
                active_idx = idx
        if ports:
            self.port_combo.set_active(active_idx)
            self.selected_port = self.port_combo.get_active_text() or ""

    def _on_port_changed(self, widget):
        self.selected_port = self.port_combo.get_active_text() or ""

    def _append_log(self, text: str):
        line_count = self.log_buffer.get_line_count()
        if line_count > 1000:
            start_iter = self.log_buffer.get_start_iter()
            cutoff_iter = self.log_buffer.get_iter_at_line(line_count - 800)
            self.log_buffer.delete(start_iter, cutoff_iter)
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, text + "\n")
        adj = self.log_view.get_vadjustment()
        if adj:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _append_event_stream(self, text: str):
        if self._stream_paused:
            return
        line_count = self.event_stream_buffer.get_line_count()
        if line_count > 500:
            start_iter = self.event_stream_buffer.get_start_iter()
            cutoff_iter = self.event_stream_buffer.get_iter_at_line(line_count - 400)
            self.event_stream_buffer.delete(start_iter, cutoff_iter)
        end_iter = self.event_stream_buffer.get_end_iter()
        self.event_stream_buffer.insert(end_iter, text + "\n")
        adj = self.event_stream_view.get_vadjustment()
        if adj:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _on_read_clicked(self):
        if self.is_reading:
            return

        active_port = self.port_combo.get_active_text()
        active_mfr = self.mfr_combo.get_active_id() or "auto"
        if not active_port:
            self.progress_bar.set_text("No port selected!")
            return

        self.is_reading = True
        self.btn_read.set_sensitive(False)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text(f"Connecting to {active_port} ({active_mfr})...")

        thread = threading.Thread(target=self._run_session_worker, args=(active_port, active_mfr), daemon=True)
        thread.start()

    def _run_session_worker(self, port: str, mfr: str):
        with self.serial_lock:
            session = SpectraSession(
                port,
                baudrate=9600,
                manufacturer=mfr,
                log_cb=lambda msg: GLib.idle_add(self._append_log, msg)
            )

            def update_prog(pct, status):
                GLib.idle_add(self.progress_bar.set_fraction, pct)
                GLib.idle_add(self.progress_bar.set_text, f"[{int(pct*100)}%] {status}")

            success = session.run_interrogation(progress_cb=update_prog)
        GLib.idle_add(self._on_session_finished, session, success)

    def _on_session_finished(self, session: SpectraSession, success: bool):
        self.is_reading = False
        self.btn_read.set_sensitive(True)
        self.wrat_session = session

        if not success:
            self.progress_bar.set_fraction(1.0)
            self.progress_bar.set_text("Interrogation failed! Check port connection / permissions.")
            return

        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_text(f"Successfully read statistics from {session.model_family}!")

        # Update Status Pill
        port_name = getattr(session, "port_name", getattr(session, "port", "UNKNOWN"))
        is_demo = "DEMO" in str(port_name).upper()
        self.lbl_status_dot.set_markup("<span color='#89b4fa'>●</span>" if is_demo else "<span color='#a6e3a1'>●</span>")
        safe_model = GLib.markup_escape_text(session.model_family.upper())
        self.lbl_status_pill_title.set_markup(f"<b><span color='#cdd6f4' size='small'>{safe_model}</span></b>")
        mfr_name = getattr(session, "manufacturer_name", getattr(session, "protocol_mode", "Jura"))
        self.lbl_status_pill_sub.set_text(f"{port_name} • {mfr_name} • OK")
        self.status_pill.get_style_context().remove_class("offline")
        self.status_pill.get_style_context().add_class("demo" if is_demo else "online")

        # Populate GUI views
        summary = session.get_structured_summary()

        # Update KPI Cards
        tot = summary.get("total_cups", 0)
        self.lbl_kpi_total.set_text(f"{tot:,}")
        self.prog_kpi_total.set_fraction(min(1.0, tot / 80000.0))
        self.lbl_kpi_total_sub.set_text(f"Lifespan: 80,000 cups ({tot/800.0:.1f}%)")

        clean_cnt = 0
        decalc_cnt = 0
        decalc_pct = None
        for m in summary.get("maintenance", []):
            m_lbl = m.get("label", "").lower()
            if m_lbl in ("cleaning", "cleanings"):
                clean_cnt = m.get("count", 0)
            elif "decalc" in m_lbl or "descal" in m_lbl:
                decalc_cnt = m.get("count", 0)
                decalc_pct = m.get("percentage")

        if decalc_pct is not None:
            cups_left = max(0, int((100 - decalc_pct) * 6.5))
            self.lbl_kpi_decalc.set_text(f"{cups_left} Cups Left")
            self.lbl_kpi_decalc_sub.set_text(f"Cycles: {decalc_cnt:,} performed ({decalc_pct}% used)")
            self.prog_kpi_decalc.set_fraction(decalc_pct / 100.0)
        elif decalc_cnt > 0:
            self.lbl_kpi_decalc.set_text(f"{decalc_cnt:,} Performed")
            self.lbl_kpi_decalc_sub.set_text("Descaling cycle nominal")
            self.prog_kpi_decalc.set_fraction(0.0)
        else:
            self.lbl_kpi_decalc.set_text("---")
            self.lbl_kpi_decalc_sub.set_text("---")
            self.prog_kpi_decalc.set_fraction(0.0)

        claris_active = summary.get("telemetry", {}).get("filter_claris_active")
        hardness = summary.get("telemetry", {}).get("water_hardness_dh")
        if claris_active is True:
            self.lbl_kpi_filter.set_text("CLARIS Active")
        elif claris_active is False:
            self.lbl_kpi_filter.set_text("Bypass Mode")
        else:
            self.lbl_kpi_filter.set_text("---")

        sub_parts = []
        if hardness is not None:
            sub_parts.append(f"Hardness: {hardness} °dH")
        if clean_cnt > 0:
            sub_parts.append(f"Cleanings: {clean_cnt:,}")
        self.lbl_kpi_filter_sub.set_text(" • ".join(sub_parts) if sub_parts else "---")
        self.prog_kpi_filter.set_fraction(0.0)

        # Evaluate Machine Health Index
        score = self.diag_advisor.evaluate_health(summary, getattr(session, "live_sensors", {}))
        self.radial_gauge.set_value(score)
        health_label = "OPTIMAL" if score >= 90 else ("GOOD" if score >= 75 else "NEEDS SERVICE")
        self.lbl_kpi_health_val.set_text(f"{score}% ({health_label})")
        self.lbl_kpi_health_sub.set_text("✓ Zero critical faults" if score >= 80 else "⚠️ Review maintenance checklist")

        # Update Beverage Analytics Widget
        water_l = float(summary.get("telemetry", {}).get("water_dispensed_liters", 0.0) or 0.0)
        self.bev_analytics.update_data(summary.get("beverages", []), tot, water_liters=water_l)

        # Populate Beverages Tab (Table)
        self.bev_store.clear()
        tot_div = tot or 1
        for b in sorted(summary["beverages"], key=lambda x: x["count"], reverse=True):
            share = f"{(b['count'] / tot_div) * 100:.1f}%" if b["count"] > 0 else "0.0%"
            cat = "Double Serving (2x)" if b["is_double"] else "Single Serving"
            self.bev_store.append([b["code"], b["name"], b["count"], share, cat])

        # Populate Maintenance Tab
        self.maint_store.clear()
        for m in summary["maintenance"]:
            pct_val = m["percentage"] if m["percentage"] is not None else 0
            pct_str = f"{pct_val}%" if m["percentage"] is not None else "N/A"
            self.maint_store.append([m["label"], m["count"], pct_str, pct_val])

        # Populate Alerts Tab
        self.alerts_store.clear()
        if not summary["alerts"]:
            self.alerts_store.append(["NORMAL / READY", "System OK - Ready to Brew", 0])
        else:
            for a in summary["alerts"]:
                sev = "BLOCKING ERROR" if a.get("blocking") else "NOTICE / STATUS"
                self.alerts_store.append([sev, a["name"].upper(), a.get("bit", 0)])

        # Populate Info Tab
        self.info_store.clear()
        self.info_store.append(["Manufacturer", getattr(session, "manufacturer_name", "Jura")])
        if summary.get("telemetry") and "appliance_type" in summary["telemetry"]:
            self.info_store.append(["Appliance Type", str(summary["telemetry"]["appliance_type"])])
        self.info_store.append(["Machine Family", summary["machine_model"]])
        if summary.get("telemetry"):
            tel = summary["telemetry"]
            for prop, key in [
                ("Serial Number (14-Digit)", "serial_number"),
                ("EAN-Code", "ean_code"),
                ("Article Number", "article_number"),
                ("Date of Production", "production_date"),
                ("Appliance Number", "appliance_number"),
                ("Logic Board Serial (ID)", "serial_number_word"),
                ("Appliance Code", "appliance_code"),
                ("Software Version Display", "software_version_display"),
            ]:
                if key in tel and tel[key] != "N/A":
                    self.info_store.append([prop, str(tel[key])])
            if "water_hardness_dh" in tel:
                self.info_store.append(["Water Hardness", f"{tel['water_hardness_dh']} °dH"])
            if "cups_since_intervention" in tel:
                self.info_store.append(["Cups Since Last Intervention", f"{tel['cups_since_intervention']:,}"])
        self.info_store.append(["Firmware Identifier", summary["firmware_string"]])
        self.info_store.append(["Profile EF Code", summary["ef_code"]])
        if summary.get("telemetry"):
            tel = summary["telemetry"]
            if "water_dispensed_liters" in tel:
                self.info_store.append(["Total Water Dispensed", f"{tel['water_dispensed_liters']} Liters"])
        self.info_store.append(["Total Cups Dispensed", f"{summary['total_cups']:,}"])
        self.info_store.append(["Serial Port", summary["port"]])
        self.info_store.append(["Protocol Mode", summary.get("protocol_mode", "ASCII Optical")])
        self.info_store.append(["Diagnostics Timestamp", summary["timestamp"]])

        # Populate Live Sensors Tab if available from session
        if hasattr(session, "live_sensors") and session.live_sensors:
            self._on_live_sensors_updated(session.live_sensors)

    def _on_auto_poll_toggled(self, widget):
        if self.chk_auto_poll.get_active():
            self.selected_port = self.port_combo.get_active_text() or ""
            self.auto_poll_active = True
            self.btn_refresh_sensors.set_sensitive(False)
            self.lbl_sensors_status.set_text("Live data stream active (~1s sampling)...")
            if self.auto_poll_thread is None or not self.auto_poll_thread.is_alive():
                self.auto_poll_thread = threading.Thread(target=self._auto_poll_worker, daemon=True)
                self.auto_poll_thread.start()
        else:
            self.auto_poll_active = False
            self.btn_refresh_sensors.set_sensitive(True)
            self.lbl_sensors_status.set_text("Live data stream stopped. Ready.")

    def _auto_poll_worker(self):
        conn: Optional[serial_io.JuraSerialConnection] = None
        current_port = None
        try:
            while self.auto_poll_active:
                if self.is_reading:
                    time.sleep(0.5)
                    continue

                active_port = self.port_combo.get_active_text()
                active_mfr = self.mfr_combo.get_active_id() or "auto"
                if not active_port:
                    time.sleep(1.0)
                    continue

                with self.serial_lock:
                    if conn is None or current_port != active_port or not conn.is_open:
                        if conn:
                            try:
                                conn.close()
                            except Exception:
                                pass
                        try:
                            conn = serial_io.JuraSerialConnection(active_port, baudrate=9600)
                            current_port = active_port
                        except Exception as e:
                            GLib.idle_add(self.lbl_sensors_status.set_text, f"Connection error: {e}")
                            time.sleep(2.0)
                            continue

                    try:
                        res = sc.query_live_sensors(active_port, conn=conn, fast_poll=True, manufacturer=active_mfr)
                    except Exception as e:
                        res = {"error": str(e)}

                if self.auto_poll_active:
                    GLib.idle_add(self._on_live_sensors_updated, res)

                # Hardware streaming pacing: 0.1s inter-query breathing pause (~1.0s physical rate)
                for _ in range(2):
                    if not self.auto_poll_active:
                        break
                    time.sleep(0.05)
        finally:
            with self.serial_lock:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None

    def _on_refresh_sensors_clicked(self, widget):
        if self.is_reading or self.is_polling or self.auto_poll_active:
            return

        active_port = self.port_combo.get_active_text()
        active_mfr = self.mfr_combo.get_active_id() or "auto"
        if not active_port:
            self.lbl_sensors_status.set_text("No serial port selected!")
            return

        self.is_polling = True
        self.btn_refresh_sensors.set_sensitive(False)
        self.spinner_sensors.start()
        self.lbl_sensors_status.set_text(f"Querying live hardware sensors on {active_port}...")

        def worker():
            try:
                with self.serial_lock:
                    result = sc.query_live_sensors(active_port, baudrate=9600, fast_poll=False, manufacturer=active_mfr)
            except Exception as e:
                result = {"error": str(e)}
            finally:
                self.is_polling = False
            GLib.idle_add(self._on_live_sensors_updated, result)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _on_live_sensors_updated(self, result: dict):
        if not self.auto_poll_active:
            self.btn_refresh_sensors.set_sensitive(True)
        self.spinner_sensors.stop()

        if not result:
            return

        self._last_live_result = result
        if "error" in result:
            self.lbl_sensors_status.set_text(f"Live notice: {result['error']}")
            return

        ts = result.get("timestamp", datetime.now().strftime("%H:%M:%S"))
        proto = result.get("protocol", "UART")
        mode_tag = "live" if self.auto_poll_active else "manual"
        self.lbl_sensors_status.set_text(f"Live Data ({mode_tag}): {ts} (via {proto})")

        telem = result.get("telemetry", {})
        switches_map = {sw["id"]: sw for sw in result.get("switches", [])}

        # 1. Update Cairo Digital Twin Widget
        self.dt_widget.update_state(telem, switches_map)

        # 2. Push telemetry to Rolling Oscilloscope Widget (strictly reported numbers)
        coffee_c = telem.get("heater_coffee_c")
        steam_c = telem.get("heater_steam_c")
        flow_rate = telem.get("flow_rate_ml_s", 0.0)
        self.osc_widget.push_sample(coffee_c, steam_c, flow_rate)

        # 3. Append to Event Stream Log
        bu_pos = telem.get("bu_encoder_pos", "---")
        bu_st = telem.get("bu_position_short", "---")
        tb1_msg = f"{coffee_c:.1f}°C" if coffee_c is not None else "---"
        tb2_msg = f"{steam_c:.1f}°C" if steam_c is not None else "N/A"
        ev_line = f"{ts} [LIVE] TB1: {tb1_msg} | TB2: {tb2_msg} | Flow: {flow_rate:.1f} ml/s | BU: {bu_pos} ({bu_st})"
        self._append_event_stream(ev_line)

        # 4. Refresh selected component inspector card if a node is selected
        if self.dt_widget.selected_node_id:
            self._on_node_selected(self.dt_widget.selected_node_id)

        # 5. Refresh developer calibration live feedback if active
        if hasattr(self, "_update_calib_live_label"):
            self._update_calib_live_label(result)

        # 6. Refresh Diagnostic Advisor if session summary exists
        if self.session:
            summary = self.session.get_structured_summary()
            score = self.diag_advisor.evaluate_health(summary, result)
            self.radial_gauge.set_value(score)

    def _on_service_report_clicked(self):
        if not self.session:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="No Machine Telemetry Available",
            )
            dialog.format_secondary_text("Please click '⚡ Read Statistics' on a machine or demo profile first.")
            dialog.run()
            dialog.destroy()
            return

        summary = self.session.get_structured_summary()
        health_score = self.radial_gauge.value
        checklist = [
            ("Visual inspection of silicone pressure lines & brass fittings", self.diag_advisor.chk1.get_active()),
            ("Safety thermal cutoff continuity (TB1: 0.1Ω, TB2: 0.1Ω)", self.diag_advisor.chk2.get_active()),
            ("Descaling cycle execution & flowmeter verification", self.diag_advisor.chk3.get_active()),
            ("Clean microswitch contact leaves on rear chassis", self.diag_advisor.chk4.get_active()),
        ]

        html_content = gui_widgets.generate_service_report_html(summary, health_score, checklist)

        downloads_dir = os.path.expanduser("~/Downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        safe_model = re.sub(r'[^\w\-_]', '_', str(summary.get("machine_model", "appliance")))
        out_filename = f"spectra_service_receipt_{safe_model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        out_path = os.path.join(downloads_dir, out_filename)

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Service Inspection Certificate Generated",
            )
            dialog.format_secondary_text(
                f"Saved to:\n{out_path}\n\nYou can open this file in any web browser to view, share, or print to PDF."
            )
            dialog.run()
            dialog.destroy()

            # Attempt to launch default browser in background (cross-platform)
            try:
                if sys.platform.startswith("win"):
                    os.startfile(out_path)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["xdg-open", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        except Exception as e:
            err_dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Failed to Save Inspection Certificate",
            )
            err_dialog.format_secondary_text(str(e))
            err_dialog.run()
            err_dialog.destroy()

    def _on_export_clicked(self):
        if not self.session:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="No Statistics Available",
            )
            dialog.format_secondary_text("Please read statistics from a machine or demo port first.")
            dialog.run()
            dialog.destroy()
            return

        dialog = Gtk.FileChooserDialog(
            title="Save SPECTRA Diagnostic Report",
            parent=self,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK
        )

        filter_txt = Gtk.FileFilter()
        filter_txt.set_name("Text Report (*.txt)")
        filter_txt.add_pattern("*.txt")
        dialog.add_filter(filter_txt)

        filter_json = Gtk.FileFilter()
        filter_json.set_name("JSON File (*.json)")
        filter_json.add_pattern("*.json")
        dialog.add_filter(filter_json)

        filter_csv = Gtk.FileFilter()
        filter_csv.set_name("CSV File (*.csv)")
        filter_csv.add_pattern("*.csv")
        dialog.add_filter(filter_csv)

        safe_family = re.sub(r'[^\w\-_]', '_', str(self.session.model_family))
        default_name = f"spectra_diag_{safe_family}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        dialog.set_current_name(default_name)

        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if filename.endswith(".json"):
                data = self.session.export_json()
            elif filename.endswith(".csv"):
                data = self.session.export_csv()
            else:
                data = self.session.export_text_report()

            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(data)
                self.progress_bar.set_text(f"Report saved to {filename}")
            except Exception as e:
                err_dialog = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Failed to Save Report",
                )
                err_dialog.format_secondary_text(str(e))
                err_dialog.run()
                err_dialog.destroy()

        dialog.destroy()


def main():
    app = JuraDiagApp()
    def _on_destroy(*_args):
        app.auto_poll_active = False
        Gtk.main_quit()
    app.connect("destroy", _on_destroy)
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
