"""Enforce explicit semantic candidate and transition coverage contracts."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from hla_lab.core.semantic_model import DocumentModel
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.paths import REPO_ROOT, document_roots


class CoverageReportModel(BaseModel):
    """Shared immutable base for semantic coverage report records."""

    model_config = ConfigDict(frozen=True)


class RequirementCoverage(CoverageReportModel):
    candidates: int
    reviews: Mapping[str, int]


class TransitionCoverage(CoverageReportModel):
    total: int
    coverage: Mapping[str, int]


class CoverageDocumentReport(CoverageReportModel):
    document: str
    requirements: RequirementCoverage
    transitions: TransitionCoverage
    sequence_diagrams: Mapping[str, int]
    content_blocks: int
    content_elements: int
    semantic_records_without_source: int
    failures: tuple[str, ...]
    passed: bool


class CoverageReport(CoverageReportModel):
    documents: tuple[CoverageDocumentReport, ...]
    failures: tuple[str, ...]
    passed: bool


def _document_report(model: DocumentModel) -> CoverageDocumentReport:
    reviews = model.requirement_review_counts()
    transitions = model.transition_coverage_counts()
    semantic_records = (
        *model.clauses,
        *model.definitions,
        *model.requirements,
        *model.content_blocks,
        *model.content_elements,
        *model.references,
        *model.notes,
        *model.figures,
        *model.examples,
        *model.annexes,
        *model.tables,
        *model.table_families,
        *model.state_machines,
        *model.sequence_diagrams,
        *model.implementations,
    )
    records_without_source = sum(
        getattr(record, "source", None) is None for record in semantic_records
    )
    failures: list[str] = []
    if reviews["unreviewed"]:
        failures.append(f"{reviews['unreviewed']} requirement candidates lack dispositions")
    if transitions["unclassified"]:
        failures.append(f"{transitions['unclassified']} transitions lack coverage dispositions")
    return CoverageDocumentReport(
        document=model.document_id,
        requirements=RequirementCoverage(
            candidates=len(
                tuple(item for item in model.requirements if item.extraction == "candidate")
            ),
            reviews=reviews,
        ),
        transitions=TransitionCoverage(
            total=sum(len(machine.transitions) for machine in model.state_machines),
            coverage=transitions,
        ),
        sequence_diagrams={
            "total": len(model.sequence_diagrams),
            "messages": sum(len(item.messages) for item in model.sequence_diagrams),
        },
        content_blocks=len(model.content_blocks),
        content_elements=len(model.content_elements),
        semantic_records_without_source=records_without_source,
        failures=tuple(failures),
        passed=not failures,
    )


def build_report(roots: tuple[Path, ...]) -> CoverageReport:
    """Return a deterministic M14 coverage report without writing artifacts."""
    corpus = load_hla_corpus(roots)
    documents = [_document_report(model) for model in corpus.documents]
    failures = tuple(
        f"{document.document}: {failure}" for document in documents for failure in document.failures
    )
    return CoverageReport(
        documents=tuple(documents),
        failures=failures,
        passed=not failures,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="Exit nonzero when coverage is incomplete"
    )
    args = parser.parse_args()
    roots = tuple(args.root or document_roots(REPO_ROOT))
    report = build_report(roots)
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        for document in report.documents:
            reviews = document.requirements.reviews
            coverage = document.transitions.coverage
            print(
                f"{document.document}: candidates={document.requirements.candidates} "
                f"unreviewed={reviews['unreviewed']} "
                f"transitions-unclassified={coverage['unclassified']}"
            )
        print(f"semantic coverage: {'passed' if report.passed else 'failed'}")
        for failure in report.failures:
            print(f"failure: {failure}")
    return 0 if report.passed or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
