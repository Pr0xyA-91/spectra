#!/usr/bin/env python3
"""
W.R.A.T. - Jura Appliance Driver
Implements native Plain-ASCII Optical Transceiver Protocol & Smart Connect @-Protocol.
Supports 170+ Jura models across all generations.
"""

from typing import Dict, List, Any, Optional, Callable, Tuple

from drivers.base import (
    BaseApplianceDriver,
    ApplianceCapabilities,
    ApplianceIdentification,
    ApplianceTelemetry,
    BeverageCounter,
    MaintenanceMetric
)

import profiles_db
import stats_collector as sc


class JuraDriver(BaseApplianceDriver):
    """Native Jura appliance driver for W.R.A.T."""

    vendor: str = "Jura"
    name: str = "Jura Diagnostics Module"
    supported_baudrates: List[int] = [9600]
    capabilities: ApplianceCapabilities = ApplianceCapabilities(
        has_live_sensors=True,
        has_thermal_sensors=True,
        has_dual_heaters=True,
        has_flowmeter=True,
        has_beverage_counters=True,
        has_maintenance_counters=True,
        has_lifetime_metrics=True,
        has_active_alerts=True,
        has_actuator_tests=True
    )

    def probe(self, conn: Any) -> Optional[ApplianceIdentification]:
        """Probe for Jura cleartext (TY:) or Smart Connect (@T0) presence."""
        try:
            # 1. Plain ASCII optical probe
            ty_resp = conn.query_ascii("TY:", timeout=1.0)
            if ty_resp and ty_resp.startswith("ty:"):
                raw_ident = ty_resp[3:].strip()
                profile = profiles_db.find_profile(raw_ident)
                model_name = profile.get("model_family", f"Jura ({raw_ident})")
                return ApplianceIdentification(
                    vendor="Jura",
                    model=model_name,
                    firmware_version=raw_ident,
                    protocol_name="ASCII Optical (Jura USB Scanner / Direct Serial)",
                    raw_ident=raw_ident
                )

            # 2. Smart Connect @-protocol probe
            import jura_protocol as jp
            t0_raw = jp.encode_wire(jp.build_encrypted_frame("@T0\r\n", 0x20))
            conn.write(t0_raw)
            rx = conn.read(256, timeout_sec=0.8)
            if rx and len(rx) >= 4:
                decoded, _ = jp.decode_wire(rx)
                if b"\r\n" in decoded or decoded.startswith(b"&"):
                    return ApplianceIdentification(
                        vendor="Jura",
                        model="Jura Smart Connect Appliance",
                        protocol_name="Encrypted Smart Connect (@-Protocol)",
                        raw_ident="Smart Connect Detected"
                    )
        except Exception:
            pass

        return None

    def read_live_sensors(self, conn: Any, fast_poll: bool = False) -> Dict[str, Any]:
        """Query live hardware sensors using the verified Jura engine."""
        res = sc.query_live_sensors(
            port_name=conn.port_name if hasattr(conn, "port_name") else "unknown",
            conn=conn,
            fast_poll=fast_poll
        )
        ready_sw = next((s for s in res.get("switches", []) if s.get("id") == "machine_ready"), None)
        if ready_sw:
            res["readiness"] = ready_sw.get("status", "Nominal")
        return res

    def read_telemetry(
        self,
        conn: Any,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> ApplianceTelemetry:
        """Perform full machine statistics extraction via JuraStatsSession."""
        session = sc.JuraStatsSession(
            port_name=conn.port_name if hasattr(conn, "port_name") else "/dev/ttyUSB0",
            baudrate=conn.baudrate if hasattr(conn, "baudrate") else 9600
        )
        # Reuse existing connection
        session.conn = conn

        success = session.run_interrogation(progress_cb=progress_cb)
        if not success:
            raise IOError("Jura interrogation failed to complete or machine refused read.")

        summary = session.get_structured_summary()
        ident = ApplianceIdentification(
            vendor="Jura",
            model=summary.get("machine_model", "Jura Appliance"),
            serial_number=str(summary.get("serial_number", "N/A")),
            article_number=str(summary.get("telemetry", {}).get("article_number", "N/A")),
            firmware_version=str(summary.get("firmware_string", "N/A")),
            display_version=str(summary.get("telemetry", {}).get("software_version_display", "N/A")),
            production_date=str(summary.get("production_date", "N/A")),
            voltage_spec=str(summary.get("power_spec", "N/A")),
            protocol_name=str(summary.get("protocol_mode", "N/A")),
            raw_ident=str(summary.get("ef_code", ""))
        )

        beverages = [
            BeverageCounter(
                code=b.get("code"),
                name=b.get("name", "Product"),
                count=b.get("count", 0),
                is_double=b.get("is_double", False)
            )
            for b in summary.get("beverages", [])
        ]

        maintenance = [
            MaintenanceMetric(
                name=m.get("name", "Maintenance"),
                count=m.get("count", 0),
                percent=m.get("percent")
            )
            for m in summary.get("maintenance", [])
        ]

        ls = summary.get("live_sensors", {})
        return ApplianceTelemetry(
            vendor="Jura",
            model=summary.get("machine_model", "Jura Appliance"),
            identification=ident,
            total_cups=summary.get("total_cups", 0),
            total_preparations=summary.get("total_preparations", 0),
            beverages=beverages,
            maintenance=maintenance,
            switches=ls.get("switches", []),
            sensors=ls.get("sensors", []),
            error_counters=ls.get("error_counters", {}),
            operational_metrics=summary.get("telemetry", {}),
            active_alerts=summary.get("alerts", []),
            raw_telemetry=summary
        )

    def test_actuator(self, conn: Any, actuator_id: str, param: Any = None) -> bool:
        """Send technician test mode actuator commands (AN:20, etc.)."""
        try:
            if actuator_id == "enter_test_mode":
                resp = conn.query_ascii("AN:20", timeout=1.0)
                return bool(resp and "ok" in resp.lower())
            elif actuator_id == "exit_test_mode":
                resp = conn.query_ascii("AN:21", timeout=1.0)
                return bool(resp and "ok" in resp.lower())
            elif actuator_id == "pulse_pump":
                resp = conn.query_ascii("FA:08", timeout=1.0)
                return bool(resp and "ok" in resp.lower())
        except Exception:
            pass
        return False

    def list_supported_models(self) -> List[Tuple[str, str]]:
        return profiles_db.list_supported_models()
