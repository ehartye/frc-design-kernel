"""Piece geometry: the numbers a delivery envelope needs, from each game piece's shape alone, with no design source.

The input is a design source's own pieces block, {"pieces": {name: {"shape": shape, ...}}}; every field but shape is
ignored. Each shape is checked against the schema, its "=..." texts worked out with no parameters, and built. A shape
that fails is reported with its error and the rest are still measured. Plain numbers only; nothing is judged.

Per shape: its identity (kind, volume and bounds of the built solid, to tell a stale record), bounds, volume, centre,
symmetry class, a convex hull that contains it (kernel/hull.py) and its through-bore by one rule: a body of
revolution whose axis line misses the solid has a bore along that axis, as wide as twice the axis's distance from
the solid, centred where the axis passes nearest the solid's centre. Every axis is written pointing one way: its first
component that is not zero is positive, so the same piece drawn from either end gives the same record.
"""
import ast
import json
import math
from pathlib import Path

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Pnt

from ..builder.shape import solid as build_shape
from ..errors import DesignError
from ..kernel import hull, props
from ..kernel.between import distance
from ..source import schema
from ..source.expand import work_out
from ..source.expressions import CONSTANTS, is_expression
from ..source.load import not_a_number
from ..version import generator
from . import symmetry

SCHEMA = "frc-design-kernel/piece-geometry@1"
MISSES_MM = 1e-6        # an axis line this far from the solid, or farther, does not meet it
ZERO = 1e-9             # an axis component this small counts as zero when choosing which way the axis points
PLACES = 4


def no_custom(name, parameters, where):
    raise DesignError(where, "a piece made with a custom shape cannot be measured on its own", "Declare the piece with a listed shape")


def read(path):
    """{name: piece} from a pieces file in UTF-8 (a leading byte-order mark is allowed). Refuses a missing or unreadable
    file, text that is not UTF-8, bad JSON, or a file with no pieces block."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=not_a_number)
    except FileNotFoundError:
        raise DesignError(str(path), "the pieces file does not exist", "Check the path") from None
    except UnicodeDecodeError:
        raise DesignError(str(path), "is not UTF-8 text", "Save it as UTF-8") from None
    except OSError as problem:          # a folder, or a file with no read access
        raise DesignError(str(path), f"cannot be read ({problem.strerror or problem})", "Give the path of a pieces file you can read") from None
    except json.JSONDecodeError as problem:
        raise DesignError(f"{path.name} line {problem.lineno}", f"is not valid JSON ({problem.msg})", "Look for a missing comma, quote or bracket near that line") from None
    pieces = raw.get("pieces") if isinstance(raw, dict) else None
    if not isinstance(pieces, dict) or not all(isinstance(piece, dict) for piece in pieces.values()):
        raise DesignError(path.name, 'has no "pieces" block of named pieces', 'Give {"pieces": {"name": {"shape": {...}}}}, as in a design source')
    return pieces


def built(piece, where):
    """(the worked-out shape entry, its one solid) for a piece, or a DesignError saying what is wrong."""
    if "shape" not in piece:
        raise DesignError(where, 'has no "shape"', 'Add "shape", written as in a design source')
    root, place = schema.load_schema(), schema.step(where, "shape")
    schema.check(piece["shape"], root["$defs"]["shape"], root, place)
    no_parameters(piece["shape"], place)
    entry = work_out(piece["shape"], {}, place)
    return entry, build_shape(entry, place, no_custom)


def no_parameters(value, where):
    """Refuse an "=..." text that names a parameter: a pieces file has none to give it."""
    if is_expression(value):
        try:
            tree = ast.parse(value[1:].strip(), mode="eval")
        except SyntaxError:
            return              # worked out next, which reports the bad arithmetic
        called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}     # a function's name, not a parameter
        names = sorted({node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and id(node) not in called} - set(CONSTANTS))
        if names:
            raise DesignError(where, f'the expression "{value}" uses "{names[0]}", but piece-geometry has no parameters', "Write the number itself")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            no_parameters(item, schema.step(where, i))
    elif isinstance(value, dict):
        for key, item in value.items():
            no_parameters(item, schema.step(where, key))


def one_way(axis):
    """The axis turned, if need be, so its first component that is not zero is positive."""
    first = next((v for v in axis if abs(v) > ZERO), 1.0)
    return [v + 0.0 if first > 0 else -v + 0.0 for v in axis]


def tidy(values):
    return [round(v, PLACES) + 0.0 for v in values]


def bore(shape, found, centre, bounds):
    """The through-bore of a body of revolution, by the one rule; None for any other shape or an axis that meets it.

    A body of revolution's centre lies on its axis, so the axis line is drawn through the centre, long enough to
    pass right through the solid's bounding box."""
    if found["class"] != "body of revolution":
        return None
    axis = found["axis"]
    reach = math.dist(bounds[:3], bounds[3:]) + 1.0
    ends = [[c + side * reach * a for c, a in zip(centre, axis)] for side in (-1, 1)]
    try:
        gap = distance(BRepBuilderAPI_MakeEdge(gp_Pnt(*ends[0]), gp_Pnt(*ends[1])).Edge(), shape)
    except ValueError:
        raise DesignError("", "the CAD kernel could not measure the gap from the axis to the shape, for its bore",
                          "Report the shape") from None
    if gap < MISSES_MM:
        return None
    return {"diameterMm": round(2 * gap, PLACES), "axis": axis, "centreMm": tidy(centre)}


def facts(entry, shape, linear_mm, angular_rad):
    """The geometry record of one built shape."""
    bounds, volume, centre = props.bounds(shape), props.volume(shape), props.centre(shape)
    box = [tidy(bounds[:3]), tidy(bounds[3:])]
    found = symmetry.classify(shape, entry["kind"])
    if "axis" in found:
        found = {**found, "axis": one_way(found["axis"])}
    grown = hull.hull(shape, linear_mm, angular_rad)
    return {"ok": True, "identity": {"kind": entry["kind"], "volumeMm3": round(volume, 3), "boundsMm": box},
            "boundsMm": box, "volumeMm3": round(volume, 3), "centreMm": tidy(centre), "symmetry": found,
            "hullMm": grown["vertices"], "hullToleranceMm": grown["toleranceMm"], "bore": bore(shape, found, centre, bounds)}


def measure(pieces, linear_mm=0.2, angular_rad=0.3):
    """The piece-geometry record for {name: piece}. A shape that fails is {"ok": false, "error": {where, problem, fix}}."""
    shapes = {}
    for name, piece in pieces.items():
        where = f'pieces "{name}"'
        try:
            entry, shape = built(piece, where)
            shapes[name] = facts(entry, shape, linear_mm, angular_rad)
        except DesignError as problem:
            shapes[name] = {"ok": False, "error": {"where": problem.where or where, "problem": problem.problem, "fix": problem.fix}}
    made = generator()
    return {"schema": SCHEMA, "generator": made, "used": {"library": made["version"], "meshing": {"linearMm": linear_mm, "angularRad": angular_rad}},
            "shapes": shapes}
