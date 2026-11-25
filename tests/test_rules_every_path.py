"""rules get of every path of the example: none ends in an error of Python."""
import json
import unittest
from unittest import mock

from frc_design_kernel.errors import DesignError

from .rules_cases import as_it_is, example, paths, written


class EveryPath(unittest.TestCase):
    """rules get of every path: an answer, or a DesignError that says what to ask; in text and as plain data."""

    def every(self, rules):
        """(how many answers, how many refusals, the ones that say nothing to do)."""
        from frc_design_kernel.rules import answers, fields, read
        answered, refused, empty = 0, 0, []
        for entry in rules.book.entries:
            if not entry.path or "[" in entry.path:
                continue
            lacks = {name for name in (fields.spec_for(entry).known if fields.spec_for(entry) else ()) if name not in entry.data} | {"spots", "outline", "at", "is", "low"}
            spots = read.spot_names(entry.data.get("spots"))
            some = [spot for spot in spots if spots.index(spot) in (0, len(spots) - 1)]
            heads = [entry.path, *([f"{entry.path}@red"] if entry.data.get("alliance") == "each" else []), *(f"{entry.path}.spots.{spot}" for spot in some)]
            steps = [tail for path in paths(entry.data) for tail in ([".".join(path)] if "[" not in ".".join(path) else [])] + sorted(lacks)
            asked = [(f"{head}.{tail}", more) for head in heads for tail in ("", *steps) for more in ({}, {"alliance": "red"})] + [(f"{entry.path}.{tail}", {"spot": spot, "alliance": "red"}) for spot in some for tail in steps]
            for path, more in asked:
                try:
                    got = rules.get(path.removesuffix("."), **more)
                    json.dumps(answers.plain(rules, got))
                    self.assertTrue(answers.lines(rules, path, got))
                    answered += 1
                except DesignError as problem:
                    refused += 1
                    if not problem.fix:
                        empty.append((path, more))
        return answered, refused, empty

    def test_no_python_error(self):
        """Catches a path of a season without faults that ends in an error of Python, or in a refusal that says nothing to do."""
        rules = as_it_is()
        answered, refused, empty = self.every(rules)
        self.assertEqual(empty, [])
        self.assertGreater(min(answered, refused), 2000)

    def test_a_path_that_ends_in_an_error_is_caught(self):
        """Control: an answer that cannot be told ends the test of every path."""
        from frc_design_kernel.rules import worker
        rules = as_it_is()
        with mock.patch.object(worker.Worker, "_at", lambda self, place, rest: rest[99]), self.assertRaises(IndexError):
            self.every(type(rules)(rules.book))

    def test_what_is_not_there(self):
        """Catches a zone with no outline, a record with no spots, or a property of a record that is called is, that ends in an error."""
        rules = as_it_is()
        for path, more, says in [("stands.outline", {}, "outline"), ("crate.spots", {"alliance": "red"}, "spots"), ("yard@red.spots.near", {}, "spots"), ("yard.spots", {}, "spots"), ("pond.spots", {"alliance": "red"}, "spots")]:
            with self.assertRaises(DesignError) as caught:
                rules.get(path, **more)
            self.assertIn(f'"{says}"', str(caught.exception), path)
        from frc_design_kernel.rules.rules import load_rules
        data = example()
        data["field"]["zones"]["pond"].update({"is": "3 in"})
        data["places"]["stall"]["spots"]["near"].update({"is": "3 in"})
        rules = load_rules(written(data))
        for path in ("pond.is", "stall.spots.near.is", "stall@red.near.is"):
            with self.assertRaises(DesignError) as caught:
                rules.get(path)
            self.assertIn("another name", caught.exception.fix, path)


if __name__ == "__main__":
    unittest.main()
