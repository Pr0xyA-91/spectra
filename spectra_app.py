#!/usr/bin/env python3
"""
SPECTRA — Universal Hardware Telemetry & Firmware Diagnostics
Standalone Native Desktop App Mode

Runs SPECTRA as a true standalone desktop application with the React UI (web/dist/),
requiring no web browser tab and no open terminal window, terminating cleanly and
completely when the window is closed.

Window Backends:
1. Linux Native GTK3 + WebKit2 (4.1/4.0) — Zero-latency native desktop window.
2. Cross-Platform pywebview — Native Windows (WebView2) / macOS (WebKit) / Linux window.
3. Chromeless Standalone App Window fallback (msedge.exe / chrome / chromium --app=...)
   with automatic window-close beacon & heartbeat watchdog termination.
4. Browser mode (--browser) or Legacy GTK (--legacy-gtk).
"""

import sys
import os

# Safe standard streams when running under pythonw.exe or FreeConsole() on Windows
import re
import tempfile

_LOG_SECRET_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{10,}|github_pat_[A-Za-z0-9_]{10,}|"
    r"(?:Authorization\s*:\s*(?:Bearer|token)\s+)[^\s\"',}]+|"
    r"(?:access_token[\"']?\s*[:=]\s*[\"']?)[^\"'\s,}]+)",
    re.IGNORECASE,
)


def _redact_log_text(text: str) -> str:
    if not text:
        return ""
    return _LOG_SECRET_RE.sub("[REDACTED]", str(text))


def _get_private_log_dir() -> str:
    """Return user-private log directory (%LOCALAPPDATA%\\SPECTRA\\logs or ~/.config/spectra/logs)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        log_dir = os.path.join(base, "SPECTRA", "logs")
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = xdg if xdg else os.path.join(os.path.expanduser("~"), ".config")
        log_dir = os.path.join(base, "spectra", "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        if os.name != "nt":
            os.chmod(log_dir, 0o700)
        return log_dir
    except Exception:
        return tempfile.gettempdir()


class _RotatingLogStream:
    """Bounded, thread-safe, token-redacting file stream rotating at max_bytes (256 KiB x 2 backups)."""

    def __init__(self, path: str, max_bytes: int = 256 * 1024, backup_count: int = 2):
        import threading as _threading
        self.path = path
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = _threading.Lock()

    def _rotate_if_needed(self) -> None:
        try:
            if not os.path.exists(self.path) or os.path.getsize(self.path) < self.max_bytes:
                return
            for idx in range(self.backup_count, 0, -1):
                src = self.path if idx == 1 else f"{self.path}.{idx - 1}"
                dst = f"{self.path}.{idx}"
                if os.path.exists(src):
                    os.replace(src, dst)
        except Exception:
            pass

    def write(self, s: str) -> int:
        if not s:
            return 0
        cleaned = _redact_log_text(s)
        with self._lock:
            try:
                self._rotate_if_needed()
                if os.name != "nt":
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    with os.fdopen(fd, "a", encoding="utf-8") as fh:
                        fh.write(cleaned)
                else:
                    with open(self.path, "a", encoding="utf-8") as fh:
                        fh.write(cleaned)
            except Exception:
                pass
        return len(s)

    def flush(self) -> None:
        pass


if sys.platform.startswith("win"):
    try:
        _log_path = os.path.join(_get_private_log_dir(), "spectra_app.log")
        if sys.stdout is None or sys.stderr is None:
            _log_file = _RotatingLogStream(_log_path)
            if sys.stdout is None:
                sys.stdout = _log_file
            if sys.stderr is None:
                sys.stderr = _log_file
    except Exception:
        if sys.stdout is None:
            try:
                sys.stdout = open(os.devnull, "w", encoding="utf-8")
            except Exception:
                pass
        if sys.stderr is None:
            try:
                sys.stderr = open(os.devnull, "w", encoding="utf-8")
            except Exception:
                pass
else:
    if sys.stdout is None:
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            pass
    if sys.stderr is None:
        try:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            pass

import time
import shutil
import threading
import subprocess
from typing import Optional, List, Tuple, Any, Dict

# Enable per-monitor High-DPI awareness on Windows early
if sys.platform.startswith("win"):
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    import tls_utils
    tls_utils.configure_process_tls_env()
except Exception:
    pass

try:
    from version import __build__, __version__
except ImportError:
    __build__ = "20261114.0020"
    __version__ = f"Build {__build__}"


def shutdown_spectra_cleanly(httpd=None):
    """
    Unified shutdown helper:
    1. Closes any active serial hardware session.
    2. Stops/unloads any SPECTRA-managed local Ollama process.
    3. Shuts down the in-process HTTP server.
    """
    try:
        import web_server
        web_server.cleanup_resources()
    except Exception:
        pass

    try:
        import hmi_inspector
        hmi_inspector.KalermHmiInspector.control_local_ollama("stop")
    except Exception:
        pass

    if httpd:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass


def start_inprocess_server() -> Tuple[Any, int, str]:
    """
    Starts the SpectraThreadingHTTPServer on a free (or preferred) localhost port
    inside a daemon thread. Returns (httpd, port, url).
    """
    import web_server
    web_server.install_tee_streams()
    httpd, port = web_server.bind_http_server(default_start=8080)
    web_server._current_http_port = port
    web_server._active_httpd = httpd

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="SpectraHttpServer")
    server_thread.start()

    url = f"http://127.0.0.1:{port}"
    return httpd, port, url


def get_host_monitor_geometry() -> Dict[str, Any]:
    """
    Detects the usable host monitor geometry and computes adaptive desktop window
    dimensions and auto-zoom factor. Zero hardcoded dimensions so windows never
    overflow compact laptop screens (1366x768, 1280x800) or Wayland/Hyprland bounds.
    """
    work_w = 1440
    work_h = 900
    scale_factor = 1

    # Linux (GTK3 / Gdk)
    if sys.platform.startswith("linux"):
        try:
            import gi
            gi.require_version("Gdk", "3.0")
            from gi.repository import Gdk
            display = Gdk.Display.get_default()
            if display:
                mon = display.get_primary_monitor() or (display.get_monitor(0) if display.get_n_monitors() > 0 else None)
                if mon:
                    geom = mon.get_workarea()
                    work_w = geom.width
                    work_h = geom.height
                    scale_factor = mon.get_scale_factor()
        except Exception:
            pass

    # Windows (ctypes user32 SPI_GETWORKAREA)
    elif sys.platform.startswith("win"):
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                work_w = rect.right - rect.left
                work_h = rect.bottom - rect.top
            else:
                work_w = ctypes.windll.user32.GetSystemMetrics(0)
                work_h = ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            pass

    # Bounds sanity
    work_w = max(int(work_w), 800)
    work_h = max(int(work_h), 520)

    # Compute Adaptive Window Geometry:
    # win_w = min(max(int(work_w * 0.94), min(960, work_w)), work_w)
    # win_h = min(max(int(work_h * 0.92), min(600, work_h)), work_h)
    win_w = min(max(int(work_w * 0.94), min(960, work_w)), work_w)
    win_h = min(max(int(work_h * 0.92), min(600, work_h)), work_h)

    # Compute auto_zoom:
    # Baseline design canvas: 1480 x 880.
    if work_w < 1440 or work_h < 840:
        auto_zoom = round(max(0.75, min(work_w / 1480.0, work_h / 880.0)), 2)
    elif work_w >= 2500 and scale_factor == 1:
        auto_zoom = round(min(1.35, work_w / 1920.0), 2)
    else:
        auto_zoom = 1.0

    return {
        "work_w": work_w,
        "work_h": work_h,
        "scale_factor": scale_factor,
        "win_w": win_w,
        "win_h": win_h,
        "auto_zoom": auto_zoom,
    }


# ============================================================================
# Backend A: Linux Native GTK3 + WebKit2 (4.1 / 4.0)
# ============================================================================
def try_launch_gtk_webkit(url: str, port: int, httpd, build_str: str) -> bool:
    """
    Launches SPECTRA in a native GTK3 + WebKit2 desktop window.
    Supports WebKit2 4.1 (modern Linux/Omarchy) and 4.0.
    """
    os.environ.setdefault("GTK_THEME", "Adwaita:dark")
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

        try:
            GLib.set_prgname("spectra")
            GLib.set_application_name("SPECTRA")
        except Exception:
            pass

        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings:
            try:
                gtk_settings.set_property("gtk-application-prefer-dark-theme", True)
            except Exception:
                pass

        try:
            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(b"""
                window, menu, menuitem, popover, combobox, treeview, cellview {
                    background-color: #18181b;
                    color: #f4f4f5;
                }
                menuitem:hover, treeview:selected, cellview:selected {
                    background-color: #164e63;
                    color: #67e8f9;
                }
            """)
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(
                    screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
        except Exception:
            pass

        try:
            gi.require_version("WebKit2", "4.1")
            from gi.repository import WebKit2
        except (ValueError, ImportError):
            gi.require_version("WebKit2", "4.0")
            from gi.repository import WebKit2
    except Exception:
        return False

    try:
        import web_server
        web_server._is_native_webview = True
    except Exception:
        pass

    geom = get_host_monitor_geometry()

    window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    window.set_title(f"SPECTRA — Universal Hardware Telemetry & Firmware Diagnostics (Build {build_str})")
    try:
        window.set_wmclass("spectra", "SPECTRA")
    except Exception:
        pass
    window.set_default_size(geom["win_w"], geom["win_h"])
    min_w = min(800, max(600, geom["work_w"] - 40))
    min_h = min(520, max(400, geom["work_h"] - 40))
    window.set_size_request(min_w, min_h)
    window.set_position(Gtk.WindowPosition.CENTER)

    # Window Icon
    for icon_candidate in [
        os.path.join(PROJECT_DIR, "icon.png"),
        os.path.join(PROJECT_DIR, "spectra_logo.svg"),
        os.path.join(PROJECT_DIR, "web", "public", "logo.svg"),
        os.path.join(PROJECT_DIR, "web", "dist", "logo.svg"),
        os.path.join(PROJECT_DIR, "icon.ico"),
    ]:
        if os.path.isfile(icon_candidate):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_candidate, 64, 64)
                window.set_icon(pixbuf)
                break
            except Exception:
                pass

    # WebKit2 Settings
    settings = WebKit2.Settings()
    settings.set_enable_javascript(True)
    settings.set_enable_developer_extras(True)
    settings.set_enable_smooth_scrolling(True)
    if hasattr(settings, "set_page_cache_enabled"):
        settings.set_page_cache_enabled(False)
    elif hasattr(settings, "set_enable_page_cache"):
        settings.set_enable_page_cache(False)
    if hasattr(settings, "set_hardware_acceleration_policy"):
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.ALWAYS)
    if hasattr(settings, "set_enable_webgl"):
        settings.set_enable_webgl(True)

    webview = WebKit2.WebView.new_with_settings(settings)

    # Key press handler: F12 or Ctrl+Shift+D toggles debug monitor
    def on_key_press(widget, event):
        keyval = event.keyval
        state = event.state
        is_ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        is_shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if keyval == Gdk.KEY_F12 or (is_ctrl and is_shift and keyval in (Gdk.KEY_d, Gdk.KEY_D)):
            js = "window.dispatchEvent(new CustomEvent('spectra-toggle-debug'));"
            webview.run_javascript(js, None, None, None)
            return True
        return False

    window.connect("key-press-event", on_key_press)

    # Dark background to prevent white flashes
    rgba = Gdk.RGBA()
    rgba.parse("#18181b")  # zinc-900
    webview.set_background_color(rgba)

    # File Download Handling & Context Cache Clearing
    context = webview.get_context()
    if context:
        if hasattr(context, "clear_cache"):
            try:
                context.clear_cache()
            except Exception:
                pass

    def on_download_started(ctx, download):
        suggested = download.get_suggested_filename() or "spectra_export"
        dialog = Gtk.FileChooserNative.new(
            "Save Export",
            window,
            Gtk.FileChooserAction.SAVE,
            "_Save",
            "_Cancel"
        )
        dialog.set_current_name(suggested)
        default_dir = os.path.expanduser("~/Downloads")
        if os.path.isdir(default_dir):
            dialog.set_current_folder(default_dir)
        response = dialog.run()
        if response == Gtk.ResponseType.ACCEPT:
            dest_file = dialog.get_filename()
            download.set_destination(f"file://{os.path.abspath(dest_file)}")
        else:
            download.cancel()
        dialog.destroy()

    if context:
        context.connect("download-started", on_download_started)

    webview.load_uri(f"{url}/?v={build_str}")

    scrolled = Gtk.ScrolledWindow()
    scrolled.add(webview)
    window.add(scrolled)

    restart_state = {"requested": False}
    try:
        import updater

        def _request_gtk_restart():
            restart_state["requested"] = True
            GLib.idle_add(window.destroy)

        updater.register_linux_restart_handler(_request_gtk_restart)
    except Exception:
        updater = None  # type: ignore[assignment]

    def on_window_destroy(widget):
        shutdown_spectra_cleanly(httpd)
        Gtk.main_quit()
        if not restart_state["requested"]:
            os._exit(0)

    window.connect("destroy", on_window_destroy)
    window.show_all()

    try:
        Gtk.main()
    except (KeyboardInterrupt, SystemExit):
        on_window_destroy(window)
    finally:
        if updater is not None:
            try:
                updater.register_linux_restart_handler(None)
            except Exception:
                pass

    if restart_state["requested"] and updater is not None:
        updater.relaunch_current_process(preferred_port=port)

    return True


# ============================================================================
# Backend B: Cross-Platform pywebview (Windows / macOS / Linux)
# ============================================================================
def try_launch_pywebview(url: str, port: int, httpd, build_str: str) -> bool:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SPECTRA.Diagnostics.Suite")
        except Exception:
            pass

        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        py_dll = os.path.join(exe_dir, f"python{sys.version_info.major}{sys.version_info.minor}.dll")
        if os.path.isfile(py_dll):
            os.environ.setdefault("PYTHONNET_PYDLL", py_dll)
        if hasattr(os, "add_dll_directory") and os.path.isdir(exe_dir):
            try:
                os.add_dll_directory(exe_dir)
            except Exception:
                pass

    try:
        import webview
    except ImportError:
        return False

    try:
        import web_server
        web_server._is_native_webview = True
    except Exception:
        pass

    geom = get_host_monitor_geometry()
    win_state_path = (
        os.path.join(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "SPECTRA", "window_state.json")
        if sys.platform.startswith("win")
        else os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"), "spectra", "window_state.json")
    )
    win_state = {"maximized": True, "width": geom["win_w"], "height": geom["win_h"], "x": None, "y": None}
    try:
        import json as _json
        if os.path.isfile(win_state_path):
            with open(win_state_path, "r", encoding="utf-8") as _f:
                loaded = _json.load(_f)
            if isinstance(loaded, dict):
                if isinstance(loaded.get("maximized"), bool):
                    win_state["maximized"] = loaded["maximized"]
                if isinstance(loaded.get("width"), int) and 640 <= loaded["width"] <= 16384:
                    win_state["width"] = loaded["width"]
                if isinstance(loaded.get("height"), int) and 480 <= loaded["height"] <= 16384:
                    win_state["height"] = loaded["height"]
                if isinstance(loaded.get("x"), int) and -16384 <= loaded["x"] <= 32768:
                    win_state["x"] = loaded["x"]
                if isinstance(loaded.get("y"), int) and -16384 <= loaded["y"] <= 32768:
                    win_state["y"] = loaded["y"]
    except Exception:
        pass

    title = f"SPECTRA — Universal Hardware Telemetry & Firmware Diagnostics (Build {build_str})"
    win_kwargs = {
        "title": title,
        "url": f"{url}/?v={build_str}",
        "width": win_state["width"],
        "height": win_state["height"],
        "min_size": (min(800, geom["win_w"]), min(520, geom["win_h"])),
        "background_color": "#18181b",
        "maximized": win_state["maximized"],
    }
    if not win_state["maximized"] and win_state["x"] is not None and win_state["y"] is not None:
        win_kwargs["x"] = win_state["x"]
        win_kwargs["y"] = win_state["y"]
    window = webview.create_window(**win_kwargs)

    def _capture_and_save_win_state():
        try:
            import json as _json
            is_max = bool(win_state["maximized"])
            if sys.platform.startswith("win"):
                try:
                    from System.Windows.Forms import Application, FormWindowState
                    for form in list(Application.OpenForms):
                        if str(getattr(form, "Text", "")).startswith("SPECTRA"):
                            if form.WindowState != FormWindowState.Minimized:
                                is_max = (form.WindowState == FormWindowState.Maximized)
                            break
                except Exception:
                    pass
            win_state["maximized"] = is_max
            if not is_max:
                w = getattr(window, "width", None)
                h = getattr(window, "height", None)
                x = getattr(window, "x", None)
                y = getattr(window, "y", None)
                if isinstance(w, int) and w >= 640:
                    win_state["width"] = w
                if isinstance(h, int) and h >= 480:
                    win_state["height"] = h
                if isinstance(x, int) and -16384 <= x <= 32768:
                    win_state["x"] = x
                if isinstance(y, int) and -16384 <= y <= 32768:
                    win_state["y"] = y
            os.makedirs(os.path.dirname(win_state_path), exist_ok=True)
            tmp_win_state = f"{win_state_path}.tmp.{os.getpid()}"
            with open(tmp_win_state, "w", encoding="utf-8") as _f:
                _json.dump(win_state, _f, indent=2)
            os.replace(tmp_win_state, win_state_path)
        except Exception:
            pass

    restart_state = {"requested": False}
    updater_mod = None
    if not sys.platform.startswith("win"):
        try:
            import updater as _updater_mod
            updater_mod = _updater_mod

            def _request_pywebview_restart():
                restart_state["requested"] = True
                try:
                    window.destroy()
                except Exception:
                    pass

            updater_mod.register_linux_restart_handler(_request_pywebview_restart)
        except Exception:
            updater_mod = None

    def on_closed():
        _capture_and_save_win_state()
        try:
            if sys.platform.startswith("win"):
                from System.Windows.Forms import Application
                Application.ExitThread()
                Application.Exit()
        except Exception:
            pass
        shutdown_spectra_cleanly(httpd)
        if not restart_state["requested"]:
            os._exit(0)

    window.events.closed += on_closed

    def on_webview_started():
        """Ensures visible desktop window + applies official SPECTRA Prism Logo icon on Windows."""
        try:
            window.show()
        except Exception:
            pass

        if not sys.platform.startswith("win"):
            return

        def _ensure_window_visible_and_icon():
            icon_candidates = [
                os.path.join(PROJECT_DIR, "icon.ico"),
                os.path.join(PROJECT_DIR, "web", "public", "favicon.ico"),
                os.path.join(PROJECT_DIR, "web", "dist", "favicon.ico"),
            ]
            icon_path = next((p for p in icon_candidates if os.path.isfile(p)), None)

            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.SendMessageW.restype = ctypes.c_ssize_t
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.ShowWindow.restype = wintypes.BOOL
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.IsIconic.restype = wintypes.BOOL
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.restype = wintypes.BOOL
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetWindowTextW.restype = ctypes.c_int
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user32.GetWindowThreadProcessId.restype = wintypes.DWORD
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            user32.SetForegroundWindow.restype = wintypes.BOOL

            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1
            SW_SHOWNORMAL = 1
            SW_SHOW = 5
            SW_RESTORE = 9

            h_big = user32.LoadImageW(None, icon_path, IMAGE_ICON, 48, 48, LR_LOADFROMFILE) if icon_path else None
            h_small = user32.LoadImageW(None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE) if icon_path else None
            pid = os.getpid()
            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            for delay in (0.15, 0.5, 1.2):
                time.sleep(delay)
                main_hwnds = set()

                # Method 1: WinForms / pythonnet Form visibility + Icon assignment ONLY for main SPECTRA form
                try:
                    import clr  # noqa: F401
                    from System import Action
                    from System.Windows.Forms import Application, FormWindowState
                    from System.Drawing import Icon

                    sys_icon = Icon(icon_path) if icon_path else None
                    for form in list(Application.OpenForms):
                        form_title = str(getattr(form, "Text", "") or "")
                        if not form_title.startswith("SPECTRA"):
                            continue
                        try:
                            main_hwnds.add(int(form.Handle.ToInt64()))
                        except Exception:
                            pass

                        def _sync_form(f=form, ic=sys_icon):
                            try:
                                if ic is not None:
                                    f.Icon = ic
                                if f.WindowState == FormWindowState.Minimized:
                                    f.WindowState = FormWindowState.Normal
                                if not f.Visible:
                                    f.Visible = True
                                    f.Show()
                                    f.Activate()
                            except Exception:
                                pass

                        try:
                            if getattr(form, "InvokeRequired", False):
                                form.Invoke(Action(_sync_form))
                            else:
                                _sync_form()
                        except Exception:
                            pass
                except Exception:
                    pass

                # Method 2: Native Win32 ShowWindow + WM_SETICON strictly on SPECTRA's main window
                # NEVER touch hidden helper windows such as "GDI+ Window" or ".NET-BroadcastEventWindow".
                try:
                    def _enum_win_cb(hwnd, _):
                        lp_pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
                        if lp_pid.value == pid:
                            t_len = user32.GetWindowTextLengthW(hwnd)
                            title = ""
                            if t_len > 0:
                                buf = ctypes.create_unicode_buffer(t_len + 1)
                                user32.GetWindowTextW(hwnd, buf, t_len + 1)
                                title = buf.value or ""
                            is_spectra_main = (hwnd in main_hwnds) or title.startswith("SPECTRA")
                            if is_spectra_main:
                                if user32.IsIconic(hwnd):
                                    user32.ShowWindow(hwnd, SW_RESTORE)
                                elif not user32.IsWindowVisible(hwnd):
                                    user32.ShowWindow(hwnd, SW_SHOWNORMAL)
                                    user32.ShowWindow(hwnd, SW_SHOW)
                                    user32.SetForegroundWindow(hwnd)
                                if h_big:
                                    user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
                                if h_small:
                                    user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
                        return True

                    user32.EnumWindows(EnumWindowsProc(_enum_win_cb), 0)
                except Exception:
                    pass

        icon_thread = threading.Thread(target=_ensure_window_visible_and_icon, daemon=True, name="SpectraIconBinder")
        icon_thread.start()

    storage_dir = None
    if sys.platform.startswith("win"):
        try:
            base_dir = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            storage_dir = os.path.join(base_dir, "SPECTRA", "WebView2")
            os.makedirs(storage_dir, exist_ok=True)
        except Exception:
            storage_dir = None

    webview_started = {"ran": False}
    try:
        def _on_started_wrapper():
            webview_started["ran"] = True
            on_webview_started()

        if sys.platform.startswith("win"):
            try:
                webview.start(
                    _on_started_wrapper,
                    gui="edgechromium",
                    debug=False,
                    private_mode=False if storage_dir else True,
                    storage_path=storage_dir,
                )
            except Exception as edge_err:
                print(f"[!] pywebview edgechromium start failed: {edge_err}", file=sys.stderr)
                if not webview_started["ran"]:
                    webview.start(
                        _on_started_wrapper,
                        debug=False,
                        private_mode=False if storage_dir else True,
                        storage_path=storage_dir,
                    )
        else:
            webview.start(debug=False)
        shutdown_spectra_cleanly(httpd)
        if updater_mod is not None:
            try:
                updater_mod.register_linux_restart_handler(None)
            except Exception:
                pass
        if restart_state["requested"] and updater_mod is not None:
            updater_mod.relaunch_current_process(preferred_port=port)
        os._exit(0)
        return True
    except Exception as pv_err:
        if updater_mod is not None:
            try:
                updater_mod.register_linux_restart_handler(None)
            except Exception:
                pass
        print(f"[!] pywebview launch failed: {pv_err}", file=sys.stderr)
        return False


# ============================================================================
# Backend C: Chromeless Standalone App Window (msedge / chrome / chromium)
# ============================================================================
def find_chromeless_browser() -> Optional[str]:
    """Finds an available Chromium-based browser supporting --app mode."""
    if sys.platform.startswith("win"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            # Local bundled portable Chromium / browser if present
            os.path.join(script_dir, "runtimes", "chromium", "chrome.exe"),
            os.path.join(script_dir, "chromium", "chrome.exe"),
            os.path.join(script_dir, "bin", "chromium", "chrome.exe"),
            # Microsoft Edge
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
            shutil.which("msedge"),
            # Google Chrome
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            shutil.which("chrome"),
            shutil.which("chromium"),
            # Brave Browser
            os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            shutil.which("brave"),
            # Vivaldi Browser
            os.path.expandvars(r"%LocalAppData%\Vivaldi\Application\vivaldi.exe"),
            os.path.expandvars(r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe"),
            shutil.which("vivaldi"),
            # Opera Browser
            os.path.expandvars(r"%LocalAppData%\Programs\Opera\launcher.exe"),
            os.path.expandvars(r"%ProgramFiles%\Opera\launcher.exe"),
            shutil.which("opera"),
        ]
    else:
        candidates = [
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("microsoft-edge"),
            shutil.which("brave"),
            shutil.which("brave-browser"),
        ]

    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def try_launch_win32_native_window(url: str, port: int, httpd, build_str: str) -> bool:
    """
    Attempts to launch a native Win32 desktop application window without tabs
    or address bars, embedding the UI with full desktop integration.
    Falls back gracefully to chromeless browser if native windowing is unavailable.
    """
    if not sys.platform.startswith("win"):
        return False

    # 1. Try native pywebview window if module is installed in Python runtime
    if try_launch_pywebview(url, port, httpd, build_str):
        return True

    # 2. Launch chromeless standalone app window with broker handoff & heartbeat watchdog
    browser_bin = find_chromeless_browser()
    if browser_bin:
        run_chromeless_app_window(browser_bin, f"{url}/?v={build_str}", port, httpd)
        return True

    return False


def run_chromeless_app_window(browser_bin: str, url: str, port: int, httpd) -> None:
    """
    Runs the chromeless standalone app window with a persistent user-data-dir
    so localStorage & browser state survive restarts, and monitors process
    lifecycle and heartbeat watchdog.
    Hardened for Windows broker process handoff (msedge.exe / chrome.exe).
    """
    geom = get_host_monitor_geometry()
    if sys.platform.startswith("win"):
        base_cfg = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        profile_dir = os.path.join(base_cfg, "SPECTRA", "browser_profile")
    else:
        base_cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        profile_dir = os.path.join(base_cfg, "spectra", "browser_profile")
    os.makedirs(profile_dir, exist_ok=True)
    for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock_path = os.path.join(profile_dir, lock_name)
        if os.path.lexists(lock_path):
            try:
                os.remove(lock_path)
            except OSError:
                pass

    cmd = [
        browser_bin,
        f"--user-data-dir={profile_dir}",
        f"--app={url}",
        f"--window-size={geom['win_w']},{geom['win_h']}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-fre",
        "--disable-background-mode",
        "--disable-extensions",
        "--disable-plugins",
        "--disable-sync",
        "--disable-translate",
        "--disable-features=Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider",
    ]

    # Explicitly configure STARTUPINFO so the browser window is never hidden by inherited SW_HIDE
    startupinfo = None
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 1  # SW_SHOWNORMAL

    start_time = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            startupinfo=startupinfo,
            creationflags=0
        )
    except Exception as e:
        print(f"[!] Failed to launch chromeless browser ({browser_bin}): {e}")
        import webbrowser
        webbrowser.open(url)
        return

    restart_state = {"requested": False}
    updater_mod = None
    if not sys.platform.startswith("win"):
        try:
            import updater as _updater_mod
            updater_mod = _updater_mod

            def _request_chromeless_restart():
                restart_state["requested"] = True
                try:
                    proc.terminate()
                except Exception:
                    pass

            updater_mod.register_linux_restart_handler(_request_chromeless_restart)
        except Exception:
            updater_mod = None

    def cleanup_and_exit():
        if updater_mod is not None:
            try:
                updater_mod.register_linux_restart_handler(None)
            except Exception:
                pass
        shutdown_spectra_cleanly(httpd)
        if restart_state["requested"] and updater_mod is not None:
            updater_mod.relaunch_current_process(preferred_port=port)
        os._exit(0)

    import web_server
    web_server._last_heartbeat_time = time.time()

    # On Windows, Edge/Chrome often hands off the window to a background broker
    # process and the spawned process exits in < 3.0 seconds with code 0.
    # When this happens, DO NOT KILL THE SERVER! Stay alive driven by the frontend heartbeat.
    try:
        proc.wait(timeout=3.0)
        # Process exited within 3.0 seconds -> broker handoff!
        # Enter heartbeat-driven event loop
        initial_grace = 30.0  # 30 seconds grace period for page load
        has_received_heartbeat = False
        fallback_opened = False

        while True:
            if restart_state["requested"]:
                break
            time.sleep(1.0)
            if restart_state["requested"]:
                break
            now = time.time()
            elapsed_total = now - start_time
            last_hb = getattr(web_server, "_last_heartbeat_time", start_time)
            gap = now - last_hb

            if gap < 3.0 and elapsed_total > 1.0:
                has_received_heartbeat = True

            if not has_received_heartbeat:
                # If 10 seconds elapsed with no heartbeat from chromeless window, trigger default browser fallback!
                if elapsed_total > 10.0 and not fallback_opened:
                    fallback_opened = True
                    try:
                        import webbrowser
                        webbrowser.open(url)
                    except Exception:
                        pass

                if elapsed_total > initial_grace:
                    print("[!] No frontend heartbeat received within grace period. Terminating.")
                    break
            else:
                hw_busy = getattr(web_server, "_active_hw_ops", 0) > 0
                if not hw_busy and gap > 18.0:
                    # Frontend window was closed without clean unload beacon
                    break

        cleanup_and_exit()
        return
    except subprocess.TimeoutExpired:
        # Process remained alive as direct child
        pass

    # Process is running as direct child; monitor process exit and heartbeats concurrently
    def watchdog():
        time.sleep(25.0)  # Initial grace period for page load
        while proc.poll() is None:
            if restart_state["requested"]:
                break
            time.sleep(1.5)
            if restart_state["requested"]:
                break
            if getattr(web_server, "_active_hw_ops", 0) > 0:
                continue
            if time.time() - getattr(web_server, "_last_heartbeat_time", time.time()) > 18.0:
                break
        try:
            proc.terminate()
        except Exception:
            pass
        cleanup_and_exit()

    t = threading.Thread(target=watchdog, daemon=True, name="SpectraHeartbeatWatchdog")
    t.start()

    try:
        proc.wait()
    except (KeyboardInterrupt, SystemExit):
        try:
            proc.terminate()
        except Exception:
            pass

    cleanup_and_exit()


# ============================================================================
# Main Dispatcher
# ============================================================================
def main():
    args = sys.argv[1:]

    # 1. Legacy GTK mode explicit request
    if "--legacy-gtk" in args or "--gtk" in args:
        if "--legacy-gtk" in sys.argv:
            sys.argv.remove("--legacy-gtk")
        if "--gtk" in sys.argv:
            sys.argv.remove("--gtk")
        import gui
        gui.main()
        return

    # 2. Browser tab mode explicit request
    if "--browser" in args:
        sys.argv.remove("--browser")
        import web_server
        web_server.main(auto_open=True)
        return

    # Filter out app/web launcher flags
    app_flags = {"--app", "--ui", "--web", "--gui", "--open"}
    filtered_args = [a for a in args if a not in app_flags]

    # 3. CLI Mode: If any other flags remain, dispatch to CLI
    if filtered_args:
        import cli
        cli.main()
        return

    # 4. Standalone Desktop App Mode
    # Prefer native Rust WebView shell (spectra-shell) when available,
    # unless explicitly overridden or already running inside spectra-shell.
    if (
        "--web" not in args
        and os.environ.get("SPECTRA_NATIVE_SHELL") != "1"
        and os.environ.get("SPECTRA_PYTHON_SHELL") != "1"
    ):
        shell_name = "spectra-shell.exe" if sys.platform.startswith("win") else "spectra-shell"
        shell_candidates = [
            os.path.join(PROJECT_DIR, shell_name),
            os.path.join(PROJECT_DIR, "target", "release", shell_name),
        ]
        for shell_bin in shell_candidates:
            if os.path.isfile(shell_bin):
                try:
                    import subprocess
                    proc = subprocess.run([shell_bin, "--root", PROJECT_DIR], check=False)
                    sys.exit(proc.returncode)
                except Exception as e:
                    print(f"[!] Native spectra-shell launch failed ({e}), falling back to Python shell.")
                    break

    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SPECTRA.Diagnostics.Suite")
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass

    httpd, port, url = start_inprocess_server()

    # Try Backend A: Linux Native GTK3 + WebKit2
    if sys.platform.startswith("linux"):
        if try_launch_gtk_webkit(url, port, httpd, __build__):
            return

    # Try Backend B: Windows Native Desktop Window / pywebview / Chromeless App Mode
    if sys.platform.startswith("win"):
        if try_launch_win32_native_window(url, port, httpd, __build__):
            return

    # Try Backend C: Cross-Platform pywebview
    if try_launch_pywebview(url, port, httpd, __build__):
        return

    # Try Backend D: Chromeless Standalone App Window (msedge / chrome / chromium)
    browser_bin = find_chromeless_browser()
    if browser_bin:
        run_chromeless_app_window(browser_bin, f"{url}/?v={__build__}", port, httpd)
        return

    # Fallback to default browser
    import webbrowser
    webbrowser.open(f"{url}/?v={__build__}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        shutdown_spectra_cleanly(httpd)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        crash_log = os.path.join(_get_private_log_dir(), "spectra_crash.log")
        try:
            _RotatingLogStream(crash_log).write(
                f"\n=======================================================\n"
                f"SPECTRA STARTUP CRASH — {time.ctime()}\n"
                f"=======================================================\n"
                f"{err_msg}"
            )
        except Exception:
            pass

        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"SPECTRA failed to start:\n\n{e}\n\nCrash log written to:\n{crash_log}",
                    "SPECTRA — Startup Error",
                    0x10  # MB_ICONERROR
                )
            except Exception:
                pass
        sys.exit(1)
