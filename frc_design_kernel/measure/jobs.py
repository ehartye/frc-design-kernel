"""Measuring jobs: the kinds of question, their fields, their file names, and how each is answered.

A job is one question about a design, given as plain data: {"kind": "reach", "motion": "lift", "pair": [a, b],
"withinMm": 3}. Every kind is a row of KINDS: its target (a motion or a pose) and its fields with their defaults. A
new kind adds a row there and a branch in perform and finish.
"""
import hashlib
import re

from ..errors import DesignError
from ..workers import silent
from . import approach, attachment, clearance, compression, electrical, mass, scene as scenes, summary
from .search import DEFAULT_DEPTH

REQUIRED = "required"
KINDS = {
    "clearance": {"minGapMm": 0.0, "depth": DEFAULT_DEPTH, "includeStill": False, "nearMm": 0.0, "contacts": "declared", "absent": [], "displace": {}},
    "clearance at a pose": {"minGapMm": 0.0, "contacts": "declared", "absent": []},
    "reach": {"pair": REQUIRED, "withinMm": REQUIRED, "window": [0.0, 1.0], "absent": [], "depth": DEFAULT_DEPTH},
    "indentation": {"piece": REQUIRED, "contact": REQUIRED, "maxDepthMm": REQUIRED, "absent": [], "depth": DEFAULT_DEPTH},
    "withdrawal": {"absent": []},
    "attachment": {"touchGapMm": 0.0, "floorZMm": 0.0, "ignore": [], "base": None, "contacts": "declared", "absent": [], "pairs": True},
    "mass": {"absent": []},
    "electrical": {"samples": electrical.DEFAULT_SAMPLES},
}
NAMES = ("clearance", "reach", "indentation", "withdrawal", "attachment", "mass", "electrical")
ALONG = {"clearance", "reach", "indentation", "withdrawal", "electrical"}     # kinds asked along a motion; the rest at a pose
NUMBERS = {"minGapMm", "nearMm", "withinMm", "maxDepthMm", "touchGapMm", "floorZMm"}
ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,159}")


def fields_of(job):
    """The KINDS row for a job: a clearance with a pose is the pose form."""
    kind = job.get("kind")
    if kind not in NAMES:
        raise DesignError("", f'there is no job kind "{kind}"', "Use clearance, reach, indentation, withdrawal, attachment, mass or electrical")
    return KINDS["clearance at a pose" if kind == "clearance" and "pose" in job else kind]


def plain_value(field, value):
    if field in NUMBERS:
        return float(value)
    if field in ("absent", "ignore"):
        return sorted(value)
    if field == "displace":
        return {name: [float(v) for v in shift] for name, shift in sorted(value.items())}
    if field == "window":
        return [float(v) for v in value]
    if field == "samples":
        return int(value)
    if field == "contacts" and value != "declared":
        return sorted(sorted(pair) for pair in value)
    return value


def normalized(data, job):
    """The job with every field present and in one plain form; refuses a field the kind does not have or a missing one."""
    fields, kind = fields_of(job), job["kind"]
    target = "motion" if kind in ALONG and "pose" not in job else "pose"
    out = {"kind": kind, target: job.get(target)}
    if target == "motion" and job.get("motion") not in data["motions"]:
        raise DesignError("", f'there is no motion named "{job.get("motion")}"', f"Known motions: {', '.join(data['motions']) or 'none'}")
    if target == "pose" and out["pose"] is not None and out["pose"] not in data["poses"]:
        raise DesignError("", f'there is no pose named "{out["pose"]}"', f"Known poses: {', '.join(data['poses']) or 'none'}")
    for field in sorted(set(job) - set(fields) - {"kind", "id", target}):
        raise DesignError("", f'a {kind} job has no field "{field}"', f"Its fields: {', '.join(fields)}")
    for field, default in fields.items():
        if job.get(field, default) == REQUIRED:
            raise DesignError("", f'needs "{field}"', f"Give the {kind} job its {field}")
        out[field] = plain_value(field, job.get(field, default))
    if kind == "reach" and not (isinstance(out["pair"], list) and len(out["pair"]) == 2):
        raise DesignError("", "a reach job's pair is two solid names", 'For example "pair": ["hook", "bar"]')
    if kind == "electrical":
        electrical.load_of(data, out["motion"])
        if out["samples"] < 2:
            raise DesignError("", "an electrical job needs at least 2 samples", "Give samples of 2 or more; 32 is the default")
    if "id" in job:
        if not isinstance(job["id"], str) or not ID.fullmatch(job["id"]):
            raise DesignError("", "an id is lower-case letters, digits, dots, dashes and underscores, starting with a letter or digit",
                              f'Give another id than "{job["id"]}"')
        out["id"] = job["id"]
    return out


def slug(text):
    """A name as a piece of a file name: lower case, anything else a dash; a long name is cut and keeps a digest."""
    found = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "x"
    return found if len(found) <= 48 else f"{found[:40]}-{hashlib.sha256(str(text).encode('utf-8')).hexdigest()[:7]}"


def job_id(job):
    """The file name of a job, from what it asks about: kind, motion or pose, and the solids it names."""
    if "id" in job:
        return job["id"]
    kind = job["kind"]
    if kind == "clearance" and "motion" in job:
        parts = ["clearance", "motion", job["motion"]] + (["displaced", *job["displace"]] if job["displace"] else [])
    elif "motion" in job:
        parts = [kind, job["motion"], *{"reach": job.get("pair", ()), "indentation": (job.get("piece"), job.get("contact"))}.get(kind, ())]
    else:
        parts = [kind, "drawn"] if job["pose"] is None else [kind, "pose", job["pose"]]
    return ".".join([parts[0], *(slug(part) for part in parts[1:])])


def named_solids(job):
    """Every solid a job names, for a check that each is in the design."""
    return [*job.get("absent", ()), *job.get("displace", {}), *job.get("pair", ()), *job.get("ignore", ()),
            *(job[key] for key in ("piece", "contact", "base") if job.get(key) is not None)]


def present(data, job):
    """The solids of the design present for a job, sorted; refuses a job that names a solid the design does not have."""
    names = {solid["name"] for solid in data["solids"] + data["fixtures"]}
    for name in named_solids(job):
        if name not in names:
            raise DesignError("", f'names the solid "{name}", which is not in the design', "Name a solid of the design")
    return sorted(names - set(job.get("absent", ())))


def perform(assembly, job, focus=None, meter=silent):
    """Answer one whole job (every kind but a clearance along a motion, which is shared). meter hears how far it is."""
    kind, data = job["kind"], assembly.data
    contacts = summary.resolved_contacts(data, job, set(present(data, job))) if "contacts" in job else ()
    if kind == "clearance":
        return clearance.at_pose(assembly, job["pose"], job["minGapMm"], contacts, job["absent"], focus, meter)
    if kind == "attachment":
        return attachment.at_pose(assembly, job["pose"], job["touchGapMm"], job["floorZMm"], job["ignore"], job["base"], contacts,
                                  job["absent"], job["pairs"], meter)
    meter(0, 1)
    if kind == "reach":
        found = approach.reach(assembly, job["motion"], job["pair"], job["withinMm"], tuple(job["window"]), job["absent"], job["depth"])
    elif kind == "indentation":
        found = compression.indentation(assembly, job["motion"], job["piece"], job["contact"], job["maxDepthMm"], job["absent"], job["depth"])
    elif kind == "withdrawal":
        found = approach.withdrawn(assembly, job["motion"], job["absent"])
    elif kind == "electrical":
        found = electrical.measured(assembly, job["motion"], job["samples"])
    else:
        found = mass.roll_up(assembly, job["pose"], job["absent"])
    meter(1, 1)
    return found


def perform_share(assembly, job, share, focus=None, memo=None, meter=silent):
    """One share of a clearance along a motion."""
    scene = scenes.for_motion(assembly, job["motion"], job["absent"], job["displace"] or None)
    contacts = clearance.declared(summary.resolved_contacts(assembly.data, job, set(scene.names)), scene.names)
    return clearance.share_of(scene, job["minGapMm"], contacts, job["depth"], share, job["includeStill"], memo, None if focus is None else set(focus), meter)


def combined(data, job, focus, parts):
    """The answer of a clearance along a motion, from its shares."""
    names = present(data, job)
    contacts = clearance.declared(summary.resolved_contacts(data, job, set(names)), names)
    head = clearance.header("motion", job["motion"], job["minGapMm"], job["depth"], contacts, job["absent"], job["includeStill"], job["displace"] or None, focus)
    return clearance.combine(parts, head)


def kept(row, min_gap, near):
    """Whether a clearance row is stored: closer than the gap, not settled, or possibly within near of the gap."""
    return row["closerThanMinGap"] or not row["proven"] or row["lowerBoundMm"] < min_gap + near


def stored_clearance(found, near):
    """A clearance result as a record keeps it: only the rows that needed more than the broad phase to stay apart, and
    the closest of those. Pairs proven farther than the gap plus near are counted, not stored."""
    rows = [row for row in found["pairs"] if kept(row, found["minGapMm"], near)]
    with_gap = [r for r in rows if r["gapMm"] is not None]
    closest = min(with_gap, key=lambda r: (r["gapMm"], -r["overlapMm3"], r["pair"])) if with_gap else None
    result = {key: value for key, value in found.items() if key not in ("counts", "focus")}
    result.update(pairs=rows, nearMm=near,
                  closest=closest and {"pair": closest["pair"], "gapMm": closest["gapMm"], "t": closest["t"], "overlapMm3": closest["overlapMm3"]})
    return found["counts"], result


def finish(job, found):
    """(counts or None, result) of a job's answer, as its record stores them."""
    return stored_clearance(found, job.get("nearMm", 0.0)) if job["kind"] == "clearance" else (None, found)
