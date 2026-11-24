"""Shared test helpers: an invented minimal design and a way to load an edited copy of it."""
import copy
import json
import tempfile
from pathlib import Path

from frc_design_kernel.source.load import load

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "lifter" / "design.json"

MINIMAL = {
    "schema": "frc-design-kernel/design@1",
    "name": "Test block",
    "units": {"length": "mm", "mass": "kg"},
    "parameters": {"tall": 100},
    "groups": {"base": {"role": "structure"}, "slide": {"role": "mechanism", "carriedBy": "base"}},
    "solids": [
        {"name": "block", "group": "base", "massKg": 1.0,
         "shape": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [50, 40, "=tall"]}},
        {"name": "runner", "group": "slide", "densityKgM3": 2700,
         "shape": {"kind": "box", "fromMm": [0, 0, "=tall"], "toMm": [50, 40, "=tall + 10"]}},
    ],
    "poses": {"in": {}, "out": {"slide": [{"kind": "translation", "travelMm": [80, 0, 0]}]}},
    "motions": {"extend": {"by": "hand", "from": "in", "to": "out", "moves": {"slide": [{"kind": "translation", "travelMm": [80, 0, 0]}]}}},
}


def edited(change=None):
    """A deep copy of MINIMAL after change(copy) has edited it."""
    data = copy.deepcopy(MINIMAL)
    if change:
        change(data)
    return data


_FOLDERS = []    # temporary folders stay until the test run ends, because a build reads files beside the source


def load_data(data, files=None):
    """Load a design given as a dict, written to a temporary folder with any extra files {relative path: text}."""
    keep = tempfile.TemporaryDirectory()
    _FOLDERS.append(keep)
    for name, text in (files or {}).items():
        target = Path(keep.name) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    path = Path(keep.name) / "design.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return load(path)
