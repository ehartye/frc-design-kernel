"""The manifest: the record of what was built. The same source always gives the same manifest."""
from ..kernel import props
from ..version import generator
from . import placement

SCHEMA = "frc-design-kernel/manifest@1"
PLACES = 6    # decimal places kept, so tiny arithmetic noise cannot change the file


def tidy(value):
    """Round every number inside value and turn -0.0 into 0.0."""
    if isinstance(value, float):
        return round(value, PLACES) + 0.0
    if isinstance(value, list):
        return [tidy(v) for v in value]
    if isinstance(value, dict):
        return {k: tidy(v) for k, v in value.items()}
    return value


def overall(boxes):
    """The box around a list of bounding boxes, or None for an empty list."""
    if not boxes:
        return None
    return [min(b[i] for b in boxes) for i in range(3)] + [max(b[i] for b in boxes) for i in range(3, 6)]


def solid_rows(assembly, placed, fixtures):
    rows = []
    for solid in assembly.solids.values():
        if solid.fixture != fixtures:
            continue
        row = {"name": solid.name, "group": solid.group, "kind": solid.kind, "volumeMm3": props.volume(placed[solid.name]),
               "boundsMm": props.bounds(placed[solid.name]), "massKg": solid.mass_kg, "massFrom": solid.mass_from}
        if solid.note:
            row["note"] = solid.note
        rows.append(row)
    return rows


def group_rows(assembly):
    """Per group: role, carrier, members and mass. A lump massKg on the group stands for all of its solids."""
    rows = {}
    for name, group in assembly.data["groups"].items():
        members = assembly.members(name)
        weighed = [assembly.solids[m].mass_kg for m in members if assembly.solids[m].mass_kg is not None]
        mass = float(group["massKg"]) if "massKg" in group else (sum(weighed) if weighed else None)
        rows[name] = {"role": group["role"], "carriedBy": group.get("carriedBy"), "members": members, "massKg": mass,
                      "massFrom": "group massKg" if "massKg" in group else ("solids" if weighed else None)}
    return rows


def mass_summary(assembly, groups):
    """Robot mass (fixtures left out) and the robot solids that no mass figure covers."""
    robot = [name for name in groups if any(not assembly.solids[m].fixture for m in groups[name]["members"])]
    unweighed = [s.name for s in assembly.solids.values()
                 if not s.fixture and s.mass_kg is None and "massKg" not in assembly.data["groups"][s.group]]
    return {"totalKg": sum(groups[name]["massKg"] or 0.0 for name in robot), "unweighed": unweighed}


def pose_rows(assembly):
    """Each pose with its operations and the box around the whole robot at that pose."""
    rows = {}
    for name, listed in assembly.data["poses"].items():
        robot = assembly.at_pose(name, fixtures=False)
        rows[name] = {"groups": listed, "robotBoundsMm": overall([props.bounds(shape) for shape in robot.values()])}
    return rows


def manifest(assembly, pose=None, files=None):
    """The manifest of an assembly exported at a pose (None is as drawn)."""
    design, data = assembly.design, assembly.data
    placed = assembly.at_pose(pose)
    groups = group_rows(assembly)
    robot = solid_rows(assembly, placed, False)
    return tidy({
        "schema": SCHEMA,
        "design": {"name": data["name"], "source": design.path.name, "sourceSha256": design.sha256, "frame": data["frame"]},
        "units": data["units"],
        "generator": generator(),
        "pose": pose,
        "files": files or {},
        "robotBoundsMm": overall([row["boundsMm"] for row in robot]),
        "mass": mass_summary(assembly, groups),
        "solids": robot,
        "fixtures": solid_rows(assembly, placed, True),
        "groups": groups,
        "mounts": data["mounts"],
        "poses": pose_rows(assembly),
        "motions": data["motions"],
        "parameters": data["parameters"],
        "parts": assembly.parts,
        "custom": assembly.custom,
    })
