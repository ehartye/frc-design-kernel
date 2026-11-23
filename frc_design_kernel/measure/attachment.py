"""At a pose: what touches what, what hangs together, what is not connected to the base, and which fixtures float.

Two solids "touch" when their surfaces are within a gap the caller chooses. A mount joins two solids whatever the gap,
and is measured: how far apart its two solids really are, and how far the stated point is from each.
"""
from ..errors import DesignError
from ..kernel import props
from ..kernel.between import distance, vertex
from . import scene as scenes
from .pairs import box_gap, near_pairs
from .sets import Sets


def touching_pairs(scene, names, gap):
    """[(a, b, gap in mm)] for every pair of the named solids whose surfaces are within gap."""
    boxes = {name: scene.boxes[name] for name in names}
    found = []
    for a, b in near_pairs(boxes, gap):
        measured = distance(scene.start[a], scene.start[b])
        if measured <= gap:
            found.append((a, b, measured))
    return found


def mount_ends(mount, scene, members):
    """The solids of the mounted group that a mount holds: its named member, or the one nearest the stated point."""
    if "member" in mount:
        return [mount["member"]] if mount["member"] in members else []
    point = [*mount["atMm"], *mount["atMm"]]
    others = [m for m in members if m != mount["on"]]
    reach = {m: box_gap(scene.boxes[m], point) for m in others}
    return [m for m in others if reach[m] <= min(reach.values()) + 1e-6]


def measured_mounts(assembly, scene, robot):
    """One row per mount and solid it holds: the real gap between the two solids and the point's distance to each."""
    rows = []
    for mount in assembly.data["mounts"]:
        if mount["on"] not in robot:
            continue
        point = vertex(mount["atMm"])
        for end in mount_ends(mount, scene, [m for m in assembly.members(mount["group"]) if m in robot]):
            rows.append({"group": mount["group"], "member": end, "on": mount["on"], "atMm": mount["atMm"],
                         "gapMm": distance(scene.start[end], scene.start[mount["on"]]),
                         "pointToMemberMm": distance(point, scene.start[end]), "pointToOnMm": distance(point, scene.start[mount["on"]])})
    return rows


def nearest(scene, name, others):
    """(the closest of the other solids, its gap). Boxes rule out the ones that cannot be closer."""
    best = (None, None)
    for other in sorted(others, key=lambda o: (box_gap(scene.boxes[name], scene.boxes[o]), o)):
        if best[1] is not None and box_gap(scene.boxes[name], scene.boxes[other]) >= best[1]:
            break
        gap = distance(scene.start[name], scene.start[other])
        if best[1] is None or gap < best[1]:
            best = (other, gap)
    return best


def base_set(sets, base):
    """The connected set that is the base: the one holding the named solid, or the largest when none is named."""
    groups = sets.groups()
    if base is None:
        return groups[0] if groups else []
    if base not in sets.parent:
        raise DesignError("", f'the base solid "{base}" is not among the solids measured', "Name a robot solid that is present and not ignored")
    return next(members for members in groups if base in members)


def fixtures_off_floor(scene, fixtures, gap, floor_z):
    """Fixtures that neither reach the floor nor rest, through touching fixtures, on one that does."""
    lowest = {name: props.bounds(scene.start[name])[2] for name in fixtures}
    grounded = [name for name in fixtures if lowest[name] <= floor_z + gap]
    hanging = [name for name in fixtures if name not in grounded]
    if not hanging:
        return []
    resting = Sets(fixtures)
    for other in grounded[1:]:
        resting.join(grounded[0], other)
    if grounded:
        for a, b, _ in touching_pairs(scene, fixtures, gap):
            resting.join(a, b)
    return [{"fixture": name, "lowestAboveFloorMm": lowest[name] - floor_z} for name in hanging
            if not grounded or not resting.together(name, grounded[0])]


def at_pose(assembly, pose=None, gap=0.0, floor_z=0.0, ignore=(), base=None, contacts=(), absent=()):
    """What is attached to what with every solid held at a named pose (None is as drawn).

    gap is how near two surfaces must be to count as touching. ignore names solids to leave out altogether (a game
    piece, a gauge). base names one solid of the base; without it the largest connected set is the base. contacts are
    pairs the caller declares joined. Returns plain data; it lists facts and judges none of them.
    """
    scene = scenes.for_pose(assembly, pose, absent)
    kept = [name for name in scene.names if name not in set(ignore)]
    robot = [name for name in kept if not assembly.solids[name].fixture]
    fixtures = [name for name in kept if assembly.solids[name].fixture]
    touching = touching_pairs(scene, robot, gap)
    by_touch, held = Sets(robot), Sets(robot)
    for a, b, _ in touching:
        by_touch.join(a, b)
        held.join(a, b)
    for a, b in contacts:
        if a in held.parent and b in held.parent:
            held.join(a, b)
    mounts = measured_mounts(assembly, scene, set(robot))
    for row in mounts:
        held.join(row["member"], row["on"])
    frame = base_set(held, base)
    inside = [members for members in by_touch.groups() if members[0] in set(frame)]
    core = next((members for members in inside if base in members), None) or (max(inside, key=len) if inside else [])
    loose = []
    for members in held.groups():
        if frame and members[0] in frame:
            continue
        for name in members:
            other, away = nearest(scene, name, frame) if frame else (None, None)
            loose.append({"solid": name, "group": assembly.solids[name].group, "nearest": other, "gapMm": away})
    return {"pose": pose, "touchGapMm": float(gap), "floorZMm": float(floor_z), "ignored": sorted(set(ignore) & set(scene.names)),
            "robotSolids": len(robot), "baseSolids": len(frame), "connectedSets": held.groups(),
            "notConnectedToBase": sorted(loose, key=lambda r: r["solid"]),
            "heldByMountOnly": sorted(set(frame) - set(core)),
            "touching": [{"pair": [a, b], "gapMm": measured} for a, b, measured in touching],
            "mounts": mounts,
            "fixtures": len(fixtures), "fixturesOffFloor": fixtures_off_floor(scene, fixtures, gap, floor_z)}
