"""Measuring again only what changed, and carrying the rest from an earlier result.

A pair's clearance depends only on its two solids, where each stands along the motion (or at the pose), and the
case's rules (the gap asked, the search depth, whether still pairs count). So each result records, for every solid
present, one short identity made from figures the build already produces: the solid's volume, centre of volume,
second moments of volume about that centre and bounding box as drawn, its group's whole placement along the motion
or at the pose, and any shift asked for. A later measurement compares those identities and measures again only the
pairs with a solid whose identity changed, and any pair whose declared contact changed. Every other pair is carried.

The decision reads no file bytes, names, notes or versions. A renamed solid is found by its identity and its rows
are carried under the new name. Two different shapes with the same volume, centre, second moments and box would be
taken as the same solid; that is the one thing the identity cannot tell apart.
"""
import hashlib
import json
from dataclasses import dataclass, field

from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from ..builder import placement
from ..kernel import props

COUNTS = ("pairs", "declaredContacts", "bothStill", "farApart", "fixedFarApart", "measured", "notInFocus")
DIGITS = 12             # significant digits kept of each figure, so the same build always gives the same identity
_HELD = {}              # {(what, id(assembly)): (assembly, table)}: tables worked out once per assembly, a few at most


def plain(value):
    """A value as plain data: numbers to DIGITS significant digits, tuples as lists, notes left out."""
    if isinstance(value, float):
        rounded = float(f"{value:.{DIGITS}g}")
        return 0.0 if abs(rounded) < 1e-9 else rounded
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items() if k != "note"}
    return value


def digest(value):
    text = json.dumps(plain(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def once(assembly, what, make):
    """make(assembly), worked out once for each assembly (it is kept, so its id cannot be reused while held)."""
    key = (what, id(assembly))
    held = _HELD.get(key)
    if held is None or held[0] is not assembly:
        if len(_HELD) > 7:
            _HELD.clear()
        held = _HELD[key] = (assembly, make(assembly))
    return held[1]


def shape_figures(shape):
    found = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, found, True)
    moments = found.MatrixOfInertia()
    return [found.Mass(), list(found.CentreOfMass().Coord()), [moments.Value(i, j) for i, j in ((1, 1), (2, 2), (3, 3), (1, 2), (1, 3), (2, 3))],
            props.bounds(shape)]


def figures(assembly):
    """{name: [volume, centre, second moments, box]} of every solid as drawn."""
    return once(assembly, "figures", lambda built: {name: shape_figures(solid.shape) for name, solid in built.solids.items()})


def placed(assembly, group_stages, absent=(), displace=None):
    """{name: identity} for every solid present, from its figures, its group's placement and any shift."""
    shapes, groups, gone = figures(assembly), {}, set(absent)
    out = {}
    for name in sorted(assembly.solids):
        if name in gone:
            continue
        group = assembly.solids[name].group
        if group not in groups:
            groups[group] = digest(group_stages.get(group, []))
        out[name] = digest([shapes[name], groups[group], (displace or {}).get(name)])
    return out


def along(assembly, motion, absent=(), displace=None):
    return placed(assembly, placement.motion_stages(assembly.data, motion), absent, displace)


def at_pose(assembly, pose=None, absent=()):
    return placed(assembly, placement.pose_stages(assembly.data, pose), absent)


def pair_of(a, b):
    return (a, b) if a < b else (b, a)


def pair_index(names, a, b):
    """Where the pair (a, b) comes in itertools.combinations(names, 2), for sorted names."""
    i, j = sorted((names.index(a), names.index(b)))
    return i * (2 * len(names) - i - 1) // 2 + (j - i - 1)


def matched(old, now):
    """{current name: earlier name} for each solid whose identity is unchanged, found by name first, then by identity alone."""
    found = {name: name for name, value in now.items() if old.get(name) == value}
    left_old, left_now = {}, {}
    for name, value in old.items():
        if name not in found:
            left_old.setdefault(value, []).append(name)
    for name, value in now.items():
        if name not in found:
            left_now.setdefault(value, []).append(name)
    for value, names in left_now.items():
        if len(names) == 1 and len(left_old.get(value, ())) == 1:
            found[names[0]] = left_old[value][0]
    return found


@dataclass
class Plan:
    """What to measure: the pairs with a focus solid in them and the pairs in also. The rest is carried, or not measured."""
    focus: set = None           # None measures every pair
    also: set = field(default_factory=set)
    rows: dict = field(default_factory=dict)      # {pair: earlier row under the current names}, for carried pairs
    carrying: bool = False      # pairs outside the focus are carried (True) or left unmeasured (False)
    renamed: dict = field(default_factory=dict)   # {current name: earlier name}
    counts: dict = None         # the earlier counts, when nothing changed and nothing is measured

    def job(self):
        """The plan as plain data for a worker process."""
        return {"focus": None if self.focus is None else sorted(self.focus), "also": sorted(self.also), "withRows": sorted(self.rows),
                "carrying": self.carrying}


def usable(earlier, rules):
    """Whether an earlier result can be carried from: it records its inputs, every pair was measured, and the rules agree."""
    inputs = (earlier or {}).get("inputs") or {}
    return bool(inputs.get("solids") is not None and plain(inputs.get("rules")) == plain(rules)
                and (earlier.get("checked") or {}).get("pairsNotMeasured", 1) == 0)


def plan(earlier, inputs, contacts, focus=None, given=False):
    """Decide which pairs to measure. earlier is the earlier result (given says one was asked for); inputs this one's.

    Without an earlier result, focus (when given) is measured and nothing else. With a usable one, the pairs of
    changed, new and focus solids are measured, and the pairs whose declared contact changed. With an unusable one
    (no inputs recorded, part measured, other rules) every pair is measured.
    """
    if not given:
        return Plan(None if focus is None else set(focus))
    if not usable(earlier, inputs["rules"]):
        return Plan()
    old, now = earlier["inputs"]["solids"], inputs["solids"]
    renamed = matched(old, now)
    back = {was: name for name, was in renamed.items()}
    changed = (set(now) - set(renamed)) | set(focus or ())
    was_contact = {pair_of(back[a], back[b]) for a, b in earlier.get("declaredContacts", []) if a in back and b in back}
    also = {pair for pair in was_contact ^ set(contacts) if pair[0] not in changed and pair[1] not in changed}
    rows = {}
    for row in earlier.get("pairs", []):
        a, b = row["pair"]
        if a in back and b in back:
            pair = pair_of(back[a], back[b])
            if pair[0] not in changed and pair[1] not in changed and pair not in also:
                rows[pair] = dict(row, pair=list(pair))
    whole = not changed and not also and len(renamed) == len(old)
    return Plan(changed, also, rows, True, {name: was for name, was in renamed.items() if name != was}, earlier["counts"] if whole else None)


def carried_part(names, chosen):
    """The carried rows of a plan as one share: in pair order, with the earlier counts when the whole result is carried."""
    rows = [(pair_index(names, *pair), row) for pair, row in chosen.rows.items()]
    counts = dict(chosen.counts) if chosen.counts is not None else dict.fromkeys(COUNTS, 0)
    carried = len(names) * (len(names) - 1) // 2 if chosen.counts is not None else 0
    return {"rows": rows, "counts": counts, "tally": {"measured": 0, "carried": carried, "notMeasured": 0}}


def checked(chosen, tally):
    """The record of what was measured now and what was carried."""
    return {"measuredSolids": None if chosen.focus is None else sorted(chosen.focus), "measuredPairs": [list(p) for p in sorted(chosen.also)],
            "pairsMeasured": tally["measured"], "pairsCarried": tally["carried"], "pairsNotMeasured": tally["notMeasured"],
            "renamed": dict(sorted(chosen.renamed.items()))}


@dataclass
class Touching:
    """What an attachment can carry from an earlier one: the touching gaps and mount distances of unchanged solids."""
    changed: set                # solids whose pairs are measured again
    gaps: dict                  # {pair: gap} of the carried pairs that touched
    mounts: dict                # {(member, on, point): earlier mount row}
    tally: dict = field(default_factory=lambda: {"pairsMeasured": 0, "pairsCarried": 0, "mountsMeasured": 0, "mountsCarried": 0})


def touching_plan(earlier, inputs):
    """What an attachment at a pose can carry from an earlier one, or None when it measures everything.

    It can carry when the earlier one recorded its inputs and its touching pairs, with the same touching gap.
    """
    held = (earlier or {}).get("inputs") or {}
    if held.get("solids") is None or held.get("touchGapMm") != inputs["touchGapMm"] or earlier.get("touching") is None:
        return None
    renamed = matched(held["solids"], inputs["solids"])
    back = {was: name for name, was in renamed.items()}
    gaps = {}
    for row in earlier["touching"]:
        a, b = row["pair"]
        if a in back and b in back:
            gaps[pair_of(back[a], back[b])] = row["gapMm"]
    mounts = {(back[row["member"]], back[row["on"]], point(row["atMm"])): row for row in earlier.get("mounts", [])
              if row["member"] in back and row["on"] in back and "gapMm" in row}
    return Touching(set(inputs["solids"]) - set(renamed), gaps, mounts)


def point(values):
    return json.dumps(plain(values))


def pose_inputs(assembly, solids, contacts, touch_gap, floor_z, ignore):
    """{"attachment": identity, "mass": identity} of everything the attachment and the mass at a pose draw on.

    Their records name solids and groups, so these identities hold the names too: a renamed solid or group is
    measured again here, though no clearance pair is.
    """
    data, built = assembly.data, assembly.solids
    attach = digest([{name: [value, built[name].group, built[name].fixture] for name, value in solids.items()},
                     sorted(sorted(pair) for pair in contacts), data["mounts"], float(touch_gap), float(floor_z), sorted(ignore)])
    weigh = digest([{name: [value, built[name].group, built[name].fixture, built[name].mass_kg] for name, value in solids.items()},
                    {name: group.get("massKg") for name, group in data["groups"].items()}])
    return {"attachment": attach, "mass": weigh}
