"""
tools/report.py
===============
Generates formatted calibration report text files from MeasTemp data.

One file per certificate, saved to ~/Documents/MeasDB/Reports/
Filename: Measured {N} - Certificate {cert_no}.txt

Usage:
    from tools.report import generate_reports
    paths = generate_reports(conn)
"""

import os
import re
import datetime


# Output directory
REPORT_DIR = os.path.join(
    os.path.expanduser("~/Documents"), "MeasDB", "Reports"
)

# Bath definitions for the report rows
BATH_ROWS = [
    (1, 'Bath 1 1st', '   0°C', 'MeasRes_0',    'CalculatedTempRef(0)',
     'MeasTemp(0)', 'DevResEN60751(0)', 'DevTempEN60751(0)'),
    (2, 'Bath 2  ', '-195°C', 'MeasRes_n195', 'CalculatedTempRef(-195)',
     'MeasTemp(-195)', 'DevResEN60751(-195)', 'DevTempEN60751(-195)'),
    (3, 'Bath 3  ', ' -76°C', 'MeasRes_n76',  'CalculatedTempRef(-76)',
     'MeasTemp(-76)', 'DevResEN60751(-76)', 'DevTempEN60751(-76)'),
    (4, 'Bath 4  ', ' 100°C', 'MeasRes_100',  'CalculatedTempRef(100)',
     'MeasTemp(100)', 'DevResEN60751(100)', 'DevTempEN60751(100)'),
]


def _next_sequence(cert_no, out_dir):
    """Return the next unused sequence number for a certificate."""
    if not os.path.isdir(out_dir):
        return 1
    pattern = re.compile(
        r'^Measured\s+(\d+)\s+-\s+Certificate\s+' + re.escape(str(cert_no)),
        re.IGNORECASE
    )
    numbers = [
        int(m.group(1))
        for f in os.listdir(out_dir)
        for m in [pattern.match(f)]
        if m
    ]
    return max(numbers, default=0) + 1


def _fmt_val(val, decimals, width):
    """Format a float or return '---' if None, right-aligned in given width."""
    if val is None:
        return '---'.rjust(width)
    return f'{val:.{decimals}f}'.rjust(width)


def _overall_class(rows):
    """
    Determine the worst EN60751 class from a sensor's bath rows.
    Class priority: FAIL > C > B > A > AA
    Returns a string or None if no data.
    """
    priority = {'AA': 0, 'A': 1, 'B': 2, 'C': 3, 'FAIL': 4}
    worst = None
    for row in rows:
        cls = row.get('class')
        if cls and cls in priority:
            if worst is None or priority[cls] > priority[worst]:
                worst = cls
    return worst


def _class_from_dev_temp(dev_temp_c):
    """
    Infer EN60751 class from |ΔT| in °C.
    AA: 0.1, A: 0.15 + 0.002*|T|  (at 0C: 0.15), B: 0.3+0.005*|T|, C: 0.6+0.01*|T|
    Approximate at each bath; stored DevTemp values come from CVD calculation.
    """
    if dev_temp_c is None:
        return None
    dt = abs(dev_temp_c)
    if dt <= 0.100:
        return 'AA'
    elif dt <= 0.150:
        return 'A'
    elif dt <= 0.300:
        return 'B'
    elif dt <= 0.600:
        return 'C'
    return 'FAIL'


def fetch_report_data(conn):
    """
    Fetch all measurement data from MeasTemp joined with Sensors.

    Returns:
        dict { cert_no: [ {serial, batch_no, date, time, baths: [...], res_0_2nd} ] }
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            m.Serial,
            m.BatchNo,
            s.CertificateNo,
            m.Date,
            m.Time,

            m."MeasRes_0",
            m."CalculatedTempRef(0)",
            m."MeasTemp(0)",
            m."DevResEN60751(0)",
            m."DevTempEN60751(0)",

            m."MeasRes_n195",
            m."CalculatedTempRef(-195)",
            m."MeasTemp(-195)",
            m."DevResEN60751(-195)",
            m."DevTempEN60751(-195)",

            m."MeasRes_n76",
            m."CalculatedTempRef(-76)",
            m."MeasTemp(-76)",
            m."DevResEN60751(-76)",
            m."DevTempEN60751(-76)",

            m."MeasRes_100",
            m."CalculatedTempRef(100)",
            m."MeasTemp(100)",
            m."DevResEN60751(100)",
            m."DevTempEN60751(100)",

            m."MeasRes_0_2nd",
            m.Skipped
        FROM MeasTemp m
        LEFT JOIN Sensors s ON m.Serial = s.Serial
        WHERE m.Skipped = 1
           OR m."MeasRes_0"    IS NOT NULL
           OR m."MeasRes_n195" IS NOT NULL
           OR m."MeasRes_n76"  IS NOT NULL
           OR m."MeasRes_100"  IS NOT NULL
        ORDER BY s.CertificateNo, m.BatchNo, m.Serial
    """)
    rows = cursor.fetchall()

    by_cert = {}
    for row in rows:
        (serial, batch_no, cert_no, date, time_,
         r0,    tref0,    temp0,    dres0,    dtemp0,
         rn195, trefn195, tempn195, dresn195, dtempn195,
         rn76,  trefn76,  tempn76,  dresn76,  dtempn76,
         r100,  tref100,  temp100,  dres100,  dtemp100,
         r0_2nd, skipped) = row

        cert_key = str(cert_no) if cert_no else 'UNKNOWN'
        if cert_key not in by_cert:
            by_cert[cert_key] = []

        baths = [
            {'label': 'Bath 1 1st', 'point': '0°C',
             'res': r0,    'tref': tref0,    'tsens': temp0,
             'dres': dres0,    'dtemp': dtemp0,
             'class': _class_from_dev_temp(dtemp0)},
            {'label': 'Bath 2  ', 'point': '-195°C',
             'res': rn195, 'tref': trefn195, 'tsens': tempn195,
             'dres': dresn195, 'dtemp': dtempn195,
             'class': _class_from_dev_temp(dtempn195)},
            {'label': 'Bath 3  ', 'point': '-76°C',
             'res': rn76,  'tref': trefn76,  'tsens': tempn76,
             'dres': dresn76,  'dtemp': dtempn76,
             'class': _class_from_dev_temp(dtempn76)},
            {'label': 'Bath 4  ', 'point': '100°C',
             'res': r100,  'tref': tref100,  'tsens': temp100,
             'dres': dres100,  'dtemp': dtemp100,
             'class': _class_from_dev_temp(dtemp100)},
        ]

        by_cert[cert_key].append({
            'serial':   serial,
            'batch_no': batch_no,
            'date':     date or '',
            'time':     time_ or '',
            'skipped':  bool(skipped),
            'baths':    baths,
            'res_0_2nd': r0_2nd,
        })

    return by_cert


def _format_report(cert_no, sensors, seq_no):
    """Build the full report text for one certificate."""
    W = 78   # total line width
    now = datetime.datetime.now()

    lines = []
    def line(s=''):
        lines.append(s)

    line('=' * W)
    line('  SENMATIC CALIBRATION SYSTEM')
    line('  PT100 Temperature Sensor Calibration Report')
    line()
    line(f'  Certificate No : {cert_no}')
    line(f'  Report No      : {seq_no}')
    line(f'  Generated      : {now.strftime("%Y-%m-%d  %H:%M:%S")}')
    line('=' * W)

    for s in sensors:
        line()
        if s['skipped']:
            line(f'  Serial: {s["serial"]}   [SKIPPED]')
            line('-' * W)
            continue

        meas_date = s['date'] + '  ' + s['time'] if s['date'] else '(not measured)'
        line(f'  Serial: {s["serial"]}   Batch: {s["batch_no"]}   Measured: {meas_date}')
        line('-' * W)

        # Column headers
        line(
            f'  {"Bath":9}  {"Point":7}  '
            f'{"Ref Temp(°C)":>13}  {"Resistance(Ω)":>14}  '
            f'{"Sens Temp(°C)":>13}  {"ΔRes(Ω)":>11}  {"ΔTemp(mK)":>9}  {"Class":5}'
        )
        line('  ' + '-' * (W - 2))

        for b in s['baths']:
            # ΔTemp in mK
            dtemp_mk = f'{b["dtemp"] * 1000:+.2f}' if b['dtemp'] is not None else '---'
            line(
                f'  {b["label"]:9}  {b["point"]:7}  '
                f'{_fmt_val(b["tref"],  5, 13)}  '
                f'{_fmt_val(b["res"],   7, 14)}  '
                f'{_fmt_val(b["tsens"], 5, 13)}  '
                f'{_fmt_val(b["dres"],  7, 11)}  '
                f'{dtemp_mk:>9}  '
                f'{(b["class"] or "---"):5}'
            )

        # Bath 1 2nd row
        r2nd = s['res_0_2nd']
        r2nd_str = f'{r2nd:.7f}' if r2nd is not None else '---'
        line(
            f'  {"Bath 1 2nd":9}  {"0°C":7}  '
            f'{"":>13}  {r2nd_str:>14}  '
            f'{"":>13}  {"":>11}  {"":>9}  '
            f'{"(2nd)":5}'
        )

        # Overall class
        overall = _overall_class(s['baths']) or '---'
        line('  ' + '-' * (W - 2))
        line(f'  Overall Classification: {overall}')
        line('-' * W)

    line()
    line('=' * W)
    line('  End of Report')
    line('=' * W)

    return '\n'.join(lines)


def generate_reports(conn, out_dir=None):
    """
    Generate one report file per certificate from current MeasTemp data.

    Args:
        conn    : sqlite3 connection
        out_dir : output directory (defaults to ~/Documents/MeasDB/Reports)

    Returns:
        list of file paths written
    """
    if out_dir is None:
        out_dir = REPORT_DIR

    os.makedirs(out_dir, exist_ok=True)

    by_cert = fetch_report_data(conn)
    if not by_cert:
        return []

    written = []
    for cert_no, sensors in sorted(by_cert.items()):
        seq = _next_sequence(cert_no, out_dir)
        filename = f'Measured {seq} - Certificate {cert_no}.txt'
        path = os.path.join(out_dir, filename)

        text = _format_report(cert_no, sensors, seq)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

        written.append(path)

    return written
