"""Measuring again only what changed: pairs whose solids, placements, motion or rules changed; the rest carried.

Every test compares a carried record with a full measurement of the same design, so a pair carried when it should
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
from frc_design_kernel.measure import attachment, clearance, mass, run, scene as scenes, summary

from .helpers import load_data
from .test_measure import STACK

SOLIDS = 8              # five robot solids and three fixtures in STACK
NEAR_BRACKET = {"kind": "box", "fromMm": [62, 40, 150], "toMm": [72, 50, 160]}    # 2 mm from the bracket's lift path and the ball


def source(change=None):
    data = copy.deepcopy(STACK)
    if change:
        change(data)
    return load_data(data).path


def move_loose(data):
    next(s for s in data["solids"] if s["name"] == "loose")["shape"] = NEAR_BRACKET


def measured(path, earlier=None, focus=None, **settings):
    return summary.measure_design(path, settings.pop("min_gap", 3.0), 1.0, workers=1, earlier=earlier, focus=focus, **settings)


def without_checked(value):
    """A record with every "checked" block taken out: what is left must equal a full measurement."""
    if isinstance(value, dict):
        return {k: without_checked(v) for k, v in value.items() if k != "checked"}
    if isinstance(value, list):
        return [without_checked(v) for v in value]
    return value


def comparable(record):
    return without_checked({"motions": record["motions"], "poses": record["poses"]})


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


class OneSolidMoved(unittest.TestCase):
    def test_a_moved_solid_measures_exactly_its_pairs_and_the_merge_is_the_full_result(self):
        """Catches a carry that measures pairs which did not change, misses one that did, or merges to a different answer."""
        before = measured(source())
        moved = source(move_loose)
        full = measured(moved)
        with watched() as seen:
            carried = measured(moved, earlier=before)
        self.assertEqual(comparable(carried), comparable(full))
        self.assertTrue(seen["pairs"] and all("loose" in pair for pair in seen["pairs"]), seen["pairs"])
        for name, found in carried["motions"].items():
            checked = found["checked"]
            self.assertEqual(checked["measuredSolids"], ["loose"], name)
            self.assertEqual((checked["pairsMeasured"], checked["pairsCarried"], checked["pairsNotMeasured"]),
                             (SOLIDS - 1, math.comb(SOLIDS, 2) - (SOLIDS - 1), 0), name)
        self.assertIn(["bracket", "loose"], full["motions"]["lift off"]["closer"])     # the move matters: the merge must find it

    def test_control_a_carry_told_the_moved_solid_is_unchanged_gives_a_different_answer(self):
        """Control: shows the comparison with a full measurement does catch a pair carried when it changed."""
        before = measured(source())
        moved = source(move_loose)
        lying = copy.deepcopy(before)
        now = measured(moved)
        for name, found in lying["motions"].items():
            found["inputs"]["solids"]["loose"] = now["motions"][name]["inputs"]["solids"]["loose"]
        carried = measured(moved, earlier=lying)
        self.assertNotEqual(comparable(carried)["motions"], comparable(now)["motions"])
        self.assertEqual(carried["motions"]["lift off"]["checked"]["pairsMeasured"], 0)

    def test_a_motion_edit_measures_only_the_pairs_of_the_solids_it_moves(self):
        """Catches a change to one motion's stroke rerunning other motions, or solids that motion does not move."""
        before = measured(source())
        edited = source(lambda d: d["motions"]["press"]["moves"].update(piece=[{"kind": "translation", "travelMm": [0, 0, -30]}]))
        carried = measured(edited, earlier=before)
        self.assertEqual(comparable(carried), comparable(measured(edited)))
        self.assertEqual(carried["motions"]["press"]["checked"]["measuredSolids"], ["ball"])
        self.assertEqual(carried["motions"]["lift off"]["checked"]["pairsMeasured"], 0)

    def test_a_newly_declared_contact_measures_that_pair_alone(self):
        """Catches a change of declared contacts being missed (the pair carried) or rerunning every pair of both solids."""
        before = measured(source())
        edited = source(lambda d: d["contacts"].append({"pair": ["bracket", "post"], "during": ["lift off"]}))
        carried = measured(edited, earlier=before)
        self.assertEqual(comparable(carried), comparable(measured(edited)))
        checked = carried["motions"]["lift off"]["checked"]
        self.assertEqual((checked["measuredSolids"], checked["measuredPairs"], checked["pairsMeasured"]), ([], [["bracket", "post"]], 1))

    def test_changed_rules_measure_every_pair(self):
        """Catches pairs carried across a change of the gap asked, which every pair is tested against."""
        path = source()
        carried = measured(path, earlier=measured(path), min_gap=5.0)
        self.assertEqual(comparable(carried), comparable(measured(path, min_gap=5.0)))
        for found in carried["motions"].values():
            self.assertEqual((found["checked"]["measuredSolids"], found["checked"]["pairsCarried"]), (None, 0))


class NothingChanged(unittest.TestCase):
    def test_a_design_rename_and_a_note_edit_measure_nothing(self):
        """Catches names or notes entering a pair's identity, or a carry that still builds and searches every motion."""
        before = measured(source())

        def relabel(data):
            data["name"] = "Stack, renamed"
            data["mounts"][0]["note"] = "Three screws now."
            data["contacts"][0]["note"] = "Edited."
        edited = source(relabel)
        with watched() as seen:
            carried = measured(edited, earlier=before)
        self.assertEqual(comparable(carried), comparable(measured(edited)))
        self.assertEqual((seen["pairs"], seen["poseGaps"], seen["attachment"], seen["mass"], seen["motionScenes"]), ([], 0, [], [], 0))
        for found in carried["motions"].values():
            self.assertEqual((found["checked"]["pairsMeasured"], found["checked"]["pairsCarried"]), (0, math.comb(SOLIDS, 2)))

    def test_a_renamed_solid_measures_no_pair_and_is_carried_under_its_new_name(self):
        """Catches a solid's name entering its identity, or carried rows that keep the old name."""
        before = measured(source(move_loose))

        def rename(data):
            next(s for s in data["solids"] if s["name"] == "loose")["name"] = "stray"
        edited = source(lambda d: (move_loose(d), rename(d)))
        with watched() as seen:
            carried = measured(edited, earlier=before)
        self.assertEqual(comparable(carried), comparable(measured(edited)))
        self.assertEqual((seen["pairs"], seen["motionScenes"]), ([], 0))
        self.assertIn(["bracket", "stray"], carried["motions"]["lift off"]["closer"])
        self.assertEqual(carried["motions"]["lift off"]["checked"]["renamed"], {"stray": "loose"})

    def test_control_a_moved_solid_is_measured(self):
        """Control: shows the same watch does see measuring when one solid really moved by a millimetre."""
        before = measured(source())
        edited = source(lambda d: next(s for s in d["solids"] if s["name"] == "loose")["shape"].update(fromMm=[301, 0, 50], toMm=[311, 10, 60]))
        with watched() as seen:
            measured(edited, earlier=before)
        self.assertTrue(seen["attachment"] and seen["mass"] and seen["poseGaps"])
        self.assertEqual(seen["motionScenes"], 2)


class PoseCarry(unittest.TestCase):
    def test_attachment_and_mass_at_an_untouched_pose_are_carried(self):
        """Catches attachment and mass measured again at a pose where nothing moved, or carried at one where something did."""
        before = measured(source())
        def lower(data):
            data["poses"]["lifted"] = {"bracket": [{"kind": "translation", "travelMm": [0, 0, 90]}]}
            data["motions"]["lift off"]["moves"]["bracket"] = [{"kind": "translation", "travelMm": [0, 0, 90]}]
        edited = source(lower)
        with watched() as seen:
            carried = measured(edited, earlier=before)
        self.assertEqual(comparable(carried), comparable(measured(edited)))
        self.assertEqual((seen["attachment"], seen["mass"]), (["lifted"], ["lifted"]))
        checked = {row["pose"]: row["checked"] for row in carried["poses"]}
        self.assertEqual(checked[None], {"attachment": "carried", "mass": "carried"})
        self.assertEqual(checked["home"], {"attachment": "carried", "mass": "carried"})
        self.assertEqual(checked["lifted"], {"attachment": "measured", "mass": "measured"})

    def test_control_a_mass_edit_measures_mass_but_not_attachment(self):
        """Control: shows mass is measured again when only a mass changed, and attachment, which no mass enters, is not."""
        before = measured(source())
        edited = source(lambda d: d["solids"][0].update(massKg=1.5))
        with watched() as seen:
            carried = measured(edited, earlier=before)
        self.assertEqual(comparable(carried), comparable(measured(edited)))
        self.assertEqual((seen["attachment"], len(seen["mass"]), seen["pairs"]), ([], 3, []))
        self.assertNotEqual(carried["poses"][0]["mass"], before["poses"][0]["mass"])


class Focus(unittest.TestCase):
    def test_a_focus_without_an_earlier_record_says_what_it_left_out_and_is_never_carried_from(self):
        """Catches a part-measured motion passed off as whole, or carried from later as if every pair had been measured."""
        path = source()
        part = measured(path, focus=["ball"])
        checked = part["motions"]["press"]["checked"]
        self.assertEqual((checked["measuredSolids"], checked["pairsMeasured"], checked["pairsNotMeasured"]),
                         (["ball"], SOLIDS - 1, math.comb(SOLIDS, 2) - (SOLIDS - 1)))
        again = measured(path, earlier=part)
        self.assertEqual(comparable(again), comparable(measured(path)))
        self.assertEqual(again["motions"]["press"]["checked"]["measuredSolids"], None)

    def test_shared_between_workers_a_carry_is_the_same(self):
        """Catches a carry that changes with the worker count, or rows lost when carried and fresh rows are put together."""
        path = source(move_loose)
        before = measured(source())
        jobs = [{"motion": name, "minGapMm": 3.0, "contacts": summary.contacts_for(STACK, name), "earlier": before["motions"][name]}
                for name in STACK["motions"]]
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
            code = main(["measure", *map(str, args), "--min-gap", "3", "--workers", "1"])
        return code, text.getvalue().splitlines(), errors.getvalue()

    def test_carry_reads_the_record_in_the_folder_and_says_what_it_measured(self):
        """Catches --carry ignoring the earlier record, not saying what it carried, or writing a different record."""
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.run_measure(source(), "--out", out)[0], 0)
            code, lines, _ = self.run_measure(source(move_loose), "--out", out, "--carry")
            record = json.loads((Path(out) / "measurements.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(record["schema"], "frc-design-kernel/measurements@3")
        self.assertIn('Motion "lift off": measured 7 of 28 pairs again (those with loose), carried 21.', lines)
        self.assertIn('As drawn: attachment measured again, mass measured again.', lines)
        self.assertEqual(comparable(record), comparable(summary.measure_design(source(move_loose), 3.0, workers=1)))

    def test_carry_needs_an_earlier_record_and_focus_a_known_solid(self):
        """Catches --carry quietly measuring everything when there is nothing to carry from, or a focus on a solid that is not there."""
        with tempfile.TemporaryDirectory() as out:
            code, _, error = self.run_measure(source(), "--out", out, "--carry")
            self.assertEqual(code, 1)
            self.assertIn("--carry needs an earlier measurements.json", error)
            code, _, error = self.run_measure(source(), "--out", out, "--focus", "lose")
            self.assertEqual(code, 1)
            self.assertIn('there is no solid named "lose"', error)


if __name__ == "__main__":
    unittest.main()
