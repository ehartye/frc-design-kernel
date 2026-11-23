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


def check_all(design):
    """Run every check on a plain design. Returns {custom shape name: [solids that use it]}."""
    check_groups(design)
    solids = check_solids(design)
    used = check_custom(design)
    check_mounts(design, solids)
    check_poses_and_motions(design)
    return used
