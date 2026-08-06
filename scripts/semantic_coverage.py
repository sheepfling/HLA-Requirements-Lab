"""Enforce explicit semantic candidate and transition coverage contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.hla_semantic import load_hla_corpus


def _document_report(model: Any) -> dict[str, Any]:
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
    return {
        "document": model.document_id,
        "requirements": {
            "candidates": len(
                tuple(item for item in model.requirements if item.extraction == "candidate")
            ),
            "reviews": reviews,
        },
        "transitions": {
            "total": sum(len(machine.transitions) for machine in model.state_machines),
            "coverage": transitions,
        },
        "content_blocks": len(model.content_blocks),
        "content_elements": len(model.content_elements),
        "semantic_records_without_source": records_without_source,
        "failures": failures,
        "passed": not failures,
    }


def build_report(roots: tuple[Path, ...]) -> dict[str, Any]:
    """Return a deterministic M14 coverage report without writing artifacts."""
    corpus = load_hla_corpus(roots)
    documents = [_document_report(model) for model in corpus.documents]
    failures = [
        f"{document['document']}: {failure}"
        for document in documents
        for failure in document["failures"]
    ]
    return {
        "documents": documents,
        "failures": failures,
        "passed": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="Exit nonzero when coverage is incomplete"
    )
    args = parser.parse_args()
    roots = tuple(args.root or sorted(Path("topics/ieee").glob("hla-1516*/")))
    report = build_report(roots)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for document in report["documents"]:
            reviews = document["requirements"]["reviews"]
            coverage = document["transitions"]["coverage"]
            print(
                f"{document['document']}: candidates={document['requirements']['candidates']} "
                f"unreviewed={reviews['unreviewed']} "
                f"transitions-unclassified={coverage['unclassified']}"
            )
        print(f"semantic coverage: {'passed' if report['passed'] else 'failed'}")
        for failure in report["failures"]:
            print(f"failure: {failure}")
    return 0 if report["passed"] or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
