#!/usr/bin/env python3
"""
SPECTRA Cross-Platform TLS Helper
==================================
Provides a verified SSLContext that works reliably inside embeddable Windows
Python distributions (which lack a default OpenSSL cert bundle) by combining:
  1. Bundled `certifi` CA bundle (`certifi.where()`), if installed
  2. Host OS default CA locations (`load_default_certs`)
  3. Windows CryptoAPI ROOT / CA stores (`ssl.enum_certificates`)
"""

import os
import ssl
import subprocess
from typing import Callable, Optional, Set
from urllib.parse import urlparse


def get_ssl_context() -> ssl.SSLContext:
    """Return a strict-verification SSLContext populated with available root CAs."""
    cafile = None
    try:
        import certifi  # type: ignore
        cand = certifi.where()
        if cand and os.path.isfile(cand):
            cafile = cand
    except Exception:
        pass

    ctx = ssl.create_default_context(cafile=cafile)

    try:
        ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)
    except Exception:
        pass

    if os.name == "nt":
        for store_name in ("ROOT", "CA"):
            try:
                der_certs = []
                for cert_bytes, encoding, trust in ssl.enum_certificates(store_name):
                    if encoding == "x509_asn" and (trust is True or "1.3.6.1.5.5.7.3.1" in str(trust)):
                        der_certs.append(cert_bytes)
                for der in der_certs:
                    try:
                        ctx.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(der))
                    except Exception:
                        pass
            except Exception:
                pass

    return ctx


def configure_process_tls_env() -> None:
    """Populate SSL_CERT_FILE / REQUESTS_CA_BUNDLE from certifi when unset."""
    try:
        import certifi  # type: ignore
        ca_path = certifi.where()
        if ca_path and os.path.isfile(ca_path):
            os.environ.setdefault("SSL_CERT_FILE", ca_path)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
    except Exception:
        pass


def windows_schannel_download(
    url: str,
    dest_path: str,
    cancel_check: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
    timeout_sec: float = 1800.0,
    allowed_hosts: Optional[Set[str]] = None,
) -> None:
    """
    Download a file using Windows built-in SChannel-backed `curl.exe` when Python's
    OpenSSL store is blocked or incomplete. Still enforces strict TLS verification
    and effective redirect host allowlist validation.
    """
    import time
    curl_exe = os.path.expandvars(r"%SystemRoot%\System32\curl.exe")
    if not os.path.isfile(curl_exe):
        curl_exe = "curl.exe"

    cmd = [
        curl_exe,
        "-fSL",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--max-redirs",
        "5",
        "--connect-timeout",
        "25",
        "--retry",
        "2",
        "-w",
        "%{url_effective}",
        "-o",
        dest_path,
        "--",
        url,
    ]
    spawn_kw = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        spawn_kw["creationflags"] = 0x08000000

    proc = subprocess.Popen(cmd, **spawn_kw)
    t0 = time.time()
    try:
        while proc.poll() is None:
            if cancel_check and cancel_check():
                proc.terminate()
                raise RuntimeError("Cancelled by user.")
            if time.time() - t0 > timeout_sec:
                proc.terminate()
                raise TimeoutError("Download timed out via Windows curl.exe.")
            if progress_cb and os.path.isfile(dest_path):
                try:
                    progress_cb(os.path.getsize(dest_path))
                except Exception:
                    pass
            time.sleep(0.35)
        if proc.returncode != 0:
            err_txt = ""
            try:
                err_txt = (proc.stderr.read() or b"").decode("utf-8", errors="replace").strip()
            except Exception:
                pass
            raise RuntimeError(err_txt or f"Windows curl.exe exited with code {proc.returncode}")

        effective_url = ""
        try:
            if proc.stdout is not None:
                effective_url = (proc.stdout.read() or b"").decode("utf-8", errors="replace").strip()
        except Exception:
            effective_url = ""

        if allowed_hosts is not None:
            check_url = effective_url or url
            parsed = urlparse(check_url)
            eff_host = (parsed.hostname or "").lower()
            allowed_norm = {str(h).lower() for h in allowed_hosts}
            if parsed.scheme != "https" or eff_host not in allowed_norm:
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                except OSError:
                    pass
                raise RuntimeError(f"Untrusted redirect target rejected: {check_url}")
    finally:
        for stream in (getattr(proc, "stdout", None), getattr(proc, "stderr", None)):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass
