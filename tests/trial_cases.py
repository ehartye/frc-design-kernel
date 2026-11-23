"""Invented trial fixtures shared by the trial tests: a wedge, a belt bed, a few pieces and trials with known answers."""
import copy
import math

G = 9.80665
# Every engine the library has. A calibration test loops over this, so an engine added here must pass the whole set.
ENGINES = ("planar", "mujoco")
# Every engine that runs a piece in 3D. The standing seating case (test_mujoco_seating.py) loops over it.
ENGINES_3D = ("mujoco",)
MEASURED = lambda value: {"value": value, "measured": "invented bench sheet 1"}
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
PANEL = {"stiffnessNPerM": MEASURED(2.0e5), "restitution": MEASURED(0.2), "friction": {"value": 0.5, "assumed": [0.2, 0.8]}}
BALL = {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 20}

# A wedge whose top face slopes down toward +X at slope_deg, and a long flat belt bed whose top is at z = -500.
DESIGN = {
    "schema": "frc-design-kernel/design@1", "name": "Trial bench", "units": {"length": "mm", "mass": "kg"},
    "parameters": {"slope_deg": 20, "rise": "=2000 * tan(radians(slope_deg))"},
    "groups": {"bench": {"role": "structure"}},
    "solids": [
        {"name": "wedge", "group": "bench", "shape": {"kind": "prism", "plane": "xz", "fromMm": -50, "toMm": 50,
                                                       "outlineMm": [[0, 0], [2000, 0], [0, "=rise"]]}},
        {"name": "belt bed", "group": "bench", "shape": BOX([-3000, -50, -520], [3000, 50, -500])},
    ],
    "pieces": {
        "block": {"shape": BALL, "massKg": MEASURED(1.0), "inertiaKgM2": MEASURED(1e6), "note": "A piece that cannot spin."},
        "ball": {"shape": BALL, "massKg": MEASURED(0.5)},
        "bar": {"shape": {"kind": "cylinder", "fromMm": [0, -100, 0], "toMm": [0, 100, 0], "radiusMm": 20}, "massKg": MEASURED(0.5)},
        "shot": {"shape": {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 5}, "massKg": MEASURED(0.1)},
    },
    "materials": {"panel": PANEL},
    "trials": {},
}
ASSUMES = [{"id": "dry-surfaces", "text": "The surfaces are dry and clean."}]


def on_slope(along_mm, radius_mm, slope_deg, rise_mm):
    """The centre of a piece resting on the wedge's slope, along_mm down from its top corner."""
    a = math.radians(slope_deg)
    return [along_mm * math.cos(a) + radius_mm * math.sin(a), rise_mm - along_mm * math.sin(a) + radius_mm * math.cos(a)]


def hold_trial(law="stick", slope_deg=20, duration=1.0, **extra):
    """A block (a piece that cannot spin) set on the wedge. It holds, or it slides 100 mm and the run stops."""
    rise = 2000 * math.tan(math.radians(slope_deg))
    sunk = 20 - 1.0 * G * math.cos(math.radians(slope_deg)) / 2.0e5 * 1000      # start pressed in as deep as it will rest
    trial = {
        "assumes": copy.deepcopy(ASSUMES),
        "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": duration, "traceS": 0.01, "planar": {"frictionLaw": law},
        "piece": {"use": "block", "start": {"atMm": on_slope(300, sunk, slope_deg, rise)}},
        "surfaces": [{"name": "slope", "solid": "wedge", "material": "panel"}],
        "events": [{"name": "slid", "when": {"signal": "xMm", "above": on_slope(400, 20, slope_deg, rise)[0]}, "outcome": "slid"},
                   {"name": "held", "when": {"all": [{"signal": "tS", "above": 0.5}, {"restFor": 0.3}]}, "outcome": "held"}],
        "measures": {"slideS": {"timeOf": "slid"}, "endX": {"final": "xMm"}, "push": {"peak": "contact.slope.forceN"}},
        "pass": {"outcomes": ["held"]},
        "control": {"change": {"materials.panel.friction": 0.1}, "note": "With a slippery panel the block must slide."},
    }
    trial.update(extra)
    return trial


def tilting_trial(**extra):
    """The block on the wedge again, with every number that depends on the slope written from the slope parameter."""
    c, s = "cos(radians(slope_deg))", "sin(radians(slope_deg))"
    trial = hold_trial(**extra)
    trial["piece"]["start"] = {"atMm": [f"=300 * {c} + 19.95 * {s}", f"=rise - 300 * {s} + 19.95 * {c}"]}
    trial["events"][0]["when"]["above"] = f"=400 * {c} + 20 * {s}"
    return trial


def bench(trials, **extra):
    data = copy.deepcopy(DESIGN)
    data["trials"] = trials
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return data
