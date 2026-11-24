"""Sharing clearance work between worker processes. Nothing here measures; it only hands out pairs and gathers rows.

Each worker loads and builds the design once, then measures the shares it is given. A share is every n-th pair of
one motion, so the rows come back in the same order whichever worker did which share, and the result is the same
for any worker count. A job given an earlier result is planned here first (see carry): only the pairs whose inputs
changed are handed out, a job with nothing changed is not handed out at all, and the carried rows are put back here.
"""
import math
import os
from concurrent.futures import ProcessPoolExecutor

from ..source.load import load
from . import carry, clearance, scene as scenes
from .search import DEFAULT_DEPTH

PAIRS_PER_SHARE = 500    # a motion with fewer pairs than this is one piece of work

_built = {}
_fixed = {}      # per process: what fixed pairs of the built design measured, reused across the jobs of that design


def default_workers():
    """Half the machine's cores, at least one. The caller may always choose another count."""
    return max(1, (os.cpu_count() or 2) // 2)


def assembly_for(source, parameters=None):
    """The built assembly for a design source, with any parameters set to other values, built once per process."""
    key = (str(source), os.path.getmtime(source), tuple(sorted((parameters or {}).items())))
    if key not in _built:
        from ..builder.assembly import build
        _built.clear()
        _fixed.clear()
        _built[key] = build(load(source, parameters or None))
    return _built[key]


def job_fields(job):
    return (job["motion"], job.get("minGapMm", 0.0), job.get("contacts", ()), job.get("absent", ()), job.get("depth", DEFAULT_DEPTH),
            bool(job.get("includeStill", False)), job.get("displace") or None)


def inputs_of(assembly, job):
    motion, min_gap, _, absent, depth, include_still, displace = job_fields(job)
    return {"rules": clearance.rules(min_gap, depth, include_still), "solids": carry.along(assembly, motion, absent, displace)}


def work(task):
    """Measure one share of one job. Runs in a worker process (or in the caller's, with one worker)."""
    source, job, share = task
    motion, min_gap, contacts, absent, depth, include_still, displace = job_fields(job)
    assembly = assembly_for(source, job.get("parameters"))
    scene = scenes.for_motion(assembly, motion, absent, displace)
    chosen = job["plan"]
    focus = set(chosen["focus"]) if chosen["focus"] is not None else None
    carried = {tuple(pair) for pair in chosen["withRows"]} if chosen["carrying"] else None
    part = clearance.share_of(scene, min_gap, clearance.declared(contacts, scene.names), depth, share, include_still, _fixed, focus,
                              {tuple(pair) for pair in chosen["also"]}, carried)
    if share[0] == 0 and not job["inputsKnown"]:
        part["inputs"] = inputs_of(assembly, job)
    return part


def shares_for(solids, workers):
    """How many shares to cut a motion into: one per worker for a large motion, one for a small one."""
    return workers if math.comb(solids, 2) >= PAIRS_PER_SHARE else 1


def planned(source, job, names, assembly):
    """(the plan, the inputs if worked out here) for one job: carried from its earlier result, or as focus says."""
    pairs = clearance.declared(job.get("contacts", ()), names)
    if "earlier" not in job:
        return carry.plan(None, None, pairs, job.get("focus")), None
    built = assembly if assembly is not None and not job.get("parameters") else assembly_for(source, job.get("parameters"))
    inputs = inputs_of(built, job)
    return carry.plan(job["earlier"], inputs, pairs, job.get("focus"), True), inputs


def clearances(source, jobs, workers=None, assembly=None):
    """Clearance along several motions of one design source, shared between workers.

    jobs is a list of {"motion": name, "minGapMm": 0.0, "contacts": [[a, b], ...], "absent": [names], "depth": 9,
    "includeStill": False, "displace": {solid: [dx, dy, dz]}, "parameters": {name: value}, "focus": [solids],
    "earlier": result}; only "motion" is required. "parameters" measures the design with those parameters changed;
    "focus" measures only pairs with one of those solids in them; "earlier" is an earlier result of the same job to
    carry unchanged pairs from, with focus then naming solids to measure again as well. assembly, when given, is the
    built design source, used here to plan carried jobs instead of building it again. Returns one clearance result
    per job, in job order, the same as clearance.along gives.
    """
    workers = default_workers() if workers is None else max(1, int(workers))
    design = load(source)
    names = [s["name"] for s in design.data["solids"] + design.data["fixtures"]]
    tasks, spans, plans = [], [], []
    for job in jobs:
        present = sorted(set(names) - set(job.get("absent", ())))
        chosen, inputs = planned(source, job, present, assembly)
        plans.append((chosen, inputs, present))
        sent = {key: value for key, value in job.items() if key != "earlier"} | {"plan": chosen.job()}
        sent["inputsKnown"] = inputs is not None       # worked out here already; the worker need not
        count = 0 if chosen.counts is not None else shares_for(len(present), workers)
        spans.append((len(tasks), count))
        tasks += [(str(source), sent, (first, count)) for first in range(count)]
    if workers == 1 or len(tasks) <= 1:
        parts = [work(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(work, tasks))
    results = []
    for job, (start, count), (chosen, inputs, present) in zip(jobs, spans, plans):
        motion, min_gap, contacts, absent, depth, include_still, displace = job_fields(job)
        pairs = clearance.declared(contacts, set(present))
        mine = parts[start:start + count]
        head = clearance.header("motion", motion, min_gap, depth, pairs, absent, include_still, displace)
        results.append(clearance.finished([carry.carried_part(tuple(present), chosen), *mine], head, inputs or mine[0]["inputs"], chosen))
    return results
