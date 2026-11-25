"""Each value is written once: a number that changes changes all that is worked out from it, and nothing else."""
import copy
import json
import unittest

from .rules_cases import Checked, Derived, example, written


def everything(rules, **variants):
    """{name: what it is} of all that is worked out: every position, outline and shape, every says, every formula and every count."""
    from frc_design_kernel.rules import words
    found = {}
    for file in ("field", "places"):
        for r in rules.records(file, **variants):
            found.update({f"{r.name}.at": r.at, f"{r.name}.outline": r.outline, f"{r.name}.ends": r.ends})
    for entry in rules.book.entries:
        if "says" in entry.data and entry.path:
            found[f"{entry.path}.says"] = rules.says(entry.path, **variants)
        if "shape" in entry.data:
            found[f"{entry.path}.shape"] = rules.get(f"{entry.path}.shape", **variants)
    worker = rules.season.worker(**variants)
    for leaf in words.leaves(rules.book):
        if isinstance(leaf.node, str) and leaf.node.startswith("="):
            found[leaf.where.partition(" ")[2].removesuffix(".is")] = worker.formula(leaf.node)
    for piece in rules.book.of_kind("piece"):
        for place, many in rules.starts(piece, **variants).items():
            found[f"{place} {piece}"] = many
    found.update({f"window {n}": w for n, w in rules.windows(**variants).items()})
    return {name: what for name, what in found.items() if what is not None}


class Once(Derived):
    """What changes when one number does."""

    def changed(self, change, **variants):
        before, after = everything(self.rules(), **variants), everything(self.rules(change), **variants)
        self.assertEqual(set(before), set(after))
        return {name for name in before if before[name] != after[name]}

    def test_a_limit(self):
        """Catches a limit whose says, or whose formula in another limit, keeps the old number."""
        self.assertEqual(self.changed(lambda d: d["robot"]["limits"]["start"].update(height="at most 5 ft")), {"limits.height.max", "R90.says", "R91.says", "G99.says"})

    def test_a_count(self):
        """Catches a count that keeps its old number in another file, in what is left over, or for red."""
        self.assertEqual(self.changed(lambda d: d["robot"]["limits"]["preload"].update(bale=2)),
                         {"robot_preload.holds.bale", "robot_preload.starts.bale", "robot_preload.says", "G99.says", "robot_preload@blue bale", "robot_preload@red bale", "stall@blue bale", "stall@red bale"})
        self.assertEqual(self.changed(lambda d: d["robot"]["limits"]["hold"].update(bale=2)), {"G94.limit.bale", "G94.says"})

    def test_a_position(self):
        """Catches a thing that stands by another and stays where it was: in a formula, a row, a ring, a pair, or red's copy."""
        got = self.changed(lambda d: d["field"]["solids"]["pen"]["at"].__setitem__(0, "190 in"))
        spots = {f"rack@{a}.{i}.{p}.at" for a in ("blue", "red") for i in range(1, 7) for p in "ab"} | {f"rope@{a}.{n}.at" for a in ("blue", "red") for n in ("front", "left", "right")}
        places = {f"{name}@{a}.at" for name in ("pen", "mast") for a in ("blue", "red")}
        self.assertEqual(got, spots | places | {"rope.spots.around.x", "rope.spots.first.at.x", "mast.at.x", "rack.spots.around.x", "rack.spots.first.a.at.x", "rack.spots.first.b.at.x"})
        self.assertEqual(self.changed(lambda d: d["places"]["near_bales"].update(apart="40 in")), {"near_bales.spots.step.y", *(f"near_bales@{a}.{i}.at" for a in ("blue", "red") for i in "234")})
        self.assertEqual(self.changed(lambda d: d["field"]["tags"]["t3"]["at"].__setitem__(1, "13 in")), {"tags.t3.at", "patch.at.y", "patch@blue.at", "patch@red.at"})

    def test_the_size_of_the_field(self):
        """Catches a red copy, a middle or an end of a line that keeps the old length, for its variant only."""
        change = lambda d: d["field"]["size"]["length"].update(bolted="600 in")
        self.assertEqual(self.changed(change), set())
        got = self.changed(change, field="bolted")
        one = ["yard", "paddock", "fold", "crate", "manger", "boulder", "tyre", "culvert", "ramp", "barn_body", "trestle", "pen", "arch", "bar", "swing", "mast", "patch", "barn", "loft", "chimney", "bench"]
        spots = {"gateway": ["near", "far"], "rope": ["front", "left", "right"], "near_bales": "1234", "rack": [f"{i}.{p}" for i in "123456" for p in "ab"], "hooks": ["left", "right"]}     # red's stalls stand at 0
        red = {f"{name}@red.at" for name in one} | {f"{name}@red.{spot}.at" for name, known in spots.items() for spot in known}
        red |= {f"{name}@red.outline" for name in ("yard", "paddock", "lane", "fold")} | {"gate_line@red.ends"}
        middle = {"pond.at", "pond.outline", "centre.ends", "silo.at", "bridge.at", "spare_hoops.at", "vine.at", *(f"centre_bales.spots.{i}.at" for i in "abcdef")}
        blue = {"loft@blue.at", "chimney@blue.at", "stall@blue.near.at", "stall@blue.far.at", "tags.t2.at"}
        formulas = {f"{name}.x" for name in ["pond.at", "centre.from", "centre.to", "silo.at", "bridge.at", "tags.t2.at", "centre_bales.spots.first.at", "stall.spots.near.at", "stall.spots.far.at", "loft.at", "chimney.at", "spare_hoops.at", "vine.at"]}
        self.assertEqual(got, red | middle | blue | formulas)

    def test_a_variant(self):
        """Catches one variant that is worked out from another and keeps its old number."""
        change = lambda d: d["field"]["hangs"]["swing"]["at"][2].update(low_gate="14 in")
        self.assertEqual(self.changed(change), {"swing@blue.at", "swing@red.at", "swing.at.z.high_gate"})
        self.assertEqual(self.changed(change, gate="high_gate"), {"swing@blue.at", "swing@red.at", "swing.at.z.high_gate"})

    def test_a_shape_a_time_and_an_angle(self):
        """Catches a shape, a window or a sine that is not worked out again."""
        self.assertEqual(self.changed(lambda d: d["field"]["zones"]["yard"].update(deep="50 in")),
                         {"yard.outline.rectangle.x", "yard@blue.outline", "yard@red.outline", "gate_line.from.x", "gate_line.to.x", "gate_line@blue.ends", "gate_line@red.ends"})
        self.assertEqual(self.changed(lambda d: d["clock"]["windows"]["endgame"].update(last="20 s")), {"window endgame", "G90.says", "G95.says"})
        self.assertEqual(self.changed(lambda d: d["places"]["barn"]["opening"].update(slope="70 deg")), {"barn.opening.top"})
        self.assertEqual(self.changed(lambda d: d["pieces"]["pumpkin"].update(mass="6 oz")), {"hoop.mass"})

    def test_a_number_that_is_typed_twice(self):
        """Control: with a number typed in place of a formula, what should change does not."""
        typed = example()
        typed["robot"]["limits"]["height"]["max"] = "66 in"
        before = written(typed)
        typed["robot"]["limits"]["start"]["height"] = "at most 5 ft"
        from frc_design_kernel.rules.rules import load_rules
        old, new = everything(load_rules(before)), everything(load_rules(written(typed)))
        self.assertEqual({name for name in old if old[name] != new[name]}, {"R90.says", "G99.says"})


class Twice(Checked):
    """A value that is written twice is refused."""

    def faults(self, change=None):
        from frc_design_kernel.rules.rules import faults
        data = copy.deepcopy(example())
        if change:
            change(data)
        return [str(f) for f in faults(written(data))]

    def test_in_says(self):
        """Catches a number typed in says that the record holds."""
        self.refused(lambda d: d["conduct"]["G89"].update(says="At most 3 bales in its own fold for longer than {longer_than}."), "conduct.json G89.says", "types 3")
        self.accepted(lambda d: d["conduct"]["G89"].update(says="At most {limit.bale} bales in its own fold for longer than {longer_than}."))

    def test_in_says_at_any_depth(self):
        """Catches a number typed in words deeper in a record, where the record holds it; what was once so, or others say, may hold it."""
        barn = lambda d, where, text: d["places"]["barn"][where].update(says=text)
        self.refused(lambda d: barn(d, "opening", "It is 5 in deep."), "places.json barn.opening.says", "types 5, which barn.opening.depth holds")
        self.refused(lambda d: barn(d, "opening", "It stands 20 in out."), "places.json barn.opening.says", "types 20, which barn.out holds")
        self.refused(lambda d: d["places"]["stall"]["spots"]["near"].update(says="It is 60 in along."), "places.json stall.spots.near.says", "types 60")
        self.refused(lambda d: d["robot"]["limits"]["weight"]["bumpers"].update(says="At most 16 lb."), "robot.json limits.weight.bumpers.says", "types 16")
        self.refused(lambda d: d["places"]["barn"]["takes"][0].update(says="Over 48 in."), "places.json barn.takes[0].says", "types 48")
        self.accepted(lambda d: barn(d, "opening", "It is {depth} deep and 17 in wide."))
        self.accepted(lambda d: d["places"]["barn"].update(was=[{"until": "2031-02-04", "says": "It was 20 in out.", "src": "update3 5"}]))
        self.accepted(lambda d: d["places"]["barn"].update(differs=[{"says": "It is 20 in out.", "src": "drawings sheet 6"}]))

    def test_a_key(self):
        """Catches a field written twice, of which JSON keeps the last."""
        from frc_design_kernel.rules.rules import faults
        data = {name: json.dumps(one) for name, one in example().items()}
        self.assertIn('"bank": 6', data["clock"])
        twice = {**data, "clock": data["clock"].replace('"bank": 6', '"bank": 6, "bank": 7')}
        self.assertEqual([(f.where, f.problem) for f in faults(written(twice))], [("clock.json states.lit", 'the field "bank" is written twice')])
        self.assertEqual(faults(written(data)), [])


if __name__ == "__main__":
    unittest.main()
