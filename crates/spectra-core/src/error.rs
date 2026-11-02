use spectra_hal::HalError;
use thiserror::Error;

#[derive(Error, Debug, PartialEq)]
pub enum CoreError {
    #[error("HAL transport error: {0}")]
    Hal(String),

    #[error("Safety violation: prohibited write/reset command '{0}' on read-only hardware port")]
    SafetyViolation(String),

    #[error("Invalid command syntax or addressing: {0}")]
    InvalidCommand(String),

    #[error("Response framing or header mismatch: expected '{expected}', got '{actual}'")]
    ResponseFraming { expected: String, actual: String },

    #[error("Parse failure for register {field}: raw '{raw}'")]
    ParseError { field: String, raw: String },

    #[error("Checksum error: calculated {calc:#06x}, received {recv:#06x}")]
    ChecksumMismatch { calc: u16, recv: u16 },
}

impl From<HalError> for CoreError {
    fn from(err: HalError) -> Self {
        CoreError::Hal(err.to_string())
    }
}
