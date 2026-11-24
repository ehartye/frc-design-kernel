"""Screen facts, adjustments and coverage, and the small things other tools asked for: each against a known answer."""
import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

import frc_design_kernel as kernel
from frc_design_kernel.cli import main
from frc_design_kernel.kernel import props
from frc_design_kernel.measure import clearance, extremes, records, run, screen, symmetry
from frc_design_kernel.motion import matrix as mx
from frc_design_kernel.trials import campaign

from .helpers import edited, load_data
from .trial_cases import PANEL, bench, tilting_trial

TAPER = ("from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone\nfrom OCP.gp import gp_Ax2, gp_Dir, gp_Pnt\n\n\ndef build(parameters):\n"
         "    return BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, -50, 0), gp_Dir(0, 1, 0)), 20.0, 30.0, 100.0).Shape()\n")
BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
TURN = lambda axis: {"kind": "rotation", "originMm": [0, 0, 0], "axis": axis, "travelDeg": 30}


def design():
    """A ball of radius 20 at the origin of a small rig: a tapered roller, a straight roller, a channel, a pad it is pressed into."""
    return {
        "schema": "frc-design-kernel/design@1", "name": "Screen rig", "units": {"length": "mm", "mass": "kg"},
        "parameters": {"gap": 3, "wall": "=20 + gap"},
        "groups": {"rig": {"role": "structure"}, "arm": {"role": "mechanism"}, "tilt": {"role": "mechanism"}, "piece": {"role": "payload"}},
        "custom": {"taper": {"reason": "A tapered roller is a cone; no listed shape makes one.", "limits": "Plain cone, no shaft or bearings."}},
        "solids": [
            {"name": "tapered roller", "group": "rig", "shape": {"kind": "custom", "use": "taper"}, "place": [{"kind": "translation", "travelMm": [0, 0, -60]}]},
            {"name": "straight roller", "group": "arm", "shape": {"kind": "cylinder", "fromMm": [80, -50, -60], "toMm": [80, 50, -60], "radiusMm": 25}},
            {"name": "wall left", "group": "rig", "shape": BOX([-40, "=wall", -40], [40, "=wall + 5", 40])},
            {"name": "wall right", "group": "rig", "shape": BOX([-40, "=-wall - 5", -40], [40, "=-wall", 40])},
            {"name": "pad", "group": "tilt", "material": {"class": "compliant", "stiffnessNPerM": {"value": 20000, "assumed": [10000, 40000]}},
             "shape": BOX([-30, -15, -40], [30, 15, -23])},
            {"name": "net", "group": "rig", "material": {"class": "flexible", "kind": "net"}, "shape": BOX([200, -50, 0], [205, 50, 100])},
            {"name": "drawn ball", "group": "piece", "shape": {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 20}},
        ],
        "pieces": {"ball": {"shape": {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 20}, "massKg": {"value": 0.2, "assumed": [0.18, 0.22]}},
                   "ring": {"shape": {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 150, "minorRadiusMm": 25}, "massKg": {"value": 0.24, "assumed": [0.2, 0.3]}},
                   "bar": {"shape": {"kind": "cylinder", "fromMm": [0, -100, 0], "toMm": [0, 100, 0], "radiusMm": 20}, "massKg": {"value": 0.5, "assumed": [0.4, 0.6]}},
                   "crate": {"shape": BOX([-50, -50, -50], [50, 50, 50]), "massKg": {"value": 1.0, "assumed": [0.8, 1.2]}}},
        "poses": {"home": {}},
        "motions": {"swing in plane": {"by": "hand", "from": "home", "moves": {"arm": [TURN([0, 1, 0])]}},
                    "swing out of plane": {"by": "hand", "from": "home", "moves": {"tilt": [TURN([1, 0, 0])]}},
                    "press": {"by": "piece", "from": "home", "moves": {"piece": [{"kind": "translation", "travelMm": [0, 0, -6]}]}}},
        "adjustments": {"channel gap": {"input": "parameters.gap", "kind": "mechanical", "range": [1, 8], "note": "Slotted wall mounts."}},
        "interactions": {
            "over the rollers": {"piece": "ball", "plane": {"normal": "y", "atMm": 0}, "solids": ["tapered roller", "straight roller", "pad"],
                                 "guides": ["wall left", "wall right", "net"], "pieceAtMm": [[0, 0, 0], [300, 0, 0]],
                                 "motions": ["swing in plane", "swing out of plane"], "pieceSolid": "drawn ball", "squeezeMotion": "press",
                                 "approach": {"angleDeg": [-10, 10], "offsetMm": [-15, 15]}, "targetOffPlane": True, "piecesAtOnce": 2},
        },
    }


class ScreenFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = kernel.build(load_data(design(), {"custom/taper.py": TAPER}))
        cls.facts = screen.facts(cls.assembly, "over the rollers")

    def piece_class(self, name):
        shape = screen.build_shape(self.assembly.data["pieces"][name]["shape"], "test", screen.no_custom)
        return symmetry.classify(shape, self.assembly.data["pieces"][name]["shape"]["kind"])

    def test_the_piece_symmetry_class_follows_its_3d_shape(self):
        """Catches a ring being called a sphere, a bar losing its axis, or a crate being called round."""
        self.assertEqual(self.piece_class("ball"), {"class": "sphere"})
        self.assertEqual(self.piece_class("ring"), {"class": "body of revolution", "axis": [0.0, 0.0, 1.0]})
        self.assertEqual(self.piece_class("bar"), {"class": "body of revolution", "axis": [0.0, 1.0, 0.0]})
        self.assertEqual(self.piece_class("crate"), {"class": "prismatic"})
        self.assertEqual(self.facts["piece"]["class"], "sphere")
        self.assertEqual((self.facts["piece"]["widthAcrossPlaneMm"], self.facts["piece"]["thicknessInPlaneMm"]), (40.0, 40.0))

    def test_a_tapered_roller_is_not_constant_across_the_width_and_a_straight_one_is(self):
        """Catches a taper passing as a plain roller: its radius grows 0.1 mm per mm, so 2 mm over the ball's half width."""
        taper, straight = self.facts["sections"]["tapered roller"], self.facts["sections"]["straight roller"]
        self.assertAlmostEqual(taper["largestDifferenceMm"], 2.0, places=3)
        self.assertEqual((abs(taper["atLevelMm"]), taper["curvedAcross"]), (20.0, ["a cone or taper"]))
        self.assertEqual((straight["largestDifferenceMm"], straight["curvedAcross"], straight["notCutAtLevelsMm"]), (0.0, [], []))

    def test_a_solid_that_ends_inside_the_width_is_reported(self):
        """Catches a narrow part (the pad is 30 wide, the ball 40) being treated as running the full width."""
        pad = self.facts["sections"]["pad"]
        self.assertEqual((pad["cutAtCentre"], pad["notCutAtLevelsMm"], pad["largestDifferenceMm"]), (True, [-20.0, 20.0], 0.0))

    def test_a_ball_in_a_channel_is_held_and_one_in_the_open_is_not(self):
        """Catches a wrong sideways gap (3 mm to each wall), or a guide being found where there is none."""
        held, loose = self.facts["sidewaysHold"]
        self.assertEqual((held["plus"]["solid"], held["minus"]["solid"]), ("wall left", "wall right"))
        self.assertAlmostEqual(held["plus"]["gapMm"], 3.0, places=6)
        self.assertAlmostEqual(held["minus"]["gapMm"], 3.0, places=6)
        self.assertEqual((loose["plus"], loose["minus"]), (None, None))

    def test_movements_that_leave_the_plane_are_listed(self):
        """Catches a hinge that is not square to the plane passing as planar, or a square one being flagged."""
        self.assertEqual(self.facts["mechanismOutOfPlane"],
                         [{"motion": "swing out of plane", "group": "tilt", "why": "turns about an axis that is not square to the plane"}])

    def test_a_path_that_turns_about_an_axis_not_square_to_the_plane_is_listed(self):
        """Catches a turning path passing as planar when its turn tips the body out of the plane; control: a square turn, either way round and of any axis length, is not listed."""
        def listed(axis):
            path = {"kind": "path", "curve": "straight", "throughMm": [[0, 0, 0], [100, 0, 0]], "turnDeg": [0, 30], "turnAxis": axis}
            design = load_data(edited(lambda d: d["motions"].update(follow={"by": "hand", "moves": {"slide": [path]}})))
            return [row["why"] for row in screen.out_of_plane(design.data, ["follow"], "y")]
        self.assertEqual(listed([0, 0, 1]), ["turns about an axis that is not square to the plane"])
        self.assertEqual((listed([0, 1, 0]), listed([0, -2, 0])), ([], []))     # either way round, any length

    def test_the_squeeze_ratio_is_the_deepest_press_over_the_thickness(self):
        """Catches a wrong ratio: the ball is pushed 6 mm down onto a pad whose top is 3 mm under it, so it ends 3 mm in, of 40."""
        squeeze = self.facts["squeeze"]
        self.assertEqual((squeeze["solid"], squeeze["t"], squeeze["thicknessMm"]), ("pad", 1.0, 40.0))
        self.assertAlmostEqual(squeeze["ratio"], 3.0 / 40.0, places=6)

    def test_what_is_not_rigid_and_what_geometry_cannot_know_are_echoed(self):
        """Catches a soft or flexible solid going unlisted, or the declared approach, target and piece count being dropped."""
        self.assertEqual([(row["solid"], row["class"]) for row in self.facts["notRigid"]], [("pad", "compliant"), ("net", "flexible")])
        self.assertEqual((self.facts["piecesAtOnce"], self.facts["targetOffPlane"], self.facts["approach"]),
                         (2, True, {"angleDeg": [-10, 10], "offsetMm": [-15, 15]}))

    def test_the_screen_command_prints_facts_and_writes_them(self):
        """Catches the command judging, or leaving a fact out of its one line."""
        text = io.StringIO()
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(text):
            self.assertEqual(main(["screen", str(self.assembly.design.path), "--out", out]), 0)
            written = json.loads((Path(out) / "screen.json").read_text(encoding="utf-8"))
        self.assertEqual(text.getvalue().splitlines()[0],
                         'Interaction "over the rollers": the piece "ball" is a sphere; sections differ across its width for tapered roller by 2.00 mm, pad (it ends inside the width); '
                         "2 sides unguided; 1 movement out of the plane; 2 pieces at once; squeeze 7.5% of its thickness; 2 solids not rigid.")
        self.assertEqual(written["interactions"]["over the rollers"]["piece"]["class"], "sphere")


class Adjustments(unittest.TestCase):
    def ends(self, workers=1, **asked):
        with run.Bench(load_data(design(), {"custom/taper.py": TAPER}), workers) as held:
            return extremes.at_extremes(held, min_gap=2.0, **asked)

    def test_clearance_is_known_at_both_ends_of_a_mechanical_adjustment(self):
        """Catches an adjustment whose far end fouls something going unseen: at a 1 mm gap the walls are 1 mm from the drawn ball."""
        found = self.ends()["channel gap"]
        tight, wide = found["settings"]
        self.assertEqual((found["parameter"], tight["setting"], wide["setting"]), ("gap", 1, 8))
        self.assertIn(["drawn ball", "wall left"], tight["poses"][0]["closer"])
        self.assertNotIn(["drawn ball", "wall left"], wide["poses"][0]["closer"])

    def test_workers_and_a_chosen_motion_give_the_same_answer(self):
        """Catches sharing the extremes between workers changing a result, or --motion and --pose being ignored."""
        alone = self.ends()
        self.assertEqual(alone, self.ends(workers=2))
        some = self.ends(motions=["press"], poses=["home"])["channel gap"]["settings"][0]
        self.assertEqual((list(some["motions"]), [p["pose"] for p in some["poses"]]), (["press"], ["home"]))
        self.assertEqual(some["motions"]["press"], alone["channel gap"]["settings"][0]["motions"]["press"])

    def tilting(self, low, high, **design_extra):
        trials = {"hold": tilting_trial(adjustments=["tilt"])}
        return campaign.run_campaign(load_data(bench(trials, adjustments={"tilt": {"input": "parameters.slope_deg", "kind": "mechanical", "range": [low, high], "step": 1}},
                                                     **design_extra)))

    def test_coverage_is_searched_only_for_an_input_that_changes_the_outcome(self):
        """Catches an adjustment's window being searched at both ends of an input that held across its range: runs spent on
        nothing. The bounce does not change whether the block holds; the friction does."""
        bouncy = {"panel": {**PANEL, "restitution": {"value": 0.2, "assumed": [0.1, 0.3]}}}
        found = self.tilting(8, 24, materials=bouncy)
        trial = found["trials"]["hold"]
        self.assertEqual([row["input"] for row in trial["coverage"]], ["materials.panel.friction"])
        self.assertTrue(next(r for r in trial["ranges"] if r["input"] == "materials.panel.restitution")["held"])
        self.assertEqual(trial["result"], "covered by adjustment")

    def test_an_adjustment_that_covers_the_uncertainty_is_reported_with_its_windows(self):
        """Catches a best guess being called a failure when the built robot can be set to pass at either end of the guess."""
        trial = self.tilting(8, 24)["trials"]["hold"]       # friction assumed 0.2 to 0.8; the slope can be set from 8 to 24 degrees
        row, = trial["coverage"]
        self.assertEqual(trial["result"], "covered by adjustment")
        self.assertEqual((row["atLow"]["passes"], row["atHigh"]["passes"]), ([8, 11], [8, 24]))      # tan(11.3 deg) = 0.2
        self.assertEqual((row["someSettingPassesEach"], row["oneSettingPassesBoth"], row["setting"]), (True, True, 10))      # the 1 degree step nearest the middle of 8 to 11
        self.assertIn('the adjustment "tilt" covers it: settings 8 to 11 pass at the low end, 8 to 24 at the high end, and one setting (10) passes at both ends',
                      trial["findings"][0])
        self.assertEqual(trial["handForward"]["adjustmentSettings"], [{"input": "materials.panel.friction", "adjustment": "tilt", "setting": 10}])

    def test_an_adjustment_that_cannot_reach_is_not_covered(self):
        """Control: catches coverage being claimed when no setting in the adjustment's range passes at one end."""
        trial = self.tilting(15, 24)["trials"]["hold"]
        self.assertEqual((trial["result"], trial["coverage"][0]["atLow"]["passes"], trial["coverage"][0]["someSettingPassesEach"]), ("not covered", None, False))
        self.assertIn("no adjustment declared for this trial has a setting that passes at each end", trial["findings"][0])

    def test_with_no_adjustment_a_flip_is_not_covered_and_says_so(self):
        """Catches a flip with nothing to recover it being reported as anything but not covered."""
        trial = campaign.run_campaign(load_data(bench({"hold": tilting_trial()})))["trials"]["hold"]
        self.assertEqual((trial["result"], trial["coverage"]), ("not covered", []))
        self.assertIn("no adjustment is declared for this trial", trial["findings"][0])


class ForOtherTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = kernel.build(load_data(design(), {"custom/taper.py": TAPER}))

    def test_a_displaced_control_needs_no_second_file(self):
        """Catches a displaced solid being ignored: the left wall pushed 4 mm inward is in the way of the pressed ball."""
        clear = clearance.along(self.assembly, "press", 0.5)
        moved = clearance.along(self.assembly, "press", 0.5, displace={"wall left": [0, -4, 0]})
        self.assertNotIn(["drawn ball", "wall left"], clear["closer"])
        self.assertIn(["drawn ball", "wall left"], moved["closer"])
        self.assertEqual(moved["displaced"], {"wall left": [0, -4, 0]})
        job = {"kind": "clearance", "motion": "press", "minGapMm": 0.5, "displace": {"wall left": [0, -4, 0]}}
        with run.Bench(self.assembly.design, 1) as held:
            self.assertEqual(records.answers(held, [job])[0]["record"]["result"]["closer"], moved["closer"])

    def test_group_placements_are_numbers_anyone_can_use(self):
        """Catches the public placement call drifting from where the solids are actually put."""
        placed = kernel.placements(self.assembly.design, motion="press", t=0.5)
        self.assertEqual(mx.apply(placed["piece"], (0, 0, 0)), (0.0, 0.0, -3.0))
        self.assertEqual(kernel.placements(self.assembly.design, pose="home")["rig"], mx.IDENTITY)
        self.assertAlmostEqual(props.bounds(self.assembly.at_motion("press", 0.5)["drawn ball"])[2], -23.0)

    def test_a_display_mesh_follows_the_solid(self):
        """Catches a mesh that strays from its solid, is wound inside out, or changes the solid it was made from."""
        mesh = self.assembly.mesh("drawn ball", 0.2)
        self.assertGreater(len(mesh["triangles"]), 100)
        self.assertTrue(all(abs(math.hypot(*v) - 20) < 0.01 for v in mesh["vertices"]))
        volume = 0.0
        for a, b, c in mesh["triangles"]:
            pa, pb, pc = (mesh["vertices"][i] for i in (a, b, c))
            volume += mx.dot(pa, mx.cross(pb, pc)) / 6
        self.assertAlmostEqual(volume, 4 / 3 * math.pi * 20 ** 3, delta=0.02 * 4 / 3 * math.pi * 20 ** 3)       # positive: wound outward
        box = self.assembly.mesh("wall left")
        self.assertEqual((len(box["vertices"]), len(box["triangles"])), (24, 12))

    def test_a_ring_is_a_listed_shape(self):
        """Catches a ring piece needing a custom shape: its volume is 2 pi^2 R r^2."""
        ring = screen.build_shape(self.assembly.data["pieces"]["ring"]["shape"], "test", screen.no_custom)
        self.assertAlmostEqual(props.volume(ring), 2 * math.pi ** 2 * 150 * 25 ** 2, delta=1.0)


if __name__ == "__main__":
    unittest.main()
