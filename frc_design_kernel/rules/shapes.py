"""Shapes in the library's own grammar, in mm: what a solid of a design has as its `shape`.

    drawn(worker, entry, node, mirrored)    a shape about its own 0, 0, 0
    solid(place, node)                      {"shape", "place"}: a shape and where it stands, as a design's solid has them
    Taper                                   a solid whose faces lean, which the grammar has not: its two outlines and its height

What is round (a ball, a ring, a cylinder, a tube) is about its own centre, because an engine places a piece by its centre.
All else stands on 0, above the point that its record's `at` is for. `at` gives the height of the lowest point, so placing
something round lifts it: a ball at 0 rests on the carpet. A part of a join or a cut stands on its own `at`, round or not.
"""
from dataclasses import dataclass

from ..errors import DesignError
from ..source import schema
from . import outlines, worth
from .alliances import numbers
from .read import names

TURN = (0, 0, 1)


@dataclass(frozen=True)
class Taper:
    """A solid whose faces lean: the points of its foot and of its top, in mm, and how tall it is."""
    bottom: list
    top: list
    tall: float


def drawn(worker, entry, node, mirrored):
    """A shape about its own 0, 0, 0, or a Taper. A mirrored one has left and right swapped, as its outlines and the places of
    its parts have."""
    node, _ = worker.unwrap(node)
    draw = _Draw(worker, entry, mirrored)
    if "taper" in node:
        return Taper(draw.outline(node["taper"]["bottom"]), draw.outline(node["taper"]["top"]), draw.size(node["taper"]["tall"]))
    got = draw.make(node, (0, 0, -draw.lift(node)))
    try:
        schema.check(got, {"$ref": "#/$defs/shape"}, schema.load_schema())
    except DesignError as problem:
        raise DesignError("", f"is not a shape that the library draws: {problem.problem}", problem.fix) from None
    return got


def is_shape(node):
    return isinstance(node, dict) and len(node) == 1 and set(node) <= set(names()["shapes"])


def solid(place, node):
    """A shape and where it stands on the field: {"shape", "place"}, as a design's solid has them."""
    got = drawn(place.worker, place.entry, node, place.swapped)
    if isinstance(got, Taper):
        raise DesignError("", "is a taper, which the library's shapes cannot draw", "Use its two outlines and its height")
    at = list(numbers(place.point("at")))
    if len(at) < 3:
        raise DesignError("", "has no height in its at, so nobody can say where it stands", "See its unknown")
    at[2] += _Draw(place.worker, place.entry, False).lift(place.worker.unwrap(node)[0])
    turn = {"kind": "rotation", "originMm": [0, 0, 0], "axis": list(TURN), "travelDeg": worth.one_number(place.faces())}
    return {"shape": got, "place": [turn, {"kind": "translation", "travelMm": at}]}


class _Draw:
    """Draws the shapes of one record. (x, y, z) is where the lowest point of a shape stands."""

    def __init__(self, worker, entry, mirrored):
        self.worker, self.entry, self.mirrored = worker, entry, mirrored

    def length(self, node):
        return outlines.number(self.worker, self.entry, node)

    def size(self, node):
        number = self.length(node)
        if number <= 0:
            raise DesignError("", f"has a size of {number:g} mm", "Give it a size of more than 0")
        return number

    def outline(self, node):
        return outlines.checked(self.worker, self.entry, node, self.mirrored)

    def lift(self, node):
        """How far its lowest point is below its centre, for what is round; 0 for what stands on 0."""
        form, given = next(iter(node.items()))
        given = self.worker.unwrap(given)[0]
        if form == "ring":
            return self.size(given["thick"]) / 2
        if form in ("cylinder", "tube") and self._axis(given) == "z":
            return self.size(given["length"]) / 2
        wide = {"ball": "diameter", "cylinder": "diameter", "tube": "outside"}.get(form)
        return self.size(given[wide]) / 2 if wide else 0

    def make(self, node, at):
        node, _ = self.worker.unwrap(node)
        form, given = next(iter(node.items()))
        return getattr(self, f"make_{form}", self._no_form)(self.worker.unwrap(given)[0], *at)

    def _no_form(self, given, *at):
        raise DesignError("", "has a shape in it that the library cannot draw", "A taper can not be part of a join or a cut")

    def make_box(self, given, x, y, z):
        a, b, c = (self.size(one) for one in given)
        return {"kind": "box", "fromMm": [x - a / 2, y - b / 2, z], "toMm": [x + a / 2, y + b / 2, z + c]}

    def make_ball(self, given, x, y, z):
        radius = self.size(given["diameter"]) / 2
        return {"kind": "sphere", "centerMm": [x, y, z + radius], "radiusMm": radius}

    def make_cylinder(self, given, x, y, z):
        radius = self.size(given["diameter"]) / 2
        return {"kind": "cylinder", **self._ends(given, radius, x, y, z), "radiusMm": radius}

    def make_tube(self, given, x, y, z):
        inside, outside = self._hole(given)
        return {"kind": "tube", "section": "round", **self._ends(given, outside / 2, x, y, z), "outerDiameterMm": outside, "wallMm": (outside - inside) / 2}

    def _hole(self, given):
        inside, outside = self.size(given["inside"]), self.size(given["outside"])
        if inside >= outside:
            raise DesignError("", "is as wide inside as outside, or wider", "Its outside is the larger one")
        return inside, outside

    def _axis(self, given):
        return self.worker.unwrap(given.get("axis", "x"))[0]

    def _ends(self, given, radius, x, y, z):
        """The middles of the two ends of something round that lies along x or y, or stands."""
        axis, half = self._axis(given), self.size(given["length"]) / 2
        if axis == "z":
            return {"fromMm": [x, y, z], "toMm": [x, y, z + 2 * half]}
        dx, dy = (half, 0) if axis == "x" else (0, half)
        return {"fromMm": [x - dx, y - dy, z + radius], "toMm": [x + dx, y + dy, z + radius]}

    def make_ring(self, given, x, y, z):
        inside, outside = self._hole(given)
        thick = self.size(given["thick"])
        if abs(thick - (outside - inside) / 2) > 1e-6:
            raise DesignError("", f"is a ring {thick:g} mm thick, and half of its outside less its inside is {(outside - inside) / 2:g} mm", "Make thick (outside - inside) / 2")
        return {"kind": "torus", "centerMm": [x, y, z + thick / 2], "axis": list(TURN), "majorRadiusMm": (inside + outside) / 4, "minorRadiusMm": thick / 2}

    def make_prism(self, given, x, y, z):
        points = [[x + u, y + v] for u, v in self.outline(given["outline"])]
        return {"kind": "prism", "plane": "xy", "outlineMm": points, "fromMm": z, "toMm": z + self.size(given["tall"])}

    def _parts(self, given, x, y, z):
        """Each shape of a join or a cut, standing at its own `at`, which is from the record's."""
        for one in given:
            own = [self.length(n) for n in self.worker.unwrap(one["at"])[0]]
            own += [0] * (3 - len(own))
            yield self.make({name: node for name, node in one.items() if name != "at"}, (x + own[0], y + (-own[1] if self.mirrored else own[1]), z + own[2]))

    def make_join(self, given, *at):
        return {"kind": "union", "of": list(self._parts(given, *at))}

    def make_cut(self, given, *at):
        first, *others = self._parts(given, *at)
        return {"kind": "difference", "from": first, "cut": others}
