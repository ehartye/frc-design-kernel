"""Smooth movement from one rigid pose to the next: a turn about a fixed line plus a slide along it (a screw motion).

Any two placements of a rigid body are joined by exactly one such movement. For an arm drawn at two angles about a
pivot it is the swing about that pivot. For two placements with the same heading it is a straight slide.
"""
import math

from . import matrix as mx


def axis_angle(m):
    """(unit axis, angle in degrees from 0 to 180) of the turning part of a transform."""
    cosine = max(-1.0, min(1.0, (m[0] + m[5] + m[10] - 1) / 2))
    angle = math.acos(cosine)
    twist = (m[9] - m[6], m[2] - m[8], m[4] - m[1])
    if mx.length(twist) > 1e-6:
        return mx.unit(twist), math.degrees(angle)
    if angle < 1e-3:
        return (0.0, 0.0, 1.0), 0.0
    # A half turn: the axis is the direction the turn leaves unchanged, read from the largest diagonal entry.
    diagonal = (m[0], m[5], m[10])
    i = diagonal.index(max(diagonal))
    column = [(m[4 * r + i] + (1.0 if r == i else 0.0)) for r in range(3)]
    return mx.unit(column), 180.0


def decompose(start, end):
    """The screw that carries start to end: (point on the axis, unit axis, turn in degrees, slide vector along the axis).

    With no turn the point is None and the slide is the whole straight movement.
    """
    step = mx.compose(end, mx.inverse(start))
    shift = (step[3], step[7], step[11])
    axis, angle = axis_angle(step)
    if angle < 1e-9:
        return None, axis, 0.0, shift
    along = mx.scale(axis, mx.dot(shift, axis))
    across = mx.sub(shift, along)
    half = math.radians(angle) / 2
    point = mx.scale(mx.add(across, mx.scale(mx.cross(axis, across), math.cos(half) / math.sin(half))), 0.5)
    return point, axis, angle, along


def between(start, end, s):
    """The placement a fraction s of the way from start to end along the screw motion that joins them."""
    point, axis, angle, slide = decompose(start, end)
    if point is None:
        return mx.compose(mx.translation(mx.scale(slide, s)), start)
    return mx.chain([start, mx.rotation(point, axis, angle * s), mx.translation(mx.scale(slide, s))])


def through(placements, t):
    """The placement at stroke fraction t along a list of placements that share the stroke evenly."""
    spans = len(placements) - 1
    index = min(int(max(0.0, t) * spans), spans - 1)
    return between(placements[index], placements[index + 1], max(0.0, min(1.0, t)) * spans - index)
