"""What kind of shape a solid is, read from its faces: a ball, a body of revolution, a prism, or none of those.

Also which of a solid's faces change across a section plane (a cone, a dome, a slope), so a reader can be told in
words why its section is not the same along the width of a piece.
"""
import math

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus

from ..kernel.between import faces

TOLERANCE = 1e-6
ROUND = {GeomAbs_Cylinder: "Cylinder", GeomAbs_Cone: "Cone", GeomAbs_Torus: "Torus"}


def surfaces(shape):
    """(kind, direction, point) for each face: its surface kind, its axis or normal, and a point on that axis (or the centre)."""
    found = []
    for face in faces(shape):
        surface = BRepAdaptor_Surface(face)
        kind = surface.GetType()
        if kind == GeomAbs_Plane:
            found.append(("plane", surface.Plane().Axis().Direction().Coord(), surface.Plane().Location().Coord()))
        elif kind == GeomAbs_Sphere:
            found.append(("sphere", None, surface.Sphere().Location().Coord()))
        elif kind in ROUND:
            axis = getattr(surface, ROUND[kind])().Axis()
            found.append((ROUND[kind].lower(), axis.Direction().Coord(), axis.Location().Coord()))
        else:
            found.append(("other", None, None))
    return found


def parallel(a, b):
    return abs(abs(sum(x * y for x, y in zip(a, b))) - 1) < TOLERANCE


def off_line(point, origin, direction):
    """How far a point is from the line through origin along direction."""
    d = [p - o for p, o in zip(point, origin)]
    along = sum(x * y for x, y in zip(d, direction))
    return math.sqrt(max(0.0, sum(x * x for x in d) - along * along))


def classify(shape, built_as=None):
    """{"class": "sphere" | "body of revolution" | "prismatic" | "general", "axis": [x, y, z]} for a solid.

    A body of revolution is the same after any turn about its axis: a bar, a tube, a ring, a cone. A ball is the
    special case with no preferred axis. built_as is the shape kind from the design source; a box or a prism with only
    flat faces is prismatic. A box with rounded edges is not: its section changes near every face.
    """
    found = surfaces(shape)
    kinds = {kind for kind, _, _ in found}
    if kinds == {"sphere"} and all(math.dist(point, found[0][2]) < TOLERANCE for _, _, point in found):
        return {"class": "sphere"}
    turned = [(direction, point) for kind, direction, point in found if kind in ("cylinder", "cone", "torus")]
    if turned and "other" not in kinds:
        axis, origin = turned[0]
        same = all(parallel(direction, axis) and off_line(point, origin, axis) < TOLERANCE for direction, point in turned)
        flat = all(parallel(direction, axis) for kind, direction, _ in found if kind == "plane")
        centred = all(off_line(point, origin, axis) < TOLERANCE for kind, _, point in found if kind == "sphere")
        if same and flat and centred:
            return {"class": "body of revolution", "axis": [round(v, 9) + 0.0 for v in axis]}
    if built_as in ("box", "prism") and kinds == {"plane"}:
        return {"class": "prismatic"}
    return {"class": "general"}


def curved_across(shape, normal):
    """Words for the faces of a solid that are not the same at every level along the plane's normal."""
    n = [1.0 if axis == normal else 0.0 for axis in "xyz"]
    words = set()
    for kind, direction, _ in surfaces(shape):
        if kind == "cone":
            words.add("a cone or taper")
        elif kind == "sphere":
            words.add("a dome (part of a ball)")
        elif kind == "torus":
            words.add("a ring-shaped curve")
        elif kind == "cylinder" and not parallel(direction, n):
            words.add("a round face lying across the plane")
        elif kind == "plane" and 1e-6 < abs(sum(x * y for x, y in zip(direction, n))) < 1 - 1e-6:
            words.add("a face sloped across the plane (a funnel or chamfer)")
        elif kind == "other":
            words.add("a free-form face")
    return sorted(words)
