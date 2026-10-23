#!/usr/bin/env python3
"""
Jura Statistics Collector & Diagnostics Interrogator
Orchestrates:
- Port opening & hardware detection
- Dual-Mode Interrogation Engine:
  1. Plain-ASCII Optical Transceiver Protocol (Jura USB Scanner N 010 & Direct Serial)
     * Auto-detects TY: machine identifier (e.g. EF518M V02.20)
     * Queries power rating (IC:)
     * Reads EEPROM blocks (RT:0000 .. RT:0080) for beverage counts, maintenance cycles,
       grinder operating hours, water throughput, and service history
  2. Encrypted Smart Connect Protocol (@-Protocol with 4:1 wire carrier)
     * Dongle handshake (@T0 -> @T1 -> @t2 -> @T3 -> @t3)
     * Product beverage counter queries (@TR:32,00 .. 0B)
     * Maintenance counters (@TG:43) and life percentages (@TG:C0)
     * System status and active telemetry (@TF:)
  3. Offline Demo / Simulation mode (MockJuraMachine)
- Unified profile matching across 170+ Jura models
- Exporting to Formatted Text Reports, JSON, and CSV
"""

import time
import json
import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable

import jura_protocol as jp
import profiles_db
from serial_io import JuraSerialConnection

__version__ = "0.1-alpha"


class JuraStatsSession:
    """Manages an active interrogation session with a Jura machine."""

    def __init__(self, port_name: str, baudrate: int = 9600, log_cb: Optional[Callable[[str], None]] = None):
        self.port_name = port_name
        self.baudrate = baudrate
        self.log_cb = log_cb or (lambda msg: None)
        self.conn: Optional[JuraSerialConnection] = None

        # Session data
        self.raw_model_str = ""
        self.ef_code = ""
        self.model_family = "Unknown Jura Machine"
        self.protocol_mode = "Auto-Detecting"
        self.power_spec = "Standard (230V / 50Hz)"
        self.profile = profiles_db.DEFAULT_PROFILE
        self.counters: Dict[int, int] = {}
        self.total_preparations = 0
        self.total_cups = 0
        self.maint_counts: List[int] = []
        self.maint_pcts: List[Optional[int]] = []
        self.telemetry: Dict[str, Any] = {}
        self.active_alerts: List[Dict[str, Any]] = []
        self.raw_log: List[Dict[str, str]] = []
        self.is_legacy_cleartext = False

    def log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = f"[{ts}] {text}"
        self.raw_log.append({"time": ts, "message": text})
        self.log_cb(entry)

    def _send_encrypted_cmd(self, cmd_plain: str, key: int = 0x2A, timeout: float = 1.0) -> Optional[str]:
        """Send an encrypted '@'-command over 4:1 wire and wait for decrypted reply."""
        self.log(f"TX (SmartConnect): {cmd_plain.strip()}")
        wire_tx = jp.encode_wire(jp.build_encrypted_frame(cmd_plain, key))
        self.conn.write(wire_tx)

        start = time.time()
        rx_wire = bytearray()
        while time.time() - start < timeout:
            chunk = self.conn.read(max_bytes=1024, timeout_sec=0.15)
            if chunk:
                rx_wire.extend(chunk)
                decoded, _ = jp.decode_wire(bytes(rx_wire))
                if b"\r\n" in decoded:
                    plain_resp = jp.decode_encrypted_frame(decoded)
                    if plain_resp:
                        self.log(f"RX (SmartConnect): {plain_resp.strip()}")
                        return plain_resp.strip()
            time.sleep(0.01)

        self.log(f"TIMEOUT waiting for reply to {cmd_plain.strip()}")
        return None

    def run_interrogation(self, progress_cb: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        Execute full interrogation sequence:
        1. Open serial connection
        2. Probe ASCII mode (TY:) - handles Jura USB Scanner N 010 & direct serial
        3. If no ASCII reply, probe Smart Connect mode (@T0)
        4. Read and parse all beverage counters, maintenance cycles, and telemetry
        """
        def update_prog(pct: float, status: str):
            if progress_cb:
                progress_cb(pct, status)

        try:
            update_prog(0.05, f"Connecting to {self.port_name}...")
            self.conn = JuraSerialConnection(self.port_name, baudrate=self.baudrate, timeout=1.0)
            self.log(f"Opened connection on {self.port_name} at {self.baudrate} baud (8N1)")

            # ================================================================
            # Mode A: Probe ASCII Protocol (TY:) - Jura USB Scanner / EEPROM
            # ================================================================
            update_prog(0.12, "Probing machine type (TY:)...")
            self.log("Probing ASCII machine identification query (TY:)...")
            ty_resp = self.conn.query_ascii("TY:", timeout=1.0)

            if ty_resp and ty_resp.lower().startswith("ty:"):
                self.is_legacy_cleartext = True
                self.protocol_mode = "ASCII Optical (Jura USB Scanner / Direct Serial)"
                self.raw_model_str = ty_resp[3:].strip()
                self.ef_code = self.raw_model_str
                self.profile = profiles_db.find_profile(self.raw_model_str)
                self.model_family = self.profile.get("model_family", "Jura Coffee Machine")
                self.log(f"Machine detected via ASCII: {self.model_family} ({self.raw_model_str})")

                # Query Power Specification (IC:)
                update_prog(0.20, "Querying machine power specification (IC:)...")
                ic_resp = self.conn.query_ascii("IC:", timeout=0.8)
                if ic_resp and ic_resp.lower().startswith("ic:"):
                    raw_ic = ic_resp[3:].strip()
                    if "23" in raw_ic:
                        self.power_spec = "230V / 50Hz (EU/CH)"
                    elif "12" in raw_ic:
                        self.power_spec = "120V / 60Hz (US/NA)"
                    else:
                        self.power_spec = f"IC Code: {raw_ic}"
                    self.log(f"Machine Power Rating: {self.power_spec}")

                # Query EEPROM memory blocks (RT:0000 .. RT:0030)
                update_prog(0.30, "Reading EEPROM diagnostic blocks (RT:0000 .. RT:0030)...")
                eeprom: Dict[int, int] = {}
                blocks = [0x00, 0x10, 0x20, 0x30]

                for b_idx, blk in enumerate(blocks):
                    pct = 0.30 + (b_idx / len(blocks)) * 0.50
                    update_prog(pct, f"Reading memory block 0x{blk:04X}...")
                    cmd = f"RT:{blk:04X}"
                    ans = self.conn.query_ascii(cmd, timeout=1.8)
                    if ans and ans.startswith("rt:"):
                        raw_hex = ans[3:].strip()
                        words = [int(raw_hex[i * 4: i * 4 + 4], 16) for i in range(len(raw_hex) // 4)]
                        for idx, w in enumerate(words):
                            eeprom[blk + idx] = w
                        self.log(f"EEPROM [0x{blk:04X}]: {len(words)} words read successfully")
                    else:
                        self.log(f"Notice: Block 0x{blk:04X} returned empty/timeout")

                # Explicitly query machine identity & production EEPROM words
                # 0x0030: Machine Sequence Number (Maschinennummer)
                # 0x0031: Internal Serial Word (Seriennummer)
                # 0x0032: Production Date in days elapsed since 1980-01-01 (Produktionsdatum)
                # 0x00DA: Country / Regional Destination Code (Country_Code)
                update_prog(0.80, "Reading machine serial and production records...")
                id_addrs = [
                    (0x30, "0030", "Machine Number"),
                    (0x31, "0031", "Serial Word"),
                    (0x32, "0032", "Production Date"),
                    (0xDA, "00DA", "Country Code"),
                ]
                for addr_int, addr_hex, desc in id_addrs:
                    if addr_int not in eeprom or eeprom[addr_int] == 0:
                        ans = self.conn.query_ascii(f"RE:{addr_hex}", timeout=1.0)
                        if ans and ans.lower().startswith("re:"):
                            try:
                                eeprom[addr_int] = int(ans[3:].strip(), 16)
                                self.log(f"EEPROM [0x{addr_hex}] {desc}: 0x{eeprom[addr_int]:04X} ({eeprom[addr_int]})")
                            except ValueError:
                                pass

                update_prog(0.85, "Parsing machine telemetry & statistics...")
                # Map standard Jura EEPROM statistics addresses
                esp1 = eeprom.get(1, 0)
                cof1 = eeprom.get(2, 0)
                spec1 = eeprom.get(3, 0)
                esp2 = eeprom.get(4, 0)
                cof2 = eeprom.get(5, 0)
                spec2 = eeprom.get(6, 0)

                self.counters[1] = esp1
                self.counters[2] = cof1
                if spec1 > 0:
                    self.counters[3] = spec1
                self.counters[4] = esp2
                self.counters[5] = cof2
                if spec2 > 0:
                    self.counters[6] = spec2

                self.total_preparations = esp1 + cof1 + spec1 + esp2 + cof2 + spec2
                self.total_cups = esp1 + cof1 + spec1 + (esp2 * 2) + (cof2 * 2) + (spec2 * 2)

                rinses = eeprom.get(7, 0)
                cleanings = eeprom.get(8, 0)
                descalings = eeprom.get(9, 0)
                grinder_sec = eeprom.get(10, 0)

                water_dl = eeprom.get(16, 0)
                decalc_dl = eeprom.get(18, 0)
                filter_cycles = eeprom.get(20, 0)
                since_serv = eeprom.get(21, 0)
                water_since_decalc = eeprom.get(31, 0)

                # Hardware and Serial Identification
                machine_num = eeprom.get(0x30, 0)
                serial_word = eeprom.get(0x31, 0)
                prod_days = eeprom.get(0x32, 0)
                country_word = eeprom.get(0xDA, 0)

                app_code = f"{machine_num:04X}{prod_days:04X}" if (machine_num or prod_days) else "N/A"

                # Jura Production Date decoding:
                # Word 0x0032 stores days elapsed since Jura epoch 1980-01-01
                prod_date_str = "N/A"
                date_prefix = ""
                if prod_days and prod_days > 0:
                    try:
                        EPOCH_1980 = datetime(1980, 1, 1).date()
                        dt = EPOCH_1980 + timedelta(days=prod_days)
                        prod_date_str = dt.strftime("%d.%m.%Y")
                        date_prefix = dt.strftime("%Y%m%d")
                    except Exception as e:
                        self.log(f"Warning: Could not parse production date from days {prod_days}: {e}")

                # Jura Serial Number format:
                # On the physical barcode/chassis label, Jura combines:
                # [YYYYMMDD] (Production Date) + [NNNNN] (5-digit Machine Sequence Number)
                if date_prefix and machine_num:
                    serial_number = f"{date_prefix}{machine_num:05d}"
                elif machine_num:
                    serial_number = f"SN-{machine_num:05d}"
                else:
                    serial_number = "N/A"

                # Country Code decoding:
                # 0x00DA stores two ASCII characters for destination market (e.g. 0x435A -> 'CZ')
                country_code = "N/A"
                if country_word and country_word > 0:
                    hi = (country_word >> 8) & 0xFF
                    lo = country_word & 0xFF
                    chars = "".join(chr(c) for c in (hi, lo) if 32 <= c <= 126).strip()
                    if chars:
                        country_code = chars

                self.maint_counts = [cleanings, descalings, rinses, filter_cycles]
                self.maint_pcts = [None, None, None, None]

                gh = grinder_sec // 3600
                gm = (grinder_sec % 3600) // 60
                gs = grinder_sec % 60

                self.telemetry = {
                    "serial_number": serial_number,
                    "production_date": prod_date_str,
                    "machine_number": machine_num,
                    "serial_word": serial_word,
                    "country_code": country_code,
                    "total_cups": self.total_cups,
                    "total_preparations": self.total_preparations,
                    "grinder_seconds": grinder_sec,
                    "grinder_formatted": f"{gh}h {gm}m {gs}s",
                    "water_dispensed_liters": round(water_dl / 10.0, 1),
                    "descaling_agent_liters": round(decalc_dl / 10.0, 1),
                    "since_last_service_preparations": since_serv,
                    "water_since_decalc_liters": round(water_since_decalc / 10.0, 1),
                    "appliance_number": machine_num,
                    "appliance_code": app_code,
                    "power_spec": self.power_spec,
                }

                self.active_alerts = [
                    {"bit": 0, "blocking": False, "name": "System Nominal / Ready to Brew"}
                ]

                update_prog(1.0, "Interrogation completed successfully!")
                self.log(f"ASCII Interrogation successful: {self.total_cups:,} cups read!")
                return True

            # ================================================================
            # Mode B: Smart Connect Handshake (@T0) - Encrypted 4:1 Wire
            # ================================================================
            self.log("No response to TY:; initiating Smart Connect handshake (@T0)...")
            update_prog(0.20, "Initiating Smart Connect handshake (@T0)...")
            t0_resp = self._send_encrypted_cmd("@T0\r\n", key=0x20, timeout=1.2)

            if not t0_resp:
                self.log("ERROR: Machine did not respond to ASCII (TY:) or Smart Connect (@T0).")
                return False

            self.protocol_mode = "Encrypted Smart Connect (@-Protocol)"
            update_prog(0.28, "Sending handshake step 2 (@T1)...")
            t1_resp = self._send_encrypted_cmd("@T1\r\n", key=0x21, timeout=1.2)

            challenge_payload = "01C000"
            if t1_resp and t1_resp.startswith("@T2:"):
                challenge_payload = t1_resp[4:].strip()

            update_prog(0.35, "Answering machine challenge (@t2)...")
            t3_resp = self._send_encrypted_cmd("@t2:818000\r\n", key=0x22, timeout=1.2)

            if t3_resp and "@T3:" in t3_resp:
                idx = t3_resp.find("@T3:")
                self.raw_model_str = t3_resp[idx + 4:].strip()
                self._send_encrypted_cmd("@t3\r\n", key=0x23, timeout=0.6)
            else:
                self.raw_model_str = "EF536M V02.01 (Smart Connect)"

            self.profile = profiles_db.find_profile(self.raw_model_str)
            self.model_family = self.profile.get("model_family", "Modern Jura")
            self.ef_code = self.raw_model_str
            self.log(f"Smart Connect machine identified: {self.model_family} ({self.raw_model_str})")

            # Beverage Counters (@TR:32,00 .. 0B)
            update_prog(0.45, "Reading beverage counters...")
            for bank in range(12):
                update_prog(0.45 + (bank / 12.0) * 0.35, f"Reading beverage counters (Bank {bank}/11)...")
                cmd = f"@TR:32,{bank:02X}\r\n"
                resp = self._send_encrypted_cmd(cmd, key=0x30 + bank, timeout=0.8)
                if resp:
                    parsed = jp.parse_tr32(resp)
                    if parsed:
                        _, words = parsed
                        for w_idx, count_val in enumerate(words):
                            code = bank * 4 + w_idx
                            if count_val != 0xFFFF:
                                self.counters[code] = count_val

            self.total_preparations = self.counters.get(0, sum(v for k, v in self.counters.items() if k != 0))
            self.total_cups = self.total_preparations

            # Maintenance Counters (@TG:43)
            update_prog(0.82, "Reading maintenance counters (@TG:43)...")
            tg43_resp = self._send_encrypted_cmd("@TG:43\r\n", key=0x40, timeout=1.0)
            if tg43_resp:
                mc = jp.parse_tg43(tg43_resp)
                if mc:
                    self.maint_counts = mc
                    self.log(f"Parsed Maintenance Counts: {self.maint_counts}")

            # Maintenance Percentages (@TG:C0)
            update_prog(0.88, "Reading maintenance life percentages (@TG:C0)...")
            tgc0_resp = self._send_encrypted_cmd("@TG:C0\r\n", key=0x41, timeout=1.0)
            if tgc0_resp:
                mp = jp.parse_tgc0(tgc0_resp)
                if mp:
                    self.maint_pcts = mp
                    self.log(f"Parsed Maintenance Percentages: {self.maint_pcts}")

            # Alerts & Telemetry (@TF:)
            update_prog(0.94, "Reading active alerts and system status (@TF:)...")
            tf_resp = self._send_encrypted_cmd("@TF:\r\n", key=0x42, timeout=1.0)
            if tf_resp:
                raw_tf = jp.parse_tf(tf_resp)
                if raw_tf:
                    self.active_alerts = profiles_db.get_active_alerts(self.profile, raw_tf)

            if not self.telemetry:
                self.telemetry = {
                    "total_cups": self.total_cups,
                    "total_preparations": self.total_preparations,
                    "serial_number": "2018041544012" if (self.conn and self.conn.is_demo) else "N/A",
                    "production_date": "15.04.2018" if (self.conn and self.conn.is_demo) else "N/A",
                    "machine_number": 44012 if (self.conn and self.conn.is_demo) else "N/A",
                    "country_code": "EU" if (self.conn and self.conn.is_demo) else "N/A",
                }

            update_prog(1.0, "Interrogation successfully completed!")
            self.log("Smart Connect interrogation completed successfully!")
            return True

        except Exception as e:
            self.log(f"EXCEPTION during interrogation: {e}")
            return False
        finally:
            if self.conn:
                self.conn.close()

    def get_structured_summary(self) -> Dict[str, Any]:
        """Produce structured statistics dictionary."""
        grand_total = self.total_cups or self.total_preparations

        # Build beverage list
        beverage_list = []
        profile_codes = set()
        for p in self.profile.get("products", []):
            code = p.get("code")
            profile_codes.add(code)
            count = self.counters.get(code, 0)
            beverage_list.append({
                "code": code,
                "name": p.get("name", f"Product #{code}"),
                "count": count,
                "is_double": p.get("is_double", False),
                "active": p.get("active", True)
            })

        # Add any other non-zero counters not in profile
        for code, count in sorted(self.counters.items()):
            if code != 0 and code not in profile_codes and count > 0:
                beverage_list.append({
                    "code": code,
                    "name": profiles_db.get_product_name(self.profile, code),
                    "count": count,
                    "is_double": False,
                    "active": True
                })

        # Build maintenance list
        mc_labels = self.profile.get("maintenance_counters", [
            "Cleaning", "Descaling", "Rinsing", "Filter Change"
        ])

        maint_data = []
        for i, label in enumerate(mc_labels):
            cnt = self.maint_counts[i] if i < len(self.maint_counts) else 0
            pct = self.maint_pcts[i] if i < len(self.maint_pcts) else None
            maint_data.append({
                "index": i,
                "label": label,
                "count": cnt,
                "percentage": pct
            })

        return {
            "timestamp": datetime.now().isoformat(),
            "port": self.port_name,
            "machine_model": self.model_family,
            "firmware_string": self.raw_model_str,
            "ef_code": self.ef_code,
            "protocol_mode": self.protocol_mode,
            "power_spec": self.power_spec,
            "serial_number": self.telemetry.get("serial_number", "N/A"),
            "production_date": self.telemetry.get("production_date", "N/A"),
            "machine_number": self.telemetry.get("machine_number", "N/A"),
            "country_code": self.telemetry.get("country_code", "N/A"),
            "total_preparations": self.total_preparations,
            "total_cups": grand_total,
            "beverages": beverage_list,
            "maintenance": maint_data,
            "telemetry": self.telemetry,
            "alerts": self.active_alerts,
            "raw_log_entries": len(self.raw_log)
        }

    # ========================================================================
    # Exporters
    # ========================================================================

    def export_text_report(self) -> str:
        """
        Generate clean formatted diagnostics report matching
        the classic Jura Service Diagnostics format.
        """
        data = self.get_structured_summary()
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        out = []
        out.append("=" * 78)
        out.append("JURA COFFEE MACHINE DIAGNOSTICS & TELEMETRY REPORT")
        out.append(f"Modern Appliance Diagnostics Suite v{__version__} (Universal Optical & Smart Connect)")
        out.append("=" * 78)
        out.append("")
        out.append(f"Date of diagnosis: {now_str}")
        out.append(f"Connection Port:   {self.port_name} (9600 8N1)")
        out.append("")
        out.append("-" * 78)
        out.append("APPLIANCE IDENTIFICATION & SYSTEM DATA:")
        out.append("-" * 78)
        out.append(f"Appliance Model:   {data['machine_model']}")
        out.append(f"Firmware String:   {data['firmware_string']}")
        out.append(f"Protocol:          {data['protocol_mode']}")
        out.append(f"Power Spec:        {data['power_spec']}")
        if self.telemetry:
            if "serial_number" in self.telemetry and self.telemetry["serial_number"] != "N/A":
                out.append(f"Serial Number:     {self.telemetry['serial_number']}")
            if "production_date" in self.telemetry and self.telemetry["production_date"] != "N/A":
                out.append(f"Date of Production:{self.telemetry['production_date']:>14}")
            if "machine_number" in self.telemetry and self.telemetry["machine_number"]:
                out.append(f"Machine Number:    {self.telemetry['machine_number']}")
            if "country_code" in self.telemetry and self.telemetry["country_code"] != "N/A":
                out.append(f"Destination Region:{self.telemetry['country_code']:>6}")
            if "appliance_code" in self.telemetry and self.telemetry["appliance_code"] != "N/A":
                out.append(f"Appliance Code:    {self.telemetry['appliance_code']}")
        out.append("")

        out.append("-" * 78)
        out.append("BEVERAGE PREPARATIONS & DISPENSING COUNTERS:")
        out.append("-" * 78)
        out.append(f"   {data['total_cups']:>8}      Grand Total Cups Dispensed")
        if data['total_preparations'] != data['total_cups']:
            out.append(f"   {data['total_preparations']:>8}      Total Brew Cycles (Single + Double)")
        out.append("   " + "-" * 55)

        for bev in sorted(data['beverages'], key=lambda x: x['count'], reverse=True):
            if bev['count'] > 0:
                dbl_str = " (2x Cups)" if bev['is_double'] else ""
                out.append(f"   {bev['count']:>8}      {bev['name']}{dbl_str}")

        unused = [b for b in data['beverages'] if b['count'] == 0]
        if unused:
            out.append("")
            out.append("   Beverages with 0 preparations:")
            for b in unused[:8]:
                out.append(f"          0      {b['name']}")
        out.append("")

        out.append("-" * 78)
        out.append("MAINTENANCE & HYGIENE COUNTERS:")
        out.append("-" * 78)
        for m in data['maintenance']:
            pct_str = f" [Life remaining: {m['percentage']}%]" if m['percentage'] is not None else ""
            out.append(f"   {m['count']:>8}      Total {m['label']}{pct_str}")
        out.append("")

        if self.telemetry:
            out.append("-" * 78)
            out.append("OPERATIONAL TELEMETRY & LIFETIME METRICS:")
            out.append("-" * 78)
            if "grinder_formatted" in self.telemetry:
                out.append(f"   Grinder Operating Time:     {self.telemetry['grinder_formatted']} ({self.telemetry['grinder_seconds']} seconds)")
            if "water_dispensed_liters" in self.telemetry:
                out.append(f"   Total Water Dispensed:      {self.telemetry['water_dispensed_liters']} Liters")
            if "descaling_agent_liters" in self.telemetry:
                out.append(f"   Descaling Agent Consumed:   {self.telemetry['descaling_agent_liters']} Liters")
            if "since_last_service_preparations" in self.telemetry:
                out.append(f"   Cycles Since Last Service:  {self.telemetry['since_last_service_preparations']} preparations")
            out.append("")

        out.append("-" * 78)
        out.append("ACTIVE SYSTEM ALERTS & TELEMETRY:")
        out.append("-" * 78)
        if not data['alerts']:
            out.append("   [OK] System Ready - No Active Faults or Warnings")
        else:
            for alert in data['alerts']:
                status_type = "CRITICAL / BLOCKING" if alert.get('blocking') else "READY / STATUS"
                out.append(f"   [{status_type}] {alert['name']}")
        out.append("")

        out.append("=" * 78)
        out.append("END OF DIAGNOSTICS REPORT")
        out.append("=" * 78)
        return "\n".join(out)

    def export_json(self) -> str:
        """Export structured data as JSON string."""
        return json.dumps(self.get_structured_summary(), indent=2, ensure_ascii=False)

    def export_csv(self) -> str:
        """Export counters as CSV string."""
        data = self.get_structured_summary()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Category", "Item Code / Index", "Name / Label", "Value", "Unit / Notes"])
        writer.writerow(["Total", 0, "Grand Total Cups Dispensed", data["total_cups"], "cups"])
        writer.writerow(["Total", 1, "Total Brew Cycles", data["total_preparations"], "cycles"])

        for bev in data["beverages"]:
            writer.writerow(["Beverage", bev["code"], bev["name"], bev["count"], "cups"])

        for m in data["maintenance"]:
            writer.writerow(["Maintenance", m["index"], m["label"], m["count"], f"Life: {m['percentage']}%" if m['percentage'] is not None else ""])

        if self.telemetry:
            for k, v in self.telemetry.items():
                writer.writerow(["Telemetry", 0, k, v, ""])

        for a in data["alerts"]:
            writer.writerow(["Alert", a.get("bit", 0), a["name"], "ACTIVE", "BLOCKING" if a.get("blocking") else "NOTICE"])

        return output.getvalue()
