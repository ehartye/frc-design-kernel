"""Broad phase: which pairs of solids are near enough to be worth an exact measurement."""
import math

BOX_MARGIN_MM = 1e-3    # a bounding box encloses its solid; past this margin a box gap proves a real gap


def box_gap(a, b):
    """The gap between two bounding boxes [xmin, ymin, zmin, xmax, ymax, zmax]. The solids inside are at least this far apart."""
    return math.hypot(*(max(a[i] - b[i + 3], b[i] - a[i + 3], 0) for i in range(3)))


def box_around(boxes):
    """The one box around several boxes."""
    return [min(b[i] for b in boxes) for i in range(3)] + [max(b[i] for b in boxes) for i in range(3, 6)]


def near_pairs(boxes, within):
    """Every pair (a, b), a < b, whose boxes are no more than within apart. Any pair left out is proven farther apart.

    Sorts the boxes along X and stops looking as soon as the next box starts too far away.
    """
    found = []
    ordered = sorted(boxes, key=lambda name: (boxes[name][0], name))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if boxes[b][0] - boxes[a][3] > within + BOX_MARGIN_MM:
                break
            if box_gap(boxes[a], boxes[b]) <= within + BOX_MARGIN_MM:
                found.append((a, b) if a < b else (b, a))
    return sorted(found)
