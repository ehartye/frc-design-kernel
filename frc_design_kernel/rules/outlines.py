"""Outlines as points in mm: a list of points, a rectangle, a hexagon or a circle.

    drawn(worker, entry, node)    its points about its own middle, or as they are listed: for an opening or inside a shape
    on_field(place, node)         its points on the field, for an alliance and a spot
    check(points)                 a DesignError for an outline that has no area or that crosses itself

A circle comes back as CIRCLE points on it. Between two of them the side is inside the true circle, by at most 0.1 % of its
radius (1 - cos 2.5 deg): 0.02 in for a circle 40 in wide.
"""
import itertools
import math

from ..errors import DesignError
from . import worth
from .alliances import Place

CIRCLE = 72


def drawn(worker, entry, node, mirrored):
    """The points of an outline about its own 0, 0. A mirrored one has left and right swapped."""
    node, _ = worker.unwrap(node)
    if isinstance(node, list):
        points = [tuple(number(worker, entry, one) for one in point) for point in node]
    elif isinstance(node, dict) and "rectangle" in node:
        a, b = (number(worker, entry, one) / 2 for one in worker.unwrap(node["rectangle"])[0])
        points = [(-a, -b), (a, -b), (a, b), (-a, b)]
    elif isinstance(node, dict) and "hexagon" in node:
        first = number(worker, entry, node["hexagon"]["points"], "angle")
        points = _round(number(worker, entry, node["hexagon"]["flats"]) / math.sqrt(3), 6, first)
    else:
        points = _round(number(worker, entry, node["circle"]) / 2, CIRCLE, 0)
    return [(x, -y) for x, y in points] if mirrored else points


def _round(radius, many, first):
    return [(radius * math.cos(math.radians(first + 360 * i / many)), radius * math.sin(math.radians(first + 360 * i / many))) for i in range(many)]


def number(worker, entry, node, kind="length"):
    return worth.one_number(worker.value(node, entry, kind))


def on_field(place, node):
    """The points of a record's own outline, where it is for an alliance and a spot."""
    points = drawn(place.worker, place.entry, node, False)
    if not isinstance(place.worker.unwrap(node)[0], list):     # listed points are in the field's frame already
        blue = Place(place.worker, place.entry, "blue", place.spot)
        x, y = (worth.one_number(one) for one in blue.point("at")[:2])
        turn = math.radians(worth.one_number(blue.faces()))
        sin, cos = math.sin(turn), math.cos(turn)
        points = [(x + u * cos - v * sin, y + u * sin + v * cos) for u, v in points]
    return [place.xy(*point) for point in points]


def check(points):
    """A DesignError for an outline that has no area or that crosses itself."""
    sides = list(zip(points, [*points[1:], points[0]]))
    if abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in sides)) < 1e-6:
        raise DesignError("", "has no area", "Check for a size of 0, or points on one line")
    if any(_cross(*one, *other) for one, other in itertools.combinations(sides, 2)):
        raise DesignError("", "crosses itself", "List its points in order, all the way round")


def _cross(a, b, c, d):
    """Whether two sides of an outline cross each other; sides that only touch, as two that meet do, do not."""
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0
