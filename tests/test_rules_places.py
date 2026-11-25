"""Where things stand: red's copies, spots, outlines and shapes of the example, against hand-computed inches."""
import math
import unittest

from .rules_cases import Derived, rename

IN = 25.4
LONG, WIDE = 612.40, 300      # the example's field, in inches, for the first variant
HALF = math.sqrt(3) / 2


class Moved(Derived):
    """Help: positions in inches."""

    def at(self, rules, path, *inches, **asked):
        got = rules.get(path, **asked)
        self.assertEqual(len(got), len(inches), path)
        for value, inch in zip(got, inches):
            self.assertEqual(value.kind, "length")
            self.assertAlmostEqual(value.value / IN, inch, places=6, msg=f"{path} {asked}")

    def faces(self, rules, path, degrees, **asked):
        self.is_(rules.get(path, **asked), "angle", degrees)


class Alliances(Moved):
    """Red is made from blue."""

    def test_a_turn(self):
        """Catches red's copy on the wrong side of a field that is turned, or looking the wrong way, or at another height."""
        rules = self.rules()
        self.at(rules, "crate.at", 131, 150, 0)
        self.at(rules, "crate.at", LONG - 131, 150, 0, alliance="red")
        self.faces(rules, "crate.faces", 180, alliance="red")
        self.at(rules, "fold.at", LONG - 120, 40, alliance="red")
        self.faces(rules, "fold.faces", 30)
        self.faces(rules, "fold.faces", 210, alliance="red")
        self.at(rules, "mast.at", LONG - 180, 190, 5, alliance="red")
        self.is_(rules.get("crate.at.x", alliance="red"), "length", (LONG - 131) * IN)
        self.is_(rules.get("crate@red.at.x"), "length", (LONG - 131) * IN)
        self.assertEqual(rules.get("crate@red.at.x").printed, "481.4 in")
        self.is_(rules.get("crate@blue.at.x", alliance="red"), "length", 131 * IN)

    def test_a_record_with_its_own_symmetry(self):
        """Catches a record that is mirrored on a field that is turned and comes out turned."""
        rules = self.rules()
        self.at(rules, "hooks.at", 20, 200, spot="left")
        self.at(rules, "hooks.at", LONG - 20, 200, spot="left", alliance="red")
        self.faces(rules, "hooks.faces", 45, spot="left")
        self.faces(rules, "hooks.faces", 135, spot="left", alliance="red")
        self.faces(rules, "hooks.faces", 225, spot="right", alliance="red")

    def test_a_field_that_is_mirrored(self):
        """Catches a field's own symmetry that is not used."""
        rules = self.rules(lambda d: d["field"].update(symmetry="mirror"))
        self.at(rules, "fold.at", LONG - 120, 260, alliance="red")
        self.faces(rules, "fold.faces", 150, alliance="red")
        self.faces(rules, "yard.faces", 180, alliance="red")

    def test_another_field(self):
        """Catches red's copy that is made with the first variant's field length."""
        self.at(self.rules(), "crate.at", 611.75 - 131, 150, 0, alliance="red", field="bolted")

    def test_what_neither_alliance_owns(self):
        """Catches a thing that stands once and that is moved for red, or a tag that is."""
        rules = self.rules()
        self.at(rules, "silo.at", LONG / 2, 150, 0, alliance="red")
        self.at(rules, "tags.t3.at", 150, 12, 40, alliance="red")
        self.faces(rules, "tags.t3.faces", 90, alliance="red")
        self.at(rules, "centre_bales.at", LONG / 2, 240, spot="f", alliance="red")
        self.wrong(lambda: rules.get("silo@red.at"), "silo", "@")

    def test_facing_left_out(self):
        """Catches a record with no facing that has none, where it is 0 deg."""
        rules = self.rules()
        self.faces(rules, "yard.faces", 0)
        self.faces(rules, "yard.faces", 180, alliance="red")
        self.faces(rules, "near_bales.faces", 0, spot="2")
        self.assertEqual((rules.get("yard.faces").printed, rules.get("yard.faces").src), ("0 deg", "manual 3.2"))
        none = self.rules(lambda d: d["field"]["zones"]["yard"].pop("src"))
        self.assertIsNone(none.get("yard.faces").src)

    def test_a_whole_turn(self):
        """Catches a direction that comes back as 360 deg, or as a hair less, where it is 0."""
        from frc_design_kernel.rules.alliances import direction
        self.assertEqual([direction(n) for n in (0, 360, -90, 725, 360 - 1e-12, -1e-12, 359.5)], [0, 0, 270, 5, 0, 0, 359.5])

    def test_only_positions_move(self):
        """Catches a size that is moved, or a shape."""
        rules = self.rules()
        for path in ["yard.deep", "gate_line.src", "patch.hole", "barn.opening.bottom", "crate.shape.box.x"]:
            self.assertEqual(rules.get(path, alliance="red"), rules.get(path), path)

    def test_lines(self):
        """Catches the end of a line that does not move."""
        rules = self.rules()
        self.at(rules, "gate_line.from", 54, 0)
        self.at(rules, "gate_line.from", LONG - 54, 300, alliance="red")
        self.at(rules, "gate_line.to", LONG - 54, 0, alliance="red")

    def test_a_formula_names_the_other_alliance(self):
        """Catches a formula that takes blue's number for red's, or that moves what it names twice."""
        at = lambda d: d["places"]["barn"].update(at=["= stall@red.near.at.x + barn.out", "= crate@red.at.x - crate.at.x"])
        rules = self.rules(at)
        self.at(rules, "barn.at", 20, LONG - 262)
        self.at(rules, "barn.at", LONG - 20, WIDE - (LONG - 262), alliance="red")

    def test_tolerance(self):
        """Catches the two ends of a tolerance that do not change places where the direction does."""
        rules = self.rules(lambda d: d["field"]["solids"]["crate"]["at"].__setitem__(0, "131 in +2 -1"))
        self.ends(rules.get("crate.at.x", alliance="red"), LONG - 133, LONG - 131, LONG - 130, unit=IN)

    def ends(self, value, *expected, unit=1):
        self.assertEqual([n if n is None else round(n / unit, 6) for n in (value.low, value.value, value.high)], list(expected))

    def test_tolerance_of_a_direction_and_of_a_spot(self):
        """Catches a tolerance that is turned round where the direction is not, or that is lost in a row or a height."""
        faces = lambda **more: self.rules(lambda d: d["field"]["zones"]["fold"].update(faces="30 deg +2 -1", **more))
        self.ends(faces().get("fold.faces"), 29, 30, 32)
        self.ends(faces().get("fold.faces", alliance="red"), 209, 210, 212)
        self.ends(faces(symmetry="mirror").get("fold.faces"), 29, 30, 32)
        self.ends(faces(symmetry="mirror").get("fold.faces", alliance="red"), 148, 150, 151)
        row = self.rules(lambda d: d["places"]["near_bales"]["spots"]["first"]["at"].__setitem__(1, "66 in +2 -1"))
        self.ends(row.get("near_bales.at.y", spot="3"), 161, 162, 164, unit=IN)
        self.ends(row.get("near_bales.at.y", spot="3", alliance="red"), 136, 138, 139, unit=IN)
        ring = self.rules(lambda d: d["field"]["hangs"]["rope"]["spots"]["first"]["at"].__setitem__(2, "28 in +2 -1"))
        self.ends(ring.get("rope.at.z", spot="left"), 27, 28, 30, unit=IN)
        self.ends(ring.get("rope.at.z", spot="left", alliance="red"), 27, 28, 30, unit=IN)
        around = self.rules(lambda d: d["field"]["hangs"]["rope"]["spots"]["first"]["at"].__setitem__(0, "196 in +2 -1"))
        self.ends(around.get("rope.at.x", spot="left"), None, 172, None, unit=IN)


class Spots(Moved):
    """Spots of a row, of a ring and of a group."""

    def test_a_row(self):
        """Catches a row that starts in the wrong place, or takes a step too many."""
        rules = self.rules()
        self.at(rules, "near_bales.at", 90, 66, spot="1")
        self.at(rules, "near_bales.at", 90, 162, spot="3")
        self.at(rules, "near_bales.at", LONG - 90, 138, spot="3", alliance="red")

    def test_names(self):
        """Catches the names of a pattern that stand in the wrong order."""
        rules = self.rules()
        for name, y in zip("abcdef", [60, 96, 132, 168, 204, 240]):
            self.at(rules, "centre_bales.at", LONG / 2, y, spot=name)

    def test_a_ring(self):
        """Catches a ring that goes clockwise, loses its height, or does not turn the way its spots look."""
        rules = self.rules()
        self.at(rules, "rope.at", 196, 110, 28, spot="front")
        self.at(rules, "rope.at", 172, 110 + 16 * HALF, 28, spot="left")
        self.at(rules, "rope.at", 172, 110 - 16 * HALF, 28, spot="right")
        self.faces(rules, "rope.faces", 120, spot="left")
        self.at(rules, "rope.at", LONG - 172, 190 - 16 * HALF, 28, spot="left", alliance="red")
        self.faces(rules, "rope.faces", 300, spot="left", alliance="red")

    def test_a_ring_of_pairs(self):
        """Catches the pegs of one side that are not on the side that is turned to."""
        rules = self.rules()
        out = 24 * HALF
        self.at(rules, "rack.at", 180 - out, 116, spot="1.a")
        self.at(rules, "rack.at", 180 - out, 104, spot="1.b")
        self.at(rules, "rack.at", 180 - out / 2 - 6 * HALF, 110 - out * HALF + 3, spot="2.a")
        self.faces(rules, "rack.faces", 240, spot="2.a")
        self.at(rules, "rack.at", 180 + out, 116, spot="4.b")
        self.faces(rules, "rack.faces", 0, spot="4.b")
        self.at(rules, "rack.at", LONG - 180 + out / 2 + 6 * HALF, 190 + out * HALF - 3, spot="2.a", alliance="red")
        self.faces(rules, "rack.faces", 60, spot="2.a", alliance="red")
        self.is_(rules.get("rack@red.2.a.at.y"), "length", (190 + out * HALF - 3) * IN)

    def test_named_spots(self):
        """Catches a spot that is taken for another, or that loses what it has of its own."""
        rules = self.rules()
        self.at(rules, "stall.at", LONG, 240, spot="far")
        self.faces(rules, "stall.faces", 180, spot="far")
        self.at(rules, "stall.at", 0, 60, spot="far", alliance="red")
        self.faces(rules, "stall.faces", 0, spot="far", alliance="red")
        self.is_(rules.get("stall.opening.bottom", spot="far"), "length", 37 * IN)

    def test_paths(self):
        """Catches a spot of a pattern that a path cannot name, after .spots or after the alliance."""
        rules = self.rules()
        self.is_(rules.get("near_bales.spots.3.at.y"), "length", 162 * IN)
        self.is_(rules.get("near_bales.spots.3.at.y", alliance="red"), "length", 138 * IN)
        self.is_(rules.get("near_bales@red.3.at.y"), "length", 138 * IN)
        self.is_(rules.get("rack.spots.2.a.faces"), "angle", 240)
        self.is_(rules.get("centre_bales.spots.f.at.y"), "length", 240 * IN)
        self.is_(rules.get("gateway.spots.far.at.y"), "length", 270 * IN)
        formula = self.rules(lambda d: d["places"]["vine"]["at"].__setitem__(1, "= near_bales.spots.3.at.y / 2"))
        self.is_(formula.get("vine.at.y"), "length", 81 * IN)

    def test_a_spot_that_is_not_there(self):
        """Catches a position asked of a record that stands in several, or a spot that it has not."""
        rules = self.rules()
        self.wrong(lambda: rules.get("rack.at"), "rack", "spot", "1.a")
        self.wrong(lambda: rules.get("rack.at", spot="7.a"), "7.a", "6.b")
        self.wrong(lambda: rules.get("crate.at", spot="near"), "crate", "near")
        self.wrong(lambda: rules.get("rack@red.7.a.at"), "rack")
        self.wrong(lambda: rules.get("near_bales.spots.5.at.y"), "5")
        self.is_(rules.get("rack.spots.first.a.at.y"), "length", 116 * IN)
        self.wrong(lambda: rules.get("rack.spots.first.a.at.y", alliance="red"), "rack", "spot")

    def test_what_a_position_has(self):
        """Catches a coordinate or an end that red's position has not and that comes back all the same."""
        rules = self.rules()
        for path in ["crate.at.w", "crate.at.x.y", "crate.faces.x", "crate.at.x.low", "fold.at.z", "fold.form"]:
            self.wrong(lambda: rules.get(path), path.partition(".")[0])
            self.wrong(lambda: rules.get(path, alliance="red"), path.partition(".")[0])
        wide = self.rules(lambda d: d["field"]["solids"]["crate"]["at"].__setitem__(0, "131 in +2 -1"))
        self.is_(wide.get("crate.at.x.low", alliance="red"), "length", (LONG - 133) * IN)


if __name__ == "__main__":
    unittest.main()
