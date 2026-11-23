"""Turn a trial's case into a scene for the MuJoCo engine: an MJCF model text and the maps the runner needs.

The same trial definition the planar engine runs is read here. The solids the trial names become fixed bodies at the
trial's pose: a box, a ball or a full cylinder as that exact primitive, a union as its parts, a convex prism as its
exact hull. Anything else (a hollow tube, a cut shape, an imported part) is used as its convex hull, and listed. The
piece is a free body built from its one 3D definition. Nothing here imports MuJoCo; the model is plain text.

Stage one of the engine: fixed surfaces and one free piece. Drives, flaps, loads and movers are refused by name.
"""
import math

from ..builder import placement
from ..builder.shape import make
from ..errors import DesignError
from ..kernel import props
from ..kernel.mesh import triangles
from ..kernel.section import AXES
from ..motion import matrix as mx
from ..motion import ops
from .contact import damping
from .inputs import plain
from .ready import breakdown

MM = 1e-3
IMPEDANCE = 0.95        # MuJoCo's contact "impedance": how much of the asked-for spring force it delivers
NOT_YET = ("flaps", "loads", "movers", "forces", "commands")


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


def primitive(shape, placed_at):
    """A geom's attributes for a box, a ball or a full cylinder, moved by a transform; None for any other shape."""
    kind = shape["kind"]
    if kind == "box":
        low, high = shape["fromMm"], shape["toMm"]
        centre = mx.apply(placed_at, [(a + b) / 2 for a, b in zip(low, high)])
        return {"type": "box", "pos": text(mx.scale(centre, MM)), "quat": text(quaternion(placed_at)), "size": text(abs(a - b) / 2 * MM for a, b in zip(low, high))}
    if kind == "sphere":
        return {"type": "sphere", "pos": text(mx.scale(mx.apply(placed_at, shape["centerMm"]), MM)), "size": text([shape["radiusMm"] * MM])}
    if kind == "cylinder" and shape.get("sweepDeg", 360) == 360:
        ends = [*mx.scale(mx.apply(placed_at, shape["fromMm"]), MM), *mx.scale(mx.apply(placed_at, shape["toMm"]), MM)]
        return {"type": "cylinder", "fromto": text(ends), "size": text([shape["radiusMm"] * MM])}
    return None


class Model:
    """Collects the meshes and geoms of a scene and writes them as MJCF."""

    def __init__(self):
        self.meshes, self.geoms, self.hulled, self.kinds = [], [], [], {}

    def add(self, solid, surface, shape, placed_at, friction, solref):
        """Add the geoms of one shape entry, part by part where it is a union."""
        if shape["kind"] == "union":
            for part in shape["of"]:
                self.add(solid, surface, part, placed_at, friction, solref)
            return
        found = primitive(shape, placed_at)
        if found is None:
            built = make(shape, f'solid "{solid}"', None)
            points = [mx.scale(mx.apply(placed_at, v), MM) for v in triangles(built, 0.2)["vertices"]]
            found = self.mesh(points)
            if breakdown(shape) != "convex" and solid not in self.hulled:
                self.hulled.append(solid)
        self.geom(solid, surface, found, friction, solref)

    def mesh(self, points):
        name = f"mesh{len(self.meshes)}"
        self.meshes.append(f'<mesh name="{name}" vertex="{text(v for p in points for v in p)}"/>')
        return {"type": "mesh", "mesh": name}

    def geom(self, solid, surface, found, friction, solref):
        name = f"g{len(self.geoms)}"
        fields = " ".join(f'{key}="{value}"' for key, value in found.items())
        self.geoms.append((name, surface, f'<geom name="{name}" {fields} friction="{friction:.9g} 0.005 0.0001" solref="{text(solref)}" '
                                          f'solimp="{IMPEDANCE} {IMPEDANCE} 0.001" priority="1" condim="3"/>'))
        self.kinds.setdefault(solid, []).append(found["type"])


def piece_body(name, piece, mass, start, normal):
    """The piece as a free body: its geom, mass and inertia from its 3D shape, its start state from the planar start."""
    shape = piece["shape"]
    axis = "xyz".index(normal)
    iu, iv = AXES[normal]
    position = [0.0, 0.0, 0.0]
    position[iu], position[iv], position[axis] = start["at"][0], start["at"][1], start["level"]
    radius = shape.get("radiusMm", shape.get("outerDiameterMm", 0) / 2) * MM
    if shape["kind"] == "sphere":
        geom, inertia = f'<geom name="piece" type="sphere" size="{radius:.9g}"', [0.4 * mass * radius ** 2] * 3
    elif shape["kind"] in ("cylinder", "tube") and shape.get("section", "round") == "round":
        length = math.dist(shape["fromMm"], shape["toMm"]) * MM
        inner = radius - shape.get("wallMm", shape.get("radiusMm", 0)) * MM if shape["kind"] == "tube" else 0.0
        along = [abs(b - a) for a, b in zip(shape["fromMm"], shape["toMm"])]
        lie = along.index(max(along))
        half = [0.0, 0.0, 0.0]
        half[lie] = length / 2
        geom = f'<geom name="piece" type="cylinder" fromto="{text([-h for h in half] + half)}" size="{radius:.9g}"'
        inertia = [mass * (3 * (radius ** 2 + inner ** 2) + length ** 2) / 12] * 3
        inertia[lie] = 0.5 * mass * (radius ** 2 + inner ** 2)
    else:
        fail(f'pieces "{name}"', "the MuJoCo engine cannot yet build this piece", "It builds a ball, a round bar and a round tube so far")
    if "inertiaKgM2" in piece:
        inertia[axis] = piece["inertiaKgM2"]
    spin = [0.0, 0.0, 0.0]
    spin[axis] = start["spin"] * (-1.0 if normal == "y" else 1.0)       # counter-clockwise in (u, v) is a turn about -y
    velocity = [0.0, 0.0, 0.0]
    velocity[iu], velocity[iv] = start["velocity"]
    body = (f'<body name="piece" pos="{text(position)}"><freejoint name="free"/>'
            f'<inertial pos="0 0 0" mass="{mass:.9g}" diaginertia="{text(inertia)}"/>'
            f'{geom} friction="0 0 0" condim="3"/></body>')
    return body, velocity + spin, radius


def start_of(case, handed):
    start = case["piece"]["start"]
    if "after" in start:
        x, z, vx, vz, w = handed
        return {"at": [x, z], "velocity": [0.0, 0.0] if start.get("atRest", True) else [vx, vz], "spin": 0.0 if start.get("atRest", True) else w}
    return {"at": [v * MM for v in start["atMm"]], "velocity": list(start.get("velocityMps", [0.0, 0.0])), "spin": start.get("spinRadps", 0.0)}


def build(assembly, name, a_case, handed=None):
    """The MuJoCo scene for a trial's case: {"engine": "mujoco", "xml": model text, ...} with the facts of what it took."""
    where = f'trials "{name}"'
    case = plain(a_case)
    used = [part for part in NOT_YET if case.get(part)]
    if used:
        fail(where, f"the MuJoCo engine does not run {', '.join(used)} yet", "Run this trial with the planar engine, or take those parts out")
    plane = case["plane"]
    use = case["piece"]["use"]
    piece = case["pieces"][use]
    mass = piece["massKg"]
    built = {entry["name"]: entry for section in ("solids", "fixtures") for entry in assembly.data[section]}
    groups, posed = assembly.data["groups"], placement.at_pose(assembly.data, case.get("pose"))
    placed, model = assembly.at_pose(case.get("pose")), Model()
    for entry in case["surfaces"]:
        if "solid" not in entry:
            fail(f'{where} surface "{entry.get("name", "surface")}"', "the MuJoCo engine needs every surface to come from a solid", "Draw the surface as a solid and name it")
        solid, surface = entry["solid"], entry.get("name", entry["solid"])
        material = case["materials"][entry["material"]]
        stiffness = material["stiffnessNPerM"]
        solref = (-stiffness / (mass * IMPEDANCE), -damping(stiffness, mass, material.get("restitution"), material.get("dampingRatio")) / (mass * IMPEDANCE))
        source = built[solid]
        if "shape" in source and source["shape"]["kind"] != "custom":
            at = mx.chain([ops.at(source.get("place", [])), ops.at(groups[source["group"]].get("place", [])), posed[source["group"]]])
            model.add(solid, surface, source["shape"], at, material["friction"], solref)
        else:       # an imported part or a custom shape: no construction to read, so its placed surface is hulled
            points = [mx.scale(v, MM) for v in triangles(placed[solid], 0.2)["vertices"]]
            model.geom(solid, surface, model.mesh(points), material["friction"], solref)
            model.hulled.append(solid)
    start = {**start_of(case, handed), "level": plane["atMm"] * MM}
    body, velocity, radius = piece_body(use, piece, mass, start, plane["normal"])
    gravity = [0.0, 0.0, 0.0 if plane["normal"] == "z" else -case.get("gravityMps2", 9.80665)]
    xml = (f'<mujoco><option timestep="{case["stepS"]:.9g}" gravity="{text(gravity)}" cone="elliptic" impratio="10"/>'
           f'<asset>{"".join(model.meshes)}</asset><worldbody>{"".join(g for _, _, g in model.geoms)}{body}</worldbody></mujoco>')
    facts = {"plane": plane, "pose": case.get("pose"), "geoms": model.kinds, "hulled": sorted(model.hulled),
             "sections": [{"solid": entry["solid"]} for entry in case["surfaces"]], "typedSurfaces": [],
             "piece": {"piece": use, "shape": piece["shape"]["kind"], "radiusMm": radius / MM},
             "contactMapping": f"spring k and damper c of each material are given to MuJoCo as solref = (-k / (m d), -c / (m d)) with piece mass m and impedance d = {IMPEDANCE}"}
    return {"engine": "mujoco", "xml": xml, "surfaceOf": {g: surface for g, surface, _ in model.geoms}, "axes": ["xyz"[i] for i in AXES[plane["normal"]]],
            "normal": plane["normal"], "levelM": plane["atMm"] * MM, "startVelocity": velocity, "radiusM": radius,
            "stepS": case["stepS"], "durationS": case["durationS"], "traceS": case.get("traceS", 0.002),
            "rest": {"speedMps": 0.005, "rimSpeedMps": 0.005, **case.get("rest", {})},
            "events": case.get("events", []), "measures": case.get("measures", {}), "drives": {}, "hinges": {}, "movers": {}, "loads": [], "surfaces": [], "facts": facts}
