"""How deep a rigid solid presses into a round, squashable piece along a motion.

The piece must be a whole ball, or a whole ring with a round cross-section. Its skin is every point one radius from
its centre (a point for a ball, a circle for a ring). So the depth another solid presses in is the radius less that
solid's distance to the centre, and the same adaptive search that proves clearance bounds the deepest press.
"""
import math

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCP.GeomAbs import GeomAbs_Sphere, GeomAbs_Torus
from OCP.gp import gp_Circ

from ..errors import DesignError
from ..kernel import props
from ..kernel.between import distance, faces
from ..kernel.transform import moved
from ..motion import stages as stage_math
from . import scene as scenes
from .search import DEFAULT_DEPTH, search


def section(shape, name):
    """(centre shape, section radius) of a whole ball or round-section ring. Refuses any other solid."""
    surfaces = [BRepAdaptor_Surface(face) for face in faces(shape)]
    kind = surfaces[0].GetType() if len(surfaces) == 1 else None
    if kind == GeomAbs_Sphere:
        ball = surfaces[0].Sphere()
        radius, centre = ball.Radius(), BRepBuilderAPI_MakeVertex(ball.Location()).Vertex()
        volume = 4 * math.pi * radius ** 3 / 3
    elif kind == GeomAbs_Torus and surfaces[0].Torus().MajorRadius() > surfaces[0].Torus().MinorRadius():
        ring = surfaces[0].Torus()
        radius = ring.MinorRadius()
        centre = BRepBuilderAPI_MakeEdge(gp_Circ(ring.Position().Ax2(), ring.MajorRadius())).Edge()
        volume = 2 * math.pi ** 2 * ring.MajorRadius() * radius ** 2
    else:
        raise DesignError(f'solid "{name}"', "is not a whole ball or a whole round-section ring", "Compression is only measured into those two shapes")
    if not math.isclose(props.volume(shape), volume, rel_tol=1e-6):
        raise DesignError(f'solid "{name}"', "is only part of a ball or ring", "Compression needs the whole piece")
    return centre, radius


def indentation(assembly, motion, piece, contact, limit, absent=(), depth=DEFAULT_DEPTH):
    """The deepest that contact presses into piece along a motion, against a depth limit the caller chooses.

    "deepestMm" at "t" is the deepest sample. "upperBoundMm" is a proven ceiling on the depth over the whole stroke
    when the search settled ("proven"); it is None when a sample went past the limit or the depth limit was reached.
    """
    scene = scenes.for_motion(assembly, motion, absent)
    for name in (piece, contact):
        if name not in scene.names:
            raise DesignError("", f'the solid "{name}" is not present', f"Present solids: {', '.join(scene.names)}")
    centre, radius = section(scene.drawn[piece], piece)
    if not 0 < limit < radius:
        raise DesignError("", f"the depth limit must be more than 0 and less than the section radius {radius:g} mm", "Give the allowed squash in millimetres")
    speed = 0.0 if scene.fixed(piece, contact) else scene.rates[piece] + scene.rates[contact]

    def to_centre(t):
        return distance(moved(centre, stage_math.at(scene.stages[piece], t)), scene.at(contact, t))

    found = search(to_centre, speed, radius - limit, depth, inclusive=True)
    t, nearest = found["hit"] or found["lowest"]
    settled = found["hit"] is None and found["unresolved"] is None
    return {"motion": motion, "piece": piece, "contact": contact, "sectionRadiusMm": radius, "limitMm": float(limit),
            "deepestMm": max(0.0, radius - nearest), "t": t, "deeperThanLimit": found["hit"] is not None, "proven": found["hit"] is not None or settled,
            "upperBoundMm": max(0.0, radius - min(found["floor"], nearest)) if settled else None, "samples": found["samples"]}
