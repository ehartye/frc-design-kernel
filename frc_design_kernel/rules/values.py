"""What a field holds: values, words of a list, sources, history, positions and shapes.

    Reader(book, faults)    read(entry, node, where, holds) and value(entry, node, kind, where): the Leaves of one field
    Leaf                    one value as it is written: a printed number, formula, count or flag
    is_group(node)          whether an object is a group of values, and not a value itself

Values that are worked out later are left alone: a formula is a Leaf whose node starts with "=". A Leaf's kind is what its
field holds (length, mass, time, angle, number, flag, or a printed unit such as AWG), or None for an extra value. What is
wrong is added to the list of faults, so that one wrong value does not hide the next.
"""
import datetime
import difflib
import re
from dataclasses import dataclass

from ..errors import DesignError, unknown
from . import quantity
from .read import AXES, ID, Entry, names, word_list

NEARLY = 0.85                               # a name this close to a known one is a slip (difflib's ratio)
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
TIMER = re.compile(r"([0-9]+):([0-5][0-9])")
STANDS_FOR = {"is", "by", "any", "text"}    # a JSON object with one of these is a value; any other is a group of values
A_TEXT = 'Write an extra text as {"text": ...}'


@dataclass(frozen=True)
class Leaf:
    """One value as it is written: a number, true or false, a printed number or a formula."""
    entry: Entry
    where: str
    kind: str | None
    node: object


def place(where, i, many):
    """The place of one value of a list: .x, .y or .z, or [i] in a longer list."""
    return f"{where}.{AXES[i]}" if many <= len(AXES) else f"{where}[{i}]"


def is_group(node):
    return isinstance(node, dict) and bool(node) and not STANDS_FOR & set(node)


def slip(where, name, known, faults):
    """Whether a name is no field name, or nearly a known one; the fault says which."""
    near = difflib.get_close_matches(name, known, 1, NEARLY)
    if near and name not in known:
        faults.append(DesignError(where, f'the field "{name}" is nearly "{near[0]}"', f'Write "{near[0]}", or choose a name that is not so close to it'))
        return True
    if not ID.fullmatch(name):
        faults.append(DesignError(where, f'"{name}" is not a field name', "Start with a letter and use letters, digits and underscores"))
        return True
    return False


def a_list(node, where, faults):
    if not isinstance(node, list):
        faults.append(DesignError(where, "is not a list", "Write it between [ and ]"))
    return node if isinstance(node, list) else []


class Reader:
    """Reads what a field holds. A fault is added to a list, so that one wrong value does not hide the next."""

    def __init__(self, book, faults):
        self.book, self.faults, self.beside = book, faults, []

    def fault(self, where, problem, fix):
        self.faults.append(DesignError(where, problem, fix))

    def read(self, entry, node, where, holds):
        """The Leaves of one field, for what fields.json says that it holds."""
        first, _, rest = holds.partition(" ")
        if holds in ("extra", "group"):
            return () if is_group(node) else self.value(entry, node, None, where, loose=True)
        if holds == "value":
            return self.value(entry, node, None, where, loose=True)
        if holds in ("piece count", "after period"):
            return self.value(entry, node, "number" if holds == "piece count" else "time", where)
        if rest == "lengths":
            return self.holds_point(entry, node, where, sizes=(int(first),))
        if first in ("word", "words"):
            return self.words(node, rest, where, many=first == "words")
        method = getattr(self, "holds_" + holds.replace(" ", "_"), None)
        if method:
            return method(entry, node, where)
        return self.value(entry, node, holds, where) if self.is_kind(holds) else ()

    def is_kind(self, holds):
        return holds in (*names()["units"], "number", "flag", *names()["kept"]["units"])

    # -- one value

    def value(self, entry, node, kind, where, loose=False, also=(), words=()):
        """The Leaves of one value. A loose one may be a list or words in {"text": ...}; also names more fields of its object;
        words are those that may stand in its place."""
        for inner, at in self.unwrapped(entry, node, where, also):
            if isinstance(inner, dict):
                yield from self._object_value(entry, inner, kind, at, loose)
            elif isinstance(inner, list) and loose and inner:
                for i, one in enumerate(inner):
                    yield from self.value(entry, one, kind, place(at, i, len(inner)), loose)
            elif inner not in words and self._plain(inner, kind, at, loose, words):
                yield Leaf(entry, at, kind, inner)

    def _plain(self, node, kind, where, loose, words):
        """Whether a plain value is a formula, or reads as its kind; a fault says why not."""
        if isinstance(node, str) and node.startswith("="):
            return True
        or_words = "".join(f', or "{word}"' for word in words)
        try:
            got = "flag" if isinstance(node, bool) else quantity.count(node).kind if isinstance(node, (int, float)) else quantity.read(node).kind if isinstance(node, str) else None
        except DesignError as problem:
            if loose and not re.match(r"-?[0-9]|" + "|".join(word_list("limit")), node):
                self.fault(where, f'"{node}" is words, not a value', A_TEXT)
            else:
                self.fault(where, problem.problem, problem.fix + or_words if kind != "flag" else "Write true or false")
            return False
        if got is None:
            self.fault(where, "is a list, not one value" if isinstance(node, list) else "is not a value", quantity.HOW_TO_WRITE + or_words)
        elif kind not in (None, got):
            self.fault(where, f"holds {_a(got)}, not {_a(kind)}", f"Write {_a(kind)}{or_words}")
        return got is not None and kind in (None, got)

    def _object_value(self, entry, node, kind, where, loose):
        """The Leaves of {"any": [...]}; {"text": ...} has none."""
        if set(node) == {"any"}:
            limits = node["any"] if isinstance(node["any"], list) else []
            if not limits or not all(isinstance(one, dict) and one for one in limits):
                self.fault(where, "does not list limits, one of which is enough", '{"any": [{"deep": "at most 1 in"}, {"wide": "at most 9 in"}]}')
                return
            for i, one in enumerate(limits):
                for name, inner in one.items():
                    slip(f"{where}.any[{i}]", name, {}, self.faults)
                    yield from self.value(entry, inner, kind, f"{where}.any[{i}].{name}")
        elif loose and "text" in node:
            self._about(entry, {k: v for k, v in node.items() if k != "text"}, where, ())
            self.text(node["text"], f"{where}.text")
        else:
            self.fault(where, "is not a value", quantity.HOW_TO_WRITE)

    def unwrapped(self, entry, node, where, also=()):
        """(data, place) for each thing that a node may stand for, through `is` and through every variant of `by`."""
        if isinstance(node, dict) and "by" in node:
            for name in self.chosen(node, where):
                yield from self.unwrapped(entry, node[name], f"{where}.{name}")
        elif isinstance(node, dict) and "is" in node:
            self._about(entry, {k: v for k, v in node.items() if k != "is"}, where, also)
            yield from self.unwrapped(entry, node["is"], f"{where}.is")
        else:
            yield node, where

    def chosen(self, node, where):
        """The variants that a value with `by` has, and a fault for one that is missing or not there."""
        kind = node["by"]
        known = self.book.variants.get(kind) if isinstance(kind, str) else None
        if known is None:
            self.faults.append(unknown(where, "kind of variant", kind, self.book.variants))
            return []
        for name in known:
            if name not in node:
                self.fault(where, f'has no "{name}", a variant of {kind}', "Write every variant, or one value without by")
        for name in node:
            if name != "by" and name not in known:
                self.faults.append(unknown(where, f"variant of {kind}", name, known))
        return [name for name in known if name in node]

    def _about(self, entry, about, where, also):
        """The fields beside `is`: where a value comes from, what it was and what differs. Their Leaves are kept in self.beside."""
        known = {name: one["holds"] for name, one in names()["kinds"]["value"]["fields"].items()}
        for name, node in about.items():
            at = f"{where}.{name}"
            if name in also:
                continue
            if name not in known:
                self.faults.append(unknown(where, "field of a value", name, [*known, *also]))
            elif known[name] == "text":
                self.text(node, at)
            else:
                self.beside.extend(getattr(self, "holds_" + known[name])(entry, node, at))

    # -- words

    def text(self, node, where):
        if not isinstance(node, str) or not node.strip():
            self.fault(where, "is not words", "Write words between quotes")

    def words(self, node, known, where, many=False):
        """A word of a list in fields.json, or several."""
        for i, word in enumerate(node if many and isinstance(node, list) else [node]):
            if word not in word_list(known):
                self.faults.append(unknown(f"{where}[{i}]" if isinstance(node, list) and many else where, "word", word, word_list(known)))
        return ()

    def holds_text(self, entry, node, where):
        self.text(node, where)
        return ()

    holds_says = holds_text     # words.py reads the names in it

    def holds_texts(self, entry, node, where):
        for i, one in enumerate(node if isinstance(node, list) else [node]):
            self.text(one, f"{where}[{i}]" if isinstance(node, list) else where)
        return ()

    def holds_list_of_texts(self, entry, node, where):
        return self.holds_texts(entry, a_list(node, where, self.faults), where)

    # -- where a value comes from

    def holds_src(self, entry, node, where):
        if node == []:
            self.fault(where, "names no source", "Name one, such as \"manual 3.2\"")
        for i, one in enumerate(node if isinstance(node, list) else [node]):
            at = f"{where}[{i}]" if isinstance(node, list) else where
            first = one.split(" ")[0] if isinstance(one, str) else one
            if not isinstance(one, str) or first not in self.book.sources and "sources" not in self.book.missing:
                self.faults.append(unknown(at, "source", first, self.book.sources))
        return ()

    def holds_differs(self, entry, node, where, dated=False):
        """What other sources say (`differs`), or what it was until a date (`was`)."""
        about = names()["kinds"]["was" if dated else "differs"]
        for i, one in enumerate(a_list(node, where, self.faults)):
            at = f"{where}[{i}]"
            if not isinstance(one, dict):
                self.fault(at, "is not an object", "Write its fields between { and }")
                continue
            for name in about["needs"]:
                if name not in one:
                    self.fault(at, f'has no "{name}"', f'Add "{name}"')
            if not set(about["any_of"]) & set(one):
                self.fault(at, f"does not say what it is: it has no {' or '.join(about['any_of'])}", "Write the value as is, or the words as says")
            for name, inner in one.items():
                if name not in about["fields"]:
                    self.faults.append(unknown(at, "field", name, about["fields"]))
                else:
                    yield from self.read(entry, inner, f"{at}.{name}", about["fields"][name]["holds"])

    def holds_was(self, entry, node, where):
        return self.holds_differs(entry, node, where, dated=True)

    def holds_date(self, entry, node, where):
        try:
            datetime.date.fromisoformat(node if DATE.fullmatch(node) else "")
        except (TypeError, ValueError):
            self.fault(where, f'"{node}" is not a date', 'Write a date such as "2031-02-04"')
        return ()

    # -- counts

    def holds_height(self, entry, node, where):
        return self.value(entry, node, "length", where, words=word_list("height"))

    def holds_by_piece(self, entry, node, where, words=()):
        if not isinstance(node, dict):
            self.fault(where, "is not counts by piece", '{"bale": 3}')
            return
        for piece, many in node.items():
            yield from self.value(entry, many, "number", f"{where}.{piece}", words=words)

    def holds_starts(self, entry, node, where):
        return self.holds_by_piece(entry, node, where, word_list("starts"))

    def holds_hold_limit(self, entry, node, where):
        return self.holds_by_piece(entry, node, where) if is_group(node) else self.value(entry, node, "number", where)

    def holds_cap(self, entry, node, where):
        return self.value(entry, node, "number", where, also=("when",))

    def holds_circuits(self, entry, node, where):
        return self.value(entry, node, "number", where, words=word_list("no_limit"))

    def holds_on(self, entry, node, where):
        if not isinstance(node, dict):
            self.fault(where, "does not say how many one device of each kind may run", '{"controller": 1, "relay": 1}')
            return
        for kind, many in node.items():
            if kind not in word_list("device"):
                self.faults.append(unknown(where, "kind of device", kind, word_list("device")))
            else:
                yield from self.holds_circuits(entry, many, f"{where}.{kind}")

    def holds_timer(self, entry, node, where):
        read = [TIMER.fullmatch(one) if isinstance(one, str) else None for one in (node if isinstance(node, list) else [])]
        seconds = [int(m[1]) * 60 + int(m[2]) for m in read if m]
        if len(read) != 2 or len(seconds) != 2 or seconds[0] <= seconds[1]:
            self.fault(where, "is not two times of the match timer, the first one earlier", 'The timer counts down: ["1:15", "0:50"]')
        return ()

    def holds_variants(self, entry, node, where):
        for kind, given in node.items() if isinstance(node, dict) else ():
            good = isinstance(given, list) and given and all(isinstance(one, str) and ID.fullmatch(one) for one in given) and len(set(given)) == len(given)
            if not good or not ID.fullmatch(kind):
                self.fault(f"{where}.{kind}", "is not a list of names, each there once", '"field": ["welded", "bolted"]')
        return ()

    # -- positions and shapes

    def holds_point(self, entry, node, where, sizes=(2, 3)):
        for inner, at in self.unwrapped(entry, node, where):
            if not isinstance(inner, list) or len(inner) not in sizes:
                self.fault(at, f"is not a list of {' or '.join(map(str, sizes))} lengths", 'Write lengths, such as ["27 in", "40 in"]')
                continue
            for i, one in enumerate(inner):
                yield from self.value(entry, one, "length", place(at, i, len(inner)))

    def holds_outline(self, entry, node, where):
        for inner, at in self.unwrapped(entry, node, where):
            if isinstance(inner, list) and len(inner) >= 3:
                for i, one in enumerate(inner):
                    yield from self.holds_point(entry, one, f"{at}[{i}]", sizes=(2,))
            elif isinstance(inner, dict):
                yield from self._drawn(entry, inner, at, names()["outlines"], "outline")
            else:
                self.fault(at, "is not an outline", 'Write three points or more, or {"rectangle": [...]}, {"hexagon": {...}} or {"circle": ...}')

    def holds_shape(self, entry, node, where):
        for inner, at in self.unwrapped(entry, node, where):
            yield from self._drawn(entry, inner, at, names()["shapes"], "shape")

    def _drawn(self, entry, node, where, forms, what):
        """One shape or outline: a JSON object with one name of the forms, and the sizes that this form has."""
        if not isinstance(node, dict) or len(node) != 1:
            self.fault(where, f"is not one {what}", f"Write one of {', '.join(forms)}")
            return
        name, sizes = next(iter(node.items()))
        at, form = f"{where}.{name}", forms.get(name)
        if form is None:
            self.faults.append(unknown(where, what, name, forms))
        elif "fields" in form:
            yield from self._sizes(entry, sizes, at, form["fields"])
        else:
            yield from self.read(entry, sizes, at, form["holds"])

    def _sizes(self, entry, node, where, form):
        if not isinstance(node, dict):
            self.fault(where, "is not an object", f"Write its {', '.join(form)} between {{ and }}")
            return
        for name in form:
            if name not in node and not form[name].get("optional"):
                self.fault(where, f'has no "{name}"', f'Add "{name}"')
        for name, inner in node.items():
            if name not in form:
                self.faults.append(unknown(where, "size", name, form))
            else:
                yield from self.read(entry, inner, f"{where}.{name}", form[name]["holds"])

    def holds_shapes(self, entry, node, where):
        """The shapes of a join or a cut, each with its own `at`."""
        shapes = a_list(node, where, self.faults)
        if isinstance(node, list) and not shapes:
            self.fault(where, "has no shapes in it", 'List shapes, each with its own "at"')
        for i, one in enumerate(shapes):
            at = f"{where}[{i}]"
            if not isinstance(one, dict) or "at" not in one:
                self.fault(at, 'has no "at"', 'Give each shape of a join or a cut its own "at"')
                continue
            yield from self.holds_point(entry, one["at"], f"{at}.at")
            yield from self._drawn(entry, {k: v for k, v in one.items() if k != "at"}, at, names()["shapes"], "shape")


def _a(kind):
    """A kind in words."""
    words = {"number": "a count", "flag": "true or false", "angle": "an angle"}
    return words.get(kind, f"a {kind}" if kind in names()["units"] else f"a number of {kind}")
