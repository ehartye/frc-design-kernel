"""The primitive shapes of a blockout, each a few lines over the CAD kernel. Lengths in millimetres."""
import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeTorus
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt, gp_Vec

PLANES = {"xy": lambda a, b, level: (a, b, level), "xz": lambda a, b, level: (a, level, b), "yz": lambda a, b, level: (level, a, b)}
NORMALS = {"xy": (0, 0, 1), "xz": (0, 1, 0), "yz": (1, 0, 0)}


def box(corner, opposite):
    low = [min(a, b) for a, b in zip(corner, opposite)]
    high = [max(a, b) for a, b in zip(corner, opposite)]
    return BRepPrimAPI_MakeBox(gp_Pnt(*low), gp_Pnt(*high)).Shape()


def cylinder(start, end, radius, sweep_deg=None, sweep_from=None):
    """A cylinder between two end centres. sweep_deg makes a pie slice, turning counter-clockwise from sweep_from."""
    axis = [b - a for a, b in zip(start, end)]
    frame = gp_Ax2(gp_Pnt(*start), gp_Dir(*axis)) if sweep_from is None else gp_Ax2(gp_Pnt(*start), gp_Dir(*axis), gp_Dir(*sweep_from))
    height = math.dist(start, end)
    if sweep_deg is None:
        return BRepPrimAPI_MakeCylinder(frame, radius, height).Shape()
    return BRepPrimAPI_MakeCylinder(frame, radius, height, math.radians(sweep_deg)).Shape()


def sphere(centre, radius):
    return BRepPrimAPI_MakeSphere(gp_Pnt(*centre), radius).Shape()


def torus(centre, axis, major_radius, minor_radius):
    """A ring: a circle of minor_radius swept round a circle of major_radius about the axis through centre."""
    return BRepPrimAPI_MakeTorus(gp_Ax2(gp_Pnt(*centre), gp_Dir(*axis)), major_radius, minor_radius).Shape()


def polygon_wire(points):
    polygon = BRepBuilderAPI_MakePolygon()
    for p in points:
        polygon.Add(gp_Pnt(*p))
    polygon.Close()
    return polygon.Wire()


def circle_wire(centre, axis, radius):
    edge = BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(gp_Pnt(*centre), gp_Dir(*axis)), radius)).Edge()
    return BRepBuilderAPI_MakeWire(edge).Wire()


def extruded(outer, travel, hole=None):
    """A flat face bounded by the outer wire, less an optional hole wire wound the other way, pushed along travel."""
    face = BRepBuilderAPI_MakeFace(outer, True)
    if hole is not None:
        face.Add(hole)
    return BRepPrimAPI_MakePrism(face.Face(), gp_Vec(*travel)).Shape()


def prism(plane, outline, start, end):
    """A closed 2D outline in the xy, xz or yz plane, pushed from level start to level end along the third axis."""
    place = PLANES[plane]
    travel = [n * (end - start) for n in NORMALS[plane]]
    return extruded(polygon_wire([place(a, b, start) for a, b in outline]), travel)


def round_tube(start, end, outer_diameter, wall):
    axis = [b - a for a, b in zip(start, end)]
    hole = circle_wire(start, [-v for v in axis], outer_diameter / 2 - wall)
    return extruded(circle_wire(start, axis, outer_diameter / 2), axis, hole)


def rectangle(centre, across, up, width, height):
    return [[c + sa * a * width / 2 + su * u * height / 2 for c, a, u in zip(centre, across, up)] for sa, su in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def rectangular_tube(start, end, width, height, wall, up=None):
    """A box-section tube between two end centres. height is measured along up (made square to the tube)."""
    axis = [b - a for a, b in zip(start, end)]
    size = math.hypot(*axis)
    along = [v / size for v in axis]
    if up is None:
        up = (1, 0, 0) if abs(along[2]) > 0.99 else (0, 0, 1)
    lean = sum(a * b for a, b in zip(up, along))
    square = [u - lean * a for u, a in zip(up, along)]
    span = math.hypot(*square)
    square = [v / span for v in square]
    across = [along[1] * square[2] - along[2] * square[1], along[2] * square[0] - along[0] * square[2], along[0] * square[1] - along[1] * square[0]]
    outer = polygon_wire(rectangle(start, across, square, width, height))
    inner = polygon_wire(rectangle(start, across, square, width - 2 * wall, height - 2 * wall)[::-1])
    return extruded(outer, axis, inner)
