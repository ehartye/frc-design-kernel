"""An invented design at the scale of a large preliminary layout: about 230 solids and 74 motions.

Nothing here copies a real robot. A frame of square tubes and brackets carries twelve mechanisms, each a carriage
plate with a stack of blocks on it; each mechanism slides and swings through six motions. A payload ball can be
pressed onto a pad, and a few test-stand blocks stand on the floor beside the frame. Every solid is a plain box or
ball, drawn 2 mm from its neighbours, so a measurement costs little and the size of the records is what is tested.

    python -m tests.scaled_design OUT     writes OUT/design.json

`jobs()` gives the kind of job list a judging tool asks for: every motion's clearance, required-contact reaches,
squeezes, service withdrawals, one displaced control, and attachment and mass at every pose.
"""
import json
import sys
from pathlib import Path

CELLS_X, CELLS_Y = 4, 3             # twelve mechanisms in a grid over the frame
CELL_X, CELL_Y = 190.0, 210.0
BLOCKS = 12                         # blocks stacked on each carriage plate


def box(low, high):
    return {"kind": "box", "fromMm": list(low), "toMm": list(high)}


def frame():
    """Side rails, cross members, posts, top rails and brackets: one rigid group of 64 solids."""
    solids = [{"name": "rail left", "shape": box([0, 0, 0], [800, 40, 40])},
              {"name": "rail right", "shape": box([0, 660, 0], [800, 700, 40])}]
    solids += [{"name": f"cross {i}", "shape": box([20 + i * 96, 42, 0], [50 + i * 96, 658, 30])} for i in range(8)]
    posts = [(x, y) for x in (0, 385, 770) for y in (0, 660)] + [(x, y) for x in (192, 578) for y in (0, 660)] + [(0, 330), (770, 330)]
    solids += [{"name": f"post {i}", "shape": box([x, y, 42], [x + 30, y + 40, 442])} for i, (x, y) in enumerate(posts)]
    solids += [{"name": "top rail left", "shape": box([0, 0, 444], [800, 40, 474])},
               {"name": "top rail right", "shape": box([0, 660, 444], [800, 700, 474])}]
    solids += [{"name": f"bracket {side} {i}", "shape": box([60 + i * 36, y0, 2], [90 + i * 36, y0 + 6, 38])}
               for side, y0 in (("left", -8), ("right", 702)) for i in range(20)]
    for solid in solids:
        solid.update(group="frame", massKg=0.25)
    return solids


def mechanism(i):
    """A carriage plate and a stack of blocks in grid cell i, one group carried by the frame."""
    x0, y0 = 60 + (i % CELLS_X) * CELL_X, 50 + (i // CELLS_X) * CELL_Y
    group = f"mech {i}"
    solids = [{"name": f"{group} plate", "group": group, "massKg": 0.3, "shape": box([x0, y0, 60], [x0 + 120, y0 + 120, 66])}]
    for k in range(BLOCKS):
        bx, by = x0 + 4 + (k % 4) * 29, y0 + 4 + (k // 4) * 38
        solids.append({"name": f"{group} block {k}", "group": group, "massKg": 0.05, "shape": box([bx, by, 68], [bx + 25, by + 34, 98])})
    return solids


def motions_for(i):
    """Six motions of mechanism i: four slides and two swings, short enough to stay inside its cell."""
    group = f"mech {i}"
    x0, y0 = 60 + (i % CELLS_X) * CELL_X, 50 + (i // CELLS_X) * CELL_Y
    pivot = [x0, y0 + 60, 60]
    slides = [[0, 0, 40], [0, 0, 120], [20, 0, 0], [0, 25, 30]]
    found = {f"{group} slide {k}": {"from": "stowed", "moves": {group: [{"kind": "translation", "travelMm": travel}]}} for k, travel in enumerate(slides)}
    for k, angle in enumerate((-40, -75)):
        found[f"{group} swing {k}"] = {"from": "stowed", "moves": {group: [{"kind": "rotation", "originMm": pivot, "axis": [0, 1, 0], "travelDeg": angle}]}}
    return found


def design():
    """The scaled design as a design-source dictionary."""
    groups = {"frame": {"role": "structure"}, "payload": {"role": "payload"}}
    solids = frame()
    motions, poses = {}, {"stowed": {}}
    for i in range(CELLS_X * CELLS_Y):
        groups[f"mech {i}"] = {"role": "mechanism", "carriedBy": "frame"}
        solids += mechanism(i)
        motions.update(motions_for(i))
    for i in range(0, CELLS_X * CELLS_Y, 2):
        poses[f"mech {i} raised"] = {f"mech {i}": [{"kind": "translation", "travelMm": [0, 0, 120]}]}
    solids += [{"name": "pad", "group": "frame", "massKg": 0.1, "shape": box([860, 300, 0], [960, 400, 20])},
               {"name": "ball", "group": "payload", "massKg": 0.2, "shape": {"kind": "sphere", "centerMm": [910, 350, 90], "radiusMm": 60}}]
    motions["payload press"] = {"from": "stowed", "moves": {"payload": [{"kind": "translation", "travelMm": [0, 0, -12]}]}}
    motions["payload lift"] = {"from": "stowed", "moves": {"payload": [{"kind": "translation", "travelMm": [0, 0, 80]}]}}
    fixtures = [{"name": f"stand {i}", "group": "stand", "shape": box([1100 + i * 80, 0, 0], [1160 + i * 80, 60, 300])} for i in range(6)]
    groups["stand"] = {"role": "test stand"}
    return {"schema": "frc-design-kernel/design@1", "name": "Scaled bench", "units": {"length": "mm", "mass": "kg"},
            "frame": "Origin on the floor at a frame corner. +X forward, +Y left, +Z up.",
            "groups": groups, "solids": solids, "fixtures": fixtures, "poses": poses, "motions": motions,
            "mounts": [{"group": f"mech {i}", "member": f"mech {i} plate", "on": "cross 0", "atMm": [60 + (i % CELLS_X) * CELL_X, 50, 60]}
                       for i in range(CELLS_X * CELLS_Y)]}


def jobs(data):
    """The jobs a judging tool asks of the design: one clearance per motion, plus the other kinds where they apply."""
    found = [{"kind": "clearance", "motion": name, "minGapMm": 1.0, "includeStill": True} for name in data["motions"]]
    for i in range(CELLS_X * CELLS_Y):
        found.append({"kind": "reach", "motion": f"mech {i} slide 0", "pair": [f"mech {i} plate", f"mech {i} block 0"], "withinMm": 3.0})
    found += [{"kind": "indentation", "motion": "payload press", "piece": "ball", "contact": "pad", "maxDepthMm": 4.0},
              {"kind": "withdrawal", "motion": "payload lift"},
              {"kind": "withdrawal", "motion": "mech 0 slide 1"},
              {"kind": "clearance", "motion": "mech 0 slide 2", "minGapMm": 1.0, "includeStill": True, "contacts": [],
               "absent": sorted(s["name"] for s in data["solids"] + data["fixtures"] if s["name"] not in ("mech 0 plate", "cross 1")),
               "displace": {"cross 1": [0, 0, 40]}}]
    for pose in [None, *data["poses"]]:
        found += [{"kind": "attachment", "pose": pose, "touchGapMm": 3.0, "ignore": ["ball"]}, {"kind": "mass", "pose": pose}]
    return found


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "design.json").write_text(json.dumps(design(), indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {out / 'design.json'}.")
