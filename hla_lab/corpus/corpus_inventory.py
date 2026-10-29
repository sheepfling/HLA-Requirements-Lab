"""Build the source-controlled semantic corpus inventory and migration queue."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from hla_lab.core.semantic_model import DocumentModel, SourceRef
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.paths import document_entry, document_roots, resources
from hla_lab.publication.publication_registry import ReleaseManifest

InventoryStatus = Literal[
    "reviewed",
    "candidate-deferred",
    "mapped",
    "not-applicable",
    "deferred",
    "non-normative",
    "layout-only",
    "unclassified",
    "layout-exception",
]


class InventoryItem(BaseModel):
    """One classified semantic or layout surface in the corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: Annotated[str, Field(min_length=1)]
    kind: Annotated[str, Field(min_length=1)]
    status: InventoryStatus
    migration: Literal["M8", "M9", "M10", "M11", "complete"]
    source: SourceRef | None = None
    owner_id: str | None = None
    notes: str = ""


class MigrationQueueItem(BaseModel):
    """One unresolved inventory item requiring migration or review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document: Annotated[str, Field(min_length=1)]
    migration: Literal["M8", "M9", "M10", "M11", "complete"]
    kind: Annotated[str, Field(min_length=1)]
    record_id: Annotated[str, Field(min_length=1)]
    status: InventoryStatus
    notes: str = ""


class DocumentInventory(BaseModel):
    """Inventory and migration contract for one document root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: Annotated[str, Field(min_length=1)]
    source_root: Annotated[str, Field(min_length=1)]
    migration: Literal["M9", "M10", "M11"]
    expected_pages: Annotated[int | None, Field(ge=1)] = None
    surface_counts: Mapping[str, int]
    status_counts: Mapping[str, int]
    items: tuple[InventoryItem, ...]


class CorpusInventory(BaseModel):
    """Deterministic, source-controlled corpus inventory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Annotated[int, Field(ge=1)]
    documents: tuple[DocumentInventory, ...]
    totals: Mapping[str, int]
    migration_queue: tuple[MigrationQueueItem, ...]


def _migration_for(
    document_id: str, workspace_root: Path | None = None
) -> Literal["M9", "M10", "M11"]:
    migration = document_entry(document_id, workspace_root).migration
    if migration not in {"M9", "M10", "M11"}:
        raise ValueError(f"document {document_id} has no valid migration assignment")
    return migration  # type: ignore[return-value]


def _item(
    record_id: str,
    kind: str,
    status: InventoryStatus,
    migration: Literal["M8", "M9", "M10", "M11", "complete"],
    source: SourceRef | None = None,
    owner_id: str | None = None,
    notes: str = "",
) -> InventoryItem:
    return InventoryItem(
        record_id=record_id,
        kind=kind,
        status=status,
        migration=migration,
        source=source,
        owner_id=owner_id,
        notes=notes,
    )


def _clause_items(model: DocumentModel) -> list[InventoryItem]:
    return [
        _item(record.id, "clause", "reviewed", "complete", record.source)
        for record in model.clauses
    ]


def _definition_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    return [
        _item(
            record.id,
            "definition",
            "reviewed",
            migration,
            record.source,
            record.clause_id,
        )
        for record in model.definitions
    ]


def _requirement_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    items = []
    for record in model.requirements:
        review = next(
            (item for item in model.requirement_reviews if item.requirement_id == record.id), None
        )
        status = (
            "reviewed"
            if record.extraction == "explicit"
            else review.status
            if review is not None
            else "candidate-deferred"
        )
        note = (
            (
                review.reason
                if review is not None
                else "Candidate retained until a reviewer confirms normative scope."
            )
            if record.extraction == "candidate"
            else f"Semantic group: {record.semantic_group_id}."
        )
        items.append(
            _item(
                record.id,
                "requirement",
                status,
                migration,
                record.source,
                record.clause_id,
                note,
            )
        )
    return items


def _content_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    items = [
        _item(record.id, "requirement-link", "reviewed", "complete", record.source)
        for record in model.requirement_links
    ]
    items.extend(
        _item(
            record.id,
            "content-block",
            "reviewed",
            migration,
            record.source,
            record.clause_id,
        )
        for record in model.content_blocks
    )
    items.extend(
        _item(
            record.id,
            "content-element",
            "reviewed",
            migration,
            record.source,
            record.clause_id or record.block_id,
            f"Typed {record.kind} content owned by {record.block_id}.",
        )
        for record in model.content_elements
    )
    return items


def _state_machine_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for machine in model.state_machines:
        items.append(
            _item(
                machine.id,
                "state-machine",
                "reviewed",
                migration,
                machine.source,
                machine.clause_id,
            )
        )
        items.extend(
            _item(state.id, "state", "reviewed", migration, state.source, machine.id)
            for state in machine.states
        )
        for transition in machine.transitions:
            coverage = next(
                (item for item in model.transition_coverage if item.transition_id == transition.id),
                None,
            )
            items.append(
                _item(
                    transition.id,
                    "transition",
                    coverage.status if coverage is not None else "unclassified",
                    migration,
                    transition.source,
                    machine.id,
                    coverage.reason
                    if coverage is not None
                    else "No transition coverage disposition yet.",
                )
            )
    return items


def _implementation_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    return [
        _item(record.id, "implementation", "mapped", migration, record.source)
        for record in model.implementations
    ]


def _table_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for table in model.tables:
        status = (
            "reviewed"
            if all(cell.row is not None and cell.column is not None for cell in table.cells)
            else "layout-exception"
        )
        items.append(_item(table.id, "table", status, migration, table.source))
        items.extend(
            _item(cell.id, "table-cell", status, migration, cell.source, table.id)
            for cell in table.cells
        )
    return items


def _table_family_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    return [
        _item(
            record.id,
            "table-family",
            "reviewed",
            migration,
            record.source,
            record.clause_id,
        )
        for record in model.table_families
    ]


def _owned_record_items(
    model: DocumentModel,
    migration: Literal["M9", "M10", "M11"],
) -> list[InventoryItem]:
    items = []
    for kind, records in (
        ("reference", model.references),
        ("cross-reference", model.cross_references),
        ("note", model.notes),
        ("figure", model.figures),
        ("example", model.examples),
        ("annex", model.annexes),
    ):
        for record in records:
            owner = getattr(record, "owner_id", None) or getattr(record, "clause_id", None)
            items.append(_item(record.id, kind, "reviewed", migration, record.source, owner))
    return items


def _document_inventory(
    model: DocumentModel,
    expected_pages: int | None,
    *,
    workspace_root: Path | None = None,
) -> DocumentInventory:
    migration = _migration_for(model.document_id, workspace_root)
    items = [
        *_clause_items(model),
        *_definition_items(model, migration),
        *_requirement_items(model, migration),
        *_content_items(model, migration),
        *_state_machine_items(model, migration),
        *_implementation_items(model, migration),
        *_table_items(model, migration),
        *_table_family_items(model, migration),
        *_owned_record_items(model, migration),
    ]
    surface_counts = dict(sorted(Counter(item.kind for item in items).items()))
    status_counts = dict(sorted(Counter(item.status for item in items).items()))
    return DocumentInventory(
        document_id=model.document_id,
        source_root=f"topics/ieee/{model.document_id}",
        migration=migration,
        expected_pages=expected_pages,
        surface_counts=surface_counts,
        status_counts=status_counts,
        items=tuple(sorted(items, key=lambda item: (item.kind, item.record_id))),
    )


def _expected_page_counts(release_manifest: Path | None) -> dict[str, int]:
    expected_pages: dict[str, int] = {}
    if release_manifest is None or not release_manifest.is_file():
        return expected_pages
    manifest = ReleaseManifest.model_validate_json(release_manifest.read_text(encoding="utf-8"))
    for project in manifest.projects:
        if project.expected_pages is not None:
            expected_pages[project.id] = project.expected_pages
    return expected_pages


def build_inventory(
    roots: tuple[Path, ...],
    release_manifest: Path | None = None,
    *,
    workspace_root: Path | None = None,
) -> CorpusInventory:
    """Load validated models and return the deterministic inventory."""
    expected_pages = _expected_page_counts(release_manifest)
    corpus = load_hla_corpus(roots, workspace_root=workspace_root)
    documents = tuple(
        _document_inventory(
            model, expected_pages.get(model.document_id), workspace_root=workspace_root
        )
        for model in sorted(corpus.documents, key=lambda item: item.document_id)
    )
    totals = Counter()
    queue: list[MigrationQueueItem] = []
    for document in documents:
        for kind, count in document.surface_counts.items():
            totals[kind] += count
        for status, count in document.status_counts.items():
            totals[f"status:{status}"] += count
        for item in document.items:
            if item.status not in {"reviewed", "mapped"}:
                queue.append(
                    MigrationQueueItem(
                        document=document.document_id,
                        migration=item.migration,
                        kind=item.kind,
                        record_id=item.record_id,
                        status=item.status,
                        notes=item.notes,
                    )
                )
    return CorpusInventory(
        schema_version=1,
        documents=documents,
        totals=dict(sorted(totals.items())),
        migration_queue=tuple(
            sorted(
                queue,
                key=lambda item: (
                    item.migration,
                    item.document,
                    item.kind,
                    item.record_id,
                ),
            )
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, help="Repository root for document catalog")
    parser.add_argument(
        "--root", action="append", type=Path, help="Document root; repeat per document"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Release manifest used for expected page counts",
    )
    parser.add_argument("--output", type=Path, help="Source-controlled JSON output path")
    parser.add_argument("--write", action="store_true", help="Write --output instead of printing")
    args = parser.parse_args()
    roots = tuple(args.root or document_roots(args.workspace_root))
    manifest = args.manifest or resources(args.workspace_root).release_manifest
    inventory = build_inventory(roots, manifest, workspace_root=args.workspace_root)
    rendered = json.dumps(inventory.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    if args.write:
        if args.output is None:
            parser.error("--output is required with --write")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
