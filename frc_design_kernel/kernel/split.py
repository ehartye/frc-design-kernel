"""A solid with no construction to read (an imported part, a custom shape) split into convex pieces at its own faces.

A solid is convex when every point of it lies on the inner side of each of its faces' planes: the plane of a flat
face, or a plane touching a round face that bulges outward (a roller, a ball, a cone). Where some points do not, that
plane cuts the solid in two, and each half is split the same way. A bracket, an angle, a bevelled blade or a plate
with windows comes apart into exact convex pieces.

A round face that dips inward (a bore, a countersink, a belt's wrap round its pulley, a relieved land on a roller) is
cut into wedges about its own axis, by planes through that axis, until no wedge spans more of it than keeps the
chord within FACET_MM of the arc. Each wedge is then convex but for that sliver and is used as flat facets, within
FACET_MM, and said so. Only a free-form face, an inward ball, or a solid past the piece limit is left rough for the
caller to hull.
"""
import math

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
FACET_MM = 0.2       # how far a wedge's flat chord may sit inside the round face it stands for
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


def hollow(surface, samples=3):
    """An inward cylinder or cone face as (axis origin, axis direction, largest radius, start angle, end angle, x, y),
    or None for a sphere, which wedges about one axis cannot make convex."""
    kind = surface.GetType()
    if kind == GeomAbs_Sphere:
        return None
    place = (surface.Cylinder() if kind == GeomAbs_Cylinder else surface.Cone()).Position()
    o, d, x, y = place.Location(), place.Direction(), place.XDirection(), place.YDirection()
    origin, along = (o.X(), o.Y(), o.Z()), (d.X(), d.Y(), d.Z())
    u0, u1, v0, v1 = surface.FirstUParameter(), surface.LastUParameter(), surface.FirstVParameter(), surface.LastVParameter()
    radius = 0.0
    for i in range(samples):
        for j in range(samples):
            p = surface.Value(u0 + (u1 - u0) * i / (samples - 1), v0 + (v1 - v0) * j / (samples - 1))
            rel = (p.X() - origin[0], p.Y() - origin[1], p.Z() - origin[2])
            t = sum(a * b for a, b in zip(rel, along))
            radius = max(radius, math.sqrt(max(0.0, sum(a * a for a in rel) - t * t)))
    return origin, along, radius, u0, u1, (x.X(), x.Y(), x.Z()), (y.X(), y.Y(), y.Z())


def step(radius):
    """The widest angle of a round face whose chord stays within FACET_MM of its arc."""
    return 2 * math.pi if radius <= FACET_MM else 2 * math.acos(1 - FACET_MM / radius)


def widest(found):
    """Of a piece's inward round faces, the one spanning most past its facet angle, or None when all are within it."""
    best, most = None, 0.0
    for face in found:
        over = (face[4] - face[3]) - step(face[2])
        if over > 1e-9 and over > most:
            best, most = face, over
    return best


def sagitta(found):
    """The most any chord of these faces sits inside its arc."""
    return max((face[2] * (1 - math.cos((face[4] - face[3]) / 2)) for face in found), default=0.0)


def axial_plane(face):
    """The plane through a round face's axis that halves its span, as (unit normal, offset)."""
    origin, along, _, u0, u1, x, y = face
    mid = (u0 + u1) / 2
    radial = tuple(math.cos(mid) * a + math.sin(mid) * b for a, b in zip(x, y))
    normal = (along[1] * radial[2] - along[2] * radial[1], along[2] * radial[0] - along[0] * radial[2], along[0] * radial[1] - along[1] * radial[0])
    size = math.sqrt(sum(c * c for c in normal))
    normal = tuple(c / size for c in normal)
    return normal, sum(a * b for a, b in zip(normal, origin))


def planes(shape, samples=3):
    """(planes that may cut the solid, whether it has a face nothing here can make convex, its inward round faces).

    A plane is (outward normal, offset): the plane of each flat face, then planes touching each round face that
    bulges outward, at a few points across it.
    """
    flat, round_, rough, hollows = [], [], False, []
    for face in faces(shape):
        surface = BRepAdaptor_Surface(face)
        kind = surface.GetType()
        if kind == GeomAbs_Plane:
            found = outward(face, surface, surface.FirstUParameter(), surface.FirstVParameter())
            if found:
                flat.append(found)
            continue
        if kind not in (GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere):
            rough = True
            continue
        u0, u1, v0, v1 = surface.FirstUParameter(), surface.LastUParameter(), surface.FirstVParameter(), surface.LastVParameter()
        touching, dips = [], False
        for i in range(samples):
            for j in range(samples):
                found = outward(face, surface, u0 + (u1 - u0) * (i + 0.5) / samples, v0 + (v1 - v0) * (j + 0.5) / samples)
                if found is not None:
                    dips = dips or not bulges_out(surface, *found)
                    touching.append(found)
        if not dips:
            round_ += touching
            continue
        dip = hollow(surface)
        if dip is None:
            rough = True
        else:
            hollows.append(dip)
    out = []
    for point, normal in flat + round_:
        offset = sum(a * b for a, b in zip(normal, point))
        if not any(abs(sum(a * b for a, b in zip(normal, m)) - 1) < 1e-9 and abs(o - offset) < TOLERANCE_MM for m, o in out):
            out.append((normal, offset))
    return out, rough, hollows


def cutting_plane(shape, points):
    """(the face plane with the most of the solid outside it, or None; whether a face nothing here can make convex
    remains; its inward round faces)."""
    found, rough, hollows = planes(shape)
    best, most = None, TOLERANCE_MM
    for normal, offset in found:
        beyond = max(sum(a * b for a, b in zip(normal, p)) - offset for p in points)
        if beyond > most:
            best, most = (normal, offset), beyond
    return best, rough, hollows


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


def convex_pieces(shape, most=128, deflection_mm=0.2):
    """([convex solid, ...], [solid still not convex, ...], the most a wedge's facets sit inside a round face, mm).

    A wedge cut about an inward round face counts as convex: its facets are within FACET_MM of the face. Past `most`
    pieces the solid is returned whole, as not convex.
    """
    whole, left, done, rough, faceted = volume(shape), [shape], [], [], 0.0
    while left:
        piece = left.pop()
        points = triangles(piece, deflection_mm)["vertices"]
        plane, curved, hollows = cutting_plane(piece, points) if points else (None, True, [])
        if plane is None and (curved or not hollows):
            (rough if curved else done).append(piece)
            continue
        if plane is None:
            face = widest(hollows)
            if face is None:        # every inward round face spans no more than its facet angle: flat facets will do
                done.append(piece)
                faceted = max(faceted, sagitta(hollows))
                continue
            plane = axial_plane(face)
        parts = halves(piece, *plane)
        if len(parts) < 2 or len(done) + len(left) + len(parts) > most:
            rough.append(piece)
            continue
        left += parts
    if abs(sum(volume(p) for p in done + rough) - whole) > 1e-6 * max(whole, 1.0) + 1e-3:
        return [], [shape], 0.0       # the cuts lost material: keep the solid whole and say so
    return done, rough, faceted
