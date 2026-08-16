"""Build the source-controlled semantic corpus inventory and migration queue."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from hla_lab.core.semantic_model import DocumentModel, SourceRef
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.paths import REPO_ROOT, document_entry, document_roots, resources

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

    record_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    status: InventoryStatus
    migration: Literal["M8", "M9", "M10", "M11", "complete"]
    source: SourceRef | None = None
    owner_id: str | None = None
    notes: str = ""

class MigrationQueueItem(BaseModel):
    """One unresolved inventory item requiring migration or review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document: str = Field(min_length=1)
    migration: Literal["M8", "M9", "M10", "M11", "complete"]
    kind: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    status: InventoryStatus
    notes: str = ""

class DocumentInventory(BaseModel):
    """Inventory and migration contract for one document root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    migration: Literal["M9", "M10", "M11"]
    expected_pages: int | None = Field(default=None, ge=1)
    surface_counts: dict[str, int]
    status_counts: dict[str, int]
    items: tuple[InventoryItem, ...]

class CorpusInventory(BaseModel):
    """Deterministic, source-controlled corpus inventory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    documents: tuple[DocumentInventory, ...]
    totals: dict[str, int]
    migration_queue: tuple[MigrationQueueItem, ...]

def _migration_for(document_id: str) -> Literal["M9", "M10", "M11"]:
    migration = document_entry(document_id).migration
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

def _document_inventory(model: DocumentModel, expected_pages: int | None) -> DocumentInventory:
    migration = _migration_for(model.document_id)
    items: list[InventoryItem] = []

    for record in model.clauses:
        items.append(_item(record.id, "clause", "reviewed", "complete", record.source))
    for record in model.definitions:
        items.append(
            _item(
                record.id,
                "definition",
                "reviewed",
                migration,
                record.source,
                record.clause_id,
            )
        )
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
        items.append(
            _item(
                record.id,
                "requirement",
                status,
                migration,
                record.source,
                record.clause_id,
                (
                    review.reason
                    if review is not None
                    else "Candidate retained until a reviewer confirms normative scope."
                )
                if record.extraction == "candidate"
                else f"Semantic group: {record.semantic_group_id}.",
            )
        )
    for record in model.requirement_links:
        items.append(_item(record.id, "requirement-link", "reviewed", "complete", record.source))
    for record in model.content_blocks:
        items.append(
            _item(
                record.id,
                "content-block",
                "reviewed",
                migration,
                record.source,
                record.clause_id,
            )
        )
    for record in model.content_elements:
        items.append(
            _item(
                record.id,
                "content-element",
                "reviewed",
                migration,
                record.source,
                record.clause_id or record.block_id,
                f"Typed {record.kind} content owned by {record.block_id}.",
            )
        )
    for record in model.state_machines:
        items.append(
            _item(
                record.id,
                "state-machine",
                "reviewed",
                migration,
                record.source,
                record.clause_id,
            )
        )
        for state in record.states:
            items.append(_item(state.id, "state", "reviewed", migration, state.source, record.id))
        for transition in record.transitions:
            coverage = next(
                (item for item in model.transition_coverage if item.transition_id == transition.id),
                None,
            )
            status = coverage.status if coverage is not None else "unclassified"
            items.append(
                _item(
                    transition.id,
                    "transition",
                    status,
                    migration,
                    transition.source,
                    record.id,
                    coverage.reason
                    if coverage is not None
                    else "No transition coverage disposition yet.",
                )
            )
    for record in model.implementations:
        items.append(_item(record.id, "implementation", "mapped", migration, record.source))
    for record in model.tables:
        table_status = (
            "reviewed"
            if all(cell.row is not None and cell.column is not None for cell in record.cells)
            else "layout-exception"
        )
        items.append(_item(record.id, "table", table_status, migration, record.source))
        for cell in record.cells:
            items.append(
                _item(cell.id, "table-cell", table_status, migration, cell.source, record.id)
            )
    for record in model.table_families:
        items.append(
            _item(
                record.id,
                "table-family",
                "reviewed",
                migration,
                record.source,
                record.clause_id,
            )
        )
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

def build_inventory(
    roots: tuple[Path, ...],
    release_manifest: Path | None = None,
) -> CorpusInventory:
    """Load validated models and return the deterministic inventory."""
    expected_pages: dict[str, int] = {}
    if release_manifest is not None and release_manifest.is_file():
        manifest = json.loads(release_manifest.read_text(encoding="utf-8"))
        for project in manifest.get("projects", []):
            if isinstance(project, dict) and project.get("id") and project.get("expected_pages"):
                expected_pages[str(project["id"])] = int(project["expected_pages"])
    corpus = load_hla_corpus(roots)
    documents = tuple(
        _document_inventory(model, expected_pages.get(model.document_id))
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
    parser.add_argument(
        "--root", action="append", type=Path, help="Document root; repeat per document"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=resources(REPO_ROOT).release_manifest,
        help="Release manifest used for expected page counts",
    )
    parser.add_argument("--output", type=Path, help="Source-controlled JSON output path")
    parser.add_argument("--write", action="store_true", help="Write --output instead of printing")
    args = parser.parse_args()
    roots = tuple(args.root or document_roots(REPO_ROOT))
    inventory = build_inventory(roots, args.manifest)
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
