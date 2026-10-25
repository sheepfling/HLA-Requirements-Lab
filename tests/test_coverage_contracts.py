"""Coverage-closure and full-1516-content ownership tests."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from pydantic import JsonValue

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.traceability.semantic_coverage import build_report
from tests.support import TEST_REPO_ROOT

REPO_ROOT = TEST_REPO_ROOT
ROOT = REPO_ROOT / "topics" / "ieee" / "hla-1516-2025"
ROOTS = tuple(sorted((REPO_ROOT / "topics" / "ieee").glob("hla-1516*/")))


class CoverageContractTests(unittest.TestCase):
    def test_candidate_and_transition_coverage_is_explicit(self) -> None:
        report = build_report(ROOTS)
        self.assertTrue(report.passed, report.failures)
        for document in report.documents:
            self.assertEqual(document.requirements.reviews["unreviewed"], 0)
            self.assertEqual(document.transitions.coverage["unclassified"], 0)

    def test_dashboard_default_is_profile_scoped_to_hla(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "hla_lab.reports.semantic_dashboard", "--json"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(
            {item["document"] for item in payload["documents"]},
            {
                "hla-1516-2010",
                "hla-1516.1-2010",
                "hla-1516.2-2010",
                "hla-1516-2025",
                "hla-1516.1-2025",
                "hla-1516.2-2025",
            },
        )

    def test_1516_has_canonical_navigation_and_full_content_ownership(self) -> None:
        model = load_document_model(ROOT, HLA_SOURCE)
        pages = tuple((ROOT / "sections" / "semantic").rglob("page-*.tex"))
        self.assertEqual(len(pages), 38)
        self.assertEqual(len(model.content_blocks), 29)
        self.assertEqual(len(model.ordered_clauses()), 33)
        self.assertTrue(all(block.layout_body for block in model.content_blocks))
        self.assertTrue(
            all(
                text.count(r"\input{output/semantic/content-block-") == 1
                and r"\HLAClauseHeading" not in text
                for text in (path.read_text(encoding="utf-8") for path in pages)
            )
        )
        navigation: dict[str, JsonValue] = json.loads(
            (ROOT / "canonical" / "source-navigation.json").read_text(encoding="utf-8")
        )
        outline: list[JsonValue] = navigation["outline"]
        self.assertEqual(sum(isinstance(item, dict) for item in outline), 33)

    def test_1516_content_block_source_and_layout_are_separate_fields(self) -> None:
        payload = json.loads(
            (ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertTrue(all(item["text"] is not None for item in payload["content_blocks"]))
        self.assertTrue(all(item["layout_body"] for item in payload["content_blocks"]))
        self.assertTrue(
            all("page-" in item["source"]["path"] for item in payload["content_blocks"])
        )


if __name__ == "__main__":
    unittest.main()
