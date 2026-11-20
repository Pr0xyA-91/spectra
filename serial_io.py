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
import re
import sys
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
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False

# Native Rust Core Acceleration Bridge (spectra_py)
try:
    import spectra_py as _rust_core
    HAS_RUST_CORE = True
except ImportError:
    _rust_core = None
    HAS_RUST_CORE = False

from jura_protocol import MockJuraMachine


def list_serial_ports() -> List[str]:
    """Discover available physical and virtual serial ports on Linux and Windows."""
    ports = []

    # Windows COM ports
    if sys.platform.startswith("win"):
        if HAS_PYSERIAL:
            try:
                for p in serial.tools.list_ports.comports():
                    desc = f" ({p.description})" if p.description and p.description != "n/a" else ""
                    ports.append(f"{p.device}{desc}")
            except Exception:
                pass
        if not ports:
            # Fallback scan via Windows Registry HKLM\HARDWARE\DEVICEMAP\SERIALCOMM
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                    i = 0
                    while True:
                        try:
                            _, port_val, _ = winreg.EnumValue(key, i)
                            if port_val and str(port_val) not in ports:
                                ports.append(str(port_val))
                            i += 1
                        except OSError:
                            break
                ports.sort()
            except Exception:
                pass
        if HAS_RUST_CORE and _rust_core is not None:
            try:
                existing_bases = {p.split()[0].upper() for p in ports}
                for r_port in _rust_core.list_serial_ports():
                    base = r_port.split()[0].upper()
                    if base.startswith("COM") and base not in existing_bases:
                        ports.append(r_port)
                        existing_bases.add(base)
            except Exception:
                pass
    else:
        # Linux / POSIX ports
        # High priority: USB adapters commonly used for Jura diagnostics (FTDI, CH340, CP210x)
        # Never enumerate /dev/pts/* (active user terminal PTYs) or phantom motherboard /dev/ttyS*
        for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
            ports.extend(sorted(glob.glob(pattern)))

        # Query native Rust hardware discovery if active (strictly USB/ACM adapters)
        if HAS_RUST_CORE and _rust_core is not None:
            try:
                for r_port in _rust_core.list_serial_ports():
                    if r_port not in ports and (r_port.startswith("/dev/ttyUSB") or r_port.startswith("/dev/ttyACM")):
                        ports.append(r_port)
            except Exception:
                pass

    # Always provide Demo / Simulation option
    ports.append("DEMO / SIMULATION (Jura Impressa XJ5)")
    ports.append("DEMO / SIMULATION (Jura Z6)")
    ports.append("DEMO / SIMULATION (Jura S8)")
    ports.append("DEMO / SIMULATION (Jura S8 Smart Connect)")
    ports.append("DEMO / SIMULATION (Jura WE8)")
    ports.append("DEMO / SIMULATION (Jura E8)")
    ports.append("DEMO / SIMULATION (Jura ENA 7)")
    ports.append("DEMO / SIMULATION (Jura Z10)")
    ports.append("DEMO / SIMULATION (Nivona NICR768)")
    ports.append("DEMO / SIMULATION (Lamanti-KL X680C)")
    ports.append("DEMO / SIMULATION (Lamanti-JN JL300)")
    return ports


_COM_PORT_PREFIX_RE = re.compile(r"^((?:\\\\\.\\)?COM\d{1,3})(?=\s|$)", re.IGNORECASE)


def normalize_port_name(port_name: str) -> str:
    """Normalize a serial port label by stripping descriptive suffixes from Windows COM ports."""
    if not isinstance(port_name, str):
        return ""
    stripped = port_name.strip()
    m = _COM_PORT_PREFIX_RE.match(stripped)
    if m:
        return m.group(1)
    return stripped


class JuraSerialConnection:
    """Universal serial transceiver interface for Jura diagnostics."""

    def __init__(self, port_name: str, baudrate: int = 9600, timeout: float = 1.5):
        raw_port = port_name if isinstance(port_name, str) else str(port_name or "")
        # Extract pure COM port if description is appended, e.g. "COM3 (USB-Serial)"
        clean_port = normalize_port_name(raw_port)
        self.port_name = clean_port
        self.raw_port_label = raw_port
        self.baudrate = baudrate
        self.timeout = timeout
        self._applied_timeout: Optional[float] = timeout
        self.is_demo = "DEMO" in raw_port.upper() or raw_port.lower() in ("mock", "demo")
        self.mock_machine: Optional[MockJuraMachine] = None
        self.fd: Optional[int] = None
        self.py_serial = None
        self.is_open = False
        self.wire_mode: Optional[str] = None
        self.encrypted_wire_mode: Optional[str] = None
        self._is_smart_connect: bool = "SMART CONNECT" in (port_name or "").upper()
        self.vendor: str = "jura"

        if self.is_demo:
            p_up = port_name.upper()
            if any(k in p_up for k in ("NIVONA", "NICR", "NIVO")):
                self.demo_vendor = "nivona"
            elif any(k in p_up for k in ("LAMANTI-KL", "X680", "KALERM", "E30", "E60", "K95")):
                self.demo_vendor = "lamanti-kl"
            elif any(k in p_up for k in ("LAMANTI-JN", "JL300", "JL500", "JETINNO", "JLTT")):
                self.demo_vendor = "lamanti-jn"
            else:
                self.demo_vendor = "jura"
            self.vendor = self.demo_vendor

            if "XJ5" in p_up:
                self.mock_machine = MockJuraMachine(model_ef="EF518M V02.20", model_name="IMPRESSA XJ5")
            elif "Z6" in p_up:
                self.mock_machine = MockJuraMachine(model_ef="EF540M V01.22", model_name="Z6")
            elif "Z10" in p_up:
                self.mock_machine = MockJuraMachine(model_ef="EF545 V01.20", model_name="Z10")
            elif "WE8" in p_up:
                self.mock_machine = MockJuraMachine(model_ef="EF533M V02.09", model_name="WE8")
            elif "E8" in p_up:
                self.mock_machine = MockJuraMachine(model_ef="EF1092 V01.05", model_name="E8")
            elif "D4" in port_name.upper():
                self.mock_machine = MockJuraMachine(model_ef="EF529M V01.02", model_name="D4")
            elif "A1" in p_up:
                self.mock_machine = MockJuraMachine(model_ef="EF509M V01.26", model_name="A1")
            elif "ENA 7" in p_up or "ENA7" in p_up or "13500" in p_up:
                self.mock_machine = MockJuraMachine(model_ef="EF634 V01.31", model_name="ENA 7")
            else:
                self.mock_machine = MockJuraMachine(model_ef="EF536M V02.01", model_name="S8")
            if self._is_smart_connect:
                self.wire_mode = "smart_connect"
            self._init_mock_eeprom()
            self.is_open = True
        else:
            self.demo_vendor = "hardware"
            self.vendor = "jura"
            self._open_hardware_port()

    def _init_mock_eeprom(self):
        """Initialize complete simulated EEPROM for offline demo & developer differential testing."""
        if "WE8" in self.port_name.upper():
            self._mock_eeprom = {i: 0x0000 for i in range(1024)}
            # Maintenance registers
            self._mock_eeprom[0x0007] = 2268  # Coffee system rinsing
            self._mock_eeprom[0x0008] = 74    # Cleaning
            self._mock_eeprom[0x0009] = 0     # Descaling
            self._mock_eeprom[0x0020] = 775   # Milk system rinsing
            self._mock_eeprom[0x0021] = 377   # Milk system cleaning
            self._mock_eeprom[0x0022] = 29    # Filter change
            # Article number 15420 (0x3C3C)
            self._mock_eeprom[0x007E] = 0x3C00
            self._mock_eeprom[0x007F] = 0x3C00
            # Cockpit percentages
            self._mock_eeprom[0x0162] = 0x0000  # Descaling 0%
            self._mock_eeprom[0x0163] = 0x1E1E  # Cleaning 30%
            self._mock_eeprom[0x01E1] = 0x000A  # Filter 10%
            # Beverage statistics
            self._mock_eeprom[0x017F] = 75    # Hot water for green tea
            self._mock_eeprom[0x0180] = 1450  # Espresso
            self._mock_eeprom[0x0181] = 137   # Ristretto
            self._mock_eeprom[0x0182] = 7233  # Coffee
            self._mock_eeprom[0x0183] = 117   # Flat white
            self._mock_eeprom[0x0184] = 390   # Cappuccino
            self._mock_eeprom[0x0185] = 50    # Latte macchiato
            self._mock_eeprom[0x0186] = 10    # Product with ground coffee
            self._mock_eeprom[0x0187] = 72    # Portion of milk
            self._mock_eeprom[0x0188] = 183   # Hot water
            self._mock_eeprom[0x0189] = 176   # 2 x Espresso
            self._mock_eeprom[0x018A] = 4     # 2 x Ristretto
            self._mock_eeprom[0x018B] = 20    # 2 x Coffee
            self._mock_eeprom[0x018C] = 5     # 2 x Special coffee
            self._mock_eeprom[0x018D] = 901   # Special coffee
            self._mock_eeprom[0x018E] = 31    # Macchiato
            self._mock_eeprom[0x018F] = 354   # Espresso doppio
            return

        if "A1" in self.port_name.upper():
            self._mock_eeprom = {i: 0x0000 for i in range(256)}
            self._mock_eeprom[0x0002] = 1954   # Single Coffee
            self._mock_eeprom[0x0004] = 2234   # Single Espresso
            self._mock_eeprom[0x0006] = 477    # Single Ristretto
            self._mock_eeprom[0x0007] = 4618   # Rinses
            self._mock_eeprom[0x0008] = 30     # Cleanings
            self._mock_eeprom[0x0009] = 7      # Descalings
            self._mock_eeprom[0x000A] = 10590  # Grinder operating seconds (2h 56m 30s)
            self._mock_eeprom[0x0010] = 8287   # Water dispensed (828.7 dl)
            self._mock_eeprom[0x0012] = 48     # Descaling agent (4.8 dl)
            self._mock_eeprom[0x0014] = 90     # Filter changes
            self._mock_eeprom[0x0015] = 5043   # Service counter (preparations since last service)
            self._mock_eeprom[0x0030] = 1002   # Appliance Number (0x03EA)
            self._mock_eeprom[0x0031] = 100    # Serial Word (0x0064)
            self._mock_eeprom[0x0032] = 14383  # Production Date: 15.01.2018 (0x382F)
            self._mock_eeprom[0x007E] = 0x3B00 # Article Number High byte (0x3B)
            self._mock_eeprom[0x007F] = 0x1D00 # Article Number Low byte (0x1D) -> 15133
            self._mock_eeprom[0x00C3] = 0x027C # Water Hardness (40 °dH)
            return

        if "D4" in self.port_name.upper():
            self._mock_eeprom = {i: 0x0000 for i in range(1024)}
            self._mock_eeprom[0x0007] = 15105  # Rinses
            self._mock_eeprom[0x0008] = 85     # Cleanings
            self._mock_eeprom[0x0009] = 30     # Descalings
            self._mock_eeprom[0x000A] = 28672  # Grinder operating seconds
            self._mock_eeprom[0x000E] = 1      # Filter changes
            self._mock_eeprom[0x0010] = 29074  # Water dispensed (dl)
            self._mock_eeprom[0x0011] = 14     # Water hardness (°dH)
            self._mock_eeprom[0x0012] = 143    # Descaling agent (dl)
            self._mock_eeprom[0x0015] = 11851  # Service counter
            self._mock_eeprom[0x0030] = 1003   # Appliance Number
            self._mock_eeprom[0x0031] = 1      # Serial Word
            self._mock_eeprom[0x0032] = 15407  # Production Date: 15.01.2020 (0x3C2F)
            self._mock_eeprom[0x0041] = 230    # BU Mill Target
            self._mock_eeprom[0x0047] = 1296   # BU Upper Limit
            self._mock_eeprom[0x0056] = 37     # BU Init count
            self._mock_eeprom[0x0330] = 2061   # Single Espresso
            self._mock_eeprom[0x0331] = 9755   # Single Coffee
            self._mock_eeprom[0x0332] = 2      # 2 Espressi
            self._mock_eeprom[0x0333] = 3      # 2 Coffee
            self._mock_eeprom[0x0334] = 7      # Hot water
            return

        if "ENA 7" in self.port_name.upper() or "ENA7" in self.port_name.upper() or "13500" in self.port_name.upper():
            self._mock_eeprom = {i: 0x0000 for i in range(512)}
            self._mock_eeprom[0x0000] = 603     # 1 Espresso
            self._mock_eeprom[0x0001] = 0       # 2 Espressi
            self._mock_eeprom[0x0002] = 10720   # 1 Coffee
            self._mock_eeprom[0x0003] = 7       # 2 Coffees
            self._mock_eeprom[0x0004] = 2167    # 1 Aroma-Boost
            self._mock_eeprom[0x0005] = 532     # Steam / Hot water valve cycles
            self._mock_eeprom[0x0006] = 236     # Ground coffee
            self._mock_eeprom[0x0007] = 10202   # Total Rinses
            self._mock_eeprom[0x0008] = 28      # Total Cleanings
            self._mock_eeprom[0x0009] = 3       # Total Descalings
            self._mock_eeprom[0x000A] = 30855   # Operating time of grinder (sec)
            self._mock_eeprom[0x000D] = 38      # Coffee water since last descaling (dl)
            self._mock_eeprom[0x000F] = 203     # Preps since last cleaning
            self._mock_eeprom[0x0010] = 25692   # Total coffee water incl. rinses (dl)
            self._mock_eeprom[0x0011] = 112     # Rinses since last cleaning
            self._mock_eeprom[0x0012] = 22      # Descaling agent used (dl)
            self._mock_eeprom[0x0015] = 1224    # Number of preparations since last intervention
            self._mock_eeprom[0x0016] = 56      # Preparations since cleaning alarm
            self._mock_eeprom[0x001B] = 3       # Milk / froth minutes
            self._mock_eeprom[0x001C] = 79      # Hot water minutes
            self._mock_eeprom[0x001E] = 4       # Hot water until previous descaling (min)
            self._mock_eeprom[0x001F] = 4244    # Coffee water until previous descaling (dl)
            self._mock_eeprom[0x0028] = 25      # History fault bitmask (0x0019)
            self._mock_eeprom[0x0030] = 1004    # Appliance number (0x03EC)
            self._mock_eeprom[0x0031] = 1       # Serial number / word
            self._mock_eeprom[0x0032] = 11311   # Date of production (15.1.2012, 0x2C2F)
            self._mock_eeprom[0x0036] = 3       # Amount through filter (dl)
            self._mock_eeprom[0x003D] = 20      # Water hardness (°dH)
            self._mock_eeprom[0x003E] = 300     # Auto off timeout (300 min = 5.0 h)
            self._mock_eeprom[0x0052] = 23      # Total filter changes
            self._mock_eeprom[0x0056] = 44      # BU initializations
            self._mock_eeprom[0x007E] = 0x3400  # Article Number High (0x34 -> 13500)
            self._mock_eeprom[0x007F] = 0xBC00  # Article Number Low (0xBC -> 13500)
            self._mock_eeprom[0x00C3] = 0x1464  # Water hardness 20 °dH (high byte 0x14)
            self._mock_eeprom[0x00D6] = 5522    # Total machine switch-on
            self._mock_eeprom[0x00DA] = 0x435A  # Country code 'CZ'
            self._mock_eeprom[0x00DB] = 11025   # SPDL Download Date (17.8.2011)
            self._mock_eeprom[0x00DC] = 10443   # SPDL Language Date (11.6.2010)
            return

        self._mock_eeprom = {i: 0x0000 for i in range(512)}
        # Block seeds with synthetic demo machine identity
        seeds = {
            0x0000: "000010A747450000025F15F500000E1900A600266DFB00000000000000000000",
            0x0010: "B0940000018700000001703A00000000000000000000000000000000000001FB",
            0x0020: "00520640000100040414780A1E04A0280B39000C0C0E1E020A0607082D64141E",
            0x0030: "03E80001302F2996000000000000000000001E6F046E5028180F001401040276",
            0x0040: "050C00E6010A02080222006A01D105107803400ADD78050F0A1200C81455145C"
        }
        for blk, hex_str in seeds.items():
            for i in range(16):
                w_hex = hex_str[i * 4: i * 4 + 4]
                self._mock_eeprom[blk + i] = int(w_hex, 16)

        # Pre-seed other known registers
        self._mock_eeprom[0x0045] = 0x0048
        self._mock_eeprom[0x0055] = 0x2801
        self._mock_eeprom[0x00C3] = 0x1E32
        self._mock_eeprom[0x00DA] = 0x435A
        self._mock_eeprom[0x00DB] = 0x2F4C
        self._mock_eeprom[0x00DC] = 0x2D8C
        self._mock_eeprom[0x00E9] = 0x0000
        self._mock_eeprom[0x00EA] = 0x0007
        self._mock_eeprom[0x0015] = 0x703A
        self._mock_eeprom[0x00B4] = 0x050A
        self._mock_eeprom[0x00B5] = 0x040A
        self._mock_eeprom[0x00B9] = 0x0050
        self._mock_eeprom[0x00BA] = 0x0078
        self._mock_eeprom[0x00BB] = 0x0096
        self._mock_eeprom[0x00A9] = 0x0102

    def set_mock_eeprom_word(self, addr: int, val: int):
        """Developer/testing utility to update a simulated EEPROM register."""
        if hasattr(self, "_mock_eeprom"):
            self._mock_eeprom[addr & 0x03FF] = val & 0xFFFF

    def get_mock_eeprom_word(self, addr: int) -> int:
        """Developer/testing utility to inspect a simulated EEPROM register."""
        if hasattr(self, "_mock_eeprom"):
            return self._mock_eeprom.get(addr & 0x03FF, 0)
        return 0

    def _open_hardware_port(self):
        is_windows = sys.platform.startswith("win") or self.port_name.upper().startswith(("COM", "\\\\.\\COM"))
        if not is_windows and not os.path.exists(self.port_name):
            raise FileNotFoundError(f"Serial port {self.port_name} does not exist.")

        # Prefer native POSIX termios on Linux
        if HAS_TERMIOS and not is_windows:
            try:
                self.fd = os.open(self.port_name, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                # Exclusive file lock to prevent multiple processes interleaving wire bytes
                lock_deadline = time.time() + 1.5
                locked = False
                while time.time() < lock_deadline:
                    try:
                        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                        break
                    except (BlockingIOError, IOError):
                        time.sleep(0.05)
                if not locked:
                    raise IOError(f"Serial port {self.port_name} is locked by another SPECTRA process.")

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
                    try:
                        os.close(self.fd)
                    except OSError:
                        pass
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
                self._applied_timeout = self.timeout
                self.is_open = True
            except Exception as e:
                raise IOError(f"Failed to open {self.port_name} via pyserial: {e}")

    def write(self, data: bytes, inter_byte_delay: float = 0.0) -> int:
        """Write raw bytes to machine with optional inter-byte pacing and flushing."""
        if not self.is_open:
            raise IOError("Serial port is not open.")

        if self.is_demo:
            if getattr(self, "demo_vendor", "jura") == "lamanti-kl":
                import struct
                from drivers.lamanti_kl.driver import calculate_modbus_crc
                if len(data) >= 8 and data[1] == 0x04:
                    reg_count = struct.unpack(">H", data[4:6])[0]
                    byte_count = reg_count * 2
                    payload = struct.pack(">HHHHH", 3, 93, 125, 150, 0x00FF)
                    if byte_count > len(payload):
                        payload += b"\x00" * (byte_count - len(payload))
                    else:
                        payload = payload[:byte_count]
                    hdr = struct.pack(">BBB", 0x01, 0x04, byte_count) + payload
                    self._demo_reply_buffer = hdr + calculate_modbus_crc(hdr)
                return len(data)
            elif getattr(self, "demo_vendor", "jura") == "lamanti-jn":
                import struct
                from drivers.lamanti_jn.driver import calculate_jetinno_crc
                if len(data) >= 6 and data[0] == 0xFE and data[3] == 0x14:
                    body = struct.pack(">BBBBBBBB", 0xFE, 0x01, 0x00, 0x14, 0x00, 0x04, 0x02, 0x00) + bytes([93, 88])
                    self._demo_reply_buffer = body + calculate_jetinno_crc(body)
                return len(data)
            # Route directly to Mock Jura device
            self._demo_reply_buffer = self.mock_machine.process_input(data)
            return len(data)

        if self.fd is not None and HAS_TERMIOS:
            try:
                if inter_byte_delay > 0.0 and len(data) > 1:
                    written = 0
                    for idx in range(len(data)):
                        written += os.write(self.fd, data[idx:idx + 1])
                        termios.tcdrain(self.fd)
                        if idx + 1 < len(data):
                            time.sleep(inter_byte_delay)
                    return written
                written = os.write(self.fd, data)
                # Drain output buffer
                termios.tcdrain(self.fd)
                return written
            except OSError:
                self.close()
                return 0

        if self.py_serial:
            try:
                if inter_byte_delay > 0.0 and len(data) > 1:
                    written = 0
                    for idx in range(len(data)):
                        written += self.py_serial.write(data[idx:idx + 1])
                        self.py_serial.flush()
                        if idx + 1 < len(data):
                            time.sleep(inter_byte_delay)
                    return written
                written = self.py_serial.write(data)
                self.py_serial.flush()
                return written
            except Exception:
                self.close()
                return 0

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
            try:
                rlist, _, _ = select.select([self.fd], [], [], t_out)
                if rlist:
                    chunk = os.read(self.fd, max_bytes)
                    if not chunk:
                        # Physical EOF / USB device disconnected
                        self.close()
                        return b""
                    return chunk
            except (OSError, BlockingIOError):
                self.close()
                return b""
            return b""

        if self.py_serial:
            try:
                cur_to = getattr(self, "_applied_timeout", None)
                if cur_to is None:
                    cur_to = getattr(self.py_serial, "timeout", None)
                if t_out != cur_to:
                    self.py_serial.timeout = t_out
                    self._applied_timeout = t_out
                return self.py_serial.read(max_bytes)
            except Exception:
                self.close()
                return b""

        return b""

    def drain_rx(self):
        """Flush any pending or trailing bytes in hardware input buffers."""
        if self.is_demo:
            self._demo_reply_buffer = b""
            return
        time.sleep(0.04)
        if self.fd is not None and HAS_TERMIOS:
            while select.select([self.fd], [], [], 0.04)[0]:
                try:
                    os.read(self.fd, 1024)
                except Exception:
                    break
        elif self.py_serial is not None:
            try:
                self.py_serial.reset_input_buffer()
            except Exception:
                self.close()

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
            vendor = getattr(self, "demo_vendor", "jura")
            if vendor in ("lamanti-kl", "lamanti-jn") or "SMART CONNECT" in self.port_name.upper():
                return None
            if vendor == "nivona":
                if cmd_clean == "TY:":
                    return "ty:NICR 0698 V01.04"
                elif cmd_clean == "HZ:":
                    return "hz:000000000000,0280,0000,0000,0000,0000,0,000000,0000,00"
                elif cmd_clean == "RT:0002":
                    return "rt:01720000"
                return None
            if cmd_clean == "TY:":
                return f"ty:{self.mock_machine.model_ef}"
            elif cmd_clean == "TL:":
                if "WE8" in self.port_name.upper():
                    return "tl:BL_RL78 V01.31"
                elif "D4" in self.port_name.upper():
                    return "tl:BL_RL78 V01.30"
                elif "A1" in self.port_name.upper():
                    return "tl:R8C Loader V1.04"
                elif "ENA 7" in self.port_name.upper() or "ENA7" in self.port_name.upper() or "13500" in self.port_name.upper():
                    return "tl:LOADER V5.0"
                return "tl:R8Cx Loader V01.00"
            elif cmd_clean == "TY$:":
                if "WE8" in self.port_name.upper():
                    return "ty$:EF533D V02.04"
                if "D4" in self.port_name.upper() or "A1" in self.port_name.upper():
                    return None
                return f"ty$:{self.mock_machine.model_ef.replace('M', 'D')}"
            elif cmd_clean == "TL$:":
                if "D4" in self.port_name.upper() or "A1" in self.port_name.upper():
                    return None
                return "tl$:SubLoader V01.00"
            elif cmd_clean == "CS$:":
                if "D4" in self.port_name.upper() or "A1" in self.port_name.upper():
                    return None
                return "cs$:1A2B"
            elif cmd_clean == "CS:":
                # Checksum / Telemetry Vector: nominal covered / beans present (slice [39:43] == 0000)
                return "cs:03C0300E5000000000000000000000000000000006D00006"
            elif cmd_clean == "IC:":
                if "WE8" in self.port_name.upper():
                    return "ic:1389"
                elif "D4" in self.port_name.upper():
                    return "ic:5700"
                elif "A1" in self.port_name.upper():
                    return "ic:AC03"
                elif "ENA 7" in self.port_name.upper() or "ENA7" in self.port_name.upper() or "13500" in self.port_name.upper():
                    return "ic:DF01"
                return "ic:230A"
            elif cmd_clean == "HZ:":
                if "Z10" in self.port_name.upper():
                    # Dual heater demo model (Coffee: 94.2°C, Steam: 135.0°C)
                    return "hz:010101100000,027E,00E2,0000,03AE,0546,4,000000,0000,00"
                elif "XJ5" in self.port_name.upper() or "Z6" in self.port_name.upper():
                    # Dual heater demo model (Coffee: 92.4°C [0x039C], Steam: 135.0°C [0x0546])
                    return "hz:010101100000,027E,00E2,0000,039C,0546,4,000000,0000,00"
                else:
                    # Single heater demo model (Coffee: 95.0°C, Steam: Not Installed)
                    return "hz:010101100000,027E,00E2,0000,03B6,0802,3,000000,0000,00"
            elif cmd_clean == "AS:":
                # Coffee Heater NTC Diagnostic Sensor Test (Ambient OFF ADC: 0x0645 = 1605, Shunt ON ADC: 0x06A5 = 1701 -> Ratio 1.0598 ~ +6.0% OK)
                return "as:077206450000,077206A50001"
            elif cmd_clean.startswith("RT:"):
                try:
                    blk = int(cmd_clean[3:], 16)
                    words = [self._mock_eeprom.get(blk + i, 0) for i in range(16)]
                    return "rt:" + "".join(f"{w:04X}" for w in words)
                except Exception:
                    return "rt:" + "0000" * 16
            elif cmd_clean.startswith("RE:"):
                try:
                    addr = int(cmd_clean[3:], 16)
                    val = self._mock_eeprom.get(addr, 0)
                    return f"re:{val:04X}"
                except Exception:
                    return "re:0000"
            return None

        return self._query_hardware_ascii(cmd_clean, timeout=timeout)

    def _query_raw_ascii(self, cmd_clean: str, timeout: float = 1.0) -> Optional[str]:
        """Send plain unencoded ASCII command terminated with CRLF and strip local echo."""
        self.drain_rx()
        tx_data = (cmd_clean + "\r\n").encode("ascii")
        self.write(tx_data)

        rx = bytearray()
        start = time.time()
        sent_raw = cmd_clean

        while time.time() - start < timeout:
            if not self.is_open:
                return None
            chunk = self.read(max_bytes=256, timeout_sec=0.05)
            if not self.is_open:
                return None
            if chunk:
                rx.extend(chunk)
                if len(rx) > 4096:
                    break
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

        return None

    def _write_paced(self, data: bytes, inter_byte_delay: float = 0.008) -> int:
        """Invoke write() with inter-byte pacing, falling back cleanly for mock overrides."""
        try:
            return self.write(data, inter_byte_delay=inter_byte_delay)
        except TypeError:
            return self.write(data)

    def _query_wire_4to1_ascii(self, cmd_clean: str, timeout: float = 0.8) -> Optional[str]:
        """Send 4:1 wire-encoded ASCII command, strip optical loopback echo, and decode 4-byte aligned RX."""
        import jura_protocol as jp

        self.drain_rx()
        tx_ascii = (cmd_clean + "\r\n").encode("ascii")
        wire_tx = jp.encode_wire(tx_ascii)
        self._write_paced(wire_tx, inter_byte_delay=0.008)

        rx_wire = bytearray()
        start = time.time()
        echo_stripped = False

        while time.time() - start < timeout:
            if not self.is_open:
                return None
            chunk = self.read(max_bytes=512, timeout_sec=0.05)
            if not self.is_open:
                return None
            if chunk:
                rx_wire.extend(chunk)
                if len(rx_wire) > 16384:
                    break
                if not echo_stripped:
                    echo_idx = rx_wire.find(wire_tx)
                    if echo_idx != -1:
                        del rx_wire[:echo_idx + len(wire_tx)]
                        echo_stripped = True
                aligned_len = (len(rx_wire) // 4) * 4
                if aligned_len >= 4:
                    decoded, _ = jp.decode_wire(bytes(rx_wire[:aligned_len]))
                    if b"\r\n" in decoded:
                        lines = [l.strip().decode("latin1", errors="ignore") for l in decoded.split(b"\r\n")]
                        complete_lines = lines[:-1]
                        replies = []
                        found_echo = False
                        for l in complete_lines:
                            if not found_echo and l == cmd_clean:
                                found_echo = True
                                continue
                            if l:
                                replies.append(l)
                        if replies:
                            time.sleep(0.04)
                            return replies[0]

        return None

    def _query_hardware_ascii(self, cmd_clean: str, timeout: float = 1.0) -> Optional[str]:
        """Dispatch physical ASCII query with 4:1 wire carrier auto-negotiation."""
        wire_mode = getattr(self, "wire_mode", None)
        if wire_mode == "smart_connect" or getattr(self, "_is_smart_connect", False):
            return None
        if wire_mode == "wire_4to1_ascii":
            return self._query_wire_4to1_ascii(cmd_clean, timeout=timeout)
        if wire_mode == "raw_ascii":
            return self._query_raw_ascii(cmd_clean, timeout=timeout)

        # First probe (wire_mode is None): try raw ASCII first, then 4:1 wire-encoded ASCII for Jura/auto
        ans = self._query_raw_ascii(cmd_clean, timeout=timeout)
        if ans is not None:
            self.wire_mode = "raw_ascii"
            return ans

        if getattr(self, "vendor", "jura") in ("jura", "auto", None):
            ans_wire = self._query_wire_4to1_ascii(cmd_clean, timeout=min(timeout, 0.8))
            if ans_wire and ":" in ans_wire:
                self.wire_mode = "wire_4to1_ascii"
                return ans_wire

        return None

    @staticmethod
    def _scan_decrypted_frames(decoded: bytes, cmd_clean: str) -> Optional[str]:
        """Scan buffer for valid '&...\\r\\n' Smart Connect frames, skipping stray '&' and TX echo."""
        import jura_protocol as jp

        search_idx = 0
        while True:
            amp = decoded.find(b"&", search_idx)
            if amp == -1:
                break
            end = decoded.find(b"\r\n", amp)
            if end == -1:
                break
            next_amp = decoded.find(b"&", amp + 1, end)
            if next_amp != -1:
                search_idx = next_amp
                continue
            frame = decoded[amp:end + 2]
            pt = jp.decode_encrypted_frame(frame)
            if pt is None:
                search_idx = amp + 1
                continue
            search_idx = end + 2
            if pt.strip() == cmd_clean:
                continue
            return pt
        return None

    def _query_encrypted_raw_frame(self, cmd_str: str, key: int = 0x20, timeout: float = 1.2) -> Optional[str]:
        """Send raw '&'-frame (for hardware 4:1 bridges like the Jura USB Service Interface box)."""
        import jura_protocol as jp

        cmd_clean = cmd_str.strip()
        cmd_line = f"{cmd_clean}\r\n"
        raw_frame = jp.build_encrypted_frame(cmd_line, key)

        self.drain_rx()
        self.write(raw_frame)

        rx = bytearray()
        start = time.time()
        echo_stripped = False

        while time.time() - start < timeout:
            if not self.is_open:
                return None
            chunk = self.read(max_bytes=512, timeout_sec=0.05)
            if not self.is_open:
                return None
            if chunk:
                rx.extend(chunk)
                if len(rx) > 16384:
                    break
                if not echo_stripped:
                    echo_idx = rx.find(raw_frame)
                    if echo_idx != -1:
                        del rx[:echo_idx + len(raw_frame)]
                        echo_stripped = True
                pt = self._scan_decrypted_frames(bytes(rx), cmd_clean)
                if pt is not None:
                    time.sleep(0.04)
                    return pt

        return None

    def _query_encrypted_wire_4to1(self, cmd_str: str, key: int = 0x20, timeout: float = 1.2) -> Optional[str]:
        """Send 4:1 wire-encoded '&'-frame with 8ms inter-byte pacing and decode 4-byte aligned RX."""
        import jura_protocol as jp

        cmd_clean = cmd_str.strip()
        cmd_line = f"{cmd_clean}\r\n"
        wire_tx = jp.encode_wire(jp.build_encrypted_frame(cmd_line, key))

        self.drain_rx()
        self._write_paced(wire_tx, inter_byte_delay=0.008)

        rx_wire = bytearray()
        start = time.time()
        echo_stripped = False

        while time.time() - start < timeout:
            if not self.is_open:
                return None
            chunk = self.read(max_bytes=512, timeout_sec=0.05)
            if not self.is_open:
                return None
            if chunk:
                rx_wire.extend(chunk)
                if len(rx_wire) > 16384:
                    break
                if not echo_stripped:
                    echo_idx = rx_wire.find(wire_tx)
                    if echo_idx != -1:
                        del rx_wire[:echo_idx + len(wire_tx)]
                        echo_stripped = True
                aligned_len = (len(rx_wire) // 4) * 4
                if aligned_len < 4:
                    continue
                decoded, _ = jp.decode_wire(bytes(rx_wire[:aligned_len]))
                pt = self._scan_decrypted_frames(decoded, cmd_clean)
                if pt is not None:
                    time.sleep(0.04)
                    return pt

        return None

    def query_encrypted(self, cmd_str: str, key: int = 0x20, timeout: float = 1.2) -> Optional[str]:
        """
        Send an encrypted Jura Smart Connect '@'-command over 4:1 wire or raw '&'-frame
        (hardware 4:1 bridge) and return the decrypted response frame, stripping loopback
        echo and scanning '&'...CRLF frames safely.
        """
        if not self.is_open:
            raise IOError("Serial port is not open.")

        import jura_protocol as jp

        cmd_clean = cmd_str.strip()
        cmd_line = cmd_clean if cmd_str.endswith("\r\n") else f"{cmd_clean}\r\n"

        if self.is_demo:
            wire_tx = jp.encode_wire(jp.build_encrypted_frame(cmd_line, key))
            self.drain_rx()
            self.write(wire_tx)
            rx = self.read(2048, timeout_sec=timeout)
            if not rx:
                return None
            aligned_len = (len(rx) // 4) * 4
            if aligned_len < 4:
                return None
            decoded, _ = jp.decode_wire(rx[:aligned_len])
            return self._scan_decrypted_frames(decoded, cmd_clean)

        enc_mode = getattr(self, "encrypted_wire_mode", None)
        if enc_mode == "raw_frame":
            return self._query_encrypted_raw_frame(cmd_str, key=key, timeout=timeout)
        if enc_mode == "wire_4to1_frame":
            return self._query_encrypted_wire_4to1(cmd_str, key=key, timeout=timeout)

        # Auto-negotiate encrypted wire mode:
        # If raw_ascii was previously observed (e.g. hardware 4:1 bridge like Jura USB Service Interface),
        # try raw '&'-frame first; otherwise try 4:1 wire-encoded '&'-frame first.
        if getattr(self, "wire_mode", None) == "raw_ascii":
            pt = self._query_encrypted_raw_frame(cmd_str, key=key, timeout=timeout)
            if pt is not None:
                self.encrypted_wire_mode = "raw_frame"
                self._is_smart_connect = True
                return pt
            pt = self._query_encrypted_wire_4to1(cmd_str, key=key, timeout=min(timeout, 0.8))
            if pt is not None:
                self.encrypted_wire_mode = "wire_4to1_frame"
                self._is_smart_connect = True
                return pt
        else:
            pt = self._query_encrypted_wire_4to1(cmd_str, key=key, timeout=timeout)
            if pt is not None:
                self.encrypted_wire_mode = "wire_4to1_frame"
                self._is_smart_connect = True
                return pt
            pt = self._query_encrypted_raw_frame(cmd_str, key=key, timeout=min(timeout, 0.8))
            if pt is not None:
                self.encrypted_wire_mode = "raw_frame"
                self._is_smart_connect = True
                return pt

        return None

    def close(self):
        """Close connection cleanly."""
        if self.fd is not None:
            if HAS_TERMIOS:
                try:
                    fcntl.flock(self.fd, fcntl.LOCK_UN)
                except Exception:
                    pass
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
        self._applied_timeout = None
        self.is_open = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Universal Alias for multi-vendor abstraction
DirectSerialConnection = JuraSerialConnection


