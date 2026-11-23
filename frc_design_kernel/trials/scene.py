"""Turn a trial definition (design units, names of solids) into a runtime scene (plain SI numbers) the solver can run.

Surfaces named by solid are cut from that solid where the trial's plane crosses it, at the trial's pose, so a trial
uses the same geometry the layout measures. Everything a trial names is checked here, before any run.
"""
import math

from ..errors import DesignError
from ..kernel.section import AXES, outlines
from ..motion import stages as stage_math
from ..builder import placement
from . import contact, rules
from .planar import signal_names

MM = 1e-3
STANDARD_GRAVITY = 9.80665


def fail(where, problem, fix):
    raise DesignError(where, problem, fix)


def pick(table, name, where, what):
    if name not in table:
        fail(where, f'names the {what} "{name}", which does not exist', f"Known: {', '.join(table) or 'none'}")
    return table[name]


def material(entry, mass):
    """A runtime material: spring, damper, friction and its law."""
    k = entry["stiffnessNPerM"]
    kt = entry.get("tangentStiffnessNPerM", 2.0e4)
    return {"k": k, "c": contact.damping(k, mass, entry.get("restitution"), entry.get("dampingRatio")), "mu": entry["friction"],
            "law": entry.get("law", "stick"), "kt": kt, "ct": math.sqrt(kt * mass), "eps": entry.get("slipSpeedMps", 0.01)}


def solid_prims(assembly, placed, trial, name, where):
    if name not in placed:
        fail(where, f'names the solid "{name}", which does not exist', f"Known: {', '.join(sorted(placed))}")
    plane = trial["plane"]
    loops = outlines(placed[name], plane["normal"], plane["atMm"])
    if not loops:
        fail(where, f'the plane {plane["normal"]} = {plane["atMm"]:g} mm does not cut the solid "{name}"', "Move the plane, or give the surface as segmentsMm")
    prims = []
    for piece in (p for loop in loops for p in loop):
        if piece["kind"] == "segment":
            if math.dist(piece["a"], piece["b"]) > 1e-9:
                prims.append(contact.segment([v * MM for v in piece["a"]], [v * MM for v in piece["b"]]))
        else:
            prims.append(contact.arc([v * MM for v in piece["centre"]], piece["radius"] * MM, piece["from"], piece["sweep"]))
    return prims


def literal_prims(entry):
    if "circleMm" in entry:
        circle = entry["circleMm"]
        return [contact.arc([v * MM for v in circle["centreMm"]], circle["radiusMm"] * MM, 0.0, 2 * math.pi)]
    points = [[v * MM for v in p] for p in entry["segmentsMm"]]
    return [contact.segment(a, b) for a, b in zip(points, points[1:])]


def mover(entry, assembly, trial, where):
    """A runtime mover: a steady slide of some surfaces, from a stated velocity or from a straight design motion."""
    out = {key: entry[key] for key in ("startS", "after", "delayS", "durationS") if key in entry}
    if "motion" in entry:
        listed = placement.motion_stages(assembly.data, entry["motion"])
        travel = stage_math.straight_travel(pick(listed, entry["group"], where, "group"))
        if travel is None:
            fail(where, f'the motion "{entry["motion"]}" does not move the group "{entry["group"]}" in one straight slide', "Only straight slides can carry trial surfaces")
        iu, iv = AXES[trial["plane"]["normal"]]
        out["velocityMps"] = (travel[iu] * MM / entry["durationS"], travel[iv] * MM / entry["durationS"])
    else:
        out["velocityMps"] = tuple(entry["velocityMps"])
    return out


def drive(entry):
    out = {k: v for k, v in entry.items() if k != "radiusMm"}
    if "radiusMm" in entry:
        out["radiusM"] = entry["radiusMm"] * MM
    return out


def check_names(trial, scene, where):
    """Every signal and event a trial's conditions, measures and limits name must exist."""
    signals = set(signal_names(scene))
    events = {event["name"] for event in scene["events"]}
    used = [(event["when"], f'event "{event["name"]}"') for event in scene["events"]]
    used += [(rule["when"], f'drive "{name}" rule') for name, d in scene["drives"].items() for rule in d.get("rules", ())]
    for condition, what in used:
        for kind, known, found in zip(("signal", "event"), (signals, events), rules.names_in(condition)):
            for name in sorted(found - known):
                fail(f"{where} {what}", f'names the {kind} "{name}", which does not exist', f"Known {kind}s: {', '.join(sorted(known))}")
    for item in [*scene["loads"], *scene["movers"].values()]:
        if "after" in item and item["after"] not in events:
            fail(where, f'something starts after the event "{item["after"]}", which does not exist', f"Known events: {', '.join(sorted(events))}")
    for name, spec in scene["measures"].items():
        key = next(k for k in ("peak", "lowest", "final", "timeOf") if k in spec)
        if spec[key] not in (events if key == "timeOf" else signals):
            fail(f'{where} measure "{name}"', f'names "{spec[key]}", which does not exist', f"Known: {', '.join(sorted(events if key == 'timeOf' else signals))}")
    for limit in trial["pass"].get("limits", []):
        pick(scene["measures"], limit["measure"], f"{where} pass", "measure")


def start_state(piece, handed):
    start = piece["start"]
    if "after" in start:
        x, z, vx, vz, w = handed
        return [x, z, 0.0, 0.0, 0.0] if start.get("atRest", True) else [x, z, vx, vz, w]
    velocity = start.get("velocityMps", [0.0, 0.0])
    return [start["atMm"][0] * MM, start["atMm"][1] * MM, velocity[0], velocity[1], start.get("spinRadps", 0.0)]


def build(assembly, name, trial, handed=None):
    """The runtime scene for a trial. handed is the end state of the trial this one starts after, when it names one."""
    where = f'trials "{name}"'
    plane = trial["plane"]
    piece = trial["piece"]
    mass, radius = piece["massKg"], piece["radiusMm"] * MM
    placed = assembly.at_pose(trial.get("pose"))
    materials = {key: material(entry, mass) for key, entry in trial["materials"].items()}
    scene_movers = {key: mover(entry, assembly, trial, f'{where} mover "{key}"') for key, entry in trial.get("movers", {}).items()}
    scene_drives = {key: drive(entry) for key, entry in trial.get("drives", {}).items()}
    surfaces, hinges = [], {}
    for entry in trial["surfaces"]:
        at = f'{where} surface "{entry["name"]}"'
        prims = solid_prims(assembly, placed, trial, entry["solid"], at) if "solid" in entry else literal_prims(entry)
        row = {"name": entry["name"], "prims": prims, "mat": pick(materials, entry["material"], at, "material"),
               "speedMps": entry.get("speedMps", 0.0), "ratio": entry.get("ratio", 1.0), "sign": -1.0 if entry.get("runs") == "clockwise" else 1.0}
        if "drive" in entry:
            pick(scene_drives, entry["drive"], at, "drive")
            row["drive"] = entry["drive"]
        if "mover" in entry:
            pick(scene_movers, entry["mover"], at, "mover")
            row["mover"] = entry["mover"]
        surfaces.append(row)
    for entry in trial.get("flaps", []):
        at = f'{where} flap "{entry["name"]}"'
        size = math.hypot(*entry["restDirection"])
        hinges[entry["name"]] = {"at": [v * MM for v in entry["hingeMm"]], "lengthM": entry["lengthMm"] * MM,
                                 "rest": [v / size for v in entry["restDirection"]], "inertiaKgM2": entry["inertiaKgM2"],
                                 "preloadNm": entry.get("preloadNm", 0.0), "springNmPerRad": entry["springNmPerRad"],
                                 "dampingNmSPerRad": entry.get("dampingNmSPerRad", 0.0), "limitRad": math.radians(entry["limitDeg"]),
                                 "stopRestitution": entry.get("stopRestitution", 0.0)}
        row = {"name": entry["name"], "prims": [], "hinge": entry["name"], "mat": pick(materials, entry["material"], at, "material"),
               "speedMps": 0.0, "ratio": 1.0, "sign": 1.0}
        if "mover" in entry:
            row["mover"] = entry["mover"]
        surfaces.append(row)
    gravity = trial.get("gravityMps2", STANDARD_GRAVITY)
    scene = {
        "axes": ["xyz"[i] for i in AXES[plane["normal"]]], "stepS": trial["stepS"], "durationS": trial["durationS"],
        "traceS": trial.get("traceS", 0.002), "contactPoint": trial.get("contactPoint", "onSurface"),
        "gravityMps2": (0.0, 0.0) if plane["normal"] == "z" else (0.0, -gravity),
        "piece": {"radiusM": radius, "massKg": mass, "start": start_state(piece, handed),
                  "inertiaKgM2": piece.get("inertiaKgM2", piece.get("inertiaFactor", 0.5) * mass * radius ** 2)},
        "rest": {"speedMps": 0.005, "rimSpeedMps": 0.005, **trial.get("rest", {})},
        "surfaces": surfaces, "hinges": hinges, "drives": scene_drives, "movers": scene_movers,
        "loads": trial.get("loads", []), "events": trial.get("events", []), "measures": trial.get("measures", {}),
    }
    check_names(trial, scene, where)
    return scene
