"""The shapes: each primitive has the volume and bounds arithmetic says it should, and bad ones are refused."""
import math
import unittest

from frc_design_kernel import DesignError
from frc_design_kernel.builder.shape import solid
from frc_design_kernel.kernel import props


def no_custom(name, parameters, where):
    raise AssertionError("no custom shape expected")


def made(entry):
    return solid(entry, "test shape", no_custom)


def near(test, a, b, places=6):
    for x, y in zip(a, b):
        test.assertAlmostEqual(x, y, places=places)


BOX = {"kind": "box", "fromMm": [0, 0, 0], "toMm": [10, 20, 30]}


class Primitives(unittest.TestCase):
    def test_box_from_corners_in_any_order(self):
        """Catches a box that depends on which corner is given first (mirrored copies give them reversed)."""
        shape = made({"kind": "box", "fromMm": [10, -20, 30], "toMm": [0, 0, 0]})
        self.assertAlmostEqual(props.volume(shape), 6000.0)
        near(self, props.bounds(shape), [0, -20, 0, 10, 0, 30])

    def test_cylinder_between_two_points(self):
        """Catches a cylinder with the wrong axis, length or radius."""
        shape = made({"kind": "cylinder", "fromMm": [0, 0, 0], "toMm": [0, 40, 0], "radiusMm": 5})
        self.assertAlmostEqual(props.volume(shape), math.pi * 25 * 40, places=6)
        near(self, props.bounds(shape), [-5, 0, -5, 5, 40, 5])

    def test_cylinder_pie_slice(self):
        """Catches a slice that turns the wrong way or starts from the wrong direction."""
        shape = made({"kind": "cylinder", "fromMm": [0, 0, 0], "toMm": [0, 0, 10], "radiusMm": 20, "sweepDeg": 90, "sweepFrom": [0, 1, 0]})
        self.assertAlmostEqual(props.volume(shape), math.pi * 400 * 10 / 4, places=6)
        near(self, props.bounds(shape), [-20, 0, 0, 0, 20, 10])

    def test_sphere(self):
        """Catches a sphere with the wrong radius or centre."""
        shape = made({"kind": "sphere", "centerMm": [1, 2, 3], "radiusMm": 10})
        self.assertAlmostEqual(props.volume(shape), 4 / 3 * math.pi * 1000, places=5)
        near(self, props.bounds(shape), [-9, -8, -7, 11, 12, 13])

    def test_prism_in_each_plane(self):
        """Catches an outline drawn in the wrong plane or pushed along the wrong axis."""
        outline = [[0, 0], [10, 0], [0, 6]]
        wanted = {"xy": [0, 0, 2, 10, 6, 5], "xz": [0, 2, 0, 10, 5, 6], "yz": [2, 0, 0, 5, 10, 6]}
        for plane, box in wanted.items():
            shape = made({"kind": "prism", "plane": plane, "outlineMm": outline, "fromMm": 5, "toMm": 2})
            self.assertAlmostEqual(props.volume(shape), 30 * 3, places=6, msg=plane)
            near(self, props.bounds(shape), box)

    def test_round_tube_is_hollow(self):
        """Catches a tube drawn as a solid bar, or with the wall on the wrong side."""
        shape = made({"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 100], "outerDiameterMm": 30, "wallMm": 2})
        self.assertAlmostEqual(props.volume(shape), math.pi * (15 ** 2 - 13 ** 2) * 100, places=5)
        near(self, props.bounds(shape), [-15, -15, 0, 15, 15, 100])

    def test_rectangular_tube_height_follows_up(self):
        """Catches width and height being swapped, or the section not being square to the tube."""
        entry = {"kind": "tube", "section": "rectangular", "fromMm": [0, 0, 0], "toMm": [100, 0, 0], "widthMm": 20, "heightMm": 50, "wallMm": 3}
        shape = made(entry)
        self.assertAlmostEqual(props.volume(shape), (20 * 50 - 14 * 44) * 100, places=5)
        near(self, props.bounds(shape), [0, -10, -25, 100, 10, 25])
        near(self, props.bounds(made({**entry, "up": [0, 1, 0]})), [0, -25, -10, 100, 25, 10])

    def test_union_difference_intersection(self):
        """Catches a boolean that keeps the wrong side."""
        other = {"kind": "box", "fromMm": [5, 0, 0], "toMm": [15, 20, 30]}
        self.assertAlmostEqual(props.volume(made({"kind": "union", "of": [BOX, other]})), 9000.0)
        self.assertAlmostEqual(props.volume(made({"kind": "difference", "from": BOX, "cut": [other]})), 3000.0)
        self.assertAlmostEqual(props.volume(made({"kind": "intersection", "of": [BOX, other]})), 3000.0)


class Refusals(unittest.TestCase):
    """Controls: the one-solid rule and the size checks are shown to fail."""

    def expect(self, entry, pattern):
        with self.assertRaisesRegex(DesignError, pattern):
            made(entry)

    def test_two_separate_pieces_are_not_one_solid(self):
        """Catches a union of pieces that do not touch slipping through as one named solid."""
        far = {"kind": "box", "fromMm": [50, 0, 0], "toMm": [60, 20, 30]}
        self.expect({"kind": "union", "of": [BOX, far]}, "test shape: This shape makes 2 solids, not exactly one")

    def test_a_cut_that_removes_everything_is_refused(self):
        """Catches an empty result being exported as a solid."""
        self.expect({"kind": "difference", "from": BOX, "cut": [{"kind": "box", "fromMm": [-1, -1, -1], "toMm": [11, 21, 31]}]}, "makes 0 solids")

    def test_sizes_must_make_sense(self):
        """Catches a zero or negative size reaching the CAD kernel, which would crash or draw nonsense."""
        self.expect({"kind": "box", "fromMm": [0, 0, 0], "toMm": [10, 0, 30]}, "zero size along an axis")
        self.expect({"kind": "cylinder", "fromMm": [0, 0, 0], "toMm": [0, 0, 5], "radiusMm": -1}, "radiusMm must be greater than 0")
        self.expect({"kind": "cylinder", "fromMm": [1, 1, 1], "toMm": [1, 1, 1], "radiusMm": 2}, "fromMm and toMm are the same point")
        self.expect({"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 9], "outerDiameterMm": 10, "wallMm": 5}, "leaves no opening")
        self.expect({"kind": "tube", "section": "rectangular", "fromMm": [0, 0, 0], "toMm": [0, 0, 9], "widthMm": 10, "wallMm": 1}, 'is missing "heightMm"')

    def test_a_folded_outline_is_refused(self):
        """Catches a self-crossing outline being exported as a broken solid."""
        with self.assertRaises(DesignError):
            made({"kind": "prism", "plane": "xy", "outlineMm": [[0, 0], [10, 10], [10, 0], [0, 10]], "fromMm": 0, "toMm": 5})


if __name__ == "__main__":
    unittest.main()
