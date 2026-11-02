pub struct JetinnoProtocol;

impl JetinnoProtocol {
    /// Computes Jetinno CRC-16 checksum (CCITT polynomial 0x1021, initial 0xFFFF, big-endian)
    pub fn compute_crc(data: &[u8]) -> [u8; 2] {
        let mut crc: u16 = 0xFFFF;
        for &byte in data {
            crc ^= (byte as u16) << 8;
            for _ in 0..8 {
                if (crc & 0x8000) != 0 {
                    crc = (crc << 1) ^ 0x1021;
                } else {
                    crc <<= 1;
                }
            }
        }
        crc.to_be_bytes()
    }

    /// Validates Jetinno packet CRC-16
    pub fn verify_crc(packet: &[u8]) -> bool {
        if packet.len() < 4 {
            return false;
        }
        let payload = &packet[..packet.len() - 2];
        let expected = &packet[packet.len() - 2..];
        Self::compute_crc(payload) == expected
    }

    /// Builds a standard Jetinno 0xFE packet: [0xFE, board_id, flags (0x00), cmd, payload..., CRC16_High, CRC16_Low]
    pub fn build_packet(board_id: u8, cmd: u8, payload: &[u8]) -> Vec<u8> {
        let mut packet = Vec::with_capacity(4 + payload.len() + 2);
        packet.push(0xFE);
        packet.push(board_id);
        packet.push(0x00);
        packet.push(cmd);
        packet.extend_from_slice(payload);
        let crc = Self::compute_crc(&packet);
        packet.extend_from_slice(&crc);
        packet
    }

    pub fn lookup_fault(hex_code: &str) -> Option<(&'static str, &'static str)> {
        match hex_code {
            "0080" => Some(("Mixer Motor 1 Short Circuit", "Whip mixer 1 electrical short detected")),
            "0088" => Some(("Mixer Motor 1 Blocked", "Instant mixer bowl impeller mechanical jam")),
            "0180" => Some(("Mixer Motor 2 Short Circuit", "Whip mixer 2 electrical short detected")),
            "0188" => Some(("Mixer Motor 2 Blocked", "Instant mixer 2 impeller jammed")),
            "0680" => Some(("Air Pump Short Circuit", "Milk/crema air assist pump shorted")),
            "0688" => Some(("Air Pump Blocked", "Air induction line clogged")),
            "0880" => Some(("Canister Motor 1 Short Circuit", "Powder dosing auger 1 short circuit")),
            "0888" => Some(("Canister Motor 1 Blocked", "Powder canister dosing auger jammed")),
            "1001" => Some(("Coffee Boiler Heating Failure", "Coffee pressure boiler heating timeout")),
            "1002" => Some(("Coffee Boiler NTC Sensor Open", "Boiler thermistor open or disconnected")),
            "1003" => Some(("Boiler Refill Timeout", "Hydraulic inlet solenoid open time exceeded; low water pressure")),
            "2001" => Some(("ES Brewer Position Timeout", "Espresso brewer drive motor position sensor timeout")),
            "2002" => Some(("ES Brewer Jammed", "Brewer piston mechanical overload during compaction")),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jetinno_frame_builder_and_crc() {
        let frame = JetinnoProtocol::build_packet(0x01, 0x14, &[0x00, 0x00]);
        assert_eq!(frame.len(), 8);
        assert_eq!(frame[0], 0xFE);
        assert_eq!(frame[1], 0x01);
        assert_eq!(frame[2], 0x00);
        assert_eq!(frame[3], 0x14);
        assert_eq!(&frame[4..6], &[0x00, 0x00]);

        assert!(JetinnoProtocol::verify_crc(&frame));
        let mut corrupt = frame.clone();
        corrupt[2] ^= 0xFF;
        assert!(!JetinnoProtocol::verify_crc(&corrupt));
    }

    #[test]
    fn test_jetinno_fault_lookup() {
        let (name, desc) = JetinnoProtocol::lookup_fault("1001").expect("1001");
        assert_eq!(name, "Coffee Boiler Heating Failure");
        assert!(desc.contains("heating timeout"));
    }
}
