"""The piece-geometry command: each piece's shape measured on its own, every shape reported, failures included."""
import contextlib
import io
import json
import math
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from frc_design_kernel import DesignError
from frc_design_kernel.cli import main
from frc_design_kernel.measure import piece_geometry

DATA = Path(__file__).resolve().parent / "data" / "piece_shapes.json"
KINDS = {"ball": "sphere", "ring": "torus", "pipe": "tube", "bar": "cylinder", "crate": "box", "disc": "difference", "cup": "difference",
         "cone": "cone", "cube": "box"}


def run(*args):
    """(exit code, stdout, stderr) of the command line, run in this process."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["piece-geometry", *map(str, args)])
    return code, out.getvalue(), err.getvalue()


def near(test, a, b, places=3):
    test.assertEqual(len(a), len(b))
    for x, y in zip(a, b):
        test.assertAlmostEqual(x, y, places=places)


class Record(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.out = Path(cls.folder.name) / "g.json"
        cls.code, cls.stdout, cls.stderr = run(DATA, "--out", cls.out)
        cls.record = json.loads(cls.out.read_text(encoding="utf-8"))
        cls.shapes = cls.record["shapes"]

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_every_listed_piece_is_measured_and_the_run_exits_0(self):
        """Catches a shape dropped from the record, extra piece fields (mass, note) refused, or a clean run not exiting 0."""
        self.assertEqual((self.code, self.stderr), (0, ""))
        self.assertEqual(set(self.shapes), set(KINDS))
        self.assertTrue(all(found["ok"] for found in self.shapes.values()))

    def test_the_record_says_what_it_is_and_what_it_used(self):
        """Catches a record with no schema, no library version or no meshing parameters to tell a stale one by."""
        self.assertEqual(self.record["schema"], "frc-design-kernel/piece-geometry@1")
        self.assertEqual(self.record["used"]["meshing"], {"linearMm": 0.2, "angularRad": 0.3})
        self.assertTrue(self.record["used"]["library"])

    def test_each_shape_has_an_identity_from_its_built_figures(self):
        """Catches an identity that is missing, names the wrong kind, or is not the built solid's volume and bounds."""
        for name, kind in KINDS.items():
            with self.subTest(name):
                identity = self.shapes[name]["identity"]
                self.assertEqual(identity["kind"], kind)
                self.assertEqual(identity["boundsMm"], self.shapes[name]["boundsMm"])
                self.assertAlmostEqual(identity["volumeMm3"], self.shapes[name]["volumeMm3"], places=2)
        self.assertAlmostEqual(self.shapes["ball"]["volumeMm3"], 4 / 3 * math.pi * 60 ** 3, places=0)    # "=120 / 2" worked out
        near(self, self.shapes["crate"]["boundsMm"][0] + self.shapes["crate"]["boundsMm"][1], [-50, -40, 0, 50, 40, 60])
        near(self, self.shapes["ring"]["centreMm"], [10, -5, 30])

    def test_each_hull_spans_at_least_the_shapes_bounds(self):
        """Catches a hull that is missing, has no tolerance, or falls inside the solid it should contain. A solid with only
        flat faces (the crate) is grown only for rounding; the rest by at least the mesher's deflection."""
        for name, found in self.shapes.items():
            with self.subTest(name):
                self.assertGreaterEqual(found["hullToleranceMm"], 0.002 if name == "crate" else 0.2)
                low, high = found["boundsMm"]
                for axis in range(3):
                    self.assertLessEqual(min(v[axis] for v in found["hullMm"]), low[axis])
                    self.assertGreaterEqual(max(v[axis] for v in found["hullMm"]), high[axis])

    def test_symmetry_classes_and_axes(self):
        """Catches a ball not called a sphere, a rounded box called prismatic, or a bar, ring, pipe or cone that loses its
        axis or gets the wrong one."""
        self.assertEqual(self.shapes["ball"]["symmetry"], {"class": "sphere"})
        self.assertEqual(self.shapes["crate"]["symmetry"], {"class": "prismatic"})
        self.assertEqual(self.shapes["cube"]["symmetry"], {"class": "general"})
        for name, axis in (("ring", [1, 0, 0]), ("bar", [0, 1, 0]), ("pipe", [0, 0, 1]), ("disc", [0, 0, 1]), ("cone", [0, 0, 1])):
            with self.subTest(name):
                self.assertEqual(self.shapes[name]["symmetry"]["class"], "body of revolution")
                near(self, [abs(v) for v in self.shapes[name]["symmetry"]["axis"]], axis, places=6)

    def test_a_through_bore_is_found_by_the_one_rule(self):
        """Catches a ring, pipe or holed disc whose bore is missed or mis-sized, or a bore centre off the axis."""
        for name, diameter, centre in (("ring", 2 * (150 - 25), [10, -5, 30]), ("pipe", 60 - 2 * 4, [0, 0, 150]), ("disc", 30, [0, 0, 10])):
            with self.subTest(name):
                bore = self.shapes[name]["bore"]
                self.assertAlmostEqual(bore["diameterMm"], diameter, places=3)
                near(self, [abs(v) for v in bore["axis"]], [abs(v) for v in self.shapes[name]["symmetry"]["axis"]], places=6)
                near(self, bore["centreMm"], centre)

    def test_control_shapes_with_no_through_bore_report_none(self):
        """Control: catches a bore rule that reports a hole in a solid bar, a ball, a box, a rounded box, a cone, or a cup
        closed at one end."""
        for name in ("bar", "ball", "crate", "cube", "cone", "cup"):
            with self.subTest(name):
                self.assertIsNone(self.shapes[name]["bore"])

    def test_every_axis_is_written_one_way(self):
        """Catches an axis whose sign follows the order a shape was drawn in (a pipe drawn upward recorded as pointing
        down), so the same piece drawn two ways gives two records."""
        for name in ("ring", "bar", "pipe", "disc", "cone"):
            axes = [self.shapes[name]["symmetry"]["axis"]] + ([self.shapes[name]["bore"]["axis"]] if self.shapes[name]["bore"] else [])
            for axis in axes:
                with self.subTest(name):
                    self.assertGreater(next(v for v in axis if abs(v) > 1e-9), 0)
        self.assertEqual(self.shapes["pipe"]["bore"]["axis"], [0.0, 0.0, 1.0])

    def test_the_meshing_flags_are_used_and_recorded(self):
        """Catches --linear-mm or --angular-rad being ignored, so the record claims meshing it did not use."""
        with tempfile.TemporaryDirectory() as folder:
            pieces = Path(folder) / "p.json"
            pieces.write_text(json.dumps({"pieces": {"bar": {"shape": {"kind": "cylinder", "fromMm": [0, 0, 0], "toMm": [0, 0, 50], "radiusMm": 30}}}}))
            code, _, _ = run(pieces, "--out", Path(folder) / "g.json", "--linear-mm", "0.5", "--angular-rad", "0.2")
            record = json.loads((Path(folder) / "g.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(record["used"]["meshing"], {"linearMm": 0.5, "angularRad": 0.2})
        self.assertGreaterEqual(record["shapes"]["bar"]["hullToleranceMm"], 0.5)


class Failures(unittest.TestCase):
    PIECES = {"pieces": {
        "fat ring": {"shape": {"kind": "torus", "centerMm": [0, 0, 0], "axis": [0, 0, 1], "majorRadiusMm": 20, "minorRadiusMm": 20}},
        "crate": {"shape": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [10, 10, 10]}, "massKg": 2},
        "made": {"shape": {"kind": "custom", "use": "blob"}},
        "unsized": {"shape": {"kind": "sphere", "centerMm": [0, 0, 0]}},
        "needs a parameter": {"shape": {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": "=size / 2"}},
        "shapeless": {"massKg": 1}}}

    def test_a_failed_shape_is_reported_and_the_rest_still_measured(self):
        """Catches one bad shape stopping the run, the file not being written, a failure exiting 0, or a stderr line
        missing for a failure."""
        with tempfile.TemporaryDirectory() as folder:
            pieces, out = Path(folder) / "p.json", Path(folder) / "g.json"
            pieces.write_text(json.dumps(self.PIECES))
            code, _, stderr = run(pieces, "--out", out)
            shapes = json.loads(out.read_text(encoding="utf-8"))["shapes"]
        self.assertEqual(code, 1)
        self.assertTrue(shapes["crate"]["ok"])
        failed = [name for name in self.PIECES["pieces"] if name != "crate"]
        for name in failed:
            with self.subTest(name):
                self.assertFalse(shapes[name]["ok"])
                self.assertEqual(set(shapes[name]["error"]), {"where", "problem", "fix"})
                self.assertIn(f'"{name}"', shapes[name]["error"]["where"])
        lines = stderr.splitlines()
        self.assertEqual(len(lines), len(failed))
        self.assertTrue(all(line.startswith("Error: pieces ") for line in lines))
        ring = shapes["fat ring"]["error"]
        self.assertEqual((ring["problem"], ring["fix"]), ("minorRadiusMm must be smaller than majorRadiusMm", "A ring needs a hole through its middle"))
        self.assertIn("custom", shapes["made"]["error"]["problem"])
        self.assertTrue(shapes["made"]["error"]["fix"])
        self.assertIn("radiusMm", shapes["unsized"]["error"]["problem"] + shapes["unsized"]["error"]["where"])
        self.assertIn("size", shapes["needs a parameter"]["error"]["problem"])
        parameter = DesignError(**shapes["needs a parameter"]["error"])
        self.assertEqual(str(parameter).count("Fix:"), 1)
        self.assertIn("has no parameters", parameter.problem)

    def test_a_missing_file_or_bad_json_exits_1_with_one_error_line(self):
        """Catches an unreadable pieces file crashing with a traceback instead of a plain error."""
        with tempfile.TemporaryDirectory() as folder:
            broken = Path(folder) / "broken.json"
            broken.write_text('{"pieces": {"ball": ')
            for source, words in ((Path(folder) / "missing.json", "does not exist"), (broken, "not valid JSON")):
                with self.subTest(source.name):
                    code, _, stderr = run(source, "--out", Path(folder) / "g.json")
                    self.assertEqual(code, 1)
                    self.assertEqual(len(stderr.splitlines()), 1)
                    self.assertTrue(stderr.startswith("Error: ") and words in stderr)

    def test_a_file_with_no_pieces_block_is_refused(self):
        """Catches a whole design source, or any other JSON, being taken as a pieces file with nothing in it."""
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "design.json"
            source.write_text(json.dumps({"schema": "frc-design-kernel/design@1", "solids": []}))
            code, _, stderr = run(source, "--out", Path(folder) / "g.json")
        self.assertEqual(code, 1)
        self.assertIn('"pieces"', stderr)

    def test_a_usage_error_exits_2(self):
        """Catches the command running with no --out, where it would have nowhere to write."""
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()):
            main(["piece-geometry", str(DATA)])
        self.assertEqual(caught.exception.code, 2)

    def test_a_meshing_value_that_is_not_finite_and_above_zero_is_a_usage_error(self):
        """Catches a zero, negative, infinite or not-a-number --linear-mm or --angular-rad reaching the mesher, which
        crashes with a traceback or hangs, instead of exiting 2 with a plain line."""
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "g.json"
            for flag in ("--linear-mm", "--angular-rad"):
                for value in ("0", "-1", "inf", "nan"):
                    err = io.StringIO()
                    with self.subTest(flag=flag, value=value), self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
                        main(["piece-geometry", str(DATA), "--out", str(out), f"{flag}={value}"])
                    self.assertEqual(caught.exception.code, 2)
                    self.assertIn("finite number greater than 0", err.getvalue())
                    self.assertNotIn("Traceback", err.getvalue())
            self.assertFalse(out.exists())

    def test_an_out_path_that_cannot_be_written_exits_1_with_one_error_line(self):
        """Catches --out naming a folder, or anywhere else that cannot be written, ending in a traceback."""
        with tempfile.TemporaryDirectory() as folder:
            code, _, stderr = run(DATA, "--out", folder)
        self.assertEqual(code, 1)
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertTrue(stderr.startswith("Error: "))


BALL = {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 5}
PIPE = {"kind": "tube", "section": "round", "fromMm": [0, 0, 0], "toMm": [0, 0, 40], "outerDiameterMm": 20, "wallMm": 2}


def one_line(test, code, stderr, words=""):
    """The run failed with exit 1 and exactly one plain error line holding words, and no traceback."""
    test.assertEqual(code, 1)
    test.assertEqual(len(stderr.splitlines()), 1, stderr)
    test.assertTrue(stderr.startswith("Error: ") and words in stderr, stderr)
    test.assertEqual(stderr.count("Fix:"), 1, stderr)


class Input(unittest.TestCase):
    """What the command meets in a real folder: other encodings, a folder, its own source as --out, odd names."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.dir = Path(self.folder.name)

    def pieces(self, name, pieces, encoding="utf-8"):
        path = self.dir / name
        path.write_text(json.dumps({"pieces": pieces}, ensure_ascii=False), encoding=encoding)
        return path

    def test_a_file_that_is_not_utf8_or_is_a_folder_exits_1_with_one_line(self):
        """Catches a UTF-16 or Latin-1 pieces file, or a folder given as the file, ending in a traceback."""
        cases = {"utf-16": (self.pieces("wide.json", {"ball": {"shape": BALL}}, "utf-16"), "UTF-8"),
                 "latin-1": (self.pieces("accent.json", {"ballé": {"shape": BALL}}, "latin-1"), "UTF-8"),
                 "folder": (self.dir, "cannot be read")}
        for name, (source, words) in cases.items():
            with self.subTest(name):
                code, _, stderr = run(source, "--out", self.dir / "g.json")
                one_line(self, code, stderr, words)

    def test_control_a_utf8_file_with_a_byte_order_mark_is_read(self):
        """Control: catches the encoding checks refusing UTF-8 that starts with a byte-order mark (Windows tools write it)."""
        source = self.pieces("marked.json", {"ball": {"shape": BALL}}, "utf-8-sig")
        self.assertEqual(run(source, "--out", self.dir / "g.json")[0], 0)

    def test_out_naming_the_pieces_file_itself_is_refused(self):
        """Catches --out the same as the source silently writing the record over the pieces file."""
        source = self.pieces("p.json", {"ball": {"shape": BALL}})
        before = source.read_text(encoding="utf-8")
        code, _, stderr = run(source, "--out", self.dir / "." / "p.json")
        one_line(self, code, stderr, "pieces file")
        self.assertEqual(source.read_text(encoding="utf-8"), before)

    def test_an_empty_pieces_block_measures_nothing_and_exits_0(self):
        """Catches an empty block being refused, or a record not written for it."""
        code, _, _ = run(self.pieces("none.json", {}), "--out", self.dir / "g.json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((self.dir / "g.json").read_text(encoding="utf-8"))["shapes"], {})

    def test_a_name_outside_the_console_code_page_is_printed_not_crashed(self):
        """Catches a piece name such as "ring \u2192 big" crashing the summary line on a Windows console or pipe, whose
        code page cannot write it."""
        source = self.pieces("names.json", {"ring \u2192 big": {"shape": BALL}})
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="cp1252")
        with contextlib.redirect_stdout(console), contextlib.redirect_stderr(io.StringIO()):
            code = main(["piece-geometry", str(source), "--out", str(self.dir / "g.json")])
            console.flush()
        self.assertEqual(code, 0)
        self.assertIn("ring \\u2192 big", raw.getvalue().decode("cp1252"))

    def test_control_that_code_page_cannot_write_the_name(self):
        """Control: catches the console test passing only because its stand-in console could write the name anyway."""
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with self.assertRaises(UnicodeEncodeError):
            console.write("ring \u2192 big")
            console.flush()


class Expressions(unittest.TestCase):
    def failed(self, text):
        found = piece_geometry.measure({"p": {"shape": {**BALL, "radiusMm": text}}})["shapes"]["p"]
        self.assertFalse(found["ok"])
        return found["error"]

    def test_a_bad_expression_gives_one_fix(self):
        """Catches an error inside an expression being wrapped in another, so one line carries two Fix clauses, and an
        unknown function being called a parameter."""
        for text in ("=pi.real", "=foo(2)"):
            with self.subTest(text):
                error = self.failed(text)
                self.assertEqual(str(DesignError(**error)).count("Fix:"), 1)
                self.assertNotIn("no parameters", error["problem"])

    def test_control_a_parameter_is_still_named_as_one(self):
        """Control: catches the function rule hiding a real parameter name."""
        self.assertIn("has no parameters", self.failed("=size * 2")["problem"])

    def test_a_huge_power_fails_at_once(self):
        """Catches "=9**9**9" being worked out exactly, which takes the run hours."""
        began = time.perf_counter()
        error = self.failed("=9**9**9")
        self.assertLess(time.perf_counter() - began, 1)
        self.assertEqual(str(DesignError(**error)).count("Fix:"), 1)

    def test_control_an_ordinary_power_is_worked_out(self):
        """Control: catches the power rule refusing a small power."""
        found = piece_geometry.measure({"p": {"shape": {**BALL, "radiusMm": "=2**3"}}})["shapes"]["p"]
        self.assertAlmostEqual(found["volumeMm3"], 4 / 3 * math.pi * 8 ** 3, places=0)


class KernelFailures(unittest.TestCase):
    def test_a_kernel_failure_measuring_the_bore_fails_only_that_shape(self):
        """Catches a plain error from the CAD kernel inside the bore rule escaping, so no record is written at all."""
        def broken(a, b):
            raise ValueError("the CAD kernel could not measure the gap between two shapes")
        with mock.patch.object(piece_geometry, "distance", broken):
            shapes = piece_geometry.measure({"pipe": {"shape": PIPE}, "ball": {"shape": BALL}})["shapes"]
        self.assertFalse(shapes["pipe"]["ok"])
        self.assertIn("bore", shapes["pipe"]["error"]["problem"])
        self.assertTrue(shapes["ball"]["ok"])

    def test_control_the_same_pipe_measures_without_the_failure(self):
        """Control: catches the failure test passing because the pipe fails anyway."""
        self.assertTrue(piece_geometry.measure({"pipe": {"shape": PIPE}})["shapes"]["pipe"]["ok"])


if __name__ == "__main__":
    unittest.main()
