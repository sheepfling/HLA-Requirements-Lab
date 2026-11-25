"""Audit source-owned requirement closure for the three 2010 documents.

The 2010 source trees use the legacy ``shall``/``must`` extractor rather than
the 2025 page-layout candidate extractor.  This module keeps that distinction
explicit: it compares the legacy source inventory with the promoted catalog,
without inventing 2025-only table-row requirements in the 2010 editions.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from hla_lab.corpus.hla_2010_semantic import _plain, _requirements, _surface_inputs
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import repository_root, resources

__all__ = [
    "RequirementClosureDocument",
    "RequirementClosureReport",
    "build_report",
]


def _default_roots(workspace_root: Path) -> tuple[Path, ...]:
    registry = resources(workspace_root)
    return tuple(
        registry.document(document_id).root
        for document_id in ("hla-1516-2010", "hla-1516.1-2010", "hla-1516.2-2010")
    )


class _ReportModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class RequirementClosureDocument(_ReportModel):
    """One 2010 document's source-to-catalog closure evidence."""

    document: Annotated[str, Field(min_length=1)]
    requirements: Annotated[int, Field(ge=0)]
    source_candidates: Annotated[int, Field(ge=0)]
    explicit_requirements: Annotated[int, Field(ge=0)]
    candidate_requirements: Annotated[int, Field(ge=0)]
    requirement_reviews: Annotated[int, Field(ge=0)]
    table_count: Annotated[int, Field(ge=0)]
    table_requirement_references: Annotated[int, Field(ge=0)]
    api_binding_rows: Annotated[int, Field(ge=0)]
    api_binding_requirement_ids: Annotated[int, Field(ge=0)]
    missing_api_requirement_ids: tuple[str, ...] = ()
    unexpected_api_requirement_ids: tuple[str, ...] = ()
    source_path_mismatches: tuple[str, ...] = ()
    missing_source_paths: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    passed: bool


class RequirementClosureReport(_ReportModel):
    """Corpus-level 2010 requirement closure report."""

    documents: tuple[RequirementClosureDocument, ...]
    failures: tuple[str, ...] = ()
    passed: bool


def _document_report(root: Path) -> RequirementClosureDocument:
    model = load_hla_document_model(root)
    extracted = _requirements(root, _surface_inputs(root))
    requirement_ids = {item.id for item in model.requirements}
    binding_ids = {item.requirement_id for item in model.requirement_api_bindings}

    # The legacy scanner segments prose into candidate paragraphs, while the
    # curated semantic catalog may split or combine those candidates. Compare
    # the normalized source statements, not their raw record counts.
    def statement_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", _plain(value).casefold())

    candidate_statements = tuple(
        (item.source.path, statement_key(item.statement)) for item in extracted
    )
    catalog_statements = tuple(
        (item.source.path, statement_key(item.statement)) for item in model.requirements
    )
    uncovered_candidates = tuple(
        path
        for path, candidate in candidate_statements
        if not candidate
        or not any(
            path == catalog_path and (candidate in catalog or catalog in candidate)
            for catalog_path, catalog in catalog_statements
        )
    )
    unmatched_catalog = tuple(
        path
        for path, catalog in catalog_statements
        if not catalog
        or not any(
            path == candidate_path and (catalog in candidate or candidate in catalog)
            for candidate_path, candidate in candidate_statements
        )
    )
    source_path_mismatches = tuple(sorted(set(uncovered_candidates + unmatched_catalog)))
    missing_source_paths = tuple(
        sorted(item.id for item in model.requirements if not (root / item.source.path).is_file())
    )
    table_requirement_references = sum(
        record_id in requirement_ids
        for table in model.tables
        for cell in table.cells
        for record_id in cell.record_ids
    )
    api_binding_audit = bool(model.requirement_api_bindings)
    failures: list[str] = []
    if source_path_mismatches:
        failures.append("promoted requirements do not cover the legacy source statements")
    if any(item.extraction != "explicit" for item in model.requirements):
        failures.append("2010 requirement catalog contains unpromoted candidates")
    if model.requirement_reviews:
        failures.append("2010 requirement catalog retains review-queue records")
    if missing_source_paths:
        failures.append("one or more 2010 requirements point at missing source files")
    if api_binding_audit and (requirement_ids - binding_ids or binding_ids - requirement_ids):
        failures.append("1516.1-2010 API bindings do not cover exactly the requirement catalog")
    return RequirementClosureDocument(
        document=model.document_id,
        requirements=len(model.requirements),
        source_candidates=len(extracted),
        explicit_requirements=sum(item.extraction == "explicit" for item in model.requirements),
        candidate_requirements=sum(item.extraction == "candidate" for item in model.requirements),
        requirement_reviews=len(model.requirement_reviews),
        table_count=len(model.tables),
        table_requirement_references=table_requirement_references,
        api_binding_rows=len(model.requirement_api_bindings),
        api_binding_requirement_ids=len(binding_ids),
        missing_api_requirement_ids=(
            tuple(sorted(requirement_ids - binding_ids)) if api_binding_audit else ()
        ),
        unexpected_api_requirement_ids=(
            tuple(sorted(binding_ids - requirement_ids)) if api_binding_audit else ()
        ),
        source_path_mismatches=source_path_mismatches,
        missing_source_paths=missing_source_paths,
        failures=tuple(failures),
        passed=not failures,
    )


def build_report(
    roots: tuple[Path, ...] | None = None,
    *,
    workspace_root: Path | None = None,
) -> RequirementClosureReport:
    """Build a deterministic source-to-catalog audit for 2010 roots."""

    selected_roots = roots if roots is not None else _default_roots(repository_root(workspace_root))
    documents = tuple(_document_report(root) for root in selected_roots)
    failures = tuple(
        f"{document.document}: {failure}" for document in documents for failure in document.failures
    )
    return RequirementClosureReport(
        documents=documents,
        failures=failures,
        passed=not failures,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path)
    parser.add_argument("--workspace-root", type=Path, help="used to discover default documents")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    roots = tuple(args.root) if args.root else None
    report = build_report(roots, workspace_root=args.workspace_root)
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        for document in report.documents:
            print(
                f"{document.document}: requirements={document.requirements} "
                f"source-candidates={document.source_candidates} "
                f"explicit={document.explicit_requirements} "
                f"tables={document.table_count}"
            )
        print(f"2010 requirement closure: {'passed' if report.passed else 'failed'}")
        for failure in report.failures:
            print(f"failure: {failure}")
    return 0 if report.passed or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
