"""The DC motor model, shared by the trials and the electrical measure.

A motor is a straight line: torque = kt * current, back-EMF = ke * shaft speed, and a winding resistance. A drive puts
count motors through a gear (motor turns per turn of the output) with an efficiency. A motor here is plain numbers:
{"ktNmPerA", "ohm", "keVsPerRad"}. Each function keeps one fixed order of arithmetic, so a result is the same to the
last digit wherever it is worked out.
"""
import math


def torque(motor, current, gear=1.0, efficiency=1.0, count=1):
    """Output torque (N m) of count motors, each carrying current (A), through gear and efficiency."""
    return count * gear * motor["ktNmPerA"] * current * efficiency


def current_for(motor, torque, gear=1.0, efficiency=1.0, count=1):
    """Current (A) in each of count motors that gives an output torque (N m) through gear and efficiency."""
    return torque / (motor["ktNmPerA"] * gear * efficiency * count)


def back_emf(motor, speed, radius, gear):
    """Back-EMF (V) of a motor whose output moves at speed (m/s) at radius (m), through gear. With radius 1, speed is
    the output's turning speed in rad/s."""
    return motor["keVsPerRad"] * speed / radius * gear


def winding_current(motor, volts, emf):
    """The current (A) that volts drives through the winding against emf."""
    return (volts - emf) / motor["ohm"]


def voltage_for(motor, current, emf):
    """The motor voltage (V) that drives current (A) through the winding against emf."""
    return current * motor["ohm"] + emf


def supply_limited(current, emf, ohm, bus, limit):
    """The largest current whose electrical input emf * i + i * i * ohm stays within bus * limit."""
    return min(current, (-emf + math.sqrt(emf * emf + 4 * ohm * bus * limit)) / (2 * ohm))


def supply_current(motor, current, emf, bus, count=1):
    """The current (A) count motors draw from a bus at bus volts, each carrying current against emf."""
    return count * current * (emf + current * motor["ohm"]) / bus
