"""Attachment, mass, compression, approach, worker sharing and the measure command, on a small stack with known numbers."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import frc_design_kernel as kernel
from frc_design_kernel import DesignError
from frc_design_kernel.cli import main
from frc_design_kernel.measure import approach, attachment, clearance, compression, mass, run, summary

from .helpers import load_data

BOX = lambda low, high: {"kind": "box", "fromMm": low, "toMm": high}
UP = lambda mm: [{"kind": "translation", "travelMm": [0, 0, mm]}]

# A plate on the floor, a post standing on it, a bracket drawn 2 mm above the post (held by a mount), a loose block
# far away, and a ball 20 mm above the bracket. Fixtures: a stand on the floor, a shelf on the stand, a lamp in mid-air.
STACK = {
    "schema": "frc-design-kernel/design@1", "name": "Stack", "units": {"length": "mm", "mass": "kg"},
    "groups": {"base": {"role": "structure"}, "bracket": {"role": "mechanism", "carriedBy": "base"}, "loose": {"role": "other"},
               "piece": {"role": "payload"}},
    "solids": [
        {"name": "plate", "group": "base", "massKg": 1.0, "shape": BOX([0, 0, 0], [100, 100, 10])},
        {"name": "post", "group": "base", "massKg": 1.0, "shape": BOX([40, 40, 10], [60, 60, 110])},
        {"name": "bracket", "group": "bracket", "massKg": 2.0, "shape": BOX([40, 40, 112], [60, 60, 120])},
        {"name": "loose", "group": "loose", "shape": BOX([300, 0, 50], [310, 10, 60])},
        {"name": "ball", "group": "piece", "shape": {"kind": "sphere", "centerMm": [50, 50, 150], "radiusMm": 10}},
    ],
    "fixtures": [
        {"name": "stand", "shape": BOX([200, 0, 0], [220, 20, 50])},
        {"name": "shelf", "shape": BOX([200, 0, 50], [220, 20, 60])},
        {"name": "lamp", "shape": BOX([400, 0, 30], [410, 10, 40])},
    ],
    "mounts": [{"group": "bracket", "on": "post", "atMm": [50, 50, 111], "note": "Two screws, not drawn."}],
    "contacts": [{"pair": ["ball", "bracket"], "during": ["press"], "note": "The ball is squeezed onto the bracket."}],
    "poses": {"home": {}, "lifted": {"bracket": UP(100)}},
    "motions": {"press": {"from": "home", "moves": {"piece": UP(-23)}}, "lift off": {"from": "home", "to": "lifted", "moves": {"bracket": UP(100)}}},
}


def built(change=None):
    data = copy.deepcopy(STACK)
    if change:
        change(data)
    return kernel.build(load_data(data))


class Attachment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = built()

    def test_touching_mounts_and_loose_solids(self):
        """Catches a floating solid going unreported, or a mount hiding the gap it bridges."""
        found = attachment.at_pose(self.assembly, "home", gap=0.0, ignore=["ball"])
        self.assertEqual([row["pair"] for row in found["touching"]], [["plate", "post"]])
        self.assertEqual(found["connectedSets"], [["bracket", "plate", "post"], ["loose"]])
        self.assertEqual(found["heldByMountOnly"], ["bracket"])
        self.assertEqual([(r["solid"], r["nearest"]) for r in found["notConnectedToBase"]], [("loose", "plate")])
        self.assertAlmostEqual(found["notConnectedToBase"][0]["gapMm"], (200 ** 2 + 40 ** 2) ** 0.5, places=6)
        mount, = found["mounts"]
        self.assertEqual((mount["member"], mount["on"]), ("bracket", "post"))
        self.assertAlmostEqual(mount["gapMm"], 2.0, places=6)
        self.assertAlmostEqual(mount["pointToMemberMm"], 1.0, places=6)
        self.assertAlmostEqual(mount["pointToOnMm"], 1.0, places=6)

    def test_the_touch_gap_is_the_callers_number(self):
        """Catches a built-in idea of "close enough": at 3 mm the bracket touches the post without its mount."""
        found = attachment.at_pose(self.assembly, "home", gap=3.0, ignore=["ball", "loose"])
        self.assertEqual((found["heldByMountOnly"], found["notConnectedToBase"], found["robotSolids"]), ([], [], 3))
        self.assertEqual(found["ignored"], ["ball", "loose"])

    def test_a_mount_is_measured_at_the_pose_asked(self):
        """Catches mounts read from the drawing only: lifted 100 mm, the bracket is 102 mm from its mount's post."""
        mount, = attachment.at_pose(self.assembly, "lifted", ignore=["ball"])["mounts"]
        self.assertAlmostEqual(mount["gapMm"], 102.0, places=6)

    def test_fixtures_off_the_floor(self):
        """Catches a floating fixture going unreported, or one resting on another being called floating."""
        found = attachment.at_pose(self.assembly, "home")
        self.assertEqual(found["fixturesOffFloor"], [{"fixture": "lamp", "lowestAboveFloorMm": 30.0}])
        raised = attachment.at_pose(self.assembly, "home", floor_z=-5.0)["fixturesOffFloor"]
        self.assertEqual([row["fixture"] for row in raised], ["lamp", "shelf", "stand"])

    def test_a_named_base_and_declared_contacts(self):
        """Catches the base being guessed when the caller names it, or a declared contact not joining its pair."""
        found = attachment.at_pose(self.assembly, "home", base="loose", ignore=["ball"])
        self.assertEqual([r["solid"] for r in found["notConnectedToBase"]], ["bracket", "plate", "post"])
        joined = attachment.at_pose(self.assembly, "home", contacts=[["ball", "bracket"]])
        self.assertEqual(joined["connectedSets"][0], ["ball", "bracket", "plate", "post"])
        with self.assertRaisesRegex(DesignError, 'the base solid "lamp" is not among the solids measured'):
            attachment.at_pose(self.assembly, "home", base="lamp")


class Mass(unittest.TestCase):
    def test_centre_of_mass_follows_the_pose(self):
        """Catches a centre of mass taken from the drawing when a group has moved, or weighted by the wrong thing."""
        home = mass.roll_up(built(), "home")
        self.assertAlmostEqual(home["totalKg"], 4.0)
        for got, want in zip(home["centreMm"], [50, 50, (5 + 60 + 2 * 116) / 4]):
            self.assertAlmostEqual(got, want, places=6)
        lifted = mass.roll_up(built(), "lifted")
        self.assertAlmostEqual(lifted["centreMm"][2], (5 + 60 + 2 * 216) / 4, places=6)
        self.assertEqual(home["unweighed"], ["ball", "loose"])
        self.assertEqual(home["groups"]["base"]["massKg"], 2.0)

    def test_a_lump_group_mass_sits_at_the_centre_of_its_volume(self):
        """Catches a lump mass being dropped from the roll-up, or placed at one solid's centre."""
        def lump(d):
            d["groups"]["base"]["massKg"] = 6.0
            for solid in d["solids"][:2]:
                solid.pop("massKg")
        found = mass.roll_up(built(lump))
        volumes = (100 * 100 * 10, 20 * 20 * 100)
        self.assertAlmostEqual(found["groups"]["base"]["centreMm"][2], (volumes[0] * 5 + volumes[1] * 60) / sum(volumes), places=6)
        self.assertAlmostEqual(found["totalKg"], 8.0)


class Pressing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembly = built()

    def test_the_deepest_press_is_known(self):
        """Catches a wrong depth: the ball starts 20 mm above the bracket and moves down 23, so it ends 3 mm in."""
        found = compression.indentation(self.assembly, "press", "ball", "bracket", limit=4.0)
        self.assertAlmostEqual(found["deepestMm"], 3.0, places=6)
        self.assertEqual((found["t"], found["proven"], found["deeperThanLimit"]), (1.0, True, False))
        self.assertTrue(3.0 - 1e-6 <= found["upperBoundMm"] <= 4.0)

    def test_pressing_past_the_limit_is_reported(self):
        """Control: catches a compression measure that cannot report too deep a press."""
        found = compression.indentation(self.assembly, "press", "ball", "bracket", limit=2.0)
        self.assertEqual((found["deeperThanLimit"], found["upperBoundMm"]), (True, None))
        self.assertGreater(found["deepestMm"], 2.0)

    def test_only_a_whole_ball_or_ring_can_be_pressed(self):
        """Catches the depth formula being applied to a shape it is not true for."""
        with self.assertRaisesRegex(DesignError, 'solid "bracket": is not a whole ball or a whole round-section ring'):
            compression.indentation(self.assembly, "press", "bracket", "ball", limit=1.0)

    def test_does_a_pair_come_together(self):
        """Catches a missed meeting, or a meeting claimed outside the window asked about."""
        late = approach.reach(self.assembly, "press", ["ball", "bracket"], within=1.0, window=(0.5, 1.0))
        self.assertTrue(late["reached"] and late["gapMm"] <= 1.0)
        early = approach.reach(self.assembly, "press", ["ball", "bracket"], within=1.0, window=(0.0, 0.5))
        self.assertEqual((early["reached"], early["proven"]), (False, True))
        self.assertAlmostEqual(early["gapMm"], 8.5, places=6)
        self.assertTrue(1.0 < early["lowerBoundMm"] <= 8.5)

    def test_a_seat_and_a_withdrawal(self):
        """Catches a wrong bearing area, or a lifted part reported clear of the rest by the wrong distance."""
        seat = approach.seat(self.assembly, "lift off", ["post", "plate"], t=1.0)
        self.assertAlmostEqual(seat["bearingAreaMm2"], 400.0, places=6)
        self.assertEqual(seat["overlapMm3"], 0.0)
        out = approach.withdrawn(self.assembly, "lift off")
        self.assertEqual(out["moving"], ["bracket"])
        self.assertAlmostEqual(out["smallestBoxGapMm"], 212 - 160, places=6)


class Sharing(unittest.TestCase):
    def test_any_worker_count_gives_the_same_result(self):
        """Catches results that change with the number of workers, or rows lost between processes."""
        assembly = built()
        source = assembly.design.path
        jobs = [{"motion": "press", "minGapMm": 1.0}, {"motion": "lift off", "minGapMm": 1.0, "absent": ["loose"]},
                {"motion": "press", "minGapMm": 1.0, "contacts": summary.contacts_for(assembly.data, "press")}]
        alone = run.clearances(source, jobs, workers=1)
        self.assertEqual(alone[0], clearance.along(assembly, "press", 1.0))
        self.assertEqual(alone[0]["closer"], [["ball", "bracket"]])
        self.assertEqual((alone[2]["closer"], alone[2]["counts"]["declaredContacts"]), ([], 1))
        old = run.PAIRS_PER_SHARE
        try:
            run.PAIRS_PER_SHARE = 1     # cut even this small design into one share per worker
            self.assertEqual(run.clearances(source, jobs, workers=2), alone)
        finally:
            run.PAIRS_PER_SHARE = old
        self.assertGreaterEqual(run.default_workers(), 1)


class Quicker(unittest.TestCase):
    def test_sets_without_the_pair_list_are_the_same_sets(self):
        """Catches the quick attachment mode disagreeing with the full one about what hangs together or floats."""
        assembly = built()
        full = attachment.at_pose(assembly, "home", gap=3.0, ignore=["ball"])
        quick = attachment.at_pose(assembly, "home", gap=3.0, ignore=["ball"], pairs=False)
        for key in ("connectedSets", "notConnectedToBase", "fixturesOffFloor", "baseSolids", "robotSolids"):
            self.assertEqual(quick[key], full[key], key)
        self.assertEqual((quick["touching"], quick["heldByMountOnly"]), (None, None))
        self.assertEqual([(m["member"], m["on"]) for m in quick["mounts"]], [("bracket", "post")])

    def test_a_fixed_pair_is_measured_once_across_motions_and_gives_the_same_rows(self):
        """Catches the memory of fixed pairs changing a result, or not being used at all."""
        assembly = built()
        source = assembly.design.path
        jobs = [{"motion": "press", "minGapMm": 1.0, "includeStill": True}, {"motion": "lift off", "minGapMm": 1.0, "includeStill": True}]
        run._built.clear()
        run._fixed.clear()
        found = run.clearances(source, jobs, workers=1)
        self.assertEqual(found[0], clearance.along(assembly, "press", 1.0, include_still=True))
        self.assertEqual(found[1], clearance.along(assembly, "lift off", 1.0, include_still=True))
        remembered = len(run._fixed)
        self.assertGreater(remembered, 0)
        run.clearances(source, jobs, workers=1)
        self.assertEqual(len(run._fixed), remembered)       # the second time nothing new had to be measured


class Command(unittest.TestCase):
    def test_measure_writes_one_stamped_record(self):
        """Catches the command writing nothing, losing the version stamp, or changing between two runs."""
        source = str(built().design.path)
        records = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as out:
                text = io.StringIO()
                with contextlib.redirect_stdout(text):
                    code = main(["measure", source, "--out", out, "--min-gap", "1", "--touch-gap", "3", "--ignore", "ball", "--workers", "1"])
                records.append(json.loads((Path(out) / "measurements.json").read_text(encoding="utf-8")))
        record = records[0]
        self.assertEqual((code, records[1]), (0, record))
        self.assertEqual((record["schema"], record["generator"]["library"]), ("frc-design-kernel/measurements@2", "frc-design-kernel"))
        self.assertEqual(record["settings"], {"minGapMm": 1.0, "touchGapMm": 3.0, "floorZMm": 0.0, "ignored": ["ball"], "depthLimit": 9})
        self.assertEqual(record["motions"]["press"]["declaredContacts"], [["ball", "bracket"]])
        self.assertEqual([row["pose"] for row in record["poses"]], [None, "home", "lifted"])
        lines = text.getvalue().splitlines()
        self.assertEqual(lines[0], 'Measured "Stack" against a gap of 1 mm, touching within 3 mm.')
        self.assertEqual(lines[1], 'Motion "press": no pair near enough to measure; 0 pairs closer than the gap; 0 pairs not settled.')
        self.assertEqual(lines[4], 'Pose "home": 2 pairs closer than the gap; 1 solid not connected to the base; 1 fixture off the floor; mass 4.000 kg.')

    def test_contacts_in_the_source_are_checked(self):
        """Catches a declared contact that names a solid or motion that does not exist."""
        with self.assertRaisesRegex(DesignError, r'contacts\[0\]: names the solid "bal"'):
            built(lambda d: d["contacts"][0].update(pair=["bal", "bracket"]))
        with self.assertRaisesRegex(DesignError, r'contacts\[0\] during: names the motion "pres"'):
            built(lambda d: d["contacts"][0].update(during=["pres"]))


if __name__ == "__main__":
    unittest.main()
