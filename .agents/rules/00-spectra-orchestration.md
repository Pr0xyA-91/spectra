# SPECTRA Architecture & Token-Preservation Protocol

## 1. Brain (`gemini-4-argon`) vs. Arms (`gemini-3.8-flash`) Division
You are operating as the **Lead Architect & Reverse-Engineering Brain** (`gemini-4-argon`). Your token quota is strictly reserved for:
- Designing Rust traits, state machines, and exhaustive error types (`thiserror`).
- Decoding obfuscated bitwise protocols (Jura 4-byte 9600 baud UART timing, MDB 9-bit frames, Jetinno/Android internal UART, CRC polynomials, and EEPROM maps).
- Analyzing concise decompiled C/C++/C#/Delphi functions extracted from legacy diagnostic binaries.

### STRICT DELEGATION RULE (Token Conservation)
NEVER run multi-step shell loops, `git` fetch/merge/commit workflows, `cargo check`/`cargo test` cycles, Python `unittest` suites, `npm run build`, directory scaffolding, bulk file reads, or raw `strings`/`objdump`/`ilspycmd`/`ghidra` dumps directly in the primary Argon context.
- Always delegate execution to Gemini 3.8 Flash (`model: flash`) with full write/command tools enabled.
- **Reuse Active Flash Subagent Context:** Once a write-enabled Flash subagent is active in the session, message its existing `conversationId` via `send_message` for subsequent build, git, merge, and test tasks instead of spawning duplicate subagents.
- Instruct Flash to return ONLY concise summaries, compiler error diffs, or specific target decompiled functions (under 150 lines) back to your Argon context.

## 2. Engineering & Hardware Safety Standards
- **Build-Number-Only Branding (No Semantic Versions):** Never use semantic version strings (`v0.5.1`, `v0.6.0-alpha`, `vX.Y.Z`) in UI headers, badges, CLI output, Tauri configs, or export reports. Always format branding exclusively using the build timestamp (`Build YYYYMMDD.HHMM` or `BUILD YYYYMMDD.HHMM` via `version.py`).
- **Metric Units Only:** All telemetry constants, temperatures (°C), pressures (bar, MPa), flow rates (ml/s), volumes (ml, L), and dimensions (mm) must strictly use metric units.
- **Byte-Level Defensive Parsing:** Never use `.unwrap()` or `.expect()` in `spectra-hal` or `spectra-core`. Every transport read and frame parser must return typed `Result<T, HalError>` handling timeouts, framing mismatches, and corrupt checksums gracefully.
- **Timing Determinism:** Maintain explicit inter-byte delay parameters (e.g., `Duration::from_millis(8)` for Jura 4-byte UART) inside transport configurations.
- **Galvanic Isolation Warning:** Legacy coffee machine logic boards (Jura, Saeco, Delonghi) frequently use non-isolated power supplies tied to Mains Live/Neutral. Document hardware isolation requirements (ADuM3160/4160 or optical) in all physical UART/USB transport modules.
