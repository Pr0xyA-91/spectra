//! Tauri v2 IPC Command Backend and Async Agent Runtime for SPECTRA Diagnostics

use std::collections::BTreeMap;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;

use spectra_core::{
    diff_eeprom_blocks, AddressingMode, EepromWordDiff, HzTelemetryFrame, JuraClient, JuraCommand,
    JuraProtocol, JuraResponse,
};
use spectra_hal::{
    AdbBridgeConfig, AdbSerialBridge, AdbSocketEndpoint, SerialConfig, SerialTransport, Transport,
};

/// Specification and design tokens for the five supported UI paradigms.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct UiParadigmInfo {
    pub id: String,
    pub name: String,
    pub code: String,
    pub concept: String,
    pub primary_accent: String,
    pub secondary_accent: String,
    pub bg_surface: String,
}

/// Global active session state maintained across UI IPC interactions.
#[derive(Default)]
pub struct SessionState {
    pub client: Option<JuraClient<Box<dyn Transport>>>,
    pub active_port: Option<String>,
    pub baseline_eeprom: BTreeMap<u16, u16>,
}

/// Thread-safe reference-counted state container for Tauri / async IPC handlers.
#[derive(Clone, Default)]
pub struct AppState {
    pub inner: Arc<Mutex<SessionState>>,
}

impl AppState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(Mutex::new(SessionState::default())),
        }
    }
}

// ============================================================================
// Asynchronous IPC Handlers
// ============================================================================

/// Enumerates physical serial port nodes available on the host machine.
pub async fn list_serial_ports() -> Result<Vec<String>, String> {
    SerialTransport::list_ports().map_err(|e| e.to_string())
}

/// Connects to a physical RS232 / USB-UART serial adapter.
pub async fn connect_serial(
    state: &AppState,
    port: String,
    baud_rate: Option<u32>,
) -> Result<String, String> {
    let baud = baud_rate.unwrap_or(9600);
    let config = SerialConfig {
        port_path: port.clone(),
        baud_rate: baud,
        timeout: Duration::from_millis(1500),
        inter_byte_delay: Some(Duration::from_millis(8)),
    };

    let transport = SerialTransport::open(config).map_err(|e| e.to_string())?;
    let boxed: Box<dyn Transport> = Box::new(transport);
    let client = JuraClient::new(boxed)
        .with_inter_byte_delay(Duration::from_millis(8))
        .with_timeout(Duration::from_millis(1500));

    let mut lock = state.inner.lock().await;
    lock.client = Some(client);
    lock.active_port = Some(port.clone());

    Ok(format!("Connected to serial port {port} at {baud} bps"))
}

/// Connects to an Android SBC UART via ADB port forwarding (TCP or Unix socket).
pub async fn connect_adb(
    state: &AppState,
    addr_or_path: String,
    tty_path: String,
    is_unix: Option<bool>,
    baud_rate: Option<u32>,
) -> Result<String, String> {
    let timeout = Duration::from_secs(3);
    let baud = baud_rate.unwrap_or(115200);
    let use_unix = is_unix.unwrap_or(false);

    let endpoint = if use_unix {
        AdbSocketEndpoint::Unix(PathBuf::from(&addr_or_path))
    } else {
        let addr: SocketAddr = addr_or_path
            .parse()
            .map_err(|e| format!("Invalid TCP socket addr '{addr_or_path}': {e}"))?;
        AdbSocketEndpoint::Tcp(addr)
    };

    let config = AdbBridgeConfig {
        device_serial: None,
        tty_path: tty_path.clone(),
        baud_rate: baud,
        endpoint,
        remote_forward_spec: "localabstract:spectra_uart".to_string(),
        connect_timeout: timeout,
    };

    let bridge = AdbSerialBridge::connect(config)
        .await
        .map_err(|e| e.to_string())?;
    let boxed: Box<dyn Transport> = Box::new(bridge);
    let client = JuraClient::new(boxed)
        .with_inter_byte_delay(Duration::from_millis(8))
        .with_timeout(timeout);

    let mut lock = state.inner.lock().await;
    lock.client = Some(client);
    lock.active_port = Some(format!("ADB:{tty_path}"));

    Ok(format!("Connected to ADB serial bridge on {tty_path}"))
}

/// Disconnects the active serial or ADB session.
pub async fn disconnect_session(state: &AppState) -> Result<String, String> {
    let mut lock = state.inner.lock().await;
    let prev = lock.active_port.take();
    lock.client = None;
    lock.baseline_eeprom.clear();
    Ok(format!("Disconnected session: {}", prev.unwrap_or_else(|| "none".into())))
}

/// Polls live machine telemetry (`HZ:` frame) and decodes all metric sensors.
pub async fn poll_telemetry(
    state: &AppState,
    delta_t_sec: Option<f32>,
) -> Result<HzTelemetryFrame, String> {
    let mut lock = state.inner.lock().await;
    let client = lock
        .client
        .as_mut()
        .ok_or_else(|| "No active connection session".to_string())?;

    client
        .poll_telemetry(delta_t_sec.unwrap_or(1.0))
        .await
        .map_err(|e| e.to_string())
}

/// Sends a formatted Jura command with full safety invariant enforcement.
pub async fn send_jura_command(
    state: &AppState,
    command: String,
    _fast: Option<bool>,
) -> Result<String, String> {
    JuraProtocol::validate_safety(&command).map_err(|e| e.to_string())?;

    let mut lock = state.inner.lock().await;
    let client = lock
        .client
        .as_mut()
        .ok_or_else(|| "No active connection session".to_string())?;

    let cmd = JuraCommand::RawSafe(command);
    let resp = client.send_command(&cmd).await.map_err(|e| e.to_string())?;

    let resp_str = match resp {
        JuraResponse::Firmware(s) => format!("TY:{s}"),
        JuraResponse::DisplayFirmware(s) => format!("TY$:{s}"),
        JuraResponse::Bootloader(s) => format!("TL:{s}"),
        JuraResponse::PowerSpec(s) => format!("IC:{s}"),
        JuraResponse::EEPROMWord(w) => format!("RE:{w:04X}"),
        JuraResponse::EEPROMBlock(words) => {
            let hex: String = words.iter().map(|w| format!("{w:04X}")).collect();
            format!("RT:{hex}")
        }
        JuraResponse::Telemetry(f) => format!("HZ:temp_c={:.1},busy={}", f.coffee_temp_c, f.is_busy),
        JuraResponse::CodeChecksum(s) => format!("CS:{s}"),
        JuraResponse::Optical(opt) => {
            format!("AS:amb={},ref={},delta={},state={:?}", opt.ambient_adc, opt.reflected_adc, opt.delta, opt.state)
        }
        JuraResponse::Ack(s) => s,
    };

    Ok(resp_str)
}

/// Reads a 16-word EEPROM block and updates internal baseline memory cache.
pub async fn read_eeprom_block(
    state: &AppState,
    block_index: u16,
    two_digit: Option<bool>,
) -> Result<Vec<u16>, String> {
    let mut lock = state.inner.lock().await;
    let client = lock
        .client
        .as_mut()
        .ok_or_else(|| "No active connection session".to_string())?;

    let mode = if two_digit.unwrap_or(false) {
        AddressingMode::TwoDigit
    } else {
        AddressingMode::FourDigit
    };
    client.set_addressing_mode(mode);

    let words = client
        .read_eeprom_block(block_index)
        .await
        .map_err(|e| e.to_string())?;

    // Cache into baseline snapshot
    let start_addr = block_index * 16;
    for (i, &w) in words.iter().enumerate() {
        lock.baseline_eeprom.insert(start_addr + i as u16, w);
    }

    Ok(words)
}

/// Diffs baseline EEPROM words against a current snapshot.
pub async fn diff_eeprom_snapshots(
    baseline: Vec<u16>,
    current: Vec<u16>,
    start_addr: u16,
) -> Result<Vec<EepromWordDiff>, String> {
    Ok(diff_eeprom_blocks(&baseline, &current, start_addr))
}

/// Returns definitions for all 5 UI design paradigms.
pub async fn get_ui_paradigms() -> Result<Vec<UiParadigmInfo>, String> {
    Ok(vec![
        UiParadigmInfo {
            id: "netrunner".into(),
            name: "01 // NETRUNNER".into(),
            code: "cyberpunk".into(),
            concept: "Militech / Arasaka Cyber-Deck Telemetry".into(),
            primary_accent: "#FCEE09".into(),
            secondary_accent: "#00F0FF".into(),
            bg_surface: "#070709".into(),
        },
        UiParadigmInfo {
            id: "tek-dark".into(),
            name: "02 // TEK-DARK".into(),
            code: "oscilloscope".into(),
            concept: "Benchtop DSO & Mixed-Domain Logic Analyzer".into(),
            primary_accent: "#00FF66".into(),
            secondary_accent: "#FFB000".into(),
            bg_surface: "#0B0F17".into(),
        },
        UiParadigmInfo {
            id: "hypr-tui".into(),
            name: "03 // HYPR-TUI".into(),
            code: "omarchy".into(),
            concept: "Wayland Tiling Window Manager & TUI Multiplexer".into(),
            primary_accent: "#7AA2F7".into(),
            secondary_accent: "#BB9AF7".into(),
            bg_surface: "#1A1B26".into(),
        },
        UiParadigmInfo {
            id: "rocinante".into(),
            name: "04 // ROCINANTE".into(),
            code: "expanse".into(),
            concept: "MCRN Corvette Tactical Bus Diagnostics".into(),
            primary_accent: "#FF7700".into(),
            secondary_accent: "#38BDF8".into(),
            bg_surface: "#060911".into(),
        },
        UiParadigmInfo {
            id: "braun-eng".into(),
            name: "05 // BRAUN-ENG".into(),
            code: "swiss".into(),
            concept: "Cleanroom Daylight Hardware Instrumentation".into(),
            primary_accent: "#FF4F00".into(),
            secondary_accent: "#18181B".into(),
            bg_surface: "#F4F3EF".into(),
        },
    ])
}

/// Diagnostic hardware capture bundle matching the format exported by probe & web UI.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiagnosticCaptureBundle {
    pub timestamp: String,
    pub target_port: String,
    pub eeprom_words: BTreeMap<u16, u16>,
    pub word_count: usize,
}

/// Creates a snapshot capture bundle of all interrogated EEPROM memory words.
pub async fn export_diagnostic_capture(
    state: &AppState,
) -> Result<DiagnosticCaptureBundle, String> {
    let lock = state.inner.lock().await;
    let port = lock.active_port.clone().unwrap_or_else(|| "none".into());
    let words = lock.baseline_eeprom.clone();
    let word_count = words.len();
    let timestamp = format!("{:?}", std::time::SystemTime::now());

    Ok(DiagnosticCaptureBundle {
        timestamp,
        target_port: port,
        eeprom_words: words,
        word_count,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_ui_paradigms_enumeration() {
        let paradigms = get_ui_paradigms().await.expect("get paradigms");
        assert_eq!(paradigms.len(), 5);
        assert_eq!(paradigms[0].id, "netrunner");
        assert_eq!(paradigms[1].id, "tek-dark");
        assert_eq!(paradigms[2].id, "hypr-tui");
        assert_eq!(paradigms[3].id, "rocinante");
        assert_eq!(paradigms[4].id, "braun-eng");
    }

    #[tokio::test]
    async fn test_diff_eeprom_snapshots_handler() {
        let base = vec![0x1000, 0x2000, 0x3000];
        let curr = vec![0x1000, 0x2001, 0x3000];
        let diffs = diff_eeprom_snapshots(base, curr, 0x0020).await.expect("diff");
        assert_eq!(diffs.len(), 1);
        assert_eq!(diffs[0].addr, 0x0021);
        assert_eq!(diffs[0].baseline, 0x2000);
        assert_eq!(diffs[0].current, 0x2001);
        assert_eq!(diffs[0].flipped_bits, 0x0001);
    }

    #[tokio::test]
    async fn test_safety_validation_in_send_command() {
        let state = AppState::new();
        let err = send_jura_command(&state, "AN:".into(), None).await.expect_err("should reject AN:");
        assert!(err.contains("Safety invariant violation") || err.contains("powers off machine"));

        let err2 = send_jura_command(&state, "FA:".into(), None).await.expect_err("should reject FA:");
        assert!(err2.contains("factory reset"));
    }

    #[tokio::test]
    async fn test_export_diagnostic_capture() {
        let state = AppState::new();
        {
            let mut lock = state.inner.lock().await;
            lock.active_port = Some("/dev/ttyUSB0".to_string());
            lock.baseline_eeprom.insert(0x0180, 1450);
            lock.baseline_eeprom.insert(0x0181, 137);
        }
        let bundle = export_diagnostic_capture(&state).await.expect("export capture");
        assert_eq!(bundle.target_port, "/dev/ttyUSB0");
        assert_eq!(bundle.word_count, 2);
        assert_eq!(bundle.eeprom_words.get(&0x0180), Some(&1450));
    }
}
