"""Curves through points for the "path" operation: straight, arc and smooth. Each gives a position by length fraction."""
import functools
import math

from . import matrix as mx

SAMPLES_PER_SPAN = 48    # straight pieces per span of a smooth curve when measuring its length


def by_length(points, t):
    """The point a fraction t of the way along a chain of straight pieces, measured by length."""
    spans = [mx.length(mx.sub(b, a)) for a, b in zip(points, points[1:])]
    target = max(0.0, min(1.0, t)) * sum(spans)
    for a, b, span in zip(points, points[1:], spans):
        if target <= span and span > 0:
            return mx.add(a, mx.scale(mx.sub(b, a), target / span))
        target -= span
    return points[-1]


def circle_through(p0, p1, p2):
    """(centre, axis, total turn in degrees) of the arc from p0 past p1 to p2, or None when they are in a line."""
    a, b = mx.sub(p1, p0), mx.sub(p2, p0)
    normal = mx.cross(a, b)    # the travel from p0 past p1 to p2 is counter-clockwise about this
    if mx.length(normal) <= 1e-9 * max(1.0, mx.length(a) * mx.length(b)):
        return None
    lean = mx.sub(mx.scale(b, mx.dot(a, a)), mx.scale(a, mx.dot(b, b)))
    centre = mx.add(p0, mx.scale(mx.cross(lean, normal), 1 / (2 * mx.dot(normal, normal))))
    axis = mx.unit(normal)
    start, end = mx.sub(p0, centre), mx.sub(p2, centre)
    turn = math.degrees(math.atan2(mx.dot(mx.cross(start, end), axis), mx.dot(start, end))) % 360
    return centre, axis, turn or 360.0


def arc(points, t):
    centre, axis, turn = circle_through(*points)
    return mx.apply(mx.rotation(centre, axis, turn * t), points[0])


def _span(p0, p1, p2, p3, u):
    """A point on the centripetal Catmull-Rom span from p1 to p2, at u from 0 to 1."""
    t0 = 0.0
    t1 = t0 + math.sqrt(mx.length(mx.sub(p1, p0)))
    t2 = t1 + math.sqrt(mx.length(mx.sub(p2, p1)))
    t3 = t2 + math.sqrt(mx.length(mx.sub(p3, p2)))
    t = t1 + u * (t2 - t1)

    def mix(a, b, ta, tb):
        return mx.add(mx.scale(a, (tb - t) / (tb - ta)), mx.scale(b, (t - ta) / (tb - ta)))

    a1, a2, a3 = mix(p0, p1, t0, t1), mix(p1, p2, t1, t2), mix(p2, p3, t2, t3)
    return mix(mix(a1, a2, t0, t2), mix(a2, a3, t1, t3), t1, t2)


@functools.lru_cache(maxsize=64)
def smooth_points(points):
    """A smooth curve through every point, as a fine chain of straight pieces."""
    first = mx.sub(mx.scale(points[0], 2), points[1])
    last = mx.sub(mx.scale(points[-1], 2), points[-2])
    knots = (first, *points, last)
    fine = [points[0]]
    for i in range(1, len(knots) - 2):
        fine += [_span(*knots[i - 1:i + 3], n / SAMPLES_PER_SPAN) for n in range(1, SAMPLES_PER_SPAN + 1)]
    return tuple(fine)


def exact(points):
    return tuple(tuple(float(v) for v in p) for p in points)


def length(curve, points):
    """The length of the curve in millimetres. A body following it by length fraction moves at exactly this speed per unit of t."""
    points = exact(points)
    if curve == "arc":
        centre, _, turn = circle_through(*points)
        return math.radians(turn) * mx.length(mx.sub(points[0], centre))
    chain = smooth_points(points) if curve == "smooth" else points
    return sum(mx.length(mx.sub(b, a)) for a, b in zip(chain, chain[1:]))


def position(curve, points, t):
    """Where the followed point is at fraction t of the curve's length."""
    points = exact(points)
    if curve == "arc":
        return arc(points, t)
    return by_length(smooth_points(points) if curve == "smooth" else points, t)


@functools.lru_cache(maxsize=64)
def _fractions(curve, points):
    if curve == "arc":
        centre, axis, turn = circle_through(*points)
        start, middle = mx.sub(points[0], centre), mx.sub(points[1], centre)
        part = math.degrees(math.atan2(mx.dot(mx.cross(start, middle), axis), mx.dot(start, middle))) % 360
        return (0.0, part / turn, 1.0)
    chain = smooth_points(points) if curve == "smooth" else points
    step = SAMPLES_PER_SPAN if curve == "smooth" else 1
    walked = [0.0]
    for a, b in zip(chain, chain[1:]):
        walked.append(walked[-1] + mx.length(mx.sub(b, a)))
    return tuple(walked[i * step] / walked[-1] for i in range(len(points)))


def fractions(curve, points):
    """The fraction of the curve's length at which it passes each listed point: 0 for the first, 1 for the last."""
    return _fractions(curve, exact(points))


def turn(curve, points, angles, t):
    """The angle at fraction t of the curve's length, growing evenly by length from each point's angle to the next one's."""
    at, t = fractions(curve, points), max(0.0, min(1.0, t))
    for a, b, start, end in zip(at, at[1:], angles, angles[1:]):
        if t <= b:
            return start + (end - start) * (t - a) / (b - a)
    return angles[-1]


def turn_rate(curve, points, angles):
    """The fastest the angle changes, in radians per unit of the length fraction."""
    at = fractions(curve, points)
    return max(abs(math.radians(end - start)) / (b - a) for a, b, start, end in zip(at, at[1:], angles, angles[1:]))
