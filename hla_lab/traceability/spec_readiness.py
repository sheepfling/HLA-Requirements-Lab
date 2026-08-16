"""Specification-surface readiness checks for RTI-facing development."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pydantic import Field

from hla_lab.core.semantic_model import ApiSurface, ComplianceIssue, DocumentModel, SemanticRecord
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.paths import document_roots

__all__ = [
    "DocumentReadiness",
    "ReadinessFinding",
    "SpecificationReadinessReport",
    "assess_corpus",
    "assess_document",
]

class ReadinessFinding(SemanticRecord):
    """A deterministic readiness diagnostic."""

    code: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    message: str = Field(min_length=1)
    record_ids: tuple[str, ...] = ()

class DocumentReadiness(SemanticRecord):
    """Readiness counts and gaps for one specification document."""

    document_id: str = Field(min_length=1)
    requirement_count: int = Field(ge=0)
    explicit_requirement_count: int = Field(ge=0)
    candidate_requirement_count: int = Field(ge=0)
    state_machine_count: int = Field(ge=0)
    transition_count: int = Field(ge=0)
    implementation_mapping_count: int = Field(ge=0)
    api_surface_count: int = Field(ge=0)
    verification_test_count: int = Field(ge=0)
    state_trace_count: int = Field(ge=0)
    planned_mapping_count: int = Field(ge=0)
    concrete_mapping_count: int = Field(ge=0)
    requirements_without_verification: tuple[str, ...] = ()
    transitions_without_verification: tuple[str, ...] = ()
    transitions_without_api_surface: tuple[str, ...] = ()
    machines_without_trace: tuple[str, ...] = ()
    api_surfaces_without_owner: tuple[str, ...] = ()
    api_surfaces_without_language: tuple[str, ...] = ()
    api_surfaces_without_parameters: tuple[str, ...] = ()
    issues: tuple[ReadinessFinding, ...] = ()
    specification_ready: bool
    api_contract_ready: bool
    implementation_ready: bool

class SpecificationReadinessReport(SemanticRecord):
    """Corpus-level specification readiness result."""

    document_ids: tuple[str, ...]
    documents: tuple[DocumentReadiness, ...]
    unresolved_references: tuple[ComplianceIssue, ...] = ()
    specification_ready: bool
    api_contract_ready: bool
    implementation_ready: bool

def _finding(code: str, severity: str, message: str, *record_ids: str) -> ReadinessFinding:
    return ReadinessFinding(
        code=code,
        severity=severity,
        message=message,
        record_ids=tuple(record_ids),
    )

def _parameters_are_unmodeled(surface: ApiSurface) -> bool:
    """Return whether an empty parameter tuple contradicts the surface signature."""
    if surface.parameters:
        return False
    if surface.language in {"fedpro", "wsdl"}:
        return False
    return "(" in surface.signature and re.search(r"\(\s*\)", surface.signature) is None

def assess_document(model: DocumentModel) -> DocumentReadiness:
    """Assess completeness without treating planned mappings as evidence."""

    requirement_ids = {item.id for item in model.requirements}
    transition_ids = {
        transition.id for machine in model.state_machines for transition in machine.transitions
    }
    verified_requirements = {
        requirement_id
        for test in model.verification_tests
        for requirement_id in test.requirement_ids
    }
    verified_transitions = {
        transition_id for test in model.verification_tests for transition_id in test.transition_ids
    }
    surfaced_transitions = {
        transition_id for surface in model.api_surfaces for transition_id in surface.transition_ids
    }
    traced_machines = {trace.machine_id for trace in model.state_traces}
    declared_surfaces = tuple(
        item for item in model.api_surfaces if item.binding_kind != "semantic"
    )
    owner_gaps = tuple(item.id for item in declared_surfaces if not item.owner.strip())
    language_gaps = tuple(
        item.id for item in declared_surfaces if item.language.casefold() == "unspecified"
    )
    parameter_gaps = tuple(item.id for item in declared_surfaces if _parameters_are_unmodeled(item))
    findings: list[ReadinessFinding] = []
    missing_requirements = tuple(sorted(requirement_ids - verified_requirements))
    missing_transitions = tuple(sorted(transition_ids - verified_transitions))
    missing_surfaces = tuple(sorted(transition_ids - surfaced_transitions))
    missing_machines = tuple(sorted({item.id for item in model.state_machines} - traced_machines))
    if missing_requirements:
        findings.append(
            _finding(
                "requirement-without-verification",
                "error",
                "requirements must have a verification slot",
                *missing_requirements,
            )
        )
    if missing_transitions:
        findings.append(
            _finding(
                "transition-without-verification",
                "error",
                "transitions must have a verification slot",
                *missing_transitions,
            )
        )
    if missing_surfaces:
        findings.append(
            _finding(
                "transition-without-api-surface",
                "error",
                "mapped state transitions must expose an API surface",
                *missing_surfaces,
            )
        )
    if missing_machines:
        findings.append(
            _finding(
                "machine-without-trace",
                "error",
                "each state machine must have at least one trace plan",
                *missing_machines,
            )
        )
    if owner_gaps:
        findings.append(
            _finding(
                "api-surface-without-owner",
                "error",
                "API surfaces must name their owning boundary",
                *owner_gaps,
            )
        )
    if language_gaps:
        findings.append(
            _finding(
                "api-language-unspecified",
                "warning",
                "language-specific API extraction remains open for these surfaces",
                *language_gaps,
            )
        )
    if parameter_gaps:
        findings.append(
            _finding(
                "api-parameters-unmodeled",
                "warning",
                "parameter contracts are not yet extracted for these surfaces",
                *parameter_gaps,
            )
        )
    for issue in model.compliance_issues(include_candidates=False):
        findings.append(_finding(issue.code, issue.severity, issue.message, issue.record_id))

    structural_errors = any(item.severity == "error" for item in findings)
    api_contract_ready = not structural_errors and not language_gaps and not parameter_gaps
    concrete_mapping_count = sum(
        item.status in {"implemented", "verified"} for item in model.implementations
    )
    planned_mapping_count = sum(item.status == "planned" for item in model.implementations)
    implementation_ready = api_contract_ready and concrete_mapping_count == len(
        model.implementations
    )
    return DocumentReadiness(
        document_id=model.document_id,
        requirement_count=len(model.requirements),
        explicit_requirement_count=sum(
            item.extraction == "explicit" for item in model.requirements
        ),
        candidate_requirement_count=sum(
            item.extraction == "candidate" for item in model.requirements
        ),
        state_machine_count=len(model.state_machines),
        transition_count=len(transition_ids),
        implementation_mapping_count=len(model.implementations),
        api_surface_count=len(model.api_surfaces),
        verification_test_count=len(model.verification_tests),
        state_trace_count=len(model.state_traces),
        planned_mapping_count=planned_mapping_count,
        concrete_mapping_count=concrete_mapping_count,
        requirements_without_verification=missing_requirements,
        transitions_without_verification=missing_transitions,
        transitions_without_api_surface=missing_surfaces,
        machines_without_trace=missing_machines,
        api_surfaces_without_owner=owner_gaps,
        api_surfaces_without_language=language_gaps,
        api_surfaces_without_parameters=parameter_gaps,
        issues=tuple(findings),
        specification_ready=not structural_errors,
        api_contract_ready=api_contract_ready,
        implementation_ready=implementation_ready,
    )

def assess_corpus(roots: tuple[Path, ...]) -> SpecificationReadinessReport:
    """Assess a corpus and preserve planned/concrete distinctions."""

    corpus = load_hla_corpus(roots)
    documents = tuple(assess_document(model) for model in corpus.documents)
    unresolved = corpus.unresolved_reference_issues()
    specification_ready = all(item.specification_ready for item in documents) and not unresolved
    api_contract_ready = specification_ready and all(item.api_contract_ready for item in documents)
    implementation_ready = api_contract_ready and all(
        item.implementation_ready for item in documents
    )
    return SpecificationReadinessReport(
        document_ids=tuple(item.document_id for item in corpus.documents),
        documents=documents,
        unresolved_references=unresolved,
        specification_ready=specification_ready,
        api_contract_ready=api_contract_ready,
        implementation_ready=implementation_ready,
    )

def _default_roots(root: Path) -> tuple[Path, ...]:
    return document_roots(root)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--document", action="append", help="Restrict to a document ID")
    parser.add_argument("--require-concrete", action="store_true")
    parser.add_argument("--require-language-contract", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    roots = _default_roots(args.root)
    if args.document:
        wanted = set(args.document)
        roots = tuple(root for root in roots if root.name in wanted)
        if len(roots) != len(wanted):
            raise SystemExit("unknown document supplied to --document")
    report = assess_corpus(roots)
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"specification_ready: {report.specification_ready}")
        print(f"api_contract_ready: {report.api_contract_ready}")
        print(f"implementation_ready: {report.implementation_ready}")
        for item in report.documents:
            print(
                f"{item.document_id}: requirements={item.requirement_count}, "
                f"transitions={item.transition_count}, api_surfaces={item.api_surface_count}, "
                f"tests={item.verification_test_count}, traces={item.state_trace_count}, "
                f"planned={item.planned_mapping_count}, concrete={item.concrete_mapping_count}"
            )
    if not report.specification_ready:
        return 1
    if args.require_language_contract and not report.api_contract_ready:
        return 1
    if args.require_concrete and not report.implementation_ready:
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
