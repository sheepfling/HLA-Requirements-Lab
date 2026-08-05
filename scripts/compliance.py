"""Query semantic requirements, transitions, and implementation coverage."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--machine", help="State-machine ID to query")
    parser.add_argument("--state", help="Source state ID")
    parser.add_argument("--event", help="Transition event text")
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
    if (args.state is None) != (args.event is None):
        parser.error("--state and --event must be supplied together")
    if len(args.roots) > 1 and any(
        value is not None for value in (args.machine, args.state, args.event)
    ):
        parser.error("state/event queries require exactly one document root")

    corpus = load_hla_corpus(args.roots)
    model = corpus.documents[0] if len(corpus.documents) == 1 else None
    query = ()
    if model is not None and args.state is not None and args.event is not None:
        query = model.requirements_applicable_after(
            args.state,
            args.event,
            args.machine,
            include_candidates=args.include_candidates,
        )
    unmapped_by_document = {
        document.document_id: document.transitions_missing_implementation_mapping(
            args.machine if model is not None else None
        )
        for document in corpus.documents
    }
    unmapped = unmapped_by_document.get(model.document_id, ()) if model else ()
    document_issues = {
        document.document_id: document.compliance_issues(
            args.machine if model is not None else None,
            include_candidates=args.include_candidates,
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
        "issue_counts": dict(Counter(item.code for item in issues)),
        "issues": [item.model_dump(mode="json") for item in issues],
    }
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
