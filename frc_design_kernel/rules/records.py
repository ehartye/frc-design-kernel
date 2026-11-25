"""Every record of a file, with red's made from blue's and every spot made.

    records(worker, file)    Records in the order written: blue's, its spots, red's, its spots

A record's name is a path to it: crate@red, rack@red.3.b, or centre_bales.spots.a for a spot of what neither alliance owns.
"""
from dataclasses import dataclass

from ..errors import unknown
from . import outlines
from .alliances import Place, moves, numbers, spots
from .read import ALLIANCES, Entry, names
from .worth import one_number


@dataclass(frozen=True)
class Record:
    """One record, for one alliance and one spot. Positions are in mm and degrees; None is for what it has not."""
    name: str
    entry: Entry
    alliance: str | None
    spot: str | None
    data: dict              # its fields as they are written; a spot has its record's too
    at: tuple | None
    faces: float | None
    outline: list | None
    ends: tuple | None      # the two ends of a line


def records(worker, file):
    if file not in names()["files"]:
        raise unknown("", "file", file, names()["files"])
    return [record for entry in worker.book.entries if entry.file == file and entry.path for record in _of(worker, entry)]


def _of(worker, entry):
    """A record for each alliance, and one for each spot of each."""
    each = entry.data.get("alliance") == "each"
    for alliance in ALLIANCES if each else (None,):
        name = f"{entry.path}@{alliance}" if each else entry.path
        yield _one(worker, entry, name, alliance, None)
        for spot in spots(entry):
            yield _one(worker, entry, f"{name}.{spot}" if each else f"{name}.spots.{spot}", alliance, spot)


def _one(worker, entry, name, alliance, spot):
    if entry.kind == "tag":
        at = numbers(worker.get(f"{entry.path}.at")) if "at" in entry.data else None
        return Record(name, entry, None, None, entry.data, at, one_number(worker.get(f"{entry.path}.faces")) if "faces" in entry.data else None, None, None)
    if not moves(entry, "faces"):
        return Record(name, entry, alliance, spot, entry.data, None, None, None, None)
    place = Place(worker, entry, alliance or "blue", spot)
    at = numbers(place.point("at")) if "at" in place.data else None
    ends = tuple(numbers(place.point(end)) for end in ("from", "to")) if moves(entry, "from") and {"from", "to"} <= set(place.data) else None
    drawn = "outline" in place.data and moves(entry, "outline") and (at is not None or isinstance(worker.unwrap(place.data["outline"])[0], list))
    return Record(name, entry, alliance, spot, place.data, at, one_number(place.faces()) if at is not None else None,
                  outlines.on_field(place, place.data["outline"]) if drawn else None, ends)
