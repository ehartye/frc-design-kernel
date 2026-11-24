"""What the measure command asks of a whole design, and the contacts the design declares."""
from ..errors import DesignError
from . import electrical
from .search import DEFAULT_DEPTH


def contacts_for(data, motion=None):
    """The contact pairs the design source declares for a motion (or the ones declared for every motion, when None)."""
    return [row["pair"] for row in data.get("contacts", []) if "during" not in row or motion in row["during"]]


def chosen(table, names, what):
    for name in names or ():
        if name not in table:
            raise DesignError("", f'there is no {what} named "{name}"', f"Known {what}s: {', '.join(table) or 'none'}")
    return list(table) if names is None else list(names)


def design_jobs(data, min_gap=0.0, touch_gap=0.0, floor_z=0.0, ignore=(), depth=DEFAULT_DEPTH, near=0.0, motions=None, poses=None):
    """The jobs the measure command records: clearance along each motion, the electrical load of each motion that has
    one, and clearance, attachment and mass at each pose.

    motions and poses name a subset (None is all of them; the as-drawn pose is measured only when poses is None).
    """
    along = chosen(data["motions"], motions, "motion")
    jobs = [{"kind": "clearance", "motion": name, "minGapMm": min_gap, "depth": depth, "nearMm": near} for name in along]
    jobs += [{"kind": "electrical", "motion": name} for name in along if electrical.has_load(data["motions"][name])]
    for pose in ([None] if poses is None else []) + chosen(data["poses"], poses, "pose"):
        jobs += [{"kind": "clearance", "pose": pose, "minGapMm": min_gap},
                 {"kind": "attachment", "pose": pose, "touchGapMm": touch_gap, "floorZMm": floor_z, "ignore": sorted(ignore)},
                 {"kind": "mass", "pose": pose}]
    return jobs


def resolved_contacts(data, job, present):
    """The pairs a job leaves out as meant to touch: the source's declared ones ("declared") or the job's own list,
    each with both solids present, as sorted pairs."""
    listed = job["contacts"]
    if listed == "declared":
        listed = contacts_for(data, job.get("motion"))
    return sorted({tuple(sorted(pair)) for pair in listed if pair[0] in present and pair[1] in present})
