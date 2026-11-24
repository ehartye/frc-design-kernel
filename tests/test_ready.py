"""What a 3D engine would need settled in a design: plain facts, stated by the screen command. Advice only."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import frc_design_kernel as kernel
from frc_design_kernel.cli import main
from frc_design_kernel.trials import ready

from .helpers import load_data
from .trial_cases import PANEL, bench, hold_trial

GRIPPY = {"panel": {**PANEL, "friction": {"value": 0.5, "assumed": [0.42, 0.8]}}}
TURN = {"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 1, 0], "travelDeg": 30}


def ride_trial():
    """A ball set on the belt bed; it only has to stay there."""
    return {"assumes": [{"text": "The bed is level and still."}], "plane": {"normal": "y", "atMm": 0}, "stepS": 1e-4, "durationS": 0.6, "traceS": 0.01,
            "piece": {"use": "ball", "start": {"atMm": [0, -480]}}, "surfaces": [{"solid": "belt bed", "material": "panel"}],
            "events": [{"name": "fell", "when": {"signal": "zMm", "below": "=-600 - rise * 0"}, "outcome": "fell"},
                       {"name": "stayed", "when": {"restFor": 0.2}, "outcome": "stayed"}],
            "movers": {"wave": {"motion": "shove", "group": "gate", "startS": 0.0, "durationS": 0.2}},
            "pass": {"outcomes": ["stayed"]}, "control": {"change": {"surfaces.belt bed": None}, "note": "With no bed under it the ball must fall."}}


def source():
    data = bench({"hold": hold_trial(), "ride": ride_trial()}, materials=GRIPPY)
    data["groups"]["gate"] = {"role": "mechanism"}
    data["solids"].append({"name": "gate", "group": "gate", "massKg": 0.2, "shape": {"kind": "box", "fromMm": [2500, -50, 0], "toMm": [2520, 50, 200]}})
    data["poses"] = {"shut": {}, "open": {"gate": [dict(TURN)]}}
    data["motions"] = {"swing": {"by": "hand", "from": "shut", "moves": {"gate": [dict(TURN)]}}, "sweep": {"by": "hand", "through": ["shut", "open"]},
                       "shove": {"by": "hand", "from": "shut", "moves": {"gate": [{"kind": "translation", "travelMm": [10, 0, 0]}]}}}
    return data


class ReadyFor3d(unittest.TestCase):
    def test_the_facts_a_3d_engine_would_need_settled(self):
        """Catches a hollow or cut solid, a weightless solid, a path-driven group, a loose drive or a typed surface going unlisted."""
        data = source()
        data["solids"] += [
            {"name": "sleeve", "group": "bench", "massKg": 0.1, "shape": {"kind": "tube", "section": "round", "fromMm": [0, -50, -700], "toMm": [0, 50, -700], "outerDiameterMm": 60, "wallMm": 5}},
            {"name": "ell", "group": "bench", "massKg": 0.1, "shape": {"kind": "union", "of": [{"kind": "box", "fromMm": [100, -50, -700], "toMm": [200, 50, -690]},
                                                                                                    {"kind": "box", "fromMm": [100, -50, -700], "toMm": [110, 50, -600]}]}}]
        trial = ride_trial()
        trial["surfaces"] += [{"solid": "sleeve", "material": "panel"}, {"solid": "ell", "material": "panel"},
                              {"name": "floor", "material": "panel", "segmentsMm": [[-100, -900], [100, -900]], "drive": "loose"}]
        trial["commands"] = {"loose": {"mode": "imposed", "speedMps": 0}}
        data["trials"] = {"ride": trial}
        data["drives"] = {"loose": {"radiusMm": 20}}
        design = load_data(data)
        found = ready.report(kernel.build(design))
        self.assertEqual(found["trialSolids"], ["belt bed", "ell", "sleeve"])
        self.assertEqual(found["concaveWithNoBreakdown"], [])     # the ell is a union of two boxes; the sleeve breaks into a ring of wedges
        self.assertEqual(found["solidsWithNoMass"], ["belt bed", "wedge"])
        self.assertEqual(found["groupsNotOneHingeOrSlider"], [{"motion": "sweep", "group": "gate"}])       # "swing" is one hinge
        self.assertEqual(found["drivesNotOnASolid"], ["loose"])
        self.assertEqual(found["surfacesNotFromSolids"], [{"trial": "ride", "surface": "floor", "drive": "loose"}])

    def test_how_a_shape_was_built_tells_whether_it_breaks_into_convex_pieces(self):
        """Catches a concave shape being called convex, or a union of boxes being called unbreakable."""
        box = {"kind": "box", "fromMm": [0, 0, 0], "toMm": [1, 1, 1]}
        self.assertEqual(ready.breakdown(box), "convex")
        self.assertEqual(ready.breakdown({"kind": "union", "of": [box, box]}), "union of convex pieces")
        ball = {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 1}
        built = "convex pieces from its construction"
        self.assertEqual(ready.breakdown({"kind": "difference", "from": box, "cut": [box]}), built)       # a box less boxes leaves boxes
        self.assertEqual(ready.breakdown({"kind": "difference", "from": box, "cut": [ball]}), "a shape with material cut away")
        self.assertEqual(ready.breakdown({"kind": "prism", "plane": "xy", "outlineMm": [[0, 0], [4, 0], [4, 4], [2, 1], [0, 4]], "fromMm": 0, "toMm": 1}), built)
        self.assertEqual(ready.breakdown({"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 9], "outerDiameterMm": 9, "wallMm": 1}), built)
        self.assertEqual(ready.breakdown({"kind": "intersection", "of": [box, ball]}), "convex")
        self.assertEqual(ready.breakdown({"kind": "cylinder", "fromMm": [0, 0, 0], "toMm": [0, 0, 1], "radiusMm": 1, "sweepDeg": 270}), "a pie slice wider than a half turn")


class ScreenCommand(unittest.TestCase):
    def test_the_screen_command_states_the_facts_and_writes_them(self):
        """Catches the facts a 3D engine would need left out of screen.json, or stated as a verdict."""
        design, text = load_data(source()), io.StringIO()
        with tempfile.TemporaryDirectory() as out, contextlib.redirect_stdout(text):
            self.assertEqual(main(["screen", str(design.path), "--out", out]), 0)
            written = json.loads((Path(out) / "screen.json").read_text(encoding="utf-8"))
        self.assertEqual(written["readyFor3d"], ready.report(kernel.build(design)))
        self.assertIn("For a 3D engine: 0 trial solids concave with no convex breakdown; 2 solids with no mass; 1 moving group not one hinge or slider; "
                      "0 drives not on a solid; 0 trial surfaces not from a solid.", text.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
