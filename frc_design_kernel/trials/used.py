"""What a trial's answer rests on, with enough of each thing's identity to tell later whether it changed.

No name, note or file byte is kept where the thing itself can be: a solid by its shape figures and where it stands, a
start by where it is, custom code by what it does. The status command works the same out from the source as it is now
and compares.
"""
import ast
import copy
import hashlib

from ..builder import identity, placement
from ..builder.custom import refused
from ..errors import DesignError
from ..measure import carry
from ..source.uses import parameters_used
from . import custom, frames, inputs

PARAMETERS = "parameters."
ADJUSTMENT = ("input", "kind", "range", "step")
WITH_DOCSTRING = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def unnamed(case):
    """A trial's case without the name of the trial it starts after: where that one ends is kept as the start."""
    found = copy.deepcopy(case)
    if "after" in found["piece"]["start"]:
        found["piece"]["start"]["after"] = True
    return found


def start_used(case, handed):
    """The resolved values a trial starts from when it starts where another ended, or None."""
    start = case["piece"]["start"]
    if "after" not in start or handed is None:
        return None
    found = {"piece": list(handed["piece"][:2] if start.get("atRest", True) else handed["piece"])}
    if start.get("carryDrives"):
        found["drives"] = {name: speed for name, speed in sorted(handed.get("drives", {}).items()) if name in case["drives"]}
    return found


def docstring(line):
    return isinstance(line, ast.Expr) and isinstance(line.value, ast.Constant) and isinstance(line.value.value, str)


def said(node):
    """A piece of parsed code as plain data: its kinds of node and their values. Positions, docstrings and fields left
    empty are not in it, so the same code reads the same whatever its layout or the Python version."""
    if isinstance(node, ast.AST):
        found = {}
        for name, value in ast.iter_fields(node):
            if name == "body" and isinstance(node, WITH_DOCSTRING):
                value = [line for line in value if not docstring(line)]
            if value is not None and value != [] and not (isinstance(node, ast.Constant) and name == "kind"):
                found[name] = said(value)
        return [type(node).__name__, found]
    return [said(item) for item in node] if isinstance(node, list) else [type(node).__name__, repr(node)]


def code_identity(design, name):
    """A digest of what custom trial code does. It may import only math and none of the project's files, so its own file
    is all of it; code that breaks that contract has no identity and is refused by name."""
    kind = design.data["custom"][name].get("kind", "shape")
    where = f'custom "{name}"'
    try:
        tree = ast.parse(design.custom_file(name).read_text(encoding="utf-8"))
    except SyntaxError as problem:
        raise DesignError(where, f"its code has a syntax error on line {problem.lineno}", "Fix the Python in the file") from None
    problem = refused(tree, custom.ENTRY[kind], custom.ALLOWED)
    if problem:
        raise DesignError(where, f"its code {problem}, which a custom {kind} may not do", f"It may import only {', '.join(custom.ALLOWED)}")
    return hashlib.sha256(repr(said(tree)).encode("utf-8")).hexdigest()[:16]


def custom_names(trial):
    """The custom code a trial runs: its forces and its criterion."""
    return sorted({use["use"] for use in [*trial.get("forces", []), *([trial["pass"]["custom"]] if "custom" in trial["pass"] else [])]})


def followed(case):
    """The motions a trial's movers follow."""
    return sorted({entry["motion"] for entry in case.get("movers", {}).values() if "motion" in entry})


def standing(assembly, case, solids):
    """{solid: identity} of each solid where it stands at the trial's pose: its shape figures and its whole placement."""
    found = carry.at_pose(assembly, case.get("pose"))
    return {solid: found[solid] for solid in solids}


def framed(assembly, name, case):
    """A digest of where a trial's frames are, or None for a trial with none."""
    return carry.digest(frames.build(case, assembly.data, f'trials "{name}"')) if case.get("frames") else None


def ends_of(changes):
    """{parameter path: [lowest, highest]} over the changes a trial's runs made to design parameters."""
    found = {}
    for change in changes:
        for path, value in change.items():
            if path.startswith(PARAMETERS) and value is not None:
                low, high = found.get(path, (value, value))
                found[path] = [min(low, value), max(high, value)]
    return found


def varied(name, solids, ends, built):
    """{parameter path: {setting: digest}}: what the trial takes from the design at the ends of each parameter it varied.
    A solid that stops following a parameter changes nothing as drawn, and everything the variation showed."""
    found = {}
    for path, settings in sorted(ends.items()):
        for value in sorted(set(settings)):
            assembly = built({path[len(PARAMETERS):]: value})
            case = inputs.case(assembly.data, assembly.data["trials"][name])
            taken = [standing(assembly, case, solids), [placement.motion_stages(assembly.data, motion) for motion in followed(case)], framed(assembly, name, case), unnamed(case)]
            found.setdefault(path, {})[f"{value:.12g}"] = carry.digest(taken)
    return found


def adjusted(data, trial):
    """The adjustments a trial names: what each changes, and the range that can cover the trial."""
    rows = {name: data["adjustments"][name] for name in sorted(trial.get("adjustments", []))}
    return {name: {field: entry[field] for field in ADJUSTMENT if field in entry} for name, entry in rows.items()}


def what_it_used(design, assembly, name, case, facts, handed, ends, built):
    """Everything a trial drew on. handed is the end of the trial it starts after; ends and built give what it varied."""
    raw, data, trial = design.raw, design.data, design.data["trials"][name]
    written = [raw["trials"][name]] + [raw.get(table, {}).get(key) for table in inputs.TABLES for key in case[table]]
    pose, solids = case.get("pose"), sorted({row["solid"] for row in facts["sections"]})
    return {"solids": identity.solids(assembly, solids), "standing": standing(assembly, case, solids),
            "pose": pose, "poseOperations": data["poses"].get(pose) if pose else None,
            "motions": {key: carry.plain(placement.motion_stages(data, key)) for key in followed(case)}, "frames": framed(assembly, name, case),
            "parameters": {key: data["parameters"][key] for key in parameters_used(raw, written)},
            "tables": {table: sorted(case[table]) for table in inputs.TABLES},
            "start": start_used(case, handed), "custom": {code: code_identity(design, code) for code in custom_names(trial)},
            "adjustments": adjusted(data, trial), "varied": varied(name, solids, ends, built)}
