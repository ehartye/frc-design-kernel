"""An invented seating pickup, the standing case that every 3D engine must still seat.

A carriage, its deck tilted 40 degrees, drives 300 mm onto a ring lying on the floor. A curved blade with a faceted
round nose gets under the ring's near side, a belt carries it up the deck, it pushes past a sprung flap, two side
belts pinch it 5 mm each side and drive it under a lid, and it comes to rest against a stop.

It carries the features that exposed the two 3D defects found so far, both of which passed single-contact
calibration: a squeeze between two driven surfaces (the engine's own soft contact gave 4 to 21 times the spring
force), and a ring meeting a faceted edge (the engine's general convex method gave a face's direction there).
Nothing here is a real robot: the sizes, angles and numbers are made up.
"""
import math

PITCH, L = 40.0, 520.0                      # the deck's tilt, and where the belt's nose is along it
COS, SIN = math.cos(math.radians(PITCH)), math.sin(math.radians(PITCH))
MAJOR, MINOR, SQUEEZE = 120.0, 20.0, 5.0    # the ring, and how far each side belt reaches into it
MEASURED = lambda v: {"value": v, "measured": "invented bench sheet 2"}
BOX = lambda lo, hi: {"kind": "box", "fromMm": lo, "toMm": hi}
ROLL = lambda x, z, r: {"kind": "cylinder", "fromMm": [x, -20, z], "toMm": [x, 20, z], "radiusMm": r}
SEAT = (40 + MAJOR + MINOR, 25 + MINOR)     # the ring's centre against the stop, on the deck, in the carriage's own coordinates


def lip_outline(thick=3.0, step=7.0):
    """A curved blade past the belt's nose, 3 mm thick, flattening toward a round nose drawn as five facets.

    Drawn in level-floor terms from the top of the nose, then turned into the carriage's tilted coordinates.
    """
    top, at = [(0.0, 0.0)], (0.0, 0.0)
    for slope in (0, 10, 20, 30, 40):
        at = (at[0] - step * math.cos(math.radians(slope)), at[1] + step * math.sin(math.radians(slope)))
        top.append(at)
    bottom = [(x - thick * math.sin(math.radians(a)), z - thick * math.cos(math.radians(a))) for (x, z), a in zip(top, (0, 5, 15, 25, 35, 45))]
    nose = [(thick / 2 * math.cos(math.radians(d)), thick / 2 * (math.sin(math.radians(d)) - 1)) for d in (60, 30, 0, -30, -60)]
    return [[L + 40 + dx * COS - dz * SIN, 22 + dx * SIN + dz * COS] for dx, dz in [*reversed(top), *nose, *bottom]]


def side_belt(side, r=15.0):
    """What a side belt reaches: every point within 15 mm of its flat face, which runs along the deck at the ring's side."""
    y = side * (MAJOR + MINOR + r - SQUEEZE)
    ball = lambda x, z: {"kind": "sphere", "centerMm": [x, y, z], "radiusMm": r}
    along = lambda z: {"kind": "cylinder", "fromMm": [100, y, z], "toMm": [L - 60, y, z], "radiusMm": r}
    post = lambda x: {"kind": "cylinder", "fromMm": [x, y, 32], "toMm": [x, y, 58], "radiusMm": r}
    return {"kind": "union", "of": [BOX([100, y - r, 32], [L - 60, y + r, 58]), along(32), along(58), post(100), post(L - 60),
                                    ball(100, 32), ball(100, 58), ball(L - 60, 32), ball(L - 60, 58)]}


def trial_for(world):
    window = [{"signal": "carriage.xMm", "above": SEAT[0] - 15}, {"signal": "carriage.xMm", "below": SEAT[0] + 15},
              {"signal": "carriage.zMm", "above": SEAT[1] - 12}, {"signal": "carriage.zMm", "below": SEAT[1] + 12}]
    nose = min((world(x, z) for x, z in lip_outline()), key=lambda p: p[1])
    return {
        "engine": "mujoco", "assumes": [{"id": "invented", "text": "An invented pickup with the features of a real one."}],
        "plane": {"normal": "y", "atMm": 0}, "stepS": 0.0005, "durationS": 2.5, "traceS": 0.01, "mujoco": {"ringSegments": 48},
        "piece": {"use": "ring", "start": {"atMm": [nose[0] + MAJOR + MINOR + 1.0, MINOR - 0.05]}},
        "surfaces": [{"solid": "floor", "material": "frame"}] + [{"solid": name, "material": material, "mover": "drive"} for name, _, material in CARRIAGE],
        "flaps": [{"name": "flap", "solid": "flap", "material": "leaf", "mover": "drive", "hingeMm": world(L - 150, 95), "lengthMm": 45,
                   "restDirection": [-SIN, -COS], "limitDeg": -90, "inertiaKgM2": MEASURED(1.5e-5), "springNmPerRad": MEASURED(0.015),
                   "dampingNmSPerRad": MEASURED(0.004), "preloadNm": MEASURED(0.003)}],
        "commands": {"belt": {"mode": "imposed", "speedMps": 0.8},
                     **{f"side {k}": {"mode": "speed", "setpointMps": 0.8, "busV": 12.0, "startMps": 0.8} for k in ("left", "right")}},
        "movers": {"drive": {"motion": "drive on", "group": "chassis", "startS": 0.0, "durationS": 1.2}},
        "frames": {"carriage": {"group": "carriage", "mover": "drive"}},
        "events": [{"name": "in seat", "when": {"all": window}},
                   {"name": "seated", "when": {"all": [{"after": "in seat", "delayS": 0.04}, *window]}, "outcome": "seated"}],
        "measures": {"seatedS": {"timeOf": "seated"}, "squeezeN": {"final": "contact.side belt left.forceN"},
                     "otherSqueezeN": {"final": "contact.side belt right.forceN"}, "flapDeg": {"peak": "hinge.flap.angleDeg"}},
        "pass": {"outcomes": ["seated"]},
        "control": {"change": {"commands.belt.speedMps": 0.0}, "note": "With the belt stopped the ring is not drawn in."},
    }


CARRIAGE = [
    ("belt", {"kind": "union", "of": [BOX([90, -20, 1], [L, 20, 25]), ROLL(90, 13, 12), ROLL(L, 13, 12)]}, "frame"),
    ("lip", {"kind": "prism", "plane": "xz", "fromMm": -180, "toMm": 180, "outlineMm": lip_outline()}, "lip"),
    ("rail left", BOX([60, 60, 21], [L - 20, 100, 25]), "frame"), ("rail right", BOX([60, -100, 21], [L - 20, -60, 25]), "frame"),
    ("stop", BOX([30, -60, 25], [40, 60, 75]), "frame"),
    ("lid left", BOX([40, 40, 68], [L - 170, 170, 70]), "frame"), ("lid right", BOX([40, -170, 68], [L - 170, -40, 70]), "frame"),
    ("side belt left", side_belt(1), "tread"), ("side belt right", side_belt(-1), "tread"),
]


def design():
    """The design source, with its one trial "seat"."""
    x0, z0 = 120.0, 4.5 + max(x * SIN - z * COS for x, z in lip_outline())       # the blade's lowest edge 4.5 mm above the floor
    world = lambda x, z: [x0 + x * COS + z * SIN, z0 - x * SIN + z * COS]
    solids = [{"name": "floor", "group": "ground", "shape": BOX([-500, -800, -20], [2000, 800, 0])}]
    solids += [{"name": name, "group": "carriage", "shape": shape} for name, shape, _ in CARRIAGE]
    solids.append({"name": "flap", "group": "carriage", "shape": BOX([L - 151.5, -40, 50], [L - 148.5, 40, 95])})
    solids += [{"name": f"side motor {k}", "group": "chassis", "shape": BOX([-400, y, 200], [-360, y + 40, 240])} for k, y in (("left", 600), ("right", -640))]
    side = lambda k, axis: {"motor": "small", "motorSolid": f"side motor {k}", "gear": 10, "radiusMm": 20, "statorLimitA": 3.2, "movingKg": MEASURED(0.2),
                            "efficiency": MEASURED(1.0), "turns": [{"solid": f"side belt {k}", "axis": axis}]}
    return {
        "schema": "frc-design-kernel/design@1", "name": "Seating pickup", "units": {"length": "mm", "mass": "kg"}, "parameters": {},
        "groups": {"ground": {"role": "structure"}, "chassis": {"role": "structure"},
                   "carriage": {"role": "mechanism", "carriedBy": "chassis",
                                "place": [{"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 1, 0], "travelDeg": PITCH},
                                          {"kind": "translation", "travelMm": [x0, 0, z0]}]}},
        "solids": solids, "poses": {"start": {}},
        "motions": {"drive on": {"by": "hand", "from": "start", "moves": {"chassis": [{"kind": "translation", "travelMm": [300, 0, 0]}]}}},
        "pieces": {"ring": {"shape": {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": MAJOR, "minorRadiusMm": MINOR},
                            "massKg": MEASURED(0.2)}},
        "materials": {"frame": {"stiffnessNPerM": MEASURED(4000.0), "dampingRatio": MEASURED(0.95), "friction": MEASURED(0.75)},
                      "lip": {"stiffnessNPerM": MEASURED(4000.0), "dampingRatio": MEASURED(0.95), "friction": MEASURED(0.15)},
                      "tread": {"stiffnessNPerM": MEASURED(4500.0), "dampingRatio": MEASURED(0.1), "friction": MEASURED(0.8)},
                      "leaf": {"stiffnessNPerM": MEASURED(25000.0), "dampingRatio": MEASURED(0.95), "friction": MEASURED(0.75)}},
        "motors": {"small": {"ktNmPerA": MEASURED(0.01), "ohm": MEASURED(0.1), "keVsPerRad": MEASURED(0.01)}},
        "drives": {"belt": {"radiusMm": 12, "turns": [{"solid": "belt", "axis": [0, -1, 0]}]},
                   "side left": side("left", [-SIN, 0, -COS]), "side right": side("right", [SIN, 0, COS])},
        "trials": {"seat": trial_for(world)},
    }
