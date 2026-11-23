"""Turn one shape entry of a design source into exactly one valid solid."""
import math

from ..errors import DesignError
from ..kernel import booleans, props, shapes

MIN_VOLUME_MM3 = 1e-6


def one_solid(shape, where, what="This shape"):
    """The single solid inside shape. Refuses none, several, an invalid one or one with no volume."""
    found = props.solids(shape) if shape is not None else []
    if len(found) != 1:
        raise DesignError(where, f"{what} makes {len(found)} solids, not exactly one",
                          "Make the pieces overlap or touch so they join, or give each piece its own solid entry")
    if not props.is_valid(found[0]):
        raise DesignError(where, f"{what} is not a valid solid", "Check for an outline that crosses itself or sizes that fold the shape inside out")
    if props.volume(found[0]) <= MIN_VOLUME_MM3:
        raise DesignError(where, f"{what} has no volume", "Check for two equal corners, a zero size or a cut that removes everything")
    return found[0]


def positive(entry, key, where):
    if entry[key] <= 0:
        raise DesignError(where, f"{key} must be greater than 0, not {entry[key]:g}", "Give a positive size in millimetres")
    return entry[key]


def apart(entry, where, first="fromMm", second="toMm"):
    if math.dist(entry[first], entry[second]) <= 1e-9:
        raise DesignError(where, f"{first} and {second} are the same point", "Give two different points")
    return entry[first], entry[second]


def _box(entry, where, custom):
    if any(abs(a - b) <= 1e-9 for a, b in zip(entry["fromMm"], entry["toMm"])):
        raise DesignError(where, "the box has zero size along an axis", "Give two opposite corners that differ in x, y and z")
    return shapes.box(entry["fromMm"], entry["toMm"])


def _cylinder(entry, where, custom):
    start, end = apart(entry, where)
    sweep = entry.get("sweepDeg")
    if sweep is not None and not 0 < sweep <= 360:
        raise DesignError(where, "sweepDeg must be more than 0 and at most 360", "Give the angle of the pie slice in degrees")
    return shapes.cylinder(start, end, positive(entry, "radiusMm", where), None if sweep in (None, 360) else sweep, entry.get("sweepFrom"))


def _sphere(entry, where, custom):
    return shapes.sphere(entry["centerMm"], positive(entry, "radiusMm", where))


def _torus(entry, where, custom):
    if positive(entry, "minorRadiusMm", where) >= positive(entry, "majorRadiusMm", where):
        raise DesignError(where, "minorRadiusMm must be smaller than majorRadiusMm", "A ring needs a hole through its middle")
    return shapes.torus(entry["centerMm"], entry["axis"], entry["majorRadiusMm"], entry["minorRadiusMm"])


def _prism(entry, where, custom):
    if abs(entry["toMm"] - entry["fromMm"]) <= 1e-9:
        raise DesignError(where, "fromMm and toMm are the same level", "Give two different levels; the prism spans between them")
    return shapes.prism(entry["plane"], entry["outlineMm"], entry["fromMm"], entry["toMm"])


def _tube(entry, where, custom):
    start, end = apart(entry, where)
    wall = positive(entry, "wallMm", where)
    wanted = ("outerDiameterMm",) if entry["section"] == "round" else ("widthMm", "heightMm")
    for key in wanted:
        if key not in entry:
            raise DesignError(where, f'a {entry["section"]} tube is missing "{key}"', f'Add "{key}"')
        if positive(entry, key, where) <= 2 * wall:
            raise DesignError(where, f"wallMm {wall:g} leaves no opening inside {key} {entry[key]:g}", "Use a thinner wall, or draw a solid bar with a box or cylinder")
    if entry["section"] == "round":
        return shapes.round_tube(start, end, entry["outerDiameterMm"], wall)
    return shapes.rectangular_tube(start, end, entry["widthMm"], entry["heightMm"], wall, entry.get("up"))


def _union(entry, where, custom):
    return booleans.union([make(part, f"{where}.of[{i}]", custom) for i, part in enumerate(entry["of"])])


def _difference(entry, where, custom):
    cuts = [make(part, f"{where}.cut[{i}]", custom) for i, part in enumerate(entry["cut"])]
    return booleans.difference(make(entry["from"], f"{where}.from", custom), cuts)


def _intersection(entry, where, custom):
    return booleans.intersection([make(part, f"{where}.of[{i}]", custom) for i, part in enumerate(entry["of"])])


def _custom(entry, where, custom):
    return custom(entry["use"], entry.get("parameters", {}), where)


MAKERS = {"box": _box, "cylinder": _cylinder, "sphere": _sphere, "torus": _torus, "prism": _prism, "tube": _tube, "union": _union,
          "difference": _difference, "intersection": _intersection, "custom": _custom}


def make(entry, where, custom):
    """The raw kernel shape for a shape entry. custom(name, parameters, where) builds a registered custom shape."""
    try:
        return MAKERS[entry["kind"]](entry, where, custom)
    except DesignError:
        raise
    except Exception as problem:    # the CAD kernel raises its own error types for impossible geometry
        raise DesignError(where, f"the CAD kernel could not make this {entry['kind']} ({type(problem).__name__})", "Check its points and sizes") from None


def solid(entry, where, custom):
    """Exactly one valid solid for a shape entry."""
    return one_solid(make(entry, where, custom), where)
