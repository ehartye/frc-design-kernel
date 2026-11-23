"""Turn a trial's case (design units, names of solids) into a runtime scene (plain SI numbers) the planar solver can run.

The piece is declared once in the design source with its real 3D shape; the section the plane takes of it is worked
out here. Surfaces named by solid are cut from that solid where the plane crosses it, at the trial's pose. Drives are
declared on solids with an axis; which way their surface runs in the plane follows from that axis. Everything the
scene took is listed under scene["facts"], so the record can say what the planar engine saw.
"""
import math

from ..builder import placement
from ..errors import DesignError
from ..kernel.section import AXES, outlines
from ..motion import stages as stage_math
from . import contact, rules
from .inputs import plain
from .planar import signal_names

MM = 1e-3
STANDARD_GRAVITY = 9.80665


def fail(where, problem, fix):
    raise DesignError(where, problem, fix)


def pick(table, name, where, what):
    if name not in table:
        fail(where, f'names the {what} "{name}", which does not exist', f"Known: {', '.join(table) or 'none'}")
    return table[name]


def piece_section(name, piece, normal, where):
    """(radius in mm, inertia factor) of the round section the plane takes of a piece declared in 3D."""
    shape = piece["shape"]
    across = "xyz".index(normal)
    lying = shape["kind"] in ("cylinder", "tube") and all(abs(a - b) < 1e-9 for i, (a, b) in enumerate(zip(shape["fromMm"], shape["toMm"])) if i != across)
    if shape["kind"] == "sphere":
        return shape["radiusMm"], 0.4
    if shape["kind"] == "cylinder" and lying and "sweepDeg" not in shape:
        return shape["radiusMm"], 0.5
    if shape["kind"] == "tube" and shape.get("section") == "round" and lying:
        outer = shape["outerDiameterMm"] / 2
        return outer, (outer ** 2 + (outer - shape["wallMm"]) ** 2) / (2 * outer ** 2)
    fail(where, f'the planar engine cannot take a round section of the piece "{name}" across {normal}',
         "It needs a ball, or a round bar or tube whose axis is square to the trial's plane")


def material(entry, mass, options):
    """A runtime material: spring, damper, friction and the planar friction law."""
    k = entry["stiffnessNPerM"]
    kt = options.get("tangentStiffnessNPerM", 2.0e4)
    return {"k": k, "c": contact.damping(k, mass, entry.get("restitution"), entry.get("dampingRatio")), "mu": entry["friction"],
            "law": options.get("frictionLaw", "stick"), "kt": kt, "ct": math.sqrt(kt * mass), "eps": options.get("slipSpeedMps", 0.01)}


def solid_prims(placed, plane, name, where):
    loops = outlines(pick(placed, name, where, "solid"), plane["normal"], plane["atMm"])
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


def turning(drives, solid, normal, where):
    """(drive, ratio, sign) for a solid a declared drive turns, or None. The sign says which way it runs in the plane."""
    for name, drive in drives.items():
        for turn in drive.get("turns", []):
            if turn["solid"] != solid:
                continue
            along = turn["axis"]["xyz".index(normal)] / math.hypot(*turn["axis"])
            if abs(along) < 0.5:
                fail(where, f'the drive "{name}" turns "{solid}" about an axis that lies in the trial\'s plane', "A planar trial needs the axis square to its plane")
            # Looking at (u, v): counter-clockwise is a turn about +x or +z, but about -y, because (x, z) is drawn with y going away.
            return name, turn.get("ratio", 1.0), (-1.0 if normal == "y" else 1.0) * (1.0 if along > 0 else -1.0)
    return None


def runtime_drive(name, drive, motors, command, where):
    """A runtime drive from its declaration on the design and the trial's command for it."""
    if command["mode"] == "imposed":
        return {"kind": "imposed", "speedMps": command.get("speedMps", 0.0), "rampS": command.get("rampS", 0.0)}
    if "motor" not in drive:
        fail(where, f'the drive "{name}" has no motor, so it can only be commanded with "mode": "imposed"', "Give the drive a motor, or impose its speed")
    out = {"kind": "motor", "motor": motors[drive["motor"]], "radiusM": drive["radiusMm"] * MM, "gear": drive.get("gear", 1.0),
           "count": drive.get("count", 1), "efficiency": drive.get("efficiency", 1.0), "statorLimitA": drive["statorLimitA"],
           "dragNm": drive.get("dragNm", 0.0), "busV": command.get("busV", 12.0), "startMps": command.get("startMps", 0.0),
           "oneWay": command.get("oneWay", False), "piecesOnDrive": command.get("piecesOnDrive", 1),
           "control": {key: command[key] for key in ("mode", "setpointMps", "band", "fullTorqueAtRad") if key in command}}
    for key in ("movingKg", "inertiaKgM2", "supplyLimitA"):
        if key in drive:
            out[key] = drive[key]
    return out


def drives_for(case, where):
    """{name: runtime drive} for every drive of the case, each with its controller rules made into runtime changes."""
    found = {}
    for name, drive in case["drives"].items():
        command = case.get("commands", {}).get(name)
        if command is None:
            fail(where, f'the drive "{name}" takes part in this trial but has no command', f'Add commands.{name}, for example {{"mode": "imposed", "speedMps": 0}}')
        runtime = runtime_drive(name, drive, case["motors"], command, where)
        runtime["rules"] = [{"when": rule["when"], "set": runtime_drive(name, drive, case["motors"], {**command, **rule["set"]}, where)}
                            for rule in command.get("rules", [])]
        found[name] = runtime
    return found


def mover(entry, assembly, plane, where):
    """A runtime mover: a steady slide of some surfaces, from a stated velocity or from a straight design motion."""
    out = {key: entry[key] for key in ("startS", "after", "delayS", "durationS") if key in entry}
    if "motion" in entry:
        listed = placement.motion_stages(assembly.data, entry["motion"])
        travel = stage_math.straight_travel(pick(listed, entry["group"], where, "group"))
        if travel is None:
            fail(where, f'the motion "{entry["motion"]}" does not move the group "{entry["group"]}" in one straight slide', "Only straight slides can carry trial surfaces")
        iu, iv = AXES[plane["normal"]]
        out["velocityMps"] = (travel[iu] * MM / entry["durationS"], travel[iv] * MM / entry["durationS"])
    else:
        out["velocityMps"] = tuple(entry["velocityMps"])
    return out


def check_names(case, scene, where, names=None):
    """Every signal and event a trial's conditions, measures and limits name must exist. names are the engine's signals."""
    signals = set(names or signal_names(scene))
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
    for limit in case["pass"].get("limits", []):
        pick(scene["measures"], limit["measure"], f"{where} pass", "measure")


def surfaces_for(case, assembly, materials, drives, movers, where, facts):
    """The runtime surfaces and flaps of a case."""
    plane = case["plane"]
    placed = assembly.at_pose(case.get("pose"))
    surfaces, hinges = [], {}
    for entry in case["surfaces"]:
        name = entry.get("name", entry.get("solid", "surface"))
        at = f'{where} surface "{name}"'
        row = {"name": name, "mat": pick(materials, entry["material"], at, "material"), "speedMps": entry.get("speedMps", 0.0),
               "ratio": entry.get("ratio", 1.0), "sign": -1.0 if entry.get("runs") == "clockwise" else 1.0}
        if "solid" in entry:
            row["prims"] = solid_prims(placed, plane, entry["solid"], at)
            turned = turning(case["drives"], entry["solid"], plane["normal"], at)
            if turned:
                row["drive"], row["ratio"], row["sign"] = turned
            facts["sections"].append({"solid": entry["solid"], "segments": sum(p[0] == "s" for p in row["prims"]),
                                      "arcs": sum(p[0] == "a" for p in row["prims"]), "drive": row.get("drive")})
        else:
            row["prims"] = literal_prims(entry)
            facts["typedSurfaces"].append(name)
            if "drive" in entry:
                row["drive"] = pick(drives, entry["drive"], at, "drive") and entry["drive"]
        if "mover" in entry:
            pick(movers, entry["mover"], at, "mover")
            row["mover"] = entry["mover"]
        surfaces.append(row)
    for entry in case.get("flaps", []):
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
    return surfaces, hinges


def start_state(start, handed):
    if "after" in start:
        x, z, vx, vz, w = handed["piece"]
        return [x, z, 0.0, 0.0, 0.0] if start.get("atRest", True) else [x, z, vx, vz, w]
    velocity = start.get("velocityMps", [0.0, 0.0])
    return [start["atMm"][0] * MM, start["atMm"][1] * MM, velocity[0], velocity[1], start.get("spinRadps", 0.0)]


def build(assembly, name, a_case, handed=None):
    """The runtime scene for a trial's case. handed is the end state of the trial this one starts after, when it names one."""
    where = f'trials "{name}"'
    case = plain(a_case)
    plane, options = case["plane"], case.get("planar", {})
    if case.get("others"):
        fail(where, "the planar engine runs one piece", 'Run a trial with more than one piece with "engine": "mujoco"')
    use = case["piece"]["use"]
    piece = case["pieces"][use]
    radius_mm, factor = piece_section(use, piece, plane["normal"], where)
    mass, radius = piece["massKg"], radius_mm * MM
    facts = {"plane": plane, "pose": case.get("pose"), "sections": [], "typedSurfaces": [],
             "piece": {"piece": use, "shape": piece["shape"]["kind"], "sectionRadiusMm": radius_mm, "inertiaFactor": factor}}
    materials = {key: material(entry, mass, options) for key, entry in case["materials"].items()}
    movers = {key: mover(entry, assembly, plane, f'{where} mover "{key}"') for key, entry in case.get("movers", {}).items()}
    drives = drives_for(case, where)
    if case["piece"]["start"].get("carryDrives"):      # each drive starts at the speed the earlier trial left it at
        for key, speed in (handed or {}).get("drives", {}).items():
            if key in drives:
                drives[key]["startMps"] = speed
    surfaces, hinges = surfaces_for(case, assembly, materials, drives, movers, where, facts)
    gravity = case.get("gravityMps2", STANDARD_GRAVITY)
    scene = {
        "axes": ["xyz"[i] for i in AXES[plane["normal"]]], "stepS": case["stepS"], "durationS": case["durationS"],
        "traceS": case.get("traceS", 0.002), "contactPoint": options.get("contactPoint", "onSurface"),
        "gravityMps2": (0.0, 0.0) if plane["normal"] == "z" else (0.0, -gravity),
        "piece": {"radiusM": radius, "massKg": mass, "start": start_state(case["piece"]["start"], handed),
                  "inertiaKgM2": piece.get("inertiaKgM2", factor * mass * radius ** 2)},
        "rest": {"speedMps": 0.005, "rimSpeedMps": 0.005, **case.get("rest", {})},
        "surfaces": surfaces, "hinges": hinges, "drives": drives, "movers": movers,
        "loads": case.get("loads", []), "events": case.get("events", []), "measures": case.get("measures", {}), "facts": facts,
    }
    check_names(case, scene, where)
    return scene
