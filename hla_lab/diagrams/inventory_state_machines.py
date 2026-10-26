"""Inventory extracted diagram images for the state-machine migration."""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from hla_lab.core.text import slugify
from hla_lab.diagrams.review_policy import review_defaults
from hla_lab.diagrams.state_machine_inventory import (
    DiagramInventoryEntry,
    DiagramType,
    DocumentInventoryScope,
    StateMachineInventory,
)

IMAGE_PATTERN = re.compile(r"source-p(?P<page>\d+)-xref(?P<xref>\d+)\.(?P<ext>png|jpg|jpeg)$", re.I)
DEFAULT_DOCUMENT = "1516.1"


def _document_slug(document: str) -> str:
    return slugify(document, fallback="", separator="_")


def _image_candidates(extracted: Path) -> tuple[tuple[Path, re.Match[str]], ...]:
    if not extracted.exists():
        return ()
    candidates: list[tuple[Path, re.Match[str]]] = []
    for path in sorted(extracted.iterdir()):
        if not path.is_file():
            continue
        match = IMAGE_PATTERN.fullmatch(path.name)
        if match is not None:
            candidates.append((path, match))
    return tuple(candidates)


def _diagram_entry(
    document: str,
    path: Path,
    match: re.Match[str],
    repository_root: Path,
    prior_entries: Mapping[str, DiagramInventoryEntry],
) -> DiagramInventoryEntry:
    page = int(match.group("page"))
    xref = match.group("xref")
    diagram_id = f"hla{_document_slug(document)}_p{page:03d}_xref{xref}"
    prior = prior_entries.get(diagram_id)
    diagram_type: DiagramType = prior.diagram_type if prior is not None else "unclassified"
    status = prior.status if prior is not None else "unmodeled"
    review_priority, review_reason = review_defaults(diagram_type, status)
    return DiagramInventoryEntry(
        diagram_id=diagram_id,
        source_image=path.relative_to(repository_root).as_posix(),
        document=document,
        page=page,
        xref=xref,
        diagram_type=diagram_type,
        status=status,
        model=prior.model if prior is not None else None,
        confidence=prior.confidence if prior is not None else None,
        notes=prior.notes if prior is not None else "",
        review_priority=review_priority,
        review_reason=review_reason,
    )


def _document_scope(
    document: str,
    extracted: Path,
    repository_root: Path,
    candidate_count: int,
    prior_scopes: Mapping[str, DocumentInventoryScope],
) -> DocumentInventoryScope:
    exists = extracted.exists()
    prior_scope = prior_scopes.get(document)
    inventory_status = "inventoried" if exists else "not_started"
    notes = (
        ""
        if exists
        else "No extracted-image directory exists yet; review source pages/vector figures."
    )
    if not exists and prior_scope is not None:
        inventory_status = prior_scope.inventory_status
        notes = prior_scope.notes
    return DocumentInventoryScope(
        document=document,
        source_directory=extracted.relative_to(repository_root).as_posix(),
        inventory_status=inventory_status,
        extracted_candidates=candidate_count,
        notes=notes,
    )


def build_inventory(
    sources: Sequence[tuple[str, Path]],
    manifest_path: Path,
    existing: StateMachineInventory | None = None,
) -> StateMachineInventory:
    """Build a stable, text-only manifest from extracted image filenames."""
    repository_root = manifest_path.parent.parent.parent
    prior_entries = (
        {item.diagram_id: item for item in existing.diagrams} if existing is not None else {}
    )
    prior_scopes = (
        {item.document: item for item in existing.document_scopes} if existing is not None else {}
    )
    diagrams: list[DiagramInventoryEntry] = []
    scopes: list[DocumentInventoryScope] = []
    for document, extracted in sources:
        candidates = _image_candidates(extracted)
        diagrams.extend(
            _diagram_entry(document, path, match, repository_root, prior_entries)
            for path, match in candidates
        )
        scopes.append(
            _document_scope(document, extracted, repository_root, len(candidates), prior_scopes)
        )
    return StateMachineInventory(
        schema_version="0.1",
        generated_by="hla_lab/diagrams/inventory_state_machines.py",
        document_scopes=tuple(scopes),
        diagrams=tuple(diagrams),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extracted", type=Path, help="Extracted image directory (legacy single-source mode)"
    )
    parser.add_argument(
        "--source",
        action="append",
        metavar="DOCUMENT=PATH",
        help="Document and extracted-image directory; repeat for each document",
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Manifest JSON path")
    parser.add_argument("--write", action="store_true", help="Write the manifest")
    args = parser.parse_args()
    source_specs = args.source or []
    if args.extracted:
        source_specs.append(f"{DEFAULT_DOCUMENT}={args.extracted}")
    if not source_specs:
        parser.error("provide --source DOCUMENT=PATH or --extracted PATH")
    sources: list[tuple[str, Path]] = []
    for spec in source_specs:
        document, separator, path = spec.partition("=")
        if not separator or not document or not path:
            parser.error(f"invalid --source value {spec!r}; expected DOCUMENT=PATH")
        sources.append((document, Path(path)))
    existing = None
    if args.manifest.exists():
        existing = StateMachineInventory.model_validate_json(
            args.manifest.read_text(encoding="utf-8")
        )
    manifest = build_inventory(sources, args.manifest, existing)
    rendered = manifest.model_dump_json(indent=2) + "\n"
    if args.write:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
