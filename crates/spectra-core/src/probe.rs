use std::collections::HashMap;
use serde::{Deserialize, Serialize};

pub use crate::jura::{diff_eeprom_blocks, EepromWordDiff};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CorrelationCandidate {
    pub beverage_name: String,
    pub ground_truth_count: u32,
    pub matched_address: u16,
    pub matched_value: u32,
    pub is_32bit_counter: bool,
}

/// Correlates J.O.E. app CSV ground-truth counts against raw EEPROM words.
/// Sweeps both 16-bit single words and reconstructed 32-bit big-endian double words.
pub fn correlate_with_joe_export(
    eeprom: &HashMap<u16, u16>,
    joe_counts: &HashMap<String, u32>,
) -> Vec<CorrelationCandidate> {
    let mut results = Vec::new();

    for (name, &target_count) in joe_counts {
        if target_count == 0 {
            continue; // Skip zero counts to avoid massive false-positive noise
        }

        // 1. Direct 16-bit match
        if target_count <= 0xFFFF {
            let target_u16 = target_count as u16;
            for (&addr, &val) in eeprom {
                if val == target_u16 {
                    results.push(CorrelationCandidate {
                        beverage_name: name.clone(),
                        ground_truth_count: target_count,
                        matched_address: addr,
                        matched_value: val as u32,
                        is_32bit_counter: false,
                    });
                }
            }
        }

        // 2. 32-bit big-endian double-word match (e.g. GIGA / Commercial lines)
        for (&addr, &high_val) in eeprom {
            if let Some(&low_val) = eeprom.get(&(addr + 1)) {
                let combined = ((high_val as u32) << 16) | (low_val as u32);
                if combined == target_count {
                    results.push(CorrelationCandidate {
                        beverage_name: name.clone(),
                        ground_truth_count: target_count,
                        matched_address: addr,
                        matched_value: combined,
                        is_32bit_counter: true,
                    });
                }
            }
        }
    }

    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_correlate_with_joe_export_16bit_and_32bit() {
        let mut eeprom = HashMap::new();
        eeprom.insert(0x0180, 1450); // Espresso
        eeprom.insert(0x0181, 137);  // Ristretto
        eeprom.insert(0x00E9, 0x0002); // 32-bit retail high
        eeprom.insert(0x00EA, 0x0010); // 32-bit retail low -> (2 << 16) | 16 = 131088

        let mut joe = HashMap::new();
        joe.insert("Espresso".to_string(), 1450);
        joe.insert("Ristretto".to_string(), 137);
        joe.insert("Retail Cups".to_string(), 131088);
        joe.insert("Zero Count Drink".to_string(), 0);

        let matches = correlate_with_joe_export(&eeprom, &joe);
        assert_eq!(matches.len(), 3);

        let esp = matches.iter().find(|m| m.beverage_name == "Espresso").unwrap();
        assert_eq!(esp.matched_address, 0x0180);
        assert!(!esp.is_32bit_counter);

        let retail = matches.iter().find(|m| m.beverage_name == "Retail Cups").unwrap();
        assert_eq!(retail.matched_address, 0x00E9);
        assert!(retail.is_32bit_counter);
    }
}
