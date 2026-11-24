"""Screen facts: what the geometry says about whether an interaction is the same in every section, before any trial runs.

An interaction names a piece, the solids it meets, a section plane and the motions involved. This module reports
plain facts about it. It does not say which engine to use or whether anything is good enough; tools that judge do.
"""
import math

from ..builder import placement
from ..builder.shape import solid as build_shape
from ..errors import DesignError
from ..kernel import props
from ..kernel.between import shared
from ..kernel.section import outlines
from ..kernel.shapes import box
from ..kernel.transform import moved
from ..motion import matrix as mx
from ..motion import screw
from ..motion import stages as stage_math
from . import compression, symmetry

OFFSETS = (-1.0, -0.5, 0.5, 1.0)      # sections are compared at these fractions of the half width, against the centre section
REACH_MM = 5000.0


def no_custom(name, parameters, where):
    raise DesignError(where, "a piece made with a custom shape cannot be screened", "Declare the piece with a listed shape")


def samples(loops):
    """Points along outlines: the ends and middle of each straight piece, and a point every 10 degrees of each arc."""
    points = []
    for piece in (p for loop in loops for p in loop):
        if piece["kind"] == "segment":
            a, b = piece["a"], piece["b"]
            points += [a, b, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]]
        else:
            steps = max(2, int(abs(piece["sweep"]) / math.radians(10)) + 1)
            points += [[piece["centre"][0] + piece["radius"] * math.cos(piece["from"] + piece["sweep"] * i / steps),
                        piece["centre"][1] + piece["radius"] * math.sin(piece["from"] + piece["sweep"] * i / steps)] for i in range(steps + 1)]
    return points


def away(point, loops):
    """How far a point is from the nearest piece of some outlines."""
    best = math.inf
    for piece in (p for loop in loops for p in loop):
        if piece["kind"] == "segment":
            (ax, ay), (bx, by) = piece["a"], piece["b"]
            size = (bx - ax) ** 2 + (by - ay) ** 2
            along = 0.0 if size == 0 else max(0.0, min(1.0, ((point[0] - ax) * (bx - ax) + (point[1] - ay) * (by - ay)) / size))
            best = min(best, math.hypot(point[0] - ax - along * (bx - ax), point[1] - ay - along * (by - ay)))
        else:
            angle = math.atan2(point[1] - piece["centre"][1], point[0] - piece["centre"][0])
            turn = ((angle - piece["from"]) if piece["sweep"] > 0 else (piece["from"] - angle)) % (2 * math.pi)
            ends = [piece["from"], piece["from"] + piece["sweep"]] if turn > abs(piece["sweep"]) else [angle]
            best = min(best, min(math.hypot(point[0] - piece["centre"][0] - piece["radius"] * math.cos(a),
                                            point[1] - piece["centre"][1] - piece["radius"] * math.sin(a)) for a in ends))
    return best


def constancy(shape, plane, half_width):
    """How much a solid's section changes across the piece's width: the largest difference from the centre section, and where."""
    centre = outlines(shape, plane["normal"], plane["atMm"])
    worst, where, missing = 0.0, None, []
    for fraction in OFFSETS:
        level = plane["atMm"] + fraction * half_width
        other = outlines(shape, plane["normal"], level)
        if not centre or not other:
            if bool(centre) != bool(other):
                missing.append(level)
            continue
        apart = max([away(p, centre) for p in samples(other)] + [away(p, other) for p in samples(centre)])
        if apart > worst:
            worst, where = apart, level
    worst = round(worst, 6)
    return {"largestDifferenceMm": worst, "atLevelMm": where if worst else None, "notCutAtLevelsMm": missing, "cutAtCentre": bool(centre),
            "curvedAcross": symmetry.curved_across(shape, plane["normal"])}


def sideways(placed, piece_shape, normal, names):
    """The gap from the piece to the nearest named solid on each side along the plane's normal; None is unguided.

    Each side is probed with the piece's shadow: a box a little smaller than the piece's bounding box, pushed out
    along the normal. The gap is to the nearest part of any named solid inside that shadow.
    """
    axis = "xyz".index(normal)
    bounds = props.bounds(piece_shape)
    low, high = list(bounds[:3]), list(bounds[3:])
    for i in range(3):
        if i != axis:
            shrink = 0.1 * (high[i] - low[i])
            low[i], high[i] = low[i] + shrink, high[i] - shrink
    found = {}
    for side, sign in (("plus", 1), ("minus", -1)):
        a, b = list(low), list(high)
        if sign > 0:
            a[axis], b[axis] = bounds[axis + 3], bounds[axis + 3] + REACH_MM
        else:
            a[axis], b[axis] = bounds[axis] - REACH_MM, bounds[axis]
        shadow, best = box(a, b), None
        for name in names:
            inside = shared(placed[name], shadow)
            if not props.solids(inside) or props.volume(inside) <= 0:
                continue
            hit = props.bounds(inside)
            gap = hit[axis] - bounds[axis + 3] if sign > 0 else bounds[axis] - hit[axis + 3]
            if best is None or gap < best["gapMm"]:
                best = {"solid": name, "gapMm": max(0.0, gap)}
        found[side] = best
    return found


def out_of_plane(data, motions, normal):
    """The moving groups whose movement leaves the plane: a hinge not square to it, or a slide that crosses it."""
    n = [1.0 if axis == normal else 0.0 for axis in "xyz"]
    along = lambda v: abs(mx.dot(v, n)) / max(mx.length(v), 1e-12)
    found = []
    for motion in motions:
        for group, listed in placement.motion_stages(data, motion).items():
            why = set()
            for kind, value in stage_math.moving_part(listed):
                if kind == "ops":
                    for op in value:
                        if op["kind"] == "rotation" and along(op["axis"]) < 1 - 1e-9:
                            why.add("turns about an axis that is not square to the plane")
                        if op["kind"] == "translation" and mx.length(op["travelMm"]) > 0 and along(op["travelMm"]) > 1e-9:
                            why.add("slides across the plane")
                        if op["kind"] == "gravity-drop" and normal == "z":
                            why.add("drops across the plane")
                        if op["kind"] == "path" and len({round(p["xyz".index(normal)], 9) for p in op["throughMm"]}) > 1:
                            why.add("follows a path that leaves the plane")
                        if op["kind"] == "path" and "turnAxis" in op and along(op["turnAxis"]) < 1 - 1e-9:
                            why.add("turns about an axis that is not square to the plane")
                elif kind == "through":
                    for start, end in zip(value, value[1:]):
                        point, axis, angle, slide = screw.decompose(start, end)
                        if (point is not None and along(axis) < 1 - 1e-9) or (mx.length(slide) > 1e-9 and along(slide) > 1e-9):
                            why.add("passes through poses that take it out of the plane")
            found += [{"motion": motion, "group": group, "why": text} for text in sorted(why)]
    return found


def squeeze(assembly, entry, radius, names):
    """The deepest the meeting solids press into the drawn piece along the named motion, as a share of its thickness."""
    if "pieceSolid" not in entry or "squeezeMotion" not in entry:
        return {"ratio": None, "why": "no drawn piece solid and motion are named for this interaction"}
    deepest = None
    for name in names:
        if name == entry["pieceSolid"]:
            continue
        found = compression.indentation(assembly, entry["squeezeMotion"], entry["pieceSolid"], name, limit=radius * 0.999)
        if deepest is None or found["deepestMm"] > deepest["deepestMm"]:
            deepest = {"solid": name, "deepestMm": found["deepestMm"], "t": found["t"], "proven": found["proven"]}
    return {"ratio": deepest["deepestMm"] / (2 * radius), "thicknessMm": 2 * radius, "motion": entry["squeezeMotion"], **deepest}


def facts(assembly, name):
    """The screen facts for one named interaction of the design. Plain data; nothing is judged."""
    data = assembly.data
    if name not in data["interactions"]:
        raise DesignError("", f'there is no interaction named "{name}"', f"Known interactions: {', '.join(data['interactions']) or 'none'}")
    entry, where = data["interactions"][name], f'interactions "{name}"'
    plane, axis = entry["plane"], "xyz".index(entry["plane"]["normal"])
    piece = data["pieces"][entry["piece"]]
    piece_shape = build_shape(piece["shape"], where, no_custom)
    bounds = props.bounds(piece_shape)
    half_width = (bounds[axis + 3] - bounds[axis]) / 2 + entry.get("marginMm", 0.0)
    in_plane = [i for i in range(3) if i != axis]
    placed = assembly.at_pose(entry.get("pose"))
    guides = entry.get("guides") or [n for n in placed if n != entry.get("pieceSolid")]
    centre = [(bounds[i] + bounds[i + 3]) / 2 for i in range(3)]
    holds = [{"pieceAtMm": at, **sideways(placed, moved(piece_shape, mx.translation(mx.sub(at, centre))), plane["normal"], guides)}
             for at in entry.get("pieceAtMm", [])]
    involved = [*entry["solids"], *entry.get("guides", [])]
    materials = {s["name"]: s["material"] for section in ("solids", "fixtures") for s in data[section] if "material" in s}
    return {
        "interaction": name, "plane": plane, "pose": entry.get("pose"),
        "piece": {"name": entry["piece"], **symmetry.classify(piece_shape, piece["shape"]["kind"]),
                  "widthAcrossPlaneMm": bounds[axis + 3] - bounds[axis], "thicknessInPlaneMm": min(bounds[i + 3] - bounds[i] for i in in_plane)},
        "sections": {solid: constancy(placed[solid], plane, half_width) for solid in entry["solids"]},
        "sidewaysHold": holds,
        "mechanismOutOfPlane": out_of_plane(data, entry.get("motions", []), plane["normal"]),
        "piecesAtOnce": entry.get("piecesAtOnce", 1),
        "squeeze": squeeze(assembly, entry, min(bounds[i + 3] - bounds[i] for i in in_plane) / 2, entry["solids"]),
        "notRigid": [{"solid": solid, **materials[solid]} for solid in involved if solid in materials and materials[solid]["class"] != "rigid"],
        "approach": entry.get("approach"), "targetOffPlane": entry.get("targetOffPlane"),
    }
