"""Any placement written as carried-over operations, for tools that only know translation and rotation."""
from . import matrix as mx
from . import screw


def as_ops(placement):
    """Operations that, applied in full, give the placement: at most one rotation and one translation."""
    if mx.is_identity(placement, 1e-12):
        return []
    point, axis, angle, slide = screw.decompose(mx.IDENTITY, placement)
    found = []
    if point is not None:
        found.append({"kind": "rotation", "originMm": list(point), "axis": list(axis), "travelDeg": angle})
    if mx.length(slide) > 1e-12:
        found.append({"kind": "translation", "travelMm": list(slide)})
    return found
