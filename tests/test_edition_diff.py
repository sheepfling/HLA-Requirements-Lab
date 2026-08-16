"""Differential edition reports preserve reviewed versus unmapped meaning."""

from __future__ import annotations

import unittest

from hla_lab.core.semantic_model import (
    Clause,
    DocumentModel,
    Requirement,
    RequirementLink,
    SourceRef,
    State,
    StateMachine,
    Transition,
)
from hla_lab.corpus.edition_lineage import (
    EditionDocument,
    EditionLineageManifest,
    EditionRelation,
    LineageRecord,
)
from hla_lab.corpus.hla_edition_diff import build_report

def _requirement(identifier: str, transition_id: str) -> Requirement:
    return Requirement(
        id=identifier,
        title=identifier,
        statement=f"{identifier} statement",
        kind="detailed",
        clause="1",
        transition_ids=(transition_id,),
        source=SourceRef(path="source.tex", line=1),
    )

def _document(
    identifier: str,
    requirement_id: str,
    machine_id: str,
    transition_id: str,
) -> DocumentModel:
    return DocumentModel(
        document_id=identifier,
        clauses=(
            Clause(
                id="clause-1",
                number="1",
                title="Lifecycle",
                parent_id=None,
                level=1,
                source=SourceRef(path="source.tex", line=1),
            ),
        ),
        definitions=(),
        requirements=(_requirement(requirement_id, transition_id),),
        requirement_links=(
            RequirementLink(
                id=f"link-{requirement_id}",
                requirement_id=requirement_id,
                transition_id=transition_id,
            ),
        ),
        state_machines=(
            StateMachine(
                id=machine_id,
                title=machine_id,
                states=(State(id="initial", label="Initial"), State(id="ready", label="Ready")),
                transitions=(
                    Transition(
                        id=transition_id,
                        source_state="initial",
                        event="start",
                        target_state="ready",
                        requirement_ids=(requirement_id,),
                    ),
                ),
                initial_state_ids=("initial",),
            ),
        ),
    )

class EditionDifferentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline_id = "hla-sample-2010"
        self.target_id = "hla-sample-2025"
        self.manifest = EditionLineageManifest(
            documents=(
                EditionDocument(
                    document_id=self.baseline_id,
                    standard_id="sample-standard",
                    edition="2010",
                    title="Sample 2010",
                ),
                EditionDocument(
                    document_id=self.target_id,
                    standard_id="sample-standard",
                    edition="2025",
                    title="Sample 2025",
                ),
            ),
            relations=(
                EditionRelation(
                    id="machine-relation",
                    stable_id="lifecycle",
                    relation="revised",
                    baseline_document_id=self.baseline_id,
                    target_document_id=self.target_id,
                    baseline_records=(
                        LineageRecord(
                            document_id=self.baseline_id,
                            record_id="machine-2010",
                            kind="state-machine",
                        ),
                    ),
                    target_records=(
                        LineageRecord(
                            document_id=self.target_id,
                            record_id="machine-2025",
                            kind="state-machine",
                        ),
                    ),
                    review_status="verified",
                    rationale="The lifecycle adds a target state.",
                ),
                EditionRelation(
                    id="requirement-relation",
                    stable_id="lifecycle.start",
                    relation="revised",
                    baseline_document_id=self.baseline_id,
                    target_document_id=self.target_id,
                    baseline_records=(
                        LineageRecord(
                            document_id=self.baseline_id,
                            record_id="req-2010",
                            kind="requirement",
                        ),
                    ),
                    target_records=(
                        LineageRecord(
                            document_id=self.target_id,
                            record_id="req-2025",
                            kind="requirement",
                        ),
                    ),
                    review_status="reviewed",
                    rationale="The requirement is clarified.",
                ),
            ),
        )
        self.baseline = _document(self.baseline_id, "req-2010", "machine-2010", "transition-2010")
        self.target = _document(self.target_id, "req-2025", "machine-2025", "transition-2025")

    def test_requirement_report_is_traceable_and_does_not_infer_additions(self) -> None:
        report = build_report(
            manifest=self.manifest,
            baseline=self.baseline,
            target=self.target,
            kind="requirement",
        )

        self.assertEqual(
            report["counts"],
            {
                "reviewed": 2,
                "baseline_unmapped": 0,
                "target_unmapped": 0,
                "target_machine_added": 0,
            },
        )
        rows = report["rows"]
        self.assertEqual({row["record_id"] for row in rows}, {"req-2010", "req-2025"})
        self.assertTrue(all(row["status"] == "reviewed" for row in rows))
        self.assertIn("not assertions", report["interpretation"])

    def test_state_machine_and_transition_reports_include_unmapped_inventory(self) -> None:
        state_report = build_report(
            manifest=self.manifest,
            baseline=self.baseline,
            target=self.target,
            kind="state-machine",
        )
        transition_report = build_report(
            manifest=self.manifest,
            baseline=self.baseline,
            target=self.target,
            kind="transition",
        )

        self.assertEqual(state_report["counts"]["reviewed"], 2)
        state_rows = state_report["rows"]
        self.assertEqual(
            state_rows[0]["transition_ids_added_in_target"]
            + state_rows[0]["transition_ids_removed_from_target"],
            ["transition-2025", "transition-2010"],
        )
        self.assertEqual(transition_report["counts"]["baseline_unmapped"], 1)
        self.assertEqual(transition_report["counts"]["target_unmapped"], 1)
        self.assertEqual(
            {row["record_id"] for row in transition_report["rows"]},
            {"transition-2010", "transition-2025"},
        )

    def test_transitions_in_reviewed_added_machine_are_classified_as_inherited_additions(
        self,
    ) -> None:
        added_machine = StateMachine(
            id="new-machine",
            title="New machine",
            states=(State(id="new-initial", label="Initial"),),
            transitions=(
                Transition(
                    id="new-transition",
                    source_state="new-initial",
                    event="new event",
                    target_state="new-initial",
                ),
            ),
            initial_state_ids=("new-initial",),
        )
        target = self.target.model_copy(
            update={"state_machines": (*self.target.state_machines, added_machine)}
        )
        manifest = self.manifest.model_copy(
            update={
                "relations": (
                    *self.manifest.relations,
                    EditionRelation(
                        id="added-machine",
                        stable_id="new-machine",
                        relation="added",
                        baseline_document_id=self.baseline_id,
                        target_document_id=self.target_id,
                        target_records=(
                            LineageRecord(
                                document_id=self.target_id,
                                record_id="new-machine",
                                kind="state-machine",
                            ),
                        ),
                        rationale="No baseline machine exists for this new surface.",
                    ),
                )
            }
        )

        report = build_report(
            manifest=manifest,
            baseline=self.baseline,
            target=target,
            kind="transition",
        )

        self.assertEqual(report["counts"]["target_machine_added"], 1)
        row = next(row for row in report["rows"] if row["record_id"] == "new-transition")
        self.assertEqual(row["status"], "target-machine-added")
        self.assertEqual(row["derived_from_state_machine"], "new-machine")

if __name__ == "__main__":
    unittest.main()
