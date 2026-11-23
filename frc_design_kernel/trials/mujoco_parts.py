"""The parts of a MuJoCo scene that are not fixed surfaces: the piece, driven surfaces, moved groups and flaps.

Plain text and numbers only; nothing here imports MuJoCo.
"""
import math

from ..builder import placement
from ..errors import DesignError
from ..kernel.section import AXES
from ..motion import matrix as mx
from ..motion import stages as stage_math

MM = 1e-3
ARMATURE = 1000.0       # makes a moved joint deaf to contact within a step; its place and speed are set again every step


def fail(where, problem, fix):
    raise DesignError(where, problem, fix)


def quaternion(m):
    """(w, x, y, z) of the turning part of a transform."""
    trace = m[0] + m[5] + m[10]
    if trace > 0:
        s = math.sqrt(trace + 1) * 2
        return (s / 4, (m[9] - m[6]) / s, (m[2] - m[8]) / s, (m[4] - m[1]) / s)
    i = max(range(3), key=lambda k: m[5 * k])
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(1 + m[5 * i] - m[5 * j] - m[5 * k]) * 2
    q = [0.0] * 4
    q[0] = (m[4 * k + j] - m[4 * j + k]) / s
    q[i + 1] = s / 4
    q[j + 1] = (m[4 * j + i] + m[4 * i + j]) / s
    q[k + 1] = (m[4 * k + i] + m[4 * i + k]) / s
    return tuple(q)


def text(values):
    return " ".join(f"{v:.9g}" for v in values)


def start_of(case, handed):
    start = case["piece"]["start"]
    if "after" in start:
        x, z, vx, vz, w = handed["piece"]
        return {"at": [x, z], "velocity": [0.0, 0.0] if start.get("atRest", True) else [vx, vz], "spin": 0.0 if start.get("atRest", True) else w}
    return {"at": [v * MM for v in start["atMm"]], "velocity": list(start.get("velocityMps", [0.0, 0.0])), "spin": start.get("spinRadps", 0.0)}


def ring(shape, mass, segments, where):
    """A ring piece as a closed chain of capsules along its centre circle: (geoms, inertia, outer radius)."""
    major, minor = shape["majorRadiusMm"] * MM, shape["minorRadiusMm"] * MM
    axis = list(mx.unit(shape["axis"]))
    lie = max(range(3), key=lambda i: abs(axis[i]))
    if abs(abs(axis[lie]) - 1.0) > 1e-9:
        fail(where, "the MuJoCo engine needs a ring piece's axis along x, y or z", "Turn the piece's shape so its axis lies along one of them")
    a, b = [i for i in range(3) if i != lie]
    points = []
    for i in range(segments + 1):
        point = [0.0, 0.0, 0.0]
        point[a], point[b] = major * math.cos(2 * math.pi * i / segments), major * math.sin(2 * math.pi * i / segments)
        points.append(point)
    geoms = [f'type="capsule" fromto="{text(points[i] + points[i + 1])}" size="{minor:.9g}"' for i in range(segments)]
    inertia = [mass * (4 * major ** 2 + 5 * minor ** 2) / 8] * 3
    inertia[lie] = mass * (major ** 2 + 0.75 * minor ** 2)
    return geoms, inertia, major + minor


def piece_body(name, piece, mass, start, normal, segments=32, body="piece"):
    """A piece as a free body: its geoms, mass and inertia from its 3D shape, its start state from the planar start."""
    shape = piece["shape"]
    axis = "xyz".index(normal)
    iu, iv = AXES[normal]
    position = [0.0, 0.0, 0.0]
    position[iu], position[iv], position[axis] = start["at"][0], start["at"][1], start["level"]
    radius = shape.get("radiusMm", shape.get("outerDiameterMm", 0) / 2) * MM
    if shape["kind"] == "sphere":
        geoms, inertia = [f'type="sphere" size="{radius:.9g}"'], [0.4 * mass * radius ** 2] * 3
    elif shape["kind"] == "torus":
        geoms, inertia, radius = ring(shape, mass, segments, f'pieces "{name}"')
    elif shape["kind"] in ("cylinder", "tube") and shape.get("section", "round") == "round":
        length = math.dist(shape["fromMm"], shape["toMm"]) * MM
        inner = radius - shape.get("wallMm", shape.get("radiusMm", 0)) * MM if shape["kind"] == "tube" else 0.0
        along = [abs(b - a) for a, b in zip(shape["fromMm"], shape["toMm"])]
        lie = along.index(max(along))
        half = [0.0, 0.0, 0.0]
        half[lie] = length / 2
        geoms = [f'type="cylinder" fromto="{text([-h for h in half] + half)}" size="{radius:.9g}"']
        inertia = [mass * (3 * (radius ** 2 + inner ** 2) + length ** 2) / 12] * 3
        inertia[lie] = 0.5 * mass * (radius ** 2 + inner ** 2)
    else:
        fail(f'pieces "{name}"', "the MuJoCo engine cannot yet build this piece", "It builds a ball, a ring, a round bar and a round tube so far")
    if "inertiaKgM2" in piece:      # a stated inertia is about the plane's normal; the other two are raised just enough to be a real body
        inertia = [max(v, 0.51 * piece["inertiaKgM2"]) for v in inertia]
        inertia[axis] = piece["inertiaKgM2"]
    spin = [0.0, 0.0, 0.0]
    spin[axis] = start["spin"] * (-1.0 if normal == "y" else 1.0)       # counter-clockwise in (u, v) is a turn about -y
    velocity = [0.0, 0.0, 0.0]
    velocity[iu], velocity[iv] = start["velocity"]
    drawn = "".join(f'<geom name="{body}#{i}" {fields}/>' for i, fields in enumerate(geoms))
    xml = (f'<body name="{body}" pos="{text(position)}"><freejoint/>'
           f'<inertial pos="0 0 0" mass="{mass:.9g}" diaginertia="{text(inertia)}"/>{drawn}</body>')
    return xml, velocity + spin, radius


def driven_by(case, solid):
    """The drive that turns a solid: {"drive", "ratio", "axis"}, or None. Its surface runs at the drive's speed across that axis."""
    for drive, entry in case["drives"].items():
        for turn in entry.get("turns", []):
            if turn["solid"] == solid:
                return {"drive": drive, "ratio": turn.get("ratio", 1.0), "axis": list(mx.unit(turn["axis"]))}
    return None


def mover_of(case, assembly, group, key, where):
    """How the surface's mover drives its group along a design motion: one hinge, one slider, or carried along its path; or None.

    The group takes its whole movement in that motion, carriers included, so a group carried by a moving one moves with it.
    """
    for key, entry in ([(key, case.get("movers", {})[key])] if key else []):
        if "motion" not in entry:
            fail(f'{where} mover "{key}"', "the MuJoCo engine moves groups along a design motion only", 'Give the mover a "motion" and a "group"')
        listed = placement.motion_stages(assembly.data, entry["motion"])[group]
        moving, timing = stage_math.moving_part(listed), {k: entry[k] for k in ("startS", "after", "delayS", "durationS") if k in entry}
        found = {"mover": key, "start": stage_math.at(listed, 0.0), **timing}
        single = len(moving) == 1 and moving[0][0] == "ops" and len(moving[0][1]) == 1 and moving[0][1][0]["kind"] in ("rotation", "translation")
        if single and moving[0][1][0]["kind"] == "rotation":
            op = moving[0][1][0]
            return {**found, "kind": "hinge", "axis": list(mx.unit(op["axis"])), "anchor": [v * MM for v in op["originMm"]], "travel": math.radians(op["travelDeg"])}
        if single:
            travel = moving[0][1][0]["travelMm"]
            return {**found, "kind": "slide", "axis": list(mx.unit(travel)), "anchor": [0.0, 0.0, 0.0], "travel": mx.length(travel) * MM}
        return {**found, "kind": "path", "stages": [[kind, value] for kind, value in listed]}
    return None


def flap_of(entry, plane, where):
    """A flap as a body on a sprung hinge about the plane's normal, between a stop at rest and a stop at its limit."""
    if "solid" not in entry:
        fail(where, "the MuJoCo engine needs a flap to name the solid that is the flap", 'Draw the flap at rest as a solid and add "solid" to the flap')
    if "mover" in entry:
        fail(where, "the MuJoCo engine does not run a flap on a mover yet", "Run this trial with the planar engine")
    across = "xyz".index(plane["normal"])
    iu, iv = AXES[plane["normal"]]
    anchor, axis = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    anchor[iu], anchor[iv], anchor[across] = entry["hingeMm"][0] * MM, entry["hingeMm"][1] * MM, plane["atMm"] * MM
    axis[across] = -1.0 if plane["normal"] == "y" else 1.0     # the planar angle grows counter-clockwise in (u, v)
    return {"kind": "flap", "flap": entry["name"], "axis": axis, "anchor": anchor, "inertia": entry["inertiaKgM2"], "preloadNm": entry.get("preloadNm", 0.0),
            "joint": f'limited="true" range="0 {entry["limitDeg"]:.9g}" solreflimit="0.002 1" stiffness="{entry["springNmPerRad"]:.9g}" '
                     f'damping="{entry.get("dampingNmSPerRad", 0.0):.9g}"'}


def bodies_xml(model, moving):
    """The fixed geoms, then one body per moved group or flap with its joint."""
    parts = ["".join(g for _, _, g, body in model.geoms if body == "world")]
    for key, entry in moving.items():
        geoms = "".join(g for _, _, g, body in model.geoms if body == key)
        if entry["kind"] == "path":
            parts.append(f'<body name="{key}" mocap="true">{geoms}</body>')
            continue
        joint = "slide" if entry["kind"] == "slide" else "hinge"
        more = entry["joint"] if entry["kind"] == "flap" else f'armature="{ARMATURE}"'
        inertia = entry.get("inertia", 1.0)
        parts.append(f'<body name="{key}"><joint name="{key}" type="{joint}" axis="{text(entry["axis"])}" pos="{text(entry["anchor"])}" {more}/>'
                     f'<inertial pos="{text(entry["anchor"])}" mass="{min(1.0, inertia * 100):.9g}" diaginertia="{text([inertia] * 3)}"/>{geoms}</body>')
    return "".join(parts)
