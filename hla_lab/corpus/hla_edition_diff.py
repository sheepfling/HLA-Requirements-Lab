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
from pathlib import Path
from typing import Literal, cast

from hla_lab.core.json_types import JsonValue
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
    state_ids_added: set[str] | None = None,
    state_ids_removed: set[str] | None = None,
    transition_ids_added: set[str] | None = None,
    transition_ids_removed: set[str] | None = None,
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

def _record_index(
    model: DocumentModel, kind: RecordKind
) -> dict[str, Requirement | StateMachine | tuple[StateMachine, Transition]]:
    if kind == "requirement":
        return {item.id: item for item in model.requirements}
    if kind == "state-machine":
        return {item.id: item for item in model.state_machines}
    return {
        transition.id: (machine, transition)
        for machine in model.state_machines
        for transition in machine.transitions
    }

def _rows(
    comparison: EditionComparison,
    baseline: DocumentModel,
    target: DocumentModel,
    kind: RecordKind,
    *,
    added_target_machine_ids: set[str] | None = None,
) -> list[dict[str, JsonValue]]:
    baseline_index = _record_index(baseline, kind)
    target_index = _record_index(target, kind)
    rows: list[dict[str, JsonValue]] = []
    linked_baseline: set[str] = set()
    linked_target: set[str] = set()

    for relation in comparison.relations:
        relation_baseline = [item for item in relation.baseline_records if item.kind == kind]
        relation_target = [item for item in relation.target_records if item.kind == kind]
        linked_baseline.update(item.record_id for item in relation_baseline)
        linked_target.update(item.record_id for item in relation_target)
        state_ids_added: set[str] = set()
        state_ids_removed: set[str] = set()
        transition_ids_added: set[str] = set()
        transition_ids_removed: set[str] = set()
        if kind == "state-machine":
            baseline_machines = [baseline_index[item.record_id] for item in relation_baseline]
            target_machines = [target_index[item.record_id] for item in relation_target]
            baseline_states = {
                state.id
                for machine in baseline_machines
                for state in machine.states  # type: ignore[union-attr]
            }
            target_states = {
                state.id
                for machine in target_machines
                for state in machine.states  # type: ignore[union-attr]
            }
            baseline_transitions = {
                transition.id
                for machine in baseline_machines
                for transition in machine.transitions  # type: ignore[union-attr]
            }
            target_transitions = {
                transition.id
                for machine in target_machines
                for transition in machine.transitions  # type: ignore[union-attr]
            }
            state_ids_added = target_states - baseline_states
            state_ids_removed = baseline_states - target_states
            transition_ids_added = target_transitions - baseline_transitions
            transition_ids_removed = baseline_transitions - target_transitions
        for item in relation_baseline:
            record = baseline_index.get(item.record_id)
            if record is not None:
                if kind == "requirement":
                    rows.append(
                        _requirement_row(
                            cast(Requirement, record), side="reviewed", relation=relation
                        )
                    )
                elif kind == "state-machine":
                    rows.append(
                        _state_machine_row(
                            cast(StateMachine, record),
                            side="reviewed",
                            relation=relation,
                            state_ids_added=state_ids_added,
                            state_ids_removed=state_ids_removed,
                            transition_ids_added=transition_ids_added,
                            transition_ids_removed=transition_ids_removed,
                        )
                    )
                else:
                    machine, transition = cast(tuple[StateMachine, Transition], record)
                    rows.append(
                        _transition_row(machine, transition, side="reviewed", relation=relation)
                    )
        for item in relation_target:
            record = target_index.get(item.record_id)
            if record is not None:
                if kind == "requirement":
                    rows.append(
                        _requirement_row(
                            cast(Requirement, record), side="reviewed", relation=relation
                        )
                    )
                elif kind == "state-machine":
                    rows.append(
                        _state_machine_row(
                            cast(StateMachine, record),
                            side="reviewed",
                            relation=relation,
                            state_ids_added=state_ids_added,
                            state_ids_removed=state_ids_removed,
                            transition_ids_added=transition_ids_added,
                            transition_ids_removed=transition_ids_removed,
                        )
                    )
                else:
                    machine, transition = cast(tuple[StateMachine, Transition], record)
                    rows.append(
                        _transition_row(machine, transition, side="reviewed", relation=relation)
                    )

    for record_id in sorted(set(baseline_index) - linked_baseline):
        record = baseline_index[record_id]
        if kind == "requirement":
            rows.append(_requirement_row(cast(Requirement, record), side="baseline-unmapped"))
        elif kind == "state-machine":
            rows.append(_state_machine_row(cast(StateMachine, record), side="baseline-unmapped"))
        else:
            machine, transition = cast(tuple[StateMachine, Transition], record)
            rows.append(_transition_row(machine, transition, side="baseline-unmapped"))
    for record_id in sorted(set(target_index) - linked_target):
        record = target_index[record_id]
        if kind == "requirement":
            rows.append(_requirement_row(cast(Requirement, record), side="target-unmapped"))
        elif kind == "state-machine":
            rows.append(_state_machine_row(cast(StateMachine, record), side="target-unmapped"))
        else:
            machine, transition = cast(tuple[StateMachine, Transition], record)
            side: RowStatus = "target-unmapped"
            if added_target_machine_ids and machine.id in added_target_machine_ids:
                side = "target-machine-added"
            row = _transition_row(machine, transition, side=side)
            if side == "target-machine-added":
                row["derived_from_state_machine"] = machine.id
            rows.append(row)
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
    rows = report["rows"]
    if not rows:
        return
    flattened: list[dict[str, JsonValue]] = []
    for row in rows:  # type: ignore[union-attr]
        flattened.append(
            {
                key: ";".join(value) if isinstance(value, list) else value
                for key, value in row.items()
            }
        )
    writer = csv.DictWriter(sys.stdout, fieldnames=tuple(flattened[0]), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(flattened)

def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[reportAttributeAccessIssue]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=resources(REPO_ROOT).edition_lineage_manifest
    )
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

    manifest = load_edition_lineage(args.manifest)
    baseline_id = _document_id(manifest, args.standard, args.baseline_edition)
    target_id = _document_id(manifest, args.standard, args.target_edition)
    repo_resources = resources(args.root)
    baseline = load_hla_document_model(repo_resources.document(baseline_id).root)
    target = load_hla_document_model(repo_resources.document(target_id).root)
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
