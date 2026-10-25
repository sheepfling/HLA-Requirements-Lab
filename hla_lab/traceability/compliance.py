"""Query semantic requirements, transitions, and implementation coverage."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from hla_lab.core.json_types import JsonObject, JsonValue
from hla_lab.core.semantic_model import (
    ApiCrosswalk,
    ComplianceCorpus,
    ComplianceIssue,
    ComplianceQueryResult,
    DocumentModel,
    Requirement,
    RequirementApiBinding,
    Transition,
)
from hla_lab.corpus.hla_semantic import load_hla_corpus


def _build_parser() -> argparse.ArgumentParser:
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
    return parser


@dataclass(slots=True)
class _ComplianceSnapshot:
    corpus: ComplianceCorpus
    model: DocumentModel | None
    query: tuple[Requirement, ...]
    query_result: ComplianceQueryResult | None
    unmapped_by_document: dict[str, tuple[Transition, ...]]
    transition_coverage: dict[str, dict[str, int]]
    requirement_reviews: dict[str, dict[str, int]]
    document_issues: dict[str, tuple[ComplianceIssue, ...]]
    issues: tuple[ComplianceIssue, ...]


def _validate_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
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


def _selected_model(
    corpus: ComplianceCorpus,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> DocumentModel | None:
    if args.document:
        try:
            return corpus.document(args.document)
        except ValueError as error:
            parser.error(str(error))
    return corpus.documents[0] if len(corpus.documents) == 1 else None


def _compliance_snapshot(
    corpus: ComplianceCorpus,
    model: DocumentModel | None,
    args: argparse.Namespace,
) -> _ComplianceSnapshot:
    query: tuple[Requirement, ...] = ()
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
    unmapped = {
        document.document_id: document.transitions_without_implementation_mapping(
            args.machine
            if model is not None and document.document_id == model.document_id
            else None
        )
        for document in corpus.documents
    }
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
    issues = tuple(issue for items in document_issues.values() for issue in items)
    issues += corpus.unresolved_reference_issues()
    return _ComplianceSnapshot(
        corpus=corpus,
        model=model,
        query=query,
        query_result=query_result,
        unmapped_by_document=unmapped,
        transition_coverage=transition_coverage,
        requirement_reviews=requirement_reviews,
        document_issues=document_issues,
        issues=issues,
    )


def _base_payload(snapshot: _ComplianceSnapshot) -> JsonObject:
    model = snapshot.model
    unmapped = snapshot.unmapped_by_document.get(model.document_id, ()) if model else ()
    return {
        "documents": [document.document_id for document in snapshot.corpus.documents],
        "query": [item.model_dump(mode="json") for item in snapshot.query],
        "unmapped_transitions": (
            [item.id for item in unmapped]
            if model is not None
            else [
                f"{document_id}:{item.id}"
                for document_id, items in snapshot.unmapped_by_document.items()
                for item in items
            ]
        ),
        "transition_coverage": (
            snapshot.transition_coverage.get(model.document_id, {})
            if model is not None
            else snapshot.transition_coverage
        ),
        "requirement_reviews": (
            snapshot.requirement_reviews.get(model.document_id, {})
            if model is not None
            else snapshot.requirement_reviews
        ),
        "issue_counts": dict(Counter(item.code for item in snapshot.issues)),
        "issues": [item.model_dump(mode="json") for item in snapshot.issues],
    }


def _filtered_implementations(
    document: DocumentModel,
    args: argparse.Namespace,
) -> list[JsonObject]:
    mappings = document.implementations
    if args.implementation_status:
        mappings = tuple(item for item in mappings if item.status == args.implementation_status)
    if args.interface_kind:
        mappings = tuple(item for item in mappings if item.interface_kind == args.interface_kind)
    if args.requirement_id:
        mappings = tuple(item for item in mappings if args.requirement_id in item.requirement_ids)
    if args.clause_id:
        mappings = tuple(item for item in mappings if args.clause_id in item.clause_ids)
    if args.transition_id:
        mappings = tuple(item for item in mappings if args.transition_id in item.transition_ids)
    return [item.model_dump(mode="json") for item in mappings]


def _implementation_payload(
    corpus: ComplianceCorpus,
    model: DocumentModel | None,
    args: argparse.Namespace,
) -> JsonValue:
    by_document = {
        document.document_id: _filtered_implementations(document, args)
        for document in corpus.documents
    }
    return by_document.get(model.document_id, []) if model is not None else by_document


def _filtered_crosswalks(
    document: DocumentModel,
    args: argparse.Namespace,
) -> tuple[ApiCrosswalk, ...]:
    crosswalks = document.api_crosswalks
    if args.api_target:
        crosswalks = tuple(item for item in crosswalks if item.target == args.api_target)
    if args.api_status:
        crosswalks = tuple(item for item in crosswalks if item.status == args.api_status)
    if args.api_gaps:
        crosswalks = tuple(item for item in crosswalks if item.status in {"unmatched", "planned"})
    return crosswalks


def _crosswalk_payload(
    corpus: ComplianceCorpus,
    model: DocumentModel | None,
    args: argparse.Namespace,
) -> tuple[JsonValue, dict[str, dict[str, int]]]:
    by_document: dict[str, list[JsonObject]] = {}
    counts: dict[str, dict[str, int]] = {}
    for document in corpus.documents:
        crosswalks = _filtered_crosswalks(document, args)
        by_document[document.document_id] = [item.model_dump(mode="json") for item in crosswalks]
        counts[document.document_id] = dict(
            Counter(item.status for item in document.api_crosswalks)
        )
    selected = by_document.get(model.document_id, []) if model is not None else by_document
    return selected, counts


def _filtered_api_bindings(
    document: DocumentModel,
    args: argparse.Namespace,
) -> tuple[RequirementApiBinding, ...]:
    bindings = document.requirement_api_bindings
    if args.api_binding_requirement_id:
        bindings = tuple(
            item for item in bindings if item.requirement_id == args.api_binding_requirement_id
        )
    if args.api_binding_language:
        bindings = tuple(item for item in bindings if item.language == args.api_binding_language)
    if args.api_binding_status:
        bindings = tuple(item for item in bindings if item.status == args.api_binding_status)
    if args.api_binding_gaps:
        bindings = tuple(
            item for item in bindings if item.status in {"candidate", "ambiguous", "unmatched"}
        )
    return bindings


def _api_binding_document(
    document: DocumentModel,
    args: argparse.Namespace,
) -> tuple[list[JsonObject], dict[str, int], list[JsonObject]]:
    bindings = _filtered_api_bindings(document, args)
    surfaces = {
        surface_id
        for item in bindings
        for surface_id in (
            *item.candidate_api_surface_ids,
            *((item.api_surface_id,) if item.api_surface_id is not None else ()),
        )
    }
    return (
        [item.model_dump(mode="json") for item in bindings],
        dict(Counter(item.status for item in document.requirement_api_bindings)),
        [item.model_dump(mode="json") for item in document.api_surfaces if item.id in surfaces],
    )


def _api_binding_payloads(
    corpus: ComplianceCorpus,
    model: DocumentModel | None,
    args: argparse.Namespace,
) -> tuple[JsonValue, dict[str, dict[str, int]], JsonValue]:
    bindings: dict[str, list[JsonObject]] = {}
    counts: dict[str, dict[str, int]] = {}
    surfaces: dict[str, list[JsonObject]] = {}
    for document in corpus.documents:
        (
            bindings[document.document_id],
            counts[document.document_id],
            surfaces[document.document_id],
        ) = _api_binding_document(document, args)
    if model is not None:
        return (
            bindings.get(model.document_id, []),
            counts,
            surfaces.get(model.document_id, []),
        )
    return bindings, counts, surfaces


def _corpus_report_requested(args: argparse.Namespace) -> bool:
    return bool(
        args.corpus_report
        or args.dependency_record
        or args.implementation_evidence_status
        or args.concrete_only
        or args.omit_unlinked_implications
    )


def _corpus_report_payload(
    snapshot: _ComplianceSnapshot,
    args: argparse.Namespace,
) -> JsonObject | None:
    if not _corpus_report_requested(args):
        return None
    report = snapshot.corpus.compliance_report(
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
        evidence = snapshot.corpus.implementation_evidence(
            args.document,
            status=args.implementation_evidence_status,
            concrete=True if args.concrete_only else None,
        )
        report = report.model_copy(update={"implementation_evidence": evidence})
    return report.model_dump(mode="json")


def _finish_payload(
    payload: JsonObject,
    snapshot: _ComplianceSnapshot,
) -> None:
    if snapshot.query_result is not None:
        payload["applicability"] = [
            item.model_dump(mode="json") for item in snapshot.query_result.applicable_requirements
        ]
        payload["query_transition_coverage"] = [
            item.model_dump(mode="json") for item in snapshot.query_result.transition_coverage
        ]
        payload["query_implementation_status_counts"] = (
            snapshot.query_result.implementation_status_counts
        )
    if snapshot.model is not None:
        payload["document"] = snapshot.model.document_id
        return
    payload["issues"] = [
        {"document": document_id, **issue.model_dump(mode="json")}
        for document_id, items in snapshot.document_issues.items()
        for issue in items
    ]
    payload["issues"].extend(
        item.model_dump(mode="json") for item in snapshot.corpus.unresolved_reference_issues()
    )


def _build_payload(
    snapshot: _ComplianceSnapshot,
    args: argparse.Namespace,
) -> tuple[JsonObject, dict[str, dict[str, int]], dict[str, dict[str, int]], bool]:
    payload = _base_payload(snapshot)
    payload["implementation_mappings"] = _implementation_payload(
        snapshot.corpus, snapshot.model, args
    )
    crosswalks, crosswalk_counts = _crosswalk_payload(snapshot.corpus, snapshot.model, args)
    payload["api_crosswalks"] = crosswalks
    payload["api_crosswalk_counts"] = (
        crosswalk_counts.get(snapshot.model.document_id, {})
        if snapshot.model is not None
        else crosswalk_counts
    )
    bindings, binding_counts, surfaces = _api_binding_payloads(
        snapshot.corpus, snapshot.model, args
    )
    payload["requirement_api_bindings"] = bindings
    payload["requirement_api_binding_counts"] = (
        binding_counts.get(snapshot.model.document_id, {})
        if snapshot.model is not None
        else binding_counts
    )
    payload["requirement_api_surfaces"] = surfaces
    corpus_report = _corpus_report_payload(snapshot, args)
    if corpus_report is not None:
        payload["compliance_corpus"] = corpus_report
    _finish_payload(payload, snapshot)
    return payload, crosswalk_counts, binding_counts, corpus_report is not None


def _print_summary(
    snapshot: _ComplianceSnapshot,
    payload: Mapping[str, JsonValue],
    crosswalk_counts: Mapping[str, Mapping[str, int]],
    binding_counts: Mapping[str, Mapping[str, int]],
    wants_corpus_report: bool,
) -> None:
    model = snapshot.model
    if model is not None:
        print(f"document: {model.document_id}")
    else:
        print(f"documents: {len(snapshot.corpus.documents)}")
    print(f"applicable requirements: {len(snapshot.query)}")
    print(
        "transitions without mappings: "
        f"{sum(len(items) for items in snapshot.unmapped_by_document.values())}"
    )
    api_gap_count = sum(
        sum(counts.get(status, 0) for status in ("unmatched", "planned"))
        for counts in crosswalk_counts.values()
    )
    print(f"API crosswalk gaps: {api_gap_count}")
    binding_gap_count = sum(
        sum(counts.get(status, 0) for status in ("candidate", "ambiguous", "unmatched"))
        for counts in binding_counts.values()
    )
    print(f"requirement API binding gaps: {binding_gap_count}")
    print(f"compliance issues: {len(snapshot.issues)}")
    if wants_corpus_report:
        report = payload["compliance_corpus"]
        print(
            "M24 corpus projection: "
            f"{len(report['state_sequence_implications'])} implications, "
            f"{len(report['dependencies'])} dependencies, "
            f"{len(report['missing_implementation_mappings'])} unmapped transitions, "
            f"{len(report['implementation_evidence'])} implementation evidence records"
        )
    for item in snapshot.query:
        print(f"{item.id}: {item.statement}")
    for item in snapshot.issues:
        print(f"{item.code}: {item.record_id} — {item.message}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_arguments(parser, args)
    corpus = load_hla_corpus(args.roots)
    model = _selected_model(corpus, args, parser)
    snapshot = _compliance_snapshot(corpus, model, args)
    payload, crosswalk_counts, binding_counts, wants_corpus_report = _build_payload(snapshot, args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    _print_summary(snapshot, payload, crosswalk_counts, binding_counts, wants_corpus_report)


if __name__ == "__main__":
    main()
