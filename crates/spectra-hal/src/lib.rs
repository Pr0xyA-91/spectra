use std::future::Future;
use std::pin::Pin;
use std::time::Duration;
use thiserror::Error;

pub type BoxFuture<'a, T> = Pin<Box<dyn Future<Output = T> + Send + 'a>>;

#[derive(Error, Debug)]
pub enum HalError {
    #[error("Transport I/O failure: {0}")]
    Io(#[from] std::io::Error),
    #[error("Frame timeout after {0:?}")]
    Timeout(Duration),
    #[error("Framing or checksum mismatch: expected {expected:#04x}, got {actual:#04x}")]
    IntegrityError { expected: u16, actual: u16 },
    #[error("Invalid bit-slice encoding in byte {index}: {raw:#04x}")]
    EncodingError { index: usize, raw: u8 },
    #[error("Hardware or bus isolation fault: {0}")]
    HardwareFault(String),
}

pub type HalResult<T> = Result<T, HalError>;

/// Physical transport link: USB-UART, ADB Socket Bridge, USB Bulk, or Linux RNDIS.
/// Dyn-compatible interface allowing dynamic dispatch via `Box<dyn Transport>`.
pub trait Transport: Send + Sync {
    fn write_raw<'a>(
        &'a mut self,
        payload: &'a [u8],
        inter_byte_delay: Option<Duration>,
    ) -> BoxFuture<'a, HalResult<()>>;

    fn read_raw<'a>(
        &'a mut self,
        buf: &'a mut [u8],
        timeout: Duration,
    ) -> BoxFuture<'a, HalResult<usize>>;
}

impl<T: ?Sized + Transport> Transport for Box<T> {
    fn write_raw<'a>(
        &'a mut self,
        payload: &'a [u8],
        inter_byte_delay: Option<Duration>,
    ) -> BoxFuture<'a, HalResult<()>> {
        (**self).write_raw(payload, inter_byte_delay)
    }

    fn read_raw<'a>(
        &'a mut self,
        buf: &'a mut [u8],
        timeout: Duration,
    ) -> BoxFuture<'a, HalResult<usize>> {
        (**self).read_raw(buf, timeout)
    }
}

/// Machine-specific framing & obfuscation layer (e.g., Jura 4-byte, MDB 9-bit, Jetinno UART)
pub trait MachineProtocol: Send + Sync {
    type Command;
    type TelemetryFrame;

    fn encode_command(&self, cmd: &Self::Command) -> HalResult<Vec<u8>>;
    fn decode_frame(&self, raw: &[u8]) -> HalResult<Self::TelemetryFrame>;
}

pub mod adb;
pub use adb::{AdbBridgeConfig, AdbSerialBridge, AdbSocketEndpoint, AdbStream};

#[cfg(feature = "serial")]
pub mod serial;
#[cfg(feature = "serial")]
pub use serial::{SerialConfig, SerialTransport};

/// Jura 4-Byte Obfuscation Primitives (9600 8N1, ~8 ms inter-byte delay)
pub mod jura_codec {
    use super::HalResult;

    const BASE_MASK: u8 = 0b0101_1011; // 0x5B base carrier byte

    /// Encodes 1 ASCII byte into 4 UART wire bytes (2 payload bits per wire byte at bit 2 & bit 5)
    pub fn encode_byte(byte: u8) -> [u8; 4] {
        let mut out = [BASE_MASK; 4];
        for i in 0..4 {
            let b0 = (byte >> (i * 2)) & 0x01;
            let b1 = (byte >> (i * 2 + 1)) & 0x01;
            out[i] = (BASE_MASK & !((1 << 2) | (1 << 5))) | (b0 << 2) | (b1 << 5);
        }
        out
    }

    /// Decodes 4 UART wire bytes back into 1 ASCII byte
    pub fn decode_quad(quad: &[u8; 4]) -> HalResult<u8> {
        let mut out: u8 = 0;
        for (i, &wire) in quad.iter().enumerate() {
            let b0 = (wire >> 2) & 0x01;
            let b1 = (wire >> 5) & 0x01;
            out |= (b0 << (i * 2)) | (b1 << (i * 2 + 1));
        }
        Ok(out)
    }
}
