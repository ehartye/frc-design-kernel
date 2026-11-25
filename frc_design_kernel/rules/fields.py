"""Every field of every record: the names that a record may use, as fields.json lists them, and what each field holds.

    walk(book, faults)     every Field, at any depth: records, openings, spots, costs and groups of extra values
    leaves(book, faults)   every Leaf (values.py): one value, wherever a value may be written in those fields
    check(book)            [DesignError] for every name and value that is wrong

A Field whose `holds` names other records, such as "when" or "awards", gives no Leaf here; words.py reads it.
"""
import re
from dataclasses import dataclass

from ..errors import DesignError, unknown
from .read import Entry, inner_spots, is_pattern, names
from .values import Reader, a_list, is_group, slip

SPOT_NAME = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class Field:
    """One field of a record, or of an object inside it."""
    entry: Entry
    where: str          # the file and the path, for a message: "places.json barn.opening.bottom"
    name: str
    holds: str          # as fields.json says it, or "extra"
    node: object
    owner: dict         # the object that the field is in


@dataclass(frozen=True)
class Spec:
    """The fields of a kind of record."""
    known: dict             # {name: what it holds}
    rest: str = "extra"     # what any other name holds
    closed: bool = False    # whether other names are refused
    needs: tuple = ()


def spec_of(kind):
    about = names()["kinds"][kind]
    known = {**names()["every"], **(names()["placed"] if about.get("placed") else {}), **about["fields"]}
    return Spec(about["fields"] if about.get("closed") else known, "piece count" if about.get("by_piece") else "extra", about.get("closed", False), tuple(about.get("needs", ())))


def spec_for(entry):
    """The Spec of a record; None for a limit that RULES.md does not name."""
    if not entry.path:
        return Spec(names()["files"][entry.file].get("fields", {}))
    if entry.kind != "limit":
        return spec_of(entry.kind)
    about = names()["limits"].get(entry.id)
    if about is None:
        return None
    return Spec(names()["every"], "piece count") if about == "by piece" else Spec({**names()["every"], **about})


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
            yield from _object(entry, entry.data, spec, entry.where, faults)


def _object(entry, data, spec, where, faults):
    for name in spec.needs:
        if name not in data:
            faults.append(DesignError(where, f'has no "{name}"', f'Add "{name}"'))
    for name, node in data.items():
        at = step(where, name)
        holds = spec.known.get(name) or _rest(entry, spec, name, node, where, faults)
        if holds:
            field = Field(entry, at, name, holds, node, data)
            yield field
            yield from _inside(field, faults)


def _rest(entry, spec, name, node, where, faults):
    """What a name holds that RULES.md does not give for this kind of record, or None when it is refused."""
    if spec.closed:
        faults.append(unknown(where, "field", name, spec.known))
    elif entry.path == "limits.weight" and isinstance(node, dict) and "max" in node:
        faults.append(unknown(where, "weight", name, names()["limits"]["weight"]))
    elif entry.kind == "judged" and name.startswith("after_"):
        return "after period"
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
        yield from _object(entry, node, spec_of(kind), where, faults)
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
    for entry in book.entries:
        _whole(entry, reader.faults)


def _whole(entry, faults):
    """What a record must have of several fields."""
    if entry.kind == "part" and not {"name", "for"} & set(entry.data):
        faults.append(DesignError(entry.where, "has no name or for", "Say what it is called, or what it is for"))
    if entry.kind == "window" and len({"first", "last", "timer"} & set(entry.data)) != 1:
        faults.append(DesignError(entry.where, "does not say one of first, last or timer", "Write exactly one of them"))
