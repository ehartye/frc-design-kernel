"""Apply a rigid transform (a 12-number table from motion.matrix) to a shape. The shape itself is not altered."""
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf
from OCP.TopLoc import TopLoc_Location


def to_kernel(matrix):
    transform = gp_Trsf()
    transform.SetValues(*matrix)
    return transform


def moved(shape, matrix):
    """The same shape at a new place. Its geometry is shared, not copied or changed."""
    return BRepBuilderAPI_Transform(shape, to_kernel(matrix), False).Shape()


def settled(shape):
    """The shape with its placement worked into its own geometry, as a file format with one body per name needs.

    A moved or imported shape is a shared body plus a placement. Written to STEP as it is, that becomes a small
    assembly and the name lands on the wrong level.
    """
    location = shape.Location()
    if location.IsIdentity():
        return shape
    return BRepBuilderAPI_Transform(shape.Located(TopLoc_Location()), location.Transformation(), True).Shape()
