"""Checks across a plain design: names exist, nothing is counted twice, nothing loops. Each raises a DesignError."""
import difflib
import re

from ..errors import DesignError
from ..motion import ops as motion_ops
from .schema import step

FIXTURE_GROUP = "fixtures"


def unknown(where, what, name, known):
    close = difflib.get_close_matches(str(name), list(known), 1)
    hint = f'Did you mean "{close[0]}"? ' if close else ""
    return DesignError(where, f'names the {what} "{name}", which does not exist', f"{hint}Known: {', '.join(sorted(known)) or 'none'}")


def custom_uses(shape):
    """Every custom shape name used inside a shape entry."""
    if shape.get("kind") == "custom":
        return [shape["use"]]
    inner = [*shape.get("of", []), *shape.get("cut", []), *([shape["from"]] if isinstance(shape.get("from"), dict) else [])]
    return [name for part in inner for name in custom_uses(part)]


def check_solids(design):
    seen = {}
    for section in ("solids", "fixtures"):
        for i, solid in enumerate(design[section]):
            where = step(section, i, solid)
            if re.search(r"\{\w+\}", solid["name"]):
                raise DesignError(where, "the name still has a { } placeholder", 'Add an "each" row that fills it, or remove the braces')
            if solid["name"] in seen:
                raise DesignError(where, f"has the same name as {seen[solid['name']]}", "Give every solid and fixture its own name")
            seen[solid["name"]] = where
            if ("shape" in solid) == ("part" in solid):
                raise DesignError(where, 'needs exactly one of "shape" or "part"', "Draw it with a shape, or take it from a STEP file with a part")
            if section == "fixtures":
                solid.setdefault("group", FIXTURE_GROUP)
            elif "group" not in solid:
                raise DesignError(where, 'is missing "group"', f"Add one of the groups: {', '.join(design['groups'])}")
            if solid["group"] not in design["groups"]:
                raise unknown(where, "group", solid["group"], design["groups"])
            check_mass(solid, design["groups"][solid["group"]], where)
            motion_ops.check(solid.get("place", []), f"{where} place")
    return seen


def check_mass(solid, group, where):
    if "massKg" in solid and "densityKgM3" in solid:
        raise DesignError(where, "has both massKg and densityKgM3", "Keep one: a known mass, or a density to weigh the drawn volume")
    for key in ("massKg", "densityKgM3"):
        if key in solid and solid[key] < 0:
            raise DesignError(where, f"{key} is negative", "Give zero or more")
        if key in solid and "massKg" in group:
            raise DesignError(where, f'has {key}, but its group "{solid["group"]}" already has one lump massKg',
                              "Remove the mass from the solid or from the group, so nothing is counted twice")


def check_groups(design):
    groups = design["groups"]
    if design["fixtures"]:
        groups.setdefault(FIXTURE_GROUP, {"role": "fixture"})
    for name, group in groups.items():
        where = f'groups "{name}"'
        if group.get("massKg", 0) < 0:
            raise DesignError(where, "massKg is negative", "Give zero or more")
        motion_ops.check(group.get("place", []), f"{where} place")
        trail = [name]
        while "carriedBy" in groups[trail[-1]]:
            carrier = groups[trail[-1]]["carriedBy"]
            if carrier not in groups:
                raise unknown(f'groups "{trail[-1]}" carriedBy', "group", carrier, groups)
            if carrier in trail:
                raise DesignError(where, f"is carried in a circle: {' -> '.join([*trail, carrier])}", "Remove one carriedBy so the chain ends at a group nothing carries")
            trail.append(carrier)


def check_custom(design):
    used = {}
    for section in ("solids", "fixtures"):
        for i, solid in enumerate(design[section]):
            for name in custom_uses(solid.get("shape", {})):
                if name not in design["custom"]:
                    raise unknown(step(section, i, solid), "custom shape", name, design["custom"])
                used.setdefault(name, []).append(solid["name"])
    for trial, entry in design["trials"].items():
        for kind, uses in (("force", entry.get("forces", [])), ("criterion", [entry["pass"]["custom"]] if "custom" in entry["pass"] else [])):
            for use in uses:
                if use["use"] not in design["custom"]:
                    raise unknown(f'trials "{trial}"', f"custom {kind}", use["use"], design["custom"])
                if design["custom"][use["use"]].get("kind", "shape") != kind:
                    raise DesignError(f'trials "{trial}"', f'uses "{use["use"]}" as a custom {kind}, but it is registered as another kind',
                                      f'Register it with "kind": "{kind}"')
                used.setdefault(use["use"], []).append(f"trial {trial}")
    for name in design["custom"]:
        if name not in used:
            raise DesignError(f'custom "{name}"', "is registered but no solid uses it", "Remove it, or use it in a shape")
    return used


def check_mounts(design, solids):
    members = {s["name"]: s["group"] for section in ("solids", "fixtures") for s in design[section]}
    for i, mount in enumerate(design["mounts"]):
        where = f"mounts[{i}]"
        if mount["group"] not in design["groups"]:
            raise unknown(where, "group", mount["group"], design["groups"])
        if mount["on"] not in solids:
            raise unknown(f"{where} on", "solid", mount["on"], solids)
        if "member" in mount and members.get(mount["member"]) != mount["group"]:
            raise DesignError(where, f'member "{mount["member"]}" is not a solid of the group "{mount["group"]}"', "Name a solid that belongs to the mounted group")


def check_contacts(design, solids):
    for i, contact in enumerate(design["contacts"]):
        where = f"contacts[{i}]"
        a, b = contact["pair"]
        for name in (a, b):
            if name not in solids:
                raise unknown(where, "solid", name, solids)
        if a == b:
            raise DesignError(where, "names the same solid twice", "A contact is between two different solids")
        for motion in contact.get("during", []):
            if motion not in design["motions"]:
                raise unknown(f"{where} during", "motion", motion, design["motions"])


def check_group_ops(table, where, groups):
    for group, ops in table.items():
        if group not in groups:
            raise unknown(where, "group", group, groups)
        motion_ops.check(ops, f"{where}.{group}")


def check_poses_and_motions(design):
    groups, poses = design["groups"], design["poses"]
    for name, pose in poses.items():
        check_group_ops(pose, f'poses "{name}"', groups)
    for name, motion in design["motions"].items():
        where = f'motions "{name}"'
        if ("moves" in motion) == ("through" in motion):
            raise DesignError(where, 'needs exactly one of "moves" or "through"', 'Use "from" and "moves" for operations, or "through" for a list of poses')
        if "through" in motion and ("from" in motion or "to" in motion):
            raise DesignError(where, 'has "through" together with "from" or "to"', 'A "through" motion starts at its first pose and ends at its last; remove "from" and "to"')
        for pose in [*motion.get("through", []), *[motion[k] for k in ("from", "to") if k in motion]]:
            if pose not in poses:
                raise unknown(where, "pose", pose, poses)
        check_group_ops(motion.get("moves", {}), f"{where} moves", groups)


SOURCED_TABLES = ("pieces", "materials", "motors", "drives")


def check_sourced(value, where):
    """A physical input that states its source must state exactly one, and an assumed range must hold its value."""
    if isinstance(value, dict) and "value" in value:
        if ("measured" in value) == ("assumed" in value):
            raise DesignError(where, 'needs exactly one of "measured" or "assumed"', 'Say where it was measured, or give the range it is believed to lie in')
        if "assumed" in value and not value["assumed"][0] <= value["value"] <= value["assumed"][1]:
            raise DesignError(where, f'its value {value["value"]:g} is outside its assumed range {value["assumed"]}', "Give the range as [low, high] around the value")
    elif isinstance(value, dict):
        for key, item in value.items():
            check_sourced(item, f"{where}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            check_sourced(item, f"{where}[{i}]")


def check_tables(design, solids):
    for table in SOURCED_TABLES:
        check_sourced(design[table], table)
    for name, drive in design["drives"].items():
        where = f'drives "{name}"'
        if "motor" in drive and drive["motor"] not in design["motors"]:
            raise unknown(where, "motor", drive["motor"], design["motors"])
        if "motor" in drive and ("movingKg" in drive) == ("inertiaKgM2" in drive):
            raise DesignError(where, 'a motor drive needs exactly one of "movingKg" or "inertiaKgM2"', "Say what the motor has to speed up")
        for turn in drive.get("turns", []):
            if turn["solid"] not in solids:
                raise unknown(where, "solid", turn["solid"], solids)


def check_adjustments(design):
    for name, entry in design["adjustments"].items():
        where = f'adjustments "{name}"'
        if not entry["range"][0] < entry["range"][1]:
            raise DesignError(where, "its range is not [low, high] with low below high", "Give the two ends the built robot can be set to")
        if entry["input"].startswith("parameters."):
            if entry["input"][len("parameters."):] not in design["parameters"]:
                raise unknown(where, "parameter", entry["input"][len("parameters."):], design["parameters"])
        elif entry["kind"] == "mechanical":
            raise DesignError(where, "a mechanical adjustment must change a design parameter", 'Write its input as "parameters.NAME", so the solids move with it')


def check_interactions(design, solids):
    for name, entry in design["interactions"].items():
        where = f'interactions "{name}"'
        if entry["piece"] not in design["pieces"]:
            raise unknown(where, "piece", entry["piece"], design["pieces"])
        for solid in [*entry["solids"], *entry.get("guides", []), *([entry["pieceSolid"]] if "pieceSolid" in entry else [])]:
            if solid not in solids:
                raise unknown(where, "solid", solid, solids)
        for motion in [*entry.get("motions", []), *([entry["squeezeMotion"]] if "squeezeMotion" in entry else [])]:
            if motion not in design["motions"]:
                raise unknown(where, "motion", motion, design["motions"])
        if "pose" in entry and entry["pose"] not in design["poses"]:
            raise unknown(where, "pose", entry["pose"], design["poses"])


def check_trials(design, solids):
    trials = design["trials"]
    for name, trial in trials.items():
        where = f'trials "{name}"'
        check_sourced(trial.get("flaps", []), f"{where} flaps")
        if trial["piece"]["use"] not in design["pieces"]:
            raise unknown(f"{where} piece", "piece", trial["piece"]["use"], design["pieces"])
        for i, surface in enumerate([*trial["surfaces"], *trial.get("flaps", [])]):
            label = f'{where} surface "{surface.get("name", surface.get("solid", i))}"'
            if "hingeMm" not in surface:
                if "solid" in surface and surface["solid"] not in solids:
                    raise unknown(label, "solid", surface["solid"], solids)
                if sum(key in surface for key in ("solid", "segmentsMm", "circleMm")) != 1:
                    raise DesignError(label, 'needs exactly one of "solid", "segmentsMm" or "circleMm"', "Say where the surface is, once")
            if surface["material"] not in design["materials"]:
                raise unknown(label, "material", surface["material"], design["materials"])
            if "drive" in surface and surface["drive"] not in design["drives"]:
                raise unknown(label, "drive", surface["drive"], design["drives"])
        for adjustment in trial.get("adjustments", []):
            if adjustment not in design["adjustments"]:
                raise unknown(where, "adjustment", adjustment, design["adjustments"])
        for drive in trial.get("commands", {}):
            if drive not in design["drives"]:
                raise unknown(f"{where} commands", "drive", drive, design["drives"])
        if "pose" in trial and trial["pose"] not in design["poses"]:
            raise unknown(where, "pose", trial["pose"], design["poses"])
        start = trial["piece"]["start"]
        if ("after" in start) == ("atMm" in start):
            raise DesignError(f"{where} piece.start", 'needs exactly one of "atMm" or "after"', "Give a start point, or the trial whose end state this one starts from")
        trail = [name]
        while "after" in trials[trail[-1]]["piece"]["start"]:
            before = trials[trail[-1]]["piece"]["start"]["after"]
            if before not in trials:
                raise unknown(f'trials "{trail[-1]}" piece.start', "trial", before, trials)
            if before in trail:
                raise DesignError(where, f"starts after itself: {' -> '.join([*trail, before])}", "Give one trial in the chain a start point")
            trail.append(before)


def check_all(design):
    """Run every check on a plain design. Returns {custom shape name: [solids that use it]}."""
    check_groups(design)
    solids = check_solids(design)
    used = check_custom(design)
    check_mounts(design, solids)
    check_contacts(design, solids)
    check_tables(design, solids)
    check_adjustments(design)
    check_interactions(design, solids)
    check_trials(design, solids)
    check_poses_and_motions(design)
    return used
