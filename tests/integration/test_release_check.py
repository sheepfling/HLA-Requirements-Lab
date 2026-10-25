"""Release-gate integration test; run after document builds have completed."""

from __future__ import annotations

import json
import unittest

import fitz

from hla_lab.publication.release_check import check_release
from tests.support import TEST_REPO_ROOT

REPO_ROOT = TEST_REPO_ROOT


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

    def test_faithful_pdfs_preserve_letter_geometry_and_lab_furniture(self) -> None:
        manifest = json.loads(
            (REPO_ROOT / "data" / "release" / "documents.json").read_text(encoding="utf-8")
        )
        faithful = [item for item in manifest["projects"] if item.get("kind") == "faithful"]
        self.assertEqual(len(faithful), 6)

        for item in faithful:
            pdf_path = REPO_ROOT / item["root"] / item["pdf"]
            with self.subTest(document=item["id"]), fitz.open(pdf_path) as document:
                self.assertEqual(len(document), item["expected_pages"])
                for page in document:
                    self.assertIn(
                        (round(page.rect.width, 1), round(page.rect.height, 1)),
                        {(612.0, 792.0), (792.0, 612.0)},
                    )

                sample_indices = {0, min(22, len(document) - 1), len(document) - 1}
                for index in sorted(sample_indices):
                    self.assertIn("HLA REQUIREMENTS LAB", document[index].get_text())
                self.assertNotIn("IEEE Standard for", document[0].get_text())


if __name__ == "__main__":
    unittest.main()
