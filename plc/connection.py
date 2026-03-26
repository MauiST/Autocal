import pyads
from config import PLC_IP, PLC_AMS_ID

def plc_connect():
    try:
        plc = pyads.Connection(PLC_AMS_ID, pyads.PORT_TC3PLC1, PLC_IP)
        plc.open()
        plc.read_state()
        return plc
    except Exception:
        return None

def plc_close(plc):
    try:
        plc.close()
    except Exception:
        pass
    