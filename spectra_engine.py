#!/usr/bin/env python3
"""
SPECTRA — Universal Hardware Telemetry & Logic Board Diagnostics
Universal Multi-Manufacturer Appliance Engine
Coordinates device probing, live sensor polling, and telemetry extraction.
"""

from typing import Dict, List, Any, Optional, Callable, Tuple
import time
import csv
import io

from drivers import (
    BaseApplianceDriver,
    ApplianceIdentification,
    ApplianceTelemetry,
    get_driver,
    detect_driver,
    DRIVER_REGISTRY,
    DRIVER_DISPLAY_NAMES,
    list_drivers
)
import serial_io


class SpectraSession:
    """
    Unified telemetry interrogation and diagnostic session for SPECTRA.
    Supports auto-detection across Jura, Nivona, Lamanti-KL, and Lamanti-JN.
    """

    def __init__(
        self,
        port_name: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        manufacturer: str = "auto",
        conn: Optional[Any] = None
    ):
        self.port_name = port_name
        self.baudrate = baudrate
        self.manufacturer = manufacturer.lower().strip()
        self.conn = conn
        self.driver: Optional[BaseApplianceDriver] = None
        self.identification: Optional[ApplianceIdentification] = None
        self.telemetry: Optional[ApplianceTelemetry] = None
        self._owns_conn = False

    def ensure_connection(self):
        """Open physical or mock connection if not already provided."""
        if self.conn is None:
            self.conn = serial_io.DirectSerialConnection(
                port_name=self.port_name,
                baudrate=self.baudrate
            )
            self._owns_conn = True

    def close(self):
        """Close connection if owned by this session."""
        if self._owns_conn and self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def initialize_driver(self) -> BaseApplianceDriver:
        """Resolve driver based on user choice or automatic probing."""
        self.ensure_connection()

        if self.manufacturer == "auto":
            driver, ident = detect_driver(self.conn)
            self.driver = driver
            self.identification = ident
        else:
            self.driver = get_driver(self.manufacturer)
            try:
                self.identification = self.driver.probe(self.conn)
            except Exception:
                self.identification = None

        return self.driver

    def query_live_sensors(self, fast_poll: bool = False) -> Dict[str, Any]:
        """Poll real-time hardware status and microswitches from active driver."""
        if self.driver is None:
            self.initialize_driver()
        return self.driver.read_live_sensors(self.conn, fast_poll=fast_poll)

    def run_interrogation(
        self,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """Run complete interrogation process across all machine registers."""
        try:
            if self.driver is None:
                self.initialize_driver()

            if progress_cb:
                vendor_title = DRIVER_DISPLAY_NAMES.get(self.driver.vendor.lower(), self.driver.vendor)
                progress_cb(0.05, f"Connected to {vendor_title} on {self.port_name}")

            self.telemetry = self.driver.read_telemetry(self.conn, progress_cb=progress_cb)
            return True
        except Exception as e:
            if progress_cb:
                progress_cb(1.0, f"Error: {e}")
            raise

    def get_structured_summary(self) -> Dict[str, Any]:
        """Generate structured summary dictionary compatible with export & GUI."""
        if self.telemetry is None:
            return {}

        t = self.telemetry
        ident = t.identification or ApplianceIdentification(
            vendor=t.vendor,
            model=t.model
        )

        beverages_list = [
            {
                "code": b.code,
                "name": b.name,
                "count": b.count,
                "is_double": b.is_double,
                "category": b.category
            }
            for b in t.beverages
        ]

        maintenance_list = [
            {
                "name": m.name,
                "label": m.name,
                "count": m.count,
                "percent": m.percent,
                "percentage": m.percent,
                "warning": m.warning
            }
            for m in t.maintenance
        ]

        return {
            "machine_model": t.model,
            "vendor": t.vendor,
            "serial_number": ident.serial_number,
            "firmware_string": ident.firmware_version,
            "protocol_mode": ident.protocol_name,
            "total_cups": t.total_cups,
            "total_preparations": t.total_preparations,
            "beverages": beverages_list,
            "maintenance": maintenance_list,
            "live_sensors": {
                "switches": t.switches,
                "sensors": t.sensors,
                "error_counters": t.error_counters
            },
            "alerts": t.active_alerts,
            "telemetry": t.operational_metrics,
            "timestamp": t.timestamp,
            "power_spec": ident.voltage_spec
        }

    def get_formatted_report(self) -> str:
        """Generate human-readable text diagnostic report."""
        return format_text_summary(self.get_structured_summary())


def format_text_summary(summary: Dict[str, Any]) -> str:
    """Generate a clean, human-readable terminal/text diagnostic report."""
    if not summary:
        return "No diagnostic data available.\n"

    lines = []
    lines.append("=" * 78)
    vendor = summary.get("vendor", "Appliance")
    model = summary.get("machine_model", "Unknown")
    lines.append(f"SPECTRA DIAGNOSTIC REPORT: {vendor} — {model}")
    serial = summary.get("serial_number", "N/A")
    proto = summary.get("protocol_mode", "N/A")
    lines.append(f"Serial Number: {serial} | Protocol: {proto}")
    cups = summary.get("total_cups", 0)
    preps = summary.get("total_preparations", 0)
    lines.append(f"Total Dispensed: {cups:,} cups ({preps:,} total preparations)")
    lines.append("=" * 78)

    lines.append("\n[BEVERAGE DISPENSING COUNTERS]")
    for b in summary.get("beverages", []):
        d_str = " (Double)" if b.get("is_double") else ""
        name = b.get("name", "Beverage") + d_str
        count = b.get("count", 0)
        lines.append(f"  * {name:<36}: {count:>8,}")

    lines.append("\n[MAINTENANCE & HYGIENE]")
    for m in summary.get("maintenance", []):
        pct = m.get("percent")
        pct_str = f" ({pct}%)" if pct is not None else ""
        name = m.get("name", "Maintenance Task")
        count = m.get("count", 0)
        lines.append(f"  * {name:<36}: {count:>8,}{pct_str}")

    telem = summary.get("telemetry")
    if telem:
        lines.append("\n[OPERATIONAL METRICS & HARDWARE SPECS]")
        for k, v in telem.items():
            if not isinstance(v, (dict, list)):
                key_fmt = k.replace("_", " ").title()
                lines.append(f"  * {key_fmt:<36}: {v}")

    lines.append("=" * 78)
    return "\n".join(lines) + "\n"


def format_csv_summary(summary: Dict[str, Any]) -> str:
    """Generate RFC 4180 compliant CSV string using standard csv.writer."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Category", "Metric", "Value"])
    writer.writerow(["Identity", "Vendor", summary.get("vendor", "Unknown")])
    writer.writerow(["Identity", "Model", summary.get("machine_model", "Unknown")])
    writer.writerow(["Identity", "Serial", summary.get("serial_number", "N/A")])
    writer.writerow(["Summary", "Total Cups", summary.get("total_cups", 0)])
    writer.writerow(["Summary", "Total Preparations", summary.get("total_preparations", 0)])
    for b in summary.get("beverages", []):
        writer.writerow(["Beverage", b.get("name", "Product"), b.get("count", 0)])
    for m in summary.get("maintenance", []):
        writer.writerow(["Maintenance", m.get("name") or m.get("label", "Maintenance"), m.get("count", 0)])
    return output.getvalue()


# Universal Alias
WRATSession = SpectraSession
