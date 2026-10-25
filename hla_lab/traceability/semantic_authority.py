"""Validate the source-controlled semantic authority manifest."""

from __future__ import annotations

import argparse
import re
from pathlib import Path, PureWindowsPath
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from hla_lab.core.semantic_model import ComplianceIssue, DocumentModel, SemanticRecord
from hla_lab.core.source_paths import normalized_source_path
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.generation.faithful_renderer import (
    FaithfulLayoutProjection,
    build_faithful_layout_projection,
    load_faithful_layout_profile,
    render_faithful_body,
)
from hla_lab.paths import REPO_ROOT, DocumentResources, document_roots, resources
from hla_lab.publication.publication_registry import load_release_manifest

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
    "references",
    "cross_references",
    "figures",
    "diagram_surfaces",
    "notes",
    "tables",
    "api_surfaces",
    "api_crosswalks",
    "requirement_api_bindings",
]
_SURFACE_RECORD_ATTRIBUTES = MappingProxyType(
    {
        "definitions": "definitions",
        "requirements": "requirements",
        "requirement_reviews": "requirement_reviews",
        "content_blocks": "content_blocks",
        "content_elements": "content_elements",
        "transition_coverage": "transition_coverage",
        "implementations": "implementations",
        "requirement_links": "requirement_links",
        "table_families": "table_families",
        "references": "references",
        "cross_references": "cross_references",
        "figures": "figures",
        "diagram_surfaces": "diagram_surfaces",
        "notes": "notes",
        "tables": "tables",
        "api_surfaces": "api_surfaces",
        "api_crosswalks": "api_crosswalks",
        "requirement_api_bindings": "requirement_api_bindings",
    }
)


class AuthoritySurfaceReport(BaseModel):
    """Validation counts for one declared semantic surface."""

    model_config = ConfigDict(frozen=True)

    document: str
    surface: str
    kind: SurfaceKind
    records: int
    source_files: int
    generated_inputs: int


class FaithfulLayoutReport(BaseModel):
    """Validation result for one document's faithful layout projection."""

    model_config = ConfigDict(frozen=True)

    document: str
    entries: int
    main: str
    direct_page_inputs: tuple[str, ...]
    failures: tuple[str, ...]
    passed: bool


class AuthorityValidationReport(BaseModel):
    """Complete typed result of semantic authority validation."""

    model_config = ConfigDict(frozen=True)

    manifest: str
    check_generated: bool
    surfaces: tuple[AuthoritySurfaceReport, ...]
    faithful_layouts: tuple[FaithfulLayoutReport, ...]
    unresolved_references: tuple[ComplianceIssue, ...]
    failures: tuple[str, ...]
    passed: bool


class AuthoritySurface(BaseModel):
    """One semantic surface and its optional faithful generated consumer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: SurfaceKind
    source_paths: Annotated[tuple[str, ...], Field(min_length=1)]
    selection: Selection
    generated_glob: str | None = None


class AuthorityDocument(BaseModel):
    """Authority declarations for one document root."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    root: str
    surfaces: Annotated[tuple[AuthoritySurface, ...], Field(min_length=1)]


class AuthorityManifest(BaseModel):
    """Versioned source-of-truth declaration for migrated surfaces."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    documents: Annotated[tuple[AuthorityDocument, ...], Field(min_length=1)]


def load_authority(path: Path) -> AuthorityManifest:
    """Load and validate a source-controlled authority manifest."""
    return AuthorityManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _surface_records(model: DocumentModel, surface: AuthoritySurface) -> tuple[SemanticRecord, ...]:
    attribute = _SURFACE_RECORD_ATTRIBUTES[surface.kind]
    records = getattr(model, attribute)
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


def _generated_matches(root: Path, surface: AuthoritySurface) -> tuple[Path, ...]:
    """Find generated data inputs without confusing IDs ending in ``-data``.

    A semantic ID such as ``federation-object-model-document-data`` produces
    both ``...-data.tex`` (the visible record) and ``...-data-data.tex`` (the
    machine-readable projection). The broad historical glob matches both, so
    discard the visible sibling when its projection is present.
    """
    if not surface.generated_glob:
        return ()
    matches = tuple(sorted(root.glob(surface.generated_glob)))
    return tuple(
        path
        for path in matches
        if not (
            path.name.endswith("-data.tex") and path.with_name(f"{path.stem}-data.tex").is_file()
        )
    )


def _main_inputs(path: Path) -> tuple[str, ...]:
    """Return normalized direct LaTeX inputs from a document entrypoint."""
    if not path.is_file():
        return ()
    values = re.findall(r"\\input\s*\{([^}]+)\}", path.read_text(encoding="utf-8"))
    return tuple(PureWindowsPath(value.strip()).with_suffix(".tex").as_posix() for value in values)


def _faithful_body_exclusions(root: Path) -> tuple[str, ...]:
    """Read the faithful-body trim policy from the release manifest."""
    manifest_path = resources(REPO_ROOT).release_manifest
    if not manifest_path.is_file():
        return ()
    try:
        relative_root = root.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        project = next(
            item
            for item in load_release_manifest(manifest_path).projects
            if normalized_source_path(item.root) == relative_root
        )
    except (ValueError, StopIteration):
        return ()
    return project.build.faithful_body_exclude_path_parts if project.build is not None else ()


def _use_generated_faithful_blocks(root: Path) -> bool:
    """Read the declared faithful-body renderer mode for a document."""
    manifest_path = resources(REPO_ROOT).release_manifest
    if not manifest_path.is_file():
        return False
    try:
        relative_root = root.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        project = next(
            item
            for item in load_release_manifest(manifest_path).projects
            if normalized_source_path(item.root) == relative_root
        )
    except (ValueError, StopIteration):
        return False
    return bool(project.build and project.build.use_generated_faithful_blocks)


def _validate_faithful_layout(
    model: DocumentModel,
    root: Path,
    *,
    check_generated: bool,
) -> FaithfulLayoutReport:
    """Verify that semantic blocks, not ``main.tex``, order faithful pages."""
    document = DocumentResources(root)
    profile_path = document.semantic_file("faithful-layout.json")
    projection = build_faithful_layout_projection(
        model,
        profile=load_faithful_layout_profile(profile_path) if profile_path.is_file() else None,
        exclude_path_parts=_faithful_body_exclusions(root),
    )
    use_generated_blocks = _use_generated_faithful_blocks(root)
    expected_sources = {entry.source_path for entry in projection.entries}
    main_path = document.main_tex
    main_inputs = _main_inputs(main_path)
    direct_page_inputs = sorted(expected_sources.intersection(main_inputs))
    failures: list[str] = []
    if "output/semantic/faithful-body.tex" not in main_inputs:
        failures.append("main.tex does not input output/semantic/faithful-body")
    if direct_page_inputs:
        failures.append(
            "main.tex directly orders layout adapters: " + ", ".join(direct_page_inputs)
        )
    missing_adapters = [
        entry.source_path
        for entry in projection.entries
        if not (document.root / entry.source_path).is_file()
    ]
    if missing_adapters:
        failures.append("semantic layout adapters are missing: " + ", ".join(missing_adapters))

    generated = document.output_semantic
    if check_generated:
        json_path = generated / "faithful-layout.json"
        body_path = generated / "faithful-body.tex"
        if not json_path.is_file() or not body_path.is_file():
            failures.append("generated faithful layout projection is missing")
        else:
            actual = FaithfulLayoutProjection.model_validate_json(
                json_path.read_text(encoding="utf-8")
            )
            if actual != projection:
                failures.append(
                    "generated faithful layout projection does not match semantic blocks"
                )
            if (
                body_path.read_text(encoding="utf-8")
                != render_faithful_body(
                    projection,
                    use_generated_blocks=use_generated_blocks,
                )
                + "\n"
            ):
                failures.append("generated faithful body does not match semantic layout projection")
    return FaithfulLayoutReport(
        document=model.document_id,
        entries=len(projection.entries),
        main=str(main_path),
        direct_page_inputs=tuple(direct_page_inputs),
        failures=tuple(failures),
        passed=not failures,
    )


def validate_authority(
    roots: tuple[Path, ...], manifest_path: Path, *, check_generated: bool = False
) -> AuthorityValidationReport:
    """Validate declared source ownership and optionally generated consumers."""
    manifest = load_authority(manifest_path)
    corpus = load_hla_corpus(roots)
    models = {model.document_id: model for model in corpus.documents}
    reports: list[AuthoritySurfaceReport] = []
    faithful_layouts: list[FaithfulLayoutReport] = []
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
                generated_matches = _generated_matches(root, surface)
                if check_generated and len(generated_matches) != len(records):
                    failures.append(
                        f"{document.document_id}/{surface.id}: expected {len(records)} generated "
                        f"inputs, found {len(generated_matches)}"
                    )
            reports.append(
                AuthoritySurfaceReport(
                    document=document.document_id,
                    surface=surface.id,
                    kind=surface.kind,
                    records=len(records),
                    source_files=len(source_matches),
                    generated_inputs=len(generated_matches),
                )
            )
        layout_report = _validate_faithful_layout(
            model,
            root,
            check_generated=check_generated,
        )
        faithful_layouts.append(layout_report)
        failures.extend(
            f"{document.document_id}/faithful-layout: {failure}"
            for failure in layout_report.failures
        )
    return AuthorityValidationReport(
        manifest=str(manifest_path),
        check_generated=check_generated,
        surfaces=tuple(reports),
        faithful_layouts=tuple(faithful_layouts),
        unresolved_references=unresolved_references,
        failures=tuple(failures),
        passed=not failures,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--root", action="append", type=Path)
    parser.add_argument("--check-generated", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    manifest = args.manifest or resources(REPO_ROOT).authority_manifest
    roots = tuple(args.root or document_roots(REPO_ROOT))
    report = validate_authority(roots, manifest, check_generated=args.check_generated)
    rendered = report.model_dump_json(indent=2)
    print(rendered)
    if report.failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
