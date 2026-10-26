"""Compare a Requirements Lab backflow snapshot with two validated corpus bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import cast

from hla_lab.traceability.compliance_contract import BundleRequirement, CorpusBundle
from tools.backflow_contracts import (
    BackflowExportDelta,
    BackflowIssueDelta,
    BackflowSnapshot,
    BundleDigest,
    CreatedRequirementDelta,
    ReadableChangeValue,
    ReadableRequirementField,
    RequirementDelta,
    RequirementField,
    RequirementFieldChange,
    UnattributedChangedRequirement,
    UnattributedCreatedChange,
    UnattributedRemovedChange,
    UnattributedRequirementChange,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_hash(record: BundleRequirement) -> str:
    stable_record = record.model_dump(mode="json", exclude={"ordinal"})
    encoded = json.dumps(
        stable_record, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return _sha256(encoded)


def requirement_delta(before: BundleRequirement, after: BundleRequirement) -> RequirementDelta:
    """Describe an exported requirement change without duplicating its source text."""
    if before.id != after.id:
        raise ValueError("requirement delta requires matching stable IDs")

    field_changes: tuple[tuple[RequirementField, bool], ...] = (
        ("id", before.id != after.id),
        ("clause", before.clause != after.clause),
        ("clause_id", before.clause_id != after.clause_id),
        ("title", before.title != after.title),
        ("statement", before.statement != after.statement),
        ("machine_statement", before.machine_statement != after.machine_statement),
        ("kind", before.kind != after.kind),
        ("coverage_kind", before.coverage_kind != after.coverage_kind),
        ("coverage_note", before.coverage_note != after.coverage_note),
        ("transition_ids", before.transition_ids != after.transition_ids),
        ("api_surface_scope", before.api_surface_scope != after.api_surface_scope),
        ("api_surface_note", before.api_surface_note != after.api_surface_note),
        ("api_surface_resolution", before.api_surface_resolution != after.api_surface_resolution),
        ("extraction", before.extraction != after.extraction),
        ("semantic_group_id", before.semantic_group_id != after.semantic_group_id),
        ("source", before.source != after.source),
    )
    changed_fields = cast(
        list[RequirementField], sorted(field for field, changed in field_changes if changed)
    )
    readable_values: dict[
        ReadableRequirementField, tuple[ReadableChangeValue, ReadableChangeValue]
    ] = {
        "clause": (before.clause, after.clause),
        "clause_id": (before.clause_id, after.clause_id),
        "kind": (before.kind, after.kind),
        "extraction": (before.extraction, after.extraction),
        "semantic_group_id": (before.semantic_group_id, after.semantic_group_id),
        "source": (before.source, after.source),
    }
    readable_fields: tuple[ReadableRequirementField, ...] = (
        "clause",
        "clause_id",
        "extraction",
        "kind",
        "semantic_group_id",
        "source",
    )
    readable_changes: dict[ReadableRequirementField, RequirementFieldChange] = {}
    for field in readable_fields:
        if field in changed_fields:
            values = readable_values[field]
            readable_changes[field] = RequirementFieldChange(before=values[0], after=values[1])
    return RequirementDelta(
        id=after.id,
        changed_fields=changed_fields,
        readable_changes=readable_changes,
        before_sha256=_record_hash(before),
        after_sha256=_record_hash(after),
    )


def _requirement_index(bundle: CorpusBundle) -> dict[str, dict[str, BundleRequirement]]:
    documents: dict[str, dict[str, BundleRequirement]] = {}
    for document in bundle.documents:
        if document.document_id in documents:
            raise ValueError(f"duplicate document {document.document_id}")
        records: dict[str, BundleRequirement] = {}
        for item in document.requirements:
            if item.id in records:
                raise ValueError(f"duplicate requirement {item.id} in {document.document_id}")
            records[item.id] = item
        documents[document.document_id] = records
    return documents


def build_delta(
    snapshot: BackflowSnapshot,
    baseline: CorpusBundle,
    candidate: CorpusBundle,
    *,
    baseline_sha256: str,
    candidate_sha256: str,
) -> BackflowExportDelta:
    """Return ordered issue deltas, rejecting missing stable IDs or untouched repairs."""
    before_by_document = _requirement_index(baseline)
    after_by_document = _requirement_index(candidate)
    issues = snapshot.issues
    if len({issue.id for issue in issues}) != len(issues):
        raise ValueError("duplicate issue ID in backflow snapshot")
    results: list[BackflowIssueDelta] = []
    attributed: dict[str, set[str]] = {}
    for issue in issues:
        document_id = issue.document_id
        attributed.setdefault(document_id, set()).update(issue.affected_requirement_ids)
        attributed[document_id].update(issue.created_requirement_ids)
        if issue.resolution is None:
            raise ValueError(f"missing resolution for backflow issue: {issue.id}")
        try:
            before = before_by_document[document_id]
            after = after_by_document[document_id]
        except KeyError as error:
            raise ValueError(f"missing export document for {issue.id}: {document_id}") from error
        affected: list[RequirementDelta] = []
        for requirement_id in issue.affected_requirement_ids:
            if requirement_id not in before or requirement_id not in after:
                raise ValueError(f"missing stable requirement for {issue.id}: {requirement_id}")
            delta = requirement_delta(before[requirement_id], after[requirement_id])
            if issue.resolution == "corrected-in-lab" and not delta.changed_fields:
                raise ValueError(f"corrected issue has unchanged requirement: {issue.id}")
            affected.append(delta)
        created: list[CreatedRequirementDelta] = []
        for requirement_id in issue.created_requirement_ids:
            if requirement_id in before or requirement_id not in after:
                raise ValueError(f"invalid new requirement for {issue.id}: {requirement_id}")
            created.append(
                CreatedRequirementDelta(
                    id=requirement_id, after_sha256=_record_hash(after[requirement_id])
                )
            )
        if issue.resolution == "corrected-in-lab" and not (affected or created):
            raise ValueError(f"corrected issue has no exported requirement: {issue.id}")
        results.append(
            BackflowIssueDelta(
                id=issue.id,
                resolution=issue.resolution,
                document_id=document_id,
                affected=affected,
                created=created,
            )
        )
    unattributed: list[UnattributedRequirementChange] = []
    for document_id in sorted(before_by_document.keys() | after_by_document.keys()):
        before = before_by_document.get(document_id, {})
        after = after_by_document.get(document_id, {})
        excluded = attributed.get(document_id, set())
        for requirement_id in sorted((before.keys() | after.keys()) - excluded):
            if requirement_id not in before and requirement_id in after:
                unattributed.append(
                    UnattributedCreatedChange(
                        document_id=document_id,
                        change="created",
                        id=requirement_id,
                        after_sha256=_record_hash(after[requirement_id]),
                    )
                )
            elif requirement_id in before and requirement_id not in after:
                unattributed.append(
                    UnattributedRemovedChange(
                        document_id=document_id,
                        change="removed",
                        id=requirement_id,
                        before_sha256=_record_hash(before[requirement_id]),
                    )
                )
            else:
                delta = requirement_delta(before[requirement_id], after[requirement_id])
                if delta.changed_fields:
                    unattributed.append(
                        UnattributedChangedRequirement(
                            document_id=document_id,
                            change="changed",
                            id=delta.id,
                            changed_fields=delta.changed_fields,
                            readable_changes=delta.readable_changes,
                            before_sha256=delta.before_sha256,
                            after_sha256=delta.after_sha256,
                        )
                    )
    return BackflowExportDelta(
        schema_version=1,
        baseline=BundleDigest(
            bundle_id=baseline.bundle_id,
            corpus_revision=baseline.corpus_revision,
            sha256=baseline_sha256,
        ),
        candidate=BundleDigest(
            bundle_id=candidate.bundle_id,
            corpus_revision=candidate.corpus_revision,
            sha256=candidate_sha256,
        ),
        issues=results,
        unattributed_requirement_changes=unattributed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = BackflowSnapshot.model_validate_json(args.snapshot.read_text(encoding="utf-8"))
    baseline_bytes = args.baseline.read_bytes()
    candidate_bytes = args.candidate.read_bytes()
    delta = build_delta(
        snapshot,
        CorpusBundle.model_validate_json(baseline_bytes),
        CorpusBundle.model_validate_json(candidate_bytes),
        baseline_sha256=_sha256(baseline_bytes),
        candidate_sha256=_sha256(candidate_bytes),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(delta.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(delta.issues)} issue deltas to {args.output}")


if __name__ == "__main__":
    main()
