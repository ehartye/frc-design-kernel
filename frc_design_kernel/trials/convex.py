"""A shape as convex pieces, worked out from how it was built in the design source.

A physics engine needs convex pieces. Taking a hollow or cut shape as its convex hull fills it in, which is the main
way a 3D result can be silently wrong. Where the construction allows, this module gives the true pieces instead:

    rectangular tube     four flat walls, exact
    round tube           a ring of wedge pieces; the bore becomes flat facets (the error is stated)
    box less boxes       the boxes that are left, exact
    prism, any outline   triangles of the outline pushed through, exact
    pie slice            slices of at most a half turn each; the round face becomes facets (the error is stated)

Each piece is a list of corner points in the shape's own coordinates (mm); its convex hull is the piece.
"""
import math

from ..kernel.shapes import PLANES, rectangle

RING_PIECES = 24
ARC_STEP_DEG = 10.0


def frame(start, end, up=None):
    """(along, across, up) unit directions for something running from start to end."""
    axis = [b - a for a, b in zip(start, end)]
    size = math.hypot(*axis)
    along = [v / size for v in axis]
    if up is None:
        up = (1, 0, 0) if abs(along[2]) > 0.99 else (0, 0, 1)
    lean = sum(a * b for a, b in zip(up, along))
    square = [u - lean * a for u, a in zip(up, along)]
    span = math.hypot(*square)
    square = [v / span for v in square]
    across = [along[1] * square[2] - along[2] * square[1], along[2] * square[0] - along[0] * square[2], along[0] * square[1] - along[1] * square[0]]
    return along, across, square


def rectangular_tube(shape):
    start, end = shape["fromMm"], shape["toMm"]
    _, across, up = frame(start, end, shape.get("up"))
    w, h, t = shape["widthMm"], shape["heightMm"], shape["wallMm"]
    pieces = []
    outer = [rectangle(at, across, up, w, h) for at in (start, end)]
    inner = [rectangle(at, across, up, w - 2 * t, h - 2 * t) for at in (start, end)]
    for i in range(4):      # one wall per side: two outer corners and the two inner corners behind them, at both ends
        j = (i + 1) % 4
        pieces.append([ring[k] for ring in (outer[0], inner[0], outer[1], inner[1]) for k in (i, j)])
    return pieces, None


def round_tube(shape):
    start, end = shape["fromMm"], shape["toMm"]
    _, across, up = frame(start, end)
    outer, inner = shape["outerDiameterMm"] / 2, shape["outerDiameterMm"] / 2 - shape["wallMm"]
    point = lambda at, radius, angle: [c + radius * (math.cos(angle) * a + math.sin(angle) * u) for c, a, u in zip(at, across, up)]
    pieces, step = [], 2 * math.pi / RING_PIECES
    for n in range(RING_PIECES):
        angles = (n * step, (n + 0.5) * step, (n + 1) * step)
        pieces.append([point(at, radius, angle) for at in (start, end) for radius, some in ((outer, angles), (inner, angles[::2])) for angle in some])
    return pieces, f"the bore is {RING_PIECES} flat facets, within {inner * (1 - math.cos(step / 2)):.3f} mm of round"


def corners(low, high):
    return [[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]


def box_less_boxes(shape):
    """The boxes left when boxes are cut from a box: the cells of the grid their faces make that no cut covers."""
    span = lambda entry: ([min(a, b) for a, b in zip(entry["fromMm"], entry["toMm"])], [max(a, b) for a, b in zip(entry["fromMm"], entry["toMm"])])
    low, high = span(shape["from"])
    cuts = [span(cut) for cut in shape["cut"]]
    marks = [sorted({low[i], high[i], *[min(max(v, low[i]), high[i]) for c in cuts for v in (c[0][i], c[1][i])]}) for i in range(3)]
    pieces = []
    for x0, x1 in zip(marks[0], marks[0][1:]):
        for y0, y1 in zip(marks[1], marks[1][1:]):
            for z0, z1 in zip(marks[2], marks[2][1:]):
                middle = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]
                if not any(all(c[0][i] < middle[i] < c[1][i] for i in range(3)) for c in cuts):
                    pieces.append(corners([x0, y0, z0], [x1, y1, z1]))
    return pieces, None


def triangles_of(outline):
    """A closed 2D outline cut into triangles (ear clipping). The outline must not cross itself."""
    points = list(outline)
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))
    if area < 0:
        points.reverse()
    turn = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    found = []
    while len(points) > 3:
        for i in range(len(points)):
            a, b, c = points[i - 1], points[i], points[(i + 1) % len(points)]
            inside = any(turn(a, b, p) > 1e-12 and turn(b, c, p) > 1e-12 and turn(c, a, p) > 1e-12 for p in points if p not in (a, b, c))
            if turn(a, b, c) > 1e-12 and not inside:
                found.append([a, b, c])
                del points[i]
                break
        else:
            break
    return found + [points]


def prism(shape):
    place = PLANES[shape["plane"]]
    return [[list(place(u, v, level)) for level in (shape["fromMm"], shape["toMm"]) for u, v in tri] for tri in triangles_of(shape["outlineMm"])], None


def pie_slice(shape):
    start, end = shape["fromMm"], shape["toMm"]
    # The slice starts along sweepFrom and turns counter-clockwise about the axis from start to end.
    _, second, first = frame(start, end, shape["sweepFrom"])
    radius, sweep = shape["radiusMm"], math.radians(shape["sweepDeg"])
    parts = max(1, math.ceil(shape["sweepDeg"] / 180.0))
    point = lambda at, angle: [c + radius * (math.cos(angle) * a + math.sin(angle) * b) for c, a, b in zip(at, first, second)]
    pieces = []
    for n in range(parts):
        a0, a1 = sweep * n / parts, sweep * (n + 1) / parts
        steps = max(2, math.ceil(math.degrees(a1 - a0) / ARC_STEP_DEG))
        angles = [a0 + (a1 - a0) * k / steps for k in range(steps + 1)]
        pieces.append([list(at) for at in (start, end)] + [point(at, angle) for at in (start, end) for angle in angles])
    return pieces, f"the round face is flat facets, within {radius * (1 - math.cos(math.radians(ARC_STEP_DEG) / 2)):.3f} mm of round"


def pieces(shape):
    """(convex pieces, note) for a shape entry that construction can break down, or None when it cannot.

    The note says what is faceted, or is None when the pieces are exact.
    """
    kind = shape["kind"]
    if kind == "tube":
        return rectangular_tube(shape) if shape["section"] == "rectangular" else round_tube(shape)
    sharp = lambda part: part["kind"] == "box" and not part.get("edgeRadiusMm")
    if kind == "difference" and sharp(shape["from"]) and all(sharp(cut) for cut in shape["cut"]):
        return box_less_boxes(shape)
    if kind == "prism":
        return prism(shape)
    if kind == "cylinder" and shape.get("sweepDeg", 360) < 360 and "sweepFrom" in shape:
        return pie_slice(shape)
    return None
