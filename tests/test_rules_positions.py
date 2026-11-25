"""A position of a record that each alliance has stands in at, from or to, and a direction in faces: what moves for red is written nowhere else."""
import re
import unittest

from .rules_cases import Derived
from .test_rules_refusals import Refused

MEAN = "(tags.t1.at.y + tags.t3.at.y + tags.t4.at.y) / 3"


class Hidden(Refused):
    """A value of a record's own: crate and pen are of each alliance, pond of neither."""

    def own(self, text, name="crate", **more):
        def change(d):
            d["field"]["solids"][name]["own"] = text
            for other, value in more.items():
                d["field"]["zones" if other == "pond" else "solids"][other]["far"] = value
        return change

    def hidden(self, text, *says, **more):
        self.refused(self.own(text, **more), "field.json crate.own:", *says)

    def distance(self, text, **more):
        self.accepted(self.own(text, **more))

    def all_hidden(self, texts, *says):
        """Each of some formulas is refused, where it is written, and told once. All are in one folder, as none needs another."""
        found = sorted(self.faults(self.all_own(texts)), key=lambda one: int(re.match(r"field.json crate.own([0-9]+):", one)[1]))
        self.assertEqual(len(found), len(texts), found)
        for text, one in zip(texts, found):
            for word in (f'"= {text}"', *says):
                self.assertIn(word, one)

    def all_distances(self, texts):
        self.assertEqual(self.faults(self.all_own(texts)), [])

    def all_own(self, texts):
        return lambda d: d["field"]["solids"]["crate"].update({f"own{i}": f"= {text}" for i, text in enumerate(texts)})

    def test_a_position(self):
        """Catches a position under a name of its own, which would stay blue's for red: of a record, a spot, a pattern, a line, an outline, a tag, or red's."""
        self.all_hidden(["barn.at.x", "barn.at.y", "pond.at.x", "rack.spots.1.a.at.y", "rack.spots.first.b.at.x", "near_bales.spots.3.at.x", "centre_bales.spots.b.at.y", "gateway.spots.far.at.y", "gate_line.from.x", "centre.to.y", "rack.spots.around.x",
                     "lane.outline.y.x", "lane.outline.z.x", "tags.t1.at.y", "tags.t4.at.x.welded", "barn@red.at.x", "stall@red.near.at.x", "silo.at.y"], "a position", "at, from or to")

    def test_a_distance(self):
        """Control: the same values as a distance, the field's size, a height and a size of something are ordinary lengths."""
        self.all_distances([f"{path} - mast.at.{path[-1]}" for path in ["barn.at.x", "rack.spots.1.a.at.y", "near_bales.spots.3.at.x", "gate_line.from.x", "lane.outline.y.x", "tags.t1.at.y", "stall@red.near.at.x", "rack.spots.around.x"]])
        self.all_distances(["size.length / 2", "size.width - yard.deep", "bar.at.z * 2", "tags.t3.at.z", "yard.outline.rectangle.x", "near_bales.spots.step.y", "crate.shape.box.x + pen.tall"])

    def test_sums_and_parts(self):
        """Catches a sum or a part of positions that is taken for a distance, or a distance that is refused: a mean is one position, and a mean less one is a distance."""
        self.all_hidden(["size.length - barn.at.x", MEAN, f"{MEAN} + 3 * patch.hole", "2 * barn.at.x", "barn.at.x / 3", "barn.at.x + mast.at.x", "-barn.at.x", "2 * barn.at.x - mast.at.x / 2", "barn.at.x * (1 / 3 + 1 / 3)", "(barn.at.x - mast.at.x) - tags.t3.at.x"])
        self.all_distances([f"{MEAN} - mast.at.y", "3 * (barn.at.x - mast.at.x) / 2", "2 * barn.at.x - (mast.at.x + tags.t3.at.x)", "barn.at.x / 2 + mast.at.x / 2 - tags.t3.at.x", "(barn.at.x - mast.at.x) * G95.limit", "barn.at.x * 0 + yard.deep",
                     "barn.at.x * (2 - 1) - mast.at.x", "-barn.at.x + mast.at.x", "barn.at.x * 0.5 * 2 - mast.at.x", "barn.at.x / -1 + mast.at.x",
                            "barn.at.x * (1 / 4 + 3 / 4) - mast.at.x", "barn.at.x * (1 / 2) * 2 - mast.at.x", "barn.at.x * (2 / 1 - 1) - mast.at.x"])

    def test_x_and_y(self):
        """Catches an x less a y, which is no distance and is another number for red; each axis with its own is one."""
        self.all_hidden(["crate.at.x - crate.at.y", "barn.at.y - tags.t1.at.x", "(barn.at.x - barn.at.y) / 2", "rack.spots.1.a.at.x - near_bales.spots.3.at.y", "gate_line.from.x - centre.to.y", "lane.outline.y.x - lane.outline.y.y",
                         "barn@red.at.x - barn.at.y", "barn.at.x - mast.at.x + tags.t3.at.x - crate.at.y", "barn.at.x + mast.at.y", "2 * barn.at.x - barn.at.y"], "uses a position, and gives neither a position nor a distance")
        self.all_hidden(["min(barn.at.x, barn.at.y)", "max(barn.at.x, mast.at.y) - mast.at.x", "min(barn.at.x - mast.at.y, yard.deep)"], "neither a position nor a distance")
        self.hidden("= pond.far - crate.at.y", "neither a position nor a distance", pond="= barn.at.x")
        self.all_distances(["crate.at.x - barn.at.x + crate.at.y - barn.at.y", "max(crate.at.x - barn.at.x, crate.at.y - barn.at.y)", "pen.side * ((crate.at.x - barn.at.x) / (crate.at.y - fold.at.y))",
                            "crate.at.x - barn.at.y + barn.at.y - barn.at.x", "lane.outline.y.x - barn.at.x"])
        self.hidden("= atan2(crate.at.y - barn.at.y, crate.at.x - barn.at.x)", "gives a direction")

    def test_what_is_neither(self):
        """Catches a message that says that a distance would not move, or advice that does not work."""
        for text, uses, gives, fix in [("2 * barn.at.x", "a position", "neither a position nor a distance", "along the same axis"), ("2 * barn.faces", "a direction", "neither a direction nor an angle between two", "one direction less another"),
                                       ("pen.side * cos(barn.faces)", "a direction", "neither a position nor a distance", "one direction less another"),
                                       ("size.length - barn.at.x", "a position", "neither a position nor a distance", "ID@red.at.x - ID.at.x"),
                                       ("barn.at.x * cos(barn.faces)", "a position and a direction", "neither a position nor a distance", "one direction less another")]:
            self.hidden(f"= {text}", f"uses {uses}, and gives {gives}. Fix: ", fix)
            self.assertNotIn("would not move", self.faults(self.own(f"= {text}"))[0])
        self.all_distances(["barn@red.at.x - barn.at.x", "stall.spots.near.at.x - barn.at.x", "barn.faces - fold.faces", "pen.side * cos(barn.faces - fold.faces)"])
        self.hidden("= barn.at.x", "gives a position, which would not move for red here", "Write it in at, from or to")
        self.hidden("= barn.faces", "gives a direction, which would not move for red here", "Write it in faces")
        self.hidden("= 2 * atan2(barn.at.y - mast.at.y, barn.at.x - mast.at.x)", "uses a direction, and gives neither a direction nor an angle between two")

    def test_functions(self):
        """Catches a function that hides a position, or a position that another value multiplies."""
        self.all_hidden(["min(barn.at.x, mast.at.x)", "max(barn.at.x, yard.deep)", "abs(barn.at.x)", "barn.at.x * G95.limit", "abs(barn.at.x) - mast.at.x", "min(barn.at.x, yard.deep) - mast.at.x", "yard.deep * (barn.at.x / mast.at.x)",
                     "yard.deep * sqrt(barn.at.x / mast.at.x)", "(barn.at.x - mast.at.x) / (barn.at.x / yard.deep)", "barn.at.x * sqrt(4) - 2 * mast.at.x",
                         "abs(barn.at.x) + yard.deep", "barn.at.x * G95.limit + yard.deep"])
        self.hidden("= barn.at.x * G95.limit", "uses a position, and gives neither")
        self.all_distances(["min(barn.at.x, mast.at.x) - tags.t3.at.x", "max(barn.at.x - mast.at.x, yard.deep)", "abs(barn.at.x - mast.at.x)", "yard.deep * sqrt((mast.at.x - barn.at.x) / yard.deep)", "yard.deep * ((barn.at.x - mast.at.x) / pen.side)"])

    def test_a_direction(self):
        """Catches a direction under a name of its own, or one that a sine hides; an angle between two directions, or of a thing's own sizes, is an angle."""
        self.all_hidden(["barn.faces", "tags.t3.faces", "rack.spots.1.a.faces", "stall@red.near.faces", "barn.faces + pen.lean", "atan2(barn.at.y - mast.at.y, barn.at.x - mast.at.x)", "atan2(abs(barn.at.y - mast.at.y), yard.deep)",
                         "atan2(yard.deep + (barn.at.x - mast.at.x), pen.side)", "atan2(pen.side, (barn.at.x - mast.at.x) * 2 + yard.deep)"], "a direction", "faces")
        self.all_hidden(["pen.side * cos(barn.faces)", "pen.side * sin(fold.faces)", "pen.side * tan(barn.faces)", "pen.side * sin(atan2(barn.at.y - mast.at.y, barn.at.x - mast.at.x))", "2 * barn.faces"])
        self.all_distances(["barn.faces - fold.faces", "pen.side * cos(barn.faces - fold.faces)", "atan2(pen.half, pen.tall)", "barn.opening.slope", "tags.t3.tilt", "atan2(barn.at.y - mast.at.y, barn.at.x - mast.at.x) - barn.faces"])

    def test_where_they_go(self):
        """Control: at, from, to, faces, spots, a pattern and the points of a zone's outline hold positions and directions of any sort, as they move for red."""
        def all_of_them(d):
            solids, zones, places = d["field"]["solids"], d["field"]["zones"], d["places"]
            solids["crate"].update(at=["= 2 * barn.at.x", "= barn.at.y + pen.side * sin(barn.faces)", "= barn.at.x"], faces="= barn.faces")
            d["field"]["lines"]["gate_line"]["from"][0] = "= barn.at.x"
            d["field"]["lines"]["gate_line"]["to"][0] = {"by": "field", "welded": "= barn.at.x", "bolted": "= mast.at.x"}
            places["stall"]["spots"]["near"].update(at=["= size.length", "= barn.at.y"], faces="= rack.spots.1.a.faces")
            places["near_bales"]["spots"]["first"]["at"][0] = "= barn.at.x"
            zones["lane"]["outline"][1][0] = "= barn.at.x"
            zones["fold"]["outline"] = {"is": [["= barn.at.x", "0 in"], ["60 in", "0 in"], ["60 in", "18 in"]], "src": "manual 3.2"}
        self.accepted(all_of_them)

    def test_where_they_do_not(self):
        """Catches a position in a size of an outline or a shape, in a step, in a limit of a place or in a list; and a direction in a step or a slope."""
        for change, where in [(lambda d: d["field"]["zones"]["yard"]["outline"].update(rectangle=["= barn.at.x", "21 in"]), "field.json yard.outline.rectangle.x"),
                              (lambda d: d["field"]["zones"]["paddock"]["outline"]["hexagon"].update(points="= barn.faces"), "field.json paddock.outline.hexagon.points"),
                              (lambda d: d["field"]["solids"]["ramp"]["shape"]["prism"]["outline"][1].__setitem__(0, "= barn.at.x"), "field.json ramp.shape.prism.outline[1].x"),
                              (lambda d: d["field"]["solids"]["trestle"]["shape"]["join"][1]["at"].__setitem__(0, "= barn.at.x"), "field.json trestle.shape.join[1].at.x"),
                              (lambda d: d["places"]["near_bales"]["spots"]["step"].__setitem__(0, "= barn.at.x"), "places.json near_bales.spots.step.x"), (lambda d: d["places"]["rack"]["spots"].update(step="= barn.faces"), "places.json rack.spots.step"),
                              (lambda d: d["places"]["barn"]["opening"].update(bottom="= barn.at.x"), "places.json barn.opening.bottom"), (lambda d: d["places"]["barn"]["opening"].update(slope="= barn.faces"), "places.json barn.opening.slope"),
                              (lambda d: d["places"]["stall"]["spots"]["near"].update(far="= barn.at.x"), "places.json stall.spots.near.far"), (lambda d: d["field"]["solids"]["crate"].update(own=["1 in", {"is": "= barn.at.x", "of": "x"}]), "field.json crate.own.y.is")]:
            self.refused(change, f"{where}:")

    def test_what_is_nobodys(self):
        """Control: what is not of each alliance does not move, so a position may be kept there: a zone of nobody's, a tag, a limit."""
        for change in [lambda d: d["field"]["zones"]["pond"].update(own="= barn.at.x"), lambda d: d["field"]["tags"]["t1"].update(own="= barn.at.x"), lambda d: d["robot"]["limits"]["reach"].update(own="= barn.at.x"),
                       lambda d: d["field"]["size"].update(own="= barn.at.x"), lambda d: d["field"]["guardrail"].update(own="= barn.faces")]:
            self.accepted(change)

    def test_two_steps_away(self):
        """Catches a position that comes through another name, by a formula or a variant; and tells it only where it is first hidden."""
        self.hidden("= pond.far", "a position", pond="= barn.at.x")
        self.hidden("= pond.far + 2 * patch.hole", pond={"is": "= barn.at.x", "of": "x"})
        self.distance("= pond.far - mast.at.x", pond="= barn.at.x")
        self.distance("= pond.far", pond="= barn.at.x - mast.at.x")
        self.hidden("= atan2(pond.far, pen.side)", "a direction", pond="= barn.at.x - mast.at.x")
        self.hidden("= pond.far", pond={"by": "field", "welded": "3 in", "bolted": "= barn.at.x"})
        self.distance("= pond.far", pond={"by": "field", "welded": "3 in", "bolted": "= barn.at.x - mast.at.x"})
        for text in ["= pen.far", "= pen.far - mast.at.x", "= pen.far * 2"]:
            self.refused(self.own(text, pen="= barn.at.x"), "field.json pen.far:", "a position")
        self.refused(self.own("= pen.far", pen="= pond.far", pond="= barn.at.x"), "field.json pen.far:", "a position")

    def test_the_size_of_the_field(self):
        """Catches the field's size that counts as a position because it is worked out from one."""
        self.accepted(lambda d: d["field"]["size"].update(width="= crate.at.y * 2") or d["field"]["solids"]["crate"].update(own="= size.width / 2"))

    def test_one_variant(self):
        """Catches a position that is hidden for one variant only, at that variant."""
        for hidden in ("welded", "bolted"):
            self.refused(self.own({"by": "field", "welded": "= barn.at.x - mast.at.x", "bolted": "= barn.at.x - mast.at.x", hidden: "= barn.at.x"}), f"field.json crate.own.{hidden}:", "a position")

    def test_told_once(self):
        """Catches a hidden position that is told beside another fault of the same value, or in what a value was."""
        self.hidden("= barn.at.x + 3", "adds a count to a length")
        self.hidden("= barn.at.x * (1 / 0)", "division by zero")
        self.refused(self.own("= brn.at.x"), "field.json crate.own the path", "names the ID")
        self.refused(lambda d: d["field"]["zones"]["yard"].update(deep="= barn.faces"), "field.json yard.deep:", "an angle, not a length")
        self.accepted(self.own({"is": "3 in", "was": [{"until": "2031-02-04", "is": "= barn.at.x", "src": "update3 3.1"}], "differs": [{"is": "= barn.at.x", "src": "manual 3.1"}]}))


class Red(Derived):
    """What red is given."""

    def test_a_distance_is_the_same_for_both(self):
        """Catches a distance of a record that get refuses for red, or turns round."""
        rules = self.rules(lambda d: d["field"]["solids"]["crate"].update(own="= crate.at.x - barn.at.x"))
        for alliance in ("blue", "red"):
            self.is_(rules.get("crate.own", alliance=alliance), "length", 111 * 25.4)

    def test_a_value_shows_nothing_of_it(self):
        """Control: how a number goes with positions is no part of a value that is asked for: two equal values are equal."""
        rules = self.rules()
        self.assertEqual(rules.get("barn.at.x"), rules.get("barn.at")[0])
        self.assertNotIn("sort", repr(rules.get("barn.at.x")))


if __name__ == "__main__":
    unittest.main()
