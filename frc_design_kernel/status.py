"""Compare the records in a folder with the design source as it is now: which are current, stale or missing, and why.

Every measurement job record, adjustment record and trial record lists what it used, with enough of each thing's identity to tell
whether it has changed. This module rebuilds those lists from the current source and states the differences as plain
facts. It does not say whether anything should be run again, and it reads no file bytes to decide: a record is
current when what its answer depends on is unchanged.
"""
import json
import time
from pathlib import Path

from .builder import identity
from .builder.assembly import build
from .errors import DesignError
from .measure import extremes, records
from .measure.search import DEFAULT_DEPTH
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


def differing(recorded, current):
    """The names whose entry is not the same in two tables; every name of the current one when nothing was recorded."""
    before = recorded or {}
    return [name for name in sorted(set(before) | set(current)) if identity.tidy(before.get(name)) != identity.tidy(current.get(name))]


def trial_changes(before, now):
    """What differs between a trial's recorded used block and what it would use now, as plain statements."""
    changes = compare_used({k: before[k] for k in ("solids", "parameters")}, {k: now[k] for k in ("solids", "parameters")})
    told = set(differing(before["solids"], now["solids"]))
    changes += [f'solid "{name}" changed shape or place' for name in differing(before.get("standing"), now["standing"]) if name not in told]
    if identity.tidy(before.get("poseOperations")) != identity.tidy(now.get("poseOperations")):
        changes.append("the trial's pose changed")
    changes += [f'the motion "{name}" changed' for name in differing(before.get("motions"), now["motions"])]
    if before.get("frames") != now["frames"]:
        changes.append("where its frames are changed")
    if identity.tidy(before.get("start")) != identity.tidy(now["start"]):
        changes.append("where it starts changed")
    changes += [f'custom code "{name}" changed' for name in differing(before.get("custom"), now["custom"])]
    changes += [f'adjustment "{name}" changed' for name in differing(before.get("adjustments"), now["adjustments"])]
    for path in sorted(set(before.get("varied") or {}) | set(now["varied"])):
        old, new = (before.get("varied") or {}).get(path), now["varied"].get(path, {})
        changes += [f'what it used with {path.split(".", 1)[-1]} at {setting} changed' for setting in differing(old, new)]
    return changes


class Trials:
    """The row of each trial in a campaign record, worked out once: a trial's row asks for the one it starts after."""

    def __init__(self, record, design, assembly, built):
        self.held, self.design, self.assembly, self.built, self.rows = record.get("trials", {}), design, assembly, built, {}

    def start(self, name, after):
        """(the recorded end a trial starts from or None, why that end is not known)."""
        if after is None:
            return None, []
        if after not in self.held:
            return None, [f'it starts where trial "{after}" ends, and that trial has no record']
        if after not in self.rows:
            self.row(after)
        if self.rows[after] is None or self.rows[after]["changes"]:
            return None, [f'it starts where trial "{after}" ends, and that record is not current']
        return self.held[after]["nominal"]["end"], []

    def row(self, name):
        from .trials import used
        self.rows[name], found, design = None, self.held[name], self.design
        if name not in design.data["trials"]:
            self.rows[name] = row(f'trial "{name}"', ["the trial is no longer in the source"])
            return
        case = inputs.case(design.data, design.data["trials"][name])
        changes = [f"the trial definition changed at {path}" for path in paths_that_differ(used.unnamed(found["definition"]), used.unnamed(case))[:8]]
        handed, unknown = self.start(name, case["piece"]["start"].get("after"))
        try:
            ends = {path: [float(setting) for setting in settings] for path, settings in (found["used"].get("varied") or {}).items()}
            now = used.what_it_used(design, self.assembly, name, case, found["saw"], handed, ends, self.built)
            before = found["used"] if not unknown else dict(found["used"], start=None)
            changes += trial_changes(before, now) + unknown
        except KeyError as missing:
            changes.append(f"a solid the trial cut is no longer there: {missing}")
        except DesignError as problem:
            changes.append(problem.problem)
        self.rows[name] = row(f'trial "{name}"', changes)


def trial_rows(record, design, assembly, built):
    trials = Trials(record, design, assembly, built)
    for name in trials.held:
        if name not in trials.rows:
            trials.row(name)
    return [trials.rows[name] for name in trials.held]


class Variants:
    """The design built with other parameter values, each set of values once."""

    def __init__(self, source):
        self.source, self.held = source, {}

    def __call__(self, overrides):
        key = tuple(sorted(overrides.items()))
        if key not in self.held:
            self.held[key] = build(load(self.source, overrides))
        return self.held[key]


def status(source, folder, min_gap=0.0, depth=DEFAULT_DEPTH):
    """{"records": [{"record", "state": "current" | "stale" | "missing", "changes": [...]}], "readyFor3d": {...}, "seconds"} for a
    source and a folder of records: every job record under measurements/, every mechanical adjustment the source declares
    and every trial in trials.json. min_gap and depth are what the ends of the adjustments are asked for: every motion and
    pose, against at least that gap. "seconds" is how long the whole comparison took, the builds included."""
    began = time.perf_counter()
    design = load(source)
    assembly = build(design)
    folder = Path(folder)
    built = Variants(source)
    rows = records.stored(assembly, folder) + extremes.rows(design, assembly, folder, min_gap, depth, built)
    if (folder / TRIALS).is_file():
        rows += trial_rows(json.loads((folder / TRIALS).read_text(encoding="utf-8")), design, assembly, built)
    found = {"design": design.data["name"], "records": rows, "readyFor3d": ready.report(assembly)}
    return dict(found, seconds=time.perf_counter() - began)
