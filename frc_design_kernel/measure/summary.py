"""Everything the measure layer can say about a design, gathered into one plain record with the library stamp."""
from ..version import generator
from . import attachment, clearance, mass, run
from .search import DEFAULT_DEPTH

SCHEMA = "frc-design-kernel/measurements@1"


def contacts_for(data, motion=None):
    """The contact pairs the design source declares for a motion (or the ones declared for every motion, when None)."""
    return [row["pair"] for row in data.get("contacts", []) if "during" not in row or motion in row["during"]]


def measure_design(source, min_gap=0.0, touch_gap=0.0, floor_z=0.0, ignore=(), workers=None, depth=DEFAULT_DEPTH):
    """Measure a design source: clearance along every motion, and clearance, attachment and mass at every pose.

    min_gap is the gap every pair is tested against. touch_gap is how near two surfaces count as touching. ignore
    names solids left out of the attachment record. The numbers are the caller's; the record states them and judges
    nothing.
    """
    assembly = run.assembly_for(source)
    data = assembly.data
    jobs = [{"motion": name, "minGapMm": min_gap, "contacts": contacts_for(data, name), "depth": depth} for name in data["motions"]]
    motions = dict(zip(data["motions"], run.clearances(source, jobs, workers)))
    poses = []
    for pose in [None, *data["poses"]]:
        declared = contacts_for(data)
        poses.append({"pose": pose, "clearance": clearance.at_pose(assembly, pose, min_gap, declared),
                      "attachment": attachment.at_pose(assembly, pose, touch_gap, floor_z, ignore, contacts=declared),
                      "mass": mass.roll_up(assembly, pose)})
    return {"schema": SCHEMA, "generator": generator(),
            "design": {"name": data["name"], "source": assembly.design.path.name, "sourceSha256": assembly.design.sha256},
            "settings": {"minGapMm": float(min_gap), "touchGapMm": float(touch_gap), "floorZMm": float(floor_z), "ignored": sorted(ignore),
                         "depthLimit": depth},
            "motions": motions, "poses": poses}
