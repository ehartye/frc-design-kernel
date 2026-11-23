"""The MuJoCo engine: rollers and belts turned by declared drives, and groups moved along design motions.

Each case is the same trial definition run in both engines, held to a closed form where there is one.
"""
import importlib.util
import math
import unittest

from .test_mujoco import one_run
from .trial_cases import ENGINES, ASSUMES, G, MEASURED, PANEL, bench

HAVE = importlib.util.find_spec("mujoco") is not None
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
MOTOR = {"small": {"ktNmPerA": MEASURED(0.02), "ohm": MEASURED(0.1), "keVsPerRad": MEASURED(0.02)}}
SLICK = {**PANEL, "friction": MEASURED(0.0)}


def rig(axis=(0, 1, 0), motor=False):
    """A block that cannot spin sits on a roller between two slick walls. The roller drags it against one wall."""
    solids = bench({})["solids"] + [
        {"name": "roller", "group": "bench", "shape": {"kind": "cylinder", "fromMm": [0, -50, -525], "toMm": [0, 50, -525], "radiusMm": 25}},
        {"name": "wall minus", "group": "bench", "shape": BOX([-31, -50, -560], [-21, 50, -440])},
        {"name": "wall plus", "group": "bench", "shape": BOX([21, -50, -560], [31, 50, -440])}]
    drive = {"radiusMm": 25, "turns": [{"solid": "roller", "axis": list(axis)}]}
    command = {"mode": "imposed", "speedMps": 1.0}
    if motor:
        drive.update(motor="small", gear=2.0, inertiaKgM2=MEASURED(2e-4), statorLimitA=40)
        command = {"mode": "speed", "setpointMps": 1.0, "band": 0.05, "busV": 12.0, "startMps": 1.0}
    return {"solids": solids, "drives": {"spin": drive}, "motors": MOTOR, "materials": {"panel": PANEL, "slick": SLICK}}, command


def dragged(engine, axis=(0, 1, 0), motor=False):
    design, command = rig(axis, motor)
    trial = {"engine": engine, "assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 0.6, "traceS": 0.01, "events": [],
             "pass": {"outcomes": ["timeout"]}, "piece": {"use": "block", "start": {"atMm": [0, -480]}}, "commands": {"spin": command},
             "surfaces": [{"solid": "roller", "material": "panel"}, {"solid": "wall minus", "material": "slick"}, {"solid": "wall plus", "material": "slick"}],
             "measures": {"minus": {"final": "contact.wall minus.forceN"}, "plus": {"final": "contact.wall plus.forceN"}, "amps": {"final": "drive.spin.currentA"}}}
    return one_run(trial, **design)


def pushed(engine, motion):
    """A ball on the bed, and a gate that a design motion drives into it."""
    design = bench({})
    design["groups"]["gate"] = {"role": "mechanism"}
    design["groups"]["finger"] = {"role": "mechanism", "carriedBy": "gate"}
    design["solids"].append({"name": "pusher", "group": "gate" if motion != "carried" else "finger", "shape": BOX([-60, -50, -500], [-40, 50, -440])})
    design["poses"] = {"back": {}, "half": {"gate": [{"kind": "translation", "travelMm": [100, 0, 0]}]}, "out": {"gate": [{"kind": "translation", "travelMm": [200, 0, 0]}]}}
    design["motions"] = {"slide": {"from": "back", "moves": {"gate": [{"kind": "translation", "travelMm": [200, 0, 0]}]}},
                         "by poses": {"through": ["back", "half", "out"]},
                         "swing": {"from": "back", "moves": {"gate": [{"kind": "rotation", "originMm": [-50, 0, -300], "axis": [0, -1, 0], "travelDeg": 40}]}}}
    trial = {"engine": engine, "assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 0.8, "traceS": 0.01, "events": [],
             "pass": {"outcomes": ["timeout"]}, "piece": {"use": "ball", "start": {"atMm": [0, -480]}},
             "movers": {"push": {"motion": motion if motion != "carried" else "slide", "group": "gate", "startS": 0.05, "durationS": 0.5}},
             "surfaces": [{"solid": "belt bed", "material": "panel"}, {"solid": "pusher", "material": "panel", "mover": "push"}],
             "measures": {"x": {"final": "xMm"}}}
    return one_run(trial, **{k: design[k] for k in ("groups", "solids", "poses", "motions")})


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class Rollers(unittest.TestCase):
    def test_a_roller_drags_a_block_against_the_wall_with_friction_times_its_weight_in_both_engines(self):
        """Catches a roller that turns the wrong way or drags with the wrong force against a slick wall.

        The block is dragged 1 mm to the wall, so it sits a = asin(1 / 45) off the top of the roller, and statics gives
        the push as m * g * (sin a + mu * cos a) / (cos a - mu * sin a).
        """
        lean = math.asin(1 / 45)
        expected = 1.0 * G * (math.sin(lean) + 0.5 * math.cos(lean)) / (math.cos(lean) - 0.5 * math.sin(lean))
        for engine in ENGINES:
            forward = dragged(engine)[0]["measures"]
            self.assertAlmostEqual(forward["plus"], expected, delta=0.03 * expected, msg=engine)
            self.assertAlmostEqual(forward["minus"], 0.0, delta=0.01, msg=engine)
            back = dragged(engine, axis=(0, -1, 0))[0]["measures"]
            self.assertAlmostEqual(back["minus"], expected, delta=0.03 * expected, msg=engine)

    def test_the_load_reaches_the_motor_the_same_in_both_engines(self):
        """Catches contact load not being fed back to the drive: holding speed against mu * m * g at the roller takes a known current."""
        lean = math.asin(1 / 45)
        drag = 0.5 * 1.0 * G / (math.cos(lean) - 0.5 * math.sin(lean))       # friction at the roller: mu times the normal force there
        expected = drag * 0.025 / (2.0 * 0.02)
        for engine in ENGINES:
            found, _ = dragged(engine, motor=True)
            self.assertAlmostEqual(found["measures"]["amps"], expected, delta=0.05 * expected, msg=engine)

    def test_a_belt_brings_a_block_up_to_its_speed_in_both_engines(self):
        """Catches a belt that does not drag: a block set down on it gains speed at friction * g, then rides at belt speed."""
        design, command = rig()
        design["drives"]["spin"]["turns"] = [{"solid": "belt bed", "axis": [0, 1, 0]}]
        for engine in ENGINES:
            speeds = {}
            for seconds in (0.1, 0.4):
                trial = {"engine": engine, "assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": seconds, "traceS": 0.01,
                         "pass": {"outcomes": ["timeout"]}, "piece": {"use": "block", "start": {"atMm": [0, -480]}}, "commands": {"spin": command},
                         "surfaces": [{"solid": "belt bed", "material": "panel"}], "planar": {"frictionLaw": "smooth"}, "events": [],
                         "measures": {"speed": {"final": "speedMps"}}}
                found, facts = one_run(trial, **design)
                speeds[seconds] = found["measures"]["speed"]
            self.assertAlmostEqual(speeds[0.1], 0.5 * G * 0.1, delta=0.02, msg=engine)
            self.assertAlmostEqual(speeds[0.4], 1.0, delta=0.02, msg=engine)
        self.assertEqual((facts["driven"], facts["bodies"]), ({"belt bed": "spin"}, {}))


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class MovedGroups(unittest.TestCase):
    def test_a_sliding_gate_pushes_a_ball_the_same_distance_in_both_engines(self):
        """Catches a moved group that does not move, moves at the wrong time, or whose speed is not felt by what it pushes."""
        flat, solid = pushed("planar", "slide")[0], pushed("mujoco", "slide")[0]
        self.assertGreater(flat["measures"]["x"], 180.0)
        self.assertAlmostEqual(solid["measures"]["x"], flat["measures"]["x"], delta=0.05 * flat["measures"]["x"])

    def test_one_hinge_one_slider_or_a_path(self):
        """Catches the wrong kind of body for a motion: one slide is a slider, one turn is a hinge, a motion through poses is carried along its path."""
        kinds = {motion: pushed("mujoco", motion) for motion in ("slide", "swing", "by poses", "carried")}
        self.assertEqual({motion: found[1]["bodies"] for motion, found in kinds.items()},
                         {"slide": {"gate:push": "slide"}, "swing": {"gate:push": "hinge"}, "by poses": {"gate:push": "path"},
                          "carried": {"finger:push": "slide"}})        # a group carried by the moving one moves with it
        for motion, (found, _) in kinds.items():
            self.assertGreater(found["measures"]["x"], 60.0, motion)       # each of them shoves the ball along


if __name__ == "__main__":
    unittest.main()
