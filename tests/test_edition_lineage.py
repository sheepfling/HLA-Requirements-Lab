"""Cross-edition lineage contracts use reviewed semantic IDs, not text matching."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from hla_lab.core.semantic_model import ComplianceCorpus, DocumentModel, Requirement, SourceRef
from hla_lab.corpus.edition_lineage import (
    EditionDocument,
    EditionLineageManifest,
    EditionRelation,
    LineageRecord,
)

def requirement(identifier: str) -> Requirement:
    return Requirement(
        id=identifier,
        title=identifier,
        statement=f"{identifier} statement",
        kind="detailed",
        clause=None,
        coverage_kind="document-wide",
        coverage_note="Synthetic cross-edition test requirement.",
        source=SourceRef(path="fixture.tex", line=1),
    )

def document(identifier: str, requirements: tuple[str, ...]) -> DocumentModel:
    return DocumentModel(
        document_id=identifier,
        clauses=(),
        definitions=(),
        requirements=tuple(requirement(item) for item in requirements),
    )

class EditionLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = "sample-2010"
        self.target = "sample-2025"
        self.documents = (
            EditionDocument(
                document_id=self.baseline,
                standard_id="sample-standard",
                edition="2010",
                title="Sample Standard 2010",
            ),
            EditionDocument(
                document_id=self.target,
                standard_id="sample-standard",
                edition="2025",
                title="Sample Standard 2025",
            ),
        )

    def test_side_by_side_requirement_comparison_reports_relations_and_gaps(self) -> None:
        manifest = EditionLineageManifest(
            documents=self.documents,
            relations=(
                EditionRelation(
                    id="join-2010-to-2025",
                    stable_id="federation.join",
                    relation="revised",
                    baseline_document_id=self.baseline,
                    target_document_id=self.target,
                    baseline_records=(
                        LineageRecord(
                            document_id=self.baseline,
                            record_id="join-2010",
                            kind="requirement",
                        ),
                    ),
                    target_records=(
                        LineageRecord(
                            document_id=self.target,
                            record_id="join-2025",
                            kind="requirement",
                        ),
                    ),
                    review_status="verified",
                    rationale="The target edition makes the precondition explicit.",
                ),
                EditionRelation(
                    id="resign-removed",
                    stable_id="federation.resign.legacy",
                    relation="removed",
                    baseline_document_id=self.baseline,
                    target_document_id=self.target,
                    baseline_records=(
                        LineageRecord(
                            document_id=self.baseline,
                            record_id="resign-2010",
                            kind="requirement",
                        ),
                    ),
                    review_status="reviewed",
                    rationale="The legacy behavior was removed from the target edition.",
                ),
                EditionRelation(
                    id="disconnect-added",
                    stable_id="federation.disconnect.recovery",
                    relation="added",
                    baseline_document_id=self.baseline,
                    target_document_id=self.target,
                    target_records=(
                        LineageRecord(
                            document_id=self.target,
                            record_id="disconnect-2025",
                            kind="requirement",
                        ),
                    ),
                    review_status="reviewed",
                    rationale="The target edition adds an explicit recovery requirement.",
                ),
            ),
        )
        corpus = ComplianceCorpus(
            documents=(
                document(self.baseline, ("join-2010", "resign-2010", "unmapped-2010")),
                document(self.target, ("join-2025", "disconnect-2025", "unmapped-2025")),
            )
        )

        comparison = manifest.comparison(
            self.baseline,
            self.target,
            record_kind="requirement",
            reviewed_only=True,
            corpus=corpus,
        )

        self.assertEqual(comparison.relation_counts, {"added": 1, "removed": 1, "revised": 1})
        self.assertEqual(comparison.unmapped_baseline_record_ids, ("unmapped-2010",))
        self.assertEqual(comparison.unmapped_target_record_ids, ("unmapped-2025",))
        self.assertEqual(
            EditionLineageManifest.model_validate_json(manifest.model_dump_json()), manifest
        )

    def test_invalid_relation_shapes_and_missing_corpus_records_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            EditionRelation(
                id="invalid-split",
                stable_id="invalid",
                relation="split",
                baseline_document_id=self.baseline,
                target_document_id=self.target,
                baseline_records=(
                    LineageRecord(
                        document_id=self.baseline,
                        record_id="one",
                        kind="requirement",
                    ),
                ),
                target_records=(
                    LineageRecord(
                        document_id=self.target,
                        record_id="only-one",
                        kind="requirement",
                    ),
                ),
                rationale="A split needs more than one target record.",
            )

        manifest = EditionLineageManifest(
            documents=self.documents,
            relations=(
                EditionRelation(
                    id="missing-record",
                    stable_id="missing",
                    relation="revised",
                    baseline_document_id=self.baseline,
                    target_document_id=self.target,
                    baseline_records=(
                        LineageRecord(
                            document_id=self.baseline,
                            record_id="missing",
                            kind="requirement",
                        ),
                    ),
                    target_records=(
                        LineageRecord(
                            document_id=self.target,
                            record_id="present",
                            kind="requirement",
                        ),
                    ),
                    rationale="Deliberately invalid fixture.",
                ),
            ),
        )
        corpus = ComplianceCorpus(
            documents=(document(self.baseline, ()), document(self.target, ("present",)))
        )
        with self.assertRaisesRegex(ValueError, "missing requirement"):
            manifest.validate_against_corpus(corpus)

    def test_relations_cannot_cross_standard_families(self) -> None:
        other = EditionDocument(
            document_id="other-2025",
            standard_id="other-standard",
            edition="2025",
            title="Other Standard 2025",
        )
        relation = EditionRelation(
            id="cross-family",
            stable_id="invalid.cross-family",
            relation="revised",
            baseline_document_id=self.baseline,
            target_document_id=other.document_id,
            baseline_records=(
                LineageRecord(
                    document_id=self.baseline,
                    record_id="one",
                    kind="requirement",
                ),
            ),
            target_records=(
                LineageRecord(
                    document_id=other.document_id,
                    record_id="two",
                    kind="requirement",
                ),
            ),
            rationale="Deliberately invalid fixture.",
        )
        with self.assertRaisesRegex(ValueError, "standard family"):
            EditionLineageManifest(documents=(*self.documents, other), relations=(relation,))

if __name__ == "__main__":
    unittest.main()
