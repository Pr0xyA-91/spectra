#!/usr/bin/env python3
"""
Unit and Integration Tests for W.R.A.T. Multi-Manufacturer Architecture
Validates Jura, Nivona, Lamanti-KL (Kalerm), and Lamanti-JN (Jetinno) drivers.
"""

import unittest
import struct

from drivers.base import (
    ApplianceCapabilities,
    ApplianceIdentification,
    BeverageCounter,
    MaintenanceMetric,
    ApplianceTelemetry
)
from drivers.jura.driver import JuraDriver
from drivers.nivona.driver import NivonaDriver, NIVONA_MODEL_CATALOG, NIVONA_ERROR_CODES
from drivers.lamanti_kl.driver import (
    LamantiKLDriver,
    calculate_modbus_crc,
    verify_modbus_crc,
    KALERM_MODEL_CATALOG,
    KALERM_FAULT_CODES
)
from drivers.lamanti_jn.driver import (
    LamantiJNDriver,
    calculate_jetinno_crc,
    verify_jetinno_crc,
    JETINNO_MODEL_CATALOG,
    JETINNO_FAULT_CODES
)
from drivers import list_drivers, get_driver, detect_driver
from wrat_engine import WRATSession
import serial_io


class MockSerialPort:
    """Mock serial connection simulating wire transactions for tests."""

    def __init__(self, vendor_profile: str = "jura"):
        self.vendor_profile = vendor_profile
        self.port_name = f"mock_{vendor_profile}"
        self.baudrate = 9600
        self.is_open = True
        self.tx_buffer = b""
        self.rx_buffer = b""

    def write(self, data: bytes) -> int:
        self.tx_buffer += data
        if self.vendor_profile == "jura":
            if b"TY:" in data:
                self.rx_buffer += b"ty:EF536M V02.01\r\n"
            elif b"HZ:" in data:
                self.rx_buffer += b"hz:010001000000,027E,00E2,0000,03AE,0546,4,000000,0000,00\r\n"
            elif b"RE:0030" in data:
                self.rx_buffer += b"re:4660\r\n"
        elif self.vendor_profile == "nivona":
            if b"TY:" in data:
                self.rx_buffer += b"ty:NICR 0698 V01.04\r\n"
            elif b"HZ:" in data:
                self.rx_buffer += b"hz:000000000000,0280,0000,0000,0000,0000,0,000000,0000,00\r\n"
            elif b"RT:0002" in data:
                self.rx_buffer += b"rt:01720000\r\n"
        elif self.vendor_profile == "lamanti-kl":
            # Modbus RTU simulation
            if len(data) >= 8 and data[1] == 0x04:
                # Modbus Read Input Registers
                reg_count = struct.unpack(">H", data[4:6])[0]
                byte_count = reg_count * 2
                # Payload: state=3 (ready), boiler=93, steam=125, flow=150, switches=0x00FF (all OK), etc.
                payload = struct.pack(">HHHHH", 3, 93, 125, 150, 0x00FF)
                payload += b"\x00" * (byte_count - len(payload))
                hdr = struct.pack(">BBB", 0x01, 0x04, byte_count) + payload
                self.rx_buffer += hdr + calculate_modbus_crc(hdr)
        elif self.vendor_profile == "lamanti-jn":
            # Jetinno packet simulation
            if len(data) >= 6 and data[0] == 0xFE and data[3] == 0x14:
                # Jetinno heartbeat response: FE 01 00 14 [flags] [t1] [t2] [CRC]
                body = struct.pack(">BBBBBBBB", 0xFE, 0x01, 0x00, 0x14, 0x00, 0x04, 0x02, 0x00) + bytes([93, 88])
                self.rx_buffer += body + calculate_jetinno_crc(body)
        return len(data)

    def read(self, max_bytes: int = 1024, timeout_sec: float = 0.5) -> bytes:
        data = self.rx_buffer[:max_bytes]
        self.rx_buffer = self.rx_buffer[max_bytes:]
        return data

    def query_ascii(self, cmd: str, timeout: float = 0.5) -> str:
        self.write((cmd.strip() + "\r\n").encode("ascii"))
        rx = self.read(256)
        return rx.decode("ascii", errors="replace").strip()

    def close(self):
        pass


class TestMultiManufacturerDrivers(unittest.TestCase):

    def test_driver_registry(self):
        drivers = list_drivers()
        keys = [d[0] for d in drivers]
        self.assertIn("jura", keys)
        self.assertIn("nivona", keys)
        self.assertIn("lamanti-kl", keys)
        self.assertIn("lamanti-jn", keys)

        # Ensure factory instantiation
        self.assertIsInstance(get_driver("jura"), JuraDriver)
        self.assertIsInstance(get_driver("nivona"), NivonaDriver)
        self.assertIsInstance(get_driver("lamanti-kl"), LamantiKLDriver)
        self.assertIsInstance(get_driver("lamanti-jn"), LamantiJNDriver)

    def test_jura_driver_on_mock(self):
        conn = MockSerialPort(vendor_profile="jura")
        driver = JuraDriver()
        ident = driver.probe(conn)
        self.assertIsNotNone(ident)
        self.assertEqual(ident.vendor, "Jura")
        self.assertIn("S8", ident.model)

        sensors = driver.read_live_sensors(conn)
        self.assertIn("switches", sensors)
        self.assertIn("sensors", sensors)

    def test_nivona_driver(self):
        conn = MockSerialPort(vendor_profile="nivona")
        driver = NivonaDriver()
        ident = driver.probe(conn)
        self.assertIsNotNone(ident)
        self.assertEqual(ident.vendor, "Nivona")
        self.assertIn("CafeRomatica", ident.model)

        sensors = driver.read_live_sensors(conn)
        self.assertEqual(sensors["readiness"], "Ready")
        switches = {s["id"]: s for s in sensors["switches"]}
        self.assertTrue(switches["water_tank"]["ok"])
        self.assertTrue(switches["drip_tray"]["ok"])
        self.assertTrue(switches["brew_group"]["ok"])

        # Test full telemetry
        telem = driver.read_telemetry(conn)
        self.assertEqual(telem.vendor, "Nivona")
        self.assertTrue(len(telem.beverages) > 0)
        self.assertTrue(len(telem.maintenance) > 0)

    def test_lamanti_kl_modbus(self):
        # Test Modbus CRC calculation and verification
        test_data = bytes.fromhex("01 04 00 00 00 15")
        crc = calculate_modbus_crc(test_data)
        self.assertEqual(len(crc), 2)
        full_frame = test_data + crc
        self.assertTrue(verify_modbus_crc(full_frame))

        # Test driver probing
        conn = MockSerialPort(vendor_profile="lamanti-kl")
        driver = LamantiKLDriver()
        ident = driver.probe(conn)
        self.assertIsNotNone(ident)
        self.assertEqual(ident.vendor, "Lamanti-KL")

        # Test live sensor reading
        sensors = driver.read_live_sensors(conn)
        self.assertEqual(sensors["readiness"], "Ready")
        switches = {s["id"]: s for s in sensors["switches"]}
        self.assertTrue(switches["water_tank"]["ok"])
        self.assertTrue(switches["door_switch"]["ok"])

        # Test telemetry
        telem = driver.read_telemetry(conn)
        self.assertEqual(telem.vendor, "Lamanti-KL")
        self.assertGreater(telem.total_cups, 10000)

    def test_lamanti_jn_jetinno(self):
        # Test Jetinno CRC calculation and verification
        test_data = bytes.fromhex("FE 01 00 14 00 00")
        crc = calculate_jetinno_crc(test_data)
        self.assertEqual(len(crc), 2)
        full_frame = test_data + crc
        self.assertTrue(verify_jetinno_crc(full_frame))

        # Test driver probing
        conn = MockSerialPort(vendor_profile="lamanti-jn")
        driver = LamantiJNDriver()
        ident = driver.probe(conn)
        self.assertIsNotNone(ident)
        self.assertEqual(ident.vendor, "Lamanti-JN")

        # Test live sensors
        sensors = driver.read_live_sensors(conn)
        self.assertEqual(sensors["readiness"], "Ready")
        switches = {s["id"]: s for s in sensors["switches"]}
        self.assertTrue(switches["cabinet_door"]["ok"])
        self.assertTrue(switches["water_inlet"]["ok"])

        # Test telemetry
        telem = driver.read_telemetry(conn)
        self.assertEqual(telem.vendor, "Lamanti-JN")
        self.assertGreater(telem.total_cups, 50000)

    def test_auto_detection_engine(self):
        # Test detect_driver on Nivona
        conn_niv = MockSerialPort(vendor_profile="nivona")
        drv_niv, id_niv = detect_driver(conn_niv)
        self.assertEqual(drv_niv.vendor, "Nivona")
        self.assertEqual(id_niv.vendor, "Nivona")

        # Test detect_driver on Lamanti-KL
        conn_kl = MockSerialPort(vendor_profile="lamanti-kl")
        drv_kl, id_kl = detect_driver(conn_kl)
        self.assertEqual(drv_kl.vendor, "Lamanti-KL")
        self.assertEqual(id_kl.vendor, "Lamanti-KL")

        # Test detect_driver on Lamanti-JN
        conn_jn = MockSerialPort(vendor_profile="lamanti-jn")
        drv_jn, id_jn = detect_driver(conn_jn)
        self.assertEqual(drv_jn.vendor, "Lamanti-JN")
        self.assertEqual(id_jn.vendor, "Lamanti-JN")

    def test_wrat_session_coordinator(self):
        conn_kl = MockSerialPort(vendor_profile="lamanti-kl")
        session = WRATSession(manufacturer="auto", conn=conn_kl)
        session.initialize_driver()
        self.assertEqual(session.driver.vendor, "Lamanti-KL")

        success = session.run_interrogation()
        self.assertTrue(success)
        summary = session.get_structured_summary()
        self.assertEqual(summary["vendor"], "Lamanti-KL")
        self.assertIn("beverages", summary)
        self.assertIn("maintenance", summary)

    def test_demo_ports_multi_vendor_autodetect(self):
        """Verify built-in DEMO / SIMULATION ports auto-detect to their respective manufacturer."""
        cases = [
            ("DEMO / SIMULATION (Jura S8)", "Jura"),
            ("DEMO / SIMULATION (Nivona NICR768)", "Nivona"),
            ("DEMO / SIMULATION (Lamanti-KL X680C)", "Lamanti-KL"),
            ("DEMO / SIMULATION (Lamanti-JN JL300)", "Lamanti-JN"),
        ]
        for port_label, expected_vendor in cases:
            with WRATSession(port_name=port_label, manufacturer="auto") as session:
                sensors = session.query_live_sensors()
                self.assertEqual(session.driver.vendor, expected_vendor)
                self.assertIn("switches", sensors)
                self.assertIn("telemetry", sensors)

                ok = session.run_interrogation()
                self.assertTrue(ok)
                summary = session.get_structured_summary()
                self.assertEqual(summary["vendor"], expected_vendor)
                self.assertTrue(len(summary["maintenance"]) > 0)
                self.assertNotEqual(summary["maintenance"][0]["name"], "Maintenance")
                if expected_vendor == "Jura":
                    names = [m["name"] for m in summary["maintenance"]]
                    self.assertIn("Cleaning", names)
                    self.assertIn("Descaling", names)
                    self.assertIn("Rinsing", names)


if __name__ == "__main__":
    unittest.main()
