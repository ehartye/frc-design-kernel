"""Motion from motors through joints, motions that state their cause, and motions that start where another one ends.

The design is an invented pivot bench: an arm swung by a geared motor about a pivot, a carriage raised by a second
motor on a belt, and a wrist that rides on the arm. Each test compares placements, records or refusals, so a joint that
turns the wrong way, a chained start that is read by name, or a refusal that names nothing shows up as a difference.
"""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from frc_design_kernel import DesignError
from frc_design_kernel.builder import placement
from frc_design_kernel.builder.assembly import build
from frc_design_kernel.builder.manifest import manifest
from frc_design_kernel.cli import main
from frc_design_kernel.measure import records
from frc_design_kernel.motion import matrix as mx
from frc_design_kernel.status import status

from .helpers import load_data

ASSUMED = lambda value, low, high: {"value": value, "assumed": [low, high]}
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
PIVOT = [0, 0, 100]
SWING = lambda degrees: {"kind": "rotation", "originMm": PIVOT, "axis": [0, -1, 0], "travelDeg": degrees}
RISE = lambda mm: {"kind": "translation", "travelMm": [0, 0, mm]}
SAMPLES = (0.0, 0.25, 0.5, 0.8, 1.0)

BENCH = {
    "schema": "frc-design-kernel/design@1", "name": "Pivot bench", "units": {"length": "mm", "mass": "kg"},
    "groups": {"base": {"role": "structure"}, "arm": {"role": "mechanism", "carriedBy": "base"},
               "wrist": {"role": "mechanism", "carriedBy": "arm"}, "carriage": {"role": "mechanism", "carriedBy": "base"}},
    "solids": [
        {"name": "base plate", "group": "base", "massKg": 2.0, "shape": BOX([-400, -100, 0], [400, 100, 20])},
        {"name": "arm motor", "group": "base", "massKg": 0.5, "shape": BOX([-60, 40, 70], [-20, 80, 130])},
        {"name": "lift motor", "group": "base", "massKg": 0.5, "shape": BOX([-360, -80, 20], [-320, -40, 80])},
        {"name": "arm bar", "group": "arm", "massKg": 0.8, "shape": BOX([0, -15, 90], [300, 15, 110])},
        {"name": "wrist plate", "group": "wrist", "massKg": 0.2, "shape": BOX([300, -20, 80], [310, 20, 120])},
        {"name": "carriage block", "group": "carriage", "massKg": 1.0, "shape": BOX([-300, -40, 40], [-260, 40, 80])},
    ],
    "motors": {"small": {"ktNmPerA": ASSUMED(0.018, 0.017, 0.019), "ohm": ASSUMED(0.09, 0.08, 0.1), "keVsPerRad": ASSUMED(0.018, 0.017, 0.019)}},
    "drives": {
        "pivot": {"motor": "small", "motorSolid": "arm motor", "gear": 50, "supplyLimitA": 40,
                  "joint": {"group": "arm", "kind": "rotation", "axis": [0, -1, 0], "originMm": PIVOT, "travel": [-10, 120]}},
        "lift": {"motor": "small", "motorSolid": "lift motor", "gear": 5, "statorLimitA": 60,
                 "joint": {"group": "carriage", "kind": "slide", "axis": [0, 0, 1], "perOutputTurn": 100, "travel": [0, 400]}},
    },
    "poses": {"stowed": {}, "up": {"arm": [SWING(95)]}},
    "motions": {
        "raise arm": {"drive": {"pivot": {"to": 95}}, "durationS": ASSUMED(0.5, 0.4, 0.7)},
        "lift": {"drive": {"lift": {"by": 300}}, "durationS": ASSUMED(0.8, 0.6, 1.0)},
        "push by hand": {"by": "hand", "from": "stowed", "moves": {"carriage": [RISE(50)]}},
    },
}


def bench(change=None):
    data = copy.deepcopy(BENCH)
    if change:
        change(data)
    return data


def placements(data, motion):
    return [placement.at_motion(data, motion, t) for t in SAMPLES]


def farthest(data_a, motion_a, data_b, motion_b):
    """The largest gap, in mm at 1 m from the origin, between two motions' group placements at the same fractions."""
    return max(mx.gap(a[group], b[group]) for a, b in zip(placements(data_a, motion_a), placements(data_b, motion_b)) for group in a)


class MotorCommands(unittest.TestCase):
    def test_a_rotation_command_places_its_group_as_the_same_typed_turn_does(self):
        """Catches a joint that turns the wrong way, about the wrong line, or by the wrong amount (acceptance 18)."""
        driven = load_data(bench()).data
        typed = load_data(bench(lambda d: d["motions"].update(typed={"by": "hand", "moves": {"arm": [SWING(95)]}}))).data
        self.assertLess(farthest(driven, "raise arm", typed, "typed"), 1e-6)
        wrong = load_data(bench(lambda d: d["motions"].update(typed={"by": "hand", "moves": {"arm": [SWING(94)]}}))).data
        self.assertGreater(farthest(driven, "raise arm", wrong, "typed"), 1.0)      # control: one degree off is seen

    def test_a_slide_command_moves_its_group_along_the_axis_and_reports_the_motor_turns(self):
        """Catches a slide moved by the wrong distance, or motor turns worked out without the gear or the lead (acceptance 18)."""
        data = load_data(bench()).data
        for t, rise in ((0.0, 0.0), (0.5, 150.0), (1.0, 300.0)):
            self.assertLess(mx.gap(placement.at_motion(data, "lift", t)["carriage"], mx.translation((0, 0, rise))), 1e-6)
        found = placement.commands(data, "lift")
        self.assertEqual(found, {"lift": {"group": "carriage", "kind": "slide", "from": 0.0, "to": 300.0, "change": 300.0, "motorTurns": 15.0}})
        self.assertAlmostEqual(placement.commands(data, "raise arm")["pivot"]["motorTurns"], 95 / 360 * 50)

    def test_the_manifest_reports_each_command_with_its_motor_turns(self):
        """Catches a build record that keeps the commands as written but not what they work out to."""
        assembly = build(load_data(bench()))
        rows = manifest(assembly)["motions"]
        self.assertEqual(rows["lift"]["commands"]["lift"]["motorTurns"], 15.0)
        self.assertNotIn("commands", rows["push by hand"])

    def test_a_command_from_a_named_pose_starts_at_the_joint_value_that_pose_holds(self):
        """Catches a joint value read as zero whatever the start, so a "to" command would overshoot."""
        data = load_data(bench(lambda d: d["motions"].update(lower={"from": "up", "drive": {"pivot": {"to": 30}}, "durationS": 0.5}))).data
        self.assertAlmostEqual(placement.commands(data, "lower")["pivot"]["from"], 95.0)
        self.assertLess(mx.gap(placement.at_motion(data, "lower", 1.0)["arm"], mx.rotation(PIVOT, [0, -1, 0], 30)), 1e-6)
        self.assertLess(mx.gap(placement.at_motion(data, "lower", 0.0)["arm"], mx.rotation(PIVOT, [0, -1, 0], 95)), 1e-6)

    def test_a_carried_group_rides_on_a_driven_joint(self):
        """Catches the joint's movement not reaching the groups its group carries."""
        data = load_data(bench()).data
        end = placement.at_motion(data, "raise arm", 1.0)
        self.assertLess(mx.gap(end["wrist"], end["arm"]), 1e-9)


class JointRefusals(unittest.TestCase):
    def refused(self, change, *named):
        """The change is refused when the design is loaded or built, and the message names everything in named."""
        with self.assertRaises(DesignError) as caught:
            build(load_data(bench(change)))
        for name in named:
            self.assertIn(name, str(caught.exception))
        return str(caught.exception)

    def test_the_bench_itself_is_accepted(self):
        """Control for every refusal below: the unchanged bench loads and builds."""
        build(load_data(bench()))

    def test_a_command_outside_the_joint_travel_is_refused(self):
        """Catches an arm commanded past its hard stop (acceptance 19)."""
        self.refused(lambda d: d["motions"]["raise arm"]["drive"]["pivot"].update(to=130), '"raise arm"', '"pivot"', '"arm"', "travel")
        self.refused(lambda d: d["motions"]["lift"]["drive"]["lift"].update(by=450), '"lift"', '"carriage"', "travel")
        build(load_data(bench(lambda d: d["motions"]["raise arm"]["drive"]["pivot"].update(to=120))))     # control: the stop itself is in

    def test_two_drives_on_one_joint_in_one_motion_are_refused(self):
        """Catches two motors fighting over one group, which would leave its placement undefined (acceptance 19)."""
        def twin(d):
            d["drives"]["pivot two"] = copy.deepcopy(d["drives"]["pivot"])
            d["motions"]["raise arm"]["drive"]["pivot two"] = {"to": 95}
        self.refused(twin, '"raise arm"', '"pivot"', '"pivot two"', '"arm"')

    def test_a_typed_op_on_a_driven_joint_group_is_refused(self):
        """Catches a motion that says both "the motor turns the arm" and "the arm moves like this" (acceptance 19)."""
        self.refused(lambda d: d["motions"]["raise arm"].update(by="hand", moves={"arm": [SWING(10)]}), '"raise arm"', '"arm"')
        build(load_data(bench(lambda d: d["motions"]["raise arm"].update(by="piece", moves={"carriage": [RISE(10)]}))))     # control

    def test_a_motor_drive_with_no_motor_solid_is_refused(self):
        """Catches a motor that weighs nothing and sits nowhere, so motors are placed with purpose (acceptance 19)."""
        self.refused(lambda d: d["drives"]["pivot"].pop("motorSolid"), '"pivot"', "motorSolid")
        self.refused(lambda d: d["drives"]["pivot"].update(motorSolid="arm moter"), '"pivot"', '"arm moter"')

    def test_a_joint_drive_needs_a_motor_and_a_sound_joint(self):
        """Catches a joint with no motor to move it, or numbers that cannot describe one."""
        self.refused(lambda d: [d["drives"]["pivot"].pop(key) for key in ("motor", "motorSolid")], '"pivot"', "motor")
        self.refused(lambda d: d["drives"]["pivot"]["joint"].pop("originMm"), '"pivot"', "originMm")
        self.refused(lambda d: d["drives"]["lift"]["joint"].pop("perOutputTurn"), '"lift"', "perOutputTurn")
        self.refused(lambda d: d["drives"]["pivot"]["joint"].update(travel=[120, -10]), '"pivot"', "travel")
        self.refused(lambda d: d["drives"]["pivot"]["joint"].update(group="elbow"), '"pivot"', '"elbow"')

    def test_a_group_that_does_not_start_on_its_joint_is_refused(self):
        """Catches a joint value read from a placement the joint cannot give, which would jump the group."""
        self.refused(lambda d: d["poses"]["up"]["arm"].append(RISE(5)) or d["motions"].update(lower={"from": "up", "drive": {"pivot": {"to": 0}}, "durationS": 0.5}),
                     '"lower"', '"pivot"', '"arm"')

    def test_a_driven_motion_states_its_duration(self):
        """Catches a motor-driven motion with no time, which the electrical load needs for acceleration."""
        self.refused(lambda d: d["motions"]["raise arm"].pop("durationS"), '"raise arm"', "durationS")

    def test_loads_running_beside_a_motion_are_checked(self):
        """Catches an extra load or a concurrent drive that names nothing real, or names a drive twice."""
        self.refused(lambda d: d["motions"]["raise arm"].update(alsoRunning=[{"drive": "drivetrain", "atLimit": True}]), '"raise arm"', '"drivetrain"')
        self.refused(lambda d: d["motions"]["raise arm"].update(alsoRunning=[{"drive": "pivot", "atLimit": True}]), '"raise arm"', '"pivot"')
        self.refused(lambda d: d["motions"]["raise arm"].update(extraLoad={"lift": ASSUMED(1.0, 0.5, 2.0)}), '"raise arm"', '"lift"')
        self.refused(lambda d: d["drives"]["lift"].pop("statorLimitA") or d["motions"]["raise arm"].update(alsoRunning=[{"drive": "lift", "atLimit": True}]),
                     '"raise arm"', '"lift"', "limit")
        build(load_data(bench(lambda d: d["motions"]["raise arm"].update(alsoRunning=[{"drive": "lift", "atLimit": True}],
                                                                         extraLoad={"pivot": ASSUMED(1.0, 0.5, 2.0)}))))     # control
        build(load_data(bench(lambda d: d["motions"]["push by hand"].update(alsoRunning=[{"drive": "lift", "currentA": ASSUMED(5, 2, 8)}]))))


class StatedCause(unittest.TestCase):
    def test_a_motion_with_no_drive_and_no_cause_is_refused(self):
        """Catches typed movement that nothing explains: no motor and no stated cause (acceptance 20)."""
        with self.assertRaises(DesignError) as caught:
            load_data(bench(lambda d: d["motions"]["push by hand"].pop("by")))
        self.assertIn('motions "push by hand"', str(caught.exception))
        self.assertIn('"by"', str(caught.exception))

    def test_a_hand_motion_with_typed_moves_is_accepted_and_commands_no_drive(self):
        """Control for the refusal above: a stated cause with typed geometry is a complete motion (acceptance 20)."""
        data = load_data(bench()).data
        self.assertEqual(placement.commands(data, "push by hand"), {})
        self.assertLess(mx.gap(placement.at_motion(data, "push by hand", 1.0)["carriage"], mx.translation((0, 0, 50))), 1e-9)

    def test_every_cause_word_is_accepted_and_others_are_not(self):
        """Catches a cause list that drops one of the four words or accepts a made-up one."""
        for word in ("hand", "spring", "gravity", "piece"):
            load_data(bench(lambda d: d["motions"]["push by hand"].update(by=word)))
        with self.assertRaises(DesignError):
            load_data(bench(lambda d: d["motions"]["push by hand"].update(by="magic")))

    def test_a_cause_on_a_driven_motion_names_typed_moves(self):
        """Catches a stated cause with nothing for it to explain."""
        with self.assertRaises(DesignError) as caught:
            load_data(bench(lambda d: d["motions"]["raise arm"].update(by="hand")))
        self.assertIn('"raise arm"', str(caught.exception))


def chained(change=None):
    """The bench with "set" (the carriage raised by hand, then the arm raised by its motor) and "tip" after it."""
    def add(d):
        d["motions"]["set"] = {"by": "hand", "moves": {"carriage": [RISE(300)]}}
        d["motions"]["raise after set"] = {"from": {"after": "set"}, "drive": {"pivot": {"to": 95}}, "durationS": 0.5}
        d["motions"]["tip"] = {"from": {"after": "raise after set"}, "drive": {"pivot": {"by": -45}}, "durationS": 0.5}
        d["poses"]["set and raised"] = {"carriage": [RISE(300)], "arm": [SWING(95)]}
        d["motions"]["tip from a pose"] = {"from": "set and raised", "drive": {"pivot": {"to": 50}}, "durationS": 0.5}
        if change:
            change(d)
    return bench(add)


class ChainedMotions(unittest.TestCase):
    def test_a_chained_start_equals_the_same_motion_from_a_pose_at_that_end(self):
        """Catches a chained start that loses a group, its carrier, or the earlier motion's own start (acceptance 14)."""
        data = load_data(chained()).data
        self.assertLess(farthest(data, "tip", data, "tip from a pose"), 1e-6)
        self.assertAlmostEqual(placement.commands(data, "tip")["pivot"]["to"], 50.0)     # "by" counts from where the chain left the joint
        self.assertGreater(farthest(data, "tip", data, "raise arm"), 1.0)      # control: a different start is seen

    def test_a_chain_that_loops_is_refused_naming_every_motion_in_it(self):
        """Catches motions that start after each other, which would never finish placing (acceptance 14)."""
        with self.assertRaises(DesignError) as caught:
            load_data(chained(lambda d: d["motions"]["set"].update({"from": {"after": "tip"}})))
        for name in ("set", "raise after set", "tip"):
            self.assertIn(name, str(caught.exception))
        with self.assertRaisesRegex(DesignError, '"lonely"'):
            load_data(bench(lambda d: d["motions"].update(lonely={"from": {"after": "lonely"}, "by": "hand", "moves": {"arm": [SWING(1)]}})))
        with self.assertRaisesRegex(DesignError, '"nowhere"'):
            load_data(bench(lambda d: d["motions"]["lift"].update({"from": {"after": "nowhere"}})))

    def test_a_chained_motion_must_still_end_at_its_stated_pose(self):
        """Catches "to" going unchecked once a motion starts after another."""
        load_data(chained(lambda d: d["motions"]["raise after set"].update(to="set and raised")))
        with self.assertRaisesRegex(DesignError, '"tip"'):
            build(load_data(chained(lambda d: d["motions"]["tip"].update(to="set and raised"))))


class ChainedRecords(unittest.TestCase):
    """A chained motion's records hold the start it resolved to, never the name of the motion it starts after."""

    JOBS = [{"kind": "clearance", "motion": "tip", "minGapMm": 1.0}, {"kind": "clearance", "motion": "set", "minGapMm": 1.0}]

    @classmethod
    def setUpClass(cls):
        cls.path = load_data(chained()).path
        cls.folder = tempfile.TemporaryDirectory()
        records.record(cls.path, cls.JOBS, cls.folder.name, workers=1)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def after(self, change):
        self.path.write_text(json.dumps(chained(change)), encoding="utf-8")
        try:
            return {row["record"]: row for row in status(self.path, self.folder.name)["records"]}
        finally:
            self.path.write_text(json.dumps(chained()), encoding="utf-8")

    def test_the_record_holds_the_resolved_start_and_the_joint_commands(self):
        """Catches a record that keeps the earlier motion's name, so it would go stale by name (acceptance 14)."""
        held = json.loads((Path(self.folder.name) / records.FOLDER / "clearance.motion.tip.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(held["used"]["start"]), ["arm", "carriage", "wrist"])
        self.assertLess(mx.gap(tuple(held["used"]["start"]["carriage"]), mx.translation((0, 0, 300))), 1e-9)
        self.assertEqual(held["used"]["joints"], {"arm": {"kind": "rotation", "from": 95.0, "to": 50.0}})
        self.assertNotIn("raise after set", json.dumps([held["job"], held["inputs"], held["used"]]))

    def test_an_earlier_motion_whose_end_moves_makes_the_later_one_stale(self):
        """Catches a chained motion left current after the place it starts from moved (acceptance 14)."""
        rows = self.after(lambda d: d["motions"]["set"]["moves"]["carriage"][0].update(travelMm=[0, 0, 250]))
        self.assertEqual(rows["clearance.motion.tip"]["state"], "stale")
        self.assertIn('start "carriage" changed', " ".join(rows["clearance.motion.tip"]["changes"]))

    def test_an_earlier_motion_changed_on_the_way_but_not_at_its_end_leaves_the_later_one_current(self):
        """Control: the later motion decides from where the earlier one ends, never from how it got there (acceptance 14)."""
        bent = {"kind": "path", "curve": "straight", "throughMm": [[0, 0, 0], [80, 0, 150], [0, 0, 300]]}
        rows = self.after(lambda d: d["motions"]["set"]["moves"].update(carriage=[bent]))
        self.assertEqual(rows["clearance.motion.set"]["state"], "stale")       # the earlier motion itself did change
        self.assertEqual((rows["clearance.motion.tip"]["state"], rows["clearance.motion.tip"]["changes"]), ("current", []))

    def test_a_command_that_ends_elsewhere_makes_the_record_stale(self):
        """Catches a joint command change that the record does not see."""
        rows = self.after(lambda d: d["motions"]["tip"]["drive"]["pivot"].update(by=-40))
        self.assertEqual(rows["clearance.motion.tip"]["state"], "stale")
        self.assertIn('joints "arm" changed', " ".join(rows["clearance.motion.tip"]["changes"]))


class CommandLine(unittest.TestCase):
    def test_validate_refuses_a_command_past_the_travel_without_building(self):
        """Catches a joint limit that only the full build would find."""
        path = load_data(bench()).path
        path.write_text(json.dumps(bench(lambda d: d["motions"]["raise arm"]["drive"]["pivot"].update(to=130))), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertNotEqual(main(["validate", str(path)]), 0)
        self.assertIn("travel", err.getvalue())


if __name__ == "__main__":
    unittest.main()
