"""rules find: a record by its code, its ID or words of it; and rules check: every fault, what has no geometry, and equal numbers."""
import json
import re
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .rules_cases import as_it_is, example, written
from .test_rules_commands import Command, run


class Find(Command):
    """rules find prints one record in full, or a line for each when several match."""

    def test_by_code(self):
        """Catches a rule that is not found by its code, or not told in full: with its numbers filled in, its conditions and its cost."""
        self.assertEqual(self.lines("find", "G90"), [
            "G90 (conduct.json, conduct)",
            "  says: A robot may not touch an opponent when either robot's bumpers are partly in the opponent's yard in the last 25 s, whoever starts it, directly or through a piece.",
            "  act: touch", "  what: their robot", "  through_pieces: true", "  whoever_starts: true",
            "  must_not:", "    - either bumpers, partly in, their yard",
            "  when: endgame",
            "  cost:", "    - minor", "    - award: loft_rp", "      to: their alliance", "      when: qualification",
            "  src: manual 7.1"])
        self.assertEqual(self.printed("find", "g90"), self.printed("find", "G90"))

    def test_by_a_code_that_others_carry(self):
        """Catches a code that only lists what carries it and does not tell the rule, or that tells the rule and not what carries it."""
        told = self.lines("find", "R91")
        self.assertEqual(told[:2], ["R91 (robot.json, rule)", "  says: Never taller than 66 in, and at most 1 ft 2 in out on 1 side."])
        self.assertEqual(told[3], "Also with this ID or code:")
        self.assertTrue(told[4].startswith("  limits.height (limit): How tall a robot may be."), told)
        self.assertEqual(told[5], "  limits.reach (limit): How far a robot may reach out. far at most 1 ft 2 in; sides 1")
        self.assertEqual(len(told), 6)

    def test_by_a_code_that_no_record_has_for_its_id(self):
        """Catches a code in a list of codes, or of one record only, that is not found."""
        def change(d):
            d["robot"]["limits"]["height"]["code"] = ["R91", "R91b"]
            d["robot"]["limits"]["reach"]["code"] = "R91c"
            d["robot"]["limits"]["drive"]["code"] = ["R91b"]
        self.assertEqual(self.lines("find", "R91c", change=change)[0], "limits.reach (robot.json, limit)")
        self.assertEqual([line.split(" ")[0] for line in self.lines("find", "R91b", change=change)], ["limits.height", "limits.drive"])

    def test_by_id(self):
        """Catches an ID that is not found, or a formula that does not tell its number."""
        self.assertEqual(self.lines("find", "yard")[:-1], [
            "yard (field.json, zone)", "  alliance: each", "  at: 27 in, 40 in", "  outline:", "    rectangle: 54 in (= yard.deep), 21 in (= yard.wide)",
            "  deep: 54 in", "  wide: 21 in", "  edge: tape inside", "  height: none", "  src: manual 3.2"])
        told = self.lines("find", "height")
        self.assertEqual(told[:-1], [
            "limits.height (robot.json, limit)", "  code: R91", "  max:", "    is: 66 in (= limits.start.height + limits.height.more)", "    of: floor to the top, at any time", "  more: 18 in", "  src: manual R91"])
        self.assertRegex(told[-1], '^"height" is also in the words of [0-9]+ more records')

    def test_a_line_names_what_to_ask_for_next(self):
        """Catches a line that names a record by something that does not find it, or that finds it with others."""
        for asked in ["R91", "signal", "launch bale"]:
            lines = [line for line in self.lines("find", asked) if " (" in line and not line.startswith(("  says", "Also"))]
            lines = lines[1:] if lines[0].startswith(f"{asked} (") else lines
            self.assertEqual(len(lines), 2, lines)
            for line in lines:
                path = line.split(" (")[0].strip()
                told = self.lines("find", path)
                self.assertTrue(told[0].startswith(f"{path} ("), told)
                self.assertTrue(any(one.startswith("  src: ") for one in told), told)

    def test_by_path(self):
        """Catches a path that is taken for words, and a path in another case that finds nothing."""
        for asked in ("limits.reach", "LIMITS.Reach"):
            self.assertEqual(self.lines("find", asked), ["limits.reach (robot.json, limit)", "  code: R91", "  far: at most 1 ft 2 in", "  sides: 1", "  src: manual R91"])

        def change(d):
            d["robot"]["parts"]["motors"]["Ox"] = {"name": "Ox", "src": "manual R97"}
            d["robot"]["rules"]["R94"]["says"] = "See parts.motors.Ox too."     # it has every word of the path
        for asked in ("parts.motors.Ox", "parts.motors.ox"):
            self.assertEqual(self.lines("find", asked, change=change)[0], "parts.motors.Ox (robot.json, part)")

    def test_every_kind_of_record(self):
        """Catches a kind of record that can not be found by its ID or its path, or that does not print."""
        from frc_design_kernel.rules.find import Finder
        finder = Finder(as_it_is())
        for entry in finder.rules.book.entries:
            if entry.path:
                found, _ = finder.find(entry.path)
                self.assertEqual([one.path for one in found], [entry.path])
                self.assertEqual(finder.full(found[0])[0], f"{entry.path} ({entry.file}.json, {entry.kind})")
                self.assertEqual(len(finder.full(found[0])) > 1, bool(entry.data))
                self.assertNotIn("\n", finder.line(entry))
        for name, path in [("t3", "tags.t3"), ("coach", "people.coach"), ("mule", "parts.motors.mule"), ("update3", "sources.update3"), ("late", "judged.late")]:
            self.assertEqual(self.lines("find", name)[0].split(" ")[0], path)

    def test_what_a_file_holds_itself(self):
        """Catches the edition, or the symmetry of the field, that no find gives."""
        self.assertEqual(self.lines("find", "game.json")[:4], ["game.json (game.json, game)", "  name: Hay Day", "  season: 2031", "  edition: manual 4, 2031-03-14, with update 3"])
        self.assertIn("  symmetry: turn", self.lines("find", "field.json"))

    def test_an_id_that_several_have(self):
        """Catches only one of two parts with one ID, or both printed in full."""
        self.assertEqual(self.lines("find", "signal"), ["parts.lights.signal (part): Signal light", "parts.wire.signal (part): signals"])

    def test_a_path_that_is_also_an_id(self):
        """Catches a record that is named by its whole path and is not told in full, because another has that ID, and one that hides the other."""
        told = self.lines("find", "frame")
        self.assertEqual((told[0], told[-3:-1]), ("frame (game.json, frame)", ["Also with this ID or code:", "  parts.guard.frame (part): The frame"]))

    def test_by_words(self):
        """Catches words that are not found in what a record says, in its numbers filled in, in its other words, or in what a limit means."""
        for asked, found in [(["touch", "opponent", "yard"], ["G90"]), (["last 25 s", "yard"], ["G90"]), (["Crow 2"], ["limits.radio"]), (["pressed straw"], ["bale"]), (["guides"], ["people.coach"])]:
            told = self.lines("find", *asked)
            self.assertEqual(told[0].split(" ")[0], found[0], asked)
            self.assertIn("says: " if found[0] == "G90" else "  ", "\n".join(told))
        self.assertEqual([line.split(" ")[0] for line in self.lines("find", "how tall may the robot be")], ["limits.start", "limits.height"])

    def test_every_word_must_be_there(self):
        """Catches a record that has only some of the words, or a short word or a number that is found inside another."""
        def change(d):
            d["terms"]["lush"] = {"says": "Green grass, 1200 blades of it.", "src": "manual 11"}
            d["terms"]["turf"] = {"says": "Greenish grass, 120 blades, often.", "src": "manual 11"}
        self.assertEqual([line.split(" ")[0] for line in self.lines("find", "green grass blade", change=change)], ["lush", "turf"])
        self.assertEqual(self.lines("find", "grass 120", change=change)[0], "turf (terms.json, term)")
        self.assertEqual(self.lines("find", "grass of", change=change)[0], "lush (terms.json, term)")
        self.wrong("find", "grass hedge", change=change, says=['"grass hedge"'])

    def test_nothing(self):
        """Catches a search that finds nothing and passes for one that did."""
        self.wrong("find", "G900", says=['"G900"', "Fix: "])
        self.wrong("find", "no such thing", says=['"no such thing"'])
        self.wrong("find", "  ", says=['"  "'])

    MORE = re.compile(r'"(.+)" is also in the words of (\d+ more records?)\. To list them all: rules (.+)')

    def more(self, *asked, change=None):
        """(the lines that a find prints, how many more it says, what the command that it gives prints)."""
        folder = self.folder(change)
        code, out, err = run("find", *asked, "--rules", folder)
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        found = self.MORE.fullmatch(lines[-1])
        if not found:
            return lines, 0, []
        code, listed, err = run(*shlex.split(found[3], posix=True))
        self.assertEqual((code, err, found[1]), (0, "", " ".join(asked)))
        many, _, word = found[2].partition(" ")
        self.assertEqual(word, "more record" if many == "1" else "more records")
        return lines[:-1], int(many), listed.splitlines()

    def test_a_word_that_is_also_an_id_or_a_code(self):
        """Catches a word that is an ID or a code, and that hides every other record that holds it; or a command for those that does not work."""
        def named(lines):
            return [line.strip().split(" ")[0] for line in lines if line.startswith(("  ", "")) and re.match(r" *[\w.@]+ \([\w]+\): ", line)]
        from frc_design_kernel.rules.rules import load_rules
        data = example()
        data["terms"].update(wave={"says": "A signal by hand, 7.3 times."}, nod={"says": "As in 7.3.", "code": "7.3"}, nowhere_else={"says": "Not here."})
        rules = load_rules(written(data))
        with mock.patch("tests.test_rules_commands.once_read", lambda _: rules):
            for asked in ["bumpers", "bar", "yard", "signal", "endgame", "frame", "7.3", "YARD"]:
                lines, many, listed = self.more(asked)
                shown = {lines[0].split(" ")[0], *named(lines)}
                self.assertGreater(many, 0, asked)
                self.assertEqual(len(set(named(listed)) - shown), many, (asked, listed))
                self.assertLessEqual(shown, set(named(listed)))
            self.assertIn("G90", named(self.more("bumpers")[2]))
            for asked in ["limits.reach", "game.json", "touch opponent yard", "launch bale", "nowhere_else", "G90"]:
                lines, many, _ = self.more(asked)
                self.assertEqual((many, [line for line in lines if "more record" in line]), (0, []), asked)

    def test_one_more(self):
        """Catches one more record that is told as several, and a folder or a word with a space that breaks the command."""
        def change(d):
            d["terms"]["zither"] = {"says": "Played.", "code": "Zq 9"}
            d["terms"]["harp"] = {"says": "Like a zither.", "code": ["Zq 9", "H1"]}
            d["terms"]["lyre"] = {"says": "As Zq, of 9."}
        data = example()
        change(data)
        for name in ("a folder of rules", "$rules [1]"):
            with tempfile.TemporaryDirectory() as keep:
                folder = Path(keep) / name
                folder.mkdir()
                for file, one in data.items():
                    (folder / f"{file}.json").write_text(json.dumps(one), encoding="utf-8")
                self.folder = lambda change=None: str(folder)
                for asked, found in [("zither", ["zither", "harp"]), ("Zq 9", ["zither", "harp", "lyre"])]:
                    _, many, listed = self.more(asked)
                    self.assertEqual((many, [line.split(" ")[0] for line in listed]), (1, found))

    def test_words_alone(self):
        """Control: --words looks for words only, prints one record in full, and finds nothing where there is nothing."""
        self.assertEqual(self.lines("find", "--words", "pressed straw")[0], "bale (pieces.json, piece)")
        self.wrong("find", "--words", "xyzzyq", says=['"xyzzyq"'])
        self.assertIn("--words", run("find", "--help")[1])

    def test_one_line_each(self):
        """Catches a line that goes on over many lines, or that says nothing of the record."""
        told = self.lines("find", "bale")
        self.assertEqual(told[0], "bale (pieces.json, piece)")
        told = self.lines("find", "bumpers")
        self.assertEqual(told[0], "limits.bumpers (robot.json, limit)")
        told = self.lines("find", "R91", change=lambda d: d["robot"]["limits"]["reach"].update(says="Measured level.", far="at most 37 in"))
        self.assertEqual(told[-1], "  limits.reach (limit): How far a robot may reach out. far at most 37 in; sides 1")

        def change(d):
            d["places"]["barn"]["opening"]["wobble"] = "3 in"
            d["places"]["hutch"] = {"alliance": "each", "opening": {"wobble": "3 in"}, "src": "manual 3.5"}
        self.assertEqual(self.lines("find", "wobble", change=change), ["barn (place): at 20 in (= tags.t1.at.x + barn.out), 150 in (= tags.t1.at.y); faces 0 deg; out 20 in", "hutch (place): has opening"])
        told = self.lines("find", "launch bale")
        self.assertEqual([line.split(" ")[0] for line in told], ["G93", "G98"])
        self.assertEqual(told[1], "G98 (conduct): A robot may not launch a bale into a loft.")
        self.assertEqual(told[0], "G93 (conduct): A robot may launch a bale only while its bumpers are partly in its own paddock or fully in its own ...")


class InFull(Command):
    """What a record in full tells."""

    def test_a_variant(self):
        """Catches a number that depends on a variant and is given for one of them only."""
        self.assertIn("  from: 306.2 in (welded) or 305.875 in (bolted) (= size.length / 2), 0 in", self.lines("find", "centre"))
        self.assertIn("    - my loft_points, at least, 12 (regional) or 16 (championship) (= loft_rp.needed)", self.lines("find", "loft_rp"))
        self.assertIn("      high_gate: 30 in (= swing.at.z.low_gate + swing.lift)", self.lines("find", "swing"))

    def test_says_by_variant(self):
        """Catches words whose number depends on a variant and is given for one of them only."""
        told = self.lines("find", "pond", change=lambda d: d["field"]["zones"]["pond"].update(says="It is in the middle of {size.length}."))
        self.assertIn("  says (welded): It is in the middle of 612.40 in.", told)
        self.assertIn("  says (bolted): It is in the middle of 611.75 in.", told)

    def test_says_of_what_is_inside(self):
        """Catches words inside an opening, or of a kind with braces, that are not filled, and words of another source that are."""
        def change(d):
            d["places"]["barn"]["opening"]["says"] = "Its bottom is {bottom} up, {barn.out} out."
            d["places"]["barn"]["differs"] = [{"says": "It is {out} up.", "src": "manual 3.5"}]
        told = self.lines("find", "barn", change=change)
        self.assertIn("    says: Its bottom is 48 in up, 20 in out.", told)
        self.assertIn("    - says: It is {out} up.", told)

    def test_left_over(self):
        """Catches a count that is left over and is not told. 60 bales less 6 of the robots, 8 near and 6 in the centre is 40, 20 for each alliance."""
        told = self.lines("find", "stall")
        self.assertEqual(told[told.index("  starts:") + 1], "    bale: 20 (left over)")

    def test_lists_and_nothing(self):
        """Catches a list in a list that runs together, and an empty list that prints as nothing at all."""
        told = self.lines("find", "hang")
        self.assertEqual(told[told.index("  needs:") + 1:told.index("  needs:") + 4],
                         ["    - my robot, touching, my bar", "    - my robot, not touching, [carpet, the base of my mast]", "    - my robot, touching only, [my bar, my mast, pieces, a robot that hangs]"])
        told = self.lines("find", "G95")
        at = told.index("  must_not:")
        self.assertEqual(told[at + 1:at + 8], ["    - any:", "        - all:", "            - my bumpers, beyond, any centre", "            - my robot, touching, carpet", "          when: early", "        - my bumpers, over, their gate_line", "  cost:"])
        self.assertIn("  cost: nothing", self.lines("find", "placing_order"))
        self.assertIn("  true: [auto], [market, not lit], [endgame]", self.lines("find", "barn_open"))


class Check(Command):
    """rules check prints every fault, and lists places to look."""

    def check(self, change=None):
        return run("check", "--rules", self.folder(change))

    def test_no_faults(self):
        """Catches a season with no faults that fails."""
        code, out, err = self.check()
        self.assertEqual((code, err, out.splitlines()[0]), (0, "", "2031-03-14: no faults."))

    def test_every_fault(self):
        """Control: several faults, in reading and in working out, are all printed and the command fails."""
        def change(d):
            d["field"]["zones"]["yard"]["deep"] = "54 inn"
            d["clock"]["windows"]["endgame"]["last"] = "3 min"
            d["terms"]["momentary"]["lasts"] = "4 in"
        code, out, err = self.check(change)
        self.assertEqual(code, 1)
        self.assertIn(": 3 faults.", out.splitlines()[0])
        for line, says in zip(err.splitlines(), ["Error: field.json yard.deep: ", "Error: terms.json momentary.lasts: ", "Error: clock.json endgame: "], strict=True):
            self.assertTrue(line.startswith(says), line)
        self.assertIn("1 fault.", self.check(lambda d: d["terms"]["momentary"].update(lasts="4 in"))[1].splitlines()[0])

    def test_a_file_that_does_not_read(self):
        """Catches a traceback, or lists made from half a folder, when a file does not read."""
        code, out, err = run("check", "--rules", str(written({**example(), "terms": "{", "places": "[]"})))
        self.assertEqual((code, len(out.splitlines())), (1, 1))
        self.assertEqual([line.split(" ")[1].rstrip(":") for line in err.splitlines()], ["places.json", "terms.json"])

    def list_of(self, out, title):
        """The lines under a title."""
        lines = out.splitlines()
        at = next(i for i, line in enumerate(lines) if title in line)
        return [line for line in lines[at + 1:next((i for i in range(at + 1, len(lines)) if not lines[i].startswith(" ")), len(lines))]]

    def test_no_geometry(self):
        """Catches a thing with no geometry that is not listed, or one that has it and is."""
        self.assertEqual(self.list_of(self.check()[1], "no geometry"), [
            "  stands: An area for people, off the field.", "  coach_line: A line for people, off the field.", "  knot: No drawing gives how high it is.",
            "  robot_preload: It needs none: it is wherever the robots are.", "  cellar: Off the field, and no drawing gives it."])
        code, out, _ = self.check(lambda d: [record.pop("no_geometry") for record in (d["field"]["zones"]["stands"], d["field"]["hangs"]["knot"], d["places"]["robot_preload"], d["places"]["cellar"])])
        self.assertNotIn("stands: An area", out)

    def equal(self, change=None):
        code, out, err = self.check(change)
        return {line.partition(": ")[0].strip(): line.partition(": ")[2] for line in self.list_of(out, "in more than one record")}

    def test_equal_numbers(self):
        """Catches a number that is in two records and is not listed, or one that is in one only and is."""
        found = self.equal()
        for number, places in [("2 s", "gap.lasts, lit.grace, judged.late.after_auto"), ("3 s", "judged.late.after_teleop, G92.apart_for"), ("4 s", "judged.climbs.after_teleop, momentary.lasts"),
                               ("5 s", "G92.longest, G95.cost[0].every"), ("15 deg", "bridge.slope, tags.t3.tilt, tags.t4.tilt"), ("60 deg", "pen.lean, rack.spots.step"),
                               ("45 deg", "loft.look, hooks.spots.left.faces"), ("48 in", "culvert.shape.tube.length, bridge.width, near_bales.apart, barn.opening.bottom"),
                               ("36 in", "silo.shape.cylinder.length, centre_bales.spots.step.y, barn.opening.outline.rectangle.x")]:
            self.assertEqual(found.get(number), places, number)
        for number in ("25 s", "35 s", "6 s", "50 deg", "270 deg", "41 in", "6 ft", "5 ft", "25 ft"):
            self.assertNotIn(number, found)

    def test_what_is_not_listed(self):
        """Catches a number that is twice in one record, in another unit, a bare count, a formula, or what a value was or other sources say."""
        def change(d):
            d["conduct"]["G95"]["cost"][0]["every"] = "7 s"
            d["conduct"]["G92"]["apart_for"] = "5 s"
            d["clock"]["periods"]["gap"]["was"] = [{"until": "2031-02-04", "is": "5 s", "src": "update3 4.1"}]
            d["clock"]["periods"]["gap"]["differs"] = [{"is": "5 s", "src": "drawings sheet 1"}]
            d["clock"]["states"]["lit"]["lasts"] = "= G92.longest"
            d["clock"]["windows"]["endgame"]["last"] = "1/12 min"
            d["field"]["guardrail"]["gates"] = 8
            d["robot"]["limits"]["reach"]["sides"] = d["robot"]["limits"]["drive"]["motors"]
        found = self.equal(change)
        self.assertNotIn("5 s", found)
        self.assertNotIn("8", found)
        self.assertNotIn("1/12 min", found)
        self.assertNotIn("6", found)

    def test_limits_and_ranges(self):
        """Catches a limit that is not told to hold the same number as a value, and two equal ranges or joined numbers that are not listed."""
        def change(d):
            d["robot"]["limits"]["reach"]["far"] = "at most 37 in"
            d["pieces"]["hoop"]["mass"] = "0.7 to 0.9 lb"
            d["field"]["guardrail"]["height"] = "6 ft 6 in"
            d["robot"]["limits"]["bumpers"]["frame_gap"]["any"][1]["wide"] = "at most 41 in"
        found = self.equal(change)
        self.assertEqual([found.get(number) for number in ("37 in", "0.7 to 0.9 lb", "6 ft 6 in", "41 in")],
                         ["stall.opening.bottom, limits.reach.far", "bale.mass, hoop.mass", "guardrail.height, G92.apart", "guardrail.gate_width, limits.bumpers.frame_gap.wide"])

    def test_it_does_not_fail(self):
        """Control: what is listed is listed, and the command passes all the same."""
        code, out, _ = self.check()
        self.assertEqual(code, 0)
        self.assertIn("5 records with no geometry", out)


if __name__ == "__main__":
    unittest.main()
