import sqlite3
import os
from config import DB_PATH


def connect_db():
    """Connect to the MeasDB database. Returns connection or None."""
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)


def verify_db_structure(conn):
    """
    Verify that MeasTemp table and all required columns exist.
    Raises Exception if anything is missing.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='MeasTemp'")
    if not cursor.fetchone():
        raise Exception("Table 'MeasTemp' not found in MeasDB")

    cursor.execute("PRAGMA table_info(MeasTemp)")
    columns = [row[1] for row in cursor.fetchall()]

    required = ['Serial', 'BatchNo', 'MeasRes_0', 'MeasRes_-195',
                'MeasRes_-76', 'MeasRes_100', 'MeasRes_0_2nd']
    for col in required:
        if col not in columns:
            raise Exception(f"Column '{col}' not found in MeasTemp")
