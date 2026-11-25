"""One value of a rules folder: a printed number, words or a list, in base units.

    Value                its kind, its number in mm, kg, s or degrees, its limit, its ends, and where it comes from
    AnyOf                a list of Values, one of which is enough
    Wrong                the DesignError of a formula, which is told where it is written
    one_number(value)    its number, or a DesignError when it has none, such as a range
    one_end(value, end)  the low or the high end of a range or a tolerance
    moved(value, ...)    a position's number somewhere else
    shown, words_of      how a number or a Value is printed
"""
from dataclasses import dataclass, replace

from ..errors import DesignError
from . import quantity

BASE = {"length": "mm", "mass": "kg", "time": "s", "angle": "deg"}
WORKED = {"ft": "in", "min": "s"}       # nobody reads a decimal foot or a decimal minute


@dataclass(frozen=True)
class Value:
    """One value. A range has no value of its own, only its ends."""
    kind: str                           # length, mass, time, angle, number, flag, text, a printed unit, or any or none for no limit
    value: float | bool | str | None    # in mm, kg, s or degrees; None for a range and for no limit
    limit: str | None = None            # "at most", "at least", "less than" or "more than"
    low: float | None = None            # the ends of a range or a tolerance
    high: float | None = None
    printed: str = ""                   # as it is printed; for what nobody printed, the number worked out, in inches for feet and in seconds for minutes
    of: str | None = None               # what is measured
    assumed: str | None = None          # why it was chosen, when no source prints it
    src: object = None                  # where it is written: its own source, or its record's
    differs: tuple = ()                 # what other sources say, as it is written
    name: str | None = None             # its name in a list of which one is enough
    unit: str | None = None             # the unit it is printed in

    @property
    def number_words(self):
        """As it is printed, without the words of a limit."""
        return self.printed[len(self.limit) + 1:] if self.limit else self.printed


class AnyOf(list):
    """Values, one of which is enough."""


class Wrong(DesignError):
    """A formula that cannot be worked out, and its text."""

    def __init__(self, text, where, problem, fix=""):
        super().__init__(where, problem, fix)
        self.text = text

    def under(self, prefix):
        return self


def worked(unit):
    """The unit that a worked-out number is printed in: inches where its values are in feet, and seconds where they are in minutes."""
    return WORKED.get(unit, unit)


def shown(number, kind, unit):
    """A number in base units as it would be printed: at most 4 decimals, and its unit."""
    if unit is not None and kind in BASE:
        number = quantity.convert(number, kind, unit)
    text = f"{round(number, 4):.10f}".rstrip("0").rstrip(".")
    text = "0" if text == "-0" else text
    return text if kind == "number" else f"{text} {unit}"


def one_number(value):
    """The number of a Value, or a DesignError when it has none."""
    if not isinstance(value, Value):
        raise DesignError("", f"is {'a list' if isinstance(value, list) else 'a shape'}, not one number", "Name one of its numbers")
    if value.value is None and value.low is not None:
        raise DesignError("", "is a range, and has no one number", "Write .low or .high after it")
    if value.value is None or isinstance(value.value, (bool, str)):
        raise DesignError("", "is not a number", "Name a number")
    return value.value


def one_end(value, end):
    """The low or the high end of a range or a tolerance, as a Value."""
    number = getattr(value, end)
    if number is None:
        raise DesignError("", f"is one number, and has no {end} end", "Only a range or a tolerance has .low and .high")
    unit = value.unit if value.value is None else worked(value.unit)       # the end of a range is printed; that of a tolerance is worked out
    return replace(value, value=number, limit=None, low=None, high=None, printed=shown(number, value.kind, unit), unit=unit)


def moved(value, number, sign=None):
    """A position's number somewhere else. The ends of a tolerance go along: sign is -1 where the direction turns round; None
    drops them, where a direction is no longer along an axis."""
    if number == value.value:
        return value
    low = high = None
    if sign is not None and value.low is not None:
        low, high = sorted(number + sign * (end - value.value) for end in (value.low, value.high))
    unit = worked(value.unit)
    return replace(value, value=number, limit=None, low=low, high=high, printed=shown(number, value.kind, unit), unit=unit)


def words_of(value):
    """A value as `says` prints it: without the words of a limit."""
    if isinstance(value, AnyOf):
        return " or ".join(f"{one.number_words} ({one.name})" for one in value)
    if isinstance(value, list):
        return ", ".join(words_of(one) for one in value)
    return value.number_words
