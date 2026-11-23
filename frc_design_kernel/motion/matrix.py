"""Rigid transforms as plain number tables. No CAD kernel needed.

A transform is a tuple of 12 numbers, row by row: three rows of (rotation x 3, shift). Applying it to a point p
gives rotation * p + shift. compose(later, first) is the transform that does first and then later.
"""
import math

IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    size = length(a)
    return (a[0] / size, a[1] / size, a[2] / size)


def translation(travel):
    x, y, z = travel
    return (1.0, 0.0, 0.0, float(x), 0.0, 1.0, 0.0, float(y), 0.0, 0.0, 1.0, float(z))


def rotation(origin, axis, degrees):
    """A turn of degrees about the line through origin along axis (right-hand rule)."""
    x, y, z = unit(axis)
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    k = 1 - c
    rows = ((c + x * x * k, x * y * k - z * s, x * z * k + y * s),
            (y * x * k + z * s, c + y * y * k, y * z * k - x * s),
            (z * x * k - y * s, z * y * k + x * s, c + z * z * k))
    shift = sub(origin, tuple(dot(row, origin) for row in rows))
    return (*rows[0], shift[0], *rows[1], shift[1], *rows[2], shift[2])


def apply(m, p):
    return (m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3],
            m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7],
            m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11])


def compose(later, first):
    """The transform that applies first, then later."""
    out = []
    for r in (0, 4, 8):
        a, b, c, d = later[r:r + 4]
        out += [a * first[0] + b * first[4] + c * first[8], a * first[1] + b * first[5] + c * first[9],
                a * first[2] + b * first[6] + c * first[10], a * first[3] + b * first[7] + c * first[11] + d]
    return tuple(out)


def chain(transforms):
    """All of the transforms applied in list order."""
    total = IDENTITY
    for m in transforms:
        total = compose(m, total)
    return total


def inverse(m):
    rows = ((m[0], m[4], m[8]), (m[1], m[5], m[9]), (m[2], m[6], m[10]))
    shift = (m[3], m[7], m[11])
    back = tuple(-dot(row, shift) for row in rows)
    return (*rows[0], back[0], *rows[1], back[1], *rows[2], back[2])


def is_identity(m, tolerance=1e-12):
    return all(abs(a - b) <= tolerance for a, b in zip(m, IDENTITY))


def gap(a, b, reach=1000.0):
    """How far apart two transforms put a point that is reach mm from the origin, at most (mm)."""
    turn = math.sqrt(sum((a[i] - b[i]) ** 2 for i in (0, 1, 2, 4, 5, 6, 8, 9, 10)))
    return turn * reach + math.sqrt(sum((a[i] - b[i]) ** 2 for i in (3, 7, 11)))
