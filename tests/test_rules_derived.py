"""Values that are worked out: formulas, what a path gives, variants, and what says prints. Hand-computed, in base units."""
import math
import subprocess
import sys
import unittest

from frc_design_kernel.errors import DesignError, unknown

from .rules_cases import EXAMPLE, ROOT, Derived

IN = 25.4


class Formulas(unittest.TestCase):
    """formulas.work: the arithmetic of one formula, with named values."""

    NAMED = {"a.long": ("length", 300.0), "a.wide": ("length", 100.0), "a.mass": ("mass", 2.0), "a.lean": ("angle", 60.0), "a.many": ("number", 4),
             "sin.x": ("length", 7.0), "a@red.3.b.at.x": ("length", 5.0), "a.in": ("length", 9.0), "a.amps": ("A", 40.0)}

    def work(self, text):
        from frc_design_kernel.rules import formulas
        return formulas.work(text, self.named)

    def named(self, path):
        if path not in self.NAMED:
            raise unknown("", "path", path, self.NAMED)
        return self.NAMED[path]

    def gives(self, text, kind, number):
        got = self.work(text)
        self.assertEqual(got[0], kind, text)
        self.assertAlmostEqual(got[1], number, places=9, msg=text)

    def refused(self, text, *says):
        with self.assertRaises(DesignError) as caught:
            self.work(text)
        for word in (text, *says):
            self.assertIn(word, str(caught.exception))

    def test_arithmetic(self):
        """Catches a formula worked out wrongly: the order of operations, a division of two lengths, a sign."""
        self.gives("= a.long + a.wide / 2 - 3 * a.wide", "length", 50)
        self.gives("= (a.long - a.wide) / 2", "length", 100)
        self.gives("= a.long / a.wide * a.many", "number", 12)
        self.gives("= -a.long", "length", -300)
        self.gives("= a.amps * 2", "A", 80)
        self.gives("= a.many + 1", "number", 5)

    def test_names_that_are_not_plain(self):
        """Catches a dotted name that the arithmetic cannot read: one like a function, a spot, or a word of the language."""
        self.gives("= sin.x + a@red.3.b.at.x + a.in", "length", 21)

    def test_functions_and_angles(self):
        """Catches degrees taken for radians, in or out: the sine of 60 deg is 0.866, and not that of 60 radians."""
        self.gives("= a.long * sin(a.lean)", "length", 300 * math.sqrt(3) / 2)
        self.gives("= a.long * cos(a.lean)", "length", 150)
        self.gives("= tan(a.lean / 2) * a.wide", "length", 100 / math.sqrt(3))
        self.gives("= atan2(a.wide, a.wide)", "angle", 45)
        self.gives("= atan2(a.wide, a.wide) + a.lean", "angle", 105)
        self.gives("= a.lean * 2", "angle", 120)
        self.gives("= sqrt(a.many) * a.wide", "length", 200)
        self.gives("= max(abs(-a.long), a.wide)", "length", 300)
        self.gives("= min(a.long, a.wide)", "length", 100)

    def test_a_name_alone_is_exact(self):
        """Catches 126 deg that comes back as 125.99999999999999 from radians and back."""
        self.NAMED["a.faces"] = ("angle", 126.0)
        self.assertEqual(self.work("= a.faces"), ("angle", 126.0))

    def test_kinds_that_do_not_fit(self):
        """Catches a bare number added to a length, two kinds added, an area, and a function with the wrong kind of number."""
        self.refused("= a.long + 3", "length", "count")
        self.refused("= a.long - a.mass", "length", "mass")
        self.refused("= a.long * a.wide", "multiplies")
        self.refused("= a.many / a.long", "divides")
        self.refused("= a.long / a.mass", "divides")
        self.refused("= a.long ** 2", "not arithmetic")
        self.refused("= a.many ** 2", "not arithmetic")
        self.refused("= a.wide * sin(a.long)", "sin", "angle")
        self.refused("= sin(0.5)", "sin", "angle")
        self.refused("= sqrt(a.long)", "sqrt")
        self.refused("= atan2(a.long, a.mass)", "atan2")
        self.refused("= max(a.long, 3)", "max")

    def test_what_is_not_a_formula(self):
        """Catches a function that is not in the list, a wrong number of arguments, or anything that is not arithmetic."""
        for bad in ["= asin(a.many)", "= radians(a.many)", "= a.long +", "= [a.long]", "= sin()", "= sin(a.lean, a.lean)", "= min(a.long)", "= a.long a.wide",
                    "= a.many < 3", "= 3 < 4", "=", "= a.long / (a.many - 4)", "= sqrt(-a.many)", "= " + "(" * 300 + "1" + ")" * 300, "= 1" + " + 1" * 3000]:
            self.refused(bad)

    def test_a_word_of_the_language(self):
        """Catches a word of the language that is run: it is a path, and there is none of that name."""
        for text, path in [("= a.long if a.many else a.wide", "if"), ("= max(a.long, key=abs)", "key"), ("= True", "True"), ("= 'x'", "x")]:
            with self.assertRaises(DesignError) as caught:
                self.work(text)
            self.assertIn(f'the path "{path}"', str(caught.exception))

    def test_a_number_written_in_other_ways(self):
        """Control: ordinary numbers are read, so the refusals above are not for the numbers."""
        self.gives("= 1.5 * a.many", "number", 6)
        self.gives("= 1e2", "number", 100)


class Get(Derived):
    """rules.get: one value by its path."""

    def test_every_kind_of_value(self):
        """Catches a value in the wrong unit, or one that has lost its limit, its ends, its source or its words."""
        get = self.rules().get
        self.is_(get("size.width"), "length", 25 * 12 * IN)
        self.is_(get("accuracy.angle"), "angle", 2)
        self.is_(get("early.first"), "time", 35)
        self.is_(get("auto.lasts"), "time", 12)
        self.is_(get("teleop.lasts"), "time", 110)
        self.is_(get("lit.bank"), "number", 6)
        self.is_(get("limits.radio.rate"), "Mbit/s", 6)
        self.is_(get("pumpkin.stiff"), "flag", False)
        height = get("limits.start.height")
        self.assertEqual((height.kind, height.limit, height.printed, height.src), ("length", "at most", "at most 4 ft", "manual R90"))
        self.assertAlmostEqual(height.value, 48 * IN)
        mass = get("bale.mass")
        self.assertEqual((mass.kind, mass.value, mass.limit, mass.printed), ("mass", None, None, "0.7 to 0.9 lb"))
        self.assertAlmostEqual(mass.low, 0.7 * 0.45359237)
        self.assertAlmostEqual(mass.high, 0.9 * 0.45359237)
        self.is_(get("bale.mass.low"), "mass", 0.7 * 0.45359237)
        self.is_(get("pumpkin.shape.ball.diameter.high"), "length", 8.75 * IN)
        mass = get("pumpkin.mass")
        self.assertAlmostEqual(mass.value, 6.4 * 0.028349523125)
        self.assertAlmostEqual(mass.low, 6.1 * 0.028349523125)
        self.assertAlmostEqual(mass.high, 6.7 * 0.028349523125)
        tall = get("limits.height.max")
        self.assertEqual((tall.of, tall.limit, tall.src), ("floor to the top, at any time", None, "manual R91"))
        self.assertEqual(get("hoop.mass").assumed, "weighed on one sample; no mass is printed")
        self.assertEqual(get("total.pumpkin").differs[0]["src"], "manual 5.6")
        self.assertEqual(get("barn.opening.outline.rectangle.y").differs[0]["is"], "15 3/4 in")
        self.assertEqual(get("bale.shape.tube.length").src, "drawings sheet 8")

    def test_words(self):
        """Catches words that are read as a number, or a word of the format that gives no value."""
        get = self.rules().get
        for path, words in [("size.surface", "low pile carpet"), ("limits.radio.part", "Crow 2"), ("yard.edge", "tape inside"), ("limits.bumpers.padding.foam", "any closed foam"), ("barn.then.to", "cellar"),
                            ("G94.longer_than", "momentary"), ("size.carpet", "laid in two halves"), ("bale.part", "hd-101"), ("endgame.in", "teleop")]:
            self.assertEqual((get(path).kind, get(path).value, get(path).printed), ("text", words, words), path)
        self.is_(get("G89.longer_than"), "time", 10)
        self.assertEqual((get("yard.height").kind, get("yard.height").value), ("none", None))
        self.assertEqual((get("parts.motors.latch.on.controller").kind, get("parts.motors.latch.on.controller").value), ("any", None))
        self.is_(get("parts.motors.latch.on.pneumatics"), "number", 1)
        self.assertEqual(get("parts.motors.latch.on.pneumatics").of, "each channel")

    def test_lists(self):
        """Catches a list that comes back as one value, and limits of which one is enough that come back as if all were needed."""
        from frc_design_kernel.rules.worth import AnyOf
        get = self.rules().get
        size = get("limits.battery.size")
        self.assertEqual([(v.kind, v.printed) for v in size], [("length", "7 in"), ("length", "3 in"), ("length", "16.8 cm")])
        self.assertAlmostEqual(size[2].value, 168)
        self.assertNotIsInstance(size, AnyOf)
        gap = get("limits.bumpers.frame_gap")
        self.assertIsInstance(gap, AnyOf)
        self.assertEqual([(v.name, v.limit) for v in gap], [("deep", "at most"), ("wide", "at most")])
        self.assertAlmostEqual(gap[0].value, 0.375 * IN)
        self.assertAlmostEqual(gap[1].value, 9 * IN)
        self.assertAlmostEqual(get("limits.bumpers.frame_gap.wide").value, 9 * IN)
        self.assertEqual([v.value for v in get("limits.start.code")], ["R90", "G99"])
        self.assertEqual([v.value for v in get("hoop.unknown")], ["No mass is printed."])

    def test_formulas(self):
        """Catches a formula worked out wrongly: across files and units, of one end of a range, of a tolerance, of a limit, or with an angle."""
        get = self.rules().get
        self.is_(get("limits.height.max"), "length", 66 * IN)
        self.is_(get("robot_preload.holds.bale"), "number", 3)
        self.is_(get("robot_preload.starts.bale"), "number", 3)
        self.is_(get("hoop.mass"), "mass", 3.2 * 0.028349523125)
        self.is_(get("pen.tall"), "length", 762 * math.sqrt(3) / 2)
        self.is_(get("pen.bearing"), "angle", 30)
        self.is_(get("pen.shape.prism.tall"), "length", 5 * IN)
        self.is_(get("rack.out"), "length", 12 * math.sqrt(3) * IN)
        self.is_(get("rack.post.length"), "length", 12 * IN * math.cos(math.radians(35)))
        self.is_(get("barn.opening.top"), "length", (48 + 16 * math.sin(math.radians(75))) * IN)
        self.is_(get("G94.limit.pumpkin"), "number", 2)
        self.is_(get("tags.t4.panel"), "length", 11 * IN)
        self.assertEqual((get("limits.height.max").printed, get("limits.height.max").unit), ("66 in", "in"))
        self.assertEqual(get("hoop.mass").printed, "3.2 oz")
        self.assertEqual(get("pen.bearing").printed, "30 deg")
        self.assertEqual((get("robot_preload.holds.bale").printed, get("robot_preload.holds.bale").unit), ("3", None))

    def test_feet(self):
        """Catches a worked-out number printed as a decimal foot, and one printed in feet by its source that is not kept."""
        def change(d):
            d["field"]["solids"]["crate"]["at"][0] = "10 ft 11 in"
            d["field"]["zones"]["fold"].update(deep="= size.width / 2 + pen.side / 12", wide="5 ft +/- 1/4", long="5 to 6 ft")
        get = self.rules(change).get
        self.assertEqual((get("fold.deep").printed, get("fold.deep").unit), ("152.5 in", "in"))
        self.assertEqual((get("crate.at.x").printed, get("crate.at.x", alliance="red").printed, get("crate.at.x", alliance="red").unit), ("10 ft 11 in", "481.4 in", "in"))
        self.assertEqual((get("size.width").printed, get("size.width").unit), ("25 ft", "ft"))
        self.assertEqual([get(f"fold.wide{end}").printed for end in ("", ".low", ".high")], ["5 ft +/- 1/4", "57 in", "63 in"])
        self.assertEqual([get(f"fold.long{end}").printed for end in ("", ".low", ".high")], ["5 to 6 ft", "5 ft", "6 ft"])

    def test_minutes(self):
        """Catches a worked-out time printed as a decimal minute, and one printed in minutes by its source that is not kept."""
        def change(d):
            d["scoring"]["judged"]["climbs"]["after_teleop"] = "= teleop.lasts / 10 + endgame.last"
            d["clock"]["states"]["lit"].update(left="= teleop.lasts", shut="2 min +/- 1/4", rests="1 to 2 min")
        get = self.rules(change).get
        self.assertEqual((get("judged.climbs.after_teleop").printed, get("judged.climbs.after_teleop").unit), ("36 s", "s"))
        self.assertEqual(get("lit.left").printed, "110 s")
        self.assertEqual((get("teleop.lasts").printed, get("teleop.lasts").unit), ("1 min 50 s", "min"))
        self.assertEqual([get(f"lit.shut{end}").printed for end in ("", ".low", ".high")], ["2 min +/- 1/4", "105 s", "135 s"])
        self.assertEqual([get(f"lit.rests{end}").printed for end in ("", ".low", ".high")], ["1 to 2 min", "1 min", "2 min"])

    def test_how_a_number_is_printed(self):
        """Catches a number that prints with a tail of digits, with -0, or without its unit."""
        from frc_design_kernel.rules.worth import shown
        self.assertEqual([shown(25.4 * 5 / 3, "length", "in"), shown(-0.00001, "length", "mm"), shown(30.000000001, "angle", "deg"), shown(40, "A", "A"), shown(2.5, "number", None), shown(1219.2, "length", "ft")],
                         ["1.6667 in", "0 mm", "30 deg", "40 A", "2.5", "4 ft"])

    def test_variants(self):
        """Catches a variant that is ignored, or a formula that keeps the first variant's number."""
        rules = self.rules()
        self.is_(rules.get("size.length"), "length", 612.40 * IN)
        self.is_(rules.get("size.length", field="bolted"), "length", 611.75 * IN)
        self.assertEqual((rules.get("size.length").src, rules.get("size.length", field="bolted").src), ("drawings sheet 1", "drawings sheet 2"))
        self.is_(rules.get("centre.from.x", field="bolted"), "length", 611.75 * IN / 2)
        self.is_(rules.get("swing.at.z"), "length", 12 * IN)
        self.is_(rules.get("swing.at.z", gate="high_gate"), "length", 30 * IN)
        self.is_(rules.get("swing.at.z.high_gate"), "length", 30 * IN)
        width = rules.get("gateway.width", gate="high_gate")
        self.assertEqual([round(n / IN, 9) for n in (width.value, width.low, width.high)], [46, 45, 51])
        self.is_(rules.get("loft_rp.needed", event="championship"), "number", 16)
        self.wrong(lambda: rules.get("size.length", feild="bolted"), "feild", "field")
        self.wrong(lambda: rules.get("size.length", field="boltde"), "boltde", 'Did you mean "bolted"')

    def test_what_is_not_there(self):
        """Catches a slip in a path that gives something else, or a whole record that comes back as a value."""
        get = self.rules().get
        self.wrong(lambda: get("yrad.deep"), 'Did you mean "yard"')
        self.wrong(lambda: get("yard.depe"), 'Did you mean "deep"')
        self.wrong(lambda: get("yard"), "yard", "not one value", "deep")
        self.wrong(lambda: get("barn.opening"), "not one value", "bottom")
        self.wrong(lambda: get("barn.takes"), "not one value")
        self.wrong(lambda: get("G90.must_not"), "not one value")
        self.wrong(lambda: get("limits.start.height.low"), "low")
        self.wrong(lambda: get("bale.mass", alliance="green"), "green", "blue")

    def test_no_cad_kernel(self):
        """Catches rules that need the CAD kernel to be read and worked out."""
        code = f"import sys; from frc_design_kernel.rules.rules import load_rules; load_rules({str(EXAMPLE)!r}).solid('crate'); print(sorted(m for m in sys.modules if m.split('.')[0] in ('OCP', 'mujoco', 'numpy')))"
        self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT).stdout.strip(), "[]")

    def test_what_is_given_is_the_askers(self):
        """Catches an answer that changes the next one, because the asker changed a list or a shape in place."""
        rules = self.rules()
        with self.assertRaises(AttributeError):
            rules.get("size.width").value = 0
        rules.get("limits.battery.size").clear()
        rules.get("crate.shape")["toMm"][0] = 0
        rules.get("yard.outline").pop()
        self.assertEqual((len(rules.get("limits.battery.size")), rules.get("crate.shape")["toMm"][0], len(rules.get("yard.outline"))), (3, 11 * IN, 4))

    def test_another_unit(self):
        """Catches a value that is converted with the wrong factor, or to a unit of another kind."""
        rules = self.rules()
        self.assertAlmostEqual(rules.to(rules.get("limits.start.height"), "in"), 48)
        self.assertAlmostEqual(rules.to(rules.get("limits.weight.robot.max"), "lb"), 112)
        self.wrong(lambda: rules.to(rules.get("limits.start.height"), "lb"), "lb", "in")
        self.wrong(lambda: rules.to(rules.get("bale.mass"), "lb"), "low", "high")
        self.wrong(lambda: rules.to(rules.get("size.surface"), "in"), "text")
        self.wrong(lambda: rules.to(rules.get("limits.battery.size"), "in"), "a list")

    def test_limits(self):
        """Catches a limit that a season does not have and that is read as a number, and a slip that is read as no limit."""
        rules = self.rules()
        self.assertEqual(rules.limit("reach.sides").value, 1)
        self.assertEqual(rules.limit("weight.robot.max").limit, "at most")
        self.assertEqual(rules.limit("hold.pumpkin").value, 2)
        self.assertIsNone(rules.limit("hold.hoop"))
        less = self.rules(lambda d: (d["robot"]["limits"]["reach"].pop("sides"), d["robot"]["rules"]["R91"].update(says="No.")))
        self.assertIsNone(less.limit("reach.sides"))
        self.wrong(lambda: less.limit("reach.sides", feild="bolted"), "feild")
        none = self.rules(lambda d: (d["robot"]["limits"].pop("drive"), d["robot"]["rules"].pop("R94")))
        self.assertIsNone(none.limit("drive.motors"))
        self.wrong(lambda: none.limit("drive.motors", field="boltde"), "bolted")
        lighter = self.rules(lambda d: (d["robot"]["limits"]["weight"]["robot"].pop("max"), d["robot"]["rules"]["R92"].update(says="No.")))
        self.assertIsNone(lighter.limit("weight.robot.max"))
        self.assertIsNone(self.rules(lambda d: d["robot"]["limits"]["weight"].pop("inspected")).limit("weight.inspected.max"))
        for slip, hint in [("reech.far", "reach"), ("reach.fra", "far"), ("hold.bail", "bale"), ("reach", "not one value"), ("weight.robot.mxa", "max"), ("weight.robot", "not one value"), ("reach.far.low", "low")]:
            self.wrong(lambda: rules.limit(slip), hint)


if __name__ == "__main__":
    unittest.main()
