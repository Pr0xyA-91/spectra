//! Phase 3 Embedded Rust HTTP Gateway & Control Plane for SPECTRA.
//!
//! Serves the compiled React frontend (`web/dist/`), native Rust health/version/heartbeat/debug
//! endpoints, and `--pure-rust` hardware routes directly from `spectra-agent`, while cleanly
//! coordinating and reverse-proxying legacy stateful endpoints (`/api/ai/*`, `/api/hmi/*`,
//! `/api/github/*`, `/api/stats`, etc.) to a loopback Python sidecar when hybrid mode is active.

use std::collections::{HashMap, VecDeque};
use std::fs;
use std::net::SocketAddr;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{watch, oneshot};

use crate::{send_jura_command, AppState};
use spectra_core::matches_connected_machine;
use spectra_hal::SerialTransport;

const MAX_REQUEST_HEAD_BYTES: usize = 64 * 1024;
const MAX_REQUEST_BODY_BYTES: usize = 64 * 1024 * 1024;
const MAX_DEBUG_LOG_ENTRIES: usize = 500;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SidecarState {
    Disabled,
    Starting,
    Ready(u16),
    Failed(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DebugLogEntry {
    pub timestamp: String,
    pub level: String,
    pub source: String,
    pub message: String,
    pub details: String,
}

#[derive(Debug, Clone)]
pub struct GatewayConfig {
    pub app_root: PathBuf,
    pub pure_rust: bool,
    pub bind_port: Option<u16>,
    pub default_build: String,
    pub default_edition: String,
}

impl Default for GatewayConfig {
    fn default() -> Self {
        Self {
            app_root: PathBuf::from("."),
            pure_rust: false,
            bind_port: Some(0),
            default_build: "20261114.0020".to_string(),
            default_edition: "Rust Gateway & Hybrid Engine".to_string(),
        }
    }
}

pub struct GatewayHandle {
    pub port: u16,
    sidecar_tx: watch::Sender<SidecarState>,
    shutdown_tx: Option<oneshot::Sender<()>>,
}

impl GatewayHandle {
    pub fn clone_sidecar_sender(&self) -> watch::Sender<SidecarState> {
        self.sidecar_tx.clone()
    }

    pub fn set_sidecar_ready(&self, port: u16) {
        let _ = self.sidecar_tx.send(SidecarState::Ready(port));
    }

    pub fn set_sidecar_failed(&self, err: String) {
        let _ = self.sidecar_tx.send(SidecarState::Failed(err));
    }

    pub fn sidecar_port_if_ready(&self) -> Option<u16> {
        match *self.sidecar_tx.borrow() {
            SidecarState::Ready(p) => Some(p),
            _ => None,
        }
    }

    pub fn shutdown(mut self) {
        if let Some(tx) = self.shutdown_tx.take() {
            let _ = tx.send(());
        }
    }
}

struct GatewayShared {
    app_root: PathBuf,
    dist_root: PathBuf,
    pure_rust: bool,
    build: String,
    edition: String,
    app_state: AppState,
    sidecar_rx: watch::Receiver<SidecarState>,
    last_heartbeat_epoch_ms: AtomicU64,
    started_epoch_ms: u64,
    logs: Mutex<VecDeque<DebugLogEntry>>,
}

fn now_epoch_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn format_timestamp_hms() -> String {
    let secs = (now_epoch_ms() / 1000) % 86_400;
    let h = secs / 3600;
    let m = (secs % 3600) / 60;
    let s = secs % 60;
    format!("{h:02}:{m:02}:{s:02}")
}

/// Extracts `__build__` and `__edition__` metadata from `version.py` when present so the Rust
/// gateway stays synchronized with release build metadata automatically.
pub fn read_version_metadata(app_root: &Path, default_build: &str, default_edition: &str) -> (String, String) {
    let version_py = app_root.join("version.py");
    let Ok(text) = fs::read_to_string(version_py) else {
        return (default_build.to_string(), default_edition.to_string());
    };
    let mut build = default_build.to_string();
    let mut edition = default_edition.to_string();
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("__build__") {
            if let Some(val) = extract_quoted_assignment(rest) {
                build = val;
            }
        } else if let Some(rest) = trimmed.strip_prefix("__edition__") {
            if let Some(val) = extract_quoted_assignment(rest) {
                edition = val;
            }
        }
    }
    (build, edition)
}

fn extract_quoted_assignment(rhs: &str) -> Option<String> {
    let after_eq = rhs.split_once('=')?.1.trim();
    let quote = after_eq.chars().next()?;
    if quote != '"' && quote != '\'' {
        return None;
    }
    let inner = &after_eq[1..];
    let end = inner.find(quote)?;
    Some(inner[..end].to_string())
}

/// Spawns the embedded Rust HTTP/1.1 gateway on `127.0.0.1` and returns its bound port + control handle.
pub async fn start_gateway_server(cfg: GatewayConfig) -> Result<GatewayHandle, String> {
    let bind_addr = SocketAddr::from(([127, 0, 0, 1], cfg.bind_port.unwrap_or(0)));
    let listener = TcpListener::bind(bind_addr)
        .await
        .map_err(|e| format!("Failed to bind Rust HTTP gateway on {bind_addr}: {e}"))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("Failed to query gateway port: {e}"))?
        .port();

    let (build, edition) = read_version_metadata(&cfg.app_root, &cfg.default_build, &cfg.default_edition);
    let init_sidecar = if cfg.pure_rust {
        SidecarState::Disabled
    } else {
        SidecarState::Starting
    };
    let (sidecar_tx, sidecar_rx) = watch::channel(init_sidecar);
    let (shutdown_tx, mut shutdown_rx) = oneshot::channel();

    let now_ms = now_epoch_ms();
    let shared = Arc::new(GatewayShared {
        dist_root: cfg.app_root.join("web").join("dist"),
        app_root: cfg.app_root,
        pure_rust: cfg.pure_rust,
        build,
        edition,
        app_state: AppState::new(),
        sidecar_rx,
        last_heartbeat_epoch_ms: AtomicU64::new(now_ms),
        started_epoch_ms: now_ms,
        logs: Mutex::new(VecDeque::with_capacity(MAX_DEBUG_LOG_ENTRIES)),
    });

    shared.push_log(
        "INFO",
        "RUST_GATEWAY",
        format!(
            "SPECTRA Rust HTTP control plane listening on 127.0.0.1:{port} (mode={})",
            if cfg.pure_rust { "pure-rust" } else { "hybrid-gateway" }
        ),
        String::new(),
    );

    tokio::spawn(async move {
        loop {
            tokio::select! {
                _ = &mut shutdown_rx => break,
                res = listener.accept() => {
                    let Ok((stream, _)) = res else {
                        break;
                    };
                    let state = Arc::clone(&shared);
                    tokio::spawn(async move {
                        let _ = handle_connection(stream, state).await;
                    });
                }
            }
        }
    });

    Ok(GatewayHandle {
        port,
        sidecar_tx,
        shutdown_tx: Some(shutdown_tx),
    })
}

impl GatewayShared {
    fn push_log(&self, level: &str, source: &str, message: String, details: String) {
        if let Ok(mut guard) = self.logs.lock() {
            if guard.len() >= MAX_DEBUG_LOG_ENTRIES {
                guard.pop_front();
            }
            guard.push_back(DebugLogEntry {
                timestamp: format_timestamp_hms(),
                level: level.to_string(),
                source: source.to_string(),
                message,
                details,
            });
        }
    }
}

struct ParsedHttpRequest {
    method: String,
    target: String,
    path: String,
    query: String,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

async fn read_http_request(stream: &mut TcpStream) -> Result<Option<ParsedHttpRequest>, String> {
    let mut buf = Vec::with_capacity(4096);
    let mut tmp = [0u8; 4096];
    let head_end;

    loop {
        if let Some(pos) = find_subslice(&buf, b"\r\n\r\n") {
            head_end = pos;
            break;
        }
        if buf.len() >= MAX_REQUEST_HEAD_BYTES {
            return Err("HTTP header too large".to_string());
        }
        let n = stream
            .read(&mut tmp)
            .await
            .map_err(|e| format!("Socket read error: {e}"))?;
        if n == 0 {
            if buf.is_empty() {
                return Ok(None);
            }
            return Err("Unexpected EOF reading HTTP headers".to_string());
        }
        buf.extend_from_slice(&tmp[..n]);
    }

    let head_str = std::str::from_utf8(&buf[..head_end])
        .map_err(|_| "Invalid UTF-8 in HTTP headers".to_string())?;
    let mut lines = head_str.split("\r\n");
    let req_line = lines.next().ok_or_else(|| "Empty request line".to_string())?;
    let mut parts = req_line.split_whitespace();
    let method = parts.next().unwrap_or("GET").to_uppercase();
    let target = parts.next().unwrap_or("/").to_string();

    let (path_raw, query) = match target.split_once('?') {
        Some((p, q)) => (p.to_string(), q.to_string()),
        None => (target.clone(), String::new()),
    };

    let mut headers = Vec::new();
    let mut content_len: usize = 0;
    for line in lines {
        if let Some((k, v)) = line.split_once(':') {
            let key = k.trim().to_string();
            let val = v.trim().to_string();
            if key.eq_ignore_ascii_case("content-length") {
                content_len = val.parse::<usize>().unwrap_or(0);
            }
            headers.push((key, val));
        }
    }

    if content_len > MAX_REQUEST_BODY_BYTES {
        return Err("Request body exceeds 64 MiB limit".to_string());
    }

    let body_start = head_end + 4;
    let mut body = buf[body_start..].to_vec();
    while body.len() < content_len {
        let remaining = content_len - body.len();
        let to_read = remaining.min(tmp.len());
        let n = stream
            .read(&mut tmp[..to_read])
            .await
            .map_err(|e| format!("Socket body read error: {e}"))?;
        if n == 0 {
            return Err("Unexpected EOF reading HTTP body".to_string());
        }
        body.extend_from_slice(&tmp[..n]);
    }
    body.truncate(content_len);

    Ok(Some(ParsedHttpRequest {
        method,
        target,
        path: percent_decode(&path_raw),
        query,
        headers,
        body,
    }))
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

fn percent_decode(input: &str) -> String {
    let mut out = Vec::with_capacity(input.len());
    let bytes = input.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(hi), Some(lo)) = (hex_val(bytes[i + 1]), hex_val(bytes[i + 2])) {
                out.push((hi << 4) | lo);
                i += 3;
                continue;
            }
        }
        if bytes[i] == b'+' {
            out.push(b' ');
        } else {
            out.push(bytes[i]);
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn hex_val(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

fn parse_query_params(query: &str) -> HashMap<String, String> {
    let mut map = HashMap::new();
    for pair in query.split('&') {
        if pair.is_empty() {
            continue;
        }
        let (k, v) = pair.split_once('=').unwrap_or((pair, ""));
        map.insert(percent_decode(k), percent_decode(v));
    }
    map
}

async fn write_http_response(
    stream: &mut TcpStream,
    status_line: &str,
    content_type: &str,
    cache_control: &str,
    body: &[u8],
) -> Result<(), String> {
    let header = format!(
        "HTTP/1.1 {status_line}\r\n\
         Content-Type: {content_type}\r\n\
         Content-Length: {}\r\n\
         Cache-Control: {cache_control}\r\n\
         X-Content-Type-Options: nosniff\r\n\
         Connection: close\r\n\r\n",
        body.len()
    );
    stream
        .write_all(header.as_bytes())
        .await
        .and_then(|_| Ok(()))
        .map_err(|e| e.to_string())?;
    stream.write_all(body).await.map_err(|e| e.to_string())?;
    let _ = stream.flush().await;
    Ok(())
}

async fn write_json_response(stream: &mut TcpStream, status: &str, val: &Value) -> Result<(), String> {
    let body = serde_json::to_vec(val).unwrap_or_else(|_| b"{}".to_vec());
    write_http_response(
        stream,
        status,
        "application/json; charset=utf-8",
        "no-store",
        &body,
    )
    .await
}

fn mime_type_for_path(path: &Path) -> &'static str {
    match path.extension().and_then(|e| e.to_str()).unwrap_or("").to_ascii_lowercase().as_str() {
        "html" | "htm" => "text/html; charset=utf-8",
        "js" | "mjs" => "application/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "ico" => "image/x-icon",
        "woff2" => "font/woff2",
        "woff" => "font/woff",
        "txt" | "md" => "text/plain; charset=utf-8",
        _ => "application/octet-stream",
    }
}

fn sanitize_safe_subpath(root: &Path, req_rel: &str) -> Option<PathBuf> {
    let trimmed = req_rel.trim_start_matches('/');
    let mut clean = PathBuf::new();
    for comp in Path::new(trimmed).components() {
        match comp {
            Component::Normal(part) => clean.push(part),
            Component::CurDir => {}
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => return None,
        }
    }
    let joined = root.join(clean);
    let canon_root = fs::canonicalize(root).ok()?;
    let canon_file = fs::canonicalize(&joined).ok()?;
    if canon_file.starts_with(&canon_root) && canon_file.is_file() {
        Some(canon_file)
    } else {
        None
    }
}

async fn handle_connection(mut stream: TcpStream, state: Arc<GatewayShared>) -> Result<(), String> {
    let Some(req) = read_http_request(&mut stream).await? else {
        return Ok(());
    };

    // 1. Static assets served natively in Rust with zero Python dependency
    if req.method == "GET" && !req.path.starts_with("/api/") {
        if let Some((file_path, is_html)) = resolve_static_asset(&state, &req.path) {
            if let Ok(bytes) = fs::read(&file_path) {
                let mime = mime_type_for_path(&file_path);
                let cache = if is_html {
                    "no-store, no-cache, must-revalidate"
                } else {
                    "public, max-age=300"
                };
                return write_http_response(&mut stream, "200 OK", mime, cache, &bytes).await;
            }
        }
        return write_http_response(
            &mut stream,
            "404 Not Found",
            "text/plain; charset=utf-8",
            "no-store",
            b"Not Found",
        )
        .await;
    }

    // 2. Core Rust-owned API endpoints (fast path in both hybrid and pure-rust modes)
    if req.method == "GET" && req.path == "/api/version" {
        return write_json_response(
            &mut stream,
            "200 OK",
            &json!({
                "success": true,
                "build": state.build,
                "version": format!("Build {}", state.build),
                "edition": state.edition,
                "shell": "spectra-shell-rust",
                "gateway": "rust",
                "pure_rust": state.pure_rust,
            }),
        )
        .await;
    }

    if req.method == "POST" && req.path == "/api/app/heartbeat" {
        state.last_heartbeat_epoch_ms.store(now_epoch_ms(), Ordering::Relaxed);
        return write_json_response(
            &mut stream,
            "200 OK",
            &json!({
                "success": true,
                "status": "ALIVE",
                "gateway": "rust"
            }),
        )
        .await;
    }

    if req.method == "POST" && (req.path == "/api/app/window_closed" || req.path == "/api/app/close") {
        let immediate = serde_json::from_slice::<Value>(&req.body)
            .ok()
            .and_then(|v| v.get("immediate").and_then(|b| b.as_bool()))
            .unwrap_or(false);
        if !immediate {
            return write_json_response(
                &mut stream,
                "200 OK",
                &json!({
                    "success": true,
                    "status": "IGNORED_NATIVE_CONTAINER"
                }),
            )
            .await;
        }
    }

    // 3. Standalone --pure-rust execution (zero Python process required)
    if state.pure_rust {
        return handle_pure_rust_api(&mut stream, &req, &state).await;
    }

    // 4. Hybrid Phase 3 sidecar reverse-proxy for legacy Python-backed routes
    proxy_to_sidecar(&mut stream, &req, &state).await
}

fn resolve_static_asset(state: &GatewayShared, req_path: &str) -> Option<(PathBuf, bool)> {
    let rel = if req_path.is_empty() || req_path == "/" {
        "index.html"
    } else {
        req_path.trim_start_matches('/')
    };

    if matches!(rel, "favicon.ico" | "icon.ico" | "icon.png" | "spectra_logo.svg") {
        let name = if rel == "favicon.ico" { "icon.ico" } else { rel };
        if let Some(p) = sanitize_safe_subpath(&state.app_root, name) {
            return Some((p, false));
        }
    }

    if let Some(p) = sanitize_safe_subpath(&state.dist_root, rel) {
        let is_html = p.extension().and_then(|e| e.to_str()) == Some("html");
        return Some((p, is_html));
    }

    // SPA fallback to web/dist/index.html for client navigation paths without extensions
    if !rel.contains('.') {
        if let Some(idx) = sanitize_safe_subpath(&state.dist_root, "index.html") {
            return Some((idx, true));
        }
    }
    None
}

async fn handle_pure_rust_api(
    stream: &mut TcpStream,
    req: &ParsedHttpRequest,
    state: &GatewayShared,
) -> Result<(), String> {
    if req.method == "GET" && req.path == "/api/ports" {
        let mut ports = SerialTransport::list_ports().unwrap_or_default();
        for demo in [
            "DEMO / SIMULATION (Jura Impressa XJ5)",
            "DEMO / SIMULATION (Jura Z6)",
            "DEMO / SIMULATION (Jura S8)",
            "DEMO / SIMULATION (Jura WE8)",
            "DEMO / SIMULATION (Jura E8)",
            "DEMO / SIMULATION (Jura Z10)",
            "DEMO / SIMULATION (Nivona NICR768)",
        ] {
            ports.push(demo.to_string());
        }
        return write_json_response(stream, "200 OK", &Value::from(ports)).await;
    }

    if req.method == "GET" && req.path == "/api/machines" {
        let params = parse_query_params(&req.query);
        let det_ef = params.get("ef").map(String::as_str).unwrap_or("");
        let det_art = params.get("art").map(String::as_str).unwrap_or("");
        let det_model = params.get("model").map(String::as_str).unwrap_or("");
        let catalog = build_rust_machine_catalog(&state.app_root, det_ef, det_art, det_model);
        return write_json_response(stream, "200 OK", &catalog).await;
    }

    if req.method == "GET" && req.path == "/api/debug/status" {
        let logs: Vec<DebugLogEntry> = state
            .logs
            .lock()
            .map(|g| g.iter().cloned().collect())
            .unwrap_or_default();
        let err_cnt = logs.iter().filter(|l| l.level == "ERROR").count();
        let warn_cnt = logs.iter().filter(|l| l.level == "WARN").count();
        return write_json_response(
            stream,
            "200 OK",
            &json!({
                "success": true,
                "build": state.build,
                "version": format!("Build {}", state.build),
                "diagnostics": {
                    "runtime": "spectra-agent (pure-rust)",
                    "uptime_sec": now_epoch_ms().saturating_sub(state.started_epoch_ms) / 1000,
                    "rust_core": true
                },
                "logs": logs,
                "error_count": err_cnt,
                "warn_count": warn_cnt,
            }),
        )
        .await;
    }

    if req.method == "POST" && req.path == "/api/debug/clear" {
        if let Ok(mut g) = state.logs.lock() {
            g.clear();
        }
        state.push_log("INFO", "DEBUG", "Debug log cleared".into(), String::new());
        return write_json_response(stream, "200 OK", &json!({"success": true})).await;
    }

    if req.method == "POST" && req.path == "/api/debug/client_error" {
        let body: Value = serde_json::from_slice(&req.body).unwrap_or_default();
        let msg = body.get("message").and_then(|v| v.as_str()).unwrap_or("Unknown error").to_string();
        let details = body.get("details").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let source = body.get("source").and_then(|v| v.as_str()).unwrap_or("FRONTEND").to_string();
        state.push_log("ERROR", &source, msg, details);
        return write_json_response(stream, "200 OK", &json!({"success": true})).await;
    }

    if req.method == "POST" && req.path == "/api/command" {
        let body: Value = serde_json::from_slice(&req.body).unwrap_or_default();
        let cmd = body.get("command").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let res = send_jura_command(&state.app_state, cmd, None).await;
        return match res {
            Ok(out) => write_json_response(stream, "200 OK", &json!({"success": true, "response": out})).await,
            Err(err) => write_json_response(stream, "400 Bad Request", &json!({"success": false, "error": err})).await,
        };
    }

    write_json_response(
        stream,
        "501 Not Implemented",
        &json!({
            "success": false,
            "pure_rust": true,
            "error": format!("Endpoint {} requires hybrid sidecar runtime (not running in --pure-rust mode)", req.path)
        }),
    )
    .await
}

fn build_rust_machine_catalog(
    app_root: &Path,
    detected_ef: &str,
    detected_art: &str,
    detected_model: &str,
) -> Value {
    let mut machines = Vec::new();
    let profiles_path = app_root.join("profiles_data.json");
    if let Ok(raw) = fs::read_to_string(profiles_path) {
        if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&raw) {
            for (ef_code, entry) in map {
                let model_family = entry
                    .get("model_family")
                    .and_then(|v| v.as_str())
                    .unwrap_or(&ef_code);
                let matched = matches_connected_machine(
                    &ef_code,
                    &[],
                    model_family,
                    detected_ef,
                    detected_art,
                    detected_model,
                );
                let products: Vec<String> = entry
                    .get("products")
                    .and_then(|v| v.as_array())
                    .map(|arr| {
                        arr.iter()
                            .filter_map(|p| p.get("name").and_then(|n| n.as_str()).map(str::to_string))
                            .collect()
                    })
                    .unwrap_or_default();
                machines.push(json!({
                    "id": ef_code,
                    "ef_code": ef_code,
                    "model_family": model_family,
                    "series": "",
                    "manufacturer": "Jura",
                    "article_numbers": [],
                    "sources": ["Built-in Profile"],
                    "active_source": "Built-in Profile",
                    "has_verified_spec": false,
                    "has_local_override": false,
                    "address_width": 4,
                    "max_words": 512,
                    "product_labels": products,
                    "maintenance_labels": [],
                    "offsets": {"products": [], "maintenance": [], "maintenance_pct": []},
                    "is_connected_match": matched
                }));
            }
        }
    }
    machines.sort_by(|a, b| {
        let ma = a.get("is_connected_match").and_then(|v| v.as_bool()).unwrap_or(false);
        let mb = b.get("is_connected_match").and_then(|v| v.as_bool()).unwrap_or(false);
        mb.cmp(&ma).then_with(|| {
            let ea = a.get("ef_code").and_then(|v| v.as_str()).unwrap_or("");
            let eb = b.get("ef_code").and_then(|v| v.as_str()).unwrap_or("");
            ea.cmp(eb)
        })
    });
    json!({
        "success": true,
        "count": machines.len(),
        "machines": machines,
        "source": "rust-gateway"
    })
}

async fn wait_for_sidecar_port(rx: &mut watch::Receiver<SidecarState>) -> Result<u16, String> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(20);
    loop {
        match rx.borrow().clone() {
            SidecarState::Ready(p) => return Ok(p),
            SidecarState::Failed(err) => return Err(err),
            SidecarState::Disabled => return Err("Sidecar disabled".to_string()),
            SidecarState::Starting => {}
        }
        let now = tokio::time::Instant::now();
        if now >= deadline {
            return Err("Timed out waiting for legacy sidecar backend".to_string());
        }
        let wait_fut = rx.changed();
        match tokio::time::timeout(deadline - now, wait_fut).await {
            Ok(Ok(())) => continue,
            Ok(Err(_)) => return Err("Sidecar coordinator channel closed".to_string()),
            Err(_) => return Err("Timed out waiting for legacy sidecar backend".to_string()),
        }
    }
}

async fn proxy_to_sidecar(
    client_stream: &mut TcpStream,
    req: &ParsedHttpRequest,
    state: &GatewayShared,
) -> Result<(), String> {
    let mut rx = state.sidecar_rx.clone();
    let backend_port = match wait_for_sidecar_port(&mut rx).await {
        Ok(p) => p,
        Err(err) => {
            return write_json_response(
                client_stream,
                "503 Service Unavailable",
                &json!({"success": false, "error": err}),
            )
            .await;
        }
    };

    let mut upstream = match TcpStream::connect(("127.0.0.1", backend_port)).await {
        Ok(s) => s,
        Err(e) => {
            return write_json_response(
                client_stream,
                "502 Bad Gateway",
                &json!({"success": false, "error": format!("Sidecar connect failed: {e}")}),
            )
            .await;
        }
    };

    // Forward HTTP/1.1 request cleanly with Connection: close so upstream closes cleanly at response EOF
    let mut raw_req = format!("{} {} HTTP/1.1\r\nHost: 127.0.0.1:{backend_port}\r\nConnection: close\r\n", req.method, req.target);
    let mut has_len = false;
    for (k, v) in &req.headers {
        if k.eq_ignore_ascii_case("host") || k.eq_ignore_ascii_case("connection") {
            continue;
        }
        if k.eq_ignore_ascii_case("content-length") {
            has_len = true;
        }
        raw_req.push_str(&format!("{k}: {v}\r\n"));
    }
    if !has_len && !req.body.is_empty() {
        raw_req.push_str(&format!("Content-Length: {}\r\n", req.body.len()));
    }
    raw_req.push_str("\r\n");

    upstream.write_all(raw_req.as_bytes()).await.map_err(|e| e.to_string())?;
    if !req.body.is_empty() {
        upstream.write_all(&req.body).await.map_err(|e| e.to_string())?;
    }
    let _ = upstream.flush().await;

    let mut raw_resp = Vec::with_capacity(8192);
    let _ = upstream.read_to_end(&mut raw_resp).await.map_err(|e| e.to_string())?;

    if let Some(head_end) = find_subslice(&raw_resp, b"\r\n\r\n") {
        let head = String::from_utf8_lossy(&raw_resp[..head_end]);
        let body = &raw_resp[head_end + 4..];
        let mut lines = head.split("\r\n");
        let status = lines.next().unwrap_or("HTTP/1.1 200 OK");
        let mut rebuilt = format!("{status}\r\n");
        let mut seen_len = false;
        for hline in lines {
            if let Some((hk, _)) = hline.split_once(':') {
                let hk_t = hk.trim();
                if hk_t.eq_ignore_ascii_case("connection") || hk_t.eq_ignore_ascii_case("transfer-encoding") {
                    continue;
                }
                if hk_t.eq_ignore_ascii_case("content-length") {
                    seen_len = true;
                }
            }
            rebuilt.push_str(hline);
            rebuilt.push_str("\r\n");
        }
        if !seen_len {
            rebuilt.push_str(&format!("Content-Length: {}\r\n", body.len()));
        }
        rebuilt.push_str("Connection: close\r\n\r\n");

        client_stream.write_all(rebuilt.as_bytes()).await.map_err(|e| e.to_string())?;
        client_stream.write_all(body).await.map_err(|e| e.to_string())?;
        let _ = client_stream.flush().await;
    } else if !raw_resp.is_empty() {
        client_stream.write_all(&raw_resp).await.map_err(|e| e.to_string())?;
    } else {
        return write_json_response(
            client_stream,
            "502 Bad Gateway",
            &json!({"success": false, "error": "Empty response from sidecar"}),
        )
        .await;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_temp_app() -> PathBuf {
        let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let root = std::env::temp_dir().join(format!("spectra_gateway_test_{nanos}"));
        let dist = root.join("web").join("dist");
        fs::create_dir_all(&dist).unwrap();
        fs::write(dist.join("index.html"), "<html><body>SPECTRA UI</body></html>").unwrap();
        fs::write(root.join("version.py"), "__build__ = \"20261114.0020\"\n__edition__ = \"Test Edition\"\n").unwrap();
        fs::write(
            root.join("profiles_data.json"),
            r#"{"EF535M":{"model_family":"Jura WE8","products":[{"name":"Espresso"}]}}"#,
        )
        .unwrap();
        root
    }

    async fn http_call(port: u16, req: &str) -> String {
        let mut stream = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
        stream.write_all(req.as_bytes()).await.unwrap();
        let mut resp = Vec::new();
        stream.read_to_end(&mut resp).await.unwrap();
        String::from_utf8_lossy(&resp).into_owned()
    }

    #[tokio::test]
    async fn test_gateway_serves_static_ui_blocks_traversal_and_handles_pure_rust_api() {
        let root = make_temp_app();
        let handle = start_gateway_server(GatewayConfig {
            app_root: root.clone(),
            pure_rust: true,
            bind_port: Some(0),
            ..Default::default()
        })
        .await
        .expect("gateway starts");

        let index = http_call(handle.port, "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n").await;
        assert!(index.starts_with("HTTP/1.1 200 OK"));
        assert!(index.contains("SPECTRA UI"));

        let trav = http_call(handle.port, "GET /../../etc/passwd HTTP/1.1\r\nHost: localhost\r\n\r\n").await;
        assert!(trav.starts_with("HTTP/1.1 404"));

        let ver = http_call(handle.port, "GET /api/version HTTP/1.1\r\nHost: localhost\r\n\r\n").await;
        assert!(ver.contains("\"build\":\"20261114.0020\""));
        assert!(ver.contains("\"gateway\":\"rust\""));

        let hb = http_call(
            handle.port,
            "POST /api/app/heartbeat HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}",
        )
        .await;
        assert!(hb.contains("\"status\":\"ALIVE\""));

        let machines = http_call(
            handle.port,
            "GET /api/machines?ef=ef535m HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )
        .await;
        assert!(machines.contains("Jura WE8"));
        assert!(machines.contains("\"is_connected_match\":true"));

        handle.shutdown();
        let _ = fs::remove_dir_all(&root);
    }

    #[tokio::test]
    async fn test_gateway_hybrid_proxy_waits_for_sidecar_and_forwards() {
        let root = make_temp_app();
        let sidecar = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let sidecar_port = sidecar.local_addr().unwrap().port();
        tokio::spawn(async move {
            if let Ok((mut s, _)) = sidecar.accept().await {
                let mut buf = [0u8; 1024];
                let _ = s.read(&mut buf).await;
                let _ = s
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"from\":\"sidecar\"}")
                    .await;
            }
        });

        let handle = start_gateway_server(GatewayConfig {
            app_root: root.clone(),
            pure_rust: false,
            bind_port: Some(0),
            ..Default::default()
        })
        .await
        .expect("hybrid gateway starts");

        // Trigger sidecar readiness slightly later to test coordination
        handle.set_sidecar_ready(sidecar_port);
        let res = http_call(
            handle.port,
            "GET /api/ai/status HTTP/1.1\r\nHost: localhost\r\n\r\n",
        )
        .await;
        assert!(res.starts_with("HTTP/1.1 200 OK"));
        assert!(res.contains("{\"from\":\"sidecar\"}"));

        handle.shutdown();
        let _ = fs::remove_dir_all(&root);
    }
}
