#!/usr/bin/env python3
"""
W.R.A.T. - WhiteRat Asynchronous Telemetry - Desktop GUI
A modern GTK3 application for reading statistics, beverage counters,
maintenance history, active alerts, and live sensors from Jura coffee machines.
"""

import sys
import os
import time
import threading
from datetime import datetime

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

import serial_io
import profiles_db
import stats_collector as sc
from wrat_engine import WRATSession
from drivers import DRIVER_DISPLAY_NAMES

__version__ = "0.3.4_mm"


class JuraDiagApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="W.R.A.T. — WhiteRat Asynchronous Telemetry (v0.3.4_mm)")
        self.set_default_size(1060, 720)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Apply dark modern CSS styling
        self._apply_styling()

        self.session: Optional[Any] = None
        self.wrat_session: Optional[WRATSession] = None
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
        button.primary-btn {
            background: linear-gradient(to bottom, #89b4fa, #74c7ec);
            color: #11111b;
            font-weight: bold;
            border-radius: 6px;
            padding: 6px 16px;
            border: none;
        }
        button.primary-btn:hover {
            background: #b4befe;
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
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_box.get_style_context().add_class("header-panel")

        # Title & Icon
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        app_title = Gtk.Label()
        app_title.set_markup("<b><span size='large' color='#89b4fa'>W.R.A.T.</span> <span size='small' color='#f9e2af'>v0.3.4_mm</span></b>")
        app_title.set_alignment(0, 0.5)
        sub_title = Gtk.Label(label="WhiteRat Asynchronous Telemetry — Multi-Manufacturer Engine")
        sub_title.get_style_context().add_class("card-label")
        sub_title.set_alignment(0, 0.5)
        title_box.pack_start(app_title, False, False, 0)
        title_box.pack_start(sub_title, False, False, 0)
        header_box.pack_start(title_box, False, False, 10)

        # Manufacturer / Brand Selector
        lbl_mfr = Gtk.Label(label="Brand:")
        header_box.pack_start(lbl_mfr, False, False, 0)

        self.mfr_combo = Gtk.ComboBoxText()
        self.mfr_combo.append("auto", "⚡ Auto-Detect")
        self.mfr_combo.append("jura", "☕ Jura")
        self.mfr_combo.append("nivona", "☕ Nivona")
        self.mfr_combo.append("lamanti-kl", "🏢 Lamanti-KL (Kalerm)")
        self.mfr_combo.append("lamanti-jn", "🥤 Lamanti-JN (Jetinno)")
        self.mfr_combo.set_active_id("auto")
        header_box.pack_start(self.mfr_combo, False, False, 0)

        # Port Selector Label
        lbl_port = Gtk.Label(label="Port:")
        header_box.pack_start(lbl_port, False, False, 0)

        # Port ComboBox
        self.port_combo = Gtk.ComboBoxText()
        self.port_combo.set_size_request(240, -1)
        header_box.pack_start(self.port_combo, False, False, 0)

        # Refresh Ports Button
        btn_refresh = Gtk.Button(label="🔄 Refresh")
        btn_refresh.connect("clicked", lambda w: self._refresh_ports())
        header_box.pack_start(btn_refresh, False, False, 0)

        # Spacer
        spacer = Gtk.Box()
        header_box.pack_start(spacer, True, True, 0)

        # Read Statistics Button
        self.btn_read = Gtk.Button(label="⚡ Read Statistics")
        self.btn_read.get_style_context().add_class("primary-btn")
        self.btn_read.connect("clicked", lambda w: self._on_read_clicked())
        header_box.pack_start(self.btn_read, False, False, 0)

        # Export Report Button
        self.btn_export = Gtk.Button(label="💾 Export Report")
        self.btn_export.connect("clicked", lambda w: self._on_export_clicked())
        header_box.pack_start(self.btn_export, False, False, 0)

        return header_box

    def _create_kpi_cards(self) -> Gtk.Widget:
        grid = Gtk.Grid()
        grid.set_column_homogeneous(True)
        grid.set_row_spacing(6)
        grid.set_column_spacing(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)

        def make_card(label_text, default_val):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.get_style_context().add_class("card")
            val_lbl = Gtk.Label(label=default_val)
            val_lbl.get_style_context().add_class("card-value")
            val_lbl.set_alignment(0, 0.5)
            lbl = Gtk.Label(label=label_text)
            lbl.get_style_context().add_class("card-label")
            lbl.set_alignment(0, 0.5)
            card.pack_start(val_lbl, False, False, 0)
            card.pack_start(lbl, False, False, 0)
            return card, val_lbl

        self.kpi_model_card, self.lbl_kpi_model = make_card("Appliance Model", "No Machine Read")
        self.kpi_total_card, self.lbl_kpi_total = make_card("Total Cups Prepared", "---")
        self.kpi_clean_card, self.lbl_kpi_clean = make_card("Cleanings Performed", "---")
        self.kpi_decalc_card, self.lbl_kpi_decalc = make_card("Descalings Performed", "---")

        grid.attach(self.kpi_model_card, 0, 0, 1, 1)
        grid.attach(self.kpi_total_card, 1, 0, 1, 1)
        grid.attach(self.kpi_clean_card, 2, 0, 1, 1)
        grid.attach(self.kpi_decalc_card, 3, 0, 1, 1)

        return grid

    def _create_beverages_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Model: Code(int), Name(str), Count(int), Share(str), Type(str)
        self.bev_store = Gtk.ListStore(int, str, int, str, str)
        self.bev_tree = Gtk.TreeView(model=self.bev_store)

        # Columns
        col_name = Gtk.TreeViewColumn("Beverage Specialty", Gtk.CellRendererText(), text=1)
        col_name.set_sort_column_id(1)
        col_name.set_min_width(260)
        self.bev_tree.append_column(col_name)

        col_count = Gtk.TreeViewColumn("Quantity Prepared", Gtk.CellRendererText(), text=2)
        col_count.set_sort_column_id(2)
        col_count.set_min_width(150)
        self.bev_tree.append_column(col_count)

        col_share = Gtk.TreeViewColumn("Share of Total", Gtk.CellRendererText(), text=3)
        col_share.set_sort_column_id(3)
        col_share.set_min_width(130)
        self.bev_tree.append_column(col_share)

        col_type = Gtk.TreeViewColumn("Category / Serving", Gtk.CellRendererText(), text=4)
        col_type.set_sort_column_id(4)
        col_type.set_min_width(150)
        self.bev_tree.append_column(col_type)

        col_code = Gtk.TreeViewColumn("Product Code", Gtk.CellRendererText(), text=0)
        col_code.set_sort_column_id(0)
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
        col_lbl.set_min_width(240)
        self.maint_tree.append_column(col_lbl)

        col_cnt = Gtk.TreeViewColumn("Execution Count", Gtk.CellRendererText(), text=1)
        col_cnt.set_min_width(140)
        self.maint_tree.append_column(col_cnt)

        # Progress bar cell renderer for remaining life
        cell_prog = Gtk.CellRendererProgress()
        col_prog = Gtk.TreeViewColumn("Cycle Life Progress", cell_prog, value=3, text=2)
        col_prog.set_min_width(250)
        self.maint_tree.append_column(col_prog)

        scrolled.add(self.maint_tree)
        return scrolled

    def _create_sensors_tab(self) -> Gtk.Widget:
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_border_width(8)

        # Control Bar
        ctrl_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.btn_refresh_sensors = Gtk.Button(label="🔄 Refresh Live Sensors")
        self.btn_refresh_sensors.get_style_context().add_class("primary-btn")
        self.btn_refresh_sensors.connect("clicked", self._on_refresh_sensors_clicked)
        ctrl_bar.pack_start(self.btn_refresh_sensors, False, False, 0)

        self.spinner_sensors = Gtk.Spinner()
        ctrl_bar.pack_start(self.spinner_sensors, False, False, 0)

        # Continuous Live Polling Toggle
        self.chk_auto_poll = Gtk.CheckButton(label="⏱️ Auto-Poll (2s)")
        self.chk_auto_poll.connect("toggled", self._on_auto_poll_toggled)
        ctrl_bar.pack_start(self.chk_auto_poll, False, False, 4)

        self.lbl_sensors_status = Gtk.Label(label="Click 'Refresh Live Sensors' or enable Auto-Poll to monitor status.")
        self.lbl_sensors_status.set_xalign(0.0)
        ctrl_bar.pack_start(self.lbl_sensors_status, True, True, 0)

        main_box.pack_start(ctrl_bar, False, False, 4)

        # Live Status Summary Badges
        badges_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        badges_box.set_homogeneous(True)

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

            c.pack_start(val_lbl, False, False, 1)
            c.pack_start(sub_lbl, False, False, 1)
            c.pack_start(title_lbl, False, False, 1)
            return c, val_lbl, sub_lbl

        card_tank, self.lbl_live_tank, self.lbl_sub_tank = make_sensor_card("💧 Water Tank", "UNKNOWN", "Level Float")
        card_tray, self.lbl_live_tray, self.lbl_sub_tray = make_sensor_card("📥 Drip Tray", "UNKNOWN", "Microswitch")
        card_state, self.lbl_live_state, self.lbl_sub_state = make_sensor_card("⚡ Machine State", "UNKNOWN", "Operating Status")
        card_coffee, self.lbl_live_coffee_tb, self.lbl_sub_coffee_tb = make_sensor_card("☕ Coffee Heater (TB1)", "UNKNOWN", "Thermoblock 1")
        card_steam, self.lbl_live_steam_tb, self.lbl_sub_steam_tb = make_sensor_card("💨 Steam Heater (TB2)", "UNKNOWN", "Thermoblock 2")
        card_flow, self.lbl_live_flow, self.lbl_sub_flow = make_sensor_card("🌊 Water Flow", "0.0 ml/s", "Flowmeter Rate")
        card_filter, self.lbl_live_filter, self.lbl_sub_filter = make_sensor_card("🛡️ Water Filter", "UNKNOWN", "Hardness")

        badges_box.pack_start(card_tank, True, True, 0)
        badges_box.pack_start(card_tray, True, True, 0)
        badges_box.pack_start(card_state, True, True, 0)
        badges_box.pack_start(card_coffee, True, True, 0)
        badges_box.pack_start(card_steam, True, True, 0)
        badges_box.pack_start(card_flow, True, True, 0)
        badges_box.pack_start(card_filter, True, True, 0)

        main_box.pack_start(badges_box, False, False, 4)

        # Paned view for Diagnostics and Counters
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(580)

        # Left: Hardware Health & Safety Diagnostics
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_left = Gtk.Label(label="<b>🔍 Hardware Component Diagnostics &amp; Safety Sensors</b>")
        lbl_left.set_use_markup(True)
        lbl_left.set_xalign(0.0)
        left_box.pack_start(lbl_left, False, False, 2)

        scrolled_left = Gtk.ScrolledWindow()
        scrolled_left.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Model: StatusIcon(str), SensorName(str), Badge(str), Details(str)
        self.live_sensors_store = Gtk.ListStore(str, str, str, str)
        self.live_sensors_tree = Gtk.TreeView(model=self.live_sensors_store)

        col_st = Gtk.TreeViewColumn("Status", Gtk.CellRendererText(), text=0)
        col_st.set_min_width(100)
        self.live_sensors_tree.append_column(col_st)

        col_sname = Gtk.TreeViewColumn("Diagnostic Sensor / Component", Gtk.CellRendererText(), text=1)
        col_sname.set_min_width(220)
        self.live_sensors_tree.append_column(col_sname)

        col_sdet = Gtk.TreeViewColumn("Verification Details", Gtk.CellRendererText(), text=3)
        col_sdet.set_min_width(260)
        self.live_sensors_tree.append_column(col_sdet)

        scrolled_left.add(self.live_sensors_tree)
        left_box.pack_start(scrolled_left, True, True, 0)
        paned.pack1(left_box, True, False)

        # Right: Historical Sensor Trip & Fault Frequency Counters
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_right = Gtk.Label(label="<b>📊 Historical Sensor Fault &amp; Trip Frequency Counters</b>")
        lbl_right.set_use_markup(True)
        lbl_right.set_xalign(0.0)
        right_box.pack_start(lbl_right, False, False, 2)

        scrolled_right = Gtk.ScrolledWindow()
        scrolled_right.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Model: CounterName(str), Count(int), Assessment(str)
        self.live_counters_store = Gtk.ListStore(str, int, str)
        self.live_counters_tree = Gtk.TreeView(model=self.live_counters_store)

        col_cname = Gtk.TreeViewColumn("Fault / Event Category", Gtk.CellRendererText(), text=0)
        col_cname.set_min_width(220)
        self.live_counters_tree.append_column(col_cname)

        col_cnt = Gtk.TreeViewColumn("Trip Count", Gtk.CellRendererText(), text=1)
        col_cnt.set_min_width(90)
        self.live_counters_tree.append_column(col_cnt)

        col_cass = Gtk.TreeViewColumn("Evaluation", Gtk.CellRendererText(), text=2)
        col_cass.set_min_width(160)
        self.live_counters_tree.append_column(col_cass)

        scrolled_right.add(self.live_counters_tree)
        right_box.pack_start(scrolled_right, True, True, 0)
        paned.pack2(right_box, True, False)

        main_box.pack_start(paned, True, True, 4)
        return main_box

    def _create_alerts_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # Model: Severity(str), AlertName(str), Bit(int)
        self.alerts_store = Gtk.ListStore(str, str, int)
        self.alerts_tree = Gtk.TreeView(model=self.alerts_store)

        col_sev = Gtk.TreeViewColumn("Status / Severity", Gtk.CellRendererText(), text=0)
        col_sev.set_min_width(180)
        self.alerts_tree.append_column(col_sev)

        col_name = Gtk.TreeViewColumn("System Notification / Alert Message", Gtk.CellRendererText(), text=1)
        col_name.set_min_width(380)
        self.alerts_tree.append_column(col_name)

        col_bit = Gtk.TreeViewColumn("Bit Index", Gtk.CellRendererText(), text=2)
        self.alerts_tree.append_column(col_bit)

        scrolled.add(self.alerts_tree)
        return scrolled

    def _create_info_tab(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.info_store = Gtk.ListStore(str, str)
        self.info_tree = Gtk.TreeView(model=self.info_store)

        col_prop = Gtk.TreeViewColumn("Property", Gtk.CellRendererText(), text=0)
        col_prop.set_min_width(240)
        self.info_tree.append_column(col_prop)

        col_val = Gtk.TreeViewColumn("Value / Diagnostic Telemetry", Gtk.CellRendererText(), text=1)
        col_val.set_min_width(450)
        self.info_tree.append_column(col_val)

        scrolled.add(self.info_tree)
        return scrolled

    def _create_log_tab(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_buffer = self.log_view.get_buffer()

        scrolled.add(self.log_view)
        box.pack_start(scrolled, True, True, 0)

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
        active_mfr = self.mfr_combo.get_active_id() or "auto"
        if not active_port:
            self.progress_bar.set_text("No port selected!")
            return

        self.is_reading = True
        self.btn_read.set_sensitive(False)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text(f"Connecting to {active_port} ({active_mfr.upper()})...")

        # Run reading session in background thread
        thread = threading.Thread(target=self._run_session_worker, args=(active_port, active_mfr), daemon=True)
        thread.start()

    def _run_session_worker(self, port: str, mfr: str):
        with self.serial_lock:
            session = WRATSession(port, manufacturer=mfr)

            def update_prog(pct, status):
                GLib.idle_add(self.progress_bar.set_fraction, pct)
                GLib.idle_add(self.progress_bar.set_text, f"[{int(pct*100)}%] {status}")
                GLib.idle_add(self._append_log, f"[*] [{int(pct*100)}%] {status}")

            try:
                success = session.run_interrogation(progress_cb=update_prog)
            except Exception as e:
                GLib.idle_add(self._append_log, f"[-] Error: {e}")
                success = False

        GLib.idle_add(self._on_session_finished, session, success)

    def _on_session_finished(self, session: WRATSession, success: bool):
        self.is_reading = False
        self.btn_read.set_sensitive(True)
        self.wrat_session = session

        if not success:
            self.progress_bar.set_fraction(1.0)
            self.progress_bar.set_text("Interrogation failed! Check port connection / permissions.")
            return

        summary = session.get_structured_summary()
        vendor = summary.get("vendor", "Appliance")
        model = summary.get("machine_model", "Machine")

        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_text(f"Successfully read statistics from [{vendor}] {model}!")

        # Update KPI Cards
        self.lbl_kpi_model.set_text(f"{model}")
        self.lbl_kpi_total.set_text(f"{summary.get('total_cups', 0):,}")

        clean_cnt = 0
        decalc_cnt = 0
        for m in summary.get("maintenance", []):
            m_name = m.get("name", "").lower()
            if "clean" in m_name:
                clean_cnt += m.get("count", 0)
            elif "decalc" in m_name or "descal" in m_name:
                decalc_cnt += m.get("count", 0)

        self.lbl_kpi_clean.set_text(f"{clean_cnt:,}")
        self.lbl_kpi_decalc.set_text(f"{decalc_cnt:,}")

        # Populate Beverages Tab
        self.bev_store.clear()
        tot = summary.get("total_cups", 0) or 1
        for b in sorted(summary.get("beverages", []), key=lambda x: x.get("count", 0), reverse=True):
            cnt = b.get("count", 0)
            share = f"{(cnt / tot) * 100:.1f}%" if cnt > 0 else "0.0%"
            cat = "Double Serving (2x)" if b.get("is_double") else b.get("category", "Beverage")
            self.bev_store.append([b.get("code", 0), b.get("name", "Product"), cnt, share, cat])

        # Populate Maintenance Tab
        self.maint_store.clear()
        for m in summary.get("maintenance", []):
            pct_val = m.get("percent") if m.get("percent") is not None else 0
            pct_str = f"{pct_val}%" if m.get("percent") is not None else "N/A"
            self.maint_store.append([m.get("name", "Maintenance"), m.get("count", 0), pct_str, pct_val])

        # Populate Alerts Tab
        self.alerts_store.clear()
        if not summary.get("alerts"):
            self.alerts_store.append(["NORMAL / READY", "System OK - Ready to Brew", 0])
        else:
            for a in summary.get("alerts", []):
                sev = a.get("level", "WARNING")
                msg = a.get("description") or a.get("message") or a.get("title", "Alert")
                self.alerts_store.append([sev, msg, 0])

        # Populate Info Tab
        self.info_store.clear()
        self.info_store.append(["Appliance Vendor", vendor])
        self.info_store.append(["Machine Model", model])
        self.info_store.append(["Serial Number", str(summary.get("serial_number", "N/A"))])
        self.info_store.append(["Firmware String", str(summary.get("firmware_string", "N/A"))])
        self.info_store.append(["Protocol Driver", str(summary.get("protocol_mode", "N/A"))])
        self.info_store.append(["Total Dispensed", f"{summary.get('total_cups', 0):,} cups"])
        self.info_store.append(["Total Brew Cycles", f"{summary.get('total_preparations', 0):,}"])
        self.info_store.append(["Diagnostics Timestamp", summary.get("timestamp", "")])

        if summary.get("telemetry"):
            for k, v in summary["telemetry"].items():
                if not isinstance(v, (dict, list)):
                    self.info_store.append([k.replace("_", " ").title(), str(v)])

        # Populate Live Sensors Tab if available from session
        if summary.get("live_sensors"):
            self._on_live_sensors_updated(summary["live_sensors"])

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
        conn: Optional[Any] = None
        current_port = None
        current_mfr = None
        session: Optional[WRATSession] = None
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

                # Maintain persistent connection across fast polls
                with self.serial_lock:
                    if (conn is None or current_port != active_port or 
                        current_mfr != active_mfr or not getattr(conn, "is_open", True)):
                        if conn:
                            try:
                                conn.close()
                            except Exception:
                                pass
                        try:
                            if active_port.lower().startswith("mock"):
                                conn = serial_io.MockJuraMachine()
                            else:
                                conn = serial_io.DirectSerialConnection(active_port, baudrate=9600)
                            current_port = active_port
                            current_mfr = active_mfr
                            session = WRATSession(active_port, manufacturer=active_mfr, conn=conn)
                        except Exception as e:
                            GLib.idle_add(self.lbl_sensors_status.set_text, f"Connection error: {e}")
                            time.sleep(2.0)
                            continue

                    try:
                        if session is None:
                            session = WRATSession(active_port, manufacturer=active_mfr, conn=conn)
                        res = session.query_live_sensors(fast_poll=True)
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
                    session = WRATSession(active_port, manufacturer=active_mfr)
                    result = session.query_live_sensors(fast_poll=False)
                    session.close()
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

        # Machine State
        rdness = result.get("readiness")
        if "machine_ready" in switches:
            sw = switches["machine_ready"]
            st = sw.get("status", "")
            if sw["ok"]:
                self.lbl_live_state.set_markup("<span color='#a6e3a1'>READY TO BREW</span>")
                self.lbl_sub_state.set_text("Appliance Ready")
            else:
                if "Press Maintenance" in st or "Maintenance" in st:
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
                elif "Heating" in st:
                    self.lbl_live_state.set_markup("<span color='#f9e2af'>HEATING UP</span>")
                    self.lbl_sub_state.set_text("Heating Thermoblock")
                elif "Busy" in st:
                    self.lbl_live_state.set_markup("<span color='#89dceb'>BUSY</span>")
                    self.lbl_sub_state.set_text("Operation in Progress")
                elif "Hardware Fault" in st or "FAULT" in st:
                    self.lbl_live_state.set_markup("<span color='#f38ba8'>HARDWARE FAULT</span>")
                    self.lbl_sub_state.set_text(st.replace("Hardware Fault (", "").replace(")", ""))
                else:
                    self.lbl_live_state.set_markup("<span color='#f38ba8'>NOT READY</span>")
                    self.lbl_sub_state.set_text(sw.get("badge", "Check Appliance"))
        elif rdness:
            if rdness.lower() == "ready":
                self.lbl_live_state.set_markup("<span color='#a6e3a1'>READY</span>")
                self.lbl_sub_state.set_text("Appliance Ready")
            elif "press maintenance" in rdness.lower():
                self.lbl_live_state.set_markup("<span color='#fab387'>PRESS MAINTENANCE</span>")
                self.lbl_sub_state.set_text("Fill System Required")
            elif "fault" in rdness.lower() or "error" in rdness.lower():
                self.lbl_live_state.set_markup("<span color='#f38ba8'>FAULT</span>")
                self.lbl_sub_state.set_text(rdness)
            else:
                self.lbl_live_state.set_markup("<span color='#fab387'>STATUS</span>")
                self.lbl_sub_state.set_text(rdness)
        else:
            self.lbl_live_state.set_markup("<span color='#a6e3a1'>READY</span>")
            self.lbl_sub_state.set_text("Nominal")

        # Thermoblock Heaters & Thermal Sensors
        telem = result.get("telemetry", {})
        sensor_dict = {s.get("id"): s for s in result.get("sensors", [])}

        if "heater_coffee_str" in telem:
            self.lbl_live_coffee_tb.set_text(telem["heater_coffee_str"])
            self.lbl_sub_coffee_tb.set_text(telem.get("heater_coffee_status", "Ready to Brew"))
        elif "heater_coffee" in sensor_dict:
            s = sensor_dict["heater_coffee"]
            self.lbl_live_coffee_tb.set_text(s.get("badge", s.get("status", "OK")))
            self.lbl_sub_coffee_tb.set_text("Coffee Thermoblock")
        elif "boiler_coffee" in sensor_dict:
            s = sensor_dict["boiler_coffee"]
            self.lbl_live_coffee_tb.set_text(s.get("badge", s.get("status", "OK")))
            self.lbl_sub_coffee_tb.set_text("Coffee Boiler")
        elif "boiler_espresso" in sensor_dict:
            s = sensor_dict["boiler_espresso"]
            self.lbl_live_coffee_tb.set_text(s.get("badge", s.get("status", "OK")))
            self.lbl_sub_coffee_tb.set_text("Espresso Boiler")
        elif "heater_ntc_raw" in telem:
            self.lbl_live_coffee_tb.set_text(f"ADC {telem['heater_ntc_raw']}")
            self.lbl_sub_coffee_tb.set_text("Nominal")
        else:
            self.lbl_live_coffee_tb.set_text("NOMINAL")
            self.lbl_sub_coffee_tb.set_text("Standby")

        is_dual = telem.get("is_dual_heater", False)
        if "heater_steam" in sensor_dict:
            s = sensor_dict["heater_steam"]
            self.lbl_live_steam_tb.set_text(s.get("badge", s.get("status", "OK")))
            self.lbl_sub_steam_tb.set_text("Steam Heater")
        elif "boiler_steam" in sensor_dict:
            s = sensor_dict["boiler_steam"]
            self.lbl_live_steam_tb.set_text(s.get("badge", s.get("status", "OK")))
            self.lbl_sub_steam_tb.set_text("Steam Generator")
        elif "boiler_instant" in sensor_dict:
            s = sensor_dict["boiler_instant"]
            self.lbl_live_steam_tb.set_text(s.get("badge", s.get("status", "OK")))
            self.lbl_sub_steam_tb.set_text("Instant Boiler")
        elif is_dual:
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

        # Water Flow Rate (ml/s) & Flowmeter Pulse Tracking
        flow_rate = telem.get("flow_rate_ml_s", 0.0)
        flow_pulses = telem.get("flow_pulses", 0)
        flow_vol = telem.get("flow_volume_ml", 0.0)
        if "water_flow" in sensor_dict:
            s_f = sensor_dict["water_flow"]
            if "value" in s_f and s_f["value"] is not None:
                flow_rate = s_f["value"]

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
        active_sess = self.wrat_session or self.session
        if not active_sess:
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
            title="Save W.R.A.T. Diagnostic Report",
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

        summary = active_sess.get_structured_summary()
        m_name = summary.get("machine_model", "appliance").replace(" ", "_").replace("/", "_")
        default_name = f"wrat_diag_{m_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        dialog.set_current_name(default_name)

        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            import json
            if filename.endswith(".json"):
                data = json.dumps(summary, indent=2, ensure_ascii=False)
            elif filename.endswith(".csv"):
                lines = ["Category,Metric,Value"]
                lines.append(f"Identity,Vendor,{summary.get('vendor')}")
                lines.append(f"Identity,Model,{summary.get('machine_model')}")
                lines.append(f"Identity,Serial,{summary.get('serial_number')}")
                lines.append(f"Summary,Total Cups,{summary.get('total_cups')}")
                for b in summary.get("beverages", []):
                    lines.append(f"Beverage,{b.get('name')},{b.get('count')}")
                for m in summary.get("maintenance", []):
                    lines.append(f"Maintenance,{m.get('name')},{m.get('count')}")
                data = "\n".join(lines)
            else:
                data = json.dumps(summary, indent=2, ensure_ascii=False)

            with open(filename, "w", encoding="utf-8") as f:
                f.write(data)
            self.progress_bar.set_text(f"Report saved to {filename}")

        dialog.destroy()


def main():
    app = JuraDiagApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
