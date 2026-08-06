"""Validate the source-controlled semantic authority manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

try:
    from scripts.hla_semantic import load_hla_corpus
    from scripts.semantic_model import DocumentModel
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hla_semantic import load_hla_corpus
    from semantic_model import DocumentModel


Selection = Literal["all", "explicit"]
SurfaceKind = Literal[
    "definitions",
    "requirements",
    "requirement_reviews",
    "content_blocks",
    "content_elements",
    "transition_coverage",
    "implementations",
    "requirement_links",
    "table_families",
]


class AuthoritySurface(BaseModel):
    """One semantic surface and its optional faithful generated consumer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SurfaceKind
    source_paths: tuple[str, ...] = Field(min_length=1)
    selection: Selection
    generated_glob: str | None = None


class AuthorityDocument(BaseModel):
    """Authority declarations for one document root."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    root: str
    surfaces: tuple[AuthoritySurface, ...] = Field(min_length=1)


class AuthorityManifest(BaseModel):
    """Versioned source-of-truth declaration for migrated surfaces."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    documents: tuple[AuthorityDocument, ...] = Field(min_length=1)


def load_authority(path: Path) -> AuthorityManifest:
    """Load and validate a source-controlled authority manifest."""
    return AuthorityManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _surface_records(model: DocumentModel, surface: AuthoritySurface) -> tuple[object, ...]:
    records: tuple[object, ...]
    if surface.kind == "definitions":
        records = model.definitions
    elif surface.kind == "requirements":
        records = model.requirements
    elif surface.kind == "requirement_reviews":
        records = model.requirement_reviews
    elif surface.kind == "content_blocks":
        records = model.content_blocks
    elif surface.kind == "content_elements":
        records = model.content_elements
    elif surface.kind == "transition_coverage":
        records = model.transition_coverage
    elif surface.kind == "implementations":
        records = model.implementations
    elif surface.kind == "requirement_links":
        records = model.requirement_links
    else:
        records = model.table_families
    if surface.selection == "explicit":
        records = tuple(
            record for record in records if getattr(record, "extraction", None) == "explicit"
        )
    return records


def _source_matches(root: Path, surface: AuthoritySurface) -> tuple[Path, ...]:
    matches: list[Path] = []
    for pattern in surface.source_paths:
        if any(character in pattern for character in "*?["):
            matches.extend(root.glob(pattern))
        else:
            matches.append(root / pattern)
    return tuple(sorted(set(matches)))


def validate_authority(
    roots: tuple[Path, ...], manifest_path: Path, *, check_generated: bool = False
) -> dict[str, object]:
    """Validate declared source ownership and optionally generated consumers."""
    manifest = load_authority(manifest_path)
    corpus = load_hla_corpus(roots)
    models = {model.document_id: model for model in corpus.documents}
    reports: list[dict[str, object]] = []
    failures: list[str] = []
    unresolved_references = corpus.unresolved_reference_issues()
    failures.extend(
        f"{issue.code}: {issue.record_id} — {issue.message}" for issue in unresolved_references
    )
    for document in manifest.documents:
        model = models.get(document.document_id)
        if model is None:
            failures.append(f"{document.document_id}: document is not loaded")
            continue
        root = Path(document.root)
        if not root.is_dir():
            failures.append(f"{document.document_id}: root does not exist: {root}")
        for surface in document.surfaces:
            source_matches = _source_matches(root, surface)
            missing_sources = [str(path) for path in source_matches if not path.is_file()]
            if not source_matches or missing_sources:
                failures.append(f"{document.document_id}/{surface.id}: source path is missing")
            records = _surface_records(model, surface)
            generated_matches: tuple[Path, ...] = ()
            if surface.generated_glob:
                generated_matches = tuple(sorted(root.glob(surface.generated_glob)))
                if check_generated and len(generated_matches) != len(records):
                    failures.append(
                        f"{document.document_id}/{surface.id}: expected {len(records)} generated "
                        f"inputs, found {len(generated_matches)}"
                    )
            reports.append(
                {
                    "document": document.document_id,
                    "surface": surface.id,
                    "kind": surface.kind,
                    "records": len(records),
                    "source_files": len(source_matches),
                    "generated_inputs": len(generated_matches),
                }
            )
    return {
        "manifest": str(manifest_path),
        "check_generated": check_generated,
        "surfaces": reports,
        "unresolved_references": [issue.model_dump(mode="json") for issue in unresolved_references],
        "failures": failures,
        "passed": not failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/semantic/authority.json"))
    parser.add_argument("--root", action="append", type=Path)
    parser.add_argument("--check-generated", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    roots = tuple(args.root or sorted(Path("topics/ieee").glob("hla-1516*/")))
    report = validate_authority(roots, args.manifest, check_generated=args.check_generated)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
