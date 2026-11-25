"""Regression checks for the local 2026-11-23 issue reconciliation snapshot."""

from __future__ import annotations

import ast
import json
import unittest
from collections import Counter
from pathlib import Path

from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
SNAPSHOT_PATH = ROOT / "data" / "hla-backflow-2026-11-23.json"
EXPECTED_TRACKED_IDS = {
    "RL-392",
    *(f"RL-{number}" for number in range(394, 402)),
    *(f"RL-{number}" for number in range(403, 411)),
    *(f"RL-{number}" for number in range(411, 421)),
    *(f"RL-{number}" for number in range(421, 438)),
    *(f"RL-{number}" for number in range(438, 457)),
}


def _declared_test_methods(path: Path) -> set[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        (class_node.name, method.name)
        for class_node in tree.body
        if isinstance(class_node, ast.ClassDef)
        for method in class_node.body
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class BackflowSnapshotTests(unittest.TestCase):
    def test_snapshot_preserves_all_tracked_records_and_current_upstream_status(self) -> None:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        records = payload["issues"]

        self.assertEqual(payload["as_of"], "2026-11-23")
        self.assertEqual(payload["source"], "Umbra/compliance/requirements-lab/known-issues.json")
        self.assertRegex(payload["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(records), 63)
        self.assertEqual({item["id"] for item in records}, EXPECTED_TRACKED_IDS)
        self.assertEqual(
            Counter(item["upstream_status"] for item in records),
            {"open": 57, "resolved-in-umbra": 6},
        )
        self.assertEqual(
            Counter(item["local_status"] for item in records),
            {
                "corrected-in-lab": 50,
                "source-anomaly-mapped": 8,
                "downstream-only-no-lab-change": 5,
            },
        )
        self.assertEqual(payload["totals"]["tracked_queue_records"], 63)
        self.assertEqual(payload["totals"]["open_upstream"], 57)
        self.assertEqual(payload["totals"]["resolved_in_umbra"], 6)
        self.assertEqual(payload["totals"]["source_anomaly_mapped"], 8)

        for item in records:
            upstream = item["upstream_record"]
            self.assertEqual(upstream["id"], item["id"])
            self.assertEqual(upstream["status"], item["upstream_status"])
            for field in ("title", "symptom", "impact", "verification"):
                self.assertIn(field, upstream, f"{item['id']} lost upstream field {field}")
            self.assertTrue(
                "source" in upstream or "sources" in upstream,
                f"{item['id']} lost upstream source evidence",
            )
            if item["local_status"] == "downstream-only-no-lab-change":
                self.assertEqual(item["verification_refs"], [])
            else:
                self.assertTrue(item["verification_refs"], item["id"])

    def test_every_snapshot_verification_reference_resolves_to_a_test(self) -> None:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        for item in payload["issues"]:
            for reference in item["verification_refs"]:
                module, class_name, method_name = reference.split("::")
                test_file = ROOT / module
                self.assertTrue(test_file.is_file(), reference)
                self.assertIn(
                    (class_name, method_name),
                    _declared_test_methods(test_file),
                    reference,
                )


if __name__ == "__main__":
    unittest.main()
