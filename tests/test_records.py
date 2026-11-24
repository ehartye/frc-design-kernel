"""Every measurement is a job with its own file, measured each time it is asked and written as it finishes.

The design is the small stack of test_measure, with one job of every kind. A record holds the question, the answer
and the library version. Nothing reads an earlier file, so no earlier file can change what a run measures or writes.
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

from .helpers import job_files, load_data, recorded
from .test_clearance import ARM
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
SWING = {"kind": "clearance", "motion": "swing", "minGapMm": 1.0}     # the arm of test_clearance passes five solids, each measured
LOOSE_NEAR = {"kind": "box", "fromMm": [62, 40, 150], "toMm": [72, 50, 160]}     # 2 mm from the bracket's lift path


def source(change=None):
    data = copy.deepcopy(STACK)
    if change:
        change(data)
    return load_data(data)


def move_loose(data):
    next(s for s in data["solids"] if s["name"] == "loose")["shape"] = LOOSE_NEAR


def raw(folder):
    return {path.name: path.read_bytes() for path in sorted((Path(folder) / records.FOLDER).iterdir())}


@contextlib.contextmanager
def watched():
    """Count what is really measured, by kind of question, and name the pairs measured along a motion."""
    real = {"pairs": (clearance, "measure_pair"), "poseGaps": (clearance, "gap_and_overlap"), "reach": (approach, "reach"),
            "indentation": (compression, "indentation"), "withdrawn": (approach, "withdrawn"), "attachment": (attachment, "at_pose"),
            "mass": (mass, "roll_up")}
    seen = {**dict.fromkeys(real, 0), "names": []}

    def counting(key, function):
        def call(*args, **kw):
            seen[key] += 1
            if key == "pairs":
                seen["names"].append((args[1], args[2]))
            return function(*args, **kw)
        return call

    with contextlib.ExitStack() as stack:
        for key, (module, name) in real.items():
            stack.enter_context(mock.patch.object(module, name, counting(key, getattr(module, name))))
        yield seen


class EveryKind(unittest.TestCase):
    def test_a_record_holds_the_question_the_answer_and_the_library_version_and_nothing_else(self):
        """Catches a record that keeps a date, or keeps figures only good for telling later whether something changed."""
        with tempfile.TemporaryDirectory() as out:
            entries = recorded(source(), JOBS, out)
            found = job_files(out)
        self.assertEqual([entry["id"] for entry in entries], IDS)
        self.assertEqual(sorted(found), sorted(IDS))
        for name, job, entry in zip(IDS, JOBS, entries):
            held = found[name]
            self.assertEqual(set(held) - {"counts"}, {"schema", "generator", "id", "job", "result"}, name)
            self.assertEqual("counts" in held, job["kind"] == "clearance", name)
            self.assertEqual((held["schema"], held["id"], held["job"]["kind"]), (records.SCHEMA, name, job["kind"]))
            self.assertEqual(set(held["generator"]), {"library", "version", "commit"})
            self.assertEqual((entry["record"], entry["file"]), (held, f"{records.FOLDER}/{name}.json"))
        self.assertEqual(found["indentation.press.ball.bracket"]["job"]["maxDepthMm"], 4.0)
        self.assertIn(["bracket", "post"], found["clearance.motion.lift-off.displaced.post"]["result"]["closer"])

    def test_a_second_identical_run_measures_everything_again_and_writes_the_same_bytes(self):
        """Catches a run that skips a job because its file is there, or the same figures writing a different file."""
        design = source()
        with tempfile.TemporaryDirectory() as out:
            with watched() as first:
                recorded(design, JOBS, out)
            before = raw(out)
            with watched() as second:
                recorded(design, JOBS, out)
            self.assertEqual(raw(out), before)
        self.assertEqual(first, second)
        self.assertTrue(all(second.values()), second)

    def test_two_askings_of_one_bench_both_measure(self):
        """Catches a bench that answers a second asking from what it remembers of the first."""
        counts = []
        with tempfile.TemporaryDirectory() as out, run.Bench(source(), 1) as bench:
            for _ in range(2):
                with watched() as seen:
                    records.record(bench, JOBS, out)
                counts.append(seen)
        self.assertEqual(counts[0], counts[1])

    def test_files_edited_or_deleted_change_no_answer(self):
        """Catches an answer taken from an earlier file: lying, broken, in another format or gone, each is written afresh."""
        design = source(move_loose)
        with tempfile.TemporaryDirectory() as out:
            recorded(design, JOBS, out)
            before = raw(out)
            folder = Path(out) / records.FOLDER
            for path in folder.glob("clearance.*.json"):
                lying = json.loads(path.read_text(encoding="utf-8"))
                lying["result"].update(closer=[], pairs=[])
                path.write_text(json.dumps(lying), encoding="utf-8")
            (folder / "mass.pose.lifted.json").write_text('{"schema": "another", "result": {}}', encoding="utf-8")
            (folder / "attachment.pose.home.json").write_text("not json", encoding="utf-8")
            (folder / "withdrawal.lift-off.json").unlink()
            recorded(design, JOBS, out)
            self.assertEqual(raw(out), before)
            self.assertIn(["bracket", "loose"], job_files(out)["clearance.motion.lift-off"]["result"]["closer"])

    def test_control_a_moved_solid_gives_another_answer(self):
        """Control: shows the comparison of files above can fail, by measuring a design whose block really moved."""
        with tempfile.TemporaryDirectory() as out:
            recorded(source(), JOBS, out)
            before = raw(out)
            recorded(source(move_loose), JOBS, out)
            self.assertNotEqual(raw(out), before)


class StoredRows(unittest.TestCase):
    def test_no_file_holds_a_row_for_a_far_apart_pair(self):
        """Catches the records keeping a row for every pair that was measured: the bulk the receipts carried."""
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as arm:
            recorded(source(), JOBS, out)
            recorded(load_data(copy.deepcopy(ARM)), [SWING], arm)
            found = [held for held in [*job_files(out).values(), *job_files(arm).values()] if held["job"]["kind"] == "clearance"]
        for held in found:
            near, gap = held["job"].get("nearMm", 0.0), held["result"]["minGapMm"]
            for row in held["result"]["pairs"]:
                self.assertTrue(row["closerThanMinGap"] or not row["proven"] or row["lowerBoundMm"] < gap + near, (held["id"], row))
        swing = found[-1]
        self.assertEqual((swing["counts"]["measured"], swing["result"]["pairs"], swing["result"]["closest"]), (5, [], None))

    def test_control_a_wider_near_band_keeps_the_passing_rows(self):
        """Control: shows passing rows do reach a file when the caller asks for them, so the check above can fail."""
        with tempfile.TemporaryDirectory() as out:
            recorded(load_data(copy.deepcopy(ARM)), [dict(SWING, nearMm=10.0)], out)
            held = job_files(out)["clearance.motion.swing"]
        self.assertEqual([row["pair"] for row in held["result"]["pairs"]], [["arm", "post"]])      # 4.9 mm away; the others are proven at least 11 mm away
        self.assertFalse(held["result"]["pairs"][0]["closerThanMinGap"])
        self.assertEqual(held["result"]["closest"]["pair"], ["arm", "post"])


class Stopped(unittest.TestCase):
    def run_measure(self, *args):
        text = io.StringIO()
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(io.StringIO()):
            code = main(["measure", *map(str, args), "--min-gap", "3", "--touch-gap", "1", "--workers", "1"])
        return code, text.getvalue().splitlines()

    def test_a_stopped_run_keeps_the_jobs_it_finished_and_the_next_measures_all_of_them(self):
        """Catches a stopped run losing finished work or leaving a half-written file, or the next run skipping what it finds."""
        path, stop_after = source().path, 4
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
                code, lines = self.run_measure(path, "--out", out)
            total = len(job_files(out))
        self.assertEqual((code, total), (0, 11))          # two motions; clearance, attachment and mass as drawn and at two poses
        self.assertEqual(lines[-1], f"Wrote 11 job records to {Path(out) / records.FOLDER}.")
        self.assertEqual((seen["attachment"], seen["mass"]), (3, 3))

    def test_a_caller_stops_a_run_by_raising_in_its_report(self):
        """Catches a caller that fails fast on the first bad job still waiting for every other job, or losing the one it saw."""
        class Enough(Exception):
            pass

        def stop(entry):
            if entry["record"]["result"]["closer"]:
                raise Enough(entry["id"])

        with tempfile.TemporaryDirectory() as out, watched() as seen:
            with self.assertRaisesRegex(Enough, "clearance.motion.press"):
                recorded(source(lambda d: d.update(contacts=[])), JOBS, out, report=stop)      # nothing excuses the press
            self.assertEqual(sorted(job_files(out)), ["clearance.motion.press"])
        self.assertEqual((seen["attachment"], seen["mass"], seen["reach"]), (0, 0, 0))


class Requests(unittest.TestCase):
    def test_workers_give_the_same_files(self):
        """Catches files that change with the worker count, or a job written before all its shares came back."""
        design, old = source(), run.PAIRS_PER_SHARE
        with tempfile.TemporaryDirectory() as alone, tempfile.TemporaryDirectory() as shared:
            recorded(design, JOBS, alone)
            try:
                run.PAIRS_PER_SHARE = 1
                recorded(design, JOBS, shared, workers=2)
            finally:
                run.PAIRS_PER_SHARE = old
            self.assertEqual(raw(alone), raw(shared))

    def test_one_job_writes_one_file_and_leaves_the_rest(self):
        """Catches asking for one job measuring others, or removing the files of jobs not asked for."""
        design = source()
        with tempfile.TemporaryDirectory() as out:
            recorded(design, JOBS, out)
            before = raw(out)
            with watched() as seen:
                recorded(design, [dict(JOBS[5], maxDepthMm=3.5)], out)
            after = raw(out)
        self.assertEqual({key: n for key, n in seen.items() if n}, {"indentation": 1})
        self.assertEqual({name for name in before if after[name] != before[name]}, {"indentation.press.ball.bracket.json"})

    def test_ids_are_named_or_given_and_never_shared(self):
        """Catches two jobs writing one file, a given id ignored, or a job that names nothing real accepted."""
        design = source()
        twice = [JOBS[0], dict(JOBS[0], minGapMm=1.0)]
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaisesRegex(DesignError, r'jobs 1 and 2 have the same id "clearance.motion.press"'):
                recorded(design, twice, out)
            entries = recorded(design, [twice[0], dict(twice[1], id="press-tight")], out)
            self.assertEqual([e["id"] for e in entries], ["clearance.motion.press", "press-tight"])
            for bad, message in (({"kind": "sideways", "motion": "press"}, 'job 1: there is no job kind "sideways"'),
                                 ({"kind": "clearance", "motion": "pres"}, 'job 1: there is no motion named "pres"'),
                                 ({"kind": "indentation", "motion": "press", "piece": "ball", "contact": "bracket"}, 'job 1: needs "maxDepthMm"'),
                                 ({"kind": "mass", "pose": None, "depth": 3}, 'job 1: a mass job has no field "depth"'),
                                 ({"kind": "mass", "id": "Mass Here"}, "job 1: an id is lower-case letters, digits")):
                with self.assertRaisesRegex(DesignError, message):
                    recorded(design, [bad], out)

    def test_a_bad_job_stops_the_run_before_anything_is_measured(self):
        """Catches a run that measures for minutes before it finds the last job names a solid that is not there."""
        bad = {"kind": "reach", "motion": "press", "pair": ["ball", "pots"], "withinMm": 1.0}
        with tempfile.TemporaryDirectory() as out, watched() as seen:
            with self.assertRaisesRegex(DesignError, 'job "reach.press.ball.pots": names the solid "pots", which is not in the design'):
                recorded(source(), [*JOBS, bad], out)
        self.assertFalse(any(seen.values()), seen)


if __name__ == "__main__":
    unittest.main()
