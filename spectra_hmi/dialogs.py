#!/usr/bin/env python3
"""SPECTRA HMI local firmware discovery and cross-platform native file chooser dialogs."""

import os
import sys
import re
import struct
import shutil
import subprocess
from typing import Dict, List, Tuple, Optional, Any

from spectra_hmi.elf_tools import DEFAULT_KALERM_DIR, ELF_MAGIC, DialogUnavailableError


class HmiDialogsMixin:
    """Local firmware auto-discovery and Win32/GTK/Zen/Tk file dialogs."""

    @staticmethod
    def discover_local_targets(search_dirs: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Dynamically discover coffee machine firmware targets (ELF32 LVGL, Android APK, and Cortex-M CTR BIN)
        present on the host system without hardcoding user home paths.
        """
        if not search_dirs:
            downloads = os.path.expanduser("~/Downloads")
            search_dirs = [downloads] if os.path.isdir(downloads) else []
        elif isinstance(search_dirs, str):
            search_dirs = [search_dirs]

        found: List[Dict[str, Any]] = []
        seen_paths: set = set()

        def inspect_file(fpath: str) -> Optional[Dict[str, Any]]:
            if fpath in seen_paths or not os.path.isfile(fpath):
                return None
            try:
                sz = os.path.getsize(fpath)
            except Exception:
                return None
            if sz < 16 or sz > 500 * 1024 * 1024:
                return None

            try:
                with open(fpath, "rb") as f:
                    head = f.read(52)
            except Exception:
                return None

            fname = os.path.basename(fpath)
            try:
                mtime = os.path.getmtime(fpath)
            except Exception:
                mtime = 0

            # 1. ELF32 ARM binary
            if head.startswith(ELF_MAGIC):
                if ".so" in fname or fname.startswith("lib") or fname.endswith(".AppImage"):
                    return None
                if len(head) >= 20:
                    ei_class = head[4]
                    e_machine = struct.unpack("<H", head[18:20])[0]
                    if ei_class == 1 and e_machine == 40:
                        stem = fname[:24]
                        return {
                            "path": fpath,
                            "name": fname,
                            "label": f"[ELF] {stem}",
                            "container_type": "ELF32_LVGL",
                            "size": sz,
                            "mtime": mtime,
                        }

            # 2. Android APK
            elif head.startswith(b"PK\x03\x04") and fname.endswith(".apk"):
                try:
                    import zipfile
                    with zipfile.ZipFile(fpath, "r") as zf:
                        if "resources.arsc" in zf.namelist():
                            stem = fname.replace(".apk", "")[:24]
                            return {
                                "path": fpath,
                                "name": fname,
                                "label": f"[APK] {stem}",
                                "container_type": "ANDROID_APK",
                                "size": sz,
                                "mtime": mtime,
                            }
                except Exception:
                    pass

            # 3. Cortex-M CTR BIN
            elif len(head) >= 8 and (fname.endswith(".bin") or "ctr" in fname.lower()):
                sp, reset = struct.unpack("<II", head[:8])
                if (0x20000000 <= sp <= 0x24100000) and (0x08000001 <= reset <= 0x081FFFFF) and (reset & 1 == 1):
                    stem = fname.replace(".bin", "")[:24]
                    return {
                        "path": fpath,
                        "name": fname,
                        "label": f"[BIN] {stem}",
                        "container_type": "MCU_CTR_BIN",
                        "size": sz,
                        "mtime": mtime,
                    }

            return None

        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for root, dirs, files in os.walk(d):
                rel = os.path.relpath(root, d)
                depth = len(rel.split(os.sep)) if rel != "." else 0
                if depth > 2:
                    continue

                # Check if this folder itself is a firmware bundle (e.g. contains ELF binary or APK)
                bundle_cands = []
                for f in files:
                    if f.endswith(".apk"):
                        bundle_cands.append((f, "ANDROID_APK"))
                    elif not (f.endswith(".so") or f.endswith(".o") or f.endswith(".a") or f.endswith(".debug") or f.endswith(".pem") or f.endswith(".AppImage")):
                        try:
                            with open(os.path.join(root, f), "rb") as ef:
                                if ef.read(4) == ELF_MAGIC:
                                    bundle_cands.append((f, "ELF32_LVGL"))
                        except Exception:
                            pass

                if bundle_cands and depth > 0:
                    dname = os.path.basename(root)
                    primary, ctype = bundle_cands[0]
                    tag = "[APK BUNDLE]" if ctype == "ANDROID_APK" else "[ELF BUNDLE]"
                    found.append({
                        "path": root,
                        "name": dname,
                        "label": f"{tag} {dname[:22]}",
                        "container_type": ctype,
                        "size": os.path.getsize(os.path.join(root, primary)),
                        "mtime": os.path.getmtime(root),
                    })
                    seen_paths.add(root)

                for f in files:
                    fpath = os.path.join(root, f)
                    info = inspect_file(fpath)
                    if info:
                        found.append(info)
                        seen_paths.add(fpath)

        found.sort(key=lambda x: x["mtime"], reverse=True)
        return found

    @staticmethod
    def _find_win32_spectra_owner_hwnd() -> Optional[int]:
        """Locate the active top-level SPECTRA HWND on Windows so dialogs stay owned & on top."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            found_hwnds: List[int] = []
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _enum_cb(hwnd, _lparam):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length <= 0:
                        return True
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value.startswith("SPECTRA"):
                        found_hwnds.append(int(hwnd))
                        return False
                except Exception:
                    pass
                return True

            cb = WNDENUMPROC(_enum_cb)
            user32.EnumWindows(cb, 0)
            if found_hwnds:
                return found_hwnds[0]

            fg = user32.GetForegroundWindow()
            return int(fg) if fg else None
        except Exception:
            return None

    @staticmethod
    def _focus_win32_window(hwnd: int) -> None:
        """Bring a Win32 file dialog HWND in front of the SPECTRA host window and focus it."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            parent = user32.GetParent(hwnd)
            target = parent if parent else hwnd
            if not target:
                return

            try:
                user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass

            fg = user32.GetForegroundWindow()
            cur_tid = kernel32.GetCurrentThreadId()
            fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
            attached = False
            if fg_tid and fg_tid != cur_tid:
                attached = bool(user32.AttachThreadInput(fg_tid, cur_tid, True))
            try:
                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                SWP_SHOWWINDOW = 0x0040
                HWND_TOPMOST = ctypes.c_void_p(-1)
                HWND_NOTOPMOST = ctypes.c_void_p(-2)
                user32.SetWindowPos(target, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                user32.SetWindowPos(target, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                user32.BringWindowToTop(target)
                user32.SetForegroundWindow(target)
                user32.SetActiveWindow(target)
            finally:
                if attached:
                    user32.AttachThreadInput(fg_tid, cur_tid, False)
        except Exception:
            pass

    @classmethod
    def _win32_comdlg_dialog(
        cls,
        *,
        is_save: bool,
        filter_str: str,
        initial_dir: str,
        title: str,
        flags: int,
        default_filename: str = "",
        default_ext: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """Run native Win32 GetOpenFileNameW / GetSaveFileNameW owned and focused above SPECTRA."""
        import ctypes
        from ctypes import wintypes

        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize", wintypes.DWORD),
                ("hwndOwner", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR),
                ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD),
                ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR),
                ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR),
                ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD),
                ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM),
                ("lpfnHook", ctypes.c_void_p),
                ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", wintypes.LPVOID),
                ("dwReserved", wintypes.DWORD),
                ("FlagsEx", wintypes.DWORD),
            ]

        class _NMHDR(ctypes.Structure):
            _fields_ = [
                ("hwndFrom", wintypes.HWND),
                ("idFrom", ctypes.c_size_t),
                ("code", wintypes.UINT),
            ]

        OFN_ENABLEHOOK = 0x00000020
        WM_INITDIALOG = 0x0110
        WM_NOTIFY = 0x004E
        CDN_INITDONE = 0xFFFFFDA7  # -601 unsigned 32-bit
        LPOFNHOOKPROC = getattr(
            ctypes,
            "WINFUNCTYPE",
            ctypes.CFUNCTYPE,
        )(ctypes.c_size_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        def _hook_proc(hdlg, msg, _wparam, lparam):
            try:
                if msg == WM_INITDIALOG:
                    cls._focus_win32_window(hdlg)
                elif msg == WM_NOTIFY and lparam:
                    nm = ctypes.cast(lparam, ctypes.POINTER(_NMHDR)).contents
                    if nm.code == CDN_INITDONE:
                        cls._focus_win32_window(hdlg)
            except Exception:
                pass
            return 0

        hook_cb = LPOFNHOOKPROC(_hook_proc)
        owner_hwnd = cls._find_win32_spectra_owner_hwnd()

        buf_size = 4096
        buf = ctypes.create_unicode_buffer(default_filename, buf_size)

        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.hwndOwner = owner_hwnd
        ofn.lpstrFilter = filter_str
        ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
        ofn.nMaxFile = buf_size
        ofn.lpstrInitialDir = initial_dir
        ofn.lpstrTitle = title
        ofn.lpstrDefExt = default_ext
        ofn.lpfnHook = ctypes.cast(hook_cb, ctypes.c_void_p).value
        ofn.Flags = flags | OFN_ENABLEHOOK

        dialog_fn = ctypes.windll.comdlg32.GetSaveFileNameW if is_save else ctypes.windll.comdlg32.GetOpenFileNameW
        if dialog_fn(ctypes.byref(ofn)):
            chosen = buf.value
            return ("OK", chosen) if chosen else ("CANCEL", None)
        ext_err = ctypes.windll.comdlg32.CommDlgExtendedError()
        if ext_err == 0:
            return ("CANCEL", None)
        return ("FALLBACK", None)

    @staticmethod
    def prompt_file_browser(initial_dir: Optional[str] = None) -> Optional[str]:
        """
        Open a native OS file chooser dialog to pick a firmware target or update folder.
        Supports Linux (GTK3 PyGObject native dialog, zenity, kdialog, yad, qarma, tkinter) and Windows (Win32, PowerShell, tkinter).
        """
        if not initial_dir or not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~/Downloads")

        # Linux
        if sys.platform.startswith("linux"):
            # 1. Native GTK3 FileChooserDialog via isolated Python subprocess (works on Omarchy/Hyprland/Wayland/X11 without zenity or tk)
            try:
                gtk_script = (
                    "import os, sys\n"
                    "os.environ.setdefault('GTK_THEME', 'Adwaita:dark')\n"
                    "try:\n"
                    "    import gi\n"
                    "    gi.require_version('Gtk', '3.0')\n"
                    "    from gi.repository import Gtk\n"
                    "    if not Gtk.init_check()[0]:\n"
                    "        sys.exit(3)\n"
                    "except Exception:\n"
                    "    sys.exit(3)\n"
                    "settings = Gtk.Settings.get_default()\n"
                    "if settings:\n"
                    "    try: settings.set_property('gtk-application-prefer-dark-theme', True)\n"
                    "    except Exception: pass\n"
                    "dlg = Gtk.FileChooserDialog(\n"
                    "    title='Select Coffee Machine Firmware Target (.apk, .bin, ELF, or Folder)',\n"
                    "    parent=None,\n"
                    "    action=Gtk.FileChooserAction.OPEN,\n"
                    ")\n"
                    "dlg.add_buttons(\n"
                    "    '_Cancel', Gtk.ResponseType.CANCEL,\n"
                    "    'Select Current _Folder', Gtk.ResponseType.APPLY,\n"
                    "    '_Open File / Folder', Gtk.ResponseType.OK,\n"
                    ")\n"
                    "dlg.set_default_size(860, 560)\n"
                    "dlg.set_keep_above(True)\n"
                    "init_dir = sys.argv[1] if len(sys.argv) > 1 else ''\n"
                    "if init_dir and os.path.isdir(init_dir):\n"
                    "    dlg.set_current_folder(init_dir)\n"
                    "resp = dlg.run()\n"
                    "chosen = ''\n"
                    "if resp == Gtk.ResponseType.OK:\n"
                    "    chosen = dlg.get_filename() or dlg.get_current_folder() or ''\n"
                    "elif resp == Gtk.ResponseType.APPLY:\n"
                    "    chosen = dlg.get_current_folder() or dlg.get_filename() or ''\n"
                    "dlg.destroy()\n"
                    "while Gtk.events_pending():\n"
                    "    Gtk.main_iteration()\n"
                    "if chosen:\n"
                    "    print(chosen)\n"
                    "    sys.exit(0)\n"
                    "# User cancelled or closed dialog without selection\n"
                    "sys.exit(2)\n"
                )
                res = subprocess.run(
                    [sys.executable, "-c", gtk_script, initial_dir],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=180,
                )
                if res.returncode == 0:
                    path = res.stdout.strip()
                    if path and os.path.exists(path):
                        return path
                elif res.returncode == 2:
                    # User explicitly clicked Cancel / closed the GTK3 dialog
                    return None
            except Exception:
                pass

            # 2. Falls through to zenity, yad, qarma, kdialog
            for tool in ("zenity", "yad", "qarma"):
                if shutil.which(tool):
                    try:
                        cmd = [
                            tool, "--file-selection",
                            f"--filename={initial_dir}/",
                            "--title=Select Coffee Machine Firmware Target (.apk, .bin, ELF, or folder)",
                        ]
                        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                        if res.returncode == 0:
                            path = res.stdout.strip()
                            if path and os.path.exists(path):
                                return path
                        elif res.returncode == 1:
                            return None
                    except Exception:
                        pass

            if shutil.which("kdialog"):
                try:
                    cmd = ["kdialog", "--getopenfilename", initial_dir]
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                    if res.returncode == 0:
                        path = res.stdout.strip()
                        if path and os.path.exists(path):
                            return path
                    elif res.returncode == 1:
                        return None
                except Exception:
                    pass

        # Windows
        if sys.platform.startswith("win"):
            # 1. Native Win32 GetOpenFileNameW via ctypes (owned & focused above SPECTRA)
            try:
                flags = 0x00080000 | 0x00000800 | 0x00000008  # OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
                filter_str = (
                    "All Firmware Targets (*.apk;*.bin;*.elf;*.so)\0*.apk;*.bin;*.elf;*.so\0"
                    "All Files (*.*)\0*.*\0\0"
                )
                from spectra_hmi.inspector import KalermHmiInspector
                status, chosen = KalermHmiInspector._win32_comdlg_dialog(
                    is_save=False,
                    filter_str=filter_str,
                    initial_dir=initial_dir,
                    title="Select Coffee Machine Firmware Target (.apk, .bin, ELF, or folder)",
                    flags=flags,
                )
                if status == "OK" and chosen and os.path.exists(chosen):
                    return chosen
                if status == "CANCEL":
                    return None
            except Exception:
                pass

            # 2. PowerShell OpenFileDialog fallback (topmost Form owner keeps focus above SPECTRA; env-vars avoid injection)
            try:
                ps_script = (
                    "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
                    "$owner = New-Object System.Windows.Forms.Form; $owner.TopMost = $true; "
                    "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                    "$f.InitialDirectory = $env:SPECTRA_DLG_INIT_DIR; "
                    "$f.Filter = $env:SPECTRA_DLG_FILTER; "
                    "$r = $f.ShowDialog($owner); $owner.Dispose(); "
                    "if($r -eq [System.Windows.Forms.DialogResult]::OK){ Write-Output $f.FileName }"
                )
                ps_env = dict(os.environ)
                ps_env["SPECTRA_DLG_INIT_DIR"] = str(initial_dir or "")
                ps_env["SPECTRA_DLG_FILTER"] = "All Firmware Targets (*.apk;*.bin;*)|*.apk;*.bin;*|All Files (*.*)|*.*"
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                    env=ps_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=120,
                    creationflags=0x08000000 if sys.platform.startswith("win") else 0,
                )
                if res.returncode == 0 and res.stdout.strip():
                    path = res.stdout.strip()
                    if os.path.exists(path):
                        return path
            except Exception:
                pass

        # Fallback to tkinter
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
                root.lift()
                root.focus_force()
            except Exception:
                pass
            path = filedialog.askopenfilename(initialdir=initial_dir, title="Select Coffee Machine Firmware Target", parent=root)
            root.destroy()
            if path and os.path.exists(path):
                return path
        except Exception:
            pass

        return None

    @staticmethod
    def prompt_save_file_dialog(
        default_filename: str,
        initial_dir: Optional[str] = None,
        title: str = "Save Diagnostic Export",
        raise_if_unavailable: bool = True
    ) -> Optional[str]:
        """
        Open a native OS 'Save As' file chooser dialog allowing the user to select
        the export destination folder and file name.
        Supports:
        - Windows: Native Win32 comdlg32.GetSaveFileNameW (OPENFILENAMEW) with
          OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_EXPLORER, returning None on cancel;
          falls through to PowerShell -STA SaveFileDialog, and tkinter.
        - Linux: Isolated GTK3 FileChooserDialog(action=SAVE), falling through to
          zenity, kdialog, yad, qarma, and tkinter.
        Returns: Absolute destination file path chosen by user, or None if cancelled.
        Raises: DialogUnavailableError if no dialog provider is available and raise_if_unavailable=True.
        """
        if not initial_dir or not os.path.isdir(initial_dir):
            for cand in [os.path.expanduser("~/Downloads"), os.path.expanduser("~/Documents"), os.path.expanduser("~")]:
                if os.path.isdir(cand):
                    initial_dir = cand
                    break
            else:
                initial_dir = os.getcwd()

        ext = os.path.splitext(default_filename)[1].lstrip(".").lower()
        filter_map = {
            "txt": ("Text Report (*.txt)\0*.txt\0All Files (*.*)\0*.*\0\0", "Text Report (*.txt)|*.txt|All Files (*.*)|*.*"),
            "csv": ("CSV Spreadsheet (*.csv)\0*.csv\0All Files (*.*)\0*.*\0\0", "CSV Spreadsheet (*.csv)|*.csv|All Files (*.*)|*.*"),
            "json": ("JSON Document (*.json)\0*.json\0All Files (*.*)\0*.*\0\0", "JSON Document (*.json)|*.json|All Files (*.*)|*.*"),
            "md": ("Markdown Report (*.md)\0*.md\0All Files (*.*)\0*.*\0\0", "Markdown Report (*.md)|*.md|All Files (*.*)|*.*"),
            "html": ("HTML Report (*.html)\0*.html\0All Files (*.*)\0*.*\0\0", "HTML Report (*.html)|*.html|All Files (*.*)|*.*"),
            "pdf": ("PDF Document (*.pdf)\0*.pdf\0All Files (*.*)\0*.*\0\0", "PDF Document (*.pdf)|*.pdf|All Files (*.*)|*.*"),
        }
        win_filter, ps_filter = filter_map.get(ext, ("All Files (*.*)\0*.*\0\0", "All Files (*.*)|*.*"))

        # Linux
        if sys.platform.startswith("linux"):
            # 1. Native GTK3 FileChooserDialog via isolated Python subprocess
            try:
                gtk_script = (
                    "import os, sys\n"
                    "os.environ.setdefault('GTK_THEME', 'Adwaita:dark')\n"
                    "try:\n"
                    "    import gi\n"
                    "    gi.require_version('Gtk', '3.0')\n"
                    "    from gi.repository import Gtk\n"
                    "    if not Gtk.init_check()[0]:\n"
                    "        sys.exit(3)\n"
                    "except Exception:\n"
                    "    sys.exit(3)\n"
                    "settings = Gtk.Settings.get_default()\n"
                    "if settings:\n"
                    "    try: settings.set_property('gtk-application-prefer-dark-theme', True)\n"
                    "    except Exception: pass\n"
                    "title = sys.argv[1]\n"
                    "def_name = sys.argv[2]\n"
                    "init_dir = sys.argv[3] if len(sys.argv) > 3 else ''\n"
                    "dlg = Gtk.FileChooserDialog(\n"
                    "    title=title,\n"
                    "    parent=None,\n"
                    "    action=Gtk.FileChooserAction.SAVE,\n"
                    ")\n"
                    "dlg.add_buttons(\n"
                    "    '_Cancel', Gtk.ResponseType.CANCEL,\n"
                    "    '_Save', Gtk.ResponseType.OK,\n"
                    ")\n"
                    "dlg.set_do_overwrite_confirmation(True)\n"
                    "if init_dir and os.path.isdir(init_dir):\n"
                    "    dlg.set_current_folder(init_dir)\n"
                    "dlg.set_current_name(def_name)\n"
                    "dlg.set_default_size(860, 560)\n"
                    "dlg.set_keep_above(True)\n"
                    "resp = dlg.run()\n"
                    "chosen = dlg.get_filename() if resp == Gtk.ResponseType.OK else ''\n"
                    "dlg.destroy()\n"
                    "while Gtk.events_pending():\n"
                    "    Gtk.main_iteration()\n"
                    "if chosen:\n"
                    "    print(chosen)\n"
                    "    sys.exit(0)\n"
                    "sys.exit(2)\n"
                )
                res = subprocess.run(
                    [sys.executable, "-c", gtk_script, title, default_filename, initial_dir],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=180,
                )
                if res.returncode == 0:
                    path = res.stdout.strip()
                    if path:
                        return os.path.abspath(path)
                elif res.returncode == 2:
                    return None
            except Exception:
                pass

            # 2. Zenity, Yad, Qarma
            for tool in ("zenity", "yad", "qarma"):
                if shutil.which(tool):
                    try:
                        cmd = [
                            tool, "--file-selection", "--save", "--confirm-overwrite",
                            f"--filename={os.path.join(initial_dir, default_filename)}",
                            f"--title={title}",
                        ]
                        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                        if res.returncode == 0:
                            path = res.stdout.strip()
                            if path:
                                return os.path.abspath(path)
                        elif res.returncode == 1:
                            return None
                    except Exception:
                        pass

            # 3. Kdialog
            if shutil.which("kdialog"):
                try:
                    cmd = ["kdialog", "--getsavefilename", os.path.join(initial_dir, default_filename)]
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
                    if res.returncode == 0:
                        path = res.stdout.strip()
                        if path:
                            return os.path.abspath(path)
                    elif res.returncode == 1:
                        return None
                except Exception:
                    pass

        # Windows
        elif sys.platform.startswith("win"):
            # 1. Native Win32 comdlg32.GetSaveFileNameW (owned & focused above SPECTRA)
            try:
                flags = 0x00080000 | 0x00000800 | 0x00000002 | 0x00000008  # OFN_EXPLORER | PATHMUSTEXIST | OVERWRITEPROMPT | NOCHANGEDIR
                from spectra_hmi.inspector import KalermHmiInspector
                status, chosen = KalermHmiInspector._win32_comdlg_dialog(
                    is_save=True,
                    filter_str=win_filter,
                    initial_dir=initial_dir,
                    title=title,
                    flags=flags,
                    default_filename=default_filename,
                    default_ext=ext if ext else None,
                )
                if status == "OK" and chosen:
                    return os.path.abspath(chosen)
                if status == "CANCEL":
                    return None
            except Exception:
                pass

            # 2. PowerShell SaveFileDialog fallback (topmost Form owner keeps focus above SPECTRA; env-vars avoid injection)
            try:
                ps_script = (
                    "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
                    "$owner = New-Object System.Windows.Forms.Form; $owner.TopMost = $true; "
                    "$f = New-Object System.Windows.Forms.SaveFileDialog; "
                    "$f.FileName = $env:SPECTRA_DLG_DEF_NAME; "
                    "$f.InitialDirectory = $env:SPECTRA_DLG_INIT_DIR; "
                    "$f.Filter = $env:SPECTRA_DLG_FILTER; "
                    "$f.Title = $env:SPECTRA_DLG_TITLE; "
                    "$f.OverwritePrompt = $true; "
                    "$r = $f.ShowDialog($owner); $owner.Dispose(); "
                    "if($r -eq [System.Windows.Forms.DialogResult]::OK){ Write-Output $f.FileName }"
                )
                ps_env = dict(os.environ)
                ps_env["SPECTRA_DLG_INIT_DIR"] = str(initial_dir or "")
                ps_env["SPECTRA_DLG_DEF_NAME"] = str(default_filename or "")
                ps_env["SPECTRA_DLG_FILTER"] = str(ps_filter or "")
                ps_env["SPECTRA_DLG_TITLE"] = str(title or "")
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                    env=ps_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=120,
                    creationflags=0x08000000 if sys.platform.startswith("win") else 0,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return os.path.abspath(res.stdout.strip())
                elif res.returncode == 0:
                    return None
            except Exception:
                pass

        # 4. Tkinter fallback
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
                root.lift()
                root.focus_force()
            except Exception:
                pass
            path = filedialog.asksaveasfilename(
                initialdir=initial_dir,
                initialfile=default_filename,
                title=title,
                defaultextension=f".{ext}" if ext else "",
                parent=root,
            )
            root.destroy()
            if path:
                return os.path.abspath(path)
            return None
        except Exception:
            pass

        if raise_if_unavailable:
            raise DialogUnavailableError("Native file dialog is unavailable on this system")
        return None

