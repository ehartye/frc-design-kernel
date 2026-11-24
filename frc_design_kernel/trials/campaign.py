"""A campaign: every run a design's trials need, counted before it starts, run, and gathered into one record.

For each trial the campaign itself runs the nominal case, the same case at half the step, the control, and the
cheapest sufficient bracket plan (trials.plan). No trial definition and no custom code can leave any of those out.
"""
import copy
import itertools
import math
from contextlib import closing

from ..errors import DesignError
from ..source.load import load
from ..version import generator
from ..workers import EVERY_S, Crew, silent
from . import assumptions, custom, engines, fit, inputs, record
from . import plan as plans_
from .plan import DEFAULT_REFINE, Bracket, Window

SCHEMA = "frc-design-kernel/trial-campaign@3"
PARAMETERS = "parameters."
# Roughly what each engine manages; only used to state a time before running. The 3D figure is for a pickup scene
# with a ring of 48 segments against about 20 solids; a simpler scene runs faster.
STEPS_PER_SECOND = {"planar": 200000, "mujoco": 2000}


def walk(case, path, where):
    """(container, key) for a dotted path into a case. List items are found by their name (a surface by its solid, if unnamed)."""
    node, parts = case, path.split(".")
    for depth, part in enumerate(parts):
        if isinstance(node, list):
            called = [item.get("name", item.get("solid")) if isinstance(item, dict) else None for item in node]
            match = [i for i, name in enumerate(called) if name == part]
            if not match:
                raise DesignError(where, f'the path "{path}" names "{part}", which is not there', f"Known names: {', '.join(str(name) for name in called)}")
            part = match[0]
        elif not isinstance(node, dict) or (part not in node and depth < len(parts) - 1):
            raise DesignError(where, f'the path "{path}" does not lead anywhere at "{part}"', "Write the path as section.name.field, such as materials.tread.friction")
        if depth == len(parts) - 1:
            return node, part
        node = node[part]


KEEPS_NULL = ("busV",)      # fields where null is itself a value: a bus voltage of null is the power off


def changed(case, changes, where):
    """A copy of the case with the changes made to it. A change to null removes the thing, except a field where null is a
    value (a busV of null switches the power off). Parameter changes are not made here."""
    out = copy.deepcopy(case)
    for path, value in changes.items():
        if path.startswith(PARAMETERS):
            continue
        node, key = walk(out, path, where)
        if value is None and key not in KEEPS_NULL:
            del node[key]
        else:
            node[key] = value
    return out


def current_value(design, case, path, where):
    if path.startswith(PARAMETERS):
        return design.data["parameters"][path[len(PARAMETERS):]]
    node, key = walk(case, path, where)
    return inputs.val(node[key])


def method(design, name):
    """A trial's case, its bracket plans and what its method lacks: (case, [Bracket], [missing], physical inputs)."""
    trial, where = design.data["trials"][name], f'trials "{name}"'
    case = inputs.case(design.data, trial)
    found = inputs.physical_inputs(case)
    listed = {entry["input"]: entry for entry in trial.get("brackets", [])}
    refine = int(trial.get("rangeRefine", DEFAULT_REFINE))
    plans = [Bracket(row["path"], row["value"], low_high=row["range"], refine=refine) for row in found if row["source"] == "assumed" and row["path"] not in listed]
    plans += [Bracket(path, current_value(design, case, path, where), entry.get("unit", ""), values=entry["values"]) for path, entry in listed.items()]
    missing = []
    if "control" not in trial:
        missing.append("no control is defined, so nothing shows the trial can fail")
    if not trial.get("assumes"):
        missing.append("the trial does not state its own assumptions (assumes), so a reader cannot tell what it leaves out")
    unstated = [row["path"] for row in found if row["source"] == "unstated"]
    if unstated:
        missing.append("these physical inputs do not say whether they were measured or assumed: " + ", ".join(unstated))
    if not plans:
        missing.append("no input has an assumed range or listed values, so nothing shows how far the inputs can move")
    return case, plans, missing, found


def grid_changes(design, name, case):
    """The opt-in grid: every combination of the range ends of the inputs a trial lists under grid."""
    wanted = design.data["trials"][name].get("grid")
    if not wanted:
        return []
    ranges = {row["path"]: row.get("range") for row in inputs.physical_inputs(case)}
    for path in wanted["inputs"]:
        if not ranges.get(path):
            raise DesignError(f'trials "{name}" grid', f'"{path}" is not an input with an assumed range', f"Inputs with a range: {', '.join(p for p, r in ranges.items() if r)}")
    return [dict(zip(wanted["inputs"], ends)) for ends in itertools.product(*[ranges[path] for path in wanted["inputs"]])]


def label(changes):
    """The run id of a set of changes: the same changes always give the same id."""
    return " & ".join(f"{path} = {value:g}" for path, value in sorted(changes.items()))


def windows_for(design, name, case, plans):
    """{(input path, end value, adjustment name): Window} for each end of each assumed range and each adjustment the trial names."""
    trial, where = design.data["trials"][name], f'trials "{name}"'
    found = {}
    for adjustment in trial.get("adjustments", []):
        entry = design.data["adjustments"][adjustment]
        nominal = current_value(design, case, entry["input"], where)
        for plan in plans:
            if plan.range is not None and plan.path != entry["input"]:
                for end in plan.range:
                    found[plan.path, end, adjustment] = (Window(*entry["range"], nominal, entry.get("step")), nominal)
    return found


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
    """What a campaign may cost before it runs: runs and steps at most, and a rough time.

    The numbers are upper limits: a run that reaches a stop event ends early, and a bracket stops at its first failure.
    """
    trials = design.data["trials"]
    per = {}
    for name in in_order(trials, names or list(trials)):
        case, plans, _, _ = method(design, name)
        runs = 2 + ("control" in trials[name]) + sum(plan.most_runs() for plan in plans) + len(grid_changes(design, name, case))
        runs += sum(window.most_runs() for window, _ in windows_for(design, name, case, plans).values())
        steps = math.ceil(trials[name]["durationS"] / trials[name]["stepS"]) * (runs + 1)
        per[name] = {"runs": runs, "steps": steps, "aboutSeconds": round(steps / STEPS_PER_SECOND[trials[name].get("engine", "planar")], 1)}
    steps = sum(p["steps"] for p in per.values())
    return {"runs": sum(p["runs"] for p in per.values()), "steps": steps, "aboutSeconds": round(sum(p["aboutSeconds"] for p in per.values()), 1), "trials": per}


def most_steps(scene, step):
    """The steps a run takes when no stop event ends it early."""
    return math.ceil(scene["durationS"] / step)


def begin(design):
    """What a process that runs starts with: the function that answers one run, (trial name, scene, step)."""
    def answer(task, meter):
        name, scene, step = task
        most = most_steps(scene, step)
        meter(0, most)
        found = engines.run(scene, step, custom.force_laws(design, design.data["trials"][name]), tick=lambda steps: meter(steps, most))
        meter(found["steps"], most)
        return found
    return answer


class Builder:
    """Builds the design once per set of parameter changes, so a change to a design parameter moves the real geometry."""

    def __init__(self, design, assembly=None):
        self.design, self.built = design, {} if assembly is None else {(): assembly}

    def assembly(self, changes=None):
        overrides = {path[len(PARAMETERS):]: value for path, value in (changes or {}).items() if path.startswith(PARAMETERS)}
        key = tuple(sorted(overrides.items()))
        if key not in self.built:
            from ..builder.assembly import build
            self.built[key] = build(load(self.design.path, overrides, self.design.field) if overrides else self.design)
        return self.built[key]


class Tally:
    """Where a campaign is: the runs done of the most it can take, whole and for the trial running, and each run's step."""

    def __init__(self, cost, progress):
        self.cost, self.progress, self.done, self.of_trial = cost, progress or silent, 0, {}

    def say(self, trial, run_id, process, step, of_steps):
        self.progress({"trial": trial, "run": run_id, "process": process, "step": step, "ofSteps": of_steps,
                       "trialRunsDone": self.of_trial.get(trial, 0), "trialRunsAtMost": self.cost["trials"][trial]["runs"],
                       "runsDone": self.done, "runsAtMost": self.cost["runs"]})

    def finished(self, trial, run_id, process, step, of_steps):
        self.done += 1
        self.of_trial[trial] = self.of_trial.get(trial, 0) + 1
        self.say(trial, run_id, process, step, of_steps)


class Runner:
    """Runs the changed cases of one trial and keeps every result by run id."""

    def __init__(self, name, builder, handed, crew, tally):
        self.name, self.builder, self.handed, self.crew, self.tally = name, builder, handed, crew, tally
        self.where, self.results, self.changes, self.facts = f'trials "{name}"', {}, {}, None

    def run(self, wanted):
        """Run [(run id, changes, halve the step)] that have not been run yet."""
        tasks, ids = [], []
        for run_id, changes, half in wanted:
            if run_id in self.results:
                continue
            assembly = self.builder.assembly(changes)
            case = changed(inputs.case(assembly.data, assembly.data["trials"][self.name]), changes, self.where)
            scene = engines.build(assembly, self.name, case, self.handed)
            self.facts = self.facts or scene["facts"]
            scene.pop("facts")
            tasks.append((self.name, scene, scene["stepS"] / 2 if half else scene["stepS"]))
            ids.append(run_id)
            self.changes[run_id] = changes
        done = [None] * len(tasks)
        with closing(self.crew.ask(tasks, lambda index, process, step, of: self.tally.say(self.name, ids[index], process, step, of))) as given:
            for index, process, found in given:
                done[index] = found
                self.tally.finished(self.name, ids[index], process, found["steps"], most_steps(*tasks[index][1:]))
        self.results.update(zip(ids, done))


def run_summary(run_id, changes, run, met, unmet):
    return {"id": run_id, "changes": changes, "stepS": run["stepS"], "outcome": run["outcome"], "met": met, "firstUnmet": unmet,
            "endS": run["endS"], "steps": run["steps"], "measures": run["measures"], "events": run["events"]}


def cover(design, name, case, plans, runner, met, trial, judge):
    """The coverage campaign: at each end of each assumed range whose outcome changed inside it, the window of each named
    adjustment that passes. An input that held across its range needs no adjustment, so nothing is run for it."""
    flipped = {plan.path for plan in plans if plan.range is not None and not plan.summary()["held"]}
    windows = {key: value for key, value in windows_for(design, name, case, plans).items() if key[0] in flipped}

    def changes_for(key, setting):
        path, end, adjustment = key
        entry = design.data["adjustments"][adjustment]
        return {path: end} if setting == windows[key][1] else {path: end, entry["input"]: setting}

    while True:
        asked = {key: window.ask() for key, (window, _) in windows.items()}
        wanted = [(label(changes_for(key, setting)), changes_for(key, setting), False) for key, settings in asked.items() for setting in settings]
        if not wanted:
            break
        runner.run(wanted)
        for run_id, _, _ in wanted:
            met.setdefault(run_id, record.judge(runner.results[run_id], trial["pass"], judge))
        for key, settings in asked.items():
            windows[key][0].tell({setting: met[label(changes_for(key, setting))][0] for setting in settings})
    rows = []
    for adjustment in trial.get("adjustments", []):
        for plan in plans:
            if plan.range is not None and (plan.path, plan.range[0], adjustment) in windows:
                low, high = (windows[plan.path, end, adjustment][0].summary(end) for end in plan.range)
                rows.append(plans_.coverage(plan.path, adjustment, design.data["adjustments"][adjustment], low, high))
    return rows


def run_trial(design, name, builder, handed, crew, tally):
    """Run one trial's whole method and return its part of the record."""
    trial, where = design.data["trials"][name], f'trials "{name}"'
    case, plans, missing, found = method(design, name)
    runner = Runner(name, builder, handed, crew, tally)
    judge = custom.criterion(design, trial)
    met = {}
    grid = [(label(combo), combo, False) for combo in grid_changes(design, name, case)]
    first = [("nominal", {}, False), ("half step", {}, True)] + ([("control", trial["control"]["change"], False)] if "control" in trial else []) + grid
    wanted = first + [(label({plan.path: value}), {plan.path: value}, False) for plan in plans for value in plan.ask()]
    while wanted:
        runner.run(wanted)
        for run_id, _, _ in wanted:
            met[run_id] = record.judge(runner.results[run_id], trial["pass"], judge)
        for plan in plans:
            plan.nominal_met = met["nominal"][0]
            for value in plan.ask():
                run_id = label({plan.path: value})
                if run_id in met:
                    plan.tell(value, met[run_id][0], runner.results[run_id]["outcome"], runner.results[run_id]["measures"], run_id)
        wanted = [(label({plan.path: value}), {plan.path: value}, False) for plan in plans for value in plan.ask()]
    covered = cover(design, name, case, plans, runner, met, trial, judge)
    results, nominal = runner.results, runner.results["nominal"]
    steps = record.step_comparison(nominal, results["half step"], met["nominal"][0], met["half step"][0])
    control = None
    if "control" in trial:
        control = {"note": trial["control"]["note"], "change": trial["control"]["change"], "outcome": results["control"]["outcome"],
                   "met": met["control"][0], "rejected": not met["control"][0], "firstUnmet": met["control"][1]}
    ranges = [plan.summary() for plan in plans]
    grid_found = None
    if grid:
        rows = [{"values": combo, "met": met[run_id][0], "outcome": results[run_id]["outcome"]} for run_id, combo, _ in grid]
        grid_found = {"inputs": trial["grid"]["inputs"], "runs": rows, "allMet": all(row["met"] == met["nominal"][0] for row in rows)}
    word, findings = record.result(met["nominal"][0], control, ranges, steps, missing, grid_found, covered)
    touched = sorted({solid for run in results.values() for solid in run.get("touchedRough", [])})     # only the 3D engine hulls
    if touched:     # a filled-in shape was part of what happened, so the outcome may rest on a surface that is not there
        word += ", on a hulled surface"
        findings.append("the piece touched a part of a solid that was taken as its convex hull, which fills in its hollows and cuts: " + ", ".join(touched))
    stated, standing = assumptions.stated(trial)
    ranking = record.sensitivity(ranges, nominal["measures"])
    return {"engine": engines.stamp(trial.get("engine", "planar")),
            "definition": case, "assumptions": {"stated": stated, "engine": standing}, "inputs": found, "saw": runner.facts,
            "result": word, "findings": findings, "touchedHulled": touched, "firstUnmet": met["nominal"][1],
            "nominal": {**run_summary("nominal", {}, nominal, *met["nominal"]), "end": nominal["end"], "trace": nominal["trace"], "contacts": nominal["contacts"]},
            "stepComparison": steps, "control": control, "ranges": ranges, "coverage": covered, "grid": grid_found, "sensitivity": ranking,
            "handForward": record.hand_forward(found, ranges, ranking, control, stated + standing, covered),
            "runs": [run_summary(run_id, runner.changes[run_id], results[run_id], *met[run_id]) for run_id in results],
            "fit": fit.path_operation(nominal["trace"], trial["plane"], trial.get("fitToleranceMm", 10.0))}


def run_campaign(design, names=None, max_steps=None, workers=1, announce=None, report=None, progress=None, every_s=EVERY_S, assembly=None):
    """Run the trials of a loaded design (those named, and any they start after) and return the campaign record.

    The cost is counted first and passed to announce (a function taking the estimate) before anything runs. With
    max_steps, a campaign whose estimate is larger is refused. workers shares the runs between processes. report, when
    given, hears each trial's name and its part of the record as it finishes; an error raised there stops the
    campaign. progress hears where the campaign is, at most every every_s seconds from each process: {"trial", "run",
    "process", "step", "ofSteps", "trialRunsDone", "trialRunsAtMost", "runsDone", "runsAtMost"}. assembly is the design
    as built, when the caller has it. A trial that starts after another runs from the end that one reached in this
    campaign, never from a saved record.
    """
    cost = estimate(design, names)
    if announce:
        announce(cost)
    if max_steps is not None and cost["steps"] > max_steps:
        raise DesignError("", f'the campaign needs up to {cost["steps"]} steps in up to {cost["runs"]} runs, over the cap of {max_steps}',
                          "Raise the cap, shorten a trial, use a larger step or narrow what is bracketed")
    builder, tally, handed, records = Builder(design, assembly), Tally(cost, progress), {}, {}
    with Crew(begin, (design,), workers, every_s) as crew:
        for name in cost["trials"]:
            before = design.data["trials"][name]["piece"]["start"].get("after")
            records[name] = run_trial(design, name, builder, handed.get(before), crew, tally)
            handed[name] = records[name]["nominal"]["end"]
            if report:
                report(name, records[name])
    return {"schema": SCHEMA, "generator": generator(), "design": {"name": design.data["name"], "source": design.path.name},
            "cost": {"runsAtMost": cost["runs"], "stepsAtMost": cost["steps"], "runs": sum(len(t["runs"]) for t in records.values()),
                     "stepsRun": sum(r["steps"] for t in records.values() for r in t["runs"])},
            "custom": custom.report(design, list(records)), "trials": records}
