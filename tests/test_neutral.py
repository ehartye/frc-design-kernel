"""The library stays self-standing: no paths from anyone's machine in any file."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".py", ".md", ".json", ".toml", ".yml", ".step", ".txt"}
MACHINE_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|/home/[a-z]|/Users/[A-Za-z]")


def machine_paths(root):
    found = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in TEXT and ".git" not in path.parts and "__pycache__" not in path.parts:
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if MACHINE_PATH.search(line):
                    found.append(f"{path.relative_to(root).as_posix()}:{number}")
    return found


class Neutral(unittest.TestCase):
    def test_no_machine_paths(self):
        """Catches a path from someone's computer leaking into the code, the docs or a generated STEP file."""
        self.assertEqual(machine_paths(ROOT / "frc_design_kernel") + machine_paths(ROOT / "examples") + machine_paths(ROOT / "tests")
                         + [f for f in machine_paths(ROOT) if "/" not in f], [])

    def test_a_machine_path_is_caught(self):
        """Control: the scan can fail."""
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "note.md").write_text("fine\nsee C:" + "\\Users" + "\\someone\\file\n", encoding="utf-8")
            self.assertEqual(machine_paths(Path(folder)), ["note.md:2"])


if __name__ == "__main__":
    unittest.main()
