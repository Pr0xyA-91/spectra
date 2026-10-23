# W.R.A.T. — WhiteRat Asynchronous Telemetry (Project Guidelines)

- **Entry Point**: Run via `./run.sh` or `JuraModernDiag.desktop`.
- **Self-Contained**: All scripts, database files, and tools for the main Linux Jura edition reside inside `/home/a91/Projects/Jura Modern Diag/`.
- **Repository & Branch Topology**:
  * `/home/a91/Projects/Jura Modern Diag/` -> Private branch `main` (`origin`: `wrat-sniffer_dev`) & Public branch `main` via `public-main` (`public`: `wrat-sniffer`).
  * `/home/a91/Projects/WRAT/` -> Private branch `multi-manufacturer` (`origin`: `wrat-sniffer_dev` only; NEVER push to `public`).
  * `/home/a91/Projects/WRAT_win/` -> Private branch `windows` (`origin`: `wrat-sniffer_dev` only; NEVER push to `public`).
- **Hardware Port**: Auto-detects `/dev/ttyUSB*` and `/dev/ttyACM*`. Default 9600 baud 8N1.
- **Offline / Simulation Mode**: Built-in mock devices (Jura S8, E8, Z10, S8 Smart Connect) allow full testing without hardware.
- **Protocol**: Dual-Mode Interrogation Engine:
  * ASCII Optical Transceiver Protocol (handles JURA USB Scanner N 010 hardware modulation & optical loopback echo) for EEPROM reading (RT:0000..RT:0030) with 16ms/char pacing.
  * Encrypted Smart Connect (@-Protocol) with 4:1 wire carrier, `&`-framing, and recovered nibble cipher.
- **Model Coverage**: 170+ machine profiles spanning all Jura generations (IMPRESSA, ENA, X/W-line, E4/E6/E8, S8, J8/J10, Z6/Z8/Z10, GIGA).
- **Integrity**: Do not alter `/home/a91/Projects/Jura SW/` (the legacy 2016 suite). Keep all projects strictly separate.
