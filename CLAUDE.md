# Autocal -- Senmatic Calibration System
## Project Context for Claude Code

This file gives Claude Code full context about this project so it can
help effectively without needing the full chat history.

---

## What This Project Does

Automated 4-point calibration system for PT100 temperature sensors using:
- **Isotech Micro-K 70** precision AC resistance bridge (GPIB or RS-232)
- **1x TwoTrees TTC3018S** CNC machine as automated pogo-pin connector
  (X axis = reference SPRT, Y axis = batch slot, Z axis = connect/disconnect)
- **PySide6** GUI running on Windows or Revolution Pi (industrial Linux)

### Calibration Points
1. Bath 1-1 (0°C) -- first measurement
2. Bath 2 (-195°C)
3. Bath 3 (-76°C)
4. Bath 4 (100°C)
5. Bath 1-2 (0°C) -- second measurement, compared against Bath 1-1

---

## Project Structure

```
Autocal/
├── main.py                      # Entry point
├── config.py                    # Config loader (DB → runtime variables)
├── create_db.py                 # Creates fresh Meas.db from scratch
├── requirements.txt
├── README.md
├── CLAUDE.md                    # This file
│
├── cnc/
│   ├── __init__.py              # Required -- must exist
│   └── control.py               # GRBL serial control (single CNC, 3 axes)
│
├── db/
│   ├── __init__.py
│   ├── connection.py            # SQLite connection (DB_PATH from config)
│   └── queries.py               # All DB queries
│
├── gui/
│   ├── __init__.py
│   ├── main_window.py           # Main PySide6 GUI (sidebar navigation)
│   ├── worker.py                # QThread measurement worker
│   ├── styles.py                # Neumorphic light theme (NEU_STYLE)
│   ├── progress_dialog.py       # Calibration progress popup
│   └── sim_dialog.py            # Simulation mode sliders
│
├── instruments/
│   ├── __init__.py
│   ├── bridge.py                # Factory -- selects GPIB or RS-232
│   ├── bridge_gpib.py           # pyvisa GPIB driver
│   └── bridge_rs232.py          # pyserial RS-232 driver
│
├── measurement/
│   ├── __init__.py
│   ├── its90.py                 # ITS-90 temperature calculation
│   ├── cvd.py                   # Callendar-Van Dusen PT100
│   └── stability.py             # 2-stage stability check
│
└── tools/
    └── report.py                # Calibration report text file generator
```

---

## Hardware Setup

### CNC -- Single machine, 3 axes
- **X axis**: selects which reference SPRT is connected (4 positions)
- **Y axis**: selects which batch slot is connected (14 positions total)
- **Z axis**: lowers/raises pogo pins to make/break contact (shared)
- Board: MakerBase MKS DLC32 (GRBL firmware, USB serial)
- Limit switches: NC type, `$5=1` in GRBL
- **Homing:** currently disabled (`$22=0`) -- limit switches being installed.
  Once installed: set `$22=1`, `$5=1` (NC switches), test `$H`.

### Reference SPRT positions (CNC X axis):
```
5003 → Bath 1-1 and Bath 1-2
5004 → Bath 2
5088 → Bath 3
4999 → Bath 4
```

### Batch positions (CNC Y axis):
```
Bath 1-1: slots 1-4   (4 batches × 6 sensors each)
Bath 1-2: slots 1-4
Bath 2:   slots 1-2
Bath 3:   slots 1-2
Bath 4:   slots 1-2
Total: 14 Y positions
```

### Pogo pins:
- Reference connectors: 4 pins each (4-wire Kelvin)
- Batch connectors: 24 pins each (6 sensors × 4 wires)
- Max 6 active DUT sensors per batch → max 7 bridge channels (1 ref + 6 DUT)

---

## Key Design Decisions

### ITS-90 Calculation
Uses iterative T90accurate solver ported from verified VB code.
**NOT** the direct inverse polynomial -- that was wrong.
Key functions in `measurement/its90.py`:
- `_Wr90(t_kelvin)` -- forward reference function
- `_T90accurate(Wr)` -- iterates to 1e-11 convergence
- `calculate_its90(ratio, coefficients, r_standard)` -- full chain

### Configuration System
All settings in DB `Config` table. Priority chain:
1. `sprt_config.json` (emergency override, if file exists)
2. DB Config table (normal operation)
3. Module-level defaults in `config.py` (absolute fallback)

Call `config.load_config(conn)` at startup -- populates all module-level
variables like `config.BRIDGE_COMM`, `config.CNC_X_POSITIONS` etc.

### Bridge Communication
`instruments/bridge.py` is a factory -- reads `config.BRIDGE_COMM`
and returns either `GPIBBridge` or `RS232Bridge`.
Both expose the same interface:
```python
bridge.connect()
bridge.close()
bridge.query_channel(channel)  # returns float ratio or None (never raises)
```
**Important:** `query_channel` must always return `None` on any error,
never raise. Both drivers have this fixed. Invalid channel returns `None`.

### CNC Control
`cnc/control.py` -- GRBL over pyserial. Single CNC, 3 axes.
Key functions:
- `cnc_connect(port, baud)` -- open serial, soft reset, set G90
- `cnc_connect_reference(cnc, sensor_id)` -- move X to ref position (Z stays up)
- `cnc_connect_batch(cnc, bath_no, slot)` -- move Y to batch slot then lower Z
- `cnc_disconnect(cnc)` -- raise Z
- `cnc_jog(cnc, direction, step, feed)` -- manual jog (X+/X-/Y+/Y-/Z+/Z-)

Config keys used: `CNC_X_POSITIONS` (dict keyed by sensor_id),
`CNC_Y_POSITIONS` (dict keyed by bath_no + slot), `CNC_FEED_RATE`,
`CNC_Z_CONNECT`, `CNC_Z_CLEAR`.

### Measurement Worker Scan Loop (`gui/worker.py`)
Each channel has two distinct states:

1. **Collecting** (scans 1–5): one bridge query per scan per channel.
   After 5 readings fill the buffer, Stage 1 (spread check) is evaluated.
   If Stage 1 passes, channel moves to `stage1_passed` state.

2. **stage1_passed** (scan 6+): one bridge query only -- the 6th reading.
   Stage 2 (avg of 5 vs 6th reading) is evaluated.
   - Passes → channel marked stable, result saved.
   - Fails → resets to Collecting (needs new readings).

**A channel is never queried more than once per scan iteration.**
This was a bug that caused double queries from scan 5 onwards, flooding
the log with bridge query fail messages and crashing the session log.

### Disable CNC Mode
Toggle button on the CNC page. When enabled (`self.cnc_disabled = True`):
- All CNC moves are skipped (worker logs "DISABLED -- manual" instead)
- Session runs normally, sensors connected manually
- Worker receives `cnc_disabled=True` at session start

### Skip Sensor
Skipped sensors: `Skipped=1` in MeasTemp, shown as `⊘ SKIP` in orange.
MeasTemp row left blank -- sensor can be re-measured in future session.

### Bath 1-2 Drift Warning
After Bath 1-2 measurement, compares against Bath 1-1:
- Resistance drift > 20mK → warning
- Bath temperature drift > 10mK → warning
Logic in `db/queries.py` `compare_bath1_results()`

### Calibration Report Generator (`tools/report.py`)
After a session completes, the "Save Calibration Report" button on the
Progress page calls `tools.report.generate_reports(conn)`.

- One `.txt` file per certificate number
- Saved to `~/Documents/MeasDB/Reports/`
- Filename: `Measured {N} - Certificate {cert_no}.txt`
  (N auto-increments so previous reports are never overwritten)
- Contains: per-sensor table with bath points, ref temp, resistance,
  sensor temp, ΔRes (Ω), ΔTemp (mK), EN60751 class, overall class,
  Bath 1-2 second reading

---

## GUI Structure (main_window.py)

Sidebar navigation with 4 pages:

### Session Page
- Bath config (5 baths, Bath 1-1/1-2 have 4 batch slots, others have 2)
- Bath timers (compact)
- Sensor list table with Skip/Unskip buttons
- Start/Stop session buttons

### CNC Page
- **Disable CNC** toggle button at top (grey = active, red = disabled/manual)
- Single connection panel: Port, Baud, Connect/Disconnect, status dot
- Manual jog: X−, X+, Y−, Y+, Z−, Z+, Home; step dropdown
- Connect Pins / Retract Pins buttons
- X axis position buttons (move to stored reference positions)
- Y axis position buttons (move to stored batch slot positions)

### Progress Page
- Batch queue table
- Live readings table (double height)
- **Save Calibration Report** button (enabled after session completes)

### Config Page (password protected)
Password: SenmaticLab1 (SHA-256 hashed in DB)
Tabs: Communication | SPRT Sensors | Standard Resistors |
      Bath Settings | Stability & Warnings | CNC Settings
CNC Settings tab: single Connection group + X axis group + Y axis group.
Change Password button opens separate dialog.

---

## Database (Meas.db)

Location: `~/Documents/MeasDB/Meas.db`
Created by: `python create_db.py`

Tables:
- `Sensors` -- serial numbers and certificate info
- `MeasTemp` -- working table for active calibration session
- `ReferenceThermometers` -- SPRT coefficients (4 sensors pre-loaded)
- `ReferenceResistors` -- calibrated 25Ω and 100Ω values
- `Config` -- all app settings (single CNC keys: cnc_port, cnc_baud,
  cnc_feed_rate, cnc_z_connect, cnc_z_clear, cnc_x_ref_*, cnc_y_bath*_slot_*)
- `CalibrationResults` -- permanent record after sessions complete

---

## Reference Sensors

| Tag  | Roits              | Bath  |
|------|--------------------|-------|
| 5003 | 25.673304498446    | 1,1-2 |
| 5004 | 25.73122           | 2     |
| 5088 | 25.3913923289315   | 3     |
| 4999 | 25.5939491065947   | 4     |

Standard resistors:
- 25Ω standard: 24.999895 Ω (calibrated)
- 100Ω standard: 100.00084 Ω (calibrated)

---

## Known Issues / TODO

- [ ] Install limit switches on both CNC axes, enable homing in GRBL
      (`$22=1`, `$5=1`, test `$H`)
- [ ] Test full session flow with real bridge and DB connected
- [ ] Test bridge RS-232 on Revolution Pi
- [ ] GitHub Actions CI for syntax checking

---

## Common Errors and Fixes

### `No module named 'cnc.control'`
- Make sure `cnc/__init__.py` exists (can be empty)
- Run app from project root: `python main.py`
- File must be named `control.py`

### Config not persisting after restart
- `config.load_config(conn)` must be called before `_build_ui()`
- Check DB exists at `~/Documents/MeasDB/Meas.db`
- Run `create_db.py` if DB missing

### ITS-90 wrong temperature
- Check `sprt_config.json` has correct calibrated resistor values
- `resistor_25: 24.999895` and `resistor_100: 100.00084`
- Roits must match the SPRT calibration certificate exactly

### CNC COM port not found
- Device must be physically connected before port appears
- Check Device Manager for actual COM number
- Update in Config → CNC Settings and save to DB

### Bridge query fail messages / session log crash
- Root cause was double bridge queries per scan (fixed in worker.py)
- Each channel now gets exactly one query per scan iteration
- `query_channel` in both drivers returns None (never raises) on any error

### Worker thread stops after scan 1 (silent crash)
- Any unhandled exception in `_measure_batch` used to silently kill the thread
- Fixed: `_measure_batch` is wrapped in try/except with full traceback logged
- If this happens again, check session log for the traceback
