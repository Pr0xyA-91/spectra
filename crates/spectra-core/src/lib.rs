pub mod error;
pub mod jetinno;
pub mod jura;
pub mod kalerm;
pub mod nivona;
pub mod probe;

pub use error::CoreError;
pub use jetinno::JetinnoProtocol;
pub use jura::{
    diff_eeprom_blocks, AddressingMode, BeansState, BoardFamily, EepromWordDiff,
    HzTelemetryFrame, JuraClient, JuraCommand, JuraProtocol, JuraResponse, OpticalSensorReading,
    SmartConnectCipher,
};
pub use kalerm::KalermProtocol;
pub use nivona::{NivonaFault, NivonaProtocol};
pub use probe::{correlate_with_joe_export, CorrelationCandidate};

pub type CoreResult<T> = Result<T, error::CoreError>;
