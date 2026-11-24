"""The method around a trial: assumptions, sources, ranges, control, half-step repeat, cost, hand-off, custom code, record, command."""
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
from frc_design_kernel.motion import matrix as mx
from frc_design_kernel.motion import ops
from frc_design_kernel.trials import campaign, fit, record
from frc_design_kernel.trials.plan import Bracket

from .helpers import load_data
from .trial_cases import MEASURED, PANEL, bench, hold_trial, with_motor

WIND = "def force(signals, parameters):\n    return (parameters['pushN'], 0.0, 0.0)\n"
JUDGE = "import math\n\n\ndef judge(run, parameters):\n    return run['outcome'] == 'held' and math.isfinite(run['measures']['push'])\n"
CUSTOM = {"wind": {"kind": "force", "reason": "A steady side wind on the block; no listed load pushes with a fixed force.",
                   "limits": "A constant force only. It does not change with speed."},
          "held_firmly": {"kind": "criterion", "reason": "Held, and the peak push is a real number; the listed limits cannot test that.",
                          "limits": "It reads the run summary only."}}
GRIPPY = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.42, 0.8]}}}      # a range the block holds across


def campaign_for(trials, files=None, **design):
    path = load_data(bench(trials, **design), files).path
    return campaign.run_campaign(path), path


class Method(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record, cls.path = campaign_for({"hold": hold_trial()}, materials=GRIPPY)
        cls.trial = cls.record["trials"]["hold"]

    def test_a_complete_trial_that_holds_across_its_ranges_is_passed(self):
        """Catches a sound trial being reported as anything but passed, or its record losing a part of the method."""
        self.assertEqual((self.trial["result"], self.trial["findings"]), ("passed", []))
        self.assertEqual([r["id"] for r in self.trial["runs"]],
                         ["nominal", "half step", "control", "materials.panel.friction = 0.42", "materials.panel.friction = 0.8"])
        grip, = self.trial["ranges"]
        self.assertEqual((grip["source"], grip["range"], grip["held"], grip["flips"]), ("assumed", [0.42, 0.8], True, []))

    def test_an_outcome_that_changes_inside_an_assumed_range_is_located(self):
        """Catches "passes at the nominal value" hiding that a believable value fails: the range reaches below the slope's threshold."""
        found, _ = campaign_for({"hold": hold_trial()})       # friction assumed 0.2 to 0.8; the block needs tan(20 deg) = 0.364
        trial = found["trials"]["hold"]
        self.assertEqual(trial["result"], "not covered")       # no adjustment is declared that could recover it
        flip, = trial["ranges"][0]["flips"]
        self.assertTrue(flip["changesAt"] < math.tan(math.radians(20)) < flip["holdsAt"])
        self.assertLess(flip["holdsAt"] - flip["changesAt"], 0.6 / 2 ** 3 + 1e-9)      # closed in on by three halvings
        self.assertIn('the outcome changes inside the assumed range of "materials.panel.friction"', trial["findings"][0])
        self.assertEqual(trial["handForward"]["marginalEdges"], [{"input": "materials.panel.friction", **flip}])
        self.assertEqual(trial["handForward"]["passingRanges"]["materials.panel.friction"], [flip["holdsAt"], 0.8])

    def test_the_control_must_be_rejected(self):
        """Control: catches a campaign that would pass a trial whose control also meets the criterion."""
        self.assertEqual((self.trial["control"]["rejected"], self.trial["control"]["outcome"]), (True, "slid"))
        soft, _ = campaign_for({"hold": hold_trial(control={"change": {"materials.panel.friction": 0.45}, "note": "Slightly less grip still holds."})},
                               materials=GRIPPY)
        self.assertEqual(soft["trials"]["hold"]["result"], "control not rejected")

    def test_what_is_missing_makes_a_trial_incomplete_not_passed(self):
        """Catches a trial being called passed with no control, no stated assumptions, no stated sources or nothing bracketed."""
        def without(key):
            trial = hold_trial()
            del trial[key]
            return trial
        cases = {"no control": ({"hold": without("control")}, GRIPPY),
                 "does not state its own assumptions": ({"hold": without("assumes")}, GRIPPY),
                 "do not say whether they were measured or assumed: materials.panel.friction": ({"hold": hold_trial()}, {"panel": {**PANEL, "friction": 0.5}}),
                 "no input has an assumed range": ({"hold": hold_trial()}, {"panel": {**PANEL, "friction": MEASURED(0.5)}})}
        for finding, (trials, materials) in cases.items():
            found, _ = campaign_for(trials, materials=materials)
            trial = found["trials"]["hold"]
            self.assertEqual((trial["result"], trial["nominal"]["met"]), ("incomplete", True), finding)
            self.assertTrue(any(finding in text for text in trial["findings"]), finding)

    def test_a_failing_nominal_run_is_failed_with_the_reason(self):
        """Catches a failed trial hidden behind a complete method."""
        found, _ = campaign_for({"hold": hold_trial()}, materials={"panel": {**PANEL, "friction": {"value": 0.3, "assumed": [0.25, 0.35]}}})
        self.assertEqual((found["trials"]["hold"]["result"], found["trials"]["hold"]["firstUnmet"]), ("failed", 'outcome was "slid"'))

    def test_a_result_that_changes_at_half_the_step_is_not_converged(self):
        """Catches a step too coarse to trust: at the full step the piece jumps through a wall; at half the step it hits it."""
        trial = {"assumes": [{"text": "Nothing else is in the way."}], "plane": {"normal": "y", "atMm": 0}, "stepS": 2e-3, "durationS": 0.02, "gravityMps2": 0.0,
                 "piece": {"use": "shot", "start": {"atMm": [0, 0], "velocityMps": [10, 0]}},
                 "surfaces": [{"name": "wall", "material": "panel", "segmentsMm": [[31, -100], [31, 100]]}],
                 "events": [{"name": "through", "when": {"signal": "xMm", "above": 60}, "outcome": "went through the wall"}],
                 "pass": {"outcomes": ["went through the wall"]},
                 "control": {"change": {"piece.start.velocityMps": [-10, 0]}, "note": "Thrown the other way it cannot get through."}}
        found, _ = campaign_for({"jump": trial}, materials=GRIPPY)
        steps = found["trials"]["jump"]["stepComparison"]
        self.assertEqual((steps["coarseOutcome"], steps["fineOutcome"], steps["converged"]), ("went through the wall", "timeout", False))
        self.assertEqual(found["trials"]["jump"]["result"], "not converged")

    def test_the_same_campaign_gives_the_same_record(self):
        """Catches anything that makes two campaigns of one source differ, including sharing runs between workers."""
        self.assertEqual(campaign.run_campaign(self.path), self.record)
        self.assertEqual(campaign.run_campaign(self.path, workers=2), self.record)
        self.assertEqual(json.loads(json.dumps(self.record)), self.record)

    def test_the_record_says_what_ran_what_it_assumed_and_what_it_saw(self):
        """Catches a record a second engine could not pick up: no engine stamp, no assumptions, no sources, no section, no trace."""
        trial = self.trial
        self.assertEqual((self.record["schema"], trial["engine"]["name"], bool(trial["engine"]["version"])), ("frc-design-kernel/trial-campaign@2", "planar", True))
        self.assertEqual([row["id"] for row in trial["assumptions"]["stated"]], ["dry-surfaces"])
        self.assertEqual([row["id"] for row in trial["assumptions"]["engine"]][:4], ["in-plane", "single-piece", "round-piece", "rigid-surfaces"])
        sources = {row["path"]: row["source"] for row in trial["inputs"]}
        self.assertEqual(sources["materials.panel.friction"], "assumed")
        self.assertEqual(sources["pieces.block.massKg"], "measured")
        saw = trial["saw"]
        self.assertEqual((saw["plane"], saw["piece"]["sectionRadiusMm"], saw["sections"]),
                         ({"normal": "y", "atMm": 0}, 20, [{"solid": "wedge", "segments": 3, "arcs": 0, "drive": None}]))
        self.assertEqual(trial["nominal"]["trace"]["columns"][:4], ["tS", "xMm", "zMm", "spinRadps"])
        self.assertGreater(len(trial["nominal"]["trace"]["rows"]), 40)
        self.assertEqual(trial["handForward"]["nominal"]["materials.panel.friction"], 0.5)
        self.assertEqual(trial["handForward"]["control"], {"materials.panel.friction": 0.1})
        self.assertIn("in-plane", trial["handForward"]["assumptionIds"])


class CheapestPlan(unittest.TestCase):
    def feed(self, plan, passes):
        runs = []
        plan.nominal_met = True
        while plan.ask():
            for value in plan.ask():
                runs.append(value)
                plan.tell(value, passes(value), "x", {}, str(value))
        return runs

    def test_a_listed_bracket_stops_each_side_at_its_first_failure(self):
        """Catches runs spent past the first failure: values beyond a failing one are never run."""
        plan = Bracket("grip", 0.5, values=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
        runs = self.feed(plan, lambda value: 0.35 < value)
        self.assertEqual(runs, [0.4, 0.6, 0.3, 0.7])
        self.assertEqual(plan.summary()["flips"], [{"holdsAt": 0.4, "changesAt": 0.3}])

    def test_a_range_is_run_at_its_ends_and_only_refined_where_it_flips(self):
        """Catches a grid by another name: a range that holds costs two runs; a flip costs a few halvings on that side only."""
        calm = Bracket("grip", 0.5, low_high=[0.4, 0.8])
        self.assertEqual((calm.most_runs(), self.feed(calm, lambda value: True)), (8, [0.4, 0.8]))
        edge = Bracket("grip", 0.5, low_high=[0.2, 0.8], refine=3)
        runs = self.feed(edge, lambda value: value > 0.364)
        for got, want in zip(runs, [0.2, 0.8, 0.35, 0.425, 0.3875], strict=True):
            self.assertAlmostEqual(got, want)
        flip, = edge.summary()["flips"]
        self.assertAlmostEqual(flip["holdsAt"], 0.3875)
        self.assertEqual(flip["changesAt"], 0.35)

    def test_a_full_grid_is_only_run_when_asked_for(self):
        """Catches grid runs creeping into the default plan, and a failing corner going unreported when the grid is asked for."""
        both = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.42, 0.8]}, "restitution": {"value": 0.2, "assumed": [0.1, 0.4]}}}
        plain, _ = campaign_for({"hold": hold_trial()}, materials=both)
        self.assertEqual((len(plain["trials"]["hold"]["runs"]), plain["trials"]["hold"]["grid"]), (7, None))
        asked, _ = campaign_for({"hold": hold_trial(grid={"inputs": ["materials.panel.friction", "materials.panel.restitution"]})}, materials=both)
        grid = asked["trials"]["hold"]["grid"]
        self.assertEqual((len(grid["runs"]), grid["allMet"], len(asked["trials"]["hold"]["runs"])), (4, True, 11))


class Sensitivity(unittest.TestCase):
    def test_inputs_are_ranked_by_how_much_they_move_the_outcome(self):
        """Catches a ranking that would send someone to measure the wrong thing first."""
        rows = lambda *pairs: [{"value": v, "met": True, "outcome": "x", "measures": {"reach": reach}, "run": str(v)} for v, reach in pairs]
        ranked = record.sensitivity([
            {"input": "stiffness", "held": True, "values": rows((1, 99.0), (3, 101.0))},
            {"input": "friction", "held": False, "values": rows((0.2, 100.0), (0.8, 100.5))},
            {"input": "bounce", "held": True, "values": rows((0.1, 80.0), (0.4, 120.0))}], {"reach": 100.0})
        self.assertEqual([row["input"] for row in ranked], ["friction", "bounce", "stiffness"])
        self.assertAlmostEqual(ranked[1]["largestChange"]["relativeChange"], 0.4)
        self.assertEqual(ranked[1]["largestChange"]["measure"], "reach")


class Cost(unittest.TestCase):
    def test_the_cost_is_counted_before_anything_runs_and_can_be_capped(self):
        """Catches a campaign that starts without saying what it may cost, or ignores the caller's cap."""
        path = load_data(bench({"hold": hold_trial()}, materials=GRIPPY)).path
        told = []
        found = campaign.run_campaign(path, announce=told.append)
        self.assertEqual(told, [{"runs": 11, "steps": 120000, "aboutSeconds": 0.6, "trials": {"hold": {"runs": 11, "steps": 120000, "aboutSeconds": 0.6}}}])
        self.assertEqual((found["cost"]["runsAtMost"], found["cost"]["runs"]), (11, 5))
        self.assertLess(found["cost"]["stepsRun"], found["cost"]["stepsAtMost"])
        told.clear()
        with self.assertRaisesRegex(DesignError, "needs up to 120000 steps in up to 11 runs, over the cap of 50000"):
            campaign.run_campaign(path, max_steps=50000, announce=told.append)
        self.assertEqual(len(told), 1)      # the cost was still stated before the refusal


    def test_a_3d_trial_is_timed_at_the_3d_engines_pace(self):
        """Catches a 3D campaign announced at the planar engine's pace: a hundred times too quick, so nobody can plan on it."""
        design = load_data(bench({"hold": hold_trial(), "hold in 3D": {**hold_trial(), "engine": "mujoco"}}, materials=GRIPPY))
        cost = campaign.estimate(design)["trials"]
        self.assertEqual(cost["hold in 3D"]["steps"], cost["hold"]["steps"])
        self.assertAlmostEqual(cost["hold in 3D"]["aboutSeconds"], 100 * cost["hold"]["aboutSeconds"], delta=1.0)


class Changes(unittest.TestCase):
    def test_a_change_to_null_removes_a_thing_but_switches_off_a_bus(self):
        """Catches a control that sets busV to null (the power off) silently deleting the key, so the drive runs at 12 V."""
        case = {"commands": {"belt": {"mode": "speed", "setpointMps": 1.0, "busV": 12.0, "rampS": 0.1}}}
        out = campaign.changed(case, {"commands.belt.busV": None, "commands.belt.rampS": None}, "test")
        self.assertEqual(out["commands"]["belt"], {"mode": "speed", "setpointMps": 1.0, "busV": None})

    def test_a_hold_command_without_its_torque_angle_is_refused_by_name(self):
        """Catches a hold command missing fullTorqueAtRad reaching a worker and dying there with a KeyError."""
        from frc_design_kernel.trials import scene
        with self.assertRaisesRegex(DesignError, 'the command for the drive "arm" is in "hold" mode but has no fullTorqueAtRad'):
            scene.runtime_drive("arm", {"motor": "m", "radiusMm": 10, "statorLimitA": 10}, {"m": {}}, {"mode": "hold", "busV": 12}, "test")


class HandOff(unittest.TestCase):
    def test_one_trials_end_state_starts_the_next(self):
        """Catches a hand-off that restarts from the drawing: the second trial must begin where the first one came to rest."""
        second = hold_trial()
        second["piece"]["start"] = {"after": "hold"}
        found, _ = campaign_for({"then": second, "hold": hold_trial()}, materials=GRIPPY)
        self.assertEqual(list(found["trials"]), ["hold", "then"])
        end = found["trials"]["hold"]["nominal"]["end"]["piece"]
        first_row = found["trials"]["then"]["nominal"]["trace"]["rows"][0]
        self.assertAlmostEqual(first_row[1], end[0] * 1000, places=3)
        self.assertAlmostEqual(first_row[2], end[1] * 1000, places=3)


    def test_a_drive_can_start_at_the_speed_the_earlier_trial_left_it_at(self):
        """Catches a wheel that restarts from rest in every shot of a batch: its speed must carry when the trial asks."""
        motor = {"small": {"ktNmPerA": MEASURED(0.02), "ohm": MEASURED(0.1), "keVsPerRad": MEASURED(0.02)}}
        drive = {"wheel": {"motor": "small", "motorSolid": "motor", "gear": 2.0, "radiusMm": 25, "inertiaKgM2": MEASURED(2e-4), "statorLimitA": 40}}
        first = hold_trial(commands={"wheel": {"mode": "voltage", "busV": 12.0}})
        second = hold_trial(commands={"wheel": {"mode": "voltage", "busV": None}})      # power off: it keeps whatever speed it starts with
        second["piece"]["start"] = {"after": "first", "carryDrives": True}
        found, _ = campaign_for({"first": first, "second": second}, materials=GRIPPY, motors=motor, drives=drive, solids=with_motor())
        left_at = found["trials"]["first"]["nominal"]["end"]["drives"]["wheel"]
        self.assertGreater(left_at, 5.0)
        self.assertAlmostEqual(found["trials"]["second"]["nominal"]["end"]["drives"]["wheel"], left_at, places=9)
        second["piece"]["start"] = {"after": "first"}
        fresh, _ = campaign_for({"first": first, "second": second}, materials=GRIPPY, motors=motor, drives=drive, solids=with_motor())
        self.assertEqual(fresh["trials"]["second"]["nominal"]["end"]["drives"]["wheel"], 0.0)


class CustomCode(unittest.TestCase):
    FILES = {"custom/wind.py": WIND, "custom/held_firmly.py": JUDGE}

    def trial(self, push=0.5):
        return hold_trial(forces=[{"use": "wind", "parameters": {"pushN": push}}], **{"pass": {"outcomes": ["held"], "custom": {"use": "held_firmly"}}})

    def test_registered_custom_code_runs_inside_the_method_and_is_listed(self):
        """Catches custom code that escapes the record, or that the control and the half-step repeat no longer surround."""
        firm = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.46, 0.8]}}}      # the wind takes some of the margin
        found, _ = campaign_for({"hold": self.trial()}, self.FILES, custom=CUSTOM, materials=firm)
        trial = found["trials"]["hold"]
        self.assertEqual((trial["result"], trial["control"]["rejected"], [r["id"] for r in trial["runs"]][:3]), ("passed", True, ["nominal", "half step", "control"]))
        self.assertEqual([(row["name"], row["kind"], row["lines"], row["usedBy"]) for row in found["custom"]],
                         [("held_firmly", "criterion", 5, ["trial hold"]), ("wind", "force", 2, ["trial hold"])])
        blown, _ = campaign_for({"hold": self.trial(6.0)}, self.FILES, custom=CUSTOM, materials=GRIPPY)      # enough to push the block down the slope
        self.assertEqual(blown["trials"]["hold"]["result"], "failed")

    def test_custom_trial_code_is_checked_before_it_runs(self):
        """Catches custom trial code that reaches for files or the CAD kernel, is unregistered, or is the wrong kind."""
        with self.assertRaisesRegex(DesignError, 'custom "wind": its code imports "os", which a custom force may not do'):
            campaign_for({"hold": self.trial()}, {**self.FILES, "custom/wind.py": "import os\n" + WIND}, custom=CUSTOM)
        with self.assertRaisesRegex(DesignError, 'imports "OCP'):
            campaign_for({"hold": self.trial()}, {**self.FILES, "custom/wind.py": "from OCP.gp import gp_Pnt\n" + WIND}, custom=CUSTOM)
        with self.assertRaisesRegex(DesignError, 'names the custom force "wind", which does not exist'):
            campaign_for({"hold": self.trial()}, self.FILES, custom={"held_firmly": CUSTOM["held_firmly"]})
        with self.assertRaisesRegex(DesignError, 'uses "wind" as a custom force, but it is registered as another kind'):
            campaign_for({"hold": self.trial()}, self.FILES, custom={**CUSTOM, "wind": {**CUSTOM["wind"], "kind": "criterion"}})


class Checks(unittest.TestCase):
    def expect(self, change, pattern, **design):
        trial = hold_trial()
        change(trial)
        with self.assertRaisesRegex(DesignError, pattern):
            campaign_for({"hold": trial}, **design)

    def test_a_trial_that_names_something_missing_is_refused_before_it_runs(self):
        """Catches a misspelt solid, material, piece, signal, event, measure, path or engine failing late or silently."""
        self.expect(lambda t: t["surfaces"][0].update(solid="wege"), r'trials "hold" surface "slope": names the solid "wege"')
        self.expect(lambda t: t["surfaces"][0].update(material="panle"), 'names the material "panle"')
        self.expect(lambda t: t["piece"].update(use="blok"), 'names the piece "blok"')
        self.expect(lambda t: t["events"][0]["when"].update(signal="xmm"), r'trials "hold" event "slid": names the signal "xmm"')
        self.expect(lambda t: t["measures"].update(late={"timeOf": "sld"}), 'measure "late": names "sld"')
        self.expect(lambda t: t["pass"].update(limits=[{"measure": "psh", "atMost": 1}]), 'names the measure "psh"')
        self.expect(lambda t: t["control"]["change"].update({"materials.pannel.friction": 1}), 'the path "materials.pannel.friction" does not lead anywhere at "pannel"')
        self.expect(lambda t: t.update(plane={"normal": "y", "atMm": 900}), "the plane y = 900 mm does not cut the solid")
        self.expect(lambda t: t.update(stpS=1), r'trials "hold": has an unknown field "stpS"\. Fix: Did you mean "stepS"')
        self.expect(lambda t: t.update(engine="rigid3d"), r'trials "hold".engine: must be one of "planar"')

    def test_a_source_must_state_one_source_and_a_range_that_holds_its_value(self):
        """Catches an input marked both measured and assumed, or an assumed range that does not contain the value used."""
        self.expect(lambda t: None, 'materials.panel.friction: needs exactly one of "measured" or "assumed"',
                    materials={"panel": {**PANEL, "friction": {"value": 0.5, "measured": "sheet 2", "assumed": [0.2, 0.8]}}})
        self.expect(lambda t: None, r"materials.panel.friction: its value 0.5 is outside its assumed range \[0.6, 0.8\]",
                    materials={"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.6, 0.8]}}})

    def test_a_trial_may_live_in_a_file_the_source_names(self):
        """Catches a trial file that is not read, or is read from outside the design folder."""
        found, _ = campaign_for({"hold": {"file": "trials/hold.json"}}, {"trials/hold.json": json.dumps(hold_trial())}, materials=GRIPPY)
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
        ops.check([operation], "fit")
        tight = fit.path_operation({"columns": [], "rows": rows}, {"normal": "y", "atMm": 0}, 0.5)
        self.assertGreater(tight["points"], found["points"])
        self.assertIsNone(fit.path_operation({"columns": [], "rows": [[0, 5, 5, 0], [1, 5, 5, 0]]}, {"normal": "y", "atMm": 0}, 1.0)["operation"])
        self.assertNotIn("turnDeg", tight["operation"])

    ROLL = 50.0     # a point on the piece this far from its centre, to see its turn as a distance

    def rolling(self, samples=201):
        """A piece that runs a quarter circle of 300 mm counter-clockwise in (x, z) while it turns, faster and faster, through 120 degrees."""
        rows = []
        for i in range(samples):
            s = i / (samples - 1)
            spin = math.radians(240) * s     # rad/s over one second: the angle is 120 s^2 degrees
            rows.append([s, 300 * math.cos(s * math.pi / 2), 300 * math.sin(s * math.pi / 2), spin])
        return {"columns": ["tS", "xMm", "zMm", "spinRadps", "speedMps"], "rows": [row + [0.0] for row in rows]}

    def worst_miss(self, operation, trace, plane):
        """How far, at most, a trace sample's true placement is from the nearest placement the operation passes through:
        the largest distance between the two of the piece's centre and of two points ROLL mm from it. Taken from
        placements only, not from what the fit reports."""
        def where(row):
            at = [row[1], row[2]]
            at.insert("xyz".index(plane["normal"]), plane["atMm"])
            return at
        start = where(trace["rows"][0])
        seen = [start, *[mx.add(start, [self.ROLL if i == k else 0.0 for i in range(3)]) for k in (0, 2)]]
        angle, previous, truth = 0.0, trace["rows"][0], []
        for row in trace["rows"]:
            angle += math.degrees((row[3] + previous[3]) / 2 * (row[0] - previous[0]))
            placed = mx.chain([mx.rotation(start, (0, -1, 0), angle), mx.translation(mx.sub(where(row), start))])
            truth.append([mx.apply(placed, p) for p in seen])
            previous = row
        path = [[mx.apply(ops.at([operation], n / 2000), p) for p in seen] for n in range(2001)]
        return max(min(max(math.dist(a, b) for a, b in zip(true, there)) for there in path) for true in truth)

    def test_a_turning_trace_becomes_one_turning_path_within_both_tolerances(self):
        """Catches a fit that drops the piece's turn, writes it about the wrong axis or in the wrong sense, or strays
        from a sample by more than its tolerances. The check rebuilds every sample's placement from the trace itself."""
        plane, trace = {"normal": "y", "atMm": 82.5}, self.rolling()
        found = fit.path_operation(trace, plane, 2.0, 2.0)
        operation = found["operation"]
        ops.check([operation], "fit")
        self.assertEqual(operation["turnAxis"], [0, -1, 0])
        self.assertEqual(len(operation["turnDeg"]), len(operation["throughMm"]))
        self.assertEqual(len(found["atS"]), len(operation["throughMm"]))
        self.assertEqual(operation["turnDeg"][0], 0.0)
        self.assertAlmostEqual(operation["turnDeg"][-1], 120.0, delta=0.01)
        self.assertLessEqual(found["maxTurnDeviationDeg"], 2.0)
        self.assertEqual(found["turnToleranceDeg"], 2.0)
        allowed = 2.0 + math.radians(2.0) * self.ROLL
        self.assertLessEqual(self.worst_miss(operation, trace, plane), allowed + 0.5)
        sliding = {k: v for k, v in operation.items() if not k.startswith("turn")}
        self.assertGreater(self.worst_miss(sliding, trace, plane), 10 * allowed, "control: the check sees a fit that leaves the turn out")

    def test_the_turn_keeps_points_where_the_place_alone_would_not(self):
        """Catches a fit that only looks at position: a piece sliding straight while it spins up needs points along a
        straight line to follow its turn. Control: with a turn tolerance too wide to matter, two points suffice."""
        rows = [[i / 100, 3 * i, 0.0, math.radians(180) * i / 100, 0.0] for i in range(101)]
        trace = {"columns": ["tS", "xMm", "zMm", "spinRadps", "speedMps"], "rows": rows}
        turned = fit.path_operation(trace, {"normal": "z", "atMm": 0}, 1.0, 1.0)
        self.assertGreater(turned["points"], 2)
        self.assertLessEqual(turned["maxTurnDeviationDeg"], 1.0)
        self.assertEqual(turned["operation"]["turnAxis"], [0, 0, 1])
        self.assertAlmostEqual(turned["operation"]["turnDeg"][-1], 90.0, delta=0.01)
        self.assertEqual(fit.path_operation(trace, {"normal": "z", "atMm": 0}, 1.0, 1000.0)["points"], 2)

    def test_a_turn_in_place_is_reported_not_hidden(self):
        """Catches a fit that claims to follow a turn it cannot express: a path is followed by length, so a piece that
        stops and spins on the spot is reported as missed by that much."""
        rows = [[i / 10, min(i, 5) * 10.0, 0.0, 0.0 if i <= 5 else math.radians(100), 0.0] for i in range(11)]
        found = fit.path_operation({"columns": ["tS", "xMm", "zMm", "spinRadps", "speedMps"], "rows": rows}, {"normal": "x", "atMm": 0}, 1.0, 1.0)
        self.assertEqual(found["operation"]["turnAxis"], [1, 0, 0])
        self.assertGreater(found["maxTurnDeviationDeg"], 40.0)
        still = fit.path_operation({"columns": ["tS", "xMm", "zMm", "spinRadps"], "rows": [[i / 10, 5.0, 5.0, 1.0] for i in range(11)]}, {"normal": "y", "atMm": 0}, 1.0)
        self.assertIsNone(still["operation"])
        self.assertAlmostEqual(still["maxTurnDeviationDeg"], math.degrees(1.0), places=6)


class Command(unittest.TestCase):
    def test_try_states_the_cost_then_reports_and_writes_the_record(self):
        """Catches the command running before it states the cost, not saying the time spent, or printing what the record does not hold."""
        path = str(load_data(bench({"hold": hold_trial()}, materials=GRIPPY)).path)
        text = io.StringIO()
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(text):
            code = main(["try", path, "--out", out])
            written = json.loads((Path(out) / "trials.json").read_text(encoding="utf-8"))
        lines = text.getvalue().splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(lines[0], "Campaign: 1 trial, at most 11 runs and 120000 steps, about 0.6 s.")
        self.assertEqual(lines[1], 'Trial "hold": passed. Nominal outcome "held"; control rejected; 1 of 1 input held across its range; half step agrees; '
                                   "most sensitive to materials.panel.friction.")
        self.assertRegex(lines[2], r"^Ran 5 runs and \d+ steps in \d+\.\d s\. Wrote trials.json to ")
        self.assertEqual(written["trials"]["hold"]["result"], "passed")
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            main(["try", path, "--estimate"])
        self.assertEqual(text.getvalue(), "Campaign: 1 trial, at most 11 runs and 120000 steps, about 0.6 s.\n")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()), tempfile.TemporaryDirectory() as out:
            self.assertEqual(main(["try", path, "--out", out, "--max-steps", "10"]), 1)
        self.assertIn("over the cap of 10", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
