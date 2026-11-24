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
from .trial_cases import ENGINES, ASSUMES, G, MEASURED, PANEL, bench, hold_trial, on_slope

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

    def test_forces_agree_with_the_planar_engine(self):
        """Catches peak force, a signal for squeeze and structure, drifting between engines: at rest both give the weight, and a bounce peaks alike."""
        lively = {"lively": {**PANEL, "restitution": MEASURED(0.5)}}
        peaks = {}
        for engine in ENGINES:
            trial = bouncing(engine)
            trial.update(durationS=3.0, measures={"peak": {"peak": "contact.belt bed.forceN"}, "end": {"final": "contact.belt bed.forceN"}})
            found = one_run(trial, materials=lively)[0]["measures"]
            self.assertAlmostEqual(found["end"], 0.5 * G, delta=0.001 * 0.5 * G, msg=engine)
            peaks[engine] = found["peak"]
        self.assertAlmostEqual(peaks["mujoco"], peaks["planar"], delta=0.05 * peaks["planar"])

    def drop(self, shape, start, design_extra=None, duration=1.5):
        """A small ball dropped at start onto one extra solid; returns where it comes to rest (x, z in mm), the scene facts
        and the hulled solids it touched."""
        trial = {"engine": "mujoco", "assumes": ASSUMES, "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": duration, "traceS": 0.01,
                 "piece": {"use": "shot", "start": {"atMm": start}}, "surfaces": [{"solid": "thing", "material": "panel"}],
                 "events": [{"name": "still", "when": {"all": [{"signal": "tS", "above": 0.3}, {"restFor": 0.2}]}, "outcome": "still"}],
                 "pass": {"outcomes": ["still"]}, "measures": {"x": {"final": "xMm"}, "z": {"final": "zMm"}}}
        solids = bench({})["solids"] + [{"name": "thing", "group": "bench", "shape": shape}]
        found, facts = one_run(trial, solids=solids, **(design_extra or {}))
        return found["measures"]["x"], found["measures"]["z"], facts, found["touchedRough"]

    def test_a_tube_keeps_its_bore_and_a_slot_stays_open(self):
        """Catches a hollow or cut shape being filled in: a ball must come to rest inside a tube's bore and in a slot, not on top."""
        tube = {"kind": "tube", "section": "round", "fromMm": [3000, -60, 100], "toMm": [3000, 60, 100], "outerDiameterMm": 200, "wallMm": 10}
        x, z, facts, touched = self.drop(tube, [3000, 120])
        self.assertAlmostEqual(z, 100 - 90 + 5, delta=0.5)        # on the bottom of the bore (inner radius 90), not on top of the tube (z = 205)
        self.assertEqual((facts["hulled"], len(facts["geoms"]["thing"])), ([], 24))
        self.assertIn("flat facets", facts["faceted"]["thing"])
        slot = {"kind": "difference", "from": {"kind": "box", "fromMm": [3000, -60, 0], "toMm": [3200, 60, 100]},
                "cut": [{"kind": "box", "fromMm": [3080, -70, 40], "toMm": [3120, 70, 110]}]}
        x, z, facts, touched = self.drop(slot, [3100, 140])
        self.assertAlmostEqual(z, 40 + 5, delta=0.5)              # on the floor of the slot, not on the box's top (z = 105)
        self.assertEqual((facts["hulled"], facts["faceted"]), ([], {}))
        vee = {"kind": "prism", "plane": "xz", "fromMm": -60, "toMm": 60, "outlineMm": [[3000, 0], [3200, 0], [3200, 100], [3100, 20], [3000, 100]]}
        x, z, facts, touched = self.drop(vee, [3110, 140])
        self.assertAlmostEqual(x, 3100, delta=1.0)                # it settles in the bottom of the vee, not across its rim
        self.assertLess(z, 40)
        self.assertEqual(facts["hulled"], [])

    def sit(self, shape, start):
        """The record of a campaign that drops the small ball at start onto one extra solid and passes when it comes to rest."""
        trial = rolling("mujoco")
        trial["surfaces"] = [{"solid": "thing", "material": "panel"}]
        trial["piece"] = {"use": "shot", "start": {"atMm": start}}
        trial["events"] = [{"name": "rolled", "when": {"all": [{"signal": "tS", "above": 0.3}, {"restFor": 0.2}]}, "outcome": "rolled"}]
        trial["measures"] = {}
        trial["control"] = {"change": {"piece.start.velocityMps": [5, 5]}, "note": "Thrown clear of the block, it never comes to rest on it."}
        solids = bench({})["solids"] + [{"name": "thing", "group": "bench", "shape": shape}]
        return campaign.run_campaign(load_data(bench({"sit": trial}, materials=GRIPPY, solids=solids)).path)["trials"]["sit"]

    def test_a_round_trough_is_wedged_and_the_piece_sits_in_it(self):
        """Catches a round cut being filled in, or a result on its exact flat facets being called a hulled surface."""
        trough = {"kind": "difference", "from": {"kind": "box", "fromMm": [3000, -60, 0], "toMm": [3200, 60, 100]},
                  "cut": [{"kind": "cylinder", "fromMm": [3100, -70, 100], "toMm": [3100, 70, 100], "radiusMm": 60}]}       # no breakdown from construction
        x, z, facts, touched = self.drop(trough, [3100, 140])
        self.assertAlmostEqual(z, 100 - 60 + 5, delta=0.5)        # on the bottom of the trough, not on the filled-in top (z = 105)
        self.assertEqual(facts["hulled"], [])
        self.assertRegex(facts["faceted"]["thing"], r"flat facets, at most 0\.\d\d mm inside them")
        found = self.sit(trough, [3100, 140])
        self.assertEqual((found["result"], found["touchedHulled"]), ("passed", []))

    def test_a_result_that_rests_on_a_filled_in_shape_says_so_and_only_then(self):
        """Control: catches a hulled piece the piece touched going unmentioned in the result word, and a touch on the
        same solid's exact pieces being flagged as if it were on the hull.

        A step block has a dimple (an inward ball, which wedges cannot make convex) in its tall end. Split at its faces,
        the low end is an exact piece and only the tall end with the dimple is hulled.
        """
        step = {"kind": "difference", "from": {"kind": "prism", "plane": "xz", "fromMm": -60, "toMm": 60,
                                                "outlineMm": [[3000, 0], [3300, 0], [3300, 100], [3200, 100], [3200, 20], [3000, 20]]},
                "cut": [{"kind": "sphere", "centerMm": [3250, 0, 100], "radiusMm": 30}]}
        x, z, facts, touched = self.drop(step, [3250, 140])
        self.assertEqual(facts["hulled"], ["thing"])
        self.assertAlmostEqual(z, 105, delta=0.5)                 # it sits on the filled-in dimple, which is exactly what must be flagged
        self.assertEqual(touched, ["thing"])
        found = self.sit(step, [3250, 140])
        self.assertEqual((found["result"], found["touchedHulled"]), ("passed, on a hulled surface", ["thing"]))
        self.assertIn("taken as its convex hull", found["findings"][-1])
        x, z, facts, touched = self.drop(step, [3050, 60])
        self.assertEqual((facts["hulled"], touched), (["thing"], []))
        self.assertAlmostEqual(z, 20 + 5, delta=0.5)              # on the low end's exact top
        found = self.sit(step, [3050, 60])
        self.assertEqual((found["result"], found["touchedHulled"]), ("passed", []))

    def test_solids_become_exact_shapes_where_they_can_and_hulls_are_listed(self):
        """Catches a box turned into a mesh, or a hull going unlisted."""
        trial = bouncing("mujoco")
        trial["surfaces"] += [{"solid": "ell", "material": "lively"}, {"solid": "wedge", "material": "lively"}]
        solids = bench({})["solids"] + [
            {"name": "ell", "group": "bench", "place": [{"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 1, 0], "travelDeg": 10}],
             "shape": {"kind": "union", "of": [{"kind": "box", "fromMm": [1100, -50, -900], "toMm": [1200, 50, -890]},
                                               {"kind": "cylinder", "fromMm": [1100, -50, -885], "toMm": [1100, 50, -885], "radiusMm": 10}]}}]
        _, facts = one_run(trial, materials={"lively": PANEL}, solids=solids)
        self.assertEqual(facts["geoms"], {"belt bed": ["box"], "ell": ["box", "cylinder"], "wedge": ["mesh"]})
        self.assertEqual(facts["hulled"], [])       # the wedge is a convex prism: its mesh is exact

    def test_the_same_method_and_record_surround_a_3d_trial(self):
        """Catches the 3D engine escaping the control, the half-step repeat or the record's engine stamp and assumptions."""
        path = load_data(bench({"roll": rolling("mujoco")}, materials=GRIPPY)).path
        trial = campaign.run_campaign(path)["trials"]["roll"]
        self.assertEqual((trial["result"], trial["engine"]["name"], trial["control"]["rejected"], trial["stepComparison"]["converged"]),
                         ("passed", "mujoco", True, True))
        self.assertRegex(trial["engine"]["version"], r"^\d+\.\d+")
        self.assertEqual([row["id"] for row in trial["assumptions"]["engine"]][:3], ["rigid-bodies", "listed-pieces", "convex-shapes"])
        self.assertIn("offPlaneMm", trial["nominal"]["trace"]["columns"])
        self.assertEqual([r["id"] for r in trial["runs"]][:3], ["nominal", "half step", "control"])
        self.assertIn("the library's own spring, damper and friction law", trial["saw"]["contactLaw"])

    def test_what_the_engine_does_not_run_yet_is_refused_by_name(self):
        """Catches a typed flap or a typed surface being run in 3D as if it were not there."""
        loaded = rolling("mujoco")
        loaded["flaps"] = [{"name": "flap", "material": "panel", "hingeMm": [0, 0], "lengthMm": 50, "restDirection": [1, 0],
                            "inertiaKgM2": MEASURED(1e-4), "springNmPerRad": MEASURED(1.0), "limitDeg": 60}]
        with self.assertRaisesRegex(DesignError, "the MuJoCo engine needs a flap to name the solid that is the flap"):
            one_run(loaded)
        typed = rolling("mujoco")
        typed["surfaces"].append({"name": "floor", "material": "panel", "segmentsMm": [[0, -10], [10, -10]]})
        with self.assertRaisesRegex(DesignError, 'surface "floor": the MuJoCo engine needs every surface to come from a solid'):
            one_run(typed)


if __name__ == "__main__":
    unittest.main()
