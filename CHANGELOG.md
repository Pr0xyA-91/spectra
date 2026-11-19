# SPECTRA Diagnostics Suite — Changelog

All notable changes and architectural milestones for SPECTRA are documented here.
In accordance with SPECTRA edition guidelines, releases are identified strictly by **Build Numbers** (`Build YYYYMMDD.HHMM`).

---

## 📦 Public Release Delta Summary (Since Last Public Sync)

> Comparing **`Build 20261116.1639`** against the previous public snapshots:
> - **Linux (`public/main`)**: Last synced at **`Build 20261114.0020`**
> - **Windows (`public/windows`)**: Last synced at **`Build 20261114.0020`**
>
> **Summary of Major Capabilities Added Since Public Sync**:
> 1. **Czech UI Localization (`web/src/i18n/translations.js`, `ConfigModal.jsx`, `gui_widgets.py`, `spectra_ai.py`)**: Full Czech secondary language translation across the entire SPECTRA workstation (keeping developer-oriented `08 // MEM MAPPER` in English), instant `Language / Jazyk` toggle inside `CONFIG`, Czech service inspection certificate HTML, and Czech Local AI bench triage / customer summary prompts.
> 2. **Interactive First-Run & Refresher Guide (`InteractiveGuideModal.jsx`)**: 7-step bilingual walkthrough popping up on first launch with an inline language quick-picker, live interactive actions (`DEMO` port switch, `⚡ INTERROGATE`, tab peeks, AI setup jump, Offset Calibrator jump), and a `CONFIG` reminder + startup toggle to relaunch anytime.
> 3. **Simple Czech Operator Guide (`docs/USER_GUIDE_CS.md`)**: Beginner-friendly Czech manual focused on basic operation, connecting Local AI, and fixing wrong drink counters via CSV/screenshot offset calibration.

---

## [Build 20261119.1612] — 2026-11-19

### 🛡️ Linux Loopback / WebKitGTK `POST /api/ui_prefs` 403 Fix
- **Loopback & Native WebView Origin Validation (`web_server.py`, `App.jsx`)**:
  - Fixed false-positive `HTTP 403` on local Linux `POST /api/ui_prefs` (and other local POST endpoints) caused by overly narrow hardcoded origin ports (`8080`/`5173`) and Linux WebKitGTK (`WebKit2`) / IPv6 `[::1]` / fallback loopback port headers.
  - Upgraded `_allowed_origins()` and added `_is_loopback_origin()` + `_is_allowed_post_origin()` to allow genuine loopback origins (`127.0.0.1`, `localhost`, `[::1]` on any local port, `self.server.server_port`, and `tauri://localhost`) plus WebKitGTK `Origin: null` ONLY when browser-enforced `Sec-Fetch-Site: same-origin` or loopback `Referer` proves same-origin (still blocking foreign cross-site `Origin: null` sandboxed iframes with `403`).
  - Added structured `SECURITY` warning logging of rejected `Origin`, `Host`, `Referer`, and `Sec-Fetch-Site` headers whenever a `403` occurs, and removed unnecessary `keepalive: true` from interactive `POST /api/ui_prefs` in `App.jsx`.

---

## [Build 20261119.1552] — 2026-11-19

### 📡 Tab 02 Device-Aware Telemetry, Capabilities Contract & Raw Frame Inspector
- **Backend `capabilities` & `raw_frames` Contract (`stats_collector.py`, `drivers/nivona/driver.py`, `drivers/lamanti_kl/driver.py`, `drivers/lamanti_jn/driver.py`, `web_server.py`)**:
  - Emits explicit `capabilities` (`vendor`, `topology`, `ef_code`, `has_live_frame`, `has_coffee_temp`, `has_steam_temp`, `has_flowmeter`, `has_bu_encoder`, `has_valve_state`, `has_as_shunt`, etc.) and tokenized `raw_frames` (`HZ:`, `@TF:`, Modbus RTU registers, Jetinno heartbeat bytes) across all supported protocols.
  - Eliminated fake healthy defaults when real hardware returns no reply (`HZ:` missing on Jura, Modbus timeout on Kalerm, heartbeat timeout on Jetinno, missing frame on Nivona) — now honestly reports `NO FRAME` / `None`.
  - Made `GET /api/sensors` vendor-aware (detecting Nivona, Kalerm/Lamanti-KL, and Jetinno/Lamanti-JN automatically) with normalized timestamps.
- **Device-Aware Digital Twin Schematic (`DigitalTwinSchematic.jsx`)**:
  - Dynamically switches schematic topology & component bindings across 6 machine layouts: Jura Single-Heater, Jura Dual-Heater (renders live **TB2 Steam Thermoblock**), Jura Smart Connect (`@TF:` live switches + honest muted `N/A (@-PROTO)` badges on unexposed nodes), Nivona ASCII, Kalerm Dual-Boiler (with Service Door & Grounds Box), and Jetinno Vending (Mains Inlet, Brew Pump Bar Pressure, Espresso & Instant Boilers, Cabinet Door, Cup Sensor).
  - Replaced hardcoded `PORTS: ONLINE` and hardcoded `"Safety interlocking verified..."` inspector text with real live protocol/frame/fault status.
- **Oscilloscope & Tab 02 Hardening (`OscilloscopeStripChart.jsx`, `SpectraWorkspace.jsx`, `RawFrameInspector.jsx`)**:
  - Auto-clears oscilloscope traces and bus event stream on port switches, right-aligns samples to `Now` using real elapsed timestamps, and displays a clear protocol notice on Smart Connect (`@TF:`-only) machines.
  - Conditionally renders the `AS:` NTC Shunt self-test card only on machines that support `AS:`, fixed the `beansOk === null` false `FILL BEANS` badge, and switched switch/register headers to live dynamic counts.
  - Added collapsible **Live Raw Telemetry Frame Inspector** (`RawFrameInspector.jsx`) with per-token live change highlighting (amber pulse when any raw field flips) and 1-click **Copy Frame Snapshot** JSON export for multi-device bench mapping.

---

## [Build 20261119.1528] — 2026-11-19

### 🚩 GitHub Issue Reporting, Live Activity Status & Operator UX
- **In-App GitHub Issue Reporter (`IssueReportModal.jsx`, `github_auth.py`, `web_server.py`, `SpectraWorkspace.jsx`)**:
  - Added a **Report Issue (`ISSUE` / `NAHLÁSIT`)** button at the end of the top control bar immediately after the Debug toggle (`🐞`).
  - Supports categories (`Bug Report`, `Machine / Protocol`, `Feature Request`, `UI / Translation`), optional sanitized SPECTRA build/OS/machine context, and opt-in sanitized recent debug log tail (automatically redacting GitHub tokens and local user home paths).
  - Submits directly to `Pr0xyA-91/spectra` via `POST /api/github/report_issue` when signed in (with HTTP `422` label fallback), and offers a 1-click pre-filled browser submission fallback when unauthenticated.
- **Dynamic Live SPECTRA Activity Status Pill (`SpectraWorkspace.jsx`)**:
  - Replaced the static `ONLINE` badge with a live **SPECTRA Activity Pill** beside the `BUILD` badge reflecting real-time operational state (`READING %`, `UPDATING %`, `RECONNECTING`, `CAPTURING EEPROM`, `MAPPING EEPROM`, `AI WORKING`, `PULLING AI MODEL`, `GITHUB SYNC`, `EXPORTING`, `CHECKING UPDATES`, `COMM ERROR`, `MONITORING`, `READY`, `IDLE`).
- **Fixed Language Preset Persistence Across Restarts (`App.jsx`, `web_server.py`)**:
  - Fixed a mount-time race condition where `App.jsx` wrote the default `'en'` to `localStorage` before `GET /api/ui_prefs` resolved, causing saved Czech (`cs`) preferences on disk to be ignored on fresh WebView/port startups.
  - Made `save_ui_prefs()` hold `_ui_prefs_lock` across the entire read-modify-write cycle using thread-unique atomic temp files so concurrent `lang` and `onboarding_seen` writes never clobber each other.
- **Custom Ticket Number / Filename Prefix on Diagnostic Exports (`SpectraWorkspace.jsx`, `web_server.py`)**:
  - Added an optional **Ticket Number / Filename Prefix** input with live sanitized filename preview inside the Export Modal.
  - Added cross-platform `sanitize_filename_prefix()` and `build_export_filename()` (diacritic transliteration, path-traversal stripping, Windows reserved-name protection) wired into `GET /api/export` (JSON, CSV, TXT, capture) and `POST /api/export_capture`.

---

## [Build 20261119.1125] — 2026-11-19

### 🔌 Hardware Bridge / Smart Connect & Protocol Engine Fixes
- **Official JURA USB Service Interface Auto-Detection (`serial_io.py`)**:
  - Added `encrypted_wire_mode` auto-detection (`raw_frame` vs. `wire_4to1_frame`) in `query_encrypted()` so hardware 4:1 bridge probes (such as the official JURA USB Service Interface box) send raw `&`-frames instead of double-encoding 4:1 (`16:1`), while direct TTL adapters continue using 4:1 wire framing with `8 ms` inter-byte pacing.
  - Replaced offset-0 echo stripping with substring echo matching (`rx.find(tx)`), added `_scan_decrypted_frames()` advancing safely past stray `&` bytes, short-circuited ASCII fallback on active Smart Connect links, and hardened Windows `pyserial` disconnect handling to close stale file descriptors immediately.
- **Correct Smart Connect EEPROM Bank Stride & Fast-Fail Sweeps (`stats_collector.py`, `memory_mapper.py`, `spectra_probe.py`, `drivers/jura/driver.py`, `web_server.py`)**:
  - Fixed Mode B `@TR:32,NN` bank stride from `bank * 16` to `bank * 4` (4 words per 8-byte bank) across `stats_collector.py`, `memory_mapper.py`, and `spectra_probe.py`.
  - Upgraded `MemoryMapperEngine.sweep_block()` (used by `08 // MEM MAPPER`) to automatically fall back to Smart Connect 4-bank reads (`16` words/block) when block 0 ASCII fails, and emit `abort_sweep` / `end_of_table` after 2 consecutive unresponsive blocks (~4 s instead of 131+ s hangs).
  - Fixed `UnboundLocalError` on `parts` when `HZ:` returns `None`, guarded `apply_local_offset_override` against `RE:` reads on Smart Connect, clamped maintenance percentages to `0..100`, and made Mode A `RT:` parsing case-insensitive with `ValueError` guards.
- **Rust Core & HAL Alignment (`crates/spectra-core/src/jura.rs`, `crates/spectra-hal/src/lib.rs`, `crates/spectra-hal/src/serial.rs`)**:
  - Fixed `SmartConnectCipher::build_frame()` framing (`key` prefix + `\r\n`), added `unescape_frame()` + `decode_frame()`, aligned `build_read_block_frame()` (`@TR:32,NN`) and `BASE_MASK` (`0xDB`), added UTF-8 `is_ascii()` guards on ASCII parsers, and added `tokio::time::timeout` around `SerialTransport::write_raw()`.

### 🛡️ Security, Concurrency & Frontend Stability Hardening
- **Web Server Security & Thread Safety (`web_server.py`)**:
  - Blocked directory traversal in `_serve_static()` via `unquote()` + `os.path.realpath()` containment against `DIST_DIR` (`403 Forbidden`), enforced `Origin` allowlist checks (removing `"null"`) on `POST` requests (`403`), enforced strict JSON object validation (`400`), hardened `COM` port validation regex, enforced `~/Downloads` containment on API-supplied HMI output paths (`403`), and replaced wildcard CORS on `/api/export` with `_send_security_headers()`.
  - Synchronized `_last_stats_cache` and `_last_sensor_payload` reads/mutations under `_session_lock`, switched `get_debug_diagnostics()` to a `50 ms` timed lock (reporting `BUSY` during hardware I/O instead of stalling), wrapped `/api/export` captures in `long_hardware_operation()`, fixed `_deferred_exit_if_not_reloaded()` heartbeat lookup, and added structured `try/except` error responses across threshold and mapper endpoints.
- **Self-Updater & Auth Supply-Chain Hardening (`updater.py`, `github_auth.py`)**:
  - Enforced mandatory SHA-256 verification (`require_sha256=True`) on Windows updater binaries by backfilling release checksums from the manifest, enforced HTTPS + GitHub host allowlist (`_validate_download_url`) and `Content-Length` completeness checks, blocked symlinks/hardlinks/device nodes in `_safe_extract_tarball()`, and locked update cache state under `_state_lock`.
  - Made token persistence atomic (`0o600` temp file + `os.replace`), parsed `HTTPError` JSON bodies in `poll_device_flow()`, and ensured `get_auth_status()` returns `authenticated: False` on any token validation failure.
- **Local AI, Profiles DB & Community Calibration Verification (`spectra_ai.py`, `profiles_db.py`, `contrib/sync_community_calibrations.py`)**:
  - Removed duplicate `_merge_joe_dicts` / `extract_joe_from_text_with_ai` definitions, fixed `_parse_counters_from_ocr_text` `NameError`, validated screenshot base64 early, tightened Ollama model tag matching (`:`), and kept models warm across upload extraction + EEPROM correlation (`auto_unload=False`).
  - Added thread-safe `_CACHE_LOCK` + deep-copy returns + `invalidate_model_specs_cache()` in `profiles_db.py`.
  - Required matching positive-integer `eeprom_words` proof for every product/maintenance offset in `verify_calibration_patch()`, hardened `_issue_has_pr_marker()` to fail closed on API errors, and escaped Markdown table cells (`_md_cell`).
- **Frontend Stability (`web/src/components/MemMapperTab.jsx`, `web/src/components/SpectraWorkspace.jsx`)**:
  - Added `AbortController` sweep cancellation + `activePortRef` cross-port guards across sweeps, sensors, and interrogations; paused background polling during live-diff/raw-sensor reads; stopped `handleFullSweep` early on `abort_sweep`/`end_of_table`; fixed update timer leaks and duplicate `/api/ai/status` refetches; and added 3-retry transient network tolerance to GitHub Device Flow polling.

---

## [Build 20261118.2220] — 2026-11-18

### 🔌 Smart Connect / 4:1 Wire Auto-Detection, Mode B Fallback & EEPROM Fixes
- **3-Mode Physical Transport Auto-Detection & Echo Stripping (`serial_io.py`)**:
  - Added 3-mode physical transport auto-detection (`raw_ascii`, `wire_4to1_ascii`, `smart_connect`) and optical loopback echo stripping across `query_ascii()` and `query_encrypted()`, enabling seamless switching between plain ASCII service ports, 4:1 wire-encoded ASCII ports, and `@`-cipher Smart Connect links.
- **Mode A Fast-Fail & Mode B `@T0..@TR:32` Fallback (`stats_collector.py`, `drivers/jura/driver.py`)**:
  - Added fast-fail detection on `RT:` timeouts or all-zero `RT:` responses with automatic fallback to Mode B (`@T0..@TR:32`), populating `self.last_eeprom` completely and applying local offset overrides in Mode B (`JuraStatsSession` & `JuraDriver`).
- **Live Sensor Polling Fixes (`stats_collector.py`)**:
  - Fixed `has_commercial_bean_sensor` `NameError` on Poll #1 in `query_live_sensors()`, prevented `_cached_ef = ""` from flipping Poll #2+ back to ASCII on Smart Connect sessions, and fixed Smart Connect demo override handling.
- **Memory Mapper & Probe Fallbacks (`memory_mapper.py`, `spectra_probe.py`)**:
  - Added `RE:` fast-fail detection and Smart Connect `@TR:32,00..1F` sweep fallback in `MemoryMapperEngine` and `spectra_probe.sweep_eeprom()`.
- **Command Injector `@`-Command Routing (`web_server.py`)**:
  - Routed read-only `@`-commands sent to `/api/command` through `query_encrypted()`.
- **Regression Coverage (`test_smart_connect_and_wire_fixes.py`)**:
  - Added unit test suite covering Smart Connect Poll #1/Poll #2+, Mode A -> Mode B fallback, optical echo stripping, 4:1 wire ASCII auto-detection, and `RE:` fast-fail sweeps.

---

## [Build 20261117.1320] — 2026-11-17

### 🤖 Local AI Model Detection, Toggle Guard & Persistent Onboarding Preferences
- **On-Disk Ollama Model Discovery (`hmi_inspector.py`)**: Added `_discover_local_ollama_models_on_disk()` scanning local Ollama manifest directories (`OLLAMA_MODELS`, `~/.ollama/models/manifests`, `~/.local/share/spectra/ollama/...`, `%USERPROFILE%\.ollama\...`, `%LOCALAPPDATA%\SPECTRA\ollama\...`) and merging them into `check_local_ollama()` / `get_ai_system_status()` so installed models are reported accurately even when the local daemon (`127.0.0.1:11434`) is stopped.
- **Local AI Activation Guard & Guided Installer Popup (`spectra_ai.py`, `web_server.py`, `SpectraWorkspace.jsx`, `ConfigModal.jsx`, `HmiInspectorTab.jsx`)**: Prevented enabling Local AI when 0 models are installed (`require_installed_model=True`), added a bilingual guided popup modal (`Download <model> & Enable AI`) when attempting to activate AI without a model, and added an inline prompt + 1-click `Pull <model> Now` button whenever an unpulled model is selected.
- **Persistent Onboarding Guide & Language Preferences (`spectra_app.py`, `web_server.py`, `App.jsx`, `SpectraWorkspace.jsx`)**: Replaced the ephemeral `mkdtemp` Chromium profile in `run_chromeless_app_window()` with persistent `~/.config/spectra/browser_profile` (`%LOCALAPPDATA%\SPECTRA\browser_profile` on Windows) and added host-level `~/.config/spectra/ui_prefs.json` (`/api/ui_prefs` + `/api/version`) so interactive guide completion and language selection persist across restarts and ports.

---

## [Build 20261117.1112] — 2026-11-17

### 🛠️ Fix: Crash / Watchdog Termination During Full EEPROM Sweep
- **Block-by-Block Non-Blocking Sweep (`web/src/components/MemMapperTab.jsx`, `SpectraWorkspace.jsx`)**:
  - Upgraded `08 // MEM MAPPER` to fetch `/api/mapper/info` first and sweep EEPROM sequentially block-by-block (`block=0..N-1`) with a live progress bar (`sweepProgress`), releasing `_session_lock` between blocks so UI heartbeats and debug telemetry never starve Chromium's 6-connection per-origin HTTP/1.1 limit.
  - Added in-flight request guards (`diffInFlightRef`, `rawSensorsInFlightRef`) and paused `/api/sensors`, `/api/mapper/diff`, and `/api/mapper/raw_sensors` polling while full sweeps, dump captures (`isDumping`), or AI offset calibrations (`isCalibratingOffsets`) are active.
- **Heartbeat Watchdog Long-Op Awareness (`web_server.py`, `spectra_app.py`)**:
  - Added `long_hardware_operation()` (`_active_hw_ops`) and `touch_heartbeat()` around `/api/stats`, `/api/mapper/info`, `/api/mapper/sweep`, `/api/export_capture`, `/api/ai/calibrate_offsets`, and `/api/offsets/calibrate_upload`.
  - Updated `SpectraHeartbeatWatchdog` loops in `spectra_app.py` to pause termination while `_active_hw_ops > 0` and raised the idle timeout from `7.0s` to `18.0s`.
- **Clean Serial Disconnect & Noise Recovery (`memory_mapper.py`, `spectra_probe.py`, `web_server.py`)**:
  - Wrapped `/api/mapper/*` endpoints in structured `try/except` handlers (clearing stale sessions cleanly on disconnect) and made `sweep_eeprom()` / `sweep_block()` abort immediately on closed ports instead of spinning through 512 fallback `RE:` retries; added `ValueError` recovery in `spectra_probe.sweep_eeprom()` on noisy `RT:` frames.
- **Czech Changelog Deliverable**: Added [CHANGELOG_CS.md](./CHANGELOG_CS.md) and SPECTRA-themed [CHANGELOG_CS.pdf](./CHANGELOG_CS.pdf) covering `Build 20261102.1738` through `Build 20261116.1639`.

---

## [Build 20261116.1639] — 2026-11-16

### 🌐 Highlights: Czech UI Localization, Interactive Guided Tour & Simple Czech User Guide

#### 1. Czech Secondary Language & Config Toggle (`web/src/i18n/translations.js`, `ConfigModal.jsx`, `spectra_ai.py`, `gui_widgets.py`)
- **Full Workstation Translation**: Added complete `en`/`cs` translation dictionaries covering top controls, 9 KPI tiles, navigation tabs, `01 // OVERVIEW`, `02 // SENSORS & OSCILLOSCOPE` (including Digital Twin & Oscilloscope canvas), `03 // BEVERAGES`, `04 // MAINTENANCE`, `05 // ALERTS`, `06 // IDENTITY`, `07 // COMMAND INJECTOR`, `09 // FIRMWARE INSPECTOR`, Export Modal, Debug Console, and Config Modal (preserving `08 // MEM MAPPER` in English).
- **Config Language Switcher**: Added persistent `Language / Jazyk` (`English (EN)` / `Čeština (CS)`) selector at the top of `ConfigModal.jsx` (`localStorage['spectra_lang']`).
- **Czech Service Certificates & AI Output**: Extended `gui_widgets.generate_service_report_html(..., lang="cs")`, `spectra_ai.analyze_fault_triage(..., lang="cs")`, and `spectra_ai.generate_customer_service_summary(..., lang="cs")` via `web_server.py`.

#### 2. Interactive Guided Tour (`web/src/components/InteractiveGuideModal.jsx`)
- **First-Start Onboarding & Config Reminder**: Pops up automatically on first run (`localStorage['spectra_onboarding_seen']`) with live 1-click actions (switching to `DEMO`, running `⚡ INTERROGATE`, jumping to tabs/AI setup/Offset Calibrator) and a persistent reminder/launch button + startup checkbox inside `ConfigModal.jsx`.

#### 3. Beginner-Friendly Czech User Guide (`docs/USER_GUIDE_CS.md`)
- **Non-Technical Operator Manual**: Added `docs/USER_GUIDE_CS.md` focusing on basic usage, connecting Local AI, and step-by-step EEPROM offset fixing, linked from `docs/USER_GUIDE.md` and `README.md`.

---

## [Build 20261114.0020] — 2026-11-14

### 🚀 Highlights: Phase 3 Embedded Rust HTTP Gateway, Window/Taskbar `.ico` Branding & Illustrated Operator Docs

#### 1. Embedded Rust HTTP/1.1 Gateway (`crates/spectra-agent/src/http_gateway.rs`, `crates/spectra-shell/src/main.rs`)
- **Unified Gateway & Sidecar Supervisor**: `spectra-shell` now boots an embedded asynchronous Rust HTTP/1.1 server (`start_gateway_server`) inside `spectra-agent`, serving compiled `web/dist/` static assets directly and supervising a loopback Python domain sidecar.
- **Native Rust & `--pure-rust` Routes**: Handles `/api/version`, `/api/app/heartbeat`, and `/api/debug/*` logs natively in Rust, and provides `--pure-rust` / `--no-python` standalone execution for `/api/ports`, `/api/machines`, and `/api/command` via `spectra-hal` + `spectra-core` (`matches_connected_machine`) without requiring a Python interpreter.
- **Transparent Reverse Proxy**: Proxies stateful domain API routes (`/api/stats`, `/api/ai/*`, `/api/hmi/*`, `/api/github/*`, `/api/machines/calibrate*`, `/api/export*`) to the loopback Python sidecar when running in full hybrid mode.

#### 2. Native Window & Taskbar Icon Fix (`crates/spectra-shell/src/main.rs`)
- **Pure-Rust `.ico` RGBA Decoder**: Added `decode_ico_entry_to_rgba()` reading embedded `icon.ico` directly into top-down RGBA bitmaps without external image crates, applying `.with_window_icon(...)` across platforms and `.with_taskbar_icon(...)` / `set_taskbar_icon(...)` on Windows.
- **Windows Taskbar Grouping**: Calls `SetCurrentProcessExplicitAppUserModelID("SPECTRA.Diagnostics.Suite")` inside `spectra-shell.exe` so Windows 11/10 taskbar and Alt+Tab render the crisp SPECTRA Prism logo instead of a generic executable icon.

#### 3. Illustrated Operator Guide & Visual Workflows (`docs/USER_GUIDE.md`, `docs/images/`, `README.md`)
- **Comprehensive Illustrated Manual**: Created `docs/USER_GUIDE.md` with 4 custom SVG technical diagrams (`spectra_overview_workflow.svg`, `spectra_ai_and_offset_calibration.svg`, `spectra_github_connect.svg`, `spectra_architecture_phase3.svg`) covering installation, hardware wiring & galvanic isolation, Local AI model setup, EEPROM offset fixing, Machine Library management, and GitHub authentication.

---

## [Build 20261113.2355] — 2026-11-13

### 🚀 Highlights: Phase 2 Rust Core Promotion (`spectra_py`) & Default `spectra-shell` Cutover

#### 1. Deterministic Rust Protocol & Calibration Core (`crates/spectra-core/`, `crates/spectra-py/`)
- **Jura Wire & Telemetry Codecs**: Promoted `encode_jura_wire_bytes`, `decode_jura_wire_bytes`, `decode_jura_temperature_word`, and `decode_jura_date_word` into `spectra-core` and exported them through PyO3 (`crates/spectra-py/src/lib.rs`).
- **Rust J.O.E. Offset Correlator & Machine Matcher**: Implemented `correlate_with_joe_ranked`, `machine_matches_connected`, `load_machine_library`, and ADuM/ADB transport helpers in `crates/spectra-core/src/probe.rs` and `machine_library.rs`, wired with parity fallbacks in `jura_protocol.py`, `machine_library.py`, `spectra_probe.py`, `stats_collector.py`, and `serial_io.py`.
- **Cross-Compiled Native Extensions**: Built and packaged both Linux `spectra_py.so` and Windows PE32+ `bin/spectra_py.pyd` (`PyInit_spectra_py`), verified by `test_rust_core_phase2.py`.

#### 2. Default `spectra-shell` Cutover & Bloat Removal (`spectra_app.py`, `src_launcher/`)
- **Primary Desktop Shell**: Updated `spectra_app.py` and Win32 `launcher.c` to launch `spectra-shell` / `spectra-shell.exe` + `WebView2Loader.dll` by default, removing `.NET` / `pywebview` multi-window overhead and subprocess leaks.

---

## [Build 20261113.2320] & [Build 20261113.2245] — 2026-11-13

### 🚀 Highlights: Phase 1 `spectra-shell`, Maximized Window Persistence, Foreground Dialogs & Windows TLS Fix

#### 1. Phase 1 Rust WebView Shell & Window State (`crates/spectra-shell/src/main.rs`)
- **Single-Window WebView Host**: Prototyped the Rust `tao` + `wry` WebView shell to eliminate stray `.NET-BroadcastEventWindow` / `GDI+ Window` child processes on Windows.
- **Maximized Default & Persistent State**: Opens maximized by default and persists window size, coordinates, and monitor maximization state across sessions in `window_state.json`.

#### 2. Focused Foreground File Dialogs (`hmi_inspector.py`, `crates/spectra-shell/src/main.rs`)
- **Above-Window Ownership & Focus Activation**: Fixed Win32 Save/Open dialogs (`GetSaveFileNameW` / `GetOpenFileNameW`) opening behind the SPECTRA window by resolving the foreground/SPECTRA window HWND as parent owner, preventing native dialogs from hiding behind WebView2.

#### 3. Windows TLS Certificate Store & SChannel Fallback (`tls_utils.py`, `hmi_inspector.py`, `github_auth.py`, `web_server.py`)
- **SSL Root Verification on Clean Windows VMs**: Resolved `[SSL: CERTIFICATE_VERIFY_FAILED]` errors when pulling the portable Local AI runtime or connecting to GitHub on minimal Windows installations by adding `tls_utils.py` (`configure_process_tls_env`, `urlopen_with_os_tls` using Windows OS cert store / `certifi` / SChannel PowerShell fallback).

---

## [Build 20261113.2205], [Build 20261113.1425] & [Build 20261113.1350] — 2026-11-13

### 🚀 Highlights: Default-OFF Local AI Suite, CSV/Screenshot Offset Calibrator, 172-Machine Library & Firmware Inspector UI

#### 1. Opt-In Default-OFF Local AI Engine & Portable Auto-Installer (`spectra_ai.py`, `hmi_inspector.py`, `AiStatusBar.jsx`, `ConfigModal.jsx`)
- **Zero Idle Footprint**: Local AI is strictly `OFF` (`0 MB RAM`, `0% CPU`) by default. Renamed UI references cleanly to `Local AI`.
- **Automated Engine & Model Pull**: Clicking `Pull Model` (e.g. `qwen2.5:0.5b`, `gemma3:1b`, `gemma2:2b`, `gemma3:4b` vision) auto-installs the user-space portable runtime in 3 tracked steps (`MB/s`, `%`, ETA) and launches the background daemon cleanly without stray console windows.
- **Bench Triage & Customer Summary**: Added `RUN AI BENCH TRIAGE` and `GENERATE CUSTOMER SUMMARY` in `DiagnosticAdvisorTab.jsx`.

#### 2. CSV / Screenshot EEPROM Offset Calibrator & 172-Machine Library (`machine_library.py`, `profiles_db.py`, `DiagnosticAdvisorTab.jsx`, `test_machine_library.py`, `test_spectra_ai.py`)
- **Ground-Truth Calibration**: Supports uploading J.O.E. exports, legacy Jura diagnostic CSVs, or screenshots (via `gemma3:4b` Vision OCR or Tesseract fallback) to detect exact beverage and maintenance register offsets (`16-bit BE` / `32-bit CDAB`).
- **Unified Machine Library (`172` profiles)**: Combines `profiles_data.json`, verified `docs/models/*.json` specs, and user overrides (`eeprom_overrides.json`), searchable by EF code, model family, or article number inside `CONFIG -> Machine Library` with `.spectra-offset.json` import/export and 1-click community contribution.

#### 3. Tab `09 // FIRMWARE INSPECTOR` & Windows Multi-Window Startup Fix (`HmiInspectorTab.jsx`, `spectra_app.py`)
- **React Workspace Tab 09**: Integrated full interactive `ELF32`/`APK`/`MCU .bin` firmware auditing and patch export directly into `SpectraWorkspace.jsx`.
- **Windows Single-Instance & Hidden Startup Fix**: Hardened Windows single-instance locking, Job Object teardown, and hidden WebView2 startup coordination in `spectra_app.py`.

---

## [Build 20261112.1820] — 2026-11-12

### 🚀 Highlights: Windows Export Typing Crash Resolution, JOE CSV Correlator & Community Telemetry Upload Pipeline

#### 1. Windows Type Annotation Resolution & Export Fault Isolation (`hmi_inspector.py`, `test_annotations_resolve.py`, `web_server.py`, `SpectraWorkspace.jsx`)
- **Fix Missing Typing Imports**: Fixed `hmi_inspector.py` typing imports to include `Set`, `Union`, `Callable`, `Iterable`, and `Sequence`, eliminating `NameError: name 'Set' is not defined` when exporting on Windows embedded Python 3.12 (where type annotations evaluate eagerly at import time).
- **Automated Annotation Regression Suite**: Introduced `test_annotations_resolve.py` scanning all project modules to verify that `typing.get_type_hints()` evaluates successfully on all functions, classes, and methods.
- **Export Error Handling & Browser Fallback**: Wrapped lazy module imports and `prompt_save_file_dialog` in `/api/export`, `/api/export_capture`, and `/api/hmi/export_report` with structured JSON error responses rather than unhandled HTML 500 pages. Added browser download fallback when native file dialogs are unavailable or cancelled (`cancelled: true` / `DialogUnavailableError`).
- **Frontend Export Resilience**: Updated `SpectraWorkspace.jsx` export handlers to parse non-JSON server error responses gracefully.

#### 2. Robust JOE CSV Telemetry Correlation (`spectra_probe.py`, `test_spectra_probe_joe.py`)
- **Type-Safe Product Count Parsing**: Hardened `correlate_with_joe` in `spectra_probe.py` to validate product counters and ignore non-integer rows (`if not isinstance(count, int): continue`), preventing `TypeError` during capture correlation.
- **Thousands Separator Coercion**: Added `_coerce_int()` helper to safely parse formatted strings with space or comma thousands separators (e.g. `"1 234"`, `"1,234"`).
- **Unit Test Suite**: Added `test_spectra_probe_joe.py` covering non-numeric product counters, thousand separators, and corrupted rows.

#### 3. Community Telemetry Upload & GitHub Device Flow Authentication (`github_auth.py`, `spectra_probe.py`, `web_server.py`, `SpectraWorkspace.jsx`, `test_github_auth.py`)
- **GitHub Device Flow & PAT Authentication**: Added `github_auth.py` implementing OAuth 2.0 Device Authorization Grant (`public_repo gist` scope) requiring `SPECTRA_GITHUB_CLIENT_ID` or `github_client_id` config, alongside Personal Access Token (PAT) fallback.
- **Hierarchical Token Resolution & Storage Security**: Token lookup follows stored credentials -> `SPECTRA_GITHUB_TOKEN` -> `GITHUB_TOKEN` -> `gh auth token`. Persists tokens using system `keyring` when available, falling back to chmod `0600` JSON files in XDG/APPDATA config directory. Tokens are never logged or exposed to the frontend.
- **REST Endpoints & Capture Caching**: Added `/api/github/auth/{status,device/start,device/poll,token,logout}` endpoints. Extended `/api/upload-capture` with `capture_id` cache and safe path verification (`_written_capture_paths`) to avoid re-uploading large telemetry payloads.
- **Export Modal UI Overhaul**: Overhauled Export modal in `SpectraWorkspace.jsx` with distinct "Save locally" (default) and "Upload to community repository" modes, Device Code activation flow, and unauthenticated manual browser submission fallback (automatic unlisted Gist creation for payloads exceeding 64KB issue URL limits, and label 422 retry).
- **Unit Test Suite**: Added `test_github_auth.py` verifying device flow state transitions, token resolution order, secure storage isolation, and GitHub API interactions.

#### 4. Windows Distribution & Build Suite Packaging (`spectra.spec`, `src_launcher/`)
- **PyInstaller Hidden Imports**: Added `github_auth` and missing typing modules to `spectra.spec` hiddenimports.
- **Recompiled PE32+ Binaries**: Recompiled native launcher suite (`bin/spectra.exe`, `dist/spectra_setup.exe`, `dist/spectra_update.exe`) to Build 20261112.1820.

---

## [Build 20261110.1445] — 2026-11-10

### 🚀 Highlights: Native OS "Save As" Dialogs for Exports, Elimination of `beforeunload` Teardown Crash & Hardened Webview Lifecycles

#### 1. Native OS "Save As..." File Dialogs (`hmi_inspector.py`)
- **Native Win32 `comdlg32.GetSaveFileNameW`**: Added `prompt_save_file_dialog` leveraging `OPENFILENAMEW` with `OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_OVERWRITEPROMPT | OFN_NOCHANGEDIR` (`0x0008080A`), multi-filter null-terminated buffers, and automatic extension resolution, giving users complete interactive control over where diagnostic logs and audit reports are saved.
- **Resilient Multi-Tier Desktop Fallback**: Falls through cleanly to PowerShell `-STA` (`System.Windows.Forms.SaveFileDialog` with `creationflags=0x08000000`), Linux GTK3 isolated subprocess (`Gtk.FileChooserAction.SAVE`), `zenity --file-selection --save --confirm-overwrite`, `kdialog`, `yad`, and `tkinter.filedialog`.
- **Integrated Backend Endpoints**: Wired `prompt_save_file_dialog` into `/api/export` (`save_dialog=1`), `/api/export_capture` (`save_dialog: true`), and `/api/hmi/export_report` (`save_dialog: true`), saving diagnostics directly to the chosen location with UTF-8 encoding and returning the target path.

#### 2. Root-Cause Resolution of Windows Navigation Crash (`web_server.py`, `spectra_app.py`, `SpectraWorkspace.jsx`)
- **Elimination of `beforeunload` Process Suicide**: Diagnosed root cause of Windows crash during diagnostic export: `window.location.href = '/api/export?...'` triggered the WebView2 browser `beforeunload` event, causing `App.jsx` to dispatch `navigator.sendBeacon('/api/app/close')` which killed the Python HTTP server via `os._exit(0)`.
- **In-Band Export Triggering**: Replaced browser navigation with in-band asynchronous `fetch` calls requesting `save_dialog=1`, eliminating page reloads and preserving application state.
- **Native Webview Lifecycle Authority**: Flagged `_is_native_webview = True` when running under `try_launch_pywebview` and `try_launch_gtk_webkit`, giving the native container host exclusive authority over application lifetime and ignoring premature unload beacons.
- **Deferred Exit Hardening**: Extended deferred shutdown grace window to 3.0s and added heartbeat checks in `web_server.py` so background navigations never terminate the server.

#### 3. Interactive Export Feedback & Session Resilience (`SpectraWorkspace.jsx`, `web_server.py`)
- **Modal Export Status Banner**: Added reactive `exportStatus` banner with spinning indicator during file dialog selection and generation, providing immediate visual confirmation and showing the full destination path upon completion.
- **Session Cache Fallback**: Hardened `/api/export` to dynamically initialize `sc.JuraStatsSession(port_name=port)` if interrogation cache is not yet loaded, guaranteeing export generation always succeeds.

---

## [Build 20261110.1355] — 2026-11-10

### 🚀 Highlights: Native Win32 Subsystem GUI Launcher, Zero-Terminal Architecture & Official SPECTRA Splash & Icon Branding

#### 1. True Windows GUI Subsystem & Zero Terminal Window Elimination (`launcher.c`, `build.sh`)
- **Native GUI Subsystem Compilation (`-Wl,/subsystem:windows`)**: Re-linked `spectra.exe` with `-Wl,/subsystem:windows -municode -luser32 -lshell32 -lgdi32 -ladvapi32` and `wWinMain` entry point. When double-clicked from Windows Explorer, Windows treats the binary as a pure GUI application, completely eliminating the unwanted black command prompt (`cmd.exe`/`conhost.exe`) terminal window.
- **Selective CLI Console Attachment**: When explicit CLI arguments (`--cli`, `--help`, `--version`, `--sensors`, `--port`) are provided, `launcher.c` dynamically calls `AttachConsole(ATTACH_PARENT_PROCESS) || AllocConsole()` and maps stdout/stderr to `CONOUT$`.
- **Silent Python Process Spawning**: Configured `CreateProcessW` with `CREATE_NO_WINDOW` (`0x08000000`) and `STARTF_USESHOWWINDOW` (`SW_HIDE`), preferring `pythonw.exe` over `python.exe` so no secondary console window is ever allocated.

#### 2. Native Win32 Animated Splash Screen (`launcher.c`)
- **High-Performance Frameless Splash**: In GUI mode, `launcher.c` creates a centered `460x280` dark frameless popup window (`#0E0E12`, 1px cyan `#06B6D4` border) rendering the official SPECTRA Prism Logo icon, bold Segoe UI typography, build badge (`Build 20261110.1355`), dynamic status text, and an animated glowing progress bar.
- **Autonomous Dismissal via Window Discovery**: The splash screen monitors child process state and uses `EnumWindows` to detect the main application window (title starting with `SPECTRA —`). Once the main dashboard appears or child process terminates, the splash is destroyed cleanly without delay.

#### 3. Official SPECTRA Window, Taskbar & Favicon Branding (`spectra_app.py`, `index.html`)
- **AppUserModelID Taskbar Binding**: Called `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SPECTRA.Diagnostics.Suite")` ensuring Windows groups the app under its own identity rather than generic Python.
- **Dual WinForms & Win32 WM_SETICON Hook**: Added `on_webview_started` hook in `try_launch_pywebview` assigning the official multi-resolution `icon.ico` directly to active WinForms forms (`form.Icon`) and sending `WM_SETICON` (`ICON_BIG` and `ICON_SMALL`) to all process HWNDs via `SendMessageW`.
- **Zero-Latency In-Window Web Splash**: Embedded an inline SVG/CSS loader inside `<div id="root">` in `web/index.html` featuring the glowing cyan/blue hexagonal prism logo and animated pulse bar, guaranteeing an instantaneous branded loader during initial page parse.
- **Favicon & Apple-Touch-Icon Assets**: Bundled `favicon.ico` and `icon.png` into `web/public/` and `web/dist/`, serving icons with fallback resolution in `web_server._serve_static`.

#### 4. Stream Safety & Windows Subprocess Hardening (`spectra_app.py`, `hmi_inspector.py`)
- **Safe Standard Streams under `pythonw.exe`**: Guarded `sys.stdout` and `sys.stderr` when `None` (running under `pythonw.exe` or `FreeConsole()`) to route to `os.devnull`, preventing `AttributeError` on print/write calls.
- **No-Window Process Flagging**: Added `creationflags=0x08000000` to PowerShell file dialogs and `taskkill.exe` calls in `hmi_inspector.py`.

---

## [Build 20261110.1150] — 2026-11-10

### 🚀 Highlights: Embedded PyWebView Windows Packaging, Custom AI Model Dropdown & Extended Browser Cascade

#### 1. Embedded PyWebView & Win_AMD64 Runtime Packaging (`src_launcher/build.sh`, `spectra_app.py`)
- **Direct PyWebView + PythonNet Packaging**: Packaged `pywebview` 6.2.1, `pythonnet` 3.2.1, `clr_loader`, `cffi`, `pycparser`, `bottle`, `typing_extensions`, and `proxy_tools` wheels directly into the Windows standalone embeddable runtime (`/tmp/pyembed/`) and cached them under `vendor/wheels_win_amd64/` for fast, offline compilation.
- **Fast In-Place Updater Upgraded**: Added `pywebview` and its supporting DLLs directly into `update_bundle.zip` (~1.5 MB) so running `spectra_update_build*.exe` instantly upgrades existing installations with the native desktop window host without requiring the full installer.
- **Embedded Python DLL Binding**: Configured `try_launch_pywebview` in `spectra_app.py` to bind `PYTHONNET_PYDLL` and call `os.add_dll_directory` pointing to the embedded runtime's `python312.dll`, initializing `webview.start(gui="edgechromium")`.
- **Extended Browser Cascade**: Expanded `find_chromeless_browser()` on Windows to discover Brave, Vivaldi, Opera, and local portable Chromium runtimes (`runtimes/chromium/chrome.exe`).

#### 2. Infallible Custom AI Model & Locale React Dropdowns (`HmiInspectorTab.jsx`)
- **Custom Cyber Dropdown Component**: Replaced native OS `<select>` with an interactive custom dark-themed React dropdown with filter input, RAM badges, `⭐ RECOMMENDED`, and `✓ INSTALLED` status indicators, completely eliminating Windows OS `<select>` dark mode rendering and dismissal bugs.
- **Infallible Fallback Catalog**: Preloaded `FALLBACK_MODEL_CATALOG` (`qwen2.5:0.5b`, `qwen2.5:1.5b`, `qwen2.5:3b`, `qwen2.5:7b`, `llama3.2:1b`, `llama3.2:3b`, `gemma2:2b`, `mistral:7b`, `llama3.1:8b`) ensuring models are immediately selectable even while hardware profiling is loading or if offline.
- **Persistent Selection**: Preserves model selection in `localStorage['spectra_ollama_model']`, preventing background polling from resetting user choices.
- **Effective Languages Fallback**: Added `effectiveLanguages` so the `Target Locale:` selector is always populated even before a firmware binary is loaded.

#### 3. Backend Hardware Probe Hardening (`hmi_inspector.py`)
- **Safe Hardware Fallback**: Wrapped `probe_host_hardware()` in `get_ai_system_status()` with resilient fallback metadata guaranteeing `hardware.model_catalog` is never null or empty.

---

## [Build 20261110.1105] — 2026-11-10

### 🚀 Highlights: Windows Edge Broker Handoff Fix, Reactive AI Daemon Status & Deep Semantic Progress Bar

#### 1. Windows Startup Broker Process Handoff & Frontend Heartbeat Watchdog (`spectra_app.py`, `App.jsx`)
- **Edge Broker Process Handoff Resolution**: Solved premature Python HTTP server shutdown on Windows 10/11 where `msedge.exe --app=...` delegates window creation to a pre-existing background browser broker process and exits with code 0 in <200ms.
- **Heartbeat-Driven Watchdog**: Implemented broker handoff detection (`proc.wait(timeout=3.0)`), a 15.0-second initial startup grace window, and a reactive polling loop that keeps the server alive via `/api/app/heartbeat` (2.0s pulse interval, 7.0s timeout).
- **Native Win32 Embedded Host (`try_launch_win32_native_window`)**: Added native Win32 window hosting support compiling a lightweight standalone C# / .NET `Form` + WebView2 / WebBrowser via `csc.exe` or PowerShell fallback.
- **Graceful Teardown Signaling**: Updated `App.jsx` window lifecycle hooks to dispatch `navigator.sendBeacon` to both `/api/app/close` and `/api/app/window_closed` upon `beforeunload` and `pagehide`.

#### 2. Real-Time AI Daemon Status & RAM Residency Telemetry (`hmi_inspector.py`, `HmiInspectorTab.jsx`)
- **Live RAM / VRAM Querying**: Updated `KalermHmiInspector.check_local_ollama` to query `/api/ps` for loaded models in RAM/VRAM with a 0.35s non-blocking timeout.
- **Robust Daemon Process Management**: Enhanced `control_local_ollama`: "stop" issues `pkill -f` on Linux and `taskkill` on Windows to cleanly terminate any orphan user processes; "start" polls readiness up to 4.0s; "unload" evicts all active models from RAM.
- **Synchronous AI Status Propagation**: Embedded daemon controller endpoints (`/api/hmi/ollama_control` and `/api/hmi/ai/control`) now return live `ai_status` directly, immediately updating the UI without round-trip race conditions.
- **Reactive Tier 3 Status Badge**: The top-right Tier 3 badge now dynamically updates across all engine states: pulsing purple during active scans, emerald when audited, cyan (`Online — Ready [model]`) when idle/ready, and muted gray when offline.
- **Telemetry Card Expansion**: Updated `DISK & DAEMON` telemetry card to display live RAM residency (`RAM: <model>` or `RAM: Idle (0 loaded)`).

#### 3. Real-Time Deep AI Semantic Scan Progress Bar
- **Thread-Safe Scan Progress**: Added `KalermHmiInspector.get_semantic_scan_progress()` and `_update_semantic_progress()` tracking phase steps (Tier 1 glossary, Tier 2 vector consensus, Tier 3 startup, Tier 3 candidate inference loop), item counters, percentage, and dynamic ETA computation.
- **Progress Streaming API**: Implemented `/api/hmi/semantic/progress` streaming endpoint across `web_server.py` and `gui_web.py`.
- **Industrial Progress Component**: Rendered cyber-style animated progress bar in `HmiInspectorTab.jsx` displaying phase step, phrase translation preview, candidate counter, percent bar, and estimated seconds remaining.

---

## [Build 20261110.1008] — 2026-11-10

### 🚀 Highlights: Cross-Platform File Browser Cascade, Serial PTY Hardening & Persistent Auto-Scan Toggle

#### 1. Multi-Desktop & Multi-OS Native File Browser Cascade (`prompt_file_browser`)
- **Linux Isolated Subprocess**: Spawns an isolated Python GTK3 `FileChooserDialog` subprocess verifying `Gtk.init_check()[0]`, exiting with `3` if headless/display is unavailable to trigger immediate non-blocking fall-through, `0` on valid file selection, and `2` on user cancellation.
- **Robust Linux Cascade**: Implemented seamless fall-through order across `zenity`, `kdialog`, `yad`, `qarma`, and `tkinter.filedialog`.
- **Windows Win32 Native Integration**: Implemented native `ctypes.windll.comdlg32.GetOpenFileNameW` (`OPENFILENAMEW` with `OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR = 0x00080808`), properly catching cancellation via `CommDlgExtendedError() == 0`, with cascading fall-through to `powershell -NoProfile -STA -Command` and `tkinter`.
- **Browse Endpoint Parameterization**: Updated `/api/hmi/browse` across `web_server.py` and `gui_web.py` to accept `initial_dir` from request payload.

#### 2. Serial Port Enumeration Hardening (`serial_io.py`)
- **PTY Bleed Prevention (Linux)**: Completely eliminated `/dev/pts/*` and phantom motherboard `/dev/ttyS*` from port scanning, strictly restricting enumeration to physical USB/ACM adapters (`/dev/ttyUSB*`, `/dev/ttyACM*`) to prevent Jura `TY:` query bleeds into active interactive terminal shells.
- **Windows Registry Hardware Discovery**: Replaced blind `COM1..COM16` fabrication loop with live Windows Registry querying via `winreg` (`HKLM\HARDWARE\DEVICEMAP\SERIALCOMM`).
- **Web UI Hardware Port Auto-Select**: Refined `fetchPorts` port priority matching in `SpectraWorkspace.jsx` to recognize any case-insensitive `COM*`, `ttyUSB*`, `ttyACM*`, and `by-id` devices.

#### 3. Persistent HMI Firmware Target Auto-Scan Toggle (`HmiInspectorTab.jsx`)
- **Persistent LocalStorage State**: Introduced `autoScanDownloads` preference stored under `localStorage['spectra_hmi_auto_scan']`, defaulting to `OFF` (`false`).
- **Interactive Toolbar Toggle**: Added `AUTO-SCAN: ON / OFF` button in the HMI Inspector path toolbar alongside `📂 BROWSE...` and `🔄 RESCAN`.
- **Conditional Rendering**: Renders quick-select firmware target chips when auto-scan is enabled; displays a clean guidance banner when auto-scan is paused.

#### 4. GTK3 Compact Header Sizing & Desktop Launcher
- **Responsive 2-Row Header**: Adjusted GTK3 layout breakpoint in `gui.py` (`<= 960px`) to display compact action button labels (`⚡ Read`, `🔬 Mapper`, `📦 HMI`, `🖨️ Receipt`) ensuring zero clipping on low-resolution displays.
- **XDG Desktop Launcher**: Installed and validated standard XDG desktop entry at `~/.local/share/applications/SPECTRA.desktop`.

---

## [Build 20261109.2255] — 2026-11-09

### 🚀 Highlights: Dynamic Header Versioning, WebKit2 Cache-Busting & App Launcher Integration

#### 1. Dynamic Top Header Build Versioning
- **Live Reactive Build Header**: Replaced static build text in `SpectraWorkspace.jsx` with dynamic backend build propagation (`liveBuild || debugSummary?.build`), synchronized live with `version.py`.
- **API Version Endpoints**: Added `/api/version` and updated `/api/debug/status` to return `"build": __build__` and `"version": __version__` across both `web_server.py` and `gui_web.py`.
- **Fallback Build Number Alignment**: Synchronized fallback `__build__` constants across all CLI, GUI, Probe, and HMI modules to `"20261109.2255"`.

#### 2. WebKit2 Cache-Busting & HTTP Cache Control
- **No-Cache HTTP Header**: Configured `web_server.py` and `gui_web.py` to serve static assets with `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`.
- **WebKit2 Cache Invalidation**: `spectra_app.py` disables page cache, calls `context.clear_cache()`, and appends version query `?v={build_str}` on every window load.

#### 3. Linux Desktop App Launcher & Official Prism Logo
- **XDG Desktop Launcher**: Installed official 256x256 PNG and scalable SVG icons into `~/.local/share/icons/hicolor/`.
- **Wayland / Hyprland Taskbar Grouping**: Configured `StartupWMClass=spectra`, `GLib.set_prgname("spectra")`, and `window.set_wmclass("spectra", "SPECTRA")` in `SPECTRA.desktop` and `spectra_app.py`.
- **Workspace Cleanup**: Retired obsolete `spectra-mm` repository and purged stale WebKit disk caches.

---

## [Build 20261109.2230] — 2026-11-09

### 🚀 Highlights: Dynamic Firmware Discovery & Zero-Hardcoding Mandate Compliance

#### 1. Dynamic Firmware Target Discovery (`KalermHmiInspector.discover_local_targets`)
- **Host Filesystem Discovery**: Dynamically scans `~/Downloads` and user-specified directories up to 2 levels deep for valid coffee machine firmware containers.
- **Architecture-Aware ELF Header Probing**: Detects Linux ARM 32-bit ELF binaries via `b"\x7fELF"` magic, `ei_class == 1`, and `e_machine == 40` (ARM), eliminating hardcoded `"lv_klm"` filename checks.
- **Zero-Hardcoding Enforcement**: Completely eradicated hardcoded user paths (`/home/<user>/...`) across all backend modules and UI components.

#### 2. Native OS File Chooser & Unified API Endpoints
- **Native File Dialog**: `prompt_file_browser()` opens native dialogs via Zenity / kdialog / tkinter on Linux and PowerShell / Win32 on Windows.
- **REST API Parity**: Added `/api/hmi/discover` (GET) and `/api/hmi/browse` (POST) across both `web_server.py` and `gui_web.py`.

#### 3. Reactive UI Firmware Chips
- **Dynamic Quick-Select Chips**: Replaced static buttons with reactive badges dynamically generated from discovered firmware on host.
- **One-Click Native File Chooser**: Integrated `📂 BROWSE...` and `🔄 RESCAN` buttons into HMI Inspector toolbar.

#### 4. Generic Heuristic Finding IDs & ISO-639-1 Endonyms
- **Generic Finding Identifiers**: Switched finding IDs to `AUDIT-SWAP-{locale}-{key}`, `AUDIT-LEAK-{locale}-{key}`, `AUDIT-TYPO-{locale}-{key}`, and `AUDIT-LANG-CASING-{LANG}`.
- **Native Endonym Resolver**: Added `_resolve_native_endonym()` mapping 35+ ISO-639-1 codes to native endonyms.
- **Dynamic Binary Reporting**: Export templates automatically render target binary name and container type dynamically.

---

## [Build 20261109.2200] — 2026-11-09

### 🚀 Highlights: Universal Container Architecture & Multi-Platform Firmware Diagnostics

#### 1. Universal Container Support in `hmi_inspector.py`
- **Container Auto-Detection via File Magic**:
  - `ELF32_LVGL`: Linux ARM 32-bit ELF binaries (`lv_klm_coffee_make_113`).
  - `ANDROID_APK`: Android HMI application packages (`.apk`) containing compiled `resources.arsc` string tables.
  - `MCU_CTR_BIN`: Bare-metal ARM Cortex-M controller application firmware (`.bin`) with Cortex-M interrupt vector table.
- **Companion CTR Binary Resolution**:
  - When inspecting an HMI directory (e.g. `X-line_1.9.9HMI`), automatically binds the companion MCU CTR `.bin` (e.g. STM32H723 logic controller) to the primary HMI session.

#### 2. Pure-Python Android APK `resources.arsc` Engine
- **In-Memory ARSC Table Parser**:
  - Full binary parser for `RES_STRING_POOL_TYPE` (UTF-8 and UTF-16 pools), `RES_TABLE_PACKAGE_TYPE`, and `RES_TABLE_TYPE_TYPE`.
  - Normalizes Android locale configs into standard BCP-47 tags (`cs` + `cs_CZ` -> `cs-CZ`, `en` + `default` -> `en-GB`, etc.), extracting 84 locales and 2,077 base English / 1,562 Czech phrases.
- **APK Signature Scheme v2 & Certificate Detection**:
  - Parses APK Signing Block (`APK Sig Block 42`, ID `0x7109871a`) from ZIP Central Directory.
  - Detects standard AOSP platform test key (`CN=Android, OU=Android, L=Mountain View`) and reports laboratory re-signing capability via `apksigner`.
- **Heuristic Auditing for Android HMI**:
  - Detects corrupted format specifiers (`% d` whitespace injection and inverted `%d~d%`) that risk runtime formatting exceptions.
  - Detects untranslated multi-word English strings and calculates translation coverage gaps (e.g. 75.2% Czech vs English).

#### 3. Bare-Metal ARM Cortex-M Logic Controller Firmware (`.bin`) Engine
- **Interrupt Vector Table Parsing**:
  - Validates initial Stack Pointer (`0x20000000..0x24100000`) and Thumb-2 Reset Vector (`0x08000001..0x081FFFFF`).
  - Infers microcontroller family (`STM32H7xx` Cortex-M7 vs `GD32F4xx` Cortex-M4) and Base Flash VMA (`0x08040000` vs `0x08020000`).
- **Release CRC32 Token Matching & Actuator Primitives**:
  - Parses release CRC token (e.g. `93180B22`, `14C2CD54`) from firmware descriptor / companion file.
  - Extracts firmware strings into virtual `"MCU-STRINGS"` locale, indexing actuator primitives (PUMP, VALVE, HEATER, NTC, FLOWMETER, STEPPER).

#### 4. UI & Standalone Application Enhancements
- **Dynamic Container Badge & Quick Preset Buttons**:
  - Displays container badge (`ELF32 ARM (LVGL)`, `ANDROID APK (ARSC)`, `ARM CORTEX-M (CTR BIN)`) in header and metadata KPI bar.
  - Adds quick load preset buttons for `D101 LINUX (V1.2.3)`, `X-LINE APK (V1.9.9)`, `X-LINE CTR (.BIN)`, and `D-LINE CTR (.BIN)`.
- **GTK3 + WebKit2 Dark Theme & Dropdown Legibility Fix**:
  - Configured GTK dark theme preference and global CSS provider in `spectra_app.py` for readable select menus.
  - Modern cyan dropdown chevron and dark background in `index.css`.

---

## [Build 20261109.1500] — 2026-11-09

### 🚀 Highlights & Generalized Heuristic Firmware Auditor

#### 1. Generalized Heuristic Firmware & Translation Auditor (`hmi_inspector.py`)
- **Generalized Cross-Locale Pointer & String Leakage Scanner (Heuristic 1)**:
  - Dynamically scans all 651+ phrases in the target locale against all 18 other locales.
  - Detects shared VMA pointers or identical phrases (>=6 chars) with non-English foreign languages while filtering universal coffee/tech loanwords, pure numbers, and format strings.
  - Automatically flags CJK characters (`[\u4e00-\u9fff]`) in non-CJK locales as `CRITICAL`.
- **Universal Orthography & Printf Format-Specifier Scanner (Heuristic 2)**:
  - Dynamically detects double-capital / mid-word typos via regex `r'(?<!\w)[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{2}[a-záčďéěíňóřšťúůýž]{2,}'` across all keys, excluding technical acronyms.
  - Compares `printf` format specifiers against English reference strings, flagging dropped or mismatched placeholders (`%d`, `%s`, etc.) as `CRITICAL` format specifier defects that could cause memory corruptions in `snprintf`/`lv_label_set_text_fmt`.
  - Flags replacement characters (`\ufffd`) and invalid control bytes.
- **Semantic Inversion & Polarity Scanner (Heuristic 3)**:
  - Dynamically evaluates opposing concept polarity pairs (`_high`/`High` vs low-temp words, `_low`/`Low` vs high-temp words, `_left` vs right words).
  - Generalized maintenance rinsing inspection across all locales.
- **Global Language Selector Table Scanner (Heuristic 4)**:
  - Dynamically inspects `.rodata` language descriptor blocks and ARM `movw/movt` instructions, flagging lowercase native proper nouns (e.g. `cestina`, `hrvatski`).
- **Multi-Locale Architecture & Web Dashboard Integration**:
  - `run_audit(target_locale=...)` accepts any compiled locale.
  - Integrated into `/api/hmi/audit?locale=...` and `/api/hmi/export_report` endpoints.
  - Added real-time Target Locale switcher to the Audit subtab in `HmiInspectorTab.jsx`.
  - 18 unit tests in `test_hmi_inspector.py` (synthetic + production Kalerm V1.2.3 binary).

---

## [Build 20261109.1339] — 2026-11-09

### 🚀 Highlights & Kalerm HMI Firmware & Translation Auditor

#### 1. SPECTRA HMI & Firmware Inspector / Auditor Engine (`hmi_inspector.py`)
- **Dynamic ELF32 Section & Symbol Table Engine**:
  - Dynamically parses 32-bit ARM ELF binary structures (`e_shoff`, `e_shentsize`, `e_shnum`, `.shstrtab`, `.symtab`, `.strtab`).
  - Implements dynamic bidirectional VMA-to-physical file offset mapping (`vma_to_off`, `off_to_vma`), resolving symbols like `lv_i18n_language_pack`, `cs_cz_singulars`, and `en_gb_singulars` with zero hardcoding.
- **Exhaustive Multi-Locale Language Pack Extraction**:
  - Automatically parses `lv_i18n_language_pack` extracting all 19 compiled locales (`en-GB`, `cs-CZ`, `da-DK`, `de-DE`, `el-GR`, `es-ES`, `fr-FR`, `hr-HR`, `hu-HU`, `it-IT`, `ja-JP`, `ko-KR`, `nl-NL`, `pl-PL`, `pt-PT`, `ru-RU`, `sv-SE`, `zh-CN`, `zh-TW`).
  - Maps 650+ phrases per locale with key/value strings, VMAs, slot file offsets, and translation byte offsets in under 35 milliseconds via memory mapping.
- **Automated Firmware Safety & Localization Auditor (`run_audit()`)**:
  - **CRITICAL (Logic Inversion)**: Detects swapped milk rinsing logic in Czech and English where `common_milk_frother_system_rinse` (invoking `milkFrotherRinseLite` / Type 26 internal frother rinse) was labeled with external tube rinse text ("EXTERNAL MILK PIPE RINSING" / "Proplach externí hadičky na mléko") and vice versa.
  - **WARNING (Localization Leakage)**: Detects Italian string leakage in `cs-CZ` (`Drink_Temp_High` pointing to Italian `"Temperatura alta"` instead of Czech `"Vysoká teplota"`).
  - **WARNING (Orthography / Typo)**: Detects mid-word uppercase typos in Czech phrases (e.g. `"ČIštění obrazovky"` with capital `'I'` at offset +2).
  - **WARNING (Typography / UI)**: Detects unaccented lowercase language selection display (`language_cs` -> `"cestina"` instead of proper noun `"Čeština"`).
- **Laboratory Binary Patcher (`apply_patches()`)**:
  - Produces byte-for-byte verified lab copies of the HMI binary:
    * Repoints `Drink_Temp_High` in `cs-CZ` to `"Vysoká teplota"` (`0x035a4fe8`).
    * Fixes typo `"ČIštění"` -> `"Čištění"` (`0x49` -> `0x69`).
    * Writes `"Čeština\0"` to `.rodata` padding (`0x064ea230`) and repoints all 230 ARM32 `movw/movt` instruction pairs loading `0x064cab14` in `.text`.
    * Swaps value pointers for `common_milk_frother_system_rinse` <-> `common_outside_milk_tube_rinse` (and `_lf` variants) in `cs-CZ` and `en-GB`.
- **Cryptographic Signature & Integrity Verifier**:
  - Computes SHA-256 digest of binaries and validates 2048-bit RSA PKCS#1 v1.5 `KLM_SIGN.pem` containers, reporting unsigned lab modifications vs verified factory signatures.
- **Multi-Format Bug Report Generator (`export_bug_report()`)**:
  - Generates comprehensive engineering reports in Markdown (`.md`), HTML (`.html`), and PDF (`.pdf` via headless LibreOffice).

#### 2. Visual GTK3 Industrial Dialog & Main GUI Integration
- **`HmiInspectorDialog`**:
  - Full Catppuccin Mocha dark theme matching `memory_mapper.py` and `gui.py`.
  - **Tab 1 (Automated Audit)**: Live severity badges (`CRITICAL`, `WARNING`, `INFO`, `FIXED`), detailed finding breakdown, one-click laboratory binary patching, and report export.
  - **Tab 2 (Translation & Pointer Explorer)**: Live search filter across keys, translated text, and hex addresses, with side-by-side English (`en-GB`) reference column for instant translation diffing across all 19 locales.
- **Header Toolbar Integration (`gui.py`)**:
  - Added `self.btn_hmi_tools = Gtk.Button("📦 HMI Tools")` with class `action-btn` and tooltip `"Kalerm Linux HMI Firmware & Translation Inspector / Auditor"`.
  - Seamlessly supported across both widescreen (>= 1580px) and compact dual-row toolbar layouts.

#### 3. CLI & Automated Test Suite Integration
- **CLI Options (`cli.py`)**: Added `--hmi-inspect`, `--hmi-search`, `--hmi-lang`, `--hmi-patch`, and `--hmi-export-report`.
- **Comprehensive Unit Tests (`test_hmi_inspector.py`)**: 12 test cases covering synthetic ELF32 fixture generation, dynamic section mapping, symbol lookup, audit detection, laboratory patching verification, signature checks, report export, and integration checks on real binaries.

---

## [Build 20261104.1418] — 2026-11-04

### 🚀 Highlights & Digital Twin Thermoblock Range Fix

#### 1. Digital Twin Thermoblock Readiness Range Normalization
- **Thermoblock Status Evaluator Fix (`DigitalTwinSchematic.jsx`)**:
  - Eliminated the artificial `tb1Temp <= 100` ceiling that caused nominal operating temperatures (e.g. `100.5 °C`) to falsely evaluate as `'HEATING'` in Box 2 (`OPERATING STATUS`).
  - Standardized `tb1` status to `tb1Temp >= 80 && tb1Temp <= 115 ? 'READY' : (tb1Temp > 115 ? 'OVERHEAT' : 'HEATING')`, matching Jura operating specifications (nominal brew ready threshold $\ge 80.0^\circ\text{C}$).
- **Hardware Interrogation Sub-Bus Proof**:
  - Verified live Display MCU `EF518D V02.04` responses across 28 commands: `RT$:00..F0` (`rt$:0000...00`), `RE$:00..0F` (`re$:0000`), confirming `TP$:1..4` and `T1$:..T3$:` are Zeta-only extensions not implemented on commercial `EF518D`.

---

## [Build 20261104.1350] — 2026-11-04

### 🚀 Highlights & Display Sub-Bus Interrogation

#### 1. Exhaustive Live Interrogation of Display Sub-Bus (`EF518D V02.04`)
- **Direct Serial Probing on Active Physical Machine in "Fill Beans"**:
  - `CS$:`: Consistently returned `cs$:1418` across multiple samples, completely invariant between Ready and Fill Beans states (firmware checksum invariant).
  - `RE$:0000..0029` and `RT$:0000..0020`: Returned all zeroes on Display MCU memory space.
  - `IC$:`, `HZ$:`, `AS$:`: Unsupported on `EF518D V02.04` (`[NO_REPLY]`).
  - Binary inspection of Jura Service Suite `P518Ani.exe`: confirmed `TS$:4,02` string presence and zero hidden bean queries to the display sub-bus.

#### 2. UI Microswitch & Digital Twin Display Fix
- **Bean Hopper Tile Status Resolution (`SpectraWorkspace.jsx`)**:
  - Dynamically extracts `beansSw` from `liveData?.switches`.
  - Tile 7 now prominently displays `'LOCAL (EF518D)'` badge and subtitle `"Monitored Locally by Display MCU (EF518D)"` when connected to commercial dual-MCU hardware, eliminating hardcoded `'Hopper Charged'`.
- **Digital Twin Schematic Integration (`DigitalTwinSchematic.jsx`)**:
  - Schematics `beans` node dynamically reflects `beansSw?.details` and hardware provenance (`Front Display MCU EF518D Local Phototransistor`).

---

## [Build 20261104.1305] — 2026-11-04

### 🚀 Highlights & Complete Physical Elimination Ledger

#### 1. Definitive 512-Word EEPROM Diff & Architecture Proof
- **Complete Elimination Ledger**:
  - Captured exhaustive 512-word active EEPROM block scan (`RT:0000..01F0`) and live telemetry (`HZ:`, `CS:`, `CS$:`, `IC:`, `AS:`) on live physical Jura IMPRESSA XJ5 (`EF518M V02.20`, Display `EF518D V02.04`):
    * Only 6 drink/grinder counters (`0001`, `000A`, `000E`, `000F`, `0015`, `0020`) and rolling checksum (`00CE`) incremented.
    * `CS[39:43] == 3FF0`, `CS$ == 1418`, `HZ[0][3] == '1'`, and `AS == 1.060 ratio` remained completely unchanged when the appliance transitioned from "Ready" to "Fill Beans" on the front display upon pressing a coffee product.
    * Conclusive proof: on commercial `EF518` architecture, the optical bean barrier circuit is strictly local to the `EF518D` front display MCU and is not exposed over serial to the main board MCU `EF518M` or to Jura's official Service Suite (`P518Ani.exe` tests `#669/#670/#738/#739` require human visual check of the LCD).
- **Non-Intrusive Readiness Gating (`stats_collector.py`)**:
  - Gated `machine_ready` strictly on the 5 physical inputs (Tray, Tank, Grounds, Coffee Thermoblock $\ge 80.0^\circ\text{C}$, Appliance Idle).
  - Evaluates `beans_ok` via universal physical puck-compression thickness fallback (`not (0 < cake_thickness_ticks <= 14)`), preventing any false "Fill Beans" software lockouts.
  - Switch `bean_hopper` clearly notes: `"Monitored Locally by Display MCU (EF518D)"`.
  - Preserved ultra-fast ~50ms auto-polling (`fast_poll=True`, `HZ:` only).
  - Maintained `AS:` Coffee Heater NTC $+6.0\%$ Shunt Self-Test (`heater_ntc_diagnostic_sensor`).

---

## [Build 20261103.1925] — 2026-11-03

### 🚀 Highlights & Architectural Discovery

#### 1. Display MCU Sub-Bus Static Disassembly & Direct LCD Readout
- **Detailed Reverse-Engineering of Display MCU Commands**:
  - Fully disassembled `#RB$` (`0x1652`), `TP$` (`0x175C`), `TS$` (`0x1578`), `ST$` (`0x15C2`), `T1$` (`0x142A`), `T2$` (`0x148A`), `T3$` (`0x14FA`), and `TY$` (`0x126E`) from `DE_EN_FlashDisplayZetaV4.0.4.LoaderV3.0.TextsV1.1.4.Common.bin` (`EF518D`, Renesas R8C).
  - `#RB$:XXXX\r\n`: arbitrary 16-bit memory / SFR port read over the serial sub-bus, responding `rb:%04X\r\n`.
  - `TP$:X\r\n`: line parameter query, reading the active message rendered on LCD line `X` (`1..4`) from parameter buffer `0xE88C`, responding `tp:%s\r\n`.
  - `TS$:L,NN\r\n`: Text Set command writing string `NN` to display line `L`, responding `ok:\r\n`.
  - `ST$:\r\n`: display communication status test, responding `ok:\r\n`.
  - `T1$:`, `T2$:`, `T3$:`: live telemetry query handlers responding `t1:%02X\r\n`, `t2:%02X\r\n`, `t3:%02X\r\n`.
- **Top-Tronic XML Script Deobfuscation (`Serv_EF518_V2.t3s`)**:
  - Solved the Top-Tronic line rotation cipher (`shift = ord(first_char) - 32`) on UTF-16 XML service definitions.
  - Verified `00B3` bit `0x0040` (`Powder_Settings`) controls the pre-ground bypass chute lock (`STATTEXT.txt` #2164/#2163).
  - Mapped functional test #135 (`0x87DD` in `TextsV1.1.4`): `'F%02u beantest'` / `'F%02u Beantest'`.
- **Hardware Telemetry Resolution Strategy**:
  - On `EF518`, the empty bean barrier blocks button presses at the front display before the main board grinder ever runs, explaining why puck thickness fallback alone cannot detect "Fill Beans" when idle.
  - Morning hardware reconnection plan: query `TP$:4\r\n` for live LCD messages ("BEANS" / "BOHNEN" / "ZRNA") and probe `#RB$:00E0` - `#RB$:00E5` for the direct SFR phototransistor input pin.

---

## [Build 20261103.1806] — 2026-11-03

### 🚀 Highlights & Architectural Clarifications

#### 1. Removal of Volatile Serial Bean Lockouts & UI Cleanup
- **Reverted Per-Session Brew Flag Lockouts**:
  - Live hardware testing established that `HZ[0][3]`, `HZ[3]` (flow pulses), `HZ[8]` (puck ticks), and `CS[39:43]` (`3FF0`) are per-power-session volatile states on Renesas MCU architectures that reset to `0` / empty on power-off and only activate after brewing an initial coffee.
  - Removed forced serial lockouts (`CS[39:43]`, `RE:0029`, `HZ[0][3]`) from `stats_collector.py` and `crates/spectra-core/src/jura.rs` to prevent false "Fill Beans" appliance readiness deadlocks.
  - Standardized bean hopper charge evaluation on physical puck-compression thickness fallback (`0 < cake_thickness_ticks <= 14`).
  - Preserved ultra-fast auto-polling (`fast_poll=True`) querying only dynamic `HZ:` frames (~50ms latency) without serial bus contention.
  - Removed obsolete `optical_bean_sensor` false "EMPTY" card from UI sensor list, keeping the verified `heater_ntc_diagnostic_sensor` (`AS:` Coffee Heater NTC $+6.0\%$ Shunt Self-Test).

#### 2. Display Sub-Bus (`$:`) Protocol & Renesas R8C Reverse-Engineering
- **Display MCU Command Jump Table**:
  - Reverse-engineered front display microcontroller firmware `DE_EN_FlashDisplayZetaV4.0.4.LoaderV3.0.TextsV1.1.4.Common.bin` (`EF518D`, Renesas R8C) at offset `0x002634`.
  - Discovered full `$:` diagnostic command family: `TY$:` (`0x126E`), `TL$:` (`tl$:R8C Loader V2.0`), `TS$:` (`0x1578`), `ST$:` (`0x15C2`), `CP$:` (`0x15F8`), `TP$:` (`0x175C`), `#PO$:` (`0x1726`), `#RB$:` (`0x1652`).
  - Proved `TS$:` queries live display line text (`TS$:4,01` -> `ts$:   JAZYK`, `TS$:4,02` -> `ts$:  CESKY`, `TS$:4,03` -> `ts$:PRIPRAVEN`).
- **Physical Bean Hopper Circuit Architecture on `EF518`**:
  - Proved that on `EF518` (IMPRESSA XJ5/XJ9), the IR bean barrier phototransistor connects directly to the front display board (`EF518D`, R8C) and is not exposed over serial to the main board (`EF518M`).
  - Confirmed via `P518Ani.exe` strings `#669/#670/#738/#739` and `ALPHA.tcr` / `EF528.tcr` that even official Jura Service Suite factory test mode does not read an electronic hopper status byte over UART, but relies on an operator visual test ("BEANS FULL" appears on screen, technician clicks Continue).
  - Decoded `STATTEXT.txt` strings `2162/2163/2164` (`00B3` bit `0x0040`), confirming it controls the pre-ground bypass powder chute release/lock, not the optical hopper.

---

## [Build 20261103.1330] — 2026-11-03

### 🚀 Highlights & Bug Fixes

#### 1. Ground Truth Bean Status Latch (`RE:0029`) & Real-Time Auto-Poll Gating
- **Resolved "Fill Beans" vs. "Charged" Display Discrepancy**:
  - Addressed customer issue where Jura IMPRESSA XJ5 (`EF518M`) physical display reported *"Fill Beans"* (*"Doplňte kávová zrna"*), but SPECTRA Web UI still reported *"Charged"*.
  - **Root Cause**: On Renesas MCU microcode, `HZ:` frame bit `parts[0][3]` does not immediately clear to `'0'` at appliance idle when beans run low; it remained `'1'` (`hz:010101100000`). Because the Web UI polls with `fast_poll=True`, non-volatile register `RE:0029` was omitted from queries, and `beans_ok` was wrongly computed as `True` from `parts[0][3] == '1'`.
- **Periodic Fast Polling of `RE:0029`**:
  - In `stats_collector.py`, added ~1.0s periodic polling of `RE:0029` during `fast_poll` on commercial models (`EF518M` XJ5, GIGA, or where `_as_supported` is True).
  - Evaluated `RE:0029` bit `0x0040` (`0x004C` = Charged, `0x000C` = Empty) as the definitive ground truth latch. When bit `0x0040` is cleared, `beans_ok` is immediately evaluated as `False`, `machine_ready` transitions to `False` (*"Not Ready (Fill Beans)"*), and the Web UI displays *"Fill Beans"* / *"EMPTY"*.
- **Comprehensive Test Coverage**:
  - Added test case `mock_xj5_empty_r29` in `test_thermal_and_dual_heaters.py` verifying that when `HZ[0][3]` is `'1'` but `RE:0029` is `0x000C`, `beans_ok` is `False` and `machine_ready` is blocked.
  - Verified against live physical hardware on `/dev/ttyUSB0` via `/api/sensors` fast-poll endpoint.

---

## [Build 20261103.1225] — 2026-11-03

### 🚀 Highlights & Major Capabilities

#### 1. Hardware-Verified IMPRESSA XJ5 Bean Hopper State & Readiness Architecture
- **Direct Physical State Detection via `HZ` Telemetry**:
  - Live bean hopper level on commercial optical-equipped Jura lines (`EF518M` XJ5, GIGA) is driven directly by bit 3 of the `HZ:` status word (`parts[0][3] == '1'` -> Beans OK / Charged; `parts[0][3] == '0'` -> Fill Beans / Hopper Empty).
  - Physical machine readiness (`machine_ready`) is strictly gated on `beans_ok`: when `parts[0][3] == '0'`, the UI immediately reports **"Fill Beans"** and blocks readiness.
  - On standard domestic lines (`S8`, `E8`, `A1`, `D4`), the proven puck-compression thickness ($\le 14$ ticks) and `@TF:` alert fallback logic is cleanly preserved.
- **Non-Volatile Confirmation via `RE:0029`**:
  - Parsed non-volatile register `RE:0029` bit `0x0040` (`0x004C` = Charged, `0x000C` = Empty) on full interrogation polls as non-volatile EEPROM confirmation of the bean charge latch.
  - Complete `RE:0029` bitmask documented: `0x0001` External Filter active, `0x0010` CLARIS Filter active, `0x0020` Grinder calibration offset, `0x0040` Bean hopper charged latch, `0x0480` Factory hydraulic fill flag, `0x1000` First-use commissioning flag.

#### 2. Reverse-Engineering of Jura Service Suite (`P518Ani.exe`) & Reclassification of `AS:`
- **Disassembly of Check Sensor (`VA 0x004E6E28`)**:
  - Reverse-engineered Delphi routine in `P518Ani.exe` querying `AS:` (`as:VREF,OFF,0000,VREF,ON,0001`).
  - Proved that `AS:` does **not** query an optical bean hopper sensor, but is the **Coffee Heater NTC Diagnostic Sensor $+6.0\%$ Shunt Self-Test**.
  - Correlated with `Endtest.txt` String ID 251 (`0xFB`): `"-Sensor Kaffee-Heizung meldet falsche Werte !"` / `"-Coffee heater sensor notifies false values !"`.
  - Valid window verified: `180 < off_adc < 17000`, with nominal $+6.0\%$ internal Renesas MCU calibration shunt ratio $\text{ON}/\text{OFF} \approx 1.060 \pm 0.010$.
  - Reclassified `AS:` telemetry across Python backend, Rust `crates/spectra-core` (`OpticalSensorReading` with `shunt_ratio` and `is_ntc_self_test_valid`), and Web UI (`SpectraWorkspace.jsx`, `DigitalTwinSchematic.jsx`, `MemMapperTab.jsx`), while preserving backward-compatible aliases.

#### 3. Diagnostic Commands Discovery (`FA:01` & `RR:`)
- **`FA:01` Hardware Fault Latch Reset**:
  - Probed Jura `FA:` command table entry (`VA 0x004D5180`).
  - Discovered that `FA:01` performs an active diagnostic fault reset (`Fehlerspeicher löschen`), clearing `RE:0028` non-volatile error latch and transitioning the machine safely to standby.
- **RAM Interrogation (`RR:`)**:
  - Probed `RR:` (Read RAM, index 3). Hardware probing confirmed Renesas microcode on EF518M restricts direct RAM dumps via `RR:`, directing volatile telemetry queries through `HZ:`, `CS:`, and `RT:` blocks.

---

## [Build 20261102.1738] — 2026-11-02

### 🚀 Highlights & Major Capabilities

#### 1. Windows Native Standalone Suite, Offline Installer & Fast In-Place Updater
- **Offline Standalone Installer (`dist/spectra_setup_build20261102.1738.exe`)**:
  - Fully self-contained PE32+ native installer compiled via Zig + LLVM-RC.
  - Bundles embedded Python 3.12 64-bit runtime, pre-configured `pyserial`, React SPA assets, and profile definitions.
  - Installs to `%LOCALAPPDATA%\Programs\SPECTRA`, creates Start Menu and Desktop shortcuts with high-resolution vector-rendered icons, and registers in Windows *Add or Remove Programs* with clean uninstallation.
- **Fast In-Place Updater (`dist/spectra_update_build20261102.1738.exe`)**:
  - Ultra-lightweight (~885 KB) updater that updates Python logic, drivers, React frontend bundles, and device profiles in-place without re-downloading the Python runtime.
- **Zero-Dependency Launcher (`bin/spectra.exe`)**:
  - Standalone Win32 PE32+ executable that auto-locates the runtime, spins up the telemetry engine on a dynamically allocated port, and launches the default browser interface.

#### 2. Windows Serial & Web Server Stability Hardening
- **Resolved `ConnectionAbortedError [WinError 10053]`**:
  - Handled client socket aborts and resets across `_send_json`, `_serve_static`, and file responses in `web_server.py` and `gui_web.py`.
- **Eliminated 20 Hz Win32 `SetCommTimeouts` Driver Thrashing**:
  - Refactored `serial_io.py:read()` to cache applied timeouts, eliminating redundant `SetCommTimeouts` Win32 syscalls during tight 50ms polling iterations that previously caused USB UART buffer stalls.
- **Stateful Error Debouncing & Session Persistence**:
  - Added consecutive error tracking (`_consecutive_sensor_errors`) in `/api/sensors`. Transient single-packet serial glitches no longer tear down `_active_session` or close the COM port. Cached nominal telemetry is retained during transient jitter.
- **Frontend Polling Queue Guard**:
  - Added `inFlightPollRef` in `SpectraWorkspace.jsx` to drop overlapping auto-poll requests if a prior serial query is still awaiting hardware response, preventing socket pileup and client-side aborts.
  - Added `pollFailCountRef` to suppress spurious red warning banner flashes during transient network or serial retries.

#### 3. 3-Layer Rust / Tauri v2 / PyO3 Hybrid Architecture
- **`crates/spectra-hal`**:
  - Universal hardware abstraction layer supporting direct RS-232/UART and Android ADB `/dev/ttyS*` bridge streaming with strict path validation and POSIX baud configuration.
- **`crates/spectra-core`**:
  - High-performance, zero-allocation protocol decoders and state machines for Jura (Plain ASCII & `@`-cipher), Nivona, Lamanti-KL (Kalerm Modbus RTU), and Lamanti-JN (Jetinno custom binary frames).
  - Differential EEPROM mappers and J.O.E. auto-correlators.
- **`crates/spectra-agent`**:
  - Tauri v2 async IPC backend connecting native desktop surfaces to real-time hardware telemetry.
- **`crates/spectra-py`**:
  - PyO3 native C-extension (`spectra_py.so`) bridging high-speed Rust decoders to Python runtimes.

#### 4. Multi-Manufacturer Telemetry Engine & Legacy Jura SW Recovery
- **Unified Multi-Vendor Driver Support**:
  - Integrated drivers for Jura, Nivona (NICR series), Lamanti-KL / Kalerm (Modbus RTU), and Lamanti-JN / Jetinno (binary serial).
- **Optical Infrared Bean Hopper Sensor (`AS:`)**:
  - Dynamic reflection delta calculation ($\Delta = \text{ON\_ADC} - \text{OFF\_ADC}$) with configurable threshold ($115 \pm 5$) and hysteresis band ($110 \dots 120$ counts) for thermal drift compensation.
- **Physical Safety Invariants & Diagnostic Gating**:
  - Physical `machine_ready` gating based strictly on live `HZ:` physical sensors (Thermoblock $\ge 80^\circ\text{C}$, Drip Tray inserted, Water Tank full, Grounds container not full, appliance idle), decoupling readiness from historical non-volatile EEPROM fault latches (`RE:0028`, `RE:01B4`).
  - Added `CS:` and `CS$:` diagnostic checksum validation, loader version interrogation (`TL:` / `TL$:`), and Renesas RL78 EEPROM layout decoding for modern Jura commercial lines (WE8, XJ5, Z10).
- **Field Capture & Correlator Tool (`spectra_probe.py`)**:
  - Automated field diagnostic captures with J.O.E. CSV auto-correlation for rapid protocol reverse engineering.

#### 5. Build-Number-Only Branding Invariant
- Deprecated semantic version strings across all UI badges, CLI banners, Tauri configurations, and installer headers.
- Standardized metadata on build timestamp: `Build 20261102.1738`.

---
