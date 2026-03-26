"""
instruments/bridge.py
======================
Micro-K 70 bridge factory.

Selects the correct driver (GPIB or RS-232) based on config setting
'bridge_comm'. Returns a driver object with a consistent interface:

    bridge.connect()
    bridge.close()
    bridge.query_channel(channel)  -> float or None
    bridge.query_all(num_duts)     -> dict {channel: ratio}

All existing code (worker.py etc.) continues to call:
    bridge_connect()       -> bridge object or None
    bridge_close(bridge)
    bridge_query_channel(bridge, channel)

These wrapper functions are kept for backward compatibility.
"""

import config


# ------------------------------------------------------------------
# Public factory functions  (backward-compatible API)
# ------------------------------------------------------------------

def bridge_connect():
    """
    Connect to Micro-K 70 using the configured communication method.

    Returns:
        bridge driver object if connected
        None if connection failed
    """
    comm = config.BRIDGE_COMM.upper()

    try:
        if comm == 'RS232':
            from instruments.bridge_rs232 import RS232Bridge
            bridge = RS232Bridge(
                port          = config.BRIDGE_RS232_PORT,
                baud          = config.BRIDGE_RS232_BAUD,
                bytesize      = config.BRIDGE_RS232_BYTESIZE,
                parity        = config.BRIDGE_RS232_PARITY,
                stopbits      = config.BRIDGE_RS232_STOPBITS,
                timeout_s     = config.BRIDGE_TIMEOUT,
                settle_time   = config.BRIDGE_SETTLE_TIME,
                channel_settle= config.BRIDGE_CHANNEL_SETTLE,
            )
        else:
            # Default: GPIB
            from instruments.bridge_gpib import GPIBBridge
            bridge = GPIBBridge(
                gpib_address  = config.BRIDGE_GPIB_ADDR,
                timeout_s     = config.BRIDGE_TIMEOUT,
                settle_time   = config.BRIDGE_SETTLE_TIME,
                channel_settle= config.BRIDGE_CHANNEL_SETTLE,
            )

        bridge.connect()
        return bridge

    except Exception as e:
        print(f"[bridge] Connection failed ({comm}): {e}")
        return None


def bridge_close(bridge):
    """Close bridge connection."""
    if bridge:
        try:
            bridge.close()
        except Exception:
            pass


def bridge_query_channel(bridge, channel):
    """
    Query a single channel ratio measurement.

    Args:
        bridge  : bridge driver object
        channel : int -- channel 1-7

    Returns:
        float -- ratio
        None  -- on failure
    """
    if bridge is None:
        return None
    return bridge.query_channel(channel)


def bridge_query_all(bridge, num_duts):
    """
    Query all active channels.

    Args:
        bridge   : bridge driver object
        num_duts : int -- number of DUT sensors

    Returns:
        dict {channel: ratio}
    """
    if bridge is None:
        return {}
    return bridge.query_all(num_duts)


def bridge_get_comm_info(bridge):
    """
    Return a human-readable string describing the active connection.
    Used for status labels in the GUI.
    """
    if bridge is None:
        return "Not connected"
    if hasattr(bridge, 'gpib_address'):
        return f"GPIB  addr={bridge.gpib_address}"
    if hasattr(bridge, 'port'):
        return f"RS-232  {bridge.port}  {bridge.baud} baud"
    return "Connected"
