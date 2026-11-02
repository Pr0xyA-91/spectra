//! Physical UART Serial Transport for Hardware Diagnostics

use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio_serial::{SerialPortBuilderExt, SerialStream};

use crate::{BoxFuture, HalError, HalResult, Transport};

/// Configuration parameters for native RS232 / USB-UART serial transport.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SerialConfig {
    /// Filesystem path to the serial port device (e.g. `"/dev/ttyUSB0"`).
    pub port_path: String,
    /// Baud rate (default `9600` for Jura, `115200` for Jetinno/Android).
    pub baud_rate: u32,
    /// Default read/write timeout.
    pub timeout: Duration,
    /// Optional default inter-byte pacing delay (e.g. 8ms for Jura 4-byte carrier).
    pub inter_byte_delay: Option<Duration>,
}

impl Default for SerialConfig {
    fn default() -> Self {
        Self {
            port_path: "/dev/ttyUSB0".to_string(),
            baud_rate: 9600,
            timeout: Duration::from_millis(1000),
            inter_byte_delay: Some(Duration::from_millis(8)),
        }
    }
}

/// Native serial transport implementation using `tokio-serial`.
pub struct SerialTransport {
    config: SerialConfig,
    stream: SerialStream,
}

impl SerialTransport {
    /// Opens the serial port in 8N1 raw mode with asynchronous I/O.
    pub fn open(config: SerialConfig) -> HalResult<Self> {
        let stream = tokio_serial::new(&config.port_path, config.baud_rate)
            .data_bits(tokio_serial::DataBits::Eight)
            .parity(tokio_serial::Parity::None)
            .stop_bits(tokio_serial::StopBits::One)
            .flow_control(tokio_serial::FlowControl::None)
            .timeout(config.timeout)
            .open_native_async()
            .map_err(|e| HalError::HardwareFault(format!("Failed to open serial port {}: {e}", config.port_path)))?;

        Ok(Self { config, stream })
    }

    /// Enumerates all available serial port device paths on the host system.
    pub fn list_ports() -> HalResult<Vec<String>> {
        let ports = tokio_serial::available_ports()
            .map_err(|e| HalError::HardwareFault(format!("Failed to list serial ports: {e}")))?;
        Ok(ports.into_iter().map(|p| p.port_name).collect())
    }

    /// Updates the inter-byte pacing delay fluently.
    pub fn with_inter_byte_delay(mut self, delay: Option<Duration>) -> Self {
        self.config.inter_byte_delay = delay;
        self
    }

    /// Updates the inter-byte pacing delay in-place.
    pub fn set_inter_byte_delay(&mut self, delay: Option<Duration>) {
        self.config.inter_byte_delay = delay;
    }

    /// Wraps an existing `SerialStream`.
    pub fn from_stream(config: SerialConfig, stream: SerialStream) -> Self {
        Self { config, stream }
    }

    /// Returns a reference to the serial configuration.
    pub fn config(&self) -> &SerialConfig {
        &self.config
    }

    /// Returns an immutable reference to the underlying `SerialStream`.
    pub fn stream(&self) -> &SerialStream {
        &self.stream
    }

    /// Returns a mutable reference to the underlying `SerialStream`.
    pub fn stream_mut(&mut self) -> &mut SerialStream {
        &mut self.stream
    }
}

impl Transport for SerialTransport {
    fn write_raw<'a>(
        &'a mut self,
        payload: &'a [u8],
        inter_byte_delay: Option<Duration>,
    ) -> BoxFuture<'a, HalResult<()>> {
        Box::pin(async move {
            let delay_opt = inter_byte_delay.or(self.config.inter_byte_delay);
            if let Some(delay) = delay_opt {
                if !delay.is_zero() {
                    for (i, &b) in payload.iter().enumerate() {
                        self.stream.write_all(&[b]).await?;
                        self.stream.flush().await?;
                        if i + 1 < payload.len() {
                            tokio::time::sleep(delay).await;
                        }
                    }
                    return Ok(());
                }
            }

            self.stream.write_all(payload).await?;
            self.stream.flush().await?;
            Ok(())
        })
    }

    fn read_raw<'a>(
        &'a mut self,
        buf: &'a mut [u8],
        timeout: Duration,
    ) -> BoxFuture<'a, HalResult<usize>> {
        Box::pin(async move {
            let res = tokio::time::timeout(timeout, self.stream.read(buf)).await;
            match res {
                Err(_) => Err(HalError::Timeout(timeout)),
                Ok(Err(e)) => Err(HalError::Io(e)),
                Ok(Ok(0)) => Err(HalError::HardwareFault("Serial port closed (EOF)".to_string())),
                Ok(Ok(n)) => Ok(n),
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_serial_config_defaults() {
        let cfg = SerialConfig::default();
        assert_eq!(cfg.port_path, "/dev/ttyUSB0");
        assert_eq!(cfg.baud_rate, 9600);
        assert_eq!(cfg.inter_byte_delay, Some(Duration::from_millis(8)));

        // Verify list_ports does not panic on host system
        let ports = SerialTransport::list_ports();
        assert!(ports.is_ok());
    }
}
