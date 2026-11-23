"""Everything the measure layer can say about a design, gathered into one plain record with the library stamp.

Each part of the record lists what it used (solids, the motion or pose, groups, declared contacts, mounts), with
enough of each thing's identity for the status command to tell later whether it has changed.
"""
from ..builder import identity
from ..errors import DesignError
from ..version import generator
from . import attachment, clearance, mass, run
from .search import DEFAULT_DEPTH

SCHEMA = "frc-design-kernel/measurements@2"


def contacts_for(data, motion=None):
    """The contact pairs the design source declares for a motion (or the ones declared for every motion, when None)."""
    return [row["pair"] for row in data.get("contacts", []) if "during" not in row or motion in row["during"]]


def groups_used(data):
    return {name: {"carriedBy": group.get("carriedBy")} for name, group in data["groups"].items()}


def used_by_motion(assembly, motion, absent=()):
    """What a clearance along a motion draws on: every solid present, the motion, the poses it names, the groups, declared contacts."""
    data = assembly.data
    entry = data["motions"][motion]
    named = [*entry.get("through", []), *[entry[key] for key in ("from", "to") if key in entry]]
    return {"solids": identity.solids(assembly, [n for n in assembly.solids if n not in set(absent)]),
            "motion": {key: value for key, value in entry.items() if key != "note"},
            "poses": {pose: data["poses"][pose] for pose in named}, "groups": groups_used(data),
            "contacts": sorted(sorted(pair) for pair in contacts_for(data, motion))}


def used_by_pose(assembly, pose):
    """What the measures at a pose draw on: every solid, the pose, the groups, mounts, lump masses and declared contacts."""
    data = assembly.data
    return {"solids": identity.solids(assembly, assembly.solids), "poses": {pose: data["poses"][pose]} if pose else {},
            "groups": {name: {"carriedBy": group.get("carriedBy"), "massKg": group.get("massKg")} for name, group in data["groups"].items()},
            "mounts": [{key: value for key, value in mount.items() if key != "note"} for mount in data["mounts"]],
            "contacts": sorted(sorted(pair) for pair in contacts_for(data))}


def chosen(table, names, what):
    for name in names or ():
        if name not in table:
            raise DesignError("", f'there is no {what} named "{name}"', f"Known {what}s: {', '.join(table) or 'none'}")
    return list(table) if names is None else list(names)


def measure_design(source, min_gap=0.0, touch_gap=0.0, floor_z=0.0, ignore=(), workers=None, depth=DEFAULT_DEPTH, motions=None, poses=None):
    """Measure a design source: clearance along motions, and clearance, attachment and mass at poses.

    min_gap is the gap every pair is tested against. touch_gap is how near two surfaces count as touching. ignore
    names solids left out of the attachment record. motions and poses name a subset to measure (None is all of
    them; the as-drawn pose is measured only when poses is None). The numbers are the caller's; the record states
    them and judges nothing.
    """
    assembly = run.assembly_for(source)
    data = assembly.data
    names = chosen(data["motions"], motions, "motion")
    jobs = [{"motion": name, "minGapMm": min_gap, "contacts": contacts_for(data, name), "depth": depth} for name in names]
    found = dict(zip(names, run.clearances(source, jobs, workers)))
    for name in names:
        found[name]["used"] = used_by_motion(assembly, name)
    rows = []
    for pose in ([None] if poses is None else []) + chosen(data["poses"], poses, "pose"):
        declared = contacts_for(data)
        rows.append({"pose": pose, "clearance": clearance.at_pose(assembly, pose, min_gap, declared),
                     "attachment": attachment.at_pose(assembly, pose, touch_gap, floor_z, ignore, contacts=declared),
                     "mass": mass.roll_up(assembly, pose), "used": used_by_pose(assembly, pose)})
    return {"schema": SCHEMA, "generator": generator(),
            "design": {"name": data["name"], "source": assembly.design.path.name, "sourceSha256": assembly.design.sha256},
            "settings": {"minGapMm": float(min_gap), "touchGapMm": float(touch_gap), "floorZMm": float(floor_z), "ignored": sorted(ignore),
                         "depthLimit": depth},
            "motions": found, "poses": rows}


def merged(old, new):
    """A measurement record with the freshly measured motions and poses put into an older record, the rest kept."""
    out = dict(new)
    out["motions"] = {**old.get("motions", {}), **new["motions"]}
    fresh = {row["pose"] for row in new["poses"]}
    out["poses"] = [row for row in old.get("poses", []) if row["pose"] not in fresh] + new["poses"]
    return out
