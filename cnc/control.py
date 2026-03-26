"""
cnc/control.py
==============
CNC controller interface for TwoTrees TTC3018S machines via GRBL.

CNC 1 -- Reference SPRT selector
  X axis: moves between 4 reference sensor positions (one per bath)
  Z axis: lowers/raises pogo pin connector to make contact

CNC 2 -- Batch sensor selector
  X axis: moves between 10 batch positions (2 slots x 5 baths)
  Z axis: lowers/raises pogo pin connector to make contact

Communication: USB serial, GRBL firmware, 115200 baud
Protocol: send G-code lines, wait for 'ok' response per command,
          poll '?' status until 'Idle' before returning from moves.

All positions are in absolute coordinates (G90).
All moves use the configured feed rate.
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
            port      = port,
            baudrate  = baud,
            timeout   = 2,
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
# REFERENCE SPRT POSITIONING  (CNC 1)
# ------------------------------------------------------------------

def cnc1_move_to_reference(cnc, sensor_id):
    """
    Move CNC 1 X axis to the position for the given reference sensor.
    Does NOT connect (lower Z) -- call cnc_z_connect() separately.

    Args:
        cnc       : serial.Serial -- CNC 1 connection
        sensor_id : str           -- '5003', '5004', '5088' or '4999'
    """
    import config
    x_pos = config.CNC1_X_POSITIONS.get(sensor_id)
    if x_pos is None:
        raise ValueError(
            f"No X position configured for reference sensor {sensor_id}"
        )
    feed = config.CNC1_FEED_RATE
    _send_command(cnc, f'G90 G0 X{x_pos:.3f} F{feed}')
    _wait_idle(cnc)


def cnc1_connect(cnc, sensor_id):
    """
    Move CNC 1 to reference sensor position and lower Z to make contact.

    Args:
        cnc       : serial.Serial
        sensor_id : str -- '5003', '5004', '5088' or '4999'
    """
    import config
    cnc1_move_to_reference(cnc, sensor_id)
    _z_connect(cnc, config.CNC1_Z_CONNECT, config.CNC1_FEED_RATE)


def cnc1_disconnect(cnc):
    """Raise CNC 1 Z to clear position (retract reference pogo pins)."""
    import config
    _z_clear(cnc, config.CNC1_Z_CLEAR, config.CNC1_FEED_RATE)


# ------------------------------------------------------------------
# BATCH SENSOR POSITIONING  (CNC 2)
# ------------------------------------------------------------------

def cnc2_move_to_batch(cnc, bath_no, slot):
    """
    Move CNC 2 X axis to the position for the given bath and slot.
    Does NOT connect (lower Z) -- call cnc_z_connect() separately.

    Args:
        cnc     : serial.Serial
        bath_no : int -- bath number (1=Bath1-1, 2, 3, 4, 5=Bath1-2)
        slot    : int -- slot number (1 or 2)
    """
    import config
    x_pos = config.CNC2_X_POSITIONS.get((bath_no, slot))
    if x_pos is None:
        raise ValueError(
            f"No X position configured for bath {bath_no} slot {slot}"
        )
    feed = config.CNC2_FEED_RATE
    _send_command(cnc, f'G90 G0 X{x_pos:.3f} F{feed}')
    _wait_idle(cnc)


def cnc2_connect(cnc, bath_no, slot):
    """
    Move CNC 2 to batch position and lower Z to make contact.

    Args:
        cnc     : serial.Serial
        bath_no : int
        slot    : int
    """
    import config
    cnc2_move_to_batch(cnc, bath_no, slot)
    _z_connect(cnc, config.CNC2_Z_CONNECT, config.CNC2_FEED_RATE)


def cnc2_disconnect(cnc):
    """Raise CNC 2 Z to clear position (retract batch pogo pins)."""
    import config
    _z_clear(cnc, config.CNC2_Z_CLEAR, config.CNC2_FEED_RATE)


# ------------------------------------------------------------------
# MANUAL JOG  (GUI use)
# ------------------------------------------------------------------

def cnc_jog(cnc, direction, feed_rate, step=JOG_STEP):
    """
    Manual jog in one direction by one step.

    Args:
        cnc        : serial.Serial
        direction  : str -- 'X+', 'X-', 'Z+', 'Z-'
        feed_rate  : int -- mm/min
        step       : float -- mm per click (default 1.0)
    """
    axis_map = {
        'X+': f'G91 X{step} F{feed_rate}',
        'X-': f'G91 X-{step} F{feed_rate}',
        'Z+': f'G91 Z{step} F{feed_rate}',
        'Z-': f'G91 Z-{step} F{feed_rate}',
        'H':  '$H',   # GRBL homing cycle
    }
    cmd = axis_map.get(direction)
    if cmd is None:
        raise ValueError(f"Unknown jog direction: {direction}")

    _send_command(cnc, cmd)
    if direction != 'H':
        _send_command(cnc, 'G90')  # back to absolute
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
    Raises Exception on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        cnc.write(b'?\n')
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
