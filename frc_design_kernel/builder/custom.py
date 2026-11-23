"""The escape hatch: load, call and check registered custom code. The contracts are in DESIGN.md sections 6 and 13.

A custom shape builds one solid. Custom trial code (a force law or a pass criterion) is loaded through the same
narrow door: one known folder, a fixed function name, limited imports, and a report row for the record.
"""
import ast
import hashlib
import importlib.util

from ..errors import DesignError
from .shape import one_solid

ALLOWED_IMPORTS = ("math", "OCP", "frc_design_kernel")
REFUSED_NAMES = ("open", "exec", "eval", "compile", "input", "__import__", "globals", "breakpoint")


def refused(tree, entry="build", allowed=ALLOWED_IMPORTS):
    """The first thing in a custom code file that breaks the contract, as text, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            return "uses a relative import"
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) else []
        for name in names:
            if name.split(".")[0] not in allowed:
                return f'imports "{name}"'
        if isinstance(node, ast.Name) and node.id in REFUSED_NAMES:
            return f'uses "{node.id}"'
    if not any(isinstance(node, ast.FunctionDef) and node.name == entry for node in tree.body):
        return f"has no {entry}(...) function"
    return None


def load_function(design, name, entry="build", allowed=ALLOWED_IMPORTS, what="custom shape"):
    """(function, source text, path) for the registered custom code name, refused before it runs if it breaks the contract."""
    path = design.custom_file(name)
    where = f'custom "{name}"'
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as problem:
        raise DesignError(where, f"its code has a syntax error on line {problem.lineno}", "Fix the Python in the file") from None
    problem = refused(tree, entry, allowed)
    if problem:
        raise DesignError(where, f"its code {problem}, which a {what} may not do",
                          f"A {what} may import only {', '.join(allowed)}, must define {entry}(...), and does nothing else")
    spec = importlib.util.spec_from_file_location(f"frc_design_kernel_custom_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, entry), text, path


def report_row(design, name, text, path, used_by):
    """The record of one piece of custom code: where it is, how long it is, and why it exists."""
    entry = design.data["custom"][name]
    return {"name": name, "kind": entry.get("kind", "shape"), "file": path.relative_to(design.folder).as_posix(), "lines": len(text.splitlines()),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "reason": entry["reason"], "limits": entry["limits"],
            "usedBy": sorted(used_by)}


class CustomShapes:
    """The custom shapes of one design: loads each file once, builds on request and reports what was used."""

    def __init__(self, design):
        self.design = design
        self.loaded = {}

    def load(self, name):
        if name not in self.loaded:
            self.loaded[name] = load_function(self.design, name)
        return self.loaded[name]

    def build(self, name, parameters, where):
        """One checked solid from the custom shape name, given its parameters."""
        function = self.load(name)[0]
        try:
            shape = function(dict(parameters))
        except Exception as problem:
            raise DesignError(where, f'the custom shape "{name}" failed ({type(problem).__name__}: {problem})', "Fix its code or its parameters") from None
        if not hasattr(shape, "ShapeType"):
            raise DesignError(where, f'the custom shape "{name}" returned {type(shape).__name__}, not a shape', "Return exactly one solid from build(parameters)")
        return one_solid(shape, where, f'The custom shape "{name}"')

    def report(self):
        """One manifest row per custom shape used."""
        return [report_row(self.design, name, self.loaded[name][1], self.loaded[name][2], self.design.custom_used.get(name, []))
                for name in sorted(self.loaded)]
