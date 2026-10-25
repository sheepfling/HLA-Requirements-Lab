"""Inventory extracted diagram images for the state-machine migration."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from hla_lab.core.text import slugify
from hla_lab.diagrams.review_policy import review_defaults

IMAGE_PATTERN = re.compile(r"source-p(?P<page>\d+)-xref(?P<xref>\d+)\.(?P<ext>png|jpg|jpeg)$", re.I)
DEFAULT_DOCUMENT = "1516.1"


def _document_slug(document: str) -> str:
    return slugify(document, fallback="", separator="_")


def _mapping_entries(
    existing: Mapping[str, JsonValue] | None, key: str
) -> tuple[dict[str, JsonValue], ...]:
    value: JsonValue = (existing or {}).get(key, [])
    if not isinstance(value, list):
        return ()
    items: list[JsonValue] = value
    entries: list[dict[str, JsonValue]] = []
    for raw_item in items:
        item: JsonValue = raw_item
        if isinstance(item, dict):
            entries.append(item)
    return tuple(entries)


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
    prior_entries: Mapping[str, Mapping[str, JsonValue]],
) -> dict[str, JsonValue]:
    page = int(match.group("page"))
    xref = match.group("xref")
    entry: dict[str, JsonValue] = {
        "diagram_id": f"hla{_document_slug(document)}_p{page:03d}_xref{xref}",
        "source_image": path.relative_to(repository_root).as_posix(),
        "document": document,
        "page": page,
        "xref": xref,
        "diagram_type": "unclassified",
        "status": "unmodeled",
        "model": None,
        "confidence": None,
        "notes": "",
    }
    prior = prior_entries.get(entry["diagram_id"])
    if prior is not None:
        for field in ("diagram_type", "status", "model", "confidence", "notes"):
            if field in prior:
                entry[field] = prior[field]
    entry["review_priority"], entry["review_reason"] = review_defaults(
        str(entry["diagram_type"]), str(entry["status"])
    )
    return entry


def _document_scope(
    document: str,
    extracted: Path,
    repository_root: Path,
    candidate_count: int,
    prior_scopes: Mapping[str, Mapping[str, JsonValue]],
) -> dict[str, JsonValue]:
    exists = extracted.exists()
    scope: dict[str, JsonValue] = {
        "document": document,
        "source_directory": extracted.relative_to(repository_root).as_posix(),
        "inventory_status": "inventoried" if exists else "not_started",
        "extracted_candidates": candidate_count,
        "notes": ""
        if exists
        else "No extracted-image directory exists yet; review source pages/vector figures.",
    }
    prior_scope = prior_scopes.get(document)
    if not exists and prior_scope is not None:
        for field in ("inventory_status", "notes"):
            if field in prior_scope:
                scope[field] = prior_scope[field]
    return scope


def build_inventory(
    sources: Sequence[tuple[str, Path]],
    manifest_path: Path,
    existing: Mapping[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    """Build a stable, text-only manifest from extracted image filenames."""
    repository_root = manifest_path.parent.parent.parent
    prior_entries = {
        cast(str, item.get("diagram_id")): item
        for item in _mapping_entries(existing, "diagrams")
        if item.get("diagram_id")
    }
    prior_scopes = {
        cast(str, item.get("document")): item
        for item in _mapping_entries(existing, "document_scopes")
        if item.get("document")
    }
    diagrams: list[dict[str, JsonValue]] = []
    scopes: list[dict[str, JsonValue]] = []
    for document, extracted in sources:
        candidates = _image_candidates(extracted)
        diagrams.extend(
            _diagram_entry(document, path, match, repository_root, prior_entries)
            for path, match in candidates
        )
        scopes.append(
            _document_scope(document, extracted, repository_root, len(candidates), prior_scopes)
        )
    return {
        "schema_version": "0.1",
        "generated_by": "hla_lab/diagrams/inventory_state_machines.py",
        "document_scopes": scopes,
        "diagrams": diagrams,
    }


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
        existing = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest = build_inventory(sources, args.manifest, existing)
    rendered = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
