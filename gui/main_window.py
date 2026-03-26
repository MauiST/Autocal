"""
main_window.py
==============
Main application window with sidebar navigation.

Pages:
  1. Session   -- bath config, batch selection, timers, sensor list, start/stop
  2. CNC       -- CNC 1 & 2 connection, jog, home, connect/disconnect
  3. Progress  -- live readings table, stability, batch queue
  4. Config    -- all settings editable, saved to DB Config table
"""

import time
import hashlib
import importlib
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QComboBox, QPushButton, QTextEdit,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QTimeEdit, QStackedWidget, QSizePolicy,
    QMessageBox, QDialog, QScrollArea, QFrame, QLineEdit,
    QFormLayout, QTabWidget, QSpacerItem
)
from PySide6.QtCore import Qt, QTimer, QTime, Signal
from PySide6.QtGui import QColor, QFont

import config
from config import BATH_LABEL, BATH_WAIT_DEFAULT, REF_SENSOR_ID, PROGRESS_COLS
from db.connection import connect_db
from db.queries import (
    fetch_available_batches, fetch_certificates,
    fetch_all_session_sensors, mark_sensor_skipped, clear_sensor_skip
)
from instruments.bridge import bridge_connect, bridge_close
from gui.worker import MeasurementWorker
from gui.progress_dialog import ProgressDialog
from gui.sim_dialog import SimDialog
from gui.styles import NEU_STYLE


# ------------------------------------------------------------------
# Session Log Window
# ------------------------------------------------------------------
class SessionLogWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Log")
        self.setMinimumSize(720, 500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Courier New", 11))
        layout.addWidget(self.log_box)

        btn_h = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self.log_box.clear)
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.hide)
        btn_h.addStretch()
        btn_h.addWidget(clear_btn)
        btn_h.addWidget(close_btn)
        layout.addLayout(btn_h)

    def append(self, msg):
        self.log_box.append(msg)
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event):
        self.hide()
        event.ignore()


# ------------------------------------------------------------------
# Change Password Dialog
# ------------------------------------------------------------------
class ChangePasswordDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn    = conn
        self.changed = False
        self.setWindowTitle("Change Config Password")
        self.setFixedSize(380, 240)
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowCloseButtonHint
        )
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(12)

        title = QLabel("Change Configuration Password")
        title.setStyleSheet(
            "font-family: Georgia; font-size: 13px; font-weight: bold;"
            "color: #4a7fa5;"
        )
        v.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)

        self._pwd_current = QLineEdit()
        self._pwd_current.setEchoMode(QLineEdit.Password)
        self._pwd_current.setPlaceholderText("Enter current password")
        self._pwd_new = QLineEdit()
        self._pwd_new.setEchoMode(QLineEdit.Password)
        self._pwd_new.setPlaceholderText("Min 6 characters")
        self._pwd_confirm = QLineEdit()
        self._pwd_confirm.setEchoMode(QLineEdit.Password)
        self._pwd_confirm.setPlaceholderText("Repeat new password")
        self._pwd_confirm.returnPressed.connect(self._apply)

        form.addRow("Current password:", self._pwd_current)
        form.addRow("New password:",     self._pwd_new)
        form.addRow("Confirm:",          self._pwd_confirm)
        v.addLayout(form)

        btn_h = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.setFixedWidth(90)
        apply_btn.setObjectName("startBtn")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(90)
        cancel_btn.clicked.connect(self.reject)
        btn_h.addStretch()
        btn_h.addWidget(cancel_btn)
        btn_h.addWidget(apply_btn)
        v.addLayout(btn_h)

    def _apply(self):
        if not self.conn:
            QMessageBox.warning(self, "No DB", "No database connection.")
            return

        current = self._pwd_current.text()
        new_pwd = self._pwd_new.text()
        confirm = self._pwd_confirm.text()

        current_hash = hashlib.sha256(current.encode()).hexdigest()
        stored_hash  = config.get(
            'config_password_hash',
            '55a76fa549255ec2626ff874cf20c47f9e47d5d55dfba2679829b8878bfeabe7'
        )
        if current_hash != stored_hash:
            QMessageBox.warning(self, "Error", "Current password is incorrect.")
            self._pwd_current.clear()
            self._pwd_current.setFocus()
            return
        if not new_pwd:
            QMessageBox.warning(self, "Error", "New password cannot be empty.")
            return
        if len(new_pwd) < 6:
            QMessageBox.warning(self, "Error", "Password must be at least 6 characters.")
            return
        if new_pwd != confirm:
            QMessageBox.warning(self, "Error", "Passwords do not match.")
            self._pwd_confirm.clear()
            self._pwd_confirm.setFocus()
            return

        new_hash = hashlib.sha256(new_pwd.encode()).hexdigest()
        config.save_config(self.conn, 'config_password_hash', new_hash)
        self.changed = True
        QMessageBox.information(self, "Success", "Password changed successfully.")
        self.accept()


# ------------------------------------------------------------------
# Sidebar nav button
# ------------------------------------------------------------------
class NavButton(QPushButton):
    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self.setText(f"  {icon}   {label}")
        self.setCheckable(True)
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 10px;
                color: #7a8290;
                font-family: 'Georgia', serif;
                font-size: 13px;
                text-align: left;
                padding-left: 14px;
            }
            QPushButton:hover {
                background-color: #dde1e5;
                color: #3a3f47;
            }
            QPushButton:checked {
                background-color: #dde1e5;
                color: #4a7fa5;
                font-weight: bold;
                border-left: 3px solid #4a7fa5;
            }
        """)


# ------------------------------------------------------------------
# Main Window
# ------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Senmatic  |  Calibration System")
        self.setMinimumSize(1300, 860)

        self.conn              = connect_db()
        config.load_config(self.conn)

        self.available_batches = fetch_available_batches(self.conn) if self.conn else []
        self.certificates      = fetch_certificates(self.conn) if self.conn else []
        self.bridge            = None
        self.cnc1              = None
        self.cnc2              = None
        self.sim_dialog        = None
        self.qtimers           = {}
        self.elapsed           = {}
        self.wait_times        = {}
        self.worker            = None
        self.sensor_rows       = {}
        self.skipped_sensors   = set()
        self._session_config   = []
        self._config_unlocked  = False   # Config page locked by default

        self._build_ui()
        self.setStyleSheet(NEU_STYLE)
        self.log_window  = SessionLogWindow(self)
        self.sim_dialog  = SimDialog(self)
        self._connect_bridge_on_startup()

    # ----------------------------------------------------------
    # CNC MODULE SAFE LOADER
    # ----------------------------------------------------------
    @property
    def _cnc(self):
        """
        Safely import cnc.control at runtime.
        Returns the module or None if not found, logging a clear message.
        """
        try:
            return importlib.import_module('cnc.control')
        except ModuleNotFoundError:
            self.log(
                "  ⚠ [CNC] Module 'cnc.control' not found.\n"
                "  Make sure cnc/__init__.py exists and the app is run\n"
                "  from the project root folder."
            )
            return None

    # ----------------------------------------------------------
    # HARDWARE
    # ----------------------------------------------------------
    def _connect_bridge_on_startup(self):
        self.log("  Connecting to Micro-K 70 bridge...")
        self.bridge = bridge_connect()
        if self.bridge:
            self.log("  [BRIDGE] Connected -- Micro-K 70 ready.")
            self._set_status(self.bridge_dot, self.bridge_lbl, "BRIDGE", True)
            self.sim_btn.setVisible(False)
        else:
            self.log("  [BRIDGE] Not found -- simulation mode active.")
            self._set_status(self.bridge_dot, self.bridge_lbl, "BRIDGE", False)
            self.sim_btn.setVisible(True)

    def _reconnect_bridge(self):
        if self.bridge:
            bridge_close(self.bridge)
        self._connect_bridge_on_startup()

    def _set_status(self, dot, lbl, name, connected):
        color = "#5a9e6f" if connected else "#c0614a"
        dot.setStyleSheet(
            f"color: {color}; font-size: 16px; font-weight: bold;"
        )
        lbl.setText(name)
        lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: bold;"
        )

    # ----------------------------------------------------------
    # UI CONSTRUCTION
    # ----------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_h = QHBoxLayout(central)
        main_h.setSpacing(0)
        main_h.setContentsMargins(0, 0, 0, 0)

        # ── SIDEBAR ───────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background-color: #e0e4e8; border-right: 1px solid #c2c8d0;")
        side_v = QVBoxLayout(sidebar)
        side_v.setContentsMargins(10, 20, 10, 20)
        side_v.setSpacing(4)

        # Logo / title
        title_lbl = QLabel("SENMATIC")
        title_lbl.setStyleSheet(
            "color: #4a7fa5; font-family: 'Georgia'; font-size: 16px;"
            "font-weight: bold; letter-spacing: 3px; padding: 0 0 16px 8px;"
        )
        side_v.addWidget(title_lbl)

        # Nav buttons
        self.nav_buttons = []
        pages = [
            ("▶", "Session"),
            ("⚙", "CNC"),
            ("📊", "Progress"),
            ("🔧", "Config"),
        ]
        for icon, label in pages:
            btn = NavButton(icon, label)
            btn.clicked.connect(lambda checked, l=label: self._switch_page(l))
            side_v.addWidget(btn)
            self.nav_buttons.append((label, btn))

        side_v.addStretch()

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color: #c2c8d0;")
        side_v.addWidget(div)

        # Status indicators
        status_grid = QGridLayout()
        status_grid.setSpacing(4)

        self.bridge_dot = QLabel("●")
        self.bridge_lbl = QLabel("BRIDGE")
        self.cnc1_dot   = QLabel("●")
        self.cnc1_lbl   = QLabel("CNC 1")
        self.cnc2_dot   = QLabel("●")
        self.cnc2_lbl   = QLabel("CNC 2")

        for dot in [self.bridge_dot, self.cnc1_dot, self.cnc2_dot]:
            dot.setStyleSheet("color: #c0614a; font-size: 16px;")
            dot.setFixedWidth(20)
        for lbl in [self.bridge_lbl, self.cnc1_lbl, self.cnc2_lbl]:
            lbl.setStyleSheet("color: #c0614a; font-size: 11px; font-weight: bold;")

        status_grid.addWidget(self.bridge_dot, 0, 0)
        status_grid.addWidget(self.bridge_lbl, 0, 1)
        status_grid.addWidget(self.cnc1_dot,   1, 0)
        status_grid.addWidget(self.cnc1_lbl,   1, 1)
        status_grid.addWidget(self.cnc2_dot,   2, 0)
        status_grid.addWidget(self.cnc2_lbl,   2, 1)
        side_v.addLayout(status_grid)

        # Log + sim buttons
        self.sim_btn = QPushButton("⚗  Simulation")
        self.sim_btn.setFixedHeight(30)
        self.sim_btn.clicked.connect(lambda: self.sim_dialog.show())
        self.sim_btn.setVisible(False)
        side_v.addWidget(self.sim_btn)

        log_btn = QPushButton("📋  Session Log")
        log_btn.setFixedHeight(30)
        log_btn.clicked.connect(lambda: self.log_window.show())
        side_v.addWidget(log_btn)

        main_h.addWidget(sidebar)

        # ── PAGE STACK ────────────────────────────────────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #e8ecef;")
        main_h.addWidget(self.stack)

        self.page_session  = self._build_session_page()
        self.page_cnc      = self._build_cnc_page()
        self.page_progress = self._build_progress_page()
        self.page_config   = self._build_config_page()

        self.stack.addWidget(self.page_session)
        self.stack.addWidget(self.page_cnc)
        self.stack.addWidget(self.page_progress)
        self.stack.addWidget(self.page_config)

        self._switch_page("Session")

    def _switch_page(self, name):
        # Lock config when navigating away
        if name != "Config":
            self._config_unlocked = False

        # Config page requires password
        if name == "Config" and not self._config_unlocked:
            if not self._prompt_password():
                # Password failed -- keep current page checked
                for label, btn in self.nav_buttons:
                    btn.setChecked(
                        self.stack.currentIndex() ==
                        {"Session":0,"CNC":1,"Progress":2,"Config":3}.get(label, -1)
                    )
                return

        pages = {"Session": 0, "CNC": 1, "Progress": 2, "Config": 3}
        idx   = pages.get(name, 0)
        self.stack.setCurrentIndex(idx)
        for label, btn in self.nav_buttons:
            btn.setChecked(label == name)

    def _prompt_password(self):
        """
        Show password dialog. Returns True if correct password entered.
        Password is SHA-256 hashed and compared against stored value.
        """
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        pwd, ok = QInputDialog.getText(
            self,
            "Config Access",
            "Enter password to access configuration:",
            QLineEdit.Password
        )
        if not ok or not pwd:
            return False

        entered_hash = hashlib.sha256(pwd.encode()).hexdigest()
        stored_hash  = config.get(
            'config_password_hash',
            '55a76fa549255ec2626ff874cf20c47f9e47d5d55dfba2679829b8878bfeabe7'  # SenmaticLab1
        )
        if entered_hash == stored_hash:
            self._config_unlocked = True
            self.log("  [CONFIG] Access granted.")
            return True
        else:
            QMessageBox.warning(self, "Access Denied", "Incorrect password.")
            self.log("  [CONFIG] Access denied -- incorrect password.")
            return False

    # ----------------------------------------------------------
    # SESSION PAGE
    # ----------------------------------------------------------
    def _build_session_page(self):
        page = QWidget()
        v    = QVBoxLayout(page)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        # ── Certificate / sensor info bar ─────────────────────
        cert_group = QGroupBox("Active Sensors")
        cert_h     = QHBoxLayout(cert_group)
        certs_text = ", ".join(self.certificates) if self.certificates else "none loaded"
        cert_lbl   = QLabel(f"Certificates:  {certs_text}")
        cert_lbl.setObjectName("certLabel")
        cert_h.addWidget(cert_lbl)
        cert_h.addStretch()
        progress_btn = QPushButton("📋  Calibration Progress")
        progress_btn.setObjectName("batchesBtn")
        progress_btn.clicked.connect(self.open_progress)
        cert_h.addWidget(progress_btn)
        v.addWidget(cert_group)

        # ── Middle row: Bath config + Timers ──────────────────
        mid_h = QHBoxLayout()

        # Bath configuration
        bath_group = QGroupBox("Bath Configuration")
        bath_v     = QVBoxLayout(bath_group)
        self.bath_rows = {}

        # Default ref sensor per bath -- Bath 1-2 uses 5003 same as Bath 1-1
        default_ref = {1: '5003', 2: '5004', 3: '5088', 4: '4999', 5: '5003'}
        ref_values  = list(REF_SENSOR_ID.values())   # ['5003','5004','5088','4999']

        for bath_no in range(1, 6):
            row_h = QHBoxLayout()
            row_h.setSpacing(6)

            lbl = QLabel(BATH_LABEL[bath_no])
            lbl.setFixedWidth(175)
            row_h.addWidget(lbl)

            row_h.addWidget(QLabel("Ref:"))
            ref_combo = QComboBox()
            for k, v2 in REF_SENSOR_ID.items():
                ref_combo.addItem(v2, k)
            # Set correct default ref sensor
            ref_name = default_ref[bath_no]
            idx = ref_values.index(ref_name) if ref_name in ref_values else 0
            ref_combo.setCurrentIndex(idx)
            ref_combo.setFixedWidth(70)
            row_h.addWidget(ref_combo)
            row_h.addSpacing(8)

            row_h.addWidget(QLabel("Batches:"))
            batch_combos = []
            max_batches = 4 if bath_no in (1, 5) else 2
            for _ in range(max_batches):
                bc = QComboBox()
                bc.addItem("--", None)
                for bn in self.available_batches:
                    bc.addItem(str(bn), bn)
                # Narrow width -- batch numbers are max 2 digits
                bc.setFixedWidth(48)
                bc.setMinimumContentsLength(2)
                row_h.addWidget(bc)
                batch_combos.append(bc)

            # Pad Bath 2/3/4 rows with a spacer to align with Bath 1 rows
            if max_batches == 2:
                row_h.addSpacing(48 * 2 + 12)   # 2 missing combos + spacing

            row_h.addStretch()
            bath_v.addLayout(row_h)
            self.bath_rows[bath_no] = {'ref': ref_combo, 'combos': batch_combos}

        mid_h.addWidget(bath_group, stretch=3)

        # Bath timers (compact)
        timer_group = QGroupBox("Bath Timers")
        timer_grid  = QGridLayout(timer_group)
        timer_grid.setColumnStretch(2, 1)
        timer_grid.setSpacing(6)

        self.timer_pickers = {}
        self.timer_bars    = {}
        self.timer_labels  = {}
        self.timer_status  = {}

        for row, bath_no in enumerate(range(1, 6)):
            lbl    = QLabel(BATH_LABEL[bath_no])
            lbl.setFixedWidth(130)
            secs   = BATH_WAIT_DEFAULT[bath_no]
            picker = QTimeEdit()
            picker.setTime(QTime(secs // 3600, (secs % 3600) // 60, secs % 60))
            picker.setDisplayFormat("HH:mm:ss")
            picker.setFixedWidth(80)
            bar    = QProgressBar()
            bar.setMaximum(100)
            bar.setValue(100)
            bar.setFormat("%p%")
            bar.setFixedHeight(14)
            time_lbl = QLabel("--:--:--")
            time_lbl.setFixedWidth(65)
            time_lbl.setAlignment(Qt.AlignCenter)
            status_lbl = QLabel("IDLE")
            status_lbl.setFixedWidth(70)
            status_lbl.setStyleSheet("color: #aab0b8; font-size: 11px;")

            timer_grid.addWidget(lbl,        row, 0)
            timer_grid.addWidget(picker,     row, 1)
            timer_grid.addWidget(bar,        row, 2)
            timer_grid.addWidget(time_lbl,   row, 3)
            timer_grid.addWidget(status_lbl, row, 4)

            self.timer_pickers[bath_no] = picker
            self.timer_bars[bath_no]    = bar
            self.timer_labels[bath_no]  = time_lbl
            self.timer_status[bath_no]  = status_lbl

        mid_h.addWidget(timer_group, stretch=2)
        v.addLayout(mid_h)

        # ── Sensor list ────────────────────────────────────────
        sensor_group = QGroupBox("Sensors in Session")
        sensor_v     = QVBoxLayout(sensor_group)
        self.sensor_list_table = QTableWidget(0, 4)
        self.sensor_list_table.setHorizontalHeaderLabels(
            ['Certificate', 'Serial', 'Batch', 'Status']
        )
        self.sensor_list_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.sensor_list_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sensor_list_table.verticalHeader().setVisible(False)
        self.sensor_list_table.setFixedHeight(120)

        skip_btn = QPushButton("⊘  Skip Selected Sensor")
        skip_btn.setFixedWidth(180)
        skip_btn.clicked.connect(self._skip_selected_sensor)
        unskip_btn = QPushButton("↺  Unskip Selected")
        unskip_btn.setFixedWidth(160)
        unskip_btn.clicked.connect(self._unskip_selected_sensor)

        btn_h = QHBoxLayout()
        btn_h.addStretch()
        btn_h.addWidget(skip_btn)
        btn_h.addWidget(unskip_btn)

        sensor_v.addWidget(self.sensor_list_table)
        sensor_v.addLayout(btn_h)
        v.addWidget(sensor_group)

        # ── Start / Stop ───────────────────────────────────────
        ctrl_h = QHBoxLayout()
        self.start_btn = QPushButton("▶   START SESSION")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setFixedHeight(38)
        self.start_btn.clicked.connect(self.start_session)

        self.stop_btn = QPushButton("■   STOP")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.clicked.connect(self.stop_session)
        self.stop_btn.setEnabled(False)

        ctrl_h.addStretch()
        ctrl_h.addWidget(self.start_btn)
        ctrl_h.addWidget(self.stop_btn)
        ctrl_h.addStretch()
        v.addLayout(ctrl_h)

        return page

    # ----------------------------------------------------------
    # CNC PAGE
    # ----------------------------------------------------------
    def _build_cnc_page(self):
        page  = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("CNC Connector Control")
        title.setStyleSheet(
            "font-family: Georgia; font-size: 16px; font-weight: bold;"
            "color: #4a7fa5; padding-bottom: 8px;"
        )
        outer.addWidget(title)

        # Scroll area
        scroll   = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        scroll_w = QWidget()
        v        = QVBoxLayout(scroll_w)
        v.setSpacing(14)
        scroll.setWidget(scroll_w)
        outer.addWidget(scroll)

        cnc_h = QHBoxLayout()
        cnc_h.setSpacing(14)

        # ── CONNECTOR 1 -- Reference SPRT ─────────────────────
        grp1 = QGroupBox("Connector 1  —  Reference SPRT")
        gv1  = QVBoxLayout(grp1)
        gv1.setSpacing(8)

        # Connection row
        port_h1 = QHBoxLayout()
        port_h1.addWidget(QLabel("Port:"))
        self.cnc1_port_entry = QLineEdit(config.get('cnc1_port', 'COM3'))
        self.cnc1_port_entry.setFixedWidth(75)
        conn1_btn    = QPushButton("Connect")
        conn1_btn.setFixedWidth(85)
        disconn1_btn = QPushButton("Disconnect")
        disconn1_btn.setFixedWidth(95)
        conn1_btn.clicked.connect(self._connect_cnc1)
        disconn1_btn.clicked.connect(self._disconnect_cnc1)
        port_h1.addWidget(self.cnc1_port_entry)
        port_h1.addWidget(conn1_btn)
        port_h1.addWidget(disconn1_btn)
        port_h1.addStretch()
        gv1.addLayout(port_h1)

        self.cnc1_status_lbl = QLabel("● NOT CONNECTED")
        self.cnc1_status_lbl.setStyleSheet("color: #c0614a; font-weight: bold; font-size: 11px;")
        gv1.addWidget(self.cnc1_status_lbl)

        # Divider
        d1 = QFrame(); d1.setFrameShape(QFrame.HLine)
        d1.setStyleSheet("color: #c2c8d0;")
        gv1.addWidget(d1)

        # Manual jog
        jog_lbl1 = QLabel("MANUAL JOG")
        jog_lbl1.setStyleSheet("color: #7a8290; font-size: 9px; letter-spacing: 2px;")
        gv1.addWidget(jog_lbl1)
        step_h1 = QHBoxLayout()
        step_h1.addWidget(QLabel("Step:"))
        self._cnc1_step = QComboBox()
        self._cnc1_step.addItems(["0.1 mm", "0.5 mm", "1 mm", "5 mm", "10 mm", "50 mm", "100 mm"])
        self._cnc1_step.setCurrentText("1 mm")
        self._cnc1_step.setFixedWidth(90)
        step_h1.addWidget(self._cnc1_step)
        step_h1.addStretch()
        gv1.addLayout(step_h1)
        jog_h1 = QHBoxLayout()
        jog_h1.setSpacing(5)
        for lbl, cmd in [("X−","X-"),("X+","X+"),("Z−","Z-"),("Z+","Z+"),("⌂ Home","H")]:
            b = QPushButton(lbl)
            b.setFixedHeight(32)
            b.setFixedWidth(95 if lbl == "⌂ Home" else 52)
            b.clicked.connect(lambda checked, c=cmd: self._cnc_jog(1, c, float(self._cnc1_step.currentText().split()[0])))
            jog_h1.addWidget(b)
        jog_h1.addStretch()
        gv1.addLayout(jog_h1)

        # Pogo pins
        pogo_h1 = QHBoxLayout()
        cp1 = QPushButton("▼  Connect Pins")
        cp1.setFixedHeight(32)
        cp1.setStyleSheet("QPushButton{border:1.5px solid #5a9e6f;color:#5a9e6f;border-radius:8px;}"
                          "QPushButton:hover{background-color:#5a9e6f;color:white;}")
        rp1 = QPushButton("▲  Retract Pins")
        rp1.setFixedHeight(32)
        rp1.setStyleSheet("QPushButton{border:1.5px solid #c0614a;color:#c0614a;border-radius:8px;}"
                          "QPushButton:hover{background-color:#c0614a;color:white;}")
        cp1.clicked.connect(lambda: self._cnc_pogo_connect(1))
        rp1.clicked.connect(lambda: self._cnc_pogo_disconnect(1))
        pogo_h1.addWidget(cp1)
        pogo_h1.addWidget(rp1)
        pogo_h1.addStretch()
        gv1.addLayout(pogo_h1)

        # Divider
        d2 = QFrame(); d2.setFrameShape(QFrame.HLine)
        d2.setStyleSheet("color: #c2c8d0;")
        gv1.addWidget(d2)

        # Reference position buttons -- move to stored X position
        pos_lbl1 = QLabel("MOVE TO POSITION")
        pos_lbl1.setStyleSheet("color: #7a8290; font-size: 9px; letter-spacing: 2px;")
        gv1.addWidget(pos_lbl1)

        ref_positions = [
            ('5003', 'Bath 1  (Ref 5003)', '5003'),
            ('5004', 'Bath 2  (Ref 5004)', '5004'),
            ('5088', 'Bath 3  (Ref 5088)', '5088'),
            ('4999', 'Bath 4  (Ref 4999)', '4999'),
        ]
        for sensor_id, label, sid in ref_positions:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.clicked.connect(
                lambda checked, s=sid: self._cnc1_move_to(s)
            )
            gv1.addWidget(btn)

        gv1.addStretch()
        cnc_h.addWidget(grp1)

        # ── CONNECTOR 2 -- Batch sensors ──────────────────────
        grp2 = QGroupBox("Connector 2  —  PT100 Batch Sensors")
        gv2  = QVBoxLayout(grp2)
        gv2.setSpacing(8)

        # Connection row
        port_h2 = QHBoxLayout()
        port_h2.addWidget(QLabel("Port:"))
        self.cnc2_port_entry = QLineEdit(config.get('cnc2_port', 'COM4'))
        self.cnc2_port_entry.setFixedWidth(75)
        conn2_btn    = QPushButton("Connect")
        conn2_btn.setFixedWidth(85)
        disconn2_btn = QPushButton("Disconnect")
        disconn2_btn.setFixedWidth(95)
        conn2_btn.clicked.connect(self._connect_cnc2)
        disconn2_btn.clicked.connect(self._disconnect_cnc2)
        port_h2.addWidget(self.cnc2_port_entry)
        port_h2.addWidget(conn2_btn)
        port_h2.addWidget(disconn2_btn)
        port_h2.addStretch()
        gv2.addLayout(port_h2)

        self.cnc2_status_lbl = QLabel("● NOT CONNECTED")
        self.cnc2_status_lbl.setStyleSheet("color: #c0614a; font-weight: bold; font-size: 11px;")
        gv2.addWidget(self.cnc2_status_lbl)

        # Divider
        d3 = QFrame(); d3.setFrameShape(QFrame.HLine)
        d3.setStyleSheet("color: #c2c8d0;")
        gv2.addWidget(d3)

        # Manual jog
        jog_lbl2 = QLabel("MANUAL JOG")
        jog_lbl2.setStyleSheet("color: #7a8290; font-size: 9px; letter-spacing: 2px;")
        gv2.addWidget(jog_lbl2)
        step_h2 = QHBoxLayout()
        step_h2.addWidget(QLabel("Step:"))
        self._cnc2_step = QComboBox()
        self._cnc2_step.addItems(["0.1 mm", "0.5 mm", "1 mm", "5 mm", "10 mm", "50 mm", "100 mm"])
        self._cnc2_step.setCurrentText("1 mm")
        self._cnc2_step.setFixedWidth(90)
        step_h2.addWidget(self._cnc2_step)
        step_h2.addStretch()
        gv2.addLayout(step_h2)
        jog_h2 = QHBoxLayout()
        jog_h2.setSpacing(5)
        for lbl, cmd in [("X−","X-"),("X+","X+"),("Z−","Z-"),("Z+","Z+"),("⌂ Home","H")]:
            b = QPushButton(lbl)
            b.setFixedHeight(32)
            b.setFixedWidth(95 if lbl == "⌂ Home" else 52)
            b.clicked.connect(lambda checked, c=cmd: self._cnc_jog(2, c, float(self._cnc2_step.currentText().split()[0])))
            jog_h2.addWidget(b)
        jog_h2.addStretch()
        gv2.addLayout(jog_h2)

        # Pogo pins
        pogo_h2 = QHBoxLayout()
        cp2 = QPushButton("▼  Connect Pins")
        cp2.setFixedHeight(32)
        cp2.setStyleSheet("QPushButton{border:1.5px solid #5a9e6f;color:#5a9e6f;border-radius:8px;}"
                          "QPushButton:hover{background-color:#5a9e6f;color:white;}")
        rp2 = QPushButton("▲  Retract Pins")
        rp2.setFixedHeight(32)
        rp2.setStyleSheet("QPushButton{border:1.5px solid #c0614a;color:#c0614a;border-radius:8px;}"
                          "QPushButton:hover{background-color:#c0614a;color:white;}")
        cp2.clicked.connect(lambda: self._cnc_pogo_connect(2))
        rp2.clicked.connect(lambda: self._cnc_pogo_disconnect(2))
        pogo_h2.addWidget(cp2)
        pogo_h2.addWidget(rp2)
        pogo_h2.addStretch()
        gv2.addLayout(pogo_h2)

        # Divider
        d4 = QFrame(); d4.setFrameShape(QFrame.HLine)
        d4.setStyleSheet("color: #c2c8d0;")
        gv2.addWidget(d4)

        # Batch position buttons -- 10 positions in a grid
        pos_lbl2 = QLabel("MOVE TO POSITION")
        pos_lbl2.setStyleSheet("color: #7a8290; font-size: 9px; letter-spacing: 2px;")
        gv2.addWidget(pos_lbl2)

        batch_positions = [
            (1, 1, 'Bath 1-1  Slot 1'),
            (1, 2, 'Bath 1-1  Slot 2'),
            (1, 3, 'Bath 1-1  Slot 3'),
            (1, 4, 'Bath 1-1  Slot 4'),
            (5, 1, 'Bath 1-2  Slot 1'),
            (5, 2, 'Bath 1-2  Slot 2'),
            (5, 3, 'Bath 1-2  Slot 3'),
            (5, 4, 'Bath 1-2  Slot 4'),
            (2, 1, 'Bath 2    Slot 1'),
            (2, 2, 'Bath 2    Slot 2'),
            (3, 1, 'Bath 3    Slot 1'),
            (3, 2, 'Bath 3    Slot 2'),
            (4, 1, 'Bath 4    Slot 1'),
            (4, 2, 'Bath 4    Slot 2'),
        ]
        # 2-column grid layout for buttons
        btn_grid = QGridLayout()
        btn_grid.setSpacing(5)
        for i, (bath_no, slot, label) in enumerate(batch_positions):
            btn = QPushButton(label)
            btn.setFixedHeight(30)
            btn.clicked.connect(
                lambda checked, b=bath_no, s=slot: self._cnc2_move_to(b, s)
            )
            btn_grid.addWidget(btn, i // 2, i % 2)
        gv2.addLayout(btn_grid)
        gv2.addStretch()
        cnc_h.addWidget(grp2)

        v.addLayout(cnc_h)

        # Bridge reconnect
        bridge_h = QHBoxLayout()
        reconnect_bridge_btn = QPushButton("↺  Reconnect Bridge")
        reconnect_bridge_btn.clicked.connect(self._reconnect_bridge)
        bridge_h.addStretch()
        bridge_h.addWidget(reconnect_bridge_btn)
        v.addLayout(bridge_h)

        return page
    # ----------------------------------------------------------
    # PROGRESS PAGE
    # ----------------------------------------------------------
    def _build_progress_page(self):
        page = QWidget()
        v    = QVBoxLayout(page)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        title = QLabel("Live Progress")
        title.setStyleSheet(
            "font-family: Georgia; font-size: 16px; font-weight: bold;"
            "color: #4a7fa5; padding-bottom: 8px;"
        )
        v.addWidget(title)

        # Top row: Batch queue + readings
        mid_h = QHBoxLayout()

        # Batch queue (compact)
        batch_group = QGroupBox("Batch Queue")
        batch_v     = QVBoxLayout(batch_group)
        self.queue_lbl = QLabel("  No session active")
        self.queue_lbl.setObjectName("queueLabel")
        batch_v.addWidget(self.queue_lbl)
        self.batch_status_table = QTableWidget(0, 3)
        self.batch_status_table.setHorizontalHeaderLabels(['Batch', 'Bath', 'Status'])
        self.batch_status_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.batch_status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.batch_status_table.verticalHeader().setVisible(False)
        batch_v.addWidget(self.batch_status_table)
        mid_h.addWidget(batch_group, stretch=1)
        v.addLayout(mid_h)

        # Live readings (full width, double height)
        readings_group = QGroupBox("Live Readings")
        readings_v     = QVBoxLayout(readings_group)
        self.readings_table = QTableWidget(0, 5)
        self.readings_table.setHorizontalHeaderLabels(
            ['Serial / Ref', 'Ratio', 'Stage 1', 'Stage 2', 'Status']
        )
        self.readings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.readings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.readings_table.verticalHeader().setVisible(False)
        self.readings_table.setMinimumHeight(360)
        readings_v.addWidget(self.readings_table)
        v.addWidget(readings_group)

        return page

    # ----------------------------------------------------------
    # CONFIG PAGE
    # ----------------------------------------------------------
    def _build_config_page(self):
        page   = QWidget()
        v      = QVBoxLayout(page)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        title = QLabel("Configuration")
        title.setStyleSheet(
            "font-family: Georgia; font-size: 16px; font-weight: bold;"
            "color: #4a7fa5; padding-bottom: 8px;"
        )
        v.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_config_comm_tab(),       "Communication")
        tabs.addTab(self._build_config_sprt_tab(),       "SPRT Sensors")
        tabs.addTab(self._build_config_resistors_tab(),  "Standard Resistors")
        tabs.addTab(self._build_config_bath_tab(),       "Bath Settings")
        tabs.addTab(self._build_config_stability_tab(),  "Stability & Warnings")
        tabs.addTab(self._build_config_cnc_tab(),        "CNC Settings")
        v.addWidget(tabs)

        # ── Bottom row: password + save ───────────────────────
        bottom_h = QHBoxLayout()
        change_pwd_btn = QPushButton("🔑  Change Password")
        change_pwd_btn.setFixedHeight(36)
        change_pwd_btn.setFixedWidth(180)
        change_pwd_btn.clicked.connect(self._show_change_password_dialog)
        bottom_h.addWidget(change_pwd_btn)
        bottom_h.addStretch()
        v.addLayout(bottom_h)

        # Save button
        save_btn = QPushButton("💾  Save All Configuration to DB")
        save_btn.setFixedHeight(38)
        save_btn.setObjectName("startBtn")
        save_btn.clicked.connect(self._save_all_config)
        v.addWidget(save_btn)

        return page

    def _build_config_comm_tab(self):
        """Communication settings tab -- GPIB or RS-232 for Micro-K 70."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(14)
        self._comm_entries = {}

        # ── Communication type selector ───────────────────────
        type_grp  = QGroupBox("Bridge Communication Type")
        type_form = QFormLayout(type_grp)

        self._comm_type_combo = QComboBox()
        self._comm_type_combo.addItems(['GPIB', 'RS232'])
        current_comm = config.get('bridge_comm', 'GPIB').upper()
        self._comm_type_combo.setCurrentText(current_comm)
        self._comm_type_combo.currentTextChanged.connect(self._on_comm_type_changed)
        type_form.addRow("Communication:", self._comm_type_combo)
        v.addWidget(type_grp)

        # ── GPIB settings ─────────────────────────────────────
        self._gpib_grp  = QGroupBox("GPIB Settings")
        gpib_form = QFormLayout(self._gpib_grp)
        for key, label in [
            ('bridge_gpib_addr', 'GPIB Address'),
            ('bridge_timeout',   'Timeout (seconds)'),
        ]:
            entry = QLineEdit(config.get(key, ''))
            gpib_form.addRow(label, entry)
            self._comm_entries[key] = entry
        v.addWidget(self._gpib_grp)

        # ── RS-232 settings ───────────────────────────────────
        self._rs232_grp  = QGroupBox("RS-232 Settings")
        rs232_form = QFormLayout(self._rs232_grp)
        for key, label in [
            ('bridge_rs232_port',     'Serial Port  (e.g. /dev/ttyS0 or COM1)'),
            ('bridge_rs232_baud',     'Baud Rate'),
            ('bridge_rs232_bytesize', 'Data Bits'),
            ('bridge_rs232_parity',   'Parity  (N / E / O)'),
            ('bridge_rs232_stopbits', 'Stop Bits'),
            ('bridge_timeout',        'Timeout (seconds)'),
        ]:
            entry = QLineEdit(config.get(key, ''))
            rs232_form.addRow(label, entry)
            self._comm_entries[key] = entry
        v.addWidget(self._rs232_grp)

        # ── Shared timing ─────────────────────────────────────
        timing_grp  = QGroupBox("Timing")
        timing_form = QFormLayout(timing_grp)
        for key, label in [
            ('bridge_settle_time',    'Settle time after connect (seconds)'),
            ('bridge_channel_settle', 'Channel relay settle time (seconds)'),
        ]:
            entry = QLineEdit(config.get(key, ''))
            timing_form.addRow(label, entry)
            self._comm_entries[key] = entry
        v.addWidget(timing_grp)

        # ── Test connection button ────────────────────────────
        test_h = QHBoxLayout()
        test_btn = QPushButton("🔌  Test Connection")
        test_btn.setFixedHeight(34)
        test_btn.clicked.connect(self._test_bridge_connection)
        self._bridge_test_lbl = QLabel("")
        self._bridge_test_lbl.setStyleSheet("font-weight: bold;")
        test_h.addWidget(test_btn)
        test_h.addWidget(self._bridge_test_lbl)
        test_h.addStretch()
        v.addLayout(test_h)

        v.addStretch()

        # Set initial visibility
        self._on_comm_type_changed(current_comm)

        return w

    def _on_comm_type_changed(self, comm_type):
        """Show/hide GPIB or RS-232 settings based on selection."""
        is_gpib = comm_type.upper() == 'GPIB'
        if hasattr(self, '_gpib_grp'):
            self._gpib_grp.setVisible(is_gpib)
        if hasattr(self, '_rs232_grp'):
            self._rs232_grp.setVisible(not is_gpib)

    def _test_bridge_connection(self):
        """Test bridge connection with current settings and show result."""
        # Save current comm settings first
        if self.conn:
            config.save_config(self.conn, 'bridge_comm',
                               self._comm_type_combo.currentText())
            for key, entry in self._comm_entries.items():
                val = entry.text().strip()
                if val:
                    config.save_config(self.conn, key, val)

        self._bridge_test_lbl.setText("Testing...")
        self._bridge_test_lbl.setStyleSheet("color: #a07840; font-weight: bold;")

        from instruments.bridge import bridge_connect, bridge_close, bridge_get_comm_info
        test_bridge = bridge_connect()
        if test_bridge:
            info = bridge_get_comm_info(test_bridge)
            self._bridge_test_lbl.setText(f"✓ Connected  ({info})")
            self._bridge_test_lbl.setStyleSheet("color: #5a9e6f; font-weight: bold;")
            bridge_close(test_bridge)
            self.log(f"  [BRIDGE] Test connection OK -- {info}")
        else:
            comm = self._comm_type_combo.currentText()
            self._bridge_test_lbl.setText(f"✗ Failed  ({comm})")
            self._bridge_test_lbl.setStyleSheet("color: #c0614a; font-weight: bold;")
            self.log(f"  ⚠ [BRIDGE] Test connection failed")

    def _build_config_sprt_tab(self):
        w  = QWidget()
        v  = QVBoxLayout(w)
        self._sprt_entries = {}

        for sensor_id in ['5003', '5004', '5088', '4999']:
            grp  = QGroupBox(f"Sensor {sensor_id}")
            form = QFormLayout(grp)
            fields = [
                (f'sprt_{sensor_id}_roits',   'Roits (Ω)'),
                (f'sprt_{sensor_id}_a_sub',   'a  (below 0°C)'),
                (f'sprt_{sensor_id}_b_sub',   'b  (below 0°C)'),
                (f'sprt_{sensor_id}_a_above', 'a  (above 0°C)'),
            ]
            for key, label in fields:
                entry = QLineEdit(config.get(key, ''))
                entry.setFont(QFont("Courier New", 10))
                form.addRow(label, entry)
                self._sprt_entries[key] = entry
            v.addWidget(grp)

        v.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(w)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        return scroll

    def _build_config_resistors_tab(self):
        w    = QWidget()
        form = QFormLayout(w)
        self._resistor_entries = {}

        for key, label in [
            ('resistor_25',  'Calibrated 25 Ω standard'),
            ('resistor_100', 'Calibrated 100 Ω standard'),
        ]:
            entry = QLineEdit(config.get(key, ''))
            entry.setFont(QFont("Courier New", 11))
            form.addRow(label, entry)
            self._resistor_entries[key] = entry

        return w

    def _build_config_bath_tab(self):
        w    = QWidget()
        form = QFormLayout(w)
        self._bath_entries = {}

        for bath_no in range(1, 6):
            for suffix, label in [
                (f'bath_wait_{bath_no}',    f'{BATH_LABEL[bath_no]}  wait (s)'),
                (f'bath_temp_min_{bath_no}', f'{BATH_LABEL[bath_no]}  min °C'),
                (f'bath_temp_max_{bath_no}', f'{BATH_LABEL[bath_no]}  max °C'),
            ]:
                entry = QLineEdit(config.get(suffix, ''))
                form.addRow(label, entry)
                self._bath_entries[suffix] = entry

        scroll = QScrollArea()
        scroll.setWidget(w)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        return scroll

    def _build_config_stability_tab(self):
        w    = QWidget()
        form = QFormLayout(w)
        self._stability_entries = {}

        fields = [
            ('stage1_threshold',          'Stage 1 threshold'),
            ('stage2_threshold',          'Stage 2 threshold'),
            ('bath1_resistance_warn_mk',  'Bath 1-2 resistance drift limit (mK)'),
            ('bath1_temperature_warn_mk', 'Bath 1-2 temperature drift limit (mK)'),
        ]
        for key, label in fields:
            entry = QLineEdit(config.get(key, ''))
            form.addRow(label, entry)
            self._stability_entries[key] = entry

        return w

    def _build_config_cnc_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        self._cnc_config_entries = {}

        # ── Connection settings ───────────────────────────────
        conn_grp  = QGroupBox("Connection Settings")
        conn_form = QFormLayout(conn_grp)
        for key, label in [
            ('cnc1_port',      'CNC 1 COM port  (Connector 1 -- Ref SPRT)'),
            ('cnc2_port',      'CNC 2 COM port  (Connector 2 -- Batch sensors)'),
            ('cnc_baud',       'Baud rate'),
            ('cnc1_feed_rate', 'CNC 1 feed rate  (mm/min)'),
            ('cnc2_feed_rate', 'CNC 2 feed rate  (mm/min)'),
        ]:
            entry = QLineEdit(config.get(key, ''))
            conn_form.addRow(label, entry)
            self._cnc_config_entries[key] = entry
        v.addWidget(conn_grp)

        # ── Connector 1 -- Reference SPRT (4 X positions + Z) ─
        cnc1_grp  = QGroupBox("Connector 1  —  Reference SPRT  (4 X positions + Z connect)")
        cnc1_form = QFormLayout(cnc1_grp)
        for key, label in [
            ('cnc1_x_ref_5003', 'X  →  Ref 5003  (Bath 1-1 / 1-2)  mm'),
            ('cnc1_x_ref_5004', 'X  →  Ref 5004  (Bath 2)           mm'),
            ('cnc1_x_ref_5088', 'X  →  Ref 5088  (Bath 3)           mm'),
            ('cnc1_x_ref_4999', 'X  →  Ref 4999  (Bath 4)           mm'),
            ('cnc1_z_connect',  'Z  →  Connect depth                mm'),
        ]:
            entry = QLineEdit(config.get(key, ''))
            entry.setFont(QFont("Courier New", 10))
            cnc1_form.addRow(label, entry)
            self._cnc_config_entries[key] = entry
        v.addWidget(cnc1_grp)

        # ── Connector 2 -- Batch sensors (10 X positions + Z) ─
        cnc2_grp  = QGroupBox("Connector 2  —  Batch Sensors  (10 X positions + Z connect)")
        cnc2_form = QFormLayout(cnc2_grp)
        for key, label in [
            ('cnc2_x_bath1_1_slot_1', 'X  →  Bath 1-1  Slot 1  mm'),
            ('cnc2_x_bath1_1_slot_2', 'X  →  Bath 1-1  Slot 2  mm'),
            ('cnc2_x_bath1_1_slot_3', 'X  →  Bath 1-1  Slot 3  mm'),
            ('cnc2_x_bath1_1_slot_4', 'X  →  Bath 1-1  Slot 4  mm'),
            ('cnc2_x_bath1_2_slot_1', 'X  →  Bath 1-2  Slot 1  mm'),
            ('cnc2_x_bath1_2_slot_2', 'X  →  Bath 1-2  Slot 2  mm'),
            ('cnc2_x_bath1_2_slot_3', 'X  →  Bath 1-2  Slot 3  mm'),
            ('cnc2_x_bath1_2_slot_4', 'X  →  Bath 1-2  Slot 4  mm'),
            ('cnc2_x_bath2_slot_1',   'X  →  Bath 2    Slot 1  mm'),
            ('cnc2_x_bath2_slot_2',   'X  →  Bath 2    Slot 2  mm'),
            ('cnc2_x_bath3_slot_1',   'X  →  Bath 3    Slot 1  mm'),
            ('cnc2_x_bath3_slot_2',   'X  →  Bath 3    Slot 2  mm'),
            ('cnc2_x_bath4_slot_1',   'X  →  Bath 4    Slot 1  mm'),
            ('cnc2_x_bath4_slot_2',   'X  →  Bath 4    Slot 2  mm'),
            ('cnc2_z_connect',        'Z  →  Connect depth     mm'),
        ]:
            entry = QLineEdit(config.get(key, ''))
            entry.setFont(QFont("Courier New", 10))
            cnc2_form.addRow(label, entry)
            self._cnc_config_entries[key] = entry
        v.addWidget(cnc2_grp)

        v.addStretch()
        scroll = QScrollArea()
        scroll.setWidget(w)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        return scroll

    def _show_change_password_dialog(self):
        """Open the Change Password dialog window."""
        dlg = ChangePasswordDialog(self.conn, self)
        dlg.exec()
        if dlg.changed:
            self.log("  [CONFIG] Password changed successfully.")

    def _save_all_config(self):
        if not self.conn:
            QMessageBox.warning(self, "No DB", "No database connection.")
            return

        all_entries = {}
        all_entries.update(self._comm_entries)
        all_entries.update(self._sprt_entries)
        all_entries.update(self._resistor_entries)
        all_entries.update(self._bath_entries)
        all_entries.update(self._stability_entries)
        all_entries.update(self._cnc_config_entries)

        # Save comm type from dropdown
        if self.conn:
            config.save_config(self.conn, 'bridge_comm',
                               self._comm_type_combo.currentText())

        saved = 0
        for key, entry in all_entries.items():
            val = entry.text().strip()
            if val:
                config.save_config(self.conn, key, val)
                saved += 1

        QMessageBox.information(
            self, "Saved",
            f"{saved} configuration values saved to DB.\n"
            f"Changes take effect immediately."
        )
        self.log(f"  [CONFIG] {saved} values saved to DB.")

    # ----------------------------------------------------------
    # CNC ACTIONS
    # ----------------------------------------------------------
    def _connect_cnc1(self):
        port = self.cnc1_port_entry.text().strip()
        try:
            m = self._cnc
            if m is None: return
            self.cnc1 = m.cnc_connect(port)
            self.cnc1_status_lbl.setText("● CONNECTED")
            self.cnc1_status_lbl.setStyleSheet("color: #5a9e6f; font-weight: bold;")
            self._set_status(self.cnc1_dot, self.cnc1_lbl, "CNC 1", True)
            self.log(f"  [CNC1] Connected on {port}")
        except Exception as e:
            QMessageBox.warning(self, "CNC 1 Error", str(e))
            self.log(f"  ⚠ [CNC1] Connection failed: {e}")

    def _disconnect_cnc1(self):
        try:
            m = self._cnc
            if m: m.cnc_close(self.cnc1)
        except Exception:
            pass
        self.cnc1 = None
        self.cnc1_status_lbl.setText("● NOT CONNECTED")
        self.cnc1_status_lbl.setStyleSheet("color: #c0614a; font-weight: bold;")
        self._set_status(self.cnc1_dot, self.cnc1_lbl, "CNC 1", False)
        self.log("  [CNC1] Disconnected")

    def _connect_cnc2(self):
        port = self.cnc2_port_entry.text().strip()
        try:
            m = self._cnc
            if m is None: return
            self.cnc2 = m.cnc_connect(port)
            self.cnc2_status_lbl.setText("● CONNECTED")
            self.cnc2_status_lbl.setStyleSheet("color: #5a9e6f; font-weight: bold;")
            self._set_status(self.cnc2_dot, self.cnc2_lbl, "CNC 2", True)
            self.log(f"  [CNC2] Connected on {port}")
        except Exception as e:
            QMessageBox.warning(self, "CNC 2 Error", str(e))
            self.log(f"  ⚠ [CNC2] Connection failed: {e}")

    def _disconnect_cnc2(self):
        try:
            m = self._cnc
            if m: m.cnc_close(self.cnc2)
        except Exception:
            pass
        self.cnc2 = None
        self.cnc2_status_lbl.setText("● NOT CONNECTED")
        self.cnc2_status_lbl.setStyleSheet("color: #c0614a; font-weight: bold;")
        self._set_status(self.cnc2_dot, self.cnc2_lbl, "CNC 2", False)
        self.log("  [CNC2] Disconnected")

    def _cnc_jog(self, cnc_no, direction, step=1.0):
        cnc = self.cnc1 if cnc_no == 1 else self.cnc2
        if cnc is None:
            self.log(f"  ⚠ [CNC{cnc_no}] Not connected")
            return
        try:
            m = self._cnc
            if m is None: return
            feed = config.CNC1_FEED_RATE if cnc_no == 1 else config.CNC2_FEED_RATE
            m.cnc_jog(cnc, direction, feed, step=float(step))
            self.log(f"  [CNC{cnc_no}] Jog {direction}  {step} mm")
        except Exception as e:
            self.log(f"  ⚠ [CNC{cnc_no}] Jog error: {e}")

    def _cnc_pogo_connect(self, cnc_no):
        cnc = self.cnc1 if cnc_no == 1 else self.cnc2
        if cnc is None:
            self.log(f"  ⚠ [CNC{cnc_no}] Not connected")
            return
        try:
            m = self._cnc
            if m is None: return
            z   = config.CNC1_Z_CONNECT if cnc_no == 1 else config.CNC2_Z_CONNECT
            feed = config.CNC1_FEED_RATE if cnc_no == 1 else config.CNC2_FEED_RATE
            m.cnc_z_move(cnc, z, feed)
            self.log(f"  [CNC{cnc_no}] Pogo pins connected (Z={config.CNC_Z_CONNECT}mm)")
        except Exception as e:
            self.log(f"  ⚠ [CNC{cnc_no}] Connect error: {e}")

    def _cnc_pogo_disconnect(self, cnc_no):
        cnc = self.cnc1 if cnc_no == 1 else self.cnc2
        if cnc is None:
            self.log(f"  ⚠ [CNC{cnc_no}] Not connected")
            return
        try:
            m = self._cnc
            if m is None: return
            z    = config.CNC1_Z_CLEAR if cnc_no == 1 else config.CNC2_Z_CLEAR
            feed = config.CNC1_FEED_RATE if cnc_no == 1 else config.CNC2_FEED_RATE
            m.cnc_z_move(cnc, z, feed)
            self.log(f"  [CNC{cnc_no}] Pogo pins retracted (Z={config.CNC_Z_CLEAR}mm)")
        except Exception as e:
            self.log(f"  ⚠ [CNC{cnc_no}] Retract error: {e}")

    def _cnc1_move_to(self, sensor_id):
        """Move CNC 1 to stored X position for a reference sensor."""
        if self.cnc1 is None:
            self.log(f"  ⚠ [CNC1] Not connected")
            return
        try:
            m = self._cnc
            if m is None: return
            m.cnc1_move_to_reference(self.cnc1, sensor_id)
            x = config.CNC1_X_POSITIONS.get(sensor_id, '?')
            self.log(f"  [CNC1] Moved to Ref {sensor_id}  X={x} mm")
        except Exception as e:
            self.log(f"  ⚠ [CNC1] Move error: {e}")

    def _cnc2_move_to(self, bath_no, slot):
        """Move CNC 2 to stored X position for a bath/slot."""
        if self.cnc2 is None:
            self.log(f"  ⚠ [CNC2] Not connected")
            return
        try:
            m = self._cnc
            if m is None: return
            m.cnc2_move_to_batch(self.cnc2, bath_no, slot)
            x = config.CNC2_X_POSITIONS.get((bath_no, slot), '?')
            self.log(f"  [CNC2] Moved to Bath {bath_no} Slot {slot}  X={x} mm")
        except Exception as e:
            self.log(f"  ⚠ [CNC2] Move error: {e}")

    def _save_cnc1_positions(self):
        if not self.conn:
            return
        for key, entry in self._cnc1_pos_entries.items():
            val = entry.text().strip()
            if val:
                config.save_config(self.conn, key, val)
        # Save Z
        z_val = self._cnc1_z_entry.text().strip()
        if z_val:
            config.save_config(self.conn, 'cnc1_z_connect', z_val)
        self.log("  [CNC1] Positions saved to DB.")

    def _save_cnc2_positions(self):
        if not self.conn:
            return
        for key, entry in self._cnc2_pos_entries.items():
            val = entry.text().strip()
            if val:
                config.save_config(self.conn, key, val)
        # Save Z
        z_val = self._cnc2_z_entry.text().strip()
        if z_val:
            config.save_config(self.conn, 'cnc2_z_connect', z_val)
        self.log("  [CNC2] Positions saved to DB.")

    def _save_slot_positions(self):
        # Legacy -- redirects to new save method
        self._save_cnc2_positions()

    # ----------------------------------------------------------
    # SENSOR LIST + SKIP
    # ----------------------------------------------------------
    def populate_sensor_list(self, session_config):
        """Populate the sensor list table from session config."""
        self.sensor_list_table.setRowCount(0)
        if not self.conn:
            return
        sensors = fetch_all_session_sensors(self.conn, session_config)
        for s in sensors:
            row = self.sensor_list_table.rowCount()
            self.sensor_list_table.insertRow(row)
            self.sensor_list_table.setItem(row, 0, QTableWidgetItem(str(s['certificate_no'])))
            self.sensor_list_table.setItem(row, 1, QTableWidgetItem(s['serial']))
            self.sensor_list_table.setItem(row, 2, QTableWidgetItem(str(s['batch_no'])))
            status = QTableWidgetItem("PENDING")
            status.setForeground(QColor("#7a8290"))
            self.sensor_list_table.setItem(row, 3, status)

    def _skip_selected_sensor(self):
        row = self.sensor_list_table.currentRow()
        if row < 0:
            return
        serial = self.sensor_list_table.item(row, 1).text()
        if self.conn:
            mark_sensor_skipped(self.conn, serial)
        self.skipped_sensors.add(serial)
        item = QTableWidgetItem("SKIP")
        item.setForeground(QColor("#f7a530"))
        self.sensor_list_table.setItem(row, 3, item)
        self.log(f"  ⊘ Sensor {serial} marked as SKIP")

    def _unskip_selected_sensor(self):
        row = self.sensor_list_table.currentRow()
        if row < 0:
            return
        serial = self.sensor_list_table.item(row, 1).text()
        if self.conn:
            clear_sensor_skip(self.conn, serial)
        self.skipped_sensors.discard(serial)
        item = QTableWidgetItem("PENDING")
        item.setForeground(QColor("#7a8290"))
        self.sensor_list_table.setItem(row, 3, item)
        self.log(f"  ↺ Sensor {serial} unskipped")

    def update_sensor_list_status(self, serial, status_text, color):
        for row in range(self.sensor_list_table.rowCount()):
            item = self.sensor_list_table.item(row, 1)
            if item and item.text() == serial:
                s = QTableWidgetItem(status_text)
                s.setForeground(QColor(color))
                self.sensor_list_table.setItem(row, 3, s)
                return

    # ----------------------------------------------------------
    # BATCH STATUS (Progress page)
    # ----------------------------------------------------------
    def populate_batch_status(self, session_config):
        self.batch_status_table.setRowCount(0)
        total = sum(len(item['batches']) for item in session_config)
        self.queue_lbl.setText(f"  {total} batch(es) queued")
        for item in session_config:
            for bn in item['batches']:
                row = self.batch_status_table.rowCount()
                self.batch_status_table.insertRow(row)
                self.batch_status_table.setItem(row, 0, QTableWidgetItem(str(bn)))
                self.batch_status_table.setItem(
                    row, 1, QTableWidgetItem(BATH_LABEL[item['bath_no']])
                )
                s = QTableWidgetItem("WAITING")
                s.setForeground(QColor("#a07840"))
                self.batch_status_table.setItem(row, 2, s)

    def update_batch_status(self, batch_no, text, color):
        for row in range(self.batch_status_table.rowCount()):
            item = self.batch_status_table.item(row, 0)
            if item and item.text() == str(batch_no):
                s = QTableWidgetItem(text)
                s.setForeground(QColor(color))
                self.batch_status_table.setItem(row, 2, s)
                return

    # ----------------------------------------------------------
    # TIMERS
    # ----------------------------------------------------------
    def start_timers(self, session_config):
        for item in session_config:
            bath_no = item['bath_no']
            total   = self.wait_times[bath_no]
            self.elapsed[bath_no] = 0
            self.timer_status[bath_no].setText("TIMING")
            self.timer_status[bath_no].setStyleSheet("color: #a07840; font-size: 11px;")
            self.timer_bars[bath_no].setValue(100)

            t = QTimer()
            t.setInterval(1000)

            def tick(b=bath_no, tot=total):
                self.elapsed[b] += 1
                remaining = max(0, tot - self.elapsed[b])
                pct = int((remaining / tot) * 100) if tot > 0 else 0
                h   = remaining // 3600
                m   = (remaining % 3600) // 60
                s   = remaining % 60
                self.timer_labels[b].setText(f"{h:02d}:{m:02d}:{s:02d}")
                self.timer_bars[b].setValue(pct)
                if remaining <= 0:
                    self.qtimers[b].stop()
                    self.timer_labels[b].setText("00:00:00")
                    self.timer_bars[b].setValue(0)
                    self.timer_status[b].setText("READY ✓")
                    self.timer_status[b].setStyleSheet(
                        "color: #5a9e6f; font-weight: bold; font-size: 11px;"
                    )
                    self.log(f"  ✓ {BATH_LABEL[b]} timer done -- queued for measurement")
                    if self.worker:
                        self.worker.mark_bath_ready(b)

            t.timeout.connect(tick)
            t.start()
            self.qtimers[bath_no] = t

    # ----------------------------------------------------------
    # SESSION CONTROL
    # ----------------------------------------------------------
    def start_session(self):
        if not self.validate_settings():
            return
        session_config = self.build_session_config()
        if not session_config:
            self.log("  ⚠ No batches selected.")
            return

        self._session_config = session_config
        self.log("=" * 50)
        self.log("  SESSION STARTED")
        self.log("=" * 50)

        self.readings_table.setRowCount(0)
        self.sensor_rows.clear()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.populate_sensor_list(session_config)
        self.populate_batch_status(session_config)
        self.start_timers(session_config)

        # Switch to Progress page automatically
        self._switch_page("Progress")

        sim_config = self.sim_dialog.get_sim_config()

        self.worker = MeasurementWorker(
            session_config, self.wait_times,
            cnc1=self.cnc1, cnc2=self.cnc2,
            bridge=self.bridge, sim_config=sim_config
        )
        self.worker.log_signal.connect(self.log)
        self.worker.reading_signal.connect(self.on_reading)
        self.worker.stage_signal.connect(self.on_stage)
        self.worker.stable_signal.connect(self.on_stable)
        self.worker.skip_signal.connect(self.on_skip)
        self.worker.warning_signal.connect(self.on_warning)
        self.worker.batch_done_signal.connect(self.on_batch_done)
        self.worker.bath_done_signal.connect(self.on_bath_done)
        self.worker.session_done_signal.connect(self.on_session_done)
        self.worker.start()

    def stop_session(self):
        if self.worker:
            self.worker.stop()
        for t in self.qtimers.values():
            t.stop()
        self.log("  [STOP] Session stopped by user.")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    # ----------------------------------------------------------
    # WORKER SIGNALS
    # ----------------------------------------------------------
    def on_reading(self, serial, value):
        if serial not in self.sensor_rows:
            row = self.readings_table.rowCount()
            self.readings_table.insertRow(row)
            self.readings_table.setItem(row, 0, QTableWidgetItem(serial))
            self.readings_table.setItem(row, 2, QTableWidgetItem("--"))
            self.readings_table.setItem(row, 3, QTableWidgetItem("--"))
            s = QTableWidgetItem("SCANNING")
            s.setForeground(QColor("#a07840"))
            self.readings_table.setItem(row, 4, s)
            self.sensor_rows[serial] = row
        row = self.sensor_rows[serial]
        self.readings_table.setItem(row, 1, QTableWidgetItem(f"{value:.9f}"))

    def on_stage(self, serial, stage, passed):
        if serial not in self.sensor_rows:
            return
        row  = self.sensor_rows[serial]
        col  = 2 if stage == 1 else 3
        item = QTableWidgetItem("✓" if passed else "✗")
        item.setForeground(QColor("#5a9e6f" if passed else "#c0614a"))
        self.readings_table.setItem(row, col, item)

    def on_stable(self, serial, value, sensor_class):
        if serial not in self.sensor_rows:
            return
        row   = self.sensor_rows[serial]
        color = "#5a9e6f" if sensor_class not in ('FAIL',) else "#c0614a"
        item  = QTableWidgetItem(f"✓ {sensor_class}")
        item.setForeground(QColor(color))
        self.readings_table.setItem(row, 4, item)
        self.update_sensor_list_status(serial, sensor_class, color)
        self.log(f"  ✓ DB SAVED: {serial} = {value:.9f}  →  {sensor_class}")

    def on_skip(self, serial):
        if serial not in self.sensor_rows:
            row = self.readings_table.rowCount()
            self.readings_table.insertRow(row)
            self.readings_table.setItem(row, 0, QTableWidgetItem(serial))
            for col in [1, 2, 3]:
                self.readings_table.setItem(row, col, QTableWidgetItem("—"))
            self.sensor_rows[serial] = row
        row  = self.sensor_rows[serial]
        item = QTableWidgetItem("⊘  SKIP")
        item.setForeground(QColor("#f7a530"))
        self.readings_table.setItem(row, 4, item)
        self.update_sensor_list_status(serial, "SKIP", "#f7a530")

    def on_warning(self, message):
        msg = QMessageBox(self)
        msg.setWindowTitle("⚠  Calibration Warning")
        msg.setText(message)
        msg.setIcon(QMessageBox.Warning)
        msg.setStandardButtons(
            QMessageBox.Ok | QMessageBox.Abort
        )
        msg.setDefaultButton(QMessageBox.Ok)
        result = msg.exec()
        if result == QMessageBox.Abort:
            self.stop_session()

    def on_batch_done(self, batch_no):
        self.update_batch_status(batch_no, "✓ COMPLETE", "#5a9e6f")
        for child in self.findChildren(ProgressDialog):
            child.refresh()

    def on_bath_done(self, bath_no):
        self.timer_status[bath_no].setText("DONE ✓")
        self.timer_status[bath_no].setStyleSheet(
            "color: #5a9e6f; font-size: 11px;"
        )
        self.log(f"  ✓ {BATH_LABEL[bath_no]} all batches complete.")

    def on_session_done(self):
        self.log("=" * 50)
        self.log("  SESSION COMPLETE")
        self.log("=" * 50)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        for t in self.qtimers.values():
            t.stop()

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------
    def log(self, msg):
        ts = time.strftime('%H:%M:%S')
        full = f"[{ts}] {msg}"
        self.log_window.append(full)

    def open_progress(self):
        dlg = ProgressDialog(self.conn, self)
        dlg.exec()

    def validate_settings(self):
        seen = {}
        for bath_no, row in self.bath_rows.items():
            for combo in row['combos']:
                bn = combo.currentData()
                if bn is None:
                    continue
                if bn in seen:
                    self.log(
                        f"  ⚠ Batch {bn} assigned to both "
                        f"{BATH_LABEL[seen[bn]]} and {BATH_LABEL[bath_no]}"
                    )
                    return False
                seen[bn] = bath_no
        return True

    def build_session_config(self):
        cfg = []
        for bath_no, row in self.bath_rows.items():
            ref     = row['ref'].currentText()
            batches = [
                c.currentData() for c in row['combos']
                if c.currentData() is not None
            ]
            if batches:
                t    = self.timer_pickers[bath_no].time()
                secs = t.hour() * 3600 + t.minute() * 60 + t.second()
                self.wait_times[bath_no] = secs
                cfg.append({'bath_no': bath_no, 'ref': ref, 'batches': batches})
        cfg.sort(key=lambda x: self.wait_times.get(x['bath_no'], 9999))
        return cfg

    # ----------------------------------------------------------
    # CLOSE
    # ----------------------------------------------------------
    def closeEvent(self, event):
        if self.worker:
            self.worker.stop()
        if self.cnc1:
            try:
                m = self._cnc
                if m: m.cnc_close(self.cnc1)
            except Exception:
                pass
        if self.cnc2:
            try:
                m = self._cnc
                if m: m.cnc_close(self.cnc2)
            except Exception:
                pass
        if self.bridge:
            bridge_close(self.bridge)
        if self.conn:
            self.conn.close()
        event.accept()
