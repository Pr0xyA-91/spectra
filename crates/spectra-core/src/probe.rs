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
            if let Some(next_addr) = addr.checked_add(1) {
                if let Some(&low_val) = eeprom.get(&next_addr) {
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
    }

    results
}

/// Scores a candidate EEPROM register address against canonical regions for a counter category.
pub fn score_address_for_category(addr: u16, category: &str) -> u32 {
    match category {
        "product" => {
            if (0x0180..=0x018F).contains(&addr) || addr == 0x017F {
                100
            } else if (0x0330..=0x033F).contains(&addr) {
                95
            } else if (0x0001..=0x0006).contains(&addr) {
                90
            } else if (0x00E0..=0x00E6).contains(&addr) {
                80
            } else {
                10
            }
        }
        "maintenance" => {
            if (0x0007..=0x0009).contains(&addr) {
                100
            } else if (0x0020..=0x0022).contains(&addr) {
                95
            } else if addr == 0x000E || addr == 0x0014 {
                90
            } else {
                10
            }
        }
        "cockpit" if (0x0160..=0x016F).contains(&addr) || (0x01E0..=0x01EF).contains(&addr) => 100,
        _ => 10,
    }
}

/// Sweeps `eeprom` for matching addresses in the given category (`"product"`, `"maintenance"`,
/// or `"cockpit"` percentage byte match), returning candidate addresses ordered highest score first.
pub fn correlate_value_addresses_ranked(
    eeprom: &HashMap<u16, u16>,
    target_value: u32,
    category: &str,
) -> Vec<u16> {
    if target_value == 0 {
        return Vec::new();
    }
    let mut matches: Vec<u16> = Vec::new();
    if category == "cockpit" {
        if target_value > 0xFF {
            return matches;
        }
        let pct = target_value as u16;
        for (&addr, &val) in eeprom {
            if (val & 0xFF) == pct || ((val >> 8) & 0xFF) == pct {
                matches.push(addr);
            }
        }
    } else if target_value <= 0xFFFF {
        let target_u16 = target_value as u16;
        for (&addr, &val) in eeprom {
            if val == target_u16 {
                matches.push(addr);
            }
        }
    }
    matches.sort_by(|&a, &b| {
        score_address_for_category(b, category)
            .cmp(&score_address_for_category(a, category))
            .then_with(|| a.cmp(&b))
    });
    matches
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

        // Verify ranked category correlation
        let mut ranked_eeprom = HashMap::new();
        ranked_eeprom.insert(0x0002, 42);
        ranked_eeprom.insert(0x0182, 42);
        ranked_eeprom.insert(0x01E4, 0x1E35); // 0x35 = 53%
        let prod_ranked = correlate_value_addresses_ranked(&ranked_eeprom, 42, "product");
        assert_eq!(prod_ranked, vec![0x0182, 0x0002]);
        let pct_ranked = correlate_value_addresses_ranked(&ranked_eeprom, 53, "cockpit");
        assert_eq!(pct_ranked, vec![0x01E4]);
    }
}
