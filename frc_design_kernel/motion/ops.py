"""The motion vocabulary: a move is a list of operations, applied in order, each evaluated at a stroke fraction t.

    {"kind": "translation", "travelMm": [x, y, z]}
    {"kind": "rotation", "originMm": [x, y, z], "axis": [x, y, z], "travelDeg": d}
    {"kind": "gravity-drop", "fallMm": h, "quadraticFraction": w}
    {"kind": "path", "throughMm": [[x, y, z], ...], "curve": "straight" | "arc" | "smooth"}

A start pose is the same list applied in full (t = 1).
"""
from ..errors import DesignError
from . import matrix as mx
from . import paths

OLD_KINDS = ("translation", "rotation", "gravity-drop")
KINDS = (*OLD_KINDS, "path")


def one(op, t):
    """The transform of one operation at stroke fraction t."""
    kind = op["kind"]
    if kind == "translation":
        return mx.translation(mx.scale(op["travelMm"], t))
    if kind == "rotation":
        return mx.rotation(op["originMm"], op["axis"], op["travelDeg"] * t)
    if kind == "gravity-drop":
        h, w = op["fallMm"], op["quadraticFraction"]
        return mx.translation((0.0, 0.0, -h * ((1 - w) * t + w * t * t)))
    if kind == "path":
        points = op["throughMm"]
        return mx.translation(mx.sub(paths.position(op["curve"], points, t), points[0]))
    raise DesignError("", f'unknown motion kind "{kind}"', f"Use one of: {', '.join(KINDS)}")


def at(ops, t=1.0):
    """The transform of a whole list of operations at stroke fraction t (t = 1 applies them in full)."""
    return mx.chain(one(op, t) for op in ops)


def check(ops, where):
    """Raise a DesignError for an operation whose numbers cannot describe a movement."""
    for i, op in enumerate(ops):
        place = f"{where}[{i}]"
        kind = op.get("kind")
        if kind == "rotation" and mx.length(op["axis"]) == 0:
            raise DesignError(place, "the rotation axis is [0, 0, 0]", "Give the direction of the turning axis, such as [0, 1, 0]")
        if kind == "gravity-drop":
            if op["fallMm"] < 0:
                raise DesignError(place, "fallMm is negative", "Give the fall as a positive distance down")
            if not 0 <= op["quadraticFraction"] <= 1:
                raise DesignError(place, "quadraticFraction must be from 0 to 1", "Use 1 for a free fall from rest and 0 for a steady descent")
        if kind == "path":
            _check_path(op, place)


def _check_path(op, place):
    points = [tuple(p) for p in op["throughMm"]]
    if any(mx.length(mx.sub(a, b)) < 1e-9 for a, b in zip(points, points[1:])):
        raise DesignError(place, "two neighbouring path points are the same", "Remove the repeated point")
    if op["curve"] == "arc":
        if len(points) != 3:
            raise DesignError(place, f"an arc needs exactly 3 points, not {len(points)}", "Give the start, a point on the way and the end")
        if paths.circle_through(*points) is None:
            raise DesignError(place, "the three arc points are in a straight line", 'Use "curve": "straight", or move the middle point')
