"""Repeatable semantic and compliance-contract checks for document model."""

from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import ValidationError

from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    DocumentModel,
    Reference,
    ReferenceTarget,
    Requirement,
    RequirementFile,
    SourceRef,
    State,
    StateMachine,
    Transition,
)
from hla_lab.corpus.hla_semantic import load_hla_corpus, load_hla_document_model

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


class DocumentModelTests(unittest.TestCase):
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

    def test_generated_requirement_title_uses_authoritative_source_span(self) -> None:
        requirement = next(
            item
            for item in self.lifecycle.requirements
            if item.id == "requirement-candidate-content-clauses-08-time-management-page-182-l43-13"
        )
        self.assertEqual(
            requirement.title,
            "Normative statement at content/clauses/08-time-management-page-182.tex:43",
        )

    def test_ordered_requirements_preserve_source_order_within_clauses(self) -> None:
        framework = self.models[0]
        self.assertEqual(
            [item.id for item in framework.ordered_requirements()[:10]],
            [f"summary-rule-{index}" for index in range(1, 11)],
        )

        omt = self.models[2]
        clause_four_a = [
            item
            for item in omt.ordered_requirements()
            if item.source.path.startswith("sections/semantic/clause-4a/")
        ]
        self.assertEqual(
            [(item.source.path, item.source.line) for item in clause_four_a[:2]],
            [
                ("sections/semantic/clause-4a/page-034.tex", 6),
                ("sections/semantic/clause-4a/page-034.tex", 14),
            ],
        )

    def test_requirement_order_contract_holds_for_both_editions(self) -> None:
        for year in ("2010", "2025"):
            roots = tuple(
                HLA_ROOT / f"hla-{suffix}-{year}"
                for suffix in ("1516", "1516.1", "1516.2")
            )
            for root in roots:
                with self.subTest(document=root.name):
                    model = load_hla_document_model(root)
                    ordered = model.ordered_requirements()
                    raw_position = {
                        item.id: index for index, item in enumerate(model.requirements)
                    }
                    clause_position = {
                        item.id: index for index, item in enumerate(model.ordered_clauses())
                    }
                    self.assertEqual(
                        [clause_position[item.clause_id] for item in ordered if item.clause_id],
                        sorted(clause_position[item.clause_id] for item in ordered if item.clause_id),
                    )
                    for clause_id in {item.clause_id for item in ordered}:
                        positions = [
                            raw_position[item.id]
                            for item in ordered
                            if item.clause_id == clause_id
                        ]
                        self.assertEqual(positions, sorted(positions))

    def test_source_clause_owners_use_active_service_sections(self) -> None:
        by_source = {
            (item.source.path, item.source.line): item.clause_id
            for item in self.lifecycle.requirements
        }
        expected = {
            ("content/clauses/06-object-management-page-112.tex", 48): "clause-6.1.12",
            ("content/clauses/07-ownership-management-page-162.tex", 16): "clause-7.8",
            ("content/clauses/07-ownership-management-page-163.tex", 24): "clause-7.8.4",
            ("content/clauses/05-declaration-management-page-093.tex", 17): "clause-5.4",
            ("content/clauses/05-declaration-management-page-097.tex", 20): "clause-5.8",
            ("content/clauses/04-federation-management-page-067.tex", 37): "clause-4.20",
            ("content/clauses/04-federation-management-page-072.tex", 17): "clause-4.26",
            ("content/clauses/04-federation-management-page-076.tex", 15): "clause-4.31",
            ("content/clauses/06-object-management-page-113.tex", 21): "clause-6.2",
            ("content/clauses/11-management-object-model-page-292.tex", 18): "clause-11.5",
        }
        for source, clause_id in expected.items():
            with self.subTest(source=source):
                self.assertEqual(by_source[source], clause_id)

    def test_ownership_and_temporal_state_machine_labels_are_consistent(self) -> None:
        ownership = next(
            item
            for item in self.lifecycle.state_machines
            if item.id == "establishing-ownership"
        )
        cancellation = next(
            item
            for item in ownership.transitions
            if item.id == "establishing.cancel-divestiture"
        )
        self.assertEqual(cancellation.target_state, "establishing.owned.not-divesting")
        self.assertEqual(cancellation.clause_id, "clause-7.14")
        divestiture_if_wanted = next(
            item
            for item in ownership.transitions
            if item.id == "establishing.divestiture-if-wanted"
        )
        self.assertEqual(
            divestiture_if_wanted.event,
            "Attribute Ownership Divestiture If Wanted",
        )
        self.assertEqual(divestiture_if_wanted.target_state, "establishing.unowned.choice")

        temporal = next(
            item for item in self.lifecycle.state_machines if item.id == "temporal-state"
        )
        asynchronous_disable = next(
            item for item in temporal.transitions if item.id == "temporal.async-disable"
        )
        self.assertEqual(asynchronous_disable.event, "Disable Asynchronous Delivery")
        self.assertEqual(
            temporal.layout.transitions["temporal.async-disable"].label,
            "Disable Asynchronous Delivery",
        )

    def test_source_refinements_are_explicit_and_traceable(self) -> None:
        expected = {
            "requirement-source-refinement-send-interaction-published-class": "clause-5.1.3",
            "requirement-source-refinement-available-attribute-declaration": "clause-5.1.2",
            "requirement-source-refinement-unpublication-pending-acquisition": "clause-5.3.3",
            "requirement-source-refinement-directed-interaction-ownership-delivery": "clause-5.12",
            "requirement-source-refinement-passive-subscription-delivery": "clause-3",
            "requirement-source-refinement-relaxed-ddm-delivery": "clause-9.1.8",
            "requirement-source-refinement-mom-service-report-file": "clause-11.6",
            "requirement-source-refinement-time-constrained-save-boundary": "clause-4.20",
            "requirement-source-refinement-connection-loss-automatic-resign": "clause-4",
            "requirement-source-refinement-guard-and-cross-machine-state-constraints": "clause-4",
            "requirement-source-refinement-service-exception-precedence": "clause-1",
            "requirement-source-refinement-object-state-completeness": "clause-1",
        }
        by_id = {item.id: item for item in self.lifecycle.requirements}
        for requirement_id, clause_id in expected.items():
            with self.subTest(requirement_id=requirement_id):
                requirement = by_id[requirement_id]
                self.assertEqual(requirement.clause_id, clause_id)
                self.assertEqual(requirement.extraction, "explicit")
                self.assertNotIn("%", requirement.statement)
                self.assertEqual(requirement.api_surface_scope, "cross-cutting")

    def test_rotated_table_continuations_and_rows_are_addressable(self) -> None:
        table_303 = next(item for item in self.lifecycle.tables if item.id == "table-5-p303")
        table_304 = next(item for item in self.lifecycle.tables if item.id == "table-5-p304")
        self.assertGreater(len(table_303.cells), 4)
        self.assertGreater(len(table_304.cells), 4)
        self.assertTrue(any("UserSuppliedTag" in cell.text for cell in table_303.cells))
        self.assertTrue(any("VariableLengthData" in cell.text for cell in table_304.cells))
        table_rows = {
            item.id: item
            for item in self.lifecycle.requirements
            if item.id.startswith("requirement-candidate-table-5-")
        }
        self.assertEqual(len(table_rows), 140)
        self.assertTrue(any("UserSuppliedTag" in item.statement for item in table_rows.values()))
        user_tag_cell = next(
            cell for cell in table_303.cells if "UserSuppliedTag" in cell.text
        )
        self.assertTrue(
            any(
                item.startswith("requirement-candidate-table-5-")
                for item in user_tag_cell.record_ids
            )
        )

    def test_cross_page_service_continuations_remain_discoverable(self) -> None:
        blocks = {item.id: item for item in self.lifecycle.content_blocks}
        page_142 = blocks["content-15161-page-142"]
        page_143 = blocks["content-15161-page-143"]
        self.assertTrue(
            {
                "requirement-candidate-content-clauses-06-object-management-page-141-l125-32",
                "requirement-candidate-content-clauses-06-object-management-page-141-l131-34",
                "requirement-candidate-content-clauses-06-object-management-page-141-l137-36",
                "requirement-candidate-content-clauses-06-object-management-page-141-l143-38",
            }
            <= set(page_142.record_ids)
        )
        self.assertIn(
            "requirement-candidate-content-clauses-06-object-management-page-142-l173-48",
            page_143.record_ids,
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
        self.assertEqual(unmapped, ())
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

    def test_duplicate_requirement_file_id_is_rejected(self) -> None:
        requirement = self.lifecycle.requirements[0].model_dump(mode="json")
        with self.assertRaises(ValidationError):
            RequirementFile.model_validate(
                {
                    "schema_version": 1,
                    "requirements": [requirement, requirement],
                }
            )

    def test_canonical_requirement_files_have_unique_ids(self) -> None:
        for path in sorted(HLA_ROOT.glob("*/semantic/requirements.json")):
            with self.subTest(path=path):
                RequirementFile.model_validate_json(path.read_text(encoding="utf-8"))

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
