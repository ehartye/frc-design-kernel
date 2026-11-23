"""Turn a recorded trace into one path operation: the fewest points that stay within a tolerance of every sample.

The piece's path through a trial has hundreds of samples. A layout needs it as one motion. This keeps the points
that matter (Ramer-Douglas-Peucker: keep the sample farthest from the straight line between two kept points, while it
is farther than the tolerance) and writes them as a single "path" operation with straight pieces.
"""
import math


def off_line(p, a, b):
    """How far point p is from the straight piece a to b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    size = dx * dx + dy * dy
    along = 0.0 if size == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / size))
    return math.hypot(p[0] - a[0] - along * dx, p[1] - a[1] - along * dy)


def keep(points, tolerance):
    """Indices of the points to keep so every point is within tolerance of the kept polyline."""
    kept, spans = {0, len(points) - 1}, [(0, len(points) - 1)]
    while spans:
        first, last = spans.pop()
        worst, index = 0.0, None
        for i in range(first + 1, last):
            away = off_line(points[i], points[first], points[last])
            if away > worst:
                worst, index = away, i
        if index is not None and worst > tolerance:
            kept.add(index)
            spans += [(first, index), (index, last)]
    return sorted(kept)


def path_operation(trace, plane, tolerance):
    """One path operation for the piece's trace, with how well it fits.

    trace is {"columns": [...], "rows": [[t, u mm, v mm, ...], ...]}. plane is {"normal": axis, "atMm": level}.
    Returns {"operation": {...}, "points": n, "samples": n, "maxDeviationMm": d, "toleranceMm": tolerance, "atS": [times]}.
    The operation moves a point from the first sample along the kept points; a path is followed by length, so the
    times of the kept points are given beside it, not inside it.
    """
    samples = [(row[1], row[2]) for row in trace["rows"]]
    distinct = [0] + [i for i in range(1, len(samples)) if math.dist(samples[i], samples[i - 1]) > 1e-9]
    points = [samples[i] for i in distinct]
    if len(points) < 2:
        return {"operation": None, "points": len(points), "samples": len(samples), "maxDeviationMm": 0.0, "toleranceMm": tolerance, "atS": []}
    chosen = keep(points, tolerance)
    kept = [points[i] for i in chosen]
    worst = max(min(off_line(p, a, b) for a, b in zip(kept, kept[1:])) for p in points)
    axis = "xyz".index(plane["normal"])

    def full(point):
        out = [round(point[0], 4), round(point[1], 4)]
        out.insert(axis, plane["atMm"])
        return out

    operation = {"kind": "path", "curve": "straight", "throughMm": [full(p) for p in kept]}
    return {"operation": operation, "points": len(kept), "samples": len(samples), "maxDeviationMm": worst, "toleranceMm": tolerance,
            "atS": [trace["rows"][distinct[i]][0] for i in chosen]}
