"""Release-audit tests for the requirement-to-API traceability surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

from hla_lab.traceability.api_traceability import build_report
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
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
                "hla-1516.1-2010": (1529, 1529, 126, 0),
                "hla-1516.1-2025": (1865, 1865, 53, 0),
            },
        )

    def test_audit_cli_is_machine_readable_and_enforced(self) -> None:
        environment = os.environ.copy()
        environment.pop("HLA_LAB_ROOT", None)
        environment.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as outside_workspace:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "hla_lab.traceability.api_traceability",
                    "--workspace-root",
                    str(ROOT),
                    "--check",
                    "--json",
                ],
                cwd=outside_workspace,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            strict = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "hla_lab.traceability.api_traceability",
                    "--workspace-root",
                    str(ROOT),
                    "--check",
                    "--require-complete",
                    "--json",
                ],
                cwd=outside_workspace,
                env=environment,
                check=False,
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
        self.assertEqual(strict.returncode, 0)


if __name__ == "__main__":
    unittest.main()
