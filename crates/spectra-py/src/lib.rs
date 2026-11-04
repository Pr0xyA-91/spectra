//! PyO3 Hardware Diagnostics and Interactive Session Bridge for SPECTRA

use std::net::SocketAddr;
use std::path::PathBuf;
use std::time::Duration;

use pyo3::prelude::*;
use pyo3::types::PyDict;

use spectra_core::{
    AddressingMode, HzTelemetryFrame, JuraCommand, JuraProtocol, SmartConnectCipher,
};
use spectra_hal::{
    AdbBridgeConfig, AdbSerialBridge, AdbSocketEndpoint, AdbStream, HalError, Transport,
};

#[cfg(feature = "serial")]
use spectra_hal::{SerialConfig, SerialTransport};

/// Real-time metric telemetry frame decoded from Jura `HZ:` responses.
#[pyclass]
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
        let dict = PyDict::new_bound(py);
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
        raw_buf.extend_from_slice(&chunk[..n]);

        if obfuscate_4byte {
            if raw_buf.len() >= 4 && raw_buf.len() % 4 == 0 {
                if let Ok(decoded) = JuraProtocol::decode_wire_frame(&raw_buf) {
                    if decoded.ends_with("\r\n") || decoded.ends_with('\n') || decoded.ends_with('\r') {
                        return Ok(decoded.trim().to_string());
                    }
                }
            }
        } else if let Ok(s) = std::str::from_utf8(&raw_buf) {
            if s.ends_with("\r\n") || s.ends_with('\n') || s.ends_with('\r') {
                return Ok(s.trim().to_string());
            }
        }
    }

    if raw_buf.is_empty() {
        return Err(pyo3::exceptions::PyTimeoutError::new_err(
            "No response received from target",
        ));
    }

    if obfuscate_4byte {
        let s = JuraProtocol::decode_wire_frame(&raw_buf).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Failed to decode wire frame: {e}"))
        })?;
        Ok(s.trim().to_string())
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
        // Drain subsequent buffered bytes if arriving in rapid succession
        loop {
            let mut more = [0u8; 64];
            match rt.block_on(transport.read_raw(&mut more, Duration::from_millis(25))) {
                Ok(count) if count > 0 => {
                    raw_buf.extend_from_slice(&more[..count]);
                }
                _ => break,
            }
        }
    }

    let hex_resp = raw_buf
        .iter()
        .map(|b| format!("{:02X}", b))
        .collect::<Vec<_>>()
        .join(" ");
    Ok(hex_resp)
}

/// Interactive diagnostics and telemetry session for Jura machines.
#[pyclass(unsendable)]
pub struct JuraSession {
    runtime: tokio::runtime::Runtime,
    transport: Box<dyn Transport>,
    inter_byte_delay: Duration,
    timeout: Duration,
    telemetry_log: Vec<String>,
}

impl JuraSession {
    /// Creates a `JuraSession` directly wrapping an existing `Transport` (useful for testing).
    pub fn from_transport(
        transport: Box<dyn Transport>,
        inter_byte_delay: Duration,
        timeout: Duration,
    ) -> Result<Self, PyErr> {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(format!("Runtime error: {e}")))?;

        Ok(Self {
            runtime: rt,
            transport,
            inter_byte_delay,
            timeout,
            telemetry_log: Vec::new(),
        })
    }
}

#[pymethods]
impl JuraSession {
    /// Opens a native physical UART connection (e.g. `"/dev/ttyUSB0"`).
    #[staticmethod]
    #[pyo3(signature = (port, baud_rate = None, inter_byte_delay_ms = None, timeout_ms = None))]
    pub fn open_uart(
        port: &str,
        baud_rate: Option<u32>,
        inter_byte_delay_ms: Option<u64>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(format!("Runtime error: {e}")))?;

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
            let transport = SerialTransport::open(config)
                .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))?;
            Ok(Self {
                runtime: rt,
                transport: Box::new(transport),
                inter_byte_delay: delay,
                timeout,
                telemetry_log: Vec::new(),
            })
        }
        #[cfg(not(feature = "serial"))]
        {
            let _ = (baud, delay, timeout, port);
            Err(pyo3::exceptions::PyRuntimeError::new_err(
                "Serial feature not compiled into spectra-hal",
            ))
        }
    }

    /// Opens an ADB TCP bridge connecting to an Android SBC UART.
    #[staticmethod]
    #[pyo3(signature = (addr, tty_path, baud_rate = None, device_serial = None, remote_spec = None, timeout_ms = None))]
    pub fn open_adb_tcp(
        addr: &str,
        tty_path: &str,
        baud_rate: Option<u32>,
        device_serial: Option<String>,
        remote_spec: Option<String>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(format!("Runtime error: {e}")))?;

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

        let bridge = rt
            .block_on(AdbSerialBridge::connect(config))
            .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))?;

        Ok(Self {
            runtime: rt,
            transport: Box::new(bridge),
            inter_byte_delay: Duration::from_millis(8),
            timeout,
            telemetry_log: Vec::new(),
        })
    }

    /// Opens an ADB Unix socket bridge connecting to an Android SBC UART.
    #[staticmethod]
    #[pyo3(signature = (socket_path, tty_path, baud_rate = None, device_serial = None, remote_spec = None, timeout_ms = None))]
    pub fn open_adb_unix(
        socket_path: &str,
        tty_path: &str,
        baud_rate: Option<u32>,
        device_serial: Option<String>,
        remote_spec: Option<String>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(format!("Runtime error: {e}")))?;

        let timeout = Duration::from_millis(timeout_ms.unwrap_or(3000));
        let config = AdbBridgeConfig {
            device_serial,
            tty_path: tty_path.to_string(),
            baud_rate: baud_rate.unwrap_or(115200),
            endpoint: AdbSocketEndpoint::Unix(PathBuf::from(socket_path)),
            remote_forward_spec: remote_spec.unwrap_or_else(|| "localabstract:spectra_uart".into()),
            connect_timeout: timeout,
        };

        let bridge = rt
            .block_on(AdbSerialBridge::connect(config))
            .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))?;

        Ok(Self {
            runtime: rt,
            transport: Box::new(bridge),
            inter_byte_delay: Duration::from_millis(8),
            timeout,
            telemetry_log: Vec::new(),
        })
    }

    /// Connects directly to an already-bound local Unix socket via `AdbSerialBridge::from_stream`
    /// without running `adb` CLI (ideal for mock servers, unit tests, and local emulation).
    #[staticmethod]
    #[pyo3(signature = (socket_path, tty_path = None, inter_byte_delay_ms = None, timeout_ms = None))]
    pub fn open_unix_raw(
        socket_path: &str,
        tty_path: Option<&str>,
        inter_byte_delay_ms: Option<u64>,
        timeout_ms: Option<u64>,
    ) -> PyResult<Self> {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(format!("Runtime error: {e}")))?;

        let stream = rt
            .block_on(async { tokio::net::UnixStream::connect(socket_path).await })
            .map_err(|e| {
                pyo3::exceptions::PyConnectionError::new_err(format!(
                    "Failed to connect to unix socket {socket_path}: {e}"
                ))
            })?;

        let timeout = Duration::from_millis(timeout_ms.unwrap_or(1000));
        let delay = Duration::from_millis(inter_byte_delay_ms.unwrap_or(8));
        let tty = tty_path.unwrap_or("/dev/ttyS1");

        let config = AdbBridgeConfig {
            device_serial: None,
            tty_path: tty.to_string(),
            baud_rate: 115200,
            endpoint: AdbSocketEndpoint::Unix(PathBuf::from(socket_path)),
            remote_forward_spec: "localabstract:spectra_uart".to_string(),
            connect_timeout: timeout,
        };

        let bridge = AdbSerialBridge::from_stream(config, AdbStream::Unix(stream))
            .map_err(|e| pyo3::exceptions::PyConnectionError::new_err(e.to_string()))?;

        Ok(Self {
            runtime: rt,
            transport: Box::new(bridge),
            inter_byte_delay: delay,
            timeout,
            telemetry_log: Vec::new(),
        })
    }

    /// Sends an ASCII command to the coffee machine, optionally encoding as 4:1 Jura wire bytes.
    #[pyo3(signature = (cmd, obfuscate_4byte = None, enforce_safety = None))]
    pub fn send_ascii(
        &mut self,
        cmd: &str,
        obfuscate_4byte: Option<bool>,
        enforce_safety: Option<bool>,
    ) -> PyResult<String> {
        let enforce = enforce_safety.unwrap_or(true);
        if enforce {
            JuraProtocol::validate_safety(cmd).map_err(|e| {
                pyo3::exceptions::PyValueError::new_err(format!("Safety invariant violation: {e}"))
            })?;
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

        let rx = read_ascii_response(&self.runtime, &mut self.transport, self.timeout, obfuscate)?;
        self.telemetry_log
            .push(format!("TX: {} -> RX: {}", full_cmd.trim(), rx));
        Ok(rx)
    }

    /// Sends raw hex bytes to the machine and returns the response as uppercase hex string.
    #[pyo3(signature = (hex_payload, inter_byte_delay_ms = None))]
    pub fn send_hex(
        &mut self,
        hex_payload: &str,
        inter_byte_delay_ms: Option<u64>,
    ) -> PyResult<String> {
        let clean_hex: String = hex_payload
            .chars()
            .filter(|c| !c.is_whitespace() && *c != ':')
            .collect();

        if clean_hex.len() % 2 != 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "Hex string has odd length: {}",
                clean_hex.len()
            )));
        }

        let raw_bytes: Vec<u8> = (0..clean_hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&clean_hex[i..i + 2], 16))
            .collect::<Result<Vec<u8>, _>>()
            .map_err(|e| {
                pyo3::exceptions::PyValueError::new_err(format!("Invalid hex byte in payload: {e}"))
            })?;

        let delay = inter_byte_delay_ms
            .map(Duration::from_millis)
            .or(Some(self.inter_byte_delay));

        self.runtime
            .block_on(self.transport.write_raw(&raw_bytes, delay))
            .map_err(|e| {
                pyo3::exceptions::PyIOError::new_err(format!("Transport write failure: {e}"))
            })?;

        let hex_resp = read_hex_response(&self.runtime, &mut self.transport, self.timeout)?;
        self.telemetry_log
            .push(format!("TX_HEX: {clean_hex} -> RX_HEX: {hex_resp}"));
        Ok(hex_resp)
    }

    /// Polls live machine telemetry via `HZ:` and decodes all metric sensors.
    #[pyo3(signature = (delta_t_sec = None, obfuscate_4byte = None))]
    pub fn poll_telemetry(
        &mut self,
        delta_t_sec: Option<f32>,
        obfuscate_4byte: Option<bool>,
    ) -> PyResult<PyHzTelemetry> {
        let rx = self.send_ascii("HZ:", obfuscate_4byte, Some(false))?;
        let frame = JuraProtocol::parse_hz_response(&rx, delta_t_sec.unwrap_or(1.0))
            .map_err(|e| {
                pyo3::exceptions::PyValueError::new_err(format!("Failed to parse HZ telemetry: {e}"))
            })?;
        Ok(PyHzTelemetry::from(frame))
    }

    /// Reads a 16-word EEPROM block via `RT:` command.
    #[pyo3(signature = (block_index, two_digit = None, obfuscate_4byte = None))]
    pub fn read_eeprom_block(
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
        let rx = self.send_ascii(&cmd_str, obfuscate_4byte, Some(false))?;
        let words = JuraProtocol::parse_rt_response(&rx).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Failed to parse RT block: {e}"))
        })?;
        Ok(words)
    }

    /// Reads a single 16-bit word from EEPROM via `RE:` command.
    #[pyo3(signature = (addr, two_digit = None, obfuscate_4byte = None))]
    pub fn read_eeprom_word(
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
        let rx = self.send_ascii(&cmd_str, obfuscate_4byte, Some(false))?;
        let word = JuraProtocol::parse_re_response(&rx).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Failed to parse RE word: {e}"))
        })?;
        Ok(word)
    }

    /// Retrieves history of sent commands and received responses for diagnostics.
    pub fn get_logs(&self) -> Vec<String> {
        self.telemetry_log.clone()
    }

    /// Clears the recorded telemetry and command history log.
    pub fn clear_logs(&mut self) {
        self.telemetry_log.clear();
    }
}

/// Encodes an ASCII command into Jura 4:1 wire carrier bytes.
#[pyfunction]
#[pyo3(signature = (cmd))]
pub fn encode_jura_ascii(cmd: &str) -> Vec<u8> {
    JuraProtocol::encode_wire_frame(cmd)
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
#[pyclass]
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
        let dict = PyDict::new_bound(py);
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
pub fn list_serial_ports() -> PyResult<Vec<String>> {
    #[cfg(feature = "serial")]
    {
        spectra_hal::SerialTransport::list_ports()
            .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }
    #[cfg(not(feature = "serial"))]
    {
        Ok(Vec::new())
    }
}

/// Performs Jura Smart Connect '@'-protocol nibble substitution encryption/decryption (involution).
#[pyfunction]
#[pyo3(signature = (data, key))]
pub fn smart_connect_crypt(data: &[u8], key: u8) -> Vec<u8> {
    SmartConnectCipher::crypt(data, key)
}

/// Python C-extension module entry point for `spectra_py`.
#[pymodule]
fn spectra_py(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyHzTelemetry>()?;
    m.add_class::<PyEepromWordDiff>()?;
    m.add_class::<JuraSession>()?;
    m.add_function(wrap_pyfunction!(encode_jura_ascii, m)?)?;
    m.add_function(wrap_pyfunction!(decode_jura_wire, m)?)?;
    m.add_function(wrap_pyfunction!(parse_hz_frame, m)?)?;
    m.add_function(wrap_pyfunction!(parse_rt_block, m)?)?;
    m.add_function(wrap_pyfunction!(parse_re_word, m)?)?;
    m.add_function(wrap_pyfunction!(smart_connect_crypt, m)?)?;
    m.add_function(wrap_pyfunction!(diff_eeprom_blocks, m)?)?;
    m.add_function(wrap_pyfunction!(list_serial_ports, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_codec_and_cipher_roundtrips() {
        let original = "TY:\r\n";
        let wire = encode_jura_ascii(original);
        assert_eq!(wire.len(), original.len() * 4);
        let decoded = decode_jura_wire(&wire).expect("decode failed");
        assert_eq!(decoded, original);

        // Test Smart Connect involution cipher
        let msg = b"SPECTRA_DIAGNOSTICS_PAYLOAD";
        let key = 0x5A;
        let encrypted = smart_connect_crypt(msg, key);
        let decrypted = smart_connect_crypt(&encrypted, key);
        assert_eq!(&decrypted, msg);
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
        let base = vec![0x1000, 0x2000, 0x3000];
        let curr = vec![0x1000, 0x2005, 0x3000];
        let diffs = diff_eeprom_blocks(base, curr, Some(0x0040));
        assert_eq!(diffs.len(), 1);
        assert_eq!(diffs[0].addr, 0x0041);
        assert_eq!(diffs[0].baseline, 0x2000);
        assert_eq!(diffs[0].current, 0x2005);
        assert_eq!(diffs[0].flipped_bits, 0x0005);

        let ports = list_serial_ports();
        assert!(ports.is_ok());
    }

    #[test]
    fn test_mock_unix_socket_jura_session_roundtrip() {
        pyo3::prepare_freethreaded_python();

        let (client, mut server) =
            std::os::unix::net::UnixStream::pair().expect("unix stream pair");
        client.set_nonblocking(true).expect("nonblocking");

        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .expect("runtime build");

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

        let mut session = JuraSession {
            runtime: rt,
            transport: Box::new(bridge),
            inter_byte_delay: Duration::from_millis(1),
            timeout: Duration::from_millis(500),
            telemetry_log: Vec::new(),
        };

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

        // Test send_ascii
        let ty_out = session
            .send_ascii("TY:", Some(true), Some(true))
            .expect("send_ascii TY");
        assert_eq!(ty_out, "ty:EF509_V01");

        // Test send_hex
        let hex_out = session.send_hex("AA BB CC", None).expect("send_hex");
        assert_eq!(hex_out, "11 22 33");

        // Test poll_telemetry
        let telem = session
            .poll_telemetry(Some(1.0), Some(true))
            .expect("poll_telemetry");
        assert_eq!(telem.coffee_temp_c, 99.0);
        assert!(telem.mcu_heartbeat_tick);

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
}
