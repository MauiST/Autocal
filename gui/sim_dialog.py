import math
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSlider, QPushButton, QGroupBox
)
from PySide6.QtCore import Qt


class SimDialog(QDialog):
    """
    Simulation mode popup.
    Shown when the Micro-K 70 bridge is not connected.
    Provides 4 sliders to control simulated ratio measurements:
        - Ref  ratio    : linear  0.30 → 1.50
        - Ref  variance : log     0.002 → 0.00000001
        - DUT  ratio    : linear  0.30 → 1.50
        - DUT  variance : log     0.002 → 0.00000001
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚗  Simulation Mode")
        self.setMinimumWidth(500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.WindowCloseButtonHint
        )
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("⚗  Simulation Mode  —  Bridge Not Connected")
        title.setStyleSheet(
            "color: #f7c97e; font-size: 13px; font-weight: bold;"
            "font-family: Consolas;"
        )
        layout.addWidget(title)

        info = QLabel(
            "Adjust sliders to simulate bridge ratio measurements.\n"
            "Ratio ≈ 1.0 corresponds to sensor at calibration temperature.\n"
            "Variance controls reading noise — lower = more stable."
        )
        info.setStyleSheet("color: #aaaacc; font-size: 11px;")
        layout.addWidget(info)

        # Reference sensor group
        ref_group = QGroupBox("Reference SPRT  (channel 1 — 25Ω standard)")
        ref_grid  = QGridLayout(ref_group)
        self.sim_ref_ratio    = self._make_slider_row(ref_grid, 0, "Ratio",    is_variance=False)
        self.sim_ref_variance = self._make_slider_row(ref_grid, 1, "Variance", is_variance=True)
        layout.addWidget(ref_group)

        # DUT sensors group
        dut_group = QGroupBox("DUT PT100s  (channels 2–7 — 100Ω standard)")
        dut_grid  = QGridLayout(dut_group)
        self.sim_dut_ratio    = self._make_slider_row(dut_grid, 0, "Ratio",    is_variance=False)
        self.sim_dut_variance = self._make_slider_row(dut_grid, 1, "Variance", is_variance=True)
        layout.addWidget(dut_group)

        # Bath presets from VB simulation values
        presets_group = QGroupBox("Bath Presets  —  click to set ref ratio")
        presets_h     = QHBoxLayout(presets_group)

        presets = [
            ("0°C",    1026),
            ("-195°C",  197),
            ("-76°C",   687),
            ("100°C",  1415),
        ]
        for label, val in presets:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "QPushButton { background-color: #16213e; color: #f7c97e; "
                "border: 1px solid #aa6600; border-radius: 4px; padding: 2px 8px; }"
                "QPushButton:hover { background-color: #aa6600; color: #ffffff; }"
            )
            btn.clicked.connect(lambda checked, v=val: self.sim_ref_ratio.setValue(v))
            presets_h.addWidget(btn)

        layout.addWidget(presets_group)

        # Close button
        btn_h = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.hide)
        btn_h.addStretch()
        btn_h.addWidget(close_btn)
        layout.addLayout(btn_h)

    def _make_slider_row(self, grid, row, label_text, is_variance):
        lbl = QLabel(label_text)
        lbl.setFixedWidth(80)

        slider  = QSlider(Qt.Horizontal)
        val_lbl = QLabel()
        val_lbl.setFixedWidth(110)
        val_lbl.setStyleSheet(
            "color: #f7c97e; font-family: Consolas; font-size: 12px;"
        )

        if is_variance:
            # Logarithmic scale: 0-1000 maps to 10^-5 → 10^-9
            # At default (100) step sigma = ~1e-6, spread of 5 ≈ 5e-6 < threshold
            slider.setMinimum(0)
            slider.setMaximum(1000)
            slider.setValue(100)  # default: very quiet, will pass stability quickly

            def update(v, vl=val_lbl):
                exp = -5 + (-4) * (v / 1000)
                val = math.pow(10, exp)
                vl.setText(f"{val:.2e}")

            slider.valueChanged.connect(update)
            update(100)
        else:
            # Linear scale: 300-1500 maps to 0.300 → 1.500
            # Ref default: 1.026301 (0°C bath from VB)
            # DUT default: 1.000500 (slightly off reference, realistic)
            slider.setMinimum(300)
            slider.setMaximum(1500)
            default = 1026 if 'Ref' in label_text else 1001
            slider.setValue(default)

            def update(v, vl=val_lbl):
                vl.setText(f"{v / 1000:.6f}")

            slider.valueChanged.connect(update)
            update(default)

        grid.addWidget(lbl,     row, 0)
        grid.addWidget(slider,  row, 1)
        grid.addWidget(val_lbl, row, 2)
        return slider

    def get_sim_config(self):
        """
        Read current slider values and return simulation config dict.
        Called by worker at session start.
        """
        ref_ratio_val = self.sim_ref_ratio.value() / 1000
        dut_ratio_val = self.sim_dut_ratio.value() / 1000
        ref_var_exp   = -5 + (-4) * (self.sim_ref_variance.value() / 1000)
        dut_var_exp   = -5 + (-4) * (self.sim_dut_variance.value() / 1000)

        return {
            'ref_ratio':    ref_ratio_val,
            'ref_variance': math.pow(10, ref_var_exp),
            'dut_ratio':    dut_ratio_val,
            'dut_variance': math.pow(10, dut_var_exp),
        }
