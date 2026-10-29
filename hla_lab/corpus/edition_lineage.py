"""Typed, reviewable semantic lineage across editions of a document family.

This module intentionally has no HLA vocabulary.  A lineage relation records a
human-reviewed correspondence between stable semantic records from two
editions; it never infers equivalence from similar wording or clause numbers.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hla_lab.core.semantic_model import ComplianceCorpus

__all__ = [
    "EditionComparison",
    "EditionDocument",
    "EditionLineageManifest",
    "EditionRelation",
    "LineageRecord",
    "LineageRelationKind",
    "RecordKind",
    "ReviewStatus",
    "load_edition_lineage",
]

RecordKind = Literal[
    "requirement",
    "definition",
    "clause",
    "table",
    "state-machine",
    "transition",
]
LineageRelationKind = Literal["unchanged", "revised", "split", "merged", "added", "removed"]
ReviewStatus = Literal["draft", "reviewed", "verified"]


class LineageRecord(BaseModel):
    """One version-specific semantic record participating in a lineage relation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: Annotated[str, Field(min_length=1)]
    record_id: Annotated[str, Field(min_length=1)]
    kind: RecordKind


class EditionDocument(BaseModel):
    """Identity of one edition kept in a lineage manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: Annotated[str, Field(min_length=1)]
    standard_id: Annotated[str, Field(min_length=1)]
    edition: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    # Repository-local adapters may use these optional fields to resolve the
    # source tree and its profile without duplicating document IDs in code.
    # They remain optional so the generic lineage contract can still be used
    # by standalone document families.
    root: str | None = None
    profile_id: str | None = None
    migration: str | None = None


class EditionRelation(BaseModel):
    """A reviewed semantic correspondence between two particular editions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, Field(min_length=1)]
    stable_id: Annotated[str, Field(min_length=1)]
    relation: LineageRelationKind
    baseline_document_id: Annotated[str, Field(min_length=1)]
    target_document_id: Annotated[str, Field(min_length=1)]
    baseline_records: tuple[LineageRecord, ...] = ()
    target_records: tuple[LineageRecord, ...] = ()
    review_status: ReviewStatus = "draft"
    rationale: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def validate_relation_shape(self) -> EditionRelation:
        if self.baseline_document_id == self.target_document_id:
            raise ValueError("edition relations must connect two different documents")
        self._validate_record_side("baseline", self.baseline_document_id, self.baseline_records)
        self._validate_record_side("target", self.target_document_id, self.target_records)
        self._validate_relation_cardinality()
        self._validate_record_kinds()
        return self

    @staticmethod
    def _validate_record_side(
        side: str,
        document_id: str,
        records: Sequence[LineageRecord],
    ) -> None:
        identifiers = [(item.document_id, item.record_id, item.kind) for item in records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{side} records must be unique within a relation")
        if any(item.document_id != document_id for item in records):
            raise ValueError(f"{side} records must belong to {document_id}")

    def _validate_relation_cardinality(self) -> None:
        baseline_count = len(self.baseline_records)
        target_count = len(self.target_records)
        if self.relation in {"unchanged", "revised"} and not (baseline_count and target_count):
            raise ValueError(f"{self.relation} relations require records on both sides")
        if self.relation == "split" and not (baseline_count == 1 and target_count >= 2):
            raise ValueError("split relations require one baseline and at least two target records")
        if self.relation == "merged" and not (baseline_count >= 2 and target_count == 1):
            raise ValueError("merged relations require at least two baseline and one target record")
        if self.relation == "added" and not (baseline_count == 0 and target_count >= 1):
            raise ValueError("added relations require no baseline and at least one target record")
        if self.relation == "removed" and not (baseline_count >= 1 and target_count == 0):
            raise ValueError(
                "removed relations require at least one baseline and no target records"
            )

    def _validate_record_kinds(self) -> None:
        kinds = {item.kind for item in (*self.baseline_records, *self.target_records)}
        if len(kinds) > 1:
            raise ValueError("a relation may only compare one semantic record kind")

    @property
    def record_kind(self) -> RecordKind:
        return next(iter((*self.baseline_records, *self.target_records))).kind


class EditionComparison(BaseModel):
    """Serializable side-by-side comparison for a selected pair of editions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline: EditionDocument
    target: EditionDocument
    record_kind: RecordKind | None = None
    relations: tuple[EditionRelation, ...]
    relation_counts: Mapping[str, int]
    unmapped_baseline_record_ids: tuple[str, ...] = ()
    unmapped_target_record_ids: tuple[str, ...] = ()


class EditionLineageManifest(BaseModel):
    """Source-controlled, reviewable lineage records for a document family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Annotated[int, Field(ge=1)] = 1
    documents: Annotated[tuple[EditionDocument, ...], Field(min_length=1)]
    relations: tuple[EditionRelation, ...] = ()

    @model_validator(mode="after")
    def validate_manifest(self) -> EditionLineageManifest:
        document_ids = [item.document_id for item in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("edition document IDs must be unique")
        relation_ids = [item.id for item in self.relations]
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("edition relation IDs must be unique")
        documents_by_id = {item.document_id: item for item in self.documents}
        known_documents = set(documents_by_id)
        seen_stable_pairs: set[tuple[str, str, str]] = set()
        for relation in self.relations:
            if {relation.baseline_document_id, relation.target_document_id} - known_documents:
                raise ValueError(f"relation {relation.id} references an unknown edition document")
            if (
                documents_by_id[relation.baseline_document_id].standard_id
                != documents_by_id[relation.target_document_id].standard_id
            ):
                raise ValueError("edition relations must remain within one standard family")
            key = (relation.stable_id, relation.baseline_document_id, relation.target_document_id)
            if key in seen_stable_pairs:
                raise ValueError("stable IDs may occur only once for an edition pair")
            seen_stable_pairs.add(key)
        return self

    def document(self, document_id: str) -> EditionDocument:
        try:
            return next(item for item in self.documents if item.document_id == document_id)
        except StopIteration as error:
            known = ", ".join(item.document_id for item in self.documents)
            raise ValueError(f"unknown edition document {document_id}; known: {known}") from error

    def comparison(
        self,
        baseline_document_id: str,
        target_document_id: str,
        *,
        record_kind: RecordKind | None = None,
        reviewed_only: bool = False,
        corpus: ComplianceCorpus | None = None,
    ) -> EditionComparison:
        """Return reviewed source/target relations and optional coverage gaps."""
        baseline = self.document(baseline_document_id)
        target = self.document(target_document_id)
        if baseline.standard_id != target.standard_id:
            raise ValueError("edition comparisons must remain within one standard family")
        relations = tuple(
            item
            for item in self.relations
            if item.baseline_document_id == baseline_document_id
            and item.target_document_id == target_document_id
            and (record_kind is None or item.record_kind == record_kind)
            and (not reviewed_only or item.review_status in {"reviewed", "verified"})
        )
        relations = tuple(sorted(relations, key=lambda item: (item.stable_id, item.id)))
        counts = dict(sorted(Counter(item.relation for item in relations).items()))
        baseline_unmapped: tuple[str, ...] = ()
        target_unmapped: tuple[str, ...] = ()
        if corpus is not None and record_kind is not None:
            self.validate_against_corpus(
                corpus,
                document_ids=(baseline_document_id, target_document_id),
            )
            baseline_linked = {
                item.record_id for relation in relations for item in relation.baseline_records
            }
            target_linked = {
                item.record_id for relation in relations for item in relation.target_records
            }
            baseline_unmapped = tuple(
                sorted(
                    _corpus_record_ids(corpus, baseline_document_id, record_kind) - baseline_linked
                )
            )
            target_unmapped = tuple(
                sorted(_corpus_record_ids(corpus, target_document_id, record_kind) - target_linked)
            )
        return EditionComparison(
            baseline=baseline,
            target=target,
            record_kind=record_kind,
            relations=relations,
            relation_counts=counts,
            unmapped_baseline_record_ids=baseline_unmapped,
            unmapped_target_record_ids=target_unmapped,
        )

    def validate_against_corpus(
        self,
        corpus: ComplianceCorpus,
        *,
        document_ids: Iterable[str] | None = None,
    ) -> EditionLineageManifest:
        """Reject lineage records that point at absent corpus documents or records.

        A comparison may intentionally load only the two documents being
        compared.  In that case, validate the selected pair instead of
        requiring every document registered in the repository-wide manifest.
        The default remains strict and validates the complete manifest.
        """
        corpus_documents = {item.document_id for item in corpus.documents}
        required_documents = (
            set(document_ids)
            if document_ids is not None
            else {item.document_id for item in self.documents}
        )
        unknown_documents = required_documents - {item.document_id for item in self.documents}
        if unknown_documents:
            raise ValueError(
                "edition lineage documents are not registered: "
                + ", ".join(sorted(unknown_documents))
            )
        missing_documents = required_documents - corpus_documents
        if missing_documents:
            raise ValueError(
                "edition lineage documents are absent from the corpus: "
                + ", ".join(sorted(missing_documents))
            )
        for relation in self.relations:
            if (
                document_ids is not None
                and {
                    relation.baseline_document_id,
                    relation.target_document_id,
                }
                - required_documents
            ):
                continue
            for record in (*relation.baseline_records, *relation.target_records):
                if record.record_id not in _corpus_record_ids(
                    corpus, record.document_id, record.kind
                ):
                    raise ValueError(
                        f"lineage relation {relation.id} references missing {record.kind} "
                        f"{record.document_id}:{record.record_id}"
                    )
        return self


def _corpus_record_ids(
    corpus: ComplianceCorpus,
    document_id: str,
    record_kind: RecordKind,
) -> set[str]:
    """Return IDs of one lineage-supported record family from a corpus document."""
    document = corpus.document(document_id)
    if record_kind == "transition":
        return {item.id for machine in document.state_machines for item in machine.transitions}
    attribute = {
        "requirement": "requirements",
        "definition": "definitions",
        "clause": "clauses",
        "table": "tables",
        "state-machine": "state_machines",
    }[record_kind]
    return {item.id for item in getattr(document, attribute)}


def load_edition_lineage(path: Path) -> EditionLineageManifest:
    """Load and validate a source-controlled edition-lineage manifest."""
    return EditionLineageManifest.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Query reviewed cross-edition semantic lineage.")
    parser.add_argument("manifest", type=Path, help="Edition-lineage JSON manifest")
    parser.add_argument("--baseline", required=True, help="Baseline document ID")
    parser.add_argument("--target", required=True, help="Target document ID")
    parser.add_argument("--kind", choices=RecordKind.__args__, help="Optional semantic record kind")
    parser.add_argument("--reviewed-only", action="store_true", help="Omit draft relations")
    parser.add_argument(
        "--json", action="store_true", help="Print JSON rather than a concise summary"
    )
    args = parser.parse_args()
    comparison = load_edition_lineage(args.manifest).comparison(
        args.baseline,
        args.target,
        record_kind=args.kind,
        reviewed_only=args.reviewed_only,
    )
    if args.json:
        print(comparison.model_dump_json(indent=2))
    else:
        print(f"{comparison.baseline.title} -> {comparison.target.title}")
        print(
            ", ".join(f"{kind}: {count}" for kind, count in comparison.relation_counts.items())
            or "no relations"
        )
        for relation in comparison.relations:
            print(f"{relation.stable_id}\t{relation.relation}\t{relation.review_status}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
