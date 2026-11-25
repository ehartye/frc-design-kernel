"""Where a record stands: for blue, for red and at each of its spots.

    Place(worker, entry, alliance, spot)    point(name) gives its at, from or to; faces(), which way it looks; xy(x, y) moves a point
    moves(entry, name)                      whether a field of a record is a position, which changes with the alliance
    holds_places(key, steps)                whether a property is for positions or a direction
    sort_at(key, steps)                     the Sort (worth.py) of what is at some steps inside a property
    spots(entry)                            the names of its spots
    size(worker, i)                         the field's length (0) or width (1) in mm

Red is made from blue by the record's own symmetry, or else the field's. A spot of a pattern is made from its first one:
a row steps, and a ring goes anticlockwise and turns the way that its spots look.
"""
import math

from ..errors import DesignError, unknown
from . import fields, worth
from .read import AXES, is_pattern, names, spot_data, spot_names

MOVES = ("at", "faces", "from", "to", "outline")
POSITIONS = ("placed.at", "spot.at", "tag.at", "line.from", "line.to", "ring.around", "zone.outline")       # properties that hold positions
DIRECTIONS = ("placed.faces", "spot.faces", "tag.faces")


def moves(entry, name):
    spec = fields.spec_for(entry)
    return name in MOVES and spec is not None and entry.kind != "tag" and {name, "faces"} <= set(spec.known)


def holds_places(key, steps):
    """Whether a property is for positions or a direction, at some steps inside it: an outline is, where its points are listed."""
    return key in (*POSITIONS, *DIRECTIONS) and not (key == "zone.outline" and set(steps) & set(names()["outlines"]))


def sort_at(key, steps):
    """The Sort of what is at some steps inside a property, when the property says it: a position, a direction, a height, or the field's size; else None."""
    if key in ("size.length", "size.width"):
        return worth.STILL
    if key in DIRECTIONS:
        return worth.DIRECTION
    axes = [step for step in steps if step in AXES][1 if key == "zone.outline" else 0:]
    if not axes or not holds_places(key, steps):
        return None
    return {"x": worth.X, "y": worth.Y, "z": worth.STILL}[axes[0]]


def spots(entry):
    return spot_names(entry.data.get("spots"))


def check_spot(entry, spot):
    """That a record has a spot of this name, when one is named."""
    if spot is not None and spot not in spots(entry):
        raise unknown(entry.path, "spot", spot, spots(entry))


def size(worker, i):
    """The field's length (0) or width (1) in mm."""
    path = ("size.length", "size.width")[i]
    return worth.one_number(worker.get(path))


def numbers(values):
    """The numbers of a position, (x, y) or with a third one; a DesignError when one is a range."""
    return tuple(worth.one_number(value) for value in values)


def direction(degrees):
    """An angle from 0 up to, not including, 360 deg."""
    degrees %= 360
    return 0.0 if 360 - degrees < 1e-9 else degrees


class Place:
    """One place where a record stands: for an alliance and, when it has spots, at one of them."""

    def __init__(self, worker, entry, alliance, spot=None):
        self.worker, self.entry, self.spot = worker, entry, spot
        check_spot(entry, spot)
        self.red = alliance == "red" and entry.data.get("alliance") == "each"
        written = entry.data.get("spots")
        self.pattern = written if spot is not None and is_pattern(written) else None
        self.data = {**entry.data, **spot_data(written, spot)} if spot is not None else entry.data

    @property
    def as_written(self):
        """Whether its position is just what is written: blue's, and not made by a pattern."""
        return not self.red and not self.pattern

    @property
    def mirrored(self):
        """Whether red's copy is a mirror image of blue's, and not a turned one."""
        return self.data.get("symmetry", self.worker.book.data.get("field", {}).get("symmetry")) == "mirror"

    @property
    def swapped(self):
        """Whether left and right change places in what is drawn here: a shape or an opening that is a mirror image."""
        return self.red and self.mirrored

    def written(self, name):
        """The coordinates of its at, from or to, as they are written."""
        known = spots(self.entry)
        if name not in self.data and name == "at" and known:
            listed = ", ".join(known)
            raise worth.Told("", f"stands at {len(known)} spots", f"Name one spot: {listed}", f'Name one with spot=, such as spot="{known[0]}": {listed}', f"Name one with --spot: {listed}")
        if name not in self.data:
            raise unknown("", "field", name, self.data)
        return self.coordinates(self.data[name])

    def coordinates(self, node):
        """The nodes of a point: two or three."""
        return self.worker.unwrap(node)[0]

    def point(self, name):
        """Its at, from or to, where it is: two Values or three."""
        nodes = self.written(name)
        return [self.coordinate(nodes, i, made=name == "at") for i in range(len(nodes))]

    def coordinate(self, nodes, i, made):
        """One coordinate of a point, moved to this alliance and, if a pattern made the point, to this spot."""
        if i >= len(nodes):
            raise unknown("", "field", AXES[i], AXES[:len(nodes)])
        value = self.worker.value(nodes[i], self.entry, "length")
        number, sign = worth.one_number(value), 1
        if made and self.pattern and self._index:
            number, sign = self._in_pattern(nodes, i, number)
        if self.red and (i == 0 or i == 1 and not self.mirrored):
            number, sign = size(self.worker, i) - number, sign and -sign
        return worth.moved(value, number, sign)

    def xy(self, x, y):
        """A point of blue's, in mm, where it is for this alliance."""
        if not self.red:
            return x, y
        return size(self.worker, 0) - x, y if self.mirrored else size(self.worker, 1) - y

    def faces(self):
        """Which way it looks."""
        if "faces" in self.data:
            got = self.worker.value(self.data["faces"], self.entry, "angle")
        else:
            got = worth.Value("angle", 0.0, printed="0 deg", src=self.entry.data.get("src"), unit="deg")
        angle = worth.one_number(got)
        if self.pattern and "ring" in self.pattern and self._index:
            angle = direction(angle + self._number(self.pattern["step"], "angle") * self._index)
        if self.red:
            angle = direction(180 - angle if self.mirrored else angle + 180)
        return worth.moved(got, angle, -1 if self.swapped else 1)

    # -- patterns

    @property
    def _index(self):
        """Which one of a row or a ring it is, from 0."""
        outer = list(dict.fromkeys(name.partition(".")[0] for name in spots(self.entry)))
        return outer.index(self.spot.partition(".")[0])

    def _in_pattern(self, nodes, i, number):
        """(a coordinate of a spot that is made from the first one, the sign of its axis there or None)."""
        if "row" in self.pattern:
            step = self.coordinates(self.pattern["step"])
            return number + (self._number(step[i], "length") * self._index if i < len(step) else 0), 1
        if i > 1:
            return number, 1
        x, y = (self._number(nodes[k], "length") - self._number(self.coordinates(self.pattern["around"])[k], "length") for k in (0, 1))
        turn = math.radians(self._number(self.pattern["step"], "angle") * self._index)
        middle = number - (x, y)[i]
        return middle + (x * math.cos(turn) - y * math.sin(turn) if i == 0 else x * math.sin(turn) + y * math.cos(turn)), None

    def _number(self, node, holds):
        return worth.one_number(self.worker.value(node, self.entry, holds))
