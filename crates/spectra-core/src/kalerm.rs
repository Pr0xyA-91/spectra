pub struct KalermProtocol;

impl KalermProtocol {
    /// Computes Modbus RTU 16-bit CRC (polynomial 0xA001, initial 0xFFFF, little-endian)
    pub fn compute_crc(data: &[u8]) -> [u8; 2] {
        let mut crc: u16 = 0xFFFF;
        for &byte in data {
            crc ^= byte as u16;
            for _ in 0..8 {
                if (crc & 0x0001) != 0 {
                    crc = (crc >> 1) ^ 0xA001;
                } else {
                    crc >>= 1;
                }
            }
        }
        crc.to_le_bytes()
    }

    /// Validates Modbus RTU packet checksum
    pub fn verify_crc(packet: &[u8]) -> bool {
        if packet.len() < 4 {
            return false;
        }
        let payload = &packet[..packet.len() - 2];
        let expected = &packet[packet.len() - 2..];
        Self::compute_crc(payload) == expected
    }

    /// Builds a Modbus RTU Read Holding Registers packet (Function 0x03)
    pub fn build_read_holding_registers(slave_addr: u8, start_reg: u16, count: u16) -> Vec<u8> {
        let mut frame = Vec::with_capacity(8);
        frame.push(slave_addr);
        frame.push(0x03);
        frame.extend_from_slice(&start_reg.to_be_bytes());
        frame.extend_from_slice(&count.to_be_bytes());
        let crc = Self::compute_crc(&frame);
        frame.extend_from_slice(&crc);
        frame
    }

    /// Builds a Modbus RTU Read Input Registers packet (Function 0x04)
    pub fn build_read_input_registers(slave_addr: u8, start_reg: u16, count: u16) -> Vec<u8> {
        let mut frame = Vec::with_capacity(8);
        frame.push(slave_addr);
        frame.push(0x04);
        frame.extend_from_slice(&start_reg.to_be_bytes());
        frame.extend_from_slice(&count.to_be_bytes());
        let crc = Self::compute_crc(&frame);
        frame.extend_from_slice(&crc);
        frame
    }

    pub fn lookup_fault(code: u8) -> Option<(&'static str, &'static str)> {
        match code {
            1 => Some(("Flowmeter Timeout (E01)", "No water pulse detected during brewing or filling loop")),
            2 => Some(("Coffee Boiler NTC Error (E02)", "Coffee heater temperature sensor open or short-circuited")),
            3 => Some(("Steam Boiler NTC Error (E03)", "Steam boiler temperature sensor open or short-circuited")),
            4 => Some(("Coffee Boiler Heating Timeout (E04)", "Coffee thermoblock failed to reach target temperature in time")),
            5 => Some(("Steam Boiler Heating Timeout (E05)", "Steam generator failed to reach target temperature in time")),
            6 => Some(("Brew Unit Up Timeout (E06)", "Brew group failed to reach upper compression switch")),
            7 => Some(("Brew Unit Down Timeout (E07)", "Brew group failed to reach home ejection switch")),
            8 => Some(("Ceramic Valve Position Fault (E08)", "Multi-way distribution valve failed to find index position")),
            9 => Some(("Grinder Overcurrent (E09)", "Grinder motor current exceeded safety limit")),
            10 => Some(("Main MCU Communication Fault (E10)", "HMI to power board serial bus communication failure")),
            11 => Some(("Overpressure Safety Cutoff (E11)", "Hydraulic line pressure relief valve triggered")),
            12 => Some(("Drip Tray Full Level Active (E12)", "Waste wastewater tray full level probe bridged")),
            15 => Some(("Drip Tray Removed During Cycle (E15)", "Drip tray was removed while machine was dispensing or cleaning")),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kalerm_crc_computation_and_verification() {
        // Modbus query: slave 0x01, func 0x03, addr 0x0000, count 0x000A -> CRC is 0xC5CD (LE: CD C5)
        let frame = KalermProtocol::build_read_holding_registers(0x01, 0x0000, 0x000A);
        assert_eq!(frame.len(), 8);
        assert_eq!(frame[0], 0x01);
        assert_eq!(frame[1], 0x03);
        assert_eq!(frame[2], 0x00);
        assert_eq!(frame[3], 0x00);
        assert_eq!(frame[4], 0x00);
        assert_eq!(frame[5], 0x0A);
        assert_eq!(frame[6], 0xC5);
        assert_eq!(frame[7], 0xCD);

        assert!(KalermProtocol::verify_crc(&frame));
        let mut corrupt = frame.clone();
        corrupt[3] ^= 0x01;
        assert!(!KalermProtocol::verify_crc(&corrupt));
    }

    #[test]
    fn test_kalerm_fault_lookup() {
        let (name, desc) = KalermProtocol::lookup_fault(1).expect("E01");
        assert_eq!(name, "Flowmeter Timeout (E01)");
        assert!(desc.contains("water pulse"));
    }
}
