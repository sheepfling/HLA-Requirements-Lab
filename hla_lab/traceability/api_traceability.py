"""Validate the requirement-to-language-API traceability surface."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, MutableSequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from hla_lab.core.semantic_model import ApiSurface, DocumentModel, SourceRef
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.paths import REPO_ROOT, document_roots

__all__ = [
    "API_TRACEABILITY_DOCUMENT_IDS",
    "ApiTraceabilityDocumentReport",
    "ApiTraceabilityReport",
    "build_report",
    "default_roots",
    "main",
]

API_TRACEABILITY_DOCUMENT_IDS = ("hla-1516.1-2010", "hla-1516.1-2025")
DECLARATION_SUFFIXES = MappingProxyType(
    {
        "cpp": {".h", ".hh", ".hpp"},
        "java": {".java"},
    }
)


class ApiTraceabilityReportModel(BaseModel):
    """Immutable base for API traceability audit records."""

    model_config = ConfigDict(frozen=True)


class ApiTraceabilityDocumentReport(ApiTraceabilityReportModel):
    """Audit result for one standard edition."""

    document: str
    requirement_count: int
    covered_requirement_count: int
    binding_count: int
    status_counts: Mapping[str, int]
    matched_binding_count: int
    review_gap_count: int
    external_source_count: int
    failures: tuple[str, ...]
    passed: bool
    complete: bool


class ApiTraceabilityReport(ApiTraceabilityReportModel):
    """Corpus-wide requirement-to-API audit result."""

    documents: tuple[ApiTraceabilityDocumentReport, ...]
    failures: tuple[str, ...]
    passed: bool
    complete: bool


def _declaration_suffix(source: SourceRef) -> str:
    """Return the suffix of a local path or an archive member path."""
    return Path(source.path.rsplit("#", 1)[-1]).suffix.casefold()


def _source_is_valid(surface: ApiSurface) -> bool:
    """Check that a language surface points to a declaration-shaped source."""
    if surface.source is None:
        return False
    return _declaration_suffix(surface.source) in DECLARATION_SUFFIXES.get(
        surface.language,
        set(),
    )


def _append_requirement_coverage_findings(
    requirement_ids: AbstractSet[str],
    binding_requirement_ids: AbstractSet[str],
    failures: MutableSequence[str],
) -> None:
    missing_requirements = requirement_ids - binding_requirement_ids
    unexpected_requirements = binding_requirement_ids - requirement_ids
    if missing_requirements:
        failures.append(
            "requirements without API traceability rows: " + ", ".join(sorted(missing_requirements))
        )
    if unexpected_requirements:
        failures.append(
            "API traceability rows reference unknown requirements: "
            + ", ".join(sorted(unexpected_requirements))
        )


def _append_surface_source_findings(
    model: DocumentModel,
    failures: MutableSequence[str],
) -> int:
    external_source_count = 0
    for surface in model.api_surfaces:
        if surface.language not in DECLARATION_SUFFIXES:
            continue
        if surface.source is not None and "#" in surface.source.path:
            external_source_count += 1
        if not _source_is_valid(surface):
            failures.append(
                f"{surface.id}: {surface.language} surface lacks a valid declaration source"
            )
    return external_source_count


def _append_binding_surface_findings(
    model: DocumentModel,
    surfaces: Mapping[str, ApiSurface],
    failures: MutableSequence[str],
) -> None:
    for binding in model.requirement_api_bindings:
        referenced_ids = set(binding.candidate_api_surface_ids)
        if binding.api_surface_id is not None:
            referenced_ids.add(binding.api_surface_id)
        for surface_id in sorted(referenced_ids):
            surface = surfaces.get(surface_id)
            if surface is None:
                failures.append(f"{binding.id}: references missing API surface {surface_id}")
                continue
            if surface.language != binding.language:
                failures.append(
                    f"{binding.id}: binding language {binding.language} does not match "
                    f"surface language {surface.language}"
                )
            if not _source_is_valid(surface):
                failures.append(
                    f"{binding.id}: referenced surface {surface_id} lacks a valid source"
                )


def _document_report(model: DocumentModel) -> ApiTraceabilityDocumentReport:
    requirement_ids = {item.id for item in model.requirements}
    binding_requirement_ids = {item.requirement_id for item in model.requirement_api_bindings}
    surfaces = {item.id: item for item in model.api_surfaces}
    failures: list[str] = []

    _append_requirement_coverage_findings(requirement_ids, binding_requirement_ids, failures)

    rebuilt = build_requirement_api_bindings(model)
    if rebuilt != model.requirement_api_bindings:
        failures.append("API traceability manifest is stale or not deterministically generated")

    external_source_count = _append_surface_source_findings(model, failures)
    _append_binding_surface_findings(model, surfaces, failures)

    status_counts = dict(Counter(item.status for item in model.requirement_api_bindings))
    review_gap_count = sum(
        status_counts.get(status, 0) for status in ("candidate", "ambiguous", "unmatched")
    )
    return ApiTraceabilityDocumentReport(
        document=model.document_id,
        requirement_count=len(requirement_ids),
        covered_requirement_count=len(requirement_ids & binding_requirement_ids),
        binding_count=len(model.requirement_api_bindings),
        status_counts=status_counts,
        matched_binding_count=status_counts.get("matched", 0),
        review_gap_count=review_gap_count,
        external_source_count=external_source_count,
        failures=tuple(failures),
        passed=not failures,
        complete=not failures and review_gap_count == 0,
    )


def default_roots(repo_root: Path = REPO_ROOT) -> tuple[Path, ...]:
    """Return the two HLA 1516.1 edition roots covered by this audit."""
    return document_roots(repo_root, API_TRACEABILITY_DOCUMENT_IDS)


def build_report(
    roots: tuple[Path, ...], *, workspace_root: Path | None = None
) -> ApiTraceabilityReport:
    """Audit deterministic requirement-to-API manifests for the supplied roots."""
    corpus = load_hla_corpus(roots, workspace_root=workspace_root)
    documents = tuple(_document_report(model) for model in corpus.documents)
    failures = tuple(
        f"{document.document}: {failure}" for document in documents for failure in document.failures
    )
    return ApiTraceabilityReport(
        documents=documents,
        failures=failures,
        passed=not failures,
        complete=not failures and all(item.complete for item in documents),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        help="Document root to audit; defaults to both hla-1516.1 editions",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Workspace containing source profiles and the HLA document roots",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero when the API traceability contract fails",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Also require every requirement-to-API review gap to be closed",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    workspace_root = args.workspace_root or REPO_ROOT
    if workspace_root is None:
        parser.error("workspace root is required; pass --workspace-root or set HLA_LAB_ROOT")
    roots = tuple(args.root) if args.root else default_roots(workspace_root)
    report = build_report(roots, workspace_root=workspace_root)
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        for document in report.documents:
            print(
                f"{document.document}: requirements={document.requirement_count} "
                f"bindings={document.binding_count} matched={document.matched_binding_count} "
                f"review-gaps={document.review_gap_count} "
                f"external-sources={document.external_source_count}"
            )
        print(
            f"API traceability: {'passed' if report.passed else 'failed'}; "
            f"complete: {'yes' if report.complete else 'no'}"
        )
        for failure in report.failures:
            print(f"failure: {failure}")
    gate_passed = report.passed and (not args.require_complete or report.complete)
    return 0 if gate_passed or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
