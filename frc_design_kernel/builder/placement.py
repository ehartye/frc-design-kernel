"""Where each group is at a pose or along a motion. Works on the plain design data; no CAD kernel needed.

Each group's movement is a list of stages (see motion.stages): its own pose or motion first, then everything its
carrier gets. The transform at any stroke fraction is read from those stages, so a clearance check and an export can
never disagree about where a group is.
"""
from ..errors import DesignError
from ..motion import matrix as mx
from ..motion import ops, stages
from ..motion.sampling import as_ops

END_TOLERANCE_MM = 1e-3


def known(table, name, what):
    if name not in table:
        raise DesignError("", f'there is no {what} named "{name}"', f"Known {what}s: {', '.join(table) or 'none'}")
    return table[name]


def own_pose(data, pose):
    """{group: transform} from a named pose's own operations; None is the as-drawn pose."""
    return {} if pose is None else {group: ops.at(listed) for group, listed in known(data["poses"], pose, "pose").items()}


def own_stages(data, motion):
    """{group: stages} for each group's own part of a named motion, before carriers."""
    entry = known(data["motions"], motion, "motion")
    if "through" in entry:
        stops = [own_pose(data, pose) for pose in entry["through"]]
        moving = sorted({group for stop in stops for group in stop})
        return {group: [("through", [stop.get(group, mx.IDENTITY) for stop in stops])] for group in moving}
    own = {group: [("fixed", placed)] for group, placed in own_pose(data, entry.get("from")).items()}
    for group, listed in entry["moves"].items():
        own.setdefault(group, []).append(("ops", listed))
    return own


def with_carriers(groups, own):
    """{group: stages} for every group: its own stages, then its carrier's, and so on up the chain."""
    total = {}

    def resolve(name):
        if name not in total:
            carrier = groups[name].get("carriedBy")
            total[name] = stages.tidy([*own.get(name, []), *(resolve(carrier) if carrier else [])])
        return total[name]

    for name in groups:
        resolve(name)
    return total


def pose_stages(data, pose):
    """{group: stages} holding every group still at a named pose."""
    return with_carriers(data["groups"], {group: [("fixed", placed)] for group, placed in own_pose(data, pose).items()})


def motion_stages(data, motion):
    """{group: stages} for a named motion, carriers included."""
    return with_carriers(data["groups"], own_stages(data, motion))


def at_pose(data, pose):
    """{group: total transform} at a named pose."""
    return {group: stages.at(listed, 0.0) for group, listed in pose_stages(data, pose).items()}


def at_motion(data, motion, t):
    """{group: total transform} at stroke fraction t of a named motion."""
    t = max(0.0, min(1.0, t))
    return {group: stages.at(listed, t) for group, listed in motion_stages(data, motion).items()}


def sampled(data, motion, steps):
    """A motion as steps + 1 still placements, for tools that only know translation, rotation and gravity-drop.

    Each row is {"t": fraction, "groups": {group: [operations]}}. The operations, applied in full to the solids as
    drawn, put the group where the motion has it at that fraction. Groups that have not moved are left out.
    """
    listed = motion_stages(data, motion)
    rows = []
    for n in range(steps + 1):
        placed = {group: as_ops(stages.at(own, n / steps)) for group, own in listed.items()}
        rows.append({"t": n / steps, "groups": {group: found for group, found in placed.items() if found}})
    return rows


def check_motion_ends(data):
    """Refuse a motion whose stated end pose is not where its moves actually finish."""
    for name, entry in data["motions"].items():
        if "to" not in entry:
            continue
        end, wanted = at_motion(data, name, 1.0), at_pose(data, entry["to"])
        for group in data["groups"]:
            miss = mx.gap(end[group], wanted[group])
            if miss > END_TOLERANCE_MM:
                raise DesignError(f'motions "{name}"', f'ends about {miss:.3g} mm away from the pose "{entry["to"]}" for the group "{group}"',
                                  'Correct the moves or the pose so they agree, or remove "to"')
