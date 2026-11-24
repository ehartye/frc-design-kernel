"""What the measure command asks of a whole design, and what each kind of job draws on besides solid shapes.

A job's solids are known by their identities (see carry). Everything else a job's answer depends on is listed in
its "used" block, in plain words and numbers, so the status command can say what changed: the declared contacts,
the mounts, which solids are fixtures, and the masses.
"""
from ..errors import DesignError
from . import carry
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
    """The jobs the measure command records: clearance along each motion, and clearance, attachment and mass at each pose.

    motions and poses name a subset (None is all of them; the as-drawn pose is measured only when poses is None).
    """
    jobs = [{"kind": "clearance", "motion": name, "minGapMm": min_gap, "depth": depth, "nearMm": near} for name in chosen(data["motions"], motions, "motion")]
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
    """The robot solids whose shape a mass roll-up uses: those with a mass, and every member of a group with a lump mass."""
    groups = assembly.data["groups"]
    return sorted(name for name in present if not assembly.solids[name].fixture
                  and (assembly.solids[name].mass_kg is not None or "massKg" in groups[assembly.solids[name].group]))


def used_by_mass(assembly, present):
    """What a mass roll-up draws on besides shapes: each solid's mass, each group's lump mass, and the solids with none."""
    built, groups = assembly.solids, assembly.data["groups"]
    robot = [name for name in sorted(present) if not built[name].fixture]
    return {"masses": {name: built[name].mass_kg for name in robot if built[name].mass_kg is not None},
            "groupMasses": {name: group["massKg"] for name, group in groups.items() if "massKg" in group},
            "unweighed": [name for name in robot if built[name].mass_kg is None and "massKg" not in groups[built[name].group]],
            "groups": carry.digest({name: built[name].group for name in robot})}
