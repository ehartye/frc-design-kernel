"""The conservative convex hull: it contains the true solid, grown by no more than the tolerance it reports."""
import itertools
import math
import random
import unittest

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace

from frc_design_kernel import DesignError
from frc_design_kernel.builder.shape import solid
from frc_design_kernel.kernel import hull, mesh, shapes

BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
ROUNDING_MM = 0.001


def made(entry):
    return solid(entry, "test shape", None)


def excess(point, faces):
    """How far a point lies outside a hull given as faces (normal, offset); zero or less is inside or on it."""
    return worst_excess([point], faces)


def worst_excess(points, faces):
    """The most any of points lies outside a hull given as faces, written out flat because it runs millions of times."""
    rows = [(n[0], n[1], n[2], d) for n, d in faces]
    return max(max(a * x + b * y + c * z - d for a, b, c, d in rows) for x, y, z in points)


def sphere_excess(centre, radius, faces):
    """The most a true sphere reaches past any face, worked out exactly: its centre's height over the face plus its radius."""
    return max(sum(n * c for n, c in zip(normal, centre)) + radius - offset for normal, offset in faces)


def on_sphere(centre, radius, count):
    """count points spread evenly over a true sphere's surface (a Fibonacci spiral), worked out analytically."""
    golden = math.pi * (3 - math.sqrt(5))
    points = []
    for i in range(count):
        z = 1 - 2 * (i + 0.5) / count
        ring, turn = math.sqrt(1 - z * z), golden * i
        points.append([c + radius * d for c, d in zip(centre, (ring * math.cos(turn), ring * math.sin(turn), z))])
    return points


def extent(vertices, axis):
    return max(v[axis] for v in vertices) - min(v[axis] for v in vertices)


class Planes(unittest.TestCase):
    def test_the_faces_bound_every_point_and_each_rests_on_three_of_them(self):
        """Catches a quickhull that leaves a point outside a face, keeps an inside point or a coplanar one as a corner,
        or invents a face no point touches."""
        corners = [list(c) for c in itertools.product((-10, 30), (-5, 15), (2, 40))]
        rng = random.Random(7)
        inner = [[rng.uniform(-10, 30), rng.uniform(-5, 15), rng.uniform(2, 40)] for _ in range(300)]
        on_faces = [[10, 5, 2], [10, 5, 40], [-10, 5, 21], [30, 0, 10]]
        faces = hull.planes(corners + inner + on_faces)
        self.assertEqual(len({(tuple(round(n, 9) for n in normal), round(offset, 9)) for normal, offset in faces}), 6)
        cloud = [[rng.gauss(0, 20) for _ in range(3)] for _ in range(400)]
        faces = hull.planes(cloud)
        self.assertLessEqual(worst_excess(cloud, faces), 1e-9)
        for normal, offset in faces:
            touching = [p for p in cloud if abs(sum(n * q for n, q in zip(normal, p)) - offset) <= 1e-9]
            self.assertGreaterEqual(len(touching), 3)

    def test_points_on_a_line_or_a_plane_are_refused_clearly(self):
        """Catches a hull of flat or thin input that divides by zero or returns a hull with no volume."""
        cases = {"line": [[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 3, 3]],
                 "plane": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0.5, 0.5, 0]],
                 "too few": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                 "one point": [[4, 4, 4]] * 6}
        for name, points in cases.items():
            with self.subTest(name), self.assertRaises(DesignError) as caught:
                hull.planes(points)
            self.assertTrue(caught.exception.problem and caught.exception.fix, name)
        flat = BRepBuilderAPI_MakeFace(shapes.polygon_wire([[0, 0, 0], [50, 0, 0], [50, 30, 0], [0, 30, 0]]), True).Face()
        with self.assertRaises(DesignError) as caught:
            hull.hull(flat)
        self.assertIn("plane", caught.exception.problem)

    def test_control_a_tetrahedron_is_not_refused(self):
        """Control: catches a degeneracy check so strict it refuses the smallest real hull."""
        self.assertEqual(len(hull.planes([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])), 4)


class Grown(unittest.TestCase):
    def test_a_box_hull_holds_its_corners_and_is_within_the_tolerance_of_them(self):
        """Catches a box hull that loses a corner, or grows by more than the tolerance it reports."""
        low, high = [-15, 5, 2], [25, 35, 22]
        found = hull.hull(made(BOX(low, high)))
        tolerance, vertices = found["toleranceMm"], found["vertices"]
        self.assertGreaterEqual(tolerance, 0.2)
        faces = hull.planes(vertices)
        corners = [list(c) for c in itertools.product(*zip(low, high))]
        for corner in corners:
            self.assertLessEqual(excess(corner, faces), 0)
        for vertex in vertices:
            nearest = min(max(abs(a - b) for a, b in zip(vertex, corner)) for corner in corners)
            self.assertLessEqual(nearest, tolerance + ROUNDING_MM)
        for axis in range(3):
            self.assertLessEqual(extent(vertices, axis), high[axis] - low[axis] + 2 * (tolerance + ROUNDING_MM))

    def test_every_point_of_a_true_sphere_is_inside_the_grown_hull(self):
        """Catches a hull taken from the mesh alone, whose flat facets cut inside a round surface, or one grown only by
        the mesher's deflection, which a small ball's mesh overshoots (at 25 mm such a hull leaves 0.05 mm of it out)."""
        centre = [3, -7, 11]
        for radius in (60, 25):
            with self.subTest(radius=radius):
                shape = made({"kind": "sphere", "centerMm": centre, "radiusMm": radius})
                faces = hull.planes(hull.hull(shape)["vertices"])
                self.assertLessEqual(worst_excess(on_sphere(centre, radius, 1500), faces), 0)
                self.assertLessEqual(sphere_excess(centre, radius, faces), 0)

    def test_control_the_ungrown_mesh_hull_leaves_part_of_the_sphere_outside(self):
        """Control: catches a containment test that cannot fail, so growing the hull would never be needed."""
        centre, radius = [3, -7, 11], 60
        shape = made({"kind": "sphere", "centerMm": centre, "radiusMm": radius})
        faces = hull.planes(mesh.triangles(shape, 0.2, 0.3)["vertices"])
        self.assertGreater(worst_excess(on_sphere(centre, radius, 1500), faces), 0.01)
        self.assertGreater(sphere_excess(centre, radius, faces), 0.01)

    def test_a_torus_hull_spans_its_outer_diameter_and_thickness_within_the_tolerance(self):
        """Catches a ring's hull that falls short of the ring, or overshoots it by more than the tolerance."""
        major, minor = 90, 25
        found = hull.hull(made({"kind": "torus", "centerMm": [5, -4, 6], "axis": [0, 0, 1], "majorRadiusMm": major, "minorRadiusMm": minor}))
        slack = 2 * (found["toleranceMm"] + ROUNDING_MM)
        for axis, size in ((0, 2 * (major + minor)), (1, 2 * (major + minor)), (2, 2 * minor)):
            with self.subTest(axis=axis):
                self.assertGreaterEqual(extent(found["vertices"], axis), size)
                self.assertLessEqual(extent(found["vertices"], axis), size + slack)

    def test_an_l_shaped_union_hull_fills_the_notch_but_no_more(self):
        """Catches a 'hull' that follows a non-convex solid's outline instead of spanning its notch, or one so large it
        holds points well clear of the solid."""
        found = hull.hull(made({"kind": "union", "of": [BOX([0, 0, 0], [60, 20, 10]), BOX([0, 0, 0], [20, 60, 10])]}))
        faces = hull.planes(found["vertices"])
        notch, beyond = [35, 35, 5], [45, 45, 5]       # neither is in either arm; the notch is inside the hull's diagonal
        self.assertTrue(notch[0] > 20 and notch[1] > 20)
        self.assertLessEqual(excess(notch, faces), 0)
        self.assertGreater(excess(beyond, faces), 0)


if __name__ == "__main__":
    unittest.main()
