"""The built design: every solid as drawn, and the same solids placed at any pose or point of a motion."""
from dataclasses import dataclass
from functools import cached_property

from ..errors import DesignError
from ..kernel import props
from ..kernel.transform import moved
from ..motion import matrix as mx
from ..motion import ops
from ..source.schema import step
from ..source.sourced import span
from . import placement
from .custom import CustomShapes
from .parts import Parts
from .shape import one_solid, solid as shape_solid

PART_VOLUME_TOLERANCE = 1e-6    # a placed part may differ from the file by this fraction of its volume, no more


@dataclass(frozen=True)
class Solid:
    """One named solid as drawn (before any pose), with what the source says about it."""
    name: str
    group: str
    shape: object           # the CAD kernel solid
    kind: str               # the shape kind, or "part"
    fixture: bool
    mass_kg: float | None   # None when the source gives no mass for this solid
    mass_range_kg: tuple | None     # (low, high); both ends are mass_kg unless the source assumes a range
    mass_from: str | None   # "massKg" or "densityKgM3"
    note: str


@dataclass(frozen=True)
class Assembly:
    """A design after building. Solids are kept as drawn; poses and motions place copies of them."""
    design: object          # the source.load.Design it was built from
    solids: dict            # {name: Solid}, robot solids first, then fixtures, in source order
    custom: list            # manifest rows for the custom shapes used
    parts: list             # manifest rows for the STEP files used

    @property
    def data(self):
        return self.design.data

    @cached_property
    def figures(self):
        """{name: (volume, centre, second moments)} of every solid as drawn, worked out once (see props.figures)."""
        return {name: props.figures(solid.shape) for name, solid in self.solids.items()}

    def members(self, group):
        return [s.name for s in self.solids.values() if s.group == group]

    def placed(self, transforms, fixtures=None):
        """{name: shape} with each solid moved by its group's transform. fixtures=True or False keeps only that kind."""
        chosen = [s for s in self.solids.values() if fixtures is None or s.fixture == fixtures]
        return {s.name: s.shape if mx.is_identity(transforms.get(s.group, mx.IDENTITY)) else moved(s.shape, transforms[s.group]) for s in chosen}

    def mesh(self, name, deflection_mm=0.5):
        """The named solid as drawn, as triangles: {"vertices": [[x, y, z]], "triangles": [[i, j, k]]} in millimetres."""
        from ..kernel.mesh import triangles
        return triangles(self.solids[name].shape, deflection_mm)

    def at_pose(self, pose=None, fixtures=None):
        """{name: shape} at a named pose. None is the pose the solids were drawn in."""
        return self.placed(placement.at_pose(self.data, pose), fixtures)

    def at_motion(self, motion, t, fixtures=None):
        """{name: shape} at stroke fraction t (0 to 1) of a named motion."""
        return self.placed(placement.at_motion(self.data, motion, t), fixtures)


def mass_of(entry, shape):
    """(mass, (low, high), where it came from) of a solid entry, or (None, None, None) when the source gives none."""
    for key, scale in (("massKg", lambda: 1.0), ("densityKgM3", lambda: props.volume(shape) * 1e-9)):
        if key in entry:
            factor = scale()
            value, low, high = span(entry[key])
            return value * factor, (low * factor, high * factor), key
    return None, None, None


def build_solid(entry, where, group, custom, parts, fixture):
    """One Solid from a source entry: made or imported, then moved by its own place and its group's place."""
    if "part" in entry:
        shape = one_solid(parts.take(entry["part"], entry["name"], where), where, "This part")
    else:
        shape = shape_solid(entry["shape"], f"{where} shape", custom.build)
    transform = mx.compose(ops.at(group.get("place", [])), ops.at(entry.get("place", [])))
    if not mx.is_identity(transform):
        before = props.volume(shape)
        shape = moved(shape, transform)
        if abs(props.volume(shape) - before) > PART_VOLUME_TOLERANCE * before:
            raise DesignError(where, "placing this solid changed its volume", "Report this: a rigid placement must not change a solid")
    mass, ends, basis = mass_of(entry, shape)
    kind = "part" if "part" in entry else entry["shape"]["kind"]
    return Solid(entry["name"], entry["group"], shape, kind, fixture, mass, ends, basis, entry.get("note", ""))


def build(design):
    """Build every solid of a loaded design. Raises DesignError, naming the entry, for anything that cannot be built."""
    data = design.data
    placement.check_motions(data)
    custom, parts = CustomShapes(design), Parts(design)
    solids = {}
    for section in ("solids", "fixtures"):
        for i, entry in enumerate(data[section]):
            where = step(section, i, entry)
            solids[entry["name"]] = build_solid(entry, where, data["groups"][entry["group"]], custom, parts, section == "fixtures")
    return Assembly(design, solids, custom.report(), parts.report())
