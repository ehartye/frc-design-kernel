"""Measuring one named thing: the pairs with named solids, one motion, one adjustment at both ends, one trial.

The caller chooses. What was asked is measured every time it is asked, and nothing else is.
"""
import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.cli import main
from frc_design_kernel.measure import clearance, extremes, records, run
from frc_design_kernel.trials import engines

from .helpers import job_files, load_data, recorded
from .test_records import JOBS, move_loose, raw, source, watched
from .test_screen import TAPER, design as rig
from .trial_cases import PANEL, bench, hold_trial

SOLIDS = 8              # five robot solids and three fixtures in the stack
EVERY_PAIR = math.comb(SOLIDS, 2)
LIFT = JOBS[1]
GRIPPY = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.42, 0.8]}}}


def command(*args):
    text, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(text), contextlib.redirect_stderr(errors):
        try:
            code = main([str(a) for a in args])
        except SystemExit as stopped:
            code = stopped.code
    return code, text.getvalue().splitlines(), errors.getvalue()


class NamedSolids(unittest.TestCase):
    def test_only_pairs_with_a_named_solid_are_measured_each_time_it_is_asked(self):
        """Catches a measurement of one solid's pairs that measures the rest, or skips what it measured a moment ago."""
        with run.Bench(source(move_loose), 1) as bench_:
            full, = records.answers(bench_, [LIFT])
            for _ in range(2):
                with watched() as seen:
                    found, = records.answers(bench_, [LIFT], focus=["loose"])
                self.assertTrue(seen["names"] and all("loose" in pair for pair in seen["names"]), seen["names"])
                held = found["record"]
                self.assertEqual((held["focus"], held["counts"]["pairs"], held["counts"]["notInFocus"]),
                                 (["loose"], EVERY_PAIR, EVERY_PAIR - (SOLIDS - 1)))
                self.assertEqual(held["result"]["pairs"], [row for row in full["record"]["result"]["pairs"] if "loose" in row["pair"]])
                self.assertEqual(held["result"]["closer"], [["bracket", "loose"]])
        self.assertNotIn("focus", full["record"])

    def test_at_a_pose_every_pair_is_counted_once(self):
        """Catches a limited pose measurement that measures other pairs, or counts that no longer add up to every pair."""
        assembly = kernel.build(source(move_loose))
        whole = clearance.at_pose(assembly, "home", 3.0)
        found = clearance.at_pose(assembly, "home", 3.0, focus=["post"])
        self.assertEqual(found["pairs"], [row for row in whole["pairs"] if "post" in row["pair"]])
        counts = found["counts"]
        self.assertEqual(counts["notInFocus"], EVERY_PAIR - (SOLIDS - 1))
        self.assertEqual(counts["pairs"], sum(n for key, n in counts.items() if key != "pairs"))
        self.assertEqual((found["focus"], whole["counts"]["notInFocus"]), (["post"], 0))
        self.assertNotIn("focus", whole)

    def test_it_is_returned_and_never_written_over_a_full_record(self):
        """Catches a passing look at one solid's pairs replacing the failing record of the whole motion."""
        design = source(move_loose)
        with tempfile.TemporaryDirectory() as out:
            recorded(design, JOBS, out)
            before = raw(out)
            self.assertIn(["bracket", "loose"], job_files(out)["clearance.motion.lift-off"]["result"]["closer"])
            code, lines, errors = command("measure", design.path, "--motion", "lift off", "--focus", "plate", "--min-gap", "3", "--workers", "1")
            self.assertEqual((code, errors), (0, ""))
            self.assertIn("clearance.motion.lift-off, pairs with plate: 7 of 28 pairs measured; 0 pairs closer than the gap; 0 pairs not settled.", lines)
            self.assertEqual(lines[-1], "Nothing was written: a measurement of named solids never replaces a full one.")
            self.assertEqual(raw(out), before)

    def test_only_a_clearance_can_be_limited_and_the_solid_must_be_real(self):
        """Catches an attachment or a mass answered as if it had been limited, or a solid that is not there accepted."""
        with run.Bench(source(), 1) as bench_:
            with self.assertRaisesRegex(DesignError, "only a clearance can be limited to named solids, not attachment"):
                records.answers(bench_, [JOBS[7]], focus=["loose"])
            with self.assertRaisesRegex(DesignError, 'there is no solid named "lose"'):
                records.answers(bench_, [LIFT], focus=["lose"])
        code, _, errors = command("measure", source().path, "--focus", "plate", "--out", "somewhere")
        self.assertEqual(code, 2)
        self.assertIn("--focus writes nothing, so it takes no --out", errors)


class OneMotion(unittest.TestCase):
    def test_one_motion_measures_and_writes_that_motion_alone(self):
        """Catches asking for one motion sweeping another, or weighing the robot."""
        design = source()
        with tempfile.TemporaryDirectory() as out:
            with watched() as seen:
                code, _, _ = command("measure", design.path, "--out", out, "--motion", "press", "--min-gap", "3", "--workers", "1")
            self.assertEqual((code, sorted(job_files(out))), (0, ["clearance.motion.press"]))
        self.assertTrue(seen["names"] and all("ball" in pair for pair in seen["names"]), seen["names"])
        self.assertEqual((seen["attachment"], seen["mass"]), (0, 0))


class OneAdjustment(unittest.TestCase):
    def two(self):
        """The screen rig with a second mechanical adjustment and a setpoint."""
        data = rig()
        data["parameters"].update(post_x=200, belt_mps=2.0)
        data["solids"][5]["shape"]["fromMm"][0] = "=post_x"
        data["solids"][5]["shape"]["toMm"][0] = "=post_x + 5"
        data["adjustments"]["net place"] = {"input": "parameters.post_x", "kind": "mechanical", "range": [190, 210]}
        data["adjustments"]["belt speed"] = {"input": "parameters.belt_mps", "kind": "setpoint", "range": [1.0, 3.0]}
        return load_data(data, {"custom/taper.py": TAPER})

    def test_an_end_is_measured_in_full(self):
        """Catches an end measured only for the pairs somebody worked out it moved: pairs of two unmoved solids are measured too."""
        design = self.two()
        real, shares = clearance.share_of, []

        def keeping(*args, **kw):
            shares.append(real(*args, **kw))
            return shares[-1]

        with run.Bench(design, 1) as bench_, mock.patch.object(clearance, "share_of", keeping):
            found = extremes.at_extremes(bench_, min_gap=20.0, adjustments=["net place"])
        self.assertEqual(len(shares), 2 * len(design.data["motions"]))
        for share in shares:
            self.assertEqual(share["counts"]["notInFocus"], 0)
        for setting in found["net place"]["settings"]:
            self.assertIn(["drawn ball", "pad"], setting["motions"]["press"]["closer"])           # neither is the net
            self.assertIn(["drawn ball", "wall left"], setting["poses"][0]["closer"])
            self.assertEqual(sorted(setting), ["motions", "poses", "setting"])

    def test_one_adjustment_can_be_named_and_only_a_mechanical_one_has_ends(self):
        """Catches naming one adjustment building the ends of another, or a setpoint measured as if it moved solids."""
        with run.Bench(self.two(), 1) as bench_:
            self.assertEqual(list(extremes.at_extremes(bench_, 2.0, adjustments=["net place"])), ["net place"])
            self.assertEqual(list(extremes.at_extremes(bench_, 2.0)), ["channel gap", "net place"])
            with self.assertRaisesRegex(DesignError, 'the adjustment "belt speed" is a setpoint, which moves no solid'):
                extremes.at_extremes(bench_, 2.0, adjustments=["belt speed"])
            with self.assertRaisesRegex(DesignError, 'there is no adjustment named "net plce"'):
                extremes.at_extremes(bench_, 2.0, adjustments=["net plce"])

    def test_each_piece_is_reported_as_it_finishes_and_the_caller_can_stop(self):
        """Catches a caller that must wait for every motion at every end before it sees the first one that fails."""
        seen = []

        def stop(row):
            seen.append((row["adjustment"], row["setting"], row["motion"], bool(row["found"]["closer"])))
            if row["found"]["closer"]:
                raise InterruptedError

        with run.Bench(self.two(), 1) as bench_, self.assertRaises(InterruptedError):
            extremes.at_extremes(bench_, min_gap=20.0, report=stop)
        self.assertEqual(seen, [("channel gap", 1, "swing in plane", True)])

    def test_the_command_measures_one_adjustment_and_keeps_the_others(self):
        """Catches a rerun of one adjustment throwing the others away, or measuring the motions as drawn as well."""
        design = self.two()
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(command("measure", design.path, "--out", out, "--extremes", "--min-gap", "2", "--workers", "1")[0], 0)
            measured = raw(out)
            path = Path(out) / "adjustments.json"
            lying = json.loads(path.read_text(encoding="utf-8"))
            whole = json.loads(json.dumps(lying))
            for entry in lying["adjustments"].values():
                entry["settings"] = []
            path.write_text(json.dumps(lying), encoding="utf-8")
            code, lines, _ = command("measure", design.path, "--out", out, "--adjustment", "net place", "--min-gap", "2", "--workers", "1")
            found = json.loads(path.read_text(encoding="utf-8"))["adjustments"]
            self.assertEqual(raw(out), measured)
        self.assertEqual((code, found["net place"], found["channel gap"]["settings"]), (0, whole["adjustments"]["net place"], []))
        self.assertTrue(lines[0].startswith('Adjustment "net place" at 190: '), lines)

    def test_part_of_the_motions_is_printed_and_not_written(self):
        """Catches the ends of one motion written as if every motion had been measured there."""
        design = self.two()
        with tempfile.TemporaryDirectory() as out:
            code, lines, _ = command("measure", design.path, "--out", out, "--adjustment", "net place", "--motion", "press", "--workers", "1")
            self.assertEqual((code, (Path(out) / "adjustments.json").exists()), (0, False))
        self.assertIn("Not written: only part of the motions and poses was measured at the ends.", lines)


class OneTrial(unittest.TestCase):
    def test_a_trial_that_starts_after_another_runs_it_too_and_never_starts_from_a_saved_result(self):
        """Catches a chained trial started from an end state in a file, which nobody knows is still where the first one ends."""
        second = hold_trial()
        second["piece"]["start"] = {"after": "hold"}
        design = load_data(bench({"then": second, "hold": hold_trial(), "apart": hold_trial()}, materials=GRIPPY))
        real, runs = engines.run, []

        def counting(scene, step=None, forces=(), **kw):
            runs.append(step)
            return real(scene, step, forces, **kw)

        with tempfile.TemporaryDirectory() as out, mock.patch.object(engines, "run", counting):
            self.assertEqual(command("try", design.path, "--out", out)[0], 0)
            path = Path(out) / "trials.json"
            first, whole = len(runs), json.loads(path.read_text(encoding="utf-8"))
            lying = json.loads(json.dumps(whole))
            lying["trials"]["hold"]["nominal"]["end"]["piece"][0] += 0.2
            lying["trials"]["apart"]["result"] = "left alone"
            path.write_text(json.dumps(lying), encoding="utf-8")
            counts = []
            for _ in range(2):
                runs.clear()
                self.assertEqual(command("try", design.path, "--out", out, "--trial", "then")[0], 0)
                counts.append(len(runs))
            again = json.loads(path.read_text(encoding="utf-8"))["trials"]
        self.assertEqual(counts, [2 * first // 3, 2 * first // 3])         # the named trial and the one it starts after, every time
        self.assertEqual((again["then"], again["hold"]), (whole["trials"]["then"], whole["trials"]["hold"]))
        self.assertEqual(again["apart"]["result"], "left alone")
        self.assertNotIn("used", again["then"])

    def test_a_record_of_trials_is_the_same_for_a_source_whose_notes_differ(self):
        """Catches a trial record that keeps a hash of the source, so an edited note writes other bytes for the same figures."""
        from frc_design_kernel.trials import campaign
        noted = bench({"hold": hold_trial()}, materials=GRIPPY)
        noted["solids"][0]["note"] = "A remark."
        plain = campaign.run_campaign(load_data(bench({"hold": hold_trial()}, materials=GRIPPY)))
        self.assertEqual(json.dumps(campaign.run_campaign(load_data(noted))), json.dumps(plain))


if __name__ == "__main__":
    unittest.main()
