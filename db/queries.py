"""
queries.py
==========
All database queries for the calibration application.

New in this version:
  - fetch_bath1_results()     -- load Bath 1-1 results for 20mK comparison
  - compare_bath1_results()   -- compare Bath 1-2 vs 1-1, return warnings
  - fetch_batch_with_cert()   -- fetch serials with certificate info for session display
  - mark_sensor_skipped()     -- mark sensor as skipped in MeasTemp (leaves data blank)
"""

import datetime


# =============================================================
# --- BATCH / SERIAL QUERIES
# =============================================================

def fetch_available_batches(conn):
    """Returns list of batch numbers that have serials in MeasTemp."""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT BatchNo FROM MeasTemp ORDER BY BatchNo")
    return [row[0] for row in cursor.fetchall()]


def fetch_certificates(conn):
    """Fetch distinct CertificateNo values linked to serials in MeasTemp."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT s.CertificateNo
            FROM Sensors s
            INNER JOIN MeasTemp m ON s.Serial = m.Serial
            ORDER BY s.CertificateNo
        """)
        return [str(row[0]) for row in cursor.fetchall()]
    except Exception:
        return []


def fetch_batch_serials(conn, batch_no):
    """Fetch all serials for a given batch number."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT Serial FROM MeasTemp WHERE BatchNo = ? ORDER BY Serial",
        (batch_no,)
    )
    return [row[0].strip() for row in cursor.fetchall()]


def fetch_batch_with_cert(conn, batch_no):
    """
    Fetch serials for a batch with their certificate numbers.
    Used for the session sensor list display.

    Returns list of (serial, certificate_no) tuples.
    certificate_no may be None if not found in Sensors table.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.Serial, s.CertificateNo
            FROM MeasTemp m
            LEFT JOIN Sensors s ON m.Serial = s.Serial
            WHERE m.BatchNo = ?
            ORDER BY m.Serial
        """, (batch_no,))
        return [(row[0].strip(), row[1]) for row in cursor.fetchall()]
    except Exception:
        # Fallback -- return serials without cert info
        return [(s, None) for s in fetch_batch_serials(conn, batch_no)]


def fetch_all_session_sensors(conn, session_config):
    """
    Fetch all serials and certificate info for a full session config.
    Used to populate the sensor list panel on the session page.

    Args:
        session_config : list of dicts with 'bath_no' and 'batches' keys

    Returns:
        list of dicts: {serial, batch_no, bath_no, certificate_no}
    """
    result = []
    for item in session_config:
        bath_no = item['bath_no']
        for bn in item['batches']:
            rows = fetch_batch_with_cert(conn, bn)
            for serial, cert in rows:
                result.append({
                    'serial':         serial,
                    'batch_no':       bn,
                    'bath_no':        bath_no,
                    'certificate_no': cert or '—',
                })
    return result


# =============================================================
# --- PROGRESS / STATUS QUERIES
# =============================================================

def fetch_progress_data(conn):
    """Fetch all rows from MeasTemp for the progress popup."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Serial, BatchNo, MeasRes_0, MeasRes_n195, MeasRes_n76,
               MeasRes_100, MeasRes_0_2nd
        FROM MeasTemp ORDER BY BatchNo, Serial
    """)
    return cursor.fetchall()


def save_reading(conn, serial, value, column):
    """Save a stable resistance reading to the correct column for a serial."""
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE MeasTemp SET {column} = ? WHERE Serial = ?",
        (round(value, 7), serial)
    )
    conn.commit()


# =============================================================
# --- BATH 1-2 vs 1-1 COMPARISON
# =============================================================

def fetch_bath1_results(conn, serials):
    """
    Fetch Bath 1-1 resistance and temperature results for a list of serials.
    Used to compare against Bath 1-2 measurements.

    Returns:
        dict {serial: {'resistance': float, 'temperature': float}}
        Values are None if not yet measured.
    """
    results = {}
    cursor  = conn.cursor()
    for serial in serials:
        try:
            cursor.execute("""
                SELECT MeasRes_0, "MeasTemp(0)", "CalculatedTempRef(0)"
                FROM MeasTemp
                WHERE Serial = ?
            """, (serial,))
            row = cursor.fetchone()
            if row and row[0] is not None:
                results[serial] = {
                    'resistance':   float(row[0]),
                    'temp_sensor':  float(row[1]) if row[1] is not None else None,
                    'temp_ref':     float(row[2]) if row[2] is not None else None,
                }
            else:
                results[serial] = None
        except Exception:
            results[serial] = None
    return results


def compare_bath1_results(serial, r_bath1_2, t_ref_bath1_2,
                           r_bath1_1, t_ref_bath1_1,
                           resistance_warn_mk=20.0,
                           temperature_warn_mk=10.0):
    """
    Compare Bath 1-2 measurement against Bath 1-1 for a single sensor.

    Resistance comparison uses CVD sensitivity ~0.3851 Ohm/K for PT100:
        delta_R / 0.3851 * 1000 = delta_mK

    Args:
        serial              : str
        r_bath1_2           : float -- resistance at Bath 1-2
        t_ref_bath1_2       : float -- bath temperature at Bath 1-2
        r_bath1_1           : float -- resistance at Bath 1-1
        t_ref_bath1_1       : float -- bath temperature at Bath 1-1
        resistance_warn_mk  : float -- threshold in mK (default 20)
        temperature_warn_mk : float -- threshold in mK (default 10)

    Returns:
        list of warning strings (empty if all OK)
    """
    warnings = []

    if r_bath1_1 is None or r_bath1_2 is None:
        return warnings

    # Resistance drift -- convert Ohm difference to mK
    # PT100 sensitivity approx 0.3851 Ohm/K  ->  1 mOhm = 2.596 mK
    CVD_SENSITIVITY = 0.3851   # Ohm/K for PT100 at 0C
    delta_r  = abs(r_bath1_2 - r_bath1_1)
    delta_mk = (delta_r / CVD_SENSITIVITY) * 1000.0

    if delta_mk > resistance_warn_mk:
        warnings.append(
            f"[{serial}]  Bath 1-2 vs 1-1 resistance drift:  "
            f"{delta_mk:.1f} mK  (limit: {resistance_warn_mk:.0f} mK)\n"
            f"  R(1-1)={r_bath1_1:.7f}Ω   R(1-2)={r_bath1_2:.7f}Ω"
        )

    # Bath temperature drift
    if t_ref_bath1_1 is not None and t_ref_bath1_2 is not None:
        delta_t_mk = abs(t_ref_bath1_2 - t_ref_bath1_1) * 1000.0
        if delta_t_mk > temperature_warn_mk:
            warnings.append(
                f"[{serial}]  Bath temperature drift between 1-1 and 1-2:  "
                f"{delta_t_mk:.1f} mK  (limit: {temperature_warn_mk:.0f} mK)\n"
                f"  T(1-1)={t_ref_bath1_1:.5f}C   T(1-2)={t_ref_bath1_2:.5f}C"
            )

    return warnings


# =============================================================
# --- SKIP SENSOR
# =============================================================

def mark_sensor_skipped(conn, serial):
    """
    Mark a sensor as skipped in MeasTemp.
    Sets a Skipped flag if column exists, otherwise leaves record blank.
    Does NOT delete or overwrite any measurement data.

    Returns True if marked, False if serial not found.
    """
    cursor = conn.cursor()

    # Check if Skipped column exists -- add it if not
    cursor.execute("PRAGMA table_info(MeasTemp)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'Skipped' not in columns:
        try:
            cursor.execute("ALTER TABLE MeasTemp ADD COLUMN Skipped INTEGER DEFAULT 0")
            conn.commit()
        except Exception:
            pass   # Column may already exist in concurrent situation

    cursor.execute(
        "UPDATE MeasTemp SET Skipped = 1 WHERE Serial = ?",
        (serial,)
    )
    conn.commit()
    return cursor.rowcount > 0


def clear_sensor_skip(conn, serial):
    """Remove skip flag from a sensor so it can be measured again."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE MeasTemp SET Skipped = 0 WHERE Serial = ?",
        (serial,)
    )
    conn.commit()


def fetch_skipped_serials(conn, batch_no):
    """Return list of skipped serials in a batch."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT Serial FROM MeasTemp WHERE BatchNo = ? AND Skipped = 1",
            (batch_no,)
        )
        return [row[0].strip() for row in cursor.fetchall()]
    except Exception:
        return []


# =============================================================
# --- FULL RESULT SAVE
# =============================================================

# Bath point column mapping
BATH_COLUMNS = {
    1: {
        'ref_temp': 'CalculatedTempRef(0)',
        'res':      'MeasRes_0',
        'temp':     'MeasTemp(0)',
        'dev_res':  'DevResEN60751(0)',
        'dev_temp': 'DevTempEN60751(0)',
    },
    2: {
        'ref_temp': 'CalculatedTempRef(-195)',
        'res':      'MeasRes_n195',
        'temp':     'MeasTemp(-195)',
        'dev_res':  'DevResEN60751(-195)',
        'dev_temp': 'DevTempEN60751(-195)',
    },
    3: {
        'ref_temp': 'CalculatedTempRef(-76)',
        'res':      'MeasRes_n76',
        'temp':     'MeasTemp(-76)',
        'dev_res':  'DevResEN60751(-76)',
        'dev_temp': 'DevTempEN60751(-76)',
    },
    4: {
        'ref_temp': 'CalculatedTempRef(100)',
        'res':      'MeasRes_100',
        'temp':     'MeasTemp(100)',
        'dev_res':  'DevResEN60751(100)',
        'dev_temp': 'DevTempEN60751(100)',
    },
    5: {
        'ref_temp': 'CalculatedTempRef(0)',
        'res':      'MeasRes_0_2nd',
        'temp':     'MeasTemp(0)',
        'dev_res':  'DevResEN60751(0)',
        'dev_temp': 'DevTempEN60751(0)',
    },
}


def save_full_result(conn, serial, bath_no, t_ref, r_measured,
                     t_sensor, dev_temp, dev_res, sensor_class):
    """
    Save full calibration result for one sensor at one bath point.
    Only saves if sensor class is AA, A, B or C.

    Returns:
        bool -- True if saved, False if FAIL
    """
    if sensor_class == 'FAIL':
        return False

    cols = BATH_COLUMNS.get(bath_no)
    if not cols:
        return False

    now = datetime.datetime.now()
    cursor = conn.cursor()
    cursor.execute(f"""
        UPDATE MeasTemp SET
            "{cols['ref_temp']}" = ?,
            "{cols['res']}"      = ?,
            "{cols['temp']}"     = ?,
            "{cols['dev_res']}"  = ?,
            "{cols['dev_temp']}" = ?,
            "Date" = ?,
            "Time" = ?
        WHERE Serial = ?
    """, (
        round(t_ref,      5),
        round(r_measured, 7),
        round(t_sensor,   5),
        round(dev_res,    7),
        round(dev_temp,   5),
        now.strftime('%Y-%m-%d'),
        now.strftime('%H:%M:%S'),
        serial
    ))
    conn.commit()
    return True


# =============================================================
# --- CERTIFICATE / MEASTEMP MANAGEMENT
# =============================================================

def fetch_serials_by_certificate(conn, certificate_no):
    """Fetch all serials belonging to a CertificateNo from Sensors table."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT Serial FROM Sensors WHERE CertificateNo = ? ORDER BY Serial",
        (certificate_no,)
    )
    return [row[0].strip() for row in cursor.fetchall()]


def get_current_meastemp(conn):
    """Returns current contents of MeasTemp as a list of (BatchNo, Serial)."""
    cursor = conn.cursor()
    cursor.execute("SELECT BatchNo, Serial FROM MeasTemp ORDER BY BatchNo, Serial")
    return cursor.fetchall()


def get_next_batch_no(conn):
    """Returns the next available batch number in MeasTemp."""
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(BatchNo) FROM MeasTemp")
    result = cursor.fetchone()[0]
    return 1 if result is None else result + 1


def delete_meastemp(conn):
    """Clears all rows from MeasTemp."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM MeasTemp")
    conn.commit()


def insert_batches_into_meastemp(conn, batches):
    """
    Inserts batch/serial pairs into MeasTemp.
    batches: dict {batch_no: [serials]}
    """
    cursor = conn.cursor()
    for batch_no, serials in batches.items():
        for serial in serials:
            cursor.execute(
                "INSERT INTO MeasTemp (Serial, BatchNo) VALUES (?, ?)",
                (serial, batch_no)
            )
    conn.commit()
