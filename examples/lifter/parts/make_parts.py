"""Make the two invented STEP files this example imports. They stand in for a supplier's file and a field file.

Run from the repository root:  python examples/lifter/parts/make_parts.py
The files are committed, so this only needs running again if the stand-ins change.
"""
from pathlib import Path

from frc_design_kernel.kernel import shapes
from frc_design_kernel.kernel.step_write import write_solids

HERE = Path(__file__).resolve().parent

write_solids(HERE / "gearmotor.step", {
    "Motor body": shapes.cylinder([0, 0, 0], [0, 70, 0], 22),
    "Output shaft": shapes.cylinder([0, 70, 0], [0, 95, 0], 4),
    "Cable tail": shapes.box([-5, -30, -3], [5, 0, 3]),
}, "Invented gearmotor")

write_solids(HERE / "bench.step", {
    "Bench top": shapes.box([-400, -300, -40], [400, 300, 0]),
    "Bench rail": shapes.box([-400, -300, -120], [400, -260, -40]),
}, "Invented bench")
