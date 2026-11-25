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
