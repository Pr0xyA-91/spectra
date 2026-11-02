//! ADB Serial Bridge Transport for Commercial Android Coffee Machine SBCs
//!
//! # Hardware Safety & Galvanic Isolation Warning
//!
//! **CRITICAL HARDWARE SAFETY NOTICE**:
//! While the Android Debug Bridge (ADB) protocol provides reliable, framed transport over
//! USB OTG, many commercial Android coffee machine Single Board Computers (SBCs) (e.g.,
//! Allwinner A20/A64, Rockchip RK3288/RK3399, MediaTek MT8167/MT8168 found in Jura, Jetinno,
//! Bianchi, Schaerer, and Franke automated machines) share a **non-isolated common ground**
//! between the 5V logic/USB bus and the 24V/Mains-referenced VMC (Vehicle/Vending Management Controller)
//! or microcontroller power board.
//!
//! When connecting an external engineering workstation or diagnostics adapter via USB OTG/ADB:
//! 1. **Galvanic Isolation**: Always insert an inline full-speed/high-speed USB isolator
//!    (such as Analog Devices ADuM3160, ADuM4160, or ADuM4165) between the workstation and the
//!    machine's USB OTG port. Ground loops and switching transients from mains heaters, 230V solenoid
//!    valves, and grinder motor inductors can backfeed into the host USB controller, causing
//!    permanent silicon destruction or dangerous potential shifts.
//! 2. **UART TX Bus Contention**: Commercial coffee machine Android HMIs continuously run proprietary
//!    vendor APKs (e.g. `com.jura.app`, `com.jetinno.hmi`) that hold open the hardware serial port
//!    (e.g., `/dev/ttyS1`, `/dev/ttyMT0`). Attempting to read or write concurrently will produce
//!    framing collisions and garbled telemetry. Before bridging, stop or freeze the vendor HMI APK
//!    via `am force-stop <package_name>` or `kill` before taking control of the hardware UART.

use std::net::SocketAddr;
use std::path::PathBuf;
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};

use crate::{BoxFuture, HalError, HalResult, Transport};

/// Target socket endpoint on the local host used for ADB port forwarding.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AdbSocketEndpoint {
    /// Local TCP port forwarding (`tcp:<port>`).
    Tcp(SocketAddr),
    /// Local Unix domain socket path forwarding (`localfilesystem:<path>`).
    Unix(PathBuf),
}

impl AdbSocketEndpoint {
    /// Formats the endpoint specification for `adb forward <local> <remote>`.
    pub fn to_adb_local_spec(&self) -> String {
        match self {
            Self::Tcp(addr) => format!("tcp:{}", addr.port()),
            Self::Unix(path) => format!("localfilesystem:{}", path.display()),
        }
    }
}

/// Configuration parameters for establishing an ADB serial port bridge.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdbBridgeConfig {
    /// Optional specific Android device serial (passed as `adb -s <serial>`).
    pub device_serial: Option<String>,
    /// Linux TTY device node on target Android SBC (e.g. `"/dev/ttyS1"`, `"/dev/ttyMT0"`).
    pub tty_path: String,
    /// Baud rate for hardware UART (typically `115200` or `9600`).
    pub baud_rate: u32,
    /// Local forwarding endpoint (TCP or Unix socket).
    pub endpoint: AdbSocketEndpoint,
    /// Remote socket specification on the Android SBC (e.g. `"localabstract:spectra_uart"`).
    pub remote_forward_spec: String,
    /// Timeout for executing ADB commands and initial socket connection.
    pub connect_timeout: Duration,
}

impl Default for AdbBridgeConfig {
    fn default() -> Self {
        Self {
            device_serial: None,
            tty_path: "/dev/ttyS1".to_string(),
            baud_rate: 115200,
            endpoint: AdbSocketEndpoint::Tcp(SocketAddr::from(([127, 0, 0, 1], 9999))),
            remote_forward_spec: "localabstract:spectra_uart".to_string(),
            connect_timeout: Duration::from_secs(3),
        }
    }
}

/// Dynamic stream wrapper for either TCP or Unix domain socket ADB tunnels.
#[derive(Debug)]
pub enum AdbStream {
    Tcp(tokio::net::TcpStream),
    Unix(tokio::net::UnixStream),
}

impl AdbStream {
    /// Asynchronously reads bytes into `buf`, returning the number of bytes read.
    pub async fn read_buf(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        match self {
            Self::Tcp(s) => s.read(buf).await,
            Self::Unix(s) => s.read(buf).await,
        }
    }

    /// Asynchronously writes the entire slice `buf` into the stream.
    pub async fn write_all_buf(&mut self, buf: &[u8]) -> std::io::Result<()> {
        match self {
            Self::Tcp(s) => s.write_all(buf).await,
            Self::Unix(s) => s.write_all(buf).await,
        }
    }

    /// Asynchronously flushes any buffered data in the underlying stream.
    pub async fn flush_buf(&mut self) -> std::io::Result<()> {
        match self {
            Self::Tcp(s) => s.flush().await,
            Self::Unix(s) => s.flush().await,
        }
    }
}

/// Hardware serial bridge communicating with an Android SBC via ADB forward and socket tunnel.
#[derive(Debug)]
pub struct AdbSerialBridge {
    config: AdbBridgeConfig,
    stream: AdbStream,
}

impl AdbSerialBridge {
    /// Validates that a TTY device path is well-formed and safe against shell injection.
    ///
    /// Ensures `tty_path` begins with `"/dev/tty"` and that all following characters
    /// are strictly ASCII alphanumeric, `_`, `-`, or `/`.
    pub fn validate_tty_path(tty_path: &str) -> HalResult<()> {
        if !tty_path.starts_with("/dev/tty") {
            return Err(HalError::HardwareFault(format!(
                "Invalid TTY path: must start with '/dev/tty' (got: {tty_path})"
            )));
        }
        let remainder = &tty_path["/dev/tty".len()..];
        if remainder.is_empty()
            || !remainder
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '/')
        {
            return Err(HalError::HardwareFault(format!(
                "Invalid TTY path: device suffix must be non-empty and ASCII alphanumeric, '_', '-', or '/' (got: {tty_path})"
            )));
        }
        Ok(())
    }

    /// Builds the `stty` shell configuration command string for the target Android SBC.
    pub fn build_stty_command(&self) -> HalResult<String> {
        Self::validate_tty_path(&self.config.tty_path)?;
        Ok(format!(
            "stty -F {} {} cs8 -parenb -cstopb raw -echo -echoe -echok",
            self.config.tty_path, self.config.baud_rate
        ))
    }

    /// Constructs the CLI arguments for `adb forward`.
    pub fn build_adb_forward_args(&self) -> Vec<String> {
        let local_spec = self.config.endpoint.to_adb_local_spec();
        let mut args = Vec::with_capacity(5);
        if let Some(ref serial) = self.config.device_serial {
            args.push("-s".to_string());
            args.push(serial.clone());
        }
        args.push("forward".to_string());
        args.push(local_spec);
        args.push(self.config.remote_forward_spec.clone());
        args
    }

    /// Configures the remote serial port via `adb shell stty`, sets up `adb forward`,
    /// and establishes a socket connection to the bridged endpoint.
    pub async fn connect(config: AdbBridgeConfig) -> HalResult<Self> {
        Self::validate_tty_path(&config.tty_path)?;

        let stty_cmd = format!(
            "stty -F {} {} cs8 -parenb -cstopb raw -echo -echoe -echok",
            config.tty_path, config.baud_rate
        );

        // 1. Configure serial port mode on remote Android target
        let mut stty_proc = tokio::process::Command::new("adb");
        if let Some(ref serial) = config.device_serial {
            stty_proc.arg("-s").arg(serial);
        }
        stty_proc.arg("shell").arg(&stty_cmd);

        let stty_output = tokio::time::timeout(config.connect_timeout, stty_proc.output())
            .await
            .map_err(|_| HalError::Timeout(config.connect_timeout))?
            .map_err(|e| HalError::HardwareFault(format!("Failed to execute adb shell stty: {e}")))?;

        if !stty_output.status.success() {
            let stderr = String::from_utf8_lossy(&stty_output.stderr);
            return Err(HalError::HardwareFault(format!(
                "adb shell stty failed with exit code {:?}: {stderr}",
                stty_output.status.code()
            )));
        }

        // 2. Setup adb forward tunnel
        let local_spec = config.endpoint.to_adb_local_spec();
        let mut fwd_proc = tokio::process::Command::new("adb");
        if let Some(ref serial) = config.device_serial {
            fwd_proc.arg("-s").arg(serial);
        }
        fwd_proc
            .arg("forward")
            .arg(&local_spec)
            .arg(&config.remote_forward_spec);

        let fwd_output = tokio::time::timeout(config.connect_timeout, fwd_proc.output())
            .await
            .map_err(|_| HalError::Timeout(config.connect_timeout))?
            .map_err(|e| HalError::HardwareFault(format!("Failed to execute adb forward: {e}")))?;

        if !fwd_output.status.success() {
            let stderr = String::from_utf8_lossy(&fwd_output.stderr);
            return Err(HalError::HardwareFault(format!(
                "adb forward failed with exit code {:?}: {stderr}",
                fwd_output.status.code()
            )));
        }

        // 3. Connect to the local forwarded socket endpoint
        let stream = match &config.endpoint {
            AdbSocketEndpoint::Tcp(addr) => {
                let s = tokio::time::timeout(config.connect_timeout, tokio::net::TcpStream::connect(addr))
                    .await
                    .map_err(|_| HalError::Timeout(config.connect_timeout))?
                    .map_err(HalError::Io)?;
                AdbStream::Tcp(s)
            }
            AdbSocketEndpoint::Unix(path) => {
                let s = tokio::time::timeout(config.connect_timeout, tokio::net::UnixStream::connect(path))
                    .await
                    .map_err(|_| HalError::Timeout(config.connect_timeout))?
                    .map_err(HalError::Io)?;
                AdbStream::Unix(s)
            }
        };

        Ok(Self { config, stream })
    }

    /// Wraps an existing, already connected `AdbStream` with the provided configuration.
    pub fn from_stream(config: AdbBridgeConfig, stream: AdbStream) -> HalResult<Self> {
        Self::validate_tty_path(&config.tty_path)?;
        Ok(Self { config, stream })
    }

    /// Returns a reference to the active bridge configuration.
    pub fn config(&self) -> &AdbBridgeConfig {
        &self.config
    }

    /// Returns an immutable reference to the underlying stream.
    pub fn stream(&self) -> &AdbStream {
        &self.stream
    }

    /// Returns a mutable reference to the underlying stream.
    pub fn stream_mut(&mut self) -> &mut AdbStream {
        &mut self.stream
    }
}

impl Transport for AdbSerialBridge {
    fn write_raw<'a>(
        &'a mut self,
        payload: &'a [u8],
        inter_byte_delay: Option<Duration>,
    ) -> BoxFuture<'a, HalResult<()>> {
        Box::pin(async move {
            if let Some(delay) = inter_byte_delay {
                if !delay.is_zero() {
                    for (i, &b) in payload.iter().enumerate() {
                        self.stream.write_all_buf(&[b]).await?;
                        self.stream.flush_buf().await?;
                        if i + 1 < payload.len() {
                            tokio::time::sleep(delay).await;
                        }
                    }
                    return Ok(());
                }
            }

            self.stream.write_all_buf(payload).await?;
            self.stream.flush_buf().await?;
            Ok(())
        })
    }

    fn read_raw<'a>(
        &'a mut self,
        buf: &'a mut [u8],
        timeout: Duration,
    ) -> BoxFuture<'a, HalResult<usize>> {
        Box::pin(async move {
            let res = tokio::time::timeout(timeout, self.stream.read_buf(buf)).await;
            match res {
                Err(_) => Err(HalError::Timeout(timeout)),
                Ok(Err(e)) => Err(HalError::Io(e)),
                Ok(Ok(0)) => Err(HalError::HardwareFault(
                    "ADB socket bridge closed by remote target (EOF)".to_string(),
                )),
                Ok(Ok(n)) => Ok(n),
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_validate_tty_path_safety() {
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyS1").is_ok());
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyMT0").is_ok());
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyUSB0").is_ok());
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyAMA0").is_ok());

        // Rejection of shell injection attempts
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyS1; reboot").is_err());
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyS1 && rm -rf /").is_err());
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyS1 | cat").is_err());
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyS1`whoami`").is_err());
        assert!(AdbSerialBridge::validate_tty_path("/dev/ttyS1$(whoami)").is_err());

        // Rejection of invalid paths
        assert!(AdbSerialBridge::validate_tty_path("/etc/passwd").is_err());
        assert!(AdbSerialBridge::validate_tty_path("/dev/pts/0").is_err());
        assert!(AdbSerialBridge::validate_tty_path("/dev/tty").is_err());
        assert!(AdbSerialBridge::validate_tty_path("").is_err());
    }

    #[tokio::test]
    async fn test_build_stty_command() {
        let config = AdbBridgeConfig {
            device_serial: None,
            tty_path: "/dev/ttyS1".to_string(),
            baud_rate: 115200,
            endpoint: AdbSocketEndpoint::Tcp(SocketAddr::from(([127, 0, 0, 1], 9999))),
            remote_forward_spec: "localabstract:spectra_uart".to_string(),
            connect_timeout: Duration::from_secs(1),
        };
        let (client, _server) = tokio::net::UnixStream::pair().expect("unix stream pair");
        let bridge = AdbSerialBridge::from_stream(config, AdbStream::Unix(client))
            .expect("from_stream failed");

        let cmd = bridge.build_stty_command().expect("build stty command");
        assert_eq!(
            cmd,
            "stty -F /dev/ttyS1 115200 cs8 -parenb -cstopb raw -echo -echoe -echok"
        );
    }

    #[tokio::test]
    async fn test_build_adb_forward_args() {
        // With device serial and TCP endpoint
        let config_tcp = AdbBridgeConfig {
            device_serial: Some("emulator-5554".to_string()),
            tty_path: "/dev/ttyMT0".to_string(),
            baud_rate: 9600,
            endpoint: AdbSocketEndpoint::Tcp(SocketAddr::from(([127, 0, 0, 1], 8088))),
            remote_forward_spec: "localabstract:coffee_vmc".to_string(),
            connect_timeout: Duration::from_secs(2),
        };
        let (client1, _) = tokio::net::UnixStream::pair().expect("unix stream pair");
        let bridge_tcp = AdbSerialBridge::from_stream(config_tcp, AdbStream::Unix(client1))
            .expect("from_stream failed");

        let args_tcp = bridge_tcp.build_adb_forward_args();
        assert_eq!(
            args_tcp,
            vec![
                "-s",
                "emulator-5554",
                "forward",
                "tcp:8088",
                "localabstract:coffee_vmc"
            ]
        );

        // Without device serial and Unix socket endpoint
        let config_unix = AdbBridgeConfig {
            device_serial: None,
            tty_path: "/dev/ttyUSB0".to_string(),
            baud_rate: 115200,
            endpoint: AdbSocketEndpoint::Unix(PathBuf::from("/tmp/spectra_bridge.sock")),
            remote_forward_spec: "localabstract:spectra_uart".to_string(),
            connect_timeout: Duration::from_secs(2),
        };
        let (client2, _) = tokio::net::UnixStream::pair().expect("unix stream pair");
        let bridge_unix = AdbSerialBridge::from_stream(config_unix, AdbStream::Unix(client2))
            .expect("from_stream failed");

        let args_unix = bridge_unix.build_adb_forward_args();
        assert_eq!(
            args_unix,
            vec![
                "forward",
                "localfilesystem:/tmp/spectra_bridge.sock",
                "localabstract:spectra_uart"
            ]
        );
    }

    #[tokio::test]
    async fn test_adb_stream_transport_read_write_timeout_eof() {
        let (client, mut server) = tokio::net::UnixStream::pair().expect("unix stream pair");

        let config = AdbBridgeConfig {
            device_serial: None,
            tty_path: "/dev/ttyS1".to_string(),
            baud_rate: 115200,
            endpoint: AdbSocketEndpoint::Unix(PathBuf::from("/tmp/dummy.sock")),
            remote_forward_spec: "localabstract:spectra_uart".to_string(),
            connect_timeout: Duration::from_secs(1),
        };

        let mut bridge = AdbSerialBridge::from_stream(config, AdbStream::Unix(client))
            .expect("from_stream failed");

        // Test write_raw with inter-byte delay
        let payload = b"AN:01\r\n";
        let write_fut = bridge.write_raw(payload, Some(Duration::from_millis(2)));
        let server_read_fut = async {
            let mut buf = [0u8; 7];
            server.read_exact(&mut buf).await.expect("server read");
            buf
        };

        let (_, received) = tokio::join!(write_fut, server_read_fut);
        assert_eq!(&received, payload);

        // Test read_raw success
        server.write_all(b"OK:01\r\n").await.expect("server write");
        let mut read_buf = [0u8; 16];
        let n = bridge
            .read_raw(&mut read_buf, Duration::from_millis(100))
            .await
            .expect("read_raw failed");
        assert_eq!(&read_buf[..n], b"OK:01\r\n");

        // Test read_raw timeout when no bytes arrive
        let mut timeout_buf = [0u8; 16];
        let err = bridge
            .read_raw(&mut timeout_buf, Duration::from_millis(20))
            .await
            .expect_err("expected timeout");
        assert!(matches!(err, HalError::Timeout(_)));

        // Test read_raw EOF detection when remote socket closes
        drop(server);
        let mut eof_buf = [0u8; 16];
        let eof_err = bridge
            .read_raw(&mut eof_buf, Duration::from_millis(100))
            .await
            .expect_err("expected EOF hardware fault");
        assert!(matches!(eof_err, HalError::HardwareFault(_)));
    }
}
