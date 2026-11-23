"""A solid with no construction to read is split into exact convex pieces at its own faces."""
import importlib.util
import unittest

from frc_design_kernel.builder.shape import make
from frc_design_kernel.kernel import props, split

from .test_mujoco import one_run
from .trial_cases import ASSUMES, bench

HAVE = importlib.util.find_spec("mujoco") is not None
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
ANGLE = {"kind": "prism", "plane": "xz", "fromMm": 0, "toMm": 50, "outlineMm": [[0, 0], [40, 0], [40, 4], [4, 4], [4, 40], [0, 40]]}


def pieces(shape):
    solid = make(shape, "test", None)
    done, rough, _ = split.convex_pieces(solid)
    return solid, done, rough


class Split(unittest.TestCase):
    def test_an_angle_and_a_windowed_plate_come_apart_into_convex_pieces_with_nothing_lost(self):
        """Catches a concave solid left whole (and hulled, filling its corner) or a split that loses or adds material."""
        for shape, count in ((ANGLE, 2), ({"kind": "difference", "from": BOX([0, 0, 0], [100, 60, 3]),
                                           "cut": [BOX([10, 10, -1], [40, 50, 4]), BOX([60, 10, -1], [90, 50, 4])]}, 5)):
            solid, done, rough = pieces(shape)
            self.assertEqual((len(done), rough), (count, []))
            self.assertAlmostEqual(sum(props.volume(p) for p in done), props.volume(solid), delta=1e-6)

    def test_a_bore_is_reported_not_cut(self):
        """Control: catches a bore being called convex. A tube's bore cannot be made convex by planes, so it stays rough."""
        _, done, rough = pieces({"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 50], "outerDiameterMm": 30, "wallMm": 2})
        self.assertEqual((done, len(rough)), ([], 1))
        _, done, rough = pieces({"kind": "cylinder", "fromMm": [0, 0, 0], "toMm": [0, 50, 0], "radiusMm": 12})
        self.assertEqual((len(done), rough), (1, []))       # a roller bulges outward: it is convex as it is


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class InTheEngine(unittest.TestCase):
    def test_a_ball_settles_into_the_inside_corner_of_an_angle_with_a_bolt_hole(self):
        """Catches an imported or round-cut solid run as its convex hull, which bridges the corner of an angle.

        The angle has a bolt hole far from the corner, so its construction gives no breakdown; split at its faces, its
        legs are exact and only the leg with the hole is hulled, and listed with its share.
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
        self.assertEqual(facts["hulled"], ["angle"])
        self.assertLess(facts["hulledShare"]["angle"], 0.6)          # the leg with the hole, not the whole angle


if __name__ == "__main__":
    unittest.main()
