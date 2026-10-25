"""Audit source-owned requirement closure for the three 2010 documents.

The 2010 source trees use the legacy ``shall``/``must`` extractor rather than
the 2025 page-layout candidate extractor.  This module keeps that distinction
explicit: it compares the legacy source inventory with the promoted catalog,
without inventing 2025-only table-row requirements in the 2010 editions.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from hla_lab.corpus.hla_2010_semantic import _requirements, _surface_inputs
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import RESOURCES, resources

__all__ = [
    "RequirementClosureDocument",
    "RequirementClosureReport",
    "build_report",
]


ROOTS_2010 = (
    tuple(
        RESOURCES.document(document_id).root
        for document_id in ("hla-1516-2010", "hla-1516.1-2010", "hla-1516.2-2010")
    )
    if RESOURCES is not None
    else ()
)


def _default_roots() -> tuple[Path, ...]:
    registry = resources()
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
    source_counts = Counter(item.source.path for item in extracted)
    catalog_counts = Counter(item.source.path for item in model.requirements)
    source_path_mismatches = tuple(
        sorted(
            path
            for path in set(source_counts) | set(catalog_counts)
            if source_counts[path] != catalog_counts[path]
        )
    )
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
    if len(extracted) != len(model.requirements):
        failures.append(
            "promoted requirement count does not match the legacy source candidate inventory"
        )
    if source_path_mismatches:
        failures.append("promoted and extracted requirement counts differ by source path")
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


def build_report(roots: tuple[Path, ...] | None = None) -> RequirementClosureReport:
    """Build a deterministic source-to-catalog audit for 2010 roots."""

    selected_roots = roots if roots is not None else _default_roots()
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
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    roots = tuple(args.root or ()) or _default_roots()
    report = build_report(roots)
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
