"""Checks on drives, motions and the battery that need no placement worked out. Each raises a DesignError naming what
is wrong.

A drive with a motor names the solid that is the motor, so every motor is weighed and sits somewhere. A drive with a
joint moves one group. A motion either commands drives, or states what moves its typed geometry ("by"). A motion may
start where another ends, and no chain of such starts may loop. What needs a placement (a command past a joint's
travel, a group that does not start on its joint) is checked when the placements are worked out. The battery states
its two figures with their sources.
"""
from ..errors import DesignError, unknown
from ..motion import matrix as mx
from .sourced import check_sourced, span

CAUSES = ("hand", "spring", "gravity", "piece")


def quoted(names):
    return " and ".join(f'"{name}"' for name in names)


def check_drive(design, name, drive, robot):
    where = f'drives "{name}"'
    if "joint" not in drive and "radiusMm" not in drive:
        raise DesignError(where, 'says neither what it moves nor what surface it runs', 'Give it a "joint" that moves a group, or a "radiusMm" for a surface a trial drives')
    if "motor" in drive:
        if drive["motor"] not in design["motors"]:
            raise unknown(where, "motor", drive["motor"], design["motors"])
        if "motorSolid" not in drive:
            raise DesignError(where, 'has a motor but no "motorSolid"', 'Draw the motor as a solid and name it in "motorSolid", so it is weighed and placed with purpose')
        if drive["motorSolid"] not in robot:
            raise unknown(f"{where} motorSolid", "robot solid", drive["motorSolid"], robot)
        if "radiusMm" in drive and ("movingKg" in drive) == ("inertiaKgM2" in drive):
            raise DesignError(where, 'a motor drive with a surface needs exactly one of "movingKg" or "inertiaKgM2"', "Say what the motor has to speed up")
    elif "motorSolid" in drive:
        raise DesignError(where, 'names a "motorSolid" but no "motor"', 'Name the motor that solid is, or remove "motorSolid"')
    if drive.get("turns") and "radiusMm" not in drive:
        raise DesignError(where, 'turns solids but has no "radiusMm"', "Give the radius of the surface it runs")
    if "joint" in drive:
        check_joint(design, drive, where)


def check_joint(design, drive, where):
    joint, place = drive["joint"], f"{where} joint"
    if "motor" not in drive:
        raise DesignError(where, 'has a joint but no "motor"', 'Name the motor that moves the joint, and place it with "motorSolid"')
    if joint["group"] not in design["groups"]:
        raise unknown(place, "group", joint["group"], design["groups"])
    if mx.length(joint["axis"]) == 0:
        raise DesignError(place, "the axis is [0, 0, 0]", "Give the direction the joint turns about or slides along, such as [0, 0, 1]")
    rotation = joint["kind"] == "rotation"
    for key, wanted in (("originMm", rotation), ("perOutputTurn", not rotation)):
        if wanted and key not in joint:
            raise DesignError(place, f'a {joint["kind"]} joint needs "{key}"', "Give a point on the turning line" if rotation else "Give the mm travelled per turn of the gear's output: a lead, or a pulley's circumference")
        if not wanted and key in joint:
            raise DesignError(place, f'a {joint["kind"]} joint has no "{key}"', f'Remove "{key}"')
    if not rotation and joint["perOutputTurn"] == 0:
        raise DesignError(place, "perOutputTurn is 0", "Give the mm travelled per turn of the gear's output")
    if drive.get("gear", 1) == 0:
        raise DesignError(where, "gear is 0", "Give the motor turns per turn of the output")
    if not joint["travel"][0] < joint["travel"][1]:
        raise DesignError(place, "its travel is not [low, high] with low below high", "Give the joint values at its two stops")


def check_drives(design):
    robot = {solid["name"] for solid in design["solids"]}
    for name, drive in design["drives"].items():
        check_drive(design, name, drive, robot)


def check_commands(design, name, motion, where):
    """A motion that commands drives: each drive has a joint, one drive per joint group, no typed op on such a group."""
    drives, moved = design["drives"], {}
    if "through" in motion:
        raise DesignError(where, 'commands drives and passes "through" poses', 'Start a driven motion at "from" (a pose, or after another motion); move a "through" motion "by" hand')
    for drive in motion["drive"]:
        if drive not in drives:
            raise unknown(f"{where} drive", "drive", drive, drives)
        if "joint" not in drives[drive]:
            raise DesignError(where, f'commands the drive "{drive}", which has no joint', 'Give the drive a "joint", or move this group by typed moves with "by"')
        moved.setdefault(drives[drive]["joint"]["group"], []).append(drive)
    for group, by in sorted(moved.items()):
        if len(by) > 1:
            raise DesignError(where, f'commands the drives {quoted(by)}, which both move the group "{group}"',
                              'Command one drive per joint in a motion; two motors on one joint are one drive with "count"')
        if group in motion.get("moves", {}):
            raise DesignError(where, f'moves the group "{group}" by typed operations, but the drive "{by[0]}" moves it',
                              "Leave the group to its drive, or move it in a motion of its own")
    if motion.get("moves") and "by" not in motion:
        raise DesignError(where, 'has typed "moves" beside its drive commands but no "by"', f"Say what moves the other groups: \"by\": {', '.join(CAUSES)}")
    if "by" in motion and not motion.get("moves"):
        raise DesignError(where, 'has "by" but no typed "moves" for it to explain', 'Remove "by"; the drive commands are the cause')
    if "durationS" not in motion:
        raise DesignError(where, 'commands drives but has no "durationS"', 'Give how long the motion takes, with its source, for example {"value": 0.5, "assumed": [0.4, 0.7]}')


def check_loads(design, motion, where):
    """durationS, alsoRunning and extraLoad: each names a real drive, once, and states its numbers with their sources."""
    drives, commanded = design["drives"], set(motion.get("drive", {}))
    if "durationS" in motion:
        check_sourced(motion["durationS"], f"{where} durationS")
        if span(motion["durationS"])[1] <= 0:
            raise DesignError(where, "durationS is not above zero at its low end", "Give a time in seconds above zero")
    seen = set()
    for i, entry in enumerate(motion.get("alsoRunning", [])):
        place, drive = f"{where} alsoRunning[{i}]", entry["drive"]
        if drive not in drives:
            raise unknown(place, "drive", drive, drives)
        if drive in commanded or drive in seen:
            raise DesignError(place, f'names the drive "{drive}" again', "List each drive once: a commanded drive is already running")
        seen.add(drive)
        if entry.get("atLimit") and not {"supplyLimitA", "statorLimitA"} & set(drives[drive]):
            raise DesignError(place, f'runs the drive "{drive}" at its current limit, but it has no current limit', 'Give the drive "supplyLimitA" or "statorLimitA", or give "currentA"')
        if "currentA" in entry:
            check_sourced(entry["currentA"], f"{place} currentA")
            if span(entry["currentA"])[1] < 0:
                raise DesignError(place, "currentA is negative", "Give the current drawn, zero or more")
    for drive, load in motion.get("extraLoad", {}).items():
        if drive not in commanded:
            raise DesignError(f"{where} extraLoad", f'names the drive "{drive}", which this motion does not command', "Give an extra load only for a drive the motion commands")
        check_sourced(load, f"{where} extraLoad.{drive}")


def check_motion(design, name, motion):
    """One motion's cause, form and loads. The poses it names and its typed operations are checked by the caller."""
    where = f'motions "{name}"'
    if "drive" in motion:
        check_commands(design, name, motion, where)
    else:
        if "by" not in motion:
            raise DesignError(where, 'states no cause: it commands no drive and has no "by"',
                              f"Command the drives that make it, or say what moves it: \"by\": {', '.join(CAUSES)}")
        if ("moves" in motion) == ("through" in motion):
            raise DesignError(where, 'needs exactly one of "moves" or "through"', 'Use "from" and "moves" for operations, or "through" for a list of poses')
    if "through" in motion and ("from" in motion or "to" in motion):
        raise DesignError(where, 'has "through" together with "from" or "to"', 'A "through" motion starts at its first pose and ends at its last; remove "from" and "to"')
    check_loads(design, motion, where)


def check_battery(design):
    """The battery's open-circuit voltage is above zero and its resistance is not below zero, each with its source."""
    battery = design["battery"]
    if battery is None:
        return
    for key, lowest, words in (("openCircuitV", 0.0, "above zero"), ("resistanceOhm", None, "zero or more")):
        check_sourced(battery[key], f"battery {key}")
        low = span(battery[key])[1]
        if low < 0 or (lowest is not None and low <= lowest):
            raise DesignError(f"battery {key}", f"is not {words} at its low end", "Give the figure, and an assumed range around it, in volts or ohms")


def check_chains(design):
    """Every motion that starts after another names a motion that exists, and no chain of such starts loops."""
    motions = design["motions"]
    for name in motions:
        trail = [name]
        while isinstance(motions[trail[-1]].get("from"), dict):
            before = motions[trail[-1]]["from"]["after"]
            if before not in motions:
                raise unknown(f'motions "{trail[-1]}" from', "motion", before, motions)
            if before in trail:
                loop = " -> ".join('"' + step + '"' for step in [*trail[trail.index(before):], before])
                raise DesignError(f'motions "{name}"', f"starts in a loop of motions: {loop}", "Start one motion of the loop at a pose, or as drawn")
            trail.append(before)
