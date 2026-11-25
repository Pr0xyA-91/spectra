#!/usr/bin/env python3
"""SPECTRA Web Server HTTP handler composition, static asset serving, and server startup."""

import os
import sys
import re
import time
import json
import socket
import threading
import mimetypes
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
from typing import Dict, Any, Optional, Tuple, Set

import stats_collector as sc
from version import __version__, __build__, __edition__

from spectra_web import state as _wstate
from spectra_web.state import (
    PROJECT_DIR,
    HAS_RUST_CORE,
    _CONNECTION_SEMAPHORE,
    _session_lock,
    SpectraThreadingHTTPServer,
    _ensure_serial_group,
    cleanup_resources,
    long_hardware_operation,
    touch_heartbeat,
)
from spectra_web.security import (
    install_tee_streams,
    is_valid_port,
    log_debug_event,
)
from spectra_web.sensors import (
    _canonical_port,
    _get_or_create_mapper,
    compute_advisor_health,
    serialize_register_entry,
)
from spectra_web.routes_get import GetRoutesMixin
from spectra_web.routes_post_hw import PostHardwareRoutesMixin
from spectra_web.routes_post_cloud_ai import PostCloudAiRoutesMixin


class SpectraApiHandler(GetRoutesMixin, PostHardwareRoutesMixin, PostCloudAiRoutesMixin, BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        try:
            msg = format % args
            lvl = "API"
            if len(args) >= 2:
                try:
                    code = int(args[1])
                    if code >= 500:
                        lvl = "ERROR"
                    elif code >= 400:
                        lvl = "WARN"
                except Exception:
                    pass
            log_debug_event(lvl, "API", msg)
        except Exception:
            pass

    def _allowed_origins(self) -> Set[str]:
        srv = getattr(self, "server", None)
        srv_port = getattr(srv, "server_port", None)
        active_port = (
            int(srv_port)
            if isinstance(srv_port, int) and srv_port > 0
            else (int(_wstate._current_http_port) if _wstate._current_http_port else 8080)
        )
        ports: Set[int] = {active_port}
        if os.environ.get("SPECTRA_DEV_CORS") == "1":
            ports.update({5173, 4173})
        origins: Set[str] = {
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        }
        for p in ports:
            origins.add(f"http://127.0.0.1:{p}")
            origins.add(f"http://localhost:{p}")
            origins.add(f"http://[::1]:{p}")
        return origins

    @staticmethod
    def _is_loopback_origin(origin: str) -> bool:
        cleaned = (origin or "").strip().rstrip("/")
        if not cleaned:
            return False
        if cleaned in ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"):
            return True
        try:
            parsed = urlparse(cleaned)
        except Exception:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            return False
        if parsed.username or parsed.password:
            return False
        return True

    def _is_allowed_post_origin(self, origin: str) -> bool:
        cleaned = (origin or "").strip().rstrip("/")
        if not cleaned:
            return True
        if cleaned in self._allowed_origins():
            return True
        # Some Linux WebKitGTK (WebKit2) fetch/beacon POSTs send `Origin: null` even on
        # same-origin localhost pages. Allow ONLY when browser-enforced forbidden headers
        # prove the request originated from local loopback (blocks foreign sandboxed iframes).
        if cleaned.lower() == "null":
            sec_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            if sec_site == "same-origin":
                return True
            if sec_site == "cross-site":
                return False
            referer = (self.headers.get("Referer") or "").strip()
            if referer:
                try:
                    ref_parsed = urlparse(referer)
                    ref_origin = f"{ref_parsed.scheme}://{ref_parsed.netloc}".rstrip("/")
                    if ref_origin in self._allowed_origins():
                        return True
                except Exception:
                    pass
        return False

    _ALLOWED_HOST_RE = re.compile(r"^(?:127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?$", re.IGNORECASE)

    def setup(self):
        if not _CONNECTION_SEMAPHORE.acquire(blocking=False):
            raise ConnectionAbortedError("Maximum concurrent HTTP connections reached")
        self._sem_acquired = True
        try:
            super().setup()
            if self.connection is not None:
                self.connection.settimeout(15.0)
        except Exception:
            _CONNECTION_SEMAPHORE.release()
            self._sem_acquired = False
            raise

    def finish(self):
        try:
            super().finish()
        finally:
            if getattr(self, "_sem_acquired", False):
                self._sem_acquired = False
                try:
                    _CONNECTION_SEMAPHORE.release()
                except ValueError:
                    pass

    def _is_allowed_host(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return False
        return bool(self._ALLOWED_HOST_RE.match(host))

    def _is_allowed_get_request(self, path: str) -> bool:
        if not path.startswith("/api/"):
            return True
        sec_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sec_site == "cross-site":
            return False
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        if origin and origin not in self._allowed_origins():
            return False
        return True

    def _send_security_headers(self):
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        srv = getattr(self, "server", None)
        port = getattr(srv, "server_port", None) or _wstate._current_http_port or 8080
        if origin and origin in self._allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; "
            "connect-src 'self' http://127.0.0.1:* http://localhost:* http://[::1]:*; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
        )

    def do_OPTIONS(self):
        if not self._is_allowed_host():
            self._send_json({"error": "Forbidden host header", "success": False}, status=403)
            return
        self.send_response(200)
        self._send_security_headers()
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def _handle_stats_request(self, port: str):
        if not port or not is_valid_port(port):
            self._send_json({"error": "Invalid or missing serial port"})
            return

        norm_port = _canonical_port(port)
        data: Dict[str, Any]
        err_occurred = False
        with long_hardware_operation(), _session_lock:
            try:
                if _wstate._active_session is not None:
                    try:
                        _wstate._active_session.close()
                    except Exception:
                        pass
                    _wstate._active_session = None

                sess = sc.JuraStatsSession(port_name=norm_port)
                sess.run_interrogation()
                data = sess.get_structured_summary()
                _wstate._active_session = sess
                _wstate._current_port = norm_port
            except Exception as e:
                err_occurred = True
                data = {"error": str(e)}

        if not err_occurred and isinstance(data, dict):
            score, cards = compute_advisor_health(data, {})
            data["health_score"] = score
            data["advisor_cards"] = cards
            with _session_lock:
                _wstate._last_stats_cache = data

        self._send_json(data)

    def _handle_mapper_sweep_request(self, port: str, block_param: str):
        with long_hardware_operation(), _session_lock:
            try:
                mapper, err = _get_or_create_mapper(port)
                if mapper is None:
                    self._send_json({"error": err, "registers": []})
                    return
                if block_param == "all" or not block_param.isdigit():
                    mapper.sweep_eeprom(progress_callback=lambda *_a: touch_heartbeat())
                    regs = [serialize_register_entry(r) for r in mapper.classified_registers]
                else:
                    b_idx = int(block_param)
                    block_res = mapper.sweep_block(b_idx)
                    if isinstance(block_res, dict):
                        updated = block_res.get("registers", [])
                        abort_sweep = bool(block_res.get("abort_sweep", False))
                        abort_reason = block_res.get("abort_reason")
                        end_of_table = bool(block_res.get("end_of_table", False))
                    else:
                        updated = block_res
                        abort_sweep = False
                        abort_reason = None
                        end_of_table = False
                    regs = [serialize_register_entry(r) for r in updated]
                summary = mapper.get_summary_stats()
                payload: Dict[str, Any] = {
                    "registers": regs,
                    "summary": summary,
                    "timestamp": time.strftime("%H:%M:%S")
                }
                if block_param != "all" and block_param.isdigit():
                    payload["abort_sweep"] = abort_sweep
                    if abort_reason:
                        payload["abort_reason"] = abort_reason
                    if end_of_table:
                        payload["end_of_table"] = True
                self._send_json(payload)
            except Exception as e:
                if _wstate._active_session is not None and _wstate._active_session.conn is not None and not getattr(_wstate._active_session.conn, "is_open", True):
                    try:
                        _wstate._active_session.close()
                    except Exception:
                        pass
                    _wstate._active_session = None
                    _wstate._mapper_engine = None
                self._send_json({
                    "error": str(e),
                    "disconnected": True,
                    "registers": []
                })


    MAX_POST_BODY = 16 * 1024 * 1024  # 16 MB safety limit

    def do_POST(self):
        if not self._is_allowed_host():
            self._send_json({"error": "Forbidden host header", "success": False}, status=403)
            return
        url = urlparse(self.path)

        sec_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if sec_site == "cross-site":
            log_debug_event(
                "WARN",
                "SECURITY",
                f"Blocked cross-site POST {url.path} (403): Sec-Fetch-Site={sec_site!r}, Host={self.headers.get('Host', '')!r}",
            )
            self._send_json({"error": "Forbidden cross-site request", "success": False}, status=403)
            return

        origin = self.headers.get("Origin", "")
        if origin and not self._is_allowed_post_origin(origin):
            log_debug_event(
                "WARN",
                "SECURITY",
                f"Blocked POST {url.path} (403): Origin={origin!r}, Host={self.headers.get('Host', '')!r}, "
                f"Referer={self.headers.get('Referer', '')!r}, Sec-Fetch-Site={self.headers.get('Sec-Fetch-Site', '')!r}",
            )
            self._send_json({"error": "Forbidden cross-origin request", "success": False}, status=403)
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_json({"error": "Invalid Content-Length header", "success": False}, status=400)
            return

        if content_length < 0 or content_length > self.MAX_POST_BODY:
            self._send_json({"error": "Payload too large or invalid Content-Length", "success": False}, status=413)
            return

        post_body = self.rfile.read(content_length) if content_length > 0 else b""
        data = {}
        if post_body:
            try:
                parsed_body = json.loads(post_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json({"error": "Invalid JSON body", "success": False}, status=400)
                return
            if not isinstance(parsed_body, dict):
                self._send_json({"error": "JSON body must be an object", "success": False}, status=400)
                return
            data = parsed_body


        if self._post_hw_and_mapper(url, data):
            return
        if self._post_hmi_and_app(url, data):
            return
        if self._post_github(url, data):
            return
        if self._post_ai_and_offsets(url, data):
            return
        if self._post_prefs_and_update(url, data):
            return

        self.send_error(404, "Endpoint Not Found")

    def _serve_static(self, req_path: str):
        _wstate._last_heartbeat_time = time.time()
        if not os.path.isdir(_wstate.DIST_DIR):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            try:
                self.wfile.write(b"<h1>SPECTRA Backend Online</h1><p>Please build the web UI with <code>npm run build</code> inside the <code>web/</code> directory.</p>")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
            return

        decoded_path = unquote(req_path or "")
        if "\x00" in decoded_path or "\\" in decoded_path:
            self.send_error(403, "Forbidden")
            return

        dist_real = os.path.realpath(_wstate.DIST_DIR)
        clean_path = decoded_path.lstrip("/")
        if not clean_path or clean_path == "index.html":
            file_path = os.path.join(dist_real, "index.html")
        else:
            cand_real = os.path.realpath(os.path.join(dist_real, clean_path))
            try:
                within_dist = os.path.commonpath([dist_real, cand_real]) == dist_real
            except ValueError:
                within_dist = False
            if not within_dist:
                self.send_error(403, "Forbidden")
                return
            file_path = cand_real

        if not os.path.isfile(file_path):
            # Check project root or public assets for exact allowlisted favicons/icons
            if clean_path in ("favicon.ico", "icon.png", "icon.ico", "logo.svg"):
                for alt_root in (os.path.join(PROJECT_DIR, "web", "public"), PROJECT_DIR):
                    cand = os.path.realpath(os.path.join(alt_root, clean_path))
                    alt_real = os.path.realpath(alt_root)
                    if os.path.commonpath([alt_real, cand]) == alt_real and os.path.isfile(cand):
                        file_path = cand
                        break

        if not os.path.isfile(file_path):
            # Fallback to SPA index.html for client-side routing
            file_path = os.path.join(dist_real, "index.html")

        if os.path.isfile(file_path):
            lower_path = file_path.lower()
            if lower_path.endswith(".webp"):
                mime_type = "image/webp"
            elif lower_path.endswith(".md"):
                mime_type = "text/markdown; charset=utf-8"
            else:
                mime_type, _ = mimetypes.guess_type(file_path)
                if not mime_type:
                    mime_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self._send_security_headers()
            self.end_headers()
            try:
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
                pass
        else:
            self.send_error(404, "File Not Found")

    def _send_json(self, data: Any, status: int = 200, extra_headers: Optional[Dict[str, str]] = None):
        try:
            payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._send_security_headers()
            if extra_headers:
                for hdr_k, hdr_v in extra_headers.items():
                    self.send_header(hdr_k, hdr_v)
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
            pass


def find_free_port(start_port: int = 8080) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def bind_http_server(
    preferred_port: Optional[int] = None,
    default_start: int = 8080,
) -> Tuple[SpectraThreadingHTTPServer, int]:
    """
    Bind SpectraThreadingHTTPServer on preferred_port (or SPECTRA_PREFERRED_PORT env)
    with brief SO_REUSEADDR retry tolerance for post-update execv restarts, falling
    back cleanly to find_free_port(default_start).
    """
    env_pref_raw = os.environ.pop("SPECTRA_PREFERRED_PORT", "")
    pref_port: Optional[int] = None
    if preferred_port is not None and 0 < int(preferred_port) < 65536:
        pref_port = int(preferred_port)
    elif env_pref_raw.strip().isdigit():
        val = int(env_pref_raw.strip())
        if 0 < val < 65536:
            pref_port = val

    if pref_port is not None:
        for _attempt in range(25):
            try:
                httpd = SpectraThreadingHTTPServer(("127.0.0.1", pref_port), SpectraApiHandler)
                return httpd, pref_port
            except OSError:
                time.sleep(0.12)

    for offset in range(50):
        candidate = default_start + offset
        if candidate >= 65536:
            break
        try:
            httpd = SpectraThreadingHTTPServer(("127.0.0.1", candidate), SpectraApiHandler)
            return httpd, candidate
        except OSError:
            continue

    httpd = SpectraThreadingHTTPServer(("127.0.0.1", 0), SpectraApiHandler)
    return httpd, int(httpd.server_address[1])


def main(auto_open: bool = False):
    _ensure_serial_group()
    install_tee_streams()
    try:
        import tls_utils
        tls_utils.configure_process_tls_env()
    except Exception:
        pass

    restarted_after_update = os.environ.pop("SPECTRA_RESTARTED_AFTER_UPDATE", "") == "1"

    requested_port: Optional[int] = None
    no_browser = "--no-browser" in sys.argv or os.environ.get("SPECTRA_NATIVE_SHELL") == "1"
    for idx, arg in enumerate(sys.argv[1:], start=1):
        if arg == "--port" and idx + 1 < len(sys.argv):
            try:
                requested_port = int(sys.argv[idx + 1])
            except ValueError:
                pass
        elif arg.startswith("--port="):
            try:
                requested_port = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    httpd, port = bind_http_server(preferred_port=requested_port, default_start=8080)
    _wstate._current_http_port = port
    _wstate._active_httpd = httpd

    print("=" * 78)
    print(f"  SPECTRA (Build {__build__}) Hardware Telemetry API & Web Server")
    print("=" * 78)
    print(f"[*] API & Web Service listening on: http://127.0.0.1:{port}")
    print(f"[*] Native Rust Core Acceleration: {'ENABLED (spectra_py)' if HAS_RUST_CORE else 'DISABLED (Pure Python fallback)'}")
    print("[*] Serving Next-Gen Multi-Paradigm UI connected to live hardware adapters.")
    print("=" * 78)

    log_debug_event(
        "INFO",
        "SpectraCore",
        f"Native Rust Acceleration: {'ACTIVE (spectra_py)' if HAS_RUST_CORE else 'INACTIVE (Pure Python fallback)'}"
    )

    # Automatically launch browser on Windows or when auto_open is True or --open is passed,
    # unless explicitly suppressed for native shell hosting (--no-browser / SPECTRA_NATIVE_SHELL=1)
    # or immediately following an in-place self-update restart (existing tab reloads seamlessly).
    if not restarted_after_update and not no_browser and (auto_open or sys.platform.startswith("win") or "--open" in sys.argv):
        try:
            import webbrowser
            threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down SPECTRA API server...")
        cleanup_resources()
        httpd.server_close()



