"""The electrical load of a motion: each commanded drive's torque, current and motor voltage, and the bus voltage.

A motion's load is every drive its commands move, plus the drives it lists under alsoRunning. For each commanded
drive, over the motion:

- the load at its joint (N m about a rotation, N along a slide): gravity on the moved groups (the joint's group and
  everything it carries), the moved groups' inertia times the acceleration of the speed profile below, and the
  motion's stated extraLoad;
- the current per motor from the motor model (frc_design_kernel.motor) through the gear, the efficiency and the
  count, clamped at the drive's current limit, with a flag when clamped;
- the motor voltage the motion needs at its peak speed: current times winding resistance plus back-EMF.

Then the bus: the battery's open-circuit voltage less the sum of the drives' currents times its resistance.

**The speed profile is a triangle.** Each commanded joint speeds up evenly over the first half of durationS and
slows evenly over the second half, from rest to rest. Its peak speed is twice the average (2 * change / durationS,
at mid-stroke) and its acceleration 4 * change / durationS ** 2. It is the gentlest profile that makes the stroke in
the time. Positions come from the motion's placements at stroke fractions, so the geometry is the same whatever the
timing.

**Ranges.** Every figure is a value with a [low, high] range. Weights are taken all at their low ends or all at their
high ends at once, as the mass roll-up adds them; each load end is the least and the most over those two and the
duration's two ends. The current's low end takes the high kt and efficiency, its high end the low ones; the motor
voltage's high end takes the high resistance and ke, and the bus's low end the low open-circuit voltage and the high
resistance (the weak pack). This module states numbers; whether they are enough is for a tool that judges.
"""
import math

from .. import motor as motors
from ..builder import placement
from ..errors import DesignError
from ..motion import matrix as mx
from ..motion import stages
from ..source.sourced import span
from . import mass

GRAVITY = 9.80665           # m/s^2, along -z
DOWN = (0.0, 0.0, -1.0)
DEFAULT_SAMPLES = 32
EXACT = (1.0, 1.0, 1.0)
PROFILE = ("triangle: each commanded joint speeds up evenly over the first half of durationS and slows evenly over the "
           "second, from rest to rest; peak speed 2 * change / durationS at mid-stroke, acceleration 4 * change / durationS^2")
CONSERVATIVE = ("conservative: each drive's peak current is added to the others as though the peaks came at once, and "
                "each motor's winding current is counted as drawn from the bus in full")


def load_of(data, motion):
    """(the drives a motion commands, its alsoRunning entries); refuses a motion that loads nothing."""
    entry = data["motions"][motion]
    commanded, running = sorted(entry.get("drive", {})), entry.get("alsoRunning", [])
    if not commanded and not running:
        raise DesignError(f'motions "{motion}"', "commands no drive and lists nothing under alsoRunning, so it has no electrical load",
                          "Ask the electrical measure only of a motion that commands a drive or lists one under alsoRunning")
    return commanded, running


def has_load(entry):
    return bool(entry.get("drive") or entry.get("alsoRunning"))


def moved_groups(groups, group):
    """The joint's group and every group it carries, at any depth, in source order."""
    found = {group}
    for _ in groups:
        found |= {name for name, entry in groups.items() if entry.get("carriedBy") in found}
    return [name for name in groups if name in found]


def ranged(value, low, high):
    return {"value": value, "range": [min(low, high), max(low, high)]}


def limit_of(drive):
    """The lower of the drive's stated current limits, per motor, or None."""
    stated = [drive[key] for key in ("statorLimitA", "supplyLimitA") if key in drive]
    return float(min(stated)) if stated else None


def motor_ends(spec):
    """The motor model at its nominal figures, at the ends that draw least current, and at those that draw most."""
    kt, ohm, ke = (span(spec[key]) for key in ("ktNmPerA", "ohm", "keVsPerRad"))
    return ({"ktNmPerA": kt[0], "ohm": ohm[0], "keVsPerRad": ke[0]},
            {"ktNmPerA": kt[2], "ohm": ohm[1], "keVsPerRad": ke[1]},
            {"ktNmPerA": kt[1], "ohm": ohm[2], "keVsPerRad": ke[2]})


def turned(transform, vector):
    return mx.sub(mx.apply(transform, vector), mx.apply(transform, (0.0, 0.0, 0.0)))


def joint_rows(assembly, listed, drive, moved, samples, found):
    """For each sampled stroke fraction t: (t, gravity load, inertia), each (nominal, low, high) at the weights' ends.

    The gravity load is signed along the joint's positive direction; the inertia is kg m^2 about a rotation joint's
    line, or the moved mass in kg along a slide. The joint rides on its group's carrier, so its line is placed by the
    carrier's placement at t.
    """
    joint, data = drive["joint"], assembly.data
    carrier = data["groups"][joint["group"]].get("carriedBy")
    rows = []
    for k in range(samples + 1):
        t = k / samples
        places = {group: stages.at(own, t) for group, own in listed.items()}
        frame = places[carrier] if carrier else mx.IDENTITY
        axis = mx.unit(turned(frame, joint["axis"]))
        held = mass.balance(assembly, moved, places, found)
        if joint["kind"] == "rotation":
            origin = mx.apply(frame, joint["originMm"])
            gravity = tuple(GRAVITY / 1000 * mx.dot(mx.cross(mx.sub(moment, mx.scale(origin, kg)), DOWN), axis)
                            for kg, moment in zip(held["kg"], held["momentKgMm"]))
            spin = mass.inertia(assembly, moved, axis, origin, places=places, found=found)
            inertia = (spin["kgM2"], *spin["rangeKgM2"])
        else:
            gravity = tuple(GRAVITY * kg * mx.dot(DOWN, axis) for kg in held["kg"])
            inertia = held["kg"]
        rows.append((t, gravity, inertia))
    return rows


def peak_at(rows, end, acceleration, sign):
    """The most load over the motion at one end of the weights: still at both ends, speeding up over the first half
    and slowing over the second (both at mid-stroke)."""
    most = max(abs(rows[0][1][end]), abs(rows[-1][1][end]))
    for t, gravity, inertia in rows:
        for phase in ([1.0] if t < 0.5 else []) + ([-1.0] if t > 0.5 else []) + ([1.0, -1.0] if t == 0.5 else []):
            most = max(most, abs(phase * sign * acceleration * inertia[end] - gravity[end]))
    return most


def over_ends(work, accelerations):
    """(value, low, high) of work(weight end, acceleration): the nominal, and the least and most over the ends."""
    found = [work(end, a) for end in (0, 1, 2) for a in accelerations[1:]]
    return work(0, accelerations[0]), min(found), max(found)


def plus(figure, extra):
    return tuple(a + b for a, b in zip(figure, extra))


def joint_loads(rows, change, duration, extra, rotation):
    """{gravity, acceleration, extra, hold, peak} at the joint, each (value, low, high), and the peak speed (value, low,
    high) in degrees or mm per second, from the triangle profile."""
    stroke = abs(change) * (math.pi / 180 if rotation else 1e-3)        # rad or m
    accelerations = tuple(4 * stroke / seconds ** 2 for seconds in duration)        # nominal, then at each end of the duration
    sign = 1.0 if change >= 0 else -1.0
    found = {
        "gravity": over_ends(lambda end, a: max(abs(row[1][end]) for row in rows), accelerations),
        "acceleration": over_ends(lambda end, a: max(row[2][end] for row in rows) * a, accelerations),
        "extra": extra,
        "hold": plus(over_ends(lambda end, a: abs(rows[-1][1][end]), accelerations), extra),
        "peak": plus(over_ends(lambda end, a: peak_at(rows, end, a, sign), accelerations), extra),
    }
    speed = tuple(2 * abs(change) / seconds for seconds in (duration[0], duration[2], duration[1]))
    return found, speed


def driven(assembly, motion, name, command, listed, samples, found):
    """The electrical figures of one commanded drive over a motion."""
    data = assembly.data
    drive, entry = data["drives"][name], data["motions"][motion]
    joint, rotation = drive["joint"], drive["joint"]["kind"] == "rotation"
    gear, count, efficiency = float(drive.get("gear", 1.0)), drive.get("count", 1), span(drive.get("efficiency", 1.0))
    moved = moved_groups(data["groups"], joint["group"])
    extra = span(entry["extraLoad"][name]) if name in entry.get("extraLoad", {}) else (0.0, 0.0, 0.0)
    loads, speed = joint_loads(joint_rows(assembly, listed, drive, moved, samples, found), command["change"], span(entry["durationS"]), extra, rotation)
    per_radian = 1.0 if rotation else joint["perOutputTurn"] / 1000 / (2 * math.pi)       # joint load to torque at the gear's output
    turning = tuple((math.radians(v) if rotation else 2 * math.pi * v / joint["perOutputTurn"]) for v in speed)      # output rad/s
    nominal, light, heavy = motor_ends(data["motors"][drive["motor"]])
    by_end = ((nominal, efficiency[0]), (light, efficiency[2]), (heavy, efficiency[1]))

    def amps(figure):
        return tuple(motors.current_for(model, figure[end] * per_radian, gear, eff, count) for end, (model, eff) in enumerate(by_end))

    needed, limit = amps(loads["peak"]), limit_of(drive)
    current = needed if limit is None else tuple(min(value, limit) for value in needed)
    volts = tuple(motors.voltage_for(model, needed[end], motors.back_emf(model, turning[end], 1.0, gear)) for end, (model, _) in enumerate(by_end))
    return {"group": joint["group"], "kind": joint["kind"], "moved": moved, "count": count, "change": command["change"],
            "load": {"unit": "N m" if rotation else "N", **{key: ranged(*figure) for key, figure in loads.items()}},
            "peakSpeed": {"unit": "deg/s" if rotation else "mm/s", **ranged(*speed)},
            "motorRadPerS": ranged(*(gear * w for w in turning)),
            "neededA": ranged(*needed), "limitA": limit, "clamped": limit is not None and needed[2] > limit,
            "currentA": ranged(*current), "holdA": ranged(*amps(loads["hold"])), "motorV": ranged(*volts),
            "busA": ranged(*(count * value for value in current)),
            "unweighed": sorted(solid for group in moved if group in found for solid in found[group].unweighed)}


def running(data, entry):
    """A drive listed under alsoRunning: its current from the bus, the whole drive (all its motors)."""
    drive = data["drives"][entry["drive"]]
    if entry.get("atLimit"):
        amps = drive.get("count", 1) * limit_of(drive)
        return {"drive": entry["drive"], "from": "atLimit", "busA": ranged(amps, amps, amps)}
    return {"drive": entry["drive"], "from": "currentA", "busA": ranged(*span(entry["currentA"]))}


def bus(battery, loads):
    """The bus voltage under the summed currents: [Voc low - I high * R high, Voc high - I low * R low]."""
    total = tuple(sum(load["busA"]["value"] if end == 0 else load["busA"]["range"][end - 1] for load in loads) for end in range(3))
    if battery is None:
        return None
    voc, ohm = span(battery["openCircuitV"]), span(battery["resistanceOhm"])
    return {"loadA": ranged(*total), "openCircuitV": list(voc), "resistanceOhm": list(ohm),
            "volts": ranged(voc[0] - total[0] * ohm[0], voc[1] - total[2] * ohm[2], voc[2] - total[1] * ohm[1])}


def measured(assembly, motion, samples=DEFAULT_SAMPLES):
    """The electrical load of a motion: each commanded drive's figures, each drive running beside it, and the bus."""
    data = assembly.data
    if motion not in data["motions"]:
        raise DesignError("", f'there is no motion named "{motion}"', f"Known motions: {', '.join(data['motions']) or 'none'}")
    commanded, beside = load_of(data, motion)
    listed, found = placement.motion_stages(data, motion), mass.weights(assembly)
    commands = placement.commands(data, motion)
    drives = {name: driven(assembly, motion, name, commands[name], listed, samples, found) for name in commanded}
    also = [running(data, entry) for entry in beside]
    entry = data["motions"][motion]
    return {"motion": motion, "profile": PROFILE, "samples": samples,
            "durationS": ranged(*span(entry["durationS"])) if "durationS" in entry else None,
            "drives": drives, "alsoRunning": also, "bus": bus(data["battery"], [*drives.values(), *also]), "conservative": CONSERVATIVE}
