"""The design source: expressions, the schema checker, "each" and the cross-reference checks."""
import unittest

from frc_design_kernel import DesignError
from frc_design_kernel.source import schema
from frc_design_kernel.source.expressions import evaluate

from .helpers import edited, load_data


def keywords_in(node):
    """Every schema keyword used anywhere in a schema, skipping the names of properties and definitions."""
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key in ("properties", "$defs"):
                for child in value.values():
                    found |= keywords_in(child)
            else:
                found |= keywords_in(value)
    elif isinstance(node, list):
        for item in node:
            found |= keywords_in(item)
    return found


class Expressions(unittest.TestCase):
    def test_arithmetic_and_names(self):
        """Catches wrong arithmetic or a parameter that is not substituted."""
        self.assertAlmostEqual(evaluate("=(wide - 2 * wall) / 2 + sqrt(16)", {"wide": 100, "wall": 3}), 51.0)
        self.assertAlmostEqual(evaluate("=180 * tan(radians(45)) - 2 ** 3", {}), 172.0)

    def test_code_is_refused(self):
        """Catches the expression door opening to arbitrary code."""
        for text in ('=__import__("os").getcwd()', "=[1, 2][0]", "=wide if wide else 1", '="text"', "=wide.real", "=1 < 2"):
            with self.assertRaises(DesignError, msg=text):
                evaluate(text, {"wide": 1})

    def test_unknown_name_suggests_the_near_one(self):
        """Catches a misspelt parameter passing silently or failing without a hint."""
        with self.assertRaisesRegex(DesignError, 'uses "widht".*Did you mean "width"'):
            evaluate("=widht / 2", {"width": 10})

    def test_divide_by_zero_is_a_design_error(self):
        """Catches a crash where a plain message is owed."""
        with self.assertRaisesRegex(DesignError, "cannot be worked out"):
            evaluate("=1 / zero", {"zero": 0})


class SchemaChecker(unittest.TestCase):
    def test_schema_uses_only_keywords_the_checker_knows(self):
        """Catches a schema rule that the small checker would silently ignore."""
        self.assertEqual(keywords_in(schema.load_schema()) - schema.KEYWORDS, set())

    def test_an_unknown_keyword_is_noticed(self):
        """Control: the keyword scan can fail."""
        self.assertEqual(keywords_in({"properties": {"a": {"maximum": 3}}}) - schema.KEYWORDS, {"maximum"})

    def test_minimal_design_loads(self):
        """Catches the checker refusing a correct source."""
        design = load_data(edited())
        self.assertEqual(design.data["solids"][0]["shape"]["toMm"], [50, 40, 100])
        self.assertEqual(design.data["solids"][1]["shape"]["toMm"], [50, 40, 110])

    def expect(self, change, pattern, files=None):
        with self.assertRaisesRegex(DesignError, pattern):
            load_data(edited(change), files)

    def test_messages_name_the_entry_and_the_fix(self):
        """Catches a vague message: each must say which entry is wrong and what to do."""
        self.expect(lambda d: d["solids"][1]["shape"].pop("toMm"), r'solids\[1\] "runner" shape: is missing "toMm"\. Fix: Add "toMm"')
        self.expect(lambda d: d["solids"][0]["shape"].update(kind="boxx"), r'solids\[0\] "block" shape: has the unknown kind "boxx"\. Fix: Did you mean "box"')
        self.expect(lambda d: d["solids"][0].update(colour="red"), r'has an unknown field "colour"\. Fix: .*Allowed fields: name, group')
        self.expect(lambda d: d["solids"][0]["shape"].update(fromMm=[0, 0]), r"shape\.fromMm: must have exactly 3 items, not 2")
        self.expect(lambda d: d["solids"][0]["shape"].update(toMm=[50, 40, "tall"]), r'shape\.toMm\[2\]: "tall" is not an allowed value\. Fix: Give a number, or an expression')
        self.expect(lambda d: d["units"].update(length="in"), r'units\.length: must be "mm"')
        self.expect(lambda d: d.update(custom={"Hook": {"reason": "x" * 30, "limits": "y" * 30}}), r'custom\.Hook: "Hook" is not in the allowed form\. Fix: Name a custom shape')

    def test_bad_json_names_the_line(self):
        """Catches a JSON typo surfacing as a stack trace."""
        import tempfile
        from pathlib import Path
        from frc_design_kernel.source.load import load
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design.json"
            path.write_text('{\n  "name": "x",\n  "units": \n}', encoding="utf-8")
            with self.assertRaisesRegex(DesignError, r"design\.json line 4: is not valid JSON"):
                load(path)


class Each(unittest.TestCase):
    def test_rows_fill_names_and_numbers(self):
        """Catches "each" losing a row, a name placeholder or a per-row number."""
        def change(d):
            d["solids"].append({"name": "post {side}", "group": "base", "each": [{"side": "left", "s": 1}, {"side": "right", "s": -1}],
                                "shape": {"kind": "box", "fromMm": [0, "=s * 100", 0], "toMm": [10, "=s * 110", "=tall"]}})
        solids = load_data(edited(change)).data["solids"]
        self.assertEqual([s["name"] for s in solids], ["block", "runner", "post left", "post right"])
        self.assertEqual(solids[3]["shape"]["fromMm"], [0, -100, 0])
        self.assertNotIn("each", solids[2])

    def test_unfilled_placeholder_is_refused(self):
        """Catches a solid literally named "post {side}" reaching the STEP file."""
        with self.assertRaisesRegex(DesignError, "still has a { } placeholder"):
            load_data(edited(lambda d: d["solids"][0].update(name="post {side}")))


class CrossChecks(unittest.TestCase):
    def expect(self, change, pattern, files=None):
        with self.assertRaisesRegex(DesignError, pattern):
            load_data(edited(change), files)

    def test_names_must_exist_and_be_unique(self):
        """Catches a dangling or repeated name that would otherwise fail deep inside the build."""
        self.expect(lambda d: d["solids"][1].update(name="block"), r'solids\[1\] "block": has the same name as solids\[0\] "block"')
        self.expect(lambda d: d["solids"][1].update(group="slider"), r'names the group "slider", which does not exist\. Fix: Did you mean "slide"')
        self.expect(lambda d: d["poses"]["out"].update(arm=[]), r'poses "out": names the group "arm"')
        self.expect(lambda d: d["motions"]["extend"].update(to="outt"), r'motions "extend": names the pose "outt".*Did you mean "out"')
        self.expect(lambda d: d.update(mounts=[{"group": "slide", "on": "blok", "atMm": [0, 0, 0]}]), r'mounts\[0\] on: names the solid "blok"')

    def test_one_source_of_geometry_and_of_mass(self):
        """Catches a solid with two shapes or a mass that would be counted twice."""
        self.expect(lambda d: d["solids"][0].pop("shape"), r'needs exactly one of "shape" or "part"')
        self.expect(lambda d: d["solids"][0].update(densityKgM3=2700), "has both massKg and densityKgM3")
        self.expect(lambda d: d["groups"]["base"].update(massKg=3), 'its group "base" already has one lump massKg')

    def test_carrier_loop_is_refused(self):
        """Catches two groups that carry each other, which would never finish placing."""
        self.expect(lambda d: d["groups"]["base"].update(carriedBy="slide"), "is carried in a circle: base -> slide -> base")

    def test_motion_needs_one_form(self):
        """Catches a motion that is neither moves nor through, or both."""
        self.expect(lambda d: d["motions"]["extend"].update(through=["in", "out"]), 'needs exactly one of "moves" or "through"')

    def test_bad_operation_numbers_are_refused(self):
        """Catches a zero turning axis or an impossible drop reaching the geometry."""
        self.expect(lambda d: d["poses"]["out"].update(slide=[{"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 0, 0], "travelDeg": 5}]),
                    r'poses "out"\.slide\[0\]: the rotation axis is \[0, 0, 0\]')
        self.expect(lambda d: d["poses"]["out"].update(slide=[{"kind": "path", "curve": "arc", "throughMm": [[0, 0, 0], [1, 0, 0], [2, 0, 0]]}]),
                    "the three arc points are in a straight line")

    def test_a_turning_path_is_written_in_the_source(self):
        """Catches a source that cannot state a path's turn, or whose angles skip the expression step or the check."""
        turning = {"kind": "path", "curve": "straight", "throughMm": [[0, 0, 0], [10, 0, 0]], "turnDeg": [0, "=tall / 4"], "turnAxis": [0, 0, 1]}
        design = load_data(edited(lambda d: d["poses"]["out"].update(slide=[turning])))
        self.assertEqual(design.data["poses"]["out"]["slide"][0]["turnDeg"], [0, 25.0])
        self.expect(lambda d: d["poses"]["out"].update(slide=[{**turning, "turnDeg": [0]}]), r'poses "out"\.slide\[0\]: .*one angle per point')

    def test_custom_must_be_registered_used_and_present(self):
        """Catches a custom shape that skips registration, is dead weight, or has no code file."""
        use = lambda d: d["solids"][0].update(shape={"kind": "custom", "use": "wedge", "parameters": {"riseMm": "=tall / 2"}})
        register = lambda d: d.update(custom={"wedge": {"reason": "No listed shape makes a curved wedge.", "limits": "Outline only, no fillets."}})
        self.expect(use, r'names the custom shape "wedge", which does not exist')
        self.expect(register, r'custom "wedge": is registered but no solid uses it')
        both = lambda d: (use(d), register(d))
        self.expect(both, r"its code file custom/wedge\.py does not exist")
        design = load_data(edited(both), {"custom/wedge.py": "def build(parameters):\n    return None\n"})
        self.assertEqual(design.custom_used, {"wedge": ["block"]})
        self.assertEqual(design.data["solids"][0]["shape"]["parameters"], {"riseMm": 50.0})

    def test_part_file_must_exist_inside_the_folder(self):
        """Catches a missing part file, or a path that reaches outside the design folder."""
        part = lambda file: (lambda d: (d["solids"][0].pop("shape"), d["solids"][0].update(part={"file": file, "solid": "a"})))
        self.expect(part("parts/missing.step"), r'the part file "parts/missing\.step" does not exist')
        self.expect(part("../elsewhere.step"), "is outside the design folder")


if __name__ == "__main__":
    unittest.main()
