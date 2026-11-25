"""Every path into every record that each alliance has, asked for red: what get gives is the matching part of what records, outline
and solid give, or what is written, the same for both, or it is refused. The answers it is compared with are made here, without get."""
import unittest
from unittest import mock

from frc_design_kernel.rules.read import spot_names

from .rules_cases import Derived, as_it_is, example, written

IN, AXES = 25.4, "xyz"
WHOLE, SPOTS = "is turned round for red", "is what blue's spots are made from"


def changed(symmetry):
    """The example with a field that is turned or mirrored, and with what it has not: positions by variant and through is, a solid at spots, a position of a spot by variant."""
    data = example()
    data["field"]["symmetry"] = symmetry
    solids = data["field"]["solids"]
    solids["crate"]["at"] = {"is": [{"by": "field", "welded": "131 in", "bolted": {"is": "130 in", "src": "drawings sheet 2"}}, "150 in", "0 in"], "src": "drawings sheet 1"}
    solids["crate"]["spread"] = {"is": [{"is": "1 in", "of": "its own"}, "2 in"], "each": "spot", "src": "drawings sheet 2"}
    solids["boulder"]["faces"] = {"by": "field", "welded": "30 deg", "bolted": "40 deg"}
    data["field"]["zones"]["fold"]["outline"] = {"by": "field", "welded": [["120 in", "250 in"], ["150 in", {"is": "250 in +/- 1", "src": "manual 3.2"}], ["150 in", "280 in"]], "bolted": {"rectangle": ["40 in", "24 in"]}}
    data["field"]["zones"]["lane"]["outline"][1][0] = {"by": "field", "welded": "60 in", "bolted": "61 in"}
    data["places"]["stall"]["spots"]["near"]["at"][1] = {"by": "field", "welded": "60 in", "bolted": "61 in"}
    data["places"]["stall"]["spots"]["near"].update(lean="3 in", says="By the wall, {lean} off.")
    data["places"]["near_bales"]["starts"] = {"bale": {"each": "spot", "is": {"by": "event", "regional": 1, "championship": {"is": 1, "src": "update3 4"}}}}
    data["places"]["barn"]["opening"]["outline"] = {"hexagon": {"flats": "20 in", "points": "10 deg"}}
    data["places"]["stall"]["opening"]["outline"] = {"hexagon": {"flats": "7 in", "points": "10 deg"}}
    data["places"]["barn"]["opening"]["top"] = data["field"]["solids"]["barn_body"]["shape"]["cut"][1]["box"][1] = data["field"]["solids"]["barn_body"]["shape"]["cut"][1]["box"][2] = "16 in"
    return data


class Oracle:
    """What red must be given, from the data as it is written and from records, outline and solid."""

    def __init__(self, rules, **variants):
        self.rules, self.variants, self.worker = rules, variants, rules.season.worker(**variants)
        self.placed = {r.name: r for file in ("field", "places") for r in rules.records(file, **variants)}
        self.skipped = {"is", *(name for known in rules.book.variants.values() for name in known)}
        self.mirror = rules.book.data["field"]["symmetry"] == "mirror"

    def mirrored(self, entry):
        return self.mirror if "symmetry" not in entry.data else entry.data["symmetry"] == "mirror"

    def is_of(self, entry, steps):
        """What a path's steps must give: ("at", numbers), ("as written", node), ("refused", why) or None for what is no one value."""
        head, name = steps[0], f"{entry.path}@red"
        node, inner = self.follow(entry.data, steps)
        if head == "spots" and steps[1:2] and {"row", "ring"}.isdisjoint(entry.data["spots"]):
            record = self.placed[f"{name}.{steps[1]}"]
            return ("at", self.part(getattr(record, steps[2]), steps[3:])) if steps[2:3] in (["at"], ["faces"]) else ("as written", node)
        if head == "spots":
            return "refused", SPOTS
        if head in ("at", "from", "to", "faces"):
            record = self.placed[name]
            whole = record.faces if head == "faces" else record.at if head == "at" else record.ends[("from", "to").index(head)]
            return "at", self.part(whole, steps[1:])
        if head == "outline" and isinstance(self.unwrapped(entry.data["outline"]), list):
            return "at", self.part(self.rules.outline(entry.path, "red", **self.variants), steps[1:])
        if head == "outline" and len([s for s in steps if s not in self.skipped]) == 1:
            return "at", self.rules.outline(entry.path, "red", **self.variants)
        if head in ("shape", "outline") or steps[:2] == ["opening", "outline"]:
            drawn = [s for s in inner if s not in self.skipped]
            if self.mirrored(entry) and self.turned(drawn):
                return "refused", WHOLE
        return "as written", node

    @staticmethod
    def turned(steps):
        """Whether a step goes into a point, to where a part stands, or to the angle of a hexagon."""
        return "at" in steps or "points" in steps or any(one in ("outline", "bottom", "top") and other in AXES for one, other in zip(steps, steps[1:]))

    def unwrapped(self, node):
        return self.worker.unwrap(node)[0]

    def part(self, whole, steps):
        for step in steps:
            if step in AXES:
                whole = whole[AXES.index(step)]
        return whole

    def follow(self, node, steps):
        for step in steps:
            node = node[AXES.index(step)] if isinstance(node, list) else node[step]
        return node, steps

    def written(self, node, entry):
        """The numbers or words of a node, as they are written: no position is in a formula here."""
        node = self.unwrapped(node)
        if isinstance(node, list):
            return [self.written(one, entry) for one in node]
        if isinstance(node, str) and node.startswith("="):
            return round(self.worker.formula(node).value, 6)
        return node["text"] if isinstance(node, dict) and "text" in node else node


def paths(node, steps=()):
    """The steps to every node of some data, but what was and what differs; of a list, as far as a path goes."""
    if steps:
        yield list(steps)
    for name, inner in node.items() if isinstance(node, dict) else zip(AXES, node) if isinstance(node, list) else ():
        if name not in ("was", "differs", "by", "unknown"):
            yield from paths(inner, (*steps, name))


def given(got):
    """Numbers and words of what get gives, as the Oracle has them."""
    if isinstance(got, (list, tuple)):
        return [given(one) for one in got]
    return round(got, 6) if isinstance(got, float) else got


class Red(Derived):
    def asked(self, rules, path, **asked):
        """What get gives, or what it says is wrong."""
        from frc_design_kernel.errors import DesignError
        try:
            return rules.get(path, **asked)
        except DesignError as problem:
            return problem.problem

    def differ(self, rules):
        """Every path of red's, written or into a spot, that ID@red.path does not answer as --alliance red does, or refuses with another thing to ask."""
        from frc_design_kernel.errors import DesignError

        def answer(path, **asked):
            try:
                return rules.get(path, **asked)
            except DesignError as problem:
                return problem.problem, problem.fix
        found, many = [], 0
        for entry in rules.book.entries:
            if entry.data.get("alliance") == "each" and entry.file in ("field", "places"):
                made = [["spots", *spot.split("."), *rest] for spot in spot_names(entry.data.get("spots")) for rest in (["at"], ["at", "x"], ["faces"], ["src"], ["opening", "outline"], ["post", "tip"], [])]
                for steps in (*paths(entry.data), *made):
                    tail, many = ".".join(steps), many + 1
                    if answer(f"{entry.path}.{tail}", alliance="red") != answer(f"{entry.path}@red.{tail}"):
                        found.append(f"{entry.path}@red.{tail}")
        self.assertGreater(many, 400)
        return found

    def test_both_ways_of_asking(self):
        """Catches a path for which ID@red.path and --alliance red do not give the same answer, or the same refusal."""
        for rules in (as_it_is(), self.rules_of("turn"), self.rules_of("mirror")):
            self.assertEqual(self.differ(rules), [])

    def test_two_ways_that_differ_are_caught(self):
        """Control: with spots that a path with @red does not go through, or an alliance that it does not tell, paths are found that differ."""
        from frc_design_kernel.rules import worker
        address = worker.Worker.address
        for patched in (mock.patch.object(worker, "after_spots", lambda _, steps: steps), mock.patch.object(worker.Worker, "address", lambda self, path: (lambda got: (got[0], None, *got[2:]))(address(self, path)))):
            with patched:
                self.assertGreater(len(self.differ(self.rules_of("mirror"))), 10)

    def all_of(self, rules, **variants):
        """How many paths are of each sort. Each is compared with what the Oracle says."""
        from frc_design_kernel.rules.worth import Value
        oracle, many = Oracle(rules, **variants), {}
        for entry in rules.book.entries:
            if entry.data.get("alliance") != "each" or entry.file not in ("field", "places"):
                continue
            for steps in paths(entry.data):
                named = {kind: step for step in steps for kind, known in rules.book.variants.items() if step in known}
                ours = oracle if not named else Oracle(rules, **{**variants, **named})
                sort, what = ours.is_of(entry, steps)
                with self.subTest(f"{entry.path}.{'.'.join(steps)}", **variants):
                    got = self.asked(rules, f"{entry.path}.{'.'.join(steps)}", alliance="red", **variants)
                    if sort == "refused":
                        self.assertIsInstance(got, str)
                        self.assertTrue(got.startswith(what), got)
                    elif isinstance(got, str):      # a list, conditions, a group, or words beside a value: no one value, for blue neither
                        sort = "no value"
                        self.assertNotIn(got, (SPOTS, WHOLE))
                        self.refused_for_blue(rules, entry, steps, **variants)
                    elif sort == "at":
                        numbers = [one.value for one in got] if isinstance(got, list) and got and isinstance(got[0], Value) else got.value if isinstance(got, Value) else got
                        self.assertEqual(given(numbers), given(what))
                    else:
                        sort = self.same(ours, entry, steps, what, got)
                many[sort] = many.get(sort, 0) + 1
        return many

    def refused_for_blue(self, rules, entry, steps, **variants):
        from frc_design_kernel.errors import DesignError
        with self.assertRaises(DesignError):
            rules.get(f"{entry.path}.{'.'.join(steps)}", **variants)

    def same(self, oracle, entry, steps, node, got):
        """A value that is written: the same for both. A drawing is red's own, with y turned round for a mirror image."""
        from frc_design_kernel.rules.worth import Value
        from frc_design_kernel.rules import outlines, shapes
        node, mirrored = oracle.unwrapped(node), oracle.mirrored(entry)
        if isinstance(got, dict) or isinstance(got, shapes.Taper):
            solid = isinstance(got, dict) and len(oracle.placed[f"{entry.path}@red"].at) > 2
            self.assertEqual(got, oracle.rules.solid(entry.path, "red", **oracle.variants)["shape"] if solid else shapes.drawn(oracle.worker, entry, node, mirrored))
            return "drawn"
        if isinstance(got, list) and got and isinstance(got[0], tuple):
            self.assertEqual(given(got), given([(x, -y if mirrored else y) for x, y in outlines.drawn(oracle.worker, entry, node, False)]))
            return "drawn"
        if isinstance(got, Value):
            want = oracle.written(node, entry)
            if want == "left over":
                want = oracle.rules.starts(steps[-1], **oracle.variants)[f"{entry.path}@red"]
            if steps[-1] == "says":
                self.assertEqual(got.value, oracle.rules.says(entry.path, **oracle.variants) if steps == ["says"] else "By the wall, 3 in off.")
            else:
                self.assertEqual(given(got.value) if isinstance(want, float) else got.printed, want if isinstance(want, float) else str(want).lower() if isinstance(want, bool) else str(want))
        else:
            self.assertEqual(len(got), len(node))
        return "as written"

    def rules_of(self, symmetry):
        from frc_design_kernel.rules.rules import load_rules
        return load_rules(written(changed(symmetry)))

    def test_every_path(self):
        """Catches an answer for red that is blue's, anywhere in the example: as it is, and with what it lacks on a field that is turned, and
        on one that is mirrored."""
        turned, mirrored = self.rules_of("turn"), self.rules_of("mirror")
        for rules, variants, refused in [(as_it_is(), {}, 40), (turned, {}, 40), (mirrored, {}, 60), (mirrored, {"field": "bolted"}, 60)]:
            found = self.all_of(rules, **variants)
            for sort, least in [("at", 130), ("as written", 240), ("refused", refused), ("drawn", 15), ("no value", 120)]:
                self.assertGreater(found[sort], least, (sort, found))

    def test_every_spot(self):
        """Catches a spot of red's that stands or looks elsewhere than its record, or that the two ways of asking do not give alike."""
        for rules in (as_it_is(), self.rules_of("mirror")):
            for file in ("field", "places"):
                for record in rules.records(file):
                    if record.alliance == "red" and record.spot:
                        for head in ("spots.", ""):
                            self.assertEqual(given([one.value for one in rules.get(f"{record.entry.path}@red.{head}{record.spot}.at")]), given(list(record.at)), record.name)
                            self.assertAlmostEqual(rules.get(f"{record.entry.path}@red.{head}{record.spot}.faces").value if record.entry.path in ("rack", "stall") else record.faces, record.faces)
                        self.assertEqual(given(rules.get(f"{record.entry.path}.spots.{record.spot}.at.y", alliance="red").value), given(record.at[1]))
                        self.assertEqual(given(rules.get(f"{record.entry.path}.at.x", alliance="red", spot=record.spot).value), given(record.at[0]))

    def test_what_to_ask(self):
        """Catches what is refused for red with nothing to ask in its place, or with something that does not answer."""
        from frc_design_kernel.errors import DesignError
        rules = self.rules_of("mirror")
        for path, ask in [("rack.spots.around.x", "rack@red.1.a.at"), ("near_bales.spots.step", "near_bales@red.1.at"), ("rope.spots", "rope@red.front.at"), ("ramp.shape.prism.outline.x.y", "ramp@red.shape"), ("trestle.shape.join.y.at.x", "trestle@red.shape"),
                          ("barn.opening.outline.hexagon.points", "barn@red.opening.outline"), ("paddock.outline.hexagon.points", "paddock@red.outline"),
                          ("stall.spots.near.opening.outline.hexagon.points", "stall@red.near.opening.outline")]:
            with self.assertRaises(DesignError) as caught:
                rules.get(path, alliance="red")
            self.assertIn(ask, caught.exception.fix, path)
            self.assertTrue(rules.get(ask))

    def test_a_formula_of_red(self):
        """Catches a formula that names a point of red's outline, or a coordinate of red's by variant, and is given blue's."""
        data = changed("mirror")
        data["field"]["zones"]["pond"].update(own="= lane@red.outline.y.x - lane.outline.y.x", other="= crate@red.at.x.bolted", third="= near_bales@red.spots.3.at.y")
        from frc_design_kernel.rules.rules import load_rules
        rules = load_rules(written(data))
        self.is_(rules.get("pond.own"), "length", (612.40 - 60 - 60) * IN)
        self.is_(rules.get("pond.other"), "length", (611.75 - 130) * IN)
        self.is_(rules.get("pond.third"), "length", (66 + 2 * 48) * IN)
        self.assertEqual(round(rules.get("fold@red.outline.y.y.low").value / IN, 6), 249)

    def test_a_wrong_answer_is_caught(self):
        """Control: with red's points of an outline given as blue's, and nothing refused as turned round, the test of every path fails."""
        from frc_design_kernel.rules import alliances, worker
        for patched in (mock.patch.object(alliances.Place, "listed", False), mock.patch.object(worker.Season, "turned", lambda *_: False)):
            with patched:
                case = Red("test_every_path")
                result = unittest.TestResult()
                rules = self.rules_of("mirror")
                case.test_every_path = lambda: case.all_of(rules)
                case.run(result)
            self.assertGreater(len(result.failures), 3)


if __name__ == "__main__":
    unittest.main()
