"""How many pieces start where, what each device may run, and every record by name, for the example."""
import unittest

from .rules_cases import Derived

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
        self.wrong(lambda: rules.runs("riens"), "reins")
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

    def test_the_variant(self):
        """Catches records that are always of the first variant."""
        rules = self.rules()
        at = {v: {r.name: r.at for r in rules.records("field", field=v)}["crate@red"][0] / IN for v in ("welded", "bolted")}
        self.assertAlmostEqual(at["welded"], 481.4)
        self.assertAlmostEqual(at["bolted"], 480.75)


if __name__ == "__main__":
    unittest.main()
