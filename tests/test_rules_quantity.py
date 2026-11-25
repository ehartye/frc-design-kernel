"""A number as it is printed, in base units (RULES.md section 3)."""
import unittest

from frc_design_kernel.errors import DesignError


class Printed(unittest.TestCase):
    """quantity.read: a number as it is printed, in base units."""

    def read(self, text):
        from frc_design_kernel.rules import quantity
        return quantity.read(text)

    def refused(self, text, *says):
        with self.assertRaises(DesignError) as caught:
            self.read(text)
        for word in says:
            self.assertIn(word, str(caught.exception))

    def test_units_that_convert(self):
        """Catches a length, mass, time or angle that comes out in the wrong size (a 71 in field read as 71 mm)."""
        for text, kind, value in [("71 in", "length", 1803.4), ("2 ft", "length", 609.6), ("3 mm", "length", 3), ("1.5 cm", "length", 15), ("2 m", "length", 2000),
                                  ("2 lb", "mass", 0.90718474), ("16 oz", "mass", 0.45359237), ("3 kg", "mass", 3), ("250 g", "mass", 0.25),
                                  ("7 s", "time", 7), ("2 min", "time", 120), ("17 deg", "angle", 17)]:
            got = self.read(text)
            self.assertEqual((got.kind, got.unit), (kind, text.split()[1]), text)
            self.assertAlmostEqual(got.value, value, 9, text)
            self.assertEqual((got.limit, got.low, got.high, got.printed), (None, None, None, text))

    def test_fractions(self):
        """Catches 4 3/8 in read as 4 in, and -1 1/2 in read as -1/2 in."""
        for text, inches in [("4 3/8 in", 4.375), ("3/8 in", 0.375), ("-1 1/2 in", -1.5), ("-3/8 in", -0.375), ("-1.50 in", -1.5)]:
            self.assertAlmostEqual(self.read(text).value, inches * 25.4, 9, text)

    def test_joined(self):
        """Catches feet with inches, or minutes with seconds, that lose one of their two parts."""
        self.assertAlmostEqual(self.read("5 ft 4 3/8 in").value, 64.375 * 25.4, 9)
        self.assertAlmostEqual(self.read("1 min 50 s").value, 110, 9)
        self.assertAlmostEqual(self.read("at most 4 ft 6 in").value, 54 * 25.4, 9)

    def test_joined_wrong(self):
        """Catches two units that do not belong together (mixed units), which would add a mass to a length."""
        for text in ["5 ft 3 lb", "2 lb 3 oz", "3 in 2 ft", "1 m 20 cm", "1 min 50 in"]:
            self.refused(text, text, "may be joined")

    def test_kept_units(self):
        """Catches a unit that does not convert being turned into another number, or refused."""
        for unit in "A V W Wh Ah ohm psi bar cfm scfm uF AWG mm2 USD Mbit/s lb/ft3 kg/m3 nm Hz rpm".split():
            got = self.read(f"at most 2.5 {unit}")
            self.assertEqual((got.kind, got.unit, got.value, got.limit), (unit, unit, 2.5, "at most"))

    def test_unit_not_listed(self):
        """Catches a unit that is misspelt or not listed, which a program would not know how to compare."""
        self.refused("54 feet", "feet", "Known", "ft")
        self.refused("at most 1.1 scfh", "scfh", 'Did you mean "scfm"')
        self.refused("5 inches", "inches")

    def test_limits(self):
        """Catches a limit that loses its direction: at most, at least, less than, more than."""
        for words in ["at most", "at least", "less than", "more than"]:
            got = self.read(f"{words} 2 1/4 in")
            self.assertEqual((got.limit, got.low, got.high), (words, None, None))
            self.assertAlmostEqual(got.value, 57.15, 9)
        got = self.read("at most 6")
        self.assertEqual((got.kind, got.value, got.limit, got.unit), ("number", 6, "at most", None))

    def test_ranges(self):
        """Catches a range that keeps only one end, or calls one end the value."""
        got = self.read("0.7 to 0.9 lb")
        self.assertEqual((got.kind, got.value, got.limit), ("mass", None, None))
        self.assertAlmostEqual(got.low, 0.7 * 0.45359237, 12)
        self.assertAlmostEqual(got.high, 0.9 * 0.45359237, 12)
        got = self.read("4 3/4 to 5 1/4 in")
        self.assertAlmostEqual(got.low, 4.75 * 25.4, 9)
        self.assertAlmostEqual(got.high, 5.25 * 25.4, 9)
        got = self.read("1 to 2")
        self.assertEqual((got.kind, got.low, got.high, got.value), ("number", 1, 2, None))

    def test_range_the_wrong_way_round(self):
        """Catches a range whose low is above its high, which nothing could ever satisfy."""
        self.refused("9 to 8 oz", "9 to 8 oz", "low")
        self.refused("2 to 1", "low")

    def test_tolerances(self):
        """Catches a tolerance dropped, put on one side only, or put on the wrong side."""
        got = self.read("6.4 oz +/- 0.3")
        self.assertAlmostEqual(got.value, 6.4 * 0.028349523125, 12)
        self.assertAlmostEqual(got.low, 6.1 * 0.028349523125, 12)
        self.assertAlmostEqual(got.high, 6.7 * 0.028349523125, 12)
        got = self.read("290 in +5 -1")
        self.assertAlmostEqual(got.low, 289 * 25.4, 9)
        self.assertAlmostEqual(got.high, 295 * 25.4, 9)
        got = self.read("16 1/4 in +/- 1/4")
        self.assertAlmostEqual(got.low, 16 * 25.4, 9)

    def test_forms_that_do_not_go_together(self):
        """Catches a limit on a range, a limit with a tolerance, or a tolerance on joined units, whose meaning is not given."""
        for text in ["at most 3 to 4 in", "at most 3 in +/- 1", "5 ft 4 in +/- 1", "3 to 4 in +/- 1", "at most at least 3 in",
                     "5 ft -3 in", "-5 ft 3 in", "3 in +/- -1", "3 in +-5 -1"]:
            self.refused(text, text)

    def test_text_that_is_no_number(self):
        """Catches words, and numbers with no unit, taken as a value."""
        for text in ["14 by 10", "a bit", "", " ", "in", "5", "3in", "3  in", "3 in ", " 3 in", "1/0 in", "1e5 in", "nan in", "1,000 USD", "3 in\n", "٣ in"]:
            self.refused(text)

    def test_a_number_too_large(self):
        """Catches a number so large that it turns into infinity."""
        self.refused("1" * 400 + " in", "ordinary")
        self.refused("1" * 5000 + " in", "ordinary")

    def test_exact(self):
        """Catches rounding noise: 20 in is exactly 508 mm, however it is written."""
        self.assertEqual(self.read("20 in").value, 508.0)
        self.assertEqual(self.read("1 ft 8 in").value, 508.0)
        self.assertEqual(self.read("0.1 in").value, 2.54)

    def test_counts(self):
        """Catches a count that loses its number, and true taken for the number 1."""
        from frc_design_kernel.rules import quantity
        got = quantity.count(45)
        self.assertEqual((got.kind, got.value, got.printed), ("number", 45, "45"))
        with self.assertRaises(DesignError):
            quantity.count(True)

    def test_convert(self):
        """Catches a value given back in the wrong unit, or a length given in pounds."""
        from frc_design_kernel.rules import quantity
        self.assertAlmostEqual(quantity.convert(508, "length", "in"), 20, 9)
        self.assertAlmostEqual(quantity.convert(0.45359237, "mass", "oz"), 16, 9)
        self.assertEqual(quantity.convert(40, "A", "A"), 40)
        for kind, unit in [("length", "lb"), ("A", "V"), ("number", "in"), ("length", "yard")]:
            with self.assertRaises(DesignError):
                quantity.convert(1, kind, unit)


if __name__ == "__main__":
    unittest.main()
