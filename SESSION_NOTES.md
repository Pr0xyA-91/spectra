# W.R.A.T. & Jura Modern Diag — Comprehensive Context & Session Notes
**Generated**: October 23, 2026 | **Current Status**: Production / Verified Working

---

## 1. Quick Resume Guide
To resume development or testing in a new agent session or terminal:

```bash
# 1. Run unit test suite (7/7 tests must pass):
cd "/home/a91/Projects/Jura Modern Diag"
python3 -m unittest test_thermal_and_dual_heaters.py

# 2. Run live telemetry diagnostic against connected physical machine:
python3 -c '
import serial_io, stats_collector
conn = serial_io.JuraSerialConnection("/dev/ttyUSB0")
res = stats_collector.query_live_sensors("/dev/ttyUSB0", conn=conn, fast_poll=False)
for sw in res["switches"]:
    print(f"{sw[\"id\"]}: {sw[\"badge\"]} - {sw[\"status\"]}")
print("Hardness:", res["telemetry"].get("water_hardness_dh"), "°dH | Temp:", res["telemetry"].get("heater_coffee_str"))
conn.close()
'

# 3. Launch GTK3 GUI diagnostic application:
./run.sh
# or:
python3 gui.py
```

---

## 2. Connected Hardware & Physical Testbench
* **Model**: Jura IMPRESSA XJ5 Professional GII (`EF518M V02.20`)
* **Serial Port**: `/dev/ttyUSB0` (FTDI / CH340 diagnostic adapter, 9600 baud, 8N1)
* **Live Operating Conditions**:
  - Machine physically hot: Coffee Thermoblock ~98.0 °C to 101.5 °C (`parts[4]` in `HZ:`).
  - Water tank: Full (`parts[7][2] == '0'`, `parts[9][1] == '0'`).
  - Drip tray: Inserted (`parts[7][0] == '0'`, `parts[9][0] == '0'`).
  - Grounds container: Inserted and empty (`parts[7][1] == '0'`).
  - Configured Water Hardness (`RE:00C3`): `re:1E32` $\rightarrow$ `(0x1E32 >> 8) & 0xFF` = **30 °dH**.
  - Flowmeter constant: DigiMesa turbine = **2.366 pulses per ml** (~422 pulses / dl).
  - Machine operational state: **Ready to Brew** (`ready_ok = True`).

---

## 3. Project Architecture & Repositories

### A. Jura Modern Diag (`/home/a91/Projects/Jura Modern Diag`)
* **Branch**: `main` | **Version**: `v0.3.4`
* **Private Remote (`origin`)**: `https://github.com/Pr0xyA-91/wrat-sniffer_dev.git`
* **Public Remote (`public`)**: `https://github.com/Pr0xyA-91/wrat-sniffer.git`
* **Release Synchronization**:
  ```bash
  ./publish_release.sh main "release: Sync v0.3.4 release to public distribution"
  ```
  - Automatically checks out `public-main`, syncs from `main`, strictly purges `GEMINI.md`, sanitizes `.desktop` launchers to portable invocation (`bash -c '"$(dirname "%k")"/run.sh'`), and pushes to `public:main`.

### B. W.R.A.T. Multi-Manufacturer Suite (`/home/a91/Projects/WRAT`)
* **Branch**: `feat/multi-manufacturer-support` | **Version**: `v0.4.1`
* **Private Remote (`origin`)**: `https://github.com/Pr0xyA-91/wrat-sniffer_dev.git`
* **Supported Brands**:
  - `jura`: Native TOP-tronic ASCII + Smart Connect `@`-protocol.
  - `nivona`: ASCII/NICR gateway protocol.
  - `lamanti-kl`: Kalerm commercial protocol (`0xAA/0x55` framing).
  - `lamanti-jn`: Jetinno Vending MDB/CC2 protocol (`0x02` STX framing).
* **Test Suite (14/14 tests pass)**:
  ```bash
  cd "/home/a91/Projects/WRAT"
  python3 -m unittest discover -s .
  ```

---

## 4. Key Protocol Nuances & Hard-Won Knowledge

### 1. Separation of Live Readiness vs. Historical EEPROM Faults
* **Non-volatile EEPROM registers** (`RE:0028` last fault latch, `RE:01B4` lifetime flowmeter timeouts) store historical events that do **NOT** clear when the machine enters ready state.
* **RULE**: Never gate live operational readiness (`machine_ready`) on `RE:0028` or `RE:01B4`.
* Live operational readiness is determined strictly from real-time physical inputs:
  - Drip Tray inserted (`tray_ok`)
  - Water Tank present (`water_ok`)
  - Grounds Container not full (`not grounds_full`)
  - Coffee Thermoblock at brewing temperature ($\ge 80.0$ °C)
  - Appliance idle (`not is_busy`, `parts[0][0] == '0'`)
* When all 5 physical conditions are met, the appliance is **Ready to Brew / Nominal (READY)**.
* Historical faults remain displayed where they belong: in the **Hardware Diagnostics** tree view.

### 2. Periodic MCU Heartbeat Bit vs. Alarm Prompts
* In the Jura `HZ:` frame, `parts[7][3]` alternates between `0` and `1` every ~1 second (`000000` $\leftrightarrow$ `000100`).
* **RULE**: `parts[7][3]` is an internal MCU clock/timer tick, **NOT** an alarm or "Press Maintenance" indicator.
* Never apply a debounce or decay window to periodic oscillator bits.

### 3. Decoupling Auto-Poll from Static EEPROM Parameters
* Fast continuous polling (`fast_poll=True`, 1–2s intervals) queries **only dynamic volatile state** (`HZ:`), caching `_cached_ef` and `_cached_val_r28` on the connection. This reduces cycle latency to ~50ms and prevents serial buffer contention.
* Static settings (e.g. water hardness `RE:00C3`, filter configuration `RE:0029`) are queried **only during manual refresh** (`fast_poll=False`).
* In `fast_poll`, `water_hardness_dh` is omitted from the telemetry dictionary so the GUI never overwrites verified configuration values with default fallbacks.

### 4. DigiMesa Live Flow Rate Calculation
* Computed using flowmeter turbine pulse deltas between sequential polling samples:
  $$\text{Flow Rate (ml/s)} = \frac{\Delta P}{2.366 \times \Delta t}$$
* Accumulated cycle volume:
  $$\text{Volume (ml)} = \frac{P_{\text{cycle}}}{2.366}$$

---

## 5. Security & Privacy Guardrails
1. `GEMINI.md` contains internal project guidelines and must **NEVER** be pushed to public repositories.
2. The pre-push hook (`.git/hooks/pre-push`) automatically blocks pushes to `public` if `GEMINI.md` is present in any outgoing commit.
3. Public release tags must always point to commits on the sanitized `public-main` branch.
4. Launcher `.desktop` files must never contain hardcoded `/home/<user>/` paths in public distributions.
