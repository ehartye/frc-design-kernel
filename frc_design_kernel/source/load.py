"""Read a design source file into a checked, plain Design."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..errors import DesignError
from . import checks, schema
from .expand import expand

CUSTOM_FOLDER = "custom"


@dataclass(frozen=True)
class Design:
    """A design source after checking: plain data with every number worked out and every "each" written out."""
    path: Path
    data: dict
    sha256: str
    custom_used: dict    # {custom code name: [names of the solids or trials that use it]}
    raw: dict            # the source as written (trial files read in), for asking which parameters something used

    @property
    def folder(self):
        return self.path.parent

    def custom_file(self, name):
        return self.folder / CUSTOM_FOLDER / f"{name}.py"

    def solids(self, fixtures=False):
        return self.data["fixtures" if fixtures else "solids"]


def not_a_number(text):
    raise DesignError("", f"{text} is not an ordinary number", "Use a finite number")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=not_a_number)
    except FileNotFoundError:
        raise DesignError(str(path), "the design source file does not exist", "Check the path") from None
    except json.JSONDecodeError as problem:
        raise DesignError(f"{path.name} line {problem.lineno}", f"is not valid JSON ({problem.msg})", "Look for a missing comma, quote or bracket near that line") from None


def check_files(design):
    """Every file the source names must exist beside it, inside its folder."""
    for section in ("solids", "fixtures"):
        for i, solid in enumerate(design.data[section]):
            if "part" not in solid:
                continue
            where = schema.step(section, i, solid)
            target = (design.folder / solid["part"]["file"]).resolve()
            if not target.is_relative_to(design.folder.resolve()):
                raise DesignError(where, f'the part file "{solid["part"]["file"]}" is outside the design folder', "Keep part files beside the design source")
            if not target.is_file():
                raise DesignError(where, f'the part file "{solid["part"]["file"]}" does not exist', "Check the path; it is relative to the design source")
    for name in design.custom_used:
        if not design.custom_file(name).is_file():
            raise DesignError(f'custom "{name}"', f"its code file {CUSTOM_FOLDER}/{name}.py does not exist", f"Create {CUSTOM_FOLDER}/{name}.py beside the design source, with a build(parameters) function")


def read_trials(raw, folder):
    """Each trial as its own definition: one written in the source, or one in a file the source names."""
    trial_schema = schema.load_schema("trial")
    for name, entry in raw.get("trials", {}).items():
        where = f'trials "{name}"'
        if set(entry) == {"file"}:
            target = (folder / str(entry["file"])).resolve()
            if not target.is_relative_to(folder.resolve()):
                raise DesignError(where, f'the trial file "{entry["file"]}" is outside the design folder', "Keep trial files beside the design source")
            raw["trials"][name] = entry = read_json(target)
        schema.check(entry, trial_schema, where=where)


def load(path, parameters=None):
    """Read, check and expand the design source at path. Raises DesignError for the first problem found.

    parameters replaces the values of named parameters, so a variant of the design can be built without editing
    the file. Everything worked out from those parameters follows.
    """
    path = Path(path)
    raw = read_json(path)
    schema.check(raw, schema.load_schema())
    read_trials(raw, path.parent)
    data = expand(raw, parameters)
    design = Design(path=path, data=data, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), custom_used=checks.check_all(data), raw=raw)
    check_files(design)
    return design
