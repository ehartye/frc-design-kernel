"""The motion vocabulary: a move is a list of operations, applied in order, each evaluated at a stroke fraction t.

    {"kind": "translation", "travelMm": [x, y, z]}
    {"kind": "rotation", "originMm": [x, y, z], "axis": [x, y, z], "travelDeg": d}
    {"kind": "gravity-drop", "fallMm": h, "quadraticFraction": w}
    {"kind": "path", "throughMm": [[x, y, z], ...], "curve": "straight" | "arc" | "smooth"}
    {"kind": "path", ..., "turnDeg": [a, ...], "turnAxis": [x, y, z]}      a path that turns as it goes

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
        slide = mx.translation(mx.sub(paths.position(op["curve"], points, t), points[0]))
        if "turnDeg" not in op:
            return slide
        angles = op["turnDeg"]     # the body turns about the followed point, by the angle gained since the first point
        return mx.compose(slide, mx.rotation(points[0], op["turnAxis"], paths.turn(op["curve"], points, angles, t) - angles[0]))
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
    _check_turn(op, place, len(points))


def _check_turn(op, place, count):
    if "turnDeg" not in op and "turnAxis" not in op:
        return
    if "turnDeg" not in op:
        raise DesignError(place, 'turnAxis is given without "turnDeg"', 'Add "turnDeg", one angle per point, or remove "turnAxis" for a path that slides')
    if "turnAxis" not in op:
        raise DesignError(place, 'a path with "turnDeg" needs a "turnAxis"', 'Give the direction the body turns about, such as [0, 1, 0]')
    if len(op["turnDeg"]) != count:
        raise DesignError(place, f"turnDeg has {len(op['turnDeg'])} angles for {count} points", "Give one angle per point of throughMm")
    if mx.length(op["turnAxis"]) == 0:
        raise DesignError(place, "the turnAxis is [0, 0, 0]", "Give the direction the body turns about, such as [0, 1, 0]")
