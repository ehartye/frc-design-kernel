"""Run a MuJoCo scene and report it in the same shape as a planar run, so the method and the record do not change.

MuJoCo is imported only here, and only when a trial names this engine. Install it with the optional extra:
pip install "frc-design-kernel[mujoco] @ git+https://github.com/ehartye/frc-design-kernel"
"""
import math

from ..errors import DesignError
from .planar import Recorder, fire


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
    for name in dict.fromkeys(scene["surfaceOf"].values()):
        names += [f"contact.{name}.forceN", f"contact.{name}.depthMm"]
    return names


def read(mujoco, model, data, scene, blank, wrench):
    """The signals now, and the contact depth per surface. Spin is counted the planar way: counter-clockwise in (u, v)."""
    iu, iv = ("xyz".index(axis) for axis in scene["axes"])
    across = "xyz".index(scene["normal"])
    position, velocity = data.qpos[:3], data.qvel[:3]
    signals = dict(blank)
    turn = data.qvel[3 + across] * (-1.0 if scene["normal"] == "y" else 1.0)
    # how far the piece's own axis (the plane normal, at the start) has leaned away from where it began
    rotation = data.xmat[model.body("piece").id].reshape(3, 3)
    lean = max(-1.0, min(1.0, float(rotation[across, across])))
    signals.update({"tS": data.time, f"{scene['axes'][0]}Mm": position[iu] * 1e3, f"{scene['axes'][1]}Mm": position[iv] * 1e3,
                    "spinRadps": float(turn), "speedMps": float(math.hypot(velocity[iu], velocity[iv])),
                    "offPlaneMm": float(position[across] - scene["levelM"]) * 1e3, "tiltDeg": math.degrees(math.acos(lean))})
    touching = {}
    for index in range(data.ncon):
        contact = data.contact[index]
        names = (model.geom(contact.geom1).name, model.geom(contact.geom2).name)
        surface = next((scene["surfaceOf"][n] for n in names if n in scene["surfaceOf"]), None)
        if surface is None or "piece" not in names or contact.dist >= 0:
            continue
        mujoco.mj_contactForce(model, data, index, wrench)
        touching[surface] = max(touching.get(surface, 0.0), -contact.dist)
        signals[f"contact.{surface}.forceN"] += float(wrench[0])
        signals[f"contact.{surface}.depthMm"] = touching[surface] * 1e3
    return signals, touching


def run(scene, step=None, forces=()):
    """Run one MuJoCo scene. Returns the same summary a planar run gives, with two more signals: offPlaneMm and tiltDeg."""
    mujoco = engine()
    model = mujoco.MjModel.from_xml_string(scene["xml"])
    dt = step or scene["stepS"]
    model.opt.timestep = dt
    data = mujoco.MjData(model)
    data.qvel[:6] = scene["startVelocity"]
    mujoco.mj_forward(model, data)
    names = signal_names(scene)
    blank = dict.fromkeys(names, 0.0)
    recorder = Recorder(scene, [n for n in names if not n.startswith("contact.") and n != "speedMps"])
    happened, events, rest_since, steps, outcome = {}, [], None, 0, "timeout"
    import numpy
    wrench = numpy.zeros(6)
    signals, touching = read(mujoco, model, data, scene, blank, wrench)
    recorder.sample(0.0, signals, 0, dt, force=True)
    while data.time < scene["durationS"]:
        mujoco.mj_step(model, data)
        steps += 1
        signals, touching = read(mujoco, model, data, scene, blank, wrench)
        resting = signals["speedMps"] < scene["rest"]["speedMps"] and abs(signals["spinRadps"]) * scene["radiusM"] < scene["rest"]["rimSpeedMps"]
        rest_since = (data.time if rest_since is None else rest_since) if resting else None
        recorder.contacts(data.time, touching)
        recorder.measure(signals)
        recorder.sample(data.time, signals, steps, dt)
        stop = fire(scene, signals, happened, events, rest_since, data.time)
        if stop is not None:
            outcome = stop
            break
    recorder.sample(data.time, signals, steps, dt, force=True)
    iu, iv = ("xyz".index(axis) for axis in scene["axes"])
    return {"outcome": outcome, "endS": float(data.time), "steps": steps, "stepS": dt, "events": events, "measures": recorder.finish(signals, happened),
            "end": {"piece": [float(data.qpos[iu]), float(data.qpos[iv]), float(data.qvel[iu]), float(data.qvel[iv]), signals["spinRadps"]],
                    "drives": {}, "hingesDeg": {}, "offPlaneMm": signals["offPlaneMm"], "tiltDeg": signals["tiltDeg"]},
            "trace": {"columns": recorder.columns, "rows": recorder.trace},
            "contacts": {name: [[r[0], r[1], round(r[2], 4)] for r in rows] for name, rows in recorder.rows.items()}}
