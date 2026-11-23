"""Clearance at the ends of every mechanical adjustment, so it is known across the whole range the robot can be set to.

A mechanical adjustment (a slot, a shim, a spacer) is a design parameter with a range. The design is built at each
end of that range, everything else as drawn, and measured there. A setpoint or a spring moves no solid, so it has no
extremes to measure and is left out. Only the solids an end actually moves are new: a pair of two solids that sit
exactly where they sit as drawn, at every pose and through every motion, measures as it did, so only pairs with a
moved solid in them are measured, shared between worker processes like the rest of `measure`. Nothing is judged;
the closest pairs are reported.
"""
from ..builder import placement
from ..builder.assembly import build
from ..kernel import props
from ..source.load import load
from . import clearance, run
from .search import DEFAULT_DEPTH
from .summary import chosen, contacts_for

PARAMETERS = "parameters."
SAMPLES = (0.0, 0.25, 0.5, 0.75, 1.0)       # stroke fractions a moved group is compared at


def brief(found):
    return {"closer": found["closer"], "unresolved": found["unresolved"], "closest": found["closest"]}


def where(assembly):
    """Each solid's drawn size and its group's place at every pose and along every motion: what an adjustment can change."""
    data = assembly.data
    group_of = {s["name"]: s["group"] for s in data["solids"] + data["fixtures"]}
    places = [placement.at_pose(data, pose) for pose in [None, *data["poses"]]]
    places += [placement.at_motion(data, motion, t) for motion in data["motions"] for t in SAMPLES]
    drawn = assembly.at_pose(None)
    return {name: (round(props.volume(drawn[name]), 6), tuple(round(v, 6) for v in props.bounds(drawn[name])),
                   tuple(tuple(round(v, 6) for v in place[group_of[name]]) for place in places)) for name in group_of}


def at_extremes(source, min_gap=0.0, depth=DEFAULT_DEPTH, workers=None, motions=None, poses=None):
    """{adjustment: {"parameter", "kind", "range", "settings": [{"setting", "moves", "motions": {...}, "poses": [...]}]}}.

    One entry for each mechanical adjustment of a design parameter. Each setting is one end of its range. "moves"
    names the solids that end moves; every motion's clearance and every pose's close pairs are given in brief for the
    pairs with one of them in it: the pairs closer than min_gap, the pairs not settled, and the closest pair. motions
    and poses name a subset, as for `measure` (None is all of them; the as-drawn pose only then).
    """
    design = load(source)
    nominal = build(design)
    data, drawn = nominal.data, where(nominal)
    names = chosen(data["motions"], motions, "motion")
    pose_names = ([None] if poses is None else []) + chosen(data["poses"], poses, "pose")
    out, jobs, slots = {}, [], []
    for name, entry in design.data.get("adjustments", {}).items():
        if entry["kind"] != "mechanical" or not entry["input"].startswith(PARAMETERS):
            continue
        parameter = entry["input"][len(PARAMETERS):]
        settings = []
        for setting in entry["range"]:
            assembly = build(load(source, {parameter: setting}))
            found = where(assembly)
            moved = sorted(n for n in found if found[n] != drawn.get(n))
            row = {"setting": setting, "moves": moved, "motions": {},
                   "poses": [{"pose": pose, **brief(clearance.at_pose(assembly, pose, min_gap, contacts_for(assembly.data), focus=set(moved)))}
                             for pose in pose_names]}
            for motion in names:
                jobs.append({"motion": motion, "minGapMm": min_gap, "contacts": contacts_for(assembly.data, motion), "depth": depth,
                             "parameters": {parameter: setting}, "focus": moved})
                slots.append((row, motion))
            settings.append(row)
        out[name] = {"parameter": parameter, "kind": entry["kind"], "range": entry["range"], "settings": settings}
    for (row, motion), found in zip(slots, run.clearances(source, jobs, workers) if jobs else []):
        row["motions"][motion] = brief(found)
    return out
