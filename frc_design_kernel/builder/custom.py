"""The escape hatch: load, call and check a registered custom shape. The contract is in DESIGN.md section 6."""
import ast
import hashlib
import importlib.util

from ..errors import DesignError
from .shape import one_solid

ALLOWED_IMPORTS = ("math", "OCP", "frc_design_kernel")
REFUSED_NAMES = ("open", "exec", "eval", "compile", "input", "__import__", "globals", "breakpoint")


def refused(tree):
    """The first thing in a custom shape file that breaks the contract, as text, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            return "uses a relative import"
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) else []
        for name in names:
            if name.split(".")[0] not in ALLOWED_IMPORTS:
                return f'imports "{name}"'
        if isinstance(node, ast.Name) and node.id in REFUSED_NAMES:
            return f'uses "{node.id}"'
    if not any(isinstance(node, ast.FunctionDef) and node.name == "build" for node in tree.body):
        return "has no build(parameters) function"
    return None


class CustomShapes:
    """The custom shapes of one design: loads each file once, builds on request and reports what was used."""

    def __init__(self, design):
        self.design = design
        self.loaded = {}

    def load(self, name):
        if name in self.loaded:
            return self.loaded[name]
        path = self.design.custom_file(name)
        where = f'custom "{name}"'
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError as problem:
            raise DesignError(where, f"its code has a syntax error on line {problem.lineno}", "Fix the Python in the file") from None
        problem = refused(tree)
        if problem:
            raise DesignError(where, f"its code {problem}, which a custom shape may not do",
                              f"A custom shape may import only {', '.join(ALLOWED_IMPORTS)}, must define build(parameters), and only makes a shape")
        spec = importlib.util.spec_from_file_location(f"frc_design_kernel_custom_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.loaded[name] = (module.build, text, path)
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
        """One manifest row per custom shape used: where its code is, how long it is, and why it exists."""
        rows = []
        for name in sorted(self.loaded):
            _, text, path = self.loaded[name]
            entry = self.design.data["custom"][name]
            rows.append({"name": name, "file": path.relative_to(self.design.folder).as_posix(), "lines": len(text.splitlines()),
                         "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "reason": entry["reason"], "limits": entry["limits"],
                         "usedBy": sorted(self.design.custom_used.get(name, []))})
        return rows
