"""
create_db.py
============
Creates a fresh Meas.db database with all required tables.
Run this once to set up the database on a new machine.

Usage:
    python create_db.py

Creates the DB at the path defined in config.py (DB_PATH):
    ~/Documents/MeasDB/Meas.db
"""

import os
import sqlite3
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_PATH, CONFIG_TABLE_SQL, CONFIG_DEFAULTS


def create_database():
    # Create directory if it doesn't exist
    db_dir = os.path.dirname(DB_PATH)
    os.makedirs(db_dir, exist_ok=True)

    if os.path.exists(DB_PATH):
        answer = input(f"DB already exists at:\n  {DB_PATH}\nOverwrite? (yes/no): ")
        if answer.strip().lower() != 'yes':
            print("Aborted.")
            return

    print(f"Creating database at:\n  {DB_PATH}\n")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ----------------------------------------------------------
    # Sensors table
    # ----------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Sensors (
            Serial        TEXT PRIMARY KEY,
            CertificateNo TEXT,
            Type          TEXT,
            Nominal       REAL,
            Tag           TEXT,
            Length        REAL,
            DateAdded     TEXT
        )
    """)
    print("  ✓ Sensors table")

    # ----------------------------------------------------------
    # MeasTemp table  (working table for active calibration session)
    # ----------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS MeasTemp (
            Serial                  TEXT PRIMARY KEY,
            BatchNo                 INTEGER,
            Skipped                 INTEGER DEFAULT 0,

            -- Bath 1-1  (0°C first)
            "MeasRes_0"             REAL,
            "CalculatedTempRef(0)"  REAL,
            "MeasTemp(0)"           REAL,
            "DevResEN60751(0)"      REAL,
            "DevTempEN60751(0)"     REAL,

            -- Bath 2  (-195°C)
            "MeasRes_n195"              REAL,
            "CalculatedTempRef(-195)"   REAL,
            "MeasTemp(-195)"            REAL,
            "DevResEN60751(-195)"       REAL,
            "DevTempEN60751(-195)"      REAL,

            -- Bath 3  (-76°C)
            "MeasRes_n76"               REAL,
            "CalculatedTempRef(-76)"    REAL,
            "MeasTemp(-76)"             REAL,
            "DevResEN60751(-76)"        REAL,
            "DevTempEN60751(-76)"       REAL,

            -- Bath 4  (100°C)
            "MeasRes_100"               REAL,
            "CalculatedTempRef(100)"    REAL,
            "MeasTemp(100)"             REAL,
            "DevResEN60751(100)"        REAL,
            "DevTempEN60751(100)"       REAL,

            -- Bath 1-2  (0°C second)
            "MeasRes_0_2nd"             REAL,

            -- Metadata
            Date                    TEXT,
            Time                    TEXT
        )
    """)
    print("  ✓ MeasTemp table")

    # ----------------------------------------------------------
    # ReferenceThermometers table  (SPRT calibration data)
    # ----------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ReferenceThermometers (
            Name    TEXT PRIMARY KEY,
            Roits   REAL,
            R0      REAL,
            "a<"    REAL,
            "b<"    REAL,
            "c<"    REAL,
            "d<"    REAL,
            "a>"    REAL,
            "b>"    REAL,
            "c>"    REAL,
            "d>"    REAL
        )
    """)
    # Insert known reference sensors
    ref_sensors = [
        ('5003', 25.673304498446,   None, -2.8008754547614e-04, -6.91040202369516e-06, None, None, -2.96924668118342e-04, None, None, None),
        ('5004', 25.73122,          None, -2.245746e-04,        -2.275693e-06,          None, None, -2.482641e-04,         None, None, None),
        ('5088', 25.3913923289315,  None, -1.6048040028668e-04, -1.0341744717991e-05,   None, None, -1.51583715855111e-04, None, None, None),
        ('4999', 25.5939491065947,  None, -1.83544024242177e-04, 1.05759953587199e-05,  None, None, -2.49000841615879e-04, None, None, None),
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO ReferenceThermometers
        (Name, Roits, R0, "a<", "b<", "c<", "d<", "a>", "b>", "c>", "d>")
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, ref_sensors)
    print("  ✓ ReferenceThermometers table  (4 sensors inserted)")

    # ----------------------------------------------------------
    # ReferenceResistors table
    # ----------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ReferenceResistors (
            Value    TEXT PRIMARY KEY,
            Measured REAL,
            Serial   TEXT,
            CalDate  TEXT
        )
    """)
    cursor.executemany("""
        INSERT OR IGNORE INTO ReferenceResistors (Value, Measured)
        VALUES (?, ?)
    """, [('25', 24.999895), ('100', 100.00084)])
    print("  ✓ ReferenceResistors table  (25Ω=24.999895, 100Ω=100.00084)")

    # ----------------------------------------------------------
    # Config table  (all app settings)
    # ----------------------------------------------------------
    cursor.executescript(CONFIG_TABLE_SQL)
    for key, (value, category, description) in CONFIG_DEFAULTS.items():
        cursor.execute(
            "INSERT OR IGNORE INTO Config (key, value, category, description) VALUES (?,?,?,?)",
            (key, value, category, description)
        )
    print(f"  ✓ Config table  ({len(CONFIG_DEFAULTS)} settings inserted)")

    # ----------------------------------------------------------
    # CalibrationResults table  (permanent record after MeasTemp is cleared)
    # ----------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS CalibrationResults (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            Serial        TEXT,
            CertificateNo TEXT,
            BatchNo       INTEGER,
            DateCompleted TEXT,

            -- Bath 1-1
            "Res_0"             REAL,
            "TempRef_0"         REAL,
            "Temp_0"            REAL,
            "DevRes_0"          REAL,
            "DevTemp_0"         REAL,

            -- Bath 2
            "Res_n195"          REAL,
            "TempRef_n195"      REAL,
            "Temp_n195"         REAL,
            "DevRes_n195"       REAL,
            "DevTemp_n195"      REAL,

            -- Bath 3
            "Res_n76"           REAL,
            "TempRef_n76"       REAL,
            "Temp_n76"          REAL,
            "DevRes_n76"        REAL,
            "DevTemp_n76"       REAL,

            -- Bath 4
            "Res_100"           REAL,
            "TempRef_100"       REAL,
            "Temp_100"          REAL,
            "DevRes_100"        REAL,
            "DevTemp_100"       REAL,

            -- Bath 1-2
            "Res_0_2nd"         REAL,

            -- EN60751 class
            Class               TEXT
        )
    """)
    print("  ✓ CalibrationResults table")

    conn.commit()
    conn.close()

    print(f"\n✓ Database created successfully at:")
    print(f"  {DB_PATH}")
    print(f"\nTables created:")
    print(f"  Sensors, MeasTemp, ReferenceThermometers,")
    print(f"  ReferenceResistors, Config, CalibrationResults")


if __name__ == "__main__":
    create_database()
