"""Write a built design to a folder: the robot STEP, the fixtures STEP and the manifest."""
import json
from pathlib import Path

from ..errors import DesignError
from ..kernel.step_write import write_solids
from .manifest import manifest

DESIGN_STEP, FIXTURES_STEP, MANIFEST = "design.step", "fixtures.step", "manifest.json"


def check_names(assembly):
    for name in assembly.solids:
        if not name.isascii() or not name.isprintable():
            raise DesignError(f'solid "{name}"', "the name has a character that STEP files do not carry safely",
                              "Use plain letters, digits, spaces and common punctuation in solid names")


def export(assembly, out, pose=None):
    """Write design.step, fixtures.step (when there are fixtures) and manifest.json into out. Returns the manifest."""
    check_names(assembly)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    title = assembly.data["name"]
    robot, fixtures = assembly.at_pose(pose, fixtures=False), assembly.at_pose(pose, fixtures=True)
    write_solids(out / DESIGN_STEP, robot, title)
    files = {"design": DESIGN_STEP, "fixtures": None}
    if fixtures:
        write_solids(out / FIXTURES_STEP, fixtures, f"{title} fixtures")
        files["fixtures"] = FIXTURES_STEP
    elif (out / FIXTURES_STEP).exists():
        (out / FIXTURES_STEP).unlink()
    record = manifest(assembly, pose, files)
    (out / MANIFEST).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return record
