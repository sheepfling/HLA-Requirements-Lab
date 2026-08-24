"""Edition-neutral quality gates for the published semantic surfaces."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model

ROOT = Path(__file__).resolve().parents[1]
EDITION_ROOTS = tuple(
    ROOT / "topics" / "ieee" / name
    for name in ("hla-1516.1-2010", "hla-1516.1-2025")
)
FORBIDDEN_LEGACY_TOKENS = ("rl-", "candidate-intake-", "temporary-")


class SemanticQualityGateTests(unittest.TestCase):
    def test_requirements_are_source_coherent_and_free_of_temporary_labels(self) -> None:
        for root in EDITION_ROOTS:
            model = load_document_model(root, HLA_SOURCE)
            with self.subTest(document=root.name):
                self.assertTrue(model.requirements)
                for requirement in model.requirements:
                    values = (
                        requirement.id,
                        requirement.title,
                        requirement.statement,
                        requirement.coverage_note,
                        requirement.api_surface_note,
                    )
                    self.assertFalse(
                        any(
                            marker in value.casefold()
                            for marker in FORBIDDEN_LEGACY_TOKENS
                            for value in values
                        ),
                        requirement.id,
                    )
                    self.assertGreaterEqual(requirement.source.line, 1)
                    if requirement.source.end_line is not None:
                        self.assertGreaterEqual(
                            requirement.source.end_line,
                            requirement.source.line,
                        )
                    self.assertTrue(
                        (root / requirement.source.path).is_file(),
                        requirement.id,
                    )
                    self.assertNotIn("%", requirement.statement, requirement.id)
                    if " at " in requirement.title:
                        self.assertIn(requirement.source.path, requirement.title)
                        self.assertIn(f":{requirement.source.line}", requirement.title)

    def test_table_cell_links_and_api_binding_manifests_are_closed(self) -> None:
        for root in EDITION_ROOTS:
            model = load_document_model(root, HLA_SOURCE)
            record_ids = model.semantic_record_ids()
            with self.subTest(document=root.name):
                self.assertTrue(
                    all(
                        related_id in record_ids
                        for table in model.tables
                        for cell in table.cells
                        for related_id in cell.record_ids
                    )
                )
                self.assertEqual(
                    {item.requirement_id for item in model.requirement_api_bindings},
                    {item.id for item in model.requirements},
                )
                self.assertTrue(model.requirement_api_bindings)

    def test_15161_source_anomaly_ledger_is_structured(self) -> None:
        path = ROOT / "topics" / "ieee" / "hla-1516.1-2025" / "semantic" / "source-anomaly-ledger.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {
            "source_id",
            "location",
            "source_text",
            "rendered_text",
            "classification",
            "reason",
            "review_status",
        }
        allowed = {
            "SOURCE_ANOMALY",
            "COMPILATION_DEFECT",
            "ENCODING_REPAIR",
            "EDITORIAL_CONTAMINATION",
            "CROSS_REFERENCE_DEFECT",
        }
        self.assertGreaterEqual(len(payload["entries"]), 10)
        self.assertTrue(all(required <= set(entry) for entry in payload["entries"]))
        self.assertTrue(all(entry["classification"] in allowed for entry in payload["entries"]))


if __name__ == "__main__":
    unittest.main()
