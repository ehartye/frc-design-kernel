"""Sharing clearance work between worker processes. Nothing here measures; it only hands out pairs and gathers rows.

Each worker loads and builds the design once, then measures the shares it is given. A share is every n-th pair of
one motion, so the rows come back in the same order whichever worker did which share, and the result is the same
for any worker count.
"""
import math
import os
from concurrent.futures import ProcessPoolExecutor

from ..source.load import load
from . import clearance, scene as scenes
from .search import DEFAULT_DEPTH

PAIRS_PER_SHARE = 500    # a motion with fewer pairs than this is one piece of work

_built = {}
_fixed = {}      # per process: what fixed pairs of the built design measured, reused across the jobs of that design


def default_workers():
    """Half the machine's cores, at least one. The caller may always choose another count."""
    return max(1, (os.cpu_count() or 2) // 2)


def assembly_for(source):
    """The built assembly for a design source, built once per process."""
    key = (str(source), os.path.getmtime(source))
    if key not in _built:
        from ..builder.assembly import build
        _built.clear()
        _fixed.clear()
        _built[key] = build(load(source))
    return _built[key]


def job_fields(job):
    return (job["motion"], job.get("minGapMm", 0.0), job.get("contacts", ()), job.get("absent", ()), job.get("depth", DEFAULT_DEPTH),
            bool(job.get("includeStill", False)), job.get("displace") or None)


def work(task):
    """Measure one share of one job. Runs in a worker process (or in the caller's, with one worker)."""
    source, job, share = task
    motion, min_gap, contacts, absent, depth, include_still, displace = job_fields(job)
    scene = scenes.for_motion(assembly_for(source), motion, absent, displace)
    return clearance.share_of(scene, min_gap, clearance.declared(contacts, scene.names), depth, share, include_still, _fixed)


def shares_for(solids, workers):
    """How many shares to cut a motion into: one per worker for a large motion, one for a small one."""
    return workers if math.comb(solids, 2) >= PAIRS_PER_SHARE else 1


def clearances(source, jobs, workers=None):
    """Clearance along several motions of one design source, shared between workers.

    jobs is a list of {"motion": name, "minGapMm": 0.0, "contacts": [[a, b], ...], "absent": [names], "depth": 9,
    "includeStill": False, "displace": {solid: [dx, dy, dz]}}; only "motion" is required. Returns one clearance result per job, in job order, the same as clearance.along gives.
    """
    workers = default_workers() if workers is None else max(1, int(workers))
    design = load(source)
    names = [s["name"] for s in design.data["solids"] + design.data["fixtures"]]
    tasks, spans = [], []
    for job in jobs:
        count = shares_for(len(names) - len(set(job.get("absent", ()))), workers)
        spans.append((len(tasks), count))
        tasks += [(str(source), job, (first, count)) for first in range(count)]
    if workers == 1:
        parts = [work(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(work, tasks))
    results = []
    for job, (start, count) in zip(jobs, spans):
        motion, min_gap, contacts, absent, depth, include_still, displace = job_fields(job)
        pairs = clearance.declared(contacts, set(names) - set(absent))
        results.append(clearance.combine(parts[start:start + count], clearance.header("motion", motion, min_gap, depth, pairs, absent, include_still, displace)))
    return results
