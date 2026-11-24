"""Mass roll-up with centre of mass, per group and for the whole robot, at a pose.

Each solid's mass sits at the centre of its volume. A group with one lump mass has it at the centre of the volume of
all its solids together. Fixtures are not part of the robot and are left out. A pose only moves solids rigidly, so
each solid's volume and centre are taken from the solid as drawn and its centre is moved by its group's placement:
no shape is moved or measured again for a pose.
"""
from ..builder import placement
from ..motion import matrix as mx
from . import carry, scene as scenes


def weighted_centre(items):
    """The centre of [(weight, point)], or None when the weights add to nothing."""
    total = sum(weight for weight, _ in items)
    if total <= 0:
        return None
    return [sum(weight * point[i] for weight, point in items) / total for i in range(3)]


def roll_up(assembly, pose=None, absent=()):
    """Mass and centre of mass of each group and of the whole robot at a named pose (None is as drawn)."""
    figures, places = carry.figures(assembly), placement.at_pose(assembly.data, pose)
    robot = [name for name in scenes.present(assembly, absent) if not assembly.solids[name].fixture]
    centre = {name: list(mx.apply(places[assembly.solids[name].group], figures[name][1])) for name in robot}
    volume = {name: figures[name][0] for name in robot}
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
