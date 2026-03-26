"""
ITS-90 Reference Function Calculations
=======================================
Calculation logic taken directly from SPRTAnalyzerV5 (verified working GUI).

ALL coefficients and standard resistor values are loaded exclusively from
sprt_config.json. The DB is NOT used for these values.

If sprt_config.json is missing or a sensor is not found in it, a clear
warning is raised and the calculation is aborted -- no silent fallbacks.
"""

import os
import json
import math

# ---------------------------------------------------------------------------
# ITS-90 Reference Functions  (ported 1:1 from verified VB Standards module)
# ---------------------------------------------------------------------------

# Below 0°C: A series for Wr90 forward function (13 terms)
_A = [
    -2.13534729,  3.18324720, -1.80143597,  0.71727204,
     0.50344027, -0.61899395, -0.05332322,  0.28021362,
     0.10715224, -0.29302865,  0.04459872,  0.11868632,
    -0.05248134,
]

# Above 0°C: C series for Wr90 forward function (10 terms)
_C = [
     2.78157254,  1.64650916, -0.13714390, -0.00649767,
    -0.00234444,  0.00511868,  0.00187982, -0.00204472,
    -0.00046122,  0.00045724,
]

# Below 0°C: B series for T90 inverse function (16 terms, index 0-15)
# NOTE: B[4]=0.142648498 and B[14]/B[15] differ from naive Python version
_B = [
     0.183324722,  0.240975303,  0.209108771,  0.190439972,
     0.142648498,  0.077993465,  0.012475611, -0.032267127,
    -0.075291522, -0.056470670,  0.076201285,  0.123893204,
    -0.029201193, -0.091173542,  0.001317696,  0.026025526,
]

# Above 0°C: D series for T90 inverse function (10 terms)
_D = [
    439.932854, 472.418020,  37.684494,   7.472018,
      2.920828,   0.005184,  -0.963864,  -0.188732,
      0.191203,   0.049025,
]


def _Wr90(t_kelvin):
    """
    Forward function: given T in Kelvin, returns Wr = R(T)/R(TPW).
    Ported 1:1 from VB Wr90() function.
    """
    t = t_kelvin
    if t < 273.16:
        Aa = _A[0]
        pot_base = (math.log(t / 273.16) + 1.5) / 1.5
        P = pot_base
        for i in range(1, 13):
            if i > 1:
                P = P * pot_base
            Aa += _A[i] * P
        return math.exp(Aa)
    else:
        Ca = _C[0]
        pot_base = (t - 754.15) / 481.0
        P = pot_base
        for i in range(1, 10):
            if i > 1:
                P = P * pot_base
            Ca += _C[i] * P
        return Ca


def _T90accurate(Wr):
    """
    Iterative solver: given Wr, returns accurate T in Kelvin.
    Ported 1:1 from VB T90accurate() -- iterates to 1e-11 convergence.
    """
    Ktemp = 273.16
    Afvigelse = 1.0
    while abs(Afvigelse) >= 1e-11:
        Afvigelse = Wr - _Wr90(Ktemp)
        Tberegnet = Ktemp
        Ktemp = Ktemp + Ktemp * Afvigelse / _Wr90(Ktemp)
    return Tberegnet

# ---------------------------------------------------------------------------
# Config file path  (sits next to the project root -- easy to edit)
# ---------------------------------------------------------------------------
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sprt_config.json')


def _load_sprt_config():
    """
    Load sprt_config.json. Raises clear errors if missing or invalid.
    The app will not proceed without this file.
    """
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f"\n[its90] CRITICAL: sprt_config.json not found at:\n"
            f"  {_CONFIG_PATH}\n"
            f"  This file is required for all ITS-90 calculations.\n"
            f"  Create it from the template and add your SPRT coefficients."
        )
    try:
        with open(_CONFIG_PATH, 'r') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        raise ValueError(
            f"\n[its90] CRITICAL: sprt_config.json contains invalid JSON:\n  {e}"
        )


# ---------------------------------------------------------------------------
# Public: coefficient and resistor loaders
# ---------------------------------------------------------------------------

def get_ref_coefficients(conn, ref_sensor_name):
    """
    Load SPRT calibration coefficients from sprt_config.json only.
    Raises KeyError if the sensor is not found in the config file.

    conn is accepted for API compatibility but is not used.
    """
    config = _load_sprt_config()
    if ref_sensor_name not in config or not isinstance(config[ref_sensor_name], dict):
        raise KeyError(
            f"\n[its90] CRITICAL: Sensor '{ref_sensor_name}' not found in sprt_config.json.\n"
            f"  Add the calibration coefficients for this sensor to the config file."
        )
    entry = config[ref_sensor_name]
    print(f"[its90] Coefficients for {ref_sensor_name} loaded from sprt_config.json")
    return {
        'roits':   float(entry['roits']),
        'a_sub':   float(entry['a_sub']),
        'b_sub':   float(entry['b_sub']),
        'a_above': float(entry['a_above']),
        'c_sub':   float(entry.get('c_sub',   0.0) or 0.0),
        'd_sub':   float(entry.get('d_sub',   0.0) or 0.0),
        'b_above': float(entry.get('b_above', 0.0) or 0.0),
        'c_above': float(entry.get('c_above', 0.0) or 0.0),
        'd_above': float(entry.get('d_above', 0.0) or 0.0),
    }


def get_standard_resistor(conn, nominal_value):
    """
    Load calibrated standard resistor value from sprt_config.json only.
    Raises KeyError if the value is not found in the config file.

    conn is accepted for API compatibility but is not used.

    Args:
        conn          : not used
        nominal_value : str or int/float -- e.g. '25' or '100'

    Returns:
        float -- calibrated resistance value
    """
    key = str(nominal_value)
    config = _load_sprt_config()
    resistors = config.get('standard_resistors', {})
    if key not in resistors:
        raise KeyError(
            f"\n[its90] CRITICAL: Standard resistor '{key}Ω' not found in sprt_config.json.\n"
            f"  Add it under the 'standard_resistors' section with its calibrated value."
        )
    val = float(resistors[key])
    print(f"[its90] Standard resistor {key}Ω loaded from sprt_config.json: {val}")
    return val


# ---------------------------------------------------------------------------
# Core ITS-90 calculation  (identical logic to SPRTAnalyzerV5 -- verified)
# ---------------------------------------------------------------------------

def ratio_to_resistance(ratio, r_standard_calibrated):
    return ratio * r_standard_calibrated


def calculate_its90(ratio, coefficients, r_standard_calibrated):
    """
    Full ITS-90 temperature calculation chain.
    Uses T90accurate iterative solver -- ported 1:1 from verified VB code.

    Args:
        ratio                 : float -- ratio from bridge
        coefficients          : dict  -- from get_ref_coefficients()
        r_standard_calibrated : float -- calibrated 25Ω standard resistor

    Returns:
        (t_celsius, w, wr, dw)
    """
    if coefficients is None:
        raise ValueError("No coefficients provided for ITS-90 calculation")

    # Step 1: resistance from ratio
    r_meas = ratio * r_standard_calibrated

    # Step 2: W ratio  (R_measured / R_at_triple_point_of_water)
    roits = coefficients['roits']
    w     = r_meas / roits
    y     = w - 1.0

    # Step 3: deviation correction (sensor-specific coefficients)
    a_sub   = coefficients['a_sub']
    b_sub   = coefficients['b_sub']
    a_above = coefficients['a_above']

    if w < 1.0:
        log_w = math.log(w) if w > 0 else 0.0
        dw = (a_sub * y) + (b_sub * y * log_w)
    else:
        dw = a_above * y

    wr = w - dw

    # Step 4: iterative temperature solve via Wr90 forward function
    # Matches VB T90accurate() -- converges to 1e-11
    t_kelvin  = _T90accurate(wr)
    t_celsius = t_kelvin - 273.15

    return t_celsius, w, wr, dw


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_ref_for_bath(ref_name, bath_no, t_ref):
    from config import BATH_TEMP_RANGE, BATH_REF_RECOMMENDED, BATH_LABEL

    warnings = []

    t_min, t_max = BATH_TEMP_RANGE.get(bath_no, (-999, 999))
    if not (t_min <= t_ref <= t_max):
        warnings.append(
            f"Bath temperature {t_ref:.3f}°C is outside expected range "
            f"({t_min}°C to {t_max}°C) for {BATH_LABEL[bath_no]}"
        )

    recommended = BATH_REF_RECOMMENDED.get(bath_no)
    if recommended and ref_name != recommended:
        warnings.append(
            f"Reference {ref_name} is not recommended for "
            f"{BATH_LABEL[bath_no]} -- expected {recommended}"
        )

    return warnings
