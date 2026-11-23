"""Air on a free piece, in both engines: drag against the closed form, terminal speed, and the Magnus curve of a spinning ball."""
import importlib.util
import math
import unittest

from frc_design_kernel import DesignError
from frc_design_kernel.trials import assumptions, inputs

from .test_mujoco import one_run
from .trial_cases import ASSUMES, G, MEASURED, bench

HAVE = importlib.util.find_spec("mujoco") is not None
ENGINES = ("planar", "mujoco") if HAVE else ("planar",)
BALL = {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 20}
FAR = {"name": "far wall", "group": "bench", "shape": {"kind": "box", "fromMm": [400000, -500000, -500000], "toMm": [401000, 500000, 500000]}}


def flown(engine, plane, start, seconds, drag=0.5, slope=0.0, air=True, most=None):
    """A 0.5 kg ball of 0.05 m2 frontal area let go at start (point, velocity, spin) in still air of 1.2 kg/m3."""
    piece = {"shape": BALL, "massKg": MEASURED(0.5), "dragCoefficient": MEASURED(drag), "frontalAreaM2": MEASURED(0.05), "liftSlope": MEASURED(slope)}
    if most is not None:
        piece["liftMax"] = MEASURED(most)
    trial = {"engine": engine, "assumes": ASSUMES, "plane": {"normal": plane, "atMm": 0}, "stepS": 1e-3, "durationS": seconds, "traceS": 0.05,
             "events": [], "pass": {"outcomes": ["timeout"]}, "piece": {"use": "flyer", "start": start},
             "surfaces": [{"solid": "far wall", "material": "panel"}],
             "measures": {"a": {"final": "xMm"}, "b": {"final": "yMm" if plane == "z" else "zMm"}, "speed": {"final": "speedMps"}}}
    if air:
        trial["air"] = {"densityKgM3": {"value": 1.2, "assumed": [1.1, 1.25]}}
    return one_run(trial, solids=bench({})["solids"] + [FAR], pieces={"flyer": piece})[0]["measures"]


class Air(unittest.TestCase):
    def test_drag_slows_a_piece_as_the_closed_form_says(self):
        """Catches drag of the wrong size or law: with no gravity, v = v0 / (1 + k v0 t / m) and x = (m / k) ln(1 + k v0 t / m)."""
        k, m, v0, t = 0.5 * 1.2 * 0.5 * 0.05, 0.5, 10.0, 1.0
        for engine in ENGINES:
            found = flown(engine, "z", {"atMm": [0, 0], "velocityMps": [v0, 0]}, t)
            self.assertAlmostEqual(found["speed"], v0 / (1 + k * v0 * t / m), delta=0.005 * v0, msg=engine)
            self.assertAlmostEqual(found["a"] / 1000, m / k * math.log(1 + k * v0 * t / m), delta=0.01, msg=engine)
            still = flown(engine, "z", {"atMm": [0, 0], "velocityMps": [v0, 0]}, t, air=False)       # control: no air, no slowing
            self.assertAlmostEqual(still["speed"], v0, delta=1e-6, msg=engine)

    def test_a_falling_piece_reaches_its_terminal_speed(self):
        """Catches drag that does not balance the weight: terminal speed is sqrt(2 m g / (rho Cd A)), 18.08 m/s here."""
        terminal = math.sqrt(2 * 0.5 * G / (1.2 * 0.5 * 0.05))
        for engine in ENGINES:
            found = flown(engine, "y", {"atMm": [0, 0]}, 8.0)
            self.assertAlmostEqual(found["speed"], terminal * math.tanh(G * 8.0 / terminal), delta=0.005 * terminal, msg=engine)

    def test_spin_curves_a_piece_round_a_circle_of_the_magnus_radius(self):
        """Catches lift of the wrong size or the wrong way: with no drag or gravity, the lift is square to the motion and the
        piece runs round a circle of radius m v^2 / F, F = 1/2 rho A slope r spin v. Counter-clockwise spin curves it left.

        Control: the opposite spin curves it the other way by the same amount.
        """
        v, spin, r = 10.0, 300.0, 0.02
        radius = 0.5 * v * v / (0.5 * 1.2 * 0.05 * 1.0 * r * spin * v)
        quarter = math.pi / 2 * radius / v
        for engine in ENGINES:
            left = flown(engine, "z", {"atMm": [0, 0], "velocityMps": [v, 0], "spinRadps": spin}, quarter, drag=0.0, slope=1.0)
            self.assertAlmostEqual(left["a"] / 1000, radius, delta=0.01 * radius, msg=engine)
            self.assertAlmostEqual(left["b"] / 1000, radius, delta=0.01 * radius, msg=engine)
            self.assertAlmostEqual(left["speed"], v, delta=0.001 * v, msg=engine)
            right = flown(engine, "z", {"atMm": [0, 0], "velocityMps": [v, 0], "spinRadps": -spin}, quarter, drag=0.0, slope=1.0)
            self.assertAlmostEqual(right["b"], -left["b"], delta=0.01 * abs(left["b"]), msg=engine)
        capped = flown("planar", "z", {"atMm": [0, 0], "velocityMps": [v, 0], "spinRadps": spin}, quarter * 2, drag=0.0, slope=1.0, most=0.3)
        self.assertAlmostEqual(capped["a"] / 1000, 2 * radius, delta=0.01 * radius)       # the cap halves the lift (Cl 0.6 to 0.3): twice the radius

    def test_air_numbers_are_sourced_inputs_and_the_record_says_air_is_on(self):
        """Catches the air coefficients escaping ranges and coverage, a piece flown in air with no drag numbers, or the
        record still claiming there is no air."""
        case = {"air": {"densityKgM3": {"value": 1.2, "assumed": [1.1, 1.25]}},
                "pieces": {"flyer": {"massKg": MEASURED(0.5), "dragCoefficient": {"value": 0.5, "assumed": [0.4, 0.6]}, "frontalAreaM2": MEASURED(0.05)}}}
        paths = {row["path"]: row["source"] for row in inputs.physical_inputs(case)}
        self.assertEqual(paths["air.densityKgM3"], "assumed")
        self.assertEqual(paths["pieces.flyer.dragCoefficient"], "assumed")
        standing = [row["id"] for row in assumptions.stated({"air": case["air"]})[1]]
        self.assertIn("air-law", standing)
        self.assertNotIn("no-air", standing)
        self.assertIn("no-air", [row["id"] for row in assumptions.stated({})[1]])
        with self.assertRaisesRegex(DesignError, "has no dragCoefficient"):
            from frc_design_kernel.trials import air
            air.params({"air": {"densityKgM3": 1.2}, "pieces": {"flyer": {"massKg": 0.5}}}, "flyer", 0.02, "test")


if __name__ == "__main__":
    unittest.main()
