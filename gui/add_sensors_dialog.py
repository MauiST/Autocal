"""
gui/add_sensors_dialog.py
=========================
PySide6 dialog for adding sensors to the database.
Replaces the standalone tkinter add_test_sensors.py tool.

Fields:
  Serial base, count, certificate (auto), tag, length (mm), batch number
Spreadsheet:
  Live table of all sensors currently in MeasTemp
"""

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFrame,
    QAbstractItemView,
)

import config

BATCH_SIZE = 6


# ------------------------------------------------------------------
# DB helpers  (no tkinter dependency)
# ------------------------------------------------------------------

def _next_cert_no(conn):
    """Return next CERT-XXXX number not yet in Sensors."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT CertificateNo FROM Sensors WHERE CertificateNo LIKE 'CERT-%'"
        )
        numbers = []
        for (val,) in cursor.fetchall():
            try:
                numbers.append(int(val.split('-')[1]))
            except (IndexError, ValueError):
                pass
        return f"CERT-{max(numbers, default=0) + 1:04d}"
    except Exception:
        return "CERT-0001"


def _next_batch_no(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(BatchNo) FROM MeasTemp")
    result = cursor.fetchone()[0]
    return 1 if result is None else result + 1


def _existing_batches(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT BatchNo FROM MeasTemp ORDER BY BatchNo")
    return [row[0] for row in cursor.fetchall()]


def _ensure_tag_length_cols(conn):
    """Add Tag / Length columns to Sensors if missing (schema migration)."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(Sensors)")
    existing = [row[1] for row in cursor.fetchall()]
    if 'Tag' not in existing:
        cursor.execute("ALTER TABLE Sensors ADD COLUMN Tag TEXT")
    if 'Length' not in existing:
        cursor.execute("ALTER TABLE Sensors ADD COLUMN Length REAL")
    conn.commit()


def _do_add_sensors(conn, serial_base, count, certificate_no,
                    tag, length, first_batch_no):
    """
    Insert sensors into Sensors + MeasTemp in batches of BATCH_SIZE.
    Returns (added [(serial, batch_no)], skipped [serial]).
    """
    _ensure_tag_length_cols(conn)
    cursor     = conn.cursor()
    serials    = [f"{serial_base}-{i:04d}" for i in range(1, count + 1)]
    added, skipped = [], []
    length_val = float(length) if length else None

    for idx, serial in enumerate(serials):
        batch_no = first_batch_no + (idx // BATCH_SIZE)
        cursor.execute("SELECT Serial FROM Sensors WHERE Serial = ?", (serial,))
        if cursor.fetchone():
            skipped.append(serial)
            continue
        cursor.execute("""
            INSERT INTO Sensors (Serial, CertificateNo, Type, Nominal, Tag, Length)
            VALUES (?, ?, 'PT100', 100.0, ?, ?)
        """, (serial, certificate_no, tag or None, length_val))
        cursor.execute("""
            INSERT OR IGNORE INTO MeasTemp (Serial, BatchNo) VALUES (?, ?)
        """, (serial, batch_no))
        added.append((serial, batch_no))

    conn.commit()
    return added, skipped


def _fetch_sheet_data(conn):
    """All MeasTemp rows joined with Sensors, ordered by batch then serial."""
    _ensure_tag_length_cols(conn)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.Serial, s.Tag, s.Length, m.BatchNo, s.CertificateNo
        FROM   MeasTemp m
        LEFT JOIN Sensors s ON m.Serial = s.Serial
        ORDER BY m.BatchNo, m.Serial
    """)
    return cursor.fetchall()


# ------------------------------------------------------------------
# Dialog
# ------------------------------------------------------------------

_ENTRY_STYLE = (
    "QLineEdit{"
    "  background-color:#dde1e5; border:1px solid #c2c8d0;"
    "  border-radius:8px; padding:5px 10px;"
    "  font-family:'Courier New'; font-size:11px; color:{color};"
    "  {extra}"
    "}"
    "QLineEdit:focus{ border:1px solid #4a7fa5; }"
)


def _entry(default="", width=150, color="#3a3f47", bold=False):
    e = QLineEdit(default)
    e.setFixedWidth(width)
    e.setStyleSheet(
        _ENTRY_STYLE.format(
            color=color,
            extra="font-weight:bold;" if bold else ""
        )
    )
    return e


class AddSensorsDialog(QDialog):
    """Modal dialog — Add Sensors to Autocal database."""

    sensors_added = Signal()   # emitted after each successful add

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Add Sensors  —  Senmatic Autocal")
        self.resize(880, 730)
        self.setMinimumSize(700, 560)
        self._build()
        self._refresh_all()

    # ----------------------------------------------------------
    # Layout
    # ----------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 14)
        root.setSpacing(0)

        # Title
        title = QLabel("Add Sensors to Database")
        title.setStyleSheet(
            "font-family:Georgia; font-size:15px; font-weight:bold; color:#4a7fa5;"
        )
        root.addWidget(title)

        db_lbl = QLabel(f"DB:  {config.DB_PATH}")
        db_lbl.setStyleSheet(
            "font-family:'Courier New'; font-size:8px; color:#7a8290;"
        )
        root.addWidget(db_lbl)
        root.addSpacing(10)

        root.addWidget(_hline())
        root.addSpacing(10)

        # ── Input card ──────────────────────────────────────────
        card = QGroupBox("SENSOR DETAILS")
        form = QFormLayout(card)
        form.setSpacing(9)
        form.setContentsMargins(14, 20, 14, 14)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.serial_entry = _entry("399048", width=140)
        form.addRow("Serial base  (e.g. 399048):", self.serial_entry)

        self.count_entry = _entry("6", width=60)
        form.addRow("Number of sensors:", self.count_entry)

        # Certificate row
        cert_h = QHBoxLayout()
        cert_h.setSpacing(8)
        self.cert_entry = _entry("loading...", width=115, color="#5a9e6f", bold=True)
        ref_btn = QPushButton("↺  Refresh")
        ref_btn.setFixedHeight(28)
        ref_btn.setFixedWidth(90)
        ref_btn.clicked.connect(self._refresh_cert)
        hint = QLabel("(editable if needed)")
        hint.setStyleSheet("color:#7a8290; font-size:9px; font-style:italic;")
        cert_h.addWidget(self.cert_entry)
        cert_h.addWidget(ref_btn)
        cert_h.addWidget(hint)
        cert_h.addStretch()
        form.addRow("Certificate No  (auto):", cert_h)

        self.tag_entry    = _entry("", width=180)
        form.addRow("Tag  (label / model):", self.tag_entry)

        self.length_entry = _entry("", width=80)
        form.addRow("Length  (mm):", self.length_entry)

        # Batch row
        batch_h = QHBoxLayout()
        batch_h.setSpacing(8)
        self.batch_combo = QComboBox()
        self.batch_combo.setEditable(True)
        self.batch_combo.setFixedWidth(115)
        new_btn = QPushButton("New batch")
        new_btn.setFixedHeight(28)
        new_btn.setFixedWidth(90)
        new_btn.clicked.connect(self._use_new_batch)
        batch_h.addWidget(self.batch_combo)
        batch_h.addWidget(new_btn)
        batch_h.addStretch()
        form.addRow("Batch number:", batch_h)

        root.addWidget(card)
        root.addSpacing(8)

        # Preview
        self.preview_lbl = QLabel("")
        self.preview_lbl.setStyleSheet(
            "font-family:'Courier New'; font-size:9px; color:#3a3f47; padding:2px 4px;"
        )
        root.addWidget(self.preview_lbl)
        self.serial_entry.textChanged.connect(self._update_preview)
        self.count_entry.textChanged.connect(self._update_preview)

        root.addSpacing(10)

        # Add button
        add_h = QHBoxLayout()
        self.add_btn = QPushButton("➕  Add Sensors to DB")
        self.add_btn.setFixedHeight(38)
        self.add_btn.setObjectName("batchesBtn")
        self.add_btn.clicked.connect(self._add)
        add_h.addWidget(self.add_btn)
        add_h.addStretch()
        root.addLayout(add_h)

        root.addSpacing(12)
        root.addWidget(_hline())
        root.addSpacing(6)

        # Spreadsheet header
        sheet_lbl = QLabel("Sensors in current session  (MeasTemp):")
        sheet_lbl.setStyleSheet("color:#7a8290; font-size:10px;")
        root.addWidget(sheet_lbl)
        root.addSpacing(4)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Serial Number", "Tag", "Length (mm)", "Batch", "Certificate"]
        )
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 95)
        self.table.setColumnWidth(3, 65)
        self.table.setColumnWidth(4, 120)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("alternate-background-color: #e2e6e9;")
        root.addWidget(self.table, 1)

        root.addSpacing(6)

        # Bottom row
        bot = QHBoxLayout()
        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self._refresh_all)

        clear_btn = QPushButton("🗑  Clear ALL MeasTemp")
        clear_btn.setFixedHeight(30)
        clear_btn.setStyleSheet(
            "QPushButton{border:1.5px solid #c0614a; color:#c0614a;"
            " border-radius:8px; padding:4px 12px;}"
            "QPushButton:hover{background-color:#c0614a; color:white;}"
        )
        clear_btn.clicked.connect(self._clear_meastemp)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color:#7a8290; font-size:9px;")

        bot.addWidget(refresh_btn)
        bot.addWidget(clear_btn)
        bot.addStretch()
        bot.addWidget(self.count_lbl)
        root.addLayout(bot)

    # ----------------------------------------------------------
    # Logic
    # ----------------------------------------------------------
    def _refresh_cert(self):
        try:
            self.cert_entry.setText(_next_cert_no(self.conn))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _update_preview(self):
        base = self.serial_entry.text().strip()
        try:
            n = int(self.count_entry.text().strip())
            if n < 1:
                raise ValueError
            num_batches = (n + BATCH_SIZE - 1) // BATCH_SIZE
            lines = []
            for i in range(1, min(n + 1, 4)):
                lines.append(
                    f"  {base}-{i:04d}  →  Batch +{(i - 1) // BATCH_SIZE}"
                )
            if n > 3:
                lines.append("  ...")
            lines.append(
                f"\n  {n} sensor(s)  →  {num_batches} batch(es) of max {BATCH_SIZE}"
            )
            self.preview_lbl.setText("\n".join(lines))
            self.preview_lbl.setStyleSheet(
                "font-family:'Courier New'; font-size:9px;"
                " color:#3a3f47; padding:2px 4px;"
            )
        except ValueError:
            self.preview_lbl.setText("  (enter a valid number)")
            self.preview_lbl.setStyleSheet(
                "font-family:'Courier New'; font-size:9px;"
                " color:#c0614a; padding:2px 4px;"
            )

    def _use_new_batch(self):
        try:
            self.batch_combo.setCurrentText(str(_next_batch_no(self.conn)))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _refresh_all(self):
        try:
            self.cert_entry.setText(_next_cert_no(self.conn))

            batches  = _existing_batches(self.conn)
            next_no  = _next_batch_no(self.conn)
            values   = [str(b) for b in batches] + [f"{next_no} (new)"]
            self.batch_combo.clear()
            self.batch_combo.addItems(values)
            if values:
                self.batch_combo.setCurrentIndex(len(values) - 1)

            rows = _fetch_sheet_data(self.conn)
            self.table.setRowCount(0)
            for serial, tag, length, batch_no, cert_no in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)
                length_str = f"{length:.0f}" if length is not None else ""
                for col, val in enumerate([
                    serial or "", tag or "", length_str,
                    str(batch_no), cert_no or ""
                ]):
                    item = QTableWidgetItem(val)
                    if col in (2, 3):
                        item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(r, col, item)

            total        = len(rows)
            batches_used = len({r[3] for r in rows})
            self.count_lbl.setText(
                f"{total} sensor(s) in {batches_used} batch(es)"
            )
        except Exception as e:
            QMessageBox.warning(self, "Refresh Error", str(e))

        self._update_preview()

    def _add(self):
        base    = self.serial_entry.text().strip()
        count_s = self.count_entry.text().strip()
        cert    = self.cert_entry.text().strip()
        tag     = self.tag_entry.text().strip()
        length  = self.length_entry.text().strip()
        batch_s = self.batch_combo.currentText().replace(" (new)", "").strip()

        if not base:
            QMessageBox.warning(self, "Input Error", "Serial base cannot be empty.")
            return
        try:
            count = int(count_s)
            if not 1 <= count <= 100:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Input Error",
                                "Number of sensors must be 1–100.")
            return
        if length:
            try:
                float(length)
            except ValueError:
                QMessageBox.warning(self, "Input Error",
                                    "Length must be a number (mm).")
                return
        try:
            first_batch = int(batch_s)
        except ValueError:
            QMessageBox.warning(self, "Input Error",
                                "Select or enter a valid batch number.")
            return

        added, skipped = _do_add_sensors(
            self.conn, base, count, cert, tag, length, first_batch
        )

        summary = defaultdict(list)
        for serial, batch_no in added:
            summary[batch_no].append(serial)

        msg = (f"Added {len(added)} sensor(s) across "
               f"{len(summary)} batch(es):\n\n")
        for bn in sorted(summary):
            msg += f"  Batch {bn}:  {len(summary[bn])} sensors\n"
        if skipped:
            msg += f"\nSkipped {len(skipped)} already existing:\n"
            msg += "  " + ", ".join(skipped[:10])
            if len(skipped) > 10:
                msg += f"  ... (+{len(skipped) - 10} more)"

        QMessageBox.information(self, "Done", msg)
        self.sensors_added.emit()
        self._refresh_all()

    def _clear_meastemp(self):
        reply = QMessageBox.question(
            self, "Clear MeasTemp",
            "This will delete ALL rows from MeasTemp.\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.conn.execute("DELETE FROM MeasTemp")
        self.conn.commit()
        self._refresh_all()
        QMessageBox.information(self, "Done", "MeasTemp cleared.")


# ------------------------------------------------------------------
def _hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: #c2c8d0;")
    return f
