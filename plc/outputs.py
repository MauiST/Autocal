import pyads


def plc_all_outputs_off(plc):
    """Turn all outputs OFF. Called on startup, stop and shutdown."""
    for i in range(1, 9):
        try:
            plc.write_by_name(f"MAIN.Output{i}", False, pyads.PLCTYPE_BOOL)
        except Exception:
            pass


def plc_activate_reference(plc, ref_number):
    """
    Activate selected reference output (1-4) --> Output 1-4.
    All other reference outputs turned OFF.

    --- FUTURE: Revolution Pi swap ---
    # rpi.io.Output1.value = (1 == ref_number)
    # rpi.io.Output2.value = (2 == ref_number)
    # etc.
    --- END ---
    """
    for i in range(1, 5):
        try:
            plc.write_by_name(f"MAIN.Output{i}", (i == ref_number), pyads.PLCTYPE_BOOL)
        except Exception:
            pass


def plc_deactivate_reference(plc):
    """Turn all reference outputs OFF."""
    for i in range(1, 5):
        try:
            plc.write_by_name(f"MAIN.Output{i}", False, pyads.PLCTYPE_BOOL)
        except Exception:
            pass


def plc_activate_batch(plc, slot):
    """
    Activate batch output for slot 1-4 --> Output 5-8.
    Slot 1 = Output 5, Slot 2 = Output 6, etc.

    --- FUTURE: actuator control (forward/retract) ---
    # forward_output  = f"MAIN.ActuatorFwd{slot}"
    # retract_output  = f"MAIN.ActuatorRet{slot}"
    # plc.write_by_name(retract_output, False, pyads.PLCTYPE_BOOL)
    # plc.write_by_name(forward_output, True,  pyads.PLCTYPE_BOOL)
    # wait for position confirmation before returning
    --- END ---
    """
    output_no = slot + 4
    try:
        plc.write_by_name(f"MAIN.Output{output_no}", True, pyads.PLCTYPE_BOOL)
        return True
    except Exception:
        return False


def plc_deactivate_batch(plc, slot):
    """
    Deactivate batch output for slot 1-4 --> Output 5-8.

    --- FUTURE: actuator retract ---
    # forward_output  = f"MAIN.ActuatorFwd{slot}"
    # retract_output  = f"MAIN.ActuatorRet{slot}"
    # plc.write_by_name(forward_output, False, pyads.PLCTYPE_BOOL)
    # plc.write_by_name(retract_output, True,  pyads.PLCTYPE_BOOL)
    # wait for position confirmation before returning
    --- END ---
    """
    output_no = slot + 4
    try:
        plc.write_by_name(f"MAIN.Output{output_no}", False, pyads.PLCTYPE_BOOL)
    except Exception:
        pass


def plc_check_confirmed(plc):
    """
    Check PLC SettingsConfirmed variable.
    Returns True when both reference and batch outputs are active.

    --- ACTIVE PLC READ (uncomment when PLC variable is ready) ---
    # try:
    #     return plc.read_by_name("MAIN.SettingsConfirmed", pyads.PLCTYPE_BOOL)
    # except Exception:
    #     return False
    --- END ---
    """
    # Placeholder: simulation always confirmed
    return True
