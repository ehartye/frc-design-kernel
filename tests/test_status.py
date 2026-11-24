"""Records say what they used; status says which are current and which are stale, and why; and what a 3D engine would need."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import frc_design_kernel as kernel
from frc_design_kernel.cli import main
from frc_design_kernel.status import status
from frc_design_kernel.trials import ready

from .helpers import load_data
from .trial_cases import MEASURED, PANEL, bench, hold_trial

GRIPPY = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.42, 0.8]}}}
TURN = {"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 1, 0], "travelDeg": 30}


def ride_trial():
    """A ball set on the belt bed; it only has to stay there."""
    return {"assumes": [{"text": "The bed is level and still."}], "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 0.6, "traceS": 0.01,
            "piece": {"use": "ball", "start": {"atMm": [0, -480]}}, "surfaces": [{"solid": "belt bed", "material": "panel"}],
            "events": [{"name": "fell", "when": {"signal": "zMm", "below": "=-600 - rise * 0"}, "outcome": "fell"},
                       {"name": "stayed", "when": {"restFor": 0.2}, "outcome": "stayed"}],
            "movers": {"wave": {"motion": "shove", "group": "gate", "startS": 0.0, "durationS": 0.2}},
            "pass": {"outcomes": ["stayed"]}, "control": {"change": {"surfaces.belt bed": None}, "note": "With no bed under it the ball must fall."}}


def source():
    data = bench({"hold": hold_trial(), "ride": ride_trial()}, materials=GRIPPY)
    data["groups"]["gate"] = {"role": "mechanism"}
    data["solids"].append({"name": "gate", "group": "gate", "massKg": 0.2, "shape": {"kind": "box", "fromMm": [2500, -50, 0], "toMm": [2520, 50, 200]}})
    data["poses"] = {"shut": {}, "open": {"gate": [dict(TURN)]}}
    data["motions"] = {"swing": {"from": "shut", "moves": {"gate": [dict(TURN)]}}, "sweep": {"through": ["shut", "open"]},
                       "shove": {"from": "shut", "moves": {"gate": [{"kind": "translation", "travelMm": [10, 0, 0]}]}}}
    return data


def states(found):
    return {row["record"]: row["state"] for row in found["records"]}


class Stale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = source()
        cls.path = load_data(cls.data).path
        cls.folder = tempfile.TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["try", str(cls.path), "--out", cls.folder.name]) == 0
            assert main(["measure", str(cls.path), "--out", cls.folder.name, "--workers", "1"]) == 0

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def after(self, change=None):
        data = copy.deepcopy(self.data)
        if change:
            change(data)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        try:
            return status(self.path, self.folder.name)
        finally:
            self.path.write_text(json.dumps(self.data), encoding="utf-8")

    def test_untouched_records_are_all_current(self):
        """Catches records reported stale when nothing has changed."""
        found = states(self.after())
        self.assertEqual(set(found.values()), {"current"})
        self.assertEqual(sorted(found), ['clearance along "shove"', 'clearance along "sweep"', 'clearance along "swing"', "measures as drawn", 'measures at the pose "open"',
                                         'measures at the pose "shut"', 'trial "hold"', 'trial "ride"'])

    def test_a_moved_solid_makes_stale_exactly_the_records_that_used_it(self):
        """Catches a moved solid going unnoticed, or records that never used it being called stale."""
        found = self.after(lambda d: d["solids"][1]["shape"].update(fromMm=[-3000, -50, -520], toMm=[3100, 50, -500]))     # the belt bed grows
        rows = {row["record"]: row for row in found["records"]}
        self.assertEqual(rows['trial "ride"']["state"], "stale")
        self.assertEqual(rows['trial "ride"']["changes"], ['solid "belt bed" changed (boundsMm, volumeMm3)'])
        self.assertEqual(rows['trial "hold"']["state"], "current")      # it cut the wedge only
        for name in ('clearance along "swing"', "measures as drawn"):   # every solid present is an obstacle or a weight there
            self.assertEqual((rows[name]["state"], rows[name]["changes"]), ("stale", ['solid "belt bed" changed (boundsMm, volumeMm3)']))

    def test_a_renamed_design_or_an_edited_note_makes_nothing_stale(self):
        """Catches staleness tied to the file's fingerprint when only words changed."""
        def reword(d):
            d["name"] = "Trial bench, renamed"
            d["trials"]["hold"]["control"]["note"] = "Reworded: a slippery panel lets the block go."
            d["motions"]["swing"]["note"] = "A new remark."
            d["pieces"]["block"]["note"] = "Still cannot spin."
        self.assertEqual(set(states(self.after(reword)).values()), {"current"})

    def test_what_changed_is_named(self):
        """Catches a stale record with no stated cause: a parameter, a trial number, a motion and a mass each name themselves."""
        slope = {r["record"]: r for r in self.after(lambda d: d["parameters"].update(slope_deg=25))["records"]}
        self.assertIn('solid "wedge" changed (boundsMm, volumeMm3)', slope['trial "hold"']["changes"])
        self.assertEqual(slope['trial "ride"']["changes"], ['parameter "rise" changed: 727.940469 to 932.615316', 'parameter "slope_deg" changed: 20 to 25'])
        grip = {r["record"]: r for r in self.after(lambda d: d["materials"]["panel"]["friction"].update(value=0.6))["records"]}
        self.assertEqual(grip['trial "hold"']["changes"], ["the trial definition changed at materials.panel.friction.value"])
        self.assertEqual(grip["measures as drawn"]["state"], "current")
        moved = {r["record"]: r for r in self.after(lambda d: d["motions"]["swing"]["moves"]["gate"][0].update(travelDeg=31))["records"]}
        self.assertEqual((moved['clearance along "swing"']["changes"], moved['clearance along "sweep"']["state"]), (["motion changed"], "current"))
        shoved = {r["record"]: r for r in self.after(lambda d: d["motions"]["shove"]["moves"]["gate"][0].update(travelMm=[12, 0, 0]))["records"]}
        self.assertEqual((shoved['trial "ride"']["changes"], shoved['trial "hold"']["state"]), (['the motion "shove" changed'], "current"))     # a mover follows it
        heavier = {r["record"]: r for r in self.after(lambda d: d["solids"][2].update(massKg=0.3))["records"]}
        self.assertEqual(heavier["measures as drawn"]["changes"], ['solid "gate" changed (massKg, massRangeKg)'])     # a plain number is both ends

    def test_a_targeted_rerun_is_one_command_and_keeps_the_rest(self):
        """Catches a rerun of one trial or one motion throwing away the records that were not run again."""
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(io.StringIO()) as text:
            for name in ("trials.json", "measurements.json"):
                (Path(out) / name).write_text((Path(self.folder.name) / name).read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(main(["try", str(self.path), "--out", out, "--trial", "ride"]), 0)
            self.assertEqual(main(["measure", str(self.path), "--out", out, "--motion", "swing", "--workers", "1"]), 0)
            trials = json.loads((Path(out) / "trials.json").read_text(encoding="utf-8"))
            measures = json.loads((Path(out) / "measurements.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(trials["trials"]), ["hold", "ride"])
        self.assertEqual((sorted(measures["motions"]), len(measures["poses"])), (["shove", "sweep", "swing"], 3))
        self.assertIn("keeping the trials that were not run again", text.getvalue())
        self.assertNotIn('Trial "hold"', text.getvalue())

    def test_the_status_command_states_facts_only(self):
        """Catches the command judging, or hiding why a record is stale."""
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            self.assertEqual(main(["status", str(self.path), self.folder.name]), 0)
        lines = text.getvalue().splitlines()
        self.assertEqual(lines[0], f'Records in {self.folder.name} against "Trial bench" as it is now:')
        self.assertIn('trial "hold": current', lines)
        self.assertTrue(lines[-1].startswith("For a 3D engine: 0 trial solids concave with no convex breakdown; 2 solids with no mass; 1 moving group not one hinge or slider;"))


class ReadyFor3d(unittest.TestCase):
    def test_the_facts_a_3d_engine_would_need_settled(self):
        """Catches a hollow or cut solid, a weightless solid, a path-driven group, a loose drive or a typed surface going unlisted."""
        data = source()
        data["solids"] += [
            {"name": "sleeve", "group": "bench", "massKg": 0.1, "shape": {"kind": "tube", "section": "round", "fromMm": [0, -50, -700], "toMm": [0, 50, -700], "outerDiameterMm": 60, "wallMm": 5}},
            {"name": "ell", "group": "bench", "massKg": 0.1, "shape": {"kind": "union", "of": [{"kind": "box", "fromMm": [100, -50, -700], "toMm": [200, 50, -690]},
                                                                                                    {"kind": "box", "fromMm": [100, -50, -700], "toMm": [110, 50, -600]}]}}]
        trial = ride_trial()
        trial["surfaces"] += [{"solid": "sleeve", "material": "panel"}, {"solid": "ell", "material": "panel"},
                              {"name": "floor", "material": "panel", "segmentsMm": [[-100, -900], [100, -900]], "drive": "loose"}]
        trial["commands"] = {"loose": {"mode": "imposed", "speedMps": 0}}
        data["trials"] = {"ride": trial}
        data["drives"] = {"loose": {"radiusMm": 20}}
        found = ready.report(kernel.build(load_data(data)))
        self.assertEqual(found["trialSolids"], ["belt bed", "ell", "sleeve"])
        self.assertEqual(found["concaveWithNoBreakdown"], [])     # the ell is a union of two boxes; the sleeve breaks into a ring of wedges
        self.assertEqual(found["solidsWithNoMass"], ["belt bed", "wedge"])
        self.assertEqual(found["groupsNotOneHingeOrSlider"], [{"motion": "sweep", "group": "gate"}])       # "swing" is one hinge
        self.assertEqual(found["drivesNotOnASolid"], ["loose"])
        self.assertEqual(found["surfacesNotFromSolids"], [{"trial": "ride", "surface": "floor", "drive": "loose"}])

    def test_how_a_shape_was_built_tells_whether_it_breaks_into_convex_pieces(self):
        """Catches a concave shape being called convex, or a union of boxes being called unbreakable."""
        box = {"kind": "box", "fromMm": [0, 0, 0], "toMm": [1, 1, 1]}
        self.assertEqual(ready.breakdown(box), "convex")
        self.assertEqual(ready.breakdown({"kind": "union", "of": [box, box]}), "union of convex pieces")
        ball = {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 1}
        built = "convex pieces from its construction"
        self.assertEqual(ready.breakdown({"kind": "difference", "from": box, "cut": [box]}), built)       # a box less boxes leaves boxes
        self.assertEqual(ready.breakdown({"kind": "difference", "from": box, "cut": [ball]}), "a shape with material cut away")
        self.assertEqual(ready.breakdown({"kind": "prism", "plane": "xy", "outlineMm": [[0, 0], [4, 0], [4, 4], [2, 1], [0, 4]], "fromMm": 0, "toMm": 1}), built)
        self.assertEqual(ready.breakdown({"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 9], "outerDiameterMm": 9, "wallMm": 1}), built)
        self.assertEqual(ready.breakdown({"kind": "intersection", "of": [box, ball]}), "convex")
        self.assertEqual(ready.breakdown({"kind": "cylinder", "fromMm": [0, 0, 0], "toMm": [0, 0, 1], "radiusMm": 1, "sweepDeg": 270}), "a pie slice wider than a half turn")


if __name__ == "__main__":
    unittest.main()
