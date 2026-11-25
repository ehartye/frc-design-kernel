"""Reading the nine files of a rules folder, the IDs in them and paths (RULES.md section 1)."""
import unittest
from pathlib import Path

from frc_design_kernel.errors import DesignError

from .rules_cases import FILES, small, written


class Files(unittest.TestCase):
    """read.read_files: the nine files as data."""

    def faults(self, files):
        from frc_design_kernel.rules import read
        return [str(f) for f in read.read_files(written(files))[1]]

    def one(self, files, *says):
        faults = self.faults(files)
        self.assertEqual(len(faults), 1, faults)
        for word in says:
            self.assertIn(word, faults[0])

    def test_nine_files(self):
        """Control: nine readable files give their data, in the order of RULES.md, and no fault."""
        from frc_design_kernel.rules import read
        data, faults = read.read_files(written(small(terms={"pin": {"says": "Held."}})))
        self.assertEqual((faults, list(data), data["terms"]), ([], FILES, {"pin": {"says": "Held."}}))

    def test_a_missing_file(self):
        """Catches a folder with a file left out, which would read as a game with no such rules."""
        files = small()
        del files["conduct"]
        self.one(files, "conduct.json", "does not exist")

    def test_a_missing_folder(self):
        """Catches a mistyped folder, with one plain message and not nine."""
        from frc_design_kernel.rules import read
        data, faults = read.read_files(Path("no") / "such")
        self.assertEqual((data, len(faults)), ({}, 1))
        self.assertIn("is not a folder", str(faults[0]))

    def test_bad_json(self):
        """Catches a missing comma, named by file and line."""
        self.one(small(clock='{"periods": {}\n "windows": {}}'), "clock.json line 2", "not valid JSON")

    def test_not_text(self):
        """Catches a file that is not UTF-8 text, or nested past reading, with a message and not a crash."""
        from frc_design_kernel.rules import read
        folder = written(small())
        (folder / "robot.json").write_bytes(b"\xff\xfe\x00")
        (folder / "terms.json").write_text("[" * 200000, encoding="utf-8")
        self.assertEqual([f.where.split()[0] for f in read.read_files(folder)[1]], ["robot.json", "terms.json"])

    def test_not_an_object(self):
        """Catches a file that holds a list, so that nothing in it could be found by name."""
        self.one(small(places="[]"), "places.json", "object")

    def test_a_field_written_twice(self):
        """Catches a duplicate key, of which JSON silently keeps the last: {"bank": 2, "bank": 3}."""
        self.one(small(clock='{"states": {"lit": {"bank": 2, "bank": 3}}}'), "clock.json states.lit", '"bank"', "twice")
        self.one(small(places='{"loft": {}, "loft": {}}'), "places.json", '"loft"', "twice")
        self.one(small(pieces='{"bale": {"list": [{"a": 1, "a": 1}]}}'), "pieces.json bale.list[0]", '"a"')

    def test_a_number_that_is_not_ordinary(self):
        """Catches infinity and NaN, which JSON readers let through, and 1e999, which turns into infinity."""
        for number in ["Infinity", "-Infinity", "NaN", "1e999"]:
            self.one(small(clock='{"states": {"lit": {"bank": %s}}}' % number), "clock.json states.lit.bank", "ordinary")
        self.one(small(clock='{"bank": %s}' % ("1" * 5000)), "clock.json")

    def test_a_folder_in_place_of_a_file(self):
        """Catches a crash where a file can not be opened."""
        from frc_design_kernel.rules import read
        folder = written({name: {} for name in FILES if name != "terms"})
        (folder / "terms.json").mkdir()
        self.assertEqual([f.where for f in read.read_files(folder)[1]], ["terms.json"])

    def test_every_fault_is_gathered(self):
        """Catches a reader that stops at the first bad file, so that a student mends them one run at a time."""
        files = small(clock="{", pieces="[]")
        del files["terms"]
        self.assertEqual(len(self.faults(files)), 3)


class Ids(unittest.TestCase):
    """read.gather: every record, by its ID, and paths into them."""

    def gather(self, **files):
        from frc_design_kernel.rules import read
        return read.gather("", small(**files))

    def one(self, *says, **files):
        faults = [str(f) for f in self.gather(**files)[1]]
        self.assertEqual(len(faults), 1, faults)
        for word in says:
            self.assertIn(word, faults[0])

    def test_records_in_the_order_written(self):
        """Catches a record that is lost, or that is given the wrong kind or the wrong place in a message."""
        book, faults = self.gather(field={"size": {"length": "9 in"}, "zones": {"yard": {}}, "tags": {"family": "36h11", "t1": {}}, "guardrail": {"height": "3 in"}},
                                   pieces={"bale": {}}, scoring={"total": {"bale": 1}, "judged": {"late": {}}},
                                   robot={"limits": {"reach": {}}, "parts": {"wire": {"about": {}, "main": {}}}, "rules": {"R1": {}}},
                                   game={"people": {"coach": {}, "together": [{}]}, "sources": {"manual": {}}, "accuracy": {"decimal": "1 in"}})
        self.assertEqual(faults, [])
        got = {(e.file, e.path): e.kind for e in book.entries if e.path}
        self.assertEqual(got, {("field", "size"): "size", ("field", "yard"): "zone", ("field", "tags"): "tags", ("field", "tags.t1"): "tag", ("field", "guardrail"): "guardrail",
                               ("pieces", "bale"): "piece", ("scoring", "total"): "total", ("scoring", "judged.late"): "judged",
                               ("robot", "limits.reach"): "limit", ("robot", "parts.wire.about"): "about", ("robot", "parts.wire.main"): "part", ("robot", "R1"): "rule",
                               ("game", "people.coach"): "person", ("game", "people.together[0]"): "together", ("game", "sources.manual"): "source", ("game", "accuracy"): "accuracy"})
        self.assertEqual(set(book.ids), {"yard", "bale", "R1"})
        self.assertEqual(next(e for e in book.entries if e.path == "tags.t1").where, "field.json tags.t1")

    def test_a_name_at_the_top_of_a_file(self):
        """Catches a name at the top of a file that RULES.md does not give, whatever it holds: a slip would lose a whole group."""
        self.one("field.json", '"pasages"', 'Did you mean "passages"', field={"pasages": {"arch": {}}})
        self.one("field.json", '"fence"', "guardrail", field={"fence": {"height": "3 in"}})
        self.one("clock.json", '"note"', "windows", clock={"note": "words"})
        self.one("game.json", '"src"', "sources", game={"src": "manual"})
        self.one("scoring.json", '"bonus"', "awards", scoring={"bonus": 3})
        self.one("robot.json", '"rule"', 'Did you mean "rules"', robot={"rule": {}})

    def test_the_other_files_hold_any_record(self):
        """Control: pieces, places, conduct and terms are records by ID, with no fixed names at the top."""
        for file in ("pieces", "places", "conduct", "terms"):
            book, faults = self.gather(**{file: {"anything": {}}})
            self.assertEqual((faults, list(book.ids)), ([], ["anything"]))

    def test_an_id_used_twice(self):
        """Catches one ID for two things, so that a path would mean either."""
        self.one('"yard"', "places.json", "field.json", field={"zones": {"yard": {}}}, places={"yard": {}})

    def test_an_id_that_begins_a_path(self):
        """Catches a record called size or limits, which a path could never reach."""
        for root in ("total", "guardrail", "accuracy", "parts"):
            self.one(f'"{root}"', "terms.json", terms={root: {}})

    def test_an_id_that_is_not_one(self):
        """Catches an ID with a space, a dash or a digit in front, which a path or a formula could not name."""
        for name in ["hay loft", "hay-loft", "2nd", "", "_x", "loé"]:
            self.one("letter", places={name: {}})
        self.one("letter", field={"tags": {"1": {}}})
        self.one("letter", robot={"parts": {"wire": {"8-4": {}}}})
        self.one("letter", robot={"parts": {"main wire": {}}})

    def test_a_record_that_is_not_an_object(self):
        """Catches a list or a number where a record or a group of records must be."""
        self.one("places.json loft", "object", places={"loft": 3})
        self.one("clock.json windows", "object", clock={"windows": []})
        self.one("robot.json parts.wire", "object", robot={"parts": {"wire": "6 AWG"}})
        self.one("robot.json limits", "object", robot={"limits": []})
        self.one("game.json people.together", "list", game={"people": {"together": {}}})

    def test_paths(self):
        """Catches a path that finds the wrong value: through a list, an object, a variant and one of several limits."""
        book, _ = self.gather(
            game={"variants": {"gate": ["low", "high"]}, "accuracy": {"angle": "1 deg"}}, field={"size": {"length": "9 in"}, "guardrail": {"gates": 2}, "tags": {"t1": {"at": ["1 in", "2 in"]}}},
            places={"stall": {"at": {"by": "gate", "low": ["1 in", {"is": "2 in", "of": "x"}], "high": ["3 in", "4 in"]}, "deep": {"is": "= size.length", "of": "x"}},
                    "loft": {"alliance": "each", "spots": {"ring": 2, "first": {"a": {"at": ["5 in"], "tall": "7 in"}}}, "deep": "8 in"}},
            robot={"limits": {"bumpers": {"low": "1 in", "gap": {"any": [{"deep": "at most 1 in"}, {"wide": "at most 9 in"}]}}}}, pieces={"bale": {"mass": "1 to 2 lb"}})
        for path, node in [("size.length", "9 in"), ("guardrail.gates", 2), ("accuracy.angle", "1 deg"), ("tags.t1.at.y", "2 in"), ("stall.at.x", "1 in"), ("stall.at.y.is", "2 in"), ("stall.deep", {"is": "= size.length", "of": "x"}),
                           ("limits.bumpers.low", "1 in"), ("limits.bumpers.gap.wide", "at most 9 in"), ("stall", book.ids["stall"].data), ("loft@red.deep", "8 in"),
                           ("loft@red.2.a.at.x", "5 in"), ("loft@blue.1.a.tall", "7 in"), ("loft@red.1.a.deep", "8 in")]:
            found = book.look(path)
            self.assertEqual((found.node, found.end), (node, None), path)
        self.assertEqual(book.look("stall.at.y", {"gate": "high"}).node, "4 in")
        self.assertEqual((book.look("bale.mass.low").node, book.look("bale.mass.low").end), ("1 to 2 lb", "low"))
        found = book.look("loft@red.2.a.at.x")
        self.assertEqual((found.entry.path, found.alliance, found.spot), ("loft", "red", "2.a"))

    def test_paths_through_a_value_that_needs_more(self):
        """Catches a path that stops at an object with is, where the number or the list that it stands for is meant."""
        book, _ = self.gather(pieces={"bale": {"mass": {"is": "1 to 2 lb", "src": "manual 5"}, "size": {"is": ["3 in", "4 in"], "src": "manual 5"}}})
        self.assertEqual(book.look("bale.size.y").node, "4 in")
        found = book.look("bale.mass.high")
        self.assertEqual((found.node, found.end), ({"is": "1 to 2 lb", "src": "manual 5"}, "high"))
        self.assertEqual(book.look("bale.mass.src").node, "manual 5")

    def test_paths_that_lead_nowhere(self):
        """Catches a path with a slip in it, and says which step and what there is."""
        book, _ = self.gather(field={"size": {"length": "9 in"}, "tags": {"t1": {"at": ["1 in", "2 in"]}}}, places={"stall": {"at": ["1 in"]}, "loft": {"alliance": "each"}})
        for path, says in [("stal.at.x", 'Did you mean "stall"'), ("stall.att", 'Did you mean "at"'), ("stall.at.z", '"z"'), ("tags.t1.at.xy", '"xy"'), ("size.lenght", 'Did you mean "length"'), ("stall.at.x.deep", "deep"),
                           ("stall@red.at.x", "each"), ("loft@green", "green"), ("", "Known"), ("stall.at.", "stall.at.")]:
            with self.assertRaises(DesignError) as caught:
                book.look(path)
            self.assertIn(says, str(caught.exception))

    def test_spot_names(self):
        """Catches spots numbered from 0, pairs named the wrong way round, and names that are not used."""
        from frc_design_kernel.rules import read
        pair = {"a": {"at": []}, "b": {"at": []}}
        self.assertEqual(read.spot_names({"near": {"at": []}, "far": {"at": []}}), ["near", "far"])
        self.assertEqual(read.spot_names({"row": 3, "first": {"at": []}}), ["1", "2", "3"])
        self.assertEqual(read.spot_names({"ring": 2, "first": pair}), ["1.a", "1.b", "2.a", "2.b"])
        self.assertEqual(read.spot_names({"ring": 2, "names": ["near", "far"], "first": pair}), ["near.a", "near.b", "far.a", "far.b"])
        for nothing in [None, [], {"row": "= 2"}, {"ring": True}, {"row": 10 ** 9}]:
            self.assertEqual(read.spot_names(nothing), [])


if __name__ == "__main__":
    unittest.main()
