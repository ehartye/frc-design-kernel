"""Shared help for the rules tests: the invented example as data to break, and rules folders written to disk."""
import functools
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["game", "clock", "field", "pieces", "places", "scoring", "conduct", "robot", "terms"]
EXAMPLE = ROOT / "examples" / "rules" / "2031-03-14"
_FOLDERS = []    # temporary folders stay until the test run ends


def written(files):
    """A temporary folder holding {file name: data, or text to write as it is}."""
    keep = tempfile.TemporaryDirectory()
    _FOLDERS.append(keep)
    for name, data in files.items():
        text = data if isinstance(data, str) else json.dumps(data)
        (Path(keep.name) / f"{name}.json").write_text(text, encoding="utf-8")
    return Path(keep.name)


def small(**changes):
    """The least that a rules folder can hold, with some files replaced."""
    return {**{name: {} for name in FILES}, **changes}


@functools.lru_cache(maxsize=None)
def _text(name):
    return (EXAMPLE / f"{name}.json").read_text(encoding="utf-8")


def example():
    """The invented example as fresh data, {file name: data}, to break one thing in."""
    return {name: json.loads(_text(name)) for name in FILES}


def paths(node, steps=()):
    """The steps to every node of some data, but what was and what differs; of a list, as far as a path goes."""
    if steps:
        yield list(steps)
    for name, inner in node.items() if isinstance(node, dict) else zip("xyz", node) if isinstance(node, list) else ():
        if name not in ("was", "differs", "by", "unknown"):
            yield from paths(inner, (*steps, name))


def rename(data, old, new):
    """Give one field of an object another name, as a slip of the keyboard would."""
    data[new] = data.pop(old)


class Checked(unittest.TestCase):
    """Help for tests that break one thing in the example and look at the fault."""

    def faults(self, change=None):
        from frc_design_kernel.rules import fields, read
        data = example()
        if change:
            change(data)
        book, faults = read.gather("", data)
        return [str(f) for f in faults + fields.check(book)]

    def refused(self, change, *says):
        """The change makes exactly one fault, and it says all of this. The example without the change has none."""
        faults = self.faults(change)
        self.assertEqual(len(faults), 1, faults)
        for word in says:
            self.assertIn(word, faults[0])

    def accepted(self, change):
        self.assertEqual(self.faults(change), [])


@functools.lru_cache(maxsize=1)
def as_it_is():
    """The Rules of the example, read once: nothing that is asked of them changes them."""
    from frc_design_kernel.rules.rules import load_rules
    return load_rules(EXAMPLE)


class Derived(unittest.TestCase):
    """Help for tests that ask the example, as it is or with one thing changed, for what is worked out."""

    def rules(self, change=None):
        from frc_design_kernel.rules.rules import load_rules
        if not change:
            return as_it_is()
        data = example()
        change(data)
        return load_rules(written(data))

    def is_(self, value, kind, number, places=6):
        self.assertEqual(value.kind, kind)
        self.assertAlmostEqual(value.value, number, places=places)

    def wrong(self, does, *says):
        from frc_design_kernel.errors import DesignError
        with self.assertRaises(DesignError) as caught:
            does()
        for word in says:
            self.assertIn(word, str(caught.exception))
