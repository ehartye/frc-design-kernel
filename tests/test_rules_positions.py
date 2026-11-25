"""What is worked out from a position or a direction stands only in what moves for red: at, faces, from, to, spots and the points of an outline."""
import re
import unittest

from .test_rules_refusals import Refused

HIDDEN = "uses a position or a direction"


class Hidden(Refused):
    """A value of a record's own: crate and pen are of each alliance, pond of neither."""

    def own(self, text, **more):
        def change(d):
            d["field"]["solids"]["crate"]["own"] = text
            for other, value in more.items():
                d["field"]["zones" if other == "pond" else "solids"][other]["far"] = value
        return change

    def all_own(self, texts):
        return lambda d: d["field"]["solids"]["crate"].update({f"own{i}": f"= {text}" for i, text in enumerate(texts)})

    def test_refused(self):
        """Catches a position or a direction under a name of its own, which would stay blue's for red: of a record, a spot, a pattern, a line, an
        outline, a tag or red's; alone, as a distance, as a part or a sum, or inside a function. Each is told once, where it is written."""
        texts = ["barn.at.x", "barn.at.y", "pond.at.x", "rack.spots.1.a.at.y", "rack.spots.first.b.at.x", "near_bales.spots.3.at.x", "centre_bales.spots.b.at.y", "gateway.spots.far.at.y", "gate_line.from.x", "centre.to.y",
                 "rack.spots.around.x", "near_bales.spots.step.y", "lane.outline.y.x", "lane.outline.z.x", "tags.t1.at.y", "tags.t4.at.x.welded", "barn@red.at.x", "stall@red.near.at.x", "barn.faces", "tags.t3.faces", "rack.spots.1.a.faces",
                 "barn.at.x - mast.at.x", "abs(barn.at.x - mast.at.x)", "size.length / 2 - barn.at.x", "barn@red.at.x - barn.at.x", "(tags.t1.at.y + tags.t3.at.y) / 2", "2 * barn.at.x", "yard.deep * (barn.at.x / mast.at.x)", "barn.at.x * 0 + yard.deep",
                 "min(barn.at.x, yard.deep)", "pen.side * cos(barn.faces)", "pen.side * sin(barn.faces - fold.faces)", "atan2(barn.at.y - mast.at.y, yard.deep)", "barn.faces - fold.faces"]
        found = sorted(self.faults(self.all_own(texts)), key=lambda one: int(re.match(r"field.json crate.own([0-9]+):", one)[1]))
        self.assertEqual(len(found), len(texts), found)
        for text, one in zip(texts, found):
            self.assertTrue(f'"= {text}" {HIDDEN}' in one and "in at" in one and "faces" in one, one)

    def test_accepted(self):
        """Control: a height, the field's size, and the sizes and angles of things are no positions."""
        self.assertEqual(self.faults(self.all_own(["size.length / 2", "size.width - yard.deep", "bar.at.z * 2", "tags.t3.at.z", "yard.outline.rectangle.x", "crate.shape.box.x + pen.tall", "atan2(pen.half, pen.tall)", "barn.opening.slope", "tags.t3.tilt"])), [])

    def test_where_they_go(self):
        """Control: at, from, to, faces, spots, a pattern and the points of a zone's outline hold what is worked out from positions, as they move for red."""
        def all_of_them(d):
            solids, zones, places = d["field"]["solids"], d["field"]["zones"], d["places"]
            solids["crate"].update(at=["= 2 * barn.at.x - mast.at.x", "= barn.at.y + pen.side * sin(barn.faces)", "= barn.at.x"], faces="= barn.faces")
            d["field"]["lines"]["gate_line"]["from"][0] = "= barn.at.x"
            d["field"]["lines"]["gate_line"]["to"][0] = {"by": "field", "welded": "= barn.at.x", "bolted": "= mast.at.x"}
            places["stall"]["spots"]["near"].update(at=["= size.length", "= barn.at.y"], faces="= rack.spots.1.a.faces")
            places["near_bales"]["spots"].update(step=["0 in", "= (barn.at.y - fold.at.y) / 3"], first={"at": ["= barn.at.x", "66 in"], "faces": "= barn.faces"})
            places["rack"]["spots"]["step"] = "= 60 * (barn.faces - fold.faces) / 30"
            zones["lane"]["outline"][1][0] = "= barn.at.x + 5 * yard.deep"
            zones["fold"]["outline"] = {"is": [["= barn.at.x", "0 in"], ["60 in", "0 in"], ["60 in", "18 in"]], "src": "manual 3.2"}
        self.accepted(all_of_them)

    def test_where_they_do_not(self):
        """Catches a position in a size of an outline or a shape, in an opening, in a spot or in a list; each at its own place."""
        for change, where in [(lambda d: d["field"]["zones"]["yard"]["outline"].update(rectangle=["= barn.at.x", "21 in"]), "field.json yard.outline.rectangle.x"),
                              (lambda d: d["field"]["zones"]["paddock"]["outline"]["hexagon"].update(points="= barn.faces"), "field.json paddock.outline.hexagon.points"),
                              (lambda d: d["field"]["solids"]["ramp"]["shape"]["prism"]["outline"][1].__setitem__(0, "= barn.at.x"), "field.json ramp.shape.prism.outline[1].x"),
                              (lambda d: d["field"]["solids"]["trestle"]["shape"]["join"][1]["at"].__setitem__(0, "= barn.at.x"), "field.json trestle.shape.join[1].at.x"),
                              (lambda d: d["places"]["barn"]["opening"].update(bottom="= barn.at.x"), "places.json barn.opening.bottom"),
                              (lambda d: d["places"]["stall"]["spots"]["near"].update(far="= barn.at.x"), "places.json stall.spots.near.far"), (lambda d: d["field"]["solids"]["crate"].update(own=["1 in", {"is": "= barn.at.x", "of": "x"}]), "field.json crate.own.y.is")]:
            self.refused(change, f"{where}:", HIDDEN)

    def test_what_is_nobodys(self):
        """Control: what is not of each alliance does not move, so a position may be kept there; but not in the first spot of a pattern, as it would be every spot's."""
        def all_of_them(d):
            d["field"]["zones"]["pond"].update(own="= barn.at.x")
            d["field"]["tags"]["t1"].update(own="= barn.at.x")
            d["field"]["size"].update(own="= barn.at.x")
            d["field"]["guardrail"].update(own="= barn.faces")
            d["robot"]["limits"]["reach"].update(own="= barn.at.x")
            d["places"]["centre_bales"].update(own="= barn.at.x")
            d["places"]["vine"].update(spots={"first": {"at": ["9 in", "9 in"], "own": "= barn.at.x"}})
            d["places"]["vine"].pop("at")
        self.accepted(all_of_them)
        self.refused(lambda d: d["places"]["centre_bales"]["spots"]["first"].update(own="= barn.at.x"), "places.json centre_bales.spots.first.own:", HIDDEN)
        self.refused(lambda d: d["places"]["centre_bales"]["spots"].update(names=["1", "2", "3", "4", "5", "6"], first={"a": {"at": ["9 in", "9 in"]}, "b": {"at": ["19 in", "9 in"], "own": "= barn.faces"}}), "places.json centre_bales.spots.first.b.own:", HIDDEN)

    def test_words(self):
        """Catches words of a record that each alliance has, or of the first spot of a pattern, that print a position or a direction of blue's, or of one spot's."""
        named = {"crate": "faces", "manger": "at.x", "boulder": "at", "tyre": "crate.at.y", "culvert": "barn.at.x", "ramp": "barn@red.at.x", "barn_body": "tags.t1.faces", "trestle": "gate_line.from", "pen": "lane.outline.y.x",
                 "silo": "pond.far", "yard": "lane.outline.y", "paddock": "pond.far", "lane": "pond.says", "fold": "rack.spots.1.a.at.x", "arch": "near_bales.spots.step.y"}

        def change(d):
            d["field"]["zones"]["pond"].update(far="= barn.at.x - mast.at.x", says="At {far}.")
            for name, one in named.items():
                next(group for group in d["field"].values() if name in group)[name]["says"] = f"It is {{size.width}} off, {{{one}}}."
        found = {one.partition(":")[0].split(" ")[1]: one for one in self.faults(change)}
        named.pop("silo")       # neither alliance has it
        self.assertEqual(set(found), {f"{name}.says" for name in named})
        for name, one in named.items():
            for word in (f"names {{{one}}}", "a position or a direction", "another one for red"):
                self.assertIn(word, found[f"{name}.says"])
        says = lambda d, text: d["field"]["solids"]["crate"].update(says=text)
        for change, where in [(lambda d: d["places"]["barn"]["opening"].update(says="It looks along {faces}."), "places.json barn.opening.says:"), (lambda d: d["places"]["barn"]["opening"].update(says="It looks along {barn.faces}."), "places.json barn.opening.says:"),
                              (lambda d: d["places"]["stall"]["spots"]["near"].update(says="At {at.y}."), "places.json stall.spots.near.says:"), (lambda d: d["places"]["centre_bales"]["spots"]["first"].update(says="At {at.y}."), "places.json centre_bales.spots.first.says:"),
                              (lambda d: d["places"]["near_bales"]["spots"]["first"].update(says="At {near_bales.spots.first.at.x}."), "places.json near_bales.spots.first.says:")]:
            self.refused(change, where)
        self.accepted(lambda d: says(d, "{at.z} up, {shape.box.x} long, {yard.deep} from the {pen.bearing}, of {size.length}."))

        def nobodys(d):
            d["field"]["zones"]["pond"].update(says="At {at.x}, near {barn.at.x}, which looks along {barn.faces}.")
            d["robot"]["rules"]["R98"].update(says="No nearer than {barn.at.x}.")
            d["places"]["centre_bales"].update(says="From {spots.first.at.y}.")
            d["places"]["vine"].update(spots={"first": {"at": ["9 in", "9 in"], "says": "At {at.x}."}})
            d["places"]["vine"].pop("at")
        self.accepted(nobodys)

    def test_two_steps_away(self):
        """Catches a position that comes through another name, by a formula or a variant; and tells it only where it is first hidden."""
        for far in ["= barn.at.x", {"is": "= barn.at.x - mast.at.x", "of": "x"}, {"by": "field", "welded": "3 in", "bolted": "= barn.at.x"}]:
            self.refused(self.own("= pond.far", pond=far), "field.json crate.own:", HIDDEN)
        self.refused(self.own("= pen.far", pen="= barn.at.x"), "field.json pen.far:", HIDDEN)
        self.refused(self.own("= pen.far * 2", pen="= pond.far", pond="= barn.at.x"), "field.json pen.far:", HIDDEN)
        self.accepted(self.own("= pond.far", pond="= bar.at.z"))

    def test_the_size_of_the_field(self):
        """Catches the field's size that counts as a position because it is worked out from one."""
        self.accepted(lambda d: d["field"]["size"].update(width="= crate.at.y * 2") or d["field"]["solids"]["crate"].update(own="= size.width / 2"))

    def test_one_variant(self):
        """Catches a position that is hidden for one variant only, at that variant."""
        for hidden in ("welded", "bolted"):
            self.refused(self.own({"by": "field", "welded": "= pen.side", "bolted": "= pen.side", hidden: "= barn.at.x"}), f"field.json crate.own.{hidden}:", HIDDEN)

    def test_told_once(self):
        """Catches a hidden position that is told beside another fault of the same value, or in what a value was."""
        self.refused(self.own("= barn.at.x + 3"), "field.json crate.own:", "adds a count to a length")
        self.refused(self.own("= brn.at.x"), "field.json crate.own the path", "names the ID")
        self.refused(self.own("= barn.at.x * (1 / 0)"), "division by zero")
        self.refused(lambda d: d["field"]["zones"]["yard"].update(deep="= barn.faces"), "field.json yard.deep:", "an angle, not a length")
        self.accepted(self.own({"is": "3 in", "was": [{"until": "2031-02-04", "is": "= barn.at.x", "src": "update3 3.1"}], "differs": [{"is": "= barn.at.x", "src": "manual 3.1"}]}))


if __name__ == "__main__":
    unittest.main()
