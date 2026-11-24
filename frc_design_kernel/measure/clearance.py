"""Clearance between solids: along a motion, with a proof that nothing was missed, and at a still pose.

Nothing here judges. min_gap is a number the caller chooses; each row says how close a pair comes and whether that
is closer than min_gap. Pairs the caller declares as intended contacts are left out and counted. A measurement can be
limited to the pairs with named solids in them (focus); it then says which, and counts the pairs left out.
"""
import itertools
import math

from ..errors import DesignError
from ..kernel.between import gap_and_overlap
from ..workers import silent
from . import proofs, scene as scenes
from .pairs import BOX_MARGIN_MM, box_gap, near_pairs
from .search import DEFAULT_DEPTH, search

COUNTS = ("pairs", "declaredContacts", "bothStill", "farApart", "fixedFarApart", "measured", "notInFocus")
QUICK = 256             # pairs settled by boxes alone between two words on how far a share is


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


def far(scene, a, b, min_gap):
    """The count a pair falls under when bounding boxes alone prove it stays farther than min_gap, or None.

    This is the broad phase: cheap, and tried before anything is measured.
    """
    if scene.fixed(a, b):
        return "fixedFarApart" if box_gap(scene.boxes[a], scene.boxes[b]) > min_gap + BOX_MARGIN_MM else None
    if (box_gap(scene.boxes[a], scene.boxes[b]) - (scene.rates[a] + scene.rates[b]) > min_gap
            or proofs.apart_along_an_axis(scene.boxes[a], scene.boxes[b], scene.laws[a], scene.laws[b], min_gap)):
        return "farApart"
    return None


def measure_pair(scene, a, b, min_gap, depth, counts, memo=None):
    """One pair along the motion: a row, or None when bounding boxes alone prove it stays farther than min_gap.

    memo remembers the gap and overlap of a pair that keeps its relative pose, by the two solids and where each
    stands, so the same pair standing the same way in another motion is not measured again.
    """
    settled = far(scene, a, b, min_gap)
    if settled:
        counts[settled] += 1
        return None
    if scene.fixed(a, b):
        key = (a, b, scene.placed[a], scene.placed[b])
        if memo is None or key not in memo:
            found = gap_and_overlap(scene.start[a], scene.start[b])
            if memo is not None:
                memo[key] = found
        gap, overlap = found if memo is None else memo[key]
        return row(a, b, "fixed relative pose", gap, 0.0, overlap, gap, True, overlap > 0 or gap < min_gap, 1)
    speed = scene.rates[a] + scene.rates[b]
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


def share_pairs(names, share, focus=None):
    """([(pair number, (a, b))] of one share, how many pairs the share leaves out): every share[1]-th pair starting at
    pair share[0], of all pairs or of those with a focus solid in them. The pairs left out are counted in share 0."""
    first, count = share
    every = enumerate(itertools.combinations(names, 2))
    if focus is None:
        return itertools.islice(every, first, None, count), len(range(first, math.comb(len(names), 2), count)), 0
    kept = [(index, pair) for index, pair in every if pair[0] in focus or pair[1] in focus]
    mine = kept[first::count]
    return mine, len(mine), math.comb(len(names), 2) - len(kept) if first == 0 else 0


def share_of(scene, min_gap, contacts, depth=DEFAULT_DEPTH, share=(0, 1), include_still=False, memo=None, focus=None, meter=silent):
    """Measure one share of a scene's pairs. Shares combine in combine().

    focus, when given, is a set of solid names: only pairs with one of them in it are measured, and the others are
    counted as not in focus. meter hears how many of the share's pairs are done.
    """
    rows, counts = [], dict.fromkeys(COUNTS, 0)
    mine, size, left_out = share_pairs(scene.names, share, focus)
    counts["pairs"], counts["notInFocus"] = size + left_out, left_out
    meter(0, size)
    for done, (index, (a, b)) in enumerate(mine, 1):
        found = None
        if (a, b) in contacts:
            counts["declaredContacts"] += 1
        elif scene.still(a) and scene.still(b) and not include_still:
            counts["bothStill"] += 1
        else:
            found = measure_pair(scene, a, b, min_gap, depth, counts, memo)
        if found:
            counts["measured"] += 1
            rows.append((index, found))
        if found or not done % QUICK:
            meter(done, size)
    meter(size, size)
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


def header(kind, name, min_gap, depth, contacts, absent, include_still=False, displace=None, focus=None):
    if not (isinstance(min_gap, (int, float)) and math.isfinite(min_gap) and min_gap >= 0):
        raise DesignError("", "the minimum gap must be zero or more millimetres", "Give min_gap as a number")
    return {kind: name, "minGapMm": float(min_gap), "depthLimit": depth, "declaredContacts": [list(p) for p in sorted(contacts)],
            "absent": sorted(absent), "includeStill": include_still, "displaced": {name: list(shift) for name, shift in sorted((displace or {}).items())},
            **({} if focus is None else {"focus": sorted(focus)})}


def along(assembly, motion, min_gap=0.0, contacts=(), absent=(), depth=DEFAULT_DEPTH, include_still=False, displace=None, focus=None):
    """Clearance of every pair that moves relative to another, over the whole of a named motion.

    Returns plain data. Each row of "pairs" gives the smallest gap sampled and its stroke fraction t, any shared
    volume, a proven lower bound on the gap over the whole stroke, and "proven": False only when the search reached
    its depth limit before it could settle the pair. Pairs that boxes prove far apart get no row; they are counted.
    Pairs where neither solid moves are left to at_pose unless include_still is set. displace shifts named solids
    by [dx, dy, dz] for this one question: a control that shows the check can report an interference. focus names
    solids: only the pairs with one of them in it are measured.
    """
    pairs = declared(contacts, scenes.present(assembly, absent))
    head = header("motion", motion, min_gap, depth, pairs, absent, include_still, displace, focus)
    scene = scenes.for_motion(assembly, motion, absent, displace)
    return combine([share_of(scene, min_gap, pairs, depth, (0, 1), include_still, None, None if focus is None else set(focus))], head)


def at_pose(assembly, pose=None, min_gap=0.0, contacts=(), absent=(), focus=None, meter=silent):
    """Every pair closer than min_gap, or sharing volume, with all solids held at a named pose (None is as drawn).

    focus names solids: only the pairs with one of them in it are measured. meter hears how many pairs near enough to
    measure are done.
    """
    names = scenes.present(assembly, absent)
    pairs = declared(contacts, names)
    head = header("pose", pose, min_gap, 0, pairs, absent, True, focus=focus)
    scene = scenes.for_pose(assembly, pose, absent)
    chosen = set(names) if focus is None else set(focus)
    near = [pair for pair in near_pairs(scene.boxes, min_gap) if pair[0] in chosen or pair[1] in chosen]
    rows, counts = [], dict.fromkeys(COUNTS, 0)
    counts["pairs"], counts["notInFocus"] = math.comb(len(names), 2), math.comb(len(set(names) - chosen), 2)
    counts["fixedFarApart"] = counts["pairs"] - counts["notInFocus"] - len(near)
    for done, (a, b) in enumerate(near):
        meter(done, len(near))
        if (a, b) in pairs:
            counts["declaredContacts"] += 1
            continue
        counts["measured"] += 1
        gap, overlap = gap_and_overlap(scene.start[a], scene.start[b])
        if overlap > 0 or gap < min_gap:
            rows.append((done, row(a, b, "fixed relative pose", gap, 0.0, overlap, gap, True, True, 1)))
    meter(len(near), len(near))
    return combine([{"rows": rows, "counts": counts}], head)
