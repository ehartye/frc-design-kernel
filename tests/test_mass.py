"""Weight from the design source: ranged masses, weight with no solid, the roll-up, the manifest and inertia.

The numbers are chosen so every expected figure can be checked by hand.
"""
import contextlib
import copy
import io
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.builder import placement
from frc_design_kernel.builder.manifest import manifest
from frc_design_kernel.cli import main
from frc_design_kernel.measure import mass, records
from frc_design_kernel.status import status

from .helpers import load_data

BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
ASSUMED = lambda value, low, high: {"value": value, "assumed": [low, high]}
MEASURED = lambda value: {"value": value, "measured": "shop scale"}
TURN_UP = [{"kind": "rotation", "originMm": [0, 50, 110], "axis": [0, -1, 0], "travelDeg": 90}]

# base: plate 1.0 kg assumed [0.9, 1.2], post 0.5 kg plain, a cover with no weight, and 0.8 kg of wiring assumed
#       [0.5, 1.0] with no solid. base = 2.3 kg, [1.9, 2.7].
# arm:  a bar of 80,000 mm3 at 2700 kg/m3 assumed [2600, 2800] (0.216 kg, [0.208, 0.224]), a tip of 0.05 kg plain and
#       0.1 kg of bolts plain with no solid. arm = 0.366 kg, [0.358, 0.374].
# pod:  one lump of 2.0 kg, measured, over two solids that carry no mass of their own. pod = 2.0 kg, [2.0, 2.0].
# The robot: 4.666 kg, [4.258, 5.074]. A stand is a fixture and weighs nothing in the robot.
RANGED = {
    "schema": "frc-design-kernel/design@1", "name": "Ranged", "units": {"length": "mm", "mass": "kg"},
    "groups": {"base": {"role": "structure"}, "arm": {"role": "mechanism", "carriedBy": "base"},
               "pod": {"role": "mechanism", "carriedBy": "base", "massKg": MEASURED(2.0)}},
    "solids": [
        {"name": "plate", "group": "base", "massKg": ASSUMED(1.0, 0.9, 1.2), "shape": BOX([0, 0, 0], [100, 100, 10])},
        {"name": "post", "group": "base", "massKg": 0.5, "shape": BOX([40, 40, 10], [60, 60, 110])},
        {"name": "cover", "group": "base", "shape": BOX([0, 0, 10], [10, 100, 30])},
        {"name": "arm bar", "group": "arm", "densityKgM3": ASSUMED(2700, 2600, 2800), "shape": BOX([0, 40, 100], [200, 60, 120])},
        {"name": "arm tip", "group": "arm", "massKg": 0.05, "shape": BOX([200, 40, 100], [220, 60, 140])},
        {"name": "pod a", "group": "pod", "shape": BOX([-100, 0, 0], [-80, 20, 20])},
        {"name": "pod b", "group": "pod", "shape": BOX([-100, 80, 0], [-80, 100, 20])},
    ],
    "fixtures": [{"name": "stand", "shape": BOX([300, 0, 0], [320, 20, 50])}],
    "extraMass": [
        {"name": "wiring", "group": "base", "massKg": ASSUMED(0.8, 0.5, 1.0), "note": "Loom, connectors and ties."},
        {"name": "bolts", "group": "arm", "massKg": 0.1},
    ],
    "poses": {"stowed": {}, "up": {"arm": TURN_UP}},
}


def design(change=None):
    data = copy.deepcopy(RANGED)
    if change:
        change(data)
    return data


def built(change=None):
    return kernel.build(load_data(design(change)))


def near(test, got, want, places=9):
    test.assertEqual(len(got), len(want))
    for a, b in zip(got, want):
        test.assertAlmostEqual(a, b, places=places)


class Ranges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = built()
        cls.rolled = mass.roll_up(cls.assembly)
        cls.manifest = manifest(cls.assembly)

    def test_the_range_is_the_sum_of_the_low_ends_and_of_the_high_ends(self):
        """Catches a range that ignores an assumed mass, a ranged density or a ranged extra mass, or a nominal total that moved."""
        for found in (self.rolled, self.manifest["mass"]):
            self.assertAlmostEqual(found["totalKg"], 4.666, places=9)
            near(self, found["rangeKg"], [4.258, 5.074])

    def test_each_group_reports_its_own_mass_and_range(self):
        """Catches a group's extra mass, density range or lump range lost from the per-group figures."""
        for groups in (self.rolled["groups"], self.manifest["mass"]["groups"]):
            for name, nominal, low, high in (("base", 2.3, 1.9, 2.7), ("arm", 0.366, 0.358, 0.374), ("pod", 2.0, 2.0, 2.0)):
                self.assertAlmostEqual(groups[name]["massKg"], nominal, places=9, msg=name)
                near(self, groups[name]["rangeKg"], [low, high])
            self.assertNotIn("fixtures", groups)
        self.assertEqual(self.rolled["groups"]["base"]["extra"], ["wiring"])
        self.assertEqual(self.manifest["mass"]["groups"]["arm"]["extra"], ["bolts"])

    def test_a_plain_number_counts_at_both_ends(self):
        """Catches a plain-number mass left out of one end of the range, or widened as though it were assumed."""
        def plain(d):
            for solid in d["solids"]:
                if isinstance(solid.get("massKg"), dict):
                    solid["massKg"] = solid["massKg"]["value"]
            d["solids"][3]["densityKgM3"] = 2700
            d["groups"]["pod"]["massKg"] = 2.0
            d["extraMass"][0]["massKg"] = 0.8
        found = manifest(built(plain))["mass"]
        near(self, found["rangeKg"], [4.666, 4.666])
        self.assertAlmostEqual(found["totalKg"], 4.666, places=9)

    def test_control_widening_one_plain_mass_widens_the_range_by_exactly_that(self):
        """Control: shows the post's plain 0.5 kg really is in both ends, by widening it alone to [0.4, 0.7]."""
        found = manifest(built(lambda d: d["solids"][1].update(massKg=ASSUMED(0.5, 0.4, 0.7))))["mass"]
        near(self, found["rangeKg"], [4.258 - 0.1, 5.074 + 0.2])

    def test_a_solid_row_states_its_range(self):
        """Catches a solid's range lost from the manifest, so a reader cannot see which solids widen the total."""
        rows = {row["name"]: row for row in self.manifest["solids"]}
        near(self, rows["plate"]["massRangeKg"], [0.9, 1.2])
        near(self, rows["post"]["massRangeKg"], [0.5, 0.5])
        near(self, rows["arm bar"]["massRangeKg"], [0.208, 0.224])
        self.assertAlmostEqual(rows["arm bar"]["massKg"], 0.216, places=9)
        self.assertEqual((rows["cover"]["massKg"], rows["cover"]["massRangeKg"]), (None, None))


class Unweighed(unittest.TestCase):
    def test_a_robot_solid_with_no_weight_is_listed(self):
        """Catches an unweighed robot solid going unreported, or a lump group's solids or a fixture listed as unweighed."""
        assembly = built()
        self.assertEqual(mass.roll_up(assembly)["unweighed"], ["cover"])
        self.assertEqual(manifest(assembly)["mass"]["unweighed"], ["cover"])

    def test_control_weighing_the_solid_empties_the_list(self):
        """Control: shows the list can be empty, so a listed solid is listed for its missing weight and nothing else."""
        assembly = built(lambda d: d["solids"][2].update(massKg=ASSUMED(0.1, 0.05, 0.2)))
        self.assertEqual(mass.roll_up(assembly)["unweighed"], [])
        self.assertEqual(manifest(assembly)["mass"]["unweighed"], [])

    def test_extra_mass_on_a_group_does_not_weigh_its_solids(self):
        """Catches weight with no solid being taken as the weight of a group's unweighed solids."""
        assembly = built(lambda d: d.update(extraMass=[{"name": "wiring", "group": "base", "massKg": 5.0}]))
        self.assertEqual(manifest(assembly)["mass"]["unweighed"], ["cover"])


class Centre(unittest.TestCase):
    def test_extra_mass_sits_at_its_groups_volume_weighted_centre(self):
        """Catches extra mass put at the origin, at one solid, or at the mass-weighted centre instead of the volume centre."""
        found = mass.roll_up(built())["groups"]["arm"]
        bar, tip = (80000, [100, 50, 110]), (16000, [210, 50, 120])
        volume_centre = [(bar[0] * bar[1][i] + tip[0] * tip[1][i]) / (bar[0] + tip[0]) for i in range(3)]
        want = [(0.216 * bar[1][i] + 0.05 * tip[1][i] + 0.1 * volume_centre[i]) / 0.366 for i in range(3)]
        near(self, found["centreMm"], want, places=6)

    def test_extra_mass_moves_with_its_group(self):
        """Catches extra mass left where the group was drawn when a pose turns the group."""
        assembly = built()
        drawn, up = mass.roll_up(assembly)["groups"]["arm"]["centreMm"], mass.roll_up(assembly, "up")["groups"]["arm"]["centreMm"]
        turn = placement.at_pose(assembly.data, "up")["arm"]
        from frc_design_kernel.motion import matrix as mx
        near(self, up, list(mx.apply(turn, drawn)), places=6)


class Checks(unittest.TestCase):
    def expect(self, change, message):
        with self.assertRaisesRegex(DesignError, message):
            load_data(design(change))

    def test_the_sourced_form_is_accepted_on_solids_densities_and_lumps(self):
        """Catches the schema refusing {value, measured} or {value, assumed} on a solid mass, a density or a group lump."""
        loaded = load_data(design())
        self.assertIn("bolts", [entry["name"] for entry in loaded.data["extraMass"]])
        self.assertEqual(load_data(design(lambda d: d.pop("extraMass"))).data["extraMass"], [])

    def test_extra_mass_must_name_a_robot_group(self):
        """Catches weight placed in a group that does not exist, or in a group that holds only fixtures."""
        self.expect(lambda d: d["extraMass"][0].update(group="bse"), 'names the group "bse", which does not exist')
        self.expect(lambda d: d["extraMass"][0].update(group="fixtures"), 'the group "fixtures" holds no robot solid')

    def test_extra_mass_entries_are_whole_and_named_once(self):
        """Catches an extra mass with no weight, an unknown field, or two entries under one name."""
        self.expect(lambda d: d["extraMass"][0].pop("massKg"), "massKg")
        self.expect(lambda d: d["extraMass"][0].update(weight=1), "weight")
        self.expect(lambda d: d["extraMass"][1].update(name="wiring"), 'has the same name as extraMass\\[0\\]')

    def test_a_negative_or_badly_sourced_mass_is_refused(self):
        """Catches a mass whose low end is below zero, or a sourced mass that states no source, two, or a value outside its range."""
        self.expect(lambda d: d["solids"][0].update(massKg=ASSUMED(0.1, -0.1, 0.2)), "negative")
        self.expect(lambda d: d["groups"]["pod"].update(massKg=ASSUMED(1.0, -1.0, 2.0)), "negative")
        self.expect(lambda d: d["extraMass"][0].update(massKg=-0.2), "negative")
        self.expect(lambda d: d["solids"][3].update(densityKgM3=ASSUMED(-5, -10, 10)), "negative")
        self.expect(lambda d: d["solids"][0].update(massKg={"value": 1.0, "assumed": [0.9, 1.1], "measured": "scale"}), 'exactly one of "measured" or "assumed"')
        self.expect(lambda d: d["extraMass"][0].update(massKg=ASSUMED(2.0, 0.5, 1.0)), "outside its assumed range")

    def test_a_lump_still_excludes_solid_masses(self):
        """Catches a solid's sourced mass counted on top of its group's sourced lump."""
        self.expect(lambda d: d["solids"][5].update(massKg=MEASURED(0.3)), 'its group "pod" already has one lump massKg')
        self.expect(lambda d: d["solids"][6].update(densityKgM3=ASSUMED(1000, 900, 1100)), 'its group "pod" already has one lump massKg')


# A bar 100 x 40 x 20 mm of 2 kg, centred on the origin. About the z axis through its centre: m(a^2 + b^2) / 12.
BAR = {
    "schema": "frc-design-kernel/design@1", "name": "Bar", "units": {"length": "mm", "mass": "kg"},
    "groups": {"bar": {"role": "mechanism"}, "other": {"role": "structure"}},
    "solids": [{"name": "bar", "group": "bar", "massKg": ASSUMED(2.0, 1.5, 3.0), "shape": BOX([-50, -20, -10], [50, 20, 10])},
               {"name": "block", "group": "other", "massKg": 1.0, "shape": BOX([200, -5, -5], [210, 5, 5])}],
    "poses": {"turned": {"bar": [{"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 0, 1], "travelDeg": 90}]}},
    "motions": {"turn": {"by": "hand", "from": "turned", "moves": {"bar": [{"kind": "rotation", "originMm": [0, 0, 0], "axis": [0, 0, 1], "travelDeg": -90}]}}},
}
KG_M2 = 1e-6    # kg mm^2 to kg m^2


def bar(change=None):
    data = copy.deepcopy(BAR)
    if change:
        change(data)
    return kernel.build(load_data(data))


class Inertia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = bar()

    def about(self, *args, **kwargs):
        return mass.inertia(self.assembly, *args, **kwargs)

    def test_a_box_about_its_own_axes(self):
        """Catches a wrong inertia for the plainest case: m(a^2 + b^2) / 12 about each axis through the centre, in kg m^2."""
        for axis, sides in (([0, 0, 1], (100, 40)), ([1, 0, 0], (40, 20)), ([0, 1, 0], (100, 20))):
            found = self.about(["bar"], axis, [0, 0, 0])
            self.assertAlmostEqual(found["kgM2"], 2.0 * (sides[0] ** 2 + sides[1] ** 2) / 12 * KG_M2, places=12, msg=axis)

    def test_the_range_follows_the_mass_range(self):
        """Catches an inertia range that does not scale with the low and high masses."""
        found = self.about(["bar"], [0, 0, 1], [0, 0, 0])
        unit = (100 ** 2 + 40 ** 2) / 12 * KG_M2
        near(self, found["rangeKgM2"], [1.5 * unit, 3.0 * unit], places=12)
        self.assertEqual(found["unweighed"], [])

    def test_an_axis_through_another_point_adds_m_d_squared(self):
        """Catches a missing parallel-axis term, or one taken along the axis instead of square to it."""
        own = 2.0 * (100 ** 2 + 40 ** 2) / 12
        self.assertAlmostEqual(self.about(["bar"], [0, 0, 1], [0, 100, 0])["kgM2"], (own + 2.0 * 100 ** 2) * KG_M2, places=12)
        self.assertAlmostEqual(self.about(["bar"], [0, 0, 7], [0, 0, 500])["kgM2"], own * KG_M2, places=12)    # along the axis: no change

    def test_an_axis_at_a_slant_uses_the_whole_tensor(self):
        """Catches products of inertia dropped or given the wrong sign, on a plate drawn turned 30 degrees about z."""
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        outline = [[x * c - y * s, x * s + y * c] for x, y in ((-50, -20), (50, -20), (50, 20), (-50, 20))]
        assembly = bar(lambda d: d["solids"][0].update(shape={"kind": "prism", "plane": "xy", "outlineMm": outline, "fromMm": -10, "toMm": 10}))
        long_axis, short_axis = 2.0 * (40 ** 2 + 20 ** 2) / 12, 2.0 * (100 ** 2 + 20 ** 2) / 12     # about the plate's own long and short sides
        found = mass.inertia(assembly, ["bar"], [1, 0, 0], [0, 0, 0])["kgM2"]
        self.assertAlmostEqual(found, (c * c * long_axis + s * s * short_axis) * KG_M2, places=12)

    def test_a_pose_turns_the_tensor_with_the_group(self):
        """Catches an inertia taken from the drawing when a pose has turned the group: turned 90 degrees, x and y swap."""
        turned = self.about(["bar"], [1, 0, 0], [0, 0, 0], pose="turned")["kgM2"]
        self.assertAlmostEqual(turned, 2.0 * (100 ** 2 + 20 ** 2) / 12 * KG_M2, places=12)

    def test_places_of_a_motion_point_can_be_given(self):
        """Catches inertia that can only be had at a named pose, which a motion's middle is not."""
        places = placement.at_motion(self.assembly.data, "turn", 1.0)
        self.assertAlmostEqual(self.about(["bar"], [1, 0, 0], [0, 0, 0], places=places)["kgM2"], 2.0 * (40 ** 2 + 20 ** 2) / 12 * KG_M2, places=12)

    def test_groups_add_and_others_are_left_out(self):
        """Catches the block of another group counted when it is not asked for, or dropped when it is."""
        alone = self.about(["bar"], [0, 0, 1], [0, 0, 0])["kgM2"]
        block = 1.0 * ((10 ** 2 + 10 ** 2) / 12 + 205 ** 2) * KG_M2
        self.assertAlmostEqual(self.about(["bar", "other"], [0, 0, 1], [0, 0, 0])["kgM2"], alone + block, places=12)

    def test_a_lump_spreads_by_volume_and_extra_mass_is_a_point(self):
        """Catches a lump put at one point, or extra mass given a size: a 3 kg lump over two equal blocks, 1 kg extra between them."""
        def lump(d):
            d["groups"]["other"]["massKg"] = 3.0
            d["solids"][1].pop("massKg")
            d["solids"].append({"name": "block 2", "group": "other", "shape": BOX([-210, -5, -5], [-200, 5, 5])})
            d["extraMass"] = [{"name": "ballast", "group": "other", "massKg": ASSUMED(1.0, 0.5, 1.5)}]
        assembly = bar(lump)
        found = mass.inertia(assembly, ["other"], [0, 0, 1], [0, 0, 0])
        blocks = 3.0 * ((10 ** 2 + 10 ** 2) / 12 + 205 ** 2) * KG_M2     # each block's 1.5 kg at 205 mm, and its own spin
        self.assertAlmostEqual(found["kgM2"], blocks, places=12)        # the extra mass sits on the axis: it adds nothing
        shifted = mass.inertia(assembly, ["other"], [0, 0, 1], [0, 30, 0])
        self.assertAlmostEqual(shifted["kgM2"], blocks + (3.0 + 1.0) * 30 ** 2 * KG_M2, places=12)
        near(self, shifted["rangeKgM2"], [blocks + 3.5 * 900 * KG_M2, blocks + 4.5 * 900 * KG_M2], places=12)

    def test_an_unweighed_solid_is_named(self):
        """Catches inertia that quietly leaves out a solid with no weight."""
        found = mass.inertia(bar(lambda d: d["solids"][1].pop("massKg")), ["other"], [0, 0, 1], [0, 0, 0])
        self.assertEqual((found["kgM2"], found["unweighed"]), (0.0, ["block"]))


class Records(unittest.TestCase):
    """The mass job record carries mass, so an edit to any weight must show in status and be measured again on a carry."""

    JOB = [{"kind": "mass", "pose": "stowed"}]

    @classmethod
    def setUpClass(cls):
        cls.data = design()
        cls.path = load_data(cls.data).path
        cls.folder = tempfile.TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["measure", str(cls.path), "--out", cls.folder.name, "--workers", "1", "--pose", "stowed"]) == 0
        cls.record = json.loads((Path(cls.folder.name) / records.FOLDER / "mass.pose.stowed.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def after(self, change):
        self.path.write_text(json.dumps(design(change)), encoding="utf-8")
        try:
            return {row["record"]: row for row in status(self.path, self.folder.name)["records"]}
        finally:
            self.path.write_text(json.dumps(self.data), encoding="utf-8")

    def carried(self, change=None):
        """The mass job recorded again, carrying from a copy of the class's records, for the design after change."""
        with tempfile.TemporaryDirectory() as out:
            shutil.copytree(Path(self.folder.name) / records.FOLDER, Path(out) / records.FOLDER)
            entry, = records.record(load_data(design(change)).path, self.JOB, out, workers=1)
        return entry

    def test_the_pose_record_holds_the_ranged_roll_up(self):
        """Catches a measured roll-up that drops the range or the extra mass."""
        near(self, self.record["result"]["rangeKg"], [4.258, 5.074])

    def test_control_an_untouched_source_is_current(self):
        """Control: shows the mass record is current before any weight is edited, and an edited note changes nothing."""
        rows = self.after(lambda d: d["extraMass"][0].update(note="Reworded."))
        self.assertEqual(rows["mass.pose.stowed"]["state"], "current")

    def test_an_extra_mass_edit_makes_the_mass_record_stale(self):
        """Catches weight with no solid changing without status seeing it."""
        rows = self.after(lambda d: d["extraMass"][0].update(massKg=ASSUMED(0.8, 0.6, 1.0)))
        self.assertEqual(rows["mass.pose.stowed"]["state"], "stale")
        self.assertIn("extraMass changed", rows["mass.pose.stowed"]["changes"])

    def test_a_range_edit_alone_makes_the_mass_record_stale(self):
        """Catches a solid whose range changed but whose nominal mass did not being called current."""
        rows = self.after(lambda d: d["solids"][0].update(massKg=ASSUMED(1.0, 0.8, 1.2)))
        self.assertEqual(rows["mass.pose.stowed"]["changes"], ['massRanges "plate" changed: [0.9, 1.2] to [0.8, 1.2]'])

    def test_a_carry_weighs_again_after_an_extra_mass_edit(self):
        """Catches a carried roll-up that keeps the old weight after an extra mass changed; control: no edit carries it."""
        self.assertEqual(self.carried()["action"], "carried")
        heavier = self.carried(lambda d: d["extraMass"][0].update(massKg=1.0))
        self.assertEqual(heavier["action"], "measured")
        self.assertAlmostEqual(heavier["record"]["result"]["totalKg"], 4.866, places=9)

    def test_a_carry_weighs_again_after_a_range_edit(self):
        """Catches a carried roll-up that keeps the old range after only a solid's range changed."""
        wider = self.carried(lambda d: d["solids"][0].update(massKg=ASSUMED(1.0, 0.8, 1.2)))
        self.assertEqual(wider["action"], "measured")
        near(self, wider["record"]["result"]["rangeKg"], [4.158, 5.074])

    def test_extra_mass_sits_at_its_group_volume_so_any_member_shape_is_used(self):
        """Catches a mass record carried after an unweighed member of a group with extra mass changed shape, which moves the centre."""
        grown = self.carried(lambda d: next(s for s in d["solids"] if s["group"] == "base" and "massKg" not in s)["shape"]["toMm"].__setitem__(2, 80))
        self.assertEqual(grown["action"], "measured")
        self.assertNotEqual(grown["record"]["result"]["groups"]["base"]["centreMm"], self.record["result"]["groups"]["base"]["centreMm"])


if __name__ == "__main__":
    unittest.main()
