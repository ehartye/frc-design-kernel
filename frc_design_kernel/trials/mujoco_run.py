"""Run a MuJoCo scene and report it in the same shape as a planar run, so the method and the record do not change.

MuJoCo is imported only here, and only when a trial names this engine. Install it with the optional extra:
pip install "frc-design-kernel[mujoco] @ git+https://github.com/ehartye/frc-design-kernel"
"""
import math

from ..errors import DesignError
from ..motion import matrix as mx
from ..motion import stages as stage_math
from . import drives as drive_math
from .mujoco_scene import quaternion
from .planar import Recorder, fire, load_force
from .rules import holds, started


def engine():
    try:
        import mujoco
    except ImportError:
        raise DesignError("", "a trial names the MuJoCo engine, but MuJoCo is not installed",
                          'Install the optional extra: pip install "frc-design-kernel[mujoco] @ git+https://github.com/ehartye/frc-design-kernel"') from None
    return mujoco


def version():
    return engine().__version__


def signal_names(scene):
    a, b = scene["axes"]
    names = ["tS", f"{a}Mm", f"{b}Mm", "spinRadps", "speedMps", "offPlaneMm", "tiltDeg"]
    for name in scene["drives"]:
        names += [f"drive.{name}.speedMps", f"drive.{name}.currentA", f"drive.{name}.supplyA"]
    names += [f"hinge.{name}.angleDeg" for name in scene["hinges"]]
    for name in dict.fromkeys(scene["surfaceOf"].values()):
        names += [f"contact.{name}.forceN", f"contact.{name}.depthMm"]
    return names


def drag(mujoco, model, data, driven, speed, normal, at, pressing, piece):
    """The friction a driven surface puts on the piece at one contact: (force, torque about the piece, load on the drive).

    The surface runs at the drive's speed across its axis. The law is the planar engine's smooth one: friction times
    the pressing force, against the slip, eased near zero slip.
    """
    along = mx.cross(driven["axis"], normal)
    turn = [float(v) for v in data.xmat[piece].reshape(3, 3) @ data.qvel[-3:]]
    arm = mx.sub(at, [float(v) for v in data.xpos[piece]])
    point = mx.add([float(v) for v in data.qvel[-6:-3]], mx.cross(turn, arm))
    slip = mx.sub(point, mx.scale(along, speed * driven["ratio"]))
    if driven["body"]:      # a driven surface on a moved group also moves with the group
        import numpy
        carrier, found = model.body(driven["body"]).id, numpy.zeros(6)
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, carrier, found, 0)
        moving = [float(v) for v in found]      # how the group turns, then how its origin moves
        slip = mx.sub(slip, mx.add(moving[3:], mx.cross(moving[:3], mx.sub(at, [float(v) for v in data.xpos[carrier]]))))
        slip = mx.sub(slip, mx.scale(normal, mx.dot(slip, normal)))
    slip = mx.sub(slip, mx.scale(normal, mx.dot(slip, normal)))
    force = mx.scale(slip, -driven["mu"] * pressing / math.sqrt(mx.dot(slip, slip) + driven["eps"] ** 2))
    return list(force), list(mx.cross(arm, force)), driven["ratio"] * mx.dot(force, along)


def read(mujoco, model, data, scene, blank, wrench, drive_state):
    """The signals now, the contact depth per surface, the load each drive feels, and the driven-surface friction to apply.

    Spin is counted the planar way: counter-clockwise in (u, v).
    """
    iu, iv = ("xyz".index(axis) for axis in scene["axes"])
    across, piece = "xyz".index(scene["normal"]), model.body("piece").id
    position, velocity = data.qpos[-7:-4], data.qvel[-6:-3]
    signals = dict(blank)
    turn = data.qvel[-3 + across] * (-1.0 if scene["normal"] == "y" else 1.0)
    # how far the piece's own axis (the plane normal, at the start) has leaned away from where it began
    rotation = data.xmat[piece].reshape(3, 3)
    lean = max(-1.0, min(1.0, float(rotation[across, across])))
    signals.update({"tS": float(data.time), f"{scene['axes'][0]}Mm": float(position[iu]) * 1e3, f"{scene['axes'][1]}Mm": float(position[iv]) * 1e3,
                    "spinRadps": float(turn), "speedMps": float(math.hypot(velocity[iu], velocity[iv])),
                    "offPlaneMm": float(position[across] - scene["levelM"]) * 1e3, "tiltDeg": math.degrees(math.acos(lean))})
    for name, body in scene["hinges"].items():
        signals[f"hinge.{name}.angleDeg"] = math.degrees(float(data.qpos[model.joint(body).qposadr[0]]))
    for name, state in drive_state.items():
        signals[f"drive.{name}.speedMps"], signals[f"drive.{name}.currentA"], signals[f"drive.{name}.supplyA"] = state["u"], state["amps"], state["supply"]
    touching, loads, applied = {}, dict.fromkeys(scene["drives"], 0.0), [0.0] * 6
    for index in range(data.ncon):
        contact = data.contact[index]
        names = (model.geom(contact.geom1).name, model.geom(contact.geom2).name)
        other = next((n for n in names if n in scene["surfaceOf"]), None)
        if other is None or piece not in (model.geom_bodyid[contact.geom1], model.geom_bodyid[contact.geom2]) or contact.dist >= 0:
            continue
        surface = scene["surfaceOf"][other]
        mujoco.mj_contactForce(model, data, index, wrench)
        touching[surface] = max(touching.get(surface, 0.0), -float(contact.dist))
        signals[f"contact.{surface}.forceN"] += float(wrench[0])
        signals[f"contact.{surface}.depthMm"] = touching[surface] * 1e3
        driven = scene["driven"].get(other)
        if driven:
            normal = [float(v) * (1.0 if names[0] == other else -1.0) for v in contact.frame[:3]]       # out of the surface, toward the piece
            force, torque, load = drag(mujoco, model, data, driven, drive_state[driven["drive"]]["u"], normal, [float(v) for v in contact.pos], float(wrench[0]), piece)
            applied = [a + b for a, b in zip(applied, force + torque)]
            loads[driven["drive"]] += load
    return signals, touching, loads, applied


def drive_bodies(model, data, scene, drive_state, happened, t):
    """Set every moved group for this step: along its hinge or slider, or carried along its path."""
    for key, entry in scene["moving"].items():
        if entry["kind"] == "flap":     # a flap swings freely on its spring
            continue
        begin = started(entry, happened, t)
        fraction = 0.0 if begin is None else min(1.0, (t - begin) / entry["durationS"])
        if entry["kind"] == "path":
            listed = [(kind, value) for kind, value in entry["stages"]]
            shift = mx.compose(stage_math.at(listed, fraction), mx.inverse(entry["start"]))
            body = model.body(key).mocapid[0]
            data.mocap_pos[body] = [shift[3] * 1e-3, shift[7] * 1e-3, shift[11] * 1e-3]
            data.mocap_quat[body] = quaternion(shift)
        else:
            joint = model.joint(key)
            data.qpos[joint.qposadr[0]] = fraction * entry["travel"]
            data.qvel[joint.dofadr[0]] = entry["travel"] / entry["durationS"] if 0.0 < fraction < 1.0 or (begin is not None and fraction == 0.0) else 0.0


def run(scene, step=None, forces=()):
    """Run one MuJoCo scene. Returns the same summary a planar run gives, with two more signals: offPlaneMm and tiltDeg."""
    import numpy
    mujoco = engine()
    model = mujoco.MjModel.from_xml_string(scene["xml"])
    dt = step or scene["stepS"]
    model.opt.timestep = dt
    data = mujoco.MjData(model)
    data.qvel[-6:] = scene["startVelocity"]
    drive_state = {name: drive_math.start(d) for name, d in scene["drives"].items()}
    happened, events, rest_since, steps, outcome = {}, [], None, 0, "timeout"
    for entry in scene["moving"].values():
        if entry["kind"] == "flap":     # the spring's preload holds the flap on its rest stop
            data.qfrc_applied[model.joint(f"flap:{entry['flap']}").dofadr[0]] = -entry["preloadNm"]
    drive_bodies(model, data, scene, drive_state, happened, 0.0)
    mujoco.mj_forward(model, data)
    names = signal_names(scene)
    blank, wrench = dict.fromkeys(names, 0.0), numpy.zeros(6)
    recorder = Recorder(scene, [n for n in names if not n.startswith("contact.") and n != "speedMps"])
    signals, touching, loads, applied = read(mujoco, model, data, scene, blank, wrench, drive_state)
    recorder.sample(0.0, signals, 0, dt, force=True)
    piece = model.body("piece").id
    iu, iv = ("xyz".index(axis) for axis in scene["axes"])
    while data.time < scene["durationS"]:
        t = float(data.time)
        for name, drive in scene["drives"].items():
            for rule in drive.get("rules", ()):
                if holds(rule["when"], signals, happened, rest_since, t):
                    drive = {**drive, **rule["set"]}
            drive_math.step(drive, drive_state[name], loads[name], t, dt)
        drive_bodies(model, data, scene, drive_state, happened, t)
        for load in scene["loads"]:
            along = load_force(load, scene["massKg"], happened, t)
            applied[iu] += along[0]
            applied[iv] += along[1]
        data.xfrc_applied[piece] = applied
        mujoco.mj_step(model, data)
        steps += 1
        t = float(data.time)
        signals, touching, loads, applied = read(mujoco, model, data, scene, blank, wrench, drive_state)
        resting = signals["speedMps"] < scene["rest"]["speedMps"] and abs(signals["spinRadps"]) * scene["radiusM"] < scene["rest"]["rimSpeedMps"]
        rest_since = (t if rest_since is None else rest_since) if resting else None
        recorder.contacts(t, touching)
        recorder.measure(signals)
        recorder.sample(t, signals, steps, dt)
        stop = fire(scene, signals, happened, events, rest_since, t)
        if stop is not None:
            outcome = stop
            break
    recorder.sample(float(data.time), signals, steps, dt, force=True)
    return {"outcome": outcome, "endS": float(data.time), "steps": steps, "stepS": dt, "events": events, "measures": recorder.finish(signals, happened),
            "end": {"piece": [float(data.qpos[-7 + iu]), float(data.qpos[-7 + iv]), float(data.qvel[-6 + iu]), float(data.qvel[-6 + iv]), signals["spinRadps"]],
                    "drives": {n: s["u"] for n, s in drive_state.items()}, "hingesDeg": {name: signals[f"hinge.{name}.angleDeg"] for name in scene["hinges"]}, "offPlaneMm": signals["offPlaneMm"], "tiltDeg": signals["tiltDeg"]},
            "trace": {"columns": recorder.columns, "rows": recorder.trace},
            "contacts": {name: [[r[0], r[1], round(r[2], 4)] for r in rows] for name, rows in recorder.rows.items()}}
