"""The standing seating case: an invented pickup every 3D engine must still seat, on its recorded path.

Both 3D defects found so far passed the single-contact calibration and were caught only by a real seated pickup: a
squeeze that came out 4 to 21 times the springs' force, and a ring given a face's direction at a faceted edge. This
case carries both features, so an engine change that brings either back, or anything else that stops a pickup
seating, fails here. The planar engine cannot take a ring's section and must say so rather than answer.
"""
import importlib.util
import unittest
from unittest import mock

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.trials import engines, inputs, mujoco_contact

from . import seating_case
from .helpers import load_data
from .trial_cases import ENGINES_3D

HAVE = importlib.util.find_spec("mujoco") is not None
# The ring's centre in the carriage's own coordinates (along the deck, off it), mm, recorded with this library at
# f68bec9 plus frames, MuJoCo 4.0.1. It seated at 1.2375 s.
RECORDED = [(0.0, 660.0, 122.2), (0.1, 641.0, 110.9), (0.2, 618.8, 108.7), (0.3, 596.4, 101.1), (0.4, 574.6, 93.5), (0.5, 553.4, 85.9),
            (0.6, 532.8, 78.3), (0.7, 512.7, 70.7), (0.8, 491.7, 63.0), (0.9, 415.3, 61.1), (1.0, 348.2, 51.0), (1.1, 271.0, 49.2), (1.2, 192.4, 48.6)]
SEATED_S = 1.2375
# Over the lip and up the belt the path is held to 1 mm: half the step, or 32 or 96 ring segments, move it 0.2 mm at
# most there, and a face's direction at the lip's edge moves it 2.8 mm. Past the flap and between the side belts it is
# held to 5 mm, where half the step moves it 2.9 mm.
TIGHT_S, TIGHT_MM, LOOSE_MM = 0.5, 1.0, 5.0


def seat(engine, change=None):
    data = seating_case.design()
    trial = data["trials"]["seat"]
    trial["engine"] = engine
    for path, value in (change or {}).items():
        at, keys = trial, path.split(".")
        for key in keys[:-1]:
            at = at[key]
        at[keys[-1]] = value
    loaded = load_data(data)
    scene = engines.build(kernel.build(loaded), "seat", inputs.case(loaded.data, loaded.data["trials"]["seat"]))
    scene.pop("facts")
    return engines.run(scene)


def off_path(found):
    """The largest distance from the recorded path, mm: (up to TIGHT_S, after it)."""
    columns = found["trace"]["columns"]
    ix, iz = columns.index("carriage.xMm"), columns.index("carriage.zMm")
    rows = {round(row[0], 2): (row[ix], row[iz]) for row in found["trace"]["rows"]}
    early, late = 0.0, 0.0
    for t, x, z in RECORDED:
        if t in rows:
            gap = max(abs(rows[t][0] - x), abs(rows[t][1] - z))
            early, late = (max(early, gap), late) if t <= TIGHT_S else (early, max(late, gap))
    return early, late


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class Seating(unittest.TestCase):
    def test_every_3d_engine_seats_the_ring_on_its_recorded_path(self):
        """Catches any 3D engine change that stops a real-shaped pickup seating, or moves it off its path or its squeeze.

        The side belts reach 5 mm into the ring and are 4500 N/m: each must press 22.5 N once it is seated.
        """
        for engine in ENGINES_3D:
            found = seat(engine)
            self.assertEqual(found["outcome"], "seated", engine)
            self.assertAlmostEqual(found["measures"]["seatedS"], SEATED_S, delta=0.03, msg=engine)
            early, late = off_path(found)
            self.assertLess(early, TIGHT_MM, engine)
            self.assertLess(late, LOOSE_MM, engine)
            for side in ("squeezeN", "otherSqueezeN"):
                self.assertAlmostEqual(found["measures"][side], 4500 * 0.005, delta=0.03 * 22.5, msg=(engine, side))
            self.assertGreater(found["measures"]["flapDeg"], 30, engine)        # the ring did push the flap open

    def test_the_case_can_fail(self):
        """Catches a case that would pass whatever the engine did: the belt stopped does not seat, and an edge given a face's
        direction leaves the recorded path over the lip."""
        for engine in ENGINES_3D:
            self.assertEqual(seat(engine, {"commands.belt.speedMps": 0.0})["outcome"], "timeout", engine)
        with mock.patch.object(mujoco_contact, "ROUND", ()):
            self.assertGreater(off_path(seat("mujoco"))[0], TIGHT_MM)


class PlanarSeating(unittest.TestCase):
    def test_the_planar_engine_says_it_cannot_take_a_ring(self):
        """Catches the planar engine answering a case it cannot see: a ring has no round section across the plane."""
        with self.assertRaisesRegex(DesignError, "cannot take a round section"):
            seat("planar")


if __name__ == "__main__":
    unittest.main()
