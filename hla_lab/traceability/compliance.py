"""Query semantic requirements, transitions, and implementation coverage."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from hla_lab.corpus.hla_semantic import load_hla_corpus


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
    parser.add_argument("--api-target", help="Filter API crosswalks by target binding/projection")
    parser.add_argument(
        "--api-status",
        choices=("matched", "ambiguous", "unmatched", "planned"),
        help="Filter API crosswalks by crosswalk status",
    )
    parser.add_argument(
        "--api-gaps",
        action="store_true",
        help="Show only unmatched or planned API crosswalks",
    )
    parser.add_argument(
        "--api-binding-requirement-id",
        help="Filter requirement-to-API bindings by requirement ID",
    )
    parser.add_argument(
        "--api-binding-language",
        help="Filter requirement-to-API bindings by language",
    )
    parser.add_argument(
        "--api-binding-status",
        choices=("candidate", "reviewed", "matched", "ambiguous", "unmatched"),
        help="Filter requirement-to-API bindings by review status",
    )
    parser.add_argument(
        "--api-binding-gaps",
        action="store_true",
        help="Show only candidate, ambiguous, or unmatched requirement-to-API bindings",
    )
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
        "--corpus-report",
        action="store_true",
        help="Include the M24 corpus projection: implications, dependencies, gaps, and evidence",
    )
    parser.add_argument(
        "--dependency-record",
        help="Limit the M24 dependency projection to one semantic record ID",
    )
    parser.add_argument(
        "--implementation-evidence-status",
        choices=("planned", "partial", "implemented", "verified"),
        help="Limit M24 implementation evidence by mapping status",
    )
    parser.add_argument(
        "--concrete-only",
        action="store_true",
        help="Limit M24 implementation evidence to implemented or verified mappings",
    )
    parser.add_argument(
        "--omit-unlinked-implications",
        action="store_true",
        help="Hide sequence messages without a state-transition clause context",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable query results",
    )
    args = parser.parse_args()
    if args.json and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[reportAttributeAccessIssue]
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
    crosswalks_by_document = {}
    crosswalk_counts = {}
    for document in corpus.documents:
        crosswalks = document.api_crosswalks
        if args.api_target:
            crosswalks = tuple(item for item in crosswalks if item.target == args.api_target)
        if args.api_status:
            crosswalks = tuple(item for item in crosswalks if item.status == args.api_status)
        if args.api_gaps:
            crosswalks = tuple(
                item for item in crosswalks if item.status in {"unmatched", "planned"}
            )
        crosswalks_by_document[document.document_id] = [
            item.model_dump(mode="json") for item in crosswalks
        ]
        crosswalk_counts[document.document_id] = dict(
            Counter(item.status for item in document.api_crosswalks)
        )
    payload["api_crosswalks"] = (
        crosswalks_by_document.get(model.document_id, [])
        if model is not None
        else crosswalks_by_document
    )
    payload["api_crosswalk_counts"] = (
        crosswalk_counts.get(model.document_id, {}) if model is not None else crosswalk_counts
    )
    api_bindings_by_document = {}
    api_binding_counts = {}
    api_binding_surfaces_by_document = {}
    for document in corpus.documents:
        bindings = document.requirement_api_bindings
        if args.api_binding_requirement_id:
            bindings = tuple(
                item for item in bindings if item.requirement_id == args.api_binding_requirement_id
            )
        if args.api_binding_language:
            bindings = tuple(
                item for item in bindings if item.language == args.api_binding_language
            )
        if args.api_binding_status:
            bindings = tuple(item for item in bindings if item.status == args.api_binding_status)
        if args.api_binding_gaps:
            bindings = tuple(
                item for item in bindings if item.status in {"candidate", "ambiguous", "unmatched"}
            )
        api_bindings_by_document[document.document_id] = [
            item.model_dump(mode="json") for item in bindings
        ]
        api_binding_counts[document.document_id] = dict(
            Counter(item.status for item in document.requirement_api_bindings)
        )
        referenced_surface_ids = {
            surface_id
            for item in bindings
            for surface_id in (
                *item.candidate_api_surface_ids,
                *((item.api_surface_id,) if item.api_surface_id is not None else ()),
            )
        }
        api_binding_surfaces_by_document[document.document_id] = [
            item.model_dump(mode="json")
            for item in document.api_surfaces
            if item.id in referenced_surface_ids
        ]
    payload["requirement_api_bindings"] = (
        api_bindings_by_document.get(model.document_id, [])
        if model is not None
        else api_bindings_by_document
    )
    payload["requirement_api_binding_counts"] = (
        api_binding_counts.get(model.document_id, {}) if model is not None else api_binding_counts
    )
    payload["requirement_api_surfaces"] = (
        api_binding_surfaces_by_document.get(model.document_id, [])
        if model is not None
        else api_binding_surfaces_by_document
    )
    wants_corpus_report = bool(
        args.corpus_report
        or args.dependency_record
        or args.implementation_evidence_status
        or args.concrete_only
        or args.omit_unlinked_implications
    )
    if wants_corpus_report:
        report = corpus.compliance_report(
            args.document,
            args.state,
            args.event,
            args.machine,
            include_candidates=args.include_candidates,
            require_concrete_implementation=args.require_concrete_implementation,
            dependency_record_id=args.dependency_record,
            include_unlinked_implications=not args.omit_unlinked_implications,
        )
        if args.implementation_evidence_status or args.concrete_only:
            evidence = corpus.implementation_evidence(
                args.document,
                status=args.implementation_evidence_status,
                concrete=True if args.concrete_only else None,
            )
            report = report.model_copy(update={"implementation_evidence": evidence})
        payload["compliance_corpus"] = report.model_dump(mode="json")
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
        ]
        payload["issues"].extend(
            item.model_dump(mode="json") for item in corpus.unresolved_reference_issues()
        )
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
    api_gap_count = sum(
        sum(counts.get(status, 0) for status in ("unmatched", "planned"))
        for counts in crosswalk_counts.values()
    )
    print(f"API crosswalk gaps: {api_gap_count}")
    api_binding_gap_count = sum(
        sum(counts.get(status, 0) for status in ("candidate", "ambiguous", "unmatched"))
        for counts in api_binding_counts.values()
    )
    print(f"requirement API binding gaps: {api_binding_gap_count}")
    print(f"compliance issues: {len(issues)}")
    if wants_corpus_report:
        report = payload["compliance_corpus"]
        print(
            "M24 corpus projection: "
            f"{len(report['state_sequence_implications'])} implications, "
            f"{len(report['dependencies'])} dependencies, "
            f"{len(report['missing_implementation_mappings'])} unmapped transitions, "
            f"{len(report['implementation_evidence'])} implementation evidence records"
        )
    for item in query:
        print(f"{item.id}: {item.statement}")
    for item in issues:
        print(f"{item.code}: {item.record_id} — {item.message}")


if __name__ == "__main__":
    main()
