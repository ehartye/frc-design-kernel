"""Exact shortcuts that settle a pair without sampling, for movements simple enough to reason about directly."""
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.gp import gp_Pnt, gp_Vec

from ..kernel.between import TOUCHING_MM, common, distance, faces, flat_faces


def apart_along_an_axis(box_a, box_b, laws_a, laws_b, min_gap):
    """Whether two boxes stay at least min_gap apart along one coordinate axis for the whole stroke.

    laws are motion.stages.axis_laws of each body: along an axis the shift is linear * t + square * t * t. The
    smallest separation of such a law over t from 0 to 1 is found exactly, at an end or at the turning point.
    """
    if laws_a is None or laws_b is None:
        return False
    for i in range(3):
        if not (laws_a[2][i] and laws_b[2][i]):
            continue
        for first, second, sign in ((box_a, box_b, 1), (box_b, box_a, -1)):
            gap = second[i] - first[i + 3]
            v = sign * (laws_b[0][i] - laws_a[0][i])
            q = sign * (laws_b[1][i] - laws_a[1][i])
            low = min(gap, gap + v + q)
            if q > 0 and 0 < -v / (2 * q) < 1:
                low = min(low, gap - v * v / (4 * q))
            if low >= min_gap:
                return True
    return False


def clear_of(shape, fixed, min_gap):
    """Whether shape is at least min_gap from fixed. At zero gap, touching faces are allowed but shared volume is not."""
    gap = distance(shape, fixed)
    return gap >= min_gap and (gap > TOUCHING_MM or common(shape, fixed) == 0)


def swept_box_clear(moving_box, fixed, travel, min_gap):
    """Whether the box swept by moving_box along travel stays clear of a fixed shape. That box holds every position."""
    low = [moving_box[i] + min(0, v) for i, v in enumerate(travel)]
    high = [moving_box[i + 3] + max(0, v) for i, v in enumerate(travel)]
    return clear_of(BRepPrimAPI_MakeBox(gp_Pnt(*low), gp_Pnt(*high)).Shape(), fixed, min_gap)


def swept_faces_clear(shape, fixed, travel, min_gap):
    """Whether a flat-faced solid sliding along travel stays clear of a fixed shape, inside corners included.

    The solid at its start plus the prisms swept by its faces cover every point it ever occupies. A face sliding in
    its own plane sweeps nothing new. Any curved face makes this proof unavailable (returns False).
    """
    sweep = gp_Vec(*travel)
    if sweep.Magnitude() == 0 or not clear_of(shape, fixed, min_gap):
        return False
    flat = list(flat_faces(shape))
    if len(flat) != sum(1 for _ in faces(shape)):
        return False
    for face, normal in flat:
        if sweep.Dot(gp_Vec(*normal)) != 0:
            prism = BRepPrimAPI_MakePrism(face, sweep)
            if not prism.IsDone() or not clear_of(prism.Shape(), fixed, min_gap):
                return False
    return True


def straight_stroke_clear(scene, a, b, min_gap):
    """Whether a pair whose relative movement is one straight slide is proven clear, by any of the enclosing proofs."""
    travel_a, travel_b = scene.straight[a], scene.straight[b]
    if travel_a is None or travel_b is None:
        return False
    forward = [x - y for x, y in zip(travel_a, travel_b)]
    back = [-v for v in forward]
    return (swept_box_clear(scene.boxes[a], scene.start[b], forward, min_gap)
            or swept_box_clear(scene.boxes[b], scene.start[a], back, min_gap)
            or swept_faces_clear(scene.start[a], scene.start[b], forward, min_gap)
            or swept_faces_clear(scene.start[b], scene.start[a], back, min_gap))
