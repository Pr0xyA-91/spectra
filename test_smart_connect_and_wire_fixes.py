#!/usr/bin/env python3
"""
Regression unit tests for Jura Smart Connect & 4:1 Wire Carrier fixes:
1. Smart Connect Poll #1 and Poll #2+ in query_live_sensors() (no NameError, no _cached_ef="" flip).
2. Mode A -> Mode B fallback when TY: responds or times out and RT: times out or returns all zeros,
   populating session.last_eeprom from @TR:32 without 45s of cascading timeouts.
3. Optical loopback echo stripping in query_encrypted() / _send_encrypted_cmd().
4. 4:1 wire carrier auto-detection in query_ascii().
5. MemoryMapperEngine & spectra_probe.sweep_eeprom RE: fast-fail and Smart Connect fallback.
"""

import os
import sys
import unittest
from unittest.mock import patch

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import jura_protocol as jp
import memory_mapper
import serial_io
import spectra_probe
import stats_collector as sc
from drivers.jura.driver import JuraDriver


class FakeSmartConnectWireTransport(serial_io.JuraSerialConnection):
    """Simulates a physical Smart Connect port with optional optical TX echo and TY: behavior."""

    def __init__(self, ty_reply=None, rt_zero=False, echo_tx=True, wire_4to1_ascii=False):
        self.port_name = "/dev/ttyUSB0"
        self.raw_port_label = "/dev/ttyUSB0"
        self.baudrate = 9600
        self.timeout = 0.2
        self._applied_timeout = 0.2
        self.is_demo = False
        self.mock_machine = jp.MockJuraMachine(model_ef="EF536M V02.01", model_name="S8")
        self.fd = None
        self.py_serial = None
        self.is_open = True
        self.wire_mode = None
        self._is_smart_connect = False
        self.vendor = "jura"
        self.demo_vendor = "hardware"
        self._rx_queue = bytearray()
        self._ty_reply = ty_reply
        self._rt_zero = rt_zero
        self._echo_tx = echo_tx
        self._wire_4to1_ascii = wire_4to1_ascii
        self.ascii_cmds = []

    def drain_rx(self):
        self._rx_queue.clear()

    def write(self, data: bytes) -> int:
        # Optical loopback echo prepended before machine reply
        if self._echo_tx:
            self._rx_queue.extend(data)

        # Check plain ASCII commands (when not wire-encoded)
        try:
            text = data.decode("ascii")
        except UnicodeDecodeError:
            text = ""
        if text.endswith("\r\n") and not self._wire_4to1_ascii:
            cmd = text.strip()
            self.ascii_cmds.append(cmd)
            if cmd == "TY:" and self._ty_reply is not None:
                self._rx_queue.extend((self._ty_reply + "\r\n").encode("ascii"))
            elif self._rt_zero and cmd.startswith("RT:"):
                self._rx_queue.extend(("rt:" + ("0000" * 16) + "\r\n").encode("ascii"))
            elif self._rt_zero and cmd.startswith("RE:"):
                self._rx_queue.extend(b"re:0000\r\n")
            return len(data)

        # Check 4:1 wire-encoded payload
        aligned = (len(data) // 4) * 4
        if aligned >= 4:
            decoded, _ = jp.decode_wire(data[:aligned])
            if self._wire_4to1_ascii and not decoded.startswith(b"&"):
                cmd = decoded.decode("ascii", errors="ignore").strip()
                self.ascii_cmds.append(f"4to1:{cmd}")
                if cmd == "TY:":
                    self._rx_queue.extend(jp.encode_wire(b"ty:EF533M V02.09\r\n"))
                elif cmd == "HZ:":
                    self._rx_queue.extend(jp.encode_wire(b"hz:010101100000,027E,00E2,0000,03B6,0802,3,000000,0000,00\r\n"))
                return len(data)

            if decoded.startswith(b"&"):
                reply = self.mock_machine.process_input(data)
                if reply:
                    self._rx_queue.extend(reply)
        return len(data)

    def read(self, max_bytes: int = 2048, timeout_sec=None) -> bytes:
        if not self._rx_queue:
            return b""
        chunk = bytes(self._rx_queue[:max_bytes])
        del self._rx_queue[:max_bytes]
        return chunk


class TestSmartConnectAndWireFixes(unittest.TestCase):
    def test_smart_connect_live_sensors_poll1_and_poll2(self):
        """Poll #1 and Poll #2+ must never raise NameError or flip back to ASCII via _cached_ef=''."""
        conn = serial_io.JuraSerialConnection("DEMO / SIMULATION (Jura S8 Smart Connect)")
        try:
            with patch("time.sleep", return_value=None):
                res1 = sc.query_live_sensors(conn.port_name, conn=conn, fast_poll=True)
                self.assertEqual(res1["protocol"], "Encrypted Smart Connect (@-Protocol)")
                self.assertNotIn("error", res1)
                self.assertTrue(len(res1["switches"]) >= 4)
                self.assertNotEqual(getattr(conn, "_cached_ef", None), "")

                # Poll #2+
                res2 = sc.query_live_sensors(conn.port_name, conn=conn, fast_poll=True)
                self.assertEqual(res2["protocol"], "Encrypted Smart Connect (@-Protocol)")
                self.assertNotIn("error", res2)

            # Also test hardware-like port where _cached_ef wasn't set yet and TY:/HZ: time out
            hw_conn = FakeSmartConnectWireTransport(ty_reply=None, echo_tx=True)
            with patch("time.sleep", return_value=None):
                # Shorten _query_raw_ascii / _query_wire_4to1_ascii timeouts for fast unit test
                orig_q = hw_conn.query_ascii
                hw_conn.query_ascii = lambda cmd, timeout=1.0: orig_q(cmd, timeout=0.05)
                p1 = sc.query_live_sensors("/dev/ttyUSB0", conn=hw_conn, fast_poll=True)
                self.assertEqual(p1["protocol"], "Encrypted Smart Connect (@-Protocol)")
                self.assertNotIn("error", p1)
                self.assertTrue(hw_conn._is_smart_connect)
                self.assertNotIn("_cached_ef", hw_conn.__dict__)

                hw_conn.ascii_cmds.clear()
                p2 = sc.query_live_sensors("/dev/ttyUSB0", conn=hw_conn, fast_poll=True)
                self.assertEqual(p2["protocol"], "Encrypted Smart Connect (@-Protocol)")
                self.assertNotIn("error", p2)
                self.assertEqual(hw_conn.ascii_cmds, [])
        finally:
            conn.close()

    def test_optical_loopback_echo_stripping_in_query_encrypted(self):
        """query_encrypted() must strip TX optical loopback echo and return decrypted reply."""
        conn = FakeSmartConnectWireTransport(echo_tx=True)
        with patch("time.sleep", return_value=None):
            t0 = conn.query_encrypted("@T0\r\n", key=0x20, timeout=0.4)
            self.assertIsNotNone(t0)
            self.assertIn("@t0", t0.lower())

            conn.query_encrypted("@T1\r\n", key=0x21, timeout=0.4)
            t3 = conn.query_encrypted("@t2:818000\r\n", key=0x22, timeout=0.4)
            self.assertIsNotNone(t3)
            self.assertIn("@T3:", t3)
            conn.query_encrypted("@t3\r\n", key=0x23, timeout=0.4)

            tr0 = conn.query_encrypted("@TR:32,00\r\n", key=0x30, timeout=0.4)
            self.assertIsNotNone(tr0)
            parsed = jp.parse_tr32(tr0)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed[1][0], 8420)

            # Test JuraDriver.probe() does not falsely match TX echo when machine is silent
            silent_echo_conn = FakeSmartConnectWireTransport(echo_tx=True)
            silent_echo_conn.mock_machine.process_input = lambda _b: b""
            orig_qa = silent_echo_conn.query_ascii
            silent_echo_conn.query_ascii = lambda cmd, timeout=1.0: orig_qa(cmd, timeout=0.02)
            self.assertIsNone(JuraDriver().probe(silent_echo_conn))

    def test_4to1_wire_carrier_auto_detection_in_query_ascii(self):
        """query_ascii() falls back to 4:1 wire carrier on raw timeout and locks wire_mode."""
        conn = FakeSmartConnectWireTransport(wire_4to1_ascii=True, echo_tx=True)
        with patch("time.sleep", return_value=None):
            # Override raw ASCII helper timeout so test runs instantaneously
            orig_raw = conn._query_raw_ascii
            conn._query_raw_ascii = lambda cmd, timeout=1.0: orig_raw(cmd, timeout=0.02)
            ty = conn.query_ascii("TY:", timeout=0.3)
            self.assertEqual(ty, "ty:EF533M V02.09")
            self.assertEqual(conn.wire_mode, "wire_4to1_ascii")

            hz = conn.query_ascii("HZ:", timeout=0.3)
            self.assertIsNotNone(hz)
            self.assertTrue(hz.startswith("hz:"))
            self.assertIn("4to1:HZ:", conn.ascii_cmds)

    def test_mode_a_to_mode_b_fallback_on_rt_timeout_and_all_zero_rt(self):
        """Mode A falls through to Mode B when TY: answers but RT: times out or returns all 0000s."""
        for rt_zero in (False, True):
            conn = FakeSmartConnectWireTransport(ty_reply="ty:EF536M V02.01", rt_zero=rt_zero, echo_tx=True)
            orig_qa = conn.query_ascii
            conn.query_ascii = lambda cmd, timeout=1.0: orig_qa(cmd, timeout=0.02)

            sess = sc.JuraStatsSession("/dev/ttyUSB0")
            sess.conn = conn
            with patch("time.sleep", return_value=None):
                ok = sess.run_interrogation()

            self.assertTrue(ok)
            self.assertIn("Smart Connect", sess.protocol_mode)
            self.assertGreater(len(sess.last_eeprom), 0)
            self.assertTrue(any(v > 0 for v in sess.last_eeprom.values()))
            self.assertGreater(sess.total_preparations, 0)
            self.assertGreater(sess.total_cups, 0)
            # Fast-fail should avoid 19 individual RE: queries on RT timeout
            if not rt_zero:
                re_cmds = [c for c in conn.ascii_cmds if c.startswith("RE:")]
                self.assertLessEqual(len(re_cmds), 1)

    def test_memory_mapper_and_probe_fast_fail_and_smart_connect_sweep(self):
        """MemoryMapperEngine and spectra_probe.sweep_eeprom avoid 16x RE: cascades and fall back to @TR:32."""
        conn = FakeSmartConnectWireTransport(ty_reply=None, echo_tx=True)
        orig_qa = conn.query_ascii
        conn.query_ascii = lambda cmd, timeout=1.0: orig_qa(cmd, timeout=0.02)

        with patch("time.sleep", return_value=None):
            engine = memory_mapper.MemoryMapperEngine(conn)
            conn.ascii_cmds.clear()
            eeprom = engine.sweep_eeprom()

        re_cmds = [c for c in conn.ascii_cmds if c.startswith("RE:")]
        # Only 1 RE: probe per failed block across first 2 blocks before aborting
        self.assertLessEqual(len(re_cmds), 2)
        self.assertGreater(eeprom.get(0x0000, 0), 0)

        # Also verify spectra_probe.sweep_eeprom
        conn2 = FakeSmartConnectWireTransport(ty_reply=None, echo_tx=True)
        orig_qa2 = conn2.query_ascii
        conn2.query_ascii = lambda cmd, timeout=1.0: orig_qa2(cmd, timeout=0.02)
        with patch("time.sleep", return_value=None):
            probe_map = spectra_probe.sweep_eeprom(conn2, max_words=512)
        re_cmds2 = [c for c in conn2.ascii_cmds if c.startswith("RE:")]
        self.assertLessEqual(len(re_cmds2), 2)
        self.assertGreater(probe_map.get(0x0000, 0), 0)

    def test_web_api_command_routes_smart_connect_at_commands(self):
        """/api/command must allow safe '@' prefixes and route them through query_encrypted()."""
        import json
        import urllib.request
        import spectra_app
        import web_server

        httpd, port, url = spectra_app.start_inprocess_server()
        try:
            demo_port = "DEMO / SIMULATION (Jura S8 Smart Connect)"

            def post_cmd(cmd_str: str):
                body = json.dumps({"port": demo_port, "cmd": cmd_str}).encode("utf-8")
                req = urllib.request.Request(
                    f"{url}/api/command",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            r_t0 = post_cmd("@T0")
            self.assertTrue(r_t0.get("success"))
            self.assertIn("@t0", r_t0.get("response", "").lower())

            r_tf = post_cmd("@TF:")
            self.assertTrue(r_tf.get("success"))
            self.assertIn("@tf:", r_tf.get("response", "").lower())

            # Unsafe write command @tw: must still be refused
            r_tw = post_cmd("@tw:0000")
            self.assertFalse(r_tw.get("success"))
            self.assertIn("Refusing command", r_tw.get("error", ""))
        finally:
            web_server.cleanup_resources()
            spectra_app.shutdown_spectra_cleanly(httpd)

    def test_official_usb_service_interface_raw_frame_autodetection(self):
        """Official Jura USB Service Interface box accepts raw '&'-frames without double 4:1 encoding."""
        class RawFrameBridgeTransport(serial_io.JuraSerialConnection):
            def __init__(self):
                self.port_name = "/dev/ttyUSB0"
                self.raw_port_label = "/dev/ttyUSB0"
                self.baudrate = 9600
                self.timeout = 0.2
                self._applied_timeout = 0.2
                self.is_demo = False
                self.mock_machine = jp.MockJuraMachine(model_ef="EF536M V02.01", model_name="S8")
                self.fd = None
                self.py_serial = None
                self.is_open = True
                self.wire_mode = None
                self.encrypted_wire_mode = None
                self._is_smart_connect = False
                self.vendor = "jura"
                self.demo_vendor = "hardware"
                self._rx_queue = bytearray()
                self.written_frames = []

            def drain_rx(self):
                self._rx_queue.clear()

            def write(self, data: bytes, inter_byte_delay: float = 0.0) -> int:
                self.written_frames.append(data)
                # Only respond to raw '&'-frames (not 4:1 encoded carrier bytes starting with 0xDB/0xDF/etc.)
                if data.startswith(b"&") and data.endswith(b"\r\n"):
                    # Echo raw frame first, then feed into MockJuraMachine by encoding to wire and unwrapping
                    self._rx_queue.extend(data)
                    reply_wire = self.mock_machine.process_input(jp.encode_wire(data))
                    if reply_wire:
                        reply_raw, _ = jp.decode_wire(reply_wire)
                        self._rx_queue.extend(reply_raw)
                return len(data)

            def read(self, max_bytes: int = 2048, timeout_sec=None) -> bytes:
                if not self._rx_queue:
                    return b""
                chunk = bytes(self._rx_queue[:max_bytes])
                del self._rx_queue[:max_bytes]
                return chunk

        conn = RawFrameBridgeTransport()
        # Shorten 4:1 fallback timeout so auto-negotiation is fast in unit tests
        orig_w41 = conn._query_encrypted_wire_4to1
        conn._query_encrypted_wire_4to1 = lambda cmd_str, key=0x20, timeout=1.2: orig_w41(cmd_str, key=key, timeout=0.02)

        with patch("time.sleep", return_value=None):
            t0 = conn.query_encrypted("@T0\r\n", key=0x20, timeout=0.4)
            self.assertIsNotNone(t0)
            self.assertIn("@t0", t0.lower())
            self.assertEqual(conn.encrypted_wire_mode, "raw_frame")
            self.assertTrue(conn._is_smart_connect)

            # Subsequent commands go straight to raw_frame without probing wire_4to1_frame
            conn.written_frames.clear()
            conn.query_encrypted("@T1\r\n", key=0x21, timeout=0.4)
            t3 = conn.query_encrypted("@t2:818000\r\n", key=0x22, timeout=0.4)
            self.assertIn("@T3:", t3)
            self.assertTrue(all(f.startswith(b"&") for f in conn.written_frames))

    def test_sweep_block_smart_connect_4_banks_and_dead_bus_abort(self):
        """sweep_block() reads 4 banks (16 words) on Smart Connect and aborts after 2 failed blocks on dead bus."""
        conn = FakeSmartConnectWireTransport(ty_reply=None, echo_tx=True)
        orig_qa = conn.query_ascii
        conn.query_ascii = lambda cmd, timeout=1.0: orig_qa(cmd, timeout=0.02)

        with patch("time.sleep", return_value=None):
            engine = memory_mapper.MemoryMapperEngine(conn)
            res0 = engine.sweep_block(0)
            self.assertIsInstance(res0, dict)
            self.assertFalse(res0.get("abort_sweep"))
            self.assertEqual(len(res0["registers"]), 16)
            # 4 banks * 4 words = 16 words populated in block 0 (addrs 0..15)
            # Mock counters: 0->8420, 1->14, 2->320, 3->6810, 4->215, 5->84, 6->62, 7->490, 8->55, 10->22, 13->130
            self.assertEqual(engine.current_eeprom[0], 8420)
            self.assertEqual(engine.current_eeprom[4], 215)
            self.assertEqual(engine.current_eeprom[8], 55)
            self.assertEqual(engine.current_eeprom[13], 130)

        # Dead bus: silent on both ASCII and Smart Connect
        dead_conn = FakeSmartConnectWireTransport(ty_reply=None, echo_tx=True)
        dead_conn.mock_machine.process_input = lambda _b: b""
        orig_qa_dead = dead_conn.query_ascii
        dead_conn.query_ascii = lambda cmd, timeout=1.0: orig_qa_dead(cmd, timeout=0.02)
        orig_qe_dead = dead_conn.query_encrypted
        dead_conn.query_encrypted = lambda cmd, key=0x20, timeout=1.2: orig_qe_dead(cmd, key=key, timeout=0.02)

        with patch("time.sleep", return_value=None):
            dead_engine = memory_mapper.MemoryMapperEngine(dead_conn)
            r0 = dead_engine.sweep_block(0)
            self.assertFalse(r0.get("abort_sweep"))
            r1 = dead_engine.sweep_block(1)
            self.assertTrue(r1.get("abort_sweep"))
            self.assertIn("abort_reason", r1)

    def test_query_live_sensors_hz_none_after_ty_no_unbound_local_error(self):
        """query_live_sensors() must not raise UnboundLocalError on 'parts' when TY: succeeds and HZ: returns None."""
        conn = FakeSmartConnectWireTransport(ty_reply="ty:EF518M V02.20", echo_tx=False)
        orig_qa = conn.query_ascii

        def mock_qa(cmd, timeout=1.0):
            if cmd == "TY:":
                return "ty:EF518M V02.20"
            return None

        conn.query_ascii = mock_qa
        with patch("time.sleep", return_value=None):
            res = sc.query_live_sensors("/dev/ttyUSB0", conn=conn, fast_poll=True)
        self.assertNotIn("error", res)
        self.assertEqual(res.get("raw_status"), "N/A")
        self.assertTrue(len(res.get("switches", [])) > 0)

    def test_run_interrogation_uppercase_rt_corrupt_hex_and_bank4_stride(self):
        """run_interrogation handles uppercase RT: with corrupt hex cleanly and uses bank * 4 stride in Mode B."""
        # 1. Uppercase RT: + corrupt hex falls through cleanly without crashing
        conn = FakeSmartConnectWireTransport(ty_reply="ty:EF536M V02.01", echo_tx=True)
        orig_qa = conn.query_ascii

        def custom_qa(cmd, timeout=1.0):
            if cmd == "TY:":
                return "ty:EF536M V02.01"
            if cmd.startswith("RT:"):
                return "RT:" + ("ZZZZ" * 16)
            return orig_qa(cmd, timeout=0.02)

        conn.query_ascii = custom_qa
        sess = sc.JuraStatsSession("/dev/ttyUSB0")
        sess.conn = conn
        with patch("time.sleep", return_value=None):
            ok = sess.run_interrogation()
        self.assertTrue(ok)
        # Mode B bank * 4 stride: bank 0 -> addr 0..3, bank 1 -> addr 4..7, bank 2 -> addr 8..11, bank 3 -> addr 12..15
        self.assertEqual(sess.last_eeprom.get(0), 8420)
        self.assertEqual(sess.last_eeprom.get(4), 215)
        self.assertEqual(sess.last_eeprom.get(8), 55)
        self.assertEqual(sess.last_eeprom.get(13), 130)

    def test_profiles_db_find_profile_preserves_base_fields_with_model_spec(self):
        """find_profile() resolves base profiles_data.json first and preserves fields when docs/models spec exists."""
        import profiles_db
        profiles_db.invalidate_model_specs_cache()
        prof = profiles_db.find_profile("EF518M V02.20")
        # Spec fields from docs/models/EF518M_*.json are merged on top
        self.assertIn("custom_registers", prof)
        # Base fields from profiles_data.json (e.g. alerts / maintenance_counters) are preserved
        self.assertIn("alerts", prof)
        self.assertTrue(len(prof["alerts"]) > 0)
        # Returned dict is a deep copy; mutating it must not pollute cached profile
        prof["alerts"].append({"bit": 999, "blocking": False, "name": "polluted"})
        prof2 = profiles_db.find_profile("EF518M V02.20")
        self.assertFalse(any(a.get("bit") == 999 for a in prof2["alerts"]))


if __name__ == "__main__":
    unittest.main()
