"""The library's own contact law, applied at the points MuJoCo finds.

MuJoCo finds where shapes overlap and moves the bodies. The force at each touching point is worked out here, with
the same spring, damper and friction law the planar engine uses, so one set of material numbers means the same
thing in both engines. MuJoCo's own contact forces are switched off. Measured on a piece squeezed between two
surfaces, they came out 4 to 21 times the spring law across the settings tried, and a resting piece sank to a
twentieth of the spring's depth.

One rule is added for three dimensions: where a piece touches one surface at several points, the surface's spring
is shared among them by depth, so a ring lying flat is held by one spring, not by one spring per point.

Where a round piece (a ball, or a ring's round segment) meets a shape MuJoCo collides by its general convex method (a
mesh or a cylinder), the touching point is worked out again from the piece's core: the nearest point of the shape to
the core gives the true direction and depth. At an edge or a corner MuJoCo's general method reports a face's
direction instead, up to 37 degrees off on a bevelled lip, and too shallow a depth.
"""
import math

from ..motion import matrix as mx
from .scene import material


class Law:
    """The materials as the contact law needs them, and the stick law's memory from the step before."""

    def __init__(self, scene, masses):
        self.scene, self.masses, self.ready, self.memory = scene, masses, {}, {}

    def material(self, name, mass):
        if (name, mass) not in self.ready:
            self.ready[(name, mass)] = material(self.scene["materials"][name], mass, self.scene["options"])
        return self.ready[(name, mass)]


def velocity_at(mujoco, model, data, body, at, seen):
    """How fast the point `at` of a body moves. The world and a path-carried body stand still."""
    if body == 0:
        return (0.0, 0.0, 0.0)
    if body not in seen:
        import numpy
        found = numpy.zeros(6)
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, body, found, 0)
        seen[body] = ([float(v) for v in found[:3]], [float(v) for v in found[3:]], [float(v) for v in data.xipos[body]])      # a body's velocity is given at its centre of mass
    turn, move, origin = seen[body]
    return mx.add(move, mx.cross(turn, mx.sub(at, origin)))


ROUND, GENERAL = (2, 3), (5, 7)        # MuJoCo geom types: sphere, capsule; cylinder, mesh


def from_core(mujoco, model, data, piece_geom, other_geom, at):
    """The true (point, normal, depth) where a round piece geom meets a general convex shape, or None where they do not meet.

    The core is the ball's centre, or the nearest point of the capsule's centre line to MuJoCo's point. A probe point
    put there is measured against the shape by MuJoCo's distance query, which is exact when the two are apart.
    Returns False when the core is inside the shape, so MuJoCo's own point is kept.
    """
    import numpy
    centre, radius = data.geom_xpos[piece_geom], float(model.geom_size[piece_geom][0])
    core = numpy.array(centre)
    if model.geom_type[piece_geom] == 3:
        axis, half = data.geom_xmat[piece_geom].reshape(3, 3)[:, 2], float(model.geom_size[piece_geom][1])
        core = core + axis * max(-half, min(half, float(numpy.dot(numpy.array(at) - centre, axis))))
    probe = model.geom("probe").id
    data.geom_xpos[probe] = core
    ends = numpy.zeros(6)
    gap = mujoco.mj_geomDistance(model, data, probe, other_geom, radius, ends)
    if gap <= 1e-9:
        return False
    if gap >= radius:
        return None
    normal = (core - ends[3:]) / gap
    return [float(v) for v in ends[3:] - normal * (radius - gap) / 2], [float(v) for v in normal], radius - gap


def touching_points(mujoco, model, data, scene, pieces, drive_state):
    """Every point where a piece overlaps a surface or another piece: {(piece body, what it touches): [point, ...]}."""
    groups, seen, count = {}, {}, {}
    for index in range(data.ncon):
        contact = data.contact[index]
        if contact.dist >= 0:
            continue
        geoms = (int(contact.geom1), int(contact.geom2))
        bodies = (int(model.geom_bodyid[geoms[0]]), int(model.geom_bodyid[geoms[1]]))
        side = 1 if bodies[1] in pieces else 0
        on, other = bodies[side], bodies[1 - side]
        if on not in pieces:
            continue
        name = model.geom(geoms[1 - side]).name
        normal = [float(v) * (1.0 if side == 1 else -1.0) for v in contact.frame[:3]]      # out of what is touched, toward the piece
        at, depth = [float(v) for v in contact.pos], -float(contact.dist)
        if model.geom_type[geoms[side]] in ROUND and model.geom_type[geoms[1 - side]] in GENERAL:
            exact = from_core(mujoco, model, data, geoms[side], geoms[1 - side], at)
            if exact is None:
                continue
            if exact:
                at, normal, depth = exact
        against, driven, along = velocity_at(mujoco, model, data, other, at, seen), scene["driven"].get(name), None
        if driven:      # a driven surface also runs at its drive's speed, across the turn's axis
            along = mx.cross(driven["axis"], normal)
            against = mx.add(against, mx.scale(along, drive_state[driven["drive"]]["u"] * driven["ratio"]))
        between = other in pieces
        count[geoms] = count.get(geoms, 0) + 1
        groups.setdefault((on, ("piece", other) if between else ("surface", scene["surfaceOf"][name])), []).append({
            "key": (*geoms, count[geoms]), "at": at, "normal": normal, "depth": depth, "other": other, "driven": driven, "along": along,
            "rel": mx.sub(velocity_at(mujoco, model, data, on, at, seen), against), "material": scene["between"] if between else scene["materialOf"][name]})
    return groups


def rub(point, share, pressing, mat, memory, kept, dt):
    """The friction at one point, as a vector: the planar engine's smooth or stick law, with this point's share of the surface."""
    normal = point["normal"]
    slip = mx.sub(point["rel"], mx.scale(normal, mx.dot(point["rel"], normal)))
    if pressing <= 0:
        return (0.0, 0.0, 0.0)
    if mat["law"] == "smooth":
        return mx.scale(slip, -mat["mu"] * pressing / math.sqrt(mx.dot(slip, slip) + mat["eps"] ** 2))
    stretch = mx.add(memory.get(point["key"], (0.0, 0.0, 0.0)), mx.scale(slip, dt))
    stretch = mx.sub(stretch, mx.scale(normal, mx.dot(stretch, normal)))
    force = mx.sub(mx.scale(stretch, -share * mat["kt"]), mx.scale(slip, share * mat["ct"]))
    size, cap = mx.length(force), mat["mu"] * pressing
    if size > cap:
        force = mx.scale(force, cap / size)
        stretch = mx.scale(force, -1.0 / (share * mat["kt"]))
    kept[point["key"]] = stretch
    return force


def apply(mujoco, model, data, scene, law, pieces, drive_state, dt):
    """Work out and apply the force at every touching point.

    Returns ({(piece body, what it touches): (pressing force, deepest overlap)}, the load each drive feels).
    """
    import numpy
    found, loads, kept, none = {}, dict.fromkeys(scene["drives"], 0.0), {}, numpy.zeros(3)
    for (on, what), points in touching_points(mujoco, model, data, scene, pieces, drive_state).items():
        other, masses = points[0]["other"], law.masses
        mass = masses[on] * masses[other] / (masses[on] + masses[other]) if what[0] == "piece" else masses[on]
        mat = law.material(points[0]["material"], mass)
        total, deepest = sum(p["depth"] for p in points), max(p["depth"] for p in points)
        closing = sum(p["depth"] / total * mx.dot(p["rel"], p["normal"]) for p in points)
        pressing = max(0.0, mat["k"] * deepest - mat["c"] * closing)
        found[(on, what)] = (pressing, deepest)
        for p in points:
            share = p["depth"] / total
            rubbing = rub(p, share, share * pressing, mat, law.memory, kept, dt)
            force, at = numpy.array(mx.add(mx.scale(p["normal"], share * pressing), rubbing)), numpy.array(p["at"])
            mujoco.mj_applyFT(model, data, force, none, at, on, data.qfrc_applied)
            if other:       # what is touched feels the same force back: another piece, or a flap on its spring
                mujoco.mj_applyFT(model, data, -force, none, at, other, data.qfrc_applied)
            if p["driven"]:     # only friction loads a drive: the part of it that lies along the way the surface runs
                loads[p["driven"]["drive"]] += p["driven"]["ratio"] * mx.dot(rubbing, p["along"])
    law.memory = kept
    return found, loads
