"""The MuJoCo engine, stage one: calibrated against the planar engine and closed forms on cases that truly are planar.

These tests need the optional extra. Without MuJoCo installed they are skipped, except the one that checks the
library says so plainly.
"""
import importlib.util
import math
import sys
import unittest
from unittest import mock

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.trials import campaign, engines, inputs, mujoco_run

from .helpers import load_data
from .trial_cases import ASSUMES, G, MEASURED, PANEL, bench, hold_trial, on_slope

HAVE = importlib.util.find_spec("mujoco") is not None
RISE = 2000 * math.tan(math.radians(20))
GRIPPY = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.42, 0.8]}}}


def rolling(engine, piece="ball"):
    """A round piece let go on the wedge; the run stops when it has rolled 100 mm down the slope."""
    trial = hold_trial()
    trial.update(engine=engine, pass_={"outcomes": ["rolled"]})
    trial["pass"] = trial.pop("pass_")
    trial["piece"] = {"use": piece, "start": {"atMm": on_slope(300, 20 - 0.5 * G * math.cos(math.radians(20)) / 2.0e5 * 1000, 20, RISE)}}
    trial["events"] = [{"name": "rolled", "when": {"signal": "xMm", "above": on_slope(400, 20, 20, RISE)[0]}, "outcome": "rolled"}]
    trial["measures"] = {"rollS": {"timeOf": "rolled"}, "spin": {"final": "spinRadps"}}
    trial["control"] = {"change": {"gravityMps2": 0.0}, "note": "With no gravity nothing sets the piece rolling."}
    return trial


def bouncing(engine):
    return {"engine": engine, "assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 1.0, "traceS": 0.0005, "events": [],
            "pass": {"outcomes": ["timeout"]}, "piece": {"use": "ball", "start": {"atMm": [0, -280]}}, "surfaces": [{"solid": "belt bed", "material": "lively"}]}


def one_run(trial, **design):
    loaded = load_data(bench({"case": trial}, **design))
    scene = engines.build(kernel.build(loaded), "case", inputs.case(loaded.data, loaded.data["trials"]["case"]))
    facts = scene.pop("facts")
    return engines.run(scene), facts


def rebound(found):
    heights = [row[2] + 480 for row in found["trace"]["rows"]]
    low = next(i for i, h in enumerate(heights) if h <= 0)
    up = next(i for i in range(low, len(heights)) if heights[i] > 0)
    again = next(i for i in range(up, len(heights)) if heights[i] <= 0)
    return max(heights[up:again]), -min(heights)


class NotInstalled(unittest.TestCase):
    def test_a_trial_that_names_the_engine_without_it_installed_is_told_how_to_get_it(self):
        """Catches an import error where a plain message is owed, and the core library needing MuJoCo at all."""
        with mock.patch.dict(sys.modules, {"mujoco": None}), self.assertRaisesRegex(DesignError, r'MuJoCo is not installed\. Fix: Install the optional extra: pip install "frc-design-kernel\[mujoco\]'):
            mujoco_run.engine()
        self.assertNotIn("mujoco", {name.split(".")[0] for name in sys.modules if "frc_design_kernel" in name and name.endswith("planar")})


@unittest.skipUnless(HAVE, "MuJoCo is not installed (the optional extra)")
class Calibration(unittest.TestCase):
    def test_both_engines_roll_a_ball_and_a_bar_down_a_slope_at_the_closed_form_rate(self):
        """Catches a wrong mass, inertia, gravity or contact in the generated scene: rolling without slip has an exact answer."""
        for piece, factor in (("ball", 0.4), ("bar", 0.5)):
            exact = math.sqrt(2 * 0.1 / (G * math.sin(math.radians(20)) / (1 + factor)))
            planar, _ = one_run(rolling("planar", piece))
            solid, _ = one_run(rolling("mujoco", piece))
            for found in (planar, solid):
                self.assertEqual(found["outcome"], "rolled")
                self.assertAlmostEqual(found["measures"]["rollS"], exact, delta=0.005 * exact, msg=piece)
            self.assertAlmostEqual(planar["measures"]["spin"], solid["measures"]["spin"], delta=0.01 * abs(planar["measures"]["spin"]), msg=piece)

    def test_a_planar_case_stays_planar_in_3d(self):
        """Catches a scene that pushes the piece sideways or tips it when nothing in the trial should."""
        found, _ = one_run(rolling("mujoco", "bar"))
        self.assertLess(abs(found["end"]["offPlaneMm"]), 1e-6)
        self.assertLess(found["end"]["tiltDeg"], 1e-3)

    def test_both_engines_bounce_alike(self):
        """Catches a contact mapping that is far from the planar spring and damper: rebound and deepest press must agree within 5%."""
        lively = {"lively": {**PANEL, "restitution": MEASURED(0.5)}}
        (flat_up, flat_in), (solid_up, solid_in) = (rebound(one_run(bouncing(engine), materials=lively)[0]) for engine in ("planar", "mujoco"))
        self.assertAlmostEqual(solid_up, flat_up, delta=0.05 * flat_up)
        self.assertAlmostEqual(solid_in, flat_in, delta=0.05 * flat_in)
        self.assertLess(solid_up, 200.0)

    def test_solids_become_exact_shapes_where_they_can_and_hulls_are_listed(self):
        """Catches a box turned into a mesh, or a hollow solid silently filled in."""
        trial = bouncing("mujoco")
        trial["surfaces"] += [{"solid": "sleeve", "material": "lively"}, {"solid": "ell", "material": "lively"}, {"solid": "wedge", "material": "lively"}]
        solids = bench({})["solids"] + [
            {"name": "sleeve", "group": "bench", "shape": {"kind": "tube", "section": "round", "fromMm": [900, -50, -700], "toMm": [900, 50, -700], "outerDiameterMm": 60, "wallMm": 5}},
            {"name": "ell", "group": "bench", "place": [{"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 1, 0], "travelDeg": 10}],
             "shape": {"kind": "union", "of": [{"kind": "box", "fromMm": [1100, -50, -900], "toMm": [1200, 50, -890]},
                                               {"kind": "cylinder", "fromMm": [1100, -50, -885], "toMm": [1100, 50, -885], "radiusMm": 10}]}}]
        _, facts = one_run(trial, materials={"lively": PANEL}, solids=solids)
        self.assertEqual(facts["geoms"], {"belt bed": ["box"], "sleeve": ["mesh"], "ell": ["box", "cylinder"], "wedge": ["mesh"]})
        self.assertEqual(facts["hulled"], ["sleeve"])       # the wedge is a convex prism: its mesh is exact

    def test_the_same_method_and_record_surround_a_3d_trial(self):
        """Catches the 3D engine escaping the control, the half-step repeat or the record's engine stamp and assumptions."""
        path = load_data(bench({"roll": rolling("mujoco")}, materials=GRIPPY)).path
        trial = campaign.run_campaign(path)["trials"]["roll"]
        self.assertEqual((trial["result"], trial["engine"]["name"], trial["control"]["rejected"], trial["stepComparison"]["converged"]),
                         ("passed", "mujoco", True, True))
        self.assertRegex(trial["engine"]["version"], r"^\d+\.\d+")
        self.assertEqual([row["id"] for row in trial["assumptions"]["engine"]][:3], ["rigid-bodies", "single-piece", "convex-shapes"])
        self.assertIn("offPlaneMm", trial["nominal"]["trace"]["columns"])
        self.assertEqual([r["id"] for r in trial["runs"]][:3], ["nominal", "half step", "control"])
        self.assertIn("solref", trial["saw"]["contactMapping"])

    def test_what_the_engine_does_not_run_yet_is_refused_by_name(self):
        """Catches a trial with drives, loads or typed surfaces being run in 3D as if they were not there."""
        loaded = rolling("mujoco")
        loaded["loads"] = [{"along": [1, 0], "accelerationMps2": 3, "durationS": 0.1}]
        with self.assertRaisesRegex(DesignError, "the MuJoCo engine does not run loads yet"):
            one_run(loaded)
        typed = rolling("mujoco")
        typed["surfaces"].append({"name": "floor", "material": "panel", "segmentsMm": [[0, -10], [10, -10]]})
        with self.assertRaisesRegex(DesignError, 'surface "floor": the MuJoCo engine needs every surface to come from a solid'):
            one_run(typed)


if __name__ == "__main__":
    unittest.main()
