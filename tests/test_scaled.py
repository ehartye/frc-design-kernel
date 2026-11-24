"""At the scale of a large preliminary design the records stay small and status stays quick.

The design is the invented one in scaled_design (about 230 solids, 74 motions), measured with the kind of job list
a judging tool asks for: 106 jobs of every kind.
"""
import tempfile
import time
import unittest
from pathlib import Path

from frc_design_kernel.measure import records
from frc_design_kernel.status import status

from . import scaled_design
from .helpers import load_data

BUDGET_BYTES = 2_000_000


class AtScale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = scaled_design.design()
        cls.path = load_data(cls.data).path
        cls.folder = tempfile.TemporaryDirectory()
        began = time.perf_counter()
        cls.entries = records.record(cls.path, scaled_design.jobs(cls.data), cls.folder.name, workers=4)
        cls.measuring = time.perf_counter() - began
        cls.files = sorted((Path(cls.folder.name) / records.FOLDER).glob("*.json"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_design_is_at_scale(self):
        """Catches the fixture shrinking until it no longer stands for a large design."""
        self.assertEqual((len(self.data["solids"]) + len(self.data["fixtures"]), len(self.data["motions"])), (228, 74))
        self.assertEqual(len(self.files), 106)

    def test_the_job_files_total_at_most_2_mb(self):
        """Catches the records rebuilding the bulk of a receipt: far-apart rows or per-solid tables copied into every job."""
        size = sum(path.stat().st_size for path in self.files)
        self.assertLessEqual(size, BUDGET_BYTES, f"{size} bytes in {len(self.files)} job files")

    def test_status_reads_every_record_current_and_says_how_long_it_took(self):
        """Catches status calling a fresh record stale at scale, or taking far longer than a build and a comparison."""
        found = status(self.path, self.folder.name)
        self.assertEqual({row["state"] for row in found["records"]}, {"current"})
        self.assertEqual(len(found["records"]), 106)
        self.assertLess(found["seconds"], 20)


if __name__ == "__main__":
    unittest.main()
