"""Windows, late scores, conditions, when and says of the example."""
import unittest

from .rules_cases import Derived

IN = 25.4


class Times(Derived):
    """rules.windows and rules.judged."""

    def test_windows(self):
        """Catches a window that is counted from the wrong end of its period, or a timer that is read as if it counted up."""
        rules = self.rules()
        self.assertEqual({n: (w.period, w.start, w.end) for n, w in rules.windows().items()},
                         {"endgame": ("teleop", 85, 110), "early": ("teleop", 0, 35), "market": ("teleop", 35, 60)})

    def test_a_window_follows_its_period(self):
        """Catches a window that keeps its seconds when its period gets longer, or that is not of the variant that is asked."""
        longer = self.rules(lambda d: d["clock"]["periods"]["teleop"].update(lasts={"by": "event", "regional": "2 min 10 s", "championship": "2 min"}))
        self.assertEqual([(w.start, w.end) for w in longer.windows().values()], [(105, 130), (0, 35), (55, 80)])
        self.assertEqual([(w.start, w.end) for w in longer.windows(event="championship").values()], [(95, 120), (0, 35), (45, 70)])

    def test_late_scores(self):
        """Catches a late piece that falls in no period, or one that counts after a period in which it does not."""
        rules = self.rules()
        self.assertEqual(rules.judged("bale_in_barn"), {"auto": 2, "teleop": 3})
        self.assertEqual(rules.judged("hang"), {"teleop": 4})
        self.assertEqual(rules.judged("bale_on_bench"), {})
        self.wrong(lambda: rules.judged("bale_in_bran"), 'Did you mean "bale_in_barn"')

    def test_points(self):
        """Catches the rows of an award that lose their time, or their variant."""
        rules = self.rules()
        rows = rules.points("bale_in_barn")
        self.assertEqual([([m.name for m in row.when], row.points.value) for row in rows], [(["auto"], 7), (["teleop"], 3), (["teleop", "lit"], 6)])
        self.assertEqual(rules.points("bale_on_bench")[0].points.value, 1)
        self.assertEqual(rules.points("bale_on_bench", event="championship")[0].points.value, 2)
        self.assertEqual(rules.points("loft_rp"), [])
        self.wrong(lambda: rules.points("loft_pr"), "loft_rp")


class When(Derived):
    """rules.when: each name as a period, a window, a state or a variant."""

    def names(self, moments):
        return [(m.name, m.kind, m.whose, m.negated) for m in moments]

    def test_what_a_name_is(self):
        """Catches a name that is taken for another kind, or a `not`, `my` or `their` that is lost."""
        rules = self.rules()
        self.assertEqual(self.names(rules.when("G95.when")), [("teleop", "period", None, False), ("endgame", "window", None, True)])
        self.assertEqual(self.names(rules.when("loft_rp.when")), [("qualification", "variant", None, False)])
        self.assertEqual(rules.when("loft_rp.when")[0].of, "match")
        self.assertEqual(self.names(rules.when("loft_rp.easier.when")), [("shared", "state", None, False)])
        self.assertEqual(self.names(rules.when(["not lit", "stuck", "their stuck", "ripe", "full"])),
                         [("lit", "state", "my", True), ("stuck", "state", None, False), ("stuck", "state", "their", False), ("ripe", "state", None, False), ("full", "state", None, False)])
        self.assertEqual(rules.when("early_bales.when")[0].entry.path, "auto")
        self.wrong(lambda: rules.when(["endgam"]), "endgame")
        self.wrong(lambda: rules.when("G91.when"), "G91")

    def test_a_state_made_of_states(self):
        """Catches a state whose ways of being true run together, or that loses whose the other state is."""
        rules = self.rules()
        self.assertEqual([self.names(one) for one in rules.when("barn_open.true")],
                         [[("auto", "period", None, False)], [("market", "window", None, False), ("lit", "state", "my", True)], [("endgame", "window", None, False)]])
        self.assertEqual([self.names(one) for one in rules.when("quiet.true")], [[("teleop", "period", None, False), ("barn_open", "state", "my", True)], [("lit", "state", "their", False)]])


class Conditions(Derived):
    """rules.conditions: (who, how, what), with the IDs resolved."""

    def test_one_condition(self):
        """Catches a condition that loses whose someone or something is."""
        one, = self.rules().conditions("G90.must_not")
        self.assertEqual((one.who.whose, one.who.name, one.who.entry, one.how), ("either", "bumpers", None, "partly in"))
        self.assertEqual((one.what.whose, one.what.name, one.what.entry.path), ("their", "yard", "yard"))

    def test_groups(self):
        """Catches conditions of which one is enough that come back as if all were needed, or that lose their time."""
        one, = self.rules().conditions("G95.must_not")
        self.assertEqual((one.kind, one.when, len(one.of)), ("any", (), 2))
        inner, line = one.of
        self.assertEqual((inner.kind, [m.name for m in inner.when], [c.how for c in inner.of]), ("all", ["early"], ["beyond", "touching"]))
        self.assertEqual((inner.of[1].what, line.what.name), ("carpet", "gate_line"))

    def test_what(self):
        """Catches a number, a formula, a count, a piece or a list that is not read as one."""
        rules = self.rules()
        points, robots = rules.conditions("loft_rp.needs")
        self.assertEqual((points.who.whose, points.who.name, points.who.entry.kind, points.how, points.what.value), ("my", "loft_points", "count", "at least", 12))
        self.assertEqual(robots.what.value, 2)
        self.assertEqual(rules.conditions("loft_rp.needs", event="championship")[0].what.value, 16)
        self.assertEqual(rules.conditions("loft_rp.easier.needs", event="championship")[0].what.value, 14)
        self.assertEqual([c.what if isinstance(c.what, str) else c.what.value for c in rules.conditions("all_moved.needs")], ["every robot", 6])
        touching, base, only = rules.conditions("hang.needs")
        self.assertEqual(base.what, ("carpet", "the base of my mast"))
        self.assertEqual([one if isinstance(one, str) else (one.whose, one.name) for one in only.what], [("my", "bar"), ("my", "mast"), "pieces", "a robot that hangs"])
        piece, bale, person = rules.conditions("G96.only_if")
        self.assertEqual([(c.who.whose, c.who.name, c.who.entry and c.who.entry.kind) for c in (piece, bale, person)], [("the", "piece", None), ("the", "bale", "piece"), ("my", "person", None)])
        self.assertEqual([(c.what.name, c.how) for c in rules.conditions("limits.start.where")], [("yard", "fully in"), ("crate", "not touching")])
        self.assertIs(rules.conditions("G97.must_not"), True)
        words = self.rules(lambda d: d["scoring"]["awards"]["hang"]["needs"].__setitem__(1, ["my robot", "not touching", ["the yard", "my tall yard", "pond"]]))
        self.assertEqual([one if isinstance(one, str) else (one.whose, one.name) for one in words.conditions("hang.needs")[1].what], ["the yard", "my tall yard", (None, "pond")])
        self.wrong(lambda: rules.conditions("G91.must_not"), "G91")
        self.wrong(lambda: rules.conditions("yard.deep"), "conditions")


class Says(Derived):
    """rules.says: what a record says, with its numbers filled in."""

    def test_what_is_filled_in(self):
        """Catches a limit that prints its own words, a number of another record, a formula that prints as a formula, or a list."""
        says = self.rules().says
        self.assertEqual(says("R90"), "The string is at most 118 in; a bolt head may stick out less than 3/8 in. At the start a robot is at most 4 ft tall.")
        self.assertEqual(says("R91"), "Never taller than 66 in, and at most 1 ft 2 in out on 1 side.")
        self.assertEqual(says("R93"), "Bumpers fill the zone from 2 in to 7 1/4 in. A gap behind them is at most 3/8 in deep or 9 in wide.")
        self.assertEqual(says("G89"), "A robot may keep at most 3 bales in its own fold for longer than 10 s.")
        self.assertEqual(says("G94"), "A robot may carry at most 1 bale and 2 pumpkins at once. More than that counts when it is longer than momentary.")
        self.assertEqual(says("G95")[:60], "In teleop before the last 25 s, at most 1 robot of an allian")
        self.assertIn("a Mule is run at most 2 to a controller or 1 to a relay", says("R97"))
        self.assertEqual(says("R98"), "The main wire is no thinner than 6 AWG; a motor has 40 A. The fuse holder is seen from 3 ft.")
        self.assertEqual(says("manger"), "Its faces lean inward, up to 12 in.")
        self.assertEqual(says("accuracy"), "Field sizes are nominal. Drawings hold 0.4 in and 2 deg.")
        self.assertEqual(says("parts.wire.main"), "No thinner than 6 AWG.")
        self.assertEqual(says("judged.climbs"), "Looked at for up to 4 s.")
        self.assertEqual(says("spare_hoops"), "On top of the silo, 36 in up.")

    def test_every_one_of_the_example(self):
        """Catches a {name} that is left in, in any record."""
        rules = self.rules()
        many = 0
        for entry in rules.book.entries:
            if "says" in entry.data and entry.path:
                self.assertNotRegex(rules.says(entry.path), r"[{}]", entry.path)
                many += 1
        self.assertGreater(many, 50)

    def test_other_forms(self):
        """Catches a range, words, a flag, a list, a variant or limits of which one is enough that do not print."""
        rules = self.rules(lambda d: d["robot"]["rules"]["R98"].update(
            says="{bale.mass}, {bale.mass.high}, {pumpkin.mass}, {size.surface}, {pumpkin.stiff}, {limits.battery.size}, {size.length}, {limits.bumpers.frame_gap}, {yard.height}, {crate@red.at.x}, {stall.starts.bale}"))
        self.assertEqual(rules.says("R98"), "0.7 to 0.9 lb, 0.9 lb, 6.4 oz +/- 0.3, low pile carpet, false, 7 in, 3 in, 16.8 cm, 612.40 in, 3/8 in (deep) or 9 in (wide), none, 481.4 in, 20")
        self.assertIn("611.75 in", rules.says("R98", field="bolted"))

    def test_what_has_nothing_to_say(self):
        """Catches a record with no words that comes back as an empty text, or a name that is not there."""
        rules = self.rules()
        self.wrong(lambda: rules.says("crate"), "crate", "says")
        self.wrong(lambda: rules.says("crat"), "crate")
        self.assertEqual(rules.get("R91.says").value, rules.says("R91"))
        deep = self.rules(lambda d: d["places"]["barn"]["opening"].update(says="{bottom} up, {opening.depth} deep and {out} out, from the {from}."))
        self.assertEqual(deep.says("barn.opening"), "48 in up, 5 in deep and 20 in out, from the front.")


if __name__ == "__main__":
    unittest.main()
