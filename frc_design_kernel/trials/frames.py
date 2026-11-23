"""Where the piece is in a group's own drawing coordinates, so a test can be written where the mechanism was drawn.

A trial may name frames: {"cassette": {"group": "Cassette", "mover": "approach"}}. Each gives one signal per axis of
the trial's plane, `cassette.xMm` and `cassette.zMm` for a plane square to y: the piece's centre in the coordinates
the group's solids were drawn in, before the group's own `place`, the trial's pose and the mover's motion. A seat
test written there holds while the robot drives, and does not have to be turned into world numbers by hand.

When the solids were not drawn square to the mechanism (taken from a STEP file in another pose, say), `place` puts
the frame within those drawing coordinates: operations applied in full, as a solid's `place` is. The signals are
then the piece's centre in that placed frame, so a seat test can still be written along the deck and off it.
Both engines read frames the same way. Nothing here imports MuJoCo.
"""
from ..builder import placement
from ..errors import DesignError
from ..kernel.section import AXES
from ..motion import matrix as mx
from ..motion import ops
from ..motion import stages as stage_math
from .rules import started


def build(case, data, where):
    """{name: frame} for a trial's case: the group's own place, and where its pose or its mover puts it."""
    found, posed = {}, placement.at_pose(data, case.get("pose"))
    for name, entry in case.get("frames", {}).items():
        at, group = f'{where} frame "{name}"', entry["group"]
        if group not in data["groups"]:
            raise DesignError(at, f'names the group "{group}", which the design does not have', f"Known groups: {', '.join(data['groups'])}")
        ops.check(entry.get("place", []), f"{at} place")
        within = ops.at(entry.get("place", []))        # the frame placed within the group's drawing coordinates
        frame = {"drawn": mx.compose(ops.at(data["groups"][group].get("place", [])), within), "posed": posed[group], "stages": None}
        if "mover" in entry:
            mover = case.get("movers", {}).get(entry["mover"])
            if mover is None or "motion" not in mover:
                raise DesignError(at, f'names the mover "{entry["mover"]}", which is not a mover along a design motion',
                                  'Name a mover of this trial that has a "motion"')
            frame["stages"] = placement.motion_stages(data, mover["motion"])[group]
            frame["timing"] = {key: mover[key] for key in ("startS", "after", "delayS", "durationS") if key in mover}
        found[name] = frame
    return found


def names(frames, normal):
    """The signals the frames add, in trace column order."""
    return [f"{name}.{'xyz'[i]}Mm" for name in frames for i in AXES[normal]]


def read(frames, normal, point_mm, happened, t):
    """{signal: value} for a piece centre at point_mm (3D, in the world) at time t."""
    signals = {}
    for name, frame in frames.items():
        place = frame["posed"]
        if frame["stages"] is not None:
            timing, begin = frame["timing"], started(frame["timing"], happened, t)
            fraction = 0.0 if begin is None else min(1.0, (t - begin) / timing["durationS"])
            place = stage_math.at(frame["stages"], fraction)
        local = mx.apply(mx.inverse(mx.compose(place, frame["drawn"])), point_mm)
        for i in AXES[normal]:
            signals[f"{name}.{'xyz'[i]}Mm"] = local[i]
    return signals
