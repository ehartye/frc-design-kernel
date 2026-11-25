"""A number as it is printed ("5 ft 4 3/8 in", "at most 6 A", "0.7 to 0.9 lb") in base units: mm, kg, s and degrees.

    read(text)                a Quantity, or a DesignError that says what is wrong with the text
    count(number)             a Quantity for a plain JSON number
    convert(value, kind, to)  a base-unit value in another unit of its kind

Degrees stay degrees here. A formula that needs radians converts for itself.
"""
import math
import re
from dataclasses import dataclass
from fractions import Fraction

from ..errors import DesignError, unknown
from .read import names

PLUS = r"(?:[0-9]+ [0-9]+/[0-9]+|[0-9]+/[0-9]+|[0-9]+(?:\.[0-9]+)?)"
NUMBER = "-?" + PLUS
UNIT = r"[A-Za-z][A-Za-z0-9/]*"
FORMS = {
    "range": re.compile(rf"({NUMBER}) to ({NUMBER})(?: ({UNIT}))?"),
    "both": re.compile(rf"({NUMBER}) ({UNIT}) \+/- ({PLUS})"),
    "sides": re.compile(rf"({NUMBER}) ({UNIT}) \+({PLUS}) -({PLUS})"),
    "joined": re.compile(rf"({PLUS}) ({UNIT}) ({PLUS}) ({UNIT})"),
    "plain": re.compile(rf"({NUMBER})(?: ({UNIT}))?"),
}
HOW_TO_WRITE = 'Write it as printed: "71 in", "5 ft 4 3/8 in", "at most 6 A", "0.7 to 0.9 lb", "6.4 oz +/- 0.3"; a count is a number without quotes'


@dataclass(frozen=True)
class Quantity:
    """A printed number. A range has no value of its own, only its two ends; a limit has a value and its limit's words."""
    kind: str               # length, mass, time, angle, number, or the printed unit when it does not convert
    value: float | None     # in the base unit of the kind; None for a range
    unit: str | None        # the unit as printed (the larger of two joined ones); None for a count
    limit: str | None       # "at most", "at least", "less than" or "more than"
    low: float | None       # the ends of a range or a tolerance
    high: float | None
    printed: str


def kind_of(unit):
    """The kind that a unit measures: length, mass, time, angle, or the unit itself when it does not convert."""
    for kind, units in names()["units"].items():
        if unit in units:
            return kind
    if unit not in names()["kept"]:
        raise unknown("", "unit", unit, all_units())
    return unit


def all_units():
    return [u for units in names()["units"].values() for u in units] + names()["kept"]


def factor(unit):
    """How many base units one of this unit is."""
    return Fraction(str(names()["units"].get(kind_of(unit), {}).get(unit, 1)))


def exact(number):
    """A printed number, such as -4 3/8, as an exact fraction."""
    sign = -1 if number.startswith("-") else 1
    return sign * sum((Fraction(part) for part in number.lstrip("-").split(" ")), Fraction(0))


def ordinary(number, text):
    try:
        return float(number)
    except OverflowError:
        raise DesignError("", f'"{text}" is not an ordinary number', "Check its digits") from None


def read(text):
    """The Quantity that a printed text stands for."""
    limit = next((w for w in names()["limit_words"] if text.startswith(w + " ")), None)
    rest = text[len(limit) + 1:] if limit else text
    form, found = next(((f, m) for f, p in FORMS.items() if (m := p.fullmatch(rest))), (None, None))
    if form is None or form == "plain" and found[2] is None and not limit:
        raise DesignError("", f'"{text}" is not a number as RULES.md section 3 writes one', HOW_TO_WRITE)
    if limit and form not in ("plain", "joined"):
        raise DesignError("", f'"{text}" puts a limit on a range or a tolerance', "Write only one of them")
    try:
        return _quantity(form, found, limit, text)
    except ZeroDivisionError:
        raise DesignError("", f'"{text}" divides by zero', HOW_TO_WRITE) from None
    except ValueError as problem:
        if isinstance(problem, DesignError):
            raise
        raise DesignError("", f'"{text[:40]}..." is not an ordinary number', "Check its digits") from None    # too many digits


def _quantity(form, found, limit, text):
    unit = found[3] if form == "range" else found[2]
    kind, size = (kind_of(unit), factor(unit)) if unit else ("number", 1)
    value, low, high = None if form == "range" else exact(found[1]) * size, None, None
    if form == "range":
        low, high = exact(found[1]) * size, exact(found[2]) * size
        if low > high:
            raise DesignError("", f'"{text}" is a range whose low end is above its high end', "Write the low end first")
    elif form == "joined":
        if names()["joined"].get(unit) != found[4]:
            raise DesignError("", f'"{text}" joins {unit} with {found[4]}', "Only feet with inches and minutes with seconds may be joined")
        value += exact(found[3]) * factor(found[4])
    elif form in ("both", "sides"):
        up = exact(found[3]) * size
        low, high = value - (up if form == "both" else exact(found[4]) * size), value + up
    number = [None if n is None else ordinary(n, text) for n in (value, low, high)]
    return Quantity(kind, number[0], unit, limit, number[1], number[2], text)


def count(number):
    """The Quantity for a plain JSON number, such as 45."""
    if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(ordinary(number, number)):
        raise DesignError("", f"{number} is not an ordinary number", "Write a number such as 45")
    return Quantity("number", number, None, None, None, None, str(number))


def convert(value, kind, to):
    """A value of a kind, in base units, given in the unit to."""
    if to not in all_units() or kind_of(to) != kind:
        fits = list(names()["units"].get(kind, [kind] if kind in names()["kept"] else []))
        raise unknown("", f"unit for a {kind}", to, fits)
    return value / float(factor(to))
