"""Release-audit tests for the requirement-to-API traceability surface."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from hla_lab.traceability.api_traceability import build_report

ROOT = Path(__file__).resolve().parents[1]
EDITION_ROOTS = tuple(ROOT / "topics" / "ieee" / f"hla-1516.1-{year}" for year in ("2010", "2025"))

class ApiTraceabilityAuditTests(unittest.TestCase):
    def test_both_editions_pass_the_traceability_audit(self) -> None:
        report = build_report(EDITION_ROOTS)
        self.assertTrue(report.passed, report.failures)
        self.assertTrue(report.complete)
        self.assertEqual(
            {
                item.document: (
                    item.requirement_count,
                    item.covered_requirement_count,
                    item.matched_binding_count,
                    item.review_gap_count,
                )
                for item in report.documents
            },
            {
                "hla-1516.1-2010": (942, 942, 186, 0),
                "hla-1516.1-2025": (1697, 1697, 48, 0),
            },
        )

    def test_audit_cli_is_machine_readable_and_enforced(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "hla_lab.traceability.api_traceability",
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
        self.assertTrue(payload["complete"])
        self.assertEqual(
            {item["document"] for item in payload["documents"]},
            {"hla-1516.1-2010", "hla-1516.1-2025"},
        )
        strict = subprocess.run(
            [
                sys.executable,
                "-m",
                "hla_lab.traceability.api_traceability",
                "--check",
                "--require-complete",
                "--json",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(strict.returncode, 0)

if __name__ == "__main__":
    unittest.main()
