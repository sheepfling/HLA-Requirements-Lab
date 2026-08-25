"""query compliance query and implementation-mapping contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    ImplementationMapping,
    ImplementationReference,
    load_document_model,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HLA_ROOT = REPO_ROOT / "topics" / "ieee"
DOCUMENT_ROOTS = tuple(
    HLA_ROOT / name
    for name in (
        "hla-1516-2025",
        "hla-1516.1-2025",
        "hla-1516.2-2025",
    )
)


class QueryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_document_model(DOCUMENT_ROOTS[1], HLA_SOURCE)
        cls.corpus = ComplianceCorpus(
            documents=tuple(load_document_model(root, HLA_SOURCE) for root in DOCUMENT_ROOTS)
        )

    def test_legacy_mapping_has_structured_implementation_reference(self) -> None:
        mapping = next(
            item for item in self.model.implementations if item.id == "rti.service.connect"
        )
        self.assertIsInstance(mapping.implementation_ref, ImplementationReference)
        self.assertEqual(mapping.implementation_ref.symbol, mapping.implementation)
        self.assertEqual(
            ImplementationMapping.model_validate(mapping.model_dump()),
            mapping,
        )

    def test_typed_applicability_explains_requirement_relationships(self) -> None:
        matches = self.model.query_requirements_applicable_after(
            "federate.not-connected",
            "Connect",
            "federate-lifetime",
        )
        self.assertEqual(
            {item.requirement_id for item in matches},
            {
                "req-federate-connect-before-rti-work",
                "req-connect-service-establishes-connection",
            },
        )
        self.assertTrue(all(item.machine_id == "federate-lifetime" for item in matches))
        self.assertTrue(all(item.transition_id == "federate.connect" for item in matches))
        self.assertEqual({item.relation for item in matches}, {"transition"})

    def test_compliance_query_is_serializable_and_distinguishes_planned(self) -> None:
        result = self.model.compliance_query(
            "federate.not-connected",
            "Connect",
            "federate-lifetime",
            require_concrete_implementation=True,
        )
        payload = result.model_dump(mode="json")
        self.assertEqual(payload["document_id"], "hla-1516.1-2025")
        self.assertEqual(len(result.applicable_requirements), 2)
        self.assertEqual(len(result.transition_coverage), 1)
        self.assertEqual(result.transition_coverage[0].status, "planned")
        self.assertFalse(result.transition_coverage[0].concrete)
        self.assertEqual(result.implementation_status_counts["planned"], 20)
        self.assertTrue(any(item.code == "non-concrete-implementation" for item in result.issues))
        self.assertEqual(json.loads(result.model_dump_json())["event"], "Connect")

    def test_mapping_queries_cover_requirement_clause_interface_and_concrete_gaps(self) -> None:
        requirement_mappings = self.model.implementation_mappings_for_requirement(
            "req-federate-connect-before-rti-work"
        )
        self.assertEqual(tuple(item.id for item in requirement_mappings), ("rti.service.connect",))
        self.assertTrue(self.model.implementation_mappings_for_clause("clause-4.1.1"))
        self.assertEqual(
            len(self.model.implementation_mappings_for_interface("service")),
            159,
        )
        coverage = self.model.implementation_coverage_for_transition(
            "federate.connect", "federate-lifetime"
        )
        self.assertEqual(coverage.mapping_ids, ("rti.service.connect",))
        self.assertEqual(coverage.status, "planned")
        self.assertFalse(coverage.concrete)
        self.assertEqual(self.model.transitions_without_implementation_mapping(), ())
        self.assertEqual(len(self.model.transitions_without_concrete_implementation()), 297)

    def test_corpus_selects_a_document_for_the_same_query_api(self) -> None:
        result = self.corpus.compliance_query(
            "hla-1516.1-2025",
            "federate.not-connected",
            "Connect",
            "federate-lifetime",
        )
        self.assertEqual(result.document_id, "hla-1516.1-2025")
        self.assertEqual(len(result.applicable_requirements), 2)
        self.assertEqual(self.corpus.document("hla-1516.2-2025").document_id, "hla-1516.2-2025")

    def test_invalid_mapping_query_targets_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.model.implementation_mappings_for_requirement("missing")
        with self.assertRaises(ValueError):
            self.model.implementation_mappings_for_clause("missing")
        with self.assertRaises(ValueError):
            self.model.implementation_coverage_for_transition("missing")
        with self.assertRaises(ValidationError):
            ImplementationReference(symbol="")

    def test_cli_exposes_typed_applicability_and_mapping_filters(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "hla_lab.traceability.compliance",
                str(DOCUMENT_ROOTS[0]),
                str(DOCUMENT_ROOTS[1]),
                str(DOCUMENT_ROOTS[2]),
                "--document",
                "hla-1516.1-2025",
                "--machine",
                "federate-lifetime",
                "--state",
                "federate.not-connected",
                "--event",
                "Connect",
                "--transition-id",
                "federate.connect",
                "--implementation-status",
                "planned",
                "--json",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["applicability"]), 2)
        self.assertEqual(
            [item["id"] for item in payload["implementation_mappings"]],
            ["rti.service.connect"],
        )


if __name__ == "__main__":
    unittest.main()
