"""A solid with no construction to read (an imported part, a custom shape) split into convex pieces at its own faces.

A solid is convex when every point of it lies on the inner side of each of its faces' planes: the plane of a flat
face, or a plane touching a round face that bulges outward (a roller, a ball, a cone). Where some points do not, that
plane cuts the solid in two, and each half is split the same way. A bracket, an angle, a bevelled blade or a plate
with windows comes apart into exact convex pieces. A piece with a round face that dips inward (a bore, a fillet in a
corner) or a free-form face is left as it is; the caller hulls it and says so.
"""
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepAlgoAPI import BRepAlgoAPI_Splitter
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere
from OCP.TopAbs import TopAbs_REVERSED, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
try:
    from OCP.TopTools import TopTools_ListOfShape
except ImportError:    # newer kernels moved the shape list
    from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
from OCP.TopoDS import TopoDS

from .between import faces
from .mesh import triangles
from .props import bounds, volume

TOLERANCE_MM = 0.01
AS_SOLID = getattr(TopoDS, "Solid_s", None) or TopoDS.Solid


def outward(face, surface, u, v):
    """(point, outward unit normal) of a face at (u, v), or None where the normal is not defined."""
    props = BRepLProp_SLProps(surface, u, v, 1, 1e-9)
    if not props.IsNormalDefined():
        return None
    n, p = props.Normal(), props.Value()
    sign = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
    return (p.X(), p.Y(), p.Z()), (sign * n.X(), sign * n.Y(), sign * n.Z())


def bulges_out(surface, point, normal):
    """True when a cylinder, cone or sphere face curves away from its own outward normal, as a roller does."""
    kind = surface.GetType()
    if kind == GeomAbs_Sphere:
        c = surface.Sphere().Location()
        centre = (c.X(), c.Y(), c.Z())
    else:
        axis = (surface.Cylinder() if kind == GeomAbs_Cylinder else surface.Cone()).Axis()
        o, d = axis.Location(), axis.Direction()
        origin, along = (o.X(), o.Y(), o.Z()), (d.X(), d.Y(), d.Z())
        t = sum((a - b) * c for a, b, c in zip(point, origin, along))
        centre = tuple(b + t * c for b, c in zip(origin, along))
    return sum((a - b) * n for a, b, n in zip(point, centre, normal)) > 0


def planes(shape, samples=3):
    """(planes that may cut the solid, whether it has a face no plane can make convex).

    A plane is (outward normal, offset): the plane of each flat face, then planes touching each round face that
    bulges outward, at a few points across it.
    """
    flat, round_, rough = [], [], False
    for face in faces(shape):
        surface = BRepAdaptor_Surface(face)
        kind = surface.GetType()
        if kind == GeomAbs_Plane:
            u, v = surface.FirstUParameter(), surface.FirstVParameter()
            found = outward(face, surface, u, v)
            if found:
                flat.append(found)
            continue
        if kind not in (GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere):
            rough = True
            continue
        u0, u1, v0, v1 = surface.FirstUParameter(), surface.LastUParameter(), surface.FirstVParameter(), surface.LastVParameter()
        for i in range(samples):
            for j in range(samples):
                found = outward(face, surface, u0 + (u1 - u0) * (i + 0.5) / samples, v0 + (v1 - v0) * (j + 0.5) / samples)
                if found is None:
                    continue
                if not bulges_out(surface, *found):
                    rough = True
                    break
                round_.append(found)
    out = []
    for point, normal in flat + round_:
        offset = sum(a * b for a, b in zip(normal, point))
        if not any(abs(sum(a * b for a, b in zip(normal, m)) - 1) < 1e-9 and abs(o - offset) < TOLERANCE_MM for m, o in out):
            out.append((normal, offset))
    return out, rough


def cutting_plane(shape, points):
    """(the face plane with the most of the solid outside it, or None; whether a face keeps the solid from being convex)."""
    found, rough = planes(shape)
    best, most = None, TOLERANCE_MM
    for normal, offset in found:
        beyond = max(sum(a * b for a, b in zip(normal, p)) - offset for p in points)
        if beyond > most:
            best, most = (normal, offset), beyond
    return best, rough


def halves(shape, normal, offset):
    """The solids a plane cuts a solid into."""
    size = 2 * max(abs(v) for v in bounds(shape)) + 10
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    point = gp_Pnt(*[n * offset for n in normal])
    face = BRepBuilderAPI_MakeFace(gp_Pln(point, gp_Dir(*normal)), -size, size, -size, size).Face()
    splitter, arguments, tools = BRepAlgoAPI_Splitter(), TopTools_ListOfShape(), TopTools_ListOfShape()
    arguments.Append(shape)
    tools.Append(face)
    splitter.SetArguments(arguments)
    splitter.SetTools(tools)
    splitter.Build()
    found, explorer = [], TopExp_Explorer(splitter.Shape(), TopAbs_SOLID)
    while explorer.More():
        found.append(AS_SOLID(explorer.Current()))
        explorer.Next()
    return found


def convex_pieces(shape, most=48, deflection_mm=0.2):
    """([convex solid, ...], [solid still not convex, ...]) for one solid. Past `most` pieces it is returned whole, as not convex."""
    whole, left, done, rough = volume(shape), [shape], [], []
    while left:
        piece = left.pop()
        points = triangles(piece, deflection_mm)["vertices"]
        plane, curved = cutting_plane(piece, points) if points else (None, True)
        if plane is None:
            (rough if curved else done).append(piece)
            continue
        parts = halves(piece, *plane)
        if len(parts) < 2 or len(done) + len(left) + len(parts) > most:
            rough.append(piece)
            continue
        left += parts
    if abs(sum(volume(p) for p in done + rough) - whole) > 1e-6 * max(whole, 1.0) + 1e-3:
        return [], [shape]       # the cuts lost material: keep the solid whole and say so
    return done, rough
