"""Frames: the piece's place in a group's own drawing coordinates, the same in both engines, while the group moves."""
import importlib.util
import unittest

from frc_design_kernel import DesignError

from .test_mujoco import one_run
from .trial_cases import ASSUMES, ENGINES, bench

HAVE = importlib.util.find_spec("mujoco") is not None
SLIDE = {"startS": 0.05, "durationS": 0.5}


def carried(engine, frame):
    """A block on a tray. The tray is drawn with its top at z = 0, then turned half a turn about z and set 100 mm along x
    and 500 mm down. A mover slides it 200 mm along x."""
    design = bench({})
    design["groups"]["tray"] = {"role": "mechanism", "place": [{"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 0, 1], "travelDeg": 180},
                                                               {"kind": "translation", "travelMm": [100, 0, -500]}]}
    design["solids"].append({"name": "tray", "group": "tray", "shape": {"kind": "box", "fromMm": [-300, -50, -20], "toMm": [300, 50, 0]}})
    design["poses"] = {"loaded": {}}
    design["motions"] = {"carry": {"from": "loaded", "moves": {"tray": [{"kind": "translation", "travelMm": [200, 0, 0]}]}}}
    trial = {"engine": engine, "assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 0.7, "traceS": 0.01, "events": [],
             "pass": {"outcomes": ["timeout"]}, "piece": {"use": "block", "start": {"atMm": [100, -480]}},
             "movers": {"carry": {"motion": "carry", "group": "tray", **SLIDE}},
             "surfaces": [{"solid": "tray", "material": "panel", "mover": "carry"}], "frames": {"tray": frame},
             "measures": {"along": {"final": "tray.xMm"}}}
    return one_run(trial, **{k: design[k] for k in ("groups", "solids", "poses", "motions")})[0]


def moved(t):
    return 200.0 * min(1.0, max(0.0, (t - SLIDE["startS"]) / SLIDE["durationS"]))


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class Frames(unittest.TestCase):
    def test_the_piece_is_found_in_the_trays_own_coordinates_as_the_tray_moves(self):
        """Catches a frame signal that ignores the group's own place (its turn and shift) or the mover's slide, in either engine.

        In the tray's coordinates x is 100 mm plus the slide so far, less the world x, and z is the world z plus 500 mm.
        """
        for engine in ENGINES:
            found = carried(engine, {"group": "tray", "mover": "carry"})
            columns = found["trace"]["columns"]
            ix, iz, fx, fz = (columns.index(name) for name in ("xMm", "zMm", "tray.xMm", "tray.zMm"))
            for row in found["trace"]["rows"]:
                self.assertAlmostEqual(row[fx], 100.0 + moved(row[0]) - row[ix], delta=0.1, msg=(engine, row[0]))
                self.assertAlmostEqual(row[fz], row[iz] + 500.0, delta=1e-6, msg=(engine, row[0]))
            still = carried(engine, {"group": "tray"})        # control: a frame with no mover stays where the pose put it
            self.assertAlmostEqual(still["measures"]["along"] - found["measures"]["along"], -200.0, delta=0.1, msg=engine)

    def test_a_frame_must_name_a_group_and_a_mover_along_a_motion(self):
        """Catches a frame that quietly reads as the world when its group or mover is misspelt."""
        with self.assertRaisesRegex(DesignError, 'names the group "tary"'):
            carried("planar", {"group": "tary"})
        with self.assertRaisesRegex(DesignError, 'names the mover "cary"'):
            carried("mujoco", {"group": "tray", "mover": "cary"})


if __name__ == "__main__":
    unittest.main()
