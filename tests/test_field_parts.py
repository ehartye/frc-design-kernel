"""A part from a folder of field models the caller names: {"field": "<file name>", "solid": "..."}.

Nothing else outside the design's own folder can be reached, and without the folder such a part is refused.
"""
import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.cli import main
from frc_design_kernel.kernel import props

from .helpers import EXAMPLE, edited, job_files, load_data, recorded

BENCH = EXAMPLE.parent / "parts" / "bench.step"
WEIGHED = {"kind": "clearance", "motion": "extend", "minGapMm": 1.0}


class FieldParts(unittest.TestCase):
    def setUp(self):
        keep = tempfile.TemporaryDirectory()
        self.addCleanup(keep.cleanup)
        self.project = Path(keep.name)
        self.field, self.folder = self.project / "field", self.project / "design"
        self.field.mkdir()
        self.folder.mkdir()
        shutil.copy(BENCH, self.field / "bench.step")
        shutil.copy(BENCH, self.project / "beside.step")

    def source(self, part):
        """The path of the minimal design with one fixture taken from a part, in a folder beside the field folder."""
        data = edited(lambda d: d.update(fixtures=[{"name": "stand", "part": part, "place": [{"kind": "translation", "travelMm": [2000, 0, 0]}]}]))
        path = self.folder / "design.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def named(self, name):
        return self.source({"field": name, "solid": self.solid()})

    def solid(self):
        from frc_design_kernel.kernel.step_read import read_solids
        return sorted(read_solids(BENCH))[0]

    def test_a_field_part_is_read_from_the_folder_the_caller_passes(self):
        """Catches a field part looked for beside the design, or built as another solid than the file holds."""
        from frc_design_kernel.kernel.step_read import read_solids
        assembly = kernel.build(kernel.load(self.named("bench.step"), field=self.field))
        self.assertAlmostEqual(props.volume(assembly.solids["stand"].shape), props.volume(read_solids(BENCH)[self.solid()]), places=3)
        self.assertEqual([(row["field"], [s["as"] for s in row["solids"]]) for row in assembly.parts], [("bench.step", ["stand"])])

    def test_without_the_folder_it_is_refused_plainly(self):
        """Catches a field part searched for somewhere, or refused with no word of what to give."""
        with self.assertRaisesRegex(DesignError, r'fixtures\[0\] "stand".*the part is the field file "bench\.step", and no field folder was given'):
            kernel.load(self.named("bench.step"))
        code, errors = self.command("validate", self.named("bench.step"))
        self.assertEqual(code, 1)
        self.assertIn("--field", errors)

    def test_nothing_else_outside_the_design_folder_is_reachable(self):
        """Catches a name that climbs out of the field folder, an absolute path, or a design's own part doing so."""
        for name in ("../beside.step", "..", ".", "sub/bench.step", "sub\\bench.step", str(self.project / "beside.step"), "C:bench.step"):
            with self.assertRaisesRegex(DesignError, "is not a plain file name", msg=name):
                kernel.load(self.named(name), field=self.field)
        with self.assertRaisesRegex(DesignError, "is outside the design folder"):
            kernel.load(self.source({"file": "../beside.step", "solid": self.solid()}), field=self.field)
        with self.assertRaisesRegex(DesignError, "is outside the design folder"):
            kernel.load(self.source({"file": "../field/bench.step", "solid": self.solid()}), field=self.field)

    def test_a_missing_file_or_folder_is_named(self):
        """Catches a field model that is not there found only when the build reads it."""
        with self.assertRaisesRegex(DesignError, r'the field file "stage\.step" does not exist'):
            kernel.load(self.named("stage.step"), field=self.field)
        with self.assertRaisesRegex(DesignError, "the field folder .* does not exist"):
            kernel.load(self.named("bench.step"), field=self.project / "nowhere")

    def test_a_part_is_one_or_the_other(self):
        """Catches a part that names a file of its own and a field file, so nobody can tell which was built."""
        with self.assertRaisesRegex(DesignError, 'part: needs "file" or "field", one of them'):
            kernel.load(self.source({"field": "bench.step", "file": "bench.step", "solid": "x"}), field=self.field)
        with self.assertRaisesRegex(DesignError, 'part: needs "file" or "field", one of them'):
            kernel.load(self.source({"solid": "x"}), field=self.field)

    def test_workers_an_adjustment_and_the_command_line_reach_it_too(self):
        """Catches a field part that builds here and not in a worker process, at an adjustment's end or from the command line."""
        path = self.named("bench.step")
        design = kernel.load(path, field=self.field)
        with tempfile.TemporaryDirectory() as out:
            recorded(design, [WEIGHED, dict(WEIGHED, id="again")], out, workers=2)
            self.assertEqual(sorted(job_files(out)), ["again", "clearance.motion.extend"])
        variant = kernel.load(path, {"tall": 90}, field=self.field)
        self.assertEqual(variant.data["parameters"]["tall"], 90)
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(self.command("build", path, "--out", out, "--field", self.field)[0], 0)
            self.assertEqual(self.command("measure", path, "--out", out, "--motion", "extend", "--field", self.field, "--workers", "1")[0], 0)
        self.assertEqual(self.command("validate", path, "--field", self.field)[0], 0)

    def test_control_a_design_with_no_field_part_needs_no_folder(self):
        """Control: shows the refusals above come from the field part, not from the design."""
        self.assertEqual(kernel.load(load_data(copy.deepcopy(edited())).path).field, None)

    def command(self, *args):
        errors = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            return main([str(a) for a in args]), errors.getvalue()


if __name__ == "__main__":
    unittest.main()
