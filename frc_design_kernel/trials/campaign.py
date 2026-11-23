"""A campaign: every run a design's trials need, counted before it starts, run, and gathered into one record.

For each trial the campaign itself runs the nominal case, the same case at half the step, the control, and one run
per bracket value. No trial definition and no custom code can leave any of those out.
"""
import copy
import math
from concurrent.futures import ProcessPoolExecutor

from ..errors import DesignError
from ..source.load import load
from ..version import generator
from . import custom, fit, planar, record, scene as scenes

SCHEMA = "frc-design-kernel/trial-campaign@1"
PARAMETERS = "parameters."


def walk(trial, path, where):
    """(container, key) for a dotted path into a trial. List items are found by their name."""
    node, parts = trial, path.split(".")
    for depth, part in enumerate(parts):
        if isinstance(node, list):
            match = [i for i, item in enumerate(node) if isinstance(item, dict) and item.get("name") == part]
            if not match:
                raise DesignError(where, f'the path "{path}" names "{part}", which is not there', f"Known names: {', '.join(str(i.get('name')) for i in node)}")
            part = match[0]
        elif not isinstance(node, dict) or (part not in node and depth < len(parts) - 1):
            raise DesignError(where, f'the path "{path}" does not lead anywhere at "{part}"', "Write the path as section.name.field, such as materials.tread.friction")
        if depth == len(parts) - 1:
            return node, part
        node = node[part]


def changed(trial, changes, where):
    """(a copy of the trial with the changes made, design parameter overrides). A change to null removes the thing."""
    out, overrides = copy.deepcopy(trial), {}
    for path, value in changes.items():
        if path.startswith(PARAMETERS):
            overrides[path[len(PARAMETERS):]] = value
            continue
        node, key = walk(out, path, where)
        if value is None:
            del node[key]
        else:
            node[key] = value
    return out, overrides


def nominal_value(design, trial, path, where):
    if path.startswith(PARAMETERS):
        return design.data["parameters"][path[len(PARAMETERS):]]
    node, key = walk(trial, path, where)
    return node[key]


def planned_runs(design, name):
    """The runs one trial needs: [(run id, changes, halve the step)]."""
    trial, where = design.data["trials"][name], f'trials "{name}"'
    runs = [("nominal", {}, False), ("half step", {}, True)]
    if "control" in trial:
        runs.append(("control", trial["control"]["change"], False))
    for entry in trial.get("brackets", []):
        nominal = nominal_value(design, trial, entry["input"], where)
        runs += [(f'{entry["input"]} = {value:g}', {entry["input"]: value}, False) for value in entry["values"] if value != nominal]
    return runs


def in_order(trials, names):
    """The named trials and the ones they start after, each after the one it needs."""
    ordered = []

    def add(name):
        before = trials[name]["piece"]["start"].get("after")
        if before:
            add(before)
        if name not in ordered:
            ordered.append(name)

    for name in names:
        if name not in trials:
            raise DesignError("", f'there is no trial named "{name}"', f"Known trials: {', '.join(trials) or 'none'}")
        add(name)
    return ordered


def estimate(design, names=None):
    """What a campaign will cost before it runs: {"runs": n, "steps": n, "trials": {name: {"runs", "steps"}}}.

    steps is an upper limit: a run that reaches a stop event ends early.
    """
    trials = design.data["trials"]
    per = {}
    for name in in_order(trials, names or list(trials)):
        runs = planned_runs(design, name)
        steps = sum(math.ceil(trials[name]["durationS"] / trials[name]["stepS"]) * (2 if half else 1) for _, _, half in runs)
        per[name] = {"runs": len(runs), "steps": steps}
    return {"runs": sum(p["runs"] for p in per.values()), "steps": sum(p["steps"] for p in per.values()), "trials": per}


def execute(task):
    """One run, in this process or a worker: (source path, trial name, run id, scene, step)."""
    source, name, run_id, scene, step = task
    design = load(source)
    return planar.run(scene, step, custom.force_laws(design, design.data["trials"][name]))


class Builder:
    """Builds the design once per set of parameter changes, so a bracket on a design parameter moves the real geometry."""

    def __init__(self, source):
        self.source, self.built = source, {}

    def assembly(self, overrides):
        key = tuple(sorted(overrides.items()))
        if key not in self.built:
            from ..builder.assembly import build
            self.built[key] = build(load(self.source, overrides or None))
        return self.built[key]


def run_summary(run_id, changes, run, met, unmet):
    return {"id": run_id, "changes": changes, "stepS": run["stepS"], "outcome": run["outcome"], "met": met, "firstUnmet": unmet,
            "endS": run["endS"], "steps": run["steps"], "measures": run["measures"], "events": run["events"]}


def trial_record(design, name, runs, results):
    """One trial's part of the record, from its runs and their results."""
    trial, where = design.data["trials"][name], f'trials "{name}"'
    judge = custom.criterion(design, trial)
    met = {run_id: record.judge(results[run_id], trial["pass"], judge) for run_id, _, _ in runs}
    steps = record.step_comparison(results["nominal"], results["half step"], met["nominal"][0], met["half step"][0])
    control = None
    if "control" in trial:
        control = {"note": trial["control"]["note"], "change": trial["control"]["change"], "outcome": results["control"]["outcome"],
                   "met": met["control"][0], "rejected": not met["control"][0], "firstUnmet": met["control"][1]}
    brackets = []
    for entry in trial.get("brackets", []):
        nominal = nominal_value(design, trial, entry["input"], where)
        rows = []
        for value in entry["values"]:
            run_id = "nominal" if value == nominal else f'{entry["input"]} = {value:g}'
            rows.append({"value": value, "passed": met[run_id][0], "outcome": results[run_id]["outcome"], "run": run_id})
        brackets.append(record.bracket(entry, nominal, rows))
    word, findings = record.result(met["nominal"][0], control, brackets, steps)
    nominal = results["nominal"]
    return {"definition": trial, "result": word, "findings": findings, "firstUnmet": met["nominal"][1],
            "nominal": {**run_summary("nominal", {}, nominal, *met["nominal"]), "end": nominal["end"], "trace": nominal["trace"], "contacts": nominal["contacts"]},
            "stepComparison": steps, "control": control, "brackets": brackets,
            "runs": [run_summary(run_id, changes, results[run_id], *met[run_id]) for run_id, changes, _ in runs],
            "fit": fit.path_operation(nominal["trace"], trial["plane"], trial.get("fitToleranceMm", 10.0))}


def run_campaign(source, names=None, max_steps=None, workers=1, announce=None):
    """Run the trials of a design source and return the campaign record.

    The cost is counted first and passed to announce (a function taking the estimate) before anything runs. With
    max_steps, a campaign whose estimate is larger is refused. workers shares the runs between processes.
    """
    design = load(source)
    cost = estimate(design, names)
    if announce:
        announce(cost)
    if max_steps is not None and cost["steps"] > max_steps:
        raise DesignError("", f'the campaign needs up to {cost["steps"]} steps in {cost["runs"]} runs, over the cap of {max_steps}',
                          "Raise the cap, shorten a trial, use a larger step or trim the brackets")
    builder, handed, records = Builder(source), {}, {}
    for name in cost["trials"]:
        trial, where = design.data["trials"][name], f'trials "{name}"'
        runs = planned_runs(design, name)
        tasks = []
        for run_id, changes, half in runs:
            variant, overrides = changed(trial, changes, where)
            scene = scenes.build(builder.assembly(overrides), name, variant, handed.get(trial["piece"]["start"].get("after")))
            tasks.append((str(source), name, run_id, scene, scene["stepS"] / 2 if half else scene["stepS"]))
        if workers > 1 and len(tasks) > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                done = list(pool.map(execute, tasks))
        else:
            done = [execute(task) for task in tasks]
        results = {run_id: result for (run_id, _, _), result in zip(runs, done)}
        handed[name] = results["nominal"]["end"]["piece"]
        records[name] = trial_record(design, name, runs, results)
    return {"schema": SCHEMA, "generator": generator(), "design": {"name": design.data["name"], "source": design.path.name, "sourceSha256": design.sha256},
            "cost": {"runs": cost["runs"], "steps": cost["steps"], "stepsRun": sum(r["steps"] for t in records.values() for r in t["runs"])},
            "custom": custom.report(design, list(records)), "trials": records}
