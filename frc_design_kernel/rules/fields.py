"""Every field of every record: the names that a record may use, as fields.json lists them, and what each field holds.

    walk(book, faults)     every Field, at any depth: records, openings, spots, costs and groups of extra values
    leaves(book, faults)   every Leaf (values.py): one value, wherever a value may be written in those fields
    check(book)            [DesignError] for every name and value that is wrong

A Field whose `holds` names other records, such as "when" or "awards", gives no Leaf here; words.py reads it.
"""
import functools
import re
from dataclasses import dataclass

from ..errors import DesignError, unknown
from .read import Entry, inner_spots, is_pattern, names
from .values import Reader, a_list, is_group, slip

SPOT_NAME = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class Property:
    """One property of a kind of record, as fields.json has it."""
    key: str            # its kind and its name: "opening.bottom", "limits.reach.far", "game.variants"
    holds: str
    means: str


@dataclass(frozen=True)
class Field:
    """One field of a record, or of an object inside it."""
    entry: Entry
    where: str          # the file and the path, for a message: "places.json barn.opening.bottom"
    name: str
    holds: str          # as fields.json says it, or "extra"
    node: object
    owner: dict         # the object that the field is in
    key: str = ""       # the key of its Property; "" for an extra field


@dataclass(frozen=True)
class Spec:
    """The fields of a kind of record."""
    known: dict             # {name: Property}; a name that ends with _ stands for every name that begins so
    rest: str = "extra"     # what any other name holds
    closed: bool = False    # whether other names are refused
    needs: tuple = ()       # names that must be there
    one_of: tuple = ()      # exactly one of these
    any_of: tuple = ()      # one of these or more


def properties(label, about):
    return {name: Property(f"{label}.{name}", one["holds"], one["means"]) for name, one in about.get("fields", {}).items()}


@functools.lru_cache(maxsize=None)
def spec_of(kind):
    """The Spec of a kind of record."""
    about, kinds = names()["kinds"][kind], names()["kinds"]
    known = properties(kind, about)
    if not about.get("closed"):
        known = {**properties("every", kinds["every"]), **(properties("placed", kinds["placed"]) if about.get("placed") else {}), **known}
    return Spec(known, "piece count" if about.get("by_piece") else "extra", about.get("closed", False), *(tuple(about.get(flag, ())) for flag in ("needs", "one_of", "any_of")))


@functools.lru_cache(maxsize=None)
def spec_of_limit(limit):
    """The Spec of a limit; None for one that fields.json does not name."""
    about = names()["limits"].get(limit)
    if about is None:
        return None
    return Spec({**properties("every", names()["kinds"]["every"]), **properties(f"limits.{limit}", about)}, "piece count" if about.get("by_piece") else "extra")


def spec_for(entry):
    """The Spec of a record; None for a limit that fields.json does not name."""
    if not entry.path:
        return Spec(properties(entry.file, names()["files"][entry.file]))
    return spec_of_limit(entry.id) if entry.kind == "limit" else spec_of(entry.kind)


def _listed(words):
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} or {words[-1]}"


def step(where, name):
    """The place one field further."""
    return f"{where} {name}" if where.endswith(".json") else f"{where}.{name}"


# ---- walking the records

def walk(book, faults):
    """Every Field of every record, in the order written. What is wrong with the names goes into faults."""
    for entry in book.entries:
        spec = spec_for(entry)
        if spec is None:
            faults.append(unknown(entry.where, "limit", entry.id, names()["limits"]))
        else:
            yield from object_fields(entry, entry.data, spec, entry.where, faults)


def object_fields(entry, data, spec, where, faults):
    """Every Field of one object of a record, and of the objects inside it."""
    if spec.one_of and len(set(spec.one_of) & set(data)) != 1:
        faults.append(DesignError(where, f"does not say one of {_listed(spec.one_of)}", "Write exactly one of them"))
    if spec.any_of and not set(spec.any_of) & set(data):
        faults.append(DesignError(where, f"has no {_listed(spec.any_of)}", "Write one of them"))
    for name in spec.needs:
        if name not in data:
            faults.append(DesignError(where, f'has no "{name}"', f'Add "{name}"'))
    for name, node in data.items():
        at = step(where, name)
        one = spec.known.get(name) or next((p for start, p in spec.known.items() if start.endswith("_") and name.startswith(start)), None)
        holds = one.holds if one else _rest(entry, spec, name, node, where, faults)
        if holds:
            field = Field(entry, at, name, holds, node, data, one.key if one else "")
            yield field
            yield from _inside(field, faults)


def _rest(entry, spec, name, node, where, faults):
    """What a name holds that this kind of record does not have in fields.json, or None when it is refused."""
    if spec.closed:
        faults.append(unknown(where, "field", name, spec.known))
    elif entry.path == "limits.weight" and isinstance(node, dict) and "max" in node:
        faults.append(unknown(where, "weight", name, names()["limits"]["weight"]["fields"]))
    elif spec.rest != "extra" or not slip(where, name, spec.known, faults):
        return spec.rest
    return None


def _inside(field, faults):
    """The fields of the objects that a field holds."""
    entry, node, where, holds = field.entry, field.node, field.where, field.holds
    first, _, rest = holds.rpartition(" ")
    if holds == "spots":
        yield from _spots(entry, node, where, faults)
    elif holds == "first spot":
        inner = inner_spots(node)
        for at, one in [(step(where, name), one) for name, one in inner.items()] if inner else [(where, node)]:
            yield from _one(entry, one, "spot", at, faults)
    elif first == "record":
        yield from _one(entry, node, rest, where, faults)
    elif holds in ("extra", "group") and is_group(node):
        yield from _one(entry, node, "extra", where, faults)
    elif holds == "cost" or first == "list of" and rest in names()["kinds"]:
        kind = "cost" if holds == "cost" else rest
        for i, one in enumerate(a_list(node, where, faults)):
            if not (kind == "cost" and isinstance(one, str)):
                yield from _one(entry, one, kind, f"{where}[{i}]", faults)


def _one(entry, node, kind, where, faults):
    if isinstance(node, dict):
        yield from object_fields(entry, node, spec_of(kind), where, faults)
    else:
        faults.append(DesignError(where, "is not an object", "Write its fields between { and }"))


def _spots(entry, node, where, faults):
    if not isinstance(node, dict) or not node:
        faults.append(DesignError(where, "is not spots", 'Name each spot, {"near": {"at": [...]}}, or write a row or a ring'))
    elif is_pattern(node):
        yield from _one(entry, node, "row" if "row" in node else "ring", where, faults)
        _pattern(node, where, faults)
    else:
        for name, one in node.items():
            _spot_name(name, where, faults)
            yield from _one(entry, one, "spot", step(where, name), faults)


def _pattern(node, where, faults):
    """A pattern makes a whole number of spots, and has as many names, if it has names."""
    kind = "row" if "row" in node else "ring"
    many, given = node[kind], node.get("names")
    if isinstance(many, bool) or not isinstance(many, int) or not 1 <= many <= 1000:
        faults.append(DesignError(f"{where}.{kind}", f"{many} is not a number of spots", "Write a whole number from 1 to 1000"))
    elif isinstance(given, list) and len(given) != many:
        faults.append(DesignError(where, f"makes {many} spots and names {len(given)}", "Name each spot once, or leave the names out"))
    for name in given if isinstance(given, list) else ():
        if given.count(name) > 1:
            faults.append(DesignError(f"{where}.names", f'the name "{name}" is there twice', "Name each spot once"))
            break
        _spot_name(name, f"{where}.names", faults)
    for name in inner_spots(node.get("first")) or ():
        _spot_name(name, f"{where}.first", faults)


def _spot_name(name, where, faults):
    if not isinstance(name, str) or not SPOT_NAME.fullmatch(name):
        faults.append(DesignError(where, f'"{name}" is not a name for a spot', "Use letters, digits and underscores"))


# ---- what they hold

def check(book):
    """Every fault in the names and the values of a book."""
    faults = []
    for _ in leaves(book, faults):
        pass
    return faults


def leaves(book, faults=None):
    """Every Leaf of a book, in the order written. What is wrong with a value goes into faults."""
    reader = Reader(book, [] if faults is None else faults)
    for field in walk(book, reader.faults):
        yield from reader.read(field.entry, field.node, field.where, field.holds)
        yield from reader.beside
        reader.beside.clear()
