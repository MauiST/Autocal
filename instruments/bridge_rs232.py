"""
instruments/bridge_rs232.py
============================
Micro-K 70 bridge driver -- RS-232 communication via pyserial.

The Micro-K 70 uses the same SCPI command set over RS-232 as over GPIB.
Commands are sent as ASCII lines terminated with CR+LF.
Responses are read until newline.
"""

import time

try:
    import serial
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False


class RS232Bridge:
    """
    Micro-K 70 over RS-232 using pyserial.

    Args:
        port          : str   -- serial port e.g. '/dev/ttyS0' or 'COM1'
        baud          : int   -- baud rate (default 9600)
        bytesize      : int   -- data bits (default 8)
        parity        : str   -- 'N', 'E', 'O' (default 'N')
        stopbits      : int   -- 1 or 2 (default 1)
        timeout_s     : int   -- read timeout in seconds (default 10)
        settle_time   : float -- settle time after connect (default 3)
        channel_settle: float -- relay settle between channels (default 0.5)
        channel_cmds  : dict  -- {channel: scpi_command}
    """

    def __init__(self, port='/dev/ttyS0', baud=9600,
                 bytesize=8, parity='N', stopbits=1,
                 timeout_s=10, settle_time=3.0,
                 channel_settle=0.5, channel_cmds=None):
        self.port           = port
        self.baud           = baud
        self.bytesize       = bytesize
        self.parity         = parity
        self.stopbits       = stopbits
        self.timeout_s      = timeout_s
        self.settle_time    = settle_time
        self.channel_settle = channel_settle
        self.channel_cmds   = channel_cmds or _default_channel_cmds()
        self._serial        = None

    def connect(self):
        """Open RS-232 connection. Raises Exception on failure."""
        if not PYSERIAL_AVAILABLE:
            raise Exception("pyserial not installed -- cannot use RS-232")

        import serial as _serial

        parity_map = {
            'N': _serial.PARITY_NONE,
            'E': _serial.PARITY_EVEN,
            'O': _serial.PARITY_ODD,
        }
        stopbits_map = {
            1: _serial.STOPBITS_ONE,
            2: _serial.STOPBITS_TWO,
        }

        self._serial = _serial.Serial(
            port     = self.port,
            baudrate = self.baud,
            bytesize = self.bytesize,
            parity   = parity_map.get(self.parity, _serial.PARITY_NONE),
            stopbits = stopbits_map.get(self.stopbits, _serial.STOPBITS_ONE),
            timeout  = self.timeout_s,
        )

        time.sleep(self.settle_time)

        # Verify bridge is responding with IDN query
        idn = self._query_raw('*IDN?')
        if not idn:
            self._serial.close()
            raise Exception(
                f"No IDN response from bridge on {self.port} "
                f"at {self.baud} baud"
            )

    def close(self):
        """Close RS-232 connection."""
        try:
            if self._serial and self._serial.is_open:
                self._serial.close()
        except Exception:
            pass
        self._serial = None

    def query_channel(self, channel):
        """
        Query a single channel ratio measurement.

        Returns:
            float -- ratio value
            None  -- on failure
        """
        if channel not in self.channel_cmds:
            raise ValueError(f"Invalid channel {channel}")
        time.sleep(self.channel_settle)
        try:
            response = self._query_raw(self.channel_cmds[channel])
            return float(response)
        except Exception:
            return None

    def query_all(self, num_duts):
        """Query all channels. Returns dict {channel: ratio}."""
        return {ch: self.query_channel(ch) for ch in range(1, num_duts + 2)}

    def _query_raw(self, cmd):
        """
        Send a SCPI command and read the response.
        Commands are terminated with CR+LF per RS-232 convention.

        Returns:
            str -- response string stripped of whitespace
            None -- on failure
        """
        if not self._serial or not self._serial.is_open:
            return None
        try:
            self._serial.reset_input_buffer()
            self._serial.write((cmd.strip() + '\r\n').encode('ascii'))
            response = self._serial.readline().decode('ascii', errors='ignore')
            return response.strip()
        except Exception:
            return None


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
