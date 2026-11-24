"""Measuring jobs: the kinds of question, their fields, their file names, what each draws on, and how each is answered.

A job is one question about a design, given as plain data: {"kind": "reach", "motion": "lift", "pair": [a, b],
"withinMm": 3}. Its rules (the caller's numbers) and the identities of the solids its answer depends on are its
"inputs"; the other design facts it depends on are its "used" block (see summary). Two jobs with equal inputs and
used blocks have equal answers, so a job whose record has both unchanged is carried whole, and a clearance whose
solids partly changed measures only the pairs that did (see carry).

Every kind is a row of KINDS: its target (a motion or a pose) and its fields with their defaults. A new kind adds a
row there and a branch in drawn_on, perform and finish.
"""
import hashlib
import re

from ..errors import DesignError
from . import approach, attachment, carry, clearance, compression, mass, summary
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
}
NAMES = ("clearance", "reach", "indentation", "withdrawal", "attachment", "mass")
ALONG = {"clearance", "reach", "indentation", "withdrawal"}     # kinds asked along a motion; the rest at a pose
NUMBERS = {"minGapMm", "nearMm", "withinMm", "maxDepthMm", "touchGapMm", "floorZMm"}
ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,159}")


def fields_of(job):
    """The KINDS row for a job: a clearance with a pose is the pose form."""
    kind = job.get("kind")
    if kind not in NAMES:
        raise DesignError("", f'there is no job kind "{kind}"', "Use clearance, reach, indentation, withdrawal, attachment or mass")
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


def present(assembly, job):
    for name in named_solids(job):
        if name not in assembly.solids:
            raise DesignError("", f'the job names the solid "{name}", which is no longer in the design', "Name a solid of the design")
    return sorted(set(assembly.solids) - set(job["absent"]))


def drawn_on(assembly, job):
    """(inputs, used) of a normalized job on a built design: its rules and solid identities, and the other facts it uses."""
    kind, names, data = job["kind"], present(assembly, job), assembly.data
    if "motion" in job:
        solids = carry.along(assembly, job["motion"], job["absent"], job.get("displace") or None)
    else:
        solids = carry.at_pose(assembly, job["pose"], job["absent"])
    used = {}
    if kind == "clearance" and "motion" in job:
        rules = dict(clearance.rules(job["minGapMm"], job["depth"], job["includeStill"]), nearMm=job["nearMm"])
        used = {"contacts": [list(pair) for pair in summary.resolved_contacts(data, job, set(names))]}
    elif kind == "clearance":
        rules = {"minGapMm": job["minGapMm"]}
        used = {"contacts": [list(pair) for pair in summary.resolved_contacts(data, job, set(names))]}
    elif kind == "reach":
        rules, solids = {"withinMm": job["withinMm"], "window": job["window"], "depthLimit": job["depth"]}, {n: solids[n] for n in sorted(job["pair"])}
    elif kind == "indentation":
        rules, solids = {"maxDepthMm": job["maxDepthMm"], "depthLimit": job["depth"]}, {n: solids[n] for n in sorted({job["piece"], job["contact"]})}
    elif kind == "withdrawal":
        rules = {}
    elif kind == "attachment":
        rules = {key: job[key] for key in ("touchGapMm", "floorZMm", "base", "pairs")} | {"ignored": job["ignore"]}
        kept = [name for name in names if name not in set(job["ignore"])]
        solids, used = {name: solids[name] for name in kept}, summary.used_by_attachment(assembly, job, kept)
    else:
        rules, used = {}, summary.used_by_mass(assembly, names)
        solids = {name: solids[name] for name in summary.weighed(assembly, names)}
    return {"rules": rules, "solids": solids}, used


def earlier_form(held):
    """A stored job record as the measuring functions take an earlier result to carry from, or None for kinds that carry whole."""
    kind = held["job"]["kind"]
    if kind == "clearance":
        return {**held["result"], "inputs": held["inputs"], "checked": held["checked"], "counts": held["counts"]}
    if kind == "attachment":
        fixtures = set(held["used"]["fixtures"])
        return {"inputs": {"touchGapMm": held["inputs"]["rules"]["touchGapMm"],
                           "solids": {name: value for name, value in held["inputs"]["solids"].items() if name not in fixtures}},
                "touching": held["result"]["touching"], "mounts": held["result"]["mounts"]}
    return None


def perform(assembly, job):
    """Answer one job that is not shared between workers (every kind but a clearance along a motion)."""
    kind, earlier = job["kind"], job.get("earlier")
    if kind == "clearance":
        return clearance.at_pose(assembly, job["pose"], job["minGapMm"], job["contacts"], job["absent"], focus=job.get("focus"), earlier=earlier)
    if kind == "reach":
        return approach.reach(assembly, job["motion"], job["pair"], job["withinMm"], tuple(job["window"]), job["absent"], job["depth"])
    if kind == "indentation":
        return compression.indentation(assembly, job["motion"], job["piece"], job["contact"], job["maxDepthMm"], job["absent"], job["depth"])
    if kind == "withdrawal":
        return approach.withdrawn(assembly, job["motion"], job["absent"])
    if kind == "attachment":
        return attachment.at_pose(assembly, job["pose"], job["touchGapMm"], job["floorZMm"], job["ignore"], job["base"], job["contacts"],
                                  job["absent"], job["pairs"], earlier)
    return mass.roll_up(assembly, job["pose"], job["absent"])


def kept(row, min_gap, near):
    """Whether a clearance row is stored: closer than the gap, not settled, or possibly within near of the gap."""
    return row["closerThanMinGap"] or not row["proven"] or row["lowerBoundMm"] < min_gap + near


def stored_clearance(found, near):
    """A clearance result as a record keeps it: only the rows that needed more than the broad phase to stay apart, and
    the closest of those. Pairs proven farther than the gap plus near are counted, not stored."""
    rows = [row for row in found["pairs"] if kept(row, found["minGapMm"], near)]
    with_gap = [r for r in rows if r["gapMm"] is not None]
    closest = min(with_gap, key=lambda r: (r["gapMm"], -r["overlapMm3"], r["pair"])) if with_gap else None
    result = {key: value for key, value in found.items() if key not in ("inputs", "checked", "counts")}
    result.update(pairs=rows, nearMm=near,
                  closest=closest and {"pair": closest["pair"], "gapMm": closest["gapMm"], "t": closest["t"], "overlapMm3": closest["overlapMm3"]})
    return found["checked"], found["counts"], result


def finish(job, found):
    """(checked, counts or None, result) of a job's answer, as its record stores them."""
    if job["kind"] == "clearance":
        return stored_clearance(found, job.get("nearMm", 0.0))
    if job["kind"] == "attachment":
        result = {key: value for key, value in found.items() if key not in ("inputs", "checked")}
        return found["checked"] or {"measured": "whole"}, None, result
    return {"measured": "whole"}, None, found
