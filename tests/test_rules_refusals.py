"""What cannot be worked out is refused, with its file, its record and its field. Every refusal has a change beside it that passes."""
import json
import unittest

from .rules_cases import Checked, example, small, written


class Refused(Checked):
    """Help: the faults of reading and those of working out, as rules.faults gives them, with no files written."""

    def faults(self, change=None):
        from frc_design_kernel.rules import derive, read, words
        data = example()
        if change:
            change(data)
        book, faults = read.gather("", data)
        faults += words.check(book)
        return [str(f) for f in faults + derive.faults(book, faults)]


class Formulas(Refused):
    """Formulas that give no number, or not the kind that is needed."""

    def test_the_example_has_no_faults(self):
        """Control for every refusal in this file: the example as it is passes."""
        self.assertEqual(self.faults(), [])

    def test_kinds(self):
        """Catches a bare number added, two kinds added, and a function with the wrong kind of number."""
        at = lambda d, text: d["places"]["barn"].update(at=[text, "0 in"])
        for text, says in [("= size.width + 3", "adds a count to a length"), ("= size.width + hoop.mass", "adds a mass to a length"), ("= size.width * sin(size.length)", "takes sin of a length"),
                           ("= size.width * size.width", "multiplies a length by a length"), ("= size.width * asin(pen.lean)", '"asin"'), ("= size.width +", "not valid arithmetic")]:
            self.refused(lambda d: at(d, text), "places.json barn.at.x", f'"{text}"', says)
        self.accepted(lambda d: at(d, "= size.width * sin(pen.lean) + 3 * crate.at.y / 4"))

    def test_a_weight_that_is_a_formula(self):
        """Catches a weight under a name of its own that is worked out, as one that is printed is caught."""
        weight = lambda d, **more: d["robot"]["limits"]["weight"].update(more)
        self.refused(lambda d: weight(d, total="= limits.weight.robot.max"), "robot.json limits.weight", '"total"', "with_bumpers")
        self.refused(lambda d: weight(d, total={"is": "= 2 * limits.weight.robot.max"}), "robot.json limits.weight", '"total"')
        self.accepted(lambda d: weight(d, cable="= limits.reach.far"))
        self.accepted(lambda d: weight(d, was=[{"until": "2031-02-04", "is": "= limits.weight.robot.max", "src": "update3 R92"}]))
        self.accepted(lambda d: d["robot"]["limits"]["weight"]["robot"].update(spare="= limits.weight.bumpers.max"))

    def test_the_kind_that_the_field_holds(self):
        """Catches a formula that gives a mass where a length is needed, a length where a count is, or a number for a flag."""
        self.refused(lambda d: d["field"]["zones"]["yard"].update(deep="= hoop.mass"), "field.json yard.deep", "a mass, not a length")
        self.refused(lambda d: d["robot"]["limits"]["reach"].update(sides="= yard.deep"), "robot.json limits.reach.sides", "a length, not a count")
        self.refused(lambda d: d["pieces"]["pumpkin"].update(stiff="= lit.bank"), "pieces.json pumpkin.stiff", "true or false")
        self.refused(lambda d: d["scoring"]["judged"]["late"].update(after_auto="= lit.bank"), "scoring.json judged.late.after_auto", "a count, not a time")
        self.accepted(lambda d: d["scoring"]["judged"]["late"].update(after_auto="= auto.lasts / lit.bank"))

    def test_loops(self):
        """Catches formulas that need each other, through is, a variant, a red copy or what is left over, and names each loop once."""
        size = lambda d, **sizes: d["field"]["size"].update(sizes)
        self.refused(lambda d: size(d, width="= size.width"), "field.json size.width", '"= size.width" needs "= size.width"')
        self.refused(lambda d: size(d, width="= yard.deep * 2") or d["field"]["zones"]["yard"].update(deep="= size.width / 2"), "field.json", "needs itself", '"= yard.deep * 2"', '"= size.width / 2"')
        self.refused(lambda d: size(d, width={"is": "= crate@red.at.y"}), "field.json size.width", "needs itself", '"= crate@red.at.y"')
        self.refused(lambda d: size(d, length={"by": "field", "welded": "612.40 in", "bolted": "= size.length.bolted"}), "field.json size.length.bolted", "needs itself")
        self.refused(lambda d: d["scoring"]["total"].update(bale="= stall.starts.bale * 2"), "scoring.json total.bale", "needs itself")
        self.refused(lambda d: size(d, length={"by": "field", "welded": "= size.length.bolted", "bolted": "= size.length.welded"}), "needs itself", '"= size.length.bolted"', '"= size.length.welded"')
        self.accepted(lambda d: size(d, length={"by": "field", "welded": "612.40 in", "bolted": "= size.length.welded"}))
        self.accepted(lambda d: d["field"]["solids"]["crate"].update(at=["= crate.at.y", "150 in", "0 in"]))

    def test_what_a_formula_may_name(self):
        """Catches a formula that names a range without its end, a list, words, a record, a shape, or the end of one number."""
        deep = lambda d, text: d["field"]["zones"]["fold"].update(deep=text)
        for text, says in [("= bale.shape", "bale.shape"), ("= crate", "not one value"), ("= crate.at", "a list"), ("= limits.bumpers.frame_gap", "a list"), ("= size.surface", "not a number"), ("= yard.height", "not a number"),
                           ("= limits.start.height.low", "low")]:
            self.refused(lambda d: deep(d, text), "field.json fold.deep", text, says)
        self.refused(lambda d: d["pieces"]["hoop"].update(mass="= bale.mass"), "pieces.json hoop.mass", "range", ".low")
        self.accepted(lambda d: d["pieces"]["hoop"].update(mass="= bale.mass.low"))
        self.accepted(lambda d: d["field"]["zones"]["pond"].update(own="= rack.spots.2.a.at.x - near_bales.spots.3.at.x"))

    def test_only_the_formula_that_is_wrong_is_told(self):
        """Catches one wrong formula that is told again for everything that uses it."""
        self.refused(lambda d: d["field"]["solids"]["crate"]["at"].__setitem__(0, "= size.width + 3"), "field.json crate.at.x")
        self.refused(lambda d: d["field"]["size"].update(width="= pen.side + 3"), "field.json size.width")

    def test_a_variant(self):
        """Catches a formula that is wrong only for a variant that nobody asked first."""
        by = lambda bolted: {"by": "field", "welded": "= pen.side", "bolted": bolted}
        self.refused(lambda d: d["field"]["zones"]["yard"].update(deep=by("= pen.side / (G95.limit - 1)")), "field.json yard.deep.bolted", "division by zero")
        self.refused(lambda d: d["field"]["zones"]["yard"].update(deep={"by": "field", "welded": "= swing.at.z", "bolted": "= swing.lift / (swing.many - 1)"}) or d["field"]["hangs"]["swing"].update(
            many={"by": "gate", "low_gate": 2, "high_gate": 1}), "field.json yard.deep.bolted", "division by zero")
        self.accepted(lambda d: d["field"]["zones"]["yard"].update(deep=by("= pen.side / 2")))


class Places(Refused):
    """Positions, outlines and shapes that cannot be drawn."""

    def test_a_position_that_is_a_range(self):
        """Catches a range where one number is needed, in a position, a pattern, an outline or a shape."""
        for change, where in [(lambda d: d["field"]["solids"]["crate"]["at"].__setitem__(0, "130 to 132 in"), "field.json crate"),
                              (lambda d: d["places"]["near_bales"].update(apart="47 to 49 in"), "places.json near_bales.spots.step.y"),
                              (lambda d: d["places"]["near_bales"]["spots"]["step"].__setitem__(1, "47 to 49 in"), "places.json near_bales"),
                              (lambda d: d["field"]["zones"]["pond"]["outline"].update(circle="45 to 47 in"), "field.json pond"),
                              (lambda d: d["pieces"]["pumpkin"]["shape"]["ball"].update(diameter="8 to 9 in") or d["field"]["solids"]["pen"]["shape"]["prism"].update(tall="5 in"), "pieces.json pumpkin.shape"),
                              (lambda d: d["field"]["tags"]["t1"]["at"].__setitem__(2, "49 to 51 in"), "field.json tags.t1"),
                              (lambda d: d["field"]["tags"]["t1"].update(faces="0 to 5 deg"), "field.json tags.t1.faces")]:
            self.refused(change, where, "range")
        self.accepted(lambda d: d["field"]["solids"]["crate"]["at"].__setitem__(0, "131 in +/- 1"))
        self.accepted(lambda d: d["field"]["tags"]["t1"].update(faces="0 deg +/- 5"))

    ONE = {      # where one number is needed: how to put a range there, and where it is told
        "placed.at": (lambda d, v: d["field"]["solids"]["crate"]["at"].__setitem__(2, v("in")), "field.json crate.at.z"),
        "placed.faces": (lambda d, v: d["field"]["solids"]["crate"].update(faces=v("deg")), "field.json crate.faces"),
        "spot.at": (lambda d, v: d["places"]["hooks"]["spots"]["left"]["at"].__setitem__(0, v("in")), "places.json hooks.spots.left.at.x"),
        "spot.faces": (lambda d, v: d["places"]["hooks"]["spots"]["left"].update(faces=v("deg")), "places.json hooks.spots.left.faces"),
        "row.step": (lambda d, v: d["places"]["centre_bales"]["spots"]["step"].__setitem__(0, v("in")), "places.json centre_bales.spots.step.x"),
        "ring.around": (lambda d, v: d["field"]["hangs"]["rope"]["spots"]["around"].__setitem__(0, v("in")), "field.json rope.spots.around.x"),
        "ring.step": (lambda d, v: d["field"]["hangs"]["rope"]["spots"].update(step=v("deg")), "field.json rope.spots.step"),
        "tag.at": (lambda d, v: d["field"]["tags"]["t1"]["at"].__setitem__(2, v("in")), "field.json tags.t1.at.z"),
        "tag.faces": (lambda d, v: d["field"]["tags"]["t1"].update(faces=v("deg")), "field.json tags.t1.faces"),
        "size.length": (lambda d, v: d["field"]["size"].update(length=v("in")), "field.json size.length"),
        "size.width": (lambda d, v: d["field"]["size"].update(width=v("in")), "field.json size.width"),
        "zone.outline": (lambda d, v: d["field"]["zones"]["pond"]["outline"].update(circle=v("in")), "field.json pond.outline.circle"),
        "line.from": (lambda d, v: d["field"]["lines"]["centre"]["from"].__setitem__(1, v("in")), "field.json centre.from.y"),
        "line.to": (lambda d, v: d["field"]["lines"]["centre"]["to"].__setitem__(1, v("in")), "field.json centre.to.y"),
        "solid.shape": (lambda d, v: d["field"]["solids"]["boulder"]["shape"]["ball"].update(diameter=v("in")), "field.json boulder.shape.ball.diameter"),
        "piece.shape": (lambda d, v: d["pieces"]["hoop"]["shape"]["ring"].update(thick=v("in")), "pieces.json hoop.shape.ring.thick"),
        "opening.outline": (lambda d, v: d["places"]["loft"]["opening"]["outline"].update(circle=v("in")), "places.json loft.opening.outline.circle"),
        "period.lasts": (lambda d, v: d["clock"]["periods"]["auto"].update(lasts=v("s")), "clock.json auto.lasts"),
        "window.first": (lambda d, v: d["clock"]["windows"]["early"].update(first=v("s")), "clock.json early.first"),
        "window.last": (lambda d, v: d["clock"]["windows"]["endgame"].update(last=v("s")), "clock.json endgame.last"),
        "state.lasts": (lambda d, v: d["clock"]["states"]["lit"].update(lasts=v("s")), "clock.json lit.lasts"),
        "tag.tilt": (lambda d, v: d["field"]["tags"]["t3"].update(tilt=v("deg")), "field.json tags.t3.tilt"),
        "judged.after_": (lambda d, v: d["scoring"]["judged"]["late"].update(after_auto=v("s")), "scoring.json judged.late.after_auto"),
        "points.points": (lambda d, v: d["scoring"]["awards"]["hang"]["points"][0].update(points=v("")), "scoring.json hang.points[0].points"),
        "foul.points_to_them": (lambda d, v: d["scoring"]["fouls"]["minor"].update(points_to_them=v("")), "scoring.json minor.points_to_them"),
        "award.rp": (lambda d, v: d["scoring"]["awards"]["all_moved"].update(rp=v("")), "scoring.json all_moved.rp"),
    }

    def test_each_place_for_one_number(self):
        """Catches a range, or limits of which one is enough, wherever fields.json says that one number is needed, each told once. All are
        in one folder, so that what uses several of them must not tell any again."""
        def put(d, value):
            for change, _ in self.ONE.values():
                change(d, value)
        for value, says in [(lambda unit: f"1 to 2 {unit}".strip(), "is a range"), (lambda unit: {"any": [{"low": f"1 {unit}" if unit else 1}, {"high": f"2 {unit}" if unit else 2}]}, "one is enough")]:
            found = self.faults(lambda d: put(d, value))
            self.assertEqual(sorted(one.partition(":")[0] for one in found), sorted(where for _, where in self.ONE.values()))
            self.assertTrue(all(says in one for one in found), found)

    def test_which_places_need_one_number(self):
        """Catches a property that no longer needs one number, or one that is new and has no case above."""
        from frc_design_kernel.rules import read
        flagged = [f"{kind}.{name}" for kind, about in read.names()["kinds"].items() for name, one in about["fields"].items() if one.get("one")]
        self.assertEqual(sorted(flagged), sorted(self.ONE))
        drawn = [f"{kind}.{name}" for kind, about in read.names()["kinds"].items() for name, one in about["fields"].items() if one["holds"] in ("point", "outline", "opening outline", "shape")]
        self.assertEqual(set(drawn) - set(flagged), set())

    def test_the_number_of_a_compare(self):
        """Catches a count that is compared with a range, which nobody can tell apart from one number; a limit of it is a thing of its own."""
        needs = lambda d, what: d["scoring"]["awards"]["loft_rp"]["needs"][1].__setitem__(2, what)
        self.refused(lambda d: needs(d, "1 to 2"), "scoring.json loft_rp.needs[1]:", "is a range")
        self.refused(lambda d: needs(d, {"by": "event", "regional": 2, "championship": "2 to 3"}), "scoring.json loft_rp.needs[1].championship:", "is a range")
        self.refused(lambda d: needs(d, {"any": [{"few": 1}, {"many": 2}]}), "scoring.json loft_rp.needs[1]:", "one is enough")
        self.refused(lambda d: d["conduct"]["G95"].update(must_not=[{"any": [{"all": [["my hanging_robots", "at least", "1 to 2"]]}]}]), "conduct.json G95.must_not[0].any[0].all[0]:", "is a range")
        self.refused(lambda d: d["scoring"]["awards"]["loft_rp"]["easier"]["needs"][0].__setitem__(2, "1 to 2"), "scoring.json loft_rp.easier.needs[0]:", "is a range")
        self.accepted(lambda d: needs(d, {"by": "event", "regional": 2, "championship": 3}))
        self.accepted(lambda d: needs(d, "= G95.limit * 2"))
        self.accepted(lambda d: d["conduct"]["G95"].update(must_not=[{"any": [{"all": [["my hanging_robots", "at least", 2]]}, ["my hanging_robots", "at most", "= G95.limit"]]}]))

    def test_a_position_of_which_one_is_enough(self):
        """Catches limits of which one is enough, in a place that needs one number."""
        self.refused(lambda d: d["field"]["tags"]["t3"]["at"].__setitem__(2, {"any": [{"deep": "3 in"}, {"wide": "4 in"}]}), "field.json tags.t3.at.z", "one is enough")
        self.refused(lambda d: d["field"]["zones"]["pond"]["outline"].update(circle={"any": [{"deep": "3 in"}]}), "field.json pond.outline.circle", "one is enough")

    def test_the_size_of_the_field(self):
        """Catches a field's length that is a range, once and not for every red copy."""
        self.refused(lambda d: d["field"]["size"].update(width="299 to 301 in") or d["places"]["stall"]["spots"]["far"]["at"].__setitem__(1, "240 in"), "size.width", "range")

    def test_outlines(self):
        """Catches an outline with no middle, no area, or sides that cross."""
        zone = lambda d, name="fold": d["field"]["zones"][name]
        self.refused(lambda d: zone(d).pop("at"), "field.json fold", '"at"')
        self.refused(lambda d: zone(d).update(outline={"rectangle": ["0 in", "24 in"]}), "field.json fold.outline", "no area")
        self.refused(lambda d: zone(d).update(outline=[["0 in", "0 in"], ["9 in", "0 in"], ["18 in", "0 in"]]), "field.json fold.outline", "no area")
        points = lambda *pairs: [[f"{x} in", f"{y} in"] for x, y in pairs]
        for line in [((1, 1), (2, 2), (4, 4)), ((5, 7), (6, 9), (8, 13)), ((3, 9), (3, 2), (3, 5)), ((1, 2), (4, 8), (3, 6), (2, 4))]:
            self.refused(lambda d: zone(d).update(outline=points(*line)), "field.json fold.outline", "no area")
        for knot in [((0, 0), (9, 9), (9, 0), (0, 8)), ((0, 0), (0, 8), (9, 0), (9, 9)), ((0, 0), (9, 0), (9, 9), (4, 9), (4, -2)), ((4, 9), (4, -2), (0, 0), (9, 0), (9, 9)), ((9, 9), (4, 9), (4, -2), (0, 0), (9, 0)),
                     ((0, 0), (10, 0), (10, 10), (5, 0), (5, -10), (0, 10))]:
            self.refused(lambda d: zone(d).update(outline=points(*knot)), "field.json fold.outline", "crosses itself")
        for whole in [((0, 0), (9, 0), (9, 9), (4, 1), (4, 9)), ((0, 0), (4, 0), (9, 0), (9, 9), (4, 1)), ((7, 3), (9, 4), (2, 9)), ((0, 0), (10, 0), (10, 10), (5, 0.01), (0, 10)), ((0, 0), (4, 0), (6, 0), (9, 0), (9, 9)),
                      ((7, -3), (37, 7), (37, 27), (22, 2.01), (7, 17)), ((5, 20), (35, 5), (35, 30), (15, 15.01), (5, 30)), ((3, 1), (21, 7), (40, 2), (33, 29), (18, 12), (2, 25))]:
            self.accepted(lambda d: zone(d).update(outline=points(*whole)))
        for touches in [((0, 0), (10, 0), (10, 10), (5, 0), (0, 10)), ((0, 0), (10, 0), (5, 5), (10, 10), (0, 10), (5, 5)), ((0, 0), (10, 0), (10, 0), (10, 10)),
                        ((0, 0), (20, 0), (10, 0), (10, 10)), ((0, 0), (4, 0), (9, 0), (9, 9), (4, 0)), ((0, 0), (5, 5), (20, 20), (20, -10), (5, 5), (0, 10)), ((10, 0), (10, 10), (0, 0), (10, 0)), ((5, 5), (0, 10), (0, 0), (5, 5), (20, 20), (20, -10)),
                        ((0, 0), (4, 0), (-3, 0), (-3, 9)), ((0, 0), (0, 9), (9, 9), (9, 4.0000001), (0, 4), (9, 4), (9, 0)),
                        ((7, -3), (37, 7), (37, 27), (22, 2), (7, 17)), ((5, 20), (35, 5), (35, 30), (15, 15), (5, 30))]:
            self.refused(lambda d: zone(d).update(outline=points(*touches)), "field.json fold.outline", "touches itself")
        self.refused(lambda d: d["field"]["solids"]["ramp"]["shape"]["prism"].update(outline=points((0, 0), (10, 0), (10, 10), (5, 0), (0, 10))), "field.json ramp.shape", "touches itself")
        self.refused(lambda d: d["places"]["barn"]["opening"]["outline"]["rectangle"].__setitem__(0, "0 in") or d["field"]["solids"]["barn_body"].update(shape={"box": ["1 in", "1 in", "1 in"]}), "places.json barn.opening.outline", "no area")
        self.accepted(lambda d: zone(d).update(at=["1 in", "1 in"]))
        self.accepted(lambda d: zone(d).pop("at") and zone(d).update(no_geometry="No drawing gives it."))
        self.accepted(lambda d: zone(d).update(outline=[["0 in", "0 in"], ["9 in", "0 in"], ["9 in", "9 in"], ["0 in", "8 in"]]))

    def test_shapes(self):
        """Catches a size that is nothing, a ring that is not round in section, a pipe with no wall, and a taper in a join."""
        shape = lambda d, name, **new: d["field"]["solids"][name].update(shape=new)
        self.refused(lambda d: shape(d, "crate", box=["22 in", "0 in", "15 in"]) or d["places"]["bench"]["surface"].update(size=["1 in", "1 in"]), "field.json crate.shape", "size of 0")
        self.refused(lambda d: shape(d, "boulder", ball={"diameter": "-1 in"}), "field.json boulder.shape", "size of")
        self.refused(lambda d: shape(d, "tyre", ring={"inside": "12 in", "outside": "22 in", "thick": "4 in"}), "field.json tyre.shape", "thick")
        self.refused(lambda d: shape(d, "culvert", tube={"inside": "18 in", "outside": "18 in", "length": "48 in"}), "field.json culvert.shape", "inside")
        self.refused(lambda d: shape(d, "trestle", join=[{"at": ["0 in", "0 in"], "box": ["4 in", "40 in", "6 in"]}]), "field.json trestle.shape")
        self.refused(lambda d: shape(d, "trestle", join=[{"at": ["0 in", "0 in"], "box": ["4 in", "40 in", "6 in"]}, {"at": ["0 in", "0 in"], "taper": {"bottom": {"circle": "4 in"}, "top": {"circle": "2 in"}, "tall": "1 in"}}]),
                     "field.json trestle.shape", "taper")
        self.refused(lambda d: shape(d, "ramp", prism={"outline": [["0 in", "0 in"], ["9 in", "9 in"], ["9 in", "0 in"], ["0 in", "8 in"]], "tall": "3 in"}), "field.json ramp.shape", "crosses itself")
        self.refused(lambda d: d["pieces"]["hoop"]["shape"]["ring"].update(thick="2 in"), "pieces.json hoop.shape", "thick")
        self.refused(lambda d: shape(d, "manger", taper={"bottom": {"circle": "0 in"}, "top": {"circle": "2 in"}, "tall": "1 in"}) or d["field"]["solids"]["manger"].update(says="x"), "field.json manger.shape", "no area")
        self.accepted(lambda d: shape(d, "tyre", ring={"inside": "12 in", "outside": "22 in", "thick": "= (tyre.shape.ring.outside - tyre.shape.ring.inside) / 2"}))
        self.accepted(lambda d: shape(d, "boulder", ball={"diameter": "0.5 mm"}))
        self.accepted(lambda d: shape(d, "boulder", taper={"bottom": {"circle": "4 in"}, "top": {"circle": "2 in"}, "tall": "1 in"}))


class Scores(Refused):
    """Times, points and pieces that do not add up."""

    def test_windows(self):
        """Catches a window that does not fit in its period, or that is counted from an end that nobody gave."""
        windows = lambda d: d["clock"]["windows"]
        self.refused(lambda d: windows(d)["endgame"].update(last="1 min 51 s"), "clock.json endgame", "does not fit")
        self.refused(lambda d: windows(d)["market"].update(timer=["1:55", "0:50"]), "clock.json market", "does not fit")
        self.refused(lambda d: windows(d)["early"].update(first="3 min"), "clock.json early", "does not fit")
        self.refused(lambda d: windows(d).update(later={"in": "gap", "last": "1 s"}) or d["clock"]["periods"]["gap"].pop("lasts"), "clock.json later", "gap", "lasts")
        self.refused(lambda d: windows(d)["early"].update(first="30 to 35 s") or d["conduct"]["G95"].update(says="x"), "clock.json early", "range")
        self.accepted(lambda d: windows(d)["market"].update(timer=["1:50", "0:00"]))
        self.accepted(lambda d: windows(d).update(sooner={"in": "gap", "first": "1 s"}) or d["clock"]["periods"]["gap"].pop("lasts"))

    def test_late_scores(self):
        """Catches an award that two records look at for different times after the same period."""
        judged = lambda d: d["scoring"]["judged"]
        self.refused(lambda d: judged(d)["late"]["awards"].append("park"), "scoring.json judged.", "park", "teleop")
        self.accepted(lambda d: judged(d)["late"]["awards"].append("out_early"))

    def test_rows_that_tie(self):
        """Catches two rows of points that may both be true with as many names, and lets those through that cannot."""
        def rows(*whens):
            return lambda d: d["scoring"]["awards"]["bale_in_barn"].update(points=[{"when": when, "points": i} for i, when in enumerate(whens)])
        for whens in [(["teleop"], ["teleop"]), ([], []), (["teleop", "lit"], ["teleop", "high_gate"]), (["teleop"], ["lit"]), (["teleop"], ["endgame"]), (["market"], ["not endgame"]), (["their lit"], ["lit"]),
                      (["quiet"], ["barn_open"]), (["teleop", "regional"], ["teleop", "playoff"]), (["shared", "lit"], ["shared", "not stuck"]), (["their quiet"], ["their lit"])]:
            self.refused(rows(*whens), "scoring.json bale_in_barn.points", "both be true")
        for whens in [(["auto"], ["teleop"]), (["teleop", "lit"], ["teleop", "not lit"]), (["teleop", "low_gate"], ["teleop", "high_gate"]), (["auto"], ["endgame"]), (["early"], ["endgame"]), (["market"], ["endgame"]),
                      (["early"], ["market"]), (["early"], ["not teleop"]), (["teleop"], ["teleop", "lit"]), (["auto", "lit"], ["auto", "not barn_open"]), (["not barn_open"], ["endgame"]),
                      (["their barn_open", "lit"], ["their barn_open", "not lit"]), (["shared"], ["not shared"])]:
            self.accepted(rows(*whens))

    def rows(self, *whens, also=None):
        def change(d):
            d["scoring"]["awards"]["bale_in_barn"].update(points=[{"when": when, "points": i} for i, when in enumerate(whens)])
            if also:
                also(d)
        return change

    def test_rows_of_states_made_of_states(self):
        """Catches a state of the other alliance that is worked out from mine, or one of which only a part needs to be true."""
        for one, other in [("their barn_open", "their lit"), ("barn_open", "lit"), ("my barn_open", "my lit")]:
            self.accepted(self.rows([one, "market"], [other, "market"]))
        for one, other in [("their barn_open", "lit"), ("barn_open", "their lit")]:
            self.refused(self.rows([one, "market"], [other, "market"]), "both be true")
        self.accepted(self.rows(["barn_open"], ["early"]))
        self.accepted(self.rows(["quiet", "auto"], ["not their lit", "auto"]))
        self.accepted(self.rows(["their quiet", "auto"], ["not lit", "auto"]))
        self.refused(self.rows(["their quiet", "auto"], ["not their lit", "auto"]), "both be true")
        self.refused(self.rows(["quiet", "auto"], ["not lit", "auto"]), "both be true")

    def test_rows_of_a_state_of_the_match(self):
        """Catches a state of the match that is not the same for both."""
        self.accepted(self.rows(["shared"], ["not shared"]))
        self.accepted(self.rows(["their both"], ["not shared"], also=lambda d: d["clock"]["states"].update(both={"of": "alliance", "true": [["shared"]]})))
        self.refused(self.rows(["my lit"], ["not their lit"]), "both be true")

    def test_rows_of_three_variants_and_of_a_period_with_no_end(self):
        """Catches two variants of three that are taken to be true at once, and a period with no printed time in which nothing happens."""
        days = lambda d: d["game"]["variants"].update(day=["mon", "tue", "wed"])
        self.accepted(self.rows(["mon"], ["tue"], ["wed"], also=days))
        self.refused(self.rows(["mon"], ["not tue"], also=days), "both be true")
        self.refused(self.rows(["gap"], ["not teleop"], also=lambda d: d["clock"]["periods"]["gap"].pop("lasts")), "both be true")

    def test_when_an_award_is_earned(self):
        """Catches rows that cannot tie, because the award is not earned then, and are refused."""
        self.refused(lambda d: d["scoring"]["awards"]["bale_in_barn"].update(points=[{"when": ["auto"], "points": 1}, {"when": ["lit"], "points": 2}, {"when": ["market"], "points": 2}]), "rows 1 and 2 may both be true")
        self.accepted(lambda d: d["scoring"]["awards"]["bale_in_barn"].update(when=["auto"], points=[{"when": ["endgame"], "points": 1}, {"when": ["market"], "points": 2}, {"when": ["lit"], "points": 2}]))
        self.refused(lambda d: d["scoring"]["awards"]["bale_in_barn"].update(when=["teleop"], points=[{"when": ["endgame"], "points": 1}, {"when": ["lit"], "points": 2}]), "both be true")

    def test_windows_that_fill_a_period(self):
        """Catches a moment after a period's end, or between two windows that meet, at which neither is open."""
        def rows(d, timer):
            d["clock"]["windows"]["later"] = {"in": "teleop", "timer": timer}
            d["scoring"]["awards"]["bale_in_barn"].update(when=["teleop"], points=[{"when": ["not early"], "points": 1}, {"when": ["not later"], "points": 2}])
        self.accepted(lambda d: rows(d, ["1:15", "0:00"]))
        self.refused(lambda d: rows(d, ["1:15", "0:01"]), "both be true")
        self.refused(lambda d: rows(d, ["1:14", "0:00"]), "both be true")
        self.refused(lambda d: rows(d, ["1:15", "0:00"]) or d["scoring"]["awards"]["bale_in_barn"].pop("when"), "both be true")

    def test_a_variant_of_the_clock(self):
        """Catches windows that overlap only for a variant."""
        rows = [{"when": ["early"], "points": 1}, {"when": ["endgame"], "points": 2}]
        short = {"by": "event", "regional": "1 min 50 s", "championship": "40 s"}
        windows = lambda d: d["clock"]["windows"].pop("market") and d["clock"]["states"]["barn_open"].update(true=[["auto"], ["endgame"]])
        self.refused(lambda d: windows(d) or d["clock"]["periods"]["teleop"].update(lasts=short) or d["scoring"]["awards"]["bale_in_barn"].update(points=rows), "bale_in_barn.points", "both be true")
        self.accepted(lambda d: windows(d) or d["clock"]["periods"]["teleop"].update(lasts={**short, "championship": "60 s"}) or d["scoring"]["awards"]["bale_in_barn"].update(points=rows))

    def test_states_in_a_loop(self):
        """Catches states that need each other, so that nobody can say when one is true."""
        self.refused(lambda d: d["clock"]["states"]["barn_open"].update(true=[["not quiet"]]), "clock.json", "barn_open", "quiet", "itself")
        self.refused(lambda d: d["clock"]["states"]["quiet"].update(true=[["their quiet"]]), "clock.json quiet.true", "itself")
        rows = [{"when": ["quiet"], "points": 1}, {"when": ["endgame"], "points": 2}]
        self.refused(lambda d: d["clock"]["states"]["quiet"].update(true=[["their quiet"]]) or d["scoring"]["awards"]["bale_in_barn"].update(points=rows), "clock.json quiet.true", "itself")

    def test_pieces(self):
        """Catches more pieces than there are, or a part of one that is left over."""
        starts = lambda d, place: d["places"][place]["starts"]
        self.refused(lambda d: starts(d, "vine").update(pumpkin=13), "places.json patch.starts.pumpkin", "12", "13", "-0.5")
        self.refused(lambda d: starts(d, "vine").update(pumpkin=14), "places.json patch.starts.pumpkin", "12", "14", "leaves -1 for each alliance")
        self.refused(lambda d: starts(d, "vine").update(pumpkin=3), "places.json patch.starts.pumpkin", "4.5 for each alliance")
        self.refused(lambda d: starts(d, "spare_hoops").update(hoop=5), "scoring.json total.hoop", "8", "9")
        self.refused(lambda d: d["scoring"]["total"].pop("pumpkin"), "places.json patch.starts.pumpkin", "no total")
        self.refused(lambda d: d["scoring"]["total"].update(bale={"by": "event", "regional": 60, "championship": 61}), "places.json stall.starts.bale", "61")
        self.refused(lambda d: starts(d, "vine").update(pumpkin={"each": "spot", "is": 2}), "places.json vine.starts.pumpkin", "each spot")
        self.refused(lambda d: starts(d, "vine").update(pumpkin={"each": "barn", "is": 2}), "places.json vine.starts.pumpkin", '"barn"', "spot", "alliance")
        self.refused(lambda d: starts(d, "vine").update(pumpkin={"is": "left over"}), "places.json vine.starts.pumpkin", "left over", "patch")
        self.refused(lambda d: starts(d, "stall").update(bale={"each": "spot", "is": "left over"}) or d["places"]["stall"]["holds"].update(bale="= stall.starts.bale * 2"), "places.json stall.starts.bale:", "each")
        self.refused(lambda d: starts(d, "stall").update(bale={"each": "zebra", "is": "left over"}), "places.json stall.starts.bale.each", '"zebra"')
        total = lambda d, many: d["scoring"]["total"].update(bale=many)
        for many, at in [({"each": "alliance", "is": 60}, ""), ({"each": "spot", "is": {"by": "event", "regional": 60, "championship": 80}}, ""), ({"by": "event", "regional": 60, "championship": {"each": "alliance", "is": 60}}, ".championship"),
                         ({"is": {"is": 60, "each": "barn"}}, ".is")]:
            self.refused(lambda d: total(d, many), f"scoring.json total.bale{at}:", "each", "in all")
        self.refused(lambda d: total(d, {"each": "zebra", "is": 60}), "scoring.json total.bale.each", '"zebra"')
        self.accepted(lambda d: total(d, {"is": 60, "src": "manual 5.6"}))
        self.accepted(lambda d: d["robot"]["limits"]["hold"].update(bale={"each": "alliance", "is": 1}) or d["conduct"]["G94"].update(limit={"pumpkin": 2}, says="x"))
        self.accepted(lambda d: starts(d, "vine").update(pumpkin=12))
        self.accepted(lambda d: starts(d, "patch").update(pumpkin={"is": "left over"}))
        self.accepted(lambda d: starts(d, "spare_hoops").update(hoop=3))

    def test_a_device_for_a_load_that_says_nothing_of_it(self):
        """Catches a device that is only for a load, when nobody says how many of it one such device may run."""
        self.refused(lambda d: d["robot"]["parts"]["relays"]["switch"].update(only_for=["pony"]), "robot.json parts.relays.switch", "pony", "relay")
        self.accepted(lambda d: d["robot"]["parts"]["relays"]["switch"].update(only_for=["mule"]))


class MoreThanNothing(Refused):
    """Sizes and times that are not more than 0, and counts below 0."""

    PUT = {     # what must be more than 0: how to put a value there, its unit, and where it is told
        "size.length": (lambda d, v: d["field"]["size"].update(length=v), "in", "field.json size.length"),
        "size.width": (lambda d, v: d["field"]["size"].update(width=v), "in", "field.json size.width"),
        "period.lasts": (lambda d, v: d["clock"]["periods"]["teleop"].update(lasts=v), "s", "clock.json teleop.lasts"),
        "window.first": (lambda d, v: d["clock"]["windows"]["early"].update(first=v), "s", "clock.json early.first"),
        "window.last": (lambda d, v: d["clock"]["windows"]["endgame"].update(last=v), "s", "clock.json endgame.last"),
    }

    @staticmethod
    def minus(unit):
        """A formula that gives less than nothing."""
        return "= -pen.side" if unit == "in" else "= gap.lasts - auto.lasts"

    def test_not_more_than_0(self):
        """Catches a field with no size, or a period or a window that lasts no time: printed, worked out or for one variant; each is told once, at its own place."""
        def put(d, value, only=None):
            for name, (change, unit, _) in self.PUT.items():
                if only in (None, name):
                    change(d, value(unit, "9 ft" if unit == "in" else "80 s"))
        for value, at in [(lambda unit, good: f"0 {unit}", ""), (lambda unit, good: f"-5 {unit}", ""), (lambda unit, good: f"0 {unit} +/- 1", ""), (lambda unit, good: self.minus(unit), ""), (lambda unit, good: f"at most 0 {unit}", ""),
                          (lambda unit, good: {"by": "event", "regional": good, "championship": f"0 {unit}"}, ".championship"), (lambda unit, good: {"by": "event", "regional": self.minus(unit), "championship": good}, ".regional"),
                          (lambda unit, good: {"is": f"-1 {unit}", "src": "manual 3.1"}, ".is")]:
            found = self.faults(lambda d: put(d, value))
            self.assertEqual(sorted(one.partition(":")[0] for one in found), sorted(f"{where}{at}" for _, _, where in self.PUT.values()))
            self.assertTrue(all("more than 0" in one for one in found), found)
        for name, (_, unit, where) in self.PUT.items():
            self.refused(lambda d: put(d, lambda unit, good: f"-5 {unit}", name), f"{where}:", f'"-5 {unit}"')
        self.accepted(lambda d: put(d, lambda unit, good: {"is": good, "was": [{"until": "2031-02-04", "is": f"0 {unit}", "src": "update3 3.1"}], "differs": [{"is": f"-1 {unit}", "src": "manual 3.1"}]}))

    def test_a_little_more_than_0(self):
        """Control: what is more than 0 passes, however little, and so does a time or a length of which nobody says that it must be. What is of another kind, or a range, is told as that alone."""
        self.refused(lambda d: d["field"]["size"].update(width="= -hoop.mass"), "field.json size.width", "a mass, not a length")
        self.refused(lambda d: d["places"]["vine"]["starts"].update(pumpkin="-2 to -1"), "places.json vine.starts.pumpkin", "is a range")
        self.accepted(lambda d: d["clock"]["windows"]["early"].update(first="0.001 s"))
        self.accepted(lambda d: d["clock"]["windows"]["early"].update(first="1 s +/- 2"))
        self.accepted(lambda d: d["clock"]["windows"]["early"].update(first="= auto.lasts - gap.lasts"))
        self.accepted(lambda d: d["clock"]["states"]["lit"].update(grace="0 s"))
        self.accepted(lambda d: d["field"]["zones"]["fold"].update(deep="-2 in"))

    def test_a_variant_of_a_formula(self):
        """Catches a formula that gives nothing only for a variant that nobody asked first."""
        for variant in ["regional", "championship"]:
            self.refused(lambda d: d["scoring"]["awards"]["loft_rp"].update(spare={"by": "event", "regional": "3 s", "championship": "3 s", variant: "12 s"}) or d["clock"]["windows"]["early"].update(
                first="= auto.lasts - loft_rp.spare"), "clock.json early.first:", "more than 0")

    def test_how_many_start(self):
        """Catches fewer pieces than none at the start, printed, worked out or for one variant, told once; none at all is a count."""
        start = lambda d, place, many: d["places"][place]["starts"].update({"bale": many})
        for many, at in [(-2, ""), (-3, ""), ({"each": "spot", "is": -1}, ".is"), ("= robot_preload.holds.bale - 4", ""), ("less than -1", ""), ({"by": "event", "regional": 4, "championship": -4}, ".championship"),
                         ({"by": "event", "regional": 4, "championship": {"each": "spot", "is": "= 2 - 3"}}, ".championship.is")]:
            self.refused(lambda d: start(d, "near_bales", many), f"places.json near_bales.starts.bale{at}:", "below 0")
        self.refused(lambda d: start(d, "robot_preload", "= -robot_preload.holds.bale"), "places.json robot_preload.starts.bale:", "below 0", '"= -robot_preload.holds.bale"')
        self.refused(lambda d: d["places"]["vine"]["starts"].update(pumpkin=-1), "places.json vine.starts.pumpkin:", "below 0")     # and not that what is left over for the patch is not whole
        for many in [0, "= robot_preload.holds.bale - 3", {"each": "spot", "is": 0}, {"by": "event", "regional": 0, "championship": 2}]:
            self.accepted(lambda d: start(d, "near_bales", many))

    def test_which_places_say_so(self):
        """Catches a property that fails to say that it must be more than 0, or not below 0, or a new one that has no case above."""
        from frc_design_kernel.rules import read
        flagged = lambda least: sorted(f"{kind}.{name}" for kind, about in read.names()["kinds"].items() for name, one in about["fields"].items() if one.get("least") == least)
        self.assertEqual((flagged("more than 0"), flagged("0 or more")), (sorted(self.PUT), ["place.starts"]))


class Says(Refused):
    """Words whose numbers cannot be filled in."""

    def test_what_cannot_be_printed(self):
        """Catches a {name} that stands for a record, a shape, a list of points, or the end of one number."""
        says = lambda d, text: d["robot"]["rules"]["R98"].update(says=text)
        for path in ["crate", "barn.opening", "bale.shape", "yard.outline", "barn.takes", "limits.start.height.low", "hang.needs"]:
            self.refused(lambda d: says(d, "It is {%s}." % path), "robot.json R98.says", path)
        self.accepted(lambda d: says(d, "It is {bale.mass.low} or {crate.at}."))

    def test_at_any_depth(self):
        """Catches words deeper in a record that are not looked at."""
        self.refused(lambda d: d["places"]["barn"]["opening"].update(says="It is {barn.opening}."), "places.json barn.opening.says", "barn.opening")
        self.accepted(lambda d: d["places"]["barn"]["opening"].update(says="It is {bottom} up, {opening.depth} deep and {out} out, from the {from}."))

    def said(self, change, *paths):
        from frc_design_kernel.rules.rules import load_rules
        data = example()
        change(data)
        rules = load_rules(written(data))
        return [rules.get(path).value for path in paths]

    def test_says_that_need_each_other(self):
        """Catches words that name themselves, alone, through others, through a formula or at any depth: each loop is told once."""
        says = lambda d, code, text: d["robot"]["rules"][code].update(says=text)
        self.refused(lambda d: says(d, "R94", "At most {limits.drive.motors}: {R94.says}"), "robot.json R94.says", "needs itself", '"R94.says" needs "R94.says"')
        self.refused(lambda d: says(d, "R94", "As {R95.says}") or says(d, "R95", "As {R94.says}"), "robot.json R94.says", "needs itself", '"R95.says"')
        self.refused(lambda d: says(d, "R94", "As {R95.says}") or says(d, "R95", "As {R96.says}") or says(d, "R96", "As {R95.says}"), "robot.json R95.says", "needs itself")
        self.refused(lambda d: d["places"]["barn"]["opening"].update(says="It is {says}."), "places.json barn.opening.says", "needs itself")
        self.refused(lambda d: d["places"]["barn"]["opening"].update(says="As {barn.opening.says}"), "places.json barn.opening.says", "needs itself")
        self.accepted(lambda d: says(d, "R94", "As {R95.says}") or says(d, "R95", "As {R96.says}"))
        spots = lambda d, of, **texts: [d["places"][of]["spots"][name].update(says=text) for name, text in texts.items()]
        self.accepted(lambda d: d["places"]["stall"].update(says="Here: {stall.spots.near.says}") or spots(d, "stall", near="The near one."))
        self.accepted(lambda d: spots(d, "stall", near="Next to: {stall.spots.far.says}", far="By the corner."))
        self.accepted(lambda d: d["places"]["near_bales"].update(says="Each: {near_bales.spots.1.says}", gap="3 in") or spots(d, "near_bales", first="On the carpet, by {near_bales.gap}."))
        self.assertEqual(self.said(lambda d: spots(d, "stall", near="Next to: {stall.spots.far.says}", far="By the corner."), "stall.spots.near.says", "stall@red.near.says", "stall.spots.far.says"),
                         ["Next to: By the corner.", "Next to: By the corner.", "By the corner."])
        self.assertEqual(self.said(lambda d: d["places"]["near_bales"].update(says="All.") or spots(d, "near_bales", first="Each."), "near_bales.says", "near_bales.spots.2.says"), ["All.", "Each."])
        self.refused(lambda d: spots(d, "stall", near="{stall.spots.far.says}", far="{stall.spots.near.says}"), "places.json stall.spots.near.says:", '"stall.spots.near.says" needs "stall.spots.far.says" needs "stall.spots.near.says"')
        self.refused(lambda d: d["places"]["stall"].update(says="{stall.spots.near.says}") or spots(d, "stall", near="{stall.says}"), "needs itself", '"stall.says" needs "stall.spots.near.says"')
        self.accepted(lambda d: d["places"]["barn"]["opening"].update(says="As {R94.says}"))


class More(Refused):
    """faults and load_rules."""

    def chain(self, many, backward=False):
        """A folder in which each of many lengths is worked out from the next."""
        lengths = {f"n{i}": f"= pen.n{i + 1} + pen.n{i + 1} / 10" for i in range(many)} | {f"n{many}": "1 mm"}
        data = example()
        data["field"]["solids"]["pen"].update(dict(reversed(lengths.items())) if backward else lengths)
        return written(data)

    def test_a_chain_by_variant(self):
        """Catches a chain that goes through the names of variants and is not counted, as another reader works each of them out."""
        from frc_design_kernel.rules.rules import faults, load_rules
        for many, whole, backward in [(60, False, False), (30, False, True), (20, True, True)]:
            data = example()
            lengths = {f"n{i}": {"by": "field", "welded": f"= pen.n{i + 1}.bolted * 2", "bolted": f"= pen.n{i + 1}.welded"} for i in range(many)} | {f"n{many}": {"by": "field", "welded": "1 mm", "bolted": "2 mm"}}
            data["field"]["solids"]["pen"].update(dict(reversed(lengths.items())) if backward else lengths)
            found = faults(written(data))
            self.assertEqual([f.problem[:13] for f in found], [] if whole else ["needs a chain"], found)
        self.assertAlmostEqual(load_rules(written(data)).get("pen.n0").value, 2 ** 10)

    def red_chain(self, many):
        """A folder in which a ring of red's is placed by the next one's, many times over."""
        data = example()
        ring = lambda x: {"alliance": "each", "spots": {"ring": 2, "around": ["9 in", "1 in"], "step": "120 deg", "first": {"at": [x, "1 in"]}}}
        data["field"]["equipment"].update({f"z{i}": ring(f"= z{i + 1}@red.2.at.x / 2") for i in range(many)} | {f"z{many}": ring("5 in")})
        return written(data)

    def test_a_chain_through_red(self):
        """Catches a chain just long enough that the folder loads and whoever asks for its end is refused."""
        from frc_design_kernel.rules.rules import faults, load_rules
        for many in (47, 48, 49, 50):
            folder = self.red_chain(many)
            found = faults(folder)
            if not found:
                load_rules(folder).get("z0@red.2.at.x")
            self.assertEqual([f.problem[:13] for f in found], ["needs a chain"] * (many > 48), many)

    def test_a_chain_of_formulas(self):
        """Catches a chain of formulas that is so long that the reader stops with an error of its own, in place of a fault; or that
        loads, because it is written the other way round, and stops whoever asks for its end."""
        from frc_design_kernel.errors import DesignError
        from frc_design_kernel.rules.rules import faults, load_rules
        for backward in (False, True):
            for many in (51,) if backward else (51, 400):
                found = faults(self.chain(many, backward))
                self.assertEqual(len(found), 1, found)
                self.assertIn("one from another", found[0].problem)
                with self.assertRaises(DesignError):
                    load_rules(self.chain(many, backward))
            self.assertAlmostEqual(load_rules(self.chain(49, backward)).get("pen.n0").value, 1.1 ** 49)

    def test_data_that_is_too_deep(self):
        """Catches data inside data inside data that stops the reader with an error of its own."""
        from frc_design_kernel.rules.rules import examine
        text = json.dumps(example()["field"])
        side = '"side": {"is": "30 in", "of": "each side in plan"}'
        self.assertIn(side, text)
        for many, faults in [(3000, 1), (300, 0)]:
            folder = written({**example(), "field": text.replace(side, '"side": ' + '{"is": ' * many + '"30 in"' + "}" * many)})
            book, found = examine(folder)
            self.assertEqual((len(found), book is None), (faults, faults == 1), found)
        self.assertIn("too deep", examine(written({**example(), "field": text.replace(side, '"side": ' + "[" * 3000 + "]" * 3000)}))[1][0].problem)

    def test_every_fault(self):
        """Catches a list of faults that ends at the first, or at those of reading."""
        got = self.faults(lambda d: (d["field"]["solids"]["crate"]["at"].__setitem__(0, "= size.width + 3"), d["places"]["barn"].update(src="manaul 3"), d["places"]["vine"]["starts"].update(pumpkin=3)))
        self.assertEqual(len(got), 3, got)
        for where in ["field.json crate.at.x", "places.json barn.src", "places.json patch.starts.pumpkin"]:
            self.assertTrue(any(where in one for one in got), (where, got))

    def test_one_fault_is_told_once(self):
        """Catches a value that does not read and that is told again by everything worked out from it."""
        for change in [lambda d: d["field"]["size"].update(width="25 feet"), lambda d: d["field"]["solids"]["crate"]["at"].__setitem__(0, "131"), lambda d: d["field"]["solids"]["pen"].update(side="30 mm mm"),
                       lambda d: d["clock"]["periods"]["teleop"].update(lasts="110"), lambda d: d["pieces"]["pumpkin"]["shape"]["ball"].update(diameter="8"), lambda d: d["scoring"]["total"].update(bale="60"),
                       lambda d: d["clock"]["windows"]["endgame"].update(last="25"), lambda d: d["scoring"]["awards"]["bale_in_barn"]["points"][0].update(when=["atuo"]),
                       lambda d: d["field"]["solids"]["crate"]["at"].__setitem__(0, "= crat.at.x"), lambda d: d["clock"]["states"]["lit"].update(of="allience")]:
            self.refused(change)

    def test_an_id_used_twice_is_told_once(self):
        """Catches a second use of an ID that is told again for everything that names the thing."""
        self.refused(lambda d: d["game"]["people"].update(yard={"says": "Keeps it."}), "field.json yard", '"yard" is used twice, also in game.json')
        self.refused(lambda d: d["field"]["tags"].update(barn={"at": ["0 in", "10 in", "50 in"], "faces": "0 deg", "tilt": "0 deg"}), "places.json barn", '"barn" is used twice, also in field.json')
        self.refused(lambda d: d["scoring"]["judged"].update(hang={"awards": ["bale_on_bench"], "after_teleop": "1 s"}), "scoring.json judged.hang", '"hang" is used twice, also in scoring.json')
        self.refused(lambda d: d["game"]["sources"].update(bale={"title": "Bales"}), "pieces.json bale", '"bale" is used twice, also in game.json')
        self.accepted(lambda d: d["game"]["people"].update(keeper={"says": "Keeps it."}))

    def test_red_that_cannot_be_made(self):
        """Catches a field with no width, on which red's copy cannot be turned; a mirror image needs none."""
        from frc_design_kernel.rules.rules import faults
        game = {"name": "Hay", "season": 2031, "edition": "1", "sources": {"manual": {"title": "Manual"}}, "frame": {"origin": "a corner"}}
        for symmetry, size, many in [("turn", {"length": "9 m"}, 1), ("mirror", {"length": "9 m"}, 0), ("turn", {"length": "9 m", "width": "4 m"}, 0), ("mirror", {"width": "4 m"}, 1)]:
            field = {"size": size, "symmetry": symmetry, "zones": {"yard": {"alliance": "each", "at": ["1 m", "1 m"], "outline": {"circle": "1 m"}}}}
            found = faults(written(small(game=game, field=field, clock={"periods": {"auto": {"lasts": "9 s"}}})))
            missing = "width" if "length" in size else "length"
            self.assertEqual([f.where for f in found], [f'field.json yard the path "size.{missing}"'] * many, found)

    def test_the_first_is_raised(self):
        """Catches a folder with a fault that loads, or a control that does not."""
        from frc_design_kernel.errors import DesignError
        from frc_design_kernel.rules.rules import load_rules
        data = example()
        data["places"]["vine"]["starts"]["pumpkin"] = 3
        with self.assertRaises(DesignError) as caught:
            load_rules(written(data))
        self.assertEqual(caught.exception.where, "places.json patch.starts.pumpkin")
        load_rules(written(example()))

    def test_every_fault_of_a_folder(self):
        """Catches faults of working out that rules.faults leaves out, or faults of reading."""
        from frc_design_kernel.rules.rules import faults
        data = example()
        data["places"]["barn"]["src"] = "manaul 3"
        data["places"]["vine"]["starts"]["pumpkin"] = 3
        self.assertEqual([f.where for f in faults(written(data))], ["places.json barn.src", "places.json patch.starts.pumpkin"])
        self.assertEqual(faults(written(example())), [])

    def test_a_folder_that_does_not_read(self):
        """Catches a folder that does not read and whose faults are lost."""
        from frc_design_kernel.rules.rules import faults
        self.assertEqual([f.where for f in faults(written({k: v for k, v in small().items() if k != "terms"}))], ["terms.json"])
        self.assertGreater(len(faults(written(small()))), 5)


if __name__ == "__main__":
    unittest.main()
