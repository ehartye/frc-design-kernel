"""Every data file that the package needs is shipped with it, and the example is a whole rules folder."""
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from .rules_cases import ROOT
from .test_size_rules import PACKAGE, import_graph

EXAMPLES = ROOT / "examples" / "rules"


def globs(project):
    """The patterns of the files that an installed copy has beside the code."""
    return tomllib.loads(project)["tool"]["setuptools"]["package-data"]["frc_design_kernel"]


def not_shipped(package, patterns):
    """Every JSON file in a package folder that no pattern matches, so that an installed copy would not have it."""
    matched = {path for pattern in patterns for path in package.glob(pattern)}
    return sorted(path.relative_to(package).as_posix() for path in package.rglob("*.json") if path not in matched)


class Shipped(unittest.TestCase):
    """An installed copy has every data file. The tests run from the checkout, where a missing one would not show."""

    def test_every_json_file_is_shipped(self):
        """Catches a JSON file that works in the checkout and is missing from the installed library."""
        self.assertEqual(not_shipped(PACKAGE, globs((ROOT / "pyproject.toml").read_text(encoding="utf-8"))), [])

    def test_the_files_are_seen(self):
        """Control: the scan looks at the real package, where fields.json and the schemas are."""
        found = {path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*.json")}
        self.assertLessEqual({"rules/fields.json", "source/design.schema.json"}, found)

    def test_a_file_that_is_not_shipped_is_caught(self):
        """Control: a JSON file in a folder that no pattern names is found, and one that is named is not."""
        project = '[tool.setuptools.package-data]\nfrc_design_kernel = ["source/*.json"]\n'
        with tempfile.TemporaryDirectory() as folder:
            for name in ["source/a.json", "rules/b.json", "source/deep/c.json", "d.json"]:
                (Path(folder) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(folder) / name).write_text("{}", encoding="utf-8")
            self.assertEqual(not_shipped(Path(folder), globs(project)), ["d.json", "rules/b.json", "source/deep/c.json"])


class Examples(unittest.TestCase):
    """The example folders are whole and read with no fault."""

    def test_the_example_reads(self):
        """Catches an example that an author copies and that the reader refuses."""
        from frc_design_kernel.rules import words
        folders = sorted(path for path in EXAMPLES.iterdir() if path.is_dir())
        self.assertGreaterEqual(len(folders), 1)
        for folder in folders:
            book, faults = words.load(folder)
            self.assertEqual([str(f) for f in faults], [], folder.name)
            self.assertGreater(len(book.ids), 80)

    def test_a_broken_example_is_caught(self):
        """Control: the same folder with one file left out does not read."""
        from frc_design_kernel.rules import words
        source = sorted(EXAMPLES.iterdir())[0]
        with tempfile.TemporaryDirectory() as folder:
            for path in source.glob("*.json"):
                if path.stem != "terms":
                    (Path(folder) / path.name).write_bytes(path.read_bytes())
            self.assertEqual([f.where for f in words.load(folder)[1]], ["terms.json"])

    def test_the_example_is_dated_and_holds_nine_files(self):
        """Catches a folder whose name is no date, or a file in it that no reader opens."""
        from frc_design_kernel.rules import read
        for folder in EXAMPLES.iterdir():
            self.assertRegex(folder.name, r"^\d{4}-\d{2}-\d{2}$")
            self.assertEqual(sorted(path.name for path in folder.iterdir()), sorted(f"{name}.json" for name in read.names()["files"]))

    def test_the_readers_own_list_is_one_json_object(self):
        """Catches a fields.json with a field written twice, of which JSON silently keeps the last."""
        def once(pairs):
            self.assertEqual(len(pairs), len(dict(pairs)), [name for name, _ in pairs])
            return dict(pairs)
        json.loads((PACKAGE / "rules" / "fields.json").read_text(encoding="utf-8"), object_pairs_hook=once)


class Alone(unittest.TestCase):
    """What the package may import."""

    def test_rules_imports_only_source_and_errors(self):
        """Catches the rules reader needing the CAD kernel, or anything above it, only to read nine text files."""
        self.assertEqual(outside(import_graph(PACKAGE)), [])

    def test_an_import_from_above_is_caught(self):
        """Control: a rules module that imports the kernel or the builder is found."""
        graph = {"frc_design_kernel.rules.read": {"frc_design_kernel.errors", "frc_design_kernel.rules.quantity", "frc_design_kernel.source.expressions", "frc_design_kernel.kernel.shapes"},
                 "frc_design_kernel.builder.shape": {"frc_design_kernel.kernel.shapes"}}
        self.assertEqual(outside(graph), ["frc_design_kernel.rules.read imports frc_design_kernel.kernel.shapes"])

    def test_nothing_is_imported_from_outside_the_standard_library(self):
        """Catches the rules reader needing a package that is not there, such as the CAD kernel, to be imported."""
        code = "import sys; from frc_design_kernel.rules import words; print(sorted(m for m in sys.modules if m.split('.')[0] in ('OCP', 'mujoco', 'numpy')))"
        self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT).stdout.strip(), "[]")


def outside(graph):
    """Each import by a rules module of something in the package that is not rules, source or errors."""
    allowed = ("frc_design_kernel.rules", "frc_design_kernel.source", "frc_design_kernel.errors")
    return [f"{name} imports {other}" for name in sorted(graph) if name.startswith("frc_design_kernel.rules")
            for other in sorted(graph[name]) if other != "frc_design_kernel" and not other.startswith(allowed)]


def sent_to_nothing(root, folders):
    """Each file of some folders that names a document, such as a NOTES.md, that is not in the repository."""
    found = []
    for folder in folders:
        for path in sorted((root / folder).rglob("*")):
            if path.suffix in (".py", ".json", ".md"):
                for name in re.findall(r"\b[A-Za-z_]+\.md\b", path.read_text(encoding="utf-8")):
                    if not (root / name).exists():
                        found.append(f"{path.relative_to(root).as_posix()} names {name}")
    return found


class NoDocument(unittest.TestCase):
    """Nobody has to open a document to learn the format."""

    def test_nobody_is_sent_to_a_document_that_is_not_there(self):
        """Catches a message or a comment that sends an author to a file that no longer exists."""
        self.assertEqual(sent_to_nothing(ROOT, ["frc_design_kernel", "examples"]), [])

    def test_a_document_that_is_not_there_is_caught(self):
        """Control: a file that names a missing document is found, and one that names a document that is there is not."""
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "code").mkdir()
            (Path(folder) / "GUIDE.md").write_text("", encoding="utf-8")
            (Path(folder) / "code" / "a.py").write_text("# see GUIDE.md and NOTES.md", encoding="utf-8")
            self.assertEqual(sent_to_nothing(Path(folder), ["code"]), ["code/a.py names NOTES.md"])


if __name__ == "__main__":
    unittest.main()
