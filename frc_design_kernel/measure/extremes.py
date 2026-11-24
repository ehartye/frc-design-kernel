"""Clearance at the ends of every mechanical adjustment, so it is known across the whole range the robot can be set to.

A mechanical adjustment (a slot, a shim, a spacer) is a design parameter with a range. The design is built at each
end of that range, everything else as drawn, and measured there. A setpoint or a spring moves no solid, so it has no
extremes to measure and is left out. Only the solids an end actually moves are new: a pair of two solids that are
shaped and sit exactly as they do as drawn, at every pose and through every motion, measures as it did, so only pairs
with a moved solid in them are measured, shared between worker processes like the rest of `measure`. Nothing is
judged; the closest pairs are reported.

Each adjustment's record holds the rules it was measured under and what it used: every solid as drawn and as each end
has it, and the declared contacts. So the status command can say whether it is of the design as it is now, and
whether it answers what is asked.
"""
import json

from ..builder import placement
from ..builder.assembly import build
from ..errors import DesignError
from ..source.load import load
from . import carry, clearance, run
from .search import DEFAULT_DEPTH
from .summary import chosen, contacts_for

SCHEMA, FILE = "frc-design-kernel/adjustments@2", "adjustments.json"
PARAMETERS = "parameters."


def brief(found):
    return {"closer": found["closer"], "unresolved": found["unresolved"], "closest": found["closest"]}


def mechanical(data):
    """{adjustment: entry} for the mechanical adjustments: the ones with ends to measure."""
    return {name: entry for name, entry in data.get("adjustments", {}).items() if entry["kind"] == "mechanical" and entry["input"].startswith(PARAMETERS)}


def asked(data, min_gap, depth, motions=None, poses=None):
    """The rules of a measurement: the gap, the search depth, and the motions and poses measured (None is the pose as drawn)."""
    listed = ([None] if poses is None else []) + sorted(chosen(data["poses"], poses, "pose"))
    return {"minGapMm": float(min_gap), "depth": depth, "motions": sorted(chosen(data["motions"], motions, "motion")), "poses": listed}


def identities(assembly, motions=None, poses=None):
    """{solid: identity} over a set of motions and poses (all of them by default): its shape figures, and its group's whole
    placement along each motion and at each pose."""
    data, figures, groups = assembly.data, carry.figures(assembly), {}
    along = {motion: placement.motion_stages(data, motion) for motion in (data["motions"] if motions is None else motions)}
    held = [placement.pose_stages(data, pose) for pose in ([None, *sorted(data["poses"])] if poses is None else poses)]
    for group in data["groups"]:
        groups[group] = carry.digest([{motion: stages.get(group, []) for motion, stages in along.items()}, [stages.get(group, []) for stages in held]])
    return {name: carry.digest([figures[name], groups[solid.group]]) for name, solid in assembly.solids.items()}


def contacts(data, names, motions):
    """One digest of the pairs meant to touch: along each motion measured and at a pose."""
    among = lambda pairs: sorted(sorted(pair) for pair in pairs if set(pair) <= set(names))
    return carry.digest([{motion: among(contacts_for(data, motion)) for motion in motions}, among(contacts_for(data))])


def used(nominal, ends, rules):
    """What an adjustment's answer rests on: every solid as drawn, the solids each end has otherwise, and the contacts.
    ends is {setting: the design built there}."""
    drawn = identities(nominal, rules["motions"], rules["poses"])
    found = {setting: identities(assembly, rules["motions"], rules["poses"]) for setting, assembly in ends.items()}
    return {"drawn": drawn, "ends": {f"{setting:.12g}": {name: value for name, value in sorted(at.items()) if drawn.get(name) != value} for setting, at in found.items()},
            "contacts": contacts(nominal.data, nominal.solids, rules["motions"])}


def at_extremes(source, min_gap=0.0, depth=DEFAULT_DEPTH, workers=None, motions=None, poses=None):
    """{adjustment: {"parameter", "kind", "range", "inputs", "used", "settings": [{"setting", "moves", "motions": {...}, "poses": [...]}]}}.

    One entry for each mechanical adjustment of a design parameter. Each setting is one end of its range. "moves"
    names the solids that end moves or shapes otherwise; every motion's clearance and every pose's close pairs are given
    in brief for the pairs with one of them in it: the pairs closer than min_gap, the pairs not settled, and the closest
    pair. motions and poses name a subset, as for `measure` (None is all of them; the as-drawn pose only then).
    """
    design = load(source)
    nominal = build(design)
    data, drawn = nominal.data, identities(nominal)
    rules = asked(data, min_gap, depth, motions, poses)
    out, jobs, slots = {}, [], []
    for name, entry in mechanical(data).items():
        parameter, settings, ends = entry["input"][len(PARAMETERS):], [], {}
        for setting in entry["range"]:
            assembly = ends[setting] = build(load(source, {parameter: setting}))
            found = identities(assembly)
            moved = sorted(n for n in found if found[n] != drawn.get(n))
            row = {"setting": setting, "moves": moved, "motions": {},
                   "poses": [{"pose": pose, **brief(clearance.at_pose(assembly, pose, min_gap, contacts_for(assembly.data), focus=set(moved)))}
                             for pose in rules["poses"]]}
            for motion in chosen(data["motions"], motions, "motion"):
                jobs.append({"motion": motion, "minGapMm": min_gap, "contacts": contacts_for(assembly.data, motion), "depth": depth,
                             "parameters": {parameter: setting}, "focus": moved})
                slots.append((row, motion))
            settings.append(row)
        out[name] = {"parameter": parameter, "kind": entry["kind"], "range": entry["range"], "inputs": {"rules": rules},
                     "used": used(nominal, ends, rules), "settings": settings}
    for (row, motion), found in zip(slots, run.clearances(source, jobs, workers) if jobs else []):
        row["motions"][motion] = brief(found)
    return out


def narrower(recorded, wanted):
    """Why a measurement does not answer what is asked: a smaller gap, a shallower search, or a motion or pose left out."""
    found = []
    if recorded["minGapMm"] < wanted["minGapMm"]:
        found.append(f"it was measured against a gap of {recorded['minGapMm']:g} mm, and {wanted['minGapMm']:g} mm is asked")
    if recorded["depth"] < wanted["depth"]:
        found.append(f"it was searched to depth {recorded['depth']}, and depth {wanted['depth']} is asked")
    found += [f'the motion "{name}" was not measured' for name in wanted["motions"] if name not in recorded["motions"]]
    return found + [("the pose as drawn" if pose is None else f'the pose "{pose}"') + " was not measured" for pose in wanted["poses"] if pose not in recorded["poses"]]


def differs(before, now, at=""):
    return [f'solid "{name}" changed{at}' for name in sorted(set(before) | set(now)) if before.get(name) != now.get(name)]


def changes(held, entry, nominal, wanted, built):
    """What differs between an adjustment's record and the design and the request as they are now, as plain statements."""
    rules, parameter = held["inputs"]["rules"], entry["input"][len(PARAMETERS):]
    found = narrower(rules, wanted)
    if held["parameter"] != parameter:
        found.append(f'it changes the parameter "{parameter}", not "{held["parameter"]}"')
    if carry.plain(held["range"]) != carry.plain(entry["range"]):
        found.append(f"its range changed: {held['range']} to {entry['range']}")
    gone = sorted(set(rules["motions"]) - set(nominal.data["motions"])) + sorted(p for p in rules["poses"] if p is not None and p not in nominal.data["poses"])
    if gone:
        return found + [f'"{name}", which it was measured along, is no longer in the source' for name in gone]
    now = used(nominal, {setting: built({parameter: setting}) for setting in entry["range"]}, rules)
    drawn = differs(held["used"]["drawn"], now["drawn"])
    found += drawn
    for setting in sorted(set(held["used"]["ends"]) & set(now["ends"]), key=float):
        found += [text for text in differs(held["used"]["ends"][setting], now["ends"][setting], f" at {setting}") if text.rsplit(" at ", 1)[0] not in drawn]
    if held["used"]["contacts"] != now["contacts"]:
        found.append("the declared contacts changed")
    return found


def rows(design, nominal, folder, min_gap, depth, built):
    """For each mechanical adjustment the source declares, whether its record in folder is current, stale (and why) or missing,
    and for each record of an adjustment that is gone, that it is. built gives the design with other parameter values."""
    path, declared = folder / FILE, mechanical(design.data)
    try:
        held = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema": SCHEMA, "adjustments": {}}
    except ValueError:
        held = {}
    known = isinstance(held, dict) and held.get("schema") == SCHEMA
    stored = held.get("adjustments", {}) if known else {}
    wanted, found = asked(design.data, min_gap, depth), []
    for name in sorted(set(declared) | set(stored)):
        if name not in declared:
            said = ["the adjustment is no longer in the source"]
        elif not known:
            said = [f"it is not a {SCHEMA} record"]
        elif name not in stored:
            said = ["its ends have not been measured"]
        else:
            try:
                said = changes(stored[name], declared[name], nominal, wanted, built)
            except DesignError as problem:
                said = [problem.problem]
        state = "missing" if known and name not in stored else "stale" if said else "current"
        found.append({"record": f'adjustment "{name}"', "file": FILE, "state": state, "changes": said})
    return found
