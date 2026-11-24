"""The convex hull of a solid, grown outward so that it holds all of the true solid. Lengths in millimetres.

    hull(shape, linear_mm=0.2, angular_rad=0.3) -> {"vertices": [[x, y, z], ...], "toleranceMm": t}
    planes(points) -> [([nx, ny, nz], offset), ...]

hull meshes the shape (linear_mm is the mesher's linear deflection, angular_rad its angular deflection) and takes the
convex hull of the mesh's corners. Those corners lie on the true surface, but the flat triangles between them cut
inside a round one, so that hull sits a little inside the solid. Each of its faces, and each face of the box fitted
to the solid's true surfaces, is therefore pushed outward by t, and the corners where the pushed faces meet are
reported, each coordinate rounded away from the middle to 0.001 mm. The grown hull contains the true solid.
toleranceMm is t, the outward push used: the most the hull stands clear of a flat face of the solid, and the most its
extent along x, y or z exceeds the solid's on each side. Where pushed faces meet at a slant over a round surface, a
corner can stand a little more than t clear of the solid.

How t is bounded. Every point of the true surface lies within some distance s of the mesh, and the mesh lies inside
the ungrown hull, so pushing every face out by s holds the whole solid. s is taken as the larger of:
- linear_mm, the deflection the mesher is asked to keep to;
- 4/3 of the most the true surface strays from any triangle edge, measured as the gap from the middle of each edge
  to the true surface of its face. Over a small triangle the gap is close to a quadratic (a curve like a parabola),
  which is zero at the corners; such a quadratic can rise at most 4/3 of its largest edge-middle value anywhere over
  the triangle. This catches the
  mesher overshooting linear_mm, which it can do on round faces meshed as a grid.
t is s plus 0.002 mm, which covers rounding each corner outward and the arithmetic, then rounded up to 0.001 mm.

planes gives the faces of the convex hull of any points, as a unit outward normal and an offset: a point x is inside
or on the hull when normal . x <= offset for every face. Faces are triangles, so one flat side can be several faces
in the same plane. Points on a line or in a plane enclose no volume and are refused with a DesignError.
"""
import math

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import gp_Pnt
from OCP.TopLoc import TopLoc_Location

from ..errors import DesignError
from . import props
from .between import faces

ROUND_MM = 0.001
ALLOWANCE_MM = 0.002    # rounding a corner outward moves it at most 0.001 * sqrt(3) mm; the rest covers arithmetic
QUADRATIC_PEAK = 4 / 3  # a quadratic that is zero at a triangle's corners peaks at most 4/3 of its largest edge-middle value
GRID_BITS = 40          # points are snapped to a grid 2**-40 of their size, so every inside-or-outside test is exact
FLAT_SHARE = 1e-9       # points this close to a line or plane, as a share of their size, enclose no volume


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class _Face:
    """A triangle of the hull, its corners wound so their normal points out, and the points still outside it.

    Corners are whole numbers of grid steps, so the normal, offset and height are exact whole numbers too; the height
    is the distance above the face's plane times the normal's length."""
    __slots__ = ("corners", "normal", "offset", "outside", "alive")

    def __init__(self, points, a, b, c):
        self.normal = _cross(_sub(points[b], points[a]), _sub(points[c], points[a]))
        self.corners, self.offset, self.outside, self.alive = (a, b, c), _dot(self.normal, points[a]), [], True

    def height(self, point):
        return _dot(self.normal, point) - self.offset

    def edges(self):
        a, b, c = self.corners
        return ((a, b), (b, c), (c, a))


def _refuse(problem):
    raise DesignError("", problem, "Hull a solid: points or a flat sheet with no inside have no convex hull")


def _simplex(points, flat):
    """Four corners that span a volume: the farthest pair, the point farthest from their line, then from their plane.
    Refuses points that all lie within flat grid steps of one place, one line or one plane."""
    extremes = {min(range(len(points)), key=lambda i: points[i][k]) for k in range(3)}
    extremes |= {max(range(len(points)), key=lambda i: points[i][k]) for k in range(3)}
    length = lambda v: _dot(v, v)
    a, b = max(((i, j) for i in extremes for j in extremes), key=lambda ij: length(_sub(points[ij[1]], points[ij[0]])))
    along = _sub(points[b], points[a])
    if length(along) <= flat ** 2:
        _refuse("the points to hull are all at one place, so they enclose no volume")
    c = max(range(len(points)), key=lambda i: length(_cross(along, _sub(points[i], points[a]))))
    if length(_cross(along, _sub(points[c], points[a]))) <= flat ** 2 * length(along):
        _refuse("the points to hull all lie on one line, so they enclose no volume")
    base = _Face(points, a, b, c)
    d = max(range(len(points)), key=lambda i: abs(base.height(points[i])))
    if base.height(points[d]) ** 2 <= flat ** 2 * length(base.normal):
        _refuse("the points to hull all lie in one plane, so they enclose no volume")
    return a, b, c, d


def _start(points, flat):
    """The first tetrahedron, its faces turned outward, and each point handed to the first face it lies outside."""
    a, b, c, d = _simplex(points, flat)
    hull, edges = [], {}
    for x, y, z, other in ((a, b, c, d), (a, b, d, c), (a, c, d, b), (b, c, d, a)):
        face = _Face(points, x, y, z)
        if face.height(points[other]) > 0:
            face = _Face(points, x, z, y)
        hull.append(face)
        for edge in face.edges():
            edges[edge] = face
    _hand_out([i for i in range(len(points)) if i not in (a, b, c, d)], hull, points)
    return hull, edges


def _hand_out(indices, candidates, points):
    for i in indices:
        point = points[i]
        for face in candidates:
            if face.height(point) > 0:
                face.outside.append(i)
                break


def _grow(face, hull, edges, points):
    """Add the farthest point outside face: drop every face it can see and join it to the edge of what is left."""
    far = max(face.outside, key=lambda i: face.height(points[i]))
    apex = points[far]
    visible, todo, horizon = {face}, [face], []
    while todo:
        for a, b in todo.pop().edges():
            other = edges[(b, a)]
            if other in visible:
                continue
            if other.height(apex) > 0:
                visible.add(other)
                todo.append(other)
            else:
                horizon.append((a, b))
    orphans = []
    for gone in visible:
        gone.alive = False
        orphans += gone.outside
        for edge in gone.edges():
            del edges[edge]
    new = [_Face(points, a, b, far) for a, b in horizon]
    for added in new:
        for edge in added.edges():
            edges[edge] = added
    hull += new
    _hand_out([i for i in orphans if i != far], new, points)
    return [added for added in new if added.outside]


def planes(points):
    """The faces of the convex hull of points, as (unit outward normal, offset), found by quickhull.

    The points are first snapped to a grid 2**-40 of their size (under a millionth of a millimetre on any robot part),
    so every test of a point against a face is exact and near-flat clusters cannot tangle the hull."""
    if not points:
        _refuse("there are no points to hull")
    size = max(abs(float(c)) for p in points for c in p)
    step = 2.0 ** (math.floor(math.log2(size)) - GRID_BITS) if size > 0 else 1.0
    grid = sorted({tuple(round(float(c) / step) for c in p) for p in points})
    hull, edges = _start(grid, FLAT_SHARE * size / step)
    todo = [face for face in hull if face.outside]
    while todo:
        face = todo.pop()
        if face.alive and face.outside:
            todo += _grow(face, hull, edges, grid)
    found = []
    for face in hull:
        if face.alive:
            length = math.sqrt(_dot(face.normal, face.normal))
            found.append(([n / length for n in face.normal], face.offset / length * step))
    return found


def _face_stray(face, triangulation, nodes):
    """The most the true surface of one face strays from a triangle edge: the gap from each edge's middle to the
    surface, found by projecting it (a flat face never strays)."""
    if BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane:
        return 0.0
    projection = GeomAPI_ProjectPointOnSurf()
    projection.Init(BRep_Tool.Surface_s(face), *BRepTools.UVBounds_s(face))
    worst, seen = 0.0, set()
    for i in range(1, triangulation.NbTriangles() + 1):
        a, b, c = triangulation.Triangle(i).Get()
        for p, q in ((a, b), (b, c), (c, a)):
            key = (min(p, q), max(p, q))
            if key in seen:
                continue
            seen.add(key)
            middle = [(x + y) / 2 for x, y in zip(nodes[p - 1], nodes[q - 1])]
            projection.Perform(gp_Pnt(*middle))
            if not projection.NbPoints():
                raise DesignError("", "the CAD kernel could not measure how far the mesh lies from a round face",
                                  "Report the shape; try a different linear_mm")
            worst = max(worst, projection.LowerDistance())
    return worst


def _meshed(shape, linear_mm, angular_rad):
    """The mesh's corners, and the most the true surface strays from a triangle edge. The shape is not altered."""
    copy = BRepBuilderAPI_Copy(shape, True, False).Shape()
    BRepMesh_IncrementalMesh(copy, linear_mm, False, angular_rad)
    corners, stray = set(), 0.0
    for face in faces(copy):
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            continue
        move = location.Transformation()
        nodes = [triangulation.Node(i).Transformed(move).Coord() for i in range(1, triangulation.NbNodes() + 1)]
        corners.update(nodes)
        stray = max(stray, _face_stray(face, triangulation, nodes))
    return sorted(corners), stray


def _box_faces(bounds):
    """The six faces of the box fitted to the true surfaces. Pushed out with the rest, they trim the corners where
    pushed faces meet at a slant and would otherwise reach a little more than push past the solid."""
    low, high = bounds[:3], bounds[3:]
    axes = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    return [(list(axis), high[k]) for k, axis in enumerate(axes)] + [([-a for a in axis], -low[k]) for k, axis in enumerate(axes)]


def _pushed(faces_found, push, middle):
    """The corners of the hull with every face pushed out by push: the faces of its polar dual about middle."""
    dual = set()
    for normal, offset in faces_found:
        reach = offset - _dot(normal, middle) + push        # at least push, since middle is inside the hull
        dual.add(tuple(n / reach for n in normal))
    return [[m + n / offset for m, n in zip(middle, normal)] for normal, offset in planes(sorted(dual))]


def _rounded_out(corners, middle):
    """Each corner on the 0.001 mm grid, every coordinate moved away from middle, without repeats."""
    rounded = set()
    for corner in corners:
        steps = (round(c / ROUND_MM, 3) for c in corner)       # a corner within a millionth of a millimetre of the grid stays
        steps = (math.ceil(s) if c >= m else math.floor(s) for s, c, m in zip(steps, corner, middle))
        rounded.add(tuple(round(s * ROUND_MM, 3) for s in steps))
    return [list(c) for c in sorted(rounded)]


def hull(shape, linear_mm=0.2, angular_rad=0.3):
    """{"vertices": [[x, y, z], ...], "toleranceMm": t}: a convex hull that contains the true shape, grown by t."""
    corners, stray = _meshed(shape, linear_mm, angular_rad)
    if not corners:
        _refuse("the shape has no surface to mesh")
    faces_found = planes(corners) + _box_faces(props.bounds(shape))
    middle = [sum(c[k] for c in corners) / len(corners) for k in range(3)]
    push = math.ceil((max(linear_mm, QUADRATIC_PEAK * stray) + ALLOWANCE_MM) / ROUND_MM) * ROUND_MM
    push = round(push, 3)
    return {"vertices": _rounded_out(_pushed(faces_found, push, middle), middle), "toleranceMm": push}
