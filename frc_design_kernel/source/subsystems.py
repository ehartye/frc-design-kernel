"""Subsystem files: what the top file keeps, what each subsystem file holds, and how a problem names its file.

A top file may list subsystem files. Each holds its own subsystem's entries; the top file keeps the entries for the
whole design. They are merged on load (in expand), so nothing measured depends on which file an entry is in.
"""
import json
import re
from contextlib import contextmanager

from ..errors import DesignError

SECTIONS = ("groups", "solids", "mounts", "contacts", "drives", "motions", "poses", "adjustments", "interactions", "extraMass")
UNORDERED = ("mounts", "contacts", "extraMass")      # lists whose order means nothing, kept in one fixed order
PLACE = re.compile(r'^(?P<section>\w+)(?:\[(?P<index>\d+)\]| "(?P<key>[^"]*)")(?P<rest>.*)$')


def check_top(raw):
    """A top file without subsystem files holds the groups and solids itself; one with them keeps no subsystem entries."""
    if "subsystems" not in raw:
        for key in ("groups", "solids"):
            if key not in raw:
                raise DesignError("", f'is missing "{key}"', f'Add "{key}", or list "subsystems" files that hold them')
        return
    for key in SECTIONS:
        if key in raw:
            raise DesignError(key, f'a design that lists "subsystems" keeps its {key} in the subsystem files',
                              f'Move "{key}" into the subsystem file each entry belongs to')


def check_present(data, parts):
    """The subsystem files together hold at least one group and one solid."""
    for key in ("groups", "solids"):
        if parts and not data[key]:
            raise DesignError("subsystems", f'no subsystem file holds any "{key}"', f'Add "{key}" to the subsystem file they belong to')


def merged(raw, parts):
    """The top file with every subsystem file's sections joined in, as written: for asking which parameters something used."""
    out = dict(raw)
    for _, body, _ in parts:
        for key in SECTIONS:
            if key in body:
                out[key] = out.get(key, []) + body[key] if isinstance(body[key], list) else {**out.get(key, {}), **body[key]}
    return out


def placed(problem, origins):
    """The same problem, its place given in the subsystem file that holds the entry, when one does."""
    found = PLACE.match(problem.where or "")
    held = origins.get(found["section"]) if found else None
    if not held:
        return problem
    if found["index"] is not None:
        index = int(found["index"])
        if index >= len(held) or held[index][0] is None:
            return problem
        file, local = held[index]
        return DesignError(f'subsystem "{file}" {found["section"]}[{local}]{found["rest"]}', problem.problem, problem.fix)
    file = held.get(found["key"]) if isinstance(held, dict) else None
    return problem.under(f'subsystem "{file}"') if file else problem


@contextmanager
def attributed(origins):
    """Raise any DesignError inside with its place in the file that holds the entry."""
    try:
        yield
    except DesignError as problem:
        raise placed(problem, origins) from None


def settle(data):
    """Put the lists whose order means nothing into one fixed order, so moving an entry between files changes nothing."""
    def key(entry):
        return json.dumps({k: v for k, v in entry.items() if k != "note"}, sort_keys=True)
    for section in UNORDERED:
        data[section] = sorted(data[section], key=key)
