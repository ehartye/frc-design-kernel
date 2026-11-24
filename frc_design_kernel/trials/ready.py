"""Plain facts about what a fuller, 3D engine would have to work around in this design. No judgement, just the list.

A 3D engine needs each body as convex pieces, a mass for every body, each moving group as one hinge or one slider
(or else it must be driven along a path), and every drive tied to a solid. A shape built in the source from boxes,
cylinders and unions keeps that construction, so an exact convex breakdown can be had from it later.
"""
from ..builder import placement
from ..motion import stages as stage_math
from . import convex

CONVEX = ("box", "sphere", "cone")
GOOD = ("convex", "union of convex pieces", "convex pieces from its construction")


def convex_outline(points):
    """Whether a closed 2D outline turns the same way at every corner."""
    turns = []
    for i in range(len(points)):
        (ax, ay), (bx, by), (cx, cy) = points[i - 2], points[i - 1], points[i]
        turns.append((bx - ax) * (cy - by) - (by - ay) * (cx - bx))
    return all(t >= -1e-9 for t in turns) or all(t <= 1e-9 for t in turns)


def breakdown(shape):
    """"convex", "union of convex pieces", "convex pieces from its construction", or the reason no breakdown follows from how the shape was built."""
    kind = shape["kind"]
    if kind in CONVEX or (kind == "cylinder" and shape.get("sweepDeg", 360) in (360,)) or (kind == "cylinder" and shape.get("sweepDeg", 360) <= 180):
        return "convex"
    if kind == "prism" and convex_outline(shape["outlineMm"]):
        return "convex"
    if kind == "intersection" and all(breakdown(part) == "convex" for part in shape["of"]):
        return "convex"
    if kind == "union":
        parts = [breakdown(part) for part in shape["of"]]
        return "union of convex pieces" if all(p in GOOD for p in parts) else next(p for p in parts if p not in GOOD)
    if convex.pieces(shape) is not None:
        return "convex pieces from its construction"
    return {"tube": "a hollow tube", "difference": "a shape with material cut away", "intersection": "an overlap of shapes",
            "custom": "a custom shape", "cylinder": "a pie slice wider than a half turn", "torus": "a ring (a torus)"}[kind]


def construction(data):
    """{solid name: its shape entry, or None for an imported part}, as written in the design source."""
    return {entry["name"]: entry.get("shape") for section in ("solids", "fixtures") for entry in data[section]}


def report(assembly):
    """The facts a 3D engine would need settled, for the solids, groups, drives and pieces this design's trials use."""
    data = assembly.data
    built = construction(data)
    cut = sorted({s["solid"] for trial in data["trials"].values() for s in trial["surfaces"] if "solid" in s})
    concave = []
    for name in cut:
        found = "an imported part with no construction in the source" if built[name] is None else breakdown(built[name])
        if found not in GOOD:
            concave.append({"solid": name, "why": found})
    weightless = [s.name for s in assembly.solids.values() if not s.fixture and s.mass_kg is None and "massKg" not in data["groups"][s.group]]
    paths = []
    for motion in data["motions"]:
        for group, listed in placement.motion_stages(data, motion).items():
            moving = stage_math.moving_part(listed)
            single = len(moving) == 1 and moving[0][0] == "ops" and len(moving[0][1]) == 1 and moving[0][1][0]["kind"] in ("rotation", "translation")
            if moving and not single:
                paths.append({"motion": motion, "group": group})
    typed = [{"trial": name, "surface": s.get("name", "surface"), "drive": s.get("drive")} for name, trial in data["trials"].items()
             for s in trial["surfaces"] if "solid" not in s]
    return {"trialSolids": cut, "concaveWithNoBreakdown": concave, "solidsWithNoMass": sorted(weightless),
            "groupsNotOneHingeOrSlider": paths, "drivesNotOnASolid": sorted(name for name, drive in data["drives"].items() if "radiusMm" in drive and not drive.get("turns")),
            "surfacesNotFromSolids": typed,
            "piecesNotPrimitive": sorted(name for name, piece in data["pieces"].items() if piece["shape"]["kind"] not in ("sphere", "cylinder", "tube", "box") or piece["shape"].get("edgeRadiusMm"))}
