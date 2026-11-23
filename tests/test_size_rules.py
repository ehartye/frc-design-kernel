"""The lean rules: module and function size ceilings, and no circular imports."""
import ast
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "frc_design_kernel"
MAX_MODULE_LINES = 600
MAX_FUNCTION_LINES = 120


def long_modules(root, limit=MAX_MODULE_LINES):
    rows = [(len(p.read_text(encoding="utf-8").splitlines()), p.relative_to(root).as_posix()) for p in sorted(root.rglob("*.py"))]
    return [f"{name}: {lines} lines" for lines, name in rows if lines > limit]


def long_functions(root, limit=MAX_FUNCTION_LINES):
    found = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines = node.end_lineno - node.lineno + 1
                if lines > limit:
                    found.append(f"{path.relative_to(root).as_posix()}: {node.name} is {lines} lines")
    return found


def module_name(root, path):
    parts = [root.name, *path.relative_to(root).with_suffix("").parts]
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def import_graph(root):
    """{module: set of modules in the package that it imports}, from every import statement in the file."""
    files = {module_name(root, p): p for p in root.rglob("*.py")}
    graph = {name: set() for name in files}
    for name, path in files.items():
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = package.split(".")[:len(package.split(".")) - node.level + 1] if node.level else []
                stem = ".".join([*base, *([node.module] if node.module else [])])
                targets = [stem, *[f"{stem}.{a.name}" for a in node.names]]
            graph[name].update(t for t in targets if t in files and t != name)
    return graph


def cycles(graph):
    """Every import circle, as a list of module names that ends where it starts."""
    found, state = [], {}

    def visit(node, trail):
        state[node] = "open"
        for nxt in sorted(graph[node]):
            if state.get(nxt) == "open":
                found.append(trail[trail.index(nxt):] + [nxt])
            elif nxt not in state:
                visit(nxt, trail + [nxt])
        state[node] = "done"

    for start in sorted(graph):
        if start not in state:
            visit(start, [start])
    return found


def write_tree(folder, files):
    root = Path(folder) / "pkg"
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


class SizeRules(unittest.TestCase):
    def test_no_module_is_over_the_ceiling(self):
        """Catches a module that has grown into a monolith (over 600 lines)."""
        self.assertEqual(long_modules(PACKAGE), [])

    def test_no_function_is_over_the_ceiling(self):
        """Catches a function that has grown past 120 lines."""
        self.assertEqual(long_functions(PACKAGE), [])

    def test_no_circular_imports(self):
        """Catches two or more modules that import each other in a circle."""
        self.assertEqual(cycles(import_graph(PACKAGE)), [])

    def test_the_package_is_seen(self):
        """Catches the rules silently scanning an empty or wrong folder."""
        self.assertIn("frc_design_kernel.errors", import_graph(PACKAGE))


class SizeRuleControls(unittest.TestCase):
    """Controls: each rule is shown to fail on a tree that breaks it."""

    def test_a_long_module_is_caught(self):
        """Catches a size check that can no longer fail."""
        with tempfile.TemporaryDirectory() as folder:
            root = write_tree(folder, {"big.py": "x = 1\n" * 601, "small.py": "x = 1\n" * 600})
            self.assertEqual(long_modules(root), ["big.py: 601 lines"])

    def test_a_long_function_is_caught(self):
        """Catches a function-length check that can no longer fail."""
        with tempfile.TemporaryDirectory() as folder:
            body = "def long():\n" + "    x = 1\n" * 120 + "def short():\n" + "    x = 1\n" * 119
            root = write_tree(folder, {"mod.py": body})
            self.assertEqual(long_functions(root), ["mod.py: long is 121 lines"])

    def test_a_circular_import_is_caught(self):
        """Catches a cycle check that can no longer fail, including a relative import inside a function."""
        with tempfile.TemporaryDirectory() as folder:
            root = write_tree(folder, {"__init__.py": "", "a.py": "from . import b\n", "sub/__init__.py": "",
                                       "b.py": "from .sub import c\n", "sub/c.py": "def f():\n    from ..a import x\n"})
            self.assertEqual(cycles(import_graph(root)), [["pkg.a", "pkg.b", "pkg.sub.c", "pkg.a"]])


if __name__ == "__main__":
    unittest.main()
