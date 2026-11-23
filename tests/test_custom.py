"""The escape hatch: a custom shape that keeps the contract is built; one that breaks it is refused by name."""
import unittest

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.kernel import props

from .helpers import edited, load_data

GOOD = """import math
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt


def build(parameters):
    return BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), parameters["baseMm"], 0.0, parameters["tallMm"]).Shape()
"""
BODY = "from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox\n\n\ndef build(parameters):\n"
BOX = "BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()"


def with_cone(data):
    data["custom"] = {"cone": {"reason": "A cone has a slanted round side; no listed shape makes one.", "limits": "Sharp tip; no wall thickness."}}
    data["solids"][0]["shape"] = {"kind": "custom", "use": "cone", "parameters": {"baseMm": 30, "tallMm": "=tall"}}
    data["solids"][0]["place"] = [{"kind": "translation", "travelMm": [0, 0, 5]}]


class CustomShapes(unittest.TestCase):
    def build(self, code):
        return kernel.build(load_data(edited(with_cone), {"custom/cone.py": code}))

    def expect(self, code, pattern):
        with self.assertRaisesRegex(DesignError, pattern):
            self.build(code)

    def test_a_shape_that_keeps_the_contract_is_built_and_placed_by_the_source(self):
        """Catches the hatch being closed to fair use, or parameters and placement not reaching the shape."""
        assembly = self.build(GOOD)
        cone = assembly.solids["block"]
        self.assertEqual(cone.kind, "custom")
        self.assertAlmostEqual(props.volume(cone.shape), 3.141592653589793 * 30 ** 2 * 100 / 3, places=4)
        self.assertAlmostEqual(props.bounds(cone.shape)[2], 5.0)
        self.assertEqual([(row["name"], row["lines"], row["usedBy"]) for row in assembly.custom], [("cone", 7, ["block"])])

    def test_other_imports_are_refused_before_the_code_runs(self):
        """Catches custom code reaching for files, the network or a project's own modules."""
        marker = "raise SystemExit('the code ran')\n"
        self.expect("import os\n" + marker + GOOD, r'custom "cone": its code imports "os", which a custom shape may not do')
        self.expect("from pathlib import Path\n" + GOOD, 'imports "pathlib"')
        self.expect("from . import helper\n" + GOOD, "uses a relative import")
        self.expect(BODY + "    import json\n    return " + BOX + "\n", 'imports "json"')

    def test_file_and_code_tricks_are_refused(self):
        """Catches custom code that writes files or runs text as code."""
        self.expect(BODY + "    open('x.txt', 'w')\n    return " + BOX + "\n", 'its code uses "open"')
        self.expect(BODY + "    return eval('1')\n", 'its code uses "eval"')

    def test_the_file_must_define_build(self):
        """Catches a custom file with the wrong entry point failing obscurely."""
        self.expect("def make(parameters):\n    return None\n", "has no build\\(parameters\\) function")

    def test_several_bodies_are_refused(self):
        """Catches a custom shape that returns more than one body, which the contract forbids."""
        code = ("from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox\nfrom OCP.BRep import BRep_Builder\nfrom OCP.TopoDS import TopoDS_Compound\n"
                "from OCP.gp import gp_Pnt\n\n\ndef build(parameters):\n    both, builder = TopoDS_Compound(), BRep_Builder()\n    builder.MakeCompound(both)\n"
                "    builder.Add(both, BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(1, 1, 1)).Shape())\n"
                "    builder.Add(both, BRepPrimAPI_MakeBox(gp_Pnt(5, 5, 5), gp_Pnt(6, 6, 6)).Shape())\n    return both\n")
        self.expect(code, r'solids\[0\] "block" shape: The custom shape "cone" makes 2 solids, not exactly one')

    def test_a_non_shape_or_a_crash_is_refused_with_the_shape_named(self):
        """Catches a custom shape returning a list or number, or raising, without a plain message."""
        self.expect("def build(parameters):\n    return [1, 2]\n", 'the custom shape "cone" returned list, not a shape')
        self.expect("def build(parameters):\n    return parameters['missing']\n", r'the custom shape "cone" failed \(KeyError')


if __name__ == "__main__":
    unittest.main()
