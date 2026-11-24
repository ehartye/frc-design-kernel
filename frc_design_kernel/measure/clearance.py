"""Clearance between solids: along a motion, with a proof that nothing was missed, and at a still pose.

Nothing here judges. min_gap is a number the caller chooses; each row says how close a pair comes and whether that
is closer than min_gap. Pairs the caller declares as intended contacts are left out and counted. Every result says
what it was measured from ("inputs") and which pairs were measured now and which were carried ("checked"); see carry.
"""
import itertools
import math

from ..errors import DesignError
from ..kernel.between import gap_and_overlap
from . import carry, proofs, scene as scenes
from .carry import COUNTS
from .pairs import BOX_MARGIN_MM, box_gap, near_pairs
from .search import DEFAULT_DEPTH, search


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

    This is the broad phase. It is cheap, so a carried pair with no stored row is counted by it again.
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


def carried_count(scene, a, b, contacts, include_still, min_gap):
    """The count a carried pair falls under: the one a full measurement puts it under, whether or not its row was kept."""
    if (a, b) in contacts:
        return "declaredContacts"
    if scene.still(a) and scene.still(b) and not include_still:
        return "bothStill"
    return far(scene, a, b, min_gap) or "measured"


def outside(focus, also, a, b):
    return focus is not None and a not in focus and b not in focus and (a, b) not in also


def share_of(scene, min_gap, contacts, depth=DEFAULT_DEPTH, share=(0, 1), include_still=False, memo=None, focus=None, also=(), carrying=False):
    """Measure one share of a scene's pairs: every share[1]-th pair starting at pair share[0]. Shares combine in combine().

    focus, when given, is a set of solid names: only pairs with one of them in it, or in also, are measured. The
    others are counted as not in focus; or, when carrying, as a full measurement would count them, their rows (those
    kept) being put in by the caller.
    """
    first, count = share
    rows, counts, tally = [], dict.fromkeys(COUNTS, 0), {"measured": 0, "carried": 0, "notMeasured": 0}
    for index, (a, b) in enumerate(itertools.combinations(scene.names, 2)):
        if index % count != first:
            continue
        counts["pairs"] += 1
        if outside(focus, also, a, b):
            if not carrying:
                counts["notInFocus"] += 1
                tally["notMeasured"] += 1
            else:
                counts[carried_count(scene, a, b, contacts, include_still, min_gap)] += 1
                tally["carried"] += 1
            continue
        tally["measured"] += 1
        if (a, b) in contacts:
            counts["declaredContacts"] += 1
        elif scene.still(a) and scene.still(b) and not include_still:
            counts["bothStill"] += 1
        else:
            found = measure_pair(scene, a, b, min_gap, depth, counts, memo)
            if found:
                counts["measured"] += 1
                rows.append((index, found))
    return {"rows": rows, "counts": counts, "tally": tally}


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


def finished(parts, head, inputs, chosen):
    """One result from its shares, with what it was measured from and what was measured now and what carried."""
    tally = {key: sum(part["tally"][key] for part in parts) for key in ("measured", "carried", "notMeasured")}
    return {**combine(parts, head), "inputs": inputs, "checked": carry.checked(chosen, tally)}


def rules(min_gap, depth, include_still):
    """The rules of a clearance along a motion: a change to any of them measures every pair again."""
    return {"minGapMm": float(min_gap), "depthLimit": depth, "includeStill": bool(include_still)}


def header(kind, name, min_gap, depth, contacts, absent, include_still=False, displace=None):
    if not (isinstance(min_gap, (int, float)) and math.isfinite(min_gap) and min_gap >= 0):
        raise DesignError("", "the minimum gap must be zero or more millimetres", "Give min_gap as a number")
    return {kind: name, "minGapMm": float(min_gap), "depthLimit": depth, "declaredContacts": [list(p) for p in sorted(contacts)],
            "absent": sorted(absent), "includeStill": include_still, "displaced": {name: list(shift) for name, shift in sorted((displace or {}).items())}}


def along(assembly, motion, min_gap=0.0, contacts=(), absent=(), depth=DEFAULT_DEPTH, include_still=False, displace=None, focus=None, earlier=None):
    """Clearance of every pair that moves relative to another, over the whole of a named motion.

    Returns plain data. Each row of "pairs" gives the smallest gap sampled and its stroke fraction t, any shared
    volume, a proven lower bound on the gap over the whole stroke, and "proven": False only when the search reached
    its depth limit before it could settle the pair. Pairs that boxes prove far apart get no row; they are counted.
    Pairs where neither solid moves are left to at_pose unless include_still is set. displace shifts named solids
    by [dx, dy, dz] for this one question: a control that shows the check can report an interference. focus and
    earlier choose which pairs are measured and which carried, as carry.plan says.
    """
    names = scenes.present(assembly, absent)
    pairs = declared(contacts, names)
    inputs = {"rules": rules(min_gap, depth, include_still), "solids": carry.along(assembly, motion, absent, displace)}
    chosen = carry.plan(earlier, inputs, pairs, focus, earlier is not None)
    head = header("motion", motion, min_gap, depth, pairs, absent, include_still, displace)
    parts = [carry.carried_part(names, chosen)]
    if chosen.counts is None:
        scene = scenes.for_motion(assembly, motion, absent, displace)
        parts.append(share_of(scene, min_gap, pairs, depth, (0, 1), include_still, None, chosen.focus, chosen.also, chosen.carrying))
    return finished(parts, head, inputs, chosen)


def at_pose(assembly, pose=None, min_gap=0.0, contacts=(), absent=(), focus=None, earlier=None):
    """Every pair closer than min_gap, or sharing volume, with all solids held at a named pose (None is as drawn).

    focus, when given, is a set of solid names: only pairs with one of them in it are measured. earlier, when given,
    is an earlier result to carry the unchanged pairs from, as carry.plan says.
    """
    names = scenes.present(assembly, absent)
    pairs = declared(contacts, names)
    inputs = {"rules": {"minGapMm": float(min_gap)}, "solids": carry.at_pose(assembly, pose, absent)}
    chosen = carry.plan(earlier, inputs, pairs, focus, earlier is not None)
    head = header("pose", pose, min_gap, 0, pairs, absent, True)
    parts = [carry.carried_part(names, chosen)]
    if chosen.counts is None:
        parts.append(pose_share(assembly, pose, min_gap, pairs, absent, names, chosen))
    return finished(parts, head, inputs, chosen)


def pose_share(assembly, pose, min_gap, pairs, absent, names, chosen):
    """The pairs at a still pose that a plan measures, with the others counted as a full measurement counts them."""
    scene = scenes.for_pose(assembly, pose, absent)
    rows, counts, focus = [], dict.fromkeys(COUNTS, 0), chosen.focus
    counts["pairs"] = math.comb(len(names), 2)
    near = near_pairs(scene.boxes, min_gap)
    counts["fixedFarApart"] = counts["pairs"] - len(near)
    for a, b in near:
        if outside(focus, chosen.also, a, b):
            counts["declaredContacts" if chosen.carrying and (a, b) in pairs else "measured" if chosen.carrying else "notInFocus"] += 1
            continue
        if (a, b) in pairs:
            counts["declaredContacts"] += 1
            continue
        counts["measured"] += 1
        gap, overlap = gap_and_overlap(scene.start[a], scene.start[b])
        if overlap > 0 or gap < min_gap:
            rows.append((carry.pair_index(names, a, b), row(a, b, "fixed relative pose", gap, 0.0, overlap, gap, True, True, 1)))
    others = 0 if focus is None else math.comb(sum(1 for name in names if name not in focus), 2) - len(chosen.also)
    tally = {"measured": counts["pairs"] - others, "carried": others if chosen.carrying else 0, "notMeasured": 0 if chosen.carrying else others}
    return {"rows": rows, "counts": counts, "tally": tally}
