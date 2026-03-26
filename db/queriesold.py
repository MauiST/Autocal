from db.connection import connect_db


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


def fetch_progress_data(conn):
    """Fetch all rows from MeasTemp for the progress popup."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Serial, BatchNo, MeasRes_0, MeasRes_-195, MeasRes_-76,
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


# Bath point column mapping for full result save
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
        'res':      'MeasRes_-195',
        'temp':     'MeasTemp(-195)',
        'dev_res':  'DevResEN60751(-195)',
        'dev_temp': 'DevTempEN60751(-195)',
    },
    3: {
        'ref_temp': 'CalculatedTempRef(-76)',
        'res':      'MeasRes_-76',
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
    Returns sensor_class so caller can log FAIL without saving.

    Args:
        conn         : sqlite3 connection
        serial       : str   -- sensor serial
        bath_no      : int   -- bath number (1-5)
        t_ref        : float -- ITS-90 reference temperature
        r_measured   : float -- measured resistance in ohms
        t_sensor     : float -- CVD calculated temperature
        dev_temp     : float -- temperature deviation
        dev_res      : float -- resistance deviation
        sensor_class : str   -- EN 60751 class

    Returns:
        bool -- True if saved, False if FAIL
    """
    if sensor_class == 'FAIL':
        return False

    cols = BATH_COLUMNS.get(bath_no)
    if not cols:
        return False

    import datetime
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
        round(t_ref,     5),
        round(r_measured, 7),
        round(t_sensor,  5),
        round(dev_res,   7),
        round(dev_temp,  5),
        now.strftime('%Y-%m-%d'),
        now.strftime('%H:%M:%S'),
        serial
    ))
    conn.commit()
    return True


# --- CERTIFICATE LOADER QUERIES ---

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
