"""Compare the records in a folder with the design source as it is now: which are current, which are stale, and why.

Every measurement and trial record lists what it used, with enough of each thing's identity to tell whether it has
changed. This module rebuilds those lists from the current source and states the differences as plain facts. It
does not say whether anything should be run again.
"""
import json
from pathlib import Path

from .builder import identity
from .builder.assembly import build
from .measure import summary
from .source.load import load
from .trials import inputs, ready

MEASUREMENTS, TRIALS = "measurements.json", "trials.json"


def paths_that_differ(old, new, at=""):
    """Dotted paths where two plain structures differ, ignoring notes."""
    if isinstance(old, dict) and isinstance(new, dict):
        found = []
        for key in sorted(set(old) | set(new)):
            if key != "note":
                found += paths_that_differ(old.get(key), new.get(key), f"{at}.{key}" if at else key)
        return found
    return [] if identity.tidy(old) == identity.tidy(new) else [at]


def compare_used(recorded, current):
    """What changed between two "used" blocks, as plain statements."""
    changes = identity.differences(recorded.get("solids", {}), current.get("solids", {}), "solid")
    for key, what in (("parameters", "parameter"), ("poses", "pose"), ("groups", "group")):
        changes += identity.differences(recorded.get(key, {}), current.get(key, {}), what)
    for key in sorted((set(recorded) | set(current)) - {"solids", "parameters", "poses", "groups"}):
        if identity.tidy(recorded.get(key)) != identity.tidy(current.get(key)):
            changes.append(f"{key} changed")
    return changes


def row(name, changes):
    return {"record": name, "state": "stale" if changes else "current", "changes": changes}


def measurement_rows(record, assembly):
    rows = []
    for name, found in record.get("motions", {}).items():
        gone = name not in assembly.data["motions"]
        rows.append(row(f'clearance along "{name}"', ["the motion is no longer in the source"] if gone
                        else compare_used(found.get("used", {}), summary.used_by_motion(assembly, name, found.get("absent", ())))))
    for found in record.get("poses", []):
        pose = found["pose"]
        label = f'measures at the pose "{pose}"' if pose else "measures as drawn"
        gone = pose is not None and pose not in assembly.data["poses"]
        rows.append(row(label, ["the pose is no longer in the source"] if gone else compare_used(found.get("used", {}), summary.used_by_pose(assembly, pose))))
    return rows


def trial_rows(record, design, assembly):
    from .trials.campaign import what_it_used
    rows = []
    for name, found in record.get("trials", {}).items():
        if name not in design.data["trials"]:
            rows.append(row(f'trial "{name}"', ["the trial is no longer in the source"]))
            continue
        case = inputs.case(design.data, design.data["trials"][name])
        changes = [f"the trial definition changed at {path}" for path in paths_that_differ(found["definition"], case)[:8]]
        try:
            now = what_it_used(design, assembly, name, case, found["saw"])
            changes += compare_used({k: found["used"][k] for k in ("solids", "parameters")}, {k: now[k] for k in ("solids", "parameters")})
            if identity.tidy(found["used"].get("poseOperations")) != identity.tidy(now.get("poseOperations")):
                changes.append("the trial's pose changed")
            before = found["used"].get("motions") or {}
            changes += [f'the motion "{key}" changed' for key in sorted(now["motions"]) if identity.tidy(before.get(key)) != identity.tidy(now["motions"][key])]
        except KeyError as missing:
            changes.append(f"a solid the trial cut is no longer there: {missing}")
        rows.append(row(f'trial "{name}"', changes))
    return rows


def status(source, folder):
    """{"records": [{"record", "state": "current" | "stale", "changes": [...]}], "readyFor3d": {...}} for a source and a folder of records."""
    design = load(source)
    assembly = build(design)
    folder, rows = Path(folder), []
    if (folder / MEASUREMENTS).is_file():
        rows += measurement_rows(json.loads((folder / MEASUREMENTS).read_text(encoding="utf-8")), assembly)
    if (folder / TRIALS).is_file():
        rows += trial_rows(json.loads((folder / TRIALS).read_text(encoding="utf-8")), design, assembly)
    return {"design": design.data["name"], "records": rows, "readyFor3d": ready.report(assembly)}
