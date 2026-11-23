"""Clearance at the ends of every mechanical adjustment, so it is known across the whole range the robot can be set to.

A mechanical adjustment (a slot, a shim, a spacer) is a design parameter with a range. The design is built at each
end of that range, everything else as drawn, and measured there. Nothing is judged; the closest pairs are reported.
"""
from ..builder.assembly import build
from ..source.load import load
from . import clearance
from .search import DEFAULT_DEPTH
from .summary import contacts_for

PARAMETERS = "parameters."


def brief(found):
    return {"closer": found["closer"], "unresolved": found["unresolved"], "closest": found["closest"]}


def at_extremes(source, min_gap=0.0, depth=DEFAULT_DEPTH):
    """{adjustment: {"parameter", "kind", "settings": [{"setting", "motions": {...}, "poses": [...]}]}} for each adjustment of a design parameter.

    Each setting is one end of the adjustment's range. For it, every motion's clearance and every pose's close pairs
    are given in brief: the pairs closer than min_gap, the pairs not settled, and the closest pair.
    """
    design = load(source)
    out = {}
    for name, entry in design.data["adjustments"].items():
        if not entry["input"].startswith(PARAMETERS):
            continue
        parameter = entry["input"][len(PARAMETERS):]
        settings = []
        for setting in entry["range"]:
            assembly = build(load(source, {parameter: setting}))
            data = assembly.data
            settings.append({"setting": setting,
                             "motions": {m: brief(clearance.along(assembly, m, min_gap, contacts_for(data, m), depth=depth)) for m in data["motions"]},
                             "poses": [{"pose": pose, **brief(clearance.at_pose(assembly, pose, min_gap, contacts_for(data)))} for pose in [None, *data["poses"]]]})
        out[name] = {"parameter": parameter, "kind": entry["kind"], "range": entry["range"], "settings": settings}
    return out
