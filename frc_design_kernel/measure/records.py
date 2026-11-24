"""The measurement records: one file per job, DIR/measurements/<job id>.json, written whole as each job finishes.

A record holds the question, the answer and the library version. Every job asked is measured, whatever files are
there, and its file is replaced the moment it finishes, so a stopped run keeps every job it finished. A clearance
limited to named solids is only part of an answer: it is returned and never written.
"""
import json
import os
from contextlib import closing
from pathlib import Path

from ..errors import DesignError
from ..version import generator
from . import jobs as kinds
from .run import Ask

SCHEMA = "frc-design-kernel/measurement-job@2"
FOLDER = "measurements"


def path_of(folder, name):
    return Path(folder) / FOLDER / f"{name}.json"


def write_record(path, record):
    """Write a job record whole or not at all: into a temporary file beside it, then moved into its place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def requested(data, jobs):
    """[(id, normalized job)] for a list of jobs; refuses an unknown kind or field, a missing name, a solid that is not in
    the design, or two jobs with one id."""
    out, seen = [], {}
    for number, job in enumerate(jobs, 1):
        try:
            found = kinds.normalized(data, job)
        except DesignError as problem:
            raise problem.under(f"job {number}") from None
        name = kinds.job_id(found)
        if name in seen:
            raise DesignError("", f'jobs {seen[name]} and {number} have the same id "{name}"', 'Give one of them its own "id"')
        seen[name] = number
        try:
            kinds.present(data, found)
        except DesignError as problem:
            raise problem.under(f'job "{name}"') from None
        out.append((name, found))
    return out


def limited(data, asked, focus):
    """The named solids a measurement is limited to, checked, or None. Only a clearance can be limited."""
    if focus is None:
        return None
    known = [solid["name"] for solid in data["solids"] + data["fixtures"]]
    for name in focus:
        if name not in known:
            raise DesignError("", f'there is no solid named "{name}"', f"Known solids: {', '.join(sorted(known))}")
    for name, job in asked:
        if job["kind"] != "clearance":
            raise DesignError(f'job "{name}"', f"only a clearance can be limited to named solids, not {job['kind']}", "Ask for it whole, or leave it out")
    return tuple(sorted(set(focus)))


def each(bench, asked, focus=None):
    """Yield (index, record) for each requested job as it finishes."""
    made = generator()
    with closing(bench.answers([Ask(job, {"job": name}, focus) for name, job in asked])) as given:
        for index, found in given:
            name, job = asked[index]
            counts, result = kinds.finish(job, found)
            yield index, {"schema": SCHEMA, "generator": made, "id": name, "job": job, **({"focus": list(focus)} if focus else {}),
                          **({"counts": counts} if counts is not None else {}), "result": result}


def entry(record, **more):
    return {"id": record["id"], "kind": record["job"]["kind"], **more, "record": record}


def collected(found, size, report, made):
    """The entries of a run in job order, each passed to report as it is made. An error raised in report stops the run."""
    entries = [None] * size
    with closing(found):
        for index, record in found:
            entries[index] = made(record)
            if report:
                report(entries[index])
    return entries


def answers(bench, jobs, focus=None, report=None):
    """Measure jobs and return one entry per job, in job order: {"id", "kind", "record"}. Nothing is written.

    focus names solids: only the pairs with one of them in it are measured. Each record then has "focus", and its
    counts say under "notInFocus" how many pairs were left out.
    """
    asked = requested(bench.design.data, jobs)
    focus = limited(bench.design.data, asked, focus)
    return collected(each(bench, asked, focus), len(asked), report, entry)


def record(bench, jobs, folder, report=None):
    """Measure jobs and keep each answer as its own file in folder/measurements, written as it finishes.

    report, when given, is called with each entry as its job finishes; an error raised there stops the run, and what
    was finished is kept. Returns one entry per job, in job order: {"id", "kind", "file", "record"}.
    """
    asked = requested(bench.design.data, jobs)

    def written(held):
        write_record(path_of(folder, held["id"]), held)
        return entry(held, file=f"{FOLDER}/{held['id']}.json")

    return collected(each(bench, asked), len(asked), report, written)
