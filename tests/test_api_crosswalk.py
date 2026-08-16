"""Contracts for semantic-to-binding API crosswalks."""

from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from hla_lab.core.semantic_model import ApiCrosswalkFile
from hla_lab.corpus.hla_api_crosswalk import hla_api_targets
from hla_lab.corpus.hla_semantic import load_hla_document_model

ROOT = Path(__file__).resolve().parents[1]


class ApiCrosswalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.models = {
            edition: load_hla_document_model(ROOT / "topics" / "ieee" / f"hla-1516.1-{edition}")
            for edition in ("2010", "2025")
        }

    def test_each_edition_has_binding_and_projection_rows(self) -> None:
        expected_targets = {
            "2010": {"cpp", "java", "python", "wsdl"},
            "2025": {"cpp", "java", "python", "fedpro", "grpc"},
        }
        for edition, model in self.models.items():
            self.assertEqual(
                {target.name for target in hla_api_targets(edition)},
                expected_targets[edition],
            )
            self.assertEqual(
                len(model.api_crosswalks),
                len(model.implementations) * len(expected_targets[edition]),
            )

    def test_crosswalk_statuses_have_explicit_evidence_rules(self) -> None:
        for model in self.models.values():
            for row in model.api_crosswalks:
                if row.status == "matched":
                    self.assertEqual(len(row.selected_api_surface_ids), 1)
                elif row.status == "ambiguous":
                    self.assertGreaterEqual(len(row.candidate_api_surface_ids), 2)
                else:
                    self.assertEqual(row.candidate_api_surface_ids, ())
                    self.assertEqual(row.selected_api_surface_ids, ())

    def test_generated_manifests_round_trip_and_expose_gaps(self) -> None:
        for edition, model in self.models.items():
            path = (
                ROOT
                / "topics"
                / "ieee"
                / f"hla-1516.1-{edition}"
                / "semantic"
                / "api-crosswalk.json"
            )
            restored = ApiCrosswalkFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(len(restored.api_crosswalks), len(model.api_crosswalks))
            self.assertTrue(model.api_crosswalk_gaps())
            self.assertEqual(
                sum(Counter(item.status for item in model.api_crosswalks).values()),
                len(model.api_crosswalks),
            )

    def test_mapping_query_returns_all_targets(self) -> None:
        for edition, model in self.models.items():
            mapping_id = model.implementations[0].id
            rows = model.api_crosswalks_for_mapping(mapping_id)
            self.assertEqual(len(rows), len(hla_api_targets(edition)))
            self.assertEqual(
                {item.target for item in rows},
                {target.name for target in hla_api_targets(edition)},
            )

    def test_disconnect_does_not_match_connect_overloads(self) -> None:
        model = self.models["2025"]
        for target in ("cpp", "java"):
            row = next(
                item
                for item in model.api_crosswalks
                if item.implementation_mapping_id == "rti.service.disconnect"
                and item.target == target
            )
            self.assertEqual(row.status, "matched")
            self.assertEqual(len(row.selected_api_surface_ids), 1)
            self.assertTrue(all("disconnect" in item for item in row.candidate_api_surface_ids))


if __name__ == "__main__":
    unittest.main()
