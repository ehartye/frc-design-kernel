"""Clearance along a motion: analytic cases with known gaps, a displaced control, and a case coarse sampling misses."""
import copy
import math
import unittest

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.kernel.between import distance
from frc_design_kernel.measure import clearance

from .helpers import load_data

TURN = lambda degrees: {"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 0, 1], "travelDeg": degrees}
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}

# An arm 100 long and 10 wide swings half a turn about the origin, from +X through +Y to -X. Its far corners run on a
# circle of radius sqrt(100^2 + 5^2). A round post of radius 5 stands at (0, 110): the closest approach is
# 110 - 5 - sqrt(10025) = 4.875 mm, when a far corner crosses the Y axis.
CORNER_RADIUS = math.sqrt(100 ** 2 + 5 ** 2)
POST_GAP = 110 - 5 - CORNER_RADIUS
CORNER_GAP = 250 / math.sqrt(50 ** 2 + 30 ** 2)    # a box corner sliding along [50, -30] past another box's corner
ARM = {
    "schema": "frc-design-kernel/design@1", "name": "Swinging arm", "units": {"length": "mm", "mass": "kg"},
    "groups": {"base": {"role": "structure"}, "arm": {"role": "mechanism"}, "slider": {"role": "mechanism"}, "ball": {"role": "payload"}},
    "solids": [
        {"name": "post", "group": "base", "shape": {"kind": "cylinder", "fromMm": [0, 110, 0], "toMm": [0, 110, 10], "radiusMm": 5}},
        {"name": "wall", "group": "base", "shape": BOX([-300, 165, 0], [300, 170, 10])},
        {"name": "block", "group": "base", "shape": BOX([-200, -60, 0], [-190, -50, 10])},
        {"name": "arm", "group": "arm", "shape": BOX([0, -5, 0], [100, 5, 10])},
        {"name": "slider", "group": "slider", "shape": BOX([-260, -45, 0], [-250, -35, 10])},
        {"name": "ball", "group": "ball", "shape": {"kind": "sphere", "centerMm": [150, 100, 5], "radiusMm": 10}},
    ],
    "poses": {"start": {}, "half": {"arm": [TURN(90)]}, "end": {"arm": [TURN(180)]}},
    "motions": {
        "swing": {"from": "start", "moves": {"arm": [TURN(180)]}},
        "swing through poses": {"through": ["start", "half", "end"]},
        "slide": {"from": "start", "moves": {"slider": [{"kind": "translation", "travelMm": [120, 0, 0]}]}},
        "slide past the corner": {"from": "start", "moves": {"slider": [{"kind": "translation", "travelMm": [50, -30, 0]}]}},
        "slide and settle": {"from": "start", "moves": {"slider": [{"kind": "translation", "travelMm": [50, -30, 0]},
                                                                    {"kind": "gravity-drop", "fallMm": 0.0, "quadraticFraction": 1}]}},
        "ball over the wall": {"from": "start", "moves": {"ball": [
            {"kind": "path", "curve": "arc", "throughMm": [[150, 100, 5], [200, 150, 5], [250, 100, 5]]}]}},
    },
}


def built(change=None):
    data = copy.deepcopy(ARM)
    if change:
        change(data)
    return kernel.build(load_data(data))


def pair(result, a, b):
    return next((row for row in result["pairs"] if row["pair"] == sorted([a, b])), None)


class KnownGaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = built()

    def test_a_swinging_arm_clears_a_post_by_the_known_margin(self):
        """Catches a search that reports a wrong smallest gap, or proves less or more than the geometry allows."""
        for motion in ("swing", "swing through poses"):
            row = pair(clearance.along(self.assembly, motion, min_gap=4.0), "arm", "post")
            self.assertTrue(row["proven"] and not row["closerThanMinGap"], motion)
            self.assertGreaterEqual(row["gapMm"], POST_GAP - 1e-6)          # no sample can be closer than the true minimum
            self.assertGreater(row["lowerBoundMm"], 4.0)                    # proven clear of the asked gap
            self.assertLessEqual(row["lowerBoundMm"], POST_GAP + 1e-6)      # and the proof never claims more than is true

    def test_asking_for_more_than_the_margin_is_reported_with_a_witness(self):
        """Catches a search that misses a near approach lasting under one hundredth of the stroke."""
        row = pair(clearance.along(self.assembly, "swing", min_gap=POST_GAP + 0.1), "arm", "post")
        self.assertTrue(row["closerThanMinGap"] and row["proven"])
        self.assertLess(row["gapMm"], POST_GAP + 0.1)
        self.assertGreaterEqual(row["gapMm"], POST_GAP - 1e-6)
        self.assertEqual(row["overlapMm3"], 0.0)

    def test_two_boxes_sliding_past_at_a_known_distance(self):
        """Catches a straight slide being measured wrongly: the slider passes the block with exactly 5 mm between them."""
        clear = clearance.along(self.assembly, "slide", min_gap=5.0)
        self.assertIsNone(pair(clear, "block", "slider"))               # settled by the boxes alone: no row, but counted
        self.assertEqual((clear["closer"], clear["counts"]["farApart"]), ([], 5))
        close = pair(clearance.along(self.assembly, "slide", min_gap=5.5), "block", "slider")
        self.assertTrue(close["closerThanMinGap"])
        self.assertAlmostEqual(close["gapMm"], 5.0, places=6)

    def test_a_box_sliding_past_a_corner_is_settled_exactly(self):
        """Catches the straight-stroke proof being wrong: corner passes corner at 250 / sqrt(3400) = 4.2875 mm."""
        clear = pair(clearance.along(self.assembly, "slide past the corner", min_gap=4.2), "block", "slider")
        self.assertEqual((clear["method"], clear["proven"], clear["closerThanMinGap"]), ("enclosed straight stroke", True, False))
        close = pair(clearance.along(self.assembly, "slide past the corner", min_gap=4.4), "block", "slider")
        self.assertTrue(close["closerThanMinGap"])
        self.assertGreaterEqual(close["gapMm"], CORNER_GAP - 1e-6)
        self.assertLess(close["gapMm"], 4.4)

    def test_a_slide_that_is_not_quite_straight_is_searched(self):
        """Catches the straight-stroke shortcut being used for a movement it does not cover."""
        row = pair(clearance.along(self.assembly, "slide and settle", min_gap=4.2), "block", "slider")
        self.assertEqual((row["method"], row["proven"], row["closerThanMinGap"]), ("adaptive search", True, False))
        self.assertGreater(row["lowerBoundMm"], 4.2)
        self.assertLessEqual(row["lowerBoundMm"], CORNER_GAP + 1e-6)

    def test_a_ball_on_a_curved_path_clears_a_wall_by_the_known_margin(self):
        """Catches a wrong speed limit for a path, or a curved move measured along its chord: the arc tops out 5 mm under the wall."""
        row = pair(clearance.along(self.assembly, "ball over the wall", min_gap=4.0), "ball", "wall")
        self.assertTrue(row["proven"] and not row["closerThanMinGap"])
        self.assertGreater(row["lowerBoundMm"], 4.0)
        self.assertLessEqual(row["lowerBoundMm"], 5.0 + 1e-6)
        self.assertTrue(pair(clearance.along(self.assembly, "ball over the wall", min_gap=5.2), "ball", "wall")["closerThanMinGap"])

    def test_far_and_still_pairs_get_no_row_but_are_counted(self):
        """Catches time spent on pairs boxes already settle, or pairs silently dropped from the count."""
        result = clearance.along(self.assembly, "swing", min_gap=1.0)
        self.assertEqual([row["pair"] for row in result["pairs"]], [["arm", other] for other in ("ball", "block", "post", "slider", "wall")])
        counts = result["counts"]
        self.assertEqual(counts["pairs"], 15)
        self.assertEqual(counts["pairs"], counts["bothStill"] + counts["farApart"] + counts["fixedFarApart"] + counts["measured"] + counts["declaredContacts"])
        self.assertEqual((counts["bothStill"], counts["measured"]), (10, 5))
        self.assertEqual(result["closest"]["pair"], ["arm", "post"])

    def test_the_same_question_gives_the_same_answer(self):
        """Catches results that depend on run order, caches or how the pairs were shared between workers."""
        once = clearance.along(self.assembly, "swing", min_gap=4.0)
        self.assertEqual(once, clearance.along(self.assembly, "swing", min_gap=4.0))
        scene = clearance.scenes.for_motion(self.assembly, "swing")
        parts = [clearance.share_of(scene, 4.0, set(), share=(n, 3)) for n in (2, 0, 1)]
        self.assertEqual(clearance.combine(parts, clearance.header("motion", "swing", 4.0, 9, set(), (), False)),
                         {key: value for key, value in once.items() if key not in ("inputs", "checked")})


class Controls(unittest.TestCase):
    def test_a_displaced_solid_is_reported_as_interfering(self):
        """Control: catches a check that cannot fail. The block is moved into the slider's way."""
        assembly = built(lambda d: d["solids"][2].update(place=[{"kind": "translation", "travelMm": [0, 12, 0]}]))
        result = clearance.along(assembly, "slide", min_gap=1.0)
        row = pair(result, "block", "slider")
        self.assertTrue(row["closerThanMinGap"] and row["proven"])
        self.assertGreater(row["overlapMm3"], 0.0)
        self.assertEqual(result["closer"], [["block", "slider"]])

    def test_a_hit_between_coarse_samples_is_caught(self):
        """Catches fixed-step sampling coming back: a pin the arm passes through is clear at every quarter of the stroke."""
        def add_pin(d):
            angle = math.radians(100)
            d["solids"].append({"name": "pin", "group": "base", "shape": {
                "kind": "cylinder", "fromMm": [90 * math.cos(angle), 90 * math.sin(angle), 0], "toMm": [90 * math.cos(angle), 90 * math.sin(angle), 10], "radiusMm": 1}})
        assembly = built(add_pin)
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            placed = assembly.at_motion("swing", t)
            self.assertGreater(distance(placed["arm"], placed["pin"]), 5.0, f"coarse sample {t} should look clear")
        row = pair(clearance.along(assembly, "swing", min_gap=1.0), "arm", "pin")
        self.assertTrue(row["closerThanMinGap"])
        self.assertTrue(0.5 < row["t"] < 0.75)

    def test_the_depth_limit_is_reported_not_hidden(self):
        """Catches an unsettled pair being passed off as proven."""
        row = pair(clearance.along(built(), "swing", min_gap=POST_GAP - 0.001, depth=2), "arm", "post")
        self.assertEqual((row["proven"], row["closerThanMinGap"], row["lowerBoundMm"]), (False, False, None))
        self.assertEqual(len(row["unresolved"]), 2)


class Inputs(unittest.TestCase):
    def test_declared_contacts_and_absent_solids_are_data(self):
        """Catches a declared contact still being measured, or an absent solid still being in the way."""
        assembly = built(lambda d: d["solids"][2].update(place=[{"kind": "translation", "travelMm": [0, 12, 0]}]))
        declared = clearance.along(assembly, "slide", min_gap=1.0, contacts=[["slider", "block"]])
        self.assertEqual((declared["closer"], declared["counts"]["declaredContacts"], declared["declaredContacts"]), ([], 1, [["block", "slider"]]))
        gone = clearance.along(assembly, "slide", min_gap=1.0, absent=["block"])
        self.assertEqual((gone["closer"], gone["counts"]["pairs"]), ([], 10))
        with self.assertRaisesRegex(DesignError, 'names the solid "blok"'):
            clearance.along(assembly, "slide", contacts=[["slider", "blok"]])

    def test_a_still_pose_lists_only_pairs_closer_than_asked(self):
        """Catches a pose check that misses an overlap, or floods the result with distant pairs."""
        assembly = built(lambda d: d["solids"][4].update(place=[{"kind": "translation", "travelMm": [65, -12, 0]}]))
        result = clearance.at_pose(assembly, "end", min_gap=0.0)
        self.assertEqual(result["closer"], [["block", "slider"]])
        self.assertAlmostEqual(result["pairs"][0]["overlapMm3"], 5 * 7 * 10, places=6)
        self.assertEqual(clearance.at_pose(built(), "end", min_gap=0.0)["closer"], [])
        near = clearance.at_pose(built(), "end", min_gap=5.5)
        self.assertEqual(near["closer"], [])      # the slider is still 50 mm short of the block at this pose


if __name__ == "__main__":
    unittest.main()
