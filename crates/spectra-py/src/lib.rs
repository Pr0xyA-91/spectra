//! PyO3 Hardware Diagnostics and Interactive Session Bridge for SPECTRA
#![allow(clippy::useless_conversion)]

use std::collections::VecDeque;
use std::net::SocketAddr;
#[cfg(unix)]
use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::Duration;

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};

use spectra_core::{
    AddressingMode, HzTelemetryFrame, JuraCommand, JuraProtocol, SmartConnectCipher,
};
#[cfg(unix)]
use spectra_hal::AdbStream;
use spectra_hal::{
    jura_codec, AdbBridgeConfig, AdbSerialBridge, AdbSocketEndpoint, HalError, Transport,
};

#[cfg(feature = "serial")]
use spectra_hal::{SerialConfig, SerialTransport};

const MAX_TELEMETRY_LOG_ENTRIES: usize = 500;
const MAX_FRAME_BYTES: usize = 16384;

static SHARED_RUNTIME: OnceLock<Result<tokio::runtime::Runtime, String>> = OnceLock::new();

fn shared_runtime() -> PyResult<&'static tokio::runtime::Runtime> {
    let res = SHARED_RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .map_err(|e| format!("Runtime error: {e}"))
    });
    match res {
        Ok(rt) => Ok(rt),
        Err(msg) => Err(pyo3::exceptions::PyIOError::new_err(msg.clone())),
    }
}

/// Real-time metric telemetry frame decoded from Jura `HZ:` responses.
#[pyclass(from_py_object)]
#[derive(Debug, Clone, PartialEq)]
pub struct PyHzTelemetry {
    #[pyo3(get)]
    pub coffee_temp_c: f32,
    #[pyo3(get)]
    pub steam_temp_c: Option<f32>,
    #[pyo3(get)]
    pub flowmeter_pulses: u16,
    #[pyo3(get)]
    pub flow_rate_ml_s: f32,
    #[pyo3(get)]
    pub bu_upper_encoder: u16,
    #[pyo3(get)]
    pub bu_current_encoder: u16,
    #[pyo3(get)]
    pub rotary_pos: u8,
    #[pyo3(get)]
    pub drip_tray_missing: bool,
    #[pyo3(get)]
    pub grounds_full: bool,
    #[pyo3(get)]
    pub water_tank_empty: bool,
    #[pyo3(get)]
    pub mcu_heartbeat_tick: bool,
    #[pyo3(get)]
    pub is_busy: bool,
    #[pyo3(get)]
    pub heater_ready: bool,
    #[pyo3(get)]
    pub bu_initialized: bool,
    #[pyo3(get)]
    pub valve_busy: bool,
    #[pyo3(get)]
    pub puck_thickness_ticks: u16,
    #[pyo3(get)]
    pub beans_charged: bool,
}

#[pymethods]
impl PyHzTelemetry {
    fn __repr__(&self) -> String {
        format!(
            "PyHzTelemetry(coffee_temp_c={:.1}, steam_temp_c={:?}, flow_rate_ml_s={:.2}, busy={}, heater_ready={}, beans_charged={})",
            self.coffee_temp_c, self.steam_temp_c, self.flow_rate_ml_s, self.is_busy, self.heater_ready, self.beans_charged
        )
    }

    /// Converts telemetry attributes into a standard Python dictionary.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("coffee_temp_c", self.coffee_temp_c)?;
        dict.set_item("steam_temp_c", self.steam_temp_c)?;
        dict.set_item("flowmeter_pulses", self.flowmeter_pulses)?;
        dict.set_item("flow_rate_ml_s", self.flow_rate_ml_s)?;
        dict.set_item("bu_upper_encoder", self.bu_upper_encoder)?;
        dict.set_item("bu_current_encoder", self.bu_current_encoder)?;
        dict.set_item("rotary_pos", self.rotary_pos)?;
        dict.set_item("drip_tray_missing", self.drip_tray_missing)?;
        dict.set_item("grounds_full", self.grounds_full)?;
        dict.set_item("water_tank_empty", self.water_tank_empty)?;
        dict.set_item("mcu_heartbeat_tick", self.mcu_heartbeat_tick)?;
        dict.set_item("is_busy", self.is_busy)?;
        dict.set_item("heater_ready", self.heater_ready)?;
        dict.set_item("bu_initialized", self.bu_initialized)?;
        dict.set_item("valve_busy", self.valve_busy)?;
        dict.set_item("puck_thickness_ticks", self.puck_thickness_ticks)?;
        dict.set_item("beans_charged", self.beans_charged)?;
        Ok(dict.unbind())
    }
}

impl From<HzTelemetryFrame> for PyHzTelemetry {
    fn from(f: HzTelemetryFrame) -> Self {
        Self {
            coffee_temp_c: f.coffee_temp_c,
            steam_temp_c: f.steam_temp_c,
            flowmeter_pulses: f.flowmeter_pulses,
            flow_rate_ml_s: f.flow_rate_ml_s,
            bu_upper_encoder: f.bu_upper_encoder,
            bu_current_encoder: f.bu_current_encoder,
            rotary_pos: f.rotary_pos,
            drip_tray_missing: f.drip_tray_missing,
            grounds_full: f.grounds_full,
            water_tank_empty: f.water_tank_empty,
            mcu_heartbeat_tick: f.mcu_heartbeat_tick,
            is_busy: f.is_busy,
            heater_ready: f.heater_ready,
            bu_initialized: f.bu_initialized,
            valve_busy: f.valve_busy,
            puck_thickness_ticks: f.puck_thickness_ticks,
            beans_charged: f.beans_charged,
        }
    }
}

fn read_ascii_response(
    rt: &tokio::runtime::Runtime,
    transport: &mut Box<dyn Transport>,
    timeout: Duration,
    obfuscate_4byte: bool,
) -> PyResult<String> {
    let start = std::time::Instant::now();
    let mut raw_buf = Vec::with_capacity(256);
    let mut decoded_bytes = Vec::with_capacity(64);
    let mut decoded_groups: usize = 0;

    loop {
        if start.elapsed() >= timeout {
            return Err(pyo3::exceptions::PyTimeoutError::new_err(
                "Timeout waiting for response from machine",
            ));
        }
        let remaining = timeout.saturating_sub(start.elapsed());
        let mut chunk = [0u8; 64];
        let n = rt
            .block_on(transport.read_raw(&mut chunk, remaining))
            .map_err(|e| match e {
                HalError::Timeout(d) => {
                    pyo3::exceptions::PyTimeoutError::new_err(format!("Timeout after {d:?}"))
                }
                _ => pyo3::exceptions::PyIOError::new_err(e.to_string()),
            })?;

        if n == 0 {
            break;
        }
        if raw_buf.len().saturating_add(n) > MAX_FRAME_BYTES {
            return Err(pyo3::exceptions::PyIOError::new_err(format!(
                "Response frame exceeded {MAX_FRAME_BYTES} byte limit"
            )));
        }
        raw_buf.extend_from_slice(&chunk[..n]);

        if obfuscate_4byte {
            let total_groups = raw_buf.len() / 4;
            while decoded_groups < total_groups {
                let base = decoded_groups * 4;
                let quad = [
                    raw_buf[base],
                    raw_buf[base + 1],
                    raw_buf[base + 2],
                    raw_buf[base + 3],
                ];
                let byte = jura_codec::decode_quad(&quad).map_err(|e| {
                    pyo3::exceptions::PyValueError::new_err(format!(
                        "Failed to decode wire frame: {e}"
                    ))
                })?;
                decoded_bytes.push(byte);
                decoded_groups += 1;
            }
            if decoded_bytes.ends_with(b"\r\n")
                || decoded_bytes.ends_with(b"\n")
                || decoded_bytes.ends_with(b"\r")
            {
                return Ok(String::from_utf8_lossy(&decoded_bytes).trim().to_string());
            }
        } else if raw_buf.contains(&b'\n') || raw_buf.contains(&b'\r') {
            if let Ok(s) = std::str::from_utf8(&raw_buf) {
                if s.ends_with("\r\n") || s.ends_with('\n') || s.ends_with('\r') {
                    return Ok(s.trim().to_string());
                }
            }
        }
    }

    if raw_buf.is_empty() {
        return Err(pyo3::exceptions::PyTimeoutError::new_err(
            "No response received from target",
        ));
    }

    if obfuscate_4byte {
        if raw_buf.len() % 4 != 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Failed to decode wire frame: incomplete 4-byte group ({} bytes)",
                raw_buf.len()
            )));
        }
        Ok(String::from_utf8_lossy(&decoded_bytes).trim().to_string())
    } else {
        Ok(String::from_utf8_lossy(&raw_buf).trim().to_string())
    }
}

fn read_hex_response(
    rt: &tokio::runtime::Runtime,
    transport: &mut Box<dyn Transport>,
    timeout: Duration,
) -> PyResult<String> {
    let mut raw_buf = Vec::with_capacity(128);
    let mut chunk = [0u8; 64];

    let n = rt
        .block_on(transport.read_raw(&mut chunk, timeout))
        .map_err(|e| match e {
            HalError::Timeout(d) => {
                pyo3::exceptions::PyTimeoutError::new_err(format!("Timeout after {d:?}"))
            }
            _ => pyo3::exceptions::PyIOError::new_err(e.to_string()),
        })?;

    if n > 0 {
        raw_buf.extend_from_slice(&chunk[..n]);
        // Short 5ms adaptive quiet poll to coalesce back-to-back bytes without blocking for 25ms
        while raw_buf.len() < MAX_FRAME_BYTES {
            let mut more = [0u8; 64];
            match rt.block_on(transport.read_raw(&mut more, Duration::from_millis(5))) {
                Ok(count) if count > 0 => {
                    let take = count.min(MAX_FRAME_BYTES - raw_buf.len());
                    raw_buf.extend_from_slice(&more[..take]);
                }
                _ => break,
            }
        }
    }

    let hex_resp = raw_buf
        .iter()
        .map(|b| format!("{b:02X}"))
        .collect::<Vec<_>>()
        .join(" ");
    Ok(hex_resp)
}

/// Interactive diagnostics and telemetry session for Jura machines.
#[pyclass]
pub struct JuraSession {
    runtime: &'static tokio::runtime::Runtime,
    transport: Box<dyn Transport>,
    inter_byte_delay: Duration,
    timeout: Duration,
    telemetry_log: VecDeque<String>,
}

impl JuraSession {
    /// Creates a `JuraSession` directly wrapping an existing `Transport` (useful for testing).
    pub fn from_transport(
        transport: Box<dyn Transport>,
        inter_byte_delay: Duration,
        timeout: Duration,
    ) -> PyResult<Self> {
        let rt = shared_runtime()?;
        Ok(Self {
            runtime: rt,
            transport,
            inter_byte_delay,
            timeout,
            telemetry_log: VecDeque::with_capacity(MAX_TELEMETRY_LOG_ENTRIES),
        })
    }

    fn push_log(&mut self, entry: String) {
        if self.telemetry_log.len() >= MAX_TELEMETRY_LOG_ENTRIES {
            self.telemetry_log.pop_front();
        }
        self.telemetry_log.push_back(entry);
    }

    const LAB_WRITE_CONFIRM_TOKEN: &'static str = "SPECTRA_LAB_WRITE";

    fn check_lab_override(
        enforce_safety: Option<bool>,
        lab_confirm_token: Option<&str>,
    ) -> PyResult<bool> {
        let enforce = enforce_safety.unwrap_or(true);
        if !enforce && lab_confirm_token != Some(Self::LAB_WRITE_CONFIRM_TOKEN) {
            return Err(pyo3::exceptions::PyPermissionError::new_err(
                "Disabling hardware safety requires explicit lab_confirm_token='SPECTRA_LAB_WRITE'",
            ));
        }
        Ok(enforce)
    }

    fn validate_raw_hex_readonly(raw_bytes: &[u8]) -> PyResult<()> {
        if raw_bytes.is_empty() || raw_bytes.len() > 256 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Raw hex payload length {} outside allowed range (1..=256 bytes)",
                raw_bytes.len()
            )));
        }

        // Case 1: Plain ASCII Jura command bytes
        if let Ok(as_str) = std::str::from_utf8(raw_bytes) {
            if JuraProtocol::validate_safety(as_str).is_ok() {
                return Ok(());
            }
        }

        // Case 2: 4:1 wire-encoded Jura carrier frame
        if raw_bytes.len().is_multiple_of(4) {
            if let Ok(decoded) = JuraProtocol::decode_wire_frame(raw_bytes) {
                if JuraProtocol::validate_safety(&decoded).is_ok() {
                    return Ok(());
                }
            }
        }

        // Case 3: Verified read-only Modbus RTU query (FC 0x01..=0x04 with valid CRC-16)
        if raw_bytes.len() >= 4
            && matches!(raw_bytes[1], 0x01..=0x04)
            && spectra_core::KalermProtocol::verify_crc(raw_bytes)
        {
            return Ok(());
        }

        Err(pyo3::exceptions::PyValueError::new_err(
            "Safety invariant violation: raw hex payload is not a verified read-only frame; pass enforce_safety=False with lab_confirm_token='SPECTRA_LAB_WRITE' for explicit lab overrides",
        ))
    }

    fn send_ascii_inner(
        &mut self,
        cmd: &str,
        obfuscate_4byte: Option<bool>,
        enforce_safety: Option<bool>,
        lab_confirm_token: Option<&str>,
    ) -> PyResult<String> {
        let enforce = Self::check_lab_override(enforce_safety, lab_confirm_token)?;
        if enforce {
            JuraProtocol::validate_safety(cmd).map_err(|e| {
                pyo3::exceptions::PyValueError::new_err(format!("Safety invariant violation: {e}"))
            })?;
        } else {
            // Even in explicit lab override mode, forbid embedded CRLF injection / NUL bytes
            let stripped = cmd
                .strip_suffix("\r\n")
                .or_else(|| cmd.strip_suffix('\r'))
                .or_else(|| cmd.strip_suffix('\n'))
                .unwrap_or(cmd);
            if stripped.is_empty()
                || stripped.len() > 64
                || stripped.bytes().any(|b| !(0x20..0x7F).contains(&b))
            {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "Lab command must be a single-line printable ASCII string (1..=64 bytes)",
                ));
            }
        }

        let full_cmd = if cmd.ends_with("\r\n") {
            cmd.to_string()
        } else if cmd.ends_with('\n') {
            format!("{}\r\n", cmd.trim_end_matches('\n'))
        } else {
            format!("{cmd}\r\n")
        };

        let obfuscate = obfuscate_4byte.unwrap_or(true);
        let wire = if obfuscate {
            JuraProtocol::encode_wire_frame(&full_cmd)
        } else {
            full_cmd.as_bytes().to_vec()
        };

        self.runtime
            .block_on(self.transport.write_raw(&wire, Some(self.inter_byte_delay)))
            .map_err(|e| {
                pyo3::exceptions::PyIOError::new_err(format!("Transport write failure: {e}"))
            })?;

        let rx = read_ascii_response(self.runtime, &mut self.transport, self.timeout, obfuscate)?;
        self.push_log(format!("TX: {} -> RX: {}", full_cmd.trim(), rx));
        Ok(rx)
    }

    fn send_hex_inner(
        &mut self,
        hex_payload: &str,
        inter_byte_delay_ms: Option<u64>,
        enforce_safety: Option<bool>,
        lab_confirm_token: Option<&str>,
    ) -> PyResult<String> {
        let enforce = Self::check_lab_override(enforce_safety, lab_confirm_token)?;

        let clean_hex: String = hex_payload
            .chars()
            .filter(|c| !c.is_whitespace() && *c != ':')
            .collect();

        if !clean_hex.is_ascii() || !clean_hex.chars().all(|c| c.is_ascii_hexdigit()) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "Hex payload must contain strictly ASCII hexadecimal digits (0-9, A-F)",
            ));
        }

        if clean_hex.is_empty() || !clean_hex.len().is_multiple_of(2) {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Hex string must be non-empty and even-length (got {} chars)",
                clean_hex.len()
            )));
        }

        let (hex_pairs, _) = clean_hex.as_bytes().as_chunks::<2>();
        let raw_bytes: Vec<u8> = hex_pairs
            .iter()
            .map(|pair| {
                let s = std::str::from_utf8(pair).map_err(|e| {
                    pyo3::exceptions::PyValueError::new_err(format!("Invalid UTF-8 in hex pair: {e}"))
                })?;
                u8::from_str_radix(s, 16).map_err(|e| {
                    pyo3::exceptions::PyValueError::new_err(format!("Invalid hex byte in payload: {e}"))
                })
            })
            .collect::<PyResult<Vec<u8>>>()?;

        if enforce {
            Self::validate_raw_hex_readonly(&raw_bytes)?;
        }

        let delay = inter_byte_delay_ms
            .map(Duration::from_millis)
            .or(Some(self.inter_byte_delay));

        self.runtime
            .block_on(self.transport.write_raw(&raw_bytes, delay))
            .map_err(|e| {
                pyo3::exceptions::PyIOError::new_err(format!("Transport write failure: {e}"))
            })?;

        let hex_resp = read_hex_response(self.runtime, &mut self.transport, self.timeout)?;
        self.push_log(format!("TX_HEX: {clean_hex} -> RX_HEX: {hex_resp}"));
        Ok(hex_resp)
    }

    fn poll_telemetry_inner(
        &mut self,
        delta_t_sec: Option<f32>,
        obfuscate_4byte: Option<bool>,
    ) -> PyResult<PyHzTelemetry> {
        let rx = self.send_ascii_inner("HZ:", obfuscate_4byte, Some(true), None)?;
        let frame = JuraProtocol::parse_hz_response(&rx, delta_t_sec.unwrap_or(1.0))
            .map_err(|e| {
                pyo3::exceptions::PyValueError::new_err(format!("Failed to parse HZ telemetry: {e}"))
            })?;
        Ok(PyHzTelemetry::from(frame))
    }

    fn read_eeprom_block_inner(
        &mut self,
        block_index: u16,
        two_digit: Option<bool>,
        obfuscate_4byte: Option<bool>,
    ) -> PyResult<Vec<u16>> {
        let mode = if two_digit.unwrap_or(false) {
            AddressingMode::TwoDigit
        } else {
            AddressingMode::FourDigit
        };
        let cmd = JuraCommand::ReadEEPROMBlock { block_index, mode };
        let cmd_str = JuraProtocol::format_command(&cmd)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
        let rx = self.send_ascii_inner(&cmd_str, obfuscate_4byte, Some(true), None)?;
        let words = JuraProtocol::parse_rt_response(&rx).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Failed to parse RT block: {e}"))
        })?;
        Ok(words)
    }

    fn read_eeprom_word_inner(
        &mut self,
        addr: u16,
        two_digit: Option<bool>,
        obfuscate_4byte: Option<bool>,
    ) -> PyResult<u16> {
        let mode = if two_digit.unwrap_or(false) {
            AddressingMode::TwoDigit
        } else {
            AddressingMode::FourDigit
        };
        let cmd = JuraCommand::ReadEEPROMWord { addr, mode };
        let cmd_str = JuraProtocol::format_command(&cmd)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
        let rx = self.send_ascii_inner(&cmd_str, obfuscate_4byte, Some(true), None)?;
        let word = JuraProtocol::parse_re_response(&rx).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Failed to parse RE word: {e}"))
        })?;
        Ok(word)
    }
}

#[pymethods]
impl JuraSession {
    /// Opens a native physical UART connection (e.g. `"/dev/ttyUSB0"`).
    #[staticmethod]
    #[pyo3(signature = (port, baud_rate = None, inter_byte_delay_ms = None, timeout_ms = None))]
    pub fn open_uart(
        py: Python<'_>,
        port: &str,
        baud_rate: Option<u32>,
        inter_byte_delay_ms: Option<u64>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        let rt = shared_runtime()?;
        let baud = baud_rate.unwrap_or(9600);
        let delay = Duration::from_millis(inter_byte_delay_ms.unwrap_or(8));
        let timeout = Duration::from_millis(timeout_ms.unwrap_or(1000));

        #[cfg(feature = "serial")]
        {
            let config = SerialConfig {
                port_path: port.to_string(),
                baud_rate: baud,
                timeout,
                inter_byte_delay: Some(delay),
            };
            let transport = py.detach(|| {
                let _guard = rt.enter();
                SerialTransport::open(config)
                    .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))
            })?;
            Ok(Self {
                runtime: rt,
                transport: Box::new(transport),
                inter_byte_delay: delay,
                timeout,
                telemetry_log: VecDeque::with_capacity(MAX_TELEMETRY_LOG_ENTRIES),
            })
        }
        #[cfg(not(feature = "serial"))]
        {
            let _ = (py, rt, baud, delay, timeout, port);
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Serial feature not compiled into spectra-hal",
            ))
        }
    }

    /// Opens an ADB TCP bridge connecting to an Android SBC UART.
    #[staticmethod]
    #[pyo3(signature = (addr, tty_path, baud_rate = None, device_serial = None, remote_spec = None, timeout_ms = None))]
    pub fn open_adb_tcp(
        py: Python<'_>,
        addr: &str,
        tty_path: &str,
        baud_rate: Option<u32>,
        device_serial: Option<String>,
        remote_spec: Option<String>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        let rt = shared_runtime()?;
        let socket_addr: SocketAddr = addr.parse().map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid TCP socket address '{addr}': {e}"))
        })?;

        let timeout = Duration::from_millis(timeout_ms.unwrap_or(3000));
        let config = AdbBridgeConfig {
            device_serial,
            tty_path: tty_path.to_string(),
            baud_rate: baud_rate.unwrap_or(115200),
            endpoint: AdbSocketEndpoint::Tcp(socket_addr),
            remote_forward_spec: remote_spec.unwrap_or_else(|| "localabstract:spectra_uart".into()),
            connect_timeout: timeout,
        };

        let bridge = py.detach(|| {
            rt.block_on(AdbSerialBridge::connect(config))
                .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))
        })?;

        Ok(Self {
            runtime: rt,
            transport: Box::new(bridge),
            inter_byte_delay: Duration::from_millis(8),
            timeout,
            telemetry_log: VecDeque::with_capacity(MAX_TELEMETRY_LOG_ENTRIES),
        })
    }

    /// Opens an ADB Unix socket bridge connecting to an Android SBC UART.
    #[staticmethod]
    #[pyo3(signature = (socket_path, tty_path, baud_rate = None, device_serial = None, remote_spec = None, timeout_ms = None))]
    pub fn open_adb_unix(
        py: Python<'_>,
        socket_path: &str,
        tty_path: &str,
        baud_rate: Option<u32>,
        device_serial: Option<String>,
        remote_spec: Option<String>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        #[cfg(not(unix))]
        {
            let _ = (py, socket_path, tty_path, baud_rate, device_serial, remote_spec, timeout_ms);
            Err(pyo3::exceptions::PyNotImplementedError::new_err(
                "Unix domain sockets are only supported on Unix hosts",
            ))
        }
        #[cfg(unix)]
        {
            let rt = shared_runtime()?;
            let timeout = Duration::from_millis(timeout_ms.unwrap_or(3000));
            let config = AdbBridgeConfig {
                device_serial,
                tty_path: tty_path.to_string(),
                baud_rate: baud_rate.unwrap_or(115200),
                endpoint: AdbSocketEndpoint::Unix(PathBuf::from(socket_path)),
                remote_forward_spec: remote_spec.unwrap_or_else(|| "localabstract:spectra_uart".into()),
                connect_timeout: timeout,
            };

            let bridge = py.detach(|| {
                rt.block_on(AdbSerialBridge::connect(config))
                    .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))
            })?;

            Ok(Self {
                runtime: rt,
                transport: Box::new(bridge),
                inter_byte_delay: Duration::from_millis(8),
                timeout,
                telemetry_log: VecDeque::with_capacity(MAX_TELEMETRY_LOG_ENTRIES),
            })
        }
    }

    /// Connects directly to an already-bound local Unix socket via `AdbSerialBridge::from_stream`
    /// without running `adb` CLI (ideal for mock servers, unit tests, and local emulation).
    #[staticmethod]
    #[pyo3(signature = (socket_path, tty_path = None, inter_byte_delay_ms = None, timeout_ms = None))]
    pub fn open_unix_raw(
        py: Python<'_>,
        socket_path: &str,
        tty_path: Option<&str>,
        inter_byte_delay_ms: Option<u64>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        #[cfg(not(unix))]
        {
            let _ = (py, socket_path, tty_path, inter_byte_delay_ms, timeout_ms);
            Err(pyo3::exceptions::PyNotImplementedError::new_err(
                "Unix domain sockets are only supported on Unix hosts",
            ))
        }
        #[cfg(unix)]
        {
            let rt = shared_runtime()?;
            let timeout = Duration::from_millis(timeout_ms.unwrap_or(1000));
            let delay = Duration::from_millis(inter_byte_delay_ms.unwrap_or(8));
            let tty = tty_path.unwrap_or("/dev/ttyS1");

            let bridge = py.detach(|| {
                let stream = rt
                    .block_on(async { tokio::net::UnixStream::connect(socket_path).await })
                    .map_err(|e| {
                        pyo3::exceptions::PyConnectionError::new_err(format!(
                            "Failed to connect to unix socket {socket_path}: {e}"
                        ))
                    })?;

                let config = AdbBridgeConfig {
                    device_serial: None,
                    tty_path: tty.to_string(),
                    baud_rate: 115200,
                    endpoint: AdbSocketEndpoint::Unix(PathBuf::from(socket_path)),
                    remote_forward_spec: "localabstract:spectra_uart".to_string(),
                    connect_timeout: timeout,
                };

                AdbSerialBridge::from_stream(config, AdbStream::Unix(stream))
                    .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))
            })?;

            Ok(Self {
                runtime: rt,
                transport: Box::new(bridge),
                inter_byte_delay: delay,
                timeout,
                telemetry_log: VecDeque::with_capacity(MAX_TELEMETRY_LOG_ENTRIES),
            })
        }
    }

    /// Sends an ASCII command to the coffee machine, optionally encoding as 4:1 Jura wire bytes.
    #[pyo3(signature = (cmd, obfuscate_4byte = None, enforce_safety = None, lab_confirm_token = None))]
    pub fn send_ascii(
        &mut self,
        py: Python<'_>,
        cmd: &str,
        obfuscate_4byte: Option<bool>,
        enforce_safety: Option<bool>,
        lab_confirm_token: Option<&str>,
    ) -> PyResult<String> {
        py.detach(|| {
            self.send_ascii_inner(cmd, obfuscate_4byte, enforce_safety, lab_confirm_token)
        })
    }

    /// Sends raw hex bytes to the machine and returns the response as uppercase hex string.
    #[pyo3(signature = (hex_payload, inter_byte_delay_ms = None, enforce_safety = None, lab_confirm_token = None))]
    pub fn send_hex(
        &mut self,
        py: Python<'_>,
        hex_payload: &str,
        inter_byte_delay_ms: Option<u64>,
        enforce_safety: Option<bool>,
        lab_confirm_token: Option<&str>,
    ) -> PyResult<String> {
        py.detach(|| {
            self.send_hex_inner(
                hex_payload,
                inter_byte_delay_ms,
                enforce_safety,
                lab_confirm_token,
            )
        })
    }

    /// Polls live machine telemetry via `HZ:` and decodes all metric sensors.
    #[pyo3(signature = (delta_t_sec = None, obfuscate_4byte = None))]
    pub fn poll_telemetry(
        &mut self,
        py: Python<'_>,
        delta_t_sec: Option<f32>,
        obfuscate_4byte: Option<bool>,
    ) -> PyResult<PyHzTelemetry> {
        py.detach(|| self.poll_telemetry_inner(delta_t_sec, obfuscate_4byte))
    }

    /// Reads a 16-word EEPROM block via `RT:` command.
    #[pyo3(signature = (block_index, two_digit = None, obfuscate_4byte = None))]
    pub fn read_eeprom_block(
        &mut self,
        py: Python<'_>,
        block_index: u16,
        two_digit: Option<bool>,
        obfuscate_4byte: Option<bool>,
    ) -> PyResult<Vec<u16>> {
        py.detach(|| self.read_eeprom_block_inner(block_index, two_digit, obfuscate_4byte))
    }

    /// Reads a single 16-bit word from EEPROM via `RE:` command.
    #[pyo3(signature = (addr, two_digit = None, obfuscate_4byte = None))]
    pub fn read_eeprom_word(
        &mut self,
        py: Python<'_>,
        addr: u16,
        two_digit: Option<bool>,
        obfuscate_4byte: Option<bool>,
    ) -> PyResult<u16> {
        py.detach(|| self.read_eeprom_word_inner(addr, two_digit, obfuscate_4byte))
    }

    /// Retrieves history of sent commands and received responses for diagnostics.
    pub fn get_logs(&self) -> Vec<String> {
        self.telemetry_log.iter().cloned().collect()
    }

    /// Clears the recorded telemetry and command history log.
    pub fn clear_logs(&mut self) {
        self.telemetry_log.clear();
    }
}

/// Encodes an ASCII command into Jura 4:1 wire carrier bytes.
#[pyfunction]
#[pyo3(signature = (cmd))]
pub fn encode_jura_ascii(py: Python<'_>, cmd: &str) -> Py<PyBytes> {
    let out = JuraProtocol::encode_wire_frame(cmd);
    PyBytes::new(py, &out).unbind()
}

/// Decodes 4:1 wire carrier bytes back into an ASCII string.
#[pyfunction]
#[pyo3(signature = (raw))]
pub fn decode_jura_wire(raw: &[u8]) -> PyResult<String> {
    JuraProtocol::decode_wire_frame(raw)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

/// Parses an ASCII `HZ:` telemetry frame into metric fields.
#[pyfunction]
#[pyo3(signature = (raw, delta_t_sec = None))]
pub fn parse_hz_frame(raw: &str, delta_t_sec: Option<f32>) -> PyResult<PyHzTelemetry> {
    let frame = JuraProtocol::parse_hz_response(raw, delta_t_sec.unwrap_or(1.0))
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    Ok(PyHzTelemetry::from(frame))
}

/// Parses a 64-hex-character `RT:` EEPROM block response into 16 `u16` words.
#[pyfunction]
#[pyo3(signature = (raw))]
pub fn parse_rt_block(raw: &str) -> PyResult<Vec<u16>> {
    JuraProtocol::parse_rt_response(raw)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

/// Parses a 4-hex-character `RE:` EEPROM word response into a single `u16` value.
#[pyfunction]
#[pyo3(signature = (raw))]
pub fn parse_re_word(raw: &str) -> PyResult<u16> {
    JuraProtocol::parse_re_response(raw)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
}

/// Differential EEPROM word delta representation for Python.
#[pyclass(from_py_object)]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PyEepromWordDiff {
    #[pyo3(get)]
    pub addr: u16,
    #[pyo3(get)]
    pub baseline: u16,
    #[pyo3(get)]
    pub current: u16,
    #[pyo3(get)]
    pub flipped_bits: u16,
}

#[pymethods]
impl PyEepromWordDiff {
    fn __repr__(&self) -> String {
        format!(
            "PyEepromWordDiff(addr={:#06X}, baseline={:#06X}, current={:#06X}, flipped={:#06X})",
            self.addr, self.baseline, self.current, self.flipped_bits
        )
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("addr", self.addr)?;
        dict.set_item("baseline", self.baseline)?;
        dict.set_item("current", self.current)?;
        dict.set_item("flipped_bits", self.flipped_bits)?;
        Ok(dict.unbind())
    }
}

/// Diffs baseline EEPROM words against a current snapshot and computes flipped bits.
#[pyfunction]
#[pyo3(signature = (baseline, current, start_addr = None))]
pub fn diff_eeprom_blocks(
    baseline: Vec<u16>,
    current: Vec<u16>,
    start_addr: Option<u16>,
) -> Vec<PyEepromWordDiff> {
    let diffs = spectra_core::diff_eeprom_blocks(&baseline, &current, start_addr.unwrap_or(0));
    diffs
        .into_iter()
        .map(|d| PyEepromWordDiff {
            addr: d.addr,
            baseline: d.baseline,
            current: d.current,
            flipped_bits: d.flipped_bits,
        })
        .collect()
}

/// Lists physical serial ports available on the host machine.
#[pyfunction]
pub fn list_serial_ports(py: Python<'_>) -> PyResult<Vec<String>> {
    #[cfg(feature = "serial")]
    {
        py.detach(|| {
            spectra_hal::SerialTransport::list_ports()
                .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
        })
    }
    #[cfg(not(feature = "serial"))]
    {
        let _ = py;
        Ok(Vec::new())
    }
}

/// Performs Jura Smart Connect '@'-protocol nibble substitution encryption/decryption (involution).
#[pyfunction]
#[pyo3(signature = (data, key))]
pub fn smart_connect_crypt(py: Python<'_>, data: &[u8], key: u8) -> Py<PyBytes> {
    let out = SmartConnectCipher::crypt(data, key);
    PyBytes::new(py, &out).unbind()
}

/// Scans text section bytes for ARMv7 movw+movt instruction pairs loading target_vma into any register.
#[pyfunction]
#[pyo3(signature = (text_bytes, target_vma))]
pub fn has_arm_movw_movt_any_reg(py: Python<'_>, text_bytes: &[u8], target_vma: u32) -> bool {
    py.detach(|| spectra_core::has_arm_movw_movt_any_reg(text_bytes, target_vma))
}

/// Repoints all ARMv7 movw+movt instruction pairs targeting orig_vma to new_vma across any register.
/// Returns (patched_bytes, repointed_count).
#[pyfunction]
#[pyo3(signature = (text_bytes, orig_vma, new_vma))]
pub fn repoint_arm_movw_movt_all_regs(
    py: Python<'_>,
    text_bytes: &[u8],
    orig_vma: u32,
    new_vma: u32,
) -> (Py<PyBytes>, usize) {
    let (patched, count) =
        py.detach(|| spectra_core::repoint_arm_movw_movt_all_regs(text_bytes, orig_vma, new_vma));
    (PyBytes::new(py, &patched).unbind(), count)
}

/// Finds `min_size` consecutive zero padding bytes in `ro_bytes` starting at `start_rel_off` with `align` alignment.
#[pyfunction]
#[pyo3(signature = (ro_bytes, sh_offset, min_size, align = 4, start_rel_off = 0))]
pub fn find_free_zero_padding_fast(
    py: Python<'_>,
    ro_bytes: &[u8],
    sh_offset: usize,
    min_size: usize,
    align: usize,
    start_rel_off: usize,
) -> Option<usize> {
    py.detach(|| {
        spectra_core::find_free_zero_padding(ro_bytes, sh_offset, min_size, align, start_rel_off)
    })
}

/// Scans rodata for unreferenced orphaned strings matching common words and diacritics.
#[pyfunction]
#[pyo3(signature = (ro_bytes, search_start_off, vma_minus_off, referenced_vmas, common_words, target_diacritics = ""))]
pub fn scan_rodata_orphaned_string_fast(
    py: Python<'_>,
    ro_bytes: &[u8],
    search_start_off: usize,
    vma_minus_off: u32,
    referenced_vmas: Vec<u32>,
    common_words: Vec<String>,
    target_diacritics: &str,
) -> Option<(u32, String)> {
    py.detach(|| {
        spectra_core::scan_rodata_orphaned_string(
            ro_bytes,
            search_start_off,
            vma_minus_off,
            &referenced_vmas,
            &common_words,
            target_diacritics,
        )
    })
}

/// Pure Rust high-speed cross-key bipartite token swap detector.
#[pyfunction]
#[pyo3(signature = (keys, key_tokens, val_tokens))]
pub fn detect_bipartite_token_swaps_fast(
    py: Python<'_>,
    keys: Vec<String>,
    key_tokens: Vec<Vec<String>>,
    val_tokens: Vec<Vec<String>>,
) -> Vec<(usize, usize)> {
    py.detach(|| spectra_core::detect_bipartite_token_swaps(keys, key_tokens, val_tokens))
}

/// Computes Modbus RTU 16-bit CRC for Kalerm packets. Returns (crc_low, crc_high).
#[pyfunction]
#[pyo3(signature = (data))]
pub fn kalerm_compute_crc(data: &[u8]) -> (u8, u8) {
    let crc = spectra_core::KalermProtocol::compute_crc(data);
    (crc[0], crc[1])
}

/// Verifies Modbus RTU 16-bit CRC for Kalerm packets.
#[pyfunction]
#[pyo3(signature = (packet))]
pub fn kalerm_verify_crc(packet: &[u8]) -> bool {
    spectra_core::KalermProtocol::verify_crc(packet)
}

/// Encodes raw bytes into Jura 4:1 UART carrier bytes.
#[pyfunction]
#[pyo3(signature = (data))]
pub fn encode_jura_wire_bytes(py: Python<'_>, data: &[u8]) -> Py<PyBytes> {
    let encoded = JuraProtocol::encode_wire_bytes(data);
    PyBytes::new(py, &encoded).unbind()
}

/// Decodes Jura 4:1 carrier bytes into `(decoded_bytes, remaining_raw_bytes)`.
#[pyfunction]
#[pyo3(signature = (raw))]
pub fn decode_jura_wire_bytes(py: Python<'_>, raw: &[u8]) -> (Py<PyBytes>, Py<PyBytes>) {
    let (decoded, remainder) = JuraProtocol::decode_wire_bytes(raw);
    (
        PyBytes::new(py, &decoded).unbind(),
        PyBytes::new(py, &remainder).unbind(),
    )
}

/// Decodes a Jura NTC integer reading into Celsius (0.1 °C precision).
#[pyfunction]
#[pyo3(signature = (num))]
pub fn decode_jura_temperature_word(num: i64) -> Option<f64> {
    spectra_core::decode_jura_temperature_word(num)
}

/// Decodes a packed 16-bit Jura EEPROM date word into `(year, month, day)`.
#[pyfunction]
#[pyo3(signature = (val))]
pub fn decode_jura_date_word(val: u16) -> Option<(u16, u8, u8)> {
    spectra_core::decode_jura_date_word(val)
}

/// Ranks candidate EEPROM hex addresses (`"0xXXXX"`) matching `target_value` in `category`.
#[pyfunction]
#[pyo3(signature = (eeprom, target_value, category))]
pub fn correlate_with_joe_ranked(
    py: Python<'_>,
    eeprom: std::collections::HashMap<u16, u16>,
    target_value: u32,
    category: &str,
) -> Vec<String> {
    py.detach(|| {
        spectra_core::correlate_value_addresses_ranked(&eeprom, target_value, category)
            .into_iter()
            .map(|addr| format!("0x{addr:04X}"))
            .collect()
    })
}

/// Matches a machine catalog entry against connected EF code, article number, and model name.
#[pyfunction]
#[pyo3(signature = (ef_code, article_numbers, model_family, detected_ef, detected_art, detected_model))]
pub fn machine_matches_connected(
    ef_code: &str,
    article_numbers: Vec<String>,
    model_family: &str,
    detected_ef: &str,
    detected_art: &str,
    detected_model: &str,
) -> bool {
    spectra_core::matches_connected_machine(
        ef_code,
        &article_numbers,
        model_family,
        detected_ef,
        detected_art,
        detected_model,
    )
}

/// Python C-extension module entry point for `spectra_py`.
#[pymodule]
fn spectra_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyHzTelemetry>()?;
    m.add_class::<PyEepromWordDiff>()?;
    m.add_class::<JuraSession>()?;
    m.add_function(wrap_pyfunction!(encode_jura_ascii, m)?)?;
    m.add_function(wrap_pyfunction!(decode_jura_wire, m)?)?;
    m.add_function(wrap_pyfunction!(encode_jura_wire_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(decode_jura_wire_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(decode_jura_temperature_word, m)?)?;
    m.add_function(wrap_pyfunction!(decode_jura_date_word, m)?)?;
    m.add_function(wrap_pyfunction!(correlate_with_joe_ranked, m)?)?;
    m.add_function(wrap_pyfunction!(machine_matches_connected, m)?)?;
    m.add_function(wrap_pyfunction!(parse_hz_frame, m)?)?;
    m.add_function(wrap_pyfunction!(parse_rt_block, m)?)?;
    m.add_function(wrap_pyfunction!(parse_re_word, m)?)?;
    m.add_function(wrap_pyfunction!(smart_connect_crypt, m)?)?;
    m.add_function(wrap_pyfunction!(diff_eeprom_blocks, m)?)?;
    m.add_function(wrap_pyfunction!(list_serial_ports, m)?)?;
    m.add_function(wrap_pyfunction!(has_arm_movw_movt_any_reg, m)?)?;
    m.add_function(wrap_pyfunction!(repoint_arm_movw_movt_all_regs, m)?)?;
    m.add_function(wrap_pyfunction!(find_free_zero_padding_fast, m)?)?;
    m.add_function(wrap_pyfunction!(scan_rodata_orphaned_string_fast, m)?)?;
    m.add_function(wrap_pyfunction!(detect_bipartite_token_swaps_fast, m)?)?;
    m.add_function(wrap_pyfunction!(kalerm_compute_crc, m)?)?;
    m.add_function(wrap_pyfunction!(kalerm_verify_crc, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_codec_and_cipher_roundtrips() {
        pyo3::Python::initialize();
        Python::attach(|py| {
            let original = "TY:\r\n";
            let wire = encode_jura_ascii(py, original);
            let wire_bytes = wire.as_bytes(py);
            assert_eq!(wire_bytes.len(), original.len() * 4);
            let decoded = decode_jura_wire(wire_bytes).expect("decode failed");
            assert_eq!(decoded, original);

            // Test Smart Connect involution cipher
            let msg = b"SPECTRA_DIAGNOSTICS_PAYLOAD";
            let key = 0x5A;
            let encrypted = smart_connect_crypt(py, msg, key);
            let decrypted = smart_connect_crypt(py, encrypted.as_bytes(py), key);
            assert_eq!(decrypted.as_bytes(py), msg);
        });
    }

    #[test]
    fn test_parse_helpers() {
        let re_word = parse_re_word("re:010A\r\n").expect("parse_re_word");
        assert_eq!(re_word, 0x010A);

        let rt_hex = "rt:000010A747450000025F15F500000E1900A600266DFB00000000000000000000";
        let words = parse_rt_block(rt_hex).expect("parse_rt_block");
        assert_eq!(words.len(), 16);
        assert_eq!(words[1], 0x10A7);

        let hz_hex = "hz:010001100000,0287,00E3,0078,03DE,0802,3,000100,0000,00";
        let hz = parse_hz_frame(hz_hex, Some(1.0)).expect("parse_hz_frame");
        assert_eq!(hz.coffee_temp_c, 99.0);
        assert_eq!(hz.steam_temp_c, None);
        assert!(hz.mcu_heartbeat_tick);
    }

    #[test]
    fn test_diff_eeprom_and_list_ports() {
        pyo3::Python::initialize();
        let base = vec![0x1000, 0x2000, 0x3000];
        let curr = vec![0x1000, 0x2005, 0x3000];
        let diffs = diff_eeprom_blocks(base, curr, Some(0x0040));
        assert_eq!(diffs.len(), 1);
        assert_eq!(diffs[0].addr, 0x0041);
        assert_eq!(diffs[0].baseline, 0x2000);
        assert_eq!(diffs[0].current, 0x2005);
        assert_eq!(diffs[0].flipped_bits, 0x0005);

        Python::attach(|py| {
            let ports = list_serial_ports(py);
            assert!(ports.is_ok());
        });
    }

    #[cfg(unix)]
    #[test]
    fn test_mock_unix_socket_jura_session_roundtrip() {
        pyo3::Python::initialize();

        let (client, mut server) =
            std::os::unix::net::UnixStream::pair().expect("unix stream pair");
        client.set_nonblocking(true).expect("nonblocking");

        let rt = shared_runtime().expect("shared runtime");

        let _guard = rt.enter();
        let tokio_client = tokio::net::UnixStream::from_std(client).expect("from_std");
        drop(_guard);

        let config = AdbBridgeConfig {
            device_serial: None,
            tty_path: "/dev/ttyS1".to_string(),
            baud_rate: 115200,
            endpoint: AdbSocketEndpoint::Unix(PathBuf::from("/tmp/test_session.sock")),
            remote_forward_spec: "localabstract:spectra_uart".to_string(),
            connect_timeout: Duration::from_secs(1),
        };

        let bridge = AdbSerialBridge::from_stream(config, AdbStream::Unix(tokio_client))
            .expect("bridge construction");

        let mut session = JuraSession::from_transport(
            Box::new(bridge),
            Duration::from_millis(1),
            Duration::from_millis(500),
        )
        .expect("session");

        let server_thread = std::thread::spawn(move || {
            use std::io::{Read, Write};

            // 1. Respond to TY: ("TY:\r\n" is 5 chars = 20 wire bytes)
            let mut ty_buf = [0u8; 20];
            server.read_exact(&mut ty_buf).expect("read TY");
            let req = JuraProtocol::decode_wire_frame(&ty_buf).expect("decode req");
            assert!(req.starts_with("TY:"));
            let ty_resp = JuraProtocol::encode_wire_frame("ty:EF509_V01\r\n");
            server.write_all(&ty_resp).expect("write TY resp");

            // 2. Respond to raw hex (3 bytes: AA BB CC)
            let mut hex_buf = [0u8; 3];
            server.read_exact(&mut hex_buf).expect("read hex");
            assert_eq!(&hex_buf, &[0xAA, 0xBB, 0xCC]);
            server.write_all(&[0x11, 0x22, 0x33]).expect("write hex resp");

            // 3. Respond to HZ: ("HZ:\r\n" is 5 chars = 20 wire bytes)
            let mut hz_buf = [0u8; 20];
            server.read_exact(&mut hz_buf).expect("read HZ");
            let req3 = JuraProtocol::decode_wire_frame(&hz_buf).expect("decode HZ req");
            assert!(req3.starts_with("HZ:"));
            let hz_resp = JuraProtocol::encode_wire_frame(
                "hz:010001100000,0287,00E3,0078,03DE,0802,3,000100,0000,00\r\n",
            );
            server.write_all(&hz_resp).expect("write HZ resp");
        });

        Python::attach(|py| {
            // Test send_ascii
            let ty_out = session
                .send_ascii(py, "TY:", Some(true), Some(true), None)
                .expect("send_ascii TY");
            assert_eq!(ty_out, "ty:EF509_V01");

            // Unlisted actuator command must be blocked by strict allowlist
            assert!(session
                .send_ascii(py, "FN:01", Some(true), Some(true), None)
                .is_err());

            // Disabling safety without explicit confirmation token must be blocked
            assert!(session
                .send_ascii(py, "WE:0030,FFFF", Some(true), Some(false), None)
                .is_err());

            // Multi-byte UTF-8 payload ("€a", 4 bytes) must return Err without panicking
            assert!(session.send_hex(py, "€a", None, None, None).is_err());

            // Unvalidated raw hex must be blocked by default
            assert!(session.send_hex(py, "AA BB CC", None, None, None).is_err());

            // 4:1-encoded destructive command must be blocked by default
            let we_wire = JuraProtocol::encode_wire_frame("WE:0030,FFFF\r\n");
            let we_hex: String = we_wire.iter().map(|b| format!("{b:02X}")).collect();
            assert!(session.send_hex(py, &we_hex, None, None, None).is_err());

            // Disabling safety without lab_confirm_token must fail
            assert!(session
                .send_hex(py, "AA BB CC", None, Some(false), None)
                .is_err());

            // Explicit lab override token allows raw hex for bench testing
            let hex_out = session
                .send_hex(py, "AA BB CC", None, Some(false), Some("SPECTRA_LAB_WRITE"))
                .expect("send_hex explicit lab override");
            assert_eq!(hex_out, "11 22 33");

            // Test poll_telemetry
            let telem = session
                .poll_telemetry(py, Some(1.0), Some(true))
                .expect("poll_telemetry");
            assert_eq!(telem.coffee_temp_c, 99.0);
            assert!(telem.mcu_heartbeat_tick);
        });

        // Test get_logs
        let logs = session.get_logs();
        assert_eq!(logs.len(), 3);
        assert!(logs[0].contains("TX: TY: -> RX: ty:EF509_V01"));
        assert!(logs[1].contains("TX_HEX: AABBCC -> RX_HEX: 11 22 33"));
        assert!(logs[2].contains("TX: HZ: -> RX: hz:010001100000"));

        session.clear_logs();
        assert_eq!(session.get_logs().len(), 0);

        server_thread.join().expect("server thread join");
    }

    #[test]
    fn test_spectra_py_hmi_and_crc_wrappers() {
        pyo3::Python::initialize();
        let vma = 0x03567890;
        let mut buf = vec![0u8; 32];
        let enc = spectra_core::encode_arm_movw_movt(3, vma);
        buf[8..16].copy_from_slice(&enc);

        let new_vma = 0x03569999;
        Python::attach(|py| {
            assert!(has_arm_movw_movt_any_reg(py, &buf, vma));
            assert!(!has_arm_movw_movt_any_reg(py, &buf, 0x12345678));

            let (repointed, count) = repoint_arm_movw_movt_all_regs(py, &buf, vma, new_vma);
            assert_eq!(count, 1);
            assert!(has_arm_movw_movt_any_reg(py, repointed.as_bytes(py), new_vma));

            let ro_bytes = vec![0xFF; 64];
            let mut ro_pad = ro_bytes.clone();
            ro_pad[16..32].fill(0);
            let pad = find_free_zero_padding_fast(py, &ro_pad, 0x1000, 16, 4, 0);
            assert_eq!(pad, Some(0x1010));

            let wire = encode_jura_wire_bytes(py, b"TY:\r\n");
            let (dec, rem) = decode_jura_wire_bytes(py, wire.as_bytes(py));
            assert_eq!(dec.as_bytes(py), b"TY:\r\n");
            assert!(rem.as_bytes(py).is_empty());

            let mut eeprom = std::collections::HashMap::new();
            eeprom.insert(0x0002, 77);
            eeprom.insert(0x0180, 77);
            let ranked = correlate_with_joe_ranked(py, eeprom, 77, "product");
            assert_eq!(ranked, vec!["0x0180", "0x0002"]);
        });

        let (crc_lo, crc_hi) = kalerm_compute_crc(&[0x01, 0x03, 0x00, 0x00, 0x00, 0x0A]);
        assert!(kalerm_verify_crc(&[0x01, 0x03, 0x00, 0x00, 0x00, 0x0A, crc_lo, crc_hi]));

        assert_eq!(decode_jura_temperature_word(0x03C4), Some(96.4));
        assert_eq!(decode_jura_date_word(((2024 - 1990) << 9) | (3 << 5) | 15), Some((2024, 3, 15)));

        assert!(machine_matches_connected(
            "EF535M",
            vec!["15141".to_string()],
            "WE8",
            "ef535m",
            "",
            "",
        ));
    }
}
