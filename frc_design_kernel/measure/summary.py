"""What the measure command asks of a whole design, and what each kind of job draws on besides solid shapes.

A job's solids are known by their identities (see carry). Everything else a job's answer depends on is listed in
its "used" block, in plain words and numbers, so the status command can say what changed: the declared contacts,
the mounts, which solids are fixtures, the masses, and the drives and battery of an electrical load.
"""
from ..builder import placement
from ..errors import DesignError
from ..source.sourced import span
from . import carry, electrical
from .search import DEFAULT_DEPTH


def contacts_for(data, motion=None):
    """The contact pairs the design source declares for a motion (or the ones declared for every motion, when None)."""
    return [row["pair"] for row in data.get("contacts", []) if "during" not in row or motion in row["during"]]


def chosen(table, names, what):
    for name in names or ():
        if name not in table:
            raise DesignError("", f'there is no {what} named "{name}"', f"Known {what}s: {', '.join(table) or 'none'}")
    return list(table) if names is None else list(names)


def known_solids(assembly, focus):
    for name in focus or ():
        if name not in assembly.solids:
            raise DesignError("", f'there is no solid named "{name}"', f"Known solids: {', '.join(sorted(assembly.solids))}")
    return None if focus is None else sorted(set(focus))


def design_jobs(data, min_gap=0.0, touch_gap=0.0, floor_z=0.0, ignore=(), depth=DEFAULT_DEPTH, near=0.0, motions=None, poses=None):
    """The jobs the measure command records: clearance along each motion, the electrical load of each motion that has
    one, and clearance, attachment and mass at each pose.

    motions and poses name a subset (None is all of them; the as-drawn pose is measured only when poses is None).
    """
    along = chosen(data["motions"], motions, "motion")
    jobs = [{"kind": "clearance", "motion": name, "minGapMm": min_gap, "depth": depth, "nearMm": near} for name in along]
    jobs += [{"kind": "electrical", "motion": name} for name in along if electrical.has_load(data["motions"][name])]
    for pose in ([None] if poses is None else []) + chosen(data["poses"], poses, "pose"):
        jobs += [{"kind": "clearance", "pose": pose, "minGapMm": min_gap},
                 {"kind": "attachment", "pose": pose, "touchGapMm": touch_gap, "floorZMm": floor_z, "ignore": sorted(ignore)},
                 {"kind": "mass", "pose": pose}]
    return jobs


def resolved_contacts(data, job, present):
    """The pairs a job leaves out as meant to touch: the source's declared ones ("declared") or the job's own list,
    each with both solids present, as sorted pairs."""
    listed = job["contacts"]
    if listed == "declared":
        listed = contacts_for(data, job.get("motion"))
    return sorted({tuple(sorted(pair)) for pair in listed if pair[0] in present and pair[1] in present})


def used_by_attachment(assembly, job, present):
    """What an attachment draws on besides shapes: declared contacts, mounts, which solids are fixtures, and the groups."""
    data, built = assembly.data, assembly.solids
    return {"contacts": [list(pair) for pair in resolved_contacts(data, job, present)],
            "mounts": [{key: value for key, value in mount.items() if key != "note"} for mount in data["mounts"]],
            "fixtures": sorted(name for name in present if built[name].fixture),
            "groups": carry.digest({name: built[name].group for name in sorted(present)})}


def weighed(assembly, present):
    """The robot solids whose shape a mass roll-up uses: those with a mass, and every member of a group with a lump mass
    or with extra mass (which sits at the centre of its group's volume)."""
    data, built = assembly.data, assembly.solids
    spread = {name for name, group in data["groups"].items() if "massKg" in group} | {entry["group"] for entry in data["extraMass"]}
    return sorted(name for name in present if not built[name].fixture and (built[name].mass_kg is not None or built[name].group in spread))


def used_by_mass(assembly, present):
    """What a mass roll-up draws on besides shapes: each solid's mass and range, each group's lump mass, the weight with no
    solid, the solids with none, and which group each solid is in."""
    data, built = assembly.data, assembly.solids
    robot = [name for name in sorted(present) if not built[name].fixture]
    weighs = [name for name in robot if built[name].mass_kg is not None]
    return {"masses": {name: built[name].mass_kg for name in weighs},
            "massRanges": {name: list(built[name].mass_range_kg) for name in weighs},
            "groupMasses": {name: list(span(group["massKg"])) for name, group in data["groups"].items() if "massKg" in group},
            "extraMass": data["extraMass"],
            "unweighed": [name for name in robot if built[name].mass_kg is None and "massKg" not in data["groups"][built[name].group]],
            "groups": carry.digest({name: built[name].group for name in robot})}


def drive_facts(data, name, commanded):
    """What an electrical load uses of one drive: its motor's figures, gear, count, efficiency and current limits, and
    for a commanded drive its joint. Each sourced figure as (value, low, high); notes left out."""
    drive = data["drives"][name]
    motor = data["motors"].get(drive.get("motor"), {})
    found = {"motor": {key: list(span(motor[key])) for key in ("ktNmPerA", "ohm", "keVsPerRad") if key in motor},
             "gear": drive.get("gear", 1.0), "count": drive.get("count", 1), "efficiency": list(span(drive.get("efficiency", 1.0))),
             "limits": {key: drive[key] for key in ("statorLimitA", "supplyLimitA") if key in drive}}
    return found | ({"joint": drive["joint"]} if commanded else {})


def used_by_electrical(assembly, motion, samples):
    """(inputs, used) of an electrical job: the identities of the moved groups' solids, and the motion's start and joint
    commands, the moved weight, the drives, the duration, the extra loads, what runs beside it and the battery."""
    data, built = assembly.data, assembly.solids
    commanded, beside = electrical.load_of(data, motion)
    moved = {group for name in commanded for group in electrical.moved_groups(data["groups"], data["drives"][name]["joint"]["group"])}
    names = sorted(name for name, solid in built.items() if solid.group in moved and not solid.fixture)
    identities = carry.along(assembly, motion)
    entry, battery = data["motions"][motion], data["battery"]
    weighs = [name for name in names if built[name].mass_kg is not None]
    used = placement.described(data, motion) | {
        "masses": {name: built[name].mass_kg for name in weighs},
        "massRanges": {name: list(built[name].mass_range_kg) for name in weighs},
        "groupMasses": {name: list(span(group["massKg"])) for name, group in data["groups"].items() if name in moved and "massKg" in group},
        "extraMass": sorted(([row["group"], row["name"], list(span(row["massKg"]))] for row in data["extraMass"] if row["group"] in moved)),
        "unweighed": [name for name in names if built[name].mass_kg is None and "massKg" not in data["groups"][built[name].group]],
        "groups": carry.digest({name: built[name].group for name in names}),
        "drives": {name: drive_facts(data, name, name in commanded) for name in [*commanded, *(row["drive"] for row in beside)]},
        "durationS": list(span(entry["durationS"])) if "durationS" in entry else None,
        "extraLoad": {name: list(span(load)) for name, load in sorted(entry.get("extraLoad", {}).items())},
        "alsoRunning": [{"drive": row["drive"], **({"atLimit": True} if row.get("atLimit") else {"currentA": list(span(row["currentA"]))})} for row in beside],
        "battery": None if battery is None else {key: list(span(battery[key])) for key in ("openCircuitV", "resistanceOhm")},
    }
    return {"rules": {"samples": samples}, "solids": {name: identities[name] for name in names}}, used
