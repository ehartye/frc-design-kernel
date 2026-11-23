"""Invented trial fixtures shared by the trial tests: a wedge, a belt bed and a few trials with known answers."""
import copy
import math

G = 9.80665
PANEL = {"stiffnessNPerM": 2.0e5, "restitution": 0.2, "friction": 0.5, "law": "stick"}
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}

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
    "trials": {},
}


def on_slope(along_mm, radius_mm, slope_deg, rise_mm):
    """The centre of a piece resting on the wedge's slope, along_mm down from its top corner."""
    a = math.radians(slope_deg)
    return [along_mm * math.cos(a) + radius_mm * math.sin(a), rise_mm - along_mm * math.sin(a) + radius_mm * math.cos(a)]


def hold_trial(law="stick", friction=0.5, slope_deg=20, duration=1.0, **extra):
    """A block (a piece that cannot spin) set on the wedge. It holds, or it slides 100 mm and the run stops."""
    rise = 2000 * math.tan(math.radians(slope_deg))
    sunk = 20 - 1.0 * G * math.cos(math.radians(slope_deg)) / PANEL["stiffnessNPerM"] * 1000     # start pressed in as deep as it will rest
    trial = {
        "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": duration, "traceS": 0.01,
        "piece": {"radiusMm": 20, "massKg": 1.0, "inertiaKgM2": 1e6, "start": {"atMm": on_slope(300, sunk, slope_deg, rise)}},
        "materials": {"panel": {**PANEL, "law": law, "friction": friction}},
        "surfaces": [{"name": "slope", "solid": "wedge", "material": "panel"}],
        "events": [{"name": "slid", "when": {"signal": "xMm", "above": on_slope(400, 20, slope_deg, rise)[0]}, "outcome": "slid"},
                   {"name": "held", "when": {"all": [{"signal": "tS", "above": 0.5}, {"restFor": 0.3}]}, "outcome": "held"}],
        "measures": {"slideS": {"timeOf": "slid"}, "endX": {"final": "xMm"}, "push": {"peak": "contact.slope.forceN"}},
        "pass": {"outcomes": ["held"]},
        "control": {"change": {"materials.panel.friction": 0.1}, "note": "With a slippery panel the block must slide."},
        "brackets": [{"input": "materials.panel.friction", "unit": "", "values": [0.2, 0.5, 0.8]},
                     {"input": "parameters.slope_deg", "unit": "deg", "values": [20, 35]}],
    }
    trial.update(extra)
    return trial


def bench(trials, **extra):
    data = copy.deepcopy(DESIGN)
    data["trials"] = trials
    data.update(extra)
    return data
