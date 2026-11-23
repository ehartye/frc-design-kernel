"""The motion vocabulary: operations at a stroke fraction, curves, and movement through poses."""
import math
import unittest

from frc_design_kernel.motion import matrix as mx
from frc_design_kernel.motion import ops, paths, screw


def near(test, a, b, places=9):
    for x, y in zip(a, b):
        test.assertAlmostEqual(x, y, places=places)


T = lambda v: {"kind": "translation", "travelMm": v}
R = lambda o, a, d: {"kind": "rotation", "originMm": o, "axis": a, "travelDeg": d}


class Operations(unittest.TestCase):
    def test_translation_scales_with_t(self):
        """Catches a translation that ignores the stroke fraction."""
        near(self, mx.apply(ops.at([T([10, 0, -4])], 0.25), (1, 1, 1)), (3.5, 1, 0))

    def test_rotation_turns_about_its_origin_by_the_right_hand_rule(self):
        """Catches a turn about the wrong point or in the wrong direction."""
        near(self, mx.apply(ops.at([R([10, 0, 0], [0, 0, 2], 90)]), (11, 0, 0)), (10, 1, 0))
        near(self, mx.apply(ops.at([R([10, 0, 0], [0, 0, 1], 90)], 0.5), (11, 0, 0)), (10 + math.sqrt(0.5), math.sqrt(0.5), 0))

    def test_gravity_drop_law(self):
        """Catches a change to the drop law h * ((1 - w) * t + w * t * t), which other tools rely on."""
        op = {"kind": "gravity-drop", "fallMm": 100, "quadraticFraction": 1}
        near(self, mx.apply(ops.at([op], 0.5), (0, 0, 0)), (0, 0, -25))
        op = {"kind": "gravity-drop", "fallMm": 100, "quadraticFraction": 0.5}
        near(self, mx.apply(ops.at([op], 0.5), (0, 0, 0)), (0, 0, -37.5))

    def test_operations_apply_in_list_order(self):
        """Catches composition in the wrong order: slide then turn is not turn then slide."""
        slide, turn = T([10, 0, 0]), R([0, 0, 0], [0, 0, 1], 90)
        near(self, mx.apply(ops.at([slide, turn]), (0, 0, 0)), (0, 10, 0))
        near(self, mx.apply(ops.at([turn, slide]), (0, 0, 0)), (10, 0, 0))

    def test_each_operation_is_evaluated_at_t_not_one_after_another(self):
        """Catches staging the operations in sequence; the vocabulary runs them together at the same t."""
        near(self, mx.apply(ops.at([T([10, 0, 0]), T([0, 20, 0])], 0.5), (0, 0, 0)), (5, 10, 0))

    def test_inverse_undoes(self):
        """Catches a wrong inverse, which would bend every movement through poses."""
        m = ops.at([R([3, 4, 5], [1, 2, 3], 71), T([7, -2, 9])])
        self.assertLess(mx.gap(mx.compose(mx.inverse(m), m), mx.IDENTITY), 1e-9)


class Paths(unittest.TestCase):
    def path(self, curve, points, t):
        return mx.apply(ops.at([{"kind": "path", "curve": curve, "throughMm": points}], t), points[0])

    def test_straight_path_is_measured_by_length(self):
        """Catches a path that moves by point count, not by distance."""
        points = [[0, 0, 0], [30, 0, 0], [30, 10, 0]]
        near(self, self.path("straight", points, 0.5), (20, 0, 0))
        near(self, self.path("straight", points, 1.0), (30, 10, 0))

    def test_arc_stays_on_its_circle_and_passes_the_middle_point(self):
        """Catches an arc that cuts the corner or goes the short way round."""
        points = [[100, 0, 0], [0, 100, 0], [0, -100, 0]]     # three quarters of a circle about the origin
        for t in (0.0, 0.2, 0.5, 0.9, 1.0):
            self.assertAlmostEqual(mx.length(self.path("arc", points, t)), 100.0, places=9)
        near(self, self.path("arc", points, 1 / 3), (0, 100, 0))
        near(self, self.path("arc", points, 1.0), (0, -100, 0))
        near(self, self.path("arc", points, 2 / 3), (-100, 0, 0))

    def test_smooth_path_passes_through_every_point(self):
        """Catches a smooth curve that only comes near its points."""
        points = [[0, 0, 0], [50, 40, 0], [120, 30, 20], [160, 90, 20]]
        fine = paths.smooth_points(tuple(tuple(float(v) for v in p) for p in points))
        for p in points:
            self.assertLess(min(mx.length(mx.sub(q, p)) for q in fine), 1e-9)
        near(self, self.path("smooth", points, 1.0), points[-1])

    def test_a_path_slides_without_turning(self):
        """Catches a path that rotates the body; it is a slide only."""
        m = ops.at([{"kind": "path", "curve": "arc", "throughMm": [[100, 0, 0], [0, 100, 0], [-100, 0, 0]]}], 0.7)
        self.assertEqual((m[0], m[5], m[10]), (1.0, 1.0, 1.0))


class ThroughPoses(unittest.TestCase):
    def test_a_swing_between_two_angles_turns_about_the_pivot(self):
        """Catches the arm cutting a straight chord between two poses when it should swing about its pivot."""
        pivot = [0, 0, 300]
        low, high = mx.IDENTITY, ops.at([R(pivot, [0, -1, 0], 90)])
        tip = (200, 0, 300)
        for s in (0.0, 0.25, 0.5, 1.0):
            there = mx.apply(screw.between(low, high, s), tip)
            self.assertAlmostEqual(mx.length(mx.sub(there, pivot)), 200.0, places=8)
        near(self, mx.apply(screw.between(low, high, 0.5), tip), (200 * math.sqrt(0.5), 0, 300 + 200 * math.sqrt(0.5)), places=8)

    def test_same_heading_gives_a_straight_slide(self):
        """Catches a divide by zero or a wobble when the two poses differ only by a slide."""
        near(self, mx.apply(screw.between(mx.IDENTITY, mx.translation((10, 20, 0)), 0.5), (1, 1, 1)), (6, 11, 1))

    def test_half_turn_and_ends_are_exact(self):
        """Catches the half-turn case, where the axis cannot be read the usual way."""
        end = ops.at([R([5, 0, 0], [0, 0, 1], 180), T([0, 0, 40])])
        self.assertLess(mx.gap(screw.between(mx.IDENTITY, end, 1.0), end), 1e-6)
        near(self, mx.apply(screw.between(mx.IDENTITY, end, 0.5), (6, 0, 0)), (5, 1, 20), places=6)

    def test_through_shares_the_stroke_evenly(self):
        """Catches a motion through three poses that skips or rushes the middle one."""
        a, b, c = mx.IDENTITY, mx.translation((10, 0, 0)), mx.translation((10, 30, 0))
        near(self, mx.apply(screw.through([a, b, c], 0.5), (0, 0, 0)), (10, 0, 0))
        near(self, mx.apply(screw.through([a, b, c], 0.75), (0, 0, 0)), (10, 15, 0))
        near(self, mx.apply(screw.through([a, b, c], 1.0), (0, 0, 0)), (10, 30, 0))


if __name__ == "__main__":
    unittest.main()
