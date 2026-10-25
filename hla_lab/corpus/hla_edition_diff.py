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
from typing import Literal, cast

from pydantic import JsonValue

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
    load_edition_lineage,
)
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import REPO_ROOT, resources

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


class _JsonEncoder(json.JSONEncoder):
    """Keep the CLI independent of a dataframe or export dependency."""

    def default(self, value: object) -> object:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")  # type: ignore[no-any-return]
        return super().default(value)


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


def _source_fields(record: Requirement | StateMachine | Transition) -> dict[str, JsonValue]:
    source = getattr(record, "source", None)
    if source is None:
        return {"source_path": None, "source_line": None}
    return {"source_path": source.path, "source_line": source.line}


def _requirement_row(
    record: Requirement, *, side: RowStatus, relation: EditionRelation | None = None
) -> dict[str, JsonValue]:
    row = {
        "status": side,
        "relation": getattr(relation, "relation", None),
        "stable_id": getattr(relation, "stable_id", None),
        "record_id": record.id,
        "title": record.title,
        "statement": record.statement,
        "clause_id": record.clause_id,
        "extraction": record.extraction,
        "transition_ids": list(record.transition_ids),
    }
    row.update(_source_fields(record))
    return row


def _state_machine_row(
    record: StateMachine,
    *,
    side: RowStatus,
    relation: EditionRelation | None = None,
    state_ids_added: AbstractSet[str] | None = None,
    state_ids_removed: AbstractSet[str] | None = None,
    transition_ids_added: AbstractSet[str] | None = None,
    transition_ids_removed: AbstractSet[str] | None = None,
) -> dict[str, JsonValue]:
    row = {
        "status": side,
        "relation": getattr(relation, "relation", None),
        "stable_id": getattr(relation, "stable_id", None),
        "record_id": record.id,
        "title": record.title,
        "clause_id": record.clause_id,
        "state_count": len(record.states),
        "transition_count": len(record.transitions),
        "state_ids": [item.id for item in record.states],
        "transition_ids": [item.id for item in record.transitions],
        "state_ids_added_in_target": sorted(state_ids_added or set()),
        "state_ids_removed_from_target": sorted(state_ids_removed or set()),
        "transition_ids_added_in_target": sorted(transition_ids_added or set()),
        "transition_ids_removed_from_target": sorted(transition_ids_removed or set()),
    }
    row.update(_source_fields(record))
    return row


def _transition_row(
    machine: StateMachine,
    record: Transition,
    *,
    side: RowStatus,
    relation: EditionRelation | None = None,
) -> dict[str, JsonValue]:
    row = {
        "status": side,
        "relation": getattr(relation, "relation", None),
        "stable_id": getattr(relation, "stable_id", None),
        "record_id": record.id,
        "machine_id": machine.id,
        "source_state": record.source_state,
        "event": record.event,
        "target_state": record.target_state,
        "clause_id": record.clause_id,
        "requirement_ids": list(record.requirement_ids),
        "implementation_ids": list(record.implementation_ids),
    }
    row.update(_source_fields(record))
    return row


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
) -> dict[str, JsonValue]:
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
        row["derived_from_state_machine"] = machine.id
    return row


def _relation_rows(
    relation: EditionRelation,
    baseline_index: Mapping[str, Record],
    target_index: Mapping[str, Record],
    *,
    kind: RecordKind,
    added_target_machine_ids: AbstractSet[str],
) -> tuple[list[dict[str, JsonValue]], set[str], set[str]]:
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
) -> list[dict[str, JsonValue]]:
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
) -> list[dict[str, JsonValue]]:
    baseline_index = _record_index(baseline, kind)
    target_index = _record_index(target, kind)
    rows: list[dict[str, JsonValue]] = []
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
) -> dict[str, JsonValue]:
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
        rows = [row for row in rows if row["status"] == "reviewed"]
    return cast(
        dict[str, JsonValue],
        {
            "schema_version": 1,
            "record_kind": kind,
            "baseline": baseline.document_id,
            "target": target.document_id,
            "lineage_relation_counts": comparison.relation_counts,
            "counts": {
                "reviewed": sum(row["status"] == "reviewed" for row in rows),
                "baseline_unmapped": sum(row["status"] == "baseline-unmapped" for row in rows),
                "target_unmapped": sum(row["status"] == "target-unmapped" for row in rows),
                "target_machine_added": sum(
                    row["status"] == "target-machine-added" for row in rows
                ),
            },
            "interpretation": (
                "Unmapped rows are inventory differences without reviewed lineage; "
                "they are not assertions that a requirement or state-machine surface "
                "was added or removed. Transitions marked target-machine-added inherit "
                "a reviewed added classification from their owning state machine."
            ),
            "rows": rows,
        },
    )


def _print_csv(report: Mapping[str, JsonValue]) -> None:
    raw_rows: JsonValue = report["rows"]
    if not isinstance(raw_rows, list) or not raw_rows:
        return
    rows: list[JsonValue] = raw_rows
    flattened: list[dict[str, JsonValue]] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        row: dict[str, JsonValue] = raw_row
        flattened_row: dict[str, JsonValue] = {}
        for key, value in row.items():
            flattened_row[key] = (
                ";".join(str(item) for item in value) if isinstance(value, list) else value
            )
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
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Repository root")
    parser.add_argument("--reviewed-only", action="store_true")
    parser.add_argument("--format", choices=("json", "csv", "summary"), default="summary")
    args = parser.parse_args()

    repo_resources = resources(args.root)
    manifest = load_edition_lineage(
        args.manifest or repo_resources.edition_lineage_manifest
    )
    baseline_id = _document_id(manifest, args.standard, args.baseline_edition)
    target_id = _document_id(manifest, args.standard, args.target_edition)
    baseline = load_hla_document_model(
        repo_resources.document(baseline_id).root, workspace_root=args.root
    )
    target = load_hla_document_model(
        repo_resources.document(target_id).root, workspace_root=args.root
    )
    report = build_report(
        manifest=manifest,
        baseline=baseline,
        target=target,
        kind=args.kind,
        reviewed_only=args.reviewed_only,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, cls=_JsonEncoder))
    elif args.format == "csv":
        _print_csv(report)
    else:
        print(f"{baseline_id} -> {target_id}: {args.kind}")
        print(json.dumps(report["counts"], sort_keys=True))
        print(json.dumps(report["lineage_relation_counts"], sort_keys=True))
        print(report["interpretation"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
