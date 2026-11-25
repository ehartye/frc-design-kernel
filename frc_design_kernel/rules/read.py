"""Reading a rules folder: the nine files as plain data, every record in them, and paths.

    names()                    fields.json, as data: the format itself
    word_list(name)            the words of one of its lists
    read_files(folder)         ({file name: data}, [DesignError]): the JSON itself
    gather(folder, data)       (Book, [DesignError]): every record as an Entry, and the IDs
    book.entries               every Entry, in the order written: records, limits, tags, parts, people and sources
    book.ids                   {ID: Entry} for what a path may begin with
    book.look(path, choice)    what a path names, as a Found: the data itself, not worked out
    spot_names(spots)          the names that spots or a pattern make, such as "near" or "3.b"

Nothing here works anything out. A Found's node is data as it is written: a printed number, a formula, or an object with
`is`, `by` or `any`. On its way a path goes through `is`, and through `by` with the variants in choice ({kind: name});
the first of game.json is taken for a kind that is not in choice.
"""
import functools
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from ..errors import DesignError, unknown

ID = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
AXES = "xyz"
ENDS = ("low", "high")
ALLIANCES = ("blue", "red")
IDS_IN_A_GROUP = ("person", "tag", "source", "judged")      # kinds whose IDs no path begins with, and that are used once in the folder all the same
STAND_FOR_IDS = ("who", "gives_to", "goes_to", "what", "someone", "the", "the_piece", "owners", "sides", "whose", "groups", "alliance")    # word lists


@functools.lru_cache(maxsize=1)
def names():
    """fields.json: the format. Every property, word, unit and form, with what it holds and what it means."""
    return json.loads(Path(__file__).with_name("fields.json").read_text(encoding="utf-8"))


def word_list(name):
    """The words of one of the lists in fields.json."""
    return list(names()["words"][name]["words"])


def taken():
    """The words of the format that stand where an ID may, so that no ID may be one of them."""
    return {word for name in STAND_FOR_IDS for word in word_list(name)} | {"pieces", "spot", "not"}


# ---- the files

class Twice(dict):
    """A JSON object in which some field is written more than once."""
    fields = ()


def _pairs(pairs):
    data = dict(pairs)
    if len(data) == len(pairs):
        return data
    data, seen = Twice(data), [name for name, _ in pairs]
    data.fields = sorted({name for name in seen if seen.count(name) > 1})
    return data


def read_files(folder):
    """({file name: its data} for each file that reads, [a DesignError for each thing wrong with the JSON])."""
    folder, data, faults = Path(folder), {}, []
    if not folder.is_dir():
        return {}, [DesignError(str(folder), "is not a folder", "Give the dated folder that holds the nine rules files")]
    for name in names()["files"]:
        try:
            got = _read(folder / f"{name}.json")
            faults += _odd(got, f"{name}.json", " ")
            data[name] = got
        except DesignError as fault:
            faults.append(fault)
    return data, faults


def _read(path):
    try:
        text = path.read_text(encoding="utf-8")
        if text.startswith("\ufeff"):
            raise DesignError(path.name, "begins with a byte order mark (BOM), which no editor shows", "Save it as UTF-8 without BOM")
        got = json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda text: math.nan)
    except DesignError:
        raise
    except FileNotFoundError:
        raise DesignError(path.name, "does not exist", "All nine files must be there; write {} for one that holds nothing") from None
    except OSError as problem:
        raise DesignError(path.name, f"cannot be read ({problem.strerror})", "Check the file") from None
    except json.JSONDecodeError as problem:
        raise DesignError(f"{path.name} line {problem.lineno}", f"is not valid JSON ({problem.msg})", "Look for a missing comma, quote or bracket near that line") from None
    except (ValueError, RecursionError) as problem:
        raise DesignError(path.name, f"is not valid JSON ({problem})", "Write it as UTF-8 text with ordinary numbers") from None
    if not isinstance(got, dict):
        raise DesignError(path.name, "is not one JSON object", "Begin it with { and end it with }")
    return got


def _odd(node, where, join="."):
    """A fault for every field written twice and every number that is not ordinary, at any depth."""
    if isinstance(node, dict):
        found = [DesignError(where, f'the field "{name}" is written twice', "Keep one of them") for name in getattr(node, "fields", ())]
        return found + [fault for name, value in node.items() for fault in _odd(value, f"{where}{join}{name}")]
    if isinstance(node, list):
        return [fault for i, value in enumerate(node) for fault in _odd(value, f"{where}[{i}]")]
    if isinstance(node, float) and not math.isfinite(node):
        return [DesignError(where, "is not an ordinary number", "Write a finite number")]
    return []


# ---- the records

@dataclass(frozen=True)
class Entry:
    """One record: a thing with an ID, or a limit, tag, part, person or source. A file's own fields are one too."""
    file: str       # the file's name, without .json
    path: str       # how a path names it, such as "yard", "limits.reach" or "tags.t4"; "" for a file's own fields
    kind: str       # its kind in fields.json, or "limit", or the file's name for a file's own fields
    data: dict

    @property
    def id(self):
        return self.path.rpartition(".")[2]

    @property
    def where(self):
        return f"{self.file}.json {self.path}".rstrip()


@dataclass(frozen=True)
class Found:
    """What a path names."""
    node: object            # the data, as written
    entry: Entry | None     # the record it is in; None for a whole group, such as "limits"
    end: str | None         # "low" or "high" when the path asks for one end of a range
    alliance: str | None    # "blue" or "red" when the path says it: stall@red.at.x
    spot: str | None        # the spot when the path says it: branch@red.3.b.at.x or branch.spots.3.b.at.x


@dataclass(frozen=True)
class Book:
    """A rules folder as data, with its records."""
    folder: str
    data: dict        # {file name: its data}
    entries: tuple
    ids: dict         # {ID: Entry}

    def of_kind(self, *kinds):
        """{ID: Entry} for the records of some kinds, in the order written; the first of two with one ID."""
        found = {}
        for entry in self.entries:
            if entry.kind in kinds:
                found.setdefault(entry.id, entry)
        return found

    def part(self, file, name):
        """A named group of a file, or an empty one when it is not there or is not an object."""
        got = self.data.get(file, {}).get(name)
        return got if isinstance(got, dict) else {}

    @property
    def variants(self):
        """{kind of variant: its names}, as far as they are lists of text."""
        return {k: [n for n in v if isinstance(n, str)] for k, v in self.part("game", "variants").items() if isinstance(v, list)}

    @property
    def sources(self):
        return self.part("game", "sources")

    @property
    def people(self):
        return {name: one for name, one in self.part("game", "people").items() if name != "together"}

    @property
    def missing(self):
        """The names that every season must have and that this one has not, or not as an object where it must be one."""
        found = set()
        for file, about in names()["files"].items():
            for name in about.get("needs", ()):
                node = self.data.get(file, {}).get(name)
                if node is None or about["fields"][name]["holds"].startswith("record") and not (isinstance(node, dict) and node):
                    found.add(name)
        return found

    @property
    def roots(self):
        """{word that a path may begin with: its data}, beside the IDs."""
        file_of = {name: file for file, about in names()["files"].items() for name in about.get("fields", ())}
        return {root: self.part(file_of[root], root) for root in names()["roots"]["words"]}

    def look(self, path, choice=None):
        """What a path names, as a Found; a DesignError that lists what there is when it names nothing."""
        head, *steps = path.split(".")
        head, at, alliance = head.partition("@")
        where, spot = f'the path "{path}"', None
        entry = self.ids.get(head)
        node = entry.data if entry else self.roots.get(head)
        if node is None:
            raise unknown(where, "ID", head, [*self.ids, *names()["roots"]["words"]])
        if at:
            if alliance not in ALLIANCES:
                raise unknown(where, "alliance", alliance, ALLIANCES)
            if not entry or entry.data.get("alliance") != "each":
                raise DesignError(where, f'"{head}" is not one of the things of each alliance', f'Write "{head}" without @, or give it "alliance": "each"')
            spot, node, steps = at_spot(node, steps)
        elif entry and steps[:1] == ["spots"] and is_pattern(node.get("spots")) and at_spot(node, steps[1:])[0]:
            spot, _, steps = at_spot(node, steps[1:])
            node = spot_data(node["spots"], spot)
        while entry is None and steps and not self._entry(head) and isinstance(node, dict) and isinstance(node.get(steps[0]), dict):
            node, head, steps = node[steps[0]], f"{head}.{steps[0]}", steps[1:]
            entry = self._entry(head)
        node, end = self._follow(node, steps, choice or {}, where)
        return Found(node, entry or self._entry(head), end, alliance or None, spot)

    def within(self, data, path, entry, choice=None):
        """What a path names that begins with a field of data, an object in the record entry."""
        node, end = self._follow(data, path.split("."), choice or {}, f'the path "{path}"')
        return Found(node, entry, end, None, None)

    def _follow(self, node, steps, choice, where):
        """(what a path's steps lead to, the end of a range that it asks for or None)."""
        for i, name in enumerate(steps):
            node, end = self._step(node, name, choice, where, last=i == len(steps) - 1)
            if end:
                return node, end
        return node, None

    def _entry(self, path):
        return next((e for e in self.entries if e.path == path), None)

    def _step(self, node, name, choice, where, last):
        """(the data one step further, None), or (the data itself, "low" or "high") when the last step asks for an end."""
        whole = node
        while isinstance(node, dict) and name not in node and (inner := self._inside(node, name, choice)) is not None:
            node = inner
        if isinstance(node, list) and name in tuple(AXES[:len(node)]):
            return node[AXES.index(name)], None
        if isinstance(node, dict) and name in node:
            return node[name], None
        if last and name in ENDS and isinstance(node, str):
            return whole, name
        raise unknown(where, "field", name, AXES[:len(node)] if isinstance(node, list) else node if isinstance(node, dict) else ())

    def _inside(self, node, name, choice):
        """What an object that stands for a value holds: its `is`, its variant, or the limit of that name in its `any`."""
        if "is" in node:
            return node["is"]
        if isinstance(node.get("by"), str):
            kinds = self.variants.get(node["by"], [])
            return node.get(choice.get(node["by"], kinds[0] if kinds else None))
        if isinstance(node.get("any"), list):
            return next((one for one in node["any"] if isinstance(one, dict) and name in one), None)
        return None


def at_spot(record, steps):
    """(spot name or None, the data that the rest of the path is in, the rest of the path)."""
    spots = record.get("spots")
    for name in sorted(spot_names(spots), key=len, reverse=True):
        size = name.count(".") + 1
        if ".".join(steps[:size]) == name:
            one = spot_data(spots, name)
            rest = steps[size:]
            return name, {**record, **one}, rest
    return None, record, steps


def is_pattern(spots):
    return isinstance(spots, dict) and ("row" in spots or "ring" in spots)


def inner_spots(first):
    """The named spots in a pattern's `first`, or None when it is one spot itself."""
    if isinstance(first, dict) and first and "at" not in first and all(isinstance(one, dict) for one in first.values()):
        return first
    return None


def spot_names(spots):
    """The names that spots make, in order. Nothing is made from data that is not spots."""
    if not isinstance(spots, dict):
        return []
    if not is_pattern(spots):
        return list(spots)
    many, given = spots.get("row", spots.get("ring")), spots.get("names")
    if isinstance(many, bool) or not isinstance(many, int) or many > 1000:
        return []
    outer = [str(n) for n in given] if isinstance(given, list) else [str(n) for n in range(1, many + 1)]
    pair = inner_spots(spots.get("first"))
    return [f"{name}.{one}" for name in outer for one in pair] if pair else outer


def spot_data(spots, name):
    """What is written for a spot: its own record, or the pattern's `first` that it is made from."""
    one = spots.get(name) if not is_pattern(spots) else spots.get("first")
    pair = inner_spots(one) if is_pattern(spots) else None
    one = pair[name.partition(".")[2]] if pair else one
    return one if isinstance(one, dict) else {}


# ---- every record of the folder

def gather(folder, data):
    """(Book, [DesignError]): every record of the files' data, and what is wrong with its ID or its place."""
    entries, faults = [], []
    for file, about in names()["files"].items():
        own = {}
        for name, node in data.get(file, {}).items():
            holds = "record " + about["records"] if "records" in about else about["fields"].get(name, {}).get("holds")
            if holds is None:
                faults.append(unknown(f"{file}.json", "field", name, about["fields"]))
            elif holds.startswith("record "):
                entries += _records({name: node}, holds.split()[1], file, "", faults)
            elif holds.startswith("records ") or holds in ("tags", "limits", "parts", "people"):
                entries += _group(node, holds, name, file, faults)
            else:
                own[name] = node
        entries.append(Entry(file, "", file, own))
    ids = _ids(entries, faults)
    return Book(str(folder), data, tuple(entries), ids), faults


def _group(node, holds, name, file, faults):
    """The entries of a named group of records."""
    if not _object(node, f"{file}.json {name}", faults):
        return []
    if holds == "tags":
        tags = {k: v for k, v in node.items() if isinstance(v, dict) and k not in names()["kinds"]["tags"]["fields"] and not {"is", "by", "text"} & set(v)}
        return [Entry(file, name, "tags", {k: v for k, v in node.items() if k not in tags}), *_records(tags, "tag", file, "tags.", faults)]
    if holds == "limits":
        return _records(node, "limit", file, "limits.", faults)
    if holds == "parts":
        found = []
        for group, rows in node.items():
            if _object(rows, f"{file}.json parts.{group}", faults):
                _id(group, f"{file}.json parts.{group}", faults)
                found += [e for k, row in rows.items() for e in _records({k: row}, "about" if k == "about" else "part", file, f"parts.{group}.", faults)]
        return found
    if holds == "people":
        together = node.get("together", [])
        if not isinstance(together, list):
            faults.append(DesignError(f"{file}.json people.together", "is not a list", "Write a list of {\"of\": [...], \"most\": ...}"))
            together = []
        found = _records({k: v for k, v in node.items() if k != "together"}, "person", file, "people.", faults)
        return found + [Entry(file, f"people.together[{i}]", "together", one) for i, one in enumerate(together) if _object(one, f"{file}.json people.together[{i}]", faults)]
    kind = holds.split()[1]
    prefix = "" if kind not in ("source", "judged") else f"{name}."
    return _records(node, kind, file, prefix, faults)


def _records(group, kind, file, prefix, faults):
    found = []
    for name, record in group.items():
        where = f"{file}.json {prefix}{name}"
        _id(name, where, faults)
        if _object(record, where, faults):
            found.append(Entry(file, prefix + name, kind, record))
    return found


def _object(node, where, faults):
    if not isinstance(node, dict):
        faults.append(DesignError(where, "is not an object", "Write its fields between { and }"))
    return isinstance(node, dict)


def _id(name, where, faults):
    if not ID.fullmatch(name):
        faults.append(DesignError(where, f'"{name}" is not an ID', "Start with a letter and use letters, digits and underscores"))


def _ids(entries, faults):
    """{ID: Entry} of every record that a path begins with, and a fault for each ID that is taken."""
    ids, used, roots, words = {}, {}, names()["roots"]["words"], taken()
    for entry in entries:
        if entry.id in words and (entry.kind == "person" or entry.path == entry.id):
            faults.append(DesignError(entry.where, f'the ID "{entry.id}" is a word of the format', "Choose another ID, so that a rule can mean only one of them"))
        own = entry.path and "." not in entry.path and entry.kind not in (*roots, "frame")
        if not own and entry.kind not in IDS_IN_A_GROUP:
            continue
        if own and entry.path in roots:
            faults.append(DesignError(entry.where, f'the ID "{entry.path}" is a word that paths begin with', "Choose another ID"))
        elif entry.id in used:
            faults.append(DesignError(entry.where, f'the ID "{entry.id}" is used twice, also in {used[entry.id].where.split()[0]}', "Choose another ID"))
        used.setdefault(entry.id, entry)
        if own and entry.path not in roots:
            ids.setdefault(entry.path, entry)
    return ids
