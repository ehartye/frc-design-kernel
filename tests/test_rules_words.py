"""Every word and every ID that a field names: conditions, times, costs, people, places and parts (RULES.md)."""
import unittest

from frc_design_kernel.errors import DesignError

from .rules_cases import FILES, Checked, example, rename, written


class Words(Checked):
    """words.check: every word and every ID that a field names. It includes what fields.check finds."""

    def faults(self, change=None):
        from frc_design_kernel.rules import read, words
        data = example()
        if change:
            change(data)
        book, faults = read.gather("", data)
        return [str(f) for f in faults + words.check(book)]

    def test_the_example_has_no_faults(self):
        """Control for every refusal in this class: the example as it is passes every check."""
        self.assertEqual(self.faults(), [])

    def test_a_condition_that_is_not_one(self):
        """Catches a condition with a word that is not in the list, two parts, or a form that nobody reads."""
        rule = lambda d: d["conduct"]["G90"]
        self.refused(lambda d: rule(d).update(must_not=[["either bumpers", "inside", "their yard"]]), "conduct.json G90.must_not[0]", "inside", "fully in")
        self.refused(lambda d: rule(d).update(must_not=[["either bumpers", "their yard"]]), "G90.must_not[0]", "who, how, what")
        self.refused(lambda d: rule(d).update(must_not=["either bumpers", "partly in", "their yard"][:1]), "G90.must_not[0]")
        self.refused(lambda d: rule(d).update(must_not=False), "G90.must_not")
        self.refused(lambda d: rule(d).update(must_not=[]), "G90.must_not")
        self.refused(lambda d: rule(d).update(must_not=[{"any": []}]), "G90.must_not[0].any")
        self.refused(lambda d: rule(d).update(must_not=[{"some": [["my robot", "touching", "carpet"]]}]), "G90.must_not[0]", '"some"', "any")
        self.refused(lambda d: rule(d).update(must_not=[{"when": ["auto"]}]), "G90.must_not[0]", "any or all")
        self.refused(lambda d: rule(d).update(must_not=[{"any": [["my robot", "touching", "carpt"]]}]), "G90.must_not[0].any[0]", "carpt")
        self.refused(lambda d: d["robot"]["limits"]["start"].update(where=[["my bumpers", "fully in", "my yrad"]]), "limits.start.where[0]", 'Did you mean "yard"')
        self.refused(lambda d: d["scoring"]["awards"]["loft_rp"]["easier"]["needs"][0].__setitem__(1, "more than"), "loft_rp.easier.needs[0]", "at least")

    def test_who_in_a_condition(self):
        """Catches someone who is not there: a slip in my, in bumpers, in a counted thing or in a piece."""
        needs = lambda d, who: d["scoring"]["awards"]["park"]["needs"][0].__setitem__(0, who)
        for who, hint in [("our bumpers", "my"), ("my bumper", "bumpers"), ("bumpers", "my"), ("the robot", "piece"), ("the bail", "bale"), ("my", "bumpers"), ("my yard", "robot"), (3, "my")]:
            self.refused(lambda d: needs(d, who), "park.needs[0]", hint)
        self.refused(lambda d: d["scoring"]["awards"]["loft_rp"]["needs"][0].__setitem__(0, "my loft_pionts"), "loft_rp.needs[0]", 'Did you mean "loft_points"')
        for who in ["their robot", "either person", "my alliance", "the piece", "the hoop", "their loft_points"]:
            self.accepted(lambda d: needs(d, who))

    def test_what_in_a_condition(self):
        """Catches a zone that is not there, or a name with no my, their or any, and lets words through in a list."""
        what = lambda d, w: d["scoring"]["awards"]["park"]["needs"][0].__setitem__(2, w)
        for bad, hint in [("their wong", "wong"), ("yard", "my"), ("my hang", "hang"), ("every bale", "every robot"), (True, "park"), (["my yrad"], "yard"), ([3], "park"), ("3 feet", "feet"), ([], "park")]:
            self.refused(lambda d: what(d, bad), "park.needs[0]", hint)
        for good in ["any yard", "carpet", "every robot", 3, "= lit.bank", "3 in", {"by": "event", "regional": 3, "championship": 4}, ["my yard", "my long fence", "a hay stack"], "their bale"]:
            self.accepted(lambda d: what(d, good))

    def test_when(self):
        """Catches a window, period, state or variant that is not there, and my in front of something that is nobody's."""
        when = lambda d, w: d["conduct"]["G90"].update(when=w)
        for bad, hint in [(["endgam"], 'Did you mean "endgame"'), (["not endgam"], "endgame"), (["their teleop"], "teleop"), (["never lit"], "lit"), ("endgame", "list"), ([3], "3"), (["hang"], "hang"), (["not not lit"], "lit")]:
            self.refused(lambda d: when(d, bad), "conduct.json G90.when", hint)
        for good in [["teleop", "lit"], ["not endgame"], ["their lit"], ["not their lit"], ["playoff"], []]:
            self.accepted(lambda d: when(d, good))
        for change, where in [(lambda d: d["scoring"]["awards"]["hang"]["points"][0].update(when=["telop"]), "hang.points[0].when"),
                              (lambda d: d["clock"]["states"]["barn_open"]["true"][1].append("shut"), "clock.json barn_open.true[1]"),
                              (lambda d: d["clock"]["states"]["barn_open"].update(true=["auto"]), "clock.json barn_open.true[0]"),
                              (lambda d: d["scoring"]["counts"]["early_bales"].update(when=["autos"]), "early_bales.when"),
                              (lambda d: d["conduct"]["G90"]["cost"][1].update(when=["qualifying"]), "G90.cost[1].when"),
                              (lambda d: d["conduct"]["G95"]["must_not"][0]["any"][0].update(when=["late"]), "G95.must_not[0].any[0].when"),
                              (lambda d: d["scoring"]["awards"]["loft_rp"]["easier"].update(when=["sharing"]), "loft_rp.easier.when"),
                              (lambda d: d["scoring"]["awards"]["hang"].update(most={"is": 2, "when": ["tele"]}), "hang.most.when")]:
            self.refused(change, where)

    def test_periods(self):
        """Catches a window in a period that is not there, and a late time after one."""
        self.refused(lambda d: d["clock"]["windows"]["early"].update({"in": "telop"}), "clock.json early.in", 'Did you mean "teleop"')
        self.refused(lambda d: rename(d["scoring"]["judged"]["late"], "after_auto", "after_autos"), "judged.late.after_autos", "auto")

    def test_awards(self):
        """Catches an award that is not there: in a score, a count, a judged time, a denied award, one that cancels, one that is also needed."""
        for change, where in [(lambda d: d["places"]["barn"]["takes"][0].update(score="bail_in_barn"), "places.json barn.takes[0].score"),
                              (lambda d: d["scoring"]["counts"]["loft_points"]["adds"].append("prak"), "loft_points.adds[3]"),
                              (lambda d: d["scoring"]["counts"]["hanging_robots"].update(counts=["hnag"]), "hanging_robots.counts[0]"),
                              (lambda d: d["scoring"]["judged"]["late"]["awards"].append("minor"), "judged.late.awards[2]"),
                              (lambda d: d["scoring"]["awards"]["park"].update(unless=["hung"]), "park.unless[0]"),
                              (lambda d: d["scoring"]["awards"]["swing_high"].update(also_needs="hang"), "swing_high.also_needs"),
                              (lambda d: d["conduct"]["G95"]["cost"][1].update(deny=["hangs"]), "G95.cost[1].deny[0]"),
                              (lambda d: d["conduct"]["G90"]["cost"][1].update(award="lofty"), "G90.cost[1].award")]:
            self.refused(change, where)

    def test_places_and_pieces(self):
        """Catches a place or a piece that is not there: where a piece goes, what is taken, held, staged, counted or limited."""
        for change, where, hint in [
                (lambda d: d["places"]["barn"].update(then={"to": "celar"}), "places.json barn.then.to", "cellar"),
                (lambda d: d["places"]["stall"]["gives"][0].update(to="flor"), "stall.gives[0].to", "floor"),
                (lambda d: d["places"]["stall"]["gives"][0].update(to="hang"), "stall.gives[0].to", "barn"),
                (lambda d: d["places"]["barn"]["takes"][0].update(piece="bail"), "barn.takes[0].piece", "bale"),
                (lambda d: rename(d["places"]["stall"]["starts"], "bale", "bail"), "stall.starts", "bale"),
                (lambda d: rename(d["places"]["stall"]["holds"], "bale", "bail"), "stall.holds", "bale"),
                (lambda d: rename(d["scoring"]["total"], "hoop", "hoops"), "scoring.json total", "hoop"),
                (lambda d: d["robot"]["limits"]["hold"].update(bales=2), "limits.hold", "bale"),
                (lambda d: d["conduct"]["G94"]["limit"].update(gourd=1), "G94.limit", "pumpkin"),
                (lambda d: d["conduct"]["G93"].update(piece="bail"), "G93.piece", "bale"),
                (lambda d: d["conduct"]["G96"].update(piece=["bale", "barn"]), "G96.piece[1]", "hoop"),
                (lambda d: d["scoring"]["counts"]["third_best"]["third_largest_of"].append("yard"), "third_best.third_largest_of[4]", "barn"),
                (lambda d: d["scoring"]["counts"]["pumpkins_everywhere"].update(smallest_of=["lofts"]), "pumpkins_everywhere.smallest_of[0]", "loft")]:
            self.refused(change, where, hint)

    def test_things_that_a_rule_names(self):
        """Catches a thing that is not there in what, into, where, may_touch, or a word that is not a thing."""
        for change, where, hint in [
                (lambda d: d["conduct"]["G90"].update(what="their robots"), "G90.what", 'Did you mean "robot"'), (lambda d: d["conduct"]["G97"].update(what=["any nkot"]), "G97.what[0]", "knot"),
                (lambda d: d["conduct"]["G93"].update(into="any lofft"), "G93.into", "loft"), (lambda d: d["conduct"]["G93"].update(into="endgame"), "G93.into", "loft"),
                (lambda d: d["conduct"]["G94"].update(where=["my flod"]), "G94.where[0]", "fold"), (lambda d: d["field"]["hangs"]["rope"].update(may_touch=["my ropes"]), "rope.may_touch[0]", "rope"),
                (lambda d: d["field"]["hangs"]["rope"].update(may_not_touch="any knot"), "rope.may_not_touch", "list"), (lambda d: d["conduct"]["G93"].update(into="our loft"), "G93.into", "my")]:
            self.refused(change, where, hint)
        self.accepted(lambda d: d["conduct"]["G93"].update(into="loft"))
        self.accepted(lambda d: d["field"]["hangs"]["rope"].update(may_touch=["my two ropes", "the end"]))

    def test_people(self):
        """Catches someone who is not there: together, or bound by a rule, or a list that is one name."""
        self.refused(lambda d: d["game"]["people"]["together"][0].update(of=["driver", "mascot"]), "game.json people.together[0].of[1]", "feeder")
        self.refused(lambda d: d["conduct"]["G96"].update(who=["feder"]), "G96.who[0]", "feeder")
        self.refused(lambda d: d["conduct"]["G96"].update(who="feeder"), "G96.who", "list")
        self.refused(lambda d: d["conduct"]["G96"].update(who=["together"]), "G96.who[0]")
        self.accepted(lambda d: d["conduct"]["G91"].update(who=["robot", "coach"]))

    def test_how_long(self):
        """Catches a rule about longer than a word that is not a term, or than something that is not a time."""
        self.refused(lambda d: d["conduct"]["G94"].update(longer_than="momentry"), "G94.longer_than", "momentary")
        self.refused(lambda d: d["conduct"]["G94"].update(longer_than="3 in"), "G94.longer_than", "time")
        self.accepted(lambda d: d["conduct"]["G94"].update(longer_than="= momentary.lasts"))

    def test_costs(self):
        """Catches a cost that is not there, has none or two of its main fields, or stands instead of a foul that is not given."""
        cost = lambda d, rule, i: d["conduct"][rule]["cost"][i]
        self.refused(lambda d: d["conduct"]["G90"].update(cost=["miner"]), "conduct.json G90.cost[0]", 'Did you mean "minor"')
        self.refused(lambda d: cost(d, "G91", 0).update(foul="green_card"), "G91.cost[0].foul", "yellow_card")
        self.refused(lambda d: cost(d, "G96", 0).update(either=["yellow_card", "green_card"]), "G96.cost[0].either[1]", "red_card")
        self.refused(lambda d: cost(d, "G91", 0).update(words="and more"), "G91.cost[0]", "foul, award, deny, either or words")
        self.refused(lambda d: cost(d, "G91", 1).pop("words"), "G91.cost[1]", "foul, award, deny, either or words")
        self.refused(lambda d: cost(d, "G90", 1).pop("to"), "G90.cost[1]", '"to"')
        self.refused(lambda d: cost(d, "G93", 1).update(instead_of="red_card"), "G93.cost[1].instead_of", "red_card", "minor")
        self.refused(lambda d: d["conduct"]["G93"].update(cost=[{"foul": "minor", "instead_of": "minor"}]), "G93.cost[0].instead_of")
        self.refused(lambda d: d["conduct"]["G90"].update(cost="minor"), "G90.cost", "list")
        self.refused(lambda d: d["conduct"]["G90"].update(cost=[3]), "G90.cost[0]")
        self.accepted(lambda d: d["conduct"]["G93"].update(cost=[{"either": ["minor", "red_card"]}, {"foul": "major", "instead_of": "red_card"}]))

    def test_an_act_with_nothing_to_judge(self):
        """Catches a rule that a program is told to compute, with nothing that makes it wrong or right."""
        self.refused(lambda d: d["conduct"]["G90"].pop("must_not"), "conduct.json G90", "must_not, only_if or limit")
        self.accepted(lambda d: [d["conduct"]["G90"].pop(k) for k in ("must_not", "act", "what")])

    def test_loads(self):
        """Catches a device only for a load that is not there, in words, or on a thing that runs nothing."""
        parts = lambda d: d["robot"]["parts"]
        self.refused(lambda d: parts(d)["relays"]["switch"].update(only_for=["lantrn"]), "parts.relays.switch.only_for[0]", 'Did you mean "lantern"')
        self.refused(lambda d: parts(d)["relays"]["switch"].update(only_for=["whistle"]), "parts.relays.switch.only_for[0]")
        self.refused(lambda d: parts(d)["relays"]["switch"].update(only_for={"text": "lamps"}), "parts.relays.switch.only_for", "list")
        self.refused(lambda d: parts(d)["wire"]["main"].update(only_for=["lantern"]), "parts.wire.main.only_for", "kind")

    def test_says_names(self):
        """Catches a {name} in says that is nowhere: in the record, in another record, in a limit or in a part."""
        self.refused(lambda d: d["conduct"]["G92"].update(says="For more than {longst}."), "conduct.json G92.says", "longst")
        self.refused(lambda d: d["clock"]["states"]["lit"].update(says="{endgame.lst}"), "clock.json lit.says", 'Did you mean "last"')
        self.refused(lambda d: d["robot"]["rules"]["R98"].update(says="No thinner than {parts.wire.mane.thinnest}."), "R98.says", 'Did you mean "main"')
        self.refused(lambda d: d["robot"]["parts"]["wire"]["main"].update(says="No thinner than {thinest}."), "parts.wire.main.says", "thinest")
        self.refused(lambda d: d["conduct"]["G94"].update(says="{limit.bail}"), "G94.says", 'Did you mean "bale"')
        self.accepted(lambda d: d["conduct"]["G92"].update(says="{judged.late.after_teleop}, {parts.wire.main.area}, {longest}, {pumpkin.mass.low}, {tags.t3.at.x}, {total.bale}"))

    def test_a_number_typed_twice(self):
        """Catches a number typed in says that the record holds, which would not change when the value does."""
        self.refused(lambda d: d["conduct"]["G92"].update(says="Not for more than 5 s."), "conduct.json G92.says", "5", "longest")
        self.refused(lambda d: d["field"]["equipment"]["barn_light"].update(says="It stands 18 in above."), "barn_light.says", "18")
        self.refused(lambda d: d["scoring"]["awards"]["loft_rp"].update(says="With 2 robots."), "loft_rp.says", "2")
        self.refused(lambda d: d["robot"]["parts"]["wire"]["main"].update(says="No thinner than 6."), "parts.wire.main.says", "6")
        self.refused(lambda d: d["places"]["rack"].update(says="Pegs 1 1/4 in thick."), "rack.says", "1 1/4")
        self.accepted(lambda d: d["conduct"]["G92"].update(says="Not for more than 55 s, nor 0.5 s, as of 2031-05-05, by G5 and rule5, figure 5-5, 1:05 or 5/8, 5/0."))
        self.accepted(lambda d: d["field"]["equipment"]["barn_light"].update(says="It stands 19 in above."))

    def test_formula_names(self):
        """Catches a formula that names nothing, in a list, a variant or a condition."""
        self.refused(lambda d: d["places"]["barn"].update(at=["= tag.t1.at.x", "0 in"]), "places.json barn.at.x", 'Did you mean "tags"')
        self.refused(lambda d: d["field"]["hangs"]["swing"]["at"][2].update(high_gate="= swing.lfit"), "swing.at.z.high_gate", "lift")
        self.refused(lambda d: d["scoring"]["awards"]["loft_rp"]["needs"][0].__setitem__(2, "= loft_rp.neded"), "loft_rp.needs[0]", "needed")
        self.refused(lambda d: d["conduct"]["G94"].update(longer_than="= momentary.last"), "G94.longer_than", "lasts")
        self.accepted(lambda d: d["places"]["barn"].update(at=["= 2 * cos(tags.t1.faces) * stall@red.near.at.x", "= bale.mass.low * size.width / bale.mass.high"]))

    def test_a_thing_with_no_geometry(self):
        """Catches a zone, line, solid or hang that a rule or a score names, of which nobody can say where it is."""
        self.refused(lambda d: [d["field"]["zones"]["fold"].pop(k) for k in ("outline", "at")], "field.json fold", "no_geometry", "G94")
        self.refused(lambda d: [d["field"]["lines"]["gate_line"].pop(k) for k in ("from", "to")], "field.json gate_line", "G95")
        self.refused(lambda d: d["field"]["hangs"]["knot"].pop("no_geometry"), "field.json knot", "no_geometry")
        self.refused(lambda d: d["places"]["stall"].pop("spots"), "places.json stall", "G96")
        self.accepted(lambda d: [d["field"]["zones"]["fold"].pop(k) for k in ("outline", "at")] + [d["field"]["zones"]["fold"].update(no_geometry="Not drawn.")])
        self.accepted(lambda d: [d["field"]["hangs"]["mast"].pop("at"), d["places"]["rack"].update(spots={"a": {"at": ["1 in", "2 in"]}}),
                                 d["field"]["hangs"]["mast"].update(shape_note=True, spots={"one": {"at": ["1 in", "2 in"]}}), d["places"]["rack"].update(out="3 in")])

    def test_a_thing_that_no_rule_names_needs_no_geometry(self):
        """Control: a line that no rule or score names may have no geometry at all."""
        self.accepted(lambda d: d["field"]["lines"].update(path={"says": "A path."}))

    def test_reading_a_folder(self):
        """Catches faults of one stage hidden by another, and a folder that does not read taken for an empty game."""
        from frc_design_kernel.rules import words
        book, faults = words.load(written(example()))
        self.assertEqual((faults, book.look("size.width").node), ([], "25 ft"))
        data = example()
        data["places"]["yard"] = {"hue": "red"}
        data["conduct"]["G90"]["cost"] = ["miner"]
        _, faults = words.load(written(data))
        self.assertEqual([f.where for f in faults], ["places.json yard", "places.json yard.hue", "conduct.json G90.cost[0]"])
        data["clock"] = "{"
        book, faults = words.load(written(data))
        self.assertEqual((book, [f.where for f in faults]), (None, ["clock.json line 1"]))

    def test_the_first_fault(self):
        """Catches a caller that wants one error and gets a list, or none."""
        from frc_design_kernel.rules import words
        self.assertEqual(words.first(written(example())).look("total.bale").node, 60)
        data = example()
        data["conduct"]["G90"]["cost"] = ["miner"]
        with self.assertRaises(DesignError) as caught:
            words.first(written(data))
        self.assertEqual(caught.exception.where, "conduct.json G90.cost[0]")

    def test_leaves_of_conditions(self):
        """Catches a value in a condition, or a time in longer_than, that a later step would never see."""
        from frc_design_kernel.rules import read, words
        book, _ = read.gather("", example())
        leaves = {leaf.where: (leaf.kind, leaf.node) for leaf in words.leaves(book)}
        for where, leaf in [("scoring.json loft_rp.needs[0]", (None, "= loft_rp.needed")), ("scoring.json loft_rp.easier.needs[0].championship", (None, 14)),
                            ("conduct.json G96.longer_than", ("time", "10 s")), ("field.json lane.long", (None, "60 in"))]:
            self.assertEqual(leaves.get(where), leaf, where)

    def test_the_wrong_kind_of_data_is_never_a_crash(self):
        """Catches a crash, with no file or record named, where the data is of another kind than the format says."""
        from frc_design_kernel.rules import read, words
        tried, seen, ids = 0, set(), set(read.gather("", example())[0].ids)
        for name in FILES:
            for trail in _trails(example()[name], seen, ids):
                data = example()
                wrong = [None, 3, "some words", [], {}][tried % 5]
                _put(data[name], trail, wrong)
                book, faults = read.gather("", data)
                for fault in faults + words.check(book):
                    self.assertIsInstance(fault, DesignError)
                    self.assertTrue(fault.where.split()[0].endswith(".json"), fault)
                tried += 1
        self.assertGreater(tried, 100)


def _trails(data, seen, ids):
    """The keys that lead to one place for each field name not seen yet, so that every kind of field is tried once. IDs are passed by."""
    trails = []

    def visit(node, trail):
        name = next((step for step in reversed(trail) if isinstance(step, str)), None)
        if trail and name not in seen and name not in ids:
            seen.add(name)
            trails.append(trail)
        for key, value in node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ():
            visit(value, (*trail, key))

    visit(data, ())
    return trails


def _put(data, trail, value):
    for step in trail[:-1]:
        data = data[step]
    data[trail[-1]] = value


if __name__ == "__main__":
    unittest.main()
