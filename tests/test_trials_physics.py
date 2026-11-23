"""The planar solver against closed-form answers: flight, friction thresholds under both laws, a belt, a flap, a bounce."""
import math
import unittest

import frc_design_kernel as kernel
from frc_design_kernel.kernel.section import outlines, signed_area
from frc_design_kernel.kernel import booleans, shapes
from frc_design_kernel.trials import planar, scene

from .helpers import load_data
from .trial_cases import G, PANEL, bench, hold_trial, on_slope

STOP_LOW = [{"name": "landed", "when": {"signal": "zMm", "below": 0}, "outcome": "landed"}]


def run(trial, parameters=None, **design):
    loaded = load_data(bench({"case": trial}, **design))
    if parameters:
        loaded = kernel.load(loaded.path, parameters)
    return planar.run(scene.build(kernel.build(loaded), "case", loaded.data["trials"]["case"]))


def base(**fields):
    trial = {"plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 2.0, "traceS": 0.002, "materials": {"panel": dict(PANEL)},
             "surfaces": [], "events": [], "pass": {"outcomes": ["timeout"]},
             "piece": {"radiusMm": 20, "massKg": 0.5, "start": {"atMm": [0, 1000]}}}
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


class ClosedForm(unittest.TestCase):
    def test_free_flight_follows_the_parabola(self):
        """Catches a wrong gravity, a wrong integration order or a wrong unit: a thrown piece must land where the formula says."""
        found = run(base(piece={"radiusMm": 20, "massKg": 0.5, "start": {"atMm": [0, 1000], "velocityMps": [2, 3], "spinRadps": 7}},
                         events=STOP_LOW, measures={"landS": {"timeOf": "landed"}, "landX": {"final": "xMm"}, "spin": {"final": "spinRadps"}}))
        time = (3 + math.sqrt(9 + 2 * G * 1.0)) / G
        self.assertEqual(found["outcome"], "landed")
        self.assertAlmostEqual(found["measures"]["landS"], time, delta=3e-4)
        self.assertAlmostEqual(found["measures"]["landX"], 2000 * time, delta=1.0)
        self.assertEqual(found["measures"]["spin"], 7)

    def test_stick_friction_holds_below_the_threshold_and_slides_above_it(self):
        """Catches a stick law that creeps on a slope it should hold on, or slides at the wrong rate above the threshold."""
        held = run(hold_trial("stick", 0.5, 20))
        self.assertEqual(held["outcome"], "held")
        self.assertAlmostEqual(held["measures"]["endX"], on_slope(300, 20, 20, 2000 * math.tan(math.radians(20)))[0], delta=0.5)      # within the stick spring's stretch
        self.assertAlmostEqual(held["measures"]["push"], G * math.cos(math.radians(20)), delta=0.5)      # the block's weight on the slope
        sliding = run(hold_trial("stick", 0.5, 30), {"slope_deg": 30})
        rate = G * (math.sin(math.radians(30)) - 0.5 * math.cos(math.radians(30)))
        self.assertEqual(sliding["outcome"], "slid")
        self.assertAlmostEqual(slide_rate(sliding), rate, delta=0.01 * rate)

    def test_smooth_friction_creeps_at_the_known_rate_and_slides_the_same_above(self):
        """Catches a smooth law with the wrong easing: below the threshold it must creep at eps * tan / sqrt(mu^2 - tan^2)."""
        trial = hold_trial("smooth", 0.5, 20, duration=2.0)
        trial["events"], trial["measures"] = [], {"endX": {"final": "xMm"}}
        creeping = run(trial)
        tan = math.tan(math.radians(20))
        speed = 0.01 * tan / math.sqrt(0.5 ** 2 - tan ** 2)
        travel = (creeping["measures"]["endX"] - on_slope(300, 20, 20, 2000 * tan)[0]) / math.cos(math.radians(20))
        self.assertAlmostEqual(travel, speed * 2.0 * 1000, delta=0.6)
        sliding = run(hold_trial("smooth", 0.5, 30), {"slope_deg": 30})
        rate = G * (math.sin(math.radians(30)) - 0.5 * math.cos(math.radians(30)))
        self.assertAlmostEqual(slide_rate(sliding), rate, delta=0.01 * rate)

    def belt(self, inertia, law):
        piece = {"radiusMm": 20, "massKg": 0.5, "start": {"atMm": [0, -480]}, **inertia}
        return run(base(piece=piece, durationS=1.5, materials={"panel": {**PANEL, "law": law}},
                        surfaces=[{"name": "belt", "solid": "belt bed", "material": "panel", "speedMps": 2.0}],
                        measures={"x": {"final": "xMm"}, "spin": {"final": "spinRadps"}}))

    def test_a_belt_brings_a_piece_to_its_surface_speed(self):
        """Catches a moving surface that drags the wrong way or by the wrong amount, under both friction laws."""
        for law in ("stick", "smooth"):
            block = self.belt({"inertiaKgM2": 1e6}, law)
            vx = block["end"]["piece"][2]
            self.assertAlmostEqual(vx, -2.0, delta=0.02, msg=law)       # the top of a counter-clockwise outline runs toward -X
            disc = self.belt({"inertiaFactor": 0.5}, law)
            vx, spin = disc["end"]["piece"][2], disc["end"]["piece"][4]
            self.assertAlmostEqual(vx, -2.0 * 0.5 / 1.5, delta=0.02, msg=law)                    # a solid disc ends at a third of the belt speed
            self.assertAlmostEqual(vx + spin * 0.02, -2.0, delta=0.03, msg=law)                  # and its rim matches the belt

    def test_a_sprung_flap_settles_where_statics_says(self):
        """Catches a flap whose spring, arm or contact torque is wrong: a weight on it must settle at the balance angle."""
        weight, stiffness, radius, reach = 0.5 * G, 5.0, 0.02, 0.1
        low, high = 0.0, 0.5
        for _ in range(60):
            mid = (low + high) / 2
            low, high = (mid, high) if weight * (reach - radius * math.sin(mid)) / math.cos(mid) ** 2 > stiffness * mid else (low, mid)
        smooth = {**PANEL, "friction": 0.0}
        found = run(base(durationS=3.0, materials={"panel": smooth},
                         piece={"radiusMm": 20, "massKg": 0.5, "start": {"atMm": [-100, 20]}},
                         surfaces=[{"name": "wall", "material": "panel", "segmentsMm": [[-120, -200], [-120, 200]]},
                                   {"name": "wall 2", "material": "panel", "segmentsMm": [[-80, -200], [-80, 200]]}],
                         flaps=[{"name": "flap", "material": "panel", "hingeMm": [0, 0], "lengthMm": 200, "restDirection": [-1, 0],
                                 "inertiaKgM2": 1e-3, "springNmPerRad": stiffness, "dampingNmSPerRad": 0.05, "limitDeg": 60}],
                         measures={"angle": {"final": "hinge.flap.angleDeg"}, "most": {"peak": "hinge.flap.angleDeg"}}))
        self.assertAlmostEqual(found["measures"]["angle"], math.degrees(low), delta=0.06)
        self.assertGreater(found["measures"]["most"], found["measures"]["angle"])       # it swings past, then settles back

    def test_a_bounce_gives_back_less_than_it_got(self):
        """Catches a contact law that creates energy: after a bounce the piece must rise to about e * e of its drop, never more."""
        found = run(base(durationS=1.0, traceS=0.0005, materials={"panel": {**PANEL, "restitution": 0.5}},
                         piece={"radiusMm": 20, "massKg": 0.5, "start": {"atMm": [0, 220]}},
                         surfaces=[{"name": "floor", "material": "panel", "segmentsMm": [[-500, 0], [500, 0]]}]))
        heights = [row[2] - 20 for row in found["trace"]["rows"]]
        first_low = next(i for i, h in enumerate(heights) if h <= 0)
        rise_start = next(i for i in range(first_low, len(heights)) if heights[i] > 0)
        next_low = next(i for i in range(rise_start, len(heights)) if heights[i] <= 0)
        rebound = max(heights[rise_start:next_low])
        self.assertLess(rebound, 200.0)
        # The spring never pulls, so the contact lets go a little early and keeps a little more than e * e of the drop.
        self.assertTrue(0.5 ** 2 * 200 <= rebound <= 1.3 * 0.5 ** 2 * 200, rebound)
        self.assertLess(max(heights[first_low:]), 200.0)


class Drives(unittest.TestCase):
    MOTOR = {"ktNmPerA": 0.02, "ohm": 0.1, "keVsPerRad": 0.02}

    def spin_up(self, **drive):
        base_drive = {"kind": "motor", "motor": self.MOTOR, "gear": 2.0, "radiusMm": 25, "inertiaKgM2": 2e-4, "statorLimitA": 40, "busV": 12.0, **drive}
        return run(base(durationS=1.0, drives={"wheel": base_drive},
                        measures={"speed": {"final": "drive.wheel.speedMps"}, "amps": {"peak": "drive.wheel.currentA"}, "supply": {"peak": "drive.wheel.supplyA"}}))

    def test_a_motor_on_voltage_reaches_its_free_speed_within_its_current_limit(self):
        """Catches a wrong back-EMF, gear or current limit: an unloaded motor must settle where back-EMF equals the bus."""
        found = self.spin_up(control={"mode": "voltage"})
        self.assertAlmostEqual(found["measures"]["speed"], 12.0 / 0.02 / 2.0 * 0.025, delta=0.01)
        self.assertAlmostEqual(found["measures"]["amps"], 40.0, delta=1e-9)

    def test_a_speed_loop_holds_its_setpoint_and_respects_the_supply_limit(self):
        """Catches a speed loop that overshoots, or a supply limit that lets through more power than bus * limit."""
        found = self.spin_up(control={"mode": "speed", "setpointMps": 3.0, "band": 0.02}, supplyLimitA=10.0)
        self.assertAlmostEqual(found["measures"]["speed"], 3.0, delta=0.06)
        self.assertLessEqual(found["measures"]["supply"], 10.0 + 1e-9)

    def test_power_off_coasts_and_shorted_windings_brake(self):
        """Catches the two unpowered states being confused: off must keep spinning, shorted must stop."""
        coast = self.spin_up(control={"mode": "voltage"}, busV=None, startMps=5.0)
        brake = self.spin_up(control={"mode": "voltage"}, busV=0.0, startMps=5.0)
        self.assertAlmostEqual(coast["measures"]["speed"], 5.0, delta=1e-9)
        self.assertLess(abs(brake["measures"]["speed"]), 0.01)

    def test_a_rule_changes_the_command_after_an_event_and_a_delay(self):
        """Catches controller rules that fire early, late or not at all: the wheel is told to stop 0.2 s after the half-second mark."""
        rule = {"when": {"after": "half", "delayS": 0.2}, "set": {"busV": 0.0, "control": {"mode": "voltage"}}}
        found = run(base(durationS=1.0, drives={"wheel": {"kind": "motor", "motor": self.MOTOR, "gear": 2.0, "radiusMm": 25, "inertiaKgM2": 2e-4,
                                                           "statorLimitA": 40, "busV": 12.0, "control": {"mode": "voltage"}, "rules": [rule]}},
                         events=[{"name": "half", "when": {"signal": "tS", "above": 0.5}}],
                         measures={"speed": {"final": "drive.wheel.speedMps"}}))
        rows = {round(row[0], 2): row[found["trace"]["columns"].index("drive.wheel.speedMps")] for row in found["trace"]["rows"]}
        self.assertGreater(rows[0.69], 7.0)
        self.assertLess(abs(found["measures"]["speed"]), 0.05)


if __name__ == "__main__":
    unittest.main()
