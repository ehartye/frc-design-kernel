"""Clearance at the ends of every mechanical adjustment, so it is known across the whole range the robot can be set to.

A mechanical adjustment (a slot, a shim, a spacer) is a design parameter with a range. The design is built at each
end of that range, everything else as drawn, and every motion and pose is measured there in full, shared between the
bench's worker processes. A setpoint or a spring moves no solid, so it has no ends to measure. Nothing is judged; the
closest pairs are reported.
"""
from contextlib import closing

from ..errors import DesignError
from . import jobs as kinds
from .run import Ask
from .search import DEFAULT_DEPTH
from .summary import chosen

PARAMETERS = "parameters."


def brief(found):
    return {"closer": found["closer"], "unresolved": found["unresolved"], "closest": found["closest"]}


def has_ends(entry):
    return entry["kind"] == "mechanical" and entry["input"].startswith(PARAMETERS)


def asked_for(table, names):
    """The adjustments to measure: those named, or every one that has ends."""
    for name in chosen(table, names, "adjustment") if names is not None else ():
        if not has_ends(table[name]):
            what = f"is a {table[name]['kind']}, which moves no solid" if table[name]["kind"] != "mechanical" else "does not change a design parameter"
            raise DesignError(f'adjustments "{name}"', f'the adjustment "{name}" {what}', "Name a mechanical adjustment of a design parameter")
    return [name for name, entry in table.items() if has_ends(entry) and (names is None or name in names)]


def at_extremes(bench, min_gap=0.0, depth=DEFAULT_DEPTH, motions=None, poses=None, adjustments=None, report=None):
    """{adjustment: {"parameter", "kind", "range", "settings": [{"setting", "motions": {...}, "poses": [...]}]}}.

    One entry for each mechanical adjustment of a design parameter, or for those named in adjustments. Each setting is
    one end of its range. Every motion's clearance and every pose's close pairs are given in brief: the pairs closer
    than min_gap, the pairs not settled, and the closest pair. motions and poses name a subset, as for `measure` (None
    is all of them; the as-drawn pose only then). report, when given, hears each piece as it finishes: {"adjustment",
    "setting", "motion" or "pose", "found"}; an error raised there stops the run.
    """
    data, table = bench.design.data, bench.design.data.get("adjustments", {})
    targets = [("motion", name) for name in chosen(data["motions"], motions, "motion")]
    targets += [("pose", name) for name in ([None] if poses is None else []) + chosen(data["poses"], poses, "pose")]
    ends = [(name, setting) for name in asked_for(table, adjustments) for setting in table[name]["range"]]
    asks, places = [], []
    for name, setting in ends:
        for kind, target in targets:
            job = kinds.normalized(data, {"kind": "clearance", kind: target, "minGapMm": min_gap, **({"depth": depth} if kind == "motion" else {})})
            asks.append(Ask(job, {"adjustment": name, "setting": setting, "job": kinds.job_id(job)}, None, {table[name]["input"][len(PARAMETERS):]: setting}))
            places.append((name, setting, kind, target))
    found = {}
    with closing(bench.answers(asks)) as given:
        for index, answer in given:
            name, setting, kind, target = places[index]
            found[index] = brief(answer)
            if report:
                report({"adjustment": name, "setting": setting, kind: target, "found": found[index]})
    out = {name: {"parameter": table[name]["input"][len(PARAMETERS):], "kind": table[name]["kind"], "range": table[name]["range"],
                  "settings": [{"setting": setting, "motions": {}, "poses": []} for setting in table[name]["range"]]} for name, _ in ends}
    for index, (name, setting, kind, target) in enumerate(places):
        row = out[name]["settings"][table[name]["range"].index(setting)]
        if kind == "motion":
            row["motions"][target] = found[index]
        else:
            row["poses"].append({"pose": target, **found[index]})
    return out
