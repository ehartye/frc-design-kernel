"""Where a run is while it runs: pairs done inside a job, the step inside a run, and which process said so.

A count that stops rising is how a caller sees a stuck worker, so the counts must come from inside the work, from
worker processes too, and must never change a figure.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

from frc_design_kernel import workers
from frc_design_kernel.measure import extremes, records, run
from frc_design_kernel.trials import campaign

from .helpers import load_data, recorded
from .scaled_design import design as scaled
from .test_one_thing import GRIPPY
from .test_records import JOBS, raw, source
from .test_screen import TAPER, design as rig
from .trial_cases import ENGINES, bench, hold_trial

SWEEP = {"kind": "clearance", "motion": "mech 0 slide 1", "minGapMm": 1.0, "includeStill": True}


def begin(step_s):
    """Answers for a crew: count to ten, or get stuck for good after three."""
    def answer(task, meter):
        for n in range(10):
            if task == "stuck" and n == 3:
                time.sleep(600)
            time.sleep(step_s)
            meter(n + 1, 10)
        return task.upper()
    return answer


def rises(values):
    """Whether a count never falls and is seen part way as well as at its end."""
    return values == sorted(values) and len(set(values)) > 2


class Crew(unittest.TestCase):
    def test_answers_and_counts_come_back_with_the_process_they_came_from(self):
        """Catches counts lost between processes, or a count nobody can tie to a process."""
        for count in (1, 2):
            told, done = [], {}
            with workers.Crew(begin, (0.02,), count, every_s=0.0) as crew:
                for index, process, answer in crew.ask(["a", "b"], lambda *event: told.append(event)):
                    done[index] = (process, answer)
            self.assertEqual([done[i][1] for i in (0, 1)], ["A", "B"])
            for index in (0, 1):
                mine = [row for row in told if row[0] == index]
                self.assertTrue(rises([row[2] for row in mine]), (count, mine))
                self.assertEqual({row[3] for row in mine}, {10})
                self.assertEqual({row[1] for row in mine}, {done[index][0]})
            self.assertEqual(os.getpid() in {process for process, _ in done.values()}, count == 1)

    def test_a_stuck_worker_is_a_count_that_stops_and_stopping_does_not_wait_for_it(self):
        """Catches a stuck worker hidden by the others, or a caller that cannot stop until a stuck worker finishes."""
        last, finished = {}, []
        began = time.perf_counter()
        with workers.Crew(begin, (0.2,), 2, every_s=0.0) as crew:
            asked = crew.ask(["stuck", "fine"], lambda index, process, done, of: last.__setitem__(index, (process, done)))
            index, _, answer = next(asked)
            finished.append((index, answer))
            asked.close()
        self.assertEqual(finished, [(1, "FINE")])
        self.assertEqual((last[0][1], last[1][1]), (3, 10))
        self.assertNotEqual(last[0][0], last[1][0])
        self.assertLess(time.perf_counter() - began, 60)

    def test_control_a_worker_that_is_not_stuck_finishes(self):
        """Control: shows the stuck task above is what stopped, not every second task."""
        with workers.Crew(begin, (0.0,), 2, every_s=0.0) as crew:
            self.assertEqual(sorted(answer for _, _, answer in crew.ask(["slow", "fine"])), ["FINE", "SLOW"])

    def test_it_says_so_at_most_as_often_as_asked(self):
        """Catches a meter that talks for every pair, which would cost more than the measuring."""
        told = []
        with workers.Crew(begin, (0.0,), 1, every_s=60.0) as crew:
            list(crew.ask(["a"], lambda *event: told.append(event[2])))
        self.assertEqual(told, [1, 10])         # its first word and where it ended


class InsideAJob(unittest.TestCase):
    def sweep(self, count):
        told = []
        with run.Bench(load_data(scaled()), count, progress=told.append, every_s=0.0) as bench_:
            answer, = records.answers(bench_, [SWEEP])
        return told, answer

    def test_a_motion_names_itself_and_its_pairs_rise_to_their_total(self):
        """Catches a job that only speaks when it is finished: a long motion and a hung one then look the same."""
        for count in (1, 2):
            told, answer = self.sweep(count)
            self.assertEqual({row["job"] for row in told}, {"clearance.motion.mech-0-slide-1"})
            self.assertEqual({row["of"] for row in told}, {answer["record"]["counts"]["pairs"]})
            self.assertTrue(rises([row["done"] for row in told]), count)
            self.assertEqual((told[0]["done"] < told[-1]["of"], told[-1]["done"]), (True, told[-1]["of"]))
            processes = {row["process"] for row in told}
            self.assertEqual(len(processes), count)
            self.assertEqual(os.getpid() in processes, count == 1)
            for process in processes:
                mine = [row for row in told if row["process"] == process]
                self.assertTrue(rises([row["processDone"] for row in mine]))
                self.assertLessEqual(mine[-1]["processOf"], mine[-1]["of"])

    def test_a_limited_measurement_counts_only_the_pairs_it_measures(self):
        """Catches a total of every pair for a measurement of one solid's pairs, so it would never read as near its end."""
        told = []
        with run.Bench(load_data(scaled()), 1, progress=told.append, every_s=0.0) as bench_:
            records.answers(bench_, [SWEEP], focus=["mech 0 plate"])
        self.assertEqual(({row["of"] for row in told}, told[-1]["done"]), ({227}, 227))

    def test_every_kind_of_job_says_it_began_and_that_it_ended(self):
        """Catches a kind of job with no word of it: the slow attachment, or a quick one that hangs."""
        told = []
        with tempfile.TemporaryDirectory() as out:
            recorded(source(), JOBS, out, progress=told.append, every_s=0.0)
        for name in {row["job"] for row in told}:
            mine = [row for row in told if row["job"] == name]
            self.assertEqual((mine[0]["done"], mine[-1]["done"]), (0, mine[-1]["of"]), name)
            self.assertGreater(mine[-1]["of"], 0)
        self.assertEqual(len({row["job"] for row in told}), len(JOBS))
        self.assertGreater(next(row["of"] for row in told if row["job"] == "attachment.pose.home" and row["done"]), 1)

    def test_an_end_of_an_adjustment_names_itself(self):
        """Catches the ends of an adjustment measured with no word of which end, or which motion there."""
        told = []
        with run.Bench(load_data(rig(), {"custom/taper.py": TAPER}), 1, progress=told.append, every_s=0.0) as bench_:
            extremes.at_extremes(bench_, 2.0, motions=["press"], poses=["home"])
        self.assertEqual({(row["adjustment"], row["setting"], row["job"]) for row in told},
                         {("channel gap", setting, job) for setting in (1, 8) for job in ("clearance.motion.press", "clearance.pose.home")})

    def test_listening_changes_no_figure(self):
        """Catches a progress count that reaches a record."""
        with tempfile.TemporaryDirectory() as quiet, tempfile.TemporaryDirectory() as heard:
            recorded(source(), JOBS, quiet)
            recorded(source(), JOBS, heard, workers=2, progress=lambda event: None, every_s=0.0)
            self.assertEqual(raw(quiet), raw(heard))


class InsideACampaign(unittest.TestCase):
    def test_a_run_names_itself_and_its_step_rises_in_every_engine(self):
        """Catches a long trial that says nothing until every run of a round is back."""
        for engine in ENGINES:
            told = []
            design = load_data(bench({"hold": {**hold_trial(), "engine": engine}}, materials=GRIPPY))
            found = campaign.run_campaign(design, progress=told.append, every_s=0.0)
            self.assertEqual({row["trial"] for row in told}, {"hold"})
            self.assertEqual({row["run"] for row in told}, {row["id"] for row in found["trials"]["hold"]["runs"]})
            nominal = [row for row in told if row["run"] == "nominal"]
            self.assertTrue(rises([row["step"] for row in nominal]), engine)
            self.assertEqual({row["ofSteps"] for row in nominal}, {10000})
            self.assertEqual({row["process"] for row in told}, {os.getpid()})

    def test_the_runs_done_rise_toward_the_most_it_can_take(self):
        """Catches a campaign whose count of runs never moves, or is out of a total nobody stated."""
        for count in (1, 2):
            told = []
            design = load_data(bench({"hold": hold_trial(), "other": hold_trial()}, materials=GRIPPY))
            found = campaign.run_campaign(design, workers=count, progress=told.append, every_s=0.0)
            self.assertEqual({row["runsAtMost"] for row in told}, {found["cost"]["runsAtMost"]})
            self.assertTrue(rises([row["runsDone"] for row in told]))
            self.assertEqual(told[-1]["runsDone"], found["cost"]["runs"])
            self.assertEqual(os.getpid() in {row["process"] for row in told}, count == 1)

    def test_each_trial_is_reported_as_it_finishes_and_the_caller_can_stop(self):
        """Catches a caller that must wait for every trial before it sees the first one that failed."""
        seen = []

        def stop(name, trial):
            seen.append((name, trial["result"]))
            raise InterruptedError

        design = load_data(bench({"hold": hold_trial(), "other": hold_trial()}, materials=GRIPPY))
        with self.assertRaises(InterruptedError):
            campaign.run_campaign(design, report=stop)
        self.assertEqual(seen, [("hold", "passed")])

    def test_listening_changes_no_figure(self):
        """Catches a progress count that reaches a trial record."""
        design = load_data(bench({"hold": hold_trial()}, materials=GRIPPY))
        self.assertEqual(campaign.run_campaign(design, workers=2, progress=lambda event: None, every_s=0.0), campaign.run_campaign(design))


if __name__ == "__main__":
    unittest.main()
