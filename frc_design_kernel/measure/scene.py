"""The solids of an assembly set up for measuring: where each starts, how it moves and how fast it can move."""
from dataclasses import dataclass

from ..builder import placement
from ..errors import DesignError
from ..kernel import props
from ..kernel.transform import moved
from ..motion import matrix as mx
from ..motion import stages as stage_math


@dataclass(frozen=True)
class Scene:
    """Solids at the start of a motion (or held at a pose), with what the clearance search needs for each."""
    names: tuple        # the solids present, sorted
    drawn: dict         # {name: solid as drawn}
    stages: dict        # {name: its group's stages}
    start: dict         # {name: solid at stroke fraction 0}
    boxes: dict         # {name: bounding box at stroke fraction 0}
    rates: dict         # {name: speed limit in mm per unit of t; 0 for a solid that does not move}
    moving: dict        # {name: text that is equal for solids that keep their relative pose}
    straight: dict      # {name: total travel if it only slides straight, else None}
    laws: dict          # {name: per-axis movement laws, or None}

    def at(self, name, t):
        """The solid at stroke fraction t."""
        if not self.rates[name]:
            return self.start[name]
        return moved(self.drawn[name], stage_math.at(self.stages[name], t))

    def fixed(self, a, b):
        """Whether two solids keep the same pose relative to each other for the whole stroke."""
        return self.moving[a] == self.moving[b]

    def still(self, name):
        return not self.rates[name]


def present(assembly, absent):
    for name in absent:
        if name not in assembly.solids:
            raise DesignError("", f'the absent solid "{name}" is not in the design', f"Known solids: {', '.join(sorted(assembly.solids))}")
    return tuple(sorted(name for name in assembly.solids if name not in set(absent)))


def build_scene(assembly, group_stages, absent=()):
    names = present(assembly, absent)
    by_group = {}
    for group, listed in group_stages.items():
        by_group[group] = (listed, stage_math.at(listed, 0.0), stage_math.signature(listed), stage_math.straight_travel(listed),
                           stage_math.axis_laws(listed), bool(stage_math.moving_part(listed)))
    drawn = {name: assembly.solids[name].shape for name in names}
    stages, start, boxes, rates, moving, straight, laws = {}, {}, {}, {}, {}, {}, {}
    for name in names:
        listed, first, signature, travel, law, moves = by_group[assembly.solids[name].group]
        stages[name], moving[name], straight[name], laws[name] = listed, signature, travel, law
        start[name] = drawn[name] if mx.is_identity(first) else moved(drawn[name], first)
        boxes[name] = props.bounds(start[name])
        rates[name] = stage_math.speed_limit(listed, props.bounds(drawn[name])) if moves else 0.0
    return Scene(names, drawn, stages, start, boxes, rates, moving, straight, laws)


def for_motion(assembly, motion, absent=()):
    """The scene for a named motion."""
    return build_scene(assembly, placement.motion_stages(assembly.data, motion), absent)


def for_pose(assembly, pose=None, absent=()):
    """The scene with every solid held at a named pose (None is as drawn)."""
    return build_scene(assembly, placement.pose_stages(assembly.data, pose), absent)
