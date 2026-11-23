"""Clearance between solids: along a motion, with a proof that nothing was missed, and at a still pose.

Nothing here judges. min_gap is a number the caller chooses; each row says how close a pair comes and whether that
is closer than min_gap. Pairs the caller declares as intended contacts are left out and counted.
"""
import itertools
import math

from ..errors import DesignError
from ..kernel.between import gap_and_overlap
from . import proofs, scene as scenes
from .pairs import BOX_MARGIN_MM, box_gap, near_pairs
from .search import DEFAULT_DEPTH, search

COUNTS = ("pairs", "declaredContacts", "bothStill", "farApart", "fixedFarApart", "measured")


def declared(contacts, names):
    """The declared contact pairs as a set of sorted name pairs, checked against the solids present."""
    found = set()
    for pair in contacts:
        a, b = pair
        for name in (a, b):
            if name not in names:
                raise DesignError("", f'a declared contact names the solid "{name}", which is not present', "Name two solids of the design")
        found.add((a, b) if a < b else (b, a))
    return found


def row(a, b, method, gap, t, overlap, lower, proven, closer, samples, unresolved=None):
    out = {"pair": [a, b], "method": method, "gapMm": gap, "t": t, "overlapMm3": overlap, "lowerBoundMm": lower,
           "proven": proven, "closerThanMinGap": closer, "samples": samples}
    if unresolved:
        out["unresolved"] = unresolved
    return out


def measure_pair(scene, a, b, min_gap, depth, counts):
    """One pair along the motion: a row, or None when bounding boxes alone prove it stays farther than min_gap."""
    if scene.fixed(a, b):
        if box_gap(scene.boxes[a], scene.boxes[b]) > min_gap + BOX_MARGIN_MM:
            counts["fixedFarApart"] += 1
            return None
        gap, overlap = gap_and_overlap(scene.start[a], scene.start[b])
        return row(a, b, "fixed relative pose", gap, 0.0, overlap, gap, True, overlap > 0 or gap < min_gap, 1)
    speed = scene.rates[a] + scene.rates[b]
    if (box_gap(scene.boxes[a], scene.boxes[b]) - speed > min_gap
            or proofs.apart_along_an_axis(scene.boxes[a], scene.boxes[b], scene.laws[a], scene.laws[b], min_gap)):
        counts["farApart"] += 1
        return None
    if proofs.straight_stroke_clear(scene, a, b, min_gap):
        return row(a, b, "enclosed straight stroke", None, None, 0.0, min_gap, True, False, 0)
    overlaps = {}

    def gap_at(t):
        gap, overlaps[t] = gap_and_overlap(scene.at(a, t), scene.at(b, t))
        return gap

    found = search(gap_at, speed, min_gap, depth, hit=lambda t, gap: overlaps[t] > 0 or gap < min_gap)
    if found["hit"]:
        t, gap = found["hit"]
        return row(a, b, "adaptive search", gap, t, overlaps[t], None, True, True, found["samples"])
    t, gap = found["lowest"]
    if found["unresolved"]:
        return row(a, b, "adaptive search", gap, t, 0.0, None, False, False, found["samples"], found["unresolved"])
    return row(a, b, "adaptive search", gap, t, 0.0, min(found["floor"], gap), True, False, found["samples"])


def share_of(scene, min_gap, contacts, depth=DEFAULT_DEPTH, share=(0, 1), include_still=False):
    """Measure one share of a scene's pairs: every share[1]-th pair starting at pair share[0]. Shares combine in combine()."""
    first, count = share
    rows, counts = [], dict.fromkeys(COUNTS, 0)
    for index, (a, b) in enumerate(itertools.combinations(scene.names, 2)):
        if index % count != first:
            continue
        counts["pairs"] += 1
        if (a, b) in contacts:
            counts["declaredContacts"] += 1
        elif scene.still(a) and scene.still(b) and not include_still:
            counts["bothStill"] += 1
        else:
            found = measure_pair(scene, a, b, min_gap, depth, counts)
            if found:
                counts["measured"] += 1
                rows.append((index, found))
    return {"rows": rows, "counts": counts}


def combine(parts, header):
    """One result from the shares of a motion, in pair order whichever worker measured which share."""
    rows = [found for _, found in sorted((r for part in parts for r in part["rows"]), key=lambda r: r[0])]
    counts = {key: sum(part["counts"][key] for part in parts) for key in COUNTS}
    with_gap = [r for r in rows if r["gapMm"] is not None]
    closest = min(with_gap, key=lambda r: (r["gapMm"], -r["overlapMm3"], r["pair"])) if with_gap else None
    return {**header, "counts": counts, "proven": all(r["proven"] for r in rows),
            "closer": [r["pair"] for r in rows if r["closerThanMinGap"]],
            "unresolved": [r["pair"] for r in rows if not r["proven"]],
            "closest": closest and {"pair": closest["pair"], "gapMm": closest["gapMm"], "t": closest["t"], "overlapMm3": closest["overlapMm3"]},
            "pairs": rows}


def header(kind, name, min_gap, depth, contacts, absent):
    if not (isinstance(min_gap, (int, float)) and math.isfinite(min_gap) and min_gap >= 0):
        raise DesignError("", "the minimum gap must be zero or more millimetres", "Give min_gap as a number")
    return {kind: name, "minGapMm": float(min_gap), "depthLimit": depth, "declaredContacts": [list(p) for p in sorted(contacts)],
            "absent": sorted(absent)}


def along(assembly, motion, min_gap=0.0, contacts=(), absent=(), depth=DEFAULT_DEPTH, share=(0, 1)):
    """Clearance of every pair that moves relative to another, over the whole of a named motion.

    Returns plain data. Each row of "pairs" gives the smallest gap sampled and its stroke fraction t, any shared
    volume, a proven lower bound on the gap over the whole stroke, and "proven": False only when the search reached
    its depth limit before it could settle the pair. Pairs that boxes prove far apart get no row; they are counted.
    """
    scene = scenes.for_motion(assembly, motion, absent)
    pairs = declared(contacts, scene.names)
    return combine([share_of(scene, min_gap, pairs, depth, share)], header("motion", motion, min_gap, depth, pairs, absent))


def at_pose(assembly, pose=None, min_gap=0.0, contacts=(), absent=()):
    """Every pair closer than min_gap, or sharing volume, with all solids held at a named pose (None is as drawn)."""
    scene = scenes.for_pose(assembly, pose, absent)
    pairs = declared(contacts, scene.names)
    rows, counts = [], dict.fromkeys(COUNTS, 0)
    counts["pairs"] = math.comb(len(scene.names), 2)
    near = near_pairs(scene.boxes, min_gap)
    counts["fixedFarApart"] = counts["pairs"] - len(near)
    for index, (a, b) in enumerate(near):
        if (a, b) in pairs:
            counts["declaredContacts"] += 1
            continue
        counts["measured"] += 1
        gap, overlap = gap_and_overlap(scene.start[a], scene.start[b])
        if overlap > 0 or gap < min_gap:
            rows.append((index, row(a, b, "fixed relative pose", gap, 0.0, overlap, gap, True, True, 1)))
    return combine([{"rows": rows, "counts": counts}], header("pose", pose, min_gap, 0, pairs, absent))
