"""
cnc/control.py
==============
CNC controller interface for a single TwoTrees TTC3018S (or compatible GRBL
machine) used as an automated pogo-pin connector.

Axes:
  X axis -- selects which reference SPRT is under the connector
             (4 positions, one per bath: 5003, 5004, 5088, 4999)
  Y axis -- selects which batch-sensor slot is under the connector
             (14 positions: 4 slots for Bath 1-1, 4 for Bath 1-2,
              2 each for Baths 2/3/4)
  Z axis -- lowers / raises the pogo-pin head to make / break contact

Communication: USB serial, GRBL firmware, 115200 baud
Protocol: send G-code lines, wait for 'ok' response per command,
          poll '?' status until 'Idle' before returning from moves.

All positions are in absolute coordinates (G90).
All moves use the configured feed rate from config.py.
"""

import time
import serial

# Timeout waiting for move to complete (seconds)
MOVE_TIMEOUT   = 30
# Timeout waiting for 'ok' response (seconds)
OK_TIMEOUT     = 10
# Poll interval for status check (seconds)
POLL_INTERVAL  = 0.1
# Jog step size for manual jog (mm)
JOG_STEP       = 1.0


# ------------------------------------------------------------------
# CONNECTION
# ------------------------------------------------------------------

def cnc_connect(port, baud=115200):
    """
    Open serial connection to a GRBL CNC controller.
    Sends soft-reset and waits for GRBL startup message.

    Args:
        port : str  -- COM port e.g. 'COM3' or '/dev/ttyUSB0'
        baud : int  -- baud rate (default 115200)

    Returns:
        serial.Serial object

    Raises:
        Exception if connection fails
    """
    try:
        cnc = serial.Serial(
            port          = port,
            baudrate      = baud,
            timeout       = 2,
            write_timeout = 2,
        )
        time.sleep(2)          # Wait for GRBL to initialise
        cnc.flushInput()
        cnc.flushOutput()

        # Soft reset
        cnc.write(b'\x18')
        time.sleep(1)
        cnc.flushInput()

        # Verify GRBL is responding
        cnc.write(b'\n')
        response = cnc.readline().decode('utf-8', errors='ignore').strip()
        if 'Grbl' in response or 'ok' in response or response == '':
            # Set absolute positioning mode
            _send_command(cnc, 'G90')
            return cnc

        raise Exception(
            f"Unexpected GRBL response on {port}: '{response}'"
        )
    except serial.SerialException as e:
        raise Exception(f"Cannot open {port}: {e}")


def cnc_close(cnc):
    """Safely close CNC serial connection."""
    if cnc and cnc.is_open:
        try:
            # Raise Z to clear before closing
            _send_command(cnc, 'G91 Z5 F200')   # relative move up 5mm
            _send_command(cnc, 'G90')             # back to absolute
            _wait_idle(cnc)
        except Exception:
            pass
        cnc.close()


# ------------------------------------------------------------------
# REFERENCE SPRT POSITIONING  (X axis)
# ------------------------------------------------------------------

def cnc_move_reference(cnc, bath_no):
    """
    Move X axis to the reference position for the given bath.
    Does NOT connect (lower Z) -- call cnc_connect_batch() to lower Z.

    Args:
        cnc     : serial.Serial
        bath_no : int -- 1=Bath1-1, 2=Bath2, 3=Bath3, 4=Bath4, 5=Bath1-2
    """
    import config
    x_pos = config.CNC_X_POSITIONS.get(bath_no)
    if x_pos is None:
        raise ValueError(
            f"No X position configured for bath_no {bath_no}"
        )
    _send_command(cnc, f'G90 G0 X{x_pos:.3f} F{config.CNC_FEED_RATE}')
    _wait_idle(cnc)


def cnc_connect_reference(cnc, bath_no):
    """
    Move X to the reference position for the given bath.
    Z is NOT lowered here -- call cnc_connect_batch() to lower Z
    after positioning both X and Y.

    Args:
        cnc     : serial.Serial
        bath_no : int -- 1=Bath1-1, 2=Bath2, 3=Bath3, 4=Bath4, 5=Bath1-2
    """
    cnc_move_reference(cnc, bath_no)


# ------------------------------------------------------------------
# BATCH SENSOR POSITIONING  (Y axis)
# ------------------------------------------------------------------

def cnc_move_batch(cnc, bath_no, slot):
    """
    Move Y axis to the position for the given bath and slot.
    Does NOT connect (lower Z).

    Args:
        cnc     : serial.Serial
        bath_no : int -- bath number (1=Bath1-1, 2, 3, 4, 5=Bath1-2)
        slot    : int -- slot number (1 or 2, up to 4 for Bath 1)
    """
    import config
    y_pos = config.CNC_Y_POSITIONS.get((bath_no, slot))
    if y_pos is None:
        raise ValueError(
            f"No Y position configured for bath {bath_no} slot {slot}"
        )
    _send_command(cnc, f'G90 G0 Y{y_pos:.3f} F{config.CNC_FEED_RATE}')
    _wait_idle(cnc)


def cnc_connect_batch(cnc, bath_no, slot):
    """
    Move Y to the batch sensor position and lower Z to make contact.
    Call cnc_connect_reference() first to position X.

    Args:
        cnc     : serial.Serial
        bath_no : int
        slot    : int
    """
    import config
    cnc_move_batch(cnc, bath_no, slot)
    _z_connect(cnc, config.CNC_Z_CONNECT, config.CNC_FEED_RATE)


def cnc_disconnect(cnc):
    """Raise Z to clear position (retract pogo pins)."""
    import config
    _z_clear(cnc, config.CNC_Z_CLEAR, config.CNC_FEED_RATE)


# ------------------------------------------------------------------
# MANUAL JOG  (GUI use)
# ------------------------------------------------------------------

def cnc_jog(cnc, direction, feed_rate, step=JOG_STEP):
    """
    Manual jog in one direction by one step.

    Args:
        cnc        : serial.Serial
        direction  : str -- 'X+', 'X-', 'Y+', 'Y-', 'Z+', 'Z-'
        feed_rate  : int -- mm/min
        step       : float -- mm per click (default 1.0)
    """
    # Use $J= (GRBL 1.1 dedicated jog command) for all axis moves.
    # $J= uses a separate jog buffer, does not affect modal state (no G90
    # needed after), and behaves identically to how Candle jogs.
    axis_map = {
        'X+': f'$J=G91 X{step} F{feed_rate}',
        'X-': f'$J=G91 X-{step} F{feed_rate}',
        'Y+': f'$J=G91 Y{step} F{feed_rate}',
        'Y-': f'$J=G91 Y-{step} F{feed_rate}',
        'Z+': f'$J=G91 Z{step} F{feed_rate}',
        'Z-': f'$J=G91 Z-{step} F{feed_rate}',
        'H':  '$H',   # GRBL homing cycle
    }
    cmd = axis_map.get(direction)
    if cmd is None:
        raise ValueError(f"Unknown jog direction: {direction}")

    _send_command(cnc, cmd)
    _wait_idle(cnc)


def cnc_z_move(cnc, z_position, feed_rate):
    """
    Move Z to absolute position.
    Used by GUI Connect Pins / Retract Pins buttons.
    """
    _send_command(cnc, f'G90 G0 Z{z_position:.3f} F{feed_rate}')
    _wait_idle(cnc)


def cnc_home(cnc):
    """Run GRBL homing cycle ($H)."""
    _send_command(cnc, '$H')
    _wait_idle(cnc, timeout=60)   # homing can take longer


def cnc_park(cnc):
    """
    Raise Z to clear position then move X and Y to 0.
    Called after each bath to park the machine between measurement steps.
    """
    import config
    _z_clear(cnc, config.CNC_Z_CLEAR, config.CNC_FEED_RATE)
    _send_command(cnc, f'G90 G0 X0.000 Y0.000 F{config.CNC_FEED_RATE}')
    _wait_idle(cnc)


def cnc_get_position(cnc):
    """
    Query current machine position.
    Returns dict {'x': float, 'y': float, 'z': float} or None.
    """
    try:
        cnc.write(b'?\n')
        response = cnc.readline().decode('utf-8', errors='ignore').strip()
        # GRBL status: <Idle|MPos:0.000,0.000,0.000|...>
        if 'MPos:' in response:
            mpos = response.split('MPos:')[1].split('|')[0]
            x, y, z = [float(v) for v in mpos.split(',')]
            return {'x': x, 'y': y, 'z': z}
    except Exception:
        pass
    return None


# ------------------------------------------------------------------
# INTERNAL HELPERS
# ------------------------------------------------------------------

def _send_command(cnc, cmd, wait_ok=True):
    """
    Send a single G-code command and optionally wait for 'ok'.

    Args:
        cnc     : serial.Serial
        cmd     : str  -- G-code command (without newline)
        wait_ok : bool -- if True, read response until 'ok' or 'error'

    Raises:
        Exception on GRBL error response or timeout
    """
    line = (cmd.strip() + '\n').encode('utf-8')
    cnc.write(line)

    if not wait_ok:
        return

    deadline = time.time() + OK_TIMEOUT
    while time.time() < deadline:
        response = cnc.readline().decode('utf-8', errors='ignore').strip()
        if response == 'ok':
            return
        if response.startswith('error'):
            raise Exception(f"GRBL error for '{cmd}': {response}")
        if response.startswith('ALARM'):
            raise Exception(f"GRBL ALARM for '{cmd}': {response}")
        # Ignore status reports and empty lines
    raise Exception(f"Timeout waiting for 'ok' after command: '{cmd}'")


def _wait_idle(cnc, timeout=MOVE_TIMEOUT):
    """
    Poll GRBL status until machine reports 'Idle'.
    The initial 0.3 s delay gives GRBL time to transition from Idle
    to Run before we start polling -- without it, a fast poll can catch
    the brief Idle window that exists right after a command is accepted
    but before motion actually starts, causing _wait_idle to return early.
    Raises Exception on timeout.
    """
    time.sleep(0.3)            # let GRBL transition Idle → Run before polling
    cnc.reset_input_buffer()   # discard any stale ok/status bytes in the buffer
    deadline = time.time() + timeout
    while time.time() < deadline:
        cnc.write(b'?')        # real-time character only -- no \n, no extra G-code line
        time.sleep(POLL_INTERVAL)
        response = cnc.readline().decode('utf-8', errors='ignore').strip()
        if 'Idle' in response:
            return
        if 'ALARM' in response:
            raise Exception(f"GRBL ALARM during move: {response}")
    raise Exception(f"CNC move timeout after {timeout}s -- check machine")


def _z_connect(cnc, z_depth, feed_rate):
    """Lower Z to contact position."""
    _send_command(cnc, f'G90 G0 Z{z_depth:.3f} F{feed_rate}')
    _wait_idle(cnc)


def _z_clear(cnc, z_clear, feed_rate):
    """Raise Z to clear position."""
    _send_command(cnc, f'G90 G0 Z{z_clear:.3f} F{feed_rate}')
    _wait_idle(cnc)
