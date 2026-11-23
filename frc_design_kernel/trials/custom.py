"""Custom trial code: a force law or a pass criterion. The same narrow door as custom shapes (DESIGN.md section 13).

    force law    custom/<name>.py defines force(signals, parameters) and returns (fx, fz, torque) on the piece, in
                 newtons and newton metres. signals is the run's current signals by name.
    criterion    custom/<name>.py defines judge(run, parameters) and returns True or False. run holds the outcome,
                 end time, events, measures and end state of one run.

Custom trial code may import only math. It cannot replace the control, the brackets or the half-step repeat, and it
never writes the record: the campaign does all four around it.
"""
from ..builder.custom import load_function, report_row

ALLOWED = ("math",)
ENTRY = {"force": "force", "criterion": "judge"}


def load(design, name, kind):
    """The custom function of one kind, checked before it runs."""
    return load_function(design, name, ENTRY[kind], ALLOWED, f"custom {kind}")[0]


def force_laws(design, trial):
    """[(function, parameters)] for the force laws a trial uses."""
    return [(load(design, use["use"], "force"), dict(use.get("parameters", {}))) for use in trial.get("forces", [])]


def criterion(design, trial):
    """(function, parameters) for a trial's custom criterion, or None."""
    use = trial["pass"].get("custom")
    return None if use is None else (load(design, use["use"], "criterion"), dict(use.get("parameters", {})))


def report(design, names):
    """Record rows for the custom trial code used by the named trials."""
    used = {}
    for trial in names:
        entry = design.data["trials"][trial]
        for use in [*entry.get("forces", []), *([entry["pass"]["custom"]] if "custom" in entry["pass"] else [])]:
            used.setdefault(use["use"], []).append(f"trial {trial}")
    rows = []
    for name in sorted(used):
        kind = design.data["custom"][name].get("kind", "shape")
        _, text, path = load_function(design, name, ENTRY[kind], ALLOWED, f"custom {kind}")
        rows.append(report_row(design, name, text, path, used[name]))
    return rows
