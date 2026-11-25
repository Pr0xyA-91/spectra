use std::time::Duration;
use crate::error::CoreError;
use serde::{Deserialize, Serialize};
use spectra_hal::{jura_codec, HalError, HalResult, MachineProtocol, Transport};

pub const DIGIMESA_PULSES_PER_ML: f32 = 2.366;

/// S-Box permutations recovered from Jura Smart Connect ('@'-protocol) reverse engineering
const SBOX_N1: [u8; 16] = [8, 14, 12, 4, 3, 13, 10, 11, 0, 15, 6, 7, 2, 5, 1, 9];
const SBOX_N2: [u8; 16] = [4, 11, 13, 10, 0, 7, 15, 5, 9, 8, 3, 1, 14, 2, 12, 6];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AddressingMode {
    /// 8-bit Top-Tronic (EF509, EF525, EF533, EF703): RT:xx (2-hex-digit offset), RE:xx
    TwoDigit,
    /// 16-bit Modern (EF518M, EF536M, XJ5/GII): RT:xxxx (4-hex-digit offset), RE:xxxx
    FourDigit,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum JuraCommand {
    IdentifyFirmware,
    IdentifyDisplaySubFirmware,
    IdentifyBootloader,
    IdentifyDisplayBootloader,
    ReadPowerSpec,
    ReadCodeChecksum,        // CS:
    ReadDisplayCodeChecksum, // CS$:
    ReadVolatileTelemetry,
    ReadOpticalBeanSensor,
    ReadEEPROMWord { addr: u16, mode: AddressingMode },
    ReadEEPROMBlock { block_index: u16, mode: AddressingMode },
    RecalculateCRC,  // AN:0B (safe checksum rebuild into RE:0075)
    EnterTestMode,   // AN:20
    ExitTestMode,    // AN:21
    PulsePump,       // FA:08 (safe actuator test)
    ExecuteFunction(u8), // FN:xx
    RawSafe(String), // User custom query verified against safety invariants
}

/// Real-time subsystem telemetry decoded from `HZ:` CSV frames (all metric units: °C, ml/s)
/// Converts a Jura NTC integer reading into Celsius (0.1 °C precision).
pub fn decode_jura_temperature_word(num: i64) -> Option<f64> {
    if num <= 0 || num >= 1900 {
        return None;
    }
    if (150..=1850).contains(&num) {
        return Some((num as f64) / 10.0);
    }
    if (15..150).contains(&num) {
        return Some(num as f64);
    }
    None
}

/// Decodes a packed 16-bit Jura EEPROM production/service date word into `(year, month, day)`.
pub fn decode_jura_date_word(val: u16) -> Option<(u16, u8, u8)> {
    if val == 0 || val == 0xFFFF {
        return None;
    }
    let day = (val & 0x1F) as u8;
    let month = ((val >> 5) & 0x0F) as u8;
    let year = 1990u16 + ((val >> 9) & 0x7F);
    if !(1..=12).contains(&month) || day < 1 {
        return None;
    }
    let is_leap = (year.is_multiple_of(4) && !year.is_multiple_of(100)) || year.is_multiple_of(400);
    let max_day = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => if is_leap { 29 } else { 28 },
        _ => return None,
    };
    if day > max_day {
        return None;
    }
    Some((year, month, day))
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct HzTelemetryFrame {
    pub coffee_temp_c: f32,
    pub steam_temp_c: Option<f32>,
    pub flowmeter_pulses: u16,
    pub flow_rate_ml_s: f32,
    pub bu_upper_encoder: u16,
    pub bu_current_encoder: u16,
    pub rotary_pos: u8,
    pub drip_tray_missing: bool,
    pub grounds_full: bool,
    pub water_tank_empty: bool,
    pub mcu_heartbeat_tick: bool,
    pub is_busy: bool,
    pub heater_ready: bool,
    pub bu_initialized: bool,
    pub valve_busy: bool,
    pub puck_thickness_ticks: u16,
    pub beans_charged: bool,
}

impl HzTelemetryFrame {
    /// Evaluates live operational readiness strictly from physical real-time inputs:
    /// 1. Drip Tray inserted (!drip_tray_missing)
    /// 2. Water Tank full (!water_tank_empty)
    /// 3. Grounds Container not full (!grounds_full)
    /// 4. Coffee Thermoblock >= 80.0 °C (coffee_temp_c >= 80.0)
    /// 5. Appliance idle (!is_busy)
    /// 6. Puck compression thickness not indicating dry grinder run (!(puck_thickness_ticks > 0 && <= 14))
    ///
    /// Heartbeat clock tick (mcu_heartbeat_tick) is 1 Hz, NOT an alarm bit.
    pub fn is_machine_ready(&self) -> bool {
        !self.drip_tray_missing
            && !self.water_tank_empty
            && !self.grounds_full
            && self.coffee_temp_c >= 80.0
            && !self.is_busy
            && !(self.puck_thickness_ticks > 0 && self.puck_thickness_ticks <= 14)
    }
}

/// Evaluates commercial optical hopper status from HZ charged flag and CS optical beam latch.
///
/// On commercial appliances (IMPRESSA XJ5, GIGA):
/// - Morning boot before any coffee brew: HZ[0][3] == '0' -> uncharged (returns false).
/// - Empty hopper run during coffee brew: CS[39..43] == 0x3FF0 (>= 0x1000) -> empty (returns false).
/// - Nominal charged hopper after coffee brew: HZ[0][3] == '1' && CS[39..43] < 0x1000 -> charged (returns true).
pub fn evaluate_commercial_hopper_state(hz_charged_flag: bool, cs_bean_word: u16) -> bool {
    hz_charged_flag && cs_bean_word < 0x1000
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BeansState {
    Present,
    Hysteresis,
    Empty,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OpticalSensorReading {
    pub ambient_adc: u16,
    pub reflected_adc: u16,
    pub delta: u16,
    pub shunt_ratio: f32,
    pub is_ntc_self_test_valid: bool,
    pub state: BeansState,
}

impl OpticalSensorReading {
    pub const DEFAULT_THRESHOLD: u16 = 115;
    pub const DEFAULT_HYSTERESIS: u16 = 5;

    pub fn evaluate(ambient_adc: u16, reflected_adc: u16) -> Self {
        Self::evaluate_with_threshold(
            ambient_adc,
            reflected_adc,
            Self::DEFAULT_THRESHOLD,
            Self::DEFAULT_HYSTERESIS,
        )
    }

    pub fn evaluate_with_threshold(
        ambient_adc: u16,
        reflected_adc: u16,
        threshold: u16,
        hysteresis: u16,
    ) -> Self {
        let delta = reflected_adc.saturating_sub(ambient_adc);
        let shunt_ratio = if ambient_adc > 0 {
            (reflected_adc as f32) / (ambient_adc as f32)
        } else {
            1.0
        };
        // P518Ani.exe Check Sensor VA 0x004E6E28 (Coffee Heater NTC Self-Test):
        // Valid range 180 < off_adc < 17000 and nominal +6.0% calibration shunt (1.050 .. 1.070)
        let is_ntc_self_test_valid = (180 < ambient_adc && ambient_adc < 17000)
            && (1.050..=1.070).contains(&shunt_ratio);

        let lower = threshold.saturating_sub(hysteresis);
        let upper = threshold.saturating_add(hysteresis);
        let state = if delta <= lower {
            BeansState::Present
        } else if delta >= upper {
            BeansState::Empty
        } else {
            BeansState::Hysteresis
        };
        Self {
            ambient_adc,
            reflected_adc,
            delta,
            shunt_ratio,
            is_ntc_self_test_valid,
            state,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CsTelemetryFrame {
    pub raw: String,
    pub coffee_temp_raw: u16,
    pub rotary_pos: u8,
    pub bu_pos_raw: u16,
    pub bean_photodiode_raw: u16,
    pub bean_photodiode_adc: u16,
    pub beans_ok: bool,
    pub flowmeter_pulses: u16,
    pub model_tag: u16,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BoardFamily {
    /// 8-bit Top-Tronic (EF509, EF525, EF533, EF703): 128/256 words, RT:xx/RE:xx
    TopTronic8Bit,
    /// 16-bit Modern Domestic (EF518M, E8, S8): 1024 words, RT:xxxx/RE:xxxx
    ModernDomestic,
    /// Renesas RL78 (EF535M, WE8): 1024 words, block 0x0180 + 0x017F layout
    RenesasRL78,
    /// Commercial Dual Thermoblock (EF536M, EF540M, GIGA series, XJ5 GII): 32-bit double-word counters
    CommercialDualTb,
}

impl BoardFamily {
    pub fn from_firmware_code(fw: &str) -> Self {
        let upper = fw.to_uppercase();
        if upper.contains("EF535") || upper.contains("WE8") || upper.contains("RL78") {
            BoardFamily::RenesasRL78
        } else if upper.contains("EF536") || upper.contains("EF540") || upper.contains("GIGA") {
            BoardFamily::CommercialDualTb
        } else if upper.contains("EF518") || upper.contains("EF529") || upper.contains("EF528") {
            BoardFamily::ModernDomestic
        } else {
            BoardFamily::TopTronic8Bit
        }
    }

    pub fn addressing_mode(&self) -> AddressingMode {
        match self {
            BoardFamily::TopTronic8Bit => AddressingMode::TwoDigit,
            _ => AddressingMode::FourDigit,
        }
    }

    pub fn max_words(&self) -> usize {
        match self {
            BoardFamily::TopTronic8Bit => 256,
            _ => 1024,
        }
    }

    /// Reconstructs 32-bit big-endian double-word counter: (high << 16) | low
    pub fn decode_counter_32bit(high_word: u16, low_word: u16) -> u32 {
        ((high_word as u32) << 16) | (low_word as u32)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum JuraResponse {
    Firmware(String),
    DisplayFirmware(String),
    Bootloader(String),
    PowerSpec(String),
    CodeChecksum(String),
    EEPROMWord(u16),
    EEPROMBlock(Vec<u16>),
    Telemetry(HzTelemetryFrame),
    Optical(OpticalSensorReading),
    Ack(String),
}

pub struct JuraProtocol;

impl JuraProtocol {
    /// Strict read-only diagnostic command allowlist (mirrors `serial_io.SAFE_READ_PREFIXES`).
    pub const SAFE_READ_PREFIXES: &'static [&'static str] = &[
        "TY:", "IC:", "HZ:", "CS:", "AS:", "RT:", "RE:", "TL:",
        "TY$:", "TL$:", "TP$:", "T1$:", "T2$:", "T3$:", "TX$:", "TZ$:",
        "EX$:", "CS$:", "HZ$:", "RE$:", "RT$:", "DS$:", "GS$:", "SS$:",
        "ST$:", "IC$:", "RR$:", "AS$:",
        "@T0", "@T1", "@T2:", "@T3", "@TR:", "@TG:", "@TF:", "@TM:",
    ];

    /// Validates that a hardware command is a single-line, printable ASCII
    /// read-only diagnostic query. Rejects standby/reset/EEPROM-write commands
    /// and any unlisted actuator or service command (e.g. `FN:`, `PA:`, `S0:`).
    pub fn validate_safety(raw_cmd: &str) -> Result<(), CoreError> {
        // Strip at most one trailing line terminator so embedded CRLF injection fails below.
        let stripped = if let Some(s) = raw_cmd.strip_suffix("\r\n") {
            s
        } else if let Some(s) = raw_cmd.strip_suffix('\r').or_else(|| raw_cmd.strip_suffix('\n')) {
            s
        } else {
            raw_cmd
        }
        .trim_matches(' ');

        if stripped.is_empty() {
            return Err(CoreError::SafetyViolation(
                "Empty command is forbidden".into(),
            ));
        }
        if stripped.len() > 64 {
            return Err(CoreError::SafetyViolation(format!(
                "Command exceeds 64-byte limit ({} bytes)",
                stripped.len()
            )));
        }
        if stripped.bytes().any(|b| !(0x20..0x7F).contains(&b)) {
            return Err(CoreError::SafetyViolation(
                "Command contains control characters or non-ASCII bytes".into(),
            ));
        }
        let clean = stripped.to_ascii_uppercase();
        if clean == "AN" || clean.starts_with("AN:") {
            return Err(CoreError::SafetyViolation(format!(
                "Prohibited 'AN' / 'AN:' command '{clean}' triggers hardware standby / powers off machine"
            )));
        }
        if clean == "FA" || clean.starts_with("FA:") {
            return Err(CoreError::SafetyViolation(format!(
                "Prohibited 'FA' / 'FA:' command '{clean}' triggers factory reset or unverified service action"
            )));
        }
        if clean.starts_with("WE:")
            || clean.starts_with("WT:")
            || clean.starts_with("DA:")
            || clean.starts_with("@TW:")
        {
            return Err(CoreError::SafetyViolation(format!(
                "Command '{clean}' mutates EEPROM; forbidden in read-only telemetry profile"
            )));
        }
        if !Self::SAFE_READ_PREFIXES
            .iter()
            .any(|prefix| clean.starts_with(prefix))
        {
            return Err(CoreError::SafetyViolation(format!(
                "Command '{clean}' is not in the strict read-only telemetry allowlist"
            )));
        }
        Ok(())
    }

    pub fn format_command(cmd: &JuraCommand) -> Result<String, CoreError> {
        let text = match cmd {
            JuraCommand::IdentifyFirmware => "TY:\r\n".into(),
            JuraCommand::IdentifyDisplaySubFirmware => "TY$:\r\n".into(),
            JuraCommand::IdentifyBootloader => "TL:\r\n".into(),
            JuraCommand::IdentifyDisplayBootloader => "TL$:\r\n".into(),
            JuraCommand::ReadPowerSpec => "IC:\r\n".into(),
            JuraCommand::ReadCodeChecksum => "CS:\r\n".into(),
            JuraCommand::ReadDisplayCodeChecksum => "CS$:\r\n".into(),
            JuraCommand::ReadVolatileTelemetry => "HZ:\r\n".into(),
            JuraCommand::ReadOpticalBeanSensor => "AS:\r\n".into(),
            JuraCommand::ReadEEPROMWord { addr, mode } => match mode {
                AddressingMode::TwoDigit => format!("RE:{:02X}\r\n", addr & 0xFF),
                AddressingMode::FourDigit => format!("RE:{:04X}\r\n", addr),
            },
            JuraCommand::ReadEEPROMBlock { block_index, mode } => match mode {
                AddressingMode::TwoDigit => format!("RT:{:02X}\r\n", block_index & 0xFF),
                AddressingMode::FourDigit => format!("RT:{:04X}\r\n", block_index),
            },
            JuraCommand::RecalculateCRC => "AN:0B\r\n".into(),
            JuraCommand::EnterTestMode => "AN:20\r\n".into(),
            JuraCommand::ExitTestMode => "AN:21\r\n".into(),
            JuraCommand::PulsePump => "FA:08\r\n".into(),
            JuraCommand::ExecuteFunction(fn_id) => format!("FN:{:02X}\r\n", fn_id),
            JuraCommand::RawSafe(s) => {
                Self::validate_safety(s)?;
                format!("{}\r\n", s.trim())
            }
        };
        Ok(text)
    }

    /// Encodes a full ASCII command string into 4:1 Jura wire bytes (`4 * N` bytes)
    pub fn encode_wire_frame(ascii_cmd: &str) -> Vec<u8> {
        Self::encode_wire_bytes(ascii_cmd.as_bytes())
    }

    /// Encodes raw payload bytes into 4:1 Jura wire carrier bytes (`4 * N` bytes)
    pub fn encode_wire_bytes(data: &[u8]) -> Vec<u8> {
        let mut wire = Vec::with_capacity(data.len() * 4);
        for &b in data {
            wire.extend_from_slice(&jura_codec::encode_byte(b));
        }
        wire
    }

    /// Decodes complete 4-byte 4:1 Jura carrier groups into raw payload bytes,
    /// returning `(decoded_bytes, remaining_tail_bytes)`.
    pub fn decode_wire_bytes(raw: &[u8]) -> (Vec<u8>, Vec<u8>) {
        let (chunks, remainder_slice) = raw.as_chunks::<4>();
        let mut decoded = Vec::with_capacity(chunks.len());
        for chunk in chunks {
            let mut b = 0u8;
            for (i, &r) in chunk.iter().enumerate() {
                let bit0 = (r >> 2) & 1;
                let bit1 = (r >> 5) & 1;
                let nibble = bit0 | (bit1 << 1);
                b |= nibble << (2 * i);
            }
            decoded.push(b);
        }
        (decoded, remainder_slice.to_vec())
    }

    /// Decodes a 4:1 Jura wire buffer (`4 * N` bytes) back into an ASCII string
    pub fn decode_wire_frame(raw: &[u8]) -> HalResult<String> {
        if !raw.len().is_multiple_of(4) {
            return Err(HalError::EncodingError {
                index: raw.len(),
                raw: *raw.last().unwrap_or(&0),
            });
        }
        let mut decoded = Vec::with_capacity(raw.len() / 4);
        let (chunks, _) = raw.as_chunks::<4>();
        for quad in chunks {
            decoded.push(jura_codec::decode_quad(quad)?);
        }
        Ok(String::from_utf8_lossy(&decoded).into_owned())
    }

    pub fn parse_re_response(raw: &str) -> Result<u16, CoreError> {
        let trimmed = raw.trim();
        let payload = trimmed
            .strip_prefix("re:")
            .or_else(|| trimmed.strip_prefix("RE:"))
            .ok_or_else(|| CoreError::ResponseFraming {
                expected: "re:".into(),
                actual: raw.into(),
            })?;
        u16::from_str_radix(payload.trim(), 16).map_err(|_| CoreError::ParseError {
            field: "RE word".into(),
            raw: raw.into(),
        })
    }

    pub fn parse_rt_response(raw: &str) -> Result<Vec<u16>, CoreError> {
        let trimmed = raw.trim();
        let payload = trimmed
            .strip_prefix("rt:")
            .or_else(|| trimmed.strip_prefix("RT:"))
            .ok_or_else(|| CoreError::ResponseFraming {
                expected: "rt:".into(),
                actual: raw.into(),
            })?;
        if !payload.is_ascii() {
            return Err(CoreError::ParseError {
                field: "RT payload (non-ASCII)".into(),
                raw: raw.into(),
            });
        }
        if payload.len() < 64 {
            return Err(CoreError::ParseError {
                field: "RT block length (<64 hex)".into(),
                raw: raw.into(),
            });
        }
        let mut words = Vec::with_capacity(16);
        for i in 0..16 {
            let chunk = &payload[i * 4..i * 4 + 4];
            let val = u16::from_str_radix(chunk, 16).map_err(|_| CoreError::ParseError {
                field: format!("RT word {i}"),
                raw: chunk.into(),
            })?;
            words.push(val);
        }
        Ok(words)
    }

    fn parse_hex_u16(field_name: &str, s: &str) -> Result<u16, CoreError> {
        u16::from_str_radix(s.trim(), 16).map_err(|_| CoreError::ParseError {
            field: field_name.into(),
            raw: s.into(),
        })
    }

    pub fn parse_hz_response(raw: &str, delta_t_sec: f32) -> Result<HzTelemetryFrame, CoreError> {
        let trimmed = raw.trim();
        let payload = trimmed
            .strip_prefix("hz:")
            .or_else(|| trimmed.strip_prefix("HZ:"))
            .ok_or_else(|| CoreError::ResponseFraming {
                expected: "hz:".into(),
                actual: raw.into(),
            })?;
        let parts: Vec<&str> = payload.split(',').collect();
        if parts.len() < 10 {
            return Err(CoreError::ParseError {
                field: "HZ fields (<10)".into(),
                raw: raw.into(),
            });
        }

        let status = parts[0];
        let is_busy = status.starts_with('1');
        let bu_initialized = status.chars().nth(1) == Some('1');
        let valve_busy = status.chars().nth(2) == Some('1');
        let beans_charged = status.chars().nth(3) == Some('1');
        let heater_ready = status.chars().nth(5) == Some('1');

        let bu_upper_encoder = Self::parse_hex_u16("HZ[1] bu_upper_encoder", parts[1])?;
        let bu_current_encoder = Self::parse_hex_u16("HZ[2] bu_current_encoder", parts[2])?;
        let flowmeter_pulses = Self::parse_hex_u16("HZ[3] flowmeter_pulses", parts[3])?;

        let tb1_raw = Self::parse_hex_u16("HZ[4] tb1_raw", parts[4])?;
        let coffee_temp_c = (tb1_raw as f32) / 10.0;

        let tb2_raw = Self::parse_hex_u16("HZ[5] tb2_raw", parts[5])?;
        let steam_temp_c = if tb2_raw >= 1900 || tb2_raw == 0x0802 {
            None
        } else {
            Some((tb2_raw as f32) / 10.0)
        };

        let rotary_pos = parts[6].trim().parse::<u8>().map_err(|_| CoreError::ParseError {
            field: "HZ[6] rotary_pos".into(),
            raw: parts[6].into(),
        })?;

        let cuts = parts[7];
        let drip_tray_missing = cuts.starts_with('1');
        let grounds_full = cuts.chars().nth(1) == Some('1');
        let water_tank_empty = cuts.chars().nth(2) == Some('1');
        let mcu_heartbeat_tick = cuts.chars().nth(3) == Some('1');

        let puck_thickness_ticks = Self::parse_hex_u16("HZ[8] puck_thickness_ticks", parts[8])?;
        let flow_rate_ml_s = if delta_t_sec > 0.0 {
            (flowmeter_pulses as f32) / (DIGIMESA_PULSES_PER_ML * delta_t_sec)
        } else {
            0.0
        };

        Ok(HzTelemetryFrame {
            coffee_temp_c,
            steam_temp_c,
            flowmeter_pulses,
            flow_rate_ml_s,
            bu_upper_encoder,
            bu_current_encoder,
            rotary_pos,
            drip_tray_missing,
            grounds_full,
            water_tank_empty,
            mcu_heartbeat_tick,
            is_busy,
            heater_ready,
            bu_initialized,
            valve_busy,
            puck_thickness_ticks,
            beans_charged,
        })
    }

    /// Parses optical IR bean hopper sensor reading from `AS:` response frame
    pub fn parse_as_response(raw: &str) -> Result<OpticalSensorReading, CoreError> {
        let trimmed = raw.trim();
        let payload = trimmed
            .strip_prefix("as:")
            .or_else(|| trimmed.strip_prefix("AS:"))
            .ok_or_else(|| CoreError::ResponseFraming {
                expected: "as:".into(),
                actual: raw.into(),
            })?;
        if !payload.is_ascii() {
            return Err(CoreError::ParseError {
                field: "AS payload (non-ASCII)".into(),
                raw: raw.into(),
            });
        }
        let parts: Vec<&str> = payload.split(',').collect();
        if parts.len() < 2 {
            return Err(CoreError::ParseError {
                field: "AS fields (<2)".into(),
                raw: raw.into(),
            });
        }
        let (off_adc, on_adc) = if parts[0].len() >= 8 && parts[1].len() >= 8 {
            let off = u16::from_str_radix(&parts[0][4..8], 16).map_err(|_| CoreError::ParseError {
                field: "AS[0] off_adc".into(),
                raw: parts[0].into(),
            })?;
            let on = u16::from_str_radix(&parts[1][4..8], 16).map_err(|_| CoreError::ParseError {
                field: "AS[1] on_adc".into(),
                raw: parts[1].into(),
            })?;
            (off, on)
        } else if parts.len() >= 5 {
            let off = u16::from_str_radix(parts[1].trim(), 16)
                .or_else(|_| u16::from_str_radix(parts[0].trim(), 16))
                .map_err(|_| CoreError::ParseError {
                    field: "AS off_adc".into(),
                    raw: raw.into(),
                })?;
            let on = u16::from_str_radix(parts[4].trim(), 16)
                .or_else(|_| u16::from_str_radix(parts[1].trim(), 16))
                .map_err(|_| CoreError::ParseError {
                    field: "AS on_adc".into(),
                    raw: raw.into(),
                })?;
            (off, on)
        } else {
            let off = u16::from_str_radix(parts[0].trim(), 16).map_err(|_| CoreError::ParseError {
                field: "AS[0]".into(),
                raw: parts[0].into(),
            })?;
            let on = u16::from_str_radix(parts[1].trim(), 16).map_err(|_| CoreError::ParseError {
                field: "AS[1]".into(),
                raw: parts[1].into(),
            })?;
            (off, on)
        };

        Ok(OpticalSensorReading::evaluate(off_adc, on_adc))
    }

    /// Parses volatile component status and live IR bean sensor photodiode ADC from `CS:` response frame
    /// Format: `cs:TTTTRPPPP...BBBBFFFFMMMM` where:
    /// - TTTT (s[3..7]): Coffee Thermoblock NTC raw temperature ADC
    /// - R (s[7..8]): Rotary dial position
    /// - PPPP (s[8..12]): Current Brew Unit encoder position ticks
    /// - BBBB (s[39..43], or payload[36..40]): 10-bit IR bean photodiode ADC (< 0x1000 = Beans OK, >= 0x1000 = Fill Beans)
    /// - FFFF (s[43..47]): Dispense volume flowmeter impulses
    /// - MMMM (s[47..51]): Model hardware line tag
    pub fn parse_cs_response(raw: &str) -> Result<CsTelemetryFrame, CoreError> {
        let trimmed = raw.trim();
        let payload = trimmed
            .strip_prefix("cs:")
            .or_else(|| trimmed.strip_prefix("CS:"))
            .ok_or_else(|| CoreError::ResponseFraming {
                expected: "cs:".into(),
                actual: raw.into(),
            })?;

        if !payload.is_ascii() {
            return Err(CoreError::ParseError {
                field: "CS payload (non-ASCII)".into(),
                raw: raw.into(),
            });
        }

        if payload.len() < 40 {
            return Err(CoreError::ParseError {
                field: "CS frame length (<40 chars)".into(),
                raw: raw.into(),
            });
        }

        let coffee_temp_raw = u16::from_str_radix(&payload[0..4], 16)
            .map_err(|_| CoreError::ParseError {
                field: "CS coffee temp".into(),
                raw: payload[0..4].into(),
            })?;

        let rotary_pos = payload.chars().nth(4).and_then(|c| c.to_digit(16)).unwrap_or(0) as u8;

        let bu_pos_raw = u16::from_str_radix(&payload[5..9], 16)
            .map_err(|_| CoreError::ParseError {
                field: "CS BU pos".into(),
                raw: payload[5..9].into(),
            })?;

        let bean_photodiode_raw = u16::from_str_radix(&payload[36..40], 16)
            .map_err(|_| CoreError::ParseError {
                field: "CS bean sensor photodiode".into(),
                raw: payload[36..40].into(),
            })?;

        let bean_photodiode_adc = bean_photodiode_raw >> 4;
        let beans_ok = bean_photodiode_raw < 0x1000;

        let flowmeter_pulses = if payload.len() >= 44 {
            u16::from_str_radix(&payload[40..44], 16).unwrap_or(0)
        } else {
            0
        };

        let model_tag = if payload.len() >= 48 {
            u16::from_str_radix(&payload[44..48], 16).unwrap_or(0)
        } else {
            0
        };

        Ok(CsTelemetryFrame {
            raw: trimmed.to_string(),
            coffee_temp_raw,
            rotary_pos,
            bu_pos_raw,
            bean_photodiode_raw,
            bean_photodiode_adc,
            beans_ok,
            flowmeter_pulses,
            model_tag,
        })
    }
}

impl MachineProtocol for JuraProtocol {
    type Command = JuraCommand;
    type TelemetryFrame = JuraResponse;

    fn encode_command(&self, cmd: &Self::Command) -> HalResult<Vec<u8>> {
        let ascii = Self::format_command(cmd)
            .map_err(|e| HalError::HardwareFault(e.to_string()))?;
        Ok(Self::encode_wire_frame(&ascii))
    }

    fn decode_frame(&self, raw: &[u8]) -> HalResult<Self::TelemetryFrame> {
        let ascii = Self::decode_wire_frame(raw)?;
        let trimmed = ascii.trim();
        let lower = trimmed.to_ascii_lowercase();
        if lower.starts_with("ty:") {
            Ok(JuraResponse::Firmware(trimmed[3..].to_string()))
        } else if lower.starts_with("ty$:") {
            Ok(JuraResponse::DisplayFirmware(trimmed[4..].to_string()))
        } else if lower.starts_with("tl:") {
            Ok(JuraResponse::Bootloader(trimmed[3..].to_string()))
        } else if lower.starts_with("tl$:") {
            Ok(JuraResponse::Bootloader(trimmed[4..].to_string()))
        } else if lower.starts_with("cs:") {
            Ok(JuraResponse::CodeChecksum(trimmed[3..].to_string()))
        } else if lower.starts_with("cs$:") {
            Ok(JuraResponse::CodeChecksum(trimmed[4..].to_string()))
        } else if lower.starts_with("ic:") {
            Ok(JuraResponse::PowerSpec(trimmed[3..].to_string()))
        } else if lower.starts_with("as:") {
            let opt = Self::parse_as_response(trimmed)
                .map_err(|e| HalError::HardwareFault(e.to_string()))?;
            Ok(JuraResponse::Optical(opt))
        } else if lower.starts_with("re:") {
            let word = Self::parse_re_response(trimmed)
                .map_err(|e| HalError::HardwareFault(e.to_string()))?;
            Ok(JuraResponse::EEPROMWord(word))
        } else if lower.starts_with("rt:") {
            let words = Self::parse_rt_response(trimmed)
                .map_err(|e| HalError::HardwareFault(e.to_string()))?;
            Ok(JuraResponse::EEPROMBlock(words))
        } else if lower.starts_with("hz:") {
            let hz = Self::parse_hz_response(trimmed, 1.0)
                .map_err(|e| HalError::HardwareFault(e.to_string()))?;
            Ok(JuraResponse::Telemetry(hz))
        } else {
            Ok(JuraResponse::Ack(trimmed.to_string()))
        }
    }
}

/// Recovered Jura Smart Connect '@'-protocol nibble substitution cipher
pub struct SmartConnectCipher;

impl SmartConnectCipher {
    fn shuffle(nib: u8, pos: usize, key: u8) -> u8 {
        let ta = (key >> 4) as isize;
        let tm = (key & 15) as isize;
        let i5 = ((pos >> 4) & 15) as isize;
        let p = pos as isize;
        let n = nib as isize;

        let a = SBOX_N1[(((n + p + ta) % 16 + 16) % 16) as usize] as isize;
        let inner = ((i5 + a + tm - p - ta) % 16 + 16) % 16;
        let outer = ((SBOX_N2[inner as usize] as isize + ta + p - tm - i5) % 16 + 16) % 16;
        let res = ((SBOX_N1[outer as usize] as isize - p - ta) % 16 + 16) % 16;
        res as u8
    }

    /// Involution per-nibble cipher (`crypt(crypt(m, k), k) == m`)
    pub fn crypt(data: &[u8], key: u8) -> Vec<u8> {
        let mut out = Vec::with_capacity(data.len());
        for (i, &b) in data.iter().enumerate() {
            let high = Self::shuffle(b >> 4, 2 * i, key);
            let low = Self::shuffle(b & 0x0F, 2 * i + 1, key);
            out.push((high << 4) | low);
        }
        out
    }

    pub fn escape_frame(data: &[u8]) -> Vec<u8> {
        let mut out = Vec::with_capacity(data.len() + 4);
        for &b in data {
            if b == 0x00 || b == 0x0A || b == 0x0D || b == 0x1B || b == 0x26 {
                out.push(0x1B);
                out.push(b ^ 0x80);
            } else {
                out.push(b);
            }
        }
        out
    }

    pub fn unescape_frame(data: &[u8]) -> Vec<u8> {
        let mut out = Vec::with_capacity(data.len());
        let mut i = 0;
        while i < data.len() {
            if data[i] == 0x1B && i + 1 < data.len() {
                i += 1;
                out.push(data[i] ^ 0x80);
            } else {
                out.push(data[i]);
            }
            i += 1;
        }
        out
    }

    /// Builds an encrypted Smart Connect frame: '&' + escape(key + crypt(cmd + "\r\n", key)) + '\r\n'
    pub fn build_frame(cmd_payload: &[u8], key: u8) -> Vec<u8> {
        let mut raw_pt = cmd_payload.to_vec();
        if !raw_pt.ends_with(b"\r\n") {
            raw_pt.extend_from_slice(b"\r\n");
        }
        let encrypted = Self::crypt(&raw_pt, key);
        let mut body = Vec::with_capacity(1 + encrypted.len());
        body.push(key);
        body.extend_from_slice(&encrypted);
        let escaped = Self::escape_frame(&body);
        let mut frame = Vec::with_capacity(escaped.len() + 3);
        frame.push(0x26); // '&'
        frame.extend_from_slice(&escaped);
        frame.push(0x0D);
        frame.push(0x0A);
        frame
    }

    /// Decodes a received '&'...CRLF Smart Connect frame back to plaintext bytes.
    pub fn decode_frame(frame: &[u8]) -> Option<String> {
        let mut start = 0;
        while start < frame.len() && (frame[start] == b'\r' || frame[start] == b'\n') {
            start += 1;
        }
        let mut end = frame.len();
        while end > start && (frame[end - 1] == b'\r' || frame[end - 1] == b'\n') {
            end -= 1;
        }
        let clean = &frame[start..end];
        if !clean.starts_with(b"&") || clean.len() < 2 {
            return None;
        }
        let body = Self::unescape_frame(&clean[1..]);
        if body.is_empty() {
            return None;
        }
        let key = body[0];
        let payload = Self::crypt(&body[1..], key);
        Some(String::from_utf8_lossy(&payload).into_owned())
    }

    /// Builds a standard Smart Connect block read frame: '@TR:32,xx\r\n'
    pub fn build_read_block_frame(block_index: u16, _word_count: u8, _mode: AddressingMode, key: u8) -> Vec<u8> {
        let ascii_cmd = format!("@TR:32,{:02X}\r\n", block_index & 0xFF);
        Self::build_frame(ascii_cmd.as_bytes(), key)
    }

    /// Builds firmware query frame: '@TF:\r\n'
    pub fn build_query_firmware_frame(key: u8) -> Vec<u8> {
        Self::build_frame(b"@TF:\r\n", key)
    }

    /// Builds model query frame: '@TM:\r\n'
    pub fn build_query_model_frame(key: u8) -> Vec<u8> {
        Self::build_frame(b"@TM:\r\n", key)
    }
}

/// Differential EEPROM word delta for reverse-engineering and sniffer memory mapping.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EepromWordDiff {
    pub addr: u16,
    pub baseline: u16,
    pub current: u16,
    pub flipped_bits: u16,
}

impl EepromWordDiff {
    pub fn new(addr: u16, baseline: u16, current: u16) -> Self {
        Self {
            addr,
            baseline,
            current,
            flipped_bits: baseline ^ current,
        }
    }
}

/// Diffs two slices of EEPROM 16-bit words starting at `start_addr`.
pub fn diff_eeprom_blocks(
    baseline: &[u16],
    current: &[u16],
    start_addr: u16,
) -> Vec<EepromWordDiff> {
    let len = baseline.len().min(current.len());
    let mut diffs = Vec::new();
    for i in 0..len {
        let base = baseline[i];
        let cur = current[i];
        if base != cur {
            if let Ok(offset) = u16::try_from(i) {
                if let Some(addr) = start_addr.checked_add(offset) {
                    diffs.push(EepromWordDiff::new(addr, base, cur));
                }
            }
        }
    }
    diffs
}

/// High-level asynchronous Jura machine protocol driver wrapping an underlying `Transport`.
pub struct JuraClient<T: Transport> {
    transport: T,
    addressing_mode: AddressingMode,
    inter_byte_delay: Duration,
    timeout: Duration,
    obfuscate_4byte: bool,
}

impl<T: Transport> JuraClient<T> {
    pub fn new(transport: T) -> Self {
        Self {
            transport,
            addressing_mode: AddressingMode::FourDigit,
            inter_byte_delay: Duration::from_millis(8),
            timeout: Duration::from_millis(1500),
            obfuscate_4byte: true,
        }
    }

    pub fn with_addressing_mode(mut self, mode: AddressingMode) -> Self {
        self.addressing_mode = mode;
        self
    }

    pub fn set_addressing_mode(&mut self, mode: AddressingMode) {
        self.addressing_mode = mode;
    }

    pub fn addressing_mode(&self) -> AddressingMode {
        self.addressing_mode
    }

    pub fn with_inter_byte_delay(mut self, delay: Duration) -> Self {
        self.inter_byte_delay = delay;
        self
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    pub fn with_obfuscation(mut self, enabled: bool) -> Self {
        self.obfuscate_4byte = enabled;
        self
    }

    pub fn transport(&self) -> &T {
        &self.transport
    }

    pub fn transport_mut(&mut self) -> &mut T {
        &mut self.transport
    }

    pub fn into_transport(self) -> T {
        self.transport
    }

    /// Strips any optical transceiver or half-duplex echo of `cmd` from the beginning of `response`.
    pub fn strip_echo<'a>(cmd: &str, response: &'a str) -> &'a str {
        let trimmed_cmd = cmd.trim();
        let trimmed_resp = response.trim();
        if let Some(stripped) = trimmed_resp.strip_prefix(trimmed_cmd) {
            stripped.trim()
        } else {
            trimmed_resp
        }
    }

    /// Transmits a formatted command, paces wire transmission, reads response until newline,
    /// strips optical echoes, and parses the returned frame into `JuraResponse`.
    pub async fn send_command(&mut self, cmd: &JuraCommand) -> HalResult<JuraResponse> {
        let formatted = JuraProtocol::format_command(cmd)
            .map_err(|e| HalError::HardwareFault(e.to_string()))?;

        let wire = if self.obfuscate_4byte {
            JuraProtocol::encode_wire_frame(&formatted)
        } else {
            formatted.as_bytes().to_vec()
        };

        self.transport
            .write_raw(&wire, Some(self.inter_byte_delay))
            .await?;

        let start = std::time::Instant::now();
        const MAX_FRAME_BYTES: usize = 16384;
        let mut raw_buf = Vec::with_capacity(256);
        let mut decoded_bytes = Vec::with_capacity(64);
        let mut decoded_groups: usize = 0;

        loop {
            if start.elapsed() >= self.timeout {
                return Err(HalError::Timeout(self.timeout));
            }
            let remaining = self.timeout.saturating_sub(start.elapsed());
            let mut chunk = [0u8; 64];
            let n = self.transport.read_raw(&mut chunk, remaining).await?;
            if n == 0 {
                break;
            }
            if raw_buf.len().saturating_add(n) > MAX_FRAME_BYTES {
                return Err(HalError::HardwareFault(format!(
                    "Response frame exceeded {MAX_FRAME_BYTES} byte limit"
                )));
            }
            raw_buf.extend_from_slice(&chunk[..n]);

            if self.obfuscate_4byte {
                let total_groups = raw_buf.len() / 4;
                while decoded_groups < total_groups {
                    let base = decoded_groups * 4;
                    let quad = [
                        raw_buf[base],
                        raw_buf[base + 1],
                        raw_buf[base + 2],
                        raw_buf[base + 3],
                    ];
                    decoded_bytes.push(jura_codec::decode_quad(&quad)?);
                    decoded_groups += 1;
                }
                if decoded_bytes.ends_with(b"\r\n")
                    || decoded_bytes.ends_with(b"\n")
                    || decoded_bytes.ends_with(b"\r")
                {
                    break;
                }
            } else if (raw_buf.contains(&b'\n') || raw_buf.contains(&b'\r'))
                && std::str::from_utf8(&raw_buf)
                    .is_ok_and(|s| s.ends_with("\r\n") || s.ends_with('\n') || s.ends_with('\r'))
            {
                break;
            }
        }

        let decoded_str = if self.obfuscate_4byte {
            if !raw_buf.len().is_multiple_of(4) {
                return Err(HalError::EncodingError {
                    index: raw_buf.len(),
                    raw: *raw_buf.last().unwrap_or(&0),
                });
            }
            String::from_utf8_lossy(&decoded_bytes).into_owned()
        } else {
            String::from_utf8_lossy(&raw_buf).to_string()
        };

        let clean = Self::strip_echo(&formatted, &decoded_str);

        let lower = clean.to_ascii_lowercase();
        if lower.starts_with("ty:") {
            Ok(JuraResponse::Firmware(clean[3..].trim().to_string()))
        } else if lower.starts_with("ty$:") {
            Ok(JuraResponse::DisplayFirmware(clean[4..].trim().to_string()))
        } else if lower.starts_with("tl:") {
            Ok(JuraResponse::Bootloader(clean[3..].trim().to_string()))
        } else if lower.starts_with("ic:") {
            Ok(JuraResponse::PowerSpec(clean[3..].trim().to_string()))
        } else if lower.starts_with("re:") {
            let word = JuraProtocol::parse_re_response(clean)
                .map_err(|e| HalError::HardwareFault(e.to_string()))?;
            Ok(JuraResponse::EEPROMWord(word))
        } else if lower.starts_with("rt:") {
            let words = JuraProtocol::parse_rt_response(clean)
                .map_err(|e| HalError::HardwareFault(e.to_string()))?;
            Ok(JuraResponse::EEPROMBlock(words))
        } else if lower.starts_with("hz:") {
            let hz = JuraProtocol::parse_hz_response(clean, 1.0)
                .map_err(|e| HalError::HardwareFault(e.to_string()))?;
            Ok(JuraResponse::Telemetry(hz))
        } else {
            Ok(JuraResponse::Ack(clean.to_string()))
        }
    }

    /// Polls `HZ:` telemetry and parses real-time metric sensor readings.
    pub async fn poll_telemetry(&mut self, delta_t_sec: f32) -> HalResult<HzTelemetryFrame> {
        let resp = self
            .send_command(&JuraCommand::ReadVolatileTelemetry)
            .await?;
        match resp {
            JuraResponse::Telemetry(mut frame) => {
                if delta_t_sec > 0.0 && delta_t_sec != 1.0 {
                    frame.flow_rate_ml_s =
                        (frame.flowmeter_pulses as f32) / (DIGIMESA_PULSES_PER_ML * delta_t_sec);
                }
                Ok(frame)
            }
            other => Err(HalError::HardwareFault(format!(
                "Expected HZ telemetry frame, got: {other:?}"
            ))),
        }
    }

    /// Reads a 16-word EEPROM block via `RT:` command.
    pub async fn read_eeprom_block(&mut self, block_index: u16) -> HalResult<Vec<u16>> {
        let resp = self
            .send_command(&JuraCommand::ReadEEPROMBlock {
                block_index,
                mode: self.addressing_mode,
            })
            .await?;
        match resp {
            JuraResponse::EEPROMBlock(words) => Ok(words),
            other => Err(HalError::HardwareFault(format!(
                "Expected RT EEPROM block, got: {other:?}"
            ))),
        }
    }

    /// Reads a single 16-bit word from EEPROM via `RE:` command.
    pub async fn read_eeprom_word(&mut self, addr: u16) -> HalResult<u16> {
        let resp = self
            .send_command(&JuraCommand::ReadEEPROMWord {
                addr,
                mode: self.addressing_mode,
            })
            .await?;
        match resp {
            JuraResponse::EEPROMWord(w) => Ok(w),
            other => Err(HalError::HardwareFault(format!(
                "Expected RE EEPROM word, got: {other:?}"
            ))),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_safety_invariants_reject_bare_power_and_reset() {
        assert!(matches!(
            JuraProtocol::validate_safety("AN:"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("AN:01"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("AN:0B"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("FA:01"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("FA:\r\n"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("WE:0030,1234"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("TY:\r\nWE:0030,FFFF"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("TY:\nAN:"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("@T0\r\n@tw:00"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety(""),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("TY:\x00"),
            Err(CoreError::SafetyViolation(_))
        ));
        // Unlisted actuator / service / write commands must be rejected by strict allowlist
        assert!(matches!(
            JuraProtocol::validate_safety("FN:01"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("PA:00"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("S0:01"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("TS$:4,01"),
            Err(CoreError::SafetyViolation(_))
        ));
        assert!(matches!(
            JuraProtocol::validate_safety("TY:00000000000000000000000000000000000000000000000000000000000000000"),
            Err(CoreError::SafetyViolation(_))
        ));

        assert_eq!(JuraProtocol::validate_safety("TY:"), Ok(()));
        assert_eq!(JuraProtocol::validate_safety("HZ:"), Ok(()));
        assert_eq!(JuraProtocol::validate_safety("RT:0000"), Ok(()));
        assert_eq!(JuraProtocol::validate_safety("TY$:"), Ok(()));
        assert_eq!(JuraProtocol::validate_safety("@TF:"), Ok(()));
    }

    #[test]
    fn test_rt_block_parser_decodes_16_words() {
        let raw = "rt:000010A747450000025F15F500000E1900A600266DFB00000000000000000000";
        let words = JuraProtocol::parse_rt_response(raw).expect("valid RT block");
        assert_eq!(words.len(), 16);
        assert_eq!(words[1], 0x10A7);
        assert_eq!(words[2], 0x4745);
        assert_eq!(words[8], 0x00A6);
    }

    #[test]
    fn test_hz_telemetry_metric_temperatures_and_heartbeat() {
        let raw = "hz:010001100000,0287,00E3,0078,03DE,0802,3,000100,0000,00";
        let frame = JuraProtocol::parse_hz_response(raw, 1.0).expect("valid HZ frame");
        assert_eq!(frame.coffee_temp_c, 99.0);
        assert_eq!(frame.steam_temp_c, None);
        assert!(frame.mcu_heartbeat_tick);
        assert!(!frame.drip_tray_missing);
    }

    #[test]
    fn test_smart_connect_cipher_is_involution() {
        let payload = b"@TR:32,00";
        let encrypted = SmartConnectCipher::crypt(payload, 0x20);
        let decrypted = SmartConnectCipher::crypt(&encrypted, 0x20);
        assert_eq!(payload.as_slice(), decrypted.as_slice());
    }

    #[test]
    fn test_diff_eeprom_blocks() {
        let baseline = [0x0000, 0x0100, 0x00FF, 0x1234];
        let current  = [0x0000, 0x0101, 0x00FE, 0x1234];
        let diffs = diff_eeprom_blocks(&baseline, &current, 0x0010);
        assert_eq!(diffs.len(), 2);
        assert_eq!(diffs[0].addr, 0x0011);
        assert_eq!(diffs[0].baseline, 0x0100);
        assert_eq!(diffs[0].current, 0x0101);
        assert_eq!(diffs[0].flipped_bits, 0x0001);

        assert_eq!(diffs[1].addr, 0x0012);
        assert_eq!(diffs[1].baseline, 0x00FF);
        assert_eq!(diffs[1].current, 0x00FE);
        assert_eq!(diffs[1].flipped_bits, 0x0001);
    }

    #[test]
    fn test_we8_rl78_block_0180_beverage_parsing() {
        // Block 0x0180 query on Jura WE8 (EF533M / EF535M RL78):
        // 1450 (Espresso), 137 (Ristretto), 7233 (Coffee), 117 (Flat White)
        let raw = "rt:05AA00891C410075000A0186001400260048003200B7001F0000000000000000";
        let words = JuraProtocol::parse_rt_response(raw).expect("valid WE8 RT block");
        assert_eq!(words.len(), 16);
        assert_eq!(words[0], 1450); // Espresso (0x05AA)
        assert_eq!(words[1], 137);  // Ristretto (0x0089)
        assert_eq!(words[2], 7233); // Coffee (0x1C41)
        assert_eq!(words[3], 117);  // Flat White (0x0075)
    }

    #[test]
    fn test_strip_echo() {
        let raw_with_echo = "TY:\r\nty:EF509_V01\r\n";
        let clean = JuraClient::<spectra_hal::AdbSerialBridge>::strip_echo("TY:\r\n", raw_with_echo);
        assert_eq!(clean, "ty:EF509_V01");

        let raw_without_echo = "ty:EF509_V01\r\n";
        let clean2 = JuraClient::<spectra_hal::AdbSerialBridge>::strip_echo("TY:\r\n", raw_without_echo);
        assert_eq!(clean2, "ty:EF509_V01");
    }

    #[test]
    fn test_as_optical_sensor_parsing_and_hysteresis() {
        // Test parsing 8-hex-digit format: "as:0000005F,000000C4,..."
        // off_adc = 0x005F = 95, on_adc = 0x00C4 = 196 -> delta = 101 (Present)
        let raw = "as:0000005F,000000C4,00000000,00000000";
        let opt = JuraProtocol::parse_as_response(raw).expect("valid AS reading");
        assert_eq!(opt.ambient_adc, 95);
        assert_eq!(opt.reflected_adc, 196);
        assert_eq!(opt.delta, 101);
        assert_eq!(opt.state, BeansState::Present);

        // Test empty: off = 50, on = 180 -> delta = 130 >= 120 (Empty)
        let eval_empty = OpticalSensorReading::evaluate(50, 180);
        assert_eq!(eval_empty.state, BeansState::Empty);

        // Test hysteresis: off = 50, on = 165 -> delta = 115 (Hysteresis)
        let eval_hyst = OpticalSensorReading::evaluate(50, 165);
        assert_eq!(eval_hyst.state, BeansState::Hysteresis);

        // Test NTC Diagnostic Sensor Self-Test (P518Ani.exe string 251, nominal +6.0% shunt ratio ~1.060):
        // Nominal operating thermoblock: off = 1605, on = 1701 -> ratio = 1.0598
        let eval_ntc = OpticalSensorReading::evaluate(1605, 1701);
        assert!(eval_ntc.is_ntc_self_test_valid);
        assert!((eval_ntc.shunt_ratio - 1.0598).abs() < 0.001);

        // Out of bounds off_adc (< 180)
        let eval_oob = OpticalSensorReading::evaluate(150, 159);
        assert!(!eval_oob.is_ntc_self_test_valid);
    }

    #[test]
    fn test_hz_is_machine_ready() {
        let mut frame = HzTelemetryFrame {
            coffee_temp_c: 85.0,
            steam_temp_c: None,
            flowmeter_pulses: 0,
            flow_rate_ml_s: 0.0,
            bu_upper_encoder: 650,
            bu_current_encoder: 230,
            rotary_pos: 1,
            drip_tray_missing: false,
            grounds_full: false,
            water_tank_empty: false,
            mcu_heartbeat_tick: true,
            is_busy: false,
            heater_ready: true,
            bu_initialized: true,
            valve_busy: false,
            puck_thickness_ticks: 0,
            beans_charged: true,
        };
        assert!(frame.is_machine_ready());

        // Cold coffee thermoblock
        frame.coffee_temp_c = 75.0;
        assert!(!frame.is_machine_ready());
        frame.coffee_temp_c = 85.0;

        // Drip tray missing
        frame.drip_tray_missing = true;
        assert!(!frame.is_machine_ready());
        frame.drip_tray_missing = false;

        // Puck compression empty grinder run (ticks > 0 && <= 14)
        frame.puck_thickness_ticks = 10;
        assert!(!frame.is_machine_ready());
        frame.puck_thickness_ticks = 25;
        assert!(frame.is_machine_ready());
        frame.puck_thickness_ticks = 0;

        // Heartbeat tick flip does NOT alter readiness
        frame.mcu_heartbeat_tick = false;
        assert!(frame.is_machine_ready());
    }

    #[test]
    fn test_board_family_resolution_and_counter_decode() {
        assert_eq!(BoardFamily::from_firmware_code("EF535M V02.09"), BoardFamily::RenesasRL78);
        assert_eq!(BoardFamily::from_firmware_code("EF536M V01.12"), BoardFamily::CommercialDualTb);
        assert_eq!(BoardFamily::from_firmware_code("EF518M V01.25"), BoardFamily::ModernDomestic);
        assert_eq!(BoardFamily::from_firmware_code("EF509M V01.26"), BoardFamily::TopTronic8Bit);

        assert_eq!(BoardFamily::CommercialDualTb.max_words(), 1024);
        assert_eq!(BoardFamily::TopTronic8Bit.max_words(), 256);

        // 32-bit big-endian counter: (0x0002 << 16) | 0x0010 = 131088
        assert_eq!(BoardFamily::decode_counter_32bit(0x0002, 0x0010), 131088);
    }

    #[test]
    fn test_smart_connect_frame_builders() {
        let frame = SmartConnectCipher::build_query_firmware_frame(0x20);
        assert_eq!(frame[0], 0x26); // '&'
        assert!(frame.ends_with(b"\r\n"));

        let blk_frame = SmartConnectCipher::build_read_block_frame(0x0180, 16, AddressingMode::FourDigit, 0x20);
        assert_eq!(blk_frame[0], 0x26);
        assert!(blk_frame.ends_with(b"\r\n"));
    }

    #[test]
    fn test_cs_code_checksum_formatting() {
        let cmd = JuraProtocol::format_command(&JuraCommand::ReadCodeChecksum).unwrap();
        assert_eq!(cmd, "CS:\r\n");
        let cmd_disp = JuraProtocol::format_command(&JuraCommand::ReadDisplayCodeChecksum).unwrap();
        assert_eq!(cmd_disp, "CS$:\r\n");
    }

    #[test]
    fn test_parse_cs_response_optical_bean_sensor() {
        // Covered / beans present: slice [39:43] == 0000 -> 0 counts, beans_ok = true
        let cs_full = "cs:03C0300E5000000000000000000000000000000006D00006";
        let frame_full = JuraProtocol::parse_cs_response(cs_full).unwrap();
        assert_eq!(frame_full.coffee_temp_raw, 0x03C0);
        assert_eq!(frame_full.rotary_pos, 3);
        assert_eq!(frame_full.bu_pos_raw, 0x00E5);
        assert_eq!(frame_full.bean_photodiode_raw, 0x0000);
        assert_eq!(frame_full.bean_photodiode_adc, 0);
        assert!(frame_full.beans_ok);
        assert_eq!(frame_full.flowmeter_pulses, 0x06D0);
        assert_eq!(frame_full.model_tag, 0x0006);

        // Uncovered / empty hopper: slice [39:43] == 3FF0 -> 1023 counts, beans_ok = false
        let cs_empty = "cs:03C0300E50000000000000000000000000003FF006D00006";
        let frame_empty = JuraProtocol::parse_cs_response(cs_empty).unwrap();
        assert_eq!(frame_empty.bean_photodiode_raw, 0x3FF0);
        assert_eq!(frame_empty.bean_photodiode_adc, 1023);
        assert!(!frame_empty.beans_ok);
    }

    #[test]
    fn test_commercial_hopper_state_evaluation() {
        assert!(!evaluate_commercial_hopper_state(false, 0x0000));
        assert!(!evaluate_commercial_hopper_state(true, 0x3FF0));
        assert!(evaluate_commercial_hopper_state(true, 0x0000));
    }

    #[test]
    fn test_wire_bytes_and_scalar_decoders() {
        let payload = b"\x26TY:\r\n";
        let encoded = JuraProtocol::encode_wire_bytes(payload);
        assert_eq!(encoded.len(), payload.len() * 4);
        let mut with_tail = encoded.clone();
        with_tail.extend_from_slice(&[0xDB, 0xDF]);
        let (decoded, rem) = JuraProtocol::decode_wire_bytes(&with_tail);
        assert_eq!(decoded, payload);
        assert_eq!(rem, vec![0xDB, 0xDF]);

        assert_eq!(decode_jura_temperature_word(0x03C4), Some(96.4));
        assert_eq!(decode_jura_temperature_word(0x0802), None);
        assert_eq!(decode_jura_temperature_word(92), Some(92.0));

        // 2024-02-29 => ((34 << 9) | (2 << 5) | 29)
        let leap_word = ((2024u16 - 1990) << 9) | (2 << 5) | 29;
        assert_eq!(decode_jura_date_word(leap_word), Some((2024, 2, 29)));
        let bad_date = ((2023u16 - 1990) << 9) | (2 << 5) | 29;
        assert_eq!(decode_jura_date_word(bad_date), None);
        assert_eq!(decode_jura_date_word(0xFFFF), None);
    }

    #[test]
    fn test_smart_connect_build_and_decode_frame_roundtrip() {
        for &key in &[0x20u8, 0x2A, 0x30, 0x00, 0x0A, 0x0D, 0x1B, 0x26] {
            let frame = SmartConnectCipher::build_frame(b"@TR:32,00", key);
            assert_eq!(frame[0], 0x26);
            assert!(frame.ends_with(b"\r\n"));
            let decoded = SmartConnectCipher::decode_frame(&frame).expect("valid decoded frame");
            assert_eq!(decoded, "@TR:32,00\r\n");

            // Also verify build_read_block_frame formats @TR:32,{bank:02X}\r\n
            let blk_frame = SmartConnectCipher::build_read_block_frame(0x05, 4, AddressingMode::FourDigit, key);
            let blk_decoded = SmartConnectCipher::decode_frame(&blk_frame).expect("valid block frame");
            assert_eq!(blk_decoded, "@TR:32,05\r\n");
        }
        assert!(SmartConnectCipher::decode_frame(b"invalid").is_none());
        assert!(SmartConnectCipher::decode_frame(b"&\r\n").is_none());
    }

    #[test]
    fn test_non_ascii_utf8_does_not_panic_in_parsers() {
        let non_ascii_rt = format!("rt:{}", "€".repeat(30));
        assert!(JuraProtocol::parse_rt_response(&non_ascii_rt).is_err());

        let non_ascii_as = "as:€€€€,€€€€";
        assert!(JuraProtocol::parse_as_response(non_ascii_as).is_err());

        let non_ascii_cs = format!("cs:{}", "€".repeat(20));
        assert!(JuraProtocol::parse_cs_response(&non_ascii_cs).is_err());
    }
}
