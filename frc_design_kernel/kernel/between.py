"""What can be measured between two shapes: the gap, the shared volume, and facing flat contact area."""
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

TOUCHING_MM = 1e-7    # two shapes this close are treated as touching, and are then tested for shared volume
as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face


def distance(a, b):
    """The smallest gap between two shapes in millimetres. Zero when they touch or overlap."""
    query = BRepExtrema_DistShapeShape(a, b)
    if not query.IsDone() or not query.Value() >= 0:
        raise ValueError("the CAD kernel could not measure the gap between two shapes")
    return query.Value()


def vertex(point):
    """A point as a shape, so its distance to a solid can be measured."""
    return BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()


def common(a, b, area=False):
    """The volume two shapes share, in cubic millimetres (or the area two faces share, with area=True)."""
    query = BRepAlgoAPI_Common(a, b)
    if not query.IsDone() or query.Shape().IsNull():
        raise ValueError("the CAD kernel could not find what two shapes share")
    properties = GProp_GProps()
    if area:
        BRepGProp.SurfaceProperties_s(query.Shape(), properties)
    else:
        BRepGProp.VolumeProperties_s(query.Shape(), properties, True)
    return max(0.0, properties.Mass())


def shared(a, b):
    """The shape two shapes have in common (it may be empty)."""
    query = BRepAlgoAPI_Common(a, b)
    if not query.IsDone():
        raise ValueError("the CAD kernel could not find what two shapes share")
    return query.Shape()


def gap_and_overlap(a, b):
    """(gap in mm, shared volume in mm3). The shared volume is only worked out when the shapes touch."""
    gap = distance(a, b)
    return gap, (common(a, b) if gap <= TOUCHING_MM else 0.0)


def faces(shape):
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        yield as_face(explorer.Current())
        explorer.Next()


def flat_faces(shape):
    """(face, outward normal) for every flat face of a shape."""
    for face in faces(shape):
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() == GeomAbs_Plane:
            normal = list(surface.Plane().Axis().Direction().Coord())
            yield face, ([-v for v in normal] if face.Orientation() == TopAbs_REVERSED else normal)


def bearing_area(a, b, load_direction=None):
    """The area in mm2 where flat faces of a and b lie against each other, facing opposite ways.

    With load_direction, only faces of a whose outward normal points that way are counted.
    """
    against = list(flat_faces(b))
    total = 0.0
    for face, normal in flat_faces(a):
        if load_direction is not None and sum(x * y for x, y in zip(normal, load_direction)) <= 0.999999999:
            continue
        for other, facing in against:
            if sum(x * y for x, y in zip(normal, facing)) < -0.999999999 and distance(face, other) <= TOUCHING_MM:
                total += common(face, other, True)
    return total
