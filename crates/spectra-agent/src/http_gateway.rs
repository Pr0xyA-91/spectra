//! Phase 3 Embedded Rust HTTP Gateway & Control Plane for SPECTRA.
//!
//! Serves the compiled React frontend (`web/dist/`), native Rust health/version/heartbeat/debug
//! endpoints, and `--pure-rust` hardware routes directly from `spectra-agent`, while cleanly
//! coordinating and reverse-proxying legacy stateful endpoints (`/api/ai/*`, `/api/hmi/*`,
//! `/api/github/*`, `/api/stats`, etc.) to a loopback Python sidecar when hybrid mode is active.

use std::collections::{HashMap, VecDeque};
use std::convert::Infallible;
use std::fs;
use std::net::SocketAddr;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use bytes::Bytes;
use http::{HeaderMap, HeaderName, HeaderValue, Method, Request, Response, StatusCode};
use http_body_util::combinators::BoxBody;
use http_body_util::{BodyExt, Full, Limited};
use hyper::body::Incoming;
use hyper::service::service_fn;
use hyper_util::rt::TokioIo;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{oneshot, watch, Semaphore};

use crate::{send_jura_command, AppState};
use spectra_core::matches_connected_machine;
use spectra_hal::SerialTransport;

const MAX_REQUEST_BODY_BYTES: usize = 16 * 1024 * 1024;
const MAX_DEBUG_LOG_ENTRIES: usize = 500;
const MAX_CONCURRENT_GATEWAY_CONNS: usize = 64;
const GATEWAY_IO_TIMEOUT: Duration = Duration::from_secs(15);
const CONTENT_SECURITY_POLICY: &str = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'";

type GatewayBody = BoxBody<Bytes, Infallible>;

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

#[derive(Clone)]
struct CachedProfileEntry {
    ef_code: String,
    model_family: String,
    products: Vec<String>,
}

struct GatewayShared {
    app_root: PathBuf,
    dist_root: PathBuf,
    gw_port: u16,
    pure_rust: bool,
    build: String,
    edition: String,
    app_state: AppState,
    sidecar_rx: watch::Receiver<SidecarState>,
    last_heartbeat_epoch_ms: AtomicU64,
    started_epoch_ms: u64,
    logs: Mutex<VecDeque<DebugLogEntry>>,
    profiles_cache: OnceLock<Vec<CachedProfileEntry>>,
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
        gw_port: port,
        pure_rust: cfg.pure_rust,
        build,
        edition,
        app_state: AppState::new(),
        sidecar_rx,
        last_heartbeat_epoch_ms: AtomicU64::new(now_ms),
        started_epoch_ms: now_ms,
        logs: Mutex::new(VecDeque::with_capacity(MAX_DEBUG_LOG_ENTRIES)),
        profiles_cache: OnceLock::new(),
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

    let conn_semaphore = Arc::new(Semaphore::new(MAX_CONCURRENT_GATEWAY_CONNS));

    tokio::spawn(async move {
        loop {
            tokio::select! {
                _ = &mut shutdown_rx => break,
                res = listener.accept() => {
                    let Ok((stream, _)) = res else {
                        break;
                    };
                    let Ok(permit) = Arc::clone(&conn_semaphore).try_acquire_owned() else {
                        drop(stream);
                        continue;
                    };
                    let state = Arc::clone(&shared);
                    tokio::spawn(async move {
                        let _permit = permit;
                        let io = TokioIo::new(stream);
                        let svc = service_fn(move |req| {
                            let st = Arc::clone(&state);
                            async move { Ok::<_, Infallible>(handle_request(req, st).await) }
                        });
                        let conn = hyper::server::conn::http1::Builder::new()
                            .timer(hyper_util::rt::TokioTimer::new())
                            .header_read_timeout(GATEWAY_IO_TIMEOUT)
                            .keep_alive(false)
                            .serve_connection(io, svc);
                        let _ = conn.await;
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

    fn cached_profiles(&self) -> &[CachedProfileEntry] {
        self.profiles_cache.get_or_init(|| {
            let mut parsed = Vec::new();
            let profiles_path = self.app_root.join("profiles_data.json");
            if let Ok(raw) = fs::read_to_string(profiles_path) {
                if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&raw) {
                    for (ef_code, entry) in map {
                        let model_family = entry
                            .get("model_family")
                            .and_then(|v| v.as_str())
                            .unwrap_or(&ef_code)
                            .to_string();
                        let products: Vec<String> = entry
                            .get("products")
                            .and_then(|v| v.as_array())
                            .map(|arr| {
                                arr.iter()
                                    .filter_map(|p| p.get("name").and_then(|n| n.as_str()).map(str::to_string))
                                    .collect()
                            })
                            .unwrap_or_default();
                        parsed.push(CachedProfileEntry {
                            ef_code,
                            model_family,
                            products,
                        });
                    }
                }
            }
            parsed
        })
    }
}

fn is_loopback_host(host: &str) -> bool {
    let trimmed = host.trim();
    if trimmed.is_empty() {
        return false;
    }
    let host_only = if let Some(rest) = trimmed.strip_prefix('[') {
        let Some((ip, tail)) = rest.split_once(']') else {
            return false;
        };
        if !tail.is_empty() {
            let Some(port_str) = tail.strip_prefix(':') else {
                return false;
            };
            if port_str.is_empty() || port_str.parse::<u16>().is_err() {
                return false;
            }
        }
        return ip.eq_ignore_ascii_case("::1");
    } else if let Some((h, port_str)) = trimmed.rsplit_once(':') {
        if port_str.is_empty() || port_str.parse::<u16>().is_err() {
            return false;
        }
        h
    } else {
        trimmed
    };

    host_only.eq_ignore_ascii_case("localhost") || host_only == "127.0.0.1"
}

fn extract_loopback_origin_port(raw: &str) -> Option<u16> {
    let trimmed = raw.trim().trim_end_matches('/');
    let rest = trimmed
        .strip_prefix("http://")
        .or_else(|| trimmed.strip_prefix("https://"))?;
    let authority = rest.split('/').next().unwrap_or("");
    if authority.is_empty() || authority.contains('@') {
        return None;
    }
    let (host_only, port_str) = if let Some(rest_v6) = authority.strip_prefix('[') {
        let (ip, tail) = rest_v6.split_once(']')?;
        let port_s = tail.strip_prefix(':')?;
        (ip, port_s)
    } else {
        authority.rsplit_once(':')?
    };
    if !(host_only.eq_ignore_ascii_case("localhost")
        || host_only == "127.0.0.1"
        || host_only.eq_ignore_ascii_case("::1"))
    {
        return None;
    }
    port_str.parse::<u16>().ok()
}

fn is_allowed_origin_for_port(origin: &str, gw_port: u16) -> bool {
    let trimmed = origin.trim().trim_end_matches('/');
    if matches!(
        trimmed,
        "tauri://localhost" | "http://tauri.localhost" | "https://tauri.localhost"
    ) {
        return true;
    }
    let Some(port) = extract_loopback_origin_port(trimmed) else {
        return false;
    };
    if port == gw_port {
        return true;
    }
    if std::env::var("SPECTRA_DEV_CORS").as_deref() == Ok("1") && matches!(port, 5173 | 4173) {
        return true;
    }
    false
}

fn is_allowed_origin(origin: &str, headers: &HeaderMap, gw_port: u16) -> bool {
    let trimmed = origin.trim();
    if trimmed.eq_ignore_ascii_case("null") {
        // Mirror web_server.py: allow `Origin: null` ONLY when browser-enforced headers
        // prove loopback origin (blocks cross-origin sandboxed iframe CSRF).
        if let Some(sec_fetch) = headers.get("sec-fetch-site").and_then(|v| v.to_str().ok()) {
            let s = sec_fetch.trim();
            if s.eq_ignore_ascii_case("same-origin") {
                return true;
            }
            if s.eq_ignore_ascii_case("cross-site") {
                return false;
            }
        }
        if let Some(referer) = headers.get(http::header::REFERER).and_then(|v| v.to_str().ok()) {
            return is_allowed_origin_for_port(referer, gw_port);
        }
        return false;
    }
    is_allowed_origin_for_port(trimmed, gw_port)
}

fn validate_request_security(headers: &HeaderMap, path: &str, gw_port: u16) -> Result<(), Box<Response<GatewayBody>>> {
    let host_ok = headers
        .get(http::header::HOST)
        .and_then(|v| v.to_str().ok())
        .is_some_and(is_loopback_host);

    if !host_ok {
        return Err(Box::new(json_response(
            StatusCode::FORBIDDEN,
            &json!({"success": false, "error": "Forbidden: invalid or missing loopback Host header"}),
        )));
    }

    if path.starts_with("/api/") {
        if let Some(sec_fetch) = headers.get("sec-fetch-site").and_then(|v| v.to_str().ok()) {
            if sec_fetch.trim().eq_ignore_ascii_case("cross-site") {
                return Err(Box::new(json_response(
                    StatusCode::FORBIDDEN,
                    &json!({"success": false, "error": "Forbidden: cross-site API request rejected"}),
                )));
            }
        }
        if let Some(origin) = headers.get(http::header::ORIGIN).and_then(|v| v.to_str().ok()) {
            if !is_allowed_origin(origin, headers, gw_port) {
                return Err(Box::new(json_response(
                    StatusCode::FORBIDDEN,
                    &json!({"success": false, "error": "Forbidden: non-loopback or cross-port Origin rejected"}),
                )));
            }
        }
    }

    Ok(())
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

fn attach_security_headers(headers: &mut HeaderMap) {
    headers.insert(
        HeaderName::from_static("x-content-type-options"),
        HeaderValue::from_static("nosniff"),
    );
    headers.insert(
        HeaderName::from_static("x-frame-options"),
        HeaderValue::from_static("SAMEORIGIN"),
    );
    headers.insert(
        HeaderName::from_static("content-security-policy"),
        HeaderValue::from_static(CONTENT_SECURITY_POLICY),
    );
}

fn bytes_response(
    status: StatusCode,
    content_type: &'static str,
    cache_control: &'static str,
    body: Bytes,
) -> Response<GatewayBody> {
    let mut resp = Response::new(Full::new(body).map_err(|never| match never {}).boxed());
    *resp.status_mut() = status;
    let headers = resp.headers_mut();
    headers.insert(
        http::header::CONTENT_TYPE,
        HeaderValue::from_static(content_type),
    );
    headers.insert(
        http::header::CACHE_CONTROL,
        HeaderValue::from_static(cache_control),
    );
    attach_security_headers(headers);
    resp
}

fn json_response(status: StatusCode, val: &Value) -> Response<GatewayBody> {
    let body = serde_json::to_vec(val).unwrap_or_else(|_| b"{}".to_vec());
    bytes_response(
        status,
        "application/json; charset=utf-8",
        "no-store",
        Bytes::from(body),
    )
}

fn mime_type_for_path(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
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

async fn read_limited_body(body: Incoming) -> Result<Bytes, Box<Response<GatewayBody>>> {
    let limited = Limited::new(body, MAX_REQUEST_BODY_BYTES);
    match limited.collect().await {
        Ok(collected) => Ok(collected.to_bytes()),
        Err(err) => {
            let msg = err.to_string();
            if msg.contains("length limit exceeded") {
                Err(Box::new(json_response(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    &json!({"success": false, "error": "Request body exceeds 16 MiB limit"}),
                )))
            } else {
                Err(Box::new(json_response(
                    StatusCode::BAD_REQUEST,
                    &json!({"success": false, "error": format!("Invalid request body: {msg}")}),
                )))
            }
        }
    }
}

async fn handle_request(req: Request<Incoming>, state: Arc<GatewayShared>) -> Response<GatewayBody> {
    let path_raw = req.uri().path().to_string();
    let path = percent_decode(&path_raw);
    let query = req.uri().query().unwrap_or("").to_string();
    let target = req
        .uri()
        .path_and_query()
        .map(|pq| pq.as_str().to_string())
        .unwrap_or_else(|| "/".to_string());
    let method = req.method().clone();

    if let Err(resp) = validate_request_security(req.headers(), &path, state.gw_port) {
        return *resp;
    }

    if let Some(content_len) = req
        .headers()
        .get(http::header::CONTENT_LENGTH)
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<usize>().ok())
    {
        if content_len > MAX_REQUEST_BODY_BYTES {
            return json_response(
                StatusCode::PAYLOAD_TOO_LARGE,
                &json!({"success": false, "error": "Request body exceeds 16 MiB limit"}),
            );
        }
    }

    // 1. Static assets served natively in Rust with zero Python dependency
    if method == Method::GET && !path.starts_with("/api/") {
        if let Some((file_path, is_html)) = resolve_static_asset(&state, &path) {
            if let Ok(bytes) = tokio::fs::read(&file_path).await {
                let mime = mime_type_for_path(&file_path);
                let cache = if is_html {
                    "no-store, no-cache, must-revalidate"
                } else {
                    "public, max-age=300"
                };
                return bytes_response(StatusCode::OK, mime, cache, Bytes::from(bytes));
            }
        }
        return bytes_response(
            StatusCode::NOT_FOUND,
            "text/plain; charset=utf-8",
            "no-store",
            Bytes::from_static(b"Not Found"),
        );
    }

    // 2. Core Rust-owned API endpoints (fast path in both hybrid and pure-rust modes)
    if method == Method::GET && path == "/api/version" {
        return json_response(
            StatusCode::OK,
            &json!({
                "success": true,
                "build": state.build,
                "version": format!("Build {}", state.build),
                "edition": state.edition,
                "shell": "spectra-shell-rust",
                "gateway": "rust",
                "pure_rust": state.pure_rust,
            }),
        );
    }

    if method == Method::POST && path == "/api/app/heartbeat" {
        state
            .last_heartbeat_epoch_ms
            .store(now_epoch_ms(), Ordering::Relaxed);
        return json_response(
            StatusCode::OK,
            &json!({
                "success": true,
                "status": "ALIVE",
                "gateway": "rust"
            }),
        );
    }

    if method == Method::POST && (path == "/api/app/window_closed" || path == "/api/app/close") {
        let req_headers = req.headers().clone();
        let body_bytes = match read_limited_body(req.into_body()).await {
            Ok(b) => b,
            Err(resp) => return *resp,
        };
        let immediate = serde_json::from_slice::<Value>(&body_bytes)
            .ok()
            .and_then(|v| v.get("immediate").and_then(|b| b.as_bool()))
            .unwrap_or(false);
        if !immediate {
            return json_response(
                StatusCode::OK,
                &json!({
                    "success": true,
                    "status": "IGNORED_NATIVE_CONTAINER"
                }),
            );
        }
        if state.pure_rust {
            return handle_pure_rust_api(method, &path, &query, &body_bytes, &state).await;
        }
        return proxy_to_sidecar(method, &target, &req_headers, body_bytes, &state).await;
    }

    // 3. Standalone --pure-rust execution (zero Python process required)
    if state.pure_rust {
        let body_bytes = match read_limited_body(req.into_body()).await {
            Ok(b) => b,
            Err(resp) => return *resp,
        };
        return handle_pure_rust_api(method, &path, &query, &body_bytes, &state).await;
    }

    // 4. Hybrid Phase 3 sidecar reverse-proxy for legacy Python-backed routes (streams upstream body)
    let req_headers = req.headers().clone();
    let body_bytes = match read_limited_body(req.into_body()).await {
        Ok(b) => b,
        Err(resp) => return *resp,
    };
    proxy_to_sidecar(method, &target, &req_headers, body_bytes, &state).await
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
    method: Method,
    path: &str,
    query: &str,
    body_bytes: &[u8],
    state: &GatewayShared,
) -> Response<GatewayBody> {
    if method == Method::GET && path == "/api/ports" {
        let mut ports = tokio::task::spawn_blocking(SerialTransport::list_ports)
            .await
            .ok()
            .and_then(Result::ok)
            .unwrap_or_default();
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
        return json_response(StatusCode::OK, &Value::from(ports));
    }

    if method == Method::GET && path == "/api/machines" {
        let params = parse_query_params(query);
        let det_ef = params.get("ef").map(String::as_str).unwrap_or("");
        let det_art = params.get("art").map(String::as_str).unwrap_or("");
        let det_model = params.get("model").map(String::as_str).unwrap_or("");
        let catalog = build_rust_machine_catalog(state, det_ef, det_art, det_model);
        return json_response(StatusCode::OK, &catalog);
    }

    if method == Method::GET && path == "/api/debug/status" {
        let logs: Vec<DebugLogEntry> = state
            .logs
            .lock()
            .map(|g| g.iter().cloned().collect())
            .unwrap_or_default();
        let err_cnt = logs.iter().filter(|l| l.level == "ERROR").count();
        let warn_cnt = logs.iter().filter(|l| l.level == "WARN").count();
        return json_response(
            StatusCode::OK,
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
        );
    }

    if method == Method::POST && path == "/api/debug/clear" {
        if let Ok(mut g) = state.logs.lock() {
            g.clear();
        }
        state.push_log("INFO", "DEBUG", "Debug log cleared".into(), String::new());
        return json_response(StatusCode::OK, &json!({"success": true}));
    }

    if method == Method::POST && path == "/api/debug/client_error" {
        let body: Value = serde_json::from_slice(body_bytes).unwrap_or_default();
        let msg = body
            .get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("Unknown error")
            .to_string();
        let details = body
            .get("details")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let source = body
            .get("source")
            .and_then(|v| v.as_str())
            .unwrap_or("FRONTEND")
            .to_string();
        state.push_log("ERROR", &source, msg, details);
        return json_response(StatusCode::OK, &json!({"success": true}));
    }

    if method == Method::POST && path == "/api/command" {
        let body: Value = match serde_json::from_slice(body_bytes) {
            Ok(v) => v,
            Err(e) => {
                return json_response(
                    StatusCode::BAD_REQUEST,
                    &json!({"success": false, "error": format!("Invalid JSON body: {e}")}),
                );
            }
        };
        let Some(cmd) = body.get("command").and_then(|v| v.as_str()).map(str::to_string) else {
            return json_response(
                StatusCode::BAD_REQUEST,
                &json!({"success": false, "error": "Missing string 'command' field"}),
            );
        };
        let res = send_jura_command(&state.app_state, cmd, None).await;
        return match res {
            Ok(out) => json_response(StatusCode::OK, &json!({"success": true, "response": out})),
            Err(err) => json_response(
                StatusCode::BAD_REQUEST,
                &json!({"success": false, "error": err}),
            ),
        };
    }

    json_response(
        StatusCode::NOT_IMPLEMENTED,
        &json!({
            "success": false,
            "pure_rust": true,
            "error": format!("Endpoint {} requires hybrid sidecar runtime (not running in --pure-rust mode)", path)
        }),
    )
}

fn build_rust_machine_catalog(
    state: &GatewayShared,
    detected_ef: &str,
    detected_art: &str,
    detected_model: &str,
) -> Value {
    let mut machines = Vec::new();
    for entry in state.cached_profiles() {
        let matched = matches_connected_machine(
            &entry.ef_code,
            &[],
            &entry.model_family,
            detected_ef,
            detected_art,
            detected_model,
        );
        machines.push(json!({
            "id": entry.ef_code,
            "ef_code": entry.ef_code,
            "model_family": entry.model_family,
            "series": "",
            "manufacturer": "Jura",
            "article_numbers": [],
            "sources": ["Built-in Profile"],
            "active_source": "Built-in Profile",
            "has_verified_spec": false,
            "has_local_override": false,
            "address_width": 4,
            "max_words": 512,
            "product_labels": entry.products,
            "maintenance_labels": [],
            "offsets": {"products": [], "maintenance": [], "maintenance_pct": []},
            "is_connected_match": matched
        }));
    }
    machines.sort_by(|a, b| {
        let ma = a
            .get("is_connected_match")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let mb = b
            .get("is_connected_match")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
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
    method: Method,
    target: &str,
    req_headers: &HeaderMap,
    body_bytes: Bytes,
    state: &GatewayShared,
) -> Response<GatewayBody> {
    let mut rx = state.sidecar_rx.clone();
    let backend_port = match wait_for_sidecar_port(&mut rx).await {
        Ok(p) => p,
        Err(err) => {
            return json_response(
                StatusCode::SERVICE_UNAVAILABLE,
                &json!({"success": false, "error": err}),
            );
        }
    };

    let stream = match tokio::time::timeout(
        GATEWAY_IO_TIMEOUT,
        TcpStream::connect(("127.0.0.1", backend_port)),
    )
    .await
    {
        Ok(Ok(s)) => s,
        Ok(Err(e)) => {
            return json_response(
                StatusCode::BAD_GATEWAY,
                &json!({"success": false, "error": format!("Sidecar connect failed: {e}")}),
            );
        }
        Err(_) => {
            return json_response(
                StatusCode::GATEWAY_TIMEOUT,
                &json!({"success": false, "error": "Sidecar connect timed out"}),
            );
        }
    };

    let io = TokioIo::new(stream);
    let (mut sender, conn) = match tokio::time::timeout(
        GATEWAY_IO_TIMEOUT,
        hyper::client::conn::http1::handshake(io),
    )
    .await
    {
        Ok(Ok(parts)) => parts,
        Ok(Err(e)) => {
            return json_response(
                StatusCode::BAD_GATEWAY,
                &json!({"success": false, "error": format!("Sidecar HTTP handshake failed: {e}")}),
            );
        }
        Err(_) => {
            return json_response(
                StatusCode::GATEWAY_TIMEOUT,
                &json!({"success": false, "error": "Sidecar HTTP handshake timed out"}),
            );
        }
    };

    tokio::spawn(async move {
        let _ = conn.await;
    });

    let mut builder = Request::builder().method(method).uri(target);
    for (k, v) in req_headers {
        if k == http::header::HOST
            || k == http::header::CONNECTION
            || k == http::header::TRANSFER_ENCODING
            || k == http::header::CONTENT_LENGTH
        {
            continue;
        }
        builder = builder.header(k, v);
    }
    if let Ok(host_val) = HeaderValue::from_str(&format!("127.0.0.1:{backend_port}")) {
        builder = builder.header(http::header::HOST, host_val);
    }
    builder = builder.header(http::header::CONNECTION, "close");

    let upstream_req = match builder.body(Full::new(body_bytes)) {
        Ok(r) => r,
        Err(e) => {
            return json_response(
                StatusCode::BAD_REQUEST,
                &json!({"success": false, "error": format!("Invalid upstream request: {e}")}),
            );
        }
    };

    let upstream_resp = match tokio::time::timeout(
        GATEWAY_IO_TIMEOUT,
        sender.send_request(upstream_req),
    )
    .await
    {
        Ok(Ok(r)) => r,
        Ok(Err(e)) => {
            return json_response(
                StatusCode::BAD_GATEWAY,
                &json!({"success": false, "error": format!("Sidecar request failed: {e}")}),
            );
        }
        Err(_) => {
            return json_response(
                StatusCode::GATEWAY_TIMEOUT,
                &json!({"success": false, "error": "Sidecar response headers timed out"}),
            );
        }
    };

    // Stream upstream response frames directly back to the caller without unbounded buffering
    let (mut parts, body) = upstream_resp.into_parts();
    parts.headers.remove(http::header::CONNECTION);
    parts.headers.remove(http::header::TRANSFER_ENCODING);
    attach_security_headers(&mut parts.headers);
    let streamed_body: GatewayBody = UpstreamStreamBody(body).boxed();
    Response::from_parts(parts, streamed_body)
}

struct UpstreamStreamBody(Incoming);

impl hyper::body::Body for UpstreamStreamBody {
    type Data = Bytes;
    type Error = Infallible;

    fn poll_frame(
        mut self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Option<Result<hyper::body::Frame<Self::Data>, Self::Error>>> {
        match std::pin::Pin::new(&mut self.0).poll_frame(cx) {
            std::task::Poll::Ready(Some(Ok(frame))) => std::task::Poll::Ready(Some(Ok(frame))),
            std::task::Poll::Ready(Some(Err(_))) | std::task::Poll::Ready(None) => {
                std::task::Poll::Ready(None)
            }
            std::task::Poll::Pending => std::task::Poll::Pending,
        }
    }

    fn is_end_stream(&self) -> bool {
        self.0.is_end_stream()
    }

    fn size_hint(&self) -> hyper::body::SizeHint {
        self.0.size_hint()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

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
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 18\r\n\r\n{\"from\":\"sidecar\"}")
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

    #[tokio::test]
    async fn test_gateway_security_host_origin_and_bad_json() {
        let root = make_temp_app();
        let handle = start_gateway_server(GatewayConfig {
            app_root: root.clone(),
            pure_rust: true,
            bind_port: Some(0),
            ..Default::default()
        })
        .await
        .expect("gateway starts");

        let rebind = http_call(
            handle.port,
            "GET /api/version HTTP/1.1\r\nHost: evil.attacker.example:8080\r\n\r\n",
        )
        .await;
        assert!(rebind.starts_with("HTTP/1.1 403 Forbidden"));

        let cross_site = http_call(
            handle.port,
            "POST /api/command HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nSec-Fetch-Site: cross-site\r\nContent-Length: 16\r\n\r\n{\"command\":\"TY:\"}",
        )
        .await;
        assert!(cross_site.starts_with("HTTP/1.1 403 Forbidden"));

        let bad_origin = http_call(
            handle.port,
            "POST /api/command HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nOrigin: https://evil.example\r\nContent-Length: 16\r\n\r\n{\"command\":\"TY:\"}",
        )
        .await;
        assert!(bad_origin.starts_with("HTTP/1.1 403 Forbidden"));

        let null_origin_bare = http_call(
            handle.port,
            "POST /api/command HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nOrigin: null\r\nContent-Length: 16\r\n\r\n{\"command\":\"TY:\"}",
        )
        .await;
        assert!(null_origin_bare.starts_with("HTTP/1.1 403 Forbidden"));

        let null_origin_same_site = http_call(
            handle.port,
            "GET /api/version HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nOrigin: null\r\nSec-Fetch-Site: same-origin\r\n\r\n",
        )
        .await;
        assert!(null_origin_same_site.starts_with("HTTP/1.1 200 OK"));

        let gw_port = handle.port;
        let null_origin_loopback_ref = http_call(
            gw_port,
            &format!(
                "GET /api/version HTTP/1.1\r\nHost: 127.0.0.1:{gw_port}\r\nOrigin: null\r\nReferer: http://127.0.0.1:{gw_port}/\r\n\r\n"
            ),
        )
        .await;
        assert!(null_origin_loopback_ref.starts_with("HTTP/1.1 200 OK"));

        let cross_port_origin = http_call(
            gw_port,
            &format!(
                "POST /api/command HTTP/1.1\r\nHost: 127.0.0.1:{gw_port}\r\nOrigin: http://127.0.0.1:59999\r\nContent-Length: 16\r\n\r\n{{\"command\":\"TY:\"}}"
            ),
        )
        .await;
        assert!(cross_port_origin.starts_with("HTTP/1.1 403 Forbidden"));

        let bad_json = http_call(
            handle.port,
            "POST /api/command HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nContent-Length: 4\r\n\r\n{bad",
        )
        .await;
        assert!(bad_json.starts_with("HTTP/1.1 400 Bad Request"));
        assert!(bad_json.contains("Invalid JSON body"));

        handle.shutdown();
        let _ = fs::remove_dir_all(&root);
    }
}
