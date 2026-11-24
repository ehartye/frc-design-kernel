"""The battery and the electrical measure: each driven motion's torque, current and motor voltage per drive, and the
bus voltage under every drive that runs.

The design is an invented arm bench: an arm bar swung about a pivot by a geared motor, a carriage lifted on a belt by a
second motor, and four wheel motors standing for a drivetrain. Each closed form below is worked out by hand from the
fixture's numbers, so a lever arm in the wrong unit, a gear applied the wrong way, a sag summed wrongly or a record
that misses a change shows up as a difference.
"""
import copy
import math
import tempfile
import unittest

from frc_design_kernel import DesignError
from frc_design_kernel.builder.assembly import build
from frc_design_kernel.measure import electrical, mass, records, summary
from frc_design_kernel.source.load import load

from .helpers import job_files, load_data, recorded

ASSUMED = lambda value, low, high: {"value": value, "assumed": [low, high]}
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
G = 9.80665
PIVOT = [0, 0, 500]
RADIUS_MM = 300.0           # the arm bar's centre from the pivot line
ARM_KG = 2.0
CARRIAGE_KG = 3.0
KT, OHM, KE = (0.02, 0.019, 0.021), (0.05, 0.045, 0.06), (0.02, 0.019, 0.021)     # (value, low, high)
EFFICIENCY = (0.9, 0.85, 0.95)
VOC, RESISTANCE = (12.6, 12.2, 12.9), (0.02, 0.015, 0.03)
DURATION = (0.5, 0.4, 0.7)
RAISE = {"kind": "electrical", "motion": "raise"}

BENCH = {
    "schema": "frc-design-kernel/design@1", "name": "Arm bench", "units": {"length": "mm", "mass": "kg"},
    "groups": {"base": {"role": "structure"}, "arm": {"role": "mechanism", "carriedBy": "base"},
               "carriage": {"role": "mechanism", "carriedBy": "base"}},
    "solids": [
        {"name": "base plate", "group": "base", "massKg": 5.0, "shape": BOX([-400, -100, 0], [400, 100, 20])},
        {"name": "arm motor", "group": "base", "massKg": 0.5, "shape": BOX([-60, 40, 470], [-20, 80, 530])},
        {"name": "lift motor", "group": "base", "massKg": 0.5, "shape": BOX([-360, -80, 20], [-320, -40, 80])},
        {"name": "wheel motor", "group": "base", "massKg": 0.5, "shape": BOX([-300, 40, 20], [-260, 80, 60])},
        {"name": "arm bar", "group": "arm", "massKg": ARM_KG, "note": "A bar standing for the arm.",
         "shape": BOX([RADIUS_MM - 20, -10, 490], [RADIUS_MM + 20, 10, 510])},
        {"name": "carriage block", "group": "carriage", "massKg": CARRIAGE_KG, "shape": BOX([-200, -40, 40], [-160, 40, 80])},
    ],
    "motors": {"small": {"ktNmPerA": ASSUMED(*KT), "ohm": ASSUMED(*OHM), "keVsPerRad": ASSUMED(*KE)}},
    "drives": {
        "pivot": {"motor": "small", "motorSolid": "arm motor", "gear": 60, "efficiency": ASSUMED(*EFFICIENCY), "supplyLimitA": 40,
                  "joint": {"group": "arm", "kind": "rotation", "axis": [0, -1, 0], "originMm": PIVOT, "travel": [-10, 120]}},
        "lift": {"motor": "small", "motorSolid": "lift motor", "gear": 10, "statorLimitA": 60,
                 "joint": {"group": "carriage", "kind": "slide", "axis": [0, 0, 1], "perOutputTurn": 100, "travel": [0, 400]}},
        "wheels": {"motor": "small", "motorSolid": "wheel motor", "count": 4, "gear": 6, "radiusMm": 50, "movingKg": ASSUMED(50, 45, 60),
                   "supplyLimitA": 40},
    },
    "battery": {"openCircuitV": ASSUMED(*VOC), "resistanceOhm": ASSUMED(*RESISTANCE), "note": "An invented pack."},
    "motions": {
        "raise": {"drive": {"pivot": {"to": 30}}, "durationS": ASSUMED(*DURATION), "note": "Up to the hold angle."},
        "lift": {"drive": {"lift": {"by": 300}}, "durationS": ASSUMED(0.8, 0.6, 1.0)},
        "push by hand": {"by": "hand", "moves": {"carriage": [{"kind": "translation", "travelMm": [0, 0, 50]}]},
                         "alsoRunning": [{"drive": "wheels", "atLimit": True}]},
        "nudge by hand": {"by": "hand", "moves": {"carriage": [{"kind": "translation", "travelMm": [0, 0, 20]}]}},
    },
}


def bench(change=None):
    data = copy.deepcopy(BENCH)
    if change:
        change(data)
    return data


def solid(data, name):
    return next(entry for entry in data["solids"] if entry["name"] == name)


def measured(change=None, motion="raise", samples=32):
    """The electrical measure of one motion of the bench after change."""
    return electrical.measured(build(load(load_data(bench(change)).path)), motion, samples)


def close(test, found, wanted, relative=1e-6):
    test.assertLessEqual(abs(found - wanted), relative * abs(wanted), f"{found} is not {wanted}")


def ends(item):
    return [item["value"], *item["range"]]


class ClosedForm(unittest.TestCase):
    def test_an_arm_holding_at_an_angle_needs_m_g_r_cos_theta_and_that_over_kt_gear_efficiency(self):
        """Catches a lever arm in the wrong unit, a wrong angle, or a gear or efficiency applied the wrong way (acceptance 11)."""
        pivot = measured()["drives"]["pivot"]
        torque = ARM_KG * G * RADIUS_MM / 1000 * math.cos(math.radians(30))
        self.assertEqual(pivot["load"]["unit"], "N m")
        for found in ends(pivot["load"]["hold"]):
            close(self, found, torque)       # every mass is exact, so the hold has no range
        close(self, pivot["holdA"]["value"], torque / (KT[0] * 60 * EFFICIENCY[0]))
        close(self, pivot["holdA"]["range"][0], torque / (KT[2] * 60 * EFFICIENCY[2]))
        close(self, pivot["holdA"]["range"][1], torque / (KT[1] * 60 * EFFICIENCY[1]))
        close(self, pivot["load"]["gravity"]["value"], ARM_KG * G * RADIUS_MM / 1000)       # the worst is level, where it starts

    def test_count_motors_share_the_load(self):
        """Catches a drive of several motors charged the whole current per motor."""
        one = measured()["drives"]["pivot"]
        two = measured(lambda d: d["drives"]["pivot"].update(count=2))["drives"]["pivot"]
        close(self, two["holdA"]["value"], one["holdA"]["value"] / 2)
        close(self, two["busA"]["value"], one["busA"]["value"])

    def test_a_slide_lifting_a_carriage_needs_its_weight_through_the_pulley(self):
        """Catches a slide's force not turned into a torque through perOutputTurn, or mm taken for m."""
        lift = measured(motion="lift")["drives"]["lift"]
        force = CARRIAGE_KG * G
        self.assertEqual(lift["load"]["unit"], "N")
        close(self, lift["load"]["hold"]["value"], force)
        close(self, lift["holdA"]["value"], force * 0.100 / (2 * math.pi) / (KT[0] * 10))

    def test_a_level_swing_needs_inertia_times_the_triangle_profile_acceleration(self):
        """Catches an acceleration, a peak speed or a motor voltage that does not follow the stated speed profile."""
        def level(d):
            d["drives"]["pivot"]["joint"]["axis"] = [0, 0, 1]
        found = measured(level)
        pivot = found["drives"]["pivot"]
        assembly = build(load(load_data(bench(level)).path))
        inertia = mass.inertia(assembly, ["arm"], [0, 0, 1], PIVOT)["kgM2"]
        close(self, inertia, ARM_KG * ((40 ** 2 + 20 ** 2) / 12 + RADIUS_MM ** 2) * 1e-6)
        alpha = 4 * math.radians(30) / DURATION[0] ** 2
        close(self, pivot["load"]["gravity"]["value"] + 1.0, 1.0)      # no gravity about an upright axis
        close(self, pivot["load"]["peak"]["value"], inertia * alpha)
        close(self, pivot["load"]["peak"]["range"][1], inertia * 4 * math.radians(30) / DURATION[1] ** 2)
        close(self, pivot["peakSpeed"]["value"], 2 * 30 / DURATION[0])
        current = inertia * alpha / (KT[0] * 60 * EFFICIENCY[0])
        close(self, pivot["neededA"]["value"], current)
        close(self, pivot["motorV"]["value"], current * OHM[0] + KE[0] * math.radians(2 * 30 / DURATION[0]) * 60)
        self.assertIn("triangle", found["profile"])

    def test_an_extra_load_adds_to_the_hold_and_the_peak(self):
        """Catches an extraLoad that is read but not added."""
        plain, loaded = measured()["drives"]["pivot"], measured(lambda d: d["motions"]["raise"].update(extraLoad={"pivot": ASSUMED(5, 3, 8)}))["drives"]["pivot"]
        close(self, loaded["load"]["hold"]["value"], plain["load"]["hold"]["value"] + 5)
        close(self, loaded["load"]["peak"]["range"][1], plain["load"]["peak"]["range"][1] + 8)
        close(self, loaded["load"]["extra"]["range"][0], 3)


class Clamped(unittest.TestCase):
    def test_a_current_past_the_limit_is_clamped_and_flagged(self):
        """Catches a drive charged more than its limit lets it draw, or a clamp that is not said."""
        pivot = measured(lambda d: d["drives"]["pivot"].update(supplyLimitA=1.0))["drives"]["pivot"]
        self.assertTrue(pivot["clamped"])
        self.assertEqual(pivot["limitA"], 1.0)
        self.assertEqual(pivot["currentA"]["range"][1], 1.0)
        self.assertGreater(pivot["neededA"]["range"][1], 1.0)

    def test_control_a_current_inside_the_limit_is_not_flagged(self):
        """Control: the clamp flag can be false."""
        pivot = measured()["drives"]["pivot"]
        self.assertFalse(pivot["clamped"])
        self.assertEqual(pivot["currentA"], pivot["neededA"])


class Sag(unittest.TestCase):
    def test_the_bus_is_the_open_circuit_voltage_less_the_current_times_the_resistance_at_each_end(self):
        """Catches a sag with the ends of the pack crossed, or a current left out of the sum (acceptance 11)."""
        found = measured()
        amps = found["drives"]["pivot"]["busA"]
        self.assertEqual(found["bus"]["loadA"], amps)
        close(self, found["bus"]["volts"]["value"], VOC[0] - amps["value"] * RESISTANCE[0])
        close(self, found["bus"]["volts"]["range"][0], VOC[1] - amps["range"][1] * RESISTANCE[2])
        close(self, found["bus"]["volts"]["range"][1], VOC[2] - amps["range"][0] * RESISTANCE[1])
        self.assertIn("conservative", found["conservative"])

    def test_a_lighter_arm_draws_less_current(self):
        """Control: a lighter moved group lowers the current and raises the bus (acceptance 11)."""
        heavy, light = measured(), measured(lambda d: solid(d, "arm bar").update(massKg=1.0))
        self.assertLess(light["drives"]["pivot"]["currentA"]["range"][1], heavy["drives"]["pivot"]["currentA"]["range"][1])
        self.assertLess(light["drives"]["pivot"]["currentA"]["value"], heavy["drives"]["pivot"]["currentA"]["value"])
        self.assertGreater(light["bus"]["volts"]["range"][0], heavy["bus"]["volts"]["range"][0])

    def test_a_drivetrain_also_running_at_its_limit_lowers_the_bus_by_its_limit_current_times_r(self):
        """Control: a drive running beside the motion is in the load, at count times its limit (acceptance 11)."""
        alone = measured()
        beside = measured(lambda d: d["motions"]["raise"].update(alsoRunning=[{"drive": "wheels", "atLimit": True}]))
        self.assertEqual(beside["alsoRunning"], [{"drive": "wheels", "from": "atLimit", "busA": {"value": 160.0, "range": [160.0, 160.0]}}])
        close(self, beside["bus"]["volts"]["value"], alone["bus"]["volts"]["value"] - 160 * RESISTANCE[0])
        close(self, beside["bus"]["volts"]["range"][0], alone["bus"]["volts"]["range"][0] - 160 * RESISTANCE[2])
        close(self, beside["bus"]["volts"]["range"][1], alone["bus"]["volts"]["range"][1] - 160 * RESISTANCE[1])

    def test_a_motion_no_motor_drives_loads_the_bus_with_what_it_lists_as_also_running(self):
        """Catches a hand-moved motion whose running drivetrain is not counted."""
        found = measured(motion="push by hand")
        self.assertEqual(found["drives"], {})
        self.assertEqual(found["bus"]["loadA"], {"value": 160.0, "range": [160.0, 160.0]})

    def test_a_design_with_no_battery_states_no_bus(self):
        """Catches a bus voltage made up when the design gives no battery."""
        found = measured(lambda d: d.pop("battery"))
        self.assertIsNone(found["bus"])
        self.assertIn("currentA", found["drives"]["pivot"])


class Refusals(unittest.TestCase):
    def test_a_motion_with_no_load_has_no_electrical_job(self):
        """Catches an electrical job asked of a motion nothing powers."""
        design = load_data(bench())
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(DesignError) as caught:
            recorded(design, [{"kind": "electrical", "motion": "nudge by hand"}], folder)
        self.assertIn("nudge by hand", str(caught.exception))

    def test_a_battery_is_checked(self):
        """Catches a battery with no source, a nonsense value or a missing figure."""
        for change, words in ((lambda d: d["battery"].update(resistanceOhm={"value": 0.02}), "resistanceOhm"),
                              (lambda d: d["battery"].update(openCircuitV=ASSUMED(12, -1, 13)), "openCircuitV"),
                              (lambda d: d["battery"].pop("openCircuitV"), "openCircuitV")):
            with self.assertRaises(DesignError) as caught:
                load_data(bench(change))
            self.assertIn(words, str(caught.exception))

    def test_the_bench_itself_is_accepted(self):
        """Control: the checks above refuse only what is wrong."""
        self.assertIn("battery", load_data(bench()).data)


class Records(unittest.TestCase):
    """One electrical job per motion, recorded."""

    def test_the_job_file_holds_its_question_and_its_result(self):
        """Catches an electrical record that a judging tool cannot read."""
        with tempfile.TemporaryDirectory() as folder:
            recorded(load_data(bench()), [RAISE], folder)
            held = job_files(folder)["electrical.raise"]
        self.assertEqual((held["schema"], held["id"]), (records.SCHEMA, "electrical.raise"))
        self.assertEqual(held["job"], {"kind": "electrical", "motion": "raise", "samples": 32})
        self.assertEqual(held["result"], measured())

    def test_another_battery_another_motor_or_a_heavier_arm_gives_another_answer(self):
        """Catches an electrical result that leaves out the battery, the motor or the weight it lifts."""
        plain = measured()
        for change in (lambda d: solid(d, "arm bar").update(massKg=ASSUMED(2.0, 1.8, 2.4)),
                       lambda d: d["battery"].update(resistanceOhm=ASSUMED(0.02, 0.015, 0.035)),
                       lambda d: d["motors"]["small"].update(ohm=ASSUMED(0.05, 0.045, 0.07)),
                       lambda d: d["motions"]["raise"].update(durationS=ASSUMED(0.5, 0.3, 0.7)),
                       lambda d: d["motions"]["raise"].update(alsoRunning=[{"drive": "wheels", "atLimit": True}]),
                       lambda d: d["drives"]["pivot"].update(gear=70)):
            self.assertNotEqual(measured(change), plain)

    def test_control_a_note_and_weight_the_motion_does_not_move_give_the_same_answer(self):
        """Control: a note, or the mass of a solid the motion does not move, changes no figure."""
        for change in (lambda d: d["battery"].update(note="Another pack note."), lambda d: solid(d, "base plate").update(massKg=7.0)):
            self.assertEqual(measured(change), measured())


class MeasureCommand(unittest.TestCase):
    def test_the_measure_command_asks_one_electrical_job_per_powered_motion(self):
        """Catches a powered motion with no electrical record, or one asked of a motion nothing powers."""
        data = load_data(bench()).data
        jobs = summary.design_jobs(data)
        self.assertEqual(sorted(job["motion"] for job in jobs if job["kind"] == "electrical"), ["lift", "push by hand", "raise"])
        self.assertEqual([job for job in summary.design_jobs(data, motions=["nudge by hand"]) if job["kind"] == "electrical"], [])


if __name__ == "__main__":
    unittest.main()
