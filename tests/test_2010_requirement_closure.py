"""Acceptance tests for the source-owned 2010 requirement catalogs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.traceability.requirement_closure import build_report
from tests.support import TEST_REPO_ROOT
from tools.migrations.complete_hla_2010_requirements import _promote

ROOT = TEST_REPO_ROOT


class RequirementClosure2010Tests(unittest.TestCase):
    def test_2010_catalogs_match_the_legacy_source_inventory(self) -> None:
        report = build_report()
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(
            {
                item.document: (
                    item.requirements,
                    item.source_candidates,
                    item.explicit_requirements,
                    item.candidate_requirements,
                    item.requirement_reviews,
                    item.table_count,
                )
                for item in report.documents
            },
            {
                "hla-1516-2010": (56, 56, 56, 0, 0, 2),
                # Legacy candidates and semantic requirements are segmented
                # differently when source statements are split or combined.
                "hla-1516.1-2010": (1529, 1530, 1529, 0, 0, 111),
                "hla-1516.2-2010": (589, 583, 589, 0, 0, 76),
            },
        )

    def test_15161_2010_api_bindings_cover_the_frozen_catalog(self) -> None:
        document = next(
            item for item in build_report().documents if item.document == "hla-1516.1-2010"
        )
        self.assertEqual(document.api_binding_rows, 1611)
        self.assertEqual(document.api_binding_requirement_ids, 1529)
        self.assertEqual(document.missing_api_requirement_ids, ())
        self.assertEqual(document.unexpected_api_requirement_ids, ())

    def test_documents_without_api_surfaces_do_not_report_binding_gaps(self) -> None:
        for document in build_report().documents:
            if document.api_binding_rows == 0:
                self.assertEqual(document.api_binding_requirement_ids, 0)
                self.assertEqual(document.missing_api_requirement_ids, ())
                self.assertEqual(document.unexpected_api_requirement_ids, ())

    def test_all_2010_catalog_records_have_clean_spans_and_content_owners(self) -> None:
        roots = (
            ROOT / "topics" / "ieee" / "hla-1516-2010",
            ROOT / "topics" / "ieee" / "hla-1516.1-2010",
            ROOT / "topics" / "ieee" / "hla-1516.2-2010",
        )
        for root in roots:
            model = load_document_model(root, HLA_SOURCE)
            with self.subTest(document=root.name):
                self.assertTrue(all(item.source.end_line for item in model.requirements))
                self.assertTrue(
                    all(
                        not re.search(r"\\\\|\\\\linebreak", item.statement)
                        and not re.search(
                            r"(?:shall|must|to|the|of|and|or)\s*$",
                            item.statement,
                            re.I,
                        )
                        for item in model.requirements
                    )
                )
                requirement_ids = {item.id for item in model.requirements}
                block_ids = {
                    record_id for block in model.content_blocks for record_id in block.record_ids
                }
                element_ids = {
                    record_id
                    for element in model.content_elements
                    for record_id in element.record_ids
                }
                self.assertEqual(requirement_ids - block_ids, set())
                self.assertEqual(requirement_ids - element_ids, set())

        framework = load_document_model(roots[0], HLA_SOURCE)
        self.assertEqual(
            sum(item.coverage_kind == "not-applicable" for item in framework.requirements),
            12,
        )

    def test_completed_2010_migration_is_read_only(self) -> None:
        root = ROOT / "topics" / "ieee" / "hla-1516.1-2010"
        with patch(
            "tools.migrations.complete_hla_2010_requirements._write",
            side_effect=AssertionError("closed migration attempted a write"),
        ) as write:
            result = _promote(root)
        self.assertEqual(result["requirements"], 1529)
        write.assert_not_called()

    def test_closure_cli_is_machine_readable_and_enforced(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "hla_lab.traceability.requirement_closure",
                "--check",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["passed"])
        self.assertEqual(
            {item["document"] for item in payload["documents"]},
            {"hla-1516-2010", "hla-1516.1-2010", "hla-1516.2-2010"},
        )


if __name__ == "__main__":
    unittest.main()
