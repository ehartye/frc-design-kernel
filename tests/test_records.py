"""Every measurement is a job with its own file, written as the job finishes, and carried while it is current.

The design is the small stack of test_measure, with one job of every kind. Each test compares files on disk, so a
job carried when it should have been measured, or a file written with the wrong content, shows up as a difference.
"""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frc_design_kernel import DesignError
from frc_design_kernel.cli import main
from frc_design_kernel.measure import approach, attachment, clearance, compression, mass, records, run

from .helpers import load_data
from .test_measure import STACK

GONE = ["ball", "lamp", "loose", "plate", "shelf", "stand"]       # every solid but the bracket and the post
JOBS = [
    {"kind": "clearance", "motion": "press", "minGapMm": 3.0},
    {"kind": "clearance", "motion": "lift off", "minGapMm": 3.0},
    {"kind": "clearance", "motion": "lift off", "minGapMm": 3.0, "contacts": [], "absent": GONE, "displace": {"post": [0, 0, 95]}},
    {"kind": "clearance", "pose": "home", "minGapMm": 3.0},
    {"kind": "reach", "motion": "press", "pair": ["ball", "bracket"], "withinMm": 1.0, "window": [0.5, 1.0]},
    {"kind": "indentation", "motion": "press", "piece": "ball", "contact": "bracket", "maxDepthMm": 4.0},
    {"kind": "withdrawal", "motion": "lift off"},
    {"kind": "attachment", "pose": "home", "touchGapMm": 1.0, "ignore": ["ball"]},
    {"kind": "mass", "pose": "lifted"},
]
IDS = ["clearance.motion.press", "clearance.motion.lift-off", "clearance.motion.lift-off.displaced.post", "clearance.pose.home",
       "reach.press.ball.bracket", "indentation.press.ball.bracket", "withdrawal.lift-off", "attachment.pose.home", "mass.pose.lifted"]
LOOSE_NEAR = {"kind": "box", "fromMm": [62, 40, 150], "toMm": [72, 50, 160]}     # 2 mm from the bracket's lift path


def source(change=None):
    data = copy.deepcopy(STACK)
    if change:
        change(data)
    return load_data(data).path


def move_loose(data):
    next(s for s in data["solids"] if s["name"] == "loose")["shape"] = LOOSE_NEAR


def files(folder):
    """{job id: the job file as data} for every job file in a folder."""
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted((Path(folder) / records.FOLDER).glob("*.json"))}


def raw(folder):
    return {path.name: path.read_bytes() for path in sorted((Path(folder) / records.FOLDER).iterdir())}


def results(folder):
    """Each job file without what says how it was made (checked, generator): what must equal a fresh measurement."""
    return {name: {k: v for k, v in found.items() if k not in ("checked", "generator")} for name, found in files(folder).items()}


@contextlib.contextmanager
def watched():
    """Count what is really measured, by kind of question."""
    seen = {"pairs": 0, "poseGaps": 0, "reach": 0, "indentation": 0, "withdrawn": 0, "attachment": 0, "mass": 0}
    real = {"pairs": (clearance, "measure_pair"), "poseGaps": (clearance, "gap_and_overlap"), "reach": (approach, "reach"),
            "indentation": (compression, "indentation"), "withdrawn": (approach, "withdrawn"), "attachment": (attachment, "at_pose"),
            "mass": (mass, "roll_up")}

    def counting(key, function):
        def call(*args, **kw):
            seen[key] += 1
            return function(*args, **kw)
        return call

    run._built.clear()
    run._fixed.clear()
    with contextlib.ExitStack() as stack:
        for key, (module, name) in real.items():
            stack.enter_context(mock.patch.object(module, name, counting(key, getattr(module, name))))
        yield seen


def recorded(path, folder, jobs=JOBS, **options):
    return records.record(path, jobs, folder, workers=1, **options)


class EveryKind(unittest.TestCase):
    def test_each_kind_is_recorded_with_its_rules_and_then_carried_untouched(self):
        """Catches a kind of job with no file, no rules or no used block, or a current job measured again or rewritten."""
        path = source()
        with tempfile.TemporaryDirectory() as out:
            first = recorded(path, out)
            self.assertEqual([entry["id"] for entry in first], IDS)
            self.assertEqual({entry["action"] for entry in first}, {"measured"})
            found = files(out)
            self.assertEqual(sorted(found), sorted(IDS))
            for name, job in zip(IDS, JOBS):
                held = found[name]
                self.assertEqual((held["schema"], held["id"], held["job"]["kind"]), (records.SCHEMA, name, job["kind"]))
                self.assertIsInstance(held["inputs"]["rules"], dict, name)
                self.assertIsInstance(held["inputs"]["solids"], dict, name)
                self.assertIn("used", held, name)
                self.assertIn("checked", held, name)
            self.assertEqual(found["indentation.press.ball.bracket"]["inputs"]["rules"]["maxDepthMm"], 4.0)
            self.assertEqual(sorted(found["reach.press.ball.bracket"]["inputs"]["solids"]), ["ball", "bracket"])
            self.assertIn(["bracket", "post"], found["clearance.motion.lift-off.displaced.post"]["result"]["closer"])
            before = raw(out)
            with watched() as seen:
                again = recorded(path, out)
            self.assertEqual({entry["action"] for entry in again}, {"carried"})
            self.assertEqual(set(seen.values()), {0})
            self.assertEqual(raw(out), before)

    def test_a_squeeze_limit_change_measures_only_the_squeeze_job(self):
        """Catches a rule of one job making every job stale, or the changed rule not measuring that job again."""
        path = source()
        with tempfile.TemporaryDirectory() as out:
            recorded(path, out)
            before = raw(out)
            tighter = [dict(job, maxDepthMm=3.5) if job["kind"] == "indentation" else job for job in JOBS]
            with watched() as seen:
                entries = recorded(path, out, tighter)
            after = raw(out)
            held = files(out)["indentation.press.ball.bracket"]
        self.assertEqual([e["id"] for e in entries if e["action"] == "measured"], ["indentation.press.ball.bracket"])
        self.assertEqual({key: n for key, n in seen.items() if n}, {"indentation": 1})
        self.assertEqual({name for name in after if after[name] != before[name]}, {"indentation.press.ball.bracket.json"})
        self.assertEqual((held["inputs"]["rules"]["maxDepthMm"], held["job"]["maxDepthMm"]), (3.5, 3.5))

    def test_a_moved_solid_measures_only_the_jobs_that_use_it(self):
        """Catches a job whose solids did not change measured again, or one whose solid moved carried."""
        with tempfile.TemporaryDirectory() as out:
            recorded(source(), out)
            entries = recorded(source(move_loose), out)
        measured = sorted(e["id"] for e in entries if e["action"] == "measured")
        self.assertEqual(measured, ["attachment.pose.home", "clearance.motion.lift-off", "clearance.motion.press", "clearance.pose.home",
                                    "withdrawal.lift-off"])     # the loose block weighs nothing, is not in the reach or squeeze, and is absent from the control


class StoredRows(unittest.TestCase):
    def test_no_file_holds_a_row_for_a_far_apart_pair(self):
        """Catches the records keeping a row for every pair that was measured: the bulk the receipts carried."""
        with tempfile.TemporaryDirectory() as out:
            recorded(source(), out)
            found = files(out)
        stored = measured = 0
        for name in IDS:
            if not name.startswith("clearance."):
                continue
            held = found[name]
            near = held["inputs"]["rules"].get("nearMm", 0.0)
            gap = held["result"]["minGapMm"]
            for row in held["result"]["pairs"]:
                self.assertTrue(row["closerThanMinGap"] or not row["proven"] or row["lowerBoundMm"] < gap + near, (name, row))
            stored += len(held["result"]["pairs"])
            measured += held["counts"]["measured"]
        self.assertGreater(measured, stored)        # some pairs were measured and passed, and are counted, not stored

    def test_control_a_wider_near_band_keeps_the_passing_rows(self):
        """Control: shows passing rows do reach a file when the caller asks for them, so the check above can fail."""
        wide = [dict(JOBS[1], nearMm=1000.0)]
        with tempfile.TemporaryDirectory() as out:
            recorded(source(), out, wide)
            held = files(out)["clearance.motion.lift-off"]
        passing = [row for row in held["result"]["pairs"] if not row["closerThanMinGap"]]
        self.assertTrue(passing)
        self.assertEqual(held["result"]["closest"]["pair"], min(held["result"]["pairs"], key=lambda r: r["gapMm"] or 0)["pair"])


class Stopped(unittest.TestCase):
    def run_measure(self, *args):
        text = io.StringIO()
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(io.StringIO()):
            code = main(["measure", *map(str, args), "--min-gap", "3", "--touch-gap", "1", "--workers", "1"])
        return code, text.getvalue().splitlines()

    def test_a_stopped_run_keeps_the_jobs_it_finished_and_the_next_carry_measures_the_rest(self):
        """Catches a stopped run losing finished work, leaving a half-written file, or a carry that measures it all again."""
        path, stop_after = source(), 4
        real, written = records.write_record, []

        def stopping(target, record):
            if len(written) == stop_after:
                raise RuntimeError("stopped")
            written.append(target)
            real(target, record)

        with tempfile.TemporaryDirectory() as out:
            with mock.patch.object(records, "write_record", stopping), self.assertRaisesRegex(RuntimeError, "stopped"):
                self.run_measure(path, "--out", out)
            kept = raw(out)
            self.assertEqual(len(kept), stop_after)                 # nothing else: no partial or temporary file
            self.assertTrue(all(json.loads(text) for text in kept.values()))
            with watched() as seen:
                code, lines = self.run_measure(path, "--out", out, "--carry")
            total = len(files(out))
        self.assertEqual(code, 0)
        self.assertEqual(total, 11)          # two motions; clearance, attachment and mass as drawn and at two poses
        self.assertIn(f"Wrote {total - stop_after} job records to {Path(out) / records.FOLDER}; carried {stop_after} that were current.", lines)
        self.assertEqual((seen["attachment"], seen["mass"]), (2, 3))     # the attachment as drawn was among the four kept

    def test_measuring_fresh_equals_carrying_after_a_one_solid_move(self):
        """Catches carried results that differ from a fresh measurement of the design as it is now, job by job."""
        moved = source(move_loose)
        with tempfile.TemporaryDirectory() as carried, tempfile.TemporaryDirectory() as fresh:
            recorded(source(), carried)
            recorded(moved, carried)
            recorded(moved, fresh, carry=False)
            self.assertEqual(results(carried), results(fresh))
            self.assertIn(["bracket", "loose"], files(fresh)["clearance.motion.lift-off"]["result"]["closer"])

    def test_control_a_record_that_lies_about_a_moved_solid_gives_a_different_answer(self):
        """Control: shows the comparison with a fresh measurement does catch a pair carried when it had changed."""
        moved = source(move_loose)
        with tempfile.TemporaryDirectory() as carried, tempfile.TemporaryDirectory() as fresh:
            recorded(source(), carried)
            recorded(moved, fresh, carry=False)
            target = Path(carried) / records.FOLDER / "clearance.motion.lift-off.json"
            lying = json.loads(target.read_text(encoding="utf-8"))
            lying["inputs"]["solids"]["loose"] = files(fresh)["clearance.motion.lift-off"]["inputs"]["solids"]["loose"]
            target.write_text(json.dumps(lying), encoding="utf-8")
            recorded(moved, carried)
            self.assertNotEqual(results(carried)["clearance.motion.lift-off"], results(fresh)["clearance.motion.lift-off"])


class Requests(unittest.TestCase):
    def test_workers_give_the_same_files(self):
        """Catches files that change with the worker count, or a job written before all its shares came back."""
        path = source()
        old = run.PAIRS_PER_SHARE
        with tempfile.TemporaryDirectory() as alone, tempfile.TemporaryDirectory() as shared:
            recorded(path, alone)
            try:
                run.PAIRS_PER_SHARE = 1
                records.record(path, JOBS, shared, workers=2)
            finally:
                run.PAIRS_PER_SHARE = old
            self.assertEqual(results(alone), results(shared))

    def test_ids_are_named_or_given_and_never_shared(self):
        """Catches two jobs writing one file, a given id ignored, or a job that names nothing real accepted."""
        path = source()
        twice = [JOBS[0], dict(JOBS[0], minGapMm=1.0)]
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaisesRegex(DesignError, r'jobs 1 and 2 have the same id "clearance.motion.press"'):
                recorded(path, out, twice)
            entries = recorded(path, out, [twice[0], dict(twice[1], id="press-tight")])
            self.assertEqual([e["id"] for e in entries], ["clearance.motion.press", "press-tight"])
            for bad, message in (({"kind": "sideways", "motion": "press"}, 'job 1: there is no job kind "sideways"'),
                                 ({"kind": "clearance", "motion": "pres"}, 'job 1: there is no motion named "pres"'),
                                 ({"kind": "indentation", "motion": "press", "piece": "ball", "contact": "bracket"}, 'job 1: needs "maxDepthMm"'),
                                 ({"kind": "mass", "pose": None, "depth": 3}, 'job 1: a mass job has no field "depth"'),
                                 ({"kind": "mass", "id": "Mass Here"}, "job 1: an id is lower-case letters, digits")):
                with self.assertRaisesRegex(DesignError, message):
                    recorded(path, out, [bad])

    def test_check_says_which_requested_jobs_are_current_stale_or_missing(self):
        """Catches a judging tool told a record is current when its own rule changed, or when no record exists."""
        path = source()
        with tempfile.TemporaryDirectory() as out:
            recorded(path, out, JOBS[:6])
            asked = [*JOBS[:5], dict(JOBS[5], maxDepthMm=3.0), JOBS[6]]
            rows = {row["record"]: row for row in records.check(path, asked, out)}
        self.assertEqual({name: row["state"] for name, row in rows.items()},
                         {**dict.fromkeys(IDS[:5], "current"), IDS[5]: "stale", IDS[6]: "missing"})
        self.assertEqual(rows[IDS[5]]["changes"], ["the job's maxDepthMm changed: 4.0 to 3.0"])
        self.assertEqual(rows[IDS[6]]["file"], f"{records.FOLDER}/{IDS[6]}.json")


if __name__ == "__main__":
    unittest.main()
