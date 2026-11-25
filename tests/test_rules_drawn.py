"""Outlines and shapes of the example, in mm: every one is drawn, for both alliances, against hand-computed inches."""
import math
import unittest

from .rules_cases import Derived

IN = 25.4
LONG, WIDE = 612.40, 300      # the example's field, in inches, for the first variant
HALF = math.sqrt(3) / 2


def area(points):
    """The area inside some points in mm, in square inches."""
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, [*points[1:], points[0]]))) / 2 / IN ** 2


class Outlines(Derived):
    """rules.outline: points on the field, in mm."""

    def points(self, got, *inches):
        self.assertEqual(len(got), len(inches), got)
        for point, inch in zip(got, inches):
            for a, b in zip(point, inch):
                self.assertAlmostEqual(a / IN, b, places=6)

    def test_a_rectangle(self):
        """Catches a rectangle whose two lengths change places, or that stands on a corner."""
        rules = self.rules()
        self.points(rules.outline("yard"), (0, 29.5), (54, 29.5), (54, 50.5), (0, 50.5))
        self.points(rules.outline("yard", "red"), (LONG, 270.5), (LONG - 54, 270.5), (LONG - 54, 249.5), (LONG, 249.5))

    def test_a_turned_rectangle(self):
        """Catches an outline that is not turned by its record's facing, or turned clockwise."""
        rules = self.rules()
        corner = 120 + 20 * HALF - 6, 260 + 10 + 12 * HALF
        self.points(rules.outline("fold")[2:3], corner)
        self.points(rules.outline("fold", "red")[2:3], (LONG - corner[0], WIDE - corner[1]))
        self.assertAlmostEqual(area(rules.outline("fold")), 960)

    def test_a_hexagon(self):
        """Catches a hexagon whose points look where its flats should, or that is measured across its points."""
        rules = self.rules()
        out = 40 / math.sqrt(3)
        self.points(rules.outline("paddock"), (131, 220 + out), (131 - 20, 220 + out / 2), (131 - 20, 220 - out / 2), (131, 220 - out), (131 + 20, 220 - out / 2), (131 + 20, 220 + out / 2))
        self.assertAlmostEqual(area(rules.outline("paddock", "red")), 2 * math.sqrt(3) * 400)
        turned = self.rules(lambda d: d["field"]["zones"]["paddock"].update(faces="30 deg"))
        self.points(turned.outline("paddock")[:1], (131 - out / 2, 220 + out * HALF))

    def test_a_circle(self):
        """Catches a circle that is as wide as its radius, or that comes back as its size and not as points."""
        points = self.rules().outline("pond")
        self.assertEqual(len(points), 72)
        self.points(points[:1], (LONG / 2 + 23, 150))
        for x, y in points:
            self.assertAlmostEqual(math.hypot(x / IN - LONG / 2, y / IN - 150), 23)

    def test_points_on_the_field(self):
        """Catches points that are measured from a record, or a mirror image with left and right not swapped."""
        rules = self.rules()
        blue = [(0, 0), (60, 0), (60, 18), (18, 18), (18, 60), (0, 60)]
        self.points(rules.outline("lane"), *blue)
        self.points(rules.outline("lane", "red"), *[(LONG - x, y) for x, y in blue])
        self.assertAlmostEqual(area(rules.outline("lane")), 1836)

    def test_every_outline_of_the_example(self):
        """Catches an outline that cannot be drawn, or a red one that is not as big as blue's, or not on the field."""
        rules = self.rules()
        zones = [r.id for r in rules.book.of_kind("zone").values() if "outline" in r.data]
        self.assertEqual(zones, ["yard", "paddock", "pond", "lane", "fold"])
        for name in zones:
            self.assertAlmostEqual(area(rules.outline(name)), area(rules.outline(name, "red")), msg=name)
            for x, y in rules.outline(name) + rules.outline(name, "red"):
                self.assertTrue(-1e-6 <= x / IN <= LONG + 1e-6 and -1e-6 <= y / IN <= WIDE + 1e-6, (name, x, y))

    def test_the_variant_and_the_spot(self):
        """Catches red's outline on another field's length, or an outline that stands at the wrong spot."""
        self.points(self.rules().outline("lane", "red", field="bolted")[:1], (611.75, 0))
        spots = {"a": {"at": ["100 in", "50 in"]}, "b": {"at": ["100 in", "90 in"], "faces": "90 deg"}}
        rules = self.rules(lambda d: (d["field"]["zones"]["fold"].pop("at"), d["field"]["zones"]["fold"].update(spots=spots)))
        self.points(rules.outline("fold", spot="b")[2:3], (88, 110))
        self.wrong(lambda: rules.outline("fold"), "fold", "spot", "a, b")
        high = self.rules(lambda d: d["field"]["zones"]["fold"]["at"].append("2 in"))
        self.assertEqual(high.outline("fold", "red"), self.rules().outline("fold", "red"))

    def test_the_outline_of_an_opening(self):
        """Catches an opening's outline that is put on the field: it is about its own middle."""
        rules = self.rules()
        self.points(rules.get("barn.opening.outline"), (-18, -8), (18, -8), (18, 8), (-18, 8))
        self.points(rules.get("chimney.opening.outline", alliance="red")[:2], (20 / math.sqrt(3), 0), (10 / math.sqrt(3), 10))
        self.assertEqual(rules.get("yard.outline", alliance="red"), rules.outline("yard", "red"))
        self.is_(rules.get("yard.outline.rectangle.x"), "length", 54 * IN)
        self.is_(rules.get("yard.outline.rectangle.x", alliance="red"), "length", 54 * IN)

    def test_an_opening_that_is_mirrored(self):
        """Catches an unsymmetric opening whose left and right do not change places in a mirrored copy, or do in a turned one."""
        hexagon = {"hexagon": {"flats": "20 in", "points": "10 deg"}}
        for symmetry, sign in [("mirror", -1), ("turn", 1)]:
            rules = self.rules(lambda d: (d["places"]["chimney"]["opening"].update(outline=hexagon), d["places"]["chimney"].update(symmetry=symmetry)))
            corners = [(11.37158, 2.005116), (3.949308, 10.850636)]      # 20 / sqrt(3) from the middle, at 10 deg and at 70 deg
            self.points(rules.get("chimney.opening.outline")[:2], *corners)
            self.points(rules.get("chimney.opening.outline", alliance="red")[:2], *[(x, y * sign) for x, y in corners])

    def test_no_outline(self):
        """Catches an outline made up for something that has none."""
        rules = self.rules()
        self.wrong(lambda: rules.outline("stands"), "stands", "An area for people, off the field.")
        self.wrong(lambda: rules.outline("crate"), "crate", "outline")
        self.wrong(lambda: rules.outline("yrad"), "yard")
        self.wrong(lambda: rules.outline("yard", "green"), "green", "blue")


class Shapes(Derived):
    """rules.get of a shape: the library's grammar, in mm. What is round is about its own centre; all else stands on 0."""

    def same(self, got, expected):
        """The same shape, number for number, where expected is in inches."""
        self.assertEqual(type(got) in (dict, list, tuple), type(expected) in (dict, list, tuple), (got, expected))
        if isinstance(expected, dict):
            self.assertEqual(set(got), set(expected))
            for name in expected:
                self.same(got[name], expected[name]) if name != "axis" else self.assertEqual(got[name], expected[name])
        elif isinstance(expected, (list, tuple)):
            self.assertEqual(len(got), len(expected))
            for a, b in zip(got, expected):
                self.same(a, b)
        elif isinstance(expected, str):
            self.assertEqual(got, expected)
        else:
            self.assertAlmostEqual(got / IN, expected, places=6)

    def test_a_box(self):
        """Catches a box that stands on a corner, or whose sizes change places."""
        self.same(self.rules().get("crate.shape"), {"kind": "box", "fromMm": [-11, -27.5, 0], "toMm": [11, 27.5, 15]})

    def test_round_shapes(self):
        """Catches a ball, a ring, a cylinder or a tube that is not about its own centre, or a cylinder along the wrong axis."""
        rules = self.rules()
        self.same(rules.get("boulder.shape"), {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 7})
        self.same(rules.get("silo.shape"), {"kind": "cylinder", "fromMm": [0, 0, -18], "toMm": [0, 0, 18], "radiusMm": 5})
        self.same(rules.get("tyre.shape"), {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 8.5, "minorRadiusMm": 2.5})
        self.same(rules.get("culvert.shape"), {"kind": "tube", "section": "round", "fromMm": [-24, 0, 0], "toMm": [24, 0, 0], "outerDiameterMm": 18, "wallMm": 1})
        for axis, ends in [("x", ([-18, 0, 0], [18, 0, 0])), ("y", ([0, -18, 0], [0, 18, 0]))]:
            lying = self.rules(lambda d: d["field"]["solids"]["silo"]["shape"]["cylinder"].update(axis=axis))
            self.same(lying.get("silo.shape"), {"kind": "cylinder", "fromMm": ends[0], "toMm": ends[1], "radiusMm": 5})

    def test_a_prism(self):
        """Catches an outline inside a shape that is taken for points on the field, or a prism that hangs in the air."""
        rules = self.rules()
        self.same(rules.get("ramp.shape"), {"kind": "prism", "plane": "xy", "outlineMm": [[0, -12], [24, -12], [18, 12], [0, 12]], "fromMm": 0, "toMm": 3})
        tall = 30 * HALF
        self.same(rules.get("pen.shape"), {"kind": "prism", "plane": "xy", "outlineMm": [[tall * 2 / 3, 0], [-tall / 3, 15], [-tall / 3, -15]], "fromMm": 0, "toMm": 5})

    def test_shapes_of_shapes(self):
        """Catches a part that does not stand at its own `at`, or a cut that is joined."""
        rules = self.rules()
        self.same(rules.get("barn_body.shape"), {"kind": "difference", "from": {"kind": "box", "fromMm": [-10, -30, 0], "toMm": [10, 30, 80]},
                                                 "cut": [{"kind": "box", "fromMm": [-20, -18, 48], "toMm": [20, 18, 64]}]})
        got = rules.get("trestle.shape")
        self.same(got["of"][0], {"kind": "box", "fromMm": [-2, -20, 0], "toMm": [2, 20, 6]})
        out = 12 / math.sqrt(3)
        self.same({**got["of"][1], "outlineMm": got["of"][1]["outlineMm"][:2]}, {"kind": "prism", "plane": "xy", "outlineMm": [[out, 0], [out / 2, 6]], "fromMm": 4, "toMm": 12})
        self.assertEqual(got["kind"], "union")

    def test_a_ball_in_a_join_stands_too(self):
        """Catches a part of a join that is round and is placed by its middle."""
        rules = self.rules(lambda d: d["field"]["solids"]["trestle"]["shape"]["join"].__setitem__(1, {"at": ["1 in", "2 in", "5 in"], "ball": {"diameter": "4 in"}}))
        self.same(rules.get("trestle.shape")["of"][1], {"kind": "sphere", "centerMm": [1, 2, 7], "radiusMm": 2})

    def test_a_part_with_no_height(self):
        """Catches a part of a join that stands higher than its record when nobody says that it does, or that is mirrored the wrong way."""
        change = lambda d: (d["field"]["solids"]["trestle"].update(symmetry="mirror"),
                            d["field"]["solids"]["trestle"]["shape"]["join"].__setitem__(1, {"at": ["1 in", "19 in"], "box": ["4 in", "40 in", "9 in"]}))
        rules = self.rules(change)
        self.same(rules.get("trestle.shape")["of"][1], {"kind": "box", "fromMm": [-1, -1, 0], "toMm": [3, 39, 9]})
        self.same(rules.get("trestle.shape", alliance="red")["of"][1], {"kind": "box", "fromMm": [-1, -39, 0], "toMm": [3, 1, 9]})

    def test_pieces(self):
        """Catches a piece that is not about its own centre, by which an engine places it, or one whose size is an end of its tolerance."""
        rules = self.rules()
        self.same(rules.get("pumpkin.shape"), {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 4.25})
        self.same(rules.get("hoop.shape"), {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 3.5, "minorRadiusMm": 0.5})
        self.same(rules.get("bale.shape"), {"kind": "tube", "section": "round", "fromMm": [-4.625, 0, 0], "toMm": [4.625, 0, 0], "outerDiameterMm": 5, "wallMm": 1})
        standing = self.rules(lambda d: d["pieces"]["bale"]["shape"]["tube"].update(axis="z"))
        self.same(standing.get("bale.shape"), {"kind": "tube", "section": "round", "fromMm": [0, 0, -4.625], "toMm": [0, 0, 4.625], "outerDiameterMm": 5, "wallMm": 1})
        self.same(self.rules(lambda d: d["pieces"]["hoop"].update(shape={"box": ["2 in", "4 in", "6 in"]})).get("hoop.shape"), {"kind": "box", "fromMm": [-1, -2, 0], "toMm": [1, 2, 6]})

    def test_a_taper(self):
        """Catches a taper that is drawn as a solid that the library does not have."""
        rules = self.rules()
        got = rules.get("manger.shape")
        self.same(got.bottom, [[-15, -10], [15, -10], [15, 10], [-15, 10]])
        self.same(got.top, [[-10, -5], [10, -5], [10, 5], [-10, 5]])
        self.same(got.tall, 12)
        self.wrong(lambda: rules.solid("manger"), "manger", "taper")
        self.is_(rules.get("manger.shape.taper.tall"), "length", 12 * IN)
        self.same(rules.get("manger.shape.taper.top"), [[-10, -5], [10, -5], [10, 5], [-10, 5]])

    def test_a_part_of_a_shape(self):
        """Catches the sizes inside a shape that are taken for a shape."""
        rules = self.rules()
        for path in ["pen.shape.prism", "boulder.shape.ball", "manger.shape.taper"]:
            self.wrong(lambda: rules.get(path), path, "not one value")
        self.same([v.value for v in rules.get("crate.shape.box")], [22, 55, 15])
        self.same(rules.get("ramp.shape.prism.outline"), [[0, -12], [24, -12], [18, 12], [0, 12]])

    def test_a_shape_that_is_turned_does_not_change(self):
        """Catches a shape that is turned or moved: only where it stands changes."""
        rules = self.rules()
        for name in ["ramp", "crate", "culvert", "pen"]:
            self.assertEqual(rules.get(f"{name}.shape", alliance="red"), rules.get(f"{name}.shape"))

    def test_a_shape_that_is_mirrored(self):
        """Catches a mirrored field in which red's unsymmetric solid is blue's, only moved."""
        rules = self.rules(lambda d: d["field"].update(symmetry="mirror"))
        self.same(rules.get("ramp.shape", alliance="red")["outlineMm"], [[0, 12], [24, 12], [18, -12], [0, -12]])
        self.same(rules.get("barn_body.shape", alliance="red"), {"kind": "difference", "from": {"kind": "box", "fromMm": [-10, -30, 0], "toMm": [10, 30, 80]},
                                                                 "cut": [{"kind": "box", "fromMm": [-20, -18, 48], "toMm": [20, 18, 64]}]})


class Solids(Derived):
    """rules.solid: a shape and where it stands, as a design's solid has them, built with the CAD kernel."""

    def built(self, solid):
        from frc_design_kernel.builder import shape
        from frc_design_kernel.kernel import props, transform
        from frc_design_kernel.motion import ops
        made = transform.moved(shape.solid(solid["shape"], "it", None), ops.at(solid["place"]))
        return [n / IN for n in props.bounds(made)], props.volume(made) / IN ** 3

    def stands(self, solid, volume, *bounds):
        got, size = self.built(solid)
        for a, b in zip(got, bounds):
            self.assertAlmostEqual(a, b, places=4, msg=(got, bounds))
        self.assertAlmostEqual(size, volume, places=3)

    VOLUMES = {"crate": 22 * 55 * 15, "silo": math.pi * 25 * 36, "boulder": math.pi * 14 ** 3 / 6, "tyre": 2 * math.pi ** 2 * 8.5 * 2.5 ** 2, "culvert": math.pi * (81 - 64) * 48,
               "ramp": (24 + 18) / 2 * 24 * 3, "barn_body": 20 * 60 * 80 - 20 * 36 * 16, "pen": 30 * 30 * HALF / 2 * 5}

    def test_every_solid_of_the_example(self):
        """Catches a solid that cannot be built, or that stands in the ground or in the air, for either alliance."""
        rules = self.rules()
        solids = rules.book.of_kind("solid")
        self.assertEqual(set(solids) - set(self.VOLUMES), {"manger", "trestle"})
        for name in self.VOLUMES:
            blue, volume = self.built(rules.solid(name))
            self.assertAlmostEqual(volume, self.VOLUMES[name], places=3, msg=name)
            self.assertAlmostEqual(blue[2], 0, places=4, msg=name)
            red = [LONG - blue[3], WIDE - blue[4], blue[2], LONG - blue[0], WIDE - blue[1], blue[5]]
            self.stands(rules.solid(name, "red"), self.VOLUMES[name], *(red if solids[name].data.get("alliance") else blue))
            for low, high, size in [(blue[0], blue[3], LONG), (blue[1], blue[4], WIDE)]:
                self.assertTrue(-1e-4 <= low < high <= size + 1e-4, (name, blue))

    def test_where_they_stand(self):
        """Catches a solid that is moved before it is turned, or turned clockwise."""
        rules = self.rules()
        self.stands(rules.solid("crate"), self.VOLUMES["crate"], 120, 122.5, 0, 142, 177.5, 15)
        self.stands(rules.solid("crate", "red"), self.VOLUMES["crate"], LONG - 142, 122.5, 0, LONG - 120, 177.5, 15)
        self.stands(rules.solid("culvert"), self.VOLUMES["culvert"], 231, 246, 0, 249, 294, 18)
        self.stands(rules.solid("ramp"), self.VOLUMES["ramp"], 46, 138, 0, 70, 162, 3)
        self.stands(rules.solid("ramp", "red"), self.VOLUMES["ramp"], LONG - 70, 138, 0, LONG - 46, 162, 3)
        pen = 30 * HALF
        self.stands(rules.solid("pen"), self.VOLUMES["pen"], 180 - pen / 3, 95, 0, 180 + pen * 2 / 3, 125, 5)
        mirrored = self.rules(lambda d: d["field"].update(symmetry="mirror") or d["field"]["solids"]["ramp"].update(faces="90 deg"))
        self.stands(mirrored.solid("ramp"), self.VOLUMES["ramp"], 58, 150, 0, 82, 174, 3)
        self.stands(mirrored.solid("ramp", "red"), self.VOLUMES["ramp"], LONG - 82, 150, 0, LONG - 58, 174, 3)
        for alliance, longest in [("blue", 82), ("red", LONG - 82)]:     # the long side of the ramp is on the side of the field's middle
            made = mirrored.solid("ramp", alliance)
            corners = [(made["place"][1]["travelMm"][0] / IN - y / IN, x / IN) for x, y in made["shape"]["outlineMm"]]
            self.assertAlmostEqual(next(x for x, far in corners if abs(far - 24) < 1e-6), longest)
        higher = self.rules(lambda d: d["field"]["solids"]["boulder"]["at"].__setitem__(2, "3 in"))
        self.stands(higher.solid("boulder"), self.VOLUMES["boulder"], 193, 273, 3, 207, 287, 17)

    def test_what_is_round_rests(self):
        """Catches a ball, a ring, or a lying or standing cylinder or tube, that is half under the height it stands on."""
        ball = lambda z: self.rules(lambda d: d["field"]["solids"]["boulder"].update(at=["200 in", "100 in", z], shape={"ball": {"diameter": "= pumpkin.shape.ball.diameter"}}))
        self.same_place(ball("0 in"), "pumpkin", "boulder", 200, 100, 4.25)
        self.stands(ball("0 in").solid("boulder"), math.pi * 8.5 ** 3 / 6, 195.75, 95.75, 0, 204.25, 104.25, 8.5)
        self.stands(ball("10 in").solid("boulder", "red"), math.pi * 8.5 ** 3 / 6, LONG - 204.25, 195.75, 10, LONG - 195.75, 204.25, 18.5)
        for axis, half in [("x", (18, 5, 5)), ("y", (5, 18, 5)), ("z", (5, 5, 18))]:
            for form, size, volume in [("cylinder", {"diameter": "10 in"}, math.pi * 25 * 36), ("tube", {"inside": "6 in", "outside": "10 in"}, math.pi * (25 - 9) * 36)]:
                rules = self.rules(lambda d: d["field"]["solids"]["boulder"].update(at=["200 in", "100 in", "2 in"], shape={form: {**size, "length": "36 in", "axis": axis}}))
                a, b, c = half
                self.stands(rules.solid("boulder"), volume, 200 - a, 100 - b, 2, 200 + a, 100 + b, 2 + 2 * c)
        self.stands(self.rules().solid("tyre"), self.VOLUMES["tyre"], 229, 9, 0, 251, 31, 5)

    def same_place(self, rules, piece, solid, *centre):
        """A solid is the piece's shape, moved so that its centre is at centre."""
        self.assertEqual(rules.get(f"{solid}.shape"), rules.get(f"{piece}.shape"))
        self.assertEqual(rules.solid(solid)["shape"], rules.get(f"{piece}.shape"))
        for got, inch in zip(rules.solid(solid)["place"][1]["travelMm"], centre):
            self.assertAlmostEqual(got / IN, inch)

    def test_a_height_that_is_not_known(self):
        """Catches a solid put on the carpet when no source says where its foot is, or one asked of a thing with no shape or place."""
        rules = self.rules()
        self.wrong(lambda: rules.solid("trestle"), "trestle", "height")
        self.wrong(lambda: rules.solid("yard"), "yard", "shape")
        self.wrong(lambda: rules.solid("pumpkin"), "pumpkin", "at")

    def test_spots(self):
        """Catches a solid that stands at several spots and is drawn at the first."""
        spots = {"row": 2, "step": ["0 in", "60 in"], "first": {"at": ["131 in", "60 in", "0 in"], "faces": "90 deg"}}
        rules = self.rules(lambda d: (d["field"]["solids"]["boulder"].pop("at"), d["field"]["solids"]["boulder"].update(spots=spots, shape={"box": ["2 in", "4 in", "1 in"]})))
        self.stands(rules.solid("boulder", spot="2"), 8, 129, 119, 0, 133, 121, 1)
        self.wrong(lambda: rules.solid("boulder"), "spot", "1, 2")


if __name__ == "__main__":
    unittest.main()
