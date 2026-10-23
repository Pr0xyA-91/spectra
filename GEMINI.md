# W.R.A.T. — WhiteRat Asynchronous Telemetry (Windows Edition Guidelines)

- **Entry Point**: Run via `run.bat`, `run_web.bat`, `run_cli.bat`, `run_demo.bat` on Windows (or `./run.sh` on Linux).
- **Self-Contained**: All scripts, drivers, database files, and batch launchers for the Windows edition reside inside `/home/a91/Projects/WRAT_win/`.
- **Repository & Branch Topology**:
  * `/home/a91/Projects/WRAT_win/` -> Private branch `windows` (`origin`: `wrat-sniffer_dev` only; NEVER push to `public`).
  * `/home/a91/Projects/WRAT/` -> Private branch `multi-manufacturer` (`origin`: `wrat-sniffer_dev` only; NEVER push to `public`).
  * `/home/a91/Projects/Jura Modern Diag/` -> Private branch `main` (`origin`: `wrat-sniffer_dev`) & Public branch `main` via `public-main` (`public`: `wrat-sniffer`).
- **Hardware Port**: Auto-detects `COM*` ports on Windows (`pyserial`) and `/dev/ttyUSB*`, `/dev/ttyACM*` on Linux. Default 9600 baud 8N1.
- **Offline / Simulation Mode**: Built-in mock devices across all 4 supported vendors (`Jura S8/E8/Z10`, `Nivona NICR768`, `Lamanti-KL X680C`, `Lamanti-JN JL300`) allow full testing without hardware.
- **Supported Manufacturers**: Jura (ASCII & Smart Connect `@`-Protocol), Nivona (Eugster/Frismag ASCII), Lamanti-KL (Kalerm Modbus RTU), and Lamanti-JN (Jetinno IO Protocol).
- **Integrity**: Do not alter `/home/a91/Projects/Jura SW/` (the legacy 2016 suite). Keep all projects strictly separate.
