"""Contract tests for full-build and visual-release checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.release_check import _log_errors, check_release

REPO_ROOT = Path(__file__).resolve().parents[1]


class Milestone7Tests(unittest.TestCase):
    def test_release_manifest_passes_against_current_builds(self) -> None:
        report = check_release(
            REPO_ROOT,
            REPO_ROOT / "data" / "release" / "documents.json",
            diagram_manifest=REPO_ROOT / "data" / "state_machines" / "manifest.json",
        )
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["tracked_generated"], [])
        self.assertEqual(report["diagram_review"]["review_gaps"], [])
        self.assertTrue(report["semantic_authority"]["passed"])
        self.assertEqual(
            {item["pages"] for item in report["projects"]},
            {1, 40, 124, 338, 1554},
        )

    def test_release_log_check_reports_fatal_latex_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.log"
            path.write_text(
                "Package Warning: okay\n! Undefined control sequence.\n", encoding="utf-8"
            )
            errors = _log_errors(path)
        self.assertEqual(len(errors), 1)
        self.assertIn("Undefined control sequence", errors[0])


if __name__ == "__main__":
    unittest.main()
