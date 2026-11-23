"""The method around a trial: control, brackets, half-step repeat, cost, hand-off, custom code, the record and the command."""
import contextlib
import copy
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

from frc_design_kernel import DesignError
from frc_design_kernel.cli import main
from frc_design_kernel.motion import ops
from frc_design_kernel.trials import campaign, fit, record

from .helpers import load_data
from .trial_cases import PANEL, bench, hold_trial

WIND = "def force(signals, parameters):\n    return (parameters['pushN'], 0.0, 0.0)\n"
JUDGE = "import math\n\n\ndef judge(run, parameters):\n    return run['outcome'] == 'held' and math.isfinite(run['measures']['push'])\n"
CUSTOM = {"wind": {"kind": "force", "reason": "A steady side wind on the block; no listed load pushes with a fixed force.",
                   "limits": "A constant force only. It does not change with speed."},
          "held_firmly": {"kind": "criterion", "reason": "Held, and the peak push is a real number; the listed limits cannot test that.",
                          "limits": "It reads the run summary only."}}


def campaign_for(trials, files=None, **design):
    path = load_data(bench(trials, **design), files).path
    return campaign.run_campaign(path), path


class Method(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record, cls.path = campaign_for({"hold": hold_trial()})
        cls.trial = cls.record["trials"]["hold"]

    def test_a_complete_trial_that_holds_is_passed(self):
        """Catches a sound trial being reported as anything but passed, or its record losing a part of the method."""
        self.assertEqual((self.trial["result"], self.trial["findings"]), ("passed", []))
        self.assertEqual(self.trial["nominal"]["outcome"], "held")
        self.assertEqual([r["id"] for r in self.trial["runs"]],
                         ["nominal", "half step", "control", "materials.panel.friction = 0.2", "materials.panel.friction = 0.8", "parameters.slope_deg = 35"])

    def test_the_control_must_be_rejected(self):
        """Control: catches a campaign that would pass a trial whose control also meets the criterion."""
        self.assertEqual((self.trial["control"]["rejected"], self.trial["control"]["outcome"]), (True, "slid"))
        soft, _ = campaign_for({"hold": hold_trial(control={"change": {"materials.panel.friction": 0.45}, "note": "Slightly less grip still holds."})})
        self.assertEqual(soft["trials"]["hold"]["result"], "control not rejected")

    def test_brackets_give_a_passing_and_a_failing_value_per_input(self):
        """Catches a bracket that reports the wrong side of the threshold, or a design parameter that did not move the geometry."""
        grip, slope = self.trial["brackets"]
        self.assertEqual((grip["nominal"], grip["passing"], grip["failing"], grip["bracketed"]), (0.5, 0.5, 0.2, True))
        self.assertEqual([(v["value"], v["passed"]) for v in grip["values"]], [(0.2, False), (0.5, True), (0.8, True)])
        self.assertEqual((slope["nominal"], slope["passing"], slope["failing"], slope["unit"]), (20, 20, 35, "deg"))

    def test_a_trial_without_control_or_brackets_is_incomplete_not_passed(self):
        """Catches a trial being called passed with nothing to show it could fail."""
        for missing in ("control", "brackets"):
            trial = hold_trial()
            del trial[missing]
            found, _ = campaign_for({"hold": trial})
            self.assertEqual(found["trials"]["hold"]["result"], "incomplete", missing)
            self.assertEqual(found["trials"]["hold"]["nominal"]["met"], True)

    def test_a_failing_nominal_run_is_failed_with_the_reason(self):
        """Catches a failed trial hidden behind a complete method."""
        found, _ = campaign_for({"hold": hold_trial(friction=0.3)})
        self.assertEqual((found["trials"]["hold"]["result"], found["trials"]["hold"]["firstUnmet"]), ("failed", 'outcome was "slid"'))

    def test_a_result_that_changes_at_half_the_step_is_not_converged(self):
        """Catches a step too coarse to trust: at the full step the piece jumps through a wall; at half the step it hits it."""
        trial = {"plane": {"normal": "y", "atMm": 0}, "stepS": 2e-3, "durationS": 0.02, "gravityMps2": 0.0, "materials": {"panel": dict(PANEL)},
                 "piece": {"radiusMm": 5, "massKg": 0.1, "start": {"atMm": [0, 0], "velocityMps": [10, 0]}},
                 "surfaces": [{"name": "wall", "material": "panel", "segmentsMm": [[31, -100], [31, 100]]}],
                 "events": [{"name": "through", "when": {"signal": "xMm", "above": 60}, "outcome": "went through the wall"}],
                 "pass": {"outcomes": ["went through the wall"]},
                 "control": {"change": {"piece.start.velocityMps": [-10, 0]}, "note": "Thrown the other way it cannot get through."},
                 "brackets": [{"input": "piece.massKg", "values": [0.1, 0.2]}]}
        found, _ = campaign_for({"jump": trial})
        steps = found["trials"]["jump"]["stepComparison"]
        self.assertEqual((steps["coarseOutcome"], steps["fineOutcome"], steps["converged"]), ("went through the wall", "timeout", False))
        self.assertEqual(found["trials"]["jump"]["result"], "not converged")

    def test_the_half_step_repeat_reports_how_much_the_measures_move(self):
        """Catches a step comparison that only looks at the outcome word."""
        steps = self.trial["stepComparison"]
        self.assertEqual((steps["coarseS"], steps["fineS"], steps["sameOutcome"]), (1e-4, 5e-5, True))
        coarse, fine = steps["measures"]["endX"]
        self.assertLess(abs(coarse - fine), 0.01)

    def test_the_same_campaign_gives_the_same_record(self):
        """Catches anything that makes two campaigns of one source differ, including sharing runs between workers."""
        self.assertEqual(campaign.run_campaign(self.path), self.record)
        self.assertEqual(campaign.run_campaign(self.path, workers=2), self.record)
        self.assertEqual(json.loads(json.dumps(self.record)), self.record)

    def test_the_record_is_stamped_and_replayable(self):
        """Catches a record without its stamp, its inputs or a trace a page could play."""
        self.assertEqual((self.record["schema"], self.record["generator"]["library"]), ("frc-design-kernel/trial-campaign@1", "frc-design-kernel"))
        nominal = self.trial["nominal"]
        self.assertEqual(nominal["trace"]["columns"][:4], ["tS", "xMm", "zMm", "spinRadps"])
        self.assertGreater(len(nominal["trace"]["rows"]), 40)
        self.assertEqual(list(nominal["contacts"]), ["slope"])
        self.assertEqual(self.trial["definition"]["materials"]["panel"]["friction"], 0.5)
        self.assertEqual(self.trial["runs"][2]["changes"], {"materials.panel.friction": 0.1})


class Cost(unittest.TestCase):
    def test_the_cost_is_counted_before_anything_runs_and_can_be_capped(self):
        """Catches a campaign that starts without saying what it will cost, or ignores the caller's cap."""
        path = load_data(bench({"hold": hold_trial()})).path
        told = []
        campaign.run_campaign(path, announce=told.append)
        self.assertEqual(told, [{"runs": 6, "steps": 70000, "trials": {"hold": {"runs": 6, "steps": 70000}}}])
        told.clear()
        with self.assertRaisesRegex(DesignError, "needs up to 70000 steps in 6 runs, over the cap of 50000"):
            campaign.run_campaign(path, max_steps=50000, announce=told.append)
        self.assertEqual(len(told), 1)      # the cost was still stated before the refusal


class HandOff(unittest.TestCase):
    def test_one_trials_end_state_starts_the_next(self):
        """Catches a hand-off that restarts from the drawing: the second trial must begin where the first one came to rest."""
        second = hold_trial()
        second["piece"]["start"] = {"after": "hold"}
        found, _ = campaign_for({"then": second, "hold": hold_trial()})
        self.assertEqual(list(found["trials"]), ["hold", "then"])
        end = found["trials"]["hold"]["nominal"]["end"]["piece"]
        first_row = found["trials"]["then"]["nominal"]["trace"]["rows"][0]
        self.assertAlmostEqual(first_row[1], end[0] * 1000, places=3)
        self.assertAlmostEqual(first_row[2], end[1] * 1000, places=3)
        self.assertEqual(campaign.estimate(load_data(bench({"then": second, "hold": hold_trial()})), ["then"])["runs"], 12)


class CustomCode(unittest.TestCase):
    def trial(self):
        return hold_trial(forces=[{"use": "wind", "parameters": {"pushN": 0.5}}],
                          **{"pass": {"outcomes": ["held"], "custom": {"use": "held_firmly"}}})

    def test_registered_custom_code_runs_inside_the_method_and_is_listed(self):
        """Catches custom code that escapes the record, or that the control and brackets no longer surround."""
        found, _ = campaign_for({"hold": self.trial()}, {"custom/wind.py": WIND, "custom/held_firmly.py": JUDGE}, custom=CUSTOM)
        trial = found["trials"]["hold"]
        self.assertEqual((trial["result"], trial["control"]["rejected"], len(trial["runs"])), ("passed", True, 6))
        self.assertEqual([(row["name"], row["kind"], row["lines"], row["usedBy"]) for row in found["custom"]],
                         [("held_firmly", "criterion", 5, ["trial hold"]), ("wind", "force", 2, ["trial hold"])])
        strong = self.trial()
        strong["forces"][0]["parameters"]["pushN"] = 6.0      # enough to push the block down the slope
        blown, _ = campaign_for({"hold": strong}, {"custom/wind.py": WIND, "custom/held_firmly.py": JUDGE}, custom=CUSTOM)
        self.assertEqual(blown["trials"]["hold"]["result"], "failed")

    def test_custom_trial_code_is_checked_before_it_runs(self):
        """Catches custom trial code that reaches for files or the CAD kernel, is unregistered, or is the wrong kind."""
        files = {"custom/wind.py": "import os\n" + WIND, "custom/held_firmly.py": JUDGE}
        with self.assertRaisesRegex(DesignError, 'custom "wind": its code imports "os", which a custom force may not do'):
            campaign_for({"hold": self.trial()}, files, custom=CUSTOM)
        with self.assertRaisesRegex(DesignError, 'imports "OCP'):
            campaign_for({"hold": self.trial()}, {**files, "custom/wind.py": "from OCP.gp import gp_Pnt\n" + WIND}, custom=CUSTOM)
        with self.assertRaisesRegex(DesignError, 'names the custom force "wind", which does not exist'):
            campaign_for({"hold": self.trial()}, files, custom={"held_firmly": CUSTOM["held_firmly"]})
        wrong = {**CUSTOM, "wind": {**CUSTOM["wind"], "kind": "criterion"}}
        with self.assertRaisesRegex(DesignError, 'uses "wind" as a custom force, but it is registered as another kind'):
            campaign_for({"hold": self.trial()}, files, custom=wrong)


class Checks(unittest.TestCase):
    def expect(self, change, pattern):
        trial = hold_trial()
        change(trial)
        with self.assertRaisesRegex(DesignError, pattern):
            campaign_for({"hold": trial})

    def test_a_trial_that_names_something_missing_is_refused_before_it_runs(self):
        """Catches a misspelt solid, material, signal, event, measure or path failing late or silently."""
        self.expect(lambda t: t["surfaces"][0].update(solid="wege"), r'trials "hold" surface "slope": names the solid "wege"')
        self.expect(lambda t: t["surfaces"][0].update(material="panle"), 'names the material "panle"')
        self.expect(lambda t: t["events"][0]["when"].update(signal="xmm"), r'trials "hold" event "slid": names the signal "xmm"')
        self.expect(lambda t: t["measures"].update(late={"timeOf": "sld"}), 'measure "late": names "sld"')
        self.expect(lambda t: t["pass"].update(limits=[{"measure": "psh", "atMost": 1}]), 'names the measure "psh"')
        self.expect(lambda t: t["control"]["change"].update({"materials.pannel.friction": 1}), 'the path "materials.pannel.friction" does not lead anywhere at "pannel"')
        self.expect(lambda t: t.update(plane={"normal": "y", "atMm": 900}), "the plane y = 900 mm does not cut the solid")
        self.expect(lambda t: t.update(stpS=1), r'trials "hold": has an unknown field "stpS"\. Fix: Did you mean "stepS"')

    def test_a_trial_may_live_in_a_file_the_source_names(self):
        """Catches a trial file that is not read, or is read from outside the design folder."""
        found, _ = campaign_for({"hold": {"file": "trials/hold.json"}}, {"trials/hold.json": json.dumps(hold_trial())})
        self.assertEqual(found["trials"]["hold"]["result"], "passed")
        with self.assertRaisesRegex(DesignError, "is outside the design folder"):
            campaign_for({"hold": {"file": "../hold.json"}})


class Limits(unittest.TestCase):
    def test_limits_on_measures_decide_with_the_outcome(self):
        """Catches a criterion that ignores its measure limits, or reports the wrong one as unmet."""
        run = {"outcome": "held", "measures": {"push": 9.3, "slideS": None}}
        self.assertEqual(record.judge(run, {"outcomes": ["held"], "limits": [{"measure": "push", "atMost": 10}]}), (True, None))
        self.assertEqual(record.judge(run, {"limits": [{"measure": "push", "atMost": 9}]}), (False, "push 9.3 is above 9"))
        self.assertEqual(record.judge(run, {"limits": [{"measure": "push", "atLeast": 9.5}]}), (False, "push 9.3 is below 9.5"))
        self.assertEqual(record.judge(run, {"limits": [{"measure": "slideS", "atMost": 1}]}), (False, "slideS has no value"))


class Fit(unittest.TestCase):
    def test_a_trace_becomes_one_path_operation_within_the_tolerance(self):
        """Catches a fitted path that strays from the recorded samples, or keeps more points than it needs."""
        rows = [[i / 100, 300 * math.cos(i / 200 * math.pi), 300 * math.sin(i / 200 * math.pi), 0.0] for i in range(201)]
        found = fit.path_operation({"columns": ["tS", "xMm", "zMm", "spinRadps"], "rows": rows}, {"normal": "y", "atMm": 82.5}, 5.0)
        operation = found["operation"]
        self.assertEqual((operation["kind"], operation["curve"], found["samples"]), ("path", "straight", 201))
        self.assertLess(found["points"], 20)
        self.assertLessEqual(found["maxDeviationMm"], 5.0)
        self.assertEqual(operation["throughMm"][0], [300.0, 82.5, 0.0])
        self.assertEqual(len(found["atS"]), found["points"])
        ops.check([operation], "fit")
        tight = fit.path_operation({"columns": [], "rows": rows}, {"normal": "y", "atMm": 0}, 0.5)
        self.assertGreater(tight["points"], found["points"])
        self.assertLessEqual(tight["maxDeviationMm"], 0.5)

    def test_a_piece_that_never_moves_has_no_path(self):
        """Catches a path operation with one point, which the motion vocabulary refuses."""
        still = fit.path_operation({"columns": [], "rows": [[0, 5, 5, 0], [1, 5, 5, 0]]}, {"normal": "y", "atMm": 0}, 1.0)
        self.assertIsNone(still["operation"])


class Command(unittest.TestCase):
    def test_try_states_the_cost_then_writes_the_record(self):
        """Catches the command running before it states the cost, or printing a verdict the record does not hold."""
        path = str(load_data(bench({"hold": hold_trial()})).path)
        text = io.StringIO()
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(text):
            code = main(["try", path, "--out", out])
            written = json.loads((Path(out) / "trials.json").read_text(encoding="utf-8"))
        lines = text.getvalue().splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(lines[0], "Campaign: 1 trial, 6 runs, up to 70000 steps.")
        self.assertEqual(lines[1], 'Trial "hold": passed. Nominal outcome "held"; control rejected; 2 of 2 inputs bracketed; half step agrees.')
        self.assertEqual(written["trials"]["hold"]["result"], "passed")
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            main(["try", path, "--estimate"])
        self.assertEqual(text.getvalue(), "Campaign: 1 trial, 6 runs, up to 70000 steps.\n")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()), tempfile.TemporaryDirectory() as out:
            self.assertEqual(main(["try", path, "--out", out, "--max-steps", "10"]), 1)
        self.assertIn("over the cap of 10", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
