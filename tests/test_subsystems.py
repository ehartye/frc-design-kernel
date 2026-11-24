"""Subsystem files: one top file plus one file per subsystem, merged on load into the same design.

The example is split into three subsystem files by group. Every test compares the split design with the example
as one file, or refuses a split that defines a name twice, so a merge that loses, doubles or reorders what is
measured shows up as a difference.
"""
import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from frc_design_kernel.builder.assembly import build
from frc_design_kernel.cli import main
from frc_design_kernel.errors import DesignError
from frc_design_kernel.measure import carry, summary
from frc_design_kernel.source import schema
from frc_design_kernel.source.load import load
from frc_design_kernel.status import status

from .helpers import EXAMPLE
from .test_source import keywords_in

WHOLE = ("schema", "name", "units", "frame", "parameters", "custom", "fixtures", "pieces", "materials", "motors", "trials")
PLAN = {"base": "subsystems/base.json", "fixtures": "subsystems/base.json", "drive": "subsystems/drive.json",
        "carriage": "subsystems/carriage.json", "load": "subsystems/carriage.json"}
LAST = "subsystems/carriage.json"       # poses, motions, adjustments and interactions live with the carriage
_FOLDERS = []


def example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def group_of(data, solid):
    every = {entry["name"].split(" {")[0]: entry.get("group", "fixtures") for entry in data["solids"] + data["fixtures"]}
    return every[solid.split(" {")[0]]


def split(data):
    """The example as a top file and three subsystem files, each holding its own groups' entries."""
    top = {key: copy.deepcopy(data[key]) for key in WHOLE if key in data}
    files = {name: {"schema": "frc-design-kernel/subsystem@1"} for name in dict.fromkeys(PLAN.values())}
    top["subsystems"] = [{"file": name} for name in files]

    def put(file, section, entry, key=None):
        holder = files[file].setdefault(section, {} if key is not None else [])
        if key is None:
            holder.append(copy.deepcopy(entry))
        else:
            holder[key] = copy.deepcopy(entry)
    for name, group in data["groups"].items():
        put(PLAN[name], "groups", group, name)
    for solid in data["solids"]:
        put(PLAN[solid["group"]], "solids", solid)
    for mount in data["mounts"]:
        put(PLAN[mount["group"]], "mounts", mount)
    for contact in data["contacts"]:
        put(PLAN[group_of(data, contact["pair"][0])], "contacts", contact)
    for section in ("poses", "motions", "adjustments", "interactions", "drives"):
        for name, entry in data.get(section, {}).items():
            put(LAST, section, entry, name)
    return top, files


def written(top, files):
    """The example's folder (parts and custom code) with the given top file and subsystem files; returns the top path."""
    keep = tempfile.TemporaryDirectory()
    _FOLDERS.append(keep)
    folder = Path(keep.name) / "lifter"
    shutil.copytree(EXAMPLE.parent, folder)
    (folder / "design.json").write_text(json.dumps(top, indent=1), encoding="utf-8")
    for name, body in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(json.dumps(body, indent=1), encoding="utf-8")
    return folder / "design.json"


def split_example(change=None):
    top, files = split(example())
    if change:
        change(top, files)
    return written(top, files)


def solid_entry(files, file, name):
    return next(entry for entry in files[file]["solids"] if entry["name"] == name)


def identities(assembly):
    """Every job identity the library keys its records to: clearance along each motion and at each pose, attachment and mass."""
    data = assembly.data
    found = {f"along {name}": carry.along(assembly, name) for name in data["motions"]}
    for pose in [None, *data["poses"]]:
        solids = carry.at_pose(assembly, pose)
        found[f"at {pose}"] = solids
        found[f"pose inputs {pose}"] = carry.pose_inputs(assembly, solids, summary.contacts_for(data), 1.0, 0.0, ())
        found[f"used at {pose}"] = summary.used_by_pose(assembly, pose)
    found.update({f"used along {name}": summary.used_by_motion(assembly, name) for name in data["motions"]})
    return found


class Merge(unittest.TestCase):
    def test_split_example_gives_the_same_identities(self):
        """Catches a merge that changes what is measured: every job identity of the split example equals the one-file example's."""
        whole, parts = build(load(EXAMPLE)), build(load(split_example()))
        self.assertEqual(sorted(parts.solids), sorted(whole.solids))
        self.assertEqual(identities(parts), identities(whole))

    def test_identities_can_differ(self):
        """Control: the comparison sees a solid that moved in a subsystem file."""
        def shift(top, files):
            solid_entry(files, LAST, "carriage plate")["shape"]["fromMm"][0] = "=post_x + 25"
        self.assertNotEqual(identities(build(load(split_example(shift)))), identities(build(load(EXAMPLE))))

    def test_parameters_and_each_rows_come_from_the_top_file(self):
        """Catches a subsystem file worked out without the top file's parameters, or a changed parameter not reaching it."""
        design = load(split_example(), parameters={"post_y": 100})
        post = next(s for s in design.data["solids"] if s["name"] == "post right")
        self.assertEqual(post["shape"]["fromMm"], [-120, -100, 8])

    def test_raw_holds_every_file(self):
        """Catches a design whose raw source misses the subsystem files, so a record could not say which parameters a table used."""
        design = load(split_example())
        self.assertIn("lift", design.raw["motions"])
        self.assertEqual(len(design.raw["solids"]), len(example()["solids"]))
        self.assertEqual([path.name for path in design.files], ["design.json", "base.json", "drive.json", "carriage.json"])

    def test_source_hash_covers_every_file(self):
        """Catches a source hash that stays the same when a subsystem file changes."""
        before = load(split_example()).sha256
        after = load(split_example(lambda top, files: files[LAST]["groups"]["carriage"].update(note="Changed."))).sha256
        self.assertNotEqual(before, after)
        self.assertEqual(len(before), 64)


class Refusals(unittest.TestCase):
    def expect(self, change, pattern):
        with self.assertRaisesRegex(DesignError, pattern):
            load(split_example(change))

    def test_a_name_defined_in_two_files_names_both(self):
        """Catches a name defined twice being merged silently, or refused without saying where."""
        both = r"subsystems/base\.json and subsystems/carriage\.json"
        self.expect(lambda top, files: files["subsystems/base.json"]["solids"].append(copy.deepcopy(solid_entry(files, LAST, "carriage plate"))),
                    r'solids "carriage plate": is defined in two files, ' + both)
        self.expect(lambda top, files: files["subsystems/base.json"]["groups"].update(load={"role": "payload"}),
                    r'groups "load": is defined in two files, ' + both)
        self.expect(lambda top, files: files["subsystems/base.json"].update(motions={"lift": {"from": "lowered", "moves": {}}}),
                    r'motions "lift": is defined in two files, ' + both)

    def test_a_name_made_by_each_rows_in_two_files_names_both(self):
        """Catches a clash that only appears once "each" rows are written out."""
        def clash(top, files):
            files["subsystems/drive.json"]["solids"].append(
                {"name": "sleeve {side}", "group": "drive", "each": [{"side": "left"}], "shape": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [1, 1, 1]}})
        self.expect(clash, r'solids "sleeve left": is defined in two files, subsystems/drive\.json and subsystems/carriage\.json')

    def test_a_solid_named_like_a_fixture_names_both_files(self):
        """Catches a subsystem solid that takes the name of a fixture in the top file."""
        def clash(top, files):
            files["subsystems/base.json"]["solids"].append({"name": "crate", "group": "base", "shape": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [1, 1, 1]}})
        self.expect(clash, r'solids "crate": is defined in two files, design\.json and subsystems/base\.json')

    def test_subsystem_files_hold_only_subsystem_entries(self):
        """Catches whole-design entries in a subsystem file, or subsystem entries left in a top file that lists subsystems."""
        self.expect(lambda top, files: files[LAST].update(parameters={"x": 1}), r'subsystem "subsystems/carriage\.json": has an unknown field "parameters"')
        self.expect(lambda top, files: top.update(groups={"extra": {"role": "other"}}),
                    r'groups: a design that lists "subsystems" keeps its groups in the subsystem files')
        self.expect(lambda top, files: files[LAST].update(schema="frc-design-kernel/design@1"),
                    r'subsystem "subsystems/carriage\.json" schema: must be "frc-design-kernel/subsystem@1"')

    def test_each_listed_file_is_read_once_from_inside_the_folder(self):
        """Catches a missing, repeated or outside subsystem file being skipped or read."""
        self.expect(lambda top, files: top["subsystems"].append({"file": "subsystems/missing.json"}),
                    r'subsystems\[3\]: the subsystem file "subsystems/missing\.json" does not exist')
        self.expect(lambda top, files: top["subsystems"].append({"file": "subsystems/base.json"}),
                    r'subsystems\[3\]: the subsystem file "subsystems/base\.json" is listed twice')
        self.expect(lambda top, files: top["subsystems"].append({"file": "../outside.json"}),
                    r'subsystems\[3\]: the subsystem file "\.\./outside\.json" is outside the design folder')

    def test_errors_inside_a_subsystem_file_name_it(self):
        """Catches a problem in a subsystem file reported with no file, or at its place in the merged list."""
        self.expect(lambda top, files: solid_entry(files, "subsystems/drive.json", "spool")["shape"].pop("toMm"),
                    r'subsystem "subsystems/drive\.json" solids\[2\] "spool" shape: is missing "toMm"')
        self.expect(lambda top, files: solid_entry(files, "subsystems/drive.json", "spool").update(group="nowhere"),
                    r'subsystem "subsystems/drive\.json" solids\[2\] "spool": names the group "nowhere"')
        self.expect(lambda top, files: files["subsystems/drive.json"]["mounts"][0].update(on="no such solid"),
                    r'subsystem "subsystems/drive\.json" mounts\[0\] on: names the solid "no such solid"')
        self.expect(lambda top, files: solid_entry(files, LAST, "carriage plate")["shape"]["toMm"].__setitem__(0, "=post_q"),
                    r'subsystem "subsystems/carriage\.json" solids\[1\] "carriage plate" shape\.toMm\[0\]: .*post_q')

    def test_part_files_resolve_from_the_top_file(self):
        """Catches a part file in a subsystem file read relative to that file instead of to the top file's folder."""
        self.expect(lambda top, files: solid_entry(files, "subsystems/drive.json", "gearmotor body")["part"].update(file="../parts/gearmotor.step"),
                    r'the part file "\.\./parts/gearmotor\.step" is outside the design folder')

    def test_a_design_needs_its_groups_and_solids_somewhere(self):
        """Catches a design with no solids at all being accepted, with or without subsystem files."""
        self.expect(lambda top, files: [body.pop("solids", None) for body in files.values()], r'no subsystem file holds any "solids"')
        with self.assertRaisesRegex(DesignError, r'is missing "groups"'):
            top, _ = split(example())
            top.pop("subsystems")
            load(written(top, {}))


class Schema(unittest.TestCase):
    def test_subsystem_schema_uses_only_keywords_the_checker_knows(self):
        """Catches a subsystem schema rule that the small checker would silently ignore."""
        self.assertEqual(keywords_in(schema.load_schema("subsystem")) - schema.KEYWORDS, set())

    def test_each_section_has_one_definition(self):
        """Catches a section defined twice, so a field added to the design schema would be missing from subsystem files."""
        sections = {key: value for key, value in schema.load_schema("subsystem")["properties"].items() if key not in ("$schema", "schema", "note")}
        self.assertEqual(set(sections), {"groups", "solids", "mounts", "contacts", "drives", "motions", "poses", "adjustments", "interactions", "extraMass"})
        for key, value in sections.items():
            self.assertEqual(value, {"$ref": f"design.schema.json#/properties/{key}"}, key)


class Status(unittest.TestCase):
    def test_moving_a_solid_to_another_file_leaves_every_record_current(self):
        """Catches a record that goes stale only because an entry moved to another subsystem file; the control moves the solid itself."""
        top, files = split(example())
        source = written(top, files)
        out = source.parent / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            main(["measure", str(source), "--out", str(out), "--motion", "lift", "--pose", "raised", "--workers", "1"])
        plate = solid_entry(files, LAST, "carriage plate")
        files[LAST]["solids"].remove(plate)
        files["subsystems/base.json"]["solids"].insert(0, plate)
        moved = written(top, files)
        report = status(moved, out)
        self.assertTrue(report["records"])
        self.assertEqual([row for row in report["records"] if row["state"] != "current"], [])
        plate["shape"]["fromMm"][0] = "=post_x + 25"
        shifted = status(written(top, files), out)
        self.assertIn("stale", [row["state"] for row in shifted["records"]])


if __name__ == "__main__":
    unittest.main()
