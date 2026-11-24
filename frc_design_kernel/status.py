"""Compare the records in a folder with the design source as it is now: which are current, which are stale, and why.

Every measurement job record and trial record lists what it used, with enough of each thing's identity to tell
whether it has changed. This module rebuilds those lists from the current source and states the differences as plain
facts. It does not say whether anything should be run again, and it reads no file bytes to decide: a record is
current when what its answer depends on is unchanged.
"""
import json
import time
from pathlib import Path

from .builder import identity
from .builder.assembly import build
from .measure import records
from .source.load import load
from .trials import inputs, ready

TRIALS = "trials.json"


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
    """{"records": [{"record", "state": "current" | "stale", "changes": [...]}], "readyFor3d": {...}, "seconds"} for a source
    and a folder of records: every job record under measurements/ and every trial in trials.json. "seconds" is how long
    the whole comparison took, the build included."""
    began = time.perf_counter()
    design = load(source)
    assembly = build(design)
    folder = Path(folder)
    rows = records.stored(assembly, folder)
    if (folder / TRIALS).is_file():
        rows += trial_rows(json.loads((folder / TRIALS).read_text(encoding="utf-8")), design, assembly)
    found = {"design": design.data["name"], "records": rows, "readyFor3d": ready.report(assembly)}
    return dict(found, seconds=time.perf_counter() - began)
