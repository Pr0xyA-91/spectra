#!/usr/bin/env python3
"""
Serial Communication Layer for Jura Coffee Machines
Supports:
- Auto-detection of USB-serial diagnostic adapters (/dev/ttyUSB*, /dev/ttyACM*)
- Native POSIX termios serial driver (zero external pip/pacman dependencies)
- Seamless fallback to pyserial if installed
- Direct plain-ASCII interrogation with optical loopback echo handling (Jura USB Scanner N 010)
- Built-in Mock / Demo device transceiver for offline testing
- Non-blocking select-based reads with accurate timeout management
- Precise inter-frame buffer draining and microcontroller settling delays
"""

import os
import glob
import time
import select
from typing import List, Optional

try:
    import termios
    import fcntl
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

try:
    import serial
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False

from jura_protocol import MockJuraMachine


def list_serial_ports() -> List[str]:
    """Discover available physical and virtual serial ports on Linux."""
    ports = []
    # High priority: USB adapters commonly used for Jura diagnostics (FTDI, CH340, CP210x)
    for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
        ports.extend(sorted(glob.glob(pattern)))
    # Virtual PTYs
    for pty_path in sorted(glob.glob("/dev/pts/[0-9]*")):
        ports.append(pty_path)
    # Hardware motherboard serials (usually low priority)
    for tty in sorted(glob.glob("/dev/ttyS[0-3]")):
        ports.append(tty)

    # Always provide Demo / Simulation option
    ports.append("DEMO / SIMULATION (Jura S8)")
    ports.append("DEMO / SIMULATION (Jura E8)")
    ports.append("DEMO / SIMULATION (Jura Z10)")
    return ports


class JuraSerialConnection:
    """Universal serial transceiver interface for Jura diagnostics."""

    def __init__(self, port_name: str, baudrate: int = 9600, timeout: float = 1.5):
        self.port_name = port_name
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_demo = "DEMO" in port_name.upper() or port_name.lower() in ("mock", "demo")
        self.mock_machine: Optional[MockJuraMachine] = None
        self.fd: Optional[int] = None
        self.py_serial = None
        self.is_open = False

        if self.is_demo:
            if "Z10" in port_name.upper():
                self.mock_machine = MockJuraMachine(model_ef="EF545 V01.20", model_name="Z10")
            elif "E8" in port_name.upper():
                self.mock_machine = MockJuraMachine(model_ef="EF1092 V01.05", model_name="E8")
            else:
                self.mock_machine = MockJuraMachine(model_ef="EF536M V02.01", model_name="S8")
            self.is_open = True
        else:
            self._open_hardware_port()

    def _open_hardware_port(self):
        if not os.path.exists(self.port_name):
            raise FileNotFoundError(f"Serial port {self.port_name} does not exist.")

        # Prefer native POSIX termios on Linux
        if HAS_TERMIOS:
            try:
                self.fd = os.open(self.port_name, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                attrs = termios.tcgetattr(self.fd)
                # iflag: Raw input, ignore break condition
                attrs[0] = termios.IGNBRK
                # oflag: Raw output
                attrs[1] = 0
                # cflag: CS8 (8 data bits), CREAD (enable receiver), CLOCAL (ignore modem control)
                attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                # lflag: Non-canonical, no echo, no signals
                attrs[3] = 0

                baud_constants = {
                    9600: termios.B9600,
                    19200: termios.B19200,
                    38400: termios.B38400,
                    57600: termios.B57600,
                    115200: termios.B115200,
                }
                baud = baud_constants.get(self.baudrate, termios.B9600)
                attrs[4] = baud
                attrs[5] = baud
                attrs[6][termios.VMIN] = 0
                attrs[6][termios.VTIME] = 0
                termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
                self.is_open = True
                return
            except Exception as e:
                if self.fd is not None:
                    os.close(self.fd)
                    self.fd = None
                if not HAS_PYSERIAL:
                    raise IOError(f"Failed to configure serial port {self.port_name}: {e}")

        # Fallback to pyserial
        if HAS_PYSERIAL:
            try:
                self.py_serial = serial.Serial(
                    port=self.port_name,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout
                )
                self.is_open = True
            except Exception as e:
                raise IOError(f"Failed to open {self.port_name} via pyserial: {e}")

    def write(self, data: bytes) -> int:
        """Write raw bytes to machine with inter-packet flushing."""
        if not self.is_open:
            raise IOError("Serial port is not open.")

        if self.is_demo:
            # Route directly to Mock device
            self._demo_reply_buffer = self.mock_machine.process_input(data)
            return len(data)

        if self.fd is not None:
            written = os.write(self.fd, data)
            # Drain output buffer
            termios.tcdrain(self.fd)
            return written

        if self.py_serial:
            written = self.py_serial.write(data)
            self.py_serial.flush()
            return written

        return 0

    def read(self, max_bytes: int = 2048, timeout_sec: Optional[float] = None) -> bytes:
        """Read incoming wire bytes with selectable timeout."""
        if not self.is_open:
            raise IOError("Serial port is not open.")

        t_out = timeout_sec if timeout_sec is not None else self.timeout

        if self.is_demo:
            # Simulate real UART transmission latency (~15 ms)
            time.sleep(0.015)
            buf = getattr(self, "_demo_reply_buffer", b"")
            self._demo_reply_buffer = b""
            return buf

        if self.fd is not None:
            rlist, _, _ = select.select([self.fd], [], [], t_out)
            if rlist:
                try:
                    return os.read(self.fd, max_bytes)
                except BlockingIOError:
                    return b""
            return b""

        if self.py_serial:
            if t_out != self.timeout:
                self.py_serial.timeout = t_out
            return self.py_serial.read(max_bytes)

        return b""

    def drain_rx(self):
        """Flush any pending or trailing bytes in hardware input buffers."""
        if self.is_demo:
            self._demo_reply_buffer = b""
            return
        time.sleep(0.04)
        if self.fd is not None:
            while select.select([self.fd], [], [], 0.04)[0]:
                try:
                    os.read(self.fd, 1024)
                except Exception:
                    break
        elif self.py_serial is not None:
            self.py_serial.reset_input_buffer()

    def query_ascii(self, cmd: str, timeout: float = 1.0) -> Optional[str]:
        """
        Send plain ASCII command terminated with CRLF, handling:
        1. Transceiver local echo reflection (e.g. Jura USB Scanner N 010)
        2. Clean line separation and partial chunk buffering
        3. Inter-command microcontroller settling delay
        """
        if not self.is_open:
            raise IOError("Serial port is not open.")

        cmd_clean = cmd.strip()

        if self.is_demo:
            time.sleep(0.02)
            if cmd_clean == "TY:":
                return f"ty:{self.mock_machine.model_ef}"
            elif cmd_clean == "IC:":
                return "ic:230A"
            elif cmd_clean == "RT:0000":
                return "rt:000010A747450000025F15F500000E1900A600266DFB00000000000000000000"
            elif cmd_clean == "RT:0010":
                return "rt:B0940000018700000001703A00000000000000000000000000000000000001FB"
            elif cmd_clean == "RT:0020":
                return "rt:00000640000100040414780A1E04A0280139004C0C0E1E020A0607082D64141E"
            elif cmd_clean == "RT:0030":
                return "rt:466000332EBE2996000000000000000000001E6F046E5028180F001401040276"
            elif cmd_clean == "RE:0030":
                return "re:4660"
            elif cmd_clean == "RE:0031":
                return "re:0033"
            elif cmd_clean == "RE:0032":
                return "re:2EBE"
            elif cmd_clean == "RE:0015":
                return "re:703A"
            elif cmd_clean == "RE:00DA":
                return "re:435A"
            elif cmd_clean == "RE:00DB":
                return "re:2F4C"
            elif cmd_clean == "RE:00DC":
                return "re:2D8C"
            elif cmd_clean == "RE:00E9":
                return "re:0000"
            elif cmd_clean == "RE:00EA":
                return "re:0007"
            elif cmd_clean == "RE:00C3":
                return "re:1E32"
            elif cmd_clean.startswith("RT:"):
                return "rt:0000000000000000000000000000000000000000000000000000000000000000"
            elif cmd_clean.startswith("RE:"):
                return "re:0000"
            return None

        self.drain_rx()
        tx_data = (cmd_clean + "\r\n").encode("ascii")
        self.write(tx_data)

        rx = bytearray()
        start = time.time()
        sent_raw = cmd_clean

        while time.time() - start < timeout:
            chunk = self.read(max_bytes=256, timeout_sec=0.05)
            if chunk:
                rx.extend(chunk)
                if b"\r\n" in rx:
                    lines = [l.strip().decode("latin1", errors="ignore") for l in rx.split(b"\r\n")]
                    complete_lines = lines[:-1]
                    replies = []
                    found_echo = False
                    for l in complete_lines:
                        # Echo is the exact command we transmitted
                        if not found_echo and l == sent_raw:
                            found_echo = True
                            continue
                        if l:
                            replies.append(l)
                    if replies:
                        # Give machine UART 40ms to settle before next command
                        time.sleep(0.04)
                        return replies[0]
            time.sleep(0.01)

        return None

    def close(self):
        """Close connection cleanly."""
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None
        if self.py_serial is not None:
            try:
                self.py_serial.close()
            except Exception:
                pass
            self.py_serial = None
        self.is_open = False
