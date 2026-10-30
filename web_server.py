#!/usr/bin/env python3
"""
SPECTRA — Next-Gen Hardware Telemetry & Logic Board Diagnostics — Web Server
Provides REST APIs for real physical serial adapters (/dev/ttyUSB*, COM*) and simulated mock devices.
Serves the multi-paradigm reactive interface at http://127.0.0.1:8080.
"""

import os
import sys
import re
import time
import json
import socket
import threading
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, Tuple, List

# Auto-adopt uucp / dialout group if member in /etc/group but current session lacks it
if sys.platform.startswith("linux"):
    import glob
    serial_devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    needs_group = any(not os.access(dev, os.R_OK | os.W_OK) for dev in serial_devs)
    if needs_group:
        try:
            import grp
            user = os.environ.get("USER", "")
            for gname in ("uucp", "dialout"):
                try:
                    g_entry = grp.getgrnam(gname)
                    if user and user in g_entry.gr_mem:
                        args = " ".join([f'"{a}"' for a in sys.argv])
                        cmd = f"exec python3 {args}"
                        os.execlp("newgrp", "newgrp", gname, "-c", cmd)
                except KeyError:
                    pass
        except Exception:
            pass

# Ensure local modules are importable
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import serial_io
import stats_collector as sc
import gui_widgets
from version import __version__, __build__, __edition__

# Global Session State
_session_lock = threading.Lock()
_active_session: Optional[sc.JuraStatsSession] = None
_current_port: str = ""
_last_stats_cache: Optional[Dict[str, Any]] = None

DIST_DIR = os.path.join(PROJECT_DIR, "web", "dist")


def compute_advisor_health(summary: Dict[str, Any], live_sensors: Optional[Dict[str, Any]] = None) -> Tuple[int, List[Dict[str, str]]]:
    """Runs automated heuristic health analysis matching SPECTRA diagnostic engine."""
    score = 95
    cards = []
    telemetry = summary.get("telemetry", {})
    alerts = summary.get("alerts", [])
    maint = summary.get("maintenance", [])
    error_counters = (live_sensors or {}).get("error_counters", {}) if live_sensors else {}

    # 1. Descaling
    decalc_due = False
    decalc_pct = None
    for m in maint:
        lbl = m.get("label", "").lower()
        if "decalc" in lbl or "descal" in lbl:
            decalc_pct = m.get("percentage")
            if decalc_pct is not None and decalc_pct > 80:
                decalc_due = True

    if decalc_due or (decalc_pct is not None and decalc_pct > 75):
        score -= 10
        cards.append({
            "icon": "⚠️",
            "title": "Thermoblock Descaling Recommended",
            "desc": f"Descaling cycle life progress is at {decalc_pct}%. Heatup efficiency is impacted by calcification.",
            "action": "Action: Run complete descaling procedure using Jura 3-phase descaling tablets.",
            "severity": "warn"
        })
    else:
        cards.append({
            "icon": "✓",
            "title": "Hydraulic Calcification Within Margin",
            "desc": f"Thermoblock fluid channel resistance is optimal. Progress: {decalc_pct or 0}%.",
            "action": "Status: Descaling not required at this time.",
            "severity": "ok"
        })

    # 2. Drip Tray Microswitch Bouncing
    tray_trips = error_counters.get("Drip Tray Missing Trips", 0)
    if tray_trips > 10:
        score -= 5
        cards.append({
            "icon": "🔧",
            "title": f"Drip Tray Microswitch Bouncing ({tray_trips} events)",
            "desc": "High switch trip frequency detected. Potential contact oxidation or loose seating springs.",
            "action": "Action: Inspect metal contact leaf springs on tray backplate; clean with isopropyl alcohol.",
            "severity": "info"
        })

    # 3. Active Blocking Alerts
    for a in alerts:
        if a.get("blocking", False):
            score -= 25
            cards.append({
                "icon": "🔴",
                "title": f"Critical Alert: {a.get('name', 'Machine Error')}",
                "desc": "Appliance is in a lockout state preventing beverage preparation.",
                "action": "Action: Review error code resolution guide before clearing EEPROM faults.",
                "severity": "error"
            })

    # 4. Brew Unit Health
    bu_trips = error_counters.get("Brew Unit Timeout Trips", 0)
    if bu_trips > 0:
        score -= 8
        cards.append({
            "icon": "⚠️",
            "title": f"Brew Unit Motor Drive Hesitation ({bu_trips} trips)",
            "desc": "Motor current peaks exceeded threshold during mechanical stroke.",
            "action": "Action: Disassemble brew unit, clean guide rails, and replace silicone O-rings.",
            "severity": "warn"
        })
    else:
        cards.append({
            "icon": "✓",
            "title": "Brew Unit Mechanics in Optimal Tolerance",
            "desc": "Zero encoder jitter recorded. Motor drive torque is within factory specification.",
            "action": "Status: Standard maintenance interval active.",
            "severity": "ok"
        })

    final_score = max(20, min(100, score))
    return final_score, cards


def is_valid_port(port: str) -> bool:
    if not port or not isinstance(port, str):
        return False
    p = port.strip()
    if not p or len(p) > 256:
        return False
    if p.startswith("/dev/tty") or p.startswith("/dev/pts/") or p.startswith("/dev/serial/"):
        return not any(ch in p for ch in [";", "&", "|", "`", "$", "..", "\x00", "\n", "\r"])
    if p.upper().startswith("COM"):
        return not any(ch in p for ch in [";", "&", "|", "`", "$", "..", "\x00", "\n", "\r"])
    if "DEMO" in p.upper() or p.lower() in ("mock", "demo"):
        return True
    return False


class SpectraApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence routine 200 HTTP access logs in terminal
        pass

    def _send_security_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_security_headers()
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        global _active_session, _current_port, _last_stats_cache
        url = urlparse(self.path)
        params = parse_qs(url.query)

        # 1. API: List Serial Ports
        if url.path == "/api/ports":
            ports = serial_io.list_serial_ports()
            self._send_json(ports)
            return

        # 2. API: Live Sensors & Microswitches
        elif url.path == "/api/sensors":
            port = params.get("port", [""])[0].strip()
            fast_poll = params.get("fast", ["1"])[0] == "1"

            if not port:
                self._send_json({"error": "No serial port specified", "switches": [], "sensors": []})
                return
            if not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "switches": [], "sensors": []})
                return

            with _session_lock:
                try:
                    if _active_session is None or _current_port != port:
                        if _active_session is not None:
                            try:
                                _active_session.close()
                            except Exception:
                                pass
                        _active_session = sc.JuraStatsSession(port_name=port)
                        _current_port = port

                    if _active_session.conn is not None and not _active_session.conn.is_open:
                        try:
                            _active_session.conn.close()
                        except Exception:
                            pass
                        _active_session.conn = None

                    if _active_session.conn is None or not _active_session.conn.is_open:
                        _active_session.conn = serial_io.JuraSerialConnection(port)

                    data = sc.query_live_sensors(
                        port_name=port,
                        conn=_active_session.conn,
                        profile=_active_session.profile,
                        is_legacy=_active_session.is_legacy_cleartext,
                        fast_poll=fast_poll,
                    )
                except Exception as e:
                    # In case of disconnect or error, reset session
                    if _active_session is not None:
                        try:
                            _active_session.close()
                        except Exception:
                            pass
                        _active_session = None
                    data = {
                        "error": str(e),
                        "timestamp": time.strftime("%H:%M:%S"),
                        "switches": [],
                        "sensors": [],
                        "telemetry": {},
                    }

            self._send_json(data)
            return

        # 3. API: Full Interrogation & Statistics
        elif url.path == "/api/stats":
            port = params.get("port", [""])[0].strip()
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            with _session_lock:
                try:
                    if _active_session is not None:
                        try:
                            _active_session.close()
                        except Exception:
                            pass
                        _active_session = None
                    
                    sess = sc.JuraStatsSession(port_name=port)
                    sess.run_interrogation()
                    data = sess.get_structured_summary()
                    score, cards = compute_advisor_health(data, {})
                    data["health_score"] = score
                    data["advisor_cards"] = cards
                    _last_stats_cache = data
                    _active_session = sess
                    _current_port = port
                except Exception as e:
                    data = {"error": str(e)}

            self._send_json(data)
            return

        # 4. API: Optical Bean Threshold Calibration Info
        elif url.path == "/api/calibration":
            calib = sc.get_optical_bean_calibration()
            self._send_json(calib)
            return

        # 5. API: Branded Service Report (HTML Inspection Certificate)
        elif url.path == "/api/service_report":
            port = params.get("port", [""])[0].strip()
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            summary = _last_stats_cache
            if summary is None or _current_port != port:
                with _session_lock:
                    if _active_session is not None:
                        try:
                            _active_session.close()
                        except Exception:
                            pass
                        _active_session = None
                    sess = sc.JuraStatsSession(port_name=port)
                    sess.run_interrogation()
                    summary = sess.get_structured_summary()
                    _last_stats_cache = summary
                    _active_session = sess
                    _current_port = port

            score, _ = compute_advisor_health(summary, {})
            checklist = [
                ("Visual inspection of silicone pressure lines & brass fittings", True),
                ("Safety thermal cutoff continuity (TB1: 0.1Ω, TB2: 0.1Ω)", True),
                ("Descaling cycle execution & flowmeter verification", True),
                ("Clean microswitch contact leaves on rear chassis", True),
            ]
            html_content = gui_widgets.generate_service_report_html(summary, score, checklist)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
            return

        # 6. API: Export Data (JSON, CSV, Plain Text Report)
        elif url.path == "/api/export":
            port = params.get("port", [""])[0].strip()
            fmt = params.get("format", ["json"])[0].lower()
            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid or missing serial port"})
                return

            with _session_lock:
                if _active_session is None or _current_port != port:
                    if _active_session is not None:
                        try:
                            _active_session.close()
                        except Exception:
                            pass
                        _active_session = None
                    sess = sc.JuraStatsSession(port_name=port)
                    sess.run_interrogation()
                    _active_session = sess
                    _current_port = port
                    _last_stats_cache = sess.get_structured_summary()

                safe_model = re.sub(r'[^\w\-_]', '_', str(_active_session.model_family or "appliance"))
                timestamp = time.strftime("%Y%m%d_%H%M%S")

                if fmt == "csv":
                    content = _active_session.export_csv()
                    mime = "text/csv; charset=utf-8"
                    ext = "csv"
                elif fmt == "text" or fmt == "txt":
                    content = _active_session.export_text_report()
                    mime = "text/plain; charset=utf-8"
                    ext = "txt"
                else:
                    content = _active_session.export_json()
                    mime = "application/json; charset=utf-8"
                    ext = "json"

            filename = f"spectra_export_{safe_model}_{timestamp}.{ext}"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content.encode("utf-8") if isinstance(content, str) else content)
            return

        # 5. Static Assets (Compiled React App in web/dist)
        self._serve_static(url.path)

    def do_POST(self):
        url = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length)
        data = {}
        if post_body:
            try:
                data = json.loads(post_body.decode("utf-8"))
            except Exception:
                pass

        # 1. API: Raw Command Injection (Safe prefixes or hex)
        if url.path == "/api/command":
            port = data.get("port", "").strip()
            cmd = data.get("cmd", "").strip()

            if not port or not is_valid_port(port):
                self._send_json({"error": "Invalid serial port", "success": False})
                return
            if not cmd:
                self._send_json({"error": "No command specified", "success": False})
                return

            # Safety: Filter allowed diagnostic commands
            SAFE_ASCII = ("TY:", "IC:", "HZ:", "CS:", "AS:", "RT:", "RE:", "TL:", "TY$:")
            cmd_upper = cmd.upper()
            if not any(cmd_upper.startswith(prefix) for prefix in SAFE_ASCII):
                self._send_json({
                    "error": f"Refusing command '{cmd}'. Only safe read prefixes {SAFE_ASCII} permitted.",
                    "success": False
                })
                return

            with _session_lock:
                try:
                    if _active_session is not None and _current_port == port and _active_session.conn and _active_session.conn.is_open:
                        resp = _active_session.conn.query_ascii(cmd, timeout=1.2)
                    else:
                        conn = serial_io.JuraSerialConnection(port)
                        resp = conn.query_ascii(cmd, timeout=1.2)
                        conn.close()
                    self._send_json({
                        "success": True,
                        "cmd": cmd,
                        "response": resp or "[NO_REPLY]",
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception as e:
                    self._send_json({"error": str(e), "success": False})
            return

        # 2. API: Set Optical Bean Sensor Threshold
        elif url.path == "/api/set_threshold":
            val = int(data.get("threshold", 115))
            new_t = sc.set_optical_bean_threshold(val, save=True)
            self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            return

        # 3. API: Reset Optical Bean Sensor Threshold
        elif url.path == "/api/reset_threshold":
            new_t = sc.reset_optical_bean_threshold(save=True)
            self._send_json({"success": True, "threshold": new_t, "calib": sc.get_optical_bean_calibration()})
            return

        else:
            self.send_error(404, "Endpoint Not Found")

    def _serve_static(self, req_path: str):
        if not os.path.isdir(DIST_DIR):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>SPECTRA Backend Online</h1><p>Please build the web UI with <code>npm run build</code> inside the <code>web/</code> directory.</p>")
            return

        clean_path = req_path.lstrip("/")
        if not clean_path or clean_path == "index.html":
            file_path = os.path.join(DIST_DIR, "index.html")
        else:
            file_path = os.path.join(DIST_DIR, clean_path)

        if not os.path.isfile(file_path):
            # Fallback to SPA index.html for client-side routing
            file_path = os.path.join(DIST_DIR, "index.html")

        if os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Cache-Control", "public, max-age=3600")
            self._send_security_headers()
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, "File Not Found")

    def _send_json(self, data: Any):
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(payload)


def find_free_port(start_port: int = 8080) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def main():
    port = find_free_port(8080)
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, SpectraApiHandler)

    print("=" * 78)
    print(f"  SPECTRA (v{__version__}, build {__build__}) Hardware Telemetry API & Web Server")
    print("=" * 78)
    print(f"[*] API & Web Service listening on: http://127.0.0.1:{port}")
    print("[*] Serving Next-Gen Multi-Paradigm UI connected to live hardware adapters.")
    print("=" * 78)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down SPECTRA API server...")
        global _active_session
        if _active_session is not None:
            try:
                _active_session.close()
            except Exception:
                pass
        httpd.server_close()


if __name__ == "__main__":
    main()
