#!/usr/bin/env python3
"""
Jura Communication & Protocol Engine
Handles:
- 4:1 UART physical line encoding & decoding (base 0xDB, data in bits 2 & 5)
- Encrypted '@'-protocol framing ('&' sync, escape, and recovered nibble cipher)
- Full Smart Connect handshake (@T0 -> @t0, @T1 -> @t1, @T2 challenge -> @t2 response, @T3 model -> @t3)
- Product beverage counter queries (@TR:32,00 .. @TR:32,0B)
- Maintenance counters (@TG:43) and percentages (@TG:C0)
- Real-time alerts and telemetry (@TF:)
- Legacy cleartext fallback (TY:, RT:, RE:)
- High-fidelity Mock Jura Machine for offline simulation and unit testing

Credits & Attribution:
Built upon reverse-engineering research and protocol contributions by CM-P,
Hajo Noerenberg (hn / cmd2jura), Jutta-Proto, makefu (jura-connect), AlexxIT,
Otto Winter (ESPHome), Google Antigravity (Agy / DeepMind), and the open-source hardware community.
"""

import time
import re
from typing import Optional, Tuple, Dict, List, Any

# Recovered S-Boxes from reverse-engineering of Jura Smart Connect protocol
SBOX_N1 = [8, 14, 12, 4, 3, 13, 10, 11, 0, 15, 6, 7, 2, 5, 1, 9]
SBOX_N2 = [4, 11, 13, 10, 0, 7, 15, 5, 9, 8, 3, 1, 14, 2, 12, 6]

RESERVED_BYTES = {0x00, 0x0A, 0x0D, 0x1B, 0x26}

# ============================================================================
# 1. Physical 4:1 Line Encoding / Decoding
# ============================================================================

def encode_wire_byte(val: int) -> bytes:
    """Encode 1 payload byte into 4 UART carrier bytes."""
    out = bytearray(4)
    for i in range(4):
        b0 = (val >> (2 * i)) & 1
        b1 = (val >> (2 * i + 1)) & 1
        out[i] = 0xDB | (b0 << 2) | (b1 << 5)
    return bytes(out)

def encode_wire(data: bytes) -> bytes:
    """Encode a sequence of bytes into 4:1 UART wire format."""
    out = bytearray()
    for b in data:
        out.extend(encode_wire_byte(b))
    return bytes(out)

def decode_wire(raw: bytes) -> Tuple[bytes, bytes]:
    """
    Decode 4:1 UART carrier bytes into payload bytes.
    Returns (decoded_bytes, remaining_unprocessed_raw_bytes).
    """
    decoded = bytearray()
    num_complete_groups = len(raw) // 4
    for g in range(num_complete_groups):
        b = 0
        for i in range(4):
            r = raw[g * 4 + i]
            # Valid Jura carrier bytes have bits 0, 1, 3, 4, 6 high (0x5B mask)
            bit0 = (r >> 2) & 1
            bit1 = (r >> 5) & 1
            chunk = bit0 | (bit1 << 1)
            b |= (chunk << (2 * i))
        decoded.append(b)
    remainder = raw[num_complete_groups * 4:]
    return bytes(decoded), remainder

# ============================================================================
# 2. Nibble-Permutation Cipher & Framing
# ============================================================================

def _shuffle(nib: int, pos: int, key: int) -> int:
    ta = key >> 4
    tm = key & 15
    i5 = (pos >> 4) & 15
    a = SBOX_N1[((nib + pos + ta) % 16 + 16) % 16]
    inner = ((i5 + a + tm - pos - ta) % 16 + 16) % 16
    outer = ((SBOX_N2[inner] + ta + pos - tm - i5) % 16 + 16) % 16
    return ((SBOX_N1[outer] - pos - ta) % 16 + 16) % 16

def crypt(data: bytes, key: int) -> bytes:
    """Self-inverse per-nibble transform (crypt(crypt(m, k), k) == m)."""
    out = bytearray(len(data))
    for i, b in enumerate(data):
        high = _shuffle(b >> 4, 2 * i, key)
        low = _shuffle(b & 15, 2 * i + 1, key)
        out[i] = (high << 4) | low
    return bytes(out)

def escape_frame(data: bytes) -> bytes:
    """Escape reserved control bytes with 0x1B prefix."""
    out = bytearray()
    for b in data:
        if b in RESERVED_BYTES:
            out.append(0x1B)
            out.append(b ^ 0x80)
        else:
            out.append(b)
    return bytes(out)

def unescape_frame(data: bytes) -> bytes:
    """Unescape bytes prefixed with 0x1B."""
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0x1B and i + 1 < len(data):
            i += 1
            out.append(data[i] ^ 0x80)
        else:
            out.append(data[i])
        i += 1
    return bytes(out)

def build_encrypted_frame(plaintext: str, key: int = 0x2A) -> bytes:
    """
    Wrap plaintext command into '&' <key> <escaped(cipher(payload))> CRLF.
    """
    if not plaintext.endswith("\r\n"):
        plaintext += "\r\n"
    raw_pt = plaintext.encode("ascii", errors="replace")
    body = bytearray([key])
    body.extend(crypt(raw_pt, key))
    return b"&" + escape_frame(bytes(body)) + b"\r\n"

def decode_encrypted_frame(frame: bytes) -> Optional[str]:
    """
    Decode received '&' frame back to plaintext command.
    """
    clean = frame.strip(b"\r\n")
    if not clean.startswith(b"&") or len(clean) < 2:
        return None
    body = unescape_frame(clean[1:])
    if not body:
        return None
    key = body[0]
    payload = crypt(body[1:], key)
    try:
        return payload.decode("ascii", errors="replace")
    except Exception:
        return None

# ============================================================================
# 3. Protocol Parser Helpers
# ============================================================================

def parse_tr32(plain: str) -> Optional[Tuple[int, List[int]]]:
    """
    Parse @tr:32,NN,WWWWWWWWWWWWWWWW
    Returns (bank_number, [word0, word1, word2, word3])
    """
    clean = plain.strip()
    m = re.match(r"^@tr:32,([0-9A-Fa-f]{2}),([0-9A-Fa-f]+)$", clean)
    if not m:
        return None
    bank = int(m.group(1), 16)
    hex_str = m.group(2)
    words = []
    for i in range(0, len(hex_str), 4):
        chunk = hex_str[i:i+4]
        if len(chunk) == 4:
            words.append(int(chunk, 16))
    return bank, words

def parse_tg43(plain: str) -> Optional[List[int]]:
    """
    Parse @tg:43WWWWWWWWWWWW... (6 16-bit words for maintenance counters)
    """
    clean = plain.strip()
    m = re.match(r"^@tg:43([0-9A-Fa-f]+)$", clean)
    if not m:
        return None
    hex_str = m.group(1)
    words = []
    for i in range(0, len(hex_str), 4):
        chunk = hex_str[i:i+4]
        if len(chunk) == 4:
            words.append(int(chunk, 16))
    return words

def parse_tgc0(plain: str) -> Optional[List[int]]:
    """
    Parse @tg:C0BBBBBB... (1-byte values for maintenance percentages)
    """
    clean = plain.strip()
    m = re.match(r"^@tg:[Cc]0([0-9A-Fa-f]+)$", clean)
    if not m:
        return None
    hex_str = m.group(1)
    bytes_list = []
    for i in range(0, len(hex_str), 2):
        chunk = hex_str[i:i+2]
        if len(chunk) == 2:
            val = int(chunk, 16)
            bytes_list.append(min(val, 100))
    return bytes_list

def parse_tf(plain: str) -> Optional[bytes]:
    """
    Parse @TF:<hex> alert/status bitfield
    """
    clean = plain.strip()
    m = re.match(r"^@TF:([0-9A-Fa-f]+)$", clean, re.I)
    if not m:
        return None
    hex_str = m.group(1)
    try:
        return bytes.fromhex(hex_str)
    except Exception:
        return None

# ============================================================================
# 4. Mock Jura Machine (High-Fidelity Offline Simulator)
# ============================================================================

class MockJuraMachine:
    """
    Simulates a modern Jura Coffee Machine (e.g., S8, E8, Z10) on a serial stream.
    Understands 4:1 line encoding, '&' encrypted frames, handshake, and telemetry queries.
    """
    def __init__(self, model_ef: str = "EF536M V02.01", model_name: str = "S8"):
        self.model_ef = model_ef
        self.model_name = model_name
        self.rx_buffer = bytearray()
        self.handshake_stage = 0
        self.counters = {
            0: 8420,   # Grand Total
            1: 14,     # Ristretto
            2: 320,    # Espresso
            3: 6810,   # Coffee
            4: 215,    # Cappuccino
            5: 84,     # Milkcoffee
            6: 62,     # Espresso Macchiato
            7: 490,    # Latte Macchiato
            8: 55,     # Milk Foam
            10: 22,    # Milk Portion
            13: 130,   # Hot Water
            17: 0,     # 2 Ristretti
            18: 0,     # 2 Espressi
            19: 0,     # 2 Coffees
            45: 42,    # Hot Water Green Tea
            46: 176,   # Flat White
        }
        # Maintenance counters: Cleaning, FilterChange, Decalc, CappuRinse, CoffeeRinse, CappuClean
        self.maint_counters = [184, 2, 41, 350, 4120, 95]
        # Maintenance percentages: Cleaning %, Filter %, Decalc %
        self.maint_percentages = [85, 25, 95]
        # Active status alerts bitfield: bit 13 = coffee ready
        # Bit 13 is in byte 1 (13 >> 3 = 1), bit (7 - (13 & 7)) = bit 2 -> 0x04
        self.alert_bytes = bytes.fromhex("000400000000")

    def process_input(self, raw_bytes: bytes) -> bytes:
        """Feed incoming wire bytes from client and return wire reply bytes."""
        self.rx_buffer.extend(raw_bytes)
        tx_out = bytearray()

        while True:
            decoded, _ = decode_wire(bytes(self.rx_buffer))
            crlf_pos = decoded.find(b"\r\n")
            if crlf_pos == -1:
                break

            frame = decoded[:crlf_pos + 2]
            # Advance raw buffer by 4 * len(frame)
            raw_len = len(frame) * 4
            self.rx_buffer = self.rx_buffer[raw_len:]

            reply = self._handle_frame(frame)
            if reply:
                tx_out.extend(encode_wire(reply))

        return bytes(tx_out)

    def _handle_frame(self, frame: bytes) -> Optional[bytes]:
        # Check if encrypted '&' frame
        if frame.startswith(b"&"):
            plain = decode_encrypted_frame(frame)
            if not plain:
                return None
            clean_cmd = plain.strip()

            # Handshake
            if clean_cmd == "@T0":
                self.handshake_stage = 1
                return build_encrypted_frame("@t0\r\n", 0x30)
            elif clean_cmd == "@T1":
                self.handshake_stage = 2
                # Return challenge @T2:01C000
                return build_encrypted_frame("@T2:01C000\r\n", 0x31)
            elif clean_cmd.startswith("@t2:"):
                self.handshake_stage = 3
                # Return model string
                return build_encrypted_frame(f"@T3:3C16{self.model_ef}\r\n", 0x32)
            elif clean_cmd == "@t3":
                self.handshake_stage = 4
                return None  # ack done

            # Product counter banks @TR:32,NN
            m_tr = re.match(r"^@TR:32,([0-9A-Fa-f]{2})", clean_cmd)
            if m_tr:
                bank = int(m_tr.group(1), 16)
                words = []
                for idx in range(4):
                    code = bank * 4 + idx
                    val = self.counters.get(code, 0xFFFF)
                    words.append(f"{val:04X}")
                resp_str = f"@tr:32,{bank:02X}," + "".join(words) + "\r\n"
                return build_encrypted_frame(resp_str, 0x40 + bank)

            # Maintenance counters @TG:43
            if clean_cmd == "@TG:43":
                words = "".join(f"{w:04X}" for w in self.maint_counters)
                return build_encrypted_frame(f"@tg:43{words}\r\n", 0x55)

            # Maintenance percentages @TG:C0
            if clean_cmd in ("@TG:C0", "@TG:c0"):
                hex_vals = "".join(f"{v:02X}" for v in self.maint_percentages)
                return build_encrypted_frame(f"@tg:C0{hex_vals}\r\n", 0x56)

            # Alerts @TF:
            if clean_cmd == "@TF:":
                return build_encrypted_frame(f"@TF:{self.alert_bytes.hex()}\r\n", 0x57)

        # Cleartext fallback (TY:)
        decoded_text = frame.decode("ascii", errors="ignore").strip()
        if decoded_text == "TY:":
            return f"ty:{self.model_ef}\r\n".encode("ascii")

        return None
