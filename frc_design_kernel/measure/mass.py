"""Mass roll-up with centre of mass, per group and for the whole robot, at a pose.

Each solid's mass sits at the centre of its volume. A group with one lump mass has it at the centre of the volume of
all its solids together. Fixtures are not part of the robot and are left out.
"""
from ..kernel import props
from . import scene as scenes


def weighted_centre(items):
    """The centre of [(weight, point)], or None when the weights add to nothing."""
    total = sum(weight for weight, _ in items)
    if total <= 0:
        return None
    return [sum(weight * point[i] for weight, point in items) / total for i in range(3)]


def roll_up(assembly, pose=None, absent=()):
    """Mass and centre of mass of each group and of the whole robot at a named pose (None is as drawn)."""
    scene = scenes.for_pose(assembly, pose, absent)
    robot = [name for name in scene.names if not assembly.solids[name].fixture]
    centre = {name: props.centre(scene.start[name]) for name in robot}
    volume = {name: props.volume(scene.start[name]) for name in robot}
    groups, unweighed, whole = {}, [], []
    for group, entry in assembly.data["groups"].items():
        members = [name for name in robot if assembly.solids[name].group == group]
        if not members:
            continue
        if "massKg" in entry:
            mass, basis = float(entry["massKg"]), "group massKg at the centre of its solids' volume"
            at = weighted_centre([(volume[name], centre[name]) for name in members])
        else:
            weighed = [(assembly.solids[name].mass_kg, centre[name]) for name in members if assembly.solids[name].mass_kg is not None]
            unweighed += [name for name in members if assembly.solids[name].mass_kg is None]
            mass, basis = sum(weight for weight, _ in weighed), "solids"
            at = weighted_centre(weighed)
        groups[group] = {"massKg": mass, "centreMm": at, "from": basis, "solids": len(members)}
        if at is not None:
            whole.append((mass, at))
    return {"pose": pose, "totalKg": sum(row["massKg"] for row in groups.values()), "centreMm": weighted_centre(whole),
            "groups": groups, "unweighed": sorted(unweighed)}
