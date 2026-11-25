"""Conditions and times, parsed, with the IDs that they name resolved to their records. Whether one holds is not worked out.

    conditions(worker, entry, node)    the Conditions and Groups of a list that must all be true; True for a plain must_not
    moments(book, names)               a `when` list as Moments, which must all be true
    rows(worker, entry)                the points of an award: Rows, each with its Moments

`my` and `their` are always seen from the robot that acts, so they stay what they are for blue and for red.
"""
from dataclasses import dataclass

from ..errors import DesignError, unknown
from .read import Entry, word_list
from .words import PLACED, WHEN


@dataclass(frozen=True)
class Someone:
    """Who a condition is about: the robot, its bumpers, a person, the alliance, a count or the piece."""
    whose: str              # my, their or either; the, before a piece
    name: str
    entry: Entry | None     # the record of a count or a piece


@dataclass(frozen=True)
class Thing:
    """What a condition is about, when it is something with an ID."""
    whose: str | None       # my, their or any; None for what belongs to neither
    name: str
    entry: Entry


@dataclass(frozen=True)
class Condition:
    """[who, how, what]."""
    who: Someone
    how: str
    what: object            # a Thing, a Value, a word of the list `what`, or several Things and words


@dataclass(frozen=True)
class Moment:
    """One name of a `when`."""
    name: str
    kind: str               # period, window, state or variant
    whose: str | None       # my or their, for a state
    negated: bool           # with `not` in front
    entry: Entry | None     # its record; None for a variant
    of: str | None = None   # the kind of variant

    @property
    def words(self):
        """As it is written, with whose a state is: not my lit."""
        return " ".join([*(["not"] if self.negated else []), *([self.whose] if self.whose else []), self.name])


@dataclass(frozen=True)
class Group:
    """Conditions of which one is enough (`any`), or that must all be true (`all`), at some times."""
    kind: str
    of: tuple
    when: tuple


@dataclass(frozen=True)
class Row:
    """Points for an award at some time."""
    when: tuple
    points: object          # a Value


def moments(book, names):
    """A `when` list, parsed. A state of an alliance with nobody in front is mine."""
    return tuple(_moment(book, name) for name in names)


def _moment(book, name):
    negated, got = name.startswith("not "), WHEN.fullmatch(name)
    whose, ident = got[1], got[2]
    kinds = {kind: book.of_kind(kind) for kind in ("period", "window", "state")}
    for kind, known in kinds.items():
        if ident in known:
            mine = kind == "state" and not whose and known[ident].data.get("of") == "alliance"
            return Moment(ident, kind, "my" if mine else whose, negated, known[ident])
    for of, known in book.variants.items():
        if ident in known:
            return Moment(ident, "variant", None, negated, None, of)
    raise unknown("", "period, window, state or variant", ident, [*(i for known in kinds.values() for i in known), *(n for known in book.variants.values() for n in known)])


def conditions(worker, entry, node):
    """Conditions and groups of them, which must all be true."""
    return True if node is True else tuple(_one(worker, entry, one) for one in node)


def _one(worker, entry, node):
    if isinstance(node, dict):
        kind = next(kind for kind in word_list("groups") if kind in node)
        return Group(kind, conditions(worker, entry, node[kind]), moments(worker.book, node.get("when", ())))
    who, how, what = node
    owner, _, name = who.partition(" ")
    someone = Someone(owner, name, worker.book.ids.get(name) if name not in (*word_list("someone"), *word_list("the_piece")) else None)
    return Condition(someone, how, _what(worker, entry, what))


def _what(worker, entry, node):
    if isinstance(node, list):
        return tuple(_thing(worker.book, one) or one for one in node)
    if isinstance(node, str) and node in word_list("what"):
        return node
    return _thing(worker.book, node) or worker.value(node, entry)


def _thing(book, node):
    """The Thing that `my yard` or `pond` names, or None for a value or for words."""
    if not isinstance(node, str):
        return None
    owner, space, name = node.partition(" ")
    owner, name = (owner, name) if space and owner in word_list("owners") else (None, node)
    entry = book.ids.get(name)
    return Thing(owner, name, entry) if entry and entry.kind in (*PLACED, "piece") else None


def rows(worker, entry):
    """The points of an award, by when."""
    return [Row(moments(worker.book, row["when"]), worker.value(row["points"], entry, "number", about={"src": row["src"]} if "src" in row else None)) for row in entry.data.get("points", ())]


def node_of(worker, path, holds, what):
    """(the record, the data) of a path whose field holds one of some forms."""
    found = worker.book.look(path, worker.choice)
    got = worker.season.holds_at(found.entry, None, path.split(".")[found.entry.path.count(".") + 1:]) if found.entry else ""
    if got not in holds:
        raise DesignError("", f"{path} holds no {what}", f"Ask for a field that holds {what}")
    return found.entry, found.node
