"""The planar solver: one round piece in a plane, against surfaces, drives, hinged flaps and loads, at a fixed step.

It takes a runtime scene (plain data in SI units, made by trials.scene) and returns one run: the outcome, events,
measures, a trace and contact rows. Each step works out every force from the state at the start of the step, then
advances speeds before positions (semi-implicit Euler). There is no adaptive stepping; the campaign repeats the run
at half the step to show whether the step was small enough.
"""
import math

from . import drives as drive_math
from .contact import push, nearest, segment
from .rules import holds, started

CONTACT_WINDOW_S = 0.05     # a lasting contact is recorded in rows no longer than this


def load_force(load, mass, happened, t):
    """The force on the piece from one load: the frame it rides in accelerates, so the piece feels the opposite."""
    begin = started(load, happened, t)
    if begin is None or t > begin + load["durationS"]:
        return 0.0, 0.0
    size = load["accelerationMps2"]
    if load.get("shape") == "halfSine":
        size *= math.sin(math.pi * (t - begin) / load["durationS"])
    return -mass * size * load["along"][0], -mass * size * load["along"][1]


def mover_velocity(mover, happened, t):
    begin = started(mover, happened, t)
    return mover["velocityMps"] if begin is not None and t < begin + mover["durationS"] else (0.0, 0.0)


def flap_prim(hinge, angle):
    """The flap as a segment from its hinge to its tip, and the direction its points move when the angle grows."""
    c, s = math.cos(angle), math.sin(angle)
    dx, dz = hinge["rest"]
    ax, az = dx * c - dz * s, dx * s + dz * c
    tip = (hinge["at"][0] + hinge["lengthM"] * ax, hinge["at"][1] + hinge["lengthM"] * az)
    return segment(hinge["at"], tip), (-az, ax)


def flap_step(hinge, state, torque, dt):
    """Advance a flap: a one-way torsion spring with preload and damping, between a stop at 0 and a stop at its limit."""
    state["rate"] += (torque - (hinge["preloadNm"] + hinge["springNmPerRad"] * state["angle"]) - hinge["dampingNmSPerRad"] * state["rate"]) / hinge["inertiaKgM2"] * dt
    state["angle"] += state["rate"] * dt
    if state["angle"] < 0.0:
        state["angle"], state["rate"] = 0.0, max(state["rate"], 0.0)
    if state["angle"] > hinge["limitRad"]:
        state["angle"], state["rate"] = hinge["limitRad"], -hinge["stopRestitution"] * max(state["rate"], 0.0)


class Recorder:
    """Keeps what a run reports: contact rows per surface, measures, and the trace."""

    def __init__(self, scene, columns):
        self.rows, self.open, self.trace, self.next = {}, {}, [], 0.0
        self.every, self.columns = scene.get("traceS", 0.002), columns
        self.measures = scene.get("measures", {})
        self.values = {name: None for name in self.measures}

    def contacts(self, t, touching):
        for label, depth in touching.items():
            row = self.open.get(label)
            if row is None or t - row[0] >= CONTACT_WINDOW_S:
                row = self.open[label] = [round(t, 5), round(t, 5), 0.0]
                self.rows.setdefault(label, []).append(row)
            row[1], row[2] = round(t, 5), max(row[2], depth * 1000)
        for label in [k for k in self.open if k not in touching]:
            del self.open[label]

    def measure(self, signals):
        for name, spec in self.measures.items():
            kind = "peak" if "peak" in spec else "lowest" if "lowest" in spec else None
            if kind:
                value, best = signals[spec[kind]], self.values[name]
                if best is None or (value > best if kind == "peak" else value < best):
                    self.values[name] = value

    def sample(self, t, signals, force=False):
        if self.every and (force or t >= self.next):
            self.trace.append([round(t, 5)] + [round(signals[c], 4) for c in self.columns[1:]])
            self.next += self.every

    def finish(self, signals, happened):
        for name, spec in self.measures.items():
            if "final" in spec:
                self.values[name] = signals[spec["final"]]
            elif "timeOf" in spec:
                self.values[name] = happened.get(spec["timeOf"])
        return self.values


def signal_names(scene):
    """Every signal a run offers, in trace column order."""
    a, b = scene["axes"]
    names = ["tS", f"{a}Mm", f"{b}Mm", "spinRadps", "speedMps"]
    for name in scene["drives"]:
        names += [f"drive.{name}.speedMps", f"drive.{name}.currentA", f"drive.{name}.supplyA"]
    names += [f"hinge.{name}.angleDeg" for name in scene["hinges"]]
    names += [f"mover.{name}.offsetMm" for name in scene["movers"]]
    for name in dict.fromkeys(s["name"] for s in scene["surfaces"]):
        names += [f"contact.{name}.forceN", f"contact.{name}.depthMm"]
    return names


def touch(scene, piece_state, radius, drive_state, hinge_state, offset, velocity, memory, dt, arm_on_piece):
    """Every contact force on the piece this step.

    Returns (fx, fz, torque, load on each drive, depth per surface, normal force per surface, torque on each flap).
    """
    x, z, vx, vz, w = piece_state
    fx = fz = torque = 0.0
    loads, touching, pressed, twist = dict.fromkeys(scene["drives"], 0.0), {}, {}, dict.fromkeys(scene["hinges"], 0.0)
    for index, surface in enumerate(scene["surfaces"]):
        mover = surface.get("mover")
        ox, oz = offset[mover] if mover else (0.0, 0.0)
        mvx, mvz = velocity[mover] if mover else (0.0, 0.0)
        state = (x - ox, z - oz, vx - mvx, vz - mvz, w)
        hinge, drive = surface.get("hinge"), surface.get("drive")
        if hinge:
            prim, swing = flap_prim(scene["hinges"][hinge], hinge_state[hinge]["angle"])
            prims = (prim,)
        else:
            prims = surface["prims"]
        speed = surface["sign"] * (drive_state[drive]["u"] * surface["ratio"] if drive else surface["speedMps"])
        for n, prim in enumerate(prims):
            qx, qz, tx, tz = nearest(prim, state[0], state[1])
            if hinge:
                reach = math.dist((qx, qz), scene["hinges"][hinge]["at"])
                moving = (hinge_state[hinge]["rate"] * reach * swing[0], hinge_state[hinge]["rate"] * reach * swing[1])
            else:
                moving = (speed * tx, speed * tz)
            found = push((index, n), memory, state, radius, (qx, qz), surface["mat"], moving, dt, arm_on_piece)
            if found is None:
                continue
            fx += found[0]
            fz += found[1]
            torque += found[2]
            name = surface["name"]
            touching[name] = max(touching.get(name, 0.0), found[5])
            pressed[name] = pressed.get(name, 0.0) + found[3]
            if drive:
                loads[drive] += surface["ratio"] * surface["sign"] * (found[0] * tx + found[1] * tz)
            if hinge:
                twist[hinge] += reach * (-found[0] * swing[0] - found[1] * swing[1])
    return fx, fz, torque, loads, touching, pressed, twist


def read_signals(blank, axes, t, piece_state, drive_state, hinge_state, offset, touching, pressed):
    """The signals at the end of a step, by name."""
    x, z, vx, vz, w = piece_state
    signals = dict(blank)
    signals.update({"tS": t, f"{axes[0]}Mm": x * 1e3, f"{axes[1]}Mm": z * 1e3, "spinRadps": w, "speedMps": math.hypot(vx, vz)})
    for name, state in drive_state.items():
        signals[f"drive.{name}.speedMps"], signals[f"drive.{name}.currentA"], signals[f"drive.{name}.supplyA"] = state["u"], state["amps"], state["supply"]
    for name, state in hinge_state.items():
        signals[f"hinge.{name}.angleDeg"] = math.degrees(state["angle"])
    for name, moved in offset.items():
        signals[f"mover.{name}.offsetMm"] = math.hypot(*moved) * 1e3
    for name, depth in touching.items():
        signals[f"contact.{name}.forceN"], signals[f"contact.{name}.depthMm"] = pressed[name], depth * 1e3
    return signals


def fire(scene, signals, happened, events, rest_since, t):
    """Record the events whose conditions now hold. Returns the outcome of the first one that stops the run, or None."""
    for event in scene["events"]:
        if event["name"] not in happened and holds(event["when"], signals, happened, rest_since, t):
            happened[event["name"]] = t
            events.append({"t": round(t, 6), "event": event["name"]})
            if "outcome" in event:
                return event["outcome"]
    return None


def applied(scene, mass, happened, t, signals, forces):
    """Gravity, loads and custom force laws on the piece: (fx, fz, torque)."""
    fx, fz, torque = mass * scene["gravityMps2"][0], mass * scene["gravityMps2"][1], 0.0
    for load in scene["loads"]:
        lx, lz = load_force(load, mass, happened, t)
        fx += lx
        fz += lz
    for law, parameters in forces:
        extra = law(signals, parameters)
        fx += extra[0]
        fz += extra[1]
        torque += extra[2]
    return fx, fz, torque


def run(scene, step=None, forces=()):
    """Run one trial scene. forces are extra force laws: [(function(signals, parameters) -> (fx, fz, torque), parameters)]."""
    dt = step or scene["stepS"]
    piece = scene["piece"]
    radius, mass, inertia = piece["radiusM"], piece["massKg"], piece["inertiaKgM2"]
    x, z, vx, vz, w = piece["start"]
    drive_state = {name: drive_math.start(d) for name, d in scene["drives"].items()}
    hinge_state = {name: {"angle": 0.0, "rate": 0.0} for name in scene["hinges"]}
    offset = {name: [0.0, 0.0] for name in scene["movers"]}
    names = signal_names(scene)
    recorder = Recorder(scene, names[:4] + [n for n in names[5:] if not n.startswith("contact.")])
    blank = dict.fromkeys(names, 0.0)
    memory, happened, events, rest_since = {}, {}, [], None
    arm_on_piece = scene.get("contactPoint") == "onPiece"
    t, steps, outcome = 0.0, 0, "timeout"
    signals = read_signals(blank, scene["axes"], 0.0, (x, z, vx, vz, w), drive_state, hinge_state, offset, {}, {})
    recorder.sample(0.0, signals, force=True)
    while t < scene["durationS"]:
        velocity = {name: mover_velocity(m, happened, t) for name, m in scene["movers"].items()}
        cx, cz, turn, loads, touching, pressed, twist = touch(scene, (x, z, vx, vz, w), radius, drive_state, hinge_state, offset, velocity,
                                                              memory, dt, arm_on_piece)
        fx, fz, torque = applied(scene, mass, happened, t, signals, forces)
        for name, drive in scene["drives"].items():
            for rule in drive.get("rules", ()):
                if holds(rule["when"], signals, happened, rest_since, t):
                    drive = {**drive, **rule["set"]}
            drive_math.step(drive, drive_state[name], loads[name], t, dt)
        for name, hinge in scene["hinges"].items():
            flap_step(hinge, hinge_state[name], twist[name], dt)
        vx += (fx + cx) / mass * dt
        vz += (fz + cz) / mass * dt
        w += (torque + turn) / inertia * dt
        x += vx * dt
        z += vz * dt
        for name, (mvx, mvz) in velocity.items():
            offset[name][0] += mvx * dt
            offset[name][1] += mvz * dt
        t += dt
        steps += 1
        signals = read_signals(blank, scene["axes"], t, (x, z, vx, vz, w), drive_state, hinge_state, offset, touching, pressed)
        resting = signals["speedMps"] < scene["rest"]["speedMps"] and abs(w) * radius < scene["rest"]["rimSpeedMps"]
        rest_since = (t if rest_since is None else rest_since) if resting else None
        recorder.contacts(t, touching)
        recorder.measure(signals)
        recorder.sample(t, signals)
        stop = fire(scene, signals, happened, events, rest_since, t)
        if stop is not None:
            outcome = stop
            break
    recorder.sample(t, signals, force=True)
    return {"outcome": outcome, "endS": t, "steps": steps, "stepS": dt, "events": events, "measures": recorder.finish(signals, happened),
            "end": {"piece": [x, z, vx, vz, w], "drives": {n: s["u"] for n, s in drive_state.items()},
                    "hingesDeg": {n: math.degrees(s["angle"]) for n, s in hinge_state.items()}},
            "trace": {"columns": recorder.columns, "rows": recorder.trace},
            "contacts": {name: [[r[0], r[1], round(r[2], 4)] for r in rows] for name, rows in recorder.rows.items()}}
