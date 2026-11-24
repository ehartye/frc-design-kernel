"""The cone and the rounded box: their volumes, refusals and symmetry, and every piece class building from a design source."""
import math
import unittest

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.builder.shape import solid
from frc_design_kernel.kernel import props
from frc_design_kernel.measure import symmetry
from frc_design_kernel.motion import matrix as mx
from frc_design_kernel.source import schema
from frc_design_kernel.trials import convex
from frc_design_kernel.trials.mujoco_scene import Model
from frc_design_kernel.trials.ready import GOOD, breakdown, report

from .helpers import edited, load_data


def no_custom(name, parameters, where):
    raise AssertionError("no custom shape expected")


def made(entry):
    return solid(entry, "test shape", no_custom)


def frustum(height, big, small):
    return math.pi * height / 3 * (big ** 2 + big * small + small ** 2)


def rounded(sides, r):
    """A box with every edge rounded to r: the inner box grown by a ball of radius r (Steiner's formula)."""
    a, b, c = (s - 2 * r for s in sides)
    return a * b * c + 2 * r * (a * b + b * c + c * a) + math.pi * r ** 2 * (a + b + c) + 4 / 3 * math.pi * r ** 3


CONE = {"kind": "cone", "fromMm": [0, 0, 0], "toMm": [30, 40, 0], "radiusFromMm": 20, "radiusToMm": 8}
BOX = {"kind": "box", "fromMm": [0, 0, 0], "toMm": [40, 30, 20]}

PIECES = {      # one invented representative of each piece class
    "ball": {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 120},
    "ring": {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 150, "minorRadiusMm": 25},
    "tube": {"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 200], "outerDiameterMm": 80, "wallMm": 4},
    "bar": {"kind": "cylinder", "fromMm": [0, -150, 0], "toMm": [0, 150, 0], "radiusMm": 15},
    "crate": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [300, 300, 300]},
    "cube": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [240, 240, 240], "edgeRadiusMm": "=240 / 8"},
    "cone": {"kind": "cone", "fromMm": [0, 0, 0], "toMm": [0, 0, "=330"], "radiusFromMm": 110, "radiusToMm": 0},
}


class Cone(unittest.TestCase):
    def test_frustum_volume_and_reach(self):
        """Catches a cone with the wrong length, radii, end or direction: its volume and bounds would be off."""
        shape = made(CONE)
        self.assertAlmostEqual(props.volume(shape), frustum(50, 20, 8), places=4)
        low, high = props.bounds(shape)[:3], props.bounds(shape)[3:]
        self.assertLess(low[0], -10)        # the wide end (radius 20) sits at the origin, not at toMm
        self.assertGreater(high[1], 40)

    def test_pointed_cone_builds(self):
        """Catches a cone with a 0 radius at either end being refused or crashing the CAD kernel."""
        for ends in ((0, 12), (12, 0)):
            shape = made({**CONE, "radiusFromMm": ends[0], "radiusToMm": ends[1]})
            self.assertAlmostEqual(props.volume(shape), frustum(50, 12, 0), places=4, msg=ends)

    def test_equal_radii_build_a_cylinder(self):
        """Catches a cone with equal radii failing, when it is simply a round bar."""
        self.assertAlmostEqual(props.volume(made({**CONE, "radiusToMm": 20})), math.pi * 400 * 50, places=4)

    def test_body_of_revolution_along_from_to(self):
        """Catches a cone classified as general, or given an axis that is not the line from fromMm to toMm."""
        for ends in ((20, 8), (0, 12)):
            found = symmetry.classify(made({**CONE, "radiusFromMm": ends[0], "radiusToMm": ends[1]}), "cone")
            self.assertEqual(found["class"], "body of revolution")
            for got, want in zip(found["axis"], [0.6, 0.8, 0.0]):
                self.assertAlmostEqual(got, want, places=9)


class RoundedBox(unittest.TestCase):
    def test_volume_and_bounds(self):
        """Catches rounding that misses edges or corners, uses the wrong radius, or moves the box."""
        shape = made({**BOX, "edgeRadiusMm": 5})
        self.assertAlmostEqual(props.volume(shape) / rounded((40, 30, 20), 5), 1.0, places=5)
        for got, want in zip(props.bounds(shape), [0, 0, 0, 40, 30, 20]):
            self.assertAlmostEqual(got, want, places=3)

    def test_zero_is_a_plain_box(self):
        """Catches edgeRadiusMm 0 failing or changing the box (0 and absent both mean sharp)."""
        self.assertAlmostEqual(props.volume(made({**BOX, "edgeRadiusMm": 0})), 24000.0)
        self.assertEqual(symmetry.classify(made({**BOX, "edgeRadiusMm": 0}), "box"), {"class": "prismatic"})

    def test_rounded_box_is_not_called_prismatic(self):
        """Catches a rounded box reported as prismatic: its section changes near every face. The sharp box is the control."""
        self.assertEqual(symmetry.classify(made({**BOX, "edgeRadiusMm": 5}), "box"), {"class": "general"})
        self.assertEqual(symmetry.classify(made(BOX), "box"), {"class": "prismatic"})


class Refusals(unittest.TestCase):
    """Controls: each size check is shown to fail, naming the field and a fix."""

    def expect(self, entry, pattern):
        with self.assertRaisesRegex(DesignError, pattern):
            made(entry)

    def test_cone_sizes_must_make_sense(self):
        """Catches a cone with no radius, no length or a negative radius reaching the CAD kernel."""
        self.expect({**CONE, "radiusFromMm": 0, "radiusToMm": 0}, "at least one of radiusFromMm and radiusToMm")
        self.expect({**CONE, "toMm": [0, 0, 0]}, "fromMm and toMm are the same point")
        self.expect({**CONE, "radiusToMm": -1}, "radiusToMm must be 0 or more")
        self.expect({**CONE, "radiusFromMm": -1}, "radiusFromMm must be 0 or more")

    def test_edge_radius_must_leave_flat_faces(self):
        """Catches an edge radius of half the smallest side or more, which leaves no box, being sent to the CAD kernel."""
        self.expect({**BOX, "edgeRadiusMm": 10}, "edgeRadiusMm 10 must be less than 10, half the smallest side")
        self.expect({**BOX, "edgeRadiusMm": 12}, "half the smallest side")
        self.expect({**BOX, "edgeRadiusMm": -1}, "edgeRadiusMm must be 0 or more")
        made({**BOX, "edgeRadiusMm": 9.9})        # control: just under half still builds


class Grammar(unittest.TestCase):
    def test_schema_takes_the_new_fields_and_refuses_an_unknown_one(self):
        """Catches a cone or rounded box the schema refuses, or a mistyped cone field slipping through unnoticed."""
        root = schema.load_schema()
        shape = root["$defs"]["shape"]
        schema.check(CONE, shape, root, "cone")
        schema.check({**BOX, "edgeRadiusMm": "=2 + 3"}, shape, root, "box")
        with self.assertRaisesRegex(DesignError, "radiusMm"):
            schema.check({**CONE, "radiusMm": 5}, shape, root, "cone")
        with self.assertRaises(DesignError):
            schema.check({**BOX, "edgeRadius": 5}, shape, root, "box")

    def test_every_piece_class_validates_and_builds_from_a_design_source(self):
        """Catches a piece class, or a solid made from a cone or rounded box, that the design source refuses or cannot build."""
        def change(data):
            data["pieces"] = {name: {"shape": shape, "massKg": 1.0} for name, shape in PIECES.items()}
            data["solids"].append({"name": "funnel", "group": "base", "massKg": 0.2, "shape": {
                "kind": "cone", "fromMm": [25, 20, "=tall + 10"], "toMm": [25, 20, "=tall + 60"], "radiusFromMm": 10, "radiusToMm": "=tall / 4"}})
            data["solids"][0]["shape"]["edgeRadiusMm"] = "=tall / 25"
        design = load_data(edited(change))
        assembly = kernel.build(design)
        self.assertAlmostEqual(props.volume(assembly.solids["funnel"].shape), frustum(50, 25, 10), places=4)
        self.assertAlmostEqual(props.volume(assembly.solids["block"].shape) / rounded((50, 40, 100), 4), 1.0, places=5)
        for name, piece in design.data["pieces"].items():
            self.assertGreater(props.volume(solid(piece["shape"], f'pieces "{name}"', no_custom)), 0, msg=name)
        self.assertEqual(len(design.data["pieces"]), 7)


class TrialScenes(unittest.TestCase):
    """The 3D trial scene takes the new shapes as they really are. MuJoCo itself is not needed to build the scene."""

    def kinds(self, shape):
        model = Model()
        model.add("s", "surface", shape, mx.translation([0, 0, 0]), "steel")
        return model.kinds["s"]

    def test_cone_is_convex_and_a_ring_has_a_reason(self):
        """Catches a cone or ring solid crashing the 3D scene (a KeyError) instead of being broken down or named."""
        self.assertEqual(breakdown(CONE), "convex")
        self.assertEqual(self.kinds(CONE), ["mesh"])
        ring = breakdown(PIECES["ring"])
        self.assertNotIn(ring, GOOD)        # control: a ring is not convex, and is not passed off as one
        self.assertIn("ring", ring)

    def test_rounded_box_is_meshed_not_a_sharp_box(self):
        """Catches a rounded box sent to the engine as a sharp box, which fills in its rounded edges. The sharp box is the control."""
        self.assertEqual(self.kinds({**BOX, "edgeRadiusMm": 5}), ["mesh"])
        self.assertEqual(self.kinds(BOX), ["box"])
        self.assertEqual(self.kinds({**BOX, "edgeRadiusMm": 0}), ["box"])

    def test_box_less_boxes_is_exact_only_for_sharp_boxes(self):
        """Catches a cut rounded box being split as sharp boxes and called exact. Sharp boxes are the control."""
        cut = {"kind": "box", "fromMm": [0, 0, 0], "toMm": [10, 10, 30]}
        sharp = {"kind": "difference", "from": BOX, "cut": [cut]}
        found = convex.pieces(sharp)
        self.assertIsNotNone(found)
        self.assertIsNone(found[1])
        self.assertIsNone(convex.pieces({**sharp, "from": {**BOX, "edgeRadiusMm": 5}}))
        self.assertIsNone(convex.pieces({**sharp, "cut": [{**cut, "edgeRadiusMm": 2}]}))

    def test_rounded_box_piece_is_not_listed_as_primitive(self):
        """Catches a rounded-box piece listed as a primitive an engine can take whole. The sharp box and the ball are the control."""
        def change(data):
            data["pieces"] = {name: {"shape": PIECES[name], "massKg": 1.0} for name in ("crate", "cube", "ball", "cone")}
        found = report(kernel.build(load_data(edited(change))))["piecesNotPrimitive"]
        self.assertEqual(found, ["cone", "cube"])


if __name__ == "__main__":
    unittest.main()
