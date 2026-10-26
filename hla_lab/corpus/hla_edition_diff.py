"""Compare HLA semantic requirements and state-machine surfaces by edition.

This is an HLA adapter over the generic edition-lineage contract.  It reports
reviewed lineage relations separately from records that have no reviewed
correspondence.  An unmatched record is deliberately called ``unmapped``;
it is not silently classified as an added or removed requirement.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict

from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    DocumentModel,
    Requirement,
    StateMachine,
    Transition,
)
from hla_lab.corpus.edition_lineage import (
    EditionComparison,
    EditionLineageManifest,
    EditionRelation,
    LineageRelationKind,
    load_edition_lineage,
)
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import repository_root, resources

__all__ = ["build_report", "main"]

RecordKind = Literal["requirement", "state-machine", "transition"]
Record = Requirement | StateMachine | tuple[StateMachine, Transition]
RecordIndex = dict[str, Record]
RowStatus = Literal[
    "reviewed",
    "baseline-unmapped",
    "target-unmapped",
    "target-machine-added",
]
_CsvValue: TypeAlias = str | int | float | bool | tuple[str, ...] | None
_CsvRow: TypeAlias = dict[str, _CsvValue]
_CsvOutputRow: TypeAlias = dict[str, str | int | float | bool | None]


class _DiffModel(BaseModel):
    """Immutable base for the edition-difference output contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class _DiffRowBase(_DiffModel):
    status: RowStatus
    relation: LineageRelationKind | None
    stable_id: str | None
    record_id: str


class RequirementDiffRow(_DiffRowBase):
    title: str
    statement: str
    clause_id: str | None
    extraction: str
    transition_ids: tuple[str, ...]
    source_path: str | None
    source_line: int | None


class StateMachineDiffRow(_DiffRowBase):
    title: str
    clause_id: str | None
    state_count: int
    transition_count: int
    state_ids: tuple[str, ...]
    transition_ids: tuple[str, ...]
    state_ids_added_in_target: tuple[str, ...]
    state_ids_removed_from_target: tuple[str, ...]
    transition_ids_added_in_target: tuple[str, ...]
    transition_ids_removed_from_target: tuple[str, ...]
    source_path: str | None
    source_line: int | None


class TransitionDiffRow(_DiffRowBase):
    machine_id: str
    source_state: str | None
    event: str
    target_state: str | None
    clause_id: str | None
    requirement_ids: tuple[str, ...]
    implementation_ids: tuple[str, ...]
    source_path: str | None
    source_line: int | None
    derived_from_state_machine: str | None = None


DiffRow = RequirementDiffRow | StateMachineDiffRow | TransitionDiffRow


class DiffCounts(_DiffModel):
    reviewed: int
    baseline_unmapped: int
    target_unmapped: int
    target_machine_added: int


class EditionDiffReport(_DiffModel):
    schema_version: Literal[1]
    record_kind: RecordKind
    baseline: str
    target: str
    lineage_relation_counts: Mapping[str, int]
    counts: DiffCounts
    interpretation: str
    rows: tuple[DiffRow, ...]


def _document_id(manifest: EditionLineageManifest, standard_id: str, edition: str) -> str:
    matches = tuple(
        item
        for item in manifest.documents
        if item.standard_id == standard_id and item.edition == edition
    )
    if len(matches) != 1:
        known = ", ".join(item.document_id for item in manifest.documents)
        raise ValueError(
            f"expected exactly one {standard_id} document for edition {edition}; known: {known}"
        )
    return matches[0].document_id


def _source_fields(
    record: Requirement | StateMachine | Transition,
) -> tuple[str | None, int | None]:
    source = record.source
    if source is None:
        return None, None
    return source.path, source.line


def _relation_fields(
    relation: EditionRelation | None,
) -> tuple[LineageRelationKind | None, str | None]:
    if relation is None:
        return None, None
    return relation.relation, relation.stable_id


def _requirement_row(
    record: Requirement, *, side: RowStatus, relation: EditionRelation | None = None
) -> RequirementDiffRow:
    relation_kind, stable_id = _relation_fields(relation)
    source_path, source_line = _source_fields(record)
    return RequirementDiffRow(
        status=side,
        relation=relation_kind,
        stable_id=stable_id,
        record_id=record.id,
        source_path=source_path,
        source_line=source_line,
        title=record.title,
        statement=record.statement,
        clause_id=record.clause_id,
        extraction=record.extraction,
        transition_ids=record.transition_ids,
    )


def _state_machine_row(
    record: StateMachine,
    *,
    side: RowStatus,
    relation: EditionRelation | None = None,
    state_ids_added: AbstractSet[str] | None = None,
    state_ids_removed: AbstractSet[str] | None = None,
    transition_ids_added: AbstractSet[str] | None = None,
    transition_ids_removed: AbstractSet[str] | None = None,
) -> StateMachineDiffRow:
    relation_kind, stable_id = _relation_fields(relation)
    source_path, source_line = _source_fields(record)
    return StateMachineDiffRow(
        status=side,
        relation=relation_kind,
        stable_id=stable_id,
        record_id=record.id,
        source_path=source_path,
        source_line=source_line,
        title=record.title,
        clause_id=record.clause_id,
        state_count=len(record.states),
        transition_count=len(record.transitions),
        state_ids=tuple(item.id for item in record.states),
        transition_ids=tuple(item.id for item in record.transitions),
        state_ids_added_in_target=tuple(sorted(state_ids_added or set())),
        state_ids_removed_from_target=tuple(sorted(state_ids_removed or set())),
        transition_ids_added_in_target=tuple(sorted(transition_ids_added or set())),
        transition_ids_removed_from_target=tuple(sorted(transition_ids_removed or set())),
    )


def _transition_row(
    machine: StateMachine,
    record: Transition,
    *,
    side: RowStatus,
    relation: EditionRelation | None = None,
) -> TransitionDiffRow:
    relation_kind, stable_id = _relation_fields(relation)
    source_path, source_line = _source_fields(record)
    return TransitionDiffRow(
        status=side,
        relation=relation_kind,
        stable_id=stable_id,
        record_id=record.id,
        source_path=source_path,
        source_line=source_line,
        machine_id=machine.id,
        source_state=record.source_state,
        event=record.event,
        target_state=record.target_state,
        clause_id=record.clause_id,
        requirement_ids=record.requirement_ids,
        implementation_ids=record.implementation_ids,
    )


def _record_index(model: DocumentModel, kind: RecordKind) -> RecordIndex:
    if kind == "requirement":
        return {item.id: item for item in model.requirements}
    if kind == "state-machine":
        return {item.id: item for item in model.state_machines}
    return {
        transition.id: (machine, transition)
        for machine in model.state_machines
        for transition in machine.transitions
    }


def _state_machine_delta_ids(
    relation: EditionRelation,
    baseline_index: Mapping[str, Record],
    target_index: Mapping[str, Record],
) -> tuple[set[str], set[str], set[str], set[str]]:
    baseline_machines = tuple(
        cast(StateMachine, baseline_index[item.record_id])
        for item in relation.baseline_records
        if item.kind == "state-machine"
    )
    target_machines = tuple(
        cast(StateMachine, target_index[item.record_id])
        for item in relation.target_records
        if item.kind == "state-machine"
    )
    baseline_states = {state.id for machine in baseline_machines for state in machine.states}
    target_states = {state.id for machine in target_machines for state in machine.states}
    baseline_transitions = {
        transition.id for machine in baseline_machines for transition in machine.transitions
    }
    target_transitions = {
        transition.id for machine in target_machines for transition in machine.transitions
    }
    return (
        target_states - baseline_states,
        baseline_states - target_states,
        target_transitions - baseline_transitions,
        baseline_transitions - target_transitions,
    )


def _record_row(
    record: Record,
    *,
    kind: RecordKind,
    side: RowStatus,
    relation: EditionRelation | None = None,
    state_ids_added: AbstractSet[str] = frozenset(),
    state_ids_removed: AbstractSet[str] = frozenset(),
    transition_ids_added: AbstractSet[str] = frozenset(),
    transition_ids_removed: AbstractSet[str] = frozenset(),
    added_target_machine_ids: AbstractSet[str] = frozenset(),
) -> DiffRow:
    if kind == "requirement":
        return _requirement_row(cast(Requirement, record), side=side, relation=relation)
    if kind == "state-machine":
        return _state_machine_row(
            cast(StateMachine, record),
            side=side,
            relation=relation,
            state_ids_added=state_ids_added,
            state_ids_removed=state_ids_removed,
            transition_ids_added=transition_ids_added,
            transition_ids_removed=transition_ids_removed,
        )
    machine, transition = cast(tuple[StateMachine, Transition], record)
    resolved_side = side
    if side == "target-unmapped" and machine.id in added_target_machine_ids:
        resolved_side = "target-machine-added"
    row = _transition_row(machine, transition, side=resolved_side, relation=relation)
    if resolved_side == "target-machine-added":
        row = row.model_copy(update={"derived_from_state_machine": machine.id})
    return row


def _relation_rows(
    relation: EditionRelation,
    baseline_index: Mapping[str, Record],
    target_index: Mapping[str, Record],
    *,
    kind: RecordKind,
    added_target_machine_ids: AbstractSet[str],
) -> tuple[list[DiffRow], set[str], set[str]]:
    baseline_records = [item for item in relation.baseline_records if item.kind == kind]
    target_records = [item for item in relation.target_records if item.kind == kind]
    state_delta = (
        _state_machine_delta_ids(relation, baseline_index, target_index)
        if kind == "state-machine"
        else (set(), set(), set(), set())
    )
    rows = [
        _record_row(
            record,
            kind=kind,
            side="reviewed",
            relation=relation,
            state_ids_added=state_delta[0],
            state_ids_removed=state_delta[1],
            transition_ids_added=state_delta[2],
            transition_ids_removed=state_delta[3],
            added_target_machine_ids=added_target_machine_ids,
        )
        for references, index in (
            (baseline_records, baseline_index),
            (target_records, target_index),
        )
        for reference in references
        if (record := index.get(reference.record_id)) is not None
    ]
    return (
        rows,
        {item.record_id for item in baseline_records},
        {item.record_id for item in target_records},
    )


def _unmapped_rows(
    index: Mapping[str, Record],
    linked_ids: AbstractSet[str],
    *,
    kind: RecordKind,
    side: RowStatus,
    added_target_machine_ids: AbstractSet[str] = frozenset(),
) -> list[DiffRow]:
    return [
        _record_row(
            index[record_id],
            kind=kind,
            side=side,
            added_target_machine_ids=added_target_machine_ids,
        )
        for record_id in sorted(set(index) - linked_ids)
    ]


def _rows(
    comparison: EditionComparison,
    baseline: DocumentModel,
    target: DocumentModel,
    kind: RecordKind,
    *,
    added_target_machine_ids: AbstractSet[str] | None = None,
) -> list[DiffRow]:
    baseline_index = _record_index(baseline, kind)
    target_index = _record_index(target, kind)
    rows: list[DiffRow] = []
    linked_baseline: set[str] = set()
    linked_target: set[str] = set()

    for relation in comparison.relations:
        relation_rows, baseline_ids, target_ids = _relation_rows(
            relation,
            baseline_index,
            target_index,
            kind=kind,
            added_target_machine_ids=added_target_machine_ids or frozenset(),
        )
        rows.extend(relation_rows)
        linked_baseline.update(baseline_ids)
        linked_target.update(target_ids)

    rows.extend(
        _unmapped_rows(
            baseline_index,
            linked_baseline,
            kind=kind,
            side="baseline-unmapped",
        )
    )
    rows.extend(
        _unmapped_rows(
            target_index,
            linked_target,
            kind=kind,
            side="target-unmapped",
            added_target_machine_ids=added_target_machine_ids or frozenset(),
        )
    )
    return rows


def build_report(
    *,
    manifest: EditionLineageManifest,
    baseline: DocumentModel,
    target: DocumentModel,
    kind: RecordKind,
    reviewed_only: bool = False,
) -> EditionDiffReport:
    comparison = manifest.comparison(
        baseline.document_id,
        target.document_id,
        record_kind=kind,
        reviewed_only=reviewed_only,
        corpus=ComplianceCorpus(documents=(baseline, target)),
    )
    added_target_machine_ids: set[str] = set()
    if kind == "transition":
        machine_comparison = manifest.comparison(
            baseline.document_id,
            target.document_id,
            record_kind="state-machine",
            corpus=ComplianceCorpus(documents=(baseline, target)),
        )
        added_target_machine_ids = {
            record.record_id
            for relation in machine_comparison.relations
            if relation.relation == "added"
            for record in relation.target_records
        }
    rows = _rows(
        comparison,
        baseline,
        target,
        kind,
        added_target_machine_ids=added_target_machine_ids,
    )
    if reviewed_only:
        rows = [row for row in rows if row.status == "reviewed"]
    return EditionDiffReport(
        schema_version=1,
        record_kind=kind,
        baseline=baseline.document_id,
        target=target.document_id,
        lineage_relation_counts=dict(comparison.relation_counts),
        counts=DiffCounts(
            reviewed=sum(row.status == "reviewed" for row in rows),
            baseline_unmapped=sum(row.status == "baseline-unmapped" for row in rows),
            target_unmapped=sum(row.status == "target-unmapped" for row in rows),
            target_machine_added=sum(row.status == "target-machine-added" for row in rows),
        ),
        interpretation=(
            "Unmapped rows are inventory differences without reviewed lineage; "
            "they are not assertions that a requirement or state-machine surface "
            "was added or removed. Transitions marked target-machine-added inherit "
            "a reviewed added classification from their owning state machine."
        ),
        rows=tuple(rows),
    )


def _print_csv(report: EditionDiffReport) -> None:
    if not report.rows:
        return
    flattened: list[_CsvOutputRow] = []
    for row in report.rows:
        serialized = cast(
            _CsvRow,
            row.model_dump(mode="python", exclude_unset=True),
        )
        flattened_row: _CsvOutputRow = {}
        for key, value in serialized.items():
            match value:
                case tuple() as parts:
                    flattened_row[key] = ";".join(parts)
                case _:
                    flattened_row[key] = value
        flattened.append(flattened_row)
    if not flattened:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=tuple(flattened[0]), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(flattened)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        reconfigure = sys.stdout.reconfigure  # type: ignore[reportAttributeAccessIssue]
        reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--standard", required=True, help="Lineage standard_id, e.g. ieee-1516.1")
    parser.add_argument("--baseline-edition", default="2010")
    parser.add_argument("--target-edition", default="2025")
    parser.add_argument(
        "--kind",
        choices=("requirement", "state-machine", "transition"),
        default="requirement",
    )
    parser.add_argument("--root", type=Path, help="explicit repository root")
    parser.add_argument("--reviewed-only", action="store_true")
    parser.add_argument("--format", choices=("json", "csv", "summary"), default="summary")
    args = parser.parse_args()

    workspace_root = repository_root(args.root)
    repo_resources = resources(workspace_root)
    manifest = load_edition_lineage(args.manifest or repo_resources.edition_lineage_manifest)
    baseline_id = _document_id(manifest, args.standard, args.baseline_edition)
    target_id = _document_id(manifest, args.standard, args.target_edition)
    baseline = load_hla_document_model(
        repo_resources.document(baseline_id).root, workspace_root=workspace_root
    )
    target = load_hla_document_model(
        repo_resources.document(target_id).root, workspace_root=workspace_root
    )
    report = build_report(
        manifest=manifest,
        baseline=baseline,
        target=target,
        kind=cast(RecordKind, args.kind),
        reviewed_only=args.reviewed_only,
    )
    if args.format == "json":
        print(report.model_dump_json(indent=2, exclude_unset=True))
    elif args.format == "csv":
        _print_csv(report)
    else:
        print(f"{baseline_id} -> {target_id}: {args.kind}")
        print(json.dumps(report.counts.model_dump(mode="json"), sort_keys=True))
        print(json.dumps(report.lineage_relation_counts, sort_keys=True))
        print(report.interpretation)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
