"""Where each group is at a pose or along a motion. Works on the plain design data; no CAD kernel needed.

A group's own transform comes from its pose or motion. A carried group then also gets everything its carrier gets:
total(group) = total(carrier) after own(group).
"""
from ..errors import DesignError
from ..motion import matrix as mx
from ..motion import ops, screw

END_TOLERANCE_MM = 1e-3


def with_carriers(groups, own):
    """{group: total transform} from {group: own transform}, passing each carrier's movement down to what it carries."""
    total = {}

    def resolve(name):
        if name not in total:
            mine = own.get(name, mx.IDENTITY)
            carrier = groups[name].get("carriedBy")
            total[name] = mx.compose(resolve(carrier), mine) if carrier else mine
        return total[name]

    for name in groups:
        resolve(name)
    return total


def own_at_pose(data, pose):
    """{group: own transform} at a named pose; None is the as-drawn pose."""
    if pose is None:
        return {}
    if pose not in data["poses"]:
        raise DesignError("", f'there is no pose named "{pose}"', f"Known poses: {', '.join(data['poses']) or 'none'}")
    return {group: ops.at(listed) for group, listed in data["poses"][pose].items()}


def own_at_motion(data, motion, t):
    """{group: own transform} at stroke fraction t of a named motion."""
    if motion not in data["motions"]:
        raise DesignError("", f'there is no motion named "{motion}"', f"Known motions: {', '.join(data['motions']) or 'none'}")
    entry = data["motions"][motion]
    t = max(0.0, min(1.0, t))
    if "through" in entry:
        stops = [own_at_pose(data, pose) for pose in entry["through"]]
        moving = sorted({group for stop in stops for group in stop})
        return {group: screw.through([stop.get(group, mx.IDENTITY) for stop in stops], t) for group in moving}
    own = own_at_pose(data, entry.get("from"))
    for group, listed in entry["moves"].items():
        own[group] = mx.compose(ops.at(listed, t), own.get(group, mx.IDENTITY))
    return own


def at_pose(data, pose):
    """{group: total transform} at a named pose."""
    return with_carriers(data["groups"], own_at_pose(data, pose))


def at_motion(data, motion, t):
    """{group: total transform} at stroke fraction t of a named motion."""
    return with_carriers(data["groups"], own_at_motion(data, motion, t))


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
