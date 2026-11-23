"""The planar solver against closed-form answers: flight, friction thresholds under both laws, a belt, a flap, a bounce."""
import math
import unittest

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.kernel import booleans, shapes
from frc_design_kernel.kernel.section import outlines, signed_area
from frc_design_kernel.trials import inputs, planar, scene

from .helpers import load_data
from .trial_cases import G, MEASURED, PANEL, bench, hold_trial, on_slope

STOP_LOW = [{"name": "landed", "when": {"signal": "zMm", "below": 0}, "outcome": "landed"}]
MOTOR = {"ktNmPerA": MEASURED(0.02), "ohm": MEASURED(0.1), "keVsPerRad": MEASURED(0.02)}
WHEEL = {"motor": "small", "gear": 2.0, "radiusMm": 25, "inertiaKgM2": MEASURED(2e-4), "statorLimitA": 40}


def run(trial, parameters=None, **design):
    loaded = load_data(bench({"case": trial}, **design))
    if parameters:
        loaded = kernel.load(loaded.path, parameters)
    built = scene.build(kernel.build(loaded), "case", inputs.case(loaded.data, loaded.data["trials"]["case"]))
    built.pop("facts")
    return planar.run(built)


def base(piece="ball", start=None, **fields):
    trial = {"plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 2.0, "traceS": 0.002, "surfaces": [], "events": [],
             "pass": {"outcomes": ["timeout"]}, "piece": {"use": piece, "start": start or {"atMm": [0, 1000]}}}
    trial.update(fields)
    return trial


def slide_rate(found):
    """The piece's acceleration along its path in m/s2, from its speed at 0.2 s and 0.4 s of the trace."""
    rows = {round(row[0], 2): row for row in found["trace"]["rows"]}
    speed = lambda t: math.dist(rows[round(t + 0.01, 2)][1:3], rows[round(t - 0.01, 2)][1:3]) / 0.02 / 1000
    return (speed(0.4) - speed(0.2)) / 0.2


class Sections(unittest.TestCase):
    def test_outlines_run_counter_clockwise_with_holes_the_other_way(self):
        """Catches a surface that runs backwards, which would drive a piece the wrong way on a belt."""
        tube = shapes.round_tube([0, -10, 0], [0, 10, 0], 60, 5)
        outer, hole = outlines(tube, "y", 0)
        self.assertAlmostEqual(signed_area(outer), 2 * math.pi * 30 ** 2, places=6)
        self.assertAlmostEqual(signed_area(hole), -2 * math.pi * 25 ** 2, places=6)
        belt = booleans.union([shapes.box([0, -10, 0], [37, 10, 100]), shapes.cylinder([18.5, -10, 0], [18.5, 10, 0], 18.5),
                               shapes.cylinder([18.5, -10, 100], [18.5, 10, 100], 18.5)])
        loop, = outlines(belt, "y", 0)
        self.assertEqual(sorted(p["kind"] for p in loop), ["arc", "arc", "arc", "segment", "segment"])
        self.assertAlmostEqual(signed_area(loop) / 2, 37 * 100 + math.pi * 18.5 ** 2, places=6)
        self.assertEqual(outlines(tube, "y", 500), [])


class OnePieceInThreeDimensions(unittest.TestCase):
    def section(self, shape, normal="y"):
        return scene.piece_section("p", {"shape": shape}, normal, "test")

    def test_the_planar_section_follows_from_the_3d_piece(self):
        """Catches a wrong radius or inertia for the section of a ball, a bar or a tube, which the author no longer types."""
        self.assertEqual(self.section({"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 75}), (75, 0.4))
        self.assertEqual(self.section({"kind": "cylinder", "fromMm": [0, -100, 0], "toMm": [0, 100, 0], "radiusMm": 20}), (20, 0.5))
        radius, factor = self.section({"kind": "tube", "section": "round", "fromMm": [0, -150, 0], "toMm": [0, 150, 0], "outerDiameterMm": 100, "wallMm": 5})
        self.assertEqual(radius, 50)
        self.assertAlmostEqual(factor, (50 ** 2 + 45 ** 2) / (2 * 50 ** 2))

    def test_a_piece_the_plane_cannot_take_round_is_refused(self):
        """Catches a bar lying along the plane, or a box, being run as if it were round."""
        with self.assertRaisesRegex(DesignError, 'cannot take a round section of the piece "p" across x'):
            self.section({"kind": "cylinder", "fromMm": [0, -100, 0], "toMm": [0, 100, 0], "radiusMm": 20}, "x")
        with self.assertRaisesRegex(DesignError, "cannot take a round section"):
            self.section({"kind": "box", "fromMm": [0, 0, 0], "toMm": [1, 1, 1]})


class ClosedForm(unittest.TestCase):
    def test_free_flight_follows_the_parabola(self):
        """Catches a wrong gravity, a wrong integration order or a wrong unit: a thrown piece must land where the formula says."""
        found = run(base(start={"atMm": [0, 1000], "velocityMps": [2, 3], "spinRadps": 7}, events=STOP_LOW,
                         measures={"landS": {"timeOf": "landed"}, "landX": {"final": "xMm"}, "spin": {"final": "spinRadps"}}))
        time = (3 + math.sqrt(9 + 2 * G * 1.0)) / G
        self.assertEqual(found["outcome"], "landed")
        self.assertAlmostEqual(found["measures"]["landS"], time, delta=3e-4)
        self.assertAlmostEqual(found["measures"]["landX"], 2000 * time, delta=1.0)
        self.assertEqual(found["measures"]["spin"], 7)

    def test_stick_friction_holds_below_the_threshold_and_slides_above_it(self):
        """Catches a stick law that creeps on a slope it should hold on, or slides at the wrong rate above the threshold."""
        held = run(hold_trial("stick", 20))
        self.assertEqual(held["outcome"], "held")
        self.assertAlmostEqual(held["measures"]["endX"], on_slope(300, 20, 20, 2000 * math.tan(math.radians(20)))[0], delta=0.5)
        self.assertAlmostEqual(held["measures"]["push"], G * math.cos(math.radians(20)), delta=0.5)
        sliding = run(hold_trial("stick", 30), {"slope_deg": 30})
        rate = G * (math.sin(math.radians(30)) - 0.5 * math.cos(math.radians(30)))
        self.assertEqual(sliding["outcome"], "slid")
        self.assertAlmostEqual(slide_rate(sliding), rate, delta=0.01 * rate)

    def test_smooth_friction_creeps_at_the_known_rate_and_slides_the_same_above(self):
        """Catches a smooth law with the wrong easing: below the threshold it must creep at eps * tan / sqrt(mu^2 - tan^2)."""
        trial = hold_trial("smooth", 20, duration=2.0)
        trial["events"], trial["measures"] = [], {"endX": {"final": "xMm"}}
        creeping = run(trial)
        tan = math.tan(math.radians(20))
        speed = 0.01 * tan / math.sqrt(0.5 ** 2 - tan ** 2)
        travel = (creeping["measures"]["endX"] - on_slope(300, 20, 20, 2000 * tan)[0]) / math.cos(math.radians(20))
        self.assertAlmostEqual(travel, speed * 2.0 * 1000, delta=0.6)
        sliding = run(hold_trial("smooth", 30), {"slope_deg": 30})
        rate = G * (math.sin(math.radians(30)) - 0.5 * math.cos(math.radians(30)))
        self.assertAlmostEqual(slide_rate(sliding), rate, delta=0.01 * rate)

    def belt(self, piece, law):
        return run(base(piece, {"atMm": [0, -480]}, durationS=1.5, planar={"frictionLaw": law},
                        surfaces=[{"solid": "belt bed", "material": "panel", "speedMps": 2.0}]))

    def test_a_belt_brings_a_piece_to_its_surface_speed(self):
        """Catches a moving surface that drags the wrong way or by the wrong amount, under both friction laws."""
        for law in ("stick", "smooth"):
            vx = self.belt("block", law)["end"]["piece"][2]
            self.assertAlmostEqual(vx, -2.0, delta=0.02, msg=law)       # the top of a counter-clockwise outline runs toward -X
            disc = self.belt("bar", law)["end"]["piece"]
            self.assertAlmostEqual(disc[2], -2.0 * 0.5 / 1.5, delta=0.02, msg=law)               # a solid bar ends at a third of the belt speed
            self.assertAlmostEqual(disc[2] + disc[4] * 0.02, -2.0, delta=0.03, msg=law)          # and its rim matches the belt

    def test_a_sprung_flap_settles_where_statics_says(self):
        """Catches a flap whose spring, arm or contact torque is wrong: a weight on it must settle at the balance angle."""
        weight, stiffness, radius, reach = 0.5 * G, 5.0, 0.02, 0.1
        low, high = 0.0, 0.5
        for _ in range(60):
            mid = (low + high) / 2
            low, high = (mid, high) if weight * (reach - radius * math.sin(mid)) / math.cos(mid) ** 2 > stiffness * mid else (low, mid)
        found = run(base(start={"atMm": [-100, 20]}, durationS=3.0,
                         surfaces=[{"name": "wall", "material": "slick", "segmentsMm": [[-120, -200], [-120, 200]]},
                                   {"name": "wall 2", "material": "slick", "segmentsMm": [[-80, -200], [-80, 200]]}],
                         flaps=[{"name": "flap", "material": "slick", "hingeMm": [0, 0], "lengthMm": 200, "restDirection": [-1, 0],
                                 "inertiaKgM2": MEASURED(1e-3), "springNmPerRad": MEASURED(stiffness), "dampingNmSPerRad": MEASURED(0.05), "limitDeg": 60}],
                         measures={"angle": {"final": "hinge.flap.angleDeg"}, "most": {"peak": "hinge.flap.angleDeg"}}),
                    materials={"slick": {**PANEL, "friction": MEASURED(0.0)}})
        self.assertAlmostEqual(found["measures"]["angle"], math.degrees(low), delta=0.06)
        self.assertGreater(found["measures"]["most"], found["measures"]["angle"])       # it swings past, then settles back

    def test_a_bounce_gives_back_less_than_it_got(self):
        """Catches a contact law that creates energy: after a bounce the piece must rise to about e * e of its drop, never more."""
        found = run(base(start={"atMm": [0, 220]}, durationS=1.0, traceS=0.0005,
                         surfaces=[{"name": "floor", "material": "lively", "segmentsMm": [[-500, 0], [500, 0]]}]),
                    materials={"lively": {**PANEL, "restitution": MEASURED(0.5)}})
        heights = [row[2] - 20 for row in found["trace"]["rows"]]
        first_low = next(i for i, h in enumerate(heights) if h <= 0)
        rise_start = next(i for i in range(first_low, len(heights)) if heights[i] > 0)
        next_low = next(i for i in range(rise_start, len(heights)) if heights[i] <= 0)
        rebound = max(heights[rise_start:next_low])
        # The spring never pulls, so the contact lets go a little early and keeps a little more than e * e of the drop.
        self.assertTrue(0.5 ** 2 * 200 <= rebound <= 1.3 * 0.5 ** 2 * 200, rebound)
        self.assertLess(max(heights[first_low:]), 200.0)


class Drives(unittest.TestCase):
    MEASURES = {"speed": {"final": "drive.wheel.speedMps"}, "amps": {"peak": "drive.wheel.currentA"}, "supply": {"peak": "drive.wheel.supplyA"}}

    def spin_up(self, command, **drive):
        return run(base(durationS=1.0, commands={"wheel": command}, measures=self.MEASURES),
                   motors={"small": MOTOR}, drives={"wheel": {**WHEEL, **drive}})

    def test_a_motor_on_voltage_reaches_its_free_speed_within_its_current_limit(self):
        """Catches a wrong back-EMF, gear or current limit: an unloaded motor must settle where back-EMF equals the bus."""
        found = self.spin_up({"mode": "voltage", "busV": 12.0})
        self.assertAlmostEqual(found["measures"]["speed"], 12.0 / 0.02 / 2.0 * 0.025, delta=0.01)
        self.assertAlmostEqual(found["measures"]["amps"], 40.0, delta=1e-9)

    def test_a_speed_loop_holds_its_setpoint_and_respects_the_supply_limit(self):
        """Catches a speed loop that overshoots, or a supply limit that lets through more power than bus * limit."""
        found = self.spin_up({"mode": "speed", "setpointMps": 3.0, "band": 0.02, "busV": 12.0}, supplyLimitA=10.0)
        self.assertAlmostEqual(found["measures"]["speed"], 3.0, delta=0.06)
        self.assertLessEqual(found["measures"]["supply"], 10.0 + 1e-9)

    def test_power_off_coasts_and_shorted_windings_brake(self):
        """Catches the two unpowered states being confused: off must keep spinning, shorted must stop."""
        coast = self.spin_up({"mode": "voltage", "busV": None, "startMps": 5.0})
        brake = self.spin_up({"mode": "voltage", "busV": 0.0, "startMps": 5.0})
        self.assertAlmostEqual(coast["measures"]["speed"], 5.0, delta=1e-9)
        self.assertLess(abs(brake["measures"]["speed"]), 0.01)

    def test_a_rule_changes_the_command_after_an_event_and_a_delay(self):
        """Catches controller rules that fire early, late or not at all: the wheel is braked 0.2 s after the half-second mark."""
        command = {"mode": "voltage", "busV": 12.0, "rules": [{"when": {"after": "half", "delayS": 0.2}, "set": {"busV": 0.0}}]}
        found = run(base(durationS=1.0, commands={"wheel": command}, measures=self.MEASURES,
                         events=[{"name": "half", "when": {"signal": "tS", "above": 0.5}}]), motors={"small": MOTOR}, drives={"wheel": WHEEL})
        rows = {round(row[0], 2): row[found["trace"]["columns"].index("drive.wheel.speedMps")] for row in found["trace"]["rows"]}
        self.assertGreater(rows[0.69], 7.0)
        self.assertLess(abs(found["measures"]["speed"]), 0.05)

    def test_several_pieces_on_one_drive_load_it_that_many_times(self):
        """Catches a belt fed three pieces abreast being loaded as if by one: the motor must work three times as hard."""
        def peak(pieces):
            command = {"mode": "speed", "setpointMps": 2.0, "band": 0.02, "busV": 12.0, "startMps": 2.0, "piecesOnDrive": pieces}
            drive = {**WHEEL, "movingKg": MEASURED(2.0), "turns": [{"solid": "belt bed", "axis": [0, 1, 0]}]}
            drive.pop("inertiaKgM2")
            found = run(base("block", {"atMm": [0, -480]}, durationS=0.3, commands={"wheel": command}, surfaces=[{"solid": "belt bed", "material": "panel"}],
                             measures={"low": {"lowest": "drive.wheel.speedMps"}}), motors={"small": MOTOR}, drives={"wheel": drive})
            return 2.0 - found["measures"]["low"]
        self.assertAlmostEqual(peak(3) / peak(1), 3.0, delta=0.3)

    def roller(self, axis):
        drive = {"radiusMm": 25, "turns": [{"solid": "roller", "axis": axis}]}
        solids = bench({})["solids"] + [{"name": "roller", "group": "bench", "shape": {"kind": "cylinder", "fromMm": [0, -50, -525], "toMm": [0, 50, -525], "radiusMm": 25}}]
        found = run(base("block", {"atMm": [0, -480]}, durationS=1.0, commands={"spin": {"mode": "imposed", "speedMps": 1.0}},
                         surfaces=[{"solid": "roller", "material": "panel"}, {"name": "cage", "material": "panel", "segmentsMm": [[-21, -600], [-21, -400]]},
                                   {"name": "cage 2", "material": "panel", "segmentsMm": [[21, -400], [21, -600]]}],
                         measures={"left": {"peak": "contact.cage.forceN"}, "right": {"peak": "contact.cage 2.forceN"}}),
                    solids=solids, drives={"spin": drive})
        return found["measures"]

    def test_a_drive_declared_on_a_solid_runs_the_way_its_axis_says(self):
        """Catches the wrong run direction for a roller: by the right-hand rule about +Y its top moves toward +X, about -Y toward -X."""
        forward = self.roller([0, 1, 0])
        self.assertGreater(forward["right"], 1.0)
        self.assertEqual(forward["left"], 0.0)
        back = self.roller([0, -1, 0])
        self.assertGreater(back["left"], 1.0)
        self.assertEqual(back["right"], 0.0)


if __name__ == "__main__":
    unittest.main()
