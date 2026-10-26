#!/usr/bin/env python3
"""
SPECTRA - Universal Hardware Telemetry & Logic Board Diagnostics - Desktop GUI
A modern GTK3 application for reading statistics, beverage counters,
maintenance history, active alerts, and live sensors from Jura coffee machines.
"""

import sys
import os
import re
import time
import threading
from datetime import datetime

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango, GdkPixbuf

import serial_io
import profiles_db
import stats_collector as sc

__version__ = "0.4.2"


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

    def __init__(self):
        super().__init__(title=f"SPECTRA — Hardware Telemetry & Diagnostics (v{__version__})")

        # Dynamic monitor-aware initial sizing
        display = Gdk.Display.get_default()
        mon = display.get_primary_monitor() if display else None
        if display and not mon and display.get_n_monitors() > 0:
            mon = display.get_monitor(0)

        if mon:
            workarea = mon.get_workarea()
            default_w = max(760, min(1040, int(workarea.width * 0.85)))
            default_h = max(500, min(700, int(workarea.height * 0.85)))
        else:
            default_w, default_h = 980, 660

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

        # Apply dark modern CSS styling
        self._apply_styling()

        self.session: Optional[sc.JuraStatsSession] = None
        self.is_reading = False
        self.is_polling = False
        self.serial_lock = threading.Lock()
        self.auto_poll_active = False
        self.auto_poll_thread: Optional[threading.Thread] = None

        # Main Layout Box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # Header Bar
        header = self._create_header_bar()
        main_box.pack_start(header, False, False, 0)

        # Progress / Status Strip
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("Ready. Select serial port and click 'Read Statistics'.")
        self.progress_bar.set_fraction(0.0)
        main_box.pack_start(self.progress_bar, False, False, 4)

        # KPI Summary Cards
        kpi_container = self._create_kpi_cards()
        main_box.pack_start(kpi_container, False, False, 8)

        # Main Notebook (Tabs)
        self.notebook = Gtk.Notebook()
        self.notebook.set_tab_pos(Gtk.PositionType.TOP)
        self.notebook.set_scrollable(True)
        main_box.pack_start(self.notebook, True, True, 4)

        # Tab 1: Beverage Counters
        self.beverages_tab = self._create_beverages_tab()
        self.notebook.append_page(self.beverages_tab, Gtk.Label(label="☕ Beverage Counters"))

        # Tab 2: Maintenance & Care
        self.maint_tab = self._create_maintenance_tab()
        self.notebook.append_page(self.maint_tab, Gtk.Label(label="🧼 Maintenance & Hygiene"))

        # Tab 3: Live Sensors & Hardware
        self.sensors_tab = self._create_sensors_tab()
        self.notebook.append_page(self.sensors_tab, Gtk.Label(label="⚡ Live Sensors"))

        # Tab 4: Alerts & Status
        self.alerts_tab = self._create_alerts_tab()
        self.notebook.append_page(self.alerts_tab, Gtk.Label(label="⚠️ Machine Alerts & Status"))

        # Tab 4: Machine Identity
        self.info_tab = self._create_info_tab()
        self.notebook.append_page(self.info_tab, Gtk.Label(label="ℹ️ Appliance Specs"))

        # Tab 5: Protocol Log
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
            min-height: 18px;
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
        app_title.set_markup(f"<b><span size='large' color='#89b4fa'>SPECTRA</span> <span size='small' color='#f9e2af'>v{__version__}</span></b>")
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

        # Port Selector Label & ComboBox
        self.lbl_port = Gtk.Label(label="Port:")
        self.lbl_port.set_valign(Gtk.Align.CENTER)

        self.port_combo = Gtk.ComboBoxText()
        self.port_combo.set_size_request(140, -1)
        self.port_combo.set_valign(Gtk.Align.CENTER)
        for cell in self.port_combo.get_cells():
            cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            cell.set_property("width-chars", 14)
            cell.set_property("max-width-chars", 22)

        # Refresh Ports Button
        self.btn_refresh = Gtk.Button(label="🔄 Refresh")
        self.btn_refresh.set_valign(Gtk.Align.CENTER)
        self.btn_refresh.connect("clicked", lambda w: self._refresh_ports())

        # Spacer
        self.header_spacer = Gtk.Box()
        self.header_spacer.set_hexpand(True)

        # Read Statistics Button
        self.btn_read = Gtk.Button(label="⚡ Read Statistics")
        self.btn_read.get_style_context().add_class("primary-btn")
        self.btn_read.set_valign(Gtk.Align.CENTER)
        self.btn_read.connect("clicked", lambda w: self._on_read_clicked())

        # Export Report Button
        self.btn_export = Gtk.Button(label="💾 Export Report")
        self.btn_export.set_valign(Gtk.Align.CENTER)
        self.btn_export.connect("clicked", lambda w: self._on_export_clicked())

        self._update_header_layout(False)
        return self.header_grid

    def _update_header_layout(self, is_compact: bool):
        if self._header_compact == is_compact:
            return
        self._header_compact = is_compact

        for w in [self.brand_box, self.lbl_port, self.port_combo, self.btn_refresh, self.header_spacer, self.btn_read, self.btn_export]:
            if w.get_parent():
                self.header_grid.remove(w)

        if not is_compact:
            # Standard single-row desktop layout
            self.header_grid.attach(self.brand_box, 0, 0, 1, 1)
            self.header_grid.attach(self.lbl_port, 1, 0, 1, 1)
            self.header_grid.attach(self.port_combo, 2, 0, 1, 1)
            self.header_grid.attach(self.btn_refresh, 3, 0, 1, 1)
            self.header_grid.attach(self.header_spacer, 4, 0, 1, 1)
            self.header_grid.attach(self.btn_read, 5, 0, 1, 1)
            self.header_grid.attach(self.btn_export, 6, 0, 1, 1)
            self.sub_title.set_visible(True)
        else:
            # Compact 2-row layout: Row 0 has Title + Actions, Row 1 has Port + Refresh
            self.header_grid.attach(self.brand_box, 0, 0, 1, 1)
            self.header_grid.attach(self.header_spacer, 1, 0, 1, 1)
            self.header_grid.attach(self.btn_read, 2, 0, 1, 1)
            self.header_grid.attach(self.btn_export, 3, 0, 1, 1)

            # Row 1 connection controls
            self.header_grid.attach(self.lbl_port, 0, 1, 1, 1)
            self.header_grid.attach(self.port_combo, 1, 1, 1, 1)
            self.header_grid.attach(self.btn_refresh, 2, 1, 1, 1)
            self.sub_title.set_visible(False)

        self.header_grid.show_all()

    def _create_kpi_cards(self) -> Gtk.Widget:
        self.kpi_grid = Gtk.Grid()
        self.kpi_grid.set_column_homogeneous(True)
        self.kpi_grid.set_row_spacing(6)
        self.kpi_grid.set_column_spacing(10)
        self.kpi_grid.set_margin_start(10)
        self.kpi_grid.set_margin_end(10)

        def make_card(label_text, default_val):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.get_style_context().add_class("card")
            val_lbl = Gtk.Label(label=default_val)
            val_lbl.get_style_context().add_class("card-value")
            val_lbl.set_xalign(0.0)
            val_lbl.set_yalign(0.5)
            lbl = Gtk.Label(label=label_text)
            lbl.get_style_context().add_class("card-label")
            lbl.set_xalign(0.0)
            lbl.set_yalign(0.5)
            card.pack_start(val_lbl, False, False, 0)
            card.pack_start(lbl, False, False, 0)
            return card, val_lbl

        self.kpi_model_card, self.lbl_kpi_model = make_card("Appliance Model", "No Machine Read")
        self.kpi_total_card, self.lbl_kpi_total = make_card("Total Cups Prepared", "---")
        self.kpi_clean_card, self.lbl_kpi_clean = make_card("Cleanings Performed", "---")
        self.kpi_decalc_card, self.lbl_kpi_decalc = make_card("Descalings Performed", "---")

        self._kpi_cards_list = [self.kpi_model_card, self.kpi_total_card, self.kpi_clean_card, self.kpi_decalc_card]

        self._update_kpi_layout(False)
        return self.kpi_grid

    def _update_kpi_layout(self, is_compact: bool):
        if self._kpi_compact == is_compact:
            return
        self._kpi_compact = is_compact

        for c in self._kpi_cards_list:
            if c.get_parent():
                self.kpi_grid.remove(c)

        if not is_compact:
            # 4 columns x 1 row
            self.kpi_grid.attach(self.kpi_model_card, 0, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_total_card, 1, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_clean_card, 2, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_decalc_card, 3, 0, 1, 1)
        else:
            # 2 columns x 2 rows
            self.kpi_grid.attach(self.kpi_model_card, 0, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_total_card, 1, 0, 1, 1)
            self.kpi_grid.attach(self.kpi_clean_card, 0, 1, 1, 1)
            self.kpi_grid.attach(self.kpi_decalc_card, 1, 1, 1, 1)

        self.kpi_grid.show_all()

    def _create_beverages_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Model: Code(int), Name(str), Count(int), Share(str), Type(str)
        self.bev_store = Gtk.ListStore(int, str, int, str, str)
        self.bev_tree = Gtk.TreeView(model=self.bev_store)

        # Columns
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

    def _create_maintenance_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Model: Label(str), Count(int), Pct_Str(str), Pct_Val(int)
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

        # Progress bar cell renderer for remaining life
        cell_prog = Gtk.CellRendererProgress()
        col_prog = Gtk.TreeViewColumn("Cycle Life Progress", cell_prog, value=3, text=2)
        col_prog.set_min_width(160)
        col_prog.set_resizable(True)
        col_prog.set_expand(True)
        self.maint_tree.append_column(col_prog)

        scrolled.add(self.maint_tree)
        return scrolled

    def _create_sensors_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_border_width(8)
        main_box.set_hexpand(True)
        main_box.set_vexpand(True)

        # Control Bar
        ctrl_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.btn_refresh_sensors = Gtk.Button(label="🔄 Refresh Live Sensors")
        self.btn_refresh_sensors.get_style_context().add_class("primary-btn")
        self.btn_refresh_sensors.set_valign(Gtk.Align.CENTER)
        self.btn_refresh_sensors.connect("clicked", self._on_refresh_sensors_clicked)
        ctrl_bar.pack_start(self.btn_refresh_sensors, False, False, 0)

        self.spinner_sensors = Gtk.Spinner()
        self.spinner_sensors.set_valign(Gtk.Align.CENTER)
        ctrl_bar.pack_start(self.spinner_sensors, False, False, 0)

        # Continuous Live Polling Toggle
        self.chk_auto_poll = Gtk.ToggleButton(label="⏱️ Auto-Poll (2s)")
        self.chk_auto_poll.get_style_context().add_class("toggle-btn")
        self.chk_auto_poll.set_valign(Gtk.Align.CENTER)
        self.chk_auto_poll.connect("toggled", self._on_auto_poll_toggled)
        ctrl_bar.pack_start(self.chk_auto_poll, False, False, 0)

        self.lbl_sensors_status = Gtk.Label(label="Click 'Refresh Live Sensors' or enable Auto-Poll to monitor status.")
        self.lbl_sensors_status.set_xalign(0.0)
        self.lbl_sensors_status.set_valign(Gtk.Align.CENTER)
        self.lbl_sensors_status.set_ellipsize(Pango.EllipsizeMode.END)
        ctrl_bar.pack_start(self.lbl_sensors_status, True, True, 0)

        main_box.pack_start(ctrl_bar, False, False, 4)

        # Live Status Summary Badges Grid
        self.sensor_badges_grid = Gtk.Grid()
        self.sensor_badges_grid.set_column_homogeneous(True)
        self.sensor_badges_grid.set_row_spacing(6)
        self.sensor_badges_grid.set_column_spacing(6)

        def make_sensor_card(title: str, default_val: str, default_sub: str = ""):
            c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            c.get_style_context().add_class("card")
            val_lbl = Gtk.Label(label=default_val)
            val_lbl.get_style_context().add_class("card-value")
            val_lbl.set_xalign(0.5)

            sub_lbl = Gtk.Label(label=default_sub)
            sub_lbl.get_style_context().add_class("card-sub")
            sub_lbl.set_xalign(0.5)

            title_lbl = Gtk.Label(label=title)
            title_lbl.get_style_context().add_class("card-label")
            title_lbl.set_xalign(0.5)
            title_lbl.set_ellipsize(Pango.EllipsizeMode.END)

            c.pack_start(val_lbl, False, False, 1)
            c.pack_start(sub_lbl, False, False, 1)
            c.pack_start(title_lbl, False, False, 1)
            return c, val_lbl, sub_lbl

        self.card_tank, self.lbl_live_tank, self.lbl_sub_tank = make_sensor_card("💧 Water Tank", "UNKNOWN", "Level Float")
        self.card_tray, self.lbl_live_tray, self.lbl_sub_tray = make_sensor_card("📥 Drip Tray", "UNKNOWN", "Microswitch")
        self.card_beans, self.lbl_live_beans, self.lbl_sub_beans = make_sensor_card("🫘 Bean Hopper", "UNKNOWN", "Charge Sensor")
        self.card_state, self.lbl_live_state, self.lbl_sub_state = make_sensor_card("⚡ Machine State", "UNKNOWN", "Operating Status")
        self.card_bu, self.lbl_live_bu, self.lbl_sub_bu = make_sensor_card("⚙️ Brew Unit", "UNKNOWN", "Encoder Pos")
        self.card_coffee, self.lbl_live_coffee_tb, self.lbl_sub_coffee_tb = make_sensor_card("☕ Coffee Heater (TB1)", "UNKNOWN", "Thermoblock 1")
        self.card_steam, self.lbl_live_steam_tb, self.lbl_sub_steam_tb = make_sensor_card("💨 Steam Heater (TB2)", "UNKNOWN", "Thermoblock 2")
        self.card_flow, self.lbl_live_flow, self.lbl_sub_flow = make_sensor_card("🌊 Water Flow", "0.0 ml/s", "Flowmeter Rate")
        self.card_filter, self.lbl_live_filter, self.lbl_sub_filter = make_sensor_card("🛡️ Water Filter", "UNKNOWN", "Hardness")

        self._sensor_cards_list = [
            self.card_state, self.card_bu, self.card_tank, self.card_tray, self.card_beans,
            self.card_coffee, self.card_steam, self.card_flow, self.card_filter
        ]

        self._update_sensor_badges_layout(False)
        main_box.pack_start(self.sensor_badges_grid, False, False, 4)

        # Paned view for Diagnostics and Counters
        self.sensors_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.sensors_paned.set_size_request(-1, 260)
        self.sensors_paned.set_vexpand(True)
        self.sensors_paned.set_hexpand(True)
        self.sensors_paned.connect("size-allocate", self._on_paned_size_allocate)

        # Left: Hardware Health & Safety Diagnostics
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_left = Gtk.Label(label="<b>🔍 Hardware Component Diagnostics &amp; Safety Sensors</b>")
        lbl_left.set_use_markup(True)
        lbl_left.set_xalign(0.0)
        left_box.pack_start(lbl_left, False, False, 2)

        scrolled_left = Gtk.ScrolledWindow()
        scrolled_left.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_left.set_vexpand(True)

        self.live_sensors_store = Gtk.ListStore(str, str, str, str)
        self.live_sensors_tree = Gtk.TreeView(model=self.live_sensors_store)

        col_st = Gtk.TreeViewColumn("Status", Gtk.CellRendererText(), text=0)
        col_st.set_min_width(80)
        col_st.set_resizable(True)
        self.live_sensors_tree.append_column(col_st)

        col_sname = Gtk.TreeViewColumn("Diagnostic Sensor / Component", Gtk.CellRendererText(), text=1)
        col_sname.set_min_width(170)
        col_sname.set_resizable(True)
        col_sname.set_expand(True)
        self.live_sensors_tree.append_column(col_sname)

        col_sdet = Gtk.TreeViewColumn("Verification Details", Gtk.CellRendererText(), text=3)
        col_sdet.set_min_width(170)
        col_sdet.set_resizable(True)
        col_sdet.set_expand(True)
        self.live_sensors_tree.append_column(col_sdet)

        scrolled_left.add(self.live_sensors_tree)
        left_box.pack_start(scrolled_left, True, True, 0)
        self.sensors_paned.pack1(left_box, True, False)

        # Right: Historical Sensor Trip & Fault Frequency Counters
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_right = Gtk.Label(label="<b>📊 Historical Sensor Fault &amp; Trip Frequency Counters</b>")
        lbl_right.set_use_markup(True)
        lbl_right.set_xalign(0.0)
        right_box.pack_start(lbl_right, False, False, 2)

        scrolled_right = Gtk.ScrolledWindow()
        scrolled_right.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_right.set_vexpand(True)

        self.live_counters_store = Gtk.ListStore(str, int, str)
        self.live_counters_tree = Gtk.TreeView(model=self.live_counters_store)

        col_cname = Gtk.TreeViewColumn("Fault / Event Category", Gtk.CellRendererText(), text=0)
        col_cname.set_min_width(170)
        col_cname.set_resizable(True)
        col_cname.set_expand(True)
        self.live_counters_tree.append_column(col_cname)

        col_cnt = Gtk.TreeViewColumn("Trip Count", Gtk.CellRendererText(), text=1)
        col_cnt.set_min_width(80)
        col_cnt.set_resizable(True)
        self.live_counters_tree.append_column(col_cnt)

        col_cass = Gtk.TreeViewColumn("Evaluation", Gtk.CellRendererText(), text=2)
        col_cass.set_min_width(110)
        col_cass.set_resizable(True)
        col_cass.set_expand(True)
        self.live_counters_tree.append_column(col_cass)

        scrolled_right.add(self.live_counters_tree)
        right_box.pack_start(scrolled_right, True, True, 0)
        self.sensors_paned.pack2(right_box, True, False)

        main_box.pack_start(self.sensors_paned, True, True, 4)
        scrolled.add(main_box)
        return scrolled

    def _on_paned_size_allocate(self, paned, allocation):
        target_orient = Gtk.Orientation.VERTICAL if allocation.width < 760 else Gtk.Orientation.HORIZONTAL
        if paned.get_orientation() != target_orient:
            paned.set_orientation(target_orient)
        if target_orient == Gtk.Orientation.HORIZONTAL:
            # Dynamically maintain proportional 55%/45% split
            target_pos = int(allocation.width * 0.55)
            current_pos = paned.get_position()
            if abs(current_pos - target_pos) > 25:
                paned.set_position(target_pos)

    def _update_sensor_badges_layout(self, is_compact: bool):
        if self._sensor_compact == is_compact:
            return
        self._sensor_compact = is_compact

        for c in self._sensor_cards_list:
            if c.get_parent():
                self.sensor_badges_grid.remove(c)

        if not is_compact:
            # 5 columns across
            # Row 0: State, BU, Tank, Tray, Beans
            self.sensor_badges_grid.attach(self.card_state, 0, 0, 1, 1)
            self.sensor_badges_grid.attach(self.card_bu, 1, 0, 1, 1)
            self.sensor_badges_grid.attach(self.card_tank, 2, 0, 1, 1)
            self.sensor_badges_grid.attach(self.card_tray, 3, 0, 1, 1)
            self.sensor_badges_grid.attach(self.card_beans, 4, 0, 1, 1)

            # Row 1: Coffee, Steam, Flow, Filter (spans 2)
            self.sensor_badges_grid.attach(self.card_coffee, 0, 1, 1, 1)
            self.sensor_badges_grid.attach(self.card_steam, 1, 1, 1, 1)
            self.sensor_badges_grid.attach(self.card_flow, 2, 1, 1, 1)
            self.sensor_badges_grid.attach(self.card_filter, 3, 1, 2, 1)
        else:
            # 3 columns across x 3 rows
            # Row 0: State, BU, Tank
            self.sensor_badges_grid.attach(self.card_state, 0, 0, 1, 1)
            self.sensor_badges_grid.attach(self.card_bu, 1, 0, 1, 1)
            self.sensor_badges_grid.attach(self.card_tank, 2, 0, 1, 1)

            # Row 1: Tray, Beans, Flow
            self.sensor_badges_grid.attach(self.card_tray, 0, 1, 1, 1)
            self.sensor_badges_grid.attach(self.card_beans, 1, 1, 1, 1)
            self.sensor_badges_grid.attach(self.card_flow, 2, 1, 1, 1)

            # Row 2: Coffee, Steam, Filter
            self.sensor_badges_grid.attach(self.card_coffee, 0, 2, 1, 1)
            self.sensor_badges_grid.attach(self.card_steam, 1, 2, 1, 1)
            self.sensor_badges_grid.attach(self.card_filter, 2, 2, 1, 1)

        self.sensor_badges_grid.show_all()

    def _create_alerts_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Model: Severity(str), AlertName(str), Bit(int)
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
        hero_title.set_markup(f"<b><span size='large' color='#89b4fa'>SPECTRA Diagnostic Suite</span> <span size='small' color='#f9e2af'>v{__version__}</span></b>")
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

        # Specs TreeView in its own scrolled container
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
        header_compact = allocation.width < 860
        kpi_compact = allocation.width < 800
        sensor_compact = allocation.width < 860

        needs_reflow = (
            self._header_compact != header_compact or
            self._kpi_compact != kpi_compact or
            self._sensor_compact != sensor_compact
        )
        if needs_reflow:
            self._pending_reflow = (header_compact, kpi_compact, sensor_compact)
            if not getattr(self, "_reflow_scheduled", False):
                self._reflow_scheduled = True
                GLib.idle_add(self._do_pending_reflow)

    def _do_pending_reflow(self):
        self._reflow_scheduled = False
        if hasattr(self, "_pending_reflow") and self._pending_reflow:
            h_comp, k_comp, s_comp = self._pending_reflow
            self._update_header_layout(h_comp)
            self._update_kpi_layout(k_comp)
            self._update_sensor_badges_layout(s_comp)
            self._pending_reflow = None
        return False

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_clear = Gtk.Button(label="Clear Log")
        btn_clear.connect("clicked", lambda w: self.log_buffer.set_text(""))
        btn_box.pack_start(btn_clear, False, False, 4)
        box.pack_start(btn_box, False, False, 4)

        return box

    def _refresh_ports(self):
        self.port_combo.remove_all()
        ports = serial_io.list_serial_ports()
        active_idx = 0
        for idx, p in enumerate(ports):
            self.port_combo.append_text(p)
            if p.startswith("/dev/ttyUSB"):
                active_idx = idx
        if ports:
            self.port_combo.set_active(active_idx)

    def _append_log(self, text: str):
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, text + "\n")
        # Scroll to bottom
        adj = self.log_view.get_vadjustment()
        if adj:
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def _on_read_clicked(self):
        if self.is_reading:
            return

        active_port = self.port_combo.get_active_text()
        if not active_port:
            self.progress_bar.set_text("No port selected!")
            return

        self.is_reading = True
        self.btn_read.set_sensitive(False)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text(f"Connecting to {active_port}...")

        # Run reading session in background thread
        thread = threading.Thread(target=self._run_session_worker, args=(active_port,), daemon=True)
        thread.start()

    def _run_session_worker(self, port: str):
        with self.serial_lock:
            session = sc.JuraStatsSession(port, baudrate=9600, log_cb=lambda msg: GLib.idle_add(self._append_log, msg))

            def update_prog(pct, status):
                GLib.idle_add(self.progress_bar.set_fraction, pct)
                GLib.idle_add(self.progress_bar.set_text, f"[{int(pct*100)}%] {status}")

            success = session.run_interrogation(progress_cb=update_prog)
        GLib.idle_add(self._on_session_finished, session, success)

    def _on_session_finished(self, session: sc.JuraStatsSession, success: bool):
        self.is_reading = False
        self.btn_read.set_sensitive(True)
        self.session = session

        if not success:
            self.progress_bar.set_fraction(1.0)
            self.progress_bar.set_text("Interrogation failed! Check port connection / permissions.")
            return

        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_text(f"Successfully read statistics from {session.model_family}!")

        # Populate GUI views
        summary = session.get_structured_summary()

        # Update KPI Cards
        self.lbl_kpi_model.set_text(summary["machine_model"])
        self.lbl_kpi_total.set_text(f"{summary['total_cups']:,}")

        clean_cnt = 0
        decalc_cnt = 0
        for m in summary.get("maintenance", []):
            m_lbl = m.get("label", "").lower()
            if m_lbl in ("cleaning", "cleanings"):
                clean_cnt = m.get("count", 0)
            elif "decalc" in m_lbl or "descal" in m_lbl:
                decalc_cnt = m.get("count", 0)
        self.lbl_kpi_clean.set_text(f"{clean_cnt:,}")
        self.lbl_kpi_decalc.set_text(f"{decalc_cnt:,}")

        # Populate Beverages Tab
        self.bev_store.clear()
        tot = summary["total_cups"] or 1
        for b in sorted(summary["beverages"], key=lambda x: x["count"], reverse=True):
            share = f"{(b['count'] / tot) * 100:.1f}%" if b["count"] > 0 else "0.0%"
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
        if summary.get("telemetry") and "appliance_type" in summary["telemetry"]:
            self.info_store.append(["Appliance Type", str(summary["telemetry"]["appliance_type"])])
        self.info_store.append(["Machine Family", summary["machine_model"]])
        if summary.get("telemetry"):
            tel = summary["telemetry"]
            if "serial_number" in tel and tel["serial_number"] != "N/A":
                self.info_store.append(["Serial Number (14-Digit)", str(tel["serial_number"])])
            if "ean_code" in tel and tel["ean_code"] != "N/A":
                self.info_store.append(["EAN-Code", str(tel["ean_code"])])
            if "article_number" in tel:
                self.info_store.append(["Article Number", str(tel["article_number"])])
            if "production_date" in tel and tel["production_date"] != "N/A":
                self.info_store.append(["Date of Production", str(tel["production_date"])])
            if "appliance_number" in tel and tel["appliance_number"]:
                self.info_store.append(["Appliance Number", str(tel["appliance_number"])])
            if "serial_number_word" in tel and tel["serial_number_word"]:
                self.info_store.append(["Logic Board Serial (ID)", str(tel["serial_number_word"])])
            if "appliance_code" in tel and tel["appliance_code"] != "N/A":
                self.info_store.append(["Appliance Code", str(tel["appliance_code"])])
            if "software_version_display" in tel:
                self.info_store.append(["Software Version Display", str(tel["software_version_display"])])
            if "spdl_country_code" in tel and tel["spdl_country_code"] != "N/A":
                self.info_store.append(["SPDL Country Code", str(tel["spdl_country_code"])])
            if "spdl_download_date" in tel and tel["spdl_download_date"] != "N/A":
                self.info_store.append(["SPDL Date Download", str(tel["spdl_download_date"])])
            if "spdl_language_date" in tel and tel["spdl_language_date"] != "N/A":
                self.info_store.append(["SPDL Date Language File", str(tel["spdl_language_date"])])
            if "water_hardness_dh" in tel:
                self.info_store.append(["Water Hardness", f"{tel['water_hardness_dh']} °dH"])
            if "cups_since_intervention" in tel:
                self.info_store.append(["Cups Since Last Intervention", f"{tel['cups_since_intervention']:,}"])
            if "preparations_since_intervention" in tel:
                self.info_store.append(["Preparations Since Last Intervention", f"{tel['preparations_since_intervention']:,}"])
        self.info_store.append(["Firmware Identifier", summary["firmware_string"]])
        self.info_store.append(["Profile EF Code", summary["ef_code"]])
        if summary.get("telemetry"):
            tel = summary["telemetry"]
            if "grinder_formatted" in tel:
                self.info_store.append(["Grinder Operating Time", f"{tel['grinder_formatted']} ({tel.get('grinder_seconds', 0)} s)"])
            if "water_dispensed_liters" in tel:
                self.info_store.append(["Total Water Dispensed", f"{tel['water_dispensed_liters']} Liters"])
            if "descaling_agent_liters" in tel:
                self.info_store.append(["Descaling Agent Consumed", f"{tel['descaling_agent_liters']} Liters"])
            if "since_last_service_preparations" in tel:
                self.info_store.append(["Cycles Since Last Service", f"{tel['since_last_service_preparations']} preparations"])
        self.info_store.append(["Power Specification", summary.get("power_spec", "N/A")])
        self.info_store.append(["Total Cups Dispensed", f"{summary['total_cups']:,}"])
        self.info_store.append(["Total Brew Cycles", f"{summary['total_preparations']:,}"])
        self.info_store.append(["Serial Port", summary["port"]])
        self.info_store.append(["Baud Rate", "9600 Baud (8-N-1)"])
        self.info_store.append(["Protocol Mode", summary.get("protocol_mode", "ASCII Optical")])
        self.info_store.append(["Diagnostics Timestamp", summary["timestamp"]])

        # Populate Live Sensors Tab if available from session
        if hasattr(session, "live_sensors") and session.live_sensors:
            self._on_live_sensors_updated(session.live_sensors)

    def _on_auto_poll_toggled(self, widget):
        if self.chk_auto_poll.get_active():
            self.auto_poll_active = True
            self.btn_refresh_sensors.set_sensitive(False)
            self.lbl_sensors_status.set_text("Continuous auto-polling active (2s)...")
            if self.auto_poll_thread is None or not self.auto_poll_thread.is_alive():
                self.auto_poll_thread = threading.Thread(target=self._auto_poll_worker, daemon=True)
                self.auto_poll_thread.start()
        else:
            self.auto_poll_active = False
            self.btn_refresh_sensors.set_sensitive(True)
            self.lbl_sensors_status.set_text("Auto-poll stopped. Ready for manual refresh.")

    def _auto_poll_worker(self):
        conn: Optional[serial_io.JuraSerialConnection] = None
        current_port = None
        try:
            while self.auto_poll_active:
                if self.is_reading:
                    time.sleep(0.5)
                    continue

                active_port = self.port_combo.get_active_text()
                if not active_port:
                    time.sleep(1.0)
                    continue

                # Maintain persistent connection across fast polls
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
                        res = sc.query_live_sensors(active_port, conn=conn, fast_poll=True)
                    except Exception as e:
                        res = {"error": str(e)}

                if self.auto_poll_active:
                    GLib.idle_add(self._on_live_sensors_updated, res)

                # Sleep 1.5s in 100ms slices to allow immediate cancellation
                for _ in range(15):
                    if not self.auto_poll_active:
                        break
                    time.sleep(0.1)
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
                    result = sc.query_live_sensors(active_port, baudrate=9600, fast_poll=False)
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

        if "error" in result:
            self.lbl_sensors_status.set_text(f"Poll notice: {result['error']}")
            return

        ts = result.get("timestamp", datetime.now().strftime("%H:%M:%S"))
        proto = result.get("protocol", "UART")
        mode_tag = "auto" if self.auto_poll_active else "manual"
        self.lbl_sensors_status.set_text(f"Last polled ({mode_tag}): {ts} (via {proto})")

        # Update KPI Cards
        switches = {sw["id"]: sw for sw in result.get("switches", [])}

        # Water Tank
        if "water_tank" in switches:
            sw = switches["water_tank"]
            self.lbl_live_tank.set_text("WATER OK" if sw["ok"] else "LOW / EMPTY")
            self.lbl_sub_tank.set_text("Float Sensor Nominal" if sw["ok"] else "Refill Water Tank")
        else:
            self.lbl_live_tank.set_text("NOMINAL")
            self.lbl_sub_tank.set_text("Float Sensor OK")

        # Drip Tray
        if "drip_tray" in switches:
            sw = switches["drip_tray"]
            self.lbl_live_tray.set_text("INSERTED" if sw["ok"] else "MISSING")
            self.lbl_sub_tray.set_text("Drawer Inserted" if sw["ok"] else "Tray / Drawer Removed")
        else:
            self.lbl_live_tray.set_text("INSERTED")
            self.lbl_sub_tray.set_text("Tray OK")

        # Bean Hopper
        if "bean_hopper" in switches:
            sw = switches["bean_hopper"]
            if sw["ok"]:
                self.lbl_live_beans.set_text("BEANS OK")
                self.lbl_sub_beans.set_text("Hopper Charged")
            else:
                self.lbl_live_beans.set_markup("<span color='#fab387'>FILL BEANS</span>")
                self.lbl_sub_beans.set_text("Refill Coffee Beans")
        else:
            self.lbl_live_beans.set_text("BEANS OK")
            self.lbl_sub_beans.set_text("Hopper OK")

        # Machine State
        if "machine_ready" in switches:
            sw = switches["machine_ready"]
            st = sw.get("status", "")
            badge = sw.get("badge", "")
            if sw["ok"]:
                self.lbl_live_state.set_markup("<span color='#a6e3a1'>READY TO BREW</span>")
                self.lbl_sub_state.set_text("Appliance Ready")
            else:
                if badge == "BREWING" or "Brewing" in st:
                    self.lbl_live_state.set_markup("<span color='#89dceb'>BREWING</span>")
                    self.lbl_sub_state.set_text(st)
                elif badge == "DISPENSING" or "Dispensing" in st or "Rinsing" in st:
                    self.lbl_live_state.set_markup("<span color='#89dceb'>DISPENSING</span>")
                    self.lbl_sub_state.set_text(st)
                elif badge == "MOVING" or "Brew Unit Active" in st:
                    self.lbl_live_state.set_markup("<span color='#89dceb'>MOVING</span>")
                    self.lbl_sub_state.set_text(st)
                elif badge == "VALVE BUSY" or "Valve" in st:
                    self.lbl_live_state.set_markup("<span color='#89dceb'>VALVE BUSY</span>")
                    self.lbl_sub_state.set_text(st)
                elif "Press Maintenance" in st or "Maintenance" in st:
                    self.lbl_live_state.set_markup("<span color='#fab387'>PRESS MAINTENANCE</span>")
                    if "Repeated No Flow" in st or "Filling Loop" in st:
                        self.lbl_sub_state.set_text("Filling Loop (Repeated No Flow)")
                    else:
                        self.lbl_sub_state.set_text("System Fill Required")
                elif "Clogged" in st:
                    self.lbl_live_state.set_markup("<span color='#f38ba8'>SYSTEM CLOGGED</span>")
                    self.lbl_sub_state.set_text("Hydraulic Blockage Detected")
                elif "Tray Missing" in st or ("drip_tray" in switches and not switches["drip_tray"]["ok"]):
                    self.lbl_live_state.set_markup("<span color='#fab387'>NOT READY</span>")
                    self.lbl_sub_state.set_text("Insert Drip Tray")
                elif "Water" in st or ("water_tank" in switches and not switches["water_tank"]["ok"]):
                    self.lbl_live_state.set_markup("<span color='#fab387'>NOT READY</span>")
                    self.lbl_sub_state.set_text("Fill Water Tank")
                elif "Grounds" in st:
                    self.lbl_live_state.set_markup("<span color='#fab387'>NOT READY</span>")
                    self.lbl_sub_state.set_text("Empty Grounds Container")
                elif "Beans" in st or ("bean_hopper" in switches and not switches["bean_hopper"]["ok"]):
                    self.lbl_live_state.set_markup("<span color='#fab387'>NOT READY</span>")
                    self.lbl_sub_state.set_text("Fill Coffee Beans")
                elif "Heating" in st:
                    self.lbl_live_state.set_markup("<span color='#f9e2af'>HEATING UP</span>")
                    self.lbl_sub_state.set_text("Heating Thermoblock")
                elif "Busy" in st:
                    self.lbl_live_state.set_markup("<span color='#89dceb'>BUSY</span>")
                    self.lbl_sub_state.set_text("Operation in Progress")
                elif "Hardware Fault" in st:
                    self.lbl_live_state.set_markup("<span color='#f38ba8'>HARDWARE FAULT</span>")
                    self.lbl_sub_state.set_text(st.replace("Hardware Fault (", "").replace(")", ""))
                else:
                    self.lbl_live_state.set_markup("<span color='#f38ba8'>NOT READY</span>")
                    self.lbl_sub_state.set_text(sw.get("badge", "Check Appliance"))
        else:
            self.lbl_live_state.set_markup("<span color='#a6e3a1'>READY</span>")
            self.lbl_sub_state.set_text("Nominal")

        # Thermoblock Heaters & Thermal Sensors
        telem = result.get("telemetry", {})

        # Brew Unit Position (Encoder)
        bu_pos = telem.get("bu_encoder_pos", 0)
        bu_ref = telem.get("bu_encoder_upper", 0)
        bu_short = telem.get("bu_position_short", "Home / Mill")
        bu_pct = telem.get("bu_stroke_pct", 0)
        bu_ok = telem.get("bu_init_ok", True)
        if bu_pos > 0:
            self.lbl_live_bu.set_text(f"{bu_pos} / {bu_ref}")
            self.lbl_sub_bu.set_text(f"{bu_short} ({bu_pct}%)" if bu_ok else "Position Fault")
        else:
            self.lbl_live_bu.set_text("NOMINAL" if bu_ok else "FAULT")
            self.lbl_sub_bu.set_text("Home Position OK" if bu_ok else "Check Brew Unit")
        if "heater_coffee_str" in telem:
            self.lbl_live_coffee_tb.set_text(telem["heater_coffee_str"])
            self.lbl_sub_coffee_tb.set_text(telem.get("heater_coffee_status", "Ready to Brew"))
        elif "heater_ntc_raw" in telem:
            self.lbl_live_coffee_tb.set_text(f"ADC {telem['heater_ntc_raw']}")
            self.lbl_sub_coffee_tb.set_text("Nominal")
        else:
            self.lbl_live_coffee_tb.set_text("NOMINAL")
            self.lbl_sub_coffee_tb.set_text("Standby")

        is_dual = telem.get("is_dual_heater", False)
        if is_dual:
            s_str = telem.get("heater_steam_str", "Installed")
            s_stat = telem.get("heater_steam_status", "Ready for Steam")
            self.lbl_live_steam_tb.set_text(s_str)
            self.lbl_sub_steam_tb.set_text(s_stat)
        else:
            self.lbl_live_steam_tb.set_text("Not Installed")
            self.lbl_sub_steam_tb.set_text("Single Heater Model")

        # Filter / Hardness (Manual refresh only)
        if "water_hardness_dh" in telem:
            dh = telem["water_hardness_dh"]
            claris = telem.get("filter_claris_active", False)
            ext = telem.get("filter_ext_active", False)
            self.lbl_live_filter.set_text(f"{dh} °dH")
            mode_desc = "CLARIS Active" if claris else ("External Active" if ext else "Bypass Mode")
            self.lbl_sub_filter.set_text(mode_desc)

        # Water Flow Rate (ml/s) & Cycle Delivered Volume
        flow_rate = telem.get("flow_rate_ml_s", 0.0)
        flow_pulses = telem.get("flow_pulses", 0)
        flow_vol = telem.get("flow_volume_ml", 0.0)
        if flow_rate > 0.0:
            self.lbl_live_flow.set_markup(f"<span color='#89dceb'><b>{flow_rate:.1f} ml/s</b></span>")
            self.lbl_sub_flow.set_text(f"Flowing ({flow_vol:.1f} ml / {flow_pulses} P)")
        else:
            self.lbl_live_flow.set_text("0.0 ml/s")
            self.lbl_sub_flow.set_text("No Flow / Idle" if flow_pulses == 0 else f"Cycle: {flow_vol:.1f} ml ({flow_pulses} P)")

        # Populate Hardware Diagnostics Store
        self.live_sensors_store.clear()
        for s in result.get("sensors", []):
            st_icon = "🟢 NOMINAL" if s.get("ok", True) else "🔴 FAULT"
            self.live_sensors_store.append([
                st_icon,
                s.get("name", "Unknown Sensor"),
                s.get("badge", "NOMINAL"),
                s.get("details", "")
            ])

        # Populate Error Counters Store
        self.live_counters_store.clear()
        for c_name, c_cnt in result.get("error_counters", {}).items():
            eval_str = "Nominal (0 events)" if c_cnt == 0 else f"⚠️ Recorded {c_cnt} event(s)"
            self.live_counters_store.append([c_name, c_cnt, eval_str])

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
