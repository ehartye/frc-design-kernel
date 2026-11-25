"""A game's rules, read from one dated folder and worked out.

    load_rules(folder)    a Rules, or the first DesignError raised
    faults(folder)        every DesignError

A Rules answers with get, limit, to and says (values and words), conditions, when, windows, judged and points (times and
scores), starts and runs (how many), and records, outline and solid (what stands where). Every length is in mm, every mass in
kg, every time in s and every angle in degrees. A variant that is not named is the first one in game.json.
"""
import copy

from ..errors import DesignError, unknown
from . import alliances, conditions, derive, fields, outlines, parts, pieces, quantity, records, says, shapes, times, words
from .read import ALLIANCES, names
from .worker import Season
from .worth import Value


def load_rules(folder):
    """The Rules of a folder. The first thing that is wrong with it is raised."""
    book, found = _read(folder)
    if found:
        raise found[0]
    return Rules(book)


def faults(folder):
    """Every DesignError of a folder: what does not read, and what cannot be worked out."""
    return _read(folder)[1]


def _read(folder):
    book, found = words.load(folder)
    return book, found + derive.faults(book, found) if book else found


class Rules:
    """Answers from one rules folder. Nothing is written, and nothing is judged."""

    def __init__(self, book):
        self.book, self.season = book, Season(book)

    def get(self, path, /, alliance="blue", spot=None, **variants):
        """The value that a path names, such as "barn.opening.bottom"; a list of them for a list; a shape or an outline in mm."""
        return copy.deepcopy(self.season.worker(**variants).get(path, alliance, spot))      # what is remembered stays as it is

    def limit(self, name, **variants):
        """The limit of that name, such as "reach.far", or None when this season has no such limit."""
        self.season.worker(**variants)      # whether there are such variants
        first, _, rest = name.partition(".")
        known = names()["limits"]
        if first not in known:
            raise unknown("", "limit", first, known)
        entry = next((e for e in self.book.entries if e.path == f"limits.{first}"), None)
        if entry is None:
            return None
        try:
            return self.get(f"limits.{name}", **variants)
        except DesignError:
            if rest and self._left_out(entry, rest.split(".")):
                return None
            raise

    def _left_out(self, entry, steps):
        """Whether a limit's record may have what the steps name and this one has not."""
        data, spec = entry.data, fields.spec_for(entry)
        while steps and isinstance(data, dict):
            name, *steps = steps
            one = spec.known.get(name)
            if name in data:
                if not one or not one.holds.startswith("record "):
                    return False
                data, spec = data[name], fields.spec_of(one.holds.removeprefix("record "))
            else:
                return one is not None or spec.rest == "piece count" and name in self.book.of_kind("piece")
        return False

    def to(self, value, unit):
        """A value in another unit of its kind."""
        if not isinstance(value, Value) or value.kind in ("text", "flag", "any", "none"):
            raise DesignError("", f"{value.kind if isinstance(value, Value) else 'a list'} has no unit", "Give one number")
        if value.value is None:
            raise DesignError("", f"{value.printed} is a range, and has no one number", "Ask for its .low or its .high")
        return quantity.convert(value.value, value.kind, unit)

    # -- what is said, and when

    def says(self, path, **variants):
        """What a record says, with its numbers filled in."""
        worker = self.season.worker(**variants)
        entry = next((e for e in self.book.entries if e.path == path and path), None)
        if entry is None or "says" not in entry.data:
            return worker.get(f"{path}.says").value
        return self._of(entry, lambda: says.fill(worker, entry, entry.data, [], entry.data["says"]))

    def conditions(self, path, **variants):
        """The conditions of a field, such as "G90.must_not", parsed: Conditions and Groups. True for a must_not that is true."""
        worker = self.season.worker(**variants)
        entry, node = conditions.node_of(worker, path, ("conditions", "must not"), "conditions")
        return self._of(entry, lambda: conditions.conditions(worker, entry, node))

    def when(self, asked):
        """The names of a `when`, such as "G95.when" or a list of them, as Moments; for the `true` of a state, a tuple for each way."""
        node, several = asked, False
        if isinstance(asked, str):
            _, node = conditions.node_of(self.season.worker(), asked, ("when", "list of whens"), "when")
            several = bool(node) and isinstance(node[0], list)
        return [conditions.moments(self.book, one) for one in node] if several else conditions.moments(self.book, node)

    def windows(self, **variants):
        """{name: Window}, with its period, and its start and end in seconds from the start of its period."""
        return times.windows(self.season.worker(**variants))

    def judged(self, award, **variants):
        """{period: the seconds after it in which an award still counts for that period}."""
        return times.judged(self.season.worker(**variants), award)

    def points(self, award, **variants):
        """The points of an award as Rows, each with its when and its points. Of those that are true, the longest when counts."""
        known = self.book.of_kind("award")
        if award not in known:
            raise unknown("", "award", award, known)
        return self._of(known[award], lambda: conditions.rows(self.season.worker(**variants), known[award]))

    def starts(self, piece, **variants):
        """{record: how many of a piece it has at the start}, such as {"stall@blue": 20, "stall@red": 20}."""
        if piece not in self.book.of_kind("piece"):
            raise unknown("", "piece", piece, self.book.of_kind("piece"))
        return pieces.starts(self.season.worker(**variants), piece)

    def runs(self, device, **variants):
        """{path of a load: how many of it} that one device of parts may run, such as {"parts.motors.mule": 2}."""
        return parts.runs(self.season.worker(**variants), device)

    # -- where things stand

    def records(self, file, **variants):
        """Every record of a file in the order written, with red's and every spot made: crate@red, rack@red.3.b."""
        return records.records(self.season.worker(**variants), file)

    def outline(self, ident, alliance="blue", spot=None, **variants):
        """The outline of a record on the field: its points [(x, y), ...] in mm."""
        place = self._place(ident, "outline", alliance, spot, variants)
        return self._of(place.entry, lambda: outlines.on_field(place, place.data["outline"]))

    def solid(self, ident, alliance="blue", spot=None, **variants):
        """The shape of a record and where it stands on the field: {"shape", "place"}, as a design's solid has them."""
        place = self._place(ident, "shape", alliance, spot, variants)
        return self._of(place.entry, lambda: shapes.solid(place, place.data["shape"]))

    def _place(self, ident, name, alliance, spot, variants):
        """The place of a record that has a field of that name."""
        entry = self.book.ids.get(ident)
        if entry is None:
            raise unknown("", f"record with {name}", ident, [i for i, e in self.book.ids.items() if name in e.data])
        if alliance not in ALLIANCES:
            raise unknown("", "alliance", alliance, ALLIANCES)
        if name not in entry.data:
            raise DesignError(entry.where, f"has no {name}", entry.data.get("no_geometry", f"Ask for something that has {name}"))
        return alliances.Place(self.season.worker(**variants), entry, alliance, spot)

    def _of(self, entry, work):
        """What work() gives; what is wrong is told with the record."""
        try:
            return work()
        except DesignError as problem:
            raise problem if problem.where else problem.under(entry.where)
