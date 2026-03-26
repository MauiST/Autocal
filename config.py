"""
config.py
=========
Application configuration.

Loading priority for runtime settings:
  1. DB Config table  (loaded at startup via load_config())
  2. sprt_config.json (emergency override if file exists)
  3. Defaults defined here (absolute fallback)
"""

import os
import json

# =============================================================
# --- PATHS
# =============================================================
DB_PATH        = os.path.join(os.path.expanduser("~/Documents"), "MeasDB", "Meas.db")
SPRT_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprt_config.json")

# =============================================================
# --- BATH CONFIGURATION
# =============================================================
# Bath 1 is split into Bath 1-1 (first 0C) and Bath 1-2 (second 0C)
# 4-point calibration order: 1-1 -> 2 -> 3 -> 4 -> 1-2

BATH_COLUMN = {
    1: 'MeasRes_0',
    2: 'MeasRes_n195',
    3: 'MeasRes_n76',
    4: 'MeasRes_100',
    5: 'MeasRes_0_2nd',
}

BATH_LABEL = {
    1: 'Bath 1-1  (0C)',
    2: 'Bath 2    (-195C)',
    3: 'Bath 3    (-76C)',
    4: 'Bath 4    (100C)',
    5: 'Bath 1-2  (0C) 2nd',
}

BATH_WAIT_DEFAULT = {
    1: 30 * 60,
    2: 60 * 60,
    3: 60 * 60,
    4: 45 * 60,
    5: 30 * 60,
}

# =============================================================
# --- REFERENCE SENSORS
# =============================================================
REF_SENSOR_ID = {
    1: '5003',
    2: '5004',
    3: '5088',
    4: '4999',
}

# =============================================================
# --- STABILITY THRESHOLDS
# =============================================================
STAGE1_THRESHOLD = 0.000020499
STAGE2_THRESHOLD = 0.000008499

# =============================================================
# --- BATH VALIDATION
# =============================================================
BATH_TEMP_RANGE = {
    1: (-10,   10),
    2: (-205, -185),
    3: (-85,  -67),
    4: ( 90,   110),
    5: (-10,   10),
}

BATH_REF_RECOMMENDED = {
    1: '5003',
    2: '5004',
    3: '5088',
    4: '4999',
    5: '5003',
}

# =============================================================
# --- BRIDGE COMMUNICATION
# =============================================================
BRIDGE_COMM         = 'GPIB'
BRIDGE_GPIB_ADDR    = '10'
BRIDGE_RS232_PORT   = '/dev/ttyS0'
BRIDGE_RS232_BAUD   = 9600
BRIDGE_RS232_BYTESIZE = 8
BRIDGE_RS232_PARITY = 'N'
BRIDGE_RS232_STOPBITS = 1
BRIDGE_TIMEOUT      = 10
BRIDGE_SETTLE_TIME  = 3
BRIDGE_CHANNEL_SETTLE = 0.5

# =============================================================
# --- WARNING THRESHOLDS  (Bath 1-2 vs Bath 1-1)
# =============================================================
BATH1_RESISTANCE_WARN_MK  = 20.0   # mK sensor resistance drift
BATH1_TEMPERATURE_WARN_MK = 10.0   # mK bath temperature drift

# =============================================================
# --- CNC MACHINE DEFAULTS
# =============================================================
CNC1_PORT       = 'COM3'
CNC2_PORT       = 'COM4'
CNC_BAUD        = 115200
CNC1_FEED_RATE  = 500
CNC2_FEED_RATE  = 500
CNC1_Z_CONNECT  = -5.0
CNC1_Z_CLEAR    = 0.0
CNC2_Z_CONNECT  = -5.0
CNC2_Z_CLEAR    = 0.0

# CNC 1 -- X positions per reference sensor
CNC1_X_POSITIONS = {
    '5003': 0.0,
    '5004': 30.0,
    '5088': 60.0,
    '4999': 90.0,
}

# CNC 2 -- X positions per bath and slot
# Key: (bath_no, slot) where bath_no matches BATH_COLUMN keys
# Bath 1-1 (bath_no=1) and Bath 1-2 (bath_no=5) have 4 slots each
CNC2_X_POSITIONS = {
    (1, 1): 0.0,    # Bath 1-1 Slot 1
    (1, 2): 30.0,   # Bath 1-1 Slot 2
    (1, 3): 60.0,   # Bath 1-1 Slot 3
    (1, 4): 90.0,   # Bath 1-1 Slot 4
    (5, 1): 120.0,  # Bath 1-2 Slot 1
    (5, 2): 150.0,  # Bath 1-2 Slot 2
    (5, 3): 180.0,  # Bath 1-2 Slot 3
    (5, 4): 210.0,  # Bath 1-2 Slot 4
    (2, 1): 240.0,  # Bath 2 Slot 1
    (2, 2): 270.0,  # Bath 2 Slot 2
    (3, 1): 300.0,  # Bath 3 Slot 1
    (3, 2): 330.0,  # Bath 3 Slot 2
    (4, 1): 360.0,  # Bath 4 Slot 1
    (4, 2): 390.0,  # Bath 4 Slot 2
}

# =============================================================
# --- PROGRESS TABLE COLUMNS
# =============================================================
PROGRESS_COLS = [
    ('Serial',           'Serial'),
    ('Batch',            'BatchNo'),
    ('Bath 1-1 (0C)',    'MeasRes_0'),
    ('Bath 2 (-195C)',   'MeasRes_n195'),
    ('Bath 3 (-76C)',    'MeasRes_n76'),
    ('Bath 4 (100C)',    'MeasRes_100'),
    ('Bath 1-2 (0C)',    'MeasRes_0_2nd'),
]

# =============================================================
# --- DB CONFIG TABLE
# =============================================================
CONFIG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS Config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    category    TEXT NOT NULL,
    description TEXT
);
"""

CONFIG_DEFAULTS = {
    'bath_wait_1':  ('1800',  'bath',      'Bath 1-1 wait time in seconds'),
    'bath_wait_2':  ('3600',  'bath',      'Bath 2 wait time in seconds'),
    'bath_wait_3':  ('3600',  'bath',      'Bath 3 wait time in seconds'),
    'bath_wait_4':  ('2700',  'bath',      'Bath 4 wait time in seconds'),
    'bath_wait_5':  ('1800',  'bath',      'Bath 1-2 wait time in seconds'),

    'bath_temp_min_1': ('-10',  'bath', 'Bath 1-1 min expected temp C'),
    'bath_temp_max_1': ('10',   'bath', 'Bath 1-1 max expected temp C'),
    'bath_temp_min_2': ('-205', 'bath', 'Bath 2 min expected temp C'),
    'bath_temp_max_2': ('-185', 'bath', 'Bath 2 max expected temp C'),
    'bath_temp_min_3': ('-85',  'bath', 'Bath 3 min expected temp C'),
    'bath_temp_max_3': ('-67',  'bath', 'Bath 3 max expected temp C'),
    'bath_temp_min_4': ('90',   'bath', 'Bath 4 min expected temp C'),
    'bath_temp_max_4': ('110',  'bath', 'Bath 4 max expected temp C'),
    'bath_temp_min_5': ('-10',  'bath', 'Bath 1-2 min expected temp C'),
    'bath_temp_max_5': ('10',   'bath', 'Bath 1-2 max expected temp C'),

    'stage1_threshold': ('0.000020499', 'stability', 'Stage 1 stability threshold'),
    'stage2_threshold': ('0.000008499', 'stability', 'Stage 2 stability threshold'),

    'bath1_resistance_warn_mk':  ('20.0', 'warnings', 'Bath 1-2 vs 1-1 resistance drift warning mK'),
    'bath1_temperature_warn_mk': ('10.0', 'warnings', 'Bath 1-2 vs 1-1 temperature drift warning mK'),

    # CNC ports and motion settings
    'cnc1_port':       ('COM3',   'cnc', 'CNC 1 COM port -- Reference SPRT selector'),
    'cnc2_port':       ('COM4',   'cnc', 'CNC 2 COM port -- Batch sensor selector'),
    'cnc_baud':        ('115200', 'cnc', 'CNC baud rate'),
    'cnc1_feed_rate':  ('500',    'cnc', 'CNC 1 feed rate mm/min'),
    'cnc2_feed_rate':  ('500',    'cnc', 'CNC 2 feed rate mm/min'),
    'cnc1_z_connect':  ('-5.0',   'cnc', 'CNC 1 Z depth for reference pogo pin contact mm'),
    'cnc1_z_clear':    ('0.0',    'cnc', 'CNC 1 Z clear/home position mm'),
    'cnc2_z_connect':  ('-5.0',   'cnc', 'CNC 2 Z depth for batch pogo pin contact mm'),
    'cnc2_z_clear':    ('0.0',    'cnc', 'CNC 2 Z clear/home position mm'),

    # CNC 1 -- Reference SPRT X positions (4 positions, one per bath)
    'cnc1_x_ref_5003': ('0.0',   'cnc', 'CNC1 X position for ref 5003 (Bath 1)  mm'),
    'cnc1_x_ref_5004': ('30.0',  'cnc', 'CNC1 X position for ref 5004 (Bath 2)  mm'),
    'cnc1_x_ref_5088': ('60.0',  'cnc', 'CNC1 X position for ref 5088 (Bath 3)  mm'),
    'cnc1_x_ref_4999': ('90.0',  'cnc', 'CNC1 X position for ref 4999 (Bath 4)  mm'),

    # CNC 2 -- Batch sensor X positions (10 positions)
    # Bath 1-1 (first 0C measurement) -- 4 slots
    'cnc2_x_bath1_1_slot_1': ('0.0',   'cnc', 'CNC2 X Bath 1-1 Slot 1 mm'),
    'cnc2_x_bath1_1_slot_2': ('30.0',  'cnc', 'CNC2 X Bath 1-1 Slot 2 mm'),
    'cnc2_x_bath1_1_slot_3': ('60.0',  'cnc', 'CNC2 X Bath 1-1 Slot 3 mm'),
    'cnc2_x_bath1_1_slot_4': ('90.0',  'cnc', 'CNC2 X Bath 1-1 Slot 4 mm'),
    # Bath 1-2 (second 0C measurement) -- 4 slots
    'cnc2_x_bath1_2_slot_1': ('120.0', 'cnc', 'CNC2 X Bath 1-2 Slot 1 mm'),
    'cnc2_x_bath1_2_slot_2': ('150.0', 'cnc', 'CNC2 X Bath 1-2 Slot 2 mm'),
    'cnc2_x_bath1_2_slot_3': ('180.0', 'cnc', 'CNC2 X Bath 1-2 Slot 3 mm'),
    'cnc2_x_bath1_2_slot_4': ('210.0', 'cnc', 'CNC2 X Bath 1-2 Slot 4 mm'),
    # Bath 2
    'cnc2_x_bath2_slot_1':   ('240.0', 'cnc', 'CNC2 X Bath 2 Slot 1 mm'),
    'cnc2_x_bath2_slot_2':   ('270.0', 'cnc', 'CNC2 X Bath 2 Slot 2 mm'),
    # Bath 3
    'cnc2_x_bath3_slot_1':   ('300.0', 'cnc', 'CNC2 X Bath 3 Slot 1 mm'),  # placeholder -- adjust per physical layout
    'cnc2_x_bath3_slot_2':   ('330.0', 'cnc', 'CNC2 X Bath 3 Slot 2 mm'),
    # Bath 4
    'cnc2_x_bath4_slot_1':   ('360.0', 'cnc', 'CNC2 X Bath 4 Slot 1 mm'),
    'cnc2_x_bath4_slot_2':   ('390.0', 'cnc', 'CNC2 X Bath 4 Slot 2 mm'),

    'sprt_5003_roits':   ('25.673304498446',      'sprt', 'Sensor 5003 Roits'),
    'sprt_5003_a_sub':   ('-2.8008754547614E-04',  'sprt', 'Sensor 5003 a<0'),
    'sprt_5003_b_sub':   ('-6.91040202369516E-06', 'sprt', 'Sensor 5003 b<0'),
    'sprt_5003_a_above': ('-2.96924668118342E-04', 'sprt', 'Sensor 5003 a>0'),

    'sprt_5004_roits':   ('25.73122',         'sprt', 'Sensor 5004 Roits'),
    'sprt_5004_a_sub':   ('-2.245746E-04',    'sprt', 'Sensor 5004 a<0'),
    'sprt_5004_b_sub':   ('-2.275693E-06',    'sprt', 'Sensor 5004 b<0'),
    'sprt_5004_a_above': ('-2.482641E-04',    'sprt', 'Sensor 5004 a>0'),

    'sprt_5088_roits':   ('25.3913923289315',      'sprt', 'Sensor 5088 Roits'),
    'sprt_5088_a_sub':   ('-1.6048040028668E-04',  'sprt', 'Sensor 5088 a<0'),
    'sprt_5088_b_sub':   ('-1.0341744717991E-05',  'sprt', 'Sensor 5088 b<0'),
    'sprt_5088_a_above': ('-1.51583715855111E-04', 'sprt', 'Sensor 5088 a>0'),

    'sprt_4999_roits':   ('25.5939491065947',      'sprt', 'Sensor 4999 Roits'),
    'sprt_4999_a_sub':   ('-1.83544024242177E-04', 'sprt', 'Sensor 4999 a<0'),
    'sprt_4999_b_sub':   ('1.05759953587199E-05',  'sprt', 'Sensor 4999 b<0'),
    'sprt_4999_a_above': ('-2.49000841615879E-04', 'sprt', 'Sensor 4999 a>0'),

    'resistor_25':  ('24.999895', 'resistors', 'Calibrated 25 ohm standard resistor'),
    'resistor_100': ('100.00084', 'resistors', 'Calibrated 100 ohm standard resistor'),

    # Bridge communication settings
    'bridge_comm':        ('GPIB',      'bridge', 'Bridge communication type: GPIB or RS232'),
    'bridge_gpib_addr':   ('10',        'bridge', 'GPIB address of Micro-K 70'),
    'bridge_rs232_port':  ('/dev/ttyS0','bridge', 'RS-232 port for Micro-K 70 (COM1 on Windows)'),
    'bridge_rs232_baud':  ('9600',      'bridge', 'RS-232 baud rate'),
    'bridge_rs232_bytesize': ('8',      'bridge', 'RS-232 data bits'),
    'bridge_rs232_parity':   ('N',      'bridge', 'RS-232 parity: N, E, O'),
    'bridge_rs232_stopbits': ('1',      'bridge', 'RS-232 stop bits'),
    'bridge_timeout':     ('10',        'bridge', 'Bridge query timeout seconds'),
    'bridge_settle_time': ('3',         'bridge', 'Bridge settle time after connect seconds'),
    'bridge_channel_settle': ('0.5',    'bridge', 'Channel relay settle time seconds'),

    # Config page password (SHA-256 hash) -- default: SenmaticLab1
    'config_password_hash': (
        '55a76fa549255ec2626ff874cf20c47f9e47d5d55dfba2679829b8878bfeabe7',
        'security',
        'SHA-256 hash of Config page access password'
    ),
}

# =============================================================
# --- RUNTIME CONFIG LOADER
# =============================================================
_runtime = {}


def load_config(conn):
    """Load config from DB into _runtime. Creates table/defaults if missing."""
    global _runtime

    if conn is None:
        _runtime = {k: v[0] for k, v in CONFIG_DEFAULTS.items()}
        print("[config] No DB -- using built-in defaults")
        return

    cursor = conn.cursor()
    cursor.executescript(CONFIG_TABLE_SQL)
    conn.commit()

    for key, (value, category, description) in CONFIG_DEFAULTS.items():
        cursor.execute(
            "INSERT OR IGNORE INTO Config (key, value, category, description) VALUES (?, ?, ?, ?)",
            (key, value, category, description)
        )
    conn.commit()

    cursor.execute("SELECT key, value FROM Config")
    _runtime = {row[0]: row[1] for row in cursor.fetchall()}

    # Emergency override from sprt_config.json if present
    if os.path.exists(SPRT_JSON_PATH):
        try:
            with open(SPRT_JSON_PATH) as f:
                jdata = json.load(f)
            for s in ['5003', '5004', '5088', '4999']:
                if s in jdata and isinstance(jdata[s], dict):
                    e = jdata[s]
                    for field in ['roits', 'a_sub', 'b_sub', 'a_above']:
                        if field in e:
                            _runtime[f'sprt_{s}_{field}'] = str(e[field])
            rs = jdata.get('standard_resistors', {})
            if '25'  in rs: _runtime['resistor_25']  = str(rs['25'])
            if '100' in rs: _runtime['resistor_100'] = str(rs['100'])
            print("[config] sprt_config.json emergency override applied")
        except Exception as e:
            print(f"[config] sprt_config.json error: {e}")

    _apply_runtime()
    print(f"[config] Loaded {len(_runtime)} settings from DB")


def save_config(conn, key, value):
    """Save a single config value to DB and refresh runtime."""
    _runtime[key] = str(value)
    cursor = conn.cursor()
    cursor.execute("UPDATE Config SET value = ? WHERE key = ?", (str(value), key))
    conn.commit()
    _apply_runtime()


def get(key, default=None):
    return _runtime.get(key, default)


def get_float(key, default=0.0):
    try:
        return float(_runtime.get(key, default))
    except (ValueError, TypeError):
        return float(default)


def get_int(key, default=0):
    try:
        return int(float(_runtime.get(key, default)))
    except (ValueError, TypeError):
        return int(default)


def _apply_runtime():
    """Push runtime values back into module-level variables."""
    global BATH_WAIT_DEFAULT, STAGE1_THRESHOLD, STAGE2_THRESHOLD
    global BATH1_RESISTANCE_WARN_MK, BATH1_TEMPERATURE_WARN_MK
    global BRIDGE_COMM, BRIDGE_GPIB_ADDR, BRIDGE_RS232_PORT
    global BRIDGE_RS232_BAUD, BRIDGE_RS232_BYTESIZE, BRIDGE_RS232_PARITY, BRIDGE_RS232_STOPBITS
    global BRIDGE_TIMEOUT, BRIDGE_SETTLE_TIME, BRIDGE_CHANNEL_SETTLE
    global CNC1_PORT, CNC2_PORT, CNC_BAUD
    global CNC1_FEED_RATE, CNC2_FEED_RATE
    global CNC1_Z_CONNECT, CNC1_Z_CLEAR, CNC2_Z_CONNECT, CNC2_Z_CLEAR
    global CNC1_X_POSITIONS, CNC2_X_POSITIONS

    BATH_WAIT_DEFAULT = {
        1: get_int('bath_wait_1', 1800),
        2: get_int('bath_wait_2', 3600),
        3: get_int('bath_wait_3', 3600),
        4: get_int('bath_wait_4', 2700),
        5: get_int('bath_wait_5', 1800),
    }

    BATH_TEMP_RANGE[1] = (get_float('bath_temp_min_1', -10),  get_float('bath_temp_max_1', 10))
    BATH_TEMP_RANGE[2] = (get_float('bath_temp_min_2', -205), get_float('bath_temp_max_2', -185))
    BATH_TEMP_RANGE[3] = (get_float('bath_temp_min_3', -85),  get_float('bath_temp_max_3', -67))
    BATH_TEMP_RANGE[4] = (get_float('bath_temp_min_4', 90),   get_float('bath_temp_max_4', 110))
    BATH_TEMP_RANGE[5] = (get_float('bath_temp_min_5', -10),  get_float('bath_temp_max_5', 10))

    STAGE1_THRESHOLD          = get_float('stage1_threshold', 0.000020499)
    STAGE2_THRESHOLD          = get_float('stage2_threshold', 0.000008499)
    BATH1_RESISTANCE_WARN_MK  = get_float('bath1_resistance_warn_mk',  20.0)
    BATH1_TEMPERATURE_WARN_MK = get_float('bath1_temperature_warn_mk', 10.0)

    BRIDGE_COMM           = get('bridge_comm', 'GPIB')
    BRIDGE_GPIB_ADDR      = get('bridge_gpib_addr', '10')
    BRIDGE_RS232_PORT     = get('bridge_rs232_port', '/dev/ttyS0')
    BRIDGE_RS232_BAUD     = get_int('bridge_rs232_baud', 9600)
    BRIDGE_RS232_BYTESIZE = get_int('bridge_rs232_bytesize', 8)
    BRIDGE_RS232_PARITY   = get('bridge_rs232_parity', 'N')
    BRIDGE_RS232_STOPBITS = get_int('bridge_rs232_stopbits', 1)
    BRIDGE_TIMEOUT        = get_int('bridge_timeout', 10)
    BRIDGE_SETTLE_TIME    = get_int('bridge_settle_time', 3)
    BRIDGE_CHANNEL_SETTLE = get_float('bridge_channel_settle', 0.5)

    CNC1_PORT      = get('cnc1_port', 'COM3')
    CNC2_PORT      = get('cnc2_port', 'COM4')
    CNC_BAUD       = get_int('cnc_baud', 115200)
    CNC1_FEED_RATE = get_int('cnc1_feed_rate', 500)
    CNC2_FEED_RATE = get_int('cnc2_feed_rate', 500)
    CNC1_Z_CONNECT = get_float('cnc1_z_connect', -5.0)
    CNC1_Z_CLEAR   = get_float('cnc1_z_clear',   0.0)
    CNC2_Z_CONNECT = get_float('cnc2_z_connect', -5.0)
    CNC2_Z_CLEAR   = get_float('cnc2_z_clear',   0.0)

    CNC1_X_POSITIONS = {
        '5003': get_float('cnc1_x_ref_5003',  0.0),
        '5004': get_float('cnc1_x_ref_5004', 30.0),
        '5088': get_float('cnc1_x_ref_5088', 60.0),
        '4999': get_float('cnc1_x_ref_4999', 90.0),
    }

    CNC2_X_POSITIONS = {
        (1, 1): get_float('cnc2_x_bath1_1_slot_1',   0.0),
        (1, 2): get_float('cnc2_x_bath1_1_slot_2',  30.0),
        (1, 3): get_float('cnc2_x_bath1_1_slot_3',  60.0),
        (1, 4): get_float('cnc2_x_bath1_1_slot_4',  90.0),
        (5, 1): get_float('cnc2_x_bath1_2_slot_1', 120.0),
        (5, 2): get_float('cnc2_x_bath1_2_slot_2', 150.0),
        (5, 3): get_float('cnc2_x_bath1_2_slot_3', 180.0),
        (5, 4): get_float('cnc2_x_bath1_2_slot_4', 210.0),
        (2, 1): get_float('cnc2_x_bath2_slot_1',   240.0),
        (2, 2): get_float('cnc2_x_bath2_slot_2',   270.0),
        (3, 1): get_float('cnc2_x_bath3_slot_1',   300.0),
        (3, 2): get_float('cnc2_x_bath3_slot_2',   330.0),
        (4, 1): get_float('cnc2_x_bath4_slot_1',   360.0),
        (4, 2): get_float('cnc2_x_bath4_slot_2',   390.0),
    }


def get_sprt_coefficients(sensor_id):
    """Get SPRT calibration coefficients from runtime config."""
    return {
        'roits':   get_float(f'sprt_{sensor_id}_roits'),
        'a_sub':   get_float(f'sprt_{sensor_id}_a_sub'),
        'b_sub':   get_float(f'sprt_{sensor_id}_b_sub'),
        'a_above': get_float(f'sprt_{sensor_id}_a_above'),
        'c_sub':   0.0, 'd_sub': 0.0,
        'b_above': 0.0, 'c_above': 0.0, 'd_above': 0.0,
    }


def get_standard_resistor(nominal):
    """Get calibrated standard resistor value from runtime config."""
    return get_float(f'resistor_{int(float(nominal))}', float(nominal))
