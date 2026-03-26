"""
instruments/bridge_gpib.py
===========================
Micro-K 70 bridge driver -- GPIB communication via pyvisa.
"""

import time

try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False


class GPIBBridge:
    """
    Micro-K 70 over GPIB using pyvisa.

    Args:
        gpib_address  : int or str -- GPIB address (default 10)
        timeout_s     : int        -- query timeout in seconds
        settle_time   : float      -- settle time after connect
        channel_settle: float      -- relay settle time between channels
        channel_cmds  : dict       -- {channel: scpi_command}
    """

    def __init__(self, gpib_address=10, timeout_s=10,
                 settle_time=3.0, channel_settle=0.5, channel_cmds=None):
        self.gpib_address   = int(gpib_address)
        self.timeout_s      = timeout_s
        self.settle_time    = settle_time
        self.channel_settle = channel_settle
        self.channel_cmds   = channel_cmds or _default_channel_cmds()
        self._resource      = None

    def connect(self):
        """Open GPIB connection. Raises Exception on failure."""
        if not PYVISA_AVAILABLE:
            raise Exception("pyvisa not installed -- cannot use GPIB")
        rm = pyvisa.ResourceManager()
        resource_str = f'GPIB0::{self.gpib_address}::INSTR'
        self._resource = rm.open_resource(resource_str)
        self._resource.timeout = self.timeout_s * 1000
        idn = self._resource.query('*IDN?')
        if not idn:
            self._resource.close()
            raise Exception("No IDN response from bridge")
        time.sleep(self.settle_time)

    def close(self):
        """Close GPIB connection."""
        try:
            if self._resource:
                self._resource.close()
        except Exception:
            pass
        self._resource = None

    def query_channel(self, channel):
        """
        Query a single channel ratio measurement.

        Returns:
            float -- ratio value
            None  -- on failure or invalid channel
        """
        try:
            if channel not in self.channel_cmds:
                return None
            time.sleep(self.channel_settle)
            val = self._resource.query(self.channel_cmds[channel])
            return float(val)
        except Exception:
            return None

    def query_all(self, num_duts):
        """Query all channels. Returns dict {channel: ratio}."""
        return {ch: self.query_channel(ch) for ch in range(1, num_duts + 2)}


def _default_channel_cmds():
    return {
        1: "MEAS:RAT10:REF17? 100,1",
        2: "MEAS:RAT11:REF18? 150,1",
        3: "MEAS:RAT12:REF18? 150,1",
        4: "MEAS:RAT13:REF18? 150,1",
        5: "MEAS:RAT14:REF18? 150,1",
        6: "MEAS:RAT15:REF18? 150,1",
        7: "MEAS:RAT16:REF18? 150,1",
    }
