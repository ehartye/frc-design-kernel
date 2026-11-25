"""What is worked out from a rules folder: one Worker for each choice of variants.

    Season(book)     a folder's records; worker(**variants) gives the Worker for some variants
    Worker           get(path, alliance, spot) and value(node, entry, holds): the Values (worth.py) that a path or a node gives

A Worker remembers what it has worked out, and which kinds of variant that needed.
"""
import functools
import itertools
from dataclasses import replace

from ..errors import DesignError, unknown
from . import alliances, conditions, fields, formulas, outlines, pieces, quantity, says, shapes
from .read import ALLIANCES, AXES, ENDS, ID, at_spot, word_list
from .values import OUTLINES
from .words import paths_in
from .worth import BASE, AnyOf, NotOne, Told, Value, Wrong, one_end, one_number, shown, worked

NO_NUMBER = {"circuits": "no_limit", "on": "no_limit", "height": "height"}      # what may hold a word that stands for no limit
WORDS = {"text", "texts", "list of texts", "says", "src", "date", "timer", "period", "piece", "pieces", "award", "awards", "foul", "fouls", "places", "things", "things touched",
         "touchable", "given to", "goes to", "several people", "who", "loads"}
NOT_VALUES = {"conditions", "must not", "when", "list of whens", "spots", "first spot", "cost", "shapes", "differs", "was", "people", "tags", "limits", "parts"}
TOLD_WHOLE = {"conditions": "conditions", "must not": "conditions", "when": "when", "list of whens": "when", "cost": "", "differs": "", "was": ""}     # and the method of Rules that gives it

LONGEST = 50        # a value is worked out from a chain of so many others at most, one from another; a real one needs a few


class Loop(Wrong):
    """Formulas, or words, that need each other."""

    def __init__(self, texts):
        self.texts = texts
        fix = "Print one of them as a number" if any(text.startswith("=") for text in texts) else "Write one of them without the other"
        super().__init__(texts[0], "", f'needs itself: {" needs ".join(f'"{text}"' for text in texts)}', fix)


class TooLong(Wrong):
    """A chain of values that is longer than any reader can follow."""

    def __init__(self):
        super().__init__("", "", f"needs a chain of more than {LONGEST} values, one from another", "Write one of them as a number")


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
    def fields(self):
        """{path: its Field}."""
        return {field.where.partition(" ")[2]: field for field in fields.walk(self.book, [])}

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

    def field_at(self, entry, spot, rest):
        """(the Field that a path's steps lead to or into, after its record and its spot, or None; the steps inside it)."""
        paths = [(".".join([start, *rest[:i]]), rest[i:]) for i in range(len(rest), 0, -1) for start in self.starts(entry, spot)]
        return next(((self.fields[path], inner) for path, inner in paths if path in self.fields), (None, rest))

    def holds_at(self, entry, spot, rest):
        field, _ = self.field_at(entry, spot, rest)
        return field.holds if field else ""

    def sort_at(self, entry, spot, rest):
        """The Sort of what a path leads to, when the property there says it; else None."""
        field, inner = self.field_at(entry, spot, rest)
        return alliances.sort_at(field.key, inner) if field else None

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
        self.known = {}         # {what was asked: (its value, the kinds of variant that it needed, how long a chain of values)}
        self.inside = 0         # how many values are being worked out, one inside another
        self.chain = 0          # the longest chain that was needed so far
        self.doing = []         # the formulas being worked out, to see one that needs itself
        self.own = None         # where what is worked out is written, while faults are looked for

    def once(self, key, work):
        """What work() gives, worked out the first time it is asked."""
        if key not in self.known:
            asked, chain = self.asked, self.chain
            self.asked, self.chain, self.inside = set(), 0, self.inside + 1
            try:
                if self.inside > LONGEST:
                    raise TooLong()
                got = work()
                if self.chain >= LONGEST:
                    raise TooLong()
                self.known[key] = got, frozenset(self.asked), self.chain + 1
            finally:
                self.asked, self.chain, self.inside = self.asked | asked, chain, self.inside - 1
        got, asked, chain = self.known[key]
        self.asked |= asked
        self.chain = max(self.chain, chain)
        return got

    # -- paths

    def get(self, path, alliance="blue", spot=None):
        """The value or values that a path names. An alliance or a spot in the path goes before those asked."""
        if alliance not in ALLIANCES:
            raise unknown("", "alliance", alliance, ALLIANCES)
        return self.once((path, alliance, spot), lambda: self._sorted(path, alliance, spot))

    def _sorted(self, path, alliance, spot):
        """What a path gives, with its Sort from where it stands."""
        got = self._get(path, alliance, spot)
        if not isinstance(got, Value):
            return got
        entry, _, own_spot, rest = self.address(path)
        sort = self.season.sort_at(entry, own_spot or spot, rest)
        return replace(got, sort=sort) if sort else got

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
            raise self.no_value(self.book.look(path, self.choice).node).under(path)
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
            try:
                return self.field(found.node, entry, rest, found.end, place)
            except NotOne:
                raise self.not_one(found.node, entry, spot, rest) from None
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
        if holds in (*OUTLINES, "shape") and rest[-1] in ("outline", "bottom", "top") and isinstance(inner, (list, dict)):
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

    def no_value(self, node):
        names = list(node) if isinstance(node, dict) else []
        return NotOne("", "is not one value", f"Name one of its fields: {', '.join(names)}" if names else "Name a value")

    def not_one(self, node, entry, spot, rest):
        """What is wrong with a path that leads to no value: an object has fields to name; a list, conditions, times or a cost is told
        as a whole, by a call for a program and by the command that finds its record."""
        field, _ = self.season.field_at(entry, spot, rest)
        path, holds = (field.where.partition(" ")[2], field.holds) if field else ("", "")
        if isinstance(node, dict) and node and holds not in TOLD_WHOLE and not holds.startswith("list of "):
            return self.no_value(node)
        beside = rest[-1] if holds == "cap" and path == ".".join([entry.path, *rest[:-1]]) else ""
        if TOLD_WHOLE.get(holds):
            call, how = f'{TOLD_WHOLE[holds]}("{path}")', ""
        elif holds == "list of points":
            call, how = f'points("{entry.path}")', ""
        elif beside in ("each", "when"):
            call, how = f'get("{path}")', f", as its {beside}"
        else:
            call, how = f'records("{entry.file}")', ", in the data of its record"
        return Told("", "is not one value", "Name a value", f"rules.{call} tells it{how}", find=entry.path)

    # -- one value

    def value(self, node, entry, holds="", end=None, name=None):
        """The Value of a node as it is written; a list for a list, and AnyOf for limits of which one is enough."""
        node, about = self.unwrap(node)
        about = {"of": about.get("of"), "assumed": about.get("assumed"), "src": about.get("src", entry.data.get("src")), "differs": tuple(about.get("differs", ())),
                 "each": about.get("each"), "when": conditions.moments(self.book, about.get("when", ())), "name": name}
        if holds in NOT_VALUES and not isinstance(node, (bool, str)) or holds.startswith("list of ") and holds != "list of texts":
            raise self.no_value(node)
        if isinstance(node, list):
            return [self.value(one, entry, holds) for one in node]
        if isinstance(node, dict) and isinstance(node.get("any"), list):
            return AnyOf(self.value(inner, entry, holds, name=n) for one in node["any"] for n, inner in one.items())
        if isinstance(node, dict) and isinstance(node.get("text"), str):
            return Value("text", node["text"], printed=node["text"], **about)
        if isinstance(node, dict) or node is None:
            raise self.no_value(node)
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
        try:
            got = _read(node)
        except DesignError:
            raise self.no_value(node) from None
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
            kind, number, sort = formulas.work(text, lambda path: self._named(text, path))
            units = [value.unit for path in paths_in(text) if (value := self.get(path)).kind == kind and value.unit]
        except Wrong:
            raise
        except DesignError as problem:
            raise Wrong(text, "", problem.problem, problem.fix) from None
        finally:
            self.doing.pop()
        unit = worked(units[0]) if units else BASE.get(kind, kind if kind != "number" else None)
        return Value(kind, number, printed=shown(number, kind, unit), unit=unit, sort=sort)

    def _named(self, text, path):
        """(kind, number, Sort) of a value that a formula names."""
        try:
            value = self.get(path)
            number = one_number(value)
            if value.each or value.when:
                raise DesignError("", f"is {f'for each {value.each}' if value.each else 'only for some times'}", "Name the count for the whole, or print it; what starts where in all is in rules.starts")
            return value.kind, number, value.sort
        except Wrong:
            raise
        except DesignError as problem:
            raise DesignError("", f'the formula "{text}" names {path}, which {problem.problem}', problem.fix) from None
