"""
Callendar-Van Dusen (CVD) Calculations
=======================================
Calculates temperature from resistance for batch PT100 sensors
using the standard IEC 60751 Callendar-Van Dusen equation.

CVD equation:
  T > 0°C :  R(T) = R0 * (1 + A*T + B*T²)
  T < 0°C :  R(T) = R0 * (1 + A*T + B*T² + C*(T-100)*T³)

Where R0 = 100Ω (nominal for PT100, IEC 60751)
  A =  3.9083e-3
  B = -5.775e-7
  C = -4.183e-12  (only below 0°C)

EN 60751 tolerance classes:
  Class AA : |ΔT| ≤ (0.1  + 0.0017 * |T|)
  Class A  : |ΔT| ≤ (0.15 + 0.002  * |T|)
  Class B  : |ΔT| ≤ (0.3  + 0.005  * |T|)
  Class C  : |ΔT| ≤ (0.6  + 0.01   * |T|)
"""

import math

# Standard IEC 60751 CVD coefficients
CVD_A =  3.9083e-3
CVD_B = -5.775e-7
CVD_C = -4.183e-12
CVD_R0 = 100.0  # nominal PT100 resistance at 0°C


def cvd_resistance(temperature):
    """
    Calculate expected resistance at a given temperature using CVD equation.
    Used to compute resistance deviation.

    Args:
        temperature : float -- temperature in °C

    Returns:
        float -- expected resistance in ohms
    """
    t = temperature
    if t >= 0:
        return CVD_R0 * (1 + CVD_A * t + CVD_B * t**2)
    else:
        return CVD_R0 * (1 + CVD_A * t + CVD_B * t**2 + CVD_C * (t - 100) * t**3)


def cvd_temperature(resistance):
    """
    Calculate temperature from measured resistance using CVD equation.
    Uses iterative Newton-Raphson solve since CVD is not easily invertible.

    Args:
        resistance : float -- measured resistance in ohms

    Returns:
        float -- temperature in °C
    """
    # Initial estimate using simplified linear approximation
    t = (resistance / CVD_R0 - 1) / CVD_A

    # Newton-Raphson iteration
    for _ in range(50):
        r_calc = cvd_resistance(t)
        r_diff = resistance - r_calc

        # Derivative of R with respect to T
        if t >= 0:
            dr_dt = CVD_R0 * (CVD_A + 2 * CVD_B * t)
        else:
            dr_dt = CVD_R0 * (CVD_A + 2 * CVD_B * t +
                               CVD_C * (4 * t**3 - 300 * t**2))

        if abs(dr_dt) < 1e-15:
            break

        t_new = t + r_diff / dr_dt
        if abs(t_new - t) < 1e-8:
            t = t_new
            break
        t = t_new

    return t


def determine_sensor_class(t_sensor, t_ref):
    """
    Determine EN 60751 tolerance class from sensor and reference temperatures.

    Args:
        t_sensor : float -- CVD calculated temperature in °C
        t_ref    : float -- ITS-90 reference temperature in °C

    Returns:
        str -- 'AA', 'A', 'B', 'C', or 'FAIL'
    """
    t   = abs(t_ref)
    dev = abs(t_sensor - t_ref)

    if dev <= (0.1  + 0.0017 * t): return 'AA'
    if dev <= (0.15 + 0.002  * t): return 'A'
    if dev <= (0.3  + 0.005  * t): return 'B'
    return 'FAIL'  # Class C and beyond treated as FAIL for now


def calculate_cvd(ratio, r_standard_100, t_ref):
    """
    Full CVD calculation chain for a batch PT100 sensor.

    Args:
        ratio          : float -- ratio from bridge instrument
        r_standard_100 : float -- calibrated 100Ω standard resistor value
        t_ref          : float -- ITS-90 bath temperature from reference sensor

    Returns:
        r_measured     : float -- actual resistance in ohms
        t_sensor       : float -- CVD calculated temperature in °C
        dev_temp       : float -- temperature deviation from reference (°C)
        dev_res        : float -- resistance deviation from expected (Ω)
        sensor_class   : str   -- EN 60751 class (AA/A/B/C/FAIL)
    """
    # Step 1: convert ratio to resistance
    r_measured = ratio * r_standard_100

    # Step 2: calculate temperature from resistance
    t_sensor = cvd_temperature(r_measured)

    # Step 3: calculate deviations
    dev_temp = t_sensor - t_ref
    dev_res  = r_measured - cvd_resistance(t_ref)

    # Step 4: determine EN 60751 class
    sensor_class = determine_sensor_class(t_sensor, t_ref)

    return r_measured, t_sensor, dev_temp, dev_res, sensor_class
