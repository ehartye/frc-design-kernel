"""The contact law in three dimensions is the planar engine's own: squeeze, rest and hold agree with it and with the closed form."""
import importlib.util
import math
import unittest

from .test_mujoco import one_run
from .trial_cases import ENGINES, ASSUMES, G, bench, hold_trial

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


if __name__ == "__main__":
    unittest.main()
