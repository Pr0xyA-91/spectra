# W.R.A.T. — WhiteRat Asynchronous Telemetry (Project Guidelines)

- **Entry Point**: Run via `./run.sh` or `JuraModernDiag.desktop`.
- **Self-Contained**: All scripts, database files, and tools reside directly inside `/home/a91/Projects/Jura Modern Diag/`.
- **Hardware Port**: Auto-detects `/dev/ttyUSB*` and `/dev/ttyACM*`. Default 9600 baud 8N1.
- **Offline / Simulation Mode**: Built-in mock devices (Jura S8, E8, Z10) allow full testing without hardware.
- **Protocol**: Dual-Mode Interrogation Engine:
  * ASCII Optical Transceiver Protocol (handles JURA USB Scanner N 010 hardware modulation & optical loopback echo) for EEPROM reading (RT:0000..RT:0030) with 16ms/char pacing.
  * Encrypted Smart Connect (@-Protocol) with 4:1 wire carrier, `&`-framing, and recovered nibble cipher.
- **Model Coverage**: 170+ machine profiles spanning all Jura generations (IMPRESSA, ENA, X/W-line, E4/E6/E8, S8, J8/J10, Z6/Z8/Z10, GIGA).
- **Integrity**: Do not alter `/home/a91/Projects/Jura SW/` (the legacy 2016 suite). Keep both projects strictly separate.
