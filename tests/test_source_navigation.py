"""Regression checks for the restored 1516.2 PDF page sequence and navigation."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from hla_lab.build.topic import project_config
from hla_lab.paths import REPO_ROOT

DOCUMENT_ROOT = REPO_ROOT / "topics" / "ieee" / "hla-1516.2-2025"
NAVIGATION_PATH = DOCUMENT_ROOT / "canonical" / "source-navigation.json"

spec = importlib.util.spec_from_file_location(
    "apply_pdf_navigation", DOCUMENT_ROOT / "tools" / "apply_pdf_navigation.py"
)
assert spec is not None and spec.loader is not None
navigation_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(navigation_module)


class SourceNavigationTests(unittest.TestCase):
    def test_build_includes_both_covers_and_canonical_navigation(self) -> None:
        config = project_config(DOCUMENT_ROOT)
        manifest = json.loads(NAVIGATION_PATH.read_text(encoding="utf-8"))
        source = (DOCUMENT_ROOT / "main.tex").read_text(encoding="utf-8")

        self.assertTrue(config.clean_before_build)
        self.assertEqual(config.navigation_manifest, NAVIGATION_PATH)
        self.assertEqual(manifest["page_count"], 124)
        self.assertEqual(len(manifest["outline"]), 168)
        self.assertEqual(len(manifest["links"]), 234)
        cover = source.index("frontmatter/cover")
        frontmatter = source.index("sections/semantic/frontmatter")
        body = source.index("faithful-body")
        back_cover = source.index("frontmatter/back-cover")
        self.assertLess(cover, frontmatter)
        self.assertLess(frontmatter, body)
        self.assertLess(body, back_cover)

    def test_navigation_postprocessor_rejects_wrong_page_count_helpfully(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "one-page.pdf"
            with pymupdf.open() as document:
                document.new_page()
                document.save(pdf_path)
            manifest_path = root / "navigation.json"
            manifest_path.write_text(
                json.dumps({"page_count": 2, "outline": [], "page_labels": [], "links": []}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError, r"Page-count mismatch: PDF has 1, manifest expects 2"
            ):
                navigation_module.apply(pdf_path, manifest_path, root / "out.pdf")


if __name__ == "__main__":
    unittest.main()
