"""The rules commands: which folder is read, get with each of its flags, and means. Expected numbers are worked out by hand from the example."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frc_design_kernel.cli import main

from .rules_cases import EXAMPLE, ROOT, as_it_is, example, small, written


def once_read(folder):
    """The Rules of a folder. The example is read once for all the tests; what is asked of it is worked out anew each time."""
    from frc_design_kernel.rules.rules import Rules, load_rules
    return Rules(as_it_is().book) if Path(folder) == EXAMPLE else load_rules(folder)


def run(*args):
    """(exit code, what is printed, what is printed as an error) of one rules command."""
    out, err = io.StringIO(), io.StringIO()
    fast = mock.patch("frc_design_kernel.rules.commands.load_rules", once_read), mock.patch("frc_design_kernel.cli.generator", lambda: {"library": "", "version": "", "commit": ""})
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), fast[0], fast[1]:
        try:
            code = main(["rules", *args])
        except SystemExit as stopped:       # argparse: a command that is not written as it should be
            code = stopped.code
    return code, out.getvalue(), err.getvalue()


class Command(unittest.TestCase):
    """Help for tests that run a command on the example, as it is or with one thing changed."""
    maxDiff = None

    def folder(self, change=None):
        if not change:
            return str(EXAMPLE)
        data = example()
        change(data)
        return str(written(data))

    def printed(self, *args, change=None):
        """What a command prints that finds an answer."""
        code, out, err = run(*args, "--rules", self.folder(change))
        self.assertEqual((code, err), (0, ""))
        return out

    def lines(self, *args, change=None):
        return self.printed(*args, change=change).splitlines()

    def wrong(self, *args, says, change=None, folder=None):
        """The command fails with one plain line of error, which says all of this, and prints nothing else."""
        code, out, err = run(*args, "--rules", folder or self.folder(change))
        self.assertEqual((code, out), (1, ""), err)
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertTrue(err.startswith("Error: "), err)
        for word in says:
            self.assertIn(word, err)


class Folder(Command):
    """Which folder --rules means."""

    def test_the_newest_of_dated_folders(self):
        """Catches an older edition that is read, or a folder or a file that is no edition and is taken for one."""
        with tempfile.TemporaryDirectory() as keep:
            for name, wide in [("2031-03-14", "25 ft"), ("2031-11-02", "26 ft"), ("2030-12-30", "27 ft"), ("zz-notes", "28 ft")]:
                data = example()
                data["field"]["size"]["width"] = wide
                (Path(keep) / name).mkdir()
                for file, text in data.items():
                    (Path(keep) / name / f"{file}.json").write_text(json.dumps(text), encoding="utf-8")
            (Path(keep) / "2031-12-31").write_text("a file", encoding="utf-8")
            code, out, _ = run("get", "size.width", "--rules", keep)
            self.assertEqual((code, out.splitlines()[0]), (0, "size.width: 26 ft (7924.8 mm)"))
            code, out, _ = run("get", "size.width", "--rules", str(Path(keep) / "2030-12-30"))
            self.assertEqual((code, out.splitlines()[0]), (0, "size.width: 27 ft (8229.6 mm)"))

    def test_no_rules(self):
        """Catches a traceback, or nine faults, for a folder that is not there or that holds no rules."""
        with tempfile.TemporaryDirectory() as keep:
            (Path(keep) / "empty").mkdir()
            (Path(keep) / "seasons" / "2031-03-14").mkdir(parents=True)
            (Path(keep) / "note.txt").write_text("a file", encoding="utf-8")
            for command in (["get", "size.width"], ["find", "yard"], ["check"]):
                self.wrong(*command, folder=str(Path(keep) / "nowhere"), says=["nowhere", "is not a folder", "Fix: "])
                self.wrong(*command, folder=str(Path(keep) / "note.txt"), says=["note.txt", "is not a folder"])
                self.wrong(*command, folder=str(Path(keep) / "empty"), says=["empty", "holds no rules", "game.json"])
                self.wrong(*command, folder=str(Path(keep) / "seasons"), says=["2031-03-14", "holds no rules"])

    def test_a_folder_with_faults(self):
        """Catches an answer from a season that has faults, or a traceback for one that does not read."""
        def slip(d):
            d["field"]["zones"]["yard"]["deep"] = "54 inn"
        for command in (["get", "size.width"], ["find", "crate"]):
            self.wrong(*command, change=slip, says=["field.json yard.deep", '"inn"'])
            self.wrong(*command, folder=str(written({**example(), "terms": "{"})), says=["terms.json line 1", "is not valid JSON"])

    def test_the_folder_must_be_named(self):
        """Catches a command that reads some folder nobody named, or that asks for one it does not need."""
        for command in (["get", "size.width"], ["find", "yard"], ["check"]):
            code, out, err = run(*command)
            self.assertEqual((code, out), (2, ""))
            self.assertIn("--rules", err)
        self.assertEqual(run("means", "lip")[0], 0)
        code, _, err = run()
        self.assertEqual(code, 2)
        self.assertIn("find", err)


class Get(Command):
    """rules get: a value and what its property means."""

    def test_a_value(self):
        """Catches a value with no base unit, no source or no meaning."""
        self.assertEqual(self.lines("get", "barn.opening.bottom"),
                         ["barn.opening.bottom: 48 in (1219.2 mm)", "  src: manual 3.5", "  opening.bottom: Carpet to its lowest edge."])
        self.assertEqual(self.lines("get", "limits.height.max"),
                         ["limits.height.max: 66 in (1676.4 mm)", "  of: floor to the top, at any time", "  src: manual R91", "  limits.height.max: The tallest it may ever be."])

    def test_what_else_is_known_of_a_value(self):
        """Catches a value that was chosen and is given as printed, or other sources that are not told."""
        self.assertEqual(self.lines("get", "hoop.mass")[:3],
                         ["hoop.mass: 3.2 oz (0.0907 kg)", "  assumed: weighed on one sample; no mass is printed", "  src: manual 5.6"])
        self.assertEqual(self.lines("get", "barn.opening.outline.rectangle.y"),
                         ["barn.opening.outline.rectangle.y: 16 in (406.4 mm)", "  src: manual 3.5", "  differs: 15 3/4 in (drawings sheet 6)", "  outline: rectangle: [along faces, across]."])
        self.assertIn("  differs: One page says a dozen or so. (manual 5.6)", self.lines("get", "total.pumpkin"))

    def test_kinds_of_value(self):
        """Catches a limit, a range, a tolerance, a word, a flag or a count that prints wrongly, or with a unit that it has not."""
        for path, text in [("limits.reach.far", "at most 1 ft 2 in (355.6 mm)"), ("bale.mass", "0.7 to 0.9 lb (0.3175 to 0.4082 kg)"), ("bale.mass.low", "0.7 lb (0.3175 kg)"),
                           ("pumpkin.shape.ball.diameter", "8 1/2 in +/- 1/4 (215.9 mm, 209.55 to 222.25 mm)"), ("teleop.lasts", "1 min 50 s (110 s)"), ("barn.opening.slope", "75 deg"),
                           ("yard.height", "none (no limit)"), ("parts.branch.lamps.each", "any (no limit)"), ("bale.part", "hd-101"), ("hang.looked_at", "at the end"), ("guardrail.see_through", "true"),
                           ("limits.reach.sides", "1"), ("parts.lights.signal.number", "1 to 2"), ("limits.drive.motors", "at most 6"), ("parts.branch.motor.protection", "at most 40 A"),
                           ("limits.battery.capacity", "17 to 18 Ah"), ("stall.starts.bale", "20"), ("limits.bumpers.backing.tall", "4 1/2 in +/- 1/2 (114.3 mm, 101.6 to 127 mm)"),
                           ("accuracy.says", "Field sizes are nominal. Drawings hold 0.4 in and 2 deg."), ("limits.console.mass", "at most 12 kg"), ("limits.weight.bumpers.without", "nothing")]:
            self.assertEqual(self.lines("get", path)[0], f"{path}: {text}")

    def test_lists(self):
        """Catches a list that prints as one value, or as code."""
        self.assertEqual(self.lines("get", "barn.at"),
                         ["barn.at:", "  x: 20 in (508 mm)", "  y: 150 in (3810 mm)", "  src: manual 3.5", "  placed.at: Where it is: [x, y] or [x, y, z] in the field's frame. A solid stands on z: it is the height of its lowest point."])
        self.assertEqual(self.lines("get", "parts.motors.mule.part_numbers")[0], "parts.motors.mule.part_numbers: 217-0000, mu-12")
        self.assertEqual(self.lines("get", "limits.battery.size")[:4], ["limits.battery.size:", "  x: 7 in (177.8 mm)", "  y: 3 in (76.2 mm)", "  z: 16.8 cm (168 mm)"])
        self.assertEqual(self.lines("get", "barn.frames", change=lambda d: d["places"]["barn"].update(frames=["1 in", "2 in", "3 in", "4 in"]))[:5],
                         ["barn.frames:", "  1: 1 in (25.4 mm)", "  2: 2 in (50.8 mm)", "  3: 3 in (76.2 mm)", "  4: 4 in (101.6 mm)"])

    def test_a_source_of_one_of_a_list(self):
        """Catches a value of a list with a source of its own that is told another's."""
        def change(d):
            d["field"]["hangs"]["bar"]["at"][1] = {"is": "150 in", "src": "drawings sheet 3"}
        self.assertEqual(self.lines("get", "bar.at", change=change)[:7],
                         ["bar.at:", "  x: 40 in (1016 mm)", "    src: manual 3.7", "  y: 150 in (3810 mm)", "    src: drawings sheet 3", "  z: 33 in (838.2 mm)", "    src: manual 3.7"])

    def test_one_is_enough(self):
        """Catches limits of which one is enough that print as if all were needed."""
        self.assertEqual(self.lines("get", "limits.bumpers.frame_gap")[:4],
                         ["limits.bumpers.frame_gap: one of these is enough", "  deep: at most 3/8 in (9.525 mm)", "  wide: at most 9 in (228.6 mm)", "  src: manual R93"])

    def test_drawn(self):
        """Catches an outline or a shape that prints as code, or in an unnamed unit."""
        self.assertEqual(self.lines("get", "yard.outline")[:5], ["yard.outline: points (x, y) in mm", "  0, 749.3", "  1371.6, 749.3", "  1371.6, 1282.7", "  0, 1282.7"])
        self.assertEqual(self.lines("get", "barn.opening.outline")[:5], ["barn.opening.outline: points (x, y) in mm", "  -457.2, -203.2", "  457.2, -203.2", "  457.2, 203.2", "  -457.2, 203.2"])
        self.assertEqual(self.lines("get", "crate.shape")[:2],
                         ["crate.shape: a shape in mm, about its own 0, 0, 0", '  {"kind": "box", "fromMm": [-279.4, -698.5, 0], "toMm": [279.4, 698.5, 381.0]}'])
        taper = self.lines("get", "manger.shape")
        self.assertEqual(taper[:4], ["manger.shape: a solid whose faces lean, in mm", "  bottom: points (x, y)", "    -381, -254", "    381, -254"])
        self.assertEqual(taper[6:8], ["  top: points (x, y)", "    -254, -127"])
        self.assertIn("  tall: 304.8", taper)

    def test_an_extra_value(self):
        """Catches a value of a record's own that is told the meaning of something else."""
        self.assertEqual(self.lines("get", "barn.out")[-1], "  barn.out: a value of this record's own, which the format does not name.")

    def test_alliance(self):
        """Catches red's place that is blue's. The field turns: x is 612.4 - 20 = 592.4, and y is 300 - 150 = 150."""
        red = self.lines("get", "barn.at", "--alliance", "red")
        self.assertEqual(red[:3], ["barn.at:", "  x: 592.4 in (15046.96 mm)", "  y: 150 in (3810 mm)"])
        self.assertEqual(self.lines("get", "barn@red.at")[:3], ["barn@red.at:", *red[1:3]])
        self.wrong("get", "barn.at", "--alliance", "green", says=['"green"', "blue, red"])

    def test_spot(self):
        """Catches a spot that is not asked for, or that is told what its record is. The far stall is at 300 - 60 = 240."""
        self.assertEqual(self.lines("get", "stall.at", "--spot", "far"), ["stall.at:", "  x: 612.4 in (15554.96 mm)", "  y: 240 in (6096 mm)", "  src: manual 3.8", "  variants: field welded, not bolted", "  spot.at: Where it is."])
        self.assertEqual(self.lines("get", "rack.faces", "--spot", "3.b", "--alliance", "red")[-1], "  spot.faces: Which way it looks in plan.")
        self.assertEqual(self.lines("get", "near_bales.at.y", "--spot", "2")[0], "near_bales.at.y: 114 in (2895.6 mm)")
        self.assertEqual(self.lines("get", "rack.post.tip", "--spot", "3.b")[-1], "  post.tip: Carpet to its top.")
        self.wrong("get", "stall.at", "--spot", "middle", says=['"middle"', "far, near"])
        self.wrong("get", "stall.at", says=["stands at 2 spots", "near, far"])

    def test_variants(self):
        """Catches a variant that is ignored, and an answer that does not tell which variant it took."""
        self.assertEqual(self.lines("get", "size.length")[:3], ["size.length: 612.40 in (15554.96 mm)", "  src: drawings sheet 1", "  variants: field welded, not bolted"])
        for flags in (["--field", "bolted"], ["--field=bolted"]):
            self.assertEqual(self.lines("get", "size.length", *flags)[:3], ["size.length: 611.75 in (15538.45 mm)", "  src: drawings sheet 2", "  variants: field bolted, not welded"])
        code, out, _ = run("get", "--gate", "high_gate", "--rules", str(EXAMPLE), "--field", "bolted", "swing.at.z")
        self.assertEqual((code, out.splitlines()[0]), (0, "swing.at.z: 30 in (762 mm)"))
        self.assertEqual([line for line in self.lines("get", "barn.opening.bottom", "--field", "bolted") if "variants" in line], [])
        self.wrong("get", "size.length", "--feild", "bolted", says=["--feild", 'Did you mean "field"'])
        self.wrong("get", "size.length", "--field", "boltde", says=['"boltde"', 'Did you mean "bolted"'])

    def test_a_flag_is_not_shortened(self):
        """Catches a kind of variant that is taken for a longer flag of get that begins so."""
        def change(d):
            d["game"]["variants"]["all"] = ["few", "many"]
            d["places"]["barn"]["out"] = {"by": "all", "few": "20 in", "many": "21 in"}
        self.assertEqual(self.lines("get", "barn.out", "--all", "many", change=change)[0], "barn.out: 21 in (533.4 mm)")

    def test_how_it_must_be_written(self):
        """Catches a flag with no value, or a second path, that is passed over."""
        for args, says in [(["size.length", "--field"], "--field"), (["size.length", "--field", "--json"], "--field"), (["size.length", "size.width"], "size.width"), ([], "path"), (["size.length", "-f", "x"], "-f")]:
            code, out, err = run("get", *args, "--rules", str(EXAMPLE))
            self.assertEqual((code, out), (2, ""), args)
            self.assertIn(says, err.splitlines()[-1])

    def test_unit(self):
        """Catches a number that is converted wrongly, or only in part."""
        for path, unit, text in [("barn.opening.bottom", "ft", "4 ft"), ("limits.reach.far", "in", "at most 14 in"), ("limits.console.mass", "g", "at most 12000 g"), ("teleop.lasts", "min", "1.8333 min"),
                                 ("pumpkin.shape.ball.diameter", "mm", "215.9 mm, 209.55 to 222.25 mm"), ("parts.branch.motor.protection", "A", "at most 40 A")]:
            self.assertEqual(self.lines("get", path, "--unit", unit)[0], f"{path}: {text}")
        self.assertEqual(self.lines("get", "barn.at", "--unit", "ft")[1:3], ["  x: 1.6667 ft", "  y: 12.5 ft"])
        self.assertEqual(self.lines("get", "limits.bumpers.frame_gap", "--unit", "mm")[1:3], ["  deep: at most 9.525 mm", "  wide: at most 228.6 mm"])
        self.assertEqual(self.lines("get", "yard.outline", "--unit", "in")[:3], ["yard.outline: points (x, y) in in", "  0, 29.5", "  54, 29.5"])

    def test_a_unit_that_does_not_fit(self):
        """Catches a unit of another kind, of a range, or of something that has none, that gives a number or a traceback."""
        self.wrong("get", "barn.opening.bottom", "--unit", "lb", says=["--unit", '"lb"', "cm, ft, in, m, mm"])
        self.wrong("get", "barn.opening.bottom", "--unit", "furlong", says=["--unit", '"furlong"'])
        self.wrong("get", "bale.mass", "--unit", "kg", says=["--unit", "0.7 to 0.9 lb is a range", ".low or its .high"])
        self.wrong("get", "bale.part", "--unit", "in", says=["--unit", "text has no unit"])
        self.wrong("get", "yard.height", "--unit", "in", says=["--unit", "none has no unit"])
        self.wrong("get", "limits.reach.sides", "--unit", "in", says=["--unit", '"in"'])
        self.wrong("get", "crate.shape", "--unit", "in", says=["--unit", "a shape"])
        self.wrong("get", "manger.shape", "--unit", "in", says=["--unit", "a shape"])
        self.wrong("get", "yard.outline", "--unit", "lb", says=["--unit", '"lb"'])
        self.wrong("get", "barn.at", "--unit", "lb", says=["--unit", '"lb"'])

    def test_a_path_that_names_nothing(self):
        """Catches a slip in a path that gives something else, or a traceback."""
        for path, says in [("yrad.deep", 'Did you mean "yard"'), ("yard.depe", 'Did you mean "deep"'), ("yard", "is not one value"), ("barn.takes", "is not one value"), ("", "names the ID"), ("barn.at.x.low", "has no low end"),
                           ("limits.start.height.low", "has no low end"), ("limits", "is not one value"), ("barn@green.at", "green"), ("pond@red.at", "each alliance"), ("barn..at", "names the field"), ("barn.at.w", '"w"'),
                           ("G90.must_not", "is not one value"), ("crate.shape.box", "")]:
            if path == "crate.shape.box":
                self.assertEqual(self.lines("get", path)[0], "crate.shape.box:")
            else:
                self.wrong("get", path, says=[says])

    def test_the_library_gives_the_same(self):
        """Catches a command that answers from something else than the data that programs use."""
        from .rules_cases import as_it_is
        for path in ["barn.opening.bottom", "limits.weight.robot.max", "bale.mass"]:
            value = as_it_is().get(path)
            answer = json.loads(self.printed("get", path, "--json"))["answer"]
            self.assertEqual([answer[name] for name in ("kind", "value", "limit", "low", "high", "printed", "src")], [value.kind, value.value, value.limit, value.low, value.high, value.printed, value.src])


class Json(Command):
    """rules get --json: the same as plain data."""

    def json(self, *args, change=None):
        return json.loads(self.printed("get", *args, "--json", change=change))

    def test_a_value(self):
        """Catches a number whose unit is not told, or that is told in the unit it is printed in."""
        self.assertEqual(self.json("barn.opening.bottom"), {
            "path": "barn.opening.bottom", "alliance": "blue", "spot": None, "variants": {},
            "means": {"key": "opening.bottom", "means": "Carpet to its lowest edge."},
            "answer": {"kind": "length", "value": 1219.2, "unit": "mm", "limit": None, "low": None, "high": None, "printed": "48 in", "of": None, "assumed": None, "src": "manual 3.5", "differs": [], "name": None}})

    def test_in_another_unit(self):
        """Catches a value in the unit asked whose ends stay in mm."""
        got = self.json("pumpkin.shape.ball.diameter", "--unit", "in")["answer"]
        self.assertEqual((got["unit"], round(got["value"], 9), round(got["low"], 9), round(got["high"], 9), got["printed"]), ("in", 8.5, 8.25, 8.75, "8 1/2 in +/- 1/4"))
        self.assertEqual([one["value"] for one in self.json("barn.at", "--unit", "cm")["answer"]], [50.8, 381.0])
        self.assertEqual([round(number, 9) for number in self.json("yard.outline", "--unit", "cm")["answer"][1]], [137.16, 74.93])

    def test_kinds(self):
        """Catches a range with a number of its own, a list of which one is enough that loses that, and a shape that is not plain data."""
        mass = self.json("bale.mass")["answer"]
        self.assertEqual((mass["value"], mass["unit"], round(mass["low"], 6)), (None, "kg", 0.317515))
        self.assertEqual([(one["name"], one["limit"], one["value"]) for one in self.json("limits.bumpers.frame_gap")["answer"]["any"]], [("deep", "at most", 9.525), ("wide", "at most", 228.6)])
        self.assertEqual([one["value"] for one in self.json("limits.weight.robot.without")["answer"]], ["bumpers", "battery"])
        self.assertEqual(self.json("limits.weight.bumpers.without")["answer"], [])
        self.assertEqual(self.json("crate.shape")["answer"], {"kind": "box", "fromMm": [-279.4, -698.5, 0.0], "toMm": [279.4, 698.5, 381.0]})
        self.assertEqual(self.json("yard.outline")["answer"], [[0.0, 749.3], [1371.6, 749.3], [1371.6, 1282.7], [0.0, 1282.7]])
        taper = self.json("manger.shape")["answer"]["taper"]
        self.assertEqual((taper["tall"], taper["top"][0]), (304.8, [-254.0, -127.0]))
        high = self.json("yard.height")["answer"]
        self.assertEqual((high["kind"], high["value"], high["unit"]), ("none", None, None))
        self.assertEqual(self.json("guardrail.see_through")["answer"]["value"], True)
        self.assertEqual((self.json("limits.drive.motors")["answer"]["unit"], self.json("parts.branch.motor.protection")["answer"]["unit"]), (None, "A"))
        self.assertEqual(self.json("barn.opening.outline.rectangle.y")["answer"]["differs"], [{"is": "15 3/4 in", "src": "drawings sheet 6"}])
        self.assertEqual(self.json("pen.tall")["answer"]["src"], ["manual 3.5", "drawings sheet 4"])

    def test_what_was_asked(self):
        """Catches an answer that does not tell for which alliance, spot and variant it is, or that has a meaning where there is none."""
        got = self.json("stall.at", "--spot", "far", "--alliance", "red", "--field", "bolted")
        self.assertEqual([got[name] for name in ("path", "alliance", "spot", "variants")], ["stall.at", "red", "far", {"field": "bolted"}])
        self.assertEqual(got["means"]["key"], "spot.at")
        self.assertIsNone(self.json("barn.out")["means"])


class Means(Command):
    """rules means: what a property, a word or a form means, and how it is written."""

    def means(self, *name):
        code, out, err = run("means", *name)
        self.assertEqual((code, err), (0, ""))
        return out.splitlines()

    def test_a_property(self):
        """Catches a property that is told without its meaning, what it holds, or how that is written."""
        self.assertEqual(self.means("opening.bottom"), [
            "opening.bottom", "  Carpet to its lowest edge.", "  Holds: length. A length.",
            '  Written: "71 in"', '  Written: "= size.width / 2"', '  Written: {"is": "37.5 in", "of": "across the flats"}'])

    def test_a_name_that_several_have(self):
        """Catches a name of which only one thing is told."""
        self.assertEqual([line for line in self.means("bottom") if line and not line.startswith(" ")], ["opening.bottom", "taper.bottom"])

    def test_a_path(self):
        """Catches a limit's property that is not found by its path."""
        self.assertEqual(self.means("limits.reach.far")[:2], ["limits.reach.far", "  How far beyond the perimeter."])

    def test_a_word(self):
        """Catches a word of two words that must be quoted, or that is not told."""
        for name in (["tape inside"], ["tape", "inside"], ["edge: tape inside"]):
            self.assertEqual(self.means(*name), ["edge: tape inside", "  The tape is part of the zone."])

    def test_a_property_that_holds_a_word(self):
        """Catches a property whose words are not listed."""
        self.assertEqual(self.means("zone.edge"), ["zone.edge", "  Whether the tape is part of it. Left out, it is not said.", "  Holds: word edge. One of a list of words.",
                                                   "  tape inside: The tape is part of the zone.", "  tape outside: The tape is not part of the zone."])

    def test_a_form(self):
        """Catches a form with no example to copy."""
        self.assertEqual(self.means("form: range"), ["form: range", "  Both ends are printed. It has a low and a high, and no one number between.", '  Written: "0.7 to 0.9 lb"', '  Written: "1 to 2"'])
        self.assertIn("form: range", self.means("range"))

    def test_a_kind_of_record(self):
        """Catches a kind of record that does not tell its fields and what must be there."""
        told = self.means("window")
        self.assertEqual(told[:4], ["window", "  A span of time with a name, inside one period. It has one of `first`, `last` and `timer`.", "  It must have `in`.", "  It has exactly one of `first`, `last` and `timer`."])
        self.assertIn("  in (period): The period that it is in.", told)
        self.assertIn("  bottom (length): Carpet to its lowest edge.", self.means("place.opening"))
        self.assertIn("  axis (word axis): Which way it lies; x if left out. It may be left out.", self.means("shape: tube"))
        self.assertIn("  periods (records period): The parts of a match, in order.", self.means("clock.json"))

    def test_units(self):
        """Catches units that are not listed."""
        self.assertIn("  Written: in, ft, mm, cm, m", self.means("unit: length"))

    def test_the_whole_format(self):
        """Catches a property, a word, a form or a note of fields.json that the whole format leaves out."""
        from frc_design_kernel.rules import meanings
        told = self.means()
        self.assertTrue(told[0].startswith("rules: One folder holds one edition of a game's rules, in nine files."))
        for one in meanings.everything():
            line = next((line for line in told if line.startswith(f"{one.key}: " if not one.holds else f"{one.key} ({one.holds}): ")), None)
            self.assertIsNotNone(line, one.key)
            for text in (one.means, *one.notes):
                self.assertIn(text, line)
        self.assertIn('  "0.7 to 0.9 lb"', told)

    def test_an_unknown_name(self):
        """Catches a slip that is answered with nothing, with a traceback, or with every name there is."""
        for name, near in [("botom", "bottom"), ("opening.botom", "opening.bottom"), ("tape insde", "tape inside")]:
            code, out, err = run("means", name)
            self.assertEqual((code, out, len(err.splitlines())), (1, "", 1))
            self.assertIn(f'"{name}"', err)
            self.assertIn(near, err)
            self.assertLess(len(err), 300)
        code, _, err = run("means", "xyzzyq")
        self.assertEqual(code, 1)
        self.assertIn("rules means", err)


class Whole(unittest.TestCase):
    """The commands as they are called, with nothing stood in for."""

    def command(self, *args):
        done = subprocess.run([sys.executable, "-X", "importtime", "-m", "frc_design_kernel", "rules", *args], capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
        timed = [line for line in done.stderr.splitlines() if line.startswith("import time:")]
        return done.returncode, done.stdout, [line for line in done.stderr.splitlines() if line not in timed], "\n".join(timed)

    def test_as_it_is_called(self):
        """Catches a command that works only in the tests, or that needs the CAD kernel to answer."""
        code, out, err, imported = self.command("get", "limits.height.max", "--rules", str(EXAMPLE))
        self.assertEqual((code, out.splitlines()[0], err), (0, "limits.height.max: 66 in (1676.4 mm)", []))
        self.assertIn("frc_design_kernel.rules.rules", imported)
        self.assertNotIn("OCP", imported)

    def test_a_failure_as_it_is_called(self):
        """Control: a command that finds nothing fails, with one line of error and no traceback."""
        code, out, err, _ = self.command("find", "G900", "--rules", str(EXAMPLE))
        self.assertEqual((code, out, len(err)), (1, "", 1))

    def test_the_least_folder_is_told_its_faults(self):
        """Control: a folder that has all nine files and nothing in them is a rules folder, and its faults are told."""
        code, _, err = run("get", "size.width", "--rules", str(written(small())))
        self.assertEqual(code, 1)
        self.assertIn("game.json", err)


if __name__ == "__main__":
    unittest.main()
