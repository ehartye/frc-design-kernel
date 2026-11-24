"""Turn a recorded trace into one path operation: the fewest points that stay within a tolerance of every sample.

The piece's path through a trial has hundreds of samples. A layout needs it as one motion. This keeps the points
that matter (Ramer-Douglas-Peucker: keep the sample farthest from the straight line between two kept points, while it
is farther than the tolerance) and writes them as a single "path" operation with straight pieces.

When the trace has the piece's spin, the path also turns: the angle is the spin summed over the trace, and a sample is
also kept where the angle strays from the even growth between two kept points by more than the turn tolerance. Only
the turn in the trial's plane is fitted. A path is followed by length, so a turn made standing still cannot be
written; it shows as the turn deviation instead.
"""
import math

TURN_TOLERANCE_DEG = 5.0


def along(p, a, b):
    """How far along the straight piece a to b the point p lies, as a fraction from 0 to 1."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    size = dx * dx + dy * dy
    return 0.0 if size == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / size))


def off_line(p, a, b):
    """How far point p is from the straight piece a to b."""
    f = along(p, a, b)
    return math.hypot(p[0] - a[0] - f * (b[0] - a[0]), p[1] - a[1] - f * (b[1] - a[1]))


def off_turn(p, angle, a, b, first, last):
    """How far a sample's angle is from the angle the path has where the sample lies along the piece a to b."""
    return abs(angle - (first + along(p, a, b) * (last - first)))


def keep(points, tolerance, angles=None, turn_tolerance=TURN_TOLERANCE_DEG):
    """Indices of the points to keep so every point is within tolerance of the kept polyline (and of its angles)."""
    kept, spans = {0, len(points) - 1}, [(0, len(points) - 1)]
    while spans:
        first, last = spans.pop()
        worst, index = 1.0, None
        for i in range(first + 1, last):
            away = off_line(points[i], points[first], points[last]) / max(tolerance, 1e-12)
            if angles is not None:
                turned = off_turn(points[i], angles[i], points[first], points[last], angles[first], angles[last])
                away = max(away, turned / max(turn_tolerance, 1e-12))
            if away > worst:
                worst, index = away, i
        if index is not None:
            kept.add(index)
            spans += [(first, index), (index, last)]
    return sorted(kept)


def angles_of(trace):
    """The piece's turn at each sample in degrees, from 0 at the first, summed from its spin; None without a spin column."""
    if "spinRadps" not in trace.get("columns", []):
        return None
    k, rows, found = trace["columns"].index("spinRadps"), trace["rows"], [0.0]
    for a, b in zip(rows, rows[1:]):
        found.append(found[-1] + math.degrees((a[k] + b[k]) / 2 * (b[0] - a[0])))
    return found


def turn_axis(normal):
    """The direction the planar spin turns about: counter-clockwise in the plane's two axes, as both engines count it."""
    return {"x": [1, 0, 0], "y": [0, -1, 0], "z": [0, 0, 1]}[normal]


def deviations(samples, angles, owner, points, point_angles, chosen):
    """The largest distance and angle by which any sample misses the piece of the kept path its own point lies on."""
    worst = turned = 0.0
    j = 0
    for row, p in enumerate(samples):
        while j + 2 < len(chosen) and chosen[j + 1] <= owner[row]:
            j += 1
        a, b = points[chosen[j]], points[chosen[j + 1]]
        worst = max(worst, off_line(p, a, b))
        if angles is not None:
            turned = max(turned, off_turn(p, angles[row], a, b, point_angles[chosen[j]], point_angles[chosen[j + 1]]))
    return worst, turned


def path_operation(trace, plane, tolerance, turn_tolerance=TURN_TOLERANCE_DEG):
    """One path operation for the piece's trace, with how well it fits.

    trace is {"columns": [...], "rows": [[t, u mm, v mm, ...], ...]}. plane is {"normal": axis, "atMm": level}.
    Returns {"operation": {...}, "points": n, "samples": n, "maxDeviationMm": d, "toleranceMm": tolerance, "atS": [times]},
    and, when the trace has a spin column, "maxTurnDeviationDeg" and "turnToleranceDeg", with the operation's "turnDeg"
    (one per point, 0 at the first) and "turnAxis". The operation moves a point from the first sample along the kept
    points; a path is followed by length, so the times of the kept points are given beside it, not inside it.
    """
    samples = [(row[1], row[2]) for row in trace["rows"]]
    angles = angles_of(trace)
    distinct = [0] + [i for i in range(1, len(samples)) if math.dist(samples[i], samples[i - 1]) > 1e-9]
    points = [samples[i] for i in distinct]
    turning = {} if angles is None else {"turnToleranceDeg": turn_tolerance}
    if len(points) < 2:     # no path to follow, so a turn on the spot is missed in full
        return {"operation": None, "points": len(points), "samples": len(samples), "maxDeviationMm": 0.0, "toleranceMm": tolerance, "atS": [],
                **({} if angles is None else {"maxTurnDeviationDeg": max(abs(v) for v in angles), **turning})}
    point_angles = None if angles is None else [angles[i] for i in distinct]
    chosen = keep(points, tolerance, point_angles, turn_tolerance)
    owner, n = [], -1      # the distinct point each sample sits at: a sample that did not move belongs to the one before
    for row in range(len(samples)):
        n += 1 if n + 1 < len(distinct) and distinct[n + 1] == row else 0
        owner.append(n)
    worst, turned = deviations(samples, angles, owner, points, point_angles, chosen)
    axis = "xyz".index(plane["normal"])

    def full(point):
        out = [round(point[0], 4), round(point[1], 4)]
        out.insert(axis, plane["atMm"])
        return out

    operation = {"kind": "path", "curve": "straight", "throughMm": [full(points[i]) for i in chosen]}
    if angles is not None:
        operation.update(turnDeg=[round(point_angles[i], 4) for i in chosen], turnAxis=turn_axis(plane["normal"]))
        turning["maxTurnDeviationDeg"] = turned
    return {"operation": operation, "points": len(chosen), "samples": len(samples), "maxDeviationMm": worst, "toleranceMm": tolerance,
            "atS": [trace["rows"][distinct[i]][0] for i in chosen], **turning}
