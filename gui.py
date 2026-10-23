#!/usr/bin/env python3
"""
Jura Modern Diagnostics - Desktop GUI
A modern GTK3 application for reading statistics, beverage counters,
maintenance history, and active alerts from modern Jura coffee machines.
"""

import sys
import os
import threading
from datetime import datetime

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

import serial_io
import profiles_db
import stats_collector as sc

__version__ = "0.1-alpha"


class JuraDiagApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Jura Modern Diagnostics Suite (v0.1-alpha)")
        self.set_default_size(980, 680)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Apply dark modern CSS styling
        self._apply_styling()

        self.session: Optional[sc.JuraStatsSession] = None
        self.is_reading = False

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

        # Tab 3: Alerts & Status
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
            padding: 12px 16px;
            margin: 4px;
        }
        .card-value {
            font-size: 24px;
            font-weight: bold;
            color: #89b4fa;
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
        app_title.set_markup("<b><span size='large' color='#89b4fa'>Jura Modern Diagnostics</span> <span size='small' color='#f9e2af'>v0.1-alpha</span></b>")
        app_title.set_alignment(0, 0.5)
        sub_title = Gtk.Label(label="Universal Optical & Smart Connect Protocol Reader")
        sub_title.get_style_context().add_class("card-label")
        sub_title.set_alignment(0, 0.5)
        title_box.pack_start(app_title, False, False, 0)
        title_box.pack_start(sub_title, False, False, 0)
        header_box.pack_start(title_box, False, False, 10)

        # Port Selector Label
        lbl_port = Gtk.Label(label="Serial Port:")
        header_box.pack_start(lbl_port, False, False, 0)

        # Port ComboBox
        self.port_combo = Gtk.ComboBoxText()
        self.port_combo.set_size_request(260, -1)
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

        clean_cnt = session.maint_counts[0] if session.maint_counts else 0
        decalc_cnt = session.maint_counts[1] if len(session.maint_counts) > 1 else 0
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
        self.info_store.append(["Machine Family", summary["machine_model"]])
        if summary.get("telemetry"):
            tel = summary["telemetry"]
            if "serial_number" in tel and tel["serial_number"] != "N/A":
                self.info_store.append(["Serial Number (Barcode)", str(tel["serial_number"])])
            if "production_date" in tel and tel["production_date"] != "N/A":
                self.info_store.append(["Date of Production", str(tel["production_date"])])
            if "machine_number" in tel and tel["machine_number"]:
                self.info_store.append(["Machine Sequence No", str(tel["machine_number"])])
            if "country_code" in tel and tel["country_code"] != "N/A":
                self.info_store.append(["Destination Market", str(tel["country_code"])])
        self.info_store.append(["Firmware Identifier", summary["firmware_string"]])
        self.info_store.append(["Profile EF Code", summary["ef_code"]])
        if summary.get("telemetry"):
            tel = summary["telemetry"]
            if "appliance_number" in tel:
                self.info_store.append(["Appliance Number", str(tel["appliance_number"])])
            if "appliance_code" in tel and tel["appliance_code"] != "N/A":
                self.info_store.append(["Appliance Code", str(tel["appliance_code"])])
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
            title="Save Jura Diagnostic Report",
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

        default_name = f"jura_diag_{self.session.model_family}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
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
