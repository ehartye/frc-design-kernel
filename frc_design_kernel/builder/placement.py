"""Where each group is at a pose or along a motion. Works on the plain design data; no CAD kernel needed.

Each group's movement is a list of stages (see motion.stages): its own pose or motion first, then everything its
carrier gets. The transform at any stroke fraction is read from those stages, so a clearance check and an export can
never disagree about where a group is.

A motion's own stages, before carriers, are built in this order:
1. Where it starts. A named pose, as drawn, or {"after": motion}: each group's own placement at the end of that
   motion, worked out as a placement, never kept as a name.
2. Its drive commands. Each commanded joint's group turns or slides from the joint value it starts at to the one
   commanded (motion.joints).
3. Its typed moves, for the groups no drive moves.
Carriers are added after that, as for any pose, so a joint rides on its carrier and a chained start composes with
the carriers exactly as a pose would.
"""
from ..errors import DesignError
from ..motion import joints
from ..motion import matrix as mx
from ..motion import ops, stages
from ..motion.sampling import as_ops

END_TOLERANCE_MM = 1e-3
TRAVEL_SLACK = 1e-9     # a command this close past a joint's stop is at the stop
SNAP_DIGITS = 12        # decimals kept of a chained start, so the same end always gives the same start


def known(table, name, what):
    if name not in table:
        raise DesignError("", f'there is no {what} named "{name}"', f"Known {what}s: {', '.join(table) or 'none'}")
    return table[name]


def own_pose(data, pose):
    """{group: transform} from a named pose's own operations; None is the as-drawn pose."""
    return {} if pose is None else {group: ops.at(listed) for group, listed in known(data["poses"], pose, "pose").items()}


def snapped(transform):
    """A worked-out placement with its last digits of arithmetic noise removed; nearly none is none."""
    if mx.is_identity(transform, 1e-9):
        return mx.IDENTITY
    return tuple(round(value, SNAP_DIGITS) + 0.0 for value in transform)


class Motions:
    """The motions of one design, each worked out once: a chained start and a joint value reuse what the earlier motion
    gave, so a chain of n motions costs n motions, not 2 ** n."""

    def __init__(self, data):
        self.data, self.held, self.given = data, {}, {}

    def own_stages(self, motion):
        """{group: stages} for each group's own part of a named motion, before carriers."""
        if motion not in self.held:
            self.held[motion] = self.work_out(motion)
        return self.held[motion]

    def work_out(self, motion):
        data = self.data
        entry = known(data["motions"], motion, "motion")
        if "through" in entry:
            stops = [own_pose(data, pose) for pose in entry["through"]]
            moving = sorted({group for stop in stops for group in stop})
            return {group: [("through", [stop.get(group, mx.IDENTITY) for stop in stops])] for group in moving}
        own = {group: [("fixed", placed)] for group, placed in self.own_start(motion).items()}
        for name, command in self.commands(motion).items():
            if command["change"]:
                own.setdefault(command["group"], []).append(("ops", [joints.operation(data["drives"][name]["joint"], command["change"])]))
        for group, listed in entry.get("moves", {}).items():
            own.setdefault(group, []).append(("ops", listed))
        return own

    def own_end(self, motion):
        """{group: transform} of each group's own placement at the end of a motion, before carriers; groups left as drawn are left out."""
        found = {group: snapped(stages.at(listed, 1.0)) for group, listed in self.own_stages(motion).items()}
        return {group: placed for group, placed in found.items() if not mx.is_identity(placed)}

    def own_start(self, motion):
        """{group: transform} of each group's own placement where a motion starts, before carriers."""
        start = known(self.data["motions"], motion, "motion").get("from")
        return self.own_end(start["after"]) if isinstance(start, dict) else own_pose(self.data, start)

    def moves_group(self, motion, group):
        """Whether a motion changes a group's own placement: a typed op, a commanded joint, or a "through" motion."""
        entry, drives = self.data["motions"][motion], self.data["drives"]
        return "through" in entry or group in entry.get("moves", {}) or any(drives[name]["joint"]["group"] == group for name in entry.get("drive", {}))

    def start_value(self, motion, name):
        """The joint value of a drive where a motion starts: carried along a chain of motions, else read from the placement."""
        joint = self.data["drives"][name]["joint"]
        start = self.data["motions"][motion].get("from")
        if isinstance(start, dict):
            before = start["after"]
            if name in self.data["motions"][before].get("drive", {}):
                return self.commands(before)[name]["to"]
            if not self.moves_group(before, joint["group"]):
                return self.start_value(before, name)
        value = joints.value_of(joint, self.own_start(motion).get(joint["group"], mx.IDENTITY))
        if value is None:
            raise DesignError(f'motions "{motion}" drive "{name}"', f'the group "{joint["group"]}" does not start on the joint of the drive "{name}"',
                              "Start the motion at a pose that places the group only by its joint, or move it there with this drive")
        return value

    def commands(self, motion):
        """{drive: {"group", "kind", "from", "to", "change", "motorTurns"}} for each drive a motion commands; {} for none."""
        if motion not in self.given:
            found = {}
            for name, command in sorted(known(self.data["motions"], motion, "motion").get("drive", {}).items()):
                drive = self.data["drives"][name]
                joint = drive["joint"]
                begin = self.start_value(motion, name)
                end = command["to"] if "to" in command else begin + command["by"]
                found[name] = {"group": joint["group"], "kind": joint["kind"], "from": begin, "to": end, "change": end - begin,
                               "motorTurns": joints.motor_turns(joint, drive.get("gear", 1.0), end - begin)}
            self.given[motion] = found
        return self.given[motion]


def own_stages(data, motion):
    """{group: stages} for each group's own part of a named motion, before carriers."""
    return Motions(data).own_stages(motion)


def commands(data, motion):
    """{drive: {"group", "kind", "from", "to", "change", "motorTurns"}} for each drive a motion commands; {} for none."""
    return Motions(data).commands(motion)


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


def described(data, motion):
    """What a record of a motion uses besides the solids' identities: each group's resolved start (carriers included),
    as 12 numbers, and each commanded joint's kind and values, by its group. No motion or drive name is kept, so a
    chained start is known by where it is, never by the motion it starts after."""
    start = {group: list(placed) for group, placed in sorted(at_motion(data, motion, 0.0).items()) if not mx.is_identity(placed)}
    found = {command["group"]: {"kind": command["kind"], "from": command["from"], "to": command["to"]} for command in commands(data, motion).values()}
    return {"start": start, "joints": dict(sorted(found.items()))}


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


def check_commands(data):
    """Refuse a drive command that starts or ends outside its joint's travel."""
    worked = Motions(data)
    for motion in data["motions"]:
        for name, command in worked.commands(motion).items():
            low, high = data["drives"][name]["joint"]["travel"]
            for end in ("from", "to"):
                if not low - TRAVEL_SLACK <= command[end] <= high + TRAVEL_SLACK:
                    verb = "starts" if end == "from" else "ends"
                    raise DesignError(f'motions "{motion}" drive "{name}"', f'{verb} the group "{command["group"]}" at {command[end]:g}, outside its joint travel [{low:g}, {high:g}]',
                                      "Command a value inside the travel, or widen the joint's travel if the mechanism allows it")


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


def check_motions(data):
    """Everything about motions that needs placements worked out: joint travel, then stated end poses."""
    check_commands(data)
    check_motion_ends(data)
