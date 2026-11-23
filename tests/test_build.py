"""The build layer on the worked example: solids, parts, poses, motions, export and the command line."""
import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.cli import main
from frc_design_kernel.kernel import props
from frc_design_kernel.kernel.step_read import read_solids, repaired
from frc_design_kernel.motion import ops

from .helpers import EXAMPLE, edited, load_data


def near(test, a, b, places=6):
    for x, y in zip(a, b):
        test.assertAlmostEqual(x, y, places=places)


def reference_bounds(shape, moves, t):
    """Bounds after the moves, done the long-standing way: one kernel transform per operation, in order."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    for move in moves:
        step = gp_Trsf()
        if move["kind"] == "gravity-drop":
            h, w = move["fallMm"], move["quadraticFraction"]
            step.SetTranslation(gp_Vec(0, 0, -h * ((1 - w) * t + w * t * t)))
        elif move["kind"] == "translation":
            step.SetTranslation(gp_Vec(*[v * t for v in move["travelMm"]]))
        else:
            step.SetRotation(gp_Ax1(gp_Pnt(*move["originMm"]), gp_Dir(*move["axis"])), math.radians(move["travelDeg"]) * t)
        shape = BRepBuilderAPI_Transform(shape, step, False).Shape()
    return props.bounds(shape)


class Example(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = kernel.build(kernel.load(EXAMPLE))
        cls.folder = tempfile.TemporaryDirectory()
        cls.out = Path(cls.folder.name)
        cls.manifest = kernel.export(cls.assembly, cls.out / "a")

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_every_solid_is_built_once_under_its_name(self):
        """Catches a lost, repeated or misnamed solid, including the ones "each" writes out."""
        names = [s["name"] for s in self.manifest["solids"]]
        self.assertEqual(names, ["base plate", "post left", "post right", "top bar", "gusset left", "gusset right", "gearmotor body",
                                 "gearmotor shaft", "spool", "sleeve left", "sleeve right", "carriage plate", "tine left", "tine right"])
        self.assertEqual([s["name"] for s in self.manifest["fixtures"]], ["bench top", "crate"])

    def test_mirrored_solids_are_mirror_images(self):
        """Catches an "each" row whose sign did not reach the geometry."""
        rows = {s["name"]: s for s in self.manifest["solids"]}
        for part in ("post", "gusset", "sleeve", "tine"):
            left, right = rows[f"{part} left"], rows[f"{part} right"]
            self.assertAlmostEqual(left["volumeMm3"], right["volumeMm3"], places=4)
            near(self, left["boundsMm"], [right["boundsMm"][i] * s for i, s in ((0, 1), (4, -1), (2, 1), (3, 1), (1, -1), (5, 1))])

    def test_a_part_is_placed_and_not_changed(self):
        """Catches an imported part that is resized, re-drawn or put in the wrong place."""
        source = read_solids(EXAMPLE.parent / "parts" / "gearmotor.step")["Motor body"]
        placed = self.assembly.solids["gearmotor body"].shape
        self.assertAlmostEqual(props.volume(placed), props.volume(source), places=6)
        near(self, props.bounds(placed), [b + d for b, d in zip(props.bounds(source), [60, -60, 30] * 2)])
        self.assertEqual(self.manifest["parts"][1]["solids"], [{"solid": "Motor body", "as": "gearmotor body"}, {"solid": "Output shaft", "as": "gearmotor shaft"}])
        self.assertEqual(len(self.manifest["parts"][1]["sha256"]), 64)

    def test_mass_roll_up(self):
        """Catches mass counted twice, a fixture weighed as robot, or an unweighed solid going unreported."""
        groups = self.manifest["groups"]
        self.assertEqual((groups["carriage"]["massKg"], groups["carriage"]["massFrom"]), (1.8, "group massKg"))
        self.assertAlmostEqual(groups["drive"]["massKg"], 0.65)
        base = sum(s["volumeMm3"] for s in self.manifest["solids"] if s["group"] == "base") * 1e-9 * 2700
        self.assertAlmostEqual(groups["base"]["massKg"], base, places=5)
        self.assertAlmostEqual(self.manifest["mass"]["totalKg"], base + 0.65 + 1.8, places=5)
        self.assertEqual(self.manifest["mass"]["unweighed"], ["spool"])

    def test_a_pose_moves_the_group_and_what_it_carries(self):
        """Catches a carried group left behind when its carrier moves, or a fixed group that moves."""
        drawn, raised = self.assembly.at_pose(), self.assembly.at_pose("raised")
        for name, rise in (("carriage plate", 220), ("tine left", 220), ("crate", 220), ("base plate", 0), ("bench top", 0)):
            near(self, props.bounds(raised[name]), [b + d for b, d in zip(props.bounds(drawn[name]), [0, 0, rise] * 2)])
        self.assertAlmostEqual(self.manifest["poses"]["raised"]["robotBoundsMm"][5], 483.0)
        self.assertAlmostEqual(self.manifest["poses"]["lowered"]["robotBoundsMm"][3], 200.0)

    def test_a_motion_is_placed_by_stroke_fraction(self):
        """Catches a motion that ignores t, or a curved move that is cut straight."""
        half = self.assembly.at_motion("lift", 0.5)
        self.assertAlmostEqual(props.bounds(half["carriage plate"])[2], 85 + 110)
        mid = props.bounds(self.assembly.at_motion("hand off", 0.5)["crate"])
        self.assertAlmostEqual(mid[2], 95 + 220 + 50, places=6)     # the top of the arc, 50 mm above its ends
        self.assertAlmostEqual((mid[0] + mid[3]) / 2, 130, places=6)

    def test_a_through_motion_visits_each_pose(self):
        """Catches a motion through several poses that misses the middle or the end pose."""
        middle = self.assembly.at_motion("whole cycle", 0.5)
        end = self.assembly.at_motion("whole cycle", 1.0)
        near(self, props.bounds(middle["crate"]), props.bounds(self.assembly.at_pose("raised")["crate"]))
        near(self, props.bounds(end["crate"]), props.bounds(self.assembly.at_pose("set down")["crate"]))

    def test_the_step_file_carries_the_names(self):
        """Catches a STEP export that loses or changes solid names."""
        self.assertEqual(sorted(read_solids(self.out / "a" / "design.step")), sorted(s["name"] for s in self.manifest["solids"]))
        back = read_solids(self.out / "a" / "fixtures.step")
        self.assertEqual(sorted(back), ["bench top", "crate"])
        self.assertAlmostEqual(props.volume(back["crate"]), 120 * 140 * 100, places=4)

    def test_the_same_source_gives_the_same_files(self):
        """Catches anything that makes two builds of one source differ: clocks, ordering, float noise."""
        kernel.export(kernel.build(kernel.load(EXAMPLE)), self.out / "b")
        for name in ("manifest.json", "design.step", "fixtures.step"):
            self.assertEqual((self.out / "a" / name).read_bytes(), (self.out / "b" / name).read_bytes(), name)

    def test_a_changed_source_changes_the_manifest(self):
        """Control: the sameness test can fail."""
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        data["parameters"]["lift"] = 221
        changed = load_data({k: v for k, v in data.items() if k not in ("custom", "fixtures", "mounts", "contacts", "trials", "interactions", "adjustments")} | {
            "solids": [s for s in data["solids"] if "part" not in s and s["shape"]["kind"] != "custom"]})
        self.assertNotEqual(kernel.export(kernel.build(changed), self.out / "c")["poses"], self.manifest["poses"])

    def test_the_manifest_records_the_generator_for_information(self):
        """Catches the version record going missing from outputs."""
        self.assertEqual(self.manifest["generator"]["library"], "frc-design-kernel")
        self.assertEqual(set(self.manifest["generator"]), {"library", "version", "commit"})

    def test_the_custom_shape_is_reported(self):
        """Catches a custom shape used without being listed for the auditor."""
        row, = self.manifest["custom"]
        text = (EXAMPLE.parent / "custom" / "tine.py").read_text(encoding="utf-8")
        self.assertEqual((row["name"], row["file"], row["lines"], row["usedBy"]), ("tine", "custom/tine.py", len(text.splitlines()), ["tine left", "tine right"]))
        self.assertTrue(row["reason"] and row["limits"] and len(row["sha256"]) == 64)

    def test_moves_match_the_long_standing_implementation(self):
        """Catches the carried-over vocabulary drifting from what other tools compute, operation by operation."""
        from frc_design_kernel.kernel.transform import moved
        moves = [{"kind": "rotation", "originMm": [10, 20, 30], "axis": [1, 2, 3], "travelDeg": 140},
                 {"kind": "translation", "travelMm": [50, -20, 5]}, {"kind": "gravity-drop", "fallMm": 80, "quadraticFraction": 0.7}]
        shape = self.assembly.solids["tine left"].shape
        for t in (0.0, 0.37, 1.0):
            near(self, props.bounds(moved(shape, ops.at(moves, t))), reference_bounds(shape, moves, t), places=6)


class Refusals(unittest.TestCase):
    def expect(self, data, pattern, files=None):
        with self.assertRaisesRegex(DesignError, pattern):
            kernel.build(load_data(data, files))

    def test_a_motion_must_end_at_its_stated_pose(self):
        """Control: catches a motion whose moves and end pose disagree."""
        self.expect(edited(lambda d: d["poses"]["out"]["slide"][0].update(travelMm=[90, 0, 0])),
                    r'motions "extend": ends about 10 mm away from the pose "out" for the group "slide"')

    def test_a_missing_part_solid_lists_what_the_file_has(self):
        """Catches a wrong solid name failing without telling the author the real names."""
        gearmotor = (EXAMPLE.parent / "parts" / "gearmotor.step").read_text(encoding="utf-8")
        def change(d):
            d["solids"][0].pop("shape")
            d["solids"][0]["part"] = {"file": "parts/gearmotor.step", "solid": "Motor bodi"}
        self.expect(edited(change), r"""has no solid named "Motor bodi"\. Fix: Did you mean 'Motor body'\? It has 3 solids: Cable tail, Motor body, Output shaft""",
                    {"parts/gearmotor.step": gearmotor})

    def test_names_that_step_cannot_carry_are_refused(self):
        """Catches a name with a symbol that would be written damaged into the STEP file."""
        assembly = kernel.build(load_data(edited(lambda d: d["solids"][0].update(name="block · left"))))
        with tempfile.TemporaryDirectory() as out, self.assertRaisesRegex(DesignError, "a character that STEP files do not carry safely"):
            kernel.export(assembly, out)

    def test_damaged_names_from_other_files_are_repaired(self):
        """Catches a supplier name with an accent or symbol becoming unselectable."""
        self.assertEqual(repaired("Belt motor Â· left"), "Belt motor · left")
        self.assertEqual(repaired("plain"), "plain")
        self.assertEqual(repaired("café"), "café")


class ReadmeExample(unittest.TestCase):
    def test_the_readme_example_builds_and_swings_about_its_pivot(self):
        """Catches the first example a reader copies being out of date with the format."""
        import re
        readme = (EXAMPLE.parents[2] / "README.md").read_text(encoding="utf-8")
        assembly = kernel.build(load_data(json.loads(re.search(r"```json\s(.*?)```", readme, re.S).group(1))))
        up = props.bounds(assembly.at_motion("raise", 1.0)["arm"])
        near(self, up, [-20, -10, 300, 0, 10, 500])
        half = props.bounds(assembly.at_motion("raise", 0.5)["arm"])
        self.assertAlmostEqual(half[5], 300 + 220 * math.sqrt(0.5), places=6)    # the far top corner, half way round


class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_validate_says_what_it_found(self):
        """Catches validate building things, or saying nothing useful."""
        code, out, _ = self.run_cli("validate", str(EXAMPLE))
        self.assertEqual(code, 0)
        self.assertEqual(out, 'OK "Bench lifter": 14 solids, 2 fixtures, 5 groups, 3 poses, 3 motions, 1 custom shape. Nothing was built.\n')

    def test_build_says_what_it_built(self):
        """Catches a build that writes nothing, or does not report custom shapes and missing mass."""
        with tempfile.TemporaryDirectory() as out:
            code, text, _ = self.run_cli("build", str(EXAMPLE), "--out", out, "--pose", "raised")
            lines = text.splitlines()
            self.assertEqual(code, 0)
            self.assertEqual(lines[0], 'Built "Bench lifter" at the pose "raised": 14 solids, 2 fixtures, 5 groups, 3 poses, 3 motions, 1 custom shape.')
            self.assertEqual(lines[1], 'Custom shape "tine" (custom/tine.py, 24 lines) is used by 2 solids.')
            self.assertRegex(lines[2], r"^Robot mass 5\.652 kg; 1 solid with no mass\.$")
            self.assertTrue(lines[3].startswith("Wrote design.step, fixtures.step, manifest.json to "))
            self.assertEqual(json.loads((Path(out) / "manifest.json").read_text(encoding="utf-8"))["pose"], "raised")

    def test_a_bad_source_gives_one_plain_line_and_a_failing_exit(self):
        """Control: catches errors that exit 0 or print a stack trace."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design.json"
            path.write_text(json.dumps(edited(lambda d: d["solids"][0].update(group="bass"))), encoding="utf-8")
            code, out, err = self.run_cli("validate", str(path))
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, 'Error: solids[0] "block": names the group "bass", which does not exist. Fix: Did you mean "base"? Known: base, slide\n')


if __name__ == "__main__":
    unittest.main()
