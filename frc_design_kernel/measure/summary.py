"""Everything the measure layer can say about a design, gathered into one plain record with the library stamp.

Each part of the record lists what it used (solids, the motion or pose, groups, declared contacts, mounts), with
enough of each thing's identity for the status command to tell later whether it has changed. Given an earlier
record, only what changed is measured again and the rest is carried from it (see carry); each part says which.
"""
from ..builder import identity
from ..errors import DesignError
from ..version import generator
from . import attachment, carry, clearance, mass, run
from .search import DEFAULT_DEPTH

SCHEMA = "frc-design-kernel/measurements@3"


def contacts_for(data, motion=None):
    """The contact pairs the design source declares for a motion (or the ones declared for every motion, when None)."""
    return [row["pair"] for row in data.get("contacts", []) if "during" not in row or motion in row["during"]]


def groups_used(data):
    return {name: {"carriedBy": group.get("carriedBy")} for name, group in data["groups"].items()}


def solids_used(assembly, names):
    """The identities of the named solids, each worked out once per assembly however many records list it."""
    every = carry.once(assembly, "identity", lambda built: identity.solids(built, built.solids))
    return {name: dict(every[name], boundsMm=list(every[name]["boundsMm"])) for name in sorted(names)}


def used_by_motion(assembly, motion, absent=()):
    """What a clearance along a motion draws on: every solid present, the motion, the poses it names, the groups, declared contacts."""
    data = assembly.data
    entry = data["motions"][motion]
    named = [*entry.get("through", []), *[entry[key] for key in ("from", "to") if key in entry]]
    return {"solids": solids_used(assembly, [n for n in assembly.solids if n not in set(absent)]),
            "motion": {key: value for key, value in entry.items() if key != "note"},
            "poses": {pose: data["poses"][pose] for pose in named}, "groups": groups_used(data),
            "contacts": sorted(sorted(pair) for pair in contacts_for(data, motion))}


def used_by_pose(assembly, pose):
    """What the measures at a pose draw on: every solid, the pose, the groups, mounts, lump masses and declared contacts."""
    data = assembly.data
    return {"solids": solids_used(assembly, assembly.solids), "poses": {pose: data["poses"][pose]} if pose else {},
            "groups": {name: {"carriedBy": group.get("carriedBy"), "massKg": group.get("massKg")} for name, group in data["groups"].items()},
            "mounts": [{key: value for key, value in mount.items() if key != "note"} for mount in data["mounts"]],
            "contacts": sorted(sorted(pair) for pair in contacts_for(data)), "extraMass": data["extraMass"]}


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


def at_pose(assembly, pose, settings, focus, earlier):
    """Clearance, attachment and mass at one pose, each carried from the earlier row (when given) where nothing it uses changed."""
    min_gap, touch_gap, floor_z, ignore = settings
    declared = contacts_for(assembly.data)
    was = earlier or {}
    found = clearance.at_pose(assembly, pose, min_gap, declared, focus=focus, earlier=(was.get("clearance") or {}) if earlier is not None else None)
    inputs = carry.pose_inputs(assembly, found["inputs"]["solids"], declared, touch_gap, floor_z, ignore)
    held = was.get("inputs") or {}
    out = {"pose": pose, "clearance": found, "inputs": inputs, "checked": {}}
    for key, measure in (("attachment", lambda: attachment.at_pose(assembly, pose, touch_gap, floor_z, ignore, contacts=declared,
                                                                  earlier=was.get("attachment") if earlier is not None else None)),
                         ("mass", lambda: mass.roll_up(assembly, pose))):
        same = earlier is not None and key in was and held.get(key) == inputs[key]
        out[key], out["checked"][key] = (was[key], "carried") if same else (measure(), "measured")
    out["used"] = used_by_pose(assembly, pose)
    return out


def measure_design(source, min_gap=0.0, touch_gap=0.0, floor_z=0.0, ignore=(), workers=None, depth=DEFAULT_DEPTH, motions=None, poses=None,
                   earlier=None, focus=None):
    """Measure a design source: clearance along motions, and clearance, attachment and mass at poses.

    min_gap is the gap every pair is tested against. touch_gap is how near two surfaces count as touching. ignore
    names solids left out of the attachment record. motions and poses name a subset to measure (None is all of
    them; the as-drawn pose is measured only when poses is None). The numbers are the caller's; the record states
    them and judges nothing. earlier is an earlier record to carry from: only the pairs whose inputs changed are
    measured, and attachment and mass at a pose only when something they use changed. focus names solids whose
    pairs are measured again even so; without earlier, only their pairs are measured and the record says so.
    """
    assembly = run.assembly_for(source)
    data = assembly.data
    names = chosen(data["motions"], motions, "motion")
    focus = known_solids(assembly, focus)
    old = {} if earlier is None else {"motions": earlier.get("motions") or {}, "poses": {row["pose"]: row for row in earlier.get("poses") or []}}
    jobs = [{"motion": name, "minGapMm": min_gap, "contacts": contacts_for(data, name), "depth": depth, "focus": focus,
             **({"earlier": old["motions"].get(name) or {}} if earlier is not None else {})} for name in names]
    found = dict(zip(names, run.clearances(source, jobs, workers, assembly)))
    for name in names:
        found[name]["used"] = used_by_motion(assembly, name)
    settings = (min_gap, touch_gap, floor_z, ignore)
    rows = [at_pose(assembly, pose, settings, focus, None if earlier is None else old["poses"].get(pose) or {})
            for pose in ([None] if poses is None else []) + chosen(data["poses"], poses, "pose")]
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
