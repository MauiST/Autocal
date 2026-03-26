from collections import deque
from config import STAGE1_THRESHOLD, STAGE2_THRESHOLD


def run_stability_check(readings):
    """
    Stage 1: check spread of last 5 readings.
    Returns (passed, spread)
    """
    spread = max(readings) - min(readings)
    return spread < STAGE1_THRESHOLD, spread


def run_stage2_check(readings, sixth):
    """
    Stage 2: compare average of last 5 readings to 6th reading.
    Returns (passed, delta)
    """
    avg5  = sum(readings) / len(readings)
    delta = abs(avg5 - sixth)
    return delta < STAGE2_THRESHOLD, delta


def create_sensor_state(total_channels, failed_channels=None):
    """
    Initialise sensor tracking state for a batch measurement.
    Returns (sensor_buffers, sensor_stable, final_readings)
    """
    sensor_buffers = [deque(maxlen=5) for _ in range(total_channels)]
    sensor_stable  = [False] * total_channels
    final_readings = [None]  * total_channels

    # Pre-mark failed channels as done
    if failed_channels:
        for chno in failed_channels:
            sensor_stable[chno]  = True
            final_readings[chno] = None

    return sensor_buffers, sensor_stable, final_readings
