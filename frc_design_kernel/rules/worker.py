"""What is worked out from a rules folder: one Worker for each choice of variants.

    Season(book)     a folder's records; worker(**variants) gives the Worker for some variants
    Worker           get(path, alliance, spot) and value(node, entry, holds): the Values (worth.py) that a path or a node gives

A Worker remembers what it has worked out, and which kinds of variant that needed.
"""
import functools
import itertools
from dataclasses import replace

from ..errors import DesignError, unknown
from . import alliances, fields, formulas, outlines, pieces, quantity, says, shapes
from .read import ALLIANCES, AXES, ENDS, ID, at_spot, word_list
from .words import paths_in
from .worth import BASE, AnyOf, Value, Wrong, one_end, one_number, shown, worked

NO_NUMBER = {"circuits": "no_limit", "on": "no_limit", "height": "height"}      # what may hold a word that stands for no limit
WORDS = {"text", "texts", "list of texts", "says", "src", "date", "timer", "period", "piece", "pieces", "award", "awards", "foul", "fouls", "places", "things", "things touched",
         "touchable", "given to", "goes to", "several people", "who", "loads"}
NOT_VALUES = {"conditions", "must not", "when", "list of whens", "spots", "first spot", "cost", "shapes", "differs", "was", "people", "tags", "limits", "parts"}


class Loop(Wrong):
    """Formulas that need each other."""

    def __init__(self, texts):
        self.texts = texts
        super().__init__(texts[0], "", f'needs itself: {" needs ".join(f'"{text}"' for text in texts)}', "Print one of them as a number")


def inside(one, where):
    """Whether a place is another one, or in it."""
    return one == where or one.startswith((f"{where}.", f"{where}["))


_read = functools.lru_cache(maxsize=4096)(quantity.read)      # the same printed number is asked for many times


class Season:
    """A rules folder's records, and a Worker for each choice of variants that is asked. bad is where a value is at fault: what
    needs one can not be worked out."""

    def __init__(self, book, bad=()):
        self.book, self.workers, self.bad = book, {}, frozenset(bad)

    @functools.cached_property
    def holds(self):
        """{path: what it holds} of every field."""
        return {field.where.partition(" ")[2]: field.holds for field in fields.walk(self.book, [])}

    @functools.cached_property
    def variants(self):
        return self.book.variants

    def worker(self, /, **variants):
        for kind, name in variants.items():
            if kind not in self.variants:
                raise unknown("", "kind of variant", kind, self.variants)
            if name not in self.variants[kind]:
                raise unknown(f"variant {kind}", "variant", name, self.variants[kind])
        choice = {kind: variants.get(kind, given[0]) for kind, given in self.variants.items() if given}
        key = tuple(choice.values())
        if key not in self.workers:
            self.workers[key] = Worker(self, choice)
        return self.workers[key]

    def each(self, work):
        """[(the names of the variants chosen, what work(worker) gives)] for each choice of the variants that the work needs."""
        kinds, before, found = [], None, []
        while kinds != before:
            before, asked, found = kinds, set(), []
            for chosen in itertools.product(*(self.variants[kind] for kind in kinds)):
                worker = self.worker(**dict(zip(kinds, chosen)))
                earlier, worker.asked = worker.asked, set()
                try:
                    found.append((chosen, work(worker)))
                finally:
                    asked |= worker.asked
                    worker.asked |= earlier
            kinds = [kind for kind in self.variants if kind in asked or kind in kinds]
        return found

    def holds_at(self, entry, spot, rest):
        """What the field holds that a path's steps lead to or into, after its record and its spot."""
        paths = [".".join([start, *rest[:i]]) for i in range(len(rest), 0, -1) for start in self.starts(entry, spot)]
        return next((self.holds[path] for path in paths if path in self.holds), "")

    def starts(self, entry, spot):
        """The paths in which a field of a record, or of one of its spots, may be written."""
        spots = f"{entry.path}.spots"
        return [entry.path, f"{spots}.{spot}", f"{spots}.first", f"{spots}.first.{spot.rpartition(".")[2]}"] if spot else [entry.path]

    def sound(self, entry, spot, rest, own):
        """Whether nothing is at fault where a path leads, in it or around it, but what is at own."""
        wheres = [f"{entry.file}.json {'.'.join([start, *rest])}" for start in self.starts(entry, spot)]
        return not any(inside(one, where) or inside(where, one) for one in self.bad if one != own for where in wheres)


class _Choice(dict):
    """{kind of variant: the name chosen}, which tells a Worker what is asked."""

    def __init__(self, choice, worker):
        super().__init__(choice)
        self.worker = worker

    def get(self, kind, default=None):
        self.worker.asked.add(kind)
        return super().get(kind, default)


class Worker:
    """Works out values for one choice of variants."""

    def __init__(self, season, choice):
        self.season, self.book = season, season.book
        self.asked = set()      # the kinds of variant that were needed so far
        self.choice = _Choice(choice, self)
        self.known = {}         # {what was asked: (its value, the kinds of variant that it needed)}
        self.doing = []         # the formulas being worked out, to see one that needs itself
        self.own = None         # where what is worked out is written, while faults are looked for

    def once(self, key, work):
        """What work() gives, worked out the first time it is asked."""
        if key not in self.known:
            before, self.asked = self.asked, set()
            try:
                got = work()
                self.known[key] = got, frozenset(self.asked)
            finally:
                self.asked |= before
        got, asked = self.known[key]
        self.asked |= asked
        return got

    # -- paths

    def get(self, path, alliance="blue", spot=None):
        """The value or values that a path names. An alliance or a spot in the path goes before those asked."""
        if alliance not in ALLIANCES:
            raise unknown("", "alliance", alliance, ALLIANCES)
        return self.once((path, alliance, spot), lambda: self._get(path, alliance, spot))

    def address(self, path):
        """(the record that a path begins with or None, the alliance and the spot that the path says, the steps after them)."""
        head, *steps = path.split(".")
        ident, at, alliance = head.partition("@")
        entry = self.book.ids.get(ident)
        if entry is None:
            found = self.book.look(path, self.choice)
            return found.entry, None, None, path.split(".")[found.entry.path.count(".") + 1:] if found.entry else []
        self.book.look(head)    # whether there is an alliance to say
        spotted = steps if at else steps[1:] if steps[:1] == ["spots"] else []
        spot, _, rest = at_spot(entry.data, spotted)
        return entry, alliance or None, spot, rest if spot else steps

    def _get(self, path, alliance, spot):
        entry, own_alliance, own_spot, rest = self.address(path)
        alliance, spot = own_alliance or alliance, own_spot or spot
        if not rest:
            raise self.not_one(self.book.look(path, self.choice).node).under(path)
        try:
            place = alliances.Place(self, entry, alliance, spot)
            self.check(entry, spot, rest)
            if rest[0] == "spots" and place.red:
                raise DesignError("", "is where blue's is", "Name the spot, such as ID@red.1.at")
            if rest == ["outline"] and alliances.moves(entry, "outline"):
                return outlines.on_field(place, place.data.get("outline"))
            if alliances.moves(entry, rest[0]) and rest[0] != "outline" and not (place.as_written and rest[0] in place.data):
                return self._moved(place, rest)
            found = self.book.within(place.data, ".".join(rest), entry, self.choice) if spot else self.book.look(path, self.choice)
            return self.field(found.node, entry, rest, found.end, place)
        except DesignError as problem:
            raise problem if problem.where else problem.under(f"{entry.file}.json {path}")

    def check(self, entry, spot, rest):
        """That the value which a path leads to is not at fault."""
        if self.season.bad and not self.season.sound(entry, spot, rest, self.own):
            raise Wrong("", "", "needs a value that is at fault", "")

    def field(self, node, entry, rest, end=None, place=None):
        """What a field of a record gives: rest are the steps to it from its record."""
        place = place or alliances.Place(self, entry, "blue")
        holds, (inner, _) = self.season.holds_at(entry, place.spot, rest), self.unwrap(node)
        if holds == "shape" and shapes.is_shape(inner):
            return shapes.drawn(self, entry, inner, place.swapped)
        if holds in ("outline", "shape") and rest[-1] in ("outline", "bottom", "top") and isinstance(inner, (list, dict)):
            return outlines.drawn(self, entry, inner, place.swapped)
        if holds == "starts" and isinstance(inner, str) and inner in word_list("starts"):
            number = pieces.left_over(self, entry, rest[-1])
            return Value("number", number, printed=str(number), src=entry.data.get("src"))
        if holds == "says" and isinstance(inner, str):
            before = rest[:-1]
            owner = self.book.within(place.data, ".".join(before), entry, self.choice).node if before else place.data
            node = says.fill(self, entry, owner, before, inner)
        return self.value(node, entry, holds, end)

    def _moved(self, place, steps):
        """The value of a path into a position that is not just what is written. Only the coordinate that is asked is worked out."""
        name, *steps = steps
        if name == "faces":
            got = place.faces()
        elif steps and steps[0] in AXES:
            got = place.coordinate(place.written(name), AXES.index(steps.pop(0)), made=name == "at")
        else:
            got = place.point(name)
        if steps and (steps[1:] or steps[0] not in ENDS or isinstance(got, list)):
            raise unknown("", "field", steps[0], ENDS if isinstance(got, Value) else AXES[:len(got)])
        return one_end(got, steps[0]) if steps else got

    def not_one(self, node):
        names = list(node) if isinstance(node, dict) else []
        return DesignError("", "is not one value", f"Name one of its fields: {', '.join(names)}" if names else "Name a value")

    # -- one value

    def value(self, node, entry, holds="", end=None, name=None):
        """The Value of a node as it is written; a list for a list, and AnyOf for limits of which one is enough."""
        node, about = self.unwrap(node)
        about = {"of": about.get("of"), "assumed": about.get("assumed"), "src": about.get("src", entry.data.get("src")), "differs": tuple(about.get("differs", ())), "name": name}
        if holds in NOT_VALUES and not isinstance(node, (bool, str)) or holds.startswith("list of ") and holds != "list of texts":
            raise self.not_one(node)
        if isinstance(node, list):
            return [self.value(one, entry, holds) for one in node]
        if isinstance(node, dict) and isinstance(node.get("any"), list):
            return AnyOf(self.value(inner, entry, holds, name=n) for one in node["any"] for n, inner in one.items())
        if isinstance(node, dict) and isinstance(node.get("text"), str):
            return Value("text", node["text"], printed=node["text"], **about)
        if isinstance(node, dict) or node is None:
            raise self.not_one(node)
        got = self._plain(node, holds)
        return replace(one_end(got, end) if end else got, **about)

    def unwrap(self, node):
        """(the node that another one stands for, through `is` and `by`; what was said about it on the way)."""
        about = {}
        while isinstance(node, dict) and ("is" in node or "by" in node):
            if "by" in node:
                node = node.get(self.choice.get(node["by"])) if isinstance(node["by"], str) else None
            else:
                about.update({k: v for k, v in node.items() if k != "is"})
                node = node["is"]
        return node, about

    def _plain(self, node, holds):
        """The Value of a number, a flag, a printed number, a formula or a word."""
        if isinstance(node, bool):
            return Value("flag", node, printed=str(node).lower())
        if isinstance(node, (int, float)):
            return Value("number", quantity.count(node).value, printed=str(node))
        if holds in WORDS or holds.split(" ")[0] in ("word", "words"):
            return Value("text", node, printed=node)
        if holds in NO_NUMBER and node in word_list(NO_NUMBER[holds]):
            return Value(node, None, printed=node)
        if node.startswith("="):
            return self.formula(node)
        if holds == "longer than" and ID.fullmatch(node):
            return Value("text", node, printed=node)
        got = _read(node)
        return Value(got.kind, got.value, got.limit, got.low, got.high, got.printed, unit=got.unit)

    # -- formulas

    def begin(self, text):
        """Note that something is being worked out, until doing.pop(). What needs itself is a Loop."""
        if text in self.doing:
            raise Loop([*self.doing[self.doing.index(text):], text])
        self.doing.append(text)

    def formula(self, text):
        """The Value that a formula gives, printed in the unit of the first value of its kind that it names; in inches for feet, in seconds for minutes."""
        self.begin(text)
        try:
            kind, number = formulas.work(text, lambda path: self._named(text, path))
            units = [value.unit for path in paths_in(text) if (value := self.get(path)).kind == kind and value.unit]
        except Wrong:
            raise
        except DesignError as problem:
            raise Wrong(text, "", problem.problem, problem.fix) from None
        finally:
            self.doing.pop()
        unit = worked(units[0]) if units else BASE.get(kind, kind if kind != "number" else None)
        return Value(kind, number, printed=shown(number, kind, unit), unit=unit)

    def _named(self, text, path):
        """(kind, number) of a value that a formula names."""
        try:
            value = self.get(path)
            return value.kind if isinstance(value, Value) else None, one_number(value)
        except Wrong:
            raise
        except DesignError as problem:
            raise DesignError("", f'the formula "{text}" names {path}, which {problem.problem}', problem.fix) from None
