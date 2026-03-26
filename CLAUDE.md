# Autocal -- Senmatic Calibration System
## Project Context for Claude Code

This file gives Claude Code full context about this project so it can
help effectively without needing the full chat history.

---

## What This Project Does

Automated 4-point calibration system for PT100 temperature sensors using:
- **Isotech Micro-K 70** precision AC resistance bridge (GPIB or RS-232)
- **2x TwoTrees TTC3018S** CNC machines as automated pogo-pin connectors
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
├── main_window.py               # Main PySide6 GUI (sidebar navigation)
├── worker.py                    # QThread measurement worker
├── config.py                    # Config loader (DB → runtime variables)
├── create_db.py                 # Creates fresh Meas.db from scratch
├── requirements.txt
├── README.md
├── CLAUDE.md                    # This file
│
├── cnc/
│   ├── __init__.py              # Required -- must exist
│   └── control.py               # GRBL serial control for TTC3018S
│
├── db/
│   ├── __init__.py
│   ├── connection.py            # SQLite connection (DB_PATH from config)
│   └── queries.py               # All DB queries
│
├── gui/
│   ├── __init__.py
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
└── measurement/
    ├── __init__.py
    ├── its90.py                 # ITS-90 temperature calculation
    ├── cvd.py                   # Callendar-Van Dusen PT100
    └── stability.py             # 2-stage stability check
```

---

## Hardware Setup

### CNC 1 -- Reference SPRT connector
- Controls which reference SPRT is connected
- X axis: 4 positions (one per bath)
- Z axis: lowers/raises pogo pins to make contact
- Board: MakerBase MKS DLC32 (GRBL, USB serial)
- Limit switches: NC type, `$5=1` in GRBL

### CNC 2 -- Batch sensor connector
- Controls which batch of PT100s is connected
- X axis: 10 positions (4 for Bath 1, 2 each for Bath 2/3/4)
- Z axis: lowers/raises pogo pins
- Same board and wiring as CNC 1

### Reference SPRT positions (CNC 1 X axis):
```
5003 → Bath 1-1 and Bath 1-2
5004 → Bath 2
5088 → Bath 3
4999 → Bath 4
```

### Batch positions (CNC 2 X axis):
```
Bath 1-1: slots 1-4
Bath 1-2: slots 1-4
Bath 2:   slots 1-2
Bath 3:   slots 1-2
Bath 4:   slots 1-2
```

### Pogo pins:
- Reference connectors: 4 pins each (4-wire Kelvin)
- Batch connectors: 24 pins each (6 sensors × 4 wires)

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
variables like `config.BRIDGE_COMM`, `config.CNC1_X_POSITIONS` etc.

### Bridge Communication
`instruments/bridge.py` is a factory -- reads `config.BRIDGE_COMM`
and returns either `GPIBBridge` or `RS232Bridge`.
Both expose the same interface:
```python
bridge.connect()
bridge.close()
bridge.query_channel(channel)  # returns float ratio or None
```

### CNC Control
`cnc/control.py` -- GRBL over pyserial.
Key functions:
- `cnc_connect(port, baud)` -- open serial, soft reset, set G90
- `cnc1_connect(cnc, sensor_id)` -- move X to ref position + Z down
- `cnc2_connect(cnc, bath_no, slot)` -- move X to batch position + Z down
- `cnc1_disconnect(cnc)` / `cnc2_disconnect(cnc)` -- Z up

**Homing:** currently disabled (`$22=0`) -- limit switches being installed.
Once switches are installed: set `$22=1`, `$5=1` (NC switches), test `$H`.

### Skip Sensor
Skipped sensors: `Skipped=1` in MeasTemp, shown as `⊘ SKIP` in orange.
MeasTemp row left blank -- sensor can be re-measured in future session.

### Bath 1-2 Drift Warning
After Bath 1-2 measurement, compares against Bath 1-1:
- Resistance drift > 20mK → warning + require confirmation
- Bath temperature drift > 10mK → warning + require confirmation
Logic in `db/queries.py` `compare_bath1_results()`

---

## GUI Structure (main_window.py)

Sidebar navigation with 4 pages:

### Session Page
- Bath config (5 baths, Bath 1-1/1-2 have 4 batch slots, others have 2)
- Bath timers (compact)
- Sensor list table with Skip/Unskip buttons
- Start/Stop session buttons

### CNC Page
- Connector 1 and Connector 2 side by side
- Port entry, Connect/Disconnect, status
- Manual jog: X−, X+, Z−, Z+, Home (disabled until limit switches)
- Step dropdown: 0.1, 0.5, 1, 5, 10, 50, 100 mm
- Connect Pins / Retract Pins
- Position buttons (move to stored X positions)

### Progress Page
- Batch queue table
- Live readings table (double height)

### Config Page (password protected)
Password: SenmaticLab1 (SHA-256 hashed in DB)
Tabs: Communication | SPRT Sensors | Standard Resistors |
      Bath Settings | Stability & Warnings | CNC Settings
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
- `Config` -- all 65+ app settings
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

- [ ] Update `worker.py` CNC calls to use `cnc1_connect(sensor_id)`
      and `cnc2_connect(bath_no, slot)` with correct arguments
- [ ] Install limit switches on both CNCs, enable homing in GRBL
- [ ] Test full session flow with DB connected
- [ ] Test bridge RS-232 on Revolution Pi
- [ ] GitHub Actions CI for syntax checking

---

## Common Errors and Fixes

### `No module named 'cnc.control'`
- Make sure `cnc/__init__.py` exists (can be empty)
- Run app from project root: `python main.py`
- File must be named `control.py` not `cnc_control.py`

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
