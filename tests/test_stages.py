"""Stages: the speed limit behind the clearance proof must never be lower than the real speed of any point."""
import itertools
import math
import unittest

from frc_design_kernel.builder import placement
from frc_design_kernel.motion import matrix as mx
from frc_design_kernel.motion import ops, stages
from frc_design_kernel.motion.sampling import as_ops

from .helpers import load_data

BOX = [20.0, -30.0, 5.0, 140.0, 10.0, 60.0]
TURN = {"kind": "rotation", "originMm": [10, 20, 30], "axis": [1, 2, 3], "travelDeg": 200}
SLIDE = {"kind": "translation", "travelMm": [50, -20, 5]}
DROP = {"kind": "gravity-drop", "fallMm": 80, "quadraticFraction": 0.7}
ARC = {"kind": "path", "curve": "arc", "throughMm": [[0, 0, 0], [100, 100, 0], [200, 0, 0]]}
SMOOTH = {"kind": "path", "curve": "smooth", "throughMm": [[0, 0, 0], [50, 40, 0], [120, 30, 20], [160, 90, 20]]}
TURNING_ARC = {**ARC, "turnDeg": [0, 60, 90], "turnAxis": [0, 0, -1]}
TURNING_SMOOTH = {**SMOOTH, "turnDeg": [15, -40, 30, 120], "turnAxis": [1, 1, 2]}
TURNING_LINE = {"kind": "path", "curve": "straight", "throughMm": [[0, 0, 0], [60, 0, 0], [60, 40, 0]], "turnDeg": [0, 0, 180], "turnAxis": [0, 1, 0]}
POSES = [mx.IDENTITY, ops.at([TURN]), ops.at([TURN, SLIDE]), ops.at([{**TURN, "axis": [0, 0, 1], "travelDeg": 180}])]
CASES = {
    "turn then slide then drop": [("ops", [TURN, SLIDE, DROP])],
    "slide then turn": [("ops", [SLIDE, TURN])],
    "two turns": [("ops", [TURN, {**TURN, "originMm": [-40, 0, 0], "axis": [0, 1, 0], "travelDeg": -150}])],
    "arc path": [("ops", [ARC])],
    "smooth path then turn": [("ops", [SMOOTH, TURN])],
    "turning arc path": [("ops", [TURNING_ARC])],
    "turn then turning smooth path": [("ops", [TURN, TURNING_SMOOTH])],
    "turning straight path that turns only on its second piece": [("ops", [TURNING_LINE])],
    "turning path on a carrier that turns": [("fixed", ops.at([SLIDE])), ("ops", [TURN]), ("fixed", ops.at([TURN])), ("ops", [SLIDE, TURNING_ARC])],
    "through poses": [("through", POSES)],
    "own turn on a carrier that turns": [("fixed", ops.at([SLIDE])), ("ops", [TURN]), ("fixed", ops.at([TURN])), ("ops", [SLIDE, TURN])],
    "own swing on a carrier that swings": [("through", POSES[:3]), ("fixed", ops.at([DROP])), ("through", POSES[1:])],
}


def fastest(listed, steps=4000):
    """The fastest any corner or inside point of BOX is seen to move, in mm per unit of t, by small steps of the stroke."""
    points = stages.corners(BOX) + [tuple((BOX[i] + BOX[i + 3]) / 2 for i in range(3))]
    top = 0.0
    before = [mx.apply(stages.at(listed, 0.0), p) for p in points]
    for n in range(1, steps + 1):
        after = [mx.apply(stages.at(listed, n / steps), p) for p in points]
        top = max(top, max(math.dist(a, b) for a, b in zip(before, after)) * steps)
        before = after
    return top


class SpeedLimit(unittest.TestCase):
    def test_no_point_ever_moves_faster_than_the_limit(self):
        """Catches an unsound limit, which would let the clearance search declare a pair clear that is not."""
        for name, listed in CASES.items():
            limit, seen = stages.speed_limit(listed, BOX), fastest(listed)
            self.assertGreaterEqual(limit * (1 + 1e-6), seen, name)
            self.assertLess(limit, 40 * seen, f"{name}: a limit this loose would make the search needlessly slow")

    def test_half_the_limit_would_be_caught(self):
        """Control: the soundness test can fail."""
        listed = CASES["turn then slide then drop"]
        self.assertLess(stages.speed_limit(listed, BOX) / 4, fastest(listed))

    def test_a_path_moves_at_exactly_its_length(self):
        """Catches a wrong curve length, the speed limit of every path move."""
        self.assertAlmostEqual(stages.speed_limit([("ops", [ARC])], BOX), math.pi * 100, places=6)
        self.assertAlmostEqual(fastest([("ops", [ARC])]), math.pi * 100, delta=0.01)

    def test_a_turning_path_adds_its_turn_at_the_farthest_corner(self):
        """Catches a turning path given only its curve length as its limit, which the turn outruns, so the clearance
        search could skip the instant a corner swings through a neighbour. A quarter arc turned a quarter turn about
        its own axis is a rigid swing about the centre, so the real speed is known."""
        quarter = {"kind": "path", "curve": "arc", "throughMm": [[100, 0, 0], [100 * math.sqrt(0.5), 100 * math.sqrt(0.5), 0], [0, 100, 0]],
                   "turnDeg": [0, 45, 90], "turnAxis": [0, 0, 1]}
        listed = [("ops", [quarter])]
        swing = math.pi / 2 * max(math.dist(p, (0, 0, 0)) for p in stages.corners(BOX))
        self.assertAlmostEqual(fastest(listed), swing, delta=0.01 * swing)
        limit = stages.speed_limit(listed, BOX)
        self.assertAlmostEqual(limit, math.pi / 2 * (100 + max(math.dist(p, (100, 0, 0)) for p in stages.corners(BOX))), places=6)
        self.assertGreaterEqual(limit, swing)
        self.assertLess(stages.speed_limit([("ops", [{k: v for k, v in quarter.items() if not k.startswith("turn")}])], BOX), fastest(listed),
                        "control: the curve length alone is too small a limit for a turning path, and the sampled speed shows it")

    def test_still_bodies_have_no_speed(self):
        """Catches a body that only holds a pose being treated as moving, which would waste the search on it."""
        self.assertEqual(stages.speed_limit([("fixed", POSES[1])], BOX), 0.0)
        self.assertEqual(stages.moving_part([("fixed", POSES[1]), ("ops", []), ("through", [POSES[1], POSES[1]])]), [])


class RelativePose(unittest.TestCase):
    def test_same_moves_from_different_starts_keep_their_relative_pose(self):
        """Catches two bodies carried by the same move being searched as if they moved against each other."""
        a = [("fixed", POSES[1]), ("ops", [SLIDE, TURN])]
        b = [("fixed", POSES[2]), ("ops", [SLIDE, TURN])]
        self.assertEqual(stages.signature(a), stages.signature(b))
        for t in (0.0, 0.3, 1.0):
            apart = mx.compose(mx.inverse(stages.at(a, t)), stages.at(b, t))
            self.assertLess(mx.gap(apart, mx.compose(mx.inverse(stages.at(a, 0)), stages.at(b, 0))), 1e-6)

    def test_different_moves_do_not(self):
        """Catches bodies that do move against each other being treated as fixed together, which would skip the search."""
        self.assertNotEqual(stages.signature([("ops", [SLIDE])]), stages.signature([("ops", [SLIDE, DROP])]))
        self.assertNotEqual(stages.signature([("ops", [SLIDE]), ("fixed", POSES[1])]), stages.signature([("ops", [SLIDE])]))

    def test_straight_travel_is_only_claimed_for_slides(self):
        """Catches the straight-stroke proof being offered a movement that turns, drops or follows a curve."""
        self.assertEqual(stages.straight_travel([("fixed", POSES[1]), ("ops", [SLIDE, SLIDE])]), [100, -40, 10])
        self.assertEqual(stages.straight_travel([("fixed", POSES[1])]), [0.0, 0.0, 0.0])
        for listed in ([("ops", [SLIDE, DROP])], [("ops", [ARC])], [("through", POSES)], [("ops", [SLIDE]), ("fixed", POSES[1])]):
            self.assertIsNone(stages.straight_travel(listed))


class Sampled(unittest.TestCase):
    def test_any_placement_is_one_turn_and_one_slide(self):
        """Catches a sampled placement that an older tool would put somewhere else."""
        for placed in POSES + [ops.at([SLIDE]), ops.at([TURN, SLIDE, DROP])]:
            listed = as_ops(placed)
            self.assertLessEqual(len(listed), 2)
            self.assertTrue(all(op["kind"] in ops.OLD_KINDS for op in listed))
            self.assertLess(mx.gap(ops.at(listed), placed), 1e-6)

    def test_a_curved_motion_becomes_still_placements_in_the_old_vocabulary(self):
        """Catches the hand-over to tools that only know the three old operations drifting from the motion itself."""
        data = {"schema": "frc-design-kernel/design@1", "name": "t", "units": {"length": "mm", "mass": "kg"},
                "groups": {"base": {"role": "structure"}, "arm": {"role": "mechanism", "carriedBy": "base"}, "tip": {"role": "mechanism", "carriedBy": "arm"}},
                "solids": [{"name": "a", "group": g, "shape": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [1, 1, 1]}} for g in ("base",)],
                "poses": {"down": {}, "up": {"arm": [TURN], "tip": [SLIDE]}},
                "motions": {"raise": {"through": ["down", "up"]}, "carry": {"from": "down", "moves": {"arm": [ARC]}}}}
        design = load_data(data).data
        for motion in ("raise", "carry"):
            rows = placement.sampled(design, motion, 4)
            self.assertEqual([row["t"] for row in rows], [0.0, 0.25, 0.5, 0.75, 1.0])
            self.assertEqual(rows[0]["groups"], {})
            for row in rows:
                there = placement.at_motion(design, motion, row["t"])
                for group in ("arm", "tip"):
                    self.assertLess(mx.gap(ops.at(row["groups"].get(group, [])), there[group]), 1e-6)
        self.assertNotIn("base", rows[-1]["groups"])


if __name__ == "__main__":
    unittest.main()
