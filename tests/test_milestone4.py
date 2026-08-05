"""Repeatable semantic and compliance-contract checks for Milestone 4."""

from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import ValidationError

from scripts.hla_semantic import load_hla_corpus, load_hla_document_model
from scripts.semantic_model import (
    ComplianceCorpus,
    DocumentModel,
    Reference,
    ReferenceTarget,
    Requirement,
    SourceRef,
    State,
    StateMachine,
    Transition,
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
SOURCE = SourceRef(path="test", line=1)


class Milestone4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.models = tuple(load_hla_document_model(root) for root in DOCUMENT_ROOTS)
        cls.corpus = load_hla_corpus(DOCUMENT_ROOTS)
        cls.lifecycle = next(
            model for model in cls.models if model.document_id == "hla-1516.1-2025"
        )

    def test_all_documents_round_trip_through_pydantic(self) -> None:
        self.assertEqual(
            [model.from_json(model.to_json()).document_id for model in self.models],
            [model.document_id for model in self.models],
        )

    def test_requirement_defaults_to_a_generic_machine_statement(self) -> None:
        requirement = Requirement(
            id="generic-requirement",
            title="Generic requirement",
            statement=r"The service shall use \textbf{typed} data.",
            kind="detailed",
            clause=None,
            extraction="candidate",
            source=SOURCE,
        )
        self.assertEqual(
            requirement.machine_statement,
            "The service shall use typed data.",
        )

    def test_state_event_query_uses_reviewed_links(self) -> None:
        requirements = self.lifecycle.requirements_applicable_after(
            "federate.not-connected",
            "Connect",
            "federate-lifetime",
        )
        self.assertEqual(
            [item.id for item in requirements],
            [
                "req-federate-connect-before-rti-work",
                "req-connect-service-establishes-connection",
            ],
        )

    def test_unmapped_transition_query_is_explicit(self) -> None:
        unmapped = self.lifecycle.transitions_missing_implementation_mapping("federate-lifetime")
        self.assertIn("federate.resign", {item.id for item in unmapped})
        self.assertNotIn("federate.connect", {item.id for item in unmapped})

    def test_documents_without_state_machines_report_orphan_requirements(self) -> None:
        issues = self.models[0].compliance_issues()
        self.assertEqual(sum(issue.code == "orphan-requirement" for issue in issues), 0)
        candidate_issues = self.models[0].compliance_issues(include_candidates=True)
        self.assertEqual(
            sum(issue.code == "orphan-requirement" for issue in candidate_issues),
            sum(item.extraction == "candidate" for item in self.models[0].requirements),
        )

    def test_invalid_state_target_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            StateMachine(
                id="invalid",
                title="Invalid",
                states=(State(id="known", label="Known", source=SOURCE),),
                transitions=(
                    Transition(
                        id="invalid.transition",
                        source_state="known",
                        event="event",
                        target_state="missing",
                    ),
                ),
            )

    def test_unresolved_requirement_link_is_rejected(self) -> None:
        payload = self.lifecycle.model_dump(mode="json")
        payload["requirement_links"] = [
            {
                "id": "invalid-link",
                "requirement_id": "missing-requirement",
                "transition_id": "federate.connect",
            }
        ]
        with self.assertRaises(ValidationError):
            DocumentModel.model_validate(payload)

    def test_duplicate_implementation_id_is_rejected(self) -> None:
        payload = self.lifecycle.model_dump(mode="json")
        payload["implementations"].append(payload["implementations"][0])
        with self.assertRaises(ValidationError):
            DocumentModel.model_validate(payload)

    def test_nonreciprocal_implementation_link_is_rejected(self) -> None:
        payload = self.lifecycle.model_dump(mode="json")
        machine = next(
            item for item in payload["state_machines"] if item["id"] == "federate-lifetime"
        )
        transition = next(
            item for item in machine["transitions"] if item["id"] == "federate.connect"
        )
        transition.pop("implementation_ids")
        with self.assertRaises(ValidationError):
            DocumentModel.model_validate(payload)

    def test_content_block_record_links_are_validated(self) -> None:
        payload = self.lifecycle.model_dump(mode="json")
        payload["content_blocks"][0]["record_ids"] = ["missing-record"]
        with self.assertRaises(ValidationError):
            DocumentModel.model_validate(payload)

    def test_table_family_links_are_validated(self) -> None:
        omt = self.models[2]
        payload = omt.model_dump(mode="json")
        payload["table_families"][0]["table_ids"] = ["missing-table"]
        with self.assertRaises(ValidationError):
            DocumentModel.model_validate(payload)

    def test_cross_document_unresolved_target_is_reported(self) -> None:
        source_model = self.models[0]
        reference = Reference(
            id="synthetic-reference",
            label="[S]",
            text="Synthetic reference",
            targets=(ReferenceTarget(document_id="missing-document", record_id="clause-1"),),
            source=SOURCE,
        )
        modified = source_model.model_copy(
            update={"references": (*source_model.references, reference)}
        )
        corpus = ComplianceCorpus(
            documents=(modified, *self.models[1:]),
        )
        issues = corpus.unresolved_reference_issues()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "unresolved-reference")


if __name__ == "__main__":
    unittest.main()
