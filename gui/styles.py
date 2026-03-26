# Neumorphic Light Theme for PySide6
# Qt does not support box-shadow -- neumorphic effect achieved via
# border, border-radius, and background colour only.
#
# Palette:
#   Base surface : #e8ecef
#   Inset well   : #dde1e5
#   Light edge   : #f4f7fa
#   Dark edge    : #c2c8d0
#   Accent blue  : #4a7fa5
#   Accent green : #5a9e6f
#   Accent red   : #c0614a
#   Text primary : #3a3f47
#   Text muted   : #7a8290

NEU_STYLE = """
    /* ── Base surfaces ───────────────────────────────────────── */
    QMainWindow, QWidget, QDialog {
        background-color: #e8ecef;
        color: #3a3f47;
        font-family: 'Georgia', serif;
        font-size: 13px;
    }

    /* ── GroupBox -- raised card ─────────────────────────────── */
    QGroupBox {
        background-color: #e8ecef;
        border: 1px solid #c2c8d0;
        border-radius: 12px;
        margin-top: 18px;
        padding: 14px 12px 12px 12px;
        font-weight: bold;
        font-size: 9px;
        color: #7a8290;
        letter-spacing: 2px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 2px 8px;
        background-color: #e8ecef;
        color: #7a8290;
        font-size: 9px;
        letter-spacing: 2px;
    }

    /* ── Standard button ─────────────────────────────────────── */
    QPushButton {
        background-color: #e8ecef;
        border: 1px solid #c2c8d0;
        border-radius: 10px;
        padding: 7px 18px;
        color: #3a3f47;
        font-family: 'Georgia', serif;
        font-size: 12px;
    }
    QPushButton:hover {
        background-color: #f0f3f6;
        color: #4a7fa5;
        border: 1px solid #4a7fa5;
    }
    QPushButton:pressed {
        background-color: #dde1e5;
        border: 1px solid #b0b8c2;
    }
    QPushButton:disabled {
        color: #aab0b8;
        border: 1px solid #d8dce0;
        background-color: #e8ecef;
    }

    /* ── Start button ────────────────────────────────────────── */
    QPushButton#startBtn {
        background-color: #e8ecef;
        color: #5a9e6f;
        font-weight: bold;
        border: 1.5px solid #5a9e6f;
        border-radius: 10px;
    }
    QPushButton#startBtn:hover {
        background-color: #5a9e6f;
        color: #ffffff;
    }
    QPushButton#startBtn:pressed {
        background-color: #4a8e5f;
        color: #ffffff;
        border-color: #3a7e4f;
    }
    QPushButton#startBtn:disabled {
        color: #a0c0a8;
        border-color: #c0d8c8;
    }

    /* ── Stop button ─────────────────────────────────────────── */
    QPushButton#stopBtn {
        background-color: #e8ecef;
        color: #c0614a;
        font-weight: bold;
        border: 1.5px solid #c0614a;
        border-radius: 10px;
    }
    QPushButton#stopBtn:hover {
        background-color: #c0614a;
        color: #ffffff;
    }
    QPushButton#stopBtn:pressed {
        background-color: #a0513a;
        color: #ffffff;
        border-color: #904030;
    }
    QPushButton#stopBtn:disabled {
        color: #d0a898;
        border-color: #ddc0b8;
    }

    /* ── Batches button ──────────────────────────────────────── */
    QPushButton#batchesBtn {
        background-color: #e8ecef;
        color: #4a7fa5;
        font-weight: bold;
        border: 1.5px solid #4a7fa5;
        border-radius: 10px;
    }
    QPushButton#batchesBtn:hover {
        background-color: #4a7fa5;
        color: #ffffff;
    }
    QPushButton#batchesBtn:pressed {
        background-color: #3a6f95;
        color: #ffffff;
    }

    /* ── ComboBox -- inset well ──────────────────────────────── */
    QComboBox {
        background-color: #dde1e5;
        border: 1px solid #c2c8d0;
        border-radius: 8px;
        padding: 6px 10px;
        color: #3a3f47;
        font-family: 'Georgia', serif;
        min-width: 80px;
    }
    QComboBox:hover { border: 1px solid #4a7fa5; }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox::down-arrow {
        image: none;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid #7a8290;
        margin-right: 8px;
    }
    QComboBox QAbstractItemView {
        background-color: #e8ecef;
        border: 1px solid #c2c8d0;
        border-radius: 8px;
        color: #3a3f47;
        selection-background-color: #4a7fa5;
        selection-color: #ffffff;
        padding: 4px;
        outline: none;
    }

    /* ── Table ───────────────────────────────────────────────── */
    QTableWidget {
        background-color: #dde1e5;
        border: 1px solid #c2c8d0;
        border-radius: 10px;
        gridline-color: #c8cdd3;
        color: #3a3f47;
        selection-background-color: #4a7fa5;
        selection-color: #ffffff;
        outline: none;
    }
    QTableWidget QHeaderView::section {
        background-color: #e8ecef;
        color: #4a7fa5;
        border: none;
        border-bottom: 2px solid #c2c8d0;
        padding: 7px 8px;
        font-weight: bold;
        font-size: 11px;
        letter-spacing: 1px;
    }
    QTableWidget::item {
        padding: 4px 8px;
        border-bottom: 1px solid #d8dce0;
    }
    QTableWidget::item:selected {
        background-color: #4a7fa5;
        color: #ffffff;
    }

    /* ── Log / Text area -- inset well ──────────────────────── */
    QTextEdit {
        background-color: #dde1e5;
        border: 1px solid #c2c8d0;
        border-radius: 10px;
        color: #3a6e4a;
        font-family: 'Courier New', monospace;
        font-size: 12px;
        padding: 8px;
    }

    /* ── Progress bar ────────────────────────────────────────── */
    QProgressBar {
        background-color: #dde1e5;
        border: 1px solid #c2c8d0;
        border-radius: 6px;
        text-align: center;
        color: #3a3f47;
        font-size: 11px;
        height: 14px;
    }
    QProgressBar::chunk {
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:0,
            stop:0 #4a7fa5, stop:1 #6a9fc5
        );
        border-radius: 6px;
    }

    /* ── Time / Spin edit ────────────────────────────────────── */
    QTimeEdit, QSpinBox {
        background-color: #dde1e5;
        border: 1px solid #c2c8d0;
        border-radius: 8px;
        padding: 5px 8px;
        color: #3a3f47;
        min-width: 80px;
    }
    QTimeEdit:hover, QSpinBox:hover {
        border: 1px solid #4a7fa5;
    }
    QTimeEdit::up-button,  QTimeEdit::down-button,
    QSpinBox::up-button,   QSpinBox::down-button {
        background-color: #e8ecef;
        border: none;
        border-left: 1px solid #c2c8d0;
        width: 18px;
    }
    QTimeEdit::up-button:hover,  QTimeEdit::down-button:hover,
    QSpinBox::up-button:hover,   QSpinBox::down-button:hover {
        background-color: #4a7fa5;
    }

    /* ── Scrollbar ───────────────────────────────────────────── */
    QScrollBar:vertical {
        background: #e8ecef;
        width: 10px;
        border-radius: 5px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: #c2c8d0;
        border-radius: 5px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover  { background: #4a7fa5; }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical      { height: 0; }
    QScrollBar:horizontal {
        background: #e8ecef;
        height: 10px;
        border-radius: 5px;
    }
    QScrollBar::handle:horizontal {
        background: #c2c8d0;
        border-radius: 5px;
        min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover { background: #4a7fa5; }
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal     { width: 0; }

    /* ── Named labels ────────────────────────────────────────── */
    QLabel#certLabel {
        color: #a07840;
        font-style: italic;
        font-size: 12px;
    }
    QLabel#plcLabel {
        color: #5a9e6f;
        font-weight: bold;
        font-size: 12px;
    }
    QLabel#plcFail {
        color: #c0614a;
        font-weight: bold;
        font-size: 12px;
    }
    QLabel#queueLabel {
        color: #4a7fa5;
        font-weight: bold;
    }

    /* ── Tooltip ─────────────────────────────────────────────── */
    QToolTip {
        background-color: #e8ecef;
        color: #3a3f47;
        border: 1px solid #c2c8d0;
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 11px;
    }
"""

# Backward compatibility alias
DARK_STYLE = NEU_STYLE
