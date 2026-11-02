use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NivonaFault {
    pub code: u8,
    pub name: String,
    pub is_critical: bool,
    pub description: String,
}

pub struct NivonaProtocol;

impl NivonaProtocol {
    pub fn lookup_fault(code: u8) -> Option<NivonaFault> {
        let (name, crit, desc) = match code {
            1 => ("Thermoblock NTC Sensor Short/Open", true, "Temperature sensor coffee heater disconnected or defective"),
            2 => ("Steam Heater NTC Sensor Short/Open", true, "Secondary heater sensor disconnected or defective"),
            3 => ("Ceramic Valve NTC Sensor Defective", false, "Multiway valve temperature sensor faulty"),
            5 => ("Thermoblock Heating Timeout", true, "Coffee heater failed to reach operating temperature within timeout"),
            7 => ("NTC Sensor Malfunction", false, "Abnormal temperature delta or sensor curve mismatch"),
            8 => ("Brew Unit Blocked / Encoder Fault", true, "Brew group mechanical jamming or motor microswitch failure"),
            9 => ("Multi-way Valve Position Error", true, "Ceramic multi-way valve failed to index to target port"),
            10 => ("Main Electronic Communication Error", true, "UART / I2C bus communication timeout on logic board"),
            20 => ("Brew Unit Drive Bus Failure", true, "No communication with brewing unit motor controller"),
            21 => ("Brew Unit Travel Time Exceeded", false, "Brew group drive took too long to complete cycle"),
            _ => return None,
        };
        Some(NivonaFault {
            code,
            name: name.into(),
            is_critical: crit,
            description: desc.into(),
        })
    }

    pub fn match_model(raw_ident: &str) -> Option<String> {
        let clean = raw_ident.to_lowercase();
        if clean.contains("nicr 520") || clean.contains("nicr 530") || clean.contains("0520") {
            Some("Nivona CafeRomatica 520 / 530".into())
        } else if clean.contains("0698") || clean.contains("768") || clean.contains("778") || clean.contains("788") {
            Some("Nivona CafeRomatica 768 / 778 / 788".into())
        } else if clean.contains("0757") || clean.contains("757") {
            Some("Nivona CafeRomatica 757".into())
        } else if clean.contains("0758") || clean.contains("758") {
            Some("Nivona CafeRomatica 758".into())
        } else if clean.contains("0841") || clean.contains("841") {
            Some("Nivona CafeRomatica 841".into())
        } else if clean.contains("0960") || clean.contains("960") {
            Some("Nivona CafeRomatica 960".into())
        } else if clean.contains("1030") || clean.contains("1040") {
            Some("Nivona CafeRomatica 1030 / 1040".into())
        } else if clean.contains("8101") || clean.contains("8103") || clean.contains("ef1040") {
            Some("Nivona NIVO 8101 / 8103".into())
        } else if clean.contains("nicr") || clean.contains("nivo") {
            Some(format!("Nivona CafeRomatica ({raw_ident})"))
        } else {
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_nivona_fault_lookup() {
        let f8 = NivonaProtocol::lookup_fault(8).expect("fault 8");
        assert_eq!(f8.name, "Brew Unit Blocked / Encoder Fault");
        assert!(f8.is_critical);

        let f21 = NivonaProtocol::lookup_fault(21).expect("fault 21");
        assert_eq!(f21.name, "Brew Unit Travel Time Exceeded");
        assert!(!f21.is_critical);

        assert!(NivonaProtocol::lookup_fault(99).is_none());
    }

    #[test]
    fn test_nivona_model_matching() {
        assert_eq!(
            NivonaProtocol::match_model("NICR 778 V02").unwrap(),
            "Nivona CafeRomatica 768 / 778 / 788"
        );
        assert_eq!(
            NivonaProtocol::match_model("NIVO 8101 V01").unwrap(),
            "Nivona NIVO 8101 / 8103"
        );
    }
}
