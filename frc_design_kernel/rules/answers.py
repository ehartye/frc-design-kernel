"""What Rules.get gives, told: as lines of text, and as plain data.

    lines(rules, path, got, unit)    the lines that tell it, with where it comes from
    plain(rules, got, unit)          the same for a program: JSON's own kinds

A number is told in its base unit (mm, kg, s, deg), or in the unit asked. An outline is points in mm or in the unit asked; a
shape is in the library's own grammar, in mm.
"""
import json
from dataclasses import asdict, replace

from ..errors import DesignError
from . import quantity
from .read import AXES, names
from .shapes import Taper
from .worth import BASE, AnyOf, Value, counted, shown


def plain(rules, got, unit=None):
    drawn = _drawn(got)
    if drawn == "outline":
        return _points(got, unit)
    if drawn:
        _no_unit(unit)
        return got if drawn == "shape" else {"taper": {"bottom": _points(got.bottom), "top": _points(got.top), "tall": got.tall}}
    if isinstance(got, list):
        inner = [plain(rules, one, unit) for one in got]
        return {"any": inner} if isinstance(got, AnyOf) else inner
    shown_in, (number, low, high) = _numbers(rules, got, unit)
    told = {name: one for name, one in asdict(replace(got, when=())).items() if name != "moves"}
    return {**told, "value": number, "low": low, "high": high, "unit": shown_in, "when": [moment.words for moment in got.when]}


def lines(rules, path, got, unit=None):
    drawn = _drawn(got)
    if drawn == "outline":
        return [f"{path}: points (x, y) in {unit or 'mm'}", *_lines_of_points(got, unit)]
    if drawn:
        _no_unit(unit)
    if drawn == "shape":
        return [f"{path}: a shape in mm, about its own 0, 0, 0", f"  {json.dumps(got)}"]
    if drawn == "taper":
        outlines = [line for name in ("bottom", "top") for line in (f"  {name}: points (x, y)", *("  " + one for one in _lines_of_points(getattr(got, name))))]
        return [f"{path}: a solid whose faces lean, in mm", *outlines, f"  tall: {shown(got.tall, 'number', None)}"]
    if isinstance(got, Value):
        return [f"{path}: {_text(rules, got, unit)}", *_about(got)]
    if not isinstance(got, AnyOf) and all(isinstance(one, Value) and one.kind == "text" for one in got) and _known(got) is not None:
        return [f"{path}: {_text(rules, got, unit)}", *_known(got)]
    return [f"{path}:{_enough(got)}", *_each(rules, got, unit)]


def _enough(got):
    return " one of these is enough" if isinstance(got, AnyOf) else ""


def _known(got):
    """What is known of every value in a list, when it is the same for all; else None."""
    if isinstance(got, Value):
        return _about(got)
    every = [_known(one) for one in got]
    return (every[0] if every else []) if all(one == every[0] for one in every) else None


def _each(rules, got, unit):
    """A line for each value of a list, and what is known of it: once at the end, when it is the same for all."""
    once, found = _known(got), []
    for i, one in enumerate(got):
        name = one.name if isinstance(got, AnyOf) and isinstance(one, Value) else AXES[i] if len(got) <= len(AXES) else i + 1
        known = _known(one)
        if known is None:
            found += [f"  {name}:{_enough(one)}", *("  " + line for line in _each(rules, one, unit))]
        else:
            found += [f"  {name}: {_text(rules, one, unit)}", *([] if once is not None else ("  " + line for line in known))]
    return found + (once or [])


def _text(rules, got, unit):
    """A value on one line: as it is printed, and then in its base unit; or in the unit asked alone; what it is for each of, and when."""
    if isinstance(got, AnyOf):
        return " or ".join(f"{_text(rules, one, unit)}{f' ({one.name})' if isinstance(one, Value) else ''}" for one in got)
    if isinstance(got, list):
        return ", ".join(f"[{_text(rules, one, unit)}]" if isinstance(one, list) else _text(rules, one, unit) for one in got) or "nothing"
    shown_in, numbers = _numbers(rules, got, unit)
    if got.kind in ("any", "none"):
        text = f"{got.printed} (no limit)"
    elif unit:
        text = f"{f'{got.limit} ' if got.limit else ''}{_in_unit(shown_in, numbers)}"
    else:
        text = got.printed if got.kind not in BASE or got.unit == shown_in else f"{got.printed} ({_in_unit(shown_in, numbers)})"
    return text + counted(got)


def _in_unit(unit, numbers):
    """A number and its two ends, as far as they are there: "215.9 mm, 209.55 to 222.25 mm"."""
    number, low, high = (None if one is None else shown(one, "number", None) for one in numbers)
    return ", ".join([*([] if number is None else [f"{number} {unit}"]), *([] if low is None else [f"{low} to {high} {unit}"])])


def _numbers(rules, value, unit):
    """(the unit asked or else the base unit, [the number, its low end, its high end] in it)."""
    if unit:
        rules.to(value, unit)       # whether it has one number, and is of the unit's kind
    unit = unit or BASE.get(value.kind) or (value.kind if value.kind in names()["kept"]["units"] else None)
    return unit, [number if number is None or not unit else quantity.convert(number, value.kind, unit) for number in (value.value, value.low, value.high)]


def _drawn(got):
    """"outline", "shape" or "taper", for what is drawn and is no value."""
    if isinstance(got, (Taper, dict)):
        return "taper" if isinstance(got, Taper) else "shape"
    return "outline" if isinstance(got, list) and got and isinstance(got[0], tuple) else None


def _points(points, unit=None):
    return [[quantity.convert(number, "length", unit or "mm") for number in point] for point in points]


def _lines_of_points(points, unit=None):
    return ["  " + ", ".join(shown(number, "number", None) for number in point) for point in _points(points, unit)]


def _no_unit(unit):
    if unit:
        raise DesignError("", "is for numbers, and this is a shape in mm", "Ask for one of its sizes, or leave the unit out")


def _about(value):
    """What is known of a value beside its number: what is measured, why it was chosen, its source and what others say."""
    found = [f"  {name}: {text}" for name, text in (("of", value.of), ("assumed", value.assumed), ("src", _listed(value.src))) if text]
    for other in value.differs:
        is_, where = other.get("is", other.get("says")), ", ".join(text for text in (other.get("of"), _listed(other["src"])) if text)
        found.append(f"  differs: {is_ if isinstance(is_, str) else json.dumps(is_)} ({where})")
    return found


def _listed(src):
    return ", ".join(src) if isinstance(src, list) else src
