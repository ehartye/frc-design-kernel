"""Cut a solid with a flat plane and return the outline as straight pieces and arcs, in the plane's own 2D coordinates.

The plane is square to one design axis. Its 2D coordinates (u, v) are the other two axes: normal "y" gives (x, z),
normal "x" gives (y, z), normal "z" gives (x, y). Every outline is returned counter-clockwise in (u, v) with the
solid's material on its left, holes clockwise, so "which way does this surface run" has one answer.
"""
import math

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

AXES = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}      # which design coordinates are (u, v) for each plane normal
CURVE_TOLERANCE_MM = 0.02                           # other curves are cut into straight pieces this close to the curve
EXTENT_MM = 1e6
cast = {name: getattr(TopoDS, f"{name}_s", None) or getattr(TopoDS, name) for name in ("Face", "Wire")}


def cutting_face(normal, at):
    origin = [0.0, 0.0, 0.0]
    origin["xyz".index(normal)] = at
    direction = [1.0 if axis == normal else 0.0 for axis in "xyz"]
    plane = gp_Pln(gp_Ax3(gp_Pnt(*origin), gp_Dir(*direction)))
    return BRepBuilderAPI_MakeFace(plane, -EXTENT_MM, EXTENT_MM, -EXTENT_MM, EXTENT_MM).Face()


def edge_pieces(edge, flat):
    """One outline edge as pieces, in the order the outline is walked."""
    curve = BRepAdaptor_Curve(edge)
    first, last = curve.FirstParameter(), curve.LastParameter()
    if edge.Orientation() == TopAbs_REVERSED:
        first, last = last, first
    start, end = flat(curve.Value(first)), flat(curve.Value(last))
    if curve.GetType() == GeomAbs_Line:
        return [{"kind": "segment", "a": start, "b": end}]
    if curve.GetType() == GeomAbs_Circle:
        centre, radius = flat(curve.Circle().Location()), curve.Circle().Radius()
        middle = flat(curve.Value((first + last) / 2))
        angles = [math.atan2(p[1] - centre[1], p[0] - centre[0]) for p in (start, middle, end)]
        turn = (angles[1] - angles[0]) % (2 * math.pi)        # counter-clockwise from the start to the middle
        sweep = abs(last - first)
        return [{"kind": "arc", "centre": centre, "radius": radius, "from": angles[0], "sweep": sweep if turn < math.pi else -sweep}]
    cut = GCPnts_QuasiUniformDeflection(curve, CURVE_TOLERANCE_MM, min(first, last), max(first, last))
    points = [flat(cut.Value(i)) for i in range(1, cut.NbPoints() + 1)]
    points = points[::-1] if first > last else points
    return [{"kind": "segment", "a": a, "b": b} for a, b in zip(points, points[1:])]


def piece_ends(piece):
    if piece["kind"] == "segment":
        return piece["a"], piece["b"]
    c, r = piece["centre"], piece["radius"]
    return tuple([c[0] + r * math.cos(a), c[1] + r * math.sin(a)] for a in (piece["from"], piece["from"] + piece["sweep"]))


def reversed_piece(piece):
    if piece["kind"] == "segment":
        return {"kind": "segment", "a": piece["b"], "b": piece["a"]}
    return {**piece, "from": piece["from"] + piece["sweep"], "sweep": -piece["sweep"]}


def signed_area(pieces):
    """Twice the area inside a closed outline; positive when it is walked counter-clockwise."""
    total = 0.0
    for piece in pieces:
        (ax, ay), (bx, by) = piece_ends(piece)
        total += ax * by - bx * ay
        if piece["kind"] == "arc":      # the sliver between the arc and its chord
            total += piece["radius"] ** 2 * (piece["sweep"] - math.sin(piece["sweep"]))
    return total


def outlines(shape, normal, at):
    """Every closed outline where the plane cuts the solid: a list of outlines, each a list of pieces.

    A piece is {"kind": "segment", "a": [u, v], "b": [u, v]} or {"kind": "arc", "centre": [u, v], "radius": r,
    "from": angle, "sweep": signed angle} with angles in radians, counter-clockwise positive. Lengths are millimetres.
    """
    iu, iv = AXES[normal]
    flat = lambda point: [point.Coord()[iu], point.Coord()[iv]]
    cut = BRepAlgoAPI_Common(shape, cutting_face(normal, at))
    found = []
    faces = TopExp_Explorer(cut.Shape(), TopAbs_FACE) if cut.IsDone() else None
    while faces is not None and faces.More():
        face = cast["Face"](faces.Current())
        wires = TopExp_Explorer(face, TopAbs_WIRE)
        loops = []
        while wires.More():
            walk, pieces = BRepTools_WireExplorer(cast["Wire"](wires.Current()), face), []
            while walk.More():
                pieces += edge_pieces(walk.Current(), flat)
                walk.Next()
            loops.append(pieces)
            wires.Next()
        # The largest outline of a cut face is its outside; the rest are holes and run the other way.
        loops.sort(key=lambda pieces: -abs(signed_area(pieces)))
        for i, pieces in enumerate(loops):
            wanted = 1 if i == 0 else -1
            if signed_area(pieces) * wanted < 0:
                pieces = [reversed_piece(p) for p in reversed(pieces)]
            found.append(pieces)
        faces.Next()
    return found
