"""Turn a trial's case into a scene for the MuJoCo engine: an MJCF model text and the maps the runner needs.

The same trial definition the planar engine runs is read here. The solids the trial names become fixed bodies at the
trial's pose: a box, a ball or a full cylinder as that exact primitive, a union as its parts, a convex prism as its
exact hull, a hollow or cut shape as the convex pieces its construction gives, and anything else (a round cut, an
imported part) as the convex pieces its own faces cut it into (kernel/split.py). A bore or other inward round face
becomes flat facets, and the record states how far inside it they sit. Only a piece with a free-form face or an inward
ball is used as its convex hull: its solid is listed, and its geoms are marked so the runner can say when a piece
touched one. The piece is a free body built from its one 3D definition. Nothing here imports MuJoCo; the model is
plain text.

A solid that a declared drive turns (a roller, a wheel, a belt) stays a still, frictionless shape; the friction of
its moving surface is worked out by the planar engine's smooth law and applied to the piece as a force. A group that
a mover drives along a design motion becomes a body on one hinge or one slider when its motion is that simple, and
is otherwise carried along its path. A flap is its drawn solid on a sprung hinge. Custom forces are refused by name.
"""
import math

from ..builder import placement
from ..builder.shape import make
from ..kernel import split
from ..kernel.mesh import triangles
from ..kernel.props import bounds, volume
from ..kernel.section import AXES
from ..motion import matrix as mx
from ..motion import ops
from . import air, convex, frames
from .inputs import plain
from .mujoco_parts import MM, bodies_xml, driven_by, fail, flap_of, mover_of, piece_body, quaternion, start_of, text
from .scene import drives_for
from .ready import breakdown

LAW = ("the library's own spring, damper and friction law at the points MuJoCo finds; where a piece touches one surface at several points, "
       "the surface's spring is shared among them by depth; a round piece's point against a mesh or a cylinder is worked out again from the piece's core")
NOT_YET = ("forces",)
PROBE = '<geom name="probe" type="sphere" size="1e-9" contype="0" conaffinity="0"/>'      # a point the contact law measures from


_PIECES = {}


def pieces_of(solid):
    """split.convex_pieces, remembered by the solid's size and place, so a campaign splits each solid once per process."""
    key = (round(volume(solid), 6), tuple(round(v, 6) for v in bounds(solid)))
    if key not in _PIECES:
        _PIECES[key] = split.convex_pieces(solid)
    return _PIECES[key]


def primitive(shape, placed_at):
    """A geom's attributes for a sharp box, a ball or a full cylinder, moved by a transform; None for any other shape."""
    kind = shape["kind"]
    if kind == "box" and not shape.get("edgeRadiusMm"):
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
        self.meshes, self.geoms, self.hulled, self.kinds, self.faceted, self.body, self.driven, self.driven_geoms, self.material_of = [], [], [], {}, {}, "world", None, {}, {}
        self.rough, self.rough_geoms = {}, {}

    def add(self, solid, surface, shape, placed_at, material):
        """Add the geoms of one shape entry, part by part where it is a union."""
        if shape["kind"] == "union":
            for part in shape["of"]:
                self.add(solid, surface, part, placed_at, material)
            return
        found = primitive(shape, placed_at)
        broken = convex.pieces(shape) if found is None and breakdown(shape) != "convex" else None
        if broken is not None:      # its true convex pieces, from how it was built: nothing is filled in
            for points in broken[0]:
                self.geom(solid, surface, self.mesh([mx.scale(mx.apply(placed_at, p), MM) for p in points]), material)
            if broken[1]:
                self.faceted[solid] = broken[1]
            return
        if found is None:
            built = make(shape, f'solid "{solid}"', None)
            if breakdown(shape) == "convex":
                found = self.mesh([mx.scale(mx.apply(placed_at, v), MM) for v in triangles(built, 0.2)["vertices"]])
            else:
                return self.split(solid, surface, built, placed_at, material)
        self.geom(solid, surface, found, material)

    def split(self, solid, surface, built, placed_at, material):
        """A solid with no construction to read, as the convex pieces its own faces cut it into. An inward round face
        is wedged into flat facets, and said so. A piece a free-form face or an inward ball keeps from being convex is
        hulled: the solid is listed with the share of it so taken, and the hulled piece's geom is marked as rough."""
        done, rough, faceted = pieces_of(built)
        for piece, is_rough in [(p, False) for p in done] + [(p, True) for p in rough]:
            if is_rough:
                self.rough_geoms[f"g{len(self.geoms)}"] = solid
            self.geom(solid, surface, self.mesh([mx.scale(mx.apply(placed_at, v), MM) for v in triangles(piece, 0.2)["vertices"]]), material)
        if faceted > 0:
            self.faceted[solid] = f"its inward round faces (bores, countersinks, wraps) as flat facets, at most {faceted:.2f} mm inside them"
        if rough:
            self.hulled.append(solid)
            self.rough[solid] = round(sum(volume(p) for p in rough) / volume(built), 4)

    def mesh(self, points):
        name = f"mesh{len(self.meshes)}"
        self.meshes.append(f'<mesh name="{name}" vertex="{text(v for p in points for v in p)}"/>')
        return {"type": "mesh", "mesh": name}

    def geom(self, solid, surface, found, material):
        """One shape of a surface. It is found touching a piece, never another surface."""
        name = f"g{len(self.geoms)}"
        fields = " ".join(f'{key}="{value}"' for key, value in found.items())
        if self.driven:
            self.driven_geoms[name] = self.driven
        self.material_of[name] = material
        self.geoms.append((name, surface, f'<geom name="{name}" {fields} contype="0" conaffinity="1"/>', self.body))
        self.kinds.setdefault(solid, []).append(found["type"])


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
    placed, model, moving, sections = assembly.at_pose(case.get("pose")), Model(), {}, []
    flaps = [(entry, flap_of(entry, plane, f'{where} flap "{entry["name"]}"')) for entry in case.get("flaps", [])]
    for entry, flap in [(entry, None) for entry in case["surfaces"]] + flaps:
        if "solid" not in entry:
            fail(f'{where} surface "{entry.get("name", "surface")}"', "the MuJoCo engine needs every surface to come from a solid", "Draw the surface as a solid and name it")
        solid, surface = entry["solid"], entry.get("name", entry["solid"])
        if solid not in built:
            fail(f'{where} "{surface}"', f'names the solid "{solid}", which the design does not have', "Name a solid or fixture of the design")
        source = built[solid]
        group, where_at = source["group"], posed[source["group"]]
        turned = None if flap else driven_by(case, solid)
        moved = mover_of(case, assembly, group, entry.get("mover"), where)
        if flap and moved:      # a flap on a moved group rides inside that group's body
            if moved["kind"] == "path":
                fail(f'{where} flap "{surface}"', "the MuJoCo engine cannot hinge a flap on a group that is carried along a path", "Give the group a single slide or turn")
            moving[f"{group}:{moved['mover']}"] = moved
            flap["parent"] = f"{group}:{moved['mover']}"
        moved = flap or moved
        model.body = "world" if not moved else f"flap:{surface}" if flap else f"{group}:{moved['mover']}"
        model.driven = turned
        if moved:
            moving[model.body] = moved
            where_at = moved.get("start", where_at)       # a moved group is drawn where its motion starts
        sections.append({"solid": solid, "surface": surface})
        if "shape" in source and source["shape"]["kind"] != "custom":
            at = mx.chain([ops.at(source.get("place", [])), ops.at(groups[group].get("place", [])), where_at])
            model.add(solid, surface, source["shape"], at, entry["material"])
        else:       # an imported part or a custom shape: no construction to read, so it is split at its own faces
            model.split(solid, surface, placed[solid], mx.compose(where_at, mx.inverse(posed[group])), entry["material"])
    start = {**start_of(case, handed), "level": plane["atMm"] * MM}
    segments = int(case.get("mujoco", {}).get("ringSegments", 32))
    others, other_xml = {}, ""
    for other in case.get("others", []):
        another = case["pieces"][other["use"]]
        begin = {"at": [v * MM for v in other["atMm"]], "velocity": list(other.get("velocityMps", [0.0, 0.0])), "spin": 0.0,
                 "level": (plane["atMm"] + other.get("acrossMm", 0.0)) * MM}
        found = piece_body(other["use"], another, another["massKg"], begin, plane["normal"], segments, f'other:{other["name"]}')
        other_xml += found[0]
        others[other["name"]] = {"velocity": found[1], "massKg": another["massKg"], "air": air.params(case, other["use"], found[2], where)}
    body, velocity, radius = piece_body(use, piece, mass, start, plane["normal"], segments)
    gravity = [0.0, 0.0, 0.0 if plane["normal"] == "z" else -case.get("gravityMps2", 9.80665)]
    xml = (f'<mujoco><option timestep="{case["stepS"]:.9g}" gravity="{text(gravity)}"><flag multiccd="enable"/></option>'
           f'<asset>{"".join(model.meshes)}</asset><worldbody>{PROBE}{bodies_xml(model, moving)}{other_xml}{body}</worldbody></mujoco>')
    drives = drives_for(case, where) if model.driven_geoms else {}
    facts = {"plane": plane, "pose": case.get("pose"), "geoms": model.kinds, "hulled": sorted(set(model.hulled)), "hulledShare": model.rough,
             "faceted": model.faceted, "sections": sections, "typedSurfaces": [], "bodies": {key: entry["kind"] for key, entry in moving.items()},
             "driven": {row["solid"]: turned["drive"] for row in sections for turned in [driven_by(case, row["solid"])] if turned},
             "others": {other["name"]: other["use"] for other in case.get("others", [])},
             "piece": {"piece": use, "shape": piece["shape"]["kind"], "radiusMm": round(radius / MM, 6), **({"ringSegments": segments} if piece["shape"]["kind"] == "torus" else {})},
             "contactLaw": LAW}
    return {"engine": "mujoco", "xml": xml, "surfaceOf": {g: surface for g, surface, _, _ in model.geoms},
            "axes": ["xyz"[i] for i in AXES[plane["normal"]]], "normal": plane["normal"], "levelM": plane["atMm"] * MM, "startVelocity": velocity, "radiusM": radius,
            "massKg": mass, "others": others, "stepS": case["stepS"], "durationS": case["durationS"], "traceS": case.get("traceS", 0.002),
            "rest": {"speedMps": 0.005, "rimSpeedMps": 0.005, **case.get("rest", {})}, "moving": moving, "driven": model.driven_geoms, "materialOf": model.material_of, "roughGeoms": model.rough_geoms,
            "materials": case["materials"], "between": case.get("betweenPieces"), "options": case.get("planar", {}),
            "events": case.get("events", []), "measures": case.get("measures", {}), "drives": drives,
            "hinges": {flap["flap"]: f"flap:{flap['flap']}" for _, flap in flaps}, "movers": {}, "frames": frames.build(case, assembly.data, where), "air": air.params(case, use, radius, where), "loads": case.get("loads", []), "surfaces": [], "facts": facts}
