"""Scalar actuators: a belt, roller or wheel surface with one speed, either imposed or driven by a motor model.

A drive's state is its surface speed in m/s. Contact friction on the piece along the surface is fed back as a load.
Motor model: the DC motor line of frc_design_kernel.motor (torque = kt * current, back-EMF = ke * speed, winding
resistance), through a gear with an efficiency, with a winding (stator) current limit and an optional supply current
limit. Three ways to command it:

    voltage   the bus voltage is applied. busV None is power off (coasting); busV 0 is shorted windings (a brake).
    speed     a speed loop asks for full current when the surface is a band below the setpoint, none at the setpoint.
    hold      a position hold: a stiff, damped spring on the shaft angle that saturates at the current limit.
"""
import math

from .. import motor as motors


def start(drive):
    still = drive.get("speedMps", 0.0) if drive["kind"] == "imposed" and not drive.get("rampS") else 0.0
    return {"u": float(drive.get("startMps", still)), "angle": 0.0, "amps": 0.0, "supply": 0.0}


def equivalent_mass(drive):
    """The mass the drive presents at its surface."""
    radius = drive["radiusM"]
    return drive["movingKg"] if "movingKg" in drive else drive["inertiaKgM2"] / radius ** 2


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def step(drive, state, load, t, dt):
    """Advance one drive by dt. load is the force (N) the piece's friction takes from the surface, along its run.

    piecesOnDrive says how many pieces load the drive at once, each the same way as the one that is solved.
    """
    if drive["kind"] == "imposed":
        ramp = drive.get("rampS", 0.0)
        state["u"] = drive["speedMps"] * (min(1.0, t / ramp) if ramp > 0 else 1.0)
        return
    motor, radius, gear = drive["motor"], drive["radiusM"], drive["gear"]
    count, efficiency, stator = drive.get("count", 1), drive.get("efficiency", 1.0), drive["statorLimitA"]
    mass, bus, control = equivalent_mass(drive), drive.get("busV"), drive["control"]
    u = state["u"]
    emf = motors.back_emf(motor, u, radius, gear)
    if control["mode"] == "hold":
        state["angle"] += u / radius * dt
        most = motor["ktNmPerA"] * stator * gear * efficiency * count
        stiffness = most / control["fullTorqueAtRad"]
        torque = clamp(-stiffness * state["angle"] - 2 * math.sqrt(stiffness * mass * radius ** 2) * u / radius, -most, most)
        current = motors.current_for(motor, abs(torque), gear, efficiency, count)
    else:
        if bus is None:
            current = 0.0
        elif control["mode"] == "voltage":
            current = clamp(motors.winding_current(motor, bus, emf), -stator, stator)
        else:
            setpoint = control["setpointMps"]
            wanted = stator * clamp((setpoint - u) / (control.get("band", 0.02) * setpoint), 0.0, 1.0)
            current = max(0.0, min(wanted, stator, motors.winding_current(motor, bus, emf)))
        if bus and current > 0 and drive.get("supplyLimitA") is not None:
            current = motors.supply_limited(current, emf, motor["ohm"], bus, drive["supplyLimitA"])
        torque = motors.torque(motor, current, gear, efficiency, count)
    state["amps"] = current
    state["supply"] = motors.supply_current(motor, current, emf, bus, count) if bus else 0.0
    u += ((torque - drive.get("dragNm", 0.0)) / radius - load * drive.get("piecesOnDrive", 1)) / mass * dt
    state["u"] = max(0.0, u) if drive.get("oneWay") else u
