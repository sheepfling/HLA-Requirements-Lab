"""M24 corpus-wide compliance projections and query contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.hla_profile import HLA_SOURCE
from scripts.semantic_model import (
    ComplianceCorpus,
    CrossReference,
    SourceRef,
    load_corpus,
    load_document_model,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_ROOTS = tuple(
    REPO_ROOT / "topics" / "ieee" / name
    for name in (
        "hla-1516-2025",
        "hla-1516.1-2025",
        "hla-1516.2-2025",
    )
)


class Milestone24Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_corpus(DOCUMENT_ROOTS, HLA_SOURCE)

    def test_requirements_and_state_sequence_implications_are_corpus_qualified(self) -> None:
        applicable = self.corpus.requirements_applicable_after(
            "federate.not-connected",
            "Connect",
            "hla-1516.1-2025",
            "federate-lifetime",
        )
        self.assertEqual(
            {item.requirement_id for item in applicable},
            {
                "req-federate-connect-before-rti-work",
                "req-connect-service-establishes-connection",
            },
        )
        implications = self.corpus.state_sequence_implications("hla-1516.1-2025")
        self.assertEqual(
            (
                sum(item.kind == "state-transition" for item in implications),
                sum(item.kind == "sequence-message" for item in implications),
            ),
            (281, 14),
        )
        filtered = self.corpus.state_sequence_implications(
            "hla-1516.1-2025",
            "federate.not-connected",
            "Connect",
            "federate-lifetime",
        )
        self.assertEqual(
            {item.record_id for item in filtered if item.kind == "state-transition"},
            {"federate.connect"},
        )
        self.assertTrue(all(item.document_id == "hla-1516.1-2025" for item in filtered))
        report = self.corpus.compliance_report()
        self.assertEqual(
            report.operational_implication_counts,
            {
                "direct": 281,
                "clause-context": 0,
                "unlinked": 14,
            },
        )
        self.assertEqual(
            report.table_definition_coverage["hla-1516.1-2025"]["cells_with_definition_links"],
            81,
        )
        self.assertEqual(
            report.table_definition_coverage["hla-1516.2-2025"]["cells_with_definition_links"],
            65,
        )
        self.corpus.assert_compliance_surfaces_classified()

    def test_dependency_projection_connects_tables_definitions_and_links(self) -> None:
        dependencies = self.corpus.table_definition_dependencies("hla-1516.2-2025")
        kinds = {item.source_kind for item in dependencies} | {
            item.target_kind for item in dependencies
        }
        self.assertTrue({"table", "table-family", "definition"} <= kinds)
        model = self.corpus.document("hla-1516.2-2025")
        definition_id = model.definitions[0].id
        definition_edges = self.corpus.dependencies_for_record(
            definition_id,
            "hla-1516.2-2025",
        )
        self.assertTrue(definition_edges)
        self.assertTrue(any(item.target_kind == "clause" for item in definition_edges))
        self.assertTrue(
            all(
                item.source_document_id == "hla-1516.2-2025"
                and item.target_document_id == "hla-1516.2-2025"
                for item in definition_edges
            )
        )

    def test_mapping_gaps_and_implementation_evidence_are_distinct(self) -> None:
        self.assertEqual(
            self.corpus.transitions_without_implementation_mappings("hla-1516.1-2025"),
            (),
        )
        non_concrete = self.corpus.transitions_without_concrete_implementations("hla-1516.1-2025")
        self.assertEqual(len(non_concrete), 281)
        planned = self.corpus.implementation_evidence(
            "hla-1516.1-2025",
            status="planned",
        )
        concrete = self.corpus.implementation_evidence(
            "hla-1516.1-2025",
            concrete=True,
        )
        self.assertEqual(len(planned), 281)
        self.assertEqual(concrete, ())
        self.assertTrue(all(not item.concrete for item in planned))
        self.assertTrue(all(not item.source_backed for item in planned))

    def test_unresolved_cross_document_targets_are_reported(self) -> None:
        model = load_document_model(DOCUMENT_ROOTS[0], HLA_SOURCE)
        bad = CrossReference(
            id="m24-unresolved-cross-reference",
            owner_id=model.cross_references[0].owner_id,
            target_document_id="missing-document",
            target_record_id="missing-record",
            label="missing",
            source=SourceRef(path="test", line=1),
        )
        mutated = model.model_copy(update={"cross_references": (*model.cross_references, bad)})
        report = ComplianceCorpus(documents=(mutated,)).unresolved_reference_issues()
        self.assertTrue(
            any(item.record_id.endswith("missing-document:missing-record") for item in report)
        )

    def test_m24_report_is_pydantic_serializable_and_cli_visible(self) -> None:
        report = self.corpus.compliance_report(
            "hla-1516.1-2025",
            "federate.not-connected",
            "Connect",
            "federate-lifetime",
            require_concrete_implementation=True,
        )
        round_trip = type(report).model_validate_json(report.model_dump_json())
        self.assertEqual(round_trip, report)
        self.assertEqual(len(report.applicable_requirements), 2)
        self.assertTrue(any(item.code == "non-concrete-implementation" for item in report.issues))

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.compliance",
                str(DOCUMENT_ROOTS[1]),
                "--document",
                "hla-1516.1-2025",
                "--corpus-report",
                "--implementation-evidence-status",
                "planned",
                "--json",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["compliance_corpus"]["document_ids"], ["hla-1516.1-2025"])
        self.assertEqual(len(payload["compliance_corpus"]["implementation_evidence"]), 281)


if __name__ == "__main__":
    unittest.main()
