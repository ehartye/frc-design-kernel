"""Read a design source, its top file and any subsystem files, into a checked, plain Design."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ..errors import DesignError
from . import checks, schema, subsystems
from .expand import expand

CUSTOM_FOLDER = "custom"


@dataclass(frozen=True)
class Design:
    """A design source after checking: plain data with every number worked out and every "each" written out."""
    path: Path
    data: dict
    sha256: str
    custom_used: dict    # {custom code name: [names of the solids or trials that use it]}
    files: tuple         # every source file read: the top file, then each subsystem file in the order listed
    field: Path | None   # the folder of field models the caller gave, for the parts named by "field"

    @property
    def folder(self):
        return self.path.parent

    def custom_file(self, name):
        return self.folder / CUSTOM_FOLDER / f"{name}.py"

    def solids(self, fixtures=False):
        return self.data["fixtures" if fixtures else "solids"]


    def part_file(self, part):
        """The file a part is read from: in the field folder for a field part, else from the design's own folder."""
        return self.field / part["field"] if "field" in part else self.folder / part["file"]


def not_a_number(text):
    raise DesignError("", f"{text} is not an ordinary number", "Use a finite number")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=not_a_number)
    except FileNotFoundError:
        raise DesignError(str(path), "the design source file does not exist", "Check the path") from None
    except json.JSONDecodeError as problem:
        raise DesignError(f"{path.name} line {problem.lineno}", f"is not valid JSON ({problem.msg})", "Look for a missing comma, quote or bracket near that line") from None


def check_field(design, name, where):
    """A field part is a plain file name in the folder of field models the caller gave; nothing else is reachable."""
    if Path(name).name != name or any(mark in name for mark in "/\\:") or name in (".", ".."):
        raise DesignError(where, f'the field file "{name}" is not a plain file name', "Name a file of the field folder itself, with no folders in it")
    if design.field is None:
        raise DesignError(where, f'the part is the field file "{name}", and no field folder was given',
                          "Give the folder of field models: load(path, field=FOLDER), or --field FOLDER on the command line")
    if not design.field.is_dir():
        raise DesignError(where, f"the field folder {design.field} does not exist", "Give the folder that holds the field models")
    target = (design.field / name).resolve()
    if target.parent != design.field.resolve():
        raise DesignError(where, f'the field file "{name}" leads outside the field folder', "Keep the field model itself in the field folder")
    if not target.is_file():
        raise DesignError(where, f'the field file "{name}" does not exist', f"Put it in the field folder, {design.field}")


def check_files(design):
    """Every file the source names must exist beside it, inside its folder; or, for a field part, in the field folder."""
    for section in ("solids", "fixtures"):
        for i, solid in enumerate(design.data[section]):
            if "part" not in solid:
                continue
            where = schema.step(section, i, solid)
            if "field" in solid["part"]:
                check_field(design, solid["part"]["field"], where)
                continue
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


def read_subsystems(raw, folder):
    """[(file as listed, its source, its path)] for each subsystem file the top file lists, each read once from inside the folder."""
    subsystems.check_top(raw)
    part_schema, parts, seen = schema.load_schema("subsystem"), [], set()
    for i, entry in enumerate(raw.get("subsystems", [])):
        where, file = f"subsystems[{i}]", entry["file"]
        target = (folder / file).resolve()
        if not target.is_relative_to(folder.resolve()):
            raise DesignError(where, f'the subsystem file "{file}" is outside the design folder', "Keep subsystem files beside the design source")
        if target in seen:
            raise DesignError(where, f'the subsystem file "{file}" is listed twice', "List each subsystem file once")
        if not target.is_file():
            raise DesignError(where, f'the subsystem file "{file}" does not exist', "Check the path; it is relative to the design source")
        seen.add(target)
        body = read_json(target)
        schema.check(body, part_schema, where=f'subsystem "{file}"')
        parts.append((file, body, folder / file))
    return parts


def load(path, parameters=None, field=None):
    """Read, check and expand the design source at path. Raises DesignError for the first problem found.

    parameters replaces the values of named parameters, so a variant of the design can be built without editing
    the file. Everything worked out from those parameters follows. A top file that lists subsystem files is merged
    with them into one design; which file an entry is written in changes nothing in the result. field is the folder
    of field models, for parts named by "field"; a design with none needs no folder.
    """
    path = Path(path)
    raw = read_json(path)
    schema.check(raw, schema.load_schema())
    parts = read_subsystems(raw, path.parent)
    read_trials(raw, path.parent)
    data, origins = expand(raw, parameters, [(file, body) for file, body, _ in parts], top=path.name)
    subsystems.check_present(data, parts)
    files = (path, *(target for _, _, target in parts))
    sha256 = hashlib.sha256(b"".join(file.read_bytes() for file in files)).hexdigest()
    with subsystems.attributed(origins):
        design = Design(path=path, data=data, sha256=sha256, custom_used=checks.check_all(data), files=files,
                        field=None if field is None else Path(field))
        check_files(design)
    subsystems.settle(data)
    return design
