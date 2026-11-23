"""The MuJoCo engine: a ring piece, loads, flaps, and a driven surface on a moved group.

Where there is a closed form the engine is held to it; otherwise the same trial is run in both engines.
"""
import importlib.util
import unittest

from .test_mujoco import one_run
from .trial_cases import ASSUMES, G, MEASURED, PANEL, bench

HAVE = importlib.util.find_spec("mujoco") is not None
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
SLICK = {**PANEL, "friction": MEASURED(0.0)}
BASE = {"assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "traceS": 0.01, "events": [], "pass": {"outcomes": ["timeout"]}}


def ring_over_post(post_radius, segments=None):
    """A ring dropped flat over a post standing on a floor."""
    solids = bench({})["solids"] + [
        {"name": "floor", "group": "bench", "shape": BOX([-400, -400, -520], [400, 400, -500])},
        {"name": "post", "group": "bench", "shape": {"kind": "cylinder", "fromMm": [0, 0, -500], "toMm": [0, 0, -380], "radiusMm": post_radius}}]
    pieces = {"ring": {"shape": {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 150, "minorRadiusMm": 25}, "massKg": MEASURED(0.25)}}
    trial = {**BASE, "engine": "mujoco", "durationS": 1.5, "piece": {"use": "ring", "start": {"atMm": [0, -300]}},
             "surfaces": [{"solid": "floor", "material": "panel"}, {"solid": "post", "material": "panel"}],
             "events": [{"name": "still", "when": {"all": [{"signal": "tS", "above": 0.3}, {"restFor": 0.2}]}, "outcome": "still"}],
             "pass": {"outcomes": ["still"]}, "measures": {"z": {"final": "zMm"}, "tilt": {"peak": "tiltDeg"}}}
    if segments:
        trial["mujoco"] = {"ringSegments": segments}
    return one_run(trial, solids=solids, pieces=pieces)


def gate(engine, spring):
    """A block that cannot spin slides on a slick bed into a sprung flap standing on the bed, and is thrown back."""
    solids = bench({})["solids"] + [{"name": "leaf", "group": "bench", "shape": BOX([99, -50, -500], [101, 50, -440])}]
    trial = {**BASE, "engine": engine, "durationS": 0.6, "piece": {"use": "block", "start": {"atMm": [200, -480], "velocityMps": [-1, 0]}},
             "surfaces": [{"solid": "belt bed", "material": "slick"}],
             "flaps": [{"name": "flap", "solid": "leaf", "material": "slick", "hingeMm": [100, -500], "lengthMm": 60, "restDirection": [0, 1],
                        "inertiaKgM2": MEASURED(1e-4), "springNmPerRad": MEASURED(spring), "dampingNmSPerRad": MEASURED(0.002), "limitDeg": 80}],
             "measures": {"most": {"peak": "hinge.flap.angleDeg"}, "x": {"final": "xMm"}}}
    return one_run(trial, solids=solids, materials={"slick": SLICK})


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class Parts(unittest.TestCase):
    def test_a_ring_falls_over_a_post_that_fits_its_hole(self):
        """Catches a ring piece with its hole filled in: over a thin post it must reach the floor, over a wide one it must sit on top."""
        found, facts = ring_over_post(100)
        self.assertAlmostEqual(found["measures"]["z"], -500 + 25, delta=0.5)        # lying on the floor, the post through its hole
        self.assertLess(found["measures"]["tilt"], 0.5)
        self.assertEqual((facts["piece"]["shape"], facts["piece"]["ringSegments"], facts["piece"]["radiusMm"]), ("torus", 32, 175.0))
        self.assertEqual(ring_over_post(100, segments=16)[1]["piece"]["ringSegments"], 16)
        control, _ = ring_over_post(140)
        self.assertGreater(control["measures"]["z"], -370)      # control: a post wider than the hole holds it up

    def test_a_load_moves_the_piece_as_the_closed_form_says_in_both_engines(self):
        """Catches a load that is dropped, doubled or pointed the wrong way: 3 m/s2 for 0.1 s, then 0.2 s of coasting, is 75 mm."""
        for engine in ("planar", "mujoco"):
            trial = {**BASE, "engine": engine, "durationS": 0.3, "piece": {"use": "block", "start": {"atMm": [0, -480]}},
                     "surfaces": [{"solid": "belt bed", "material": "slick"}], "loads": [{"along": [1, 0], "accelerationMps2": 3, "durationS": 0.1}],
                     "measures": {"x": {"final": "xMm"}}}
            found, _ = one_run(trial, materials={"slick": SLICK})
            self.assertAlmostEqual(found["measures"]["x"], -75.0, delta=1.0, msg=engine)

    def test_a_sprung_flap_gives_way_alike_in_both_engines(self):
        """Catches a flap that is rigid, limp or turns the wrong way: the block's energy must wind the spring to about the same angle."""
        most = {}
        for engine in ("planar", "mujoco"):
            found, facts = gate(engine, 2.0)
            most[engine] = found["measures"]["most"]
            self.assertGreater(found["measures"]["x"], 150.0, engine)       # thrown back the way it came
        self.assertGreater(most["planar"], 20.0)
        self.assertAlmostEqual(most["mujoco"], most["planar"], delta=0.1 * most["planar"])
        self.assertEqual(facts["bodies"], {"flap:flap": "flap"})
        stiff, _ = gate("mujoco", 200.0)
        self.assertLess(stiff["measures"]["most"], 0.2 * most["mujoco"])     # control: a much stiffer spring barely moves

    def test_a_belt_on_a_moving_cart_adds_the_carts_speed(self):
        """Catches a driven surface that forgets its carrier is moving: the block ends at cart speed plus belt speed."""
        design = bench({})
        design["groups"]["cart"] = {"role": "mechanism"}
        design["solids"].append({"name": "deck", "group": "cart", "shape": BOX([-3000, -50, -520], [3000, 50, -500])})
        design["poses"] = {"back": {}}
        design["motions"] = {"roll": {"from": "back", "moves": {"cart": [{"kind": "translation", "travelMm": [250, 0, 0]}]}}}
        design["drives"] = {"spin": {"radiusMm": 25, "turns": [{"solid": "deck", "axis": [0, 1, 0]}]}}
        trial = {**BASE, "engine": "mujoco", "durationS": 0.45, "piece": {"use": "block", "start": {"atMm": [0, -480]}},
                 "commands": {"spin": {"mode": "imposed", "speedMps": 1.0}}, "movers": {"go": {"motion": "roll", "group": "cart", "startS": 0.0, "durationS": 0.5}},
                 "surfaces": [{"solid": "deck", "material": "panel", "mover": "go"}], "measures": {"speed": {"final": "speedMps"}}}
        found, facts = one_run(trial, **{k: design[k] for k in ("groups", "solids", "poses", "motions", "drives")})
        self.assertAlmostEqual(found["measures"]["speed"], 0.5 + 1.0, delta=0.03)
        self.assertEqual((facts["bodies"], facts["driven"]), ({"cart:go": "slide"}, {"deck": "spin"}))
        self.assertLess(0.5 * G * 0.45, 2.5)       # friction could have taken it further: the speed is set by the surfaces, not by the time


if __name__ == "__main__":
    unittest.main()
