"""What is worked out from a rules folder: one Worker for each choice of variants.

    Season(book)     a folder's records; worker(**variants) gives the Worker for some variants
    Worker           get(path, alliance, spot) and value(node, entry, holds): the Values (worth.py) that a path or a node gives

A Worker remembers what it has worked out, and which kinds of variant that needed.
"""
import functools
import itertools
import re
from dataclasses import replace

from ..errors import DesignError, unknown
from . import alliances, conditions, fields, formulas, outlines, pieces, quantity, says, shapes
from .read import ALLIANCES, AXES, ENDS, ID, after_spots, at_spot, spot_data, word_list
from .values import OUTLINES
from .words import paths_in
from .worth import BASE, AnyOf, NotOne, Told, Value, Wrong, one_end, one_number, shown, worked

NO_NUMBER = {"circuits": "no_limit", "on": "no_limit", "height": "height"}      # what may hold a word that stands for no limit
WORDS = {"text", "texts", "list of texts", "says", "src", "date", "timer", "period", "piece", "pieces", "award", "awards", "foul", "fouls", "places", "things", "things touched",
         "touchable", "given to", "goes to", "several people", "who", "loads"}
NOT_VALUES = {"conditions", "must not", "when", "list of whens", "spots", "first spot", "cost", "shapes", "differs", "was", "people", "tags", "limits", "parts"}
TOLD_WHOLE = {"conditions": "conditions", "must not": "conditions", "when": "when", "list of whens": "when", "cost": "", "differs": "", "was": ""}     # and the method of Rules that gives it
SAID = ("differs", "when")      # what is said beside a value and must read before the value can be told

LONGEST = 50        # a value is worked out from a chain of so many others at most, one from another; a real one needs a few


class Loop(Wrong):
    """Formulas, or words, that need each other."""

    def __init__(self, texts):
        self.texts = texts
        fix = "Print one of them as a number" if any(text.startswith("=") for text in texts) else "Write one of them without the other"
        super().__init__(texts[0], "", f'needs itself: {" needs ".join(f'"{text}"' for text in texts)}', fix)


class Turned(Exception):
    """A part of a drawing that a mirror image turns round, asked for red."""


class TooLong(Wrong):
    """A chain of values that is longer than any reader can follow."""

    def __init__(self):
        super().__init__("", "", f"needs a chain of more than {LONGEST} values, one from another", "Write one of them as a number")


def as_named(where):
    """A place as a path names it: without `is` and `any`, and with .x for the first of a list."""
    return re.sub(r"\[([0-2])\]", lambda found: f".{AXES[int(found[1])]}", re.sub(r"\.is(?=[.\[]|$)|\.any\[[0-9]+\]", "", where))


def inside(one, where):
    """Whether a place is another one, or in it."""
    return one == where or one.startswith((f"{where}.", f"{where}["))


_read = functools.lru_cache(maxsize=4096)(quantity.read)      # the same printed number is asked for many times


class Season:
    """A rules folder's records, and a Worker for each choice of variants that is asked. bad is where a value is at fault: what
    needs one can not be worked out."""

    def __init__(self, book, bad=()):
        self.book, self.workers, self.bad = book, {}, [(as_named(one), one) for one in bad]
        self.inside = 0         # how many values are being worked out, one inside another
        self.doing = []         # the formulas and the words being worked out, to see one that needs itself
        self.own = None         # where what is worked out is written, while faults are looked for

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

    def marked(self, got, entry, spot, rest):
        """What a path gives, marked as a position or a direction when the property that the path leads to says so."""
        field, inner = self.field_at(entry, spot, rest)
        if field and isinstance(got, list) and field.key in alliances.POSITIONS:
            return [self.marked(one, entry, spot, [*rest, axis]) for one, axis in zip(got, AXES)]
        uses = alliances.uses_place(field.key, inner) if field and isinstance(got, Value) else None
        return got if uses is None else replace(got, moves=uses)

    def turned(self, entry, spot, rest):
        """Whether a path leads into a drawing, to a part that a mirror image turns round: a point, a part's `at` or an angle."""
        field, inner = self.field_at(entry, spot, rest)
        return bool(field) and field.holds in (*OUTLINES, "shape") and (bool({"at", "points"} & set(inner)) or any(
            name in ("outline", "bottom", "top") and step in AXES for name, step in zip(inner, inner[1:])))

    def whole(self, entry, spot, rest):
        """The steps to the whole drawing that a path leads into, of the variant that the path names."""
        field, inner = self.field_at(entry, spot, rest)
        _, chosen = self.book.plain(field.owner, [field.name, *inner], {})
        return ".".join([*([spot] if spot else []), *rest[:len(rest) - len(inner)], *(step for step in inner if step in chosen.values())])

    def starts(self, entry, spot):
        """The paths in which a field of a record, or of one of its spots, may be written: the spot's own first."""
        spots = f"{entry.path}.spots"
        return [f"{spots}.{spot}", f"{spots}.first", f"{spots}.first.{spot.rpartition(".")[2]}", entry.path] if spot else [entry.path]

    def sound(self, entry, spot, rest, own):
        """Whether nothing is at fault where a path leads, in it or around it, nor in what is said beside it on the way, but what is at own."""
        wheres = [as_named(f"{entry.file}.json {'.'.join([start, *rest])}") for start in self.starts(entry, spot)]
        wheres += [f"{where.rsplit('.', i)[0]}.{name}" for where in wheres for i in range(len(rest)) for name in SAID]
        return not any(inside(at, where) or inside(where, at) for at, one in self.bad if one != own for where in wheres)


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
        self.chain = 0          # the longest chain that was needed so far

    def once(self, key, work):
        """What work() gives, worked out the first time it is asked."""
        if key not in self.known:
            asked, chain = self.asked, self.chain
            self.asked, self.chain, self.season.inside = set(), 0, self.season.inside + 1
            try:
                if self.season.inside > LONGEST:
                    raise TooLong()
                got = work()
                if self.chain >= LONGEST:
                    raise TooLong()
                self.known[key] = got, frozenset(self.asked), self.chain + 1
            finally:
                self.asked, self.chain, self.season.inside = self.asked | asked, chain, self.season.inside - 1
        got, asked, chain = self.known[key]
        self.asked |= asked
        self.chain = max(self.chain, chain)
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
        spotted = after_spots(entry.data, steps) if at else steps[1:] if steps[:1] == ["spots"] else []
        spot, _, rest = at_spot(entry.data, spotted)
        return entry, alliance or None, spot, rest if spot else steps

    def _get(self, path, alliance, spot):
        entry, own_alliance, own_spot, rest = self.address(path)
        alliance, spot = own_alliance or alliance, own_spot or spot
        if not rest:
            raise self.no_value(spot_data(entry.data["spots"], own_spot) if own_spot else self.book.look(path, self.choice).node).under(path)
        try:
            place = alliances.Place(self, entry, alliance, spot)
            self.check(entry, spot, rest)
            if rest[0] == "spots" and place.red:
                names = alliances.spots(entry)
                raise DesignError("", "is what blue's spots are made from", f"Ask for a spot of red's, such as {entry.id}@red.{names[0]}.at, of: {', '.join(names)}")
            try:
                return self.along(self._data(place), rest, (entry.path, alliance, spot), lambda worker, plain: worker._at(alliances.Place(worker, entry, alliance, spot), plain))
            except NotOne:
                raise self.not_one(self.book.within(self._data(place), ".".join(rest), entry, self.choice).node, entry, spot, rest) from None
            except Turned:
                raise DesignError("", "is turned round for red, whose copy is a mirror image", f"Ask for the whole of it: {entry.id}@red.{self.season.whole(entry, spot, rest)}") from None
        except DesignError as problem:
            raise problem if problem.where else problem.under(f"{entry.file}.json {path}")

    def _data(self, place):
        """What a path goes on into from its record. What all the tags share is a record, and each tag is in the same group."""
        return self.book.part("field", "tags") if place.entry.kind == "tags" else place.data

    def along(self, data, steps, key, work):
        """What work(worker, steps) gives: the steps without `is` and the names of variants, and the worker of the variants that they name."""
        plain, chosen = self.book.plain(data, steps, self.choice)
        return self.of_variant(chosen, (*key, *plain), lambda worker: work(worker, plain)) if chosen else work(self, plain)

    def of_variant(self, chosen, key, work):
        """What work(worker) gives for the variants that a path names, whichever were chosen."""
        worker, before = self.season.worker(**{**self.choice, **chosen}), set(self.asked)
        got = worker.once(key, lambda: work(worker))
        _, asked, chain = worker.known[key]
        self.asked, self.chain = before | asked - set(chosen), max(self.chain, chain)
        return got

    def _at(self, place, rest):
        """What a path into a record gives, for an alliance and a spot: rest are its steps, with no `is` and no variant in them."""
        entry, spot = place.entry, place.spot
        if rest == ["outline"] and alliances.moves(entry, "outline"):
            return outlines.on_field(place, place.data.get("outline"))
        if alliances.moves(entry, rest[0]) and (place.listed if rest[0] == "outline" else not (place.as_written and rest[0] in place.data)):
            return self.season.marked(self._moved(place, rest), entry, spot, rest)
        if place.swapped and self.season.turned(entry, spot, rest):
            raise Turned()
        return self.written(self._data(place), entry, [], rest, place)

    def written(self, data, entry, start, rest, place=None):
        """What a path gives that begins in data, the object that some steps lead to in a record."""
        found, steps = self.book.within(data, ".".join(rest), entry, self.choice, f"{'.'.join([entry.path, *start])}."), [*start, *rest]
        return self.season.marked(self.field(found.node, entry, steps, found.end, place, found.about), entry, place.spot if place else None, steps)

    def check(self, entry, spot, rest):
        """That the value which a path leads to is not at fault."""
        if self.season.bad and not self.season.sound(entry, spot, rest, self.season.own):
            raise Wrong("", "", "needs a value that is at fault", "")

    def field(self, node, entry, rest, end=None, place=None, about=None):
        """What a field of a record gives: rest are the steps to it from its record, and about what was said on the way."""
        place = place or alliances.Place(self, entry, "blue")
        holds, (inner, said) = self.season.holds_at(entry, place.spot, rest), self.unwrap(node, about)
        if holds == "shape" and shapes.is_shape(inner):
            return shapes.drawn(self, entry, inner, place.swapped)
        if holds in (*OUTLINES, "shape") and rest[-1] in ("outline", "bottom", "top") and isinstance(inner, (list, dict)):
            return outlines.drawn(self, entry, inner, place.swapped)
        if holds == "starts" and isinstance(inner, str) and inner in word_list("starts"):
            number = pieces.left_over(self, entry, rest[-1])
            return self.told(Value("number", number, printed=str(number)), said, entry)
        if holds == "says" and isinstance(inner, str):
            filled = says.fill(self, self.season.field_at(entry, place.spot, rest)[0], place.spot)
            return replace(self.value(filled.value, entry, holds), moves=filled.moves)
        return self.value(node, entry, holds, end, about=about)

    def _moved(self, place, steps):
        """The value of a path into a position that is not just what is written. Only the coordinate that is asked is worked out."""
        name, *steps = steps
        if name == "outline":
            name = f"outline.{steps.pop(0)}"
        if name == "faces":
            got = place.faces()
        elif steps and steps[0] in AXES:
            got = place.coordinate(*place.written(name), AXES.index(steps.pop(0)), made=name == "at")
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
        if TOLD_WHOLE.get(holds):
            call, how = f'{TOLD_WHOLE[holds]}("{path}")', ""
        elif holds == "list of points":
            call, how = f'points("{entry.path}")', ""
        elif holds == "cap" and "when" in rest:
            call, how = f'when("{".".join([entry.path, *rest[:rest.index("when") + 1]])}")', ""
        elif holds == "cap" and path == ".".join([entry.path, *rest[:-1]]):
            call, how = f'get("{path}")', f", as its {rest[-1]}"
        else:
            call, how = f'records("{entry.file}")', ", in the data of its record"
        return Told("", "is not one value", "Name a value", f"rules.{call} tells it{how}", find=entry.path)

    # -- one value

    def value(self, node, entry, holds="", end=None, name=None, about=None):
        """The Value of a node as it is written; a list for a list, and AnyOf for limits of which one is enough. about is what is said
        around it, to which its own is added."""
        node, said = self.unwrap(node, about)
        if holds in NOT_VALUES and not isinstance(node, (bool, str)) or holds.startswith("list of ") and holds != "list of texts":
            raise self.no_value(node)
        if isinstance(node, list):
            return [self.value(one, entry, holds, about=said) for one in node]
        if isinstance(node, dict) and isinstance(node.get("any"), list):
            return AnyOf(self.value(inner, entry, holds, name=n, about=said) for one in node["any"] for n, inner in one.items())
        if isinstance(node, dict) and isinstance(node.get("text"), str):
            return self.told(Value("text", node["text"], printed=node["text"]), said, entry, name)
        if isinstance(node, dict) or node is None:
            raise self.no_value(node)
        got = self._plain(node, holds)
        return self.told(one_end(got, end) if end else got, said, entry, name)

    def told(self, got, said, entry, name=None):
        """A Value with what is said beside it and around it: the one place where that becomes part of a Value."""
        return replace(got, of=said.get("of"), assumed=said.get("assumed"), src=said.get("src", entry.data.get("src")), differs=tuple(said.get("differs", ())),
                       each=said.get("each"), when=conditions.moments(self.book, said.get("when", ())), name=name)

    def unwrap(self, node, about=None):
        """(the node that another one stands for, through `is` and `by`; what is said beside it, over what is said around it)."""
        return self.book.opened(node, self.choice, about=about)

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
        """Note that something is being worked out, until season.doing.pop(). What needs itself is a Loop; the same text for other
        variants is something else."""
        doing = self.season.doing
        if (self, text) in doing:
            raise Loop([*(one for _, one in doing[doing.index((self, text)):]), text])
        doing.append((self, text))

    def formula(self, text):
        """The Value that a formula gives, printed in the unit of the first value of its kind that it names; in inches for feet, in seconds for minutes."""
        self.begin(text)
        try:
            kind, number = formulas.work(text, lambda path: self._named(text, path))
            named = [self.get(path) for path in paths_in(text)]
            units = [value.unit for value in named if value.kind == kind and value.unit]
        except Wrong:
            raise
        except DesignError as problem:
            raise Wrong(text, "", problem.problem, problem.fix) from None
        finally:
            self.season.doing.pop()
        unit = worked(units[0]) if units else BASE.get(kind, kind if kind != "number" else None)
        return Value(kind, number, printed=shown(number, kind, unit), unit=unit, moves=any(value.moves for value in named))

    def _named(self, text, path):
        """(kind, number) of a value that a formula names."""
        try:
            value = self.get(path)
            number = one_number(value)
            if value.each or value.when:
                raise DesignError("", f"is {f'for each {value.each}' if value.each else 'only for some times'}", "Name the count for the whole, or print it; what starts where in all is in rules.starts")
            return value.kind, number
        except Wrong:
            raise
        except DesignError as problem:
            raise DesignError("", f'the formula "{text}" names {path}, which {problem.problem}', problem.fix) from None
