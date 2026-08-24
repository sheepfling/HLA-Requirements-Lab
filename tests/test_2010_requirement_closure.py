"""Acceptance tests for the source-owned 2010 requirement catalogs."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from hla_lab.traceability.requirement_closure import build_report

ROOT = Path(__file__).resolve().parents[1]


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
                "hla-1516-2010": (55, 55, 55, 0, 0, 2),
                "hla-1516.1-2010": (942, 942, 942, 0, 0, 111),
                "hla-1516.2-2010": (388, 388, 388, 0, 0, 76),
            },
        )

    def test_15161_2010_api_bindings_cover_the_frozen_catalog(self) -> None:
        document = next(item for item in build_report().documents if item.document == "hla-1516.1-2010")
        self.assertEqual(document.api_binding_rows, 1078)
        self.assertEqual(document.api_binding_requirement_ids, 942)
        self.assertEqual(document.missing_api_requirement_ids, ())
        self.assertEqual(document.unexpected_api_requirement_ids, ())

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
