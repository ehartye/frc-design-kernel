"""Measuring again only what changed: pairs whose solids, placements, motion or rules changed; the rest carried.

Every test compares carried job files with a fresh measurement of the same design, so a pair carried when it should
have been measured shows up as a difference.
"""
import contextlib
import copy
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frc_design_kernel.cli import main
from frc_design_kernel.measure import attachment, clearance, mass, records, run, scene as scenes, summary

from .helpers import load_data
from .test_measure import STACK
from .test_records import files, raw, results

SOLIDS = 8              # five robot solids and three fixtures in STACK
NEAR_BRACKET = {"kind": "box", "fromMm": [62, 40, 150], "toMm": [72, 50, 160]}    # 2 mm from the bracket's lift path and the ball
MOTIONS = ("clearance.motion.press", "clearance.motion.lift-off")


def source(change=None):
    data = copy.deepcopy(STACK)
    if change:
        change(data)
    return load_data(data).path


def move_loose(data):
    next(s for s in data["solids"] if s["name"] == "loose")["shape"] = NEAR_BRACKET


def measured(path, folder, carry=True, focus=None, min_gap=3.0, touch_gap=1.0):
    """Record every job the measure command asks of a design, into folder; {job id: what was done}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    jobs = summary.design_jobs(data, min_gap, touch_gap)
    return {e["id"]: e["action"] for e in records.record(path, jobs, folder, workers=1, carry=carry, focus=focus)}


@contextlib.contextmanager
def watched():
    """Count what is really measured: each pair along a motion, each still-pose gap, each attachment and mass roll-up."""
    seen = {"pairs": [], "poseGaps": 0, "attachment": [], "mass": [], "motionScenes": 0}
    pair, gap, hold, weigh, scene = clearance.measure_pair, clearance.gap_and_overlap, attachment.at_pose, mass.roll_up, scenes.for_motion

    def on_pair(s, a, b, *rest, **kw):
        seen["pairs"].append((a, b))
        return pair(s, a, b, *rest, **kw)

    def on_gap(*args):
        seen["poseGaps"] += 1
        return gap(*args)

    def on_hold(assembly, pose=None, *rest, **kw):
        seen["attachment"].append(pose)
        return hold(assembly, pose, *rest, **kw)

    def on_weigh(assembly, pose=None, *rest):
        seen["mass"].append(pose)
        return weigh(assembly, pose, *rest)

    def on_scene(*args, **kw):
        seen["motionScenes"] += 1
        return scene(*args, **kw)

    run._built.clear()
    run._fixed.clear()
    with mock.patch.object(clearance, "measure_pair", on_pair), mock.patch.object(clearance, "gap_and_overlap", on_gap), \
            mock.patch.object(attachment, "at_pose", on_hold), mock.patch.object(mass, "roll_up", on_weigh), \
            mock.patch.object(scenes, "for_motion", on_scene):
        yield seen


class Folders:
    """A carried folder and a fresh one, both removed after the test."""

    def setUp(self):
        self.held = [tempfile.TemporaryDirectory() for _ in range(2)]
        self.carried, self.fresh = (folder.name for folder in self.held)

    def tearDown(self):
        for folder in self.held:
            folder.cleanup()


class OneSolidMoved(Folders, unittest.TestCase):
    def test_a_moved_solid_measures_exactly_its_pairs_and_the_merge_is_the_full_result(self):
        """Catches a carry that measures pairs which did not change, misses one that did, or merges to a different answer."""
        measured(source(), self.carried)
        moved = source(move_loose)
        measured(moved, self.fresh, carry=False)
        with watched() as seen:
            measured(moved, self.carried)
        self.assertEqual(results(self.carried), results(self.fresh))
        self.assertTrue(seen["pairs"] and all("loose" in pair for pair in seen["pairs"]), seen["pairs"])
        found = files(self.carried)
        for name in MOTIONS:
            checked = found[name]["checked"]
            self.assertEqual(checked["measuredSolids"], ["loose"], name)
            self.assertEqual((checked["pairsMeasured"], checked["pairsCarried"], checked["pairsNotMeasured"]),
                             (SOLIDS - 1, math.comb(SOLIDS, 2) - (SOLIDS - 1), 0), name)
        self.assertIn(["bracket", "loose"], found["clearance.motion.lift-off"]["result"]["closer"])     # the move matters: the merge must find it

    def test_a_motion_edit_measures_only_the_pairs_of_the_solids_it_moves(self):
        """Catches a change to one motion's stroke rerunning other motions, or solids that motion does not move."""
        measured(source(), self.carried)
        edited = source(lambda d: d["motions"]["press"]["moves"].update(piece=[{"kind": "translation", "travelMm": [0, 0, -30]}]))
        done = measured(edited, self.carried)
        measured(edited, self.fresh, carry=False)
        self.assertEqual(results(self.carried), results(self.fresh))
        self.assertEqual(files(self.carried)["clearance.motion.press"]["checked"]["measuredSolids"], ["ball"])
        self.assertEqual(done["clearance.motion.lift-off"], "carried")

    def test_a_newly_declared_contact_measures_that_pair_alone(self):
        """Catches a change of declared contacts being missed (the pair carried) or rerunning every pair of both solids."""
        measured(source(), self.carried)
        edited = source(lambda d: d["contacts"].append({"pair": ["bracket", "post"], "during": ["lift off"]}))
        measured(edited, self.carried)
        measured(edited, self.fresh, carry=False)
        self.assertEqual(results(self.carried), results(self.fresh))
        checked = files(self.carried)["clearance.motion.lift-off"]["checked"]
        self.assertEqual((checked["measuredSolids"], checked["measuredPairs"], checked["pairsMeasured"]), ([], [["bracket", "post"]], 1))

    def test_changed_rules_measure_every_pair(self):
        """Catches pairs carried across a change of the gap asked, which every pair is tested against."""
        path = source()
        measured(path, self.carried)
        measured(path, self.carried, min_gap=5.0)
        measured(path, self.fresh, carry=False, min_gap=5.0)
        self.assertEqual(results(self.carried), results(self.fresh))
        for name in MOTIONS:
            checked = files(self.carried)[name]["checked"]
            self.assertEqual((checked["measuredSolids"], checked["pairsCarried"]), (None, 0))


class NothingChanged(Folders, unittest.TestCase):
    def test_a_design_rename_and_a_note_edit_measure_nothing_and_write_nothing(self):
        """Catches names or notes entering a job's identity, or a carry that still builds and searches every motion."""
        measured(source(), self.carried)
        before = raw(self.carried)

        def relabel(data):
            data["name"] = "Stack, renamed"
            data["mounts"][0]["note"] = "Three screws now."
            data["contacts"][0]["note"] = "Edited."
        with watched() as seen:
            done = measured(source(relabel), self.carried)
        self.assertEqual(set(done.values()), {"carried"})
        self.assertEqual((seen["pairs"], seen["poseGaps"], seen["attachment"], seen["mass"], seen["motionScenes"]), ([], 0, [], [], 0))
        self.assertEqual(raw(self.carried), before)

    def test_a_renamed_solid_measures_no_pair_and_is_carried_under_its_new_name(self):
        """Catches a solid's name entering its identity, or carried rows that keep the old name."""
        measured(source(move_loose), self.carried)

        def rename(data):
            next(s for s in data["solids"] if s["name"] == "loose")["name"] = "stray"
        edited = source(lambda d: (move_loose(d), rename(d)))
        with watched() as seen:
            measured(edited, self.carried)
        measured(edited, self.fresh, carry=False)
        self.assertEqual(results(self.carried), results(self.fresh))
        self.assertEqual((seen["pairs"], seen["motionScenes"]), ([], 0))
        lift = files(self.carried)["clearance.motion.lift-off"]
        self.assertIn(["bracket", "stray"], lift["result"]["closer"])
        self.assertEqual(lift["checked"]["renamed"], {"stray": "loose"})

    def test_control_a_moved_solid_is_measured(self):
        """Control: shows the same watch does see measuring when one solid really moved by a millimetre."""
        measured(source(), self.carried)
        edited = source(lambda d: next(s for s in d["solids"] if s["name"] == "loose")["shape"].update(fromMm=[301, 0, 50], toMm=[311, 10, 60]))
        with watched() as seen:
            done = measured(edited, self.carried)
        self.assertEqual(sorted(seen["attachment"], key=str), [None, "home", "lifted"])
        self.assertEqual(seen["mass"], [])              # the loose block has no mass, so no roll-up uses its shape
        self.assertEqual(seen["motionScenes"], 2)
        self.assertEqual({files(self.carried)[name]["checked"]["measuredSolids"][0] for name in done if name.startswith("clearance.")}, {"loose"})


class PoseCarry(Folders, unittest.TestCase):
    def test_attachment_and_mass_at_an_untouched_pose_are_carried(self):
        """Catches attachment and mass measured again at a pose where nothing moved, or carried at one where something did."""
        measured(source(), self.carried)

        def lower(data):
            data["poses"]["lifted"] = {"bracket": [{"kind": "translation", "travelMm": [0, 0, 90]}]}
            data["motions"]["lift off"]["moves"]["bracket"] = [{"kind": "translation", "travelMm": [0, 0, 90]}]
        edited = source(lower)
        with watched() as seen:
            done = measured(edited, self.carried)
        measured(edited, self.fresh, carry=False)
        self.assertEqual(results(self.carried), results(self.fresh))
        self.assertEqual((seen["attachment"], seen["mass"]), (["lifted"], ["lifted"]))
        self.assertEqual(sorted(name for name, action in done.items() if action == "measured"),
                         ["attachment.pose.lifted", "clearance.motion.lift-off", "clearance.pose.lifted", "mass.pose.lifted"])

    def test_control_a_mass_edit_measures_mass_but_not_attachment(self):
        """Control: shows mass is measured again when only a mass changed, and attachment, which no mass enters, is not."""
        measured(source(), self.carried)
        before = files(self.carried)["mass.drawn"]["result"]
        edited = source(lambda d: d["solids"][0].update(massKg=1.5))
        with watched() as seen:
            measured(edited, self.carried)
        measured(edited, self.fresh, carry=False)
        self.assertEqual(results(self.carried), results(self.fresh))
        self.assertEqual((seen["attachment"], len(seen["mass"]), seen["pairs"]), ([], 3, []))
        self.assertNotEqual(files(self.carried)["mass.drawn"]["result"], before)


class AttachmentCarry(Folders, unittest.TestCase):
    def test_touching_gaps_and_mounts_of_unchanged_solids_are_carried(self):
        """Catches an attachment that measures every touching pair and mount again after one solid moved, or merges to a different answer."""
        measured(source(), self.carried)
        moved = source(move_loose)
        measured(moved, self.carried)
        measured(moved, self.fresh, carry=False)
        self.assertEqual(results(self.carried), results(self.fresh))
        for name in ("attachment.drawn", "attachment.pose.home", "attachment.pose.lifted"):
            checked = files(self.carried)[name]["checked"]
            self.assertEqual((checked["mountsMeasured"], checked["mountsCarried"]), (0, 1), name)
            self.assertGreater(checked["pairsCarried"], 0, name)

    def test_control_a_carried_gap_is_the_earlier_number_and_a_new_touch_gap_measures_all(self):
        """Control: shows touching gaps really are carried (a wrong earlier gap shows through) and are not across a new touch gap."""
        measured(source(), self.carried)
        for path in (Path(self.carried) / records.FOLDER).glob("attachment.*.json"):
            lying = json.loads(path.read_text(encoding="utf-8"))
            for pair in lying["result"]["touching"]:
                pair["gapMm"] = 0.5
            path.write_text(json.dumps(lying), encoding="utf-8")
        measured(source(move_loose), self.carried)
        found = files(self.carried)
        self.assertEqual({pair["gapMm"] for name in found if name.startswith("attachment.") for pair in found[name]["result"]["touching"]}, {0.5})
        measured(source(move_loose), self.carried, touch_gap=2.0)
        found = files(self.carried)
        self.assertEqual({json.dumps(found[name]["checked"]) for name in found if name.startswith("attachment.")}, {'{"measured": "whole"}'})


class Focus(Folders, unittest.TestCase):
    def test_a_focus_without_an_earlier_record_says_what_it_left_out_and_is_never_carried_from(self):
        """Catches a part-measured motion passed off as whole, or carried from later as if every pair had been measured."""
        path = source()
        measured(path, self.carried, carry=False, focus=["ball"])
        checked = files(self.carried)["clearance.motion.press"]["checked"]
        self.assertEqual((checked["measuredSolids"], checked["pairsMeasured"], checked["pairsNotMeasured"]),
                         (["ball"], SOLIDS - 1, math.comb(SOLIDS, 2) - (SOLIDS - 1)))
        done = measured(path, self.carried)
        measured(path, self.fresh, carry=False)
        self.assertEqual(results(self.carried), results(self.fresh))
        self.assertEqual(done["clearance.motion.press"], "measured")
        self.assertEqual(files(self.carried)["clearance.motion.press"]["checked"]["measuredSolids"], None)

    def test_shared_between_workers_a_carry_is_the_same(self):
        """Catches a carry that changes with the worker count, or rows lost when carried and fresh rows are put together."""
        path = source(move_loose)
        plain = [{"motion": name, "minGapMm": 3.0, "contacts": summary.contacts_for(STACK, name)} for name in STACK["motions"]]
        before = run.clearances(source(), plain, workers=1)
        jobs = [dict(job, earlier=found) for job, found in zip(plain, before)]
        alone = run.clearances(path, jobs, workers=1)
        old = run.PAIRS_PER_SHARE
        try:
            run.PAIRS_PER_SHARE = 1
            self.assertEqual(run.clearances(path, jobs, workers=2), alone)
        finally:
            run.PAIRS_PER_SHARE = old
        self.assertEqual(alone[1]["checked"]["measuredSolids"], ["loose"])


class Command(unittest.TestCase):
    def run_measure(self, *args):
        text, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(errors):
            code = main(["measure", *map(str, args), "--min-gap", "3", "--touch-gap", "1", "--workers", "1"])
        return code, text.getvalue().splitlines(), errors.getvalue()

    def test_carry_reads_the_records_in_the_folder_and_says_what_it_measured(self):
        """Catches --carry ignoring the earlier records, not saying what it carried, or writing a different record."""
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as fresh:
            self.assertEqual(self.run_measure(source(), "--out", out)[0], 0)
            code, lines, _ = self.run_measure(source(move_loose), "--out", out, "--carry")
            self.assertEqual(self.run_measure(source(move_loose), "--out", fresh)[0], 0)
            self.assertEqual(results(out), results(fresh))
            schema = files(out)["clearance.motion.lift-off"]["schema"]
        self.assertEqual((code, schema), (0, records.SCHEMA))
        self.assertIn("clearance.motion.lift-off: measured 7 of 28 pairs again (those with loose), carried 21.", lines)
        self.assertIn("mass.drawn: carried; its record is current.", lines)

    def test_carry_needs_earlier_records_and_focus_a_known_solid(self):
        """Catches --carry quietly measuring everything when there is nothing to carry from, or a focus on a solid that is not there."""
        with tempfile.TemporaryDirectory() as out:
            code, _, error = self.run_measure(source(), "--out", out, "--carry")
            self.assertEqual(code, 1)
            self.assertIn(f"--carry needs earlier job records in {Path(out) / records.FOLDER}", error)
            code, _, error = self.run_measure(source(), "--out", out, "--focus", "lose")
            self.assertEqual(code, 1)
            self.assertIn('there is no solid named "lose"', error)


if __name__ == "__main__":
    unittest.main()
