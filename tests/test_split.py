"""A solid with no construction to read is split into exact convex pieces at its own faces."""
import importlib.util
import math
import unittest
from unittest import mock

from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from frc_design_kernel.builder.shape import make
from frc_design_kernel.kernel import booleans, mesh, props, split
from frc_design_kernel.trials import assumptions

from .test_mujoco import one_run
from .trial_cases import ASSUMES, bench

HAVE = importlib.util.find_spec("mujoco") is not None
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
ANGLE = {"kind": "prism", "plane": "xz", "fromMm": 0, "toMm": 50, "outlineMm": [[0, 0], [40, 0], [40, 4], [4, 4], [4, 40], [0, 40]]}
TUBE = {"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 50], "outerDiameterMm": 30, "wallMm": 2}
CYLINDER = lambda start, end, radius: {"kind": "cylinder", "fromMm": start, "toMm": end, "radiusMm": radius}
# a roller relieved to a smaller land in its middle, bored through for its shaft
RELIEVED = {"kind": "difference", "from": CYLINDER([0, 0, 0], [0, 60, 0], 20),
            "cut": [{"kind": "tube", "section": "round", "fromMm": [0, 20, 0], "toMm": [0, 40, 0], "outerDiameterMm": 44, "wallMm": 6},
                    CYLINDER([0, -1, 0], [0, 61, 0], 5)]}
# half a belt, wrapped round a pulley of 22 mm radius
WRAP = {"kind": "difference", "from": {"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 20, 0], "outerDiameterMm": 50, "wallMm": 3},
        "cut": [BOX([-30, -1, -30], [30, 21, 0])]}


def pieces(shape):
    solid = make(shape, "test", None)
    done, rough, _ = split.convex_pieces(solid)
    return solid, done, rough


def countersunk_plate():
    """A 10 mm plate with a 4 mm radius bolt hole, countersunk at 45 degrees to 9 mm radius at its top face."""
    cone = BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, 5), gp_Dir(0, 0, 1)), 4.0, 10.0, 6.0).Shape()
    return booleans.difference(make(BOX([-30, -30, 0], [30, 30, 10]), "test", None), [make(CYLINDER([0, 0, -1], [0, 0, 11], 4), "test", None), cone])


def radial(vertex, axis):
    """(distance from the axis, angle about it) of a point, for an axis through the origin along x, y or z."""
    a, b = [vertex[i] for i in range(3) if i != axis]
    return math.hypot(a, b), math.atan2(b, a)


def hole_error(piece, largest, axis):
    """The most a flat chord across this piece's share of a hole could sit inside the hole, worked out from the piece's
    own surface: the angle its hole-side points span, at the hole's largest radius. Independent of what split reports."""
    angles = sorted(angle for distance, angle in (radial(v, axis) for v in mesh.triangles(piece, 0.05)["vertices"]) if 0.1 < distance <= largest + 0.01)
    if not angles:
        return 0.0
    gaps = [b - a for a, b in zip(angles, angles[1:])] + [angles[0] + 2 * math.pi - angles[-1]]
    return largest * (1 - math.cos((2 * math.pi - max(gaps)) / 2))


def poke_out(piece, largest, axis):
    """How far the piece reaches past the plane of any of its own triangles not on the hole: zero for a convex piece."""
    found = mesh.triangles(piece, 0.05)
    points, worst = found["vertices"], 0.0
    for tri in found["triangles"]:
        a, b, c = (points[i] for i in tri)
        if all(radial(p, axis)[0] <= largest + 0.01 for p in (a, b, c)):
            continue        # on the hole: its chord is what hole_error bounds
        n = [(b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]), (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
             (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])]
        size = math.hypot(*n)
        if size > 1e-9:
            worst = max(worst, max(sum((p[i] - a[i]) * n[i] for i in range(3)) / size for p in points))
    return worst


class Split(unittest.TestCase):
    def test_an_angle_and_a_windowed_plate_come_apart_into_convex_pieces_with_nothing_lost(self):
        """Catches a concave solid left whole (and hulled, filling its corner) or a split that loses or adds material."""
        for shape, count in ((ANGLE, 2), ({"kind": "difference", "from": BOX([0, 0, 0], [100, 60, 3]),
                                           "cut": [BOX([10, 10, -1], [40, 50, 4]), BOX([60, 10, -1], [90, 50, 4])]}, 5)):
            solid, done, rough = pieces(shape)
            self.assertEqual((len(done), rough), (count, []))
            self.assertAlmostEqual(sum(props.volume(p) for p in done), props.volume(solid), delta=1e-6)

    def test_bores_countersinks_wraps_and_relieved_lands_are_wedged_within_the_facet_error(self):
        """Catches an inward round face left rough (and hulled, filling a bore or a land), a wedge whose flat chord sits
        further inside its face than FACET_MM, a piece that is still concave elsewhere, or a split that loses material."""
        cases = (("bore", make(TUBE, "test", None), 13, 2), ("countersink", countersunk_plate(), 9, 2),
                 ("belt wrap", make(WRAP, "test", None), 22, 1), ("relieved land", make(RELIEVED, "test", None), 5, 1))
        for name, solid, largest, axis in cases:
            with self.subTest(name):
                done, rough, faceted = split.convex_pieces(solid)
                self.assertEqual(rough, [])
                self.assertAlmostEqual(sum(props.volume(p) for p in done), props.volume(solid), delta=1e-6 * props.volume(solid))
                measured = max(hole_error(p, largest, axis) for p in done)
                self.assertLessEqual(measured, split.FACET_MM + 1e-3)
                self.assertGreater(measured, 0.0)
                self.assertAlmostEqual(faceted, measured, delta=0.01)        # the error it states is the error its pieces have
                self.assertLess(max(poke_out(p, largest, axis) for p in done), 0.01)

    def test_a_looser_facet_error_gives_fewer_wedges_and_says_so(self):
        """Control: catches a stated facet error that does not follow the wedges actually cut."""
        solid = make(TUBE, "test", None)
        fine, _, fine_error = split.convex_pieces(solid)
        with mock.patch.object(split, "FACET_MM", 2.0):
            coarse, rough, coarse_error = split.convex_pieces(solid)
        self.assertEqual(rough, [])
        self.assertLess(len(coarse), len(fine))
        self.assertGreater(coarse_error, split.FACET_MM)
        self.assertLessEqual(coarse_error, 2.0)
        self.assertGreater(max(hole_error(p, 13, 2) for p in coarse), split.FACET_MM)

    def test_only_an_inward_ball_or_a_free_form_face_stays_rough(self):
        """Control: catches a face that no wedge can make convex being called convex. A dimple (an inward ball) and a
        ring (a torus face, neither flat, cylindrical, conical nor spherical) stay rough; a plain roller is convex as it is."""
        _, done, rough = pieces({"kind": "difference", "from": BOX([0, 0, 0], [60, 60, 30]), "cut": [{"kind": "sphere", "centerMm": [30, 30, 30], "radiusMm": 20}]})
        self.assertEqual((done, len(rough)), ([], 1))
        _, done, rough = pieces({"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 30, "minorRadiusMm": 5})
        self.assertEqual((done, len(rough)), ([], 1))
        _, done, rough = pieces(CYLINDER([0, 0, 0], [0, 50, 0], 12))
        self.assertEqual((len(done), rough), (1, []))

    def test_the_standing_assumption_states_the_facet_error(self):
        """Catches the record's convex-shapes assumption still saying cut solids are hulled, or naming another error."""
        text = next(row["text"] for row in assumptions.MUJOCO if row["id"] == "convex-shapes")
        self.assertIn(f"{split.FACET_MM:g} mm", text)
        self.assertIn("inward ball", text)


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class InTheEngine(unittest.TestCase):
    def test_a_ball_settles_into_the_inside_corner_of_an_angle_with_a_bolt_hole(self):
        """Catches an imported or round-cut solid run as its convex hull, which bridges the corner of an angle.

        The angle has a bolt hole far from the corner, so its construction gives no breakdown; split at its faces, its
        legs are exact, the hole is wedged into flat facets within the facet error, and nothing is hulled.
        """
        angle = {"kind": "difference", "from": {"kind": "prism", "plane": "xz", "fromMm": -60, "toMm": 60,
                                                 "outlineMm": [[3000, 0], [3200, 0], [3200, 10], [3010, 10], [3010, 200], [3000, 200]]},
                 "cut": [{"kind": "cylinder", "fromMm": [3180, 0, -1], "toMm": [3180, 0, 11], "radiusMm": 4}]}
        trial = {"engine": "mujoco", "assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 1.5, "traceS": 0.01,
                 "piece": {"use": "shot", "start": {"atMm": [3040, 60]}}, "surfaces": [{"solid": "angle", "material": "panel"}],
                 "events": [{"name": "still", "when": {"all": [{"signal": "tS", "above": 0.3}, {"restFor": 0.2}]}, "outcome": "still"}],
                 "pass": {"outcomes": ["still"]}, "measures": {"x": {"final": "xMm"}, "z": {"final": "zMm"}}}
        found, facts = one_run(trial, solids=bench({})["solids"] + [{"name": "angle", "group": "bench", "shape": angle}])
        self.assertAlmostEqual(found["measures"]["z"], 10 + 5, delta=0.5)      # on the leg, in the corner: the hull's diagonal is far above
        self.assertEqual((facts["hulled"], facts["hulledShare"], found["touchedRough"]), ([], {}, []))
        self.assertRegex(facts["faceted"]["angle"], r"flat facets, at most 0\.\d\d mm inside them")


if __name__ == "__main__":
    unittest.main()
