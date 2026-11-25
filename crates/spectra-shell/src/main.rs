#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::fs;
use std::io::Write;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use spectra_agent::http_gateway::{start_gateway_server, GatewayConfig, GatewayHandle, SidecarState};
use tao::dpi::{LogicalPosition, LogicalSize};
use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder};
use tao::window::{Icon, WindowBuilder};
use wry::WebViewBuilder;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
use tao::platform::windows::{WindowBuilderExtWindows, WindowExtWindows};

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const EMBEDDED_ICON_ICO: &[u8] = include_bytes!("../../../icon.ico");

#[cfg(target_os = "windows")]
#[link(name = "shell32")]
extern "system" {
    fn SetCurrentProcessExplicitAppUserModelID(app_id: *const u16) -> i32;
}

#[cfg(target_os = "windows")]
#[link(name = "kernel32")]
extern "system" {
    fn SetDllDirectoryW(lp_path_name: *const u16) -> i32;
    fn SetDefaultDllDirectories(directory_flags: u32) -> i32;
}

#[cfg(target_os = "windows")]
#[link(name = "bcrypt")]
extern "system" {
    fn BCryptGenRandom(
        h_algorithm: *mut core::ffi::c_void,
        pb_buffer: *mut u8,
        cb_buffer: u32,
        dw_flags: u32,
    ) -> i32;
}

#[cfg(target_os = "windows")]
fn harden_windows_dll_search_path() {
    const LOAD_LIBRARY_SEARCH_SYSTEM32: u32 = 0x0000_0800;
    const LOAD_LIBRARY_SEARCH_APPLICATION_DIR: u32 = 0x0000_0200;
    let empty: [u16; 1] = [0];
    unsafe {
        let _ = SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_APPLICATION_DIR);
        let _ = SetDllDirectoryW(empty.as_ptr());
    }
}

#[cfg(target_os = "windows")]
fn set_windows_app_user_model_id(app_id: &str) {
    let mut wide: Vec<u16> = app_id.encode_utf16().collect();
    wide.push(0);
    unsafe {
        let _ = SetCurrentProcessExplicitAppUserModelID(wide.as_ptr());
    }
}

/// Generates a 128-bit cryptographic hex nonce used to authenticate the spawned Python sidecar.
fn generate_sidecar_nonce() -> String {
    let mut bytes = [0u8; 16];
    let mut filled = false;

    #[cfg(target_os = "windows")]
    {
        const BCRYPT_USE_SYSTEM_PREFERRED_RNG: u32 = 0x0000_0002;
        let status = unsafe {
            BCryptGenRandom(
                std::ptr::null_mut(),
                bytes.as_mut_ptr(),
                bytes.len() as u32,
                BCRYPT_USE_SYSTEM_PREFERRED_RNG,
            )
        };
        if status == 0 {
            filled = true;
        }
    }

    #[cfg(unix)]
    {
        use std::io::Read;
        if let Ok(mut f) = fs::File::open("/dev/urandom") {
            if f.read_exact(&mut bytes).is_ok() {
                filled = true;
            }
        }
    }

    if !filled {
        use std::collections::hash_map::RandomState;
        use std::hash::{BuildHasher, Hasher};
        use std::time::{SystemTime, UNIX_EPOCH};
        let now_nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let stack_addr = bytes.as_ptr() as usize as u64;
        let s1 = RandomState::new();
        let mut h1 = s1.build_hasher();
        h1.write_u32(std::process::id());
        h1.write_u64(stack_addr);
        let a = h1.finish().to_le_bytes();
        let s2 = RandomState::new();
        let mut h2 = s2.build_hasher();
        h2.write_u64(now_nanos as u64);
        h2.write_u64((now_nanos >> 64) as u64);
        let b = h2.finish().to_le_bytes();
        bytes[..8].copy_from_slice(&a);
        bytes[8..].copy_from_slice(&b);
    }

    let mut hex = String::with_capacity(32);
    for b in bytes {
        use std::fmt::Write as _;
        let _ = write!(&mut hex, "{b:02x}");
    }
    hex
}

/// Decodes an uncompressed 32-bit BGRA entry from an `.ico` buffer into top-down RGBA bytes.
fn decode_ico_entry_to_rgba(ico: &[u8], preferred_size: u32) -> Option<(Vec<u8>, u32, u32)> {
    if ico.len() < 6 {
        return None;
    }
    let reserved = u16::from_le_bytes([ico[0], ico[1]]);
    let ico_type = u16::from_le_bytes([ico[2], ico[3]]);
    let count = u16::from_le_bytes([ico[4], ico[5]]) as usize;
    if reserved != 0 || ico_type != 1 || count == 0 || ico.len() < 6 + count * 16 {
        return None;
    }

    let mut best: Option<(u32, u32, usize, u32)> = None;
    for idx in 0..count {
        let base = 6 + idx * 16;
        let w = if ico[base] == 0 { 256 } else { ico[base] as u32 };
        let h = if ico[base + 1] == 0 { 256 } else { ico[base + 1] as u32 };
        let bpp = u16::from_le_bytes([ico[base + 6], ico[base + 7]]);
        let size = u32::from_le_bytes([ico[base + 8], ico[base + 9], ico[base + 10], ico[base + 11]]) as usize;
        let offset = u32::from_le_bytes([ico[base + 12], ico[base + 13], ico[base + 14], ico[base + 15]]) as usize;

        if offset.checked_add(40).map_or(true, |end| end > ico.len()) {
            continue;
        }
        if offset.checked_add(size).map_or(true, |end| end > ico.len()) {
            continue;
        }
        let dib_size = u32::from_le_bytes([ico[offset], ico[offset + 1], ico[offset + 2], ico[offset + 3]]) as usize;
        if dib_size < 40 || offset + dib_size > ico.len() {
            continue;
        }
        let dib_bpp = u16::from_le_bytes([ico[offset + 14], ico[offset + 15]]);
        if bpp != 32 && dib_bpp != 32 {
            continue;
        }
        let score = w.abs_diff(preferred_size);
        let replace = match best {
            None => true,
            Some((_, _, _, best_score)) => score < best_score,
        };
        if replace {
            best = Some((w, h, offset, score));
        }
    }

    let (w, h, offset, _) = best?;
    let dib_size = u32::from_le_bytes([ico[offset], ico[offset + 1], ico[offset + 2], ico[offset + 3]]) as usize;
    let pixels_start = offset + dib_size;
    let row_bytes = (w as usize) * 4;
    let needed = row_bytes.checked_mul(h as usize)?;
    if pixels_start.checked_add(needed)? > ico.len() {
        return None;
    }

    let mut rgba = Vec::with_capacity(needed);
    for y in (0..h as usize).rev() {
        let row = &ico[pixels_start + y * row_bytes..pixels_start + (y + 1) * row_bytes];
        for px in row.chunks_exact(4) {
            // Convert BGRA DIB pixel order to top-down RGBA
            rgba.push(px[2]);
            rgba.push(px[1]);
            rgba.push(px[0]);
            rgba.push(px[3]);
        }
    }
    Some((rgba, w, h))
}

fn load_shell_icon(preferred_size: u32) -> Option<Icon> {
    let (rgba, w, h) = decode_ico_entry_to_rgba(EMBEDDED_ICON_ICO, preferred_size)?;
    Icon::from_rgba(rgba, w, h).ok()
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ShellConfig {
    attach_url: Option<String>,
    root_dir: Option<PathBuf>,
    port: Option<u16>,
    headless_check: bool,
    pure_rust: bool,
}

#[derive(Debug, Clone)]
enum ShellEvent {
    BackendError(String),
}

const SPLASH_HTML: &str = r#"<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>SPECTRA — Starting</title>
<style>
  html, body {
    margin: 0; height: 100%; background: #070a0f; color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
    display: flex; align-items: center; justify-content: center; overflow: hidden;
  }
  .card {
    text-align: center; padding: 36px 44px; border: 1px solid #1e293b;
    border-radius: 12px; background: #0c121b;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.65); max-width: 460px;
  }
  .badge {
    display: inline-block; font-size: 11px; letter-spacing: 0.14em;
    color: #38bdf8; text-transform: uppercase; margin-bottom: 10px;
  }
  h1 { margin: 0 0 10px; font-size: 24px; letter-spacing: 0.08em; color: #f8fafc; }
  p { margin: 0 0 20px; font-size: 13px; color: #94a3b8; line-height: 1.5; }
  .bar {
    height: 4px; width: 100%; background: #1e293b; border-radius: 999px; overflow: hidden;
  }
  .bar > span {
    display: block; height: 100%; width: 42%; background: linear-gradient(90deg, #0ea5e9, #a855f7);
    border-radius: 999px; animation: slide 1.2s ease-in-out infinite alternate;
  }
  @keyframes slide {
    from { transform: translateX(-10%); }
    to   { transform: translateX(150%); }
  }
</style>
</head>
<body>
  <div class="card">
    <div class="badge">Native Desktop Shell</div>
    <h1>SPECTRA</h1>
    <p>Initializing local diagnostics backend and hardware telemetry services&hellip;</p>
    <div class="bar"><span></span></div>
  </div>
</body>
</html>"#;

fn is_allowed_loopback_url(url: &str) -> bool {
    let trimmed = url.trim();
    let Some(rest) = trimmed.strip_prefix("http://") else {
        return false;
    };
    let authority = rest.split('/').next().unwrap_or("");
    if authority.is_empty() || authority.contains('@') {
        return false;
    }
    let host = if let Some((h, port_str)) = authority.rsplit_once(':') {
        if port_str.is_empty() || port_str.parse::<u16>().is_err() {
            return false;
        }
        h
    } else {
        authority
    };
    host.eq_ignore_ascii_case("127.0.0.1") || host.eq_ignore_ascii_case("localhost")
}

fn is_allowed_navigation_url(url: &str) -> bool {
    url == "about:blank" || is_allowed_loopback_url(url)
}

fn parse_cli_args<I, S>(args: I) -> Result<ShellConfig, String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    let mut cfg = ShellConfig {
        attach_url: None,
        root_dir: None,
        port: None,
        headless_check: false,
        pure_rust: false,
    };
    let mut iter = args.into_iter();
    while let Some(raw) = iter.next() {
        let arg = raw.as_ref();
        match arg {
            "--url" => {
                let val = iter
                    .next()
                    .ok_or_else(|| "Missing value for --url".to_string())?;
                let url_str = val.as_ref().trim();
                if !is_allowed_loopback_url(url_str) {
                    return Err(format!(
                        "Invalid --url '{url_str}': only http://127.0.0.1... or http://localhost... are permitted"
                    ));
                }
                cfg.attach_url = Some(url_str.to_string());
            }
            "--root" => {
                let val = iter
                    .next()
                    .ok_or_else(|| "Missing value for --root".to_string())?;
                cfg.root_dir = Some(PathBuf::from(val.as_ref()));
            }
            "--port" => {
                let val = iter
                    .next()
                    .ok_or_else(|| "Missing value for --port".to_string())?;
                let parsed: u16 = val
                    .as_ref()
                    .parse()
                    .map_err(|_| format!("Invalid --port value: {}", val.as_ref()))?;
                cfg.port = Some(parsed);
            }
            "--check-only" => {
                cfg.headless_check = true;
            }
            "--pure-rust" | "--no-python" => {
                cfg.pure_rust = true;
            }
            "--help" | "-h" => {
                return Err("Usage: spectra-shell [--url URL] [--root DIR] [--port PORT] [--pure-rust] [--check-only]".to_string());
            }
            other => {
                return Err(format!("Unknown argument: {other}"));
            }
        }
    }
    Ok(cfg)
}

fn resolve_app_root(explicit: Option<&Path>, exe_dir: Option<&Path>, cwd: Option<&Path>) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(root) = explicit {
        candidates.push(root.to_path_buf());
    }
    if let Some(exe) = exe_dir {
        candidates.push(exe.to_path_buf());
        candidates.push(exe.join("app"));
        if let Some(parent) = exe.parent() {
            candidates.push(parent.to_path_buf());
            candidates.push(parent.join("app"));
            if let Some(grand) = parent.parent() {
                candidates.push(grand.to_path_buf());
            }
        }
    }
    if let Some(dir) = cwd {
        candidates.push(dir.to_path_buf());
    }

    candidates
        .iter()
        .find(|dir| dir.join("web_server.py").is_file())
        .cloned()
        .or_else(|| {
            candidates
                .into_iter()
                .find(|dir| dir.join("web").join("dist").join("index.html").is_file())
        })
}

fn resolve_python_executable(app_root: &Path) -> (PathBuf, bool) {
    #[cfg(target_os = "windows")]
    {
        let mut bases = vec![app_root.to_path_buf()];
        if let Some(parent) = app_root.parent() {
            bases.push(parent.to_path_buf());
        }
        for base in &bases {
            let flat_w = base.join("pythonw.exe");
            if flat_w.is_file() {
                return (flat_w, true);
            }
            let pyembed_w = base.join("pyembed").join("pythonw.exe");
            if pyembed_w.is_file() {
                return (pyembed_w, true);
            }
            let flat_cli = base.join("python.exe");
            if flat_cli.is_file() {
                return (flat_cli, true);
            }
            let pyembed_cli = base.join("pyembed").join("python.exe");
            if pyembed_cli.is_file() {
                return (pyembed_cli, true);
            }
            let venv_w = base.join("venv").join("Scripts").join("pythonw.exe");
            if venv_w.is_file() {
                return (venv_w, false);
            }
        }
        (PathBuf::from("pythonw.exe"), false)
    }

    #[cfg(not(target_os = "windows"))]
    {
        for rel in ["venv/bin/python3", ".venv/bin/python3", "venv/bin/python"] {
            let cand = app_root.join(rel);
            if cand.is_file() {
                return (cand, false);
            }
        }
        (PathBuf::from("python3"), false)
    }
}

fn pick_free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|e| format!("Failed to bind ephemeral loopback port: {e}"))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("Failed to read bound port: {e}"))?
        .port();
    Ok(port)
}

fn spawn_python_backend(app_root: &Path, port: u16, sidecar_nonce: &str) -> Result<Child, String> {
    let (python_bin, is_embedded) = resolve_python_executable(app_root);
    let server_script = app_root.join("web_server.py");
    if !server_script.is_file() {
        return Err(format!("Missing web_server.py in {}", app_root.display()));
    }

    let mut cmd = Command::new(&python_bin);
    cmd.current_dir(app_root)
        .arg(&server_script)
        .arg("--port")
        .arg(port.to_string())
        .arg("--no-browser")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .env("SPECTRA_NATIVE_SHELL", "1")
        .env("SPECTRA_SIDECAR_NONCE", sidecar_nonce);

    if is_embedded {
        cmd.env("PYTHONNOUSERSITE", "1");
        let py_dir = python_bin.parent().unwrap_or(app_root);
        let site_pkgs = py_dir.join("Lib").join("site-packages");
        let mut paths = vec![app_root.to_path_buf(), py_dir.to_path_buf()];
        if site_pkgs.is_dir() {
            paths.push(site_pkgs);
        }
        if let Ok(joined) = env::join_paths(paths) {
            cmd.env("PYTHONPATH", joined);
        }
    }

    #[cfg(target_os = "windows")]
    cmd.creation_flags(CREATE_NO_WINDOW);

    let mut child = cmd.spawn().map_err(|e| {
        format!(
            "Failed to launch backend using {}: {e}",
            python_bin.display()
        )
    })?;

    if let Some(mut stderr_pipe) = child.stderr.take() {
        let log_path = env::temp_dir().join("spectra_sidecar_stderr.log");
        let _ = std::thread::Builder::new()
            .name("spectra-sidecar-stderr-drain".to_string())
            .spawn(move || {
                use std::io::Read;
                const MAX_LOG_BYTES: usize = 256 * 1024;
                let mut file = fs::OpenOptions::new()
                    .create(true)
                    .write(true)
                    .truncate(true)
                    .open(&log_path)
                    .ok();
                let mut written: usize = 0;
                let mut buf = [0u8; 4096];
                while let Ok(n) = stderr_pipe.read(&mut buf) {
                    if n == 0 {
                        break;
                    }
                    if let Some(ref mut f) = file {
                        if written < MAX_LOG_BYTES {
                            let to_write = (MAX_LOG_BYTES - written).min(n);
                            let _ = f.write_all(&buf[..to_write]);
                            written += to_write;
                        }
                    }
                }
            });
    }

    Ok(child)
}

fn verify_sidecar_nonce(port: u16, expected_nonce: &str) -> Result<bool, String> {
    use std::io::Read;
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    let mut stream = match TcpStream::connect_timeout(&addr, Duration::from_millis(150)) {
        Ok(s) => s,
        Err(_) => return Ok(false),
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(400)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(250)));

    let req = format!(
        "GET /api/version HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() || stream.flush().is_err() {
        return Ok(false);
    }

    let mut resp = Vec::with_capacity(2048);
    let mut chunk = [0u8; 1024];
    while resp.len() < 8192 {
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => {
                resp.extend_from_slice(&chunk[..n]);
                if resp.windows(4).any(|w| w == b"\r\n\r\n") {
                    break;
                }
            }
            Err(_) => break,
        }
    }
    let text = String::from_utf8_lossy(&resp);
    let header_block = text.split("\r\n\r\n").next().unwrap_or("");
    let mut lines = header_block.lines();
    let status_line = lines.next().unwrap_or("");
    if !status_line.starts_with("HTTP/1.") || !status_line.contains(" 200") {
        return Ok(false);
    }
    for line in lines {
        if let Some((name, value)) = line.split_once(':') {
            if name.trim().eq_ignore_ascii_case("x-spectra-nonce") {
                if value.trim() == expected_nonce {
                    return Ok(true);
                }
                return Err(format!(
                    "Sidecar nonce mismatch on 127.0.0.1:{port} — refusing untrusted local listener"
                ));
            }
        }
    }
    Err(format!(
        "Port 127.0.0.1:{port} responded without expected X-Spectra-Nonce — refusing untrusted listener"
    ))
}

fn send_shutdown_signal(port: u16) {
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    let body = br#"{"reason":"shell_exit","immediate":true}"#;
    if let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(250)) {
        let _ = stream.set_write_timeout(Some(Duration::from_millis(250)));
        let req = format!(
            "POST /api/app/close HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            body.len()
        );
        let _ = stream.write_all(req.as_bytes());
        let _ = stream.write_all(body);
        let _ = stream.flush();
    }
}

fn stop_backend(child_slot: &Arc<Mutex<Option<Child>>>, port: Option<u16>) {
    if let Some(p) = port {
        send_shutdown_signal(p);
    }
    let mut guard = match child_slot.lock() {
        Ok(g) => g,
        Err(poisoned) => poisoned.into_inner(),
    };
    if let Some(mut child) = guard.take() {
        let pid = child.id();
        let deadline = Instant::now() + Duration::from_millis(1000);
        loop {
            match child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) => {
                    if Instant::now() >= deadline {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(50));
                }
                Err(_) => break,
            }
        }
        #[cfg(target_os = "windows")]
        {
            let taskkill_path = env::var_os("SystemRoot")
                .map(|root| PathBuf::from(root).join("System32").join("taskkill.exe"))
                .filter(|p| p.is_file())
                .unwrap_or_else(|| PathBuf::from("taskkill.exe"));
            let _ = Command::new(taskkill_path)
                .args(["/F", "/PID", &pid.to_string(), "/T"])
                .creation_flags(CREATE_NO_WINDOW)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
        #[cfg(not(target_os = "windows"))]
        let _ = pid;
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn wait_for_backend_ready(
    port: u16,
    expected_nonce: &str,
    child_slot: &Arc<Mutex<Option<Child>>>,
    stop_flag: &Arc<AtomicBool>,
    timeout: Duration,
) -> Result<(), String> {
    let deadline = Instant::now() + timeout;

    while Instant::now() < deadline {
        if stop_flag.load(Ordering::Relaxed) {
            return Err("Startup cancelled".to_string());
        }

        match verify_sidecar_nonce(port, expected_nonce) {
            Ok(true) => return Ok(()),
            Ok(false) => {}
            Err(err) => return Err(err),
        }

        if let Ok(mut guard) = child_slot.lock() {
            if let Some(child) = guard.as_mut() {
                if let Ok(Some(status)) = child.try_wait() {
                    return Err(format!("Backend exited early with status: {status}"));
                }
            }
        }

        std::thread::sleep(Duration::from_millis(75));
    }

    Err(format!(
        "Timed out waiting for SPECTRA backend on http://127.0.0.1:{port}"
    ))
}

fn escape_html(raw: &str) -> String {
    raw.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn render_error_html(msg: &str) -> String {
    let safe = escape_html(msg);
    format!(
        r#"<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><title>SPECTRA — Startup Error</title>
<style>
  body {{ margin: 0; height: 100vh; background: #070a0f; color: #fecaca;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
         display: flex; align-items: center; justify-content: center; }}
  .box {{ max-width: 560px; padding: 28px 32px; background: #180b10;
          border: 1px solid #ef4444; border-radius: 10px; }}
  h2 {{ margin: 0 0 10px; color: #f87171; font-size: 16px; letter-spacing: 0.06em; }}
  pre {{ white-space: pre-wrap; margin: 0; font-size: 12px; color: #fca5a5; }}
</style></head>
<body><div class="box"><h2>SPECTRA BACKEND STARTUP ERROR</h2><pre>{safe}</pre></div></body>
</html>"#
    )
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct WindowState {
    maximized: bool,
    width: u32,
    height: u32,
    x: Option<i32>,
    y: Option<i32>,
}

impl Default for WindowState {
    fn default() -> Self {
        Self {
            maximized: true,
            width: 1440,
            height: 920,
            x: None,
            y: None,
        }
    }
}

impl WindowState {
    fn extract_json_token<'a>(raw: &'a str, key: &str) -> Option<&'a str> {
        let needle = format!("\"{key}\"");
        let idx = raw.find(&needle)?;
        let after_key = &raw[idx + needle.len()..];
        let colon = after_key.find(':')?;
        let rest = after_key[colon + 1..].trim_start();
        let end = rest
            .find(|c: char| c == ',' || c == '}' || c == '\n' || c == '\r')
            .unwrap_or(rest.len());
        Some(rest[..end].trim())
    }

    fn from_json(raw: &str) -> Self {
        let mut st = Self::default();
        if let Some(tok) = Self::extract_json_token(raw, "maximized") {
            if tok == "true" {
                st.maximized = true;
            } else if tok == "false" {
                st.maximized = false;
            }
        }
        if let Some(tok) = Self::extract_json_token(raw, "width") {
            if let Ok(w) = tok.parse::<u32>() {
                if (640..=16384).contains(&w) {
                    st.width = w;
                }
            }
        }
        if let Some(tok) = Self::extract_json_token(raw, "height") {
            if let Ok(h) = tok.parse::<u32>() {
                if (480..=16384).contains(&h) {
                    st.height = h;
                }
            }
        }
        if let Some(tok) = Self::extract_json_token(raw, "x") {
            if let Ok(x) = tok.parse::<i32>() {
                if (-16384..=32768).contains(&x) {
                    st.x = Some(x);
                }
            }
        }
        if let Some(tok) = Self::extract_json_token(raw, "y") {
            if let Ok(y) = tok.parse::<i32>() {
                if (-16384..=32768).contains(&y) {
                    st.y = Some(y);
                }
            }
        }
        st
    }

    fn to_json(&self) -> String {
        let x_val = self.x.map_or_else(|| "null".to_string(), |v| v.to_string());
        let y_val = self.y.map_or_else(|| "null".to_string(), |v| v.to_string());
        format!(
            "{{\n  \"maximized\": {},\n  \"width\": {},\n  \"height\": {},\n  \"x\": {},\n  \"y\": {}\n}}\n",
            self.maximized, self.width, self.height, x_val, y_val
        )
    }
}

fn window_state_path() -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = env::var("APPDATA") {
            if !appdata.trim().is_empty() {
                return Some(PathBuf::from(appdata).join("SPECTRA").join("window_state.json"));
            }
        }
        if let Ok(local) = env::var("LOCALAPPDATA") {
            if !local.trim().is_empty() {
                return Some(PathBuf::from(local).join("SPECTRA").join("window_state.json"));
            }
        }
        None
    }

    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(xdg) = env::var("XDG_CONFIG_HOME") {
            if !xdg.trim().is_empty() {
                return Some(PathBuf::from(xdg).join("spectra").join("window_state.json"));
            }
        }
        if let Ok(home) = env::var("HOME") {
            if !home.trim().is_empty() {
                return Some(
                    PathBuf::from(home)
                        .join(".config")
                        .join("spectra")
                        .join("window_state.json"),
                );
            }
        }
        None
    }
}

fn load_window_state(path: Option<&Path>) -> WindowState {
    let Some(p) = path else {
        return WindowState::default();
    };
    match fs::read_to_string(p) {
        Ok(raw) => WindowState::from_json(&raw),
        Err(_) => WindowState::default(),
    }
}

fn save_window_state(path: Option<&Path>, state: &WindowState) {
    let Some(p) = path else {
        return;
    };
    if let Some(parent) = p.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(p, state.to_json());
}

fn capture_window_state(window: &tao::window::Window, state: &mut WindowState) {
    let is_min = window.is_minimized();
    if is_min {
        return;
    }
    let is_max = window.is_maximized();
    state.maximized = is_max;
    if !is_max {
        let scale = window.scale_factor();
        let sz = window.inner_size().to_logical::<u32>(scale);
        if sz.width >= 640 && sz.height >= 480 {
            state.width = sz.width;
            state.height = sz.height;
        }
        if let Ok(pos) = window.outer_position() {
            let lpos = pos.to_logical::<i32>(scale);
            if (-16384..=32768).contains(&lpos.x) && (-16384..=32768).contains(&lpos.y) {
                state.x = Some(lpos.x);
                state.y = Some(lpos.y);
            }
        }
    }
}

fn main() {
    #[cfg(target_os = "windows")]
    {
        harden_windows_dll_search_path();
        set_windows_app_user_model_id("SPECTRA.Diagnostics.Suite");
    }

    let cfg = match parse_cli_args(env::args().skip(1)) {
        Ok(c) => c,
        Err(msg) => {
            eprintln!("{msg}");
            std::process::exit(if msg.starts_with("Usage:") { 0 } else { 2 });
        }
    };

    let exe_path = env::current_exe().ok();
    let exe_dir = exe_path.as_deref().and_then(|p| p.parent());
    let cwd = env::current_dir().ok();
    let app_root = resolve_app_root(cfg.root_dir.as_deref(), exe_dir, cwd.as_deref());

    if cfg.headless_check {
        println!(
            "spectra-shell ok: app_root={:?}, attach_url={:?}, pure_rust={}",
            app_root, cfg.attach_url, cfg.pure_rust
        );
        return;
    }

    let state_path = window_state_path();
    let mut win_state = load_window_state(state_path.as_deref());

    let event_loop = EventLoopBuilder::<ShellEvent>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    let win_icon = load_shell_icon(32).or_else(|| load_shell_icon(48)).or_else(|| load_shell_icon(256));
    let mut win_builder = WindowBuilder::new()
        .with_title("SPECTRA — Universal Hardware Telemetry & Firmware Diagnostics")
        .with_inner_size(LogicalSize::new(win_state.width as f64, win_state.height as f64))
        .with_min_inner_size(LogicalSize::new(1024.0, 680.0))
        .with_maximized(win_state.maximized);

    #[cfg(not(target_os = "windows"))]
    {
        if let Some(icon) = load_shell_icon(256).or(win_icon) {
            win_builder = win_builder.with_window_icon(Some(icon));
        }
    }
    #[cfg(target_os = "windows")]
    {
        if let Some(icon) = win_icon {
            win_builder = win_builder.with_window_icon(Some(icon));
        }
        if let Some(taskbar_icon) = load_shell_icon(256).or_else(|| load_shell_icon(48)) {
            win_builder = win_builder.with_taskbar_icon(Some(taskbar_icon));
        }
    }

    if !win_state.maximized {
        if let (Some(x), Some(y)) = (win_state.x, win_state.y) {
            win_builder = win_builder.with_position(LogicalPosition::new(x as f64, y as f64));
        }
    }
    let window = win_builder
        .build(&event_loop)
        .expect("Failed to create SPECTRA native window");
    #[cfg(target_os = "windows")]
    if let Some(taskbar_icon) = load_shell_icon(256).or_else(|| load_shell_icon(48)) {
        window.set_taskbar_icon(Some(taskbar_icon));
    }
    if win_state.maximized {
        window.set_maximized(true);
    }

    // Phase 3 Embedded Rust HTTP Gateway starts immediately so the WebView mounts
    // the React UI without waiting for Python cold start.
    let child_slot: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let stop_flag = Arc::new(AtomicBool::new(false));
    let mut managed_sidecar_port: Option<u16> = None;
    let mut gateway_runtime: Option<tokio::runtime::Runtime> = None;
    let mut gateway_handle: Option<GatewayHandle> = None;
    let mut gateway_boot_error: Option<String> = None;

    let initial_url = if let Some(ref url) = cfg.attach_url {
        Some(url.clone())
    } else if let Some(ref root) = app_root {
        let has_python_server = root.join("web_server.py").is_file();
        let use_pure_rust = cfg.pure_rust || !has_python_server;
        match tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .worker_threads(4)
            .build()
        {
            Ok(rt) => {
                let gw_cfg = GatewayConfig {
                    app_root: root.clone(),
                    pure_rust: use_pure_rust,
                    bind_port: cfg.port.or(Some(0)),
                    ..Default::default()
                };
                match rt.block_on(start_gateway_server(gw_cfg)) {
                    Ok(handle) => {
                        let gw_port = handle.port;
                        let url = format!("http://127.0.0.1:{gw_port}/");
                        if !use_pure_rust {
                            if let Ok(sidecar_port) = pick_free_port() {
                                managed_sidecar_port = Some(sidecar_port);
                                let sidecar_nonce = generate_sidecar_nonce();
                                let root_bg = root.clone();
                                let child_slot_bg = Arc::clone(&child_slot);
                                let stop_flag_bg = Arc::clone(&stop_flag);
                                let sidecar_tx = handle.clone_sidecar_sender();
                                std::thread::spawn(move || {
                                    match spawn_python_backend(&root_bg, sidecar_port, &sidecar_nonce) {
                                        Ok(child) => {
                                            if let Ok(mut g) = child_slot_bg.lock() {
                                                *g = Some(child);
                                            }
                                            match wait_for_backend_ready(
                                                sidecar_port,
                                                &sidecar_nonce,
                                                &child_slot_bg,
                                                &stop_flag_bg,
                                                Duration::from_secs(20),
                                            ) {
                                                Ok(()) => {
                                                    let _ = sidecar_tx.send(SidecarState::Ready(sidecar_port));
                                                }
                                                Err(err) => {
                                                    let _ = sidecar_tx.send(SidecarState::Failed(err.clone()));
                                                    let _ = proxy.send_event(ShellEvent::BackendError(err));
                                                }
                                            }
                                        }
                                        Err(err) => {
                                            let _ = sidecar_tx.send(SidecarState::Failed(err.clone()));
                                            let _ = proxy.send_event(ShellEvent::BackendError(err));
                                        }
                                    }
                                });
                            }
                        }
                        gateway_handle = Some(handle);
                        gateway_runtime = Some(rt);
                        Some(url)
                    }
                    Err(e) => {
                        gateway_boot_error = Some(e);
                        None
                    }
                }
            }
            Err(e) => {
                gateway_boot_error = Some(format!("Failed to start async Rust runtime: {e}"));
                None
            }
        }
    } else {
        gateway_boot_error = Some(
            "Could not locate SPECTRA installation directory (web/dist/index.html or web_server.py). Pass --root <SPECTRA_DIR>."
                .to_string(),
        );
        None
    };

    let builder = WebViewBuilder::new()
        .with_devtools(cfg!(debug_assertions))
        .with_navigation_handler(|uri| is_allowed_navigation_url(&uri))
        .with_new_window_req_handler(|uri| is_allowed_navigation_url(&uri));
    let builder = if let Some(ref url) = initial_url {
        builder.with_url(url)
    } else if let Some(ref err) = gateway_boot_error {
        builder.with_html(render_error_html(err))
    } else {
        builder.with_html(SPLASH_HTML)
    };

    #[cfg(any(
        target_os = "windows",
        target_os = "macos",
        target_os = "ios",
        target_os = "android"
    ))]
    let webview = builder
        .build(&window)
        .expect("Failed to initialize native WebView");

    #[cfg(not(any(
        target_os = "windows",
        target_os = "macos",
        target_os = "ios",
        target_os = "android"
    )))]
    let webview = {
        use tao::platform::unix::WindowExtUnix;
        use wry::WebViewBuilderExtUnix;
        let vbox = window.default_vbox().expect("GTK default vbox unavailable");
        builder
            .build_gtk(vbox)
            .expect("Failed to initialize WebKitGTK WebView")
    };

    let child_slot_loop = Arc::clone(&child_slot);
    let stop_flag_loop = Arc::clone(&stop_flag);
    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::UserEvent(ShellEvent::BackendError(msg)) => {
                let _ = webview.load_html(&render_error_html(&msg));
            }
            Event::WindowEvent {
                event: WindowEvent::Resized(_) | WindowEvent::Moved(_),
                ..
            } => {
                capture_window_state(&window, &mut win_state);
            }
            Event::WindowEvent {
                event: WindowEvent::CloseRequested,
                ..
            } => {
                capture_window_state(&window, &mut win_state);
                save_window_state(state_path.as_deref(), &win_state);
                stop_flag_loop.store(true, Ordering::Relaxed);
                stop_backend(&child_slot_loop, managed_sidecar_port);
                if let Some(gh) = gateway_handle.take() {
                    gh.shutdown();
                }
                drop(gateway_runtime.take());
                *control_flow = ControlFlow::Exit;
            }
            Event::LoopDestroyed => {
                save_window_state(state_path.as_deref(), &win_state);
                stop_flag_loop.store(true, Ordering::Relaxed);
                stop_backend(&child_slot_loop, managed_sidecar_port);
                if let Some(gh) = gateway_handle.take() {
                    gh.shutdown();
                }
                drop(gateway_runtime.take());
            }
            _ => {}
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn make_temp_dir(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = env::temp_dir().join(format!("spectra_shell_test_{label}_{nanos}"));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn window_state_defaults_maximized_and_roundtrips_json() {
        let def = WindowState::default();
        assert!(def.maximized);
        assert_eq!(def.width, 1440);
        assert_eq!(def.height, 920);

        let dir = make_temp_dir("winstate");
        let file = dir.join("window_state.json");
        let custom = WindowState {
            maximized: false,
            width: 1280,
            height: 800,
            x: Some(120),
            y: Some(64),
        };
        save_window_state(Some(&file), &custom);
        let loaded = load_window_state(Some(&file));
        assert_eq!(loaded, custom);

        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn window_state_ignores_out_of_range_minimized_coordinates() {
        let bad_json = r#"{"maximized": false, "width": 100, "height": 50, "x": -32000, "y": -32000}"#;
        let parsed = WindowState::from_json(bad_json);
        assert!(!parsed.maximized);
        assert_eq!(parsed.width, 1440);
        assert_eq!(parsed.height, 920);
        assert_eq!(parsed.x, None);
        assert_eq!(parsed.y, None);
    }

    #[test]
    fn parse_cli_args_handles_url_root_port() {
        let cfg = parse_cli_args(["--url", "http://127.0.0.1:8765/", "--port", "9001", "--check-only"]).unwrap();
        assert_eq!(cfg.attach_url.as_deref(), Some("http://127.0.0.1:8765/"));
        assert_eq!(cfg.port, Some(9001));
        assert!(cfg.headless_check);
        assert!(cfg.root_dir.is_none());
    }

    #[test]
    fn parse_cli_args_rejects_bad_port() {
        let err = parse_cli_args(["--port", "abc"]).unwrap_err();
        assert!(err.contains("Invalid --port"));
    }

    #[test]
    fn resolve_app_root_prefers_explicit_and_finds_app_subdir() {
        let root = make_temp_dir("resolve");
        let exe_dir = root.join("bin");
        let app_dir = root.join("app");
        fs::create_dir_all(&exe_dir).unwrap();
        fs::create_dir_all(&app_dir).unwrap();
        fs::write(app_dir.join("web_server.py"), "# test").unwrap();

        let found = resolve_app_root(None, Some(&exe_dir), None);
        assert_eq!(found.as_deref(), Some(app_dir.as_path()));

        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn pick_free_port_returns_nonzero_loopback_port() {
        let port = pick_free_port().unwrap();
        assert!(port > 0);
    }

    #[test]
    fn escape_html_escapes_special_chars() {
        assert_eq!(escape_html("<script>&\"</script>"), "&lt;script&gt;&amp;&quot;&lt;/script&gt;");
    }

    #[test]
    fn icon_decoder_extracts_32_and_256_rgba() {
        let (rgba32, w32, h32) = decode_ico_entry_to_rgba(EMBEDDED_ICON_ICO, 32).expect("32px icon");
        assert_eq!((w32, h32), (32, 32));
        assert_eq!(rgba32.len(), 32 * 32 * 4);
        assert!(rgba32.chunks_exact(4).any(|px| px[3] > 0));

        let (rgba256, w256, h256) = decode_ico_entry_to_rgba(EMBEDDED_ICON_ICO, 256).expect("256px icon");
        assert_eq!((w256, h256), (256, 256));
        assert_eq!(rgba256.len(), 256 * 256 * 4);
        assert!(rgba256.chunks_exact(4).any(|px| px[3] > 0));
    }

    #[test]
    fn parse_cli_args_supports_pure_rust_flag() {
        let cfg = parse_cli_args(["--root", "/opt/spectra", "--pure-rust"]).unwrap();
        assert!(cfg.pure_rust);
        assert_eq!(cfg.root_dir.as_deref(), Some(Path::new("/opt/spectra")));
    }

    #[test]
    fn parse_cli_args_validates_loopback_url_and_navigation() {
        assert!(parse_cli_args(["--url", "http://localhost:5173/"]).is_ok());
        assert!(parse_cli_args(["--url", "http://127.0.0.1:8080/app"]).is_ok());
        assert!(parse_cli_args(["--url", "file:///etc/passwd"]).is_err());
        assert!(parse_cli_args(["--url", "javascript:alert(1)"]).is_err());
        assert!(parse_cli_args(["--url", "https://evil.example.com/"]).is_err());
        assert!(parse_cli_args(["--url", "http://127.0.0.1@evil.example/"]).is_err());

        assert!(is_allowed_navigation_url("about:blank"));
        assert!(is_allowed_navigation_url("http://127.0.0.1:8080/index.html"));
        assert!(is_allowed_navigation_url("http://localhost:5173/"));
        assert!(!is_allowed_navigation_url("https://example.com"));
        assert!(!is_allowed_navigation_url("file:///etc/passwd"));
    }
}
