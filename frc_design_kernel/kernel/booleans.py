"""Joining, cutting and overlapping shapes."""
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse


def _fold(operation, shapes):
    result = shapes[0]
    for other in shapes[1:]:
        result = operation(result, other).Shape()
    return result


def union(shapes):
    return _fold(BRepAlgoAPI_Fuse, shapes)


def difference(base, cuts):
    return _fold(BRepAlgoAPI_Cut, [base, *cuts])


def intersection(shapes):
    return _fold(BRepAlgoAPI_Common, shapes)
