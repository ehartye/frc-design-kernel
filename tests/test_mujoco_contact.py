"""The contact law in three dimensions is the planar engine's own: squeeze, rest and hold agree with it and with the closed form."""
import importlib.util
import math
import unittest
from unittest import mock

import frc_design_kernel as kernel
from frc_design_kernel.trials import engines, inputs, mujoco_contact, mujoco_run

from .helpers import load_data
from .test_mujoco import RISE, one_run
from .trial_cases import ENGINES, ASSUMES, G, MEASURED, bench, hold_trial

HAVE = importlib.util.find_spec("mujoco") is not None
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
BASE = {"assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "traceS": 0.01, "events": [], "pass": {"outcomes": ["timeout"]}}


def squeezed(engine, squash=2.0):
    """A block between the bed and a lid set 2 mm too low for it: each surface must give 1 mm."""
    solids = bench({})["solids"] + [{"name": "lid", "group": "bench", "shape": BOX([-100, -50, -460 - squash], [100, 50, -440])}]
    trial = {**BASE, "engine": engine, "durationS": 0.3, "piece": {"use": "block", "start": {"atMm": [0, -480 - squash / 2]}},
             "surfaces": [{"solid": "belt bed", "material": "panel"}, {"solid": "lid", "material": "panel"}],
             "measures": {"bed": {"final": "contact.belt bed.forceN"}, "lid": {"final": "contact.lid.forceN"}, "most": {"peak": "contact.lid.forceN"}}}
    return one_run(trial, solids=solids)[0]["measures"]


def resting(engine):
    trial = {**BASE, "engine": engine, "durationS": 0.3, "piece": {"use": "block", "start": {"atMm": [0, -480]}},
             "surfaces": [{"solid": "belt bed", "material": "panel"}],
             "measures": {"depth": {"final": "contact.belt bed.depthMm"}, "force": {"final": "contact.belt bed.forceN"}}}
    return one_run(trial)[0]["measures"]


def at_the_corner(pressed_mm=0.5):
    """The points MuJoCo finds where a ring lies flat with its near side pressed straight down onto the wedge's sharp top corner.

    Under the ring's middle the true direction is straight up, from the corner to the core of the ring's round section.
    """
    import mujoco
    ring = {"shape": {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 150, "minorRadiusMm": 20}, "massKg": MEASURED(0.25)}
    trial = {**BASE, "engine": "mujoco", "durationS": 0.01, "piece": {"use": "ring", "start": {"atMm": [150, RISE + 20 - pressed_mm]}},
             "surfaces": [{"name": "slope", "solid": "wedge", "material": "panel"}]}
    loaded = load_data(bench({"case": trial}, pieces={"ring": ring}))
    scene = engines.build(kernel.build(loaded), "case", inputs.case(loaded.data, loaded.data["trials"]["case"]))
    model, data, pieces, _ = mujoco_run.start(mujoco, scene, 1e-4)
    mujoco.mj_fwdPosition(model, data)
    found = mujoco_contact.touching_points(mujoco, model, data, scene, pieces, {})
    return [point for points in found.values() for point in points if abs(point["at"][1]) < 0.005]


def held(engine, **extra):
    trial = hold_trial(**extra)
    trial["engine"] = engine
    return one_run(trial)[0]


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class OneLaw(unittest.TestCase):
    def test_a_squeeze_presses_as_hard_as_the_springs_say(self):
        """Catches squeeze force, the signal for grip and structure, coming from anything but the springs: 1 mm into 200 N/mm is 200 N.

        MuJoCo's own contact gave 4200 N here. The lid carries the spring force less half the weight, the bed the rest.
        """
        for engine in ENGINES:
            found = squeezed(engine)
            self.assertAlmostEqual(found["lid"], 200.0 - 0.5 * G, delta=2.0, msg=engine)
            self.assertAlmostEqual(found["bed"], 200.0 + 0.5 * G, delta=2.0, msg=engine)
            self.assertLess(found["most"], 215.0, engine)       # and it never spiked on the way there
            harder = squeezed(engine, squash=4.0)
            self.assertAlmostEqual(harder["lid"], 400.0 - 0.5 * G, delta=4.0, msg=engine)      # control: twice the squash, twice the force

    def test_a_resting_piece_sinks_by_its_weight_over_the_stiffness(self):
        """Catches a resting depth that is not the spring's: 1 kg on 200 N/mm sinks 0.049 mm, in both engines."""
        for engine in ENGINES:
            found = resting(engine)
            self.assertAlmostEqual(found["depth"], 1.0 * G / 2.0e5 * 1000, delta=0.001, msg=engine)
            self.assertAlmostEqual(found["force"], 1.0 * G, delta=0.01, msg=engine)

    def test_a_block_holds_on_a_slope_or_slides_as_friction_says(self):
        """Catches a 3D friction law that creeps or grips wrongly: at friction 0.5 a block holds on 20 degrees, and slides on 30."""
        for engine in ENGINES:
            found = held(engine)
            self.assertEqual(found["outcome"], "held", engine)
            start = 300 * math.cos(math.radians(20)) + 20 * math.sin(math.radians(20))
            self.assertAlmostEqual(found["measures"]["endX"], start, delta=0.3, msg=engine)        # it has not crept
            self.assertEqual(held(engine, slope_deg=30)["outcome"], "slid", engine)                # control: steeper than the friction angle


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class RoundPieces(unittest.TestCase):
    def test_a_ring_on_a_sharp_corner_is_pushed_from_the_corner_toward_its_core(self):
        """Catches a round piece taking a face's direction at an edge or corner, so a lip pushes a ring along instead of lifting it.

        MuJoCo's general convex method gives a ring's segment the slope's direction there, 20 degrees off, and too shallow a depth.
        """
        points = at_the_corner()
        self.assertTrue(points)
        for point in points:
            self.assertAlmostEqual(point["normal"][0], 0.0, delta=0.01)
            self.assertAlmostEqual(point["normal"][2], 1.0, delta=0.001)
            self.assertAlmostEqual(point["depth"] * 1000, 0.5, delta=0.01)
        with mock.patch.object(mujoco_contact, "ROUND", ()):       # control: MuJoCo's own direction is far off here
            raw = at_the_corner()
        self.assertTrue(raw)
        self.assertTrue(all(math.degrees(math.acos(min(1.0, p["normal"][2]))) > 10 for p in raw))

    def test_a_ring_clear_of_the_corner_is_not_touching(self):
        """Catches a point being kept where the ring is in fact clear of the corner."""
        self.assertEqual(at_the_corner(pressed_mm=-0.5), [])

if __name__ == "__main__":
    unittest.main()
