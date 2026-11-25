"""How many pieces start where, what each device may run, and every record by name, for the example."""
import unittest

from .rules_cases import Derived, example, written

IN = 25.4


class Starts(Derived):
    """rules.starts: the pieces add up."""

    def test_the_pieces_add_up(self):
        """Catches a count that is not doubled for two alliances, or not made for each spot, or a half that is not left over."""
        rules = self.rules()
        self.assertEqual(rules.starts("bale"), {"robot_preload@blue": 3, "robot_preload@red": 3, "near_bales@blue": 4, "near_bales@red": 4, "centre_bales": 6, "stall@blue": 20, "stall@red": 20})
        self.assertEqual(rules.starts("pumpkin"), {"patch@blue": 5, "patch@red": 5, "vine": 2})
        self.assertEqual(rules.starts("hoop"), {"hooks@blue": 2, "hooks@red": 2, "spare_hoops": 4})
        for piece, total in [("bale", 60), ("pumpkin", 12), ("hoop", 8)]:
            self.assertEqual(sum(rules.starts(piece).values()), total)
        self.is_(rules.get("stall.starts.bale"), "number", 20)
        self.assertEqual((rules.get("stall.starts.bale").src, rules.get("stall.starts.bale").printed), ("manual 3.8", "20"))
        self.assertIsNone(self.rules(lambda d: d["places"]["stall"].pop("src")).get("stall.starts.bale").src)
        self.wrong(lambda: rules.starts("bail"), 'Did you mean "bale"')

    def test_what_is_left_over_follows(self):
        """Catches what is left over that is written down and does not follow the total, a spot or a variant."""
        self.assertEqual(self.rules(lambda d: d["scoring"]["total"].update(bale=70)).starts("bale")["stall@red"], 25)
        self.assertEqual(self.rules(lambda d: d["places"]["near_bales"]["spots"].update(row=5)).starts("bale")["stall@red"], 19)
        more = self.rules(lambda d: d["scoring"]["total"].update(bale={"by": "event", "regional": 60, "championship": 80}))
        self.assertEqual((more.starts("bale")["stall@blue"], more.starts("bale", event="championship")["stall@blue"]), (20, 30))
        one = self.rules(lambda d: (d["places"]["patch"].pop("alliance"), d["scoring"]["total"].update(pumpkin=13)))
        self.assertEqual(one.starts("pumpkin"), {"patch": 11, "vine": 2})

    def test_a_count_for_each_alliance(self):
        """Catches a count for each alliance, at a place that neither owns, that is taken for the whole."""
        rules = self.rules(lambda d: d["places"]["vine"]["starts"].update(pumpkin={"each": "alliance", "is": 2}))
        self.assertEqual(rules.starts("pumpkin"), {"patch@blue": 4, "patch@red": 4, "vine": 4})

    def test_a_formula_of_what_is_left_over(self):
        """Catches a formula that cannot name what is left over."""
        self.is_(self.rules(lambda d: d["places"]["stall"]["holds"].update(bale="= stall.starts.bale * 2")).get("stall.holds.bale"), "number", 40)


class Each(Derived):
    """What a number is for each of, and a cap's times: they go with the Value wherever it goes."""

    CAP = {"each": "alliance", "is": 2, "when": ["auto", "not lit"]}

    def capped(self):
        return self.rules(lambda d: d["scoring"]["awards"]["hang"].update(most=self.CAP))

    def test_get(self):
        """Catches a count for each spot, or a cap at some times, that comes back as if it were for the whole, always."""
        rules = self.rules()
        one = rules.get("near_bales.starts.bale")
        self.assertEqual((one.kind, one.value, one.printed, one.each, one.when), ("number", 1, "1", "spot", ()))
        self.assertEqual((rules.get("hang.most").value, rules.get("hang.most").each), (2, "alliance"))
        self.assertEqual((rules.get("total.bale").each, rules.get("stall.starts.bale").each, rules.get("barn.out").each), (None, None, None))
        cap = self.capped().get("hang.most")
        self.assertEqual([(m.name, m.kind, m.whose, m.negated) for m in cap.when], [("auto", "period", None, False), ("lit", "state", "my", True)])
        by = self.rules(lambda d: d["scoring"]["awards"]["hang"].update(most={**self.CAP, "is": {"by": "event", "regional": 2, "championship": {"is": 3, "each": "stall"}}}))
        self.assertEqual([(v.value, v.each, len(v.when)) for v in (by.get("hang.most"), by.get("hang.most", event="championship"))], [(2, "alliance", 2), (3, "stall", 2)])

    def test_says(self):
        """Catches words in which a count for each spot reads as the count of all."""
        rules = self.rules(lambda d: d["robot"]["rules"]["R98"].update(says="{near_bales.starts.bale}; {hang.most}; {total.bale}; {limits.bumpers.frame_gap}; {cellar.holds.bale}") or d["places"]["cellar"]["holds"].update(
            bale={"is": "at most 8", "each": "barn"}))
        self.assertEqual(rules.says("R98"), "1 each spot; 2 each alliance; 60; 3/8 in (deep) or 9 in (wide); 8 each barn")

    def test_says_when(self):
        """Catches words in which a cap at some times reads as one for always, or one of several limits as one for the whole."""
        def change(d):
            d["robot"]["rules"]["R98"].update(says="{hang.most}; {park.most}; {cellar.either}")
            d["scoring"]["awards"]["hang"].update(most=self.CAP)
            d["scoring"]["awards"]["park"].update(most={"is": "at most 3", "when": ["endgame"]})
            d["places"]["cellar"].update(either={"any": [{"deep": {"is": "at most 1 in", "each": "spot"}}, {"wide": "2 in"}]})
        self.assertEqual(self.rules(change).says("R98"), "2 each alliance when auto and not my lit; 3 when endgame; 1 in each spot (deep) or 2 in (wide)")

    def test_a_formula(self):
        """Catches a formula that takes a count for each spot, or a cap at some times, for the whole."""
        from frc_design_kernel.rules.rules import faults
        data = lambda text, **more: (lambda d: d["places"]["cellar"]["holds"].update(bale=text) or d["scoring"]["awards"]["hang"].update(**more))
        for change, name in [(data("= near_bales.starts.bale * 4"), "near_bales.starts.bale"), (data("= hang.most"), "hang.most"), (data("= hang.most * 2", most={"is": 2, "when": ["auto"]}), "hang.most")]:
            files = example()
            change(files)
            found = faults(written(files))
            self.assertEqual([f.where for f in found], ["places.json cellar.holds.bale"], found)
            for text in (name, "for the whole", "rules.starts"):
                self.assertIn(text, str(found[0]))
        self.is_(self.rules(data("= total.bale / 10 + hang.most", most={"is": 2})).get("cellar.holds.bale"), "number", 8)

    def test_starts_go_on(self):
        """Catches what is there at the start that is no longer all of it."""
        self.assertEqual(self.rules().starts("bale")["near_bales@red"], 4)


class Runs(Derived):
    """rules.runs: the loads that one device may run."""

    def runs(self, rules, device):
        return {path: value.value if value.kind == "number" else value.kind for path, value in rules.runs(device).items()}

    def test_what_each_kind_of_device_may_run(self):
        """Catches a load on a kind of device that may not run it, or a number of one kind that is taken for another's."""
        rules = self.rules()
        self.assertEqual(self.runs(rules, "reins"), {"parts.motors.mule": 2, "parts.motors.latch": "any", "parts.loads.lantern": "any"})
        self.assertEqual(self.runs(rules, "whistle"), {"parts.motors.mule": 1, "parts.motors.latch": "any", "parts.loads.lantern": "any"})
        self.assertEqual(self.runs(rules, "bellows"), {"parts.motors.latch": 1, "parts.loads.lantern": "any"})
        self.assertEqual(rules.runs("bellows")["parts.motors.latch"].of, "each channel")

    def test_only_for(self):
        """Catches a device for some loads only that runs everything its kind may, or a controller of one motor that runs others."""
        rules = self.rules()
        self.assertEqual(self.runs(rules, "switch"), {"parts.loads.lantern": "any"})
        self.assertEqual(self.runs(rules, "saddle"), {"parts.motors.pony": 1})
        free = self.rules(lambda d: d["robot"]["parts"]["relays"]["switch"].pop("only_for"))
        self.assertEqual(self.runs(free, "switch"), self.runs(free, "whistle"))

    def test_what_is_no_device(self):
        """Catches something that runs nothing and comes back as if it might run nothing yet, and an ID in two groups."""
        rules = self.rules(lambda d: d["robot"]["parts"]["valves"].update(reins={"name": "Reins", "kind": "relay", "src": "manual R97"}))
        self.wrong(lambda: rules.runs("panel"), "panel", "kind")
        self.wrong(lambda: rules.runs("riens"), 'Did you mean "reins"')
        self.wrong(lambda: rules.runs("reins"), "controllers.reins", "valves.reins")
        self.assertEqual(self.runs(rules, "valves.reins"), self.runs(rules, "parts.relays.whistle"))


class Records(Derived):
    """rules.records: every record of a file, with red's and every spot."""

    def test_the_names(self):
        """Catches a record that is left out, a red copy or a spot that is not made, or an order that is not the file's."""
        names = [r.name for r in self.rules().records("places")]
        self.assertEqual(names[:12], ["robot_preload@blue", "robot_preload@red", "near_bales@blue", *[f"near_bales@blue.{i}" for i in "1234"], "near_bales@red", *[f"near_bales@red.{i}" for i in "1234"]])
        self.assertEqual(names[12:19], ["centre_bales", *[f"centre_bales.spots.{i}" for i in "abcdef"]])
        self.assertIn("rack@red.3.b", names)
        self.assertEqual([n for n in names if n.startswith("hooks")], ["hooks@blue", "hooks@blue.left", "hooks@blue.right", "hooks@red", "hooks@red.left", "hooks@red.right"])
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(sum(n.startswith("rack") for n in names), 2 * 13)

    def test_every_file(self):
        """Catches a file whose records are not given, or a limit, a part or a tag that is not one."""
        rules = self.rules()
        for file in ["game", "clock", "field", "pieces", "places", "scoring", "conduct", "robot", "terms"]:
            written = [e.path for e in rules.book.entries if e.file == file and e.path]
            self.assertEqual(list(dict.fromkeys(r.entry.path for r in rules.records(file))), written, file)
        self.assertIn("limits.reach", [r.name for r in rules.records("robot")])
        self.assertIn("parts.motors.mule", [r.name for r in rules.records("robot")])
        self.assertIn("tags.t3", [r.name for r in rules.records("field")])
        self.wrong(lambda: rules.records("place"), 'Did you mean "places"')

    def test_where_each_stands(self):
        """Catches a record that stands at another place than its path says, or a facing that is not turned."""
        rules = self.rules()
        found = {r.name: r for file in ("field", "places") for r in rules.records(file)}
        self.assertEqual([round(n / IN, 4) for n in found["hooks@red.left"].at], [592.4, 200])
        self.assertEqual(found["hooks@red.left"].faces, 135)
        self.assertEqual([round(n / IN, 4) for n in found["tags.t3"].at], [150, 12, 40])
        self.assertEqual(found["fold@red"].outline, rules.outline("fold", "red"))
        self.assertEqual([[round(n / IN, 4) for n in end] for end in found["gate_line@red"].ends], [[558.4, 300], [558.4, 0]])
        self.assertEqual((found["rack@blue"].at, found["cellar@red"].at, found["stands"].outline), (None, None, None))
        self.assertEqual((found["rack@red.3.b"].alliance, found["rack@red.3.b"].spot, found["pond"].alliance), ("red", "3.b", None))

    def test_every_place_of_the_example(self):
        """Catches a record with a position that is not placed, for an alliance or a spot: each name is a path to the same."""
        rules = self.rules()
        many = 0
        for file in ("field", "places"):
            for r in rules.records(file):
                if r.at is not None:
                    self.assertEqual([v.value for v in rules.get(f"{r.name}.at")], list(r.at), r.name)
                    self.assertTrue(-1 <= r.at[0] <= 612.40 * IN + 1 and -1 <= r.at[1] <= 300 * IN + 1, r.name)
                    many += 1
        self.assertEqual(many, 49 + 58)    # of the field: zones 7, solids 19, passages 7, hangs 12 and tags 4; of the places: 58

    def test_no_place_no_facing(self):
        """Catches a record that stands nowhere, or at its spots only, and that looks somewhere all the same."""
        found = {r.name: r for file in ("field", "places") for r in self.rules().records(file)}
        self.assertEqual([found[name].faces for name in ("lane@blue", "lane@red", "rack@red", "centre", "stands", "cellar@blue")], [None] * 6)
        self.assertEqual([found[name].faces for name in ("yard@blue", "yard@red", "rack@red.4.b")], [0, 180, 180])

    def test_copies(self):
        """Catches an asker who changes what is given, and with it the rules that the next one is given."""
        rules = self.rules(lambda d: None)      # its own, as a failure here would change it for other tests
        found = {r.name: r for r in rules.records("field")}
        found["yard@red"].data["deep"] = found["yard@blue"].entry.data["wide"] = "1 in"
        found["yard@blue"].outline.clear()
        rules.conditions("G90.must_not")[0].what.entry.data["deep"] = "1 in"
        rules.when("G95.when")[1].entry.data["last"] = "1 s"
        rules.points("bale_in_barn")[0].when[0].entry.data["lasts"] = "1 s"
        self.assertEqual([rules.book.ids["yard"].data[name] for name in ("deep", "wide")], ["54 in", "21 in"])
        self.assertEqual((rules.book.ids["endgame"].data["last"], rules.book.ids["auto"].data["lasts"]), ("25 s", "12 s"))
        again = {r.name: r for r in rules.records("field")}
        self.assertEqual((again["yard@red"].data["deep"], again["yard@blue"].entry.data["wide"], len(again["yard@blue"].outline)), ("54 in", "21 in", 4))

    def test_the_variant(self):
        """Catches records that are always of the first variant."""
        rules = self.rules()
        at = {v: {r.name: r.at for r in rules.records("field", field=v)}["crate@red"][0] / IN for v in ("welded", "bolted")}
        self.assertAlmostEqual(at["welded"], 481.4)
        self.assertAlmostEqual(at["bolted"], 480.75)


if __name__ == "__main__":
    unittest.main()
