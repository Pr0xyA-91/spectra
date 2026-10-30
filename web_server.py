#!/usr/bin/env python3
"""
SPECTRA — Next-Gen Hardware Telemetry & Logic Board Diagnostics — Web Server
Provides REST APIs for real physical serial adapters (/dev/ttyUSB*, COM*) and simulated mock devices.
Serves the multi-paradigm reactive interface at http://127.0.0.1:8080.
"""

import os
import sys
import time
import json
import socket
import threading
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional

# Ensure local modules are importable
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import serial_io
import stats_collector as sc
from version import __version__, __build__, __edition__

# Global Session State
_session_lock = threading.Lock()
_active_session: Optional[sc.JuraStatsSession] = None
_current_port: str = ""
_last_stats_cache: Optional[Dict[str, Any]] = None

DIST_DIR = os.path.join(PROJECT_DIR, "web", "dist")


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

            global _active_session, _current_port
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

                    data = sc.query_live_sensors(
                        port_name=port,
                        conn=_active_session.conn if (_active_session.conn and _active_session.conn.is_open) else None,
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

            global _last_stats_cache
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
                    _last_stats_cache = data
                    sess.close()
                except Exception as e:
                    data = {"error": str(e)}

            self._send_json(data)
            return

        # 4. API: Optical Bean Threshold Calibration Info
        elif url.path == "/api/calibration":
            calib = sc.get_optical_bean_calibration()
            self._send_json(calib)
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
