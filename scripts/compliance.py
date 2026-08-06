"""Query semantic requirements, transitions, and implementation coverage."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from scripts.hla_semantic import load_hla_corpus
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hla_semantic import load_hla_corpus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        type=Path,
        nargs="+",
        help="One document source directory, or several for a corpus report",
    )
    parser.add_argument(
        "--document",
        help="Select one document ID when querying a multi-document corpus",
    )
    parser.add_argument("--machine", help="State-machine ID to query")
    parser.add_argument("--state", help="Source state ID")
    parser.add_argument("--event", help="Transition event text")
    parser.add_argument("--requirement-id", help="Filter implementation mappings by requirement")
    parser.add_argument("--clause-id", help="Filter implementation mappings by clause")
    parser.add_argument("--transition-id", help="Filter implementation mappings by transition")
    parser.add_argument(
        "--implementation-status",
        choices=("planned", "partial", "implemented", "verified"),
        help="Filter implementation mappings by lifecycle status",
    )
    parser.add_argument(
        "--interface-kind",
        choices=("service", "callback", "adapter", "handler"),
        help="Filter implementation mappings by interface kind",
    )
    parser.add_argument(
        "--require-concrete-implementation",
        action="store_true",
        help="Report planned or partial mappings as compliance gaps",
    )
    parser.add_argument(
        "--include-candidates",
        action="store_true",
        help="Include unreviewed candidate requirements in coverage queries",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable query results",
    )
    args = parser.parse_args()
    if args.json and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if (args.state is None) != (args.event is None):
        parser.error("--state and --event must be supplied together")
    if (
        len(args.roots) > 1
        and not args.document
        and any(value is not None for value in (args.machine, args.state, args.event))
    ):
        parser.error("state/event queries across multiple roots require --document")

    corpus = load_hla_corpus(args.roots)
    if args.document:
        try:
            model = corpus.document(args.document)
        except ValueError as error:
            parser.error(str(error))
    else:
        model = corpus.documents[0] if len(corpus.documents) == 1 else None
    query = ()
    query_result = None
    if model is not None and args.state is not None and args.event is not None:
        query_result = model.compliance_query(
            args.state,
            args.event,
            args.machine,
            include_candidates=args.include_candidates,
            require_concrete_implementation=args.require_concrete_implementation,
        )
        query = model.requirements_applicable_after(
            args.state,
            args.event,
            args.machine,
            include_candidates=args.include_candidates,
        )
    unmapped_by_document = {
        document.document_id: document.transitions_without_implementation_mapping(
            args.machine
            if model is not None and document.document_id == model.document_id
            else None
        )
        for document in corpus.documents
    }
    unmapped = unmapped_by_document.get(model.document_id, ()) if model else ()
    transition_coverage = {
        document.document_id: document.transition_coverage_counts() for document in corpus.documents
    }
    requirement_reviews = {
        document.document_id: document.requirement_review_counts() for document in corpus.documents
    }
    document_issues = {
        document.document_id: document.compliance_issues(
            args.machine
            if model is not None and document.document_id == model.document_id
            else None,
            include_candidates=args.include_candidates,
            require_concrete_implementation=args.require_concrete_implementation,
        )
        for document in corpus.documents
    }
    issues = (
        tuple(issue for items in document_issues.values() for issue in items)
        + corpus.unresolved_reference_issues()
    )
    payload = {
        "documents": [document.document_id for document in corpus.documents],
        "query": [item.model_dump(mode="json") for item in query],
        "unmapped_transitions": (
            [item.id for item in unmapped]
            if model is not None
            else [
                f"{document_id}:{item.id}"
                for document_id, items in unmapped_by_document.items()
                for item in items
            ]
        ),
        "transition_coverage": (
            transition_coverage.get(model.document_id, {})
            if model is not None
            else transition_coverage
        ),
        "requirement_reviews": (
            requirement_reviews.get(model.document_id, {})
            if model is not None
            else requirement_reviews
        ),
        "issue_counts": dict(Counter(item.code for item in issues)),
        "issues": [item.model_dump(mode="json") for item in issues],
    }
    mappings_by_document = {}
    for document in corpus.documents:
        mappings = document.implementations
        if args.implementation_status:
            mappings = tuple(item for item in mappings if item.status == args.implementation_status)
        if args.interface_kind:
            mappings = tuple(
                item for item in mappings if item.interface_kind == args.interface_kind
            )
        if args.requirement_id:
            mappings = tuple(
                item for item in mappings if args.requirement_id in item.requirement_ids
            )
        if args.clause_id:
            mappings = tuple(item for item in mappings if args.clause_id in item.clause_ids)
        if args.transition_id:
            mappings = tuple(item for item in mappings if args.transition_id in item.transition_ids)
        mappings_by_document[document.document_id] = [
            item.model_dump(mode="json") for item in mappings
        ]
    payload["implementation_mappings"] = (
        mappings_by_document.get(model.document_id, [])
        if model is not None
        else mappings_by_document
    )
    if query_result is not None:
        payload["applicability"] = [
            item.model_dump(mode="json") for item in query_result.applicable_requirements
        ]
        payload["query_transition_coverage"] = [
            item.model_dump(mode="json") for item in query_result.transition_coverage
        ]
        payload["query_implementation_status_counts"] = query_result.implementation_status_counts
    if model is not None:
        payload["document"] = model.document_id
    else:
        payload["issues"] = [
            {
                "document": document_id,
                **issue.model_dump(mode="json"),
            }
            for document_id, items in document_issues.items()
            for issue in items
        ] + [item.model_dump(mode="json") for item in corpus.unresolved_reference_issues()]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if model is not None:
        print(f"document: {model.document_id}")
    else:
        print(f"documents: {len(corpus.documents)}")
    print(f"applicable requirements: {len(query)}")
    print(
        "transitions without mappings: "
        f"{sum(len(items) for items in unmapped_by_document.values())}"
    )
    print(f"compliance issues: {len(issues)}")
    for item in query:
        print(f"{item.id}: {item.statement}")
    for item in issues:
        print(f"{item.code}: {item.record_id} — {item.message}")


if __name__ == "__main__":
    main()
