"""What the robot weighs, where its centre of mass is, and the inertia of its groups, at a pose.

Every weight is three numbers: the nominal value and the low and high ends of its range. A plain or measured number
is exact, so it counts at both ends; only an assumed range widens them. The ends add separately, so a total's range
is the sum of the low ends and the sum of the high ends.

Each solid's mass sits at the centre of its volume. A group with one lump mass has it spread over its solids by
volume. Weight with no solid (`extraMass`) is a point at the centre of its group's volume. Fixtures are not part of
the robot and are left out. A pose only moves solids rigidly, so each solid's volume, centre and second moments are
taken from the solid as drawn and moved by its group's placement: no shape is moved or measured again for a pose.
"""
from dataclasses import dataclass

from ..builder import placement
from ..errors import DesignError
from ..motion import matrix as mx
from ..source.sourced import span
from . import carry, scene as scenes

KG_MM2 = 1e-6       # kg mm^2 in kg m^2
ZERO = (0.0, 0.0, 0.0)


def add(*weights):
    """The sum of (nominal, low, high) weights, end by end."""
    return tuple(sum(weight[i] for weight in weights) for i in range(3)) if weights else ZERO


def weighted_centre(items):
    """The centre of [(weight, point)], or None when the weights add to nothing."""
    total = sum(weight for weight, _ in items)
    if total <= 0:
        return None
    return [sum(weight * point[i] for weight, point in items) / total for i in range(3)]


@dataclass(frozen=True)
class Weight:
    """What one robot group weighs, and how the weight is spread over it. Each weight is (nominal, low, high)."""
    members: list           # its robot solids present, in source order
    solids: dict            # {solid: weight} of the solids that carry their own
    lump: tuple | None      # the group's one lump figure, spread over its solids by volume
    extra: dict             # {extra mass name: weight}, a point at the centre of the group's volume
    unweighed: list         # members that no figure covers

    @property
    def total(self):
        return add(*self.solids.values(), *([self.lump] if self.lump else []), *self.extra.values())

    def row(self):
        nominal, low, high = self.total
        return {"massKg": nominal, "rangeKg": [low, high], "from": "group massKg" if self.lump else "solids", "extra": list(self.extra)}

    def per_solid(self, volume):
        """{solid: weight} with a lump shared out by volume ({solid: mm3})."""
        if self.lump is None:
            return dict(self.solids)
        whole = sum(volume[name] for name in self.members)
        return {name: tuple(end * volume[name] / whole for end in self.lump) for name in self.members}


def weights(assembly, absent=()):
    """{group: Weight} for every group with a robot solid present, in source order."""
    present = set(scenes.present(assembly, absent))
    extra = {}
    for entry in assembly.data["extraMass"]:
        extra.setdefault(entry["group"], {})[entry["name"]] = span(entry["massKg"])
    found = {}
    for group, entry in assembly.data["groups"].items():
        members = [name for name, solid in assembly.solids.items() if solid.group == group and not solid.fixture and name in present]
        if not members:
            continue
        own = {name: (assembly.solids[name].mass_kg, *assembly.solids[name].mass_range_kg) for name in members if assembly.solids[name].mass_kg is not None}
        lump = span(entry["massKg"]) if "massKg" in entry else None
        found[group] = Weight(members, own, lump, extra.get(group, {}), [] if lump else [name for name in members if name not in own])
    return found


def totals(found):
    """{"totalKg", "rangeKg", "groups", "unweighed"} of {group: Weight}: the robot's mass as the manifest and roll-up state it."""
    nominal, low, high = add(*(weight.total for weight in found.values()))
    return {"totalKg": nominal, "rangeKg": [low, high], "groups": {group: weight.row() for group, weight in found.items()},
            "unweighed": sorted(name for weight in found.values() for name in weight.unweighed)}


def roll_up(assembly, pose=None, absent=(), places=None):
    """Mass, range and centre of mass of each group and of the whole robot at a named pose (None is as drawn).

    places ({group: transform}) stands in for the pose, for a point along a motion. Centres are of the nominal masses.
    """
    figures = carry.figures(assembly)
    places = placement.at_pose(assembly.data, pose) if places is None else places
    found = weights(assembly, absent)
    out = {"pose": pose, **totals(found)}
    whole = []
    for group, weight in found.items():
        centre = {name: list(mx.apply(places[group], figures[name][1])) for name in weight.members}
        volume = {name: figures[name][0] for name in weight.members}
        middle = weighted_centre([(volume[name], centre[name]) for name in weight.members])
        at = weighted_centre([(mass[0], centre[name]) for name, mass in weight.per_solid(volume).items()]
                             + [(mass[0], middle) for mass in weight.extra.values()])
        out["groups"][group].update(centreMm=at, solids=len(weight.members))
        if at is not None:
            whole.append((weight.total[0], at))
    out["centreMm"] = weighted_centre(whole)
    return out


def square_to(vector, axis):
    """The squared distance of a vector from a line along the unit axis."""
    along = mx.dot(vector, axis)
    return mx.dot(vector, vector) - along * along


def spin(moments, transform, axis):
    """A solid's second moment of volume about the unit axis through its centre, after the transform turns it (mm^5)."""
    xx, yy, zz, xy, xz, yz = moments
    m = transform
    u = (m[0] * axis[0] + m[4] * axis[1] + m[8] * axis[2], m[1] * axis[0] + m[5] * axis[1] + m[9] * axis[2],
         m[2] * axis[0] + m[6] * axis[1] + m[10] * axis[2])      # the axis in the solid's drawn directions
    return (xx * u[0] * u[0] + yy * u[1] * u[1] + zz * u[2] * u[2]
            + 2 * (xy * u[0] * u[1] + xz * u[0] * u[2] + yz * u[1] * u[2]))


def placed_masses(weight, figures, move):
    """[(weight, point)] of one group's masses placed by move: each solid's share at its centre, and each extra mass at
    the centre of the group's volume."""
    centre = {name: mx.apply(move, figures[name][1]) for name in weight.members}
    volume = {name: figures[name][0] for name in weight.members}
    middle = weighted_centre([(volume[name], centre[name]) for name in weight.members])
    return [(mass, centre[name]) for name, mass in weight.per_solid(volume).items()] + [(mass, middle) for mass in weight.extra.values()]


def balance(assembly, groups, places, found=None):
    """Mass and first moment of the named groups together at places ({group: transform}), at each end of the range.

    Returns {"kg": (nominal, low, high), "momentKgMm": (vector, vector, vector), "unweighed"}: the first moment is the
    sum of each mass times its point, so it over the mass is the centre of mass at that end. found is weights(assembly)
    when the caller already has it.
    """
    figures, found = carry.figures(assembly), weights(assembly) if found is None else found
    kg, moment, unweighed = [0.0, 0.0, 0.0], [ZERO, ZERO, ZERO], []
    for group in groups:
        if group not in found:
            continue
        for weight, point in placed_masses(found[group], figures, places[group]):
            for end in range(3):
                kg[end] += weight[end]
                moment[end] = mx.add(moment[end], mx.scale(point, weight[end]))
        unweighed += found[group].unweighed
    return {"kg": tuple(kg), "momentKgMm": tuple(tuple(vector) for vector in moment), "unweighed": sorted(unweighed)}


def inertia(assembly, groups, axis, point_mm, pose=None, places=None, found=None):
    """Moment of inertia of the named groups together about the line through point_mm along axis, in kg m^2.

    Each solid is taken as uniform: its mass over its volume times its second moments, moved to the line. Weight
    with no solid is a point at its group's centre of volume. At a named pose, or at places ({group: transform}).
    found is weights(assembly) when the caller already has it.
    Returns {"groups", "axis", "pointMm", "kgM2" (nominal), "rangeKgM2": [low, high], "unweighed"}.
    """
    for group in groups:
        if group not in assembly.data["groups"]:
            raise DesignError("", f'there is no group named "{group}"', f"Known groups: {', '.join(assembly.data['groups'])}")
    figures = carry.figures(assembly)
    places = placement.at_pose(assembly.data, pose) if places is None else places
    line, point, found = mx.unit(axis), tuple(point_mm), weights(assembly) if found is None else found
    parts, unweighed = [], []
    for group in groups:
        if group not in found:
            continue
        weight, move = found[group], places[group]
        centre = {name: mx.apply(move, figures[name][1]) for name in weight.members}
        volume = {name: figures[name][0] for name in weight.members}
        for name, mass in weight.per_solid(volume).items():
            reach = spin(figures[name][2], move, line) / volume[name] + square_to(mx.sub(centre[name], point), line)
            parts.append(tuple(end * reach for end in mass))
        middle = weighted_centre([(volume[name], centre[name]) for name in weight.members])
        parts += [tuple(end * square_to(mx.sub(middle, point), line) for end in mass) for mass in weight.extra.values()]
        unweighed += weight.unweighed
    nominal, low, high = add(*parts)
    return {"groups": list(groups), "axis": list(line), "pointMm": list(point), "kgM2": nominal * KG_MM2,
            "rangeKgM2": [low * KG_MM2, high * KG_MM2], "unweighed": sorted(unweighed)}
