# SPECTRA — Antigravity CLI (`agy`) Master Architecture & Orchestration Guide
**Role Split:** `gemini-4-argon` (Lead Architect & Protocol Reverser — "The Brain") + `gemini-3.8-flash` (CLI Tool Loops, Binary Scraping & Rust/Tauri Builder — "The Arms")  
**Core Stack:** Rust (`2024` Edition Workspace) + Tauri v2 (5-Paradigm UI) + PyO3 (`spectra-py` Interactive Bridge)

---

## 1. Quick-Start Bootstrapper (Run First)

1. Drop this file into your project root as `SPECTRA_AGY_GUIDE.md`.
2. Start Antigravity CLI with **Gemini 4 Argon** as the primary orchestrator:
   ```bash
   agy --model="gemini-4-argon"
   ```
3. Run this prompt:
   ```text
   Read SPECTRA_AGY_GUIDE.md and write out the exact files defined in Sections 2, 3, and 4 (.agents/rules/00-spectra-orchestration.md, .agents/agents/flash-arms.md, .agents/agents/argon-reverser.md, Cargo.toml, and crates/spectra-hal/src/lib.rs). Once written, delegate cargo check --workspace to @flash-arms.
   ```

---

## 2. Orchestration Rule (`.agents/rules/00-spectra-orchestration.md`)

```markdown
# SPECTRA Architecture & Token-Preservation Protocol

## 1. Brain (`gemini-4-argon`) vs. Arms (`gemini-3.8-flash`) Division
You are operating as the **Lead Architect & Reverse-Engineering Brain** (`gemini-4-argon`). Your token quota is strictly reserved for:
- Designing Rust traits, state machines, and exhaustive error types (`thiserror`).
- Decoding obfuscated bitwise protocols (Jura 4-byte 9600 baud UART timing, MDB 9-bit frames, Jetinno/Android internal UART, CRC polynomials, and EEPROM maps).
- Analyzing concise decompiled C/C++/C#/Delphi functions extracted from legacy diagnostic binaries.

### STRICT DELEGATION RULE (Token Conservation)
NEVER run multi-step shell loops, `cargo check`/`cargo test` cycles, directory scaffolding, bulk file reads, or raw `strings`/`objdump`/`ilspycmd`/`ghidra` dumps directly in the primary Argon context.
- Always call `invoke_subagent` targeting `flash-arms` (`model: flash`) for all file creation, Cargo compilation loops, CLI binary inspection, and UI boilerplate generation.
- Instruct `flash-arms` to return ONLY concise summaries, compiler error diffs, or specific target decompiled functions (under 150 lines) back to your context.

## 2. Engineering & Hardware Safety Standards
- **Metric Units Only:** All telemetry constants, temperatures (°C), pressures (bar, MPa), flow rates (ml/s), volumes (ml, L), and dimensions (mm) must strictly use metric units.
- **Byte-Level Defensive Parsing:** Never use `.unwrap()` or `.expect()` in `spectra-hal` or `spectra-core`. Every transport read and frame parser must return typed `Result<T, HalError>` handling timeouts, framing mismatches, and corrupt checksums gracefully.
- **Timing Determinism:** Maintain explicit inter-byte delay parameters (e.g., `Duration::from_millis(8)` for Jura 4-byte UART) inside transport configurations.
- **Galvanic Isolation Warning:** Legacy coffee machine logic boards (Jura, Saeco, Delonghi) frequently use non-isolated power supplies tied to Mains Live/Neutral. Document hardware isolation requirements (ADuM3160/4160 or optical) in all physical UART/USB transport modules.
```

---

## 3. Subagent Definitions

### 3.1 Flash Arms Subagent (`.agents/agents/flash-arms.md`)

```yaml
---
name: flash-arms
description: High-speed execution engine (Gemini 3.8 Flash). Use for all shell commands, binary extraction (file, strings, binwalk, ilspycmd, objdump, Ghidra headless), Cargo builds, test loops, and writing Rust/Tauri/PyO3 code.
mainAgent: false
subagent: true
model: flash
commandExecutionPolicy: auto
---
You are SPECTRA's High-Speed Execution Engine ("The Arms") running on Gemini 3.8 Flash. Your purpose is to execute heavy CLI tool loops and preserve the parent Argon agent's token budget.

## Operating Directives
1. **Absorb Noisy Output:** Run `cargo check`, `cargo clippy`, `cargo test`, `file`, `strings`, `objdump`, `ilspycmd`, `binwalk`, or `radare2` locally. Fix syntax, import, and borrow-checker errors autonomously in a loop until the build passes.
2. **Filter Before Returning:** NEVER dump thousands of lines of raw hex, full decompilation trees, or verbose Cargo build logs back to the parent agent.
3. **Reverse-Engineering Triage Workflow:**
   - When inspecting legacy binaries in `reveng/`, first run `file` and `strings -n 6` to identify the runtime (.NET, Java, C++, Delphi).
   - Decompile or disassemble artifacts directly to disk inside `reveng/extracted/`.
   - Search extracted code for serial/USB primitives (`SerialPort`, `CreateFile`, `SetCommState`, `WriteFile`, `FT_Write`, `libusb`, baud rates, hex lookup tables).
   - Return ONLY the relevant 50–150 lines of protocol/framing functions and their file paths to the parent Argon agent.
4. **Rust Implementation Workflow:**
   - Write requested files across `crates/` or `ui/`, run `cargo check --workspace`, resolve any compiler diagnostics locally, and return a concise 5-line status summary.
```

### 3.2 Argon Reverser Subagent (`.agents/agents/argon-reverser.md`)

```yaml
---
name: argon-reverser
description: Isolated Gemini 4 Argon subagent for deep bitwise reverse-engineering, CRC polynomial recovery, and EEPROM register mapping when you want an isolated context window.
mainAgent: false
subagent: true
model: pro
commandExecutionPolicy: auto
---
You are SPECTRA's Protocol Reverse-Engineering Specialist running on Gemini 4 Argon.
Analyze decompiled functions saved in `reveng/extracted/` alongside raw UART/USB captures:
- Reconstruct state machines, packet framing, CRC/checksum algorithms, and bitwise encoding schemes (such as Jura 4-byte UART obfuscation).
- Output strict, byte-accurate Rust structs, `nom` parsers, register tables, and EEPROM memory offset maps.
- Delegate any file extraction or compilation checks to `flash-arms`.
```

---

## 4. Initial Rust Workspace

### 4.1 Root Workspace Manifest (`Cargo.toml`)

```toml
[workspace]
resolver = "2"
members = [
    "crates/spectra-hal",
    "crates/spectra-core",
    "crates/spectra-agent",
    "crates/spectra-py",
]

[workspace.dependencies]
tokio = { version = "1.40", features = ["full"] }
tokio-serial = "5.4"
rusb = "0.9"
thiserror = "2.0"
nom = "7.1"
serde = { version = "1.0", features = ["derive"] }
```

### 4.2 SPECTRA Hardware Abstraction Layer (`crates/spectra-hal/src/lib.rs`)

```rust
use std::time::Duration;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum HalError {
    #[error("Transport I/O failure: {0}")]
    Io(#[from] std::io::Error),
    #[error("Frame timeout after {0:?}")]
    Timeout(Duration),
    #[error("Framing or checksum mismatch: expected {expected:#04x}, got {actual:#04x}")]
    IntegrityError { expected: u16, actual: u16 },
    #[error("Invalid bit-slice encoding in byte {index}: {raw:#04x}")]
    EncodingError { index: usize, raw: u8 },
    #[error("Hardware or bus isolation fault: {0}")]
    HardwareFault(String),
}

pub type HalResult<T> = Result<T, HalError>;

/// Physical transport link: USB-UART, ADB Socket Bridge, USB Bulk, or Linux RNDIS
#[allow(async_fn_in_trait)]
pub trait Transport: Send + Sync {
    async fn write_raw(&mut self, payload: &[u8], inter_byte_delay: Option<Duration>) -> HalResult<()>;
    async fn read_raw(&mut self, buf: &mut [u8], timeout: Duration) -> HalResult<usize>;
}

/// Machine-specific framing & obfuscation layer (e.g., Jura 4-byte, MDB 9-bit, Jetinno UART)
pub trait MachineProtocol: Send + Sync {
    type Command;
    type TelemetryFrame;

    fn encode_command(&self, cmd: &Self::Command) -> HalResult<Vec<u8>>;
    fn decode_frame(&self, raw: &[u8]) -> HalResult<Self::TelemetryFrame>;
}

/// Jura 4-Byte Obfuscation Primitives (9600 8N1, ~8 ms inter-byte delay)
pub mod jura_codec {
    use super::{HalError, HalResult};

    const BASE_MASK: u8 = 0b0101_1011; // 0x5B base carrier byte

    /// Encodes 1 ASCII byte into 4 UART wire bytes (2 payload bits per wire byte at bit 2 & bit 5)
    pub fn encode_byte(byte: u8) -> [u8; 4] {
        let mut out = [BASE_MASK; 4];
        for i in 0..4 {
            let b0 = (byte >> (i * 2)) & 0x01;
            let b1 = (byte >> (i * 2 + 1)) & 0x01;
            out[i] = (BASE_MASK & !((1 << 2) | (1 << 5))) | (b0 << 2) | (b1 << 5);
        }
        out
    }

    /// Decodes 4 UART wire bytes back into 1 ASCII byte
    pub fn decode_quad(quad: &[u8; 4]) -> HalResult<u8> {
        let mut out: u8 = 0;
        for (i, &wire) in quad.iter().enumerate() {
            let b0 = (wire >> 2) & 0x01;
            let b1 = (wire >> 5) & 0x01;
            out |= (b0 << (i * 2)) | (b1 << (i * 2 + 1));
        }
        Ok(out)
    }
}
```
