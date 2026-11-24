"""The measurement records: one file per job, DIR/measurements/<job id>.json, written whole as each job finishes.

record() answers a list of jobs (see jobs). A job whose file is current, meaning its job, its inputs and its used
block are what the design gives now, is carried: not measured and not written again. Every other job is measured,
carrying from its earlier file what it can, and its file is replaced the moment the job finishes. So a stopped run
keeps every job it finished, and the next run measures only the rest. check() says the same without measuring.
"""
import contextlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import DesignError
from ..version import generator
from . import carry, clearance, jobs as kinds, run, summary

SCHEMA = "frc-design-kernel/measurement-job@1"
FOLDER = "measurements"


def path_of(folder, name):
    return Path(folder) / FOLDER / f"{name}.json"


def read_record(path):
    """A job record, None when there is none, or {} for a file that is not a job record in this format."""
    if not path.is_file():
        return None
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return held if isinstance(held, dict) and held.get("schema") == SCHEMA else {}


def write_record(path, record):
    """Write a job record whole or not at all: into a temporary file beside it, then moved into its place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def requested(data, jobs):
    """[(id, normalized job)] for a list of jobs; refuses an unknown kind or field, a missing name, or two jobs with one id."""
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
        out.append((name, found))
    return out


def shown(value):
    return json.dumps(value) if not isinstance(value, str) else value


def table_changes(what, old, new):
    found = []
    for name in sorted(set(old) | set(new)):
        if name not in new:
            found.append(f'{what} "{name}" is no longer there')
        elif name not in old:
            found.append(f'{what} "{name}" is new')
        elif carry.plain(old[name]) != carry.plain(new[name]):
            found.append(f'{what} "{name}" changed' + ("" if what == "solid" else f": {shown(old[name])} to {shown(new[name])}"))
    return found


def changes(held, job, inputs, used):
    """What differs between a stored job record and the job as the design gives it now, as plain statements; [] when current."""
    before = held.get("job") or {}
    found = [f"the job's {key} changed: {shown(before.get(key))} to {shown(job.get(key))}"
             for key in sorted(set(before) | set(job)) if carry.plain(before.get(key)) != carry.plain(job.get(key))]
    if found:
        return found
    if carry.plain(held["inputs"]["rules"]) != carry.plain(inputs["rules"]):
        found.append("the rules changed")
    found += table_changes("solid", held["inputs"]["solids"], inputs["solids"])
    for key in sorted(set(held["used"]) | set(used)):
        old, new = held["used"].get(key), used.get(key)
        if carry.plain(old) != carry.plain(new):
            found += table_changes(key, old, new) if isinstance(old, dict) and isinstance(new, dict) else [f"{key} changed"]
    if (held.get("checked") or {}).get("pairsNotMeasured"):
        found.append("only part of it was measured (a focus)")
    return found


def drawn(assembly, job, name):
    """(inputs, used) of a job asked for, with a problem in it named by the job's id."""
    try:
        return kinds.drawn_on(assembly, job)
    except DesignError as problem:
        raise problem.under(f'job "{name}"') from None


def state_row(name, job, state, found):
    return {"record": name, "kind": job["kind"], "file": f"{FOLDER}/{name}.json", "state": state, "changes": found}


def check(source, jobs, folder):
    """For each job asked, whether its record in folder is current, stale (and why) or missing. Measures nothing."""
    from ..builder.assembly import build
    from ..source.load import load
    assembly, rows = build(load(source)), []
    for name, job in requested(assembly.data, jobs):
        held = read_record(path_of(folder, name))
        found = ["there is no record"] if held is None else [f"it is not a {SCHEMA} record"] if not held else changes(held, job, *drawn(assembly, job, name))
        rows.append(state_row(name, job, "missing" if held is None else "stale" if found else "current", found))
    return rows


def stored(assembly, folder):
    """For every job record in folder, whether it is current for the design as built now, or stale and why."""
    data, rows = assembly.data, []
    for path in sorted((Path(folder) / FOLDER).glob("*.json")):
        held, name = read_record(path), path.stem
        job = held.get("job") or {"kind": None}
        target = "motion" if "motion" in job else "pose"
        if not held:
            found = [f"it is not a {SCHEMA} record"]
        elif job.get(target) is not None and job[target] not in data[f"{target}s"]:
            found = [f'the {target} "{job[target]}" is no longer in the source']
        else:
            try:
                found = changes(held, job, *kinds.drawn_on(assembly, job))
            except DesignError as problem:
                found = [problem.problem]
        rows.append(state_row(name, job, "stale" if found else "current", found))
    return rows


@dataclass
class Pending:
    """A job to be measured: what it is, what it draws on, its tasks, and the answers back so far."""
    index: int
    name: str
    job: dict
    inputs: dict
    used: dict
    tasks: list = field(default_factory=list)
    parts: dict = field(default_factory=dict)
    shared: tuple = None        # for a clearance along a motion: (solids present, contact pairs, the carry plan)


def planned(source, assembly, item, earlier, focus, workers):
    """Cut a job into its tasks: shares for a clearance along a motion, one task for any other kind."""
    job = {key: value for key, value in item.job.items() if key != "id"}
    contacts = item.used.get("contacts")
    if job["kind"] == "clearance" and "motion" in job:
        names = tuple(kinds.present(assembly, job))
        pairs = clearance.declared(contacts, set(names))
        chosen = carry.plan(earlier, item.inputs, pairs, focus, earlier is not None)
        item.shared = (names, pairs, chosen)
        sent = dict(job, contacts=contacts, plan=chosen.job(), inputsKnown=True)
        count = 0 if chosen.counts is not None else run.shares_for(len(names), workers)
        item.tasks = [(str(source), sent, (first, count)) for first in range(count)]
    else:
        sent = dict(job, earlier=earlier, focus=focus, **({"contacts": contacts} if contacts is not None else {}))
        item.tasks = [(str(source), sent, None)]


def answered(item):
    """The job's answer from its tasks' answers."""
    if item.shared is None:
        return item.parts[0]
    names, pairs, chosen = item.shared
    job = item.job
    head = clearance.header("motion", job["motion"], job["minGapMm"], job["depth"], pairs, job["absent"], job["includeStill"], job["displace"] or None)
    parts = [item.parts[index] for index in sorted(item.parts)]
    return clearance.finished([carry.carried_part(names, chosen), *parts], head, item.inputs, chosen)


def written(folder, item, made):
    """Store a finished job's record, and return it."""
    checked, counts, result = kinds.finish(item.job, answered(item))
    record = {"schema": SCHEMA, "generator": made, "id": item.name, "job": item.job, "inputs": item.inputs, "used": item.used,
              "checked": checked, **({"counts": counts} if counts is not None else {}), "result": result}
    write_record(path_of(folder, item.name), record)
    return record


def record(source, jobs, folder, workers=None, carry=True, focus=None, report=None):
    """Answer jobs about a design source and keep each answer as its own file in folder/measurements, written as it finishes.

    With carry, a job whose file is current is carried as it is, and every other job carries from its file what it
    can; without it every job is measured afresh. focus names solids whose clearance pairs are measured again even
    so (without carry, only those, and the record says so). report, when given, is called with each entry as its job
    is carried or finished. Returns one entry per job, in job order: {"id", "kind", "action": "carried" | "measured",
    "file", "record"}.
    """
    workers = run.default_workers() if workers is None else max(1, int(workers))
    assembly = run.assembly_for(source)
    focus = summary.known_solids(assembly, focus)
    asked, pending, made = requested(assembly.data, jobs), [], generator()
    entries = [None] * len(asked)
    (Path(folder) / FOLDER).mkdir(parents=True, exist_ok=True)

    def done(index, name, job, action, held):
        entries[index] = {"id": name, "kind": job["kind"], "action": action, "file": f"{FOLDER}/{name}.json", "record": held}
        if report:
            report(entries[index])

    for index, (name, job) in enumerate(asked):
        inputs, used = drawn(assembly, job, name)
        held = (read_record(path_of(folder, name)) or None) if carry else None
        if held is not None and not (focus and job["kind"] == "clearance") and not changes(held, job, inputs, used):
            done(index, name, job, "carried", held)
            continue
        item = Pending(index, name, job, inputs, used)
        same = held is not None and held["job"]["kind"] == job["kind"]
        earlier = kinds.earlier_form(held) if same else ({} if carry and job["kind"] == "clearance" else None)
        planned(source, assembly, item, earlier, focus, workers)
        pending.append(item)
    for item in [item for item in pending if not item.tasks]:
        done(item.index, item.name, item.job, "measured", written(folder, item, made))
    tasks, owners = [], []
    for item in pending:
        for slot, task in enumerate(item.tasks):
            owners.append((item, slot))
            tasks.append(task)
    with contextlib.closing(run.completed(tasks, workers)) as answers:
        for index, part in answers:
            item, slot = owners[index]
            item.parts[slot] = part
            if len(item.parts) == len(item.tasks):
                done(item.index, item.name, item.job, "measured", written(folder, item, made))
    return entries
