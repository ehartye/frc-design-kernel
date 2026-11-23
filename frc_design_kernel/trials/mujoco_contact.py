"""The library's own contact law, applied at the points MuJoCo finds.

MuJoCo finds where shapes overlap and moves the bodies. The force at each touching point is worked out here, with
the same spring, damper and friction law the planar engine uses, so one set of material numbers means the same
thing in both engines. MuJoCo's own contact forces are switched off. Measured on a piece squeezed between two
surfaces, they came out 4 to 21 times the spring law across the settings tried, and a resting piece sank to a
twentieth of the spring's depth.

One rule is added for three dimensions: where a piece touches one surface at several points, the surface's spring
is shared among them by depth, so a ring lying flat is held by one spring, not by one spring per point.
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
        at = [float(v) for v in contact.pos]
        against, driven, along = velocity_at(mujoco, model, data, other, at, seen), scene["driven"].get(name), None
        if driven:      # a driven surface also runs at its drive's speed, across the turn's axis
            along = mx.cross(driven["axis"], normal)
            against = mx.add(against, mx.scale(along, drive_state[driven["drive"]]["u"] * driven["ratio"]))
        between = other in pieces
        count[geoms] = count.get(geoms, 0) + 1
        groups.setdefault((on, ("piece", other) if between else ("surface", scene["surfaceOf"][name])), []).append({
            "key": (*geoms, count[geoms]), "at": at, "normal": normal, "depth": -float(contact.dist), "other": other, "driven": driven, "along": along,
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
