import time
import random
from queue import Queue
from collections import deque

import pyads
from PySide6.QtCore import QThread, Signal

from config import BATH_COLUMN, BATH_LABEL, REF_SENSOR_ID
from db.connection import connect_db
from db.queries import fetch_batch_serials, save_full_result, BATH_COLUMNS
from measurement.stability import run_stability_check, run_stage2_check, create_sensor_state
from measurement.its90 import calculate_its90, get_ref_coefficients, get_standard_resistor, validate_ref_for_bath
from measurement.cvd import calculate_cvd
from instruments.bridge import bridge_query_channel
from plc.outputs import (
    plc_activate_reference, plc_deactivate_reference,
    plc_activate_batch, plc_deactivate_batch,
    plc_check_confirmed, plc_all_outputs_off
)


class MeasurementWorker(QThread):
    log_signal          = Signal(str)
    reading_signal      = Signal(str, float)
    stage_signal        = Signal(str, int, bool)
    stable_signal       = Signal(str, float, str)
    warning_signal      = Signal(str)
    batch_done_signal   = Signal(int)
    bath_done_signal    = Signal(int)
    session_done_signal = Signal()

    def __init__(self, session_config, wait_times, plc, bridge=None, sim_config=None):
        super().__init__()
        self.session_config = session_config
        self.wait_times     = wait_times
        self.plc            = plc
        self.bridge         = bridge
        self.sim_config     = sim_config or {
            'ref_ratio': 1.0, 'ref_variance': 1e-7,
            'dut_ratio': 1.0, 'dut_variance': 1e-7,
        }
        self._running       = True
        self._ready_queue   = Queue()

    def mark_bath_ready(self, bath_no):
        self._ready_queue.put(bath_no)
        self.log(f"  ✓ {BATH_LABEL[bath_no]} ready -- added to measurement queue")

    def stop(self):
        self._running = False
        self._ready_queue.put(None)

    def log(self, msg):
        self.log_signal.emit(msg)

    def run(self):
        config_by_bath = {item['bath_no']: item for item in self.session_config}
        total          = len(self.session_config)
        processed      = 0

        self.log("=" * 50)
        self.log("  Worker started -- waiting for bath timers")
        self.log("=" * 50)

        while processed < total and self._running:
            bath_no = self._ready_queue.get()
            if bath_no is None or not self._running:
                break

            item = config_by_bath.get(bath_no)
            if not item:
                continue

            ref_name   = item['ref']
            ref_number = next(k for k, v in REF_SENSOR_ID.items() if v == ref_name)

            self.log(f"  → {BATH_LABEL[bath_no]}  Ref: {ref_name}")

            if self.plc:
                plc_activate_reference(self.plc, ref_number)
                self.log(f"    [PLC] Reference {ref_name} --> Output {ref_number} ON")

            for slot, bn in enumerate(item['batches'], start=1):
                if not self._running:
                    break
                self.log(f"    Batch {bn}  Slot {slot}  --> Output {slot + 4}")
                self._measure_batch(bath_no, bn, slot, ref_name)
                self.batch_done_signal.emit(bn)

            # Turn reference OFF after all batches in this bath complete
            if self.plc:
                plc_deactivate_reference(self.plc)
                self.log(f"    [PLC] Reference OFF -- {BATH_LABEL[bath_no]} complete")

            self.bath_done_signal.emit(bath_no)
            processed += 1

        if self.plc:
            plc_all_outputs_off(self.plc)
            self.log("  [PLC] All outputs OFF.")

        self.session_done_signal.emit()

    def _measure_batch(self, bath_no, batch_no, slot, ref_name):
        # Activate batch output
        if self.plc:
            plc_activate_batch(self.plc, slot)
            self.log(f"      [PLC] Batch output ON --> Output {slot + 4}")
            self.log(f"      [PLC] Waiting for SettingsConfirmed...")
            while self._running:
                if plc_check_confirmed(self.plc):
                    self.log(f"      [PLC] Settings confirmed -- starting measurement")
                    break
                time.sleep(0.5)

        conn    = connect_db()
        serials = fetch_batch_serials(conn, batch_no)
        column  = BATH_COLUMN[bath_no]

        total_channels = len(serials) + 1

        # Failed channels placeholder -- wire to GUI checkboxes later
        failed_channels = []
        sensor_buffers, sensor_stable, final_readings = create_sensor_state(
            total_channels, failed_channels
        )

        # Reference temperature -- set when channel 0 goes stable
        ref_temperature = None

        # Fetch ITS-90 coefficients and standard resistor for this session
        ref_coefficients   = get_ref_coefficients(conn, ref_name)
        r_standard_25      = get_standard_resistor(conn, '25')
        r_standard_100     = get_standard_resistor(conn, '100')
        if ref_coefficients is None:
            self.log(f"      ⚠ No ITS-90 coefficients found for {ref_name} -- check DB")

        def label(chno):
            return f'REF {ref_name}' if chno == 0 else serials[chno - 1]

        scan = 1
        # Simulation: each channel walks slowly around its mean
        # so readings are correlated and stability is achievable.
        sim_current = {}   # chno -> current simulated ratio

        while not all(sensor_stable) and self._running:
            self.log(f"      Scan {scan}  --  Batch {batch_no}")

            for chno in range(total_channels):
                if sensor_stable[chno]:
                    continue

                # Bridge channel number: chno 0 = channel 1, chno 1 = channel 2 etc.
                bridge_channel = chno + 1

                if self.bridge:
                    # Real bridge measurement
                    ratio = bridge_query_channel(self.bridge, bridge_channel)
                    if ratio is None:
                        self.log(f"      ⚠ [{label(chno)}] bridge query failed -- skipping")
                        continue
                else:
                    # Simulation: slow random walk so readings converge naturally.
                    # Step size is 1/10 of the variance slider value per scan.
                    if chno not in sim_current:
                        # Initialise at mean on first reading
                        sim_current[chno] = (
                            self.sim_config['ref_ratio'] if chno == 0
                            else self.sim_config['dut_ratio']
                        )
                    step_sigma = (
                        self.sim_config['ref_variance'] if chno == 0
                        else self.sim_config['dut_variance']
                    ) * 0.01
                    sim_current[chno] += random.normalvariate(0, step_sigma)
                    ratio = sim_current[chno]

                sensor_buffers[chno].append(ratio)
                self.reading_signal.emit(label(chno), ratio)
                self.log(
                    f"      [{label(chno)}]  ratio: {ratio:.9f}"
                    f"  (buffer: {len(sensor_buffers[chno])}/5)"
                )
                time.sleep(0.5)

            for chno in range(total_channels):
                if sensor_stable[chno]:
                    continue
                buf = sensor_buffers[chno]
                if len(buf) < 5:
                    continue

                # Batch sensors must wait for reference to be stable first
                if chno > 0 and ref_temperature is None:
                    self.log(f"      [{label(chno)}] waiting for reference sensor...")
                    continue

                # Stage 1
                readings = list(buf)[-5:]
                passed1, spread = run_stability_check(readings)
                self.stage_signal.emit(label(chno), 1, passed1)
                if not passed1:
                    continue

                # Stage 2
                if self.bridge:
                    sixth = bridge_query_channel(self.bridge, chno + 1)
                    if sixth is None:
                        continue
                else:
                    step_sigma = (
                        self.sim_config['ref_variance'] if chno == 0
                        else self.sim_config['dut_variance']
                    ) * 0.01
                    sim_current[chno] += random.normalvariate(0, step_sigma)
                    sixth = sim_current[chno]
                passed2, delta = run_stage2_check(readings, sixth)
                self.stage_signal.emit(label(chno), 2, passed2)
                if not passed2:
                    # Discard sixth -- do NOT put it in the buffer.
                    # The next scan loop will add a fresh reading naturally.
                    continue

                # Stable
                sensor_stable[chno]  = True
                final_readings[chno] = sixth

                if chno == 0:
                    # Reference: log ratio + calculated resistance for debugging
                    r_ref_calc = sixth * r_standard_25
                    self.log(
                        f"      ✓ STABLE  [{label(chno)}]  ratio: {sixth:.9f}"
                        f"  →  R = {r_ref_calc:.7f} Ω  (using std = {r_standard_25} Ω)"
                    )
                else:
                    self.log(f"      ✓ STABLE  [{label(chno)}]  ratio: {sixth:.9f}")

                if chno == 0:
                    # Reference sensor stable -- calculate ITS-90 temperature
                    if ref_coefficients is not None:
                        try:
                            t_ref, w, wr, dw = calculate_its90(
                                sixth, ref_coefficients, r_standard_25
                            )
                            ref_temperature = t_ref
                            self.log(
                                f"      → ITS-90: R={r_ref_calc:.7f}Ω"
                                f"  Roits={ref_coefficients['roits']}Ω"
                            )
                            self.log(f"      → ITS-90: W={w:.9f}  Wr={wr:.9f}  dW={dw:.10f}")
                            self.log(f"      → Bath temperature: {t_ref:.5f} °C")

                            # Validate reference sensor and bath temperature
                            val_warnings = validate_ref_for_bath(
                                ref_name, bath_no, t_ref
                            )
                            for warning in val_warnings:
                                self.log(f"      {warning}")
                                self.warning_signal.emit(warning)
                        except Exception as e:
                            self.log(f"      ⚠ ITS-90 calculation error: {e}")
                            ref_temperature = None
                    else:
                        self.log(f"      ⚠ Skipping ITS-90 -- no coefficients for {ref_name}")

                elif chno > 0 and final_readings[chno] is not None:
                    # CVD calculation for batch PT100 sensor
                    try:
                        r_measured, t_sensor, dev_temp, dev_res, sensor_class = calculate_cvd(
                            sixth, r_standard_100, ref_temperature
                        )
                        self.log(
                            f"      → CVD: R={r_measured:.7f}Ω  "
                            f"T={t_sensor:.5f}°C  "
                            f"ΔT={dev_temp:+.5f}°C  "
                            f"ΔR={dev_res:+.7f}Ω  "
                            f"Class={sensor_class}"
                        )

                        if sensor_class == 'FAIL':
                            self.log(
                                f"      ⚠ SENSOR OUTSIDE OF CLASSES: {serials[chno - 1]}"
                            )
                            self.stable_signal.emit(
                                serials[chno - 1], sixth, 'FAIL'
                            )
                        else:
                            saved = save_full_result(
                                conn, serials[chno - 1], bath_no,
                                ref_temperature, r_measured,
                                t_sensor, dev_temp, dev_res, sensor_class
                            )
                            if saved:
                                self.stable_signal.emit(
                                    serials[chno - 1], sixth, sensor_class
                                )
                                self.log(
                                    f"      → DB saved: {serials[chno - 1]}"
                                    f"  Class {sensor_class}"
                                )
                    except Exception as e:
                        self.log(f"      ⚠ CVD error for {serials[chno - 1]}: {e}")

            scan += 1

        if self.plc:
            plc_deactivate_batch(self.plc, slot)
            self.log(f"      [PLC] Batch output OFF --> Output {slot + 4}")

        conn.close()
        self.log(f"    Batch {batch_no} complete.")
