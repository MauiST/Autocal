from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from config import PROGRESS_COLS
from db.queries import fetch_progress_data


class ProgressDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Calibration Progress")
        self.setMinimumSize(920, 520)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("  Calibration Progress Overview")
        title.setStyleSheet(
            "font-size:15px; font-weight:bold; color:#7eb8f7; padding:6px;"
        )
        layout.addWidget(title)

        self.table = QTableWidget(0, len(PROGRESS_COLS))
        self.table.setHorizontalHeaderLabels([c[0] for c in PROGRESS_COLS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_h = QHBoxLayout()
        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.clicked.connect(self.refresh)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_h.addStretch()
        btn_h.addWidget(refresh_btn)
        btn_h.addWidget(close_btn)
        layout.addLayout(btn_h)

    def refresh(self):
        rows = fetch_progress_data(self.conn)
        self.table.setRowCount(0)
        for row_data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(row_data[0])))
            self.table.setItem(row, 1, QTableWidgetItem(str(row_data[1])))
            for col_idx, val in enumerate(row_data[2:], start=2):
                if val is not None:
                    item = QTableWidgetItem("✓")
                    item.setForeground(QColor("#7ec87e"))
                else:
                    item = QTableWidgetItem("○")
                    item.setForeground(QColor("#555577"))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col_idx, item)
