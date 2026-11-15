pub mod error;
pub mod hmi_elf;
pub mod jetinno;
pub mod jura;
pub mod kalerm;
pub mod machine_library;
pub mod nivona;
pub mod probe;

pub use error::CoreError;
pub use hmi_elf::{
    detect_bipartite_token_swaps, encode_arm_movw_movt, find_free_zero_padding,
    has_arm_movw_movt_any_reg, repoint_arm_movw_movt_all_regs, scan_rodata_orphaned_string,
};
pub use jetinno::JetinnoProtocol;
pub use jura::{
    decode_jura_date_word, decode_jura_temperature_word, diff_eeprom_blocks, AddressingMode,
    BeansState, BoardFamily, EepromWordDiff, HzTelemetryFrame, JuraClient, JuraCommand,
    JuraProtocol, JuraResponse, OpticalSensorReading, SmartConnectCipher,
};
pub use kalerm::KalermProtocol;
pub use machine_library::{matches_connected_machine, normalize_ef_code};
pub use nivona::{NivonaFault, NivonaProtocol};
pub use probe::{
    correlate_value_addresses_ranked, correlate_with_joe_export, CorrelationCandidate,
};

pub type CoreResult<T> = Result<T, error::CoreError>;
