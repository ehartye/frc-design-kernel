"""A body's whole movement as a list of stages, applied in order, with a proven limit on how fast any point moves.

A stage is one of:
    ("fixed", transform)            a placement that does not change with the stroke
    ("ops", [operations])           motion operations, each evaluated at the stroke fraction t
    ("through", [transforms])       a smooth movement through placements that share the stroke evenly

The speed limit is what lets a clearance check prove that nothing was missed between two sampled fractions: a point
that moves at most `speed` millimetres per unit of t cannot close a gap of g in less than g / speed of the stroke.
"""
import itertools
import json
import math

from . import matrix as mx
from . import ops as motion_ops
from . import paths, screw


def at(stages, t):
    """The transform of a stage list at stroke fraction t."""
    total = mx.IDENTITY
    for kind, value in stages:
        if kind == "fixed":
            step = value
        elif kind == "ops":
            step = motion_ops.at(value, t)
        else:
            step = screw.through(value, t)
        total = mx.compose(step, total)
    return total


def tidy(stages):
    """The same movement with stages that do nothing removed."""
    kept = []
    for kind, value in stages:
        if kind == "fixed" and mx.is_identity(value):
            continue
        if kind == "ops" and not value:
            continue
        if kind == "through" and all(mx.gap(value[0], other) == 0 for other in value[1:]):
            kind, value = "fixed", value[0]
            if mx.is_identity(value):
                continue
        kept.append((kind, value))
    return kept


def moving_part(stages):
    """The stages from the first one that changes with t. Two bodies with the same moving part keep their relative pose."""
    stages = tidy(stages)
    for i, (kind, _) in enumerate(stages):
        if kind != "fixed":
            return stages[i:]
    return []


def lead(stages):
    """The placement a body holds before its moving part begins: its leading fixed stages as one transform."""
    total = mx.IDENTITY
    for kind, value in tidy(stages):
        if kind != "fixed":
            break
        total = mx.compose(value, total)
    return total


def signature(stages):
    """Text that is equal for two bodies exactly when their moving parts are the same."""
    return json.dumps(moving_part(stages), sort_keys=True)


def corners(box):
    return list(itertools.product(*[(box[i], box[i + 3]) for i in range(3)]))


def reach(points, origin):
    return max(math.dist(p, origin) for p in points)


def op_speed(op, points, so_far):
    """A limit on the speed one operation gives a point, in mm per unit of t.

    points are where the body's box corners are at t = 0 before this operation. Earlier stages may have carried a
    point at most so_far away from there, which lengthens the lever arm of a turn by at most that much.
    """
    kind = op["kind"]
    if kind == "translation":
        return mx.length(op["travelMm"])
    if kind == "gravity-drop":
        return op["fallMm"] * (1 + op["quadraticFraction"])
    if kind == "rotation":
        return abs(math.radians(op["travelDeg"])) * (reach(points, op["originMm"]) + so_far)
    return paths.length(op["curve"], op["throughMm"])


def through_speed(placements, points, so_far):
    """A limit on the speed of a movement through placements: the fastest of its screw motions, each run in 1/spans of the stroke."""
    spans = len(placements) - 1
    fastest = 0.0
    for start, end in zip(placements, placements[1:]):
        point, _, angle, slide = screw.decompose(start, end)
        speed = mx.length(slide)
        if point is not None:
            speed += math.radians(angle) * (reach([mx.apply(start, p) for p in points], point) + so_far)
        fastest = max(fastest, speed)
    return spans * fastest


def speed_limit(stages, box):
    """A proven limit on the speed of every point of a body, in mm per unit of t, over the whole stroke.

    box is the body's bounding box before the first of these stages. The limit is conservative: the real speed is
    never higher, and is often lower. A tighter box gives a tighter limit, so pass moving_part(stages) with the box
    of the body where it stands when the moving part begins.
    """
    points, limit = corners(box), 0.0
    for kind, value in stages:
        if kind == "fixed":
            points = [mx.apply(value, p) for p in points]
        elif kind == "ops":
            for op in value:
                limit += op_speed(op, points, limit)
        else:
            limit += through_speed(value, points, limit)
            points = [mx.apply(value[0], p) for p in points]
    return limit


def straight_travel(stages):
    """The total travel when the moving part is translations only (as [x, y, z]), or None for any other movement."""
    listed = [op for kind, value in moving_part(stages) for op in (value if kind == "ops" else [None])]
    if any(op is None or op["kind"] != "translation" for op in listed):
        return None
    return [sum(op["travelMm"][i] for op in listed) for i in range(3)]


def axis_laws(stages):
    """For a moving part made of operations only: (linear, square, unchanged) per axis, or None.

    Along axis i the body's shift is linear[i] * t + square[i] * t * t, and unchanged[i] says no turn alters that
    axis's coordinates. A path operation, a through stage or a later fixed stage gives None.
    """
    moving = moving_part(stages)
    if any(kind != "ops" for kind, _ in moving):
        return None
    linear, square, unchanged = [0.0] * 3, [0.0] * 3, [True] * 3
    for op in (op for _, listed in moving for op in listed):
        if op["kind"] == "translation":
            linear = [a + b for a, b in zip(linear, op["travelMm"])]
        elif op["kind"] == "gravity-drop":
            linear[2] -= op["fallMm"] * (1 - op["quadraticFraction"])
            square[2] -= op["fallMm"] * op["quadraticFraction"]
        elif op["kind"] == "rotation":
            unchanged = [ok and all(op["axis"][k] == 0 for k in range(3) if k != i) for i, ok in enumerate(unchanged)]
        else:
            return None
    return linear, square, unchanged
