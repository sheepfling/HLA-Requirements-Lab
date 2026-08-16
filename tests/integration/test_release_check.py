"""Release-gate integration test; run after document builds have completed."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from hla_lab.publication.release_check import check_release

REPO_ROOT = Path(__file__).resolve().parents[2]

class ReleaseCheckIntegrationTests(unittest.TestCase):
    def test_release_manifest_passes_against_current_builds(self) -> None:
        manifest_path = REPO_ROOT / "data" / "release" / "documents.json"
        report = check_release(
            REPO_ROOT,
            manifest_path,
            diagram_manifest=REPO_ROOT / "data" / "state_machines" / "manifest.json",
        )
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["tracked_generated"], [])
        self.assertEqual(report["diagram_review"]["review_gaps"], [])
        self.assertTrue(report["semantic_authority"]["passed"])
        self.assertTrue(report["api_traceability"]["passed"])
        self.assertEqual(
            {item["id"]: item["pages"] for item in report["projects"]},
            {
                str(item["id"]): item["expected_pages"]
                for item in json.loads(manifest_path.read_text(encoding="utf-8"))["projects"]
            },
        )

if __name__ == "__main__":
    unittest.main()
