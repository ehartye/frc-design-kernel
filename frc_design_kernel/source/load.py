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
    custom_used: dict    # {custom shape name: [names of the solids that use it]}

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


def load(path):
    """Read, check and expand the design source at path. Raises DesignError for the first problem found."""
    path = Path(path)
    raw = read_json(path)
    schema.check(raw, schema.load_schema())
    data = expand(raw)
    design = Design(path=path, data=data, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), custom_used=checks.check_all(data))
    check_files(design)
    return design
