"""Regression checks for the restored 1516.2 PDF page sequence and navigation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

from hla_lab.build.topic import project_config
from hla_lab.paths import REPO_ROOT

DOCUMENT_ROOT = REPO_ROOT / "topics" / "ieee" / "hla-1516.2-2025"
NAVIGATION_PATH = DOCUMENT_ROOT / "canonical" / "lab-navigation.json"
APPLY_NAVIGATION = DOCUMENT_ROOT / "tools" / "apply_pdf_navigation.py"


class SourceNavigationTests(unittest.TestCase):
    def test_build_includes_both_covers_and_canonical_navigation(self) -> None:
        config = project_config(DOCUMENT_ROOT)
        manifest = json.loads(NAVIGATION_PATH.read_text(encoding="utf-8"))
        source = (DOCUMENT_ROOT / "main.tex").read_text(encoding="utf-8")

        self.assertTrue(config.clean_before_build)
        self.assertEqual(config.navigation_manifest, NAVIGATION_PATH)
        self.assertEqual(manifest["page_count"], 113)
        self.assertEqual(len(manifest["outline"]), 18)
        self.assertEqual(len(manifest["outline_text_checks"]), 18)
        self.assertEqual(manifest["links"], [])
        self.assertEqual(manifest["outline"][1], [1, "1. Overview", 2])
        cover = r"\input{../hla-requirements-lab-cover}"
        self.assertEqual(source.count(cover), 1)
        self.assertNotIn("frontmatter/cover", source)
        self.assertNotIn("sections/semantic/frontmatter", source)
        self.assertLess(source.index(cover), source.index("faithful-body"))
        self.assertLess(source.index("faithful-body"), source.index("frontmatter/back-cover"))
        historical = json.loads(
            (DOCUMENT_ROOT / "canonical" / "source-navigation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(historical["page_count"], 124)

    def test_navigation_postprocessor_rejects_wrong_page_count_helpfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "one-page.pdf"
            with pymupdf.open() as document:
                document.new_page()
                document.save(pdf_path)
            manifest_path = root / "navigation.json"
            manifest = {
                "schema_version": 1,
                "page_count": 2,
                "outline": [],
                "page_labels": [],
                "links": [],
            }

            def run_navigation() -> subprocess.CompletedProcess[str]:
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                return subprocess.run(
                    [
                        sys.executable,
                        str(APPLY_NAVIGATION),
                        str(pdf_path),
                        str(manifest_path),
                        str(root / "out.pdf"),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )

            result = run_navigation()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Page-count mismatch: PDF has 1, manifest expects 2", result.stderr)
            manifest["page_count"] = 1
            manifest["outline"] = [[1, "Missing", 1]]
            manifest["outline_text_checks"] = [[1, "Missing"]]
            result = run_navigation()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Outline marker not found on page 1", result.stderr)
            self.assertFalse((root / "out.pdf").exists())


if __name__ == "__main__":
    unittest.main()
