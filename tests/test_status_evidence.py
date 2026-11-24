"""Status covers everything a record's answer rests on: adjustment extremes, a trial's start, its custom code, and what it saw.

Each class records something, changes one thing the answer depends on and expects exactly that record to go stale; each
has a control that a change the answer does not depend on leaves it current.
"""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from frc_design_kernel.cli import main
from frc_design_kernel.measure import extremes
from frc_design_kernel.status import status

from .helpers import load_data
from .test_screen import BOX, TAPER, design as rig
from .trial_cases import PANEL, bench, hold_trial, tilting_trial

GRIPPY = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.42, 0.8]}}}
WIND = '"""A steady push."""\n\n\ndef force(signals, parameters):\n    """Along x."""\n    return (parameters["pushN"], 0.0, 0.0)  # newtons\n'
JUDGE = "import math\n\n\ndef judge(run, parameters):\n    return math.isfinite(run['endS'])\n"
CUSTOM = {"wind": {"kind": "force", "reason": "An invented steady wind; no listed load does it.", "limits": "Steady, along x only."},
          "held_firmly": {"kind": "criterion", "reason": "An invented criterion on the end of the run.", "limits": "Any finite end passes."}}


def quiet(*args):
    with contextlib.redirect_stdout(io.StringIO()) as text:
        assert main([str(a) for a in args]) == 0, text.getvalue()
    return text.getvalue()


class Evidence(unittest.TestCase):
    """A design and its records in temporary folders; after(change) is each record's row for the changed source."""

    def begin(self, data, files=None):
        self.data, self.path = data, load_data(data, files).path
        keep = tempfile.TemporaryDirectory()
        self.addCleanup(keep.cleanup)
        self.out = Path(keep.name)

    def put(self, change=None):
        data = copy.deepcopy(self.data)
        if change:
            change(data)
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def rows(self, change=None, **asked):
        self.put(change)
        try:
            return {row["record"]: row for row in status(self.path, self.out, **asked)["records"]}
        finally:
            self.put()

    def stored(self, name):
        return json.loads((self.out / name).read_text(encoding="utf-8"))


class Extremes(Evidence):
    ROW = 'adjustment "channel gap"'

    def setUp(self):
        self.begin(rig(), {"custom/taper.py": TAPER})

    def measure(self, *more, min_gap=2):
        return quiet("measure", self.path, "--out", self.out, "--extremes", "--min-gap", min_gap, "--workers", "1", *more)

    def after(self, change=None, **asked):
        return self.rows(change, **{"min_gap": 2, **asked})[self.ROW]

    def test_a_declared_mechanical_adjustment_with_no_record_is_missing(self):
        """Catches ends that were never measured passing in silence. Control: a setpoint moves no solid and has no row."""
        self.data["parameters"]["belt_mps"] = 2.0
        self.data["adjustments"]["belt speed"] = {"input": "parameters.belt_mps", "kind": "setpoint", "range": [1.0, 3.0]}
        rows = self.rows()
        self.assertEqual((rows[self.ROW]["state"], rows[self.ROW]["changes"]), ("missing", ["its ends have not been measured"]))
        self.assertNotIn('adjustment "belt speed"', rows)
        self.measure()
        self.assertEqual(self.after()["state"], "current")
        held = self.stored(extremes.FILE)
        self.assertEqual(held["schema"], extremes.SCHEMA)
        found = held["adjustments"]["channel gap"]
        self.assertEqual(found["inputs"]["rules"], {"minGapMm": 2.0, "depth": 9, "motions": sorted(self.data["motions"]), "poses": [None, "home"]})
        self.assertEqual(sorted(found["used"]["ends"]), ["1", "8"])
        self.assertEqual(sorted(found["used"]["ends"]["1"]), ["wall left", "wall right"], "an end keeps only the solids it moves")

    def test_a_solid_the_ends_are_measured_against_changing_makes_them_stale(self):
        """Catches the hole this closes: extremes measured, then a solid moved, and the old extremes still read as clear."""
        self.measure()
        moved = self.after(lambda d: d["solids"][1]["shape"].update(radiusMm=26))
        self.assertEqual((moved["state"], moved["changes"]), ("stale", ['solid "straight roller" changed']))
        turned = self.after(lambda d: d["motions"]["swing in plane"]["moves"]["arm"][0].update(travelDeg=31))
        self.assertEqual(turned["changes"], ['solid "straight roller" changed'])
        touching = self.after(lambda d: d.update(contacts=[{"pair": ["drawn ball", "pad"]}]))
        self.assertIn("the declared contacts changed", touching["changes"])

    def test_what_the_adjustment_moves_at_its_ends_is_part_of_it(self):
        """Catches a solid that no longer follows the parameter: nothing changes as drawn, and the end is another design."""
        self.measure()
        stuck = self.after(lambda d: d["solids"][2]["shape"].update(fromMm=[-40, 23, -40], toMm=[40, 28, 40]))      # where "=wall" puts it as drawn
        self.assertEqual(stuck["changes"], ['solid "wall left" changed at 1', 'solid "wall left" changed at 8'])
        wider = self.after(lambda d: d["adjustments"]["channel gap"].update(range=[1, 9]))
        self.assertIn("its range changed: [1, 8] to [1, 9]", wider["changes"])

    def test_words_change_nothing(self):
        """Control: a renamed design, an edited note and a reordered motion table leave the ends current."""
        def reword(d):
            d["name"] = "Another name"
            d["adjustments"]["channel gap"]["note"] = "Reworded: slotted mounts."
            d["motions"] = dict(reversed(list(d["motions"].items())))
        self.measure()
        self.assertEqual(self.after(reword)["state"], "current")

    def test_rules_narrower_than_those_asked_for_do_not_count(self):
        """Catches ends measured against a smaller gap, a shallower search or a few motions standing for the whole request."""
        self.measure(min_gap=1)
        self.assertEqual(self.after()["changes"], ["it was measured against a gap of 1 mm, and 2 mm is asked"])
        self.assertEqual(self.after(min_gap=1)["state"], "current", "control: the gap it was measured against")
        self.assertEqual(self.after(min_gap=0)["state"], "current", "control: a wider measurement answers a narrower request")
        self.assertEqual(self.after(min_gap=1, depth=12)["changes"], ["it was searched to depth 9, and depth 12 is asked"])
        self.measure("--motion", "press")
        narrow = self.after()
        self.assertEqual(narrow["state"], "stale")
        self.assertEqual(narrow["changes"], ['the motion "swing in plane" was not measured', 'the motion "swing out of plane" was not measured',
                                             "the pose as drawn was not measured", 'the pose "home" was not measured'])

    def test_a_record_in_another_form_and_an_adjustment_that_is_gone_are_stated(self):
        """Catches a file of an earlier format, or of a removed adjustment, passing as current or crashing status."""
        self.measure()
        self.assertEqual(self.after(lambda d: d["adjustments"].pop("channel gap"))["changes"], ["the adjustment is no longer in the source"])
        held = self.stored(extremes.FILE)
        held["schema"] = "frc-design-kernel/adjustments@1"
        (self.out / extremes.FILE).write_text(json.dumps(held), encoding="utf-8")
        self.assertEqual((self.after()["state"], self.after()["changes"]), ("stale", [f"it is not a {extremes.SCHEMA} record"]))

    def test_an_end_that_only_moves_a_hole_is_measured_at_that_end(self):
        """Catches an end taken as moving nothing because the solid keeps its volume and its box: the slot moved in the plate."""
        slot = BOX(["=320 + gap", 2, 2], ["=330 + gap", 8, 11])
        self.data["solids"].append({"name": "slotted plate", "group": "rig", "shape": {"kind": "difference", "from": BOX([300, 0, 0], [400, 10, 10]), "cut": [slot]}})
        path = load_data(self.data, {"custom/taper.py": TAPER}).path
        tight = extremes.at_extremes(path, min_gap=2.0, workers=1)["channel gap"]["settings"][0]
        self.assertIn("slotted plate", tight["moves"])

    def test_the_command_asks_with_its_own_gap_and_says_missing(self):
        """Catches the status command hiding a missing record, or asking no gap of the ends."""
        self.assertIn('adjustment "channel gap": missing - its ends have not been measured', quiet("status", self.path, self.out))
        self.measure(min_gap=1)
        self.assertIn('adjustment "channel gap": current', quiet("status", self.path, self.out, "--min-gap", 1))
        self.assertIn('adjustment "channel gap": stale - it was measured against a gap of 1 mm, and 2 mm is asked', quiet("status", self.path, self.out, "--min-gap", 2))


class HandedStart(Evidence):
    """A trial that starts where another ended."""

    def setUp(self):
        then = hold_trial()
        then["piece"]["start"] = {"after": "hold"}
        self.begin(bench({"hold": hold_trial(), "then": then}, materials=GRIPPY))
        quiet("try", self.path, "--out", self.out)

    def again(self, change, name):
        """Run one trial again from the changed source, keeping the other's record; the rows for that source."""
        self.put(change)
        quiet("try", self.path, "--out", self.out, "--trial", name)
        return self.rows(change)

    def test_the_resolved_start_is_recorded_and_no_name(self):
        """Catches a start known by the other trial's name or record, which would go stale when nothing physical changed."""
        used = self.stored("trials.json")["trials"]["then"]["used"]
        end = self.stored("trials.json")["trials"]["hold"]["nominal"]["end"]["piece"]
        self.assertEqual(used["start"], {"piece": end[:2]}, "at rest, so only where it is")
        self.assertNotIn("hold", json.dumps(used))
        self.assertIsNone(self.stored("trials.json")["trials"]["hold"]["used"]["start"])
        self.assertEqual({row["state"] for row in self.rows().values()}, {"current"})

    def test_the_first_trial_ending_elsewhere_makes_the_second_stale(self):
        """Catches the hole this closes: the first trial rerun to another end, and the second still read as current."""
        longer = lambda d: d["trials"]["hold"]["piece"]["start"].update(atMm=[v + dv for v, dv in zip(d["trials"]["hold"]["piece"]["start"]["atMm"], (9.4, -3.42))])
        before = self.rows(longer)
        self.assertEqual(before['trial "hold"']["state"], "stale")
        self.assertEqual(before['trial "then"']["changes"], ['it starts where trial "hold" ends, and that record is not current'])
        rows = self.again(longer, "hold")
        self.assertEqual((rows['trial "hold"']["state"], rows['trial "then"']["state"]), ("current", "stale"))
        self.assertEqual(rows['trial "then"']["changes"], ["where it starts changed"])

    def test_the_first_trial_rerun_to_the_same_end_leaves_the_second_current(self):
        """Control: rerunning the first trial, with another note or a run longer than it needs, to the same end changes nothing."""
        rows = self.again(lambda d: d["trials"]["hold"]["control"].update(note="Reworded: a slippery panel lets it go."), "hold")
        self.assertEqual(rows['trial "then"']["state"], "current")
        rows = self.again(lambda d: d["trials"]["hold"].update(measures={"endX": {"final": "xMm"}}), "hold")
        self.assertEqual((rows['trial "hold"']["state"], rows['trial "then"']["state"]), ("current", "current"))

    def test_a_first_trial_with_no_record_leaves_the_start_unknown(self):
        """Catches a chained trial read as current when nothing says where it started."""
        held = self.stored("trials.json")
        del held["trials"]["hold"]
        (self.out / "trials.json").write_text(json.dumps(held), encoding="utf-8")
        self.assertEqual(self.rows()['trial "then"']["changes"], ['it starts where trial "hold" ends, and that trial has no record'])

    def test_a_renamed_first_trial_is_not_a_change(self):
        """Control: the first trial under another name, run again, leaves the second current: names are no part of it."""
        def rename(d):
            d["trials"] = {"first": d["trials"]["hold"], "then": {**d["trials"]["then"], "piece": {**d["trials"]["then"]["piece"], "start": {"after": "first"}}}}
        rows = self.again(rename, "first")
        self.assertEqual((rows['trial "first"']["state"], rows['trial "then"']["state"]), ("current", "current"))


class CustomCode(Evidence):
    FILES = {"custom/wind.py": WIND, "custom/held_firmly.py": JUDGE}

    def setUp(self):
        trial = hold_trial(forces=[{"use": "wind", "parameters": {"pushN": 0.01}}], **{"pass": {"outcomes": ["held"], "custom": {"use": "held_firmly"}}})
        self.begin(bench({"hold": trial, "plain": hold_trial()}, custom=CUSTOM, materials=GRIPPY), self.FILES)
        quiet("try", self.path, "--out", self.out)

    def code(self, name, text):
        (self.path.parent / "custom" / f"{name}.py").write_text(text, encoding="utf-8")
        try:
            return self.rows()
        finally:
            (self.path.parent / "custom" / f"{name}.py").write_text(self.FILES[f"custom/{name}.py"], encoding="utf-8")

    def test_an_edit_to_what_the_code_does_makes_its_trial_stale(self):
        """Catches the hole this closes: a criterion or a force edited after the trial, and the trial still read as current."""
        self.assertEqual({row["state"] for row in self.rows().values()}, {"current"})
        always = self.code("held_firmly", JUDGE.replace("math.isfinite(run['endS'])", "True"))
        self.assertEqual(always['trial "hold"']["changes"], ['custom code "held_firmly" changed'])
        self.assertEqual(always['trial "plain"']["state"], "current", "control: a trial that does not use it")
        for text in (WIND.replace("(parameters[\"pushN\"], 0.0, 0.0)", "(2 * parameters[\"pushN\"], 0.0, 0.0)"), WIND.replace("0.0, 0.0)", "0.0, 0.1)"),
                     WIND + "\n\ndef force(signals, parameters):\n    return (0.0, 0.0, 0.0)\n"):
            self.assertEqual(self.code("wind", text)['trial "hold"']["changes"], ['custom code "wind" changed'])

    def test_a_helper_in_the_same_file_is_part_of_it(self):
        """Catches a helper edited under an unchanged entry function. The file may import nothing else of the project's."""
        helped = JUDGE.replace("import math\n", "import math\n\n\ndef near(value):\n    return value < 1e9\n").replace("math.isfinite(run['endS'])", "near(run['endS'])")
        self.FILES = {**self.FILES, "custom/held_firmly.py": helped}
        (self.path.parent / "custom/held_firmly.py").write_text(helped, encoding="utf-8")
        quiet("try", self.path, "--out", self.out)
        self.assertEqual(self.rows()['trial "hold"']["state"], "current")
        self.assertEqual(self.code("held_firmly", helped.replace("1e9", "1e-9"))['trial "hold"']["changes"], ['custom code "held_firmly" changed'])
        refused = self.code("held_firmly", "import helper\n" + helped)['trial "hold"']
        self.assertEqual(refused["state"], "stale")
        self.assertIn('imports "helper"', " ".join(refused["changes"]))

    def test_comments_docstrings_and_layout_change_nothing(self):
        """Control: an edit that changes no behaviour leaves the trial current."""
        for text in ("# A remark.\n" + WIND, WIND.replace("  # newtons", ""), WIND.replace('"""Along x."""', '"""Along the x axis, steadily."""'),
                     WIND.replace('    """Along x."""\n', ""), WIND.replace('(parameters["pushN"], 0.0, 0.0)', "(\n        parameters['pushN'],\n        0.0, 0.0,\n    )"),
                     WIND.replace("\n", "\r\n")):
            self.assertEqual(self.code("wind", text)['trial "hold"']["state"], "current", text)
        self.assertNotIn("sha256", json.dumps(self.stored("trials.json")["trials"]["hold"]["used"]))


class WhatATrialSaw(Evidence):
    """The rest of what a trial's answer rests on: the true shape and place of each solid, its adjustments and its variants."""

    def test_a_hole_moved_in_a_solid_makes_the_trial_stale(self):
        """Catches a solid taken as the same because its volume and its box are: the notch moved along the belt bed."""
        data = bench({"hold": hold_trial()}, materials=GRIPPY)
        wedge = data["solids"][0]
        wedge["shape"] = {"kind": "difference", "from": wedge["shape"], "cut": [BOX([400, -60, 50], [450, 60, 100])]}
        self.begin(data)
        quiet("try", self.path, "--out", self.out)
        self.assertEqual(self.rows()['trial "hold"']["state"], "current")
        moved = self.rows(lambda d: d["solids"][0]["shape"].update(cut=[BOX([600, -60, 50], [650, 60, 100])]))['trial "hold"']
        self.assertEqual((moved["state"], moved["changes"]), ("stale", ['solid "wedge" changed shape or place']))

    def test_a_carrier_that_puts_a_solid_elsewhere_at_the_trials_pose_makes_it_stale(self):
        """Catches a group given another carrier: its own pose is as it was and it stands somewhere else."""
        data = bench({"hold": hold_trial(pose="set")}, materials=GRIPPY)
        data["groups"]["cart"] = {"role": "mechanism"}
        data["solids"].append({"name": "cart plate", "group": "cart", "shape": BOX([-500, -50, 0], [-400, 50, 10])})
        data["poses"] = {"set": {"cart": [{"kind": "translation", "travelMm": [0, 0, 5]}]}}
        self.begin(data)
        quiet("try", self.path, "--out", self.out)
        self.assertEqual(self.rows()['trial "hold"']["state"], "current")
        carried = self.rows(lambda d: d["groups"]["bench"].update(carriedBy="cart"))['trial "hold"']
        self.assertEqual(carried["changes"], ['solid "wedge" changed shape or place'])

    def tilting(self):
        self.begin(bench({"hold": tilting_trial(adjustments=["tilt"])}, adjustments={"tilt": {"input": "parameters.slope_deg", "kind": "mechanical", "range": [8, 24], "step": 1}}))
        quiet("try", self.path, "--out", self.out)
        self.assertEqual(self.stored("trials.json")["trials"]["hold"]["result"], "covered by adjustment")
        self.assertEqual(self.rows()['trial "hold"']["state"], "current")

    def test_an_adjustments_range_is_part_of_the_trial_it_covers(self):
        """Catches "covered by adjustment" standing for a setting the adjustment can no longer reach."""
        self.tilting()
        narrow = self.rows(lambda d: d["adjustments"]["tilt"].update(range=[15, 24]))['trial "hold"']
        self.assertEqual((narrow["state"], narrow["changes"]), ("stale", ['adjustment "tilt" changed']))
        self.assertEqual(self.rows(lambda d: d["adjustments"]["tilt"].update(note="Reworded: slotted feet."))['trial "hold"']["state"], "current")

    def test_the_design_at_the_settings_a_trial_varied_is_part_of_it(self):
        """Catches a solid that stops following the parameter the trial varied: nothing changes as drawn."""
        self.tilting()
        self.assertEqual(sorted(self.stored("trials.json")["trials"]["hold"]["used"]["varied"]), ["parameters.slope_deg"])
        stuck = self.rows(lambda d: d["solids"][0]["shape"].update(outlineMm=[[0, 0], [2000, 0], [0, "=2000 * tan(radians(20)) + 0 * rise"]]))['trial "hold"']
        self.assertEqual(stuck["state"], "stale")
        self.assertTrue(all(change.startswith("what it used with slope_deg at ") for change in stuck["changes"]), stuck["changes"])


if __name__ == "__main__":
    unittest.main()
