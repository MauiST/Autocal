"""
worker.py
=========
Measurement worker thread.

Changes from previous version:
  - PLC replaced by CNC connector control (cnc1, cnc2)
  - Skip sensor support -- skipped sensors emit skip_signal and are not measured
  - Bath 1-2 vs Bath 1-1 comparison -- warns if drift > 20mK (R) or 10mK (T)
  - ITS-90 coefficients and standard resistors loaded from config (DB/JSON)
  - Stable log shows ratio + calculated resistance for reference sensor
"""

import time
import random
from queue import Queue

from PySide6.QtCore import QThread, Signal

import config
from config import BATH_COLUMN, BATH_LABEL, REF_SENSOR_ID
from db.connection import connect_db
from db.queries import (
    fetch_batch_serials, fetch_skipped_serials,
    save_full_result, fetch_bath1_results, compare_bath1_results
)
from measurement.stability import run_stability_check, run_stage2_check, create_sensor_state
from measurement.its90 import calculate_its90, validate_ref_for_bath
from measurement.cvd import calculate_cvd
from instruments.bridge import bridge_query_channel


class MeasurementWorker(QThread):
    log_signal          = Signal(str)
    reading_signal      = Signal(str, float)
    stage_signal        = Signal(str, int, bool)
    stable_signal       = Signal(str, float, str)
    skip_signal         = Signal(str)          # emitted when a sensor is skipped
    warning_signal      = Signal(str)
    batch_done_signal   = Signal(int)
    bath_done_signal    = Signal(int)
    session_done_signal = Signal()

    def __init__(self, session_config, wait_times, cnc=None,
                 bridge=None, sim_config=None, cnc_disabled=False):
        super().__init__()
        self.session_config = session_config
        self.wait_times     = wait_times
        self.cnc            = cnc          # Single CNC (X=ref, Y=batch, Z=connect)
        self.cnc_disabled   = cnc_disabled # True = skip all CNC moves (manual mode)
        self.bridge         = bridge
        self.sim_config     = sim_config or {
            'ref_ratio': 1.0, 'ref_variance': 1e-7,
            'dut_ratio': 1.0, 'dut_variance': 1e-7,
        }
        self._running       = True
        self._ready_queue   = Queue()

        # Bath 1-1 results stored for Bath 1-2 comparison
        self._bath1_1_results = {}   # {serial: {resistance, temp_ref}}
        self._bath1_1_temp    = None

    def mark_bath_ready(self, bath_no):
        self._ready_queue.put(bath_no)
        self.log(f"  ✓ {BATH_LABEL[bath_no]} ready -- added to measurement queue")

    def stop(self):
        self._running = False
        self._ready_queue.put(None)

    def log(self, msg):
        self.log_signal.emit(msg)

    # ------------------------------------------------------------------
    # MAIN RUN LOOP
    # ------------------------------------------------------------------
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

            ref_name = item['ref']
            self.log(f"  → {BATH_LABEL[bath_no]}  Ref: {ref_name}")

            self._cnc_connect_reference(ref_name, bath_no)

            for slot, bn in enumerate(item['batches'], start=1):
                if not self._running:
                    break
                self.log(f"    Batch {bn}  Slot {slot}")
                self._cnc_connect_batch(bath_no, slot, bn)
                try:
                    self._measure_batch(bath_no, bn, slot, ref_name)
                except Exception as e:
                    self.log(f"    ⚠ [WORKER] Unhandled error in batch {bn}: {e}")
                    import traceback
                    self.log(traceback.format_exc())
                self._cnc_disconnect_batch(slot)
                self.batch_done_signal.emit(bn)

            self._cnc_disconnect_reference(ref_name, bath_no)
            self.bath_done_signal.emit(bath_no)
            processed += 1

        self.log("  All outputs cleared.")
        self.session_done_signal.emit()

    # ------------------------------------------------------------------
    # CNC CONNECTOR CONTROL
    # ------------------------------------------------------------------
    def _cnc_connect_reference(self, ref_name, bath_no):
        """Move X to reference sensor position (Z stays up)."""
        if self.cnc and not self.cnc_disabled:
            try:
                from cnc.control import cnc_connect_reference
                cnc_connect_reference(self.cnc, ref_name)
                self.log(f"    [CNC] Reference {ref_name} positioned (X axis)")
            except Exception as e:
                self.log(f"    ⚠ [CNC] Reference position error: {e}")
        else:
            self.log(f"    [CNC] {'DISABLED' if self.cnc_disabled else 'Simulation'} -- reference {ref_name} (manual)")

    def _cnc_disconnect_reference(self, ref_name, bath_no):
        """Reference done -- Z is already up after last batch disconnect."""
        self.log(f"    [CNC] Reference {ref_name} done")

    def _cnc_connect_batch(self, bath_no, slot, batch_no):
        """Move Y to batch slot position then lower Z to connect."""
        if self.cnc and not self.cnc_disabled:
            try:
                from cnc.control import cnc_connect_batch
                cnc_connect_batch(self.cnc, bath_no, slot)
                self.log(f"    [CNC] Batch {batch_no} slot {slot} connected (Y+Z)")
            except Exception as e:
                self.log(f"    ⚠ [CNC] Batch connect error: {e}")
        else:
            self.log(f"    [CNC] {'DISABLED' if self.cnc_disabled else 'Simulation'} -- batch {batch_no} slot {slot} (manual)")

    def _cnc_disconnect_batch(self, slot):
        """Raise Z after batch measurement."""
        if self.cnc and not self.cnc_disabled:
            try:
                from cnc.control import cnc_disconnect
                cnc_disconnect(self.cnc)
                self.log(f"    [CNC] Slot {slot} disconnected (Z raised)")
            except Exception as e:
                self.log(f"    ⚠ [CNC] Disconnect error: {e}")
        else:
            self.log(f"    [CNC] {'DISABLED' if self.cnc_disabled else 'Simulation'} -- slot {slot} disconnected (manual)")

    # ------------------------------------------------------------------
    # BATCH MEASUREMENT
    # ------------------------------------------------------------------
    def _measure_batch(self, bath_no, batch_no, slot, ref_name):
        conn    = connect_db()
        serials = fetch_batch_serials(conn, batch_no)

        # Handle skipped sensors
        skipped = set(fetch_skipped_serials(conn, batch_no))
        if skipped:
            self.log(f"      Skipped: {', '.join(skipped)}")
            for s in skipped:
                self.skip_signal.emit(s)

        active_serials = [s for s in serials if s not in skipped]
        total_channels = len(active_serials) + 1

        sensor_buffers, sensor_stable, final_readings = create_sensor_state(
            total_channels, []
        )

        ref_temperature  = None
        ref_coefficients = config.get_sprt_coefficients(ref_name)
        r_standard_25    = config.get_standard_resistor(25)
        r_standard_100   = config.get_standard_resistor(100)

        self.log(
            f"      Roits={ref_coefficients['roits']}  "
            f"Std25={r_standard_25}  Std100={r_standard_100}"
        )

        def label(chno):
            return f'REF {ref_name}' if chno == 0 else active_serials[chno - 1]

        scan            = 1
        sim_current     = {}
        # True once stage 1 passed -- next query is the 6th (stage 2) reading
        stage1_passed   = [False] * total_channels
        # Consecutive bridge query failures per channel -- auto-skip after 3
        fail_count      = [0] * total_channels
        MAX_FAILS       = 3
        # Scan timeout -- auto-skip sensor if exceeded
        MAX_SCANS       = config.get_int('max_scans',        30)
        MAX_STAGE2_FAILS = config.get_int('max_stage2_fails', 5)
        MAX_ITS90_FAILS  = config.get_int('max_its90_fails',  3)
        scan_count      = [0] * total_channels   # scans per channel
        stage2_fails    = [0] * total_channels   # stage 2 retry count
        its90_fail_count = 0                     # ITS-90 consecutive failures
        # Rolling reference buffer -- keeps updating T_ref every scan
        ref_buffer      = []

        while not all(sensor_stable) and self._running:
            self.log(f"      Scan {scan}  --  Batch {batch_no}")

            for chno in range(total_channels):
                if sensor_stable[chno]:
                    continue

                # ── Reference exits once all DUTs are stable ───────
                if chno == 0 and all(sensor_stable[1:]):
                    sensor_stable[0] = True
                    self.log(f"      ✓ REF [{ref_name}] -- all DUTs stable, reference scan complete")
                    continue

                # ── SCAN TIMEOUT -- auto-skip if exceeded ──────────
                scan_count[chno] += 1
                if chno > 0 and scan_count[chno] > MAX_SCANS:
                    self.log(
                        f"      ✗ [{label(chno)}] timeout -- no stable reading"
                        f" after {MAX_SCANS} scans -- sensor auto-skipped"
                    )
                    sensor_stable[chno] = True
                    self.skip_signal.emit(label(chno))
                    continue

                # ── SIMULATION helper ──────────────────────────────
                def _sim_read(c):
                    if c not in sim_current:
                        sim_current[c] = (
                            self.sim_config['ref_ratio'] if c == 0
                            else self.sim_config['dut_ratio']
                        )
                    sigma = (
                        self.sim_config['ref_variance'] if c == 0
                        else self.sim_config['dut_variance']
                    ) * 0.01
                    sim_current[c] += random.normalvariate(0, sigma)
                    return sim_current[c]

                # ── STATE: waiting for 6th (stage-2) reading ───────
                if stage1_passed[chno]:
                    if chno > 0 and ref_temperature is None:
                        self.log(f"      [{label(chno)}] waiting for reference...")
                        continue

                    if self.bridge:
                        sixth = bridge_query_channel(self.bridge, chno + 1)
                        if sixth is None:
                            self.log(
                                f"      ⚠ [{label(chno)}] 6th reading failed"
                                f" -- retrying next scan"
                            )
                            stage1_passed[chno] = False   # collect new readings
                            continue
                    else:
                        sixth = _sim_read(chno)

                    readings = list(sensor_buffers[chno])
                    passed2, delta = run_stage2_check(readings, sixth)
                    self.stage_signal.emit(label(chno), 2, passed2)
                    if not passed2:
                        stage2_fails[chno] += 1
                        if stage2_fails[chno] >= MAX_STAGE2_FAILS:
                            self.log(
                                f"      ✗ [{label(chno)}] Stage 2 failed"
                                f" {MAX_STAGE2_FAILS} times -- sensor auto-skipped"
                            )
                            sensor_stable[chno] = True
                            self.skip_signal.emit(label(chno))
                        else:
                            stage1_passed[chno] = False   # re-collect
                        continue

                    # ── STABLE ────────────────────────────────────
                    sensor_stable[chno]  = True
                    final_readings[chno] = sixth

                    if chno == 0:
                        # Rolling T_ref -- update every scan, never mark stable
                        ref_buffer.append(sixth)
                        if len(ref_buffer) > 5:
                            ref_buffer.pop(0)
                        ref_avg = sum(ref_buffer) / len(ref_buffer)
                        try:
                            t_ref, w, wr, dw = calculate_its90(
                                ref_avg, ref_coefficients, r_standard_25
                            )
                            if ref_temperature is None:
                                # First successful T_ref -- log full detail
                                r_ref = ref_avg * r_standard_25
                                self.log(
                                    f"      ✓ REF [{ref_name}]  "
                                    f"ratio: {ref_avg:.9f}  R={r_ref:.7f}Ω"
                                )
                                self.log(
                                    f"      → ITS-90: W={w:.9f}  "
                                    f"Wr={wr:.9f}  dW={dw:.10f}"
                                )
                                self.log(f"      → Bath temperature: {t_ref:.5f} °C")
                                for warning in validate_ref_for_bath(
                                    ref_name, bath_no, t_ref
                                ):
                                    self.log(f"      ⚠ {warning}")
                                    self.warning_signal.emit(warning)
                                if bath_no == 1:
                                    self._bath1_1_temp = t_ref
                            else:
                                # Subsequent updates -- brief log only
                                self.log(
                                    f"      → T_ref updated: {t_ref:.5f}°C"
                                    f"  (was {ref_temperature:.5f}°C)"
                                )
                            ref_temperature      = t_ref
                            its90_fail_count     = 0
                            sensor_stable[chno]  = False  # keep scanning ref
                        except Exception as e:
                            its90_fail_count += 1
                            self.log(
                                f"      ⚠ ITS-90 error ({its90_fail_count}/"
                                f"{MAX_ITS90_FAILS}): {e}"
                            )
                            if its90_fail_count >= MAX_ITS90_FAILS:
                                self.log(
                                    f"      ✗ ITS-90 failed {MAX_ITS90_FAILS} times"
                                    f" -- aborting batch"
                                )
                                conn.close()
                                return
                        # Don't mark ref as stable -- reset stage flags to keep scanning
                        sensor_stable[chno]  = False
                        stage1_passed[chno]  = False
                        sensor_buffers[chno].clear()
                    else:
                        serial = active_serials[chno - 1]
                        self._handle_sensor_stable(
                            conn, serial, sixth, r_standard_100,
                            ref_temperature, bath_no
                        )

                # ── STATE: collecting readings (scans 1–5) ─────────
                else:
                    # If buffer is full but reference not ready -- just wait
                    # Don't query bridge, don't log, don't add to buffer
                    if chno > 0 and len(sensor_buffers[chno]) >= 5 and ref_temperature is None:
                        self.log(f"      [{label(chno)}] waiting for reference...")
                        continue

                    if self.bridge:
                        ratio = bridge_query_channel(self.bridge, chno + 1)
                        if ratio is None:
                            fail_count[chno] += 1
                            if fail_count[chno] >= MAX_FAILS:
                                self.log(
                                    f"      ✗ [{label(chno)}] no bridge response"
                                    f" after {MAX_FAILS} attempts -- sensor skipped"
                                )
                                sensor_stable[chno] = True  # unblock loop
                            else:
                                self.log(f"      ⚠ [{label(chno)}] bridge query failed")
                            continue
                        fail_count[chno] = 0
                    else:
                        ratio = _sim_read(chno)

                    sensor_buffers[chno].append(ratio)
                    self.reading_signal.emit(label(chno), ratio)
                    self.log(
                        f"      [{label(chno)}]  ratio: {ratio:.9f}"
                        f"  (buffer: {len(sensor_buffers[chno])}/5)"
                    )
                    time.sleep(0.5)

                    # Check stage 1 once buffer has 5 readings
                    if len(sensor_buffers[chno]) == 5:
                        if chno > 0 and ref_temperature is None:
                            # Will wait silently next scan (handled above)
                            continue
                        readings = list(sensor_buffers[chno])
                        passed1, spread = run_stability_check(readings)
                        self.stage_signal.emit(label(chno), 1, passed1)
                        if passed1:
                            stage1_passed[chno] = True   # 6th reading next scan

            scan += 1

        conn.close()
        self.log(f"    Batch {batch_no} complete.")

    # ------------------------------------------------------------------
    # STABLE HANDLERS
    # ------------------------------------------------------------------
    _last_ref_temperature = None

    def _handle_reference_stable(self, sixth, ref_coefficients,
                                  r_standard_25, ref_name, bath_no):
        r_ref = sixth * r_standard_25
        self.log(
            f"      ✓ STABLE  [REF {ref_name}]  "
            f"ratio: {sixth:.9f}  →  R = {r_ref:.7f} Ω"
            f"  (std = {r_standard_25} Ω)"
        )
        try:
            t_ref, w, wr, dw = calculate_its90(
                sixth, ref_coefficients, r_standard_25
            )
            self._last_ref_temperature = t_ref
            self.log(
                f"      → ITS-90: R={r_ref:.7f}Ω  "
                f"Roits={ref_coefficients['roits']}Ω"
            )
            self.log(f"      → ITS-90: W={w:.9f}  Wr={wr:.9f}  dW={dw:.10f}")
            self.log(f"      → Bath temperature: {t_ref:.5f} °C")

            if bath_no == 1:
                self._bath1_1_temp = t_ref

            for warning in validate_ref_for_bath(ref_name, bath_no, t_ref):
                self.log(f"      ⚠ {warning}")
                self.warning_signal.emit(warning)

        except Exception as e:
            self.log(f"      ⚠ ITS-90 calculation error: {e}")
            self._last_ref_temperature = None

    def _handle_sensor_stable(self, conn, serial, sixth, r_standard_100,
                               ref_temperature, bath_no):
        self.log(f"      ✓ STABLE  [{serial}]  ratio: {sixth:.9f}")
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

            # Bath 1-2: compare against Bath 1-1
            if bath_no == 5:
                self._check_bath1_drift(conn, serial, r_measured, ref_temperature)

            if sensor_class == 'FAIL':
                self.log(f"      ⚠ SENSOR OUTSIDE CLASSES: {serial}")
                self.stable_signal.emit(serial, sixth, 'FAIL')
            else:
                saved = save_full_result(
                    conn, serial, bath_no,
                    ref_temperature, r_measured,
                    t_sensor, dev_temp, dev_res, sensor_class
                )
                if saved:
                    if bath_no == 1:
                        self._bath1_1_results[serial] = {
                            'resistance': r_measured,
                            'temp_ref':   ref_temperature,
                        }
                    self.stable_signal.emit(serial, sixth, sensor_class)
                    self.log(f"      → DB saved: {serial}  Class {sensor_class}")

        except Exception as e:
            self.log(f"      ⚠ CVD error for {serial}: {e}")

    # ------------------------------------------------------------------
    # BATH 1-2 vs 1-1 DRIFT CHECK
    # ------------------------------------------------------------------
    def _check_bath1_drift(self, conn, serial, r_bath1_2, t_ref_bath1_2):
        """Compare Bath 1-2 vs Bath 1-1 and emit warnings if drift exceeded."""
        bath1_1 = self._bath1_1_results.get(serial)

        if bath1_1 is None:
            db_res  = fetch_bath1_results(conn, [serial])
            bath1_1 = db_res.get(serial)

        if bath1_1 is None:
            self.log(
                f"      ⚠ [{serial}] No Bath 1-1 result -- skipping drift check"
            )
            return

        warnings = compare_bath1_results(
            serial,
            r_bath1_2     = r_bath1_2,
            t_ref_bath1_2 = t_ref_bath1_2,
            r_bath1_1     = bath1_1['resistance'],
            t_ref_bath1_1 = bath1_1.get('temp_ref', self._bath1_1_temp),
            resistance_warn_mk  = config.BATH1_RESISTANCE_WARN_MK,
            temperature_warn_mk = config.BATH1_TEMPERATURE_WARN_MK,
        )

        for warning in warnings:
            self.log(f"      ⚠ DRIFT WARNING: {warning}")
            self.warning_signal.emit(
                f"Bath 1-2 drift warning for {serial}:\n\n{warning}"
            )
