"""The slips that an author makes, one at a time in the invented example. A reader once passed files without looking at them, so
each of these must be refused, and the same folder with none of them must not be."""
import copy
import functools
import json
import random
import unittest

from .rules_cases import example, rename, written
from .test_rules_refusals import Refused


def limits(d):
    return d["robot"]["limits"]


def parts(d):
    return d["robot"]["parts"]


def rule(d, code):
    return d["conduct"][code]


def award(d, name):
    return d["scoring"]["awards"][name]


def barn(d, text):
    d["places"]["barn"].update(at=[text, "0 in"])


SLIPS = [    # what it is, how to make it, the place that is told, and what is said of it
    ("a unit misspelt", lambda d: d["field"]["size"].update(width="25 feet"), "field.json size.width", "feet"),
    ("a unit that is not listed", lambda d: limits(d)["air"].update(flow="at most 1.1 scfh"), "limits.air.flow", "scfh"),
    ("words that start with a number", lambda d: d["places"]["barn"].update(note_size="14 by 10"), "barn.note_size", "14 by 10"),
    ("a formula that names nothing", lambda d: barn(d, "= chimny.at.x"), "barn.at.x", "chimny"),
    ("a bare number added", lambda d: barn(d, "= size.width + 3"), "barn.at.x", "adds a count to a length"),
    ("a length and a mass", lambda d: barn(d, "= size.width + hoop.mass"), "barn.at.x", "adds a mass to a length"),
    ("formulas that need each other", lambda d: d["field"]["size"].update(width="= pen.side") or d["field"]["solids"]["pen"].update(side="= size.width"), "field.json", "needs itself"),
    ("a word that is not in the list", lambda d: rule(d, "G90").update(must_not=[["my bumpers", "inside", "their yard"]]), "G90.must_not[0]", "inside"),
    ("a zone that is not there", lambda d: rule(d, "G90").update(must_not=[["my bumpers", "partly in", "their yrad"]]), "G90.must_not[0]", "yrad"),
    ("something counted that is not there", lambda d: award(d, "loft_rp").update(needs=[["my loft_pionts", "at least", 10]]), "loft_rp.needs[0]", "loft_pionts"),
    ("a window that is not there", lambda d: rule(d, "G95").update(when=["teleop", "not endgaem"]), "G95.when[1]", "endgaem"),
    ("an award that is not there", lambda d: d["places"]["barn"]["takes"][0].update(score="bale_in_bran"), "barn.takes[0].score", "bale_in_bran"),
    ("a foul that is not there", lambda d: rule(d, "G90").update(cost=["minro"]), "G90.cost[0]", "minro"),
    ("an award that is denied and not there", lambda d: rule(d, "G95")["cost"][1].update(deny=["hnag"]), "G95.cost[1].deny[0]", "hnag"),
    ("a place that a piece goes to and is not there", lambda d: d["places"]["barn"].update(then={"to": "celler"}), "barn.then.to", "celler"),
    ("a name in says that is not there", lambda d: rule(d, "G92").update(says="For more than {longst}, or within {apart}, {apart_for}."), "G92.says", "longst"),
    ("a number typed in says", lambda d: rule(d, "G92").update(says="No hold of more than 5 s, nor within {apart}, for {apart_for}."), "G92.says", "types 5"),
    ("a source that is not there", lambda d: d["places"]["barn"].update(src="manaul 5.3"), "barn.src", "manaul"),
    ("what differs, with no source", lambda d: d["field"]["solids"]["pen"]["side"].update(differs=[{"is": "36 in"}]), "pen.side.differs[0]", '"src"'),
    ("an ID that is used twice", lambda d: d["places"].update(yard=copy.deepcopy(d["places"]["vine"])), "places.json yard", "twice"),
    ("a slip in a field's name", lambda d: rename(d["places"]["barn"], "opening", "openning"), "barn", "openning"),
    ("a slip inside an opening", lambda d: rename(d["places"]["stall"]["opening"], "bottom", "botom"), "stall.opening", "botom"),
    ("a zone that a rule names, with no outline", lambda d: d["field"]["zones"]["lane"].pop("outline"), "field.json lane", "geometry"),
    ("a rule with no cost", lambda d: rule(d, "G98").pop("cost"), "G98", '"cost"'),
    ("an act with nothing to judge", lambda d: rule(d, "G98").pop("must_not"), "G98", "nothing to judge"),
    ("an act that is not there", lambda d: rule(d, "G98").update(act="shoot"), "G98.act", "shoot"),
    ("a variant that is left out", lambda d: award(d, "loft_rp")["easier"]["needs"][0].__setitem__(2, {"by": "event", "regional": 18}), "loft_rp.easier.needs[0]", "championship"),
    ("a limit that is not a name", lambda d: limits(d).update(power={"says": "x", "src": "manual 8"}), "limits.power", "power"),
    ("a weight that is not a name", lambda d: limits(d)["weight"].update(naked={"max": "at most 100 lb", "without": []}), "limits.weight", "naked"),
    ("a slip in a limit's field", lambda d: limits(d)["bumpers"].update(toleranse="1/4 in"), "limits.bumpers", "toleranse"),
    ("a slip in a part's field", lambda d: parts(d)["motors"]["mule"].update(part_numers=["x"]), "parts.motors.mule", "part_numers"),
    ("a kind of device that is not there", lambda d: parts(d)["controllers"]["reins"].update(kind="box"), "parts.controllers.reins.kind", "box"),
    ("a load on a kind that is not there", lambda d: parts(d)["motors"]["mule"].update(on={"contoller": 1}) or d["robot"]["rules"]["R97"].update(says="x"), "parts.motors.mule.on", "contoller"),
    ("only for a load that is not there", lambda d: parts(d)["relays"]["switch"].update(only_for=["lantren"]), "parts.relays.switch.only_for[0]", "lantren"),
    ("only for, in words", lambda d: parts(d)["relays"]["switch"].update(only_for={"text": "lantern"}), "parts.relays.switch.only_for", "list"),
    ("only for, on something that runs nothing", lambda d: parts(d)["wire"]["main"].update(only_for=["lantern"]), "parts.wire.main.only_for", "runs nothing"),
    ("a wire size that is not one", lambda d: parts(d)["wire"]["main"].update(thinnest="6 gauge"), "parts.wire.main.thinnest", "gauge"),
    ("a part with no source", lambda d: parts(d)["motors"]["mule"].pop("src"), "parts.motors.mule", '"src"'),
    ("a part whose source is not there", lambda d: parts(d)["motors"]["mule"].update(src="manaul R97"), "parts.motors.mule.src", "manaul"),
    ("a group that allows something else", lambda d: parts(d)["motors"]["about"].update(allow="some"), "parts.motors.about.allow", "some"),
    ("a part in says that is not there", lambda d: d["robot"]["rules"]["R98"].update(says="No thinner than {parts.wire.mane.thinnest}."), "R98.says", "mane"),
    ("a history with no date", lambda d: limits(d)["weight"]["robot"]["max"]["was"][0].pop("until"), "limits.weight.robot.max.was[0]", '"until"'),
    ("a history that is not a list", lambda d: limits(d)["weight"]["robot"]["max"].update(was={"is": "at most 110 lb"}), "limits.weight.robot.max.was", "list"),
    ("a history whose value does not read", lambda d: limits(d)["weight"]["robot"]["max"]["was"][0].update({"is": "110 pounds"}), "limits.weight.robot.max.was[0].is", "pounds"),
    ("in place of a foul that is not given", lambda d: rule(d, "G93")["cost"][1].update(instead_of="red_card"), "G93.cost[1].instead_of", "red_card"),
    ("every, which is not a time", lambda d: rule(d, "G95")["cost"][0].update(every="3 in"), "G95.cost[0].every", "length"),
    ("again, which is not a word of the list", lambda d: rule(d, "G91")["cost"][0].update(again="season"), "G91.cost[0].again", "season"),
    ("either, with a foul that is not there", lambda d: rule(d, "G96")["cost"][0].update(either=["yellow_card", "green_card"]), "G96.cost[0].either[1]", "green_card"),
    ("together, with someone who is not there", lambda d: d["game"]["people"]["together"][0].update(of=["driver", "mascot"]), "people.together[0].of[1]", "mascot"),
    ("someone who must obey and is not there", lambda d: rule(d, "G96").update(who=["mascot"]), "G96.who[0]", "mascot"),
    ("longer than a word that is not a term", lambda d: rule(d, "G94").update(longer_than="momentry"), "G94.longer_than", "momentry"),
    ("a judged time of an award that is not there", lambda d: d["scoring"]["judged"]["late"].update(awards=["bale_in_bran"]), "judged.late.awards[0]", "bale_in_bran"),
    ("the sine of a length", lambda d: barn(d, "= size.width * sin(size.length)"), "barn.at.x", "takes sin of a length"),
    ("a range the wrong way round", lambda d: d["pieces"]["bale"].update(mass="9 to 8 oz"), "bale.mass", "above its high end"),
    ("one is enough, which does not read", lambda d: limits(d)["bumpers"].update(frame_gap={"any": [{"deep": "a bit"}]}) or d["robot"]["rules"]["R93"].update(says="x"), "limits.bumpers.frame_gap.any[0].deep", "a bit"),
]
RAW = [      # the same, in the text of clock.json
    ("a field that is written twice", '"bank": 6, "bank": 7', "clock.json states.lit", "twice"),
    ("a number that is not ordinary", '"bank": Infinity', "clock.json states.lit.bank", "ordinary"),
]


ODD = [None, 3, True, "x", "3 in", "2 to 3 in", "= crate.at.x", [], ["3 in"], {}, {"is": "3 in"}, {"by": "field", "welded": "3 in", "bolted": "3 lb"}, {"by": "nothing"},
       {"any": [{"deep": "3 in"}]}, {"text": "words"}, {"each": "spot", "is": 1}, "any", "left over"]


def nodes(data, way=()):
    """The way to every node of some data."""
    for name in data if isinstance(data, dict) else range(len(data)) if isinstance(data, list) else ():
        yield (*way, name)
        yield from nodes(data[name], (*way, name))


class Beside(Refused):
    """A slip beside a value, or in it, when the value is named past it."""

    CAP = {"by": "event", "regional": 2, "championship": 3}

    def test_a_slip_beside_a_value(self):
        """Catches a slip in what differs, or when, that stops the reader, or is told again, when the value is named past it: by a formula or
        words, through is, a variant, a list or any."""
        for slip in (5, None, True, "auto", {}, ["auto and teleop"], [5], [None], ["zebra"], [{}]):
            def change(d, beside=True):
                d["scoring"]["awards"]["hang"].update(most={"is": self.CAP, **({"when": slip} if beside else {})}, says="{most.regional} {most.is}")
                d["robot"]["rules"]["R98"].update(says="{hang.most.regional} {hang.most.is} {hang.most.is.championship} {hang.most}")
                d["places"]["cellar"]["holds"].update(bale="= hang.most.regional * 2")
            self.refused(change, "scoring.json hang.most.when")
        self.accepted(lambda d: change(d, beside=False))
        for slip in (5, None, True, "133 in", {}, {"is": "133 in", "src": "drawings sheet 6"}):
            def change(d):
                d["field"]["solids"]["crate"].update(at={"is": ["131 in", "150 in", "0 in"], "differs": slip})
                d["field"]["zones"]["pond"].update(own={"is": {"any": [{"a": "1 in"}, {"b": "2 in"}]}, "differs": slip}, says="{own.a} {own.is.b} {pond.own.a}", k="= pond.own.b")
                d["game"]["people"]["coach"].update(step={"is": "1 in", "differs": slip}, says="{step.is}")
            self.assertEqual([one.partition(":")[0] for one in self.faults(change)], ["game.json people.coach.step.differs", "field.json pond.own.differs", "field.json crate.at.differs"])

    def test_a_slip_in_a_value(self):
        """Catches a value at fault that is told again where it is named without the is, the any or the place in a list that it is in."""
        most = lambda d: d["scoring"]["awards"]["hang"].update(most={"is": {**self.CAP, "regional": "two"}})
        for path in ("hang.most.regional", "hang.most.is.regional"):
            self.refused(lambda d: most(d) or d["places"]["cellar"]["holds"].update(bale=f"= {path} * 2"), "scoring.json hang.most.is.regional:")
        self.refused(lambda d: d["field"]["zones"]["pond"].update(own={"is": ["1 zz", "2 in"]}, k="= pond.own.x * 2"), "field.json pond.own.is.x:")
        self.refused(lambda d: d["field"]["zones"]["pond"].update(own={"any": [{"a": "1 zz"}, {"b": "2 in"}]}, k="= pond.own.a * 2"), "field.json pond.own.any[0].a:")
        self.refused(lambda d: d["field"]["zones"]["fold"].update(outline=[["1 in", "2 in"], ["9 zz", "2 in"], ["9 in", "8 in"], ["1 in", "8 in"]]) or d["field"]["zones"]["pond"].update(k="= fold.outline.y.x"), "field.json fold.outline[1].x:")
        both = self.faults(lambda d: d["field"]["solids"]["crate"].update(differs=5) or d["field"]["zones"]["pond"].update(k="= crate.at.x + hoop.mass"))
        self.assertEqual(len(both), 2, both)      # beside a record, it is no slip of its values


class Slips(unittest.TestCase):
    def faults(self, data):
        from frc_design_kernel.rules.rules import faults
        return [str(f) for f in faults(written(data))]

    def test_every_slip_is_refused(self):
        """Catches a slip that is passed, or that is told of another place."""
        for name, change, where, says in SLIPS:
            with self.subTest(name):
                data = example()
                change(data)
                found = self.faults(data)
                self.assertTrue(any(where in one and says in one for one in found), found)

    def test_every_slip_of_the_text(self):
        """Catches a slip that the JSON reader itself hides."""
        text = json.dumps(example()["clock"])
        for name, slip, where, says in RAW:
            with self.subTest(name):
                found = self.faults({**example(), "clock": text.replace('"bank": 6', slip)})
                self.assertTrue(any(where in one and says in one for one in found), found)

    def test_odd_data(self):
        """Catches data that nobody expected and that stops the reader, in place of a fault: some of all there is, the same each time."""
        from frc_design_kernel.rules import derive, read, words
        ways = [way for way in nodes(example()) if len(way) > 1]
        self.assertGreater(len(ways), 1500)
        chosen = random.Random(1)
        for way, odd in [(chosen.choice(ways), chosen.choice(ODD)) for _ in range(40)]:
            with self.subTest(f"{way} {odd}"):
                data = example()
                inside = functools.reduce(lambda node, name: node[name], way[:-1], data)
                inside[way[-1]] = odd
                book, faults = read.gather("", data)
                faults += words.check(book)
                faults += derive.faults(book, faults)
                self.assertTrue(all(f.where for f in faults))

    def test_no_slip(self):
        """Control: the folder that the slips are made in has no faults, and there are as many slips as there were."""
        self.assertEqual(self.faults(example()), [])
        self.assertEqual(self.faults({**example(), "clock": json.dumps(example()["clock"])}), [])
        self.assertEqual(len(SLIPS) + len(RAW), 57)
        self.assertEqual(len({name for name, *_ in SLIPS + RAW}), 57)


if __name__ == "__main__":
    unittest.main()
