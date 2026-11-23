"""Run a MuJoCo scene and report it in the same shape as a planar run, so the method and the record do not change.

MuJoCo finds the touching points and moves the bodies; the contact forces are the library's own (mujoco_contact.py).
Each step is two passes: one with MuJoCo's contacts on, only to find what overlaps, and one with them off, to move
everything under the library's forces. So MuJoCo's own contact solver never pushes on anything.
MuJoCo is imported only here, and only when a trial names this engine. Install it with the optional extra:
pip install "frc-design-kernel[mujoco] @ git+https://github.com/ehartye/frc-design-kernel"
"""
import math

from ..errors import DesignError
from ..motion import matrix as mx
from ..motion import stages as stage_math
from . import drives as drive_math
from . import frames, mujoco_contact
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
    names += frames.names(scene["frames"], scene["normal"])
    for name in scene["others"]:
        names += [f"other.{name}.{a}Mm", f"other.{name}.{b}Mm", f"other.{name}.offPlaneMm", f"other.{name}.speedMps", f"contact.piece {name}.forceN"]
    for name in dict.fromkeys(scene["surfaceOf"].values()):
        names += [f"contact.{name}.forceN", f"contact.{name}.depthMm"]
    return names


def read(model, data, scene, blank, drive_state, pieces, pressed):
    """The signals now and the contact depth per surface. Spin is counted the planar way: counter-clockwise in (u, v)."""
    iu, iv = ("xyz".index(axis) for axis in scene["axes"])
    across, piece = "xyz".index(scene["normal"]), model.body("piece").id
    position, velocity = data.qpos[-7:-4], data.qvel[-6:-3]
    signals = dict(blank)
    turn = data.qvel[-3 + across] * (-1.0 if scene["normal"] == "y" else 1.0)
    # how far the piece's own axis (the plane normal, at the start) has leaned away from where it began
    lean = max(-1.0, min(1.0, float(data.xmat[piece].reshape(3, 3)[across, across])))
    signals.update({"tS": float(data.time), f"{scene['axes'][0]}Mm": float(position[iu]) * 1e3, f"{scene['axes'][1]}Mm": float(position[iv]) * 1e3,
                    "spinRadps": float(turn), "speedMps": float(math.hypot(velocity[iu], velocity[iv])),
                    "offPlaneMm": float(position[across] - scene["levelM"]) * 1e3, "tiltDeg": math.degrees(math.acos(lean))})
    for name, body in scene["hinges"].items():
        signals[f"hinge.{name}.angleDeg"] = math.degrees(float(data.qpos[model.joint(body).qposadr[0]]))
    for name, state in drive_state.items():
        signals[f"drive.{name}.speedMps"], signals[f"drive.{name}.currentA"], signals[f"drive.{name}.supplyA"] = state["u"], state["amps"], state["supply"]
    for body, name in pieces.items():
        if name is not None:
            at, free = data.xpos[body], model.body_dofadr[body]
            signals.update({f"other.{name}.{scene['axes'][0]}Mm": float(at[iu]) * 1e3, f"other.{name}.{scene['axes'][1]}Mm": float(at[iv]) * 1e3,
                            f"other.{name}.offPlaneMm": float(at[across] - scene["levelM"]) * 1e3,
                            f"other.{name}.speedMps": float(math.sqrt(sum(v * v for v in data.qvel[free:free + 3])))})
    touching = {}
    for (on, (kind, what)), (force, deepest) in pressed.items():
        if kind == "piece" and piece in (on, what):      # the trial's piece against another one
            signals[f"contact.piece {pieces[what if on == piece else on]}.forceN"] += force
        elif kind == "surface" and on == piece:
            touching[what] = max(touching.get(what, 0.0), deepest)
            signals[f"contact.{what}.forceN"] += force
            signals[f"contact.{what}.depthMm"] = touching[what] * 1e3
    return signals, touching


def drive_bodies(model, data, scene, happened, t):
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


def start(mujoco, scene, dt):
    """The model and its data at the start, the piece bodies {body: name, None for the trial's own} and their masses."""
    model = mujoco.MjModel.from_xml_string(scene["xml"])
    model.opt.timestep = dt
    data = mujoco.MjData(model)
    data.qvel[-6:] = scene["startVelocity"]
    piece = model.body("piece").id
    pieces, masses = {piece: None}, {piece: scene["massKg"]}
    for name, other in scene["others"].items():
        body = model.body(f"other:{name}").id
        free = model.body_dofadr[body]
        data.qvel[free:free + 6] = other["velocity"]
        pieces[body], masses[body] = name, other["massKg"]
    return model, data, pieces, masses


def push(mujoco, model, data, scene, law, pieces, masses, drive_state, happened, t, dt):
    """Set this step's forces from the state now: flap preloads, contact forces, and the loads every piece feels."""
    data.qfrc_applied[:] = 0.0
    for entry in scene["moving"].values():
        if entry["kind"] == "flap":     # the spring's preload holds the flap on its rest stop
            data.qfrc_applied[model.joint(f"flap:{entry['flap']}").dofadr[0]] = -entry["preloadNm"]
    pressed, loads = mujoco_contact.apply(mujoco, model, data, scene, law, pieces, drive_state, dt)
    iu, iv = ("xyz".index(axis) for axis in scene["axes"])
    for body in pieces:       # every piece rides in the same frame, so every piece feels each load
        wrench = [0.0] * 6
        for load in scene["loads"]:
            along = load_force(load, masses[body], happened, t)
            wrench[iu] += along[0]
            wrench[iv] += along[1]
        data.xfrc_applied[body] = wrench
    return pressed, loads


def run(scene, step=None, forces=()):
    """Run one MuJoCo scene. Returns the same summary a planar run gives, with two more signals: offPlaneMm and tiltDeg."""
    mujoco = engine()
    dt = step or scene["stepS"]
    model, data, pieces, masses = start(mujoco, scene, dt)
    law = mujoco_contact.Law(scene, masses)
    drive_state = {name: drive_math.start(d) for name, d in scene["drives"].items()}
    happened, events, rest_since, steps, outcome = {}, [], None, 0, "timeout"
    names = signal_names(scene)
    blank = dict.fromkeys(names, 0.0)
    recorder = Recorder(scene, [n for n in names if not n.startswith("contact.") and n != "speedMps"])
    no_contact = int(mujoco.mjtDisableBit.mjDSBL_CONTACT)
    while True:
        t = float(data.time)
        drive_bodies(model, data, scene, happened, t)
        mujoco.mj_fwdPosition(model, data)      # where everything is now, and what overlaps
        mujoco.mj_fwdVelocity(model, data)      # how everything moves now
        pressed, loads = push(mujoco, model, data, scene, law, pieces, masses, drive_state, happened, t, dt)
        signals, touching = read(model, data, scene, blank, drive_state, pieces, pressed)
        signals.update(frames.read(scene["frames"], scene["normal"], [float(v) * 1e3 for v in data.qpos[-7:-4]], happened, t))
        if steps == 0:
            recorder.sample(0.0, signals, 0, dt, force=True)
        else:
            resting = signals["speedMps"] < scene["rest"]["speedMps"] and abs(signals["spinRadps"]) * scene["radiusM"] < scene["rest"]["rimSpeedMps"]
            rest_since = (t if rest_since is None else rest_since) if resting else None
            recorder.contacts(t, touching)
            recorder.measure(signals)
            recorder.sample(t, signals, steps, dt)
            stop = fire(scene, signals, happened, events, rest_since, t)
            if stop is not None:
                outcome = stop
                break
        if t >= scene["durationS"] - 0.5 * dt:
            break
        for name, drive in scene["drives"].items():
            for rule in drive.get("rules", ()):
                if holds(rule["when"], signals, happened, rest_since, t):
                    drive = {**drive, **rule["set"]}
            drive_math.step(drive, drive_state[name], loads[name], t, dt)
        model.opt.disableflags |= no_contact
        mujoco.mj_step(model, data)             # move everything one step under those forces, with MuJoCo's own contact off
        model.opt.disableflags &= ~no_contact
        steps += 1
    recorder.sample(float(data.time), signals, steps, dt, force=True)
    iu, iv = ("xyz".index(axis) for axis in scene["axes"])
    return {"outcome": outcome, "endS": float(data.time), "steps": steps, "stepS": dt, "events": events, "measures": recorder.finish(signals, happened),
            "end": {"piece": [float(data.qpos[-7 + iu]), float(data.qpos[-7 + iv]), float(data.qvel[-6 + iu]), float(data.qvel[-6 + iv]), signals["spinRadps"]],
                    "drives": {n: s["u"] for n, s in drive_state.items()}, "hingesDeg": {name: signals[f"hinge.{name}.angleDeg"] for name in scene["hinges"]},
                    "offPlaneMm": signals["offPlaneMm"], "tiltDeg": signals["tiltDeg"]},
            "trace": {"columns": recorder.columns, "rows": recorder.trace},
            "contacts": {name: [[r[0], r[1], round(r[2], 4)] for r in rows] for name, rows in recorder.rows.items()}}
