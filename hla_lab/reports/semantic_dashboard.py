"""Report deterministic semantic coverage metrics for a document corpus."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from hla_lab.core.semantic_model import ComplianceIssue, DocumentModel
from hla_lab.paths import REPO_ROOT, document_roots

class DashboardModel(BaseModel):
    """Shared immutable base for dashboard report records."""

    model_config = ConfigDict(frozen=True)

class RequirementDashboard(DashboardModel):
    total: int
    explicit: int
    candidate: int
    explicit_with_clause: int
    explicit_transition_covered: int
    explicit_non_transition_covered: int
    explicit_transition_requirements_with_reviewed_links: int
    review_dispositions: dict[str, int]

class ImplementationDashboard(DashboardModel):
    total: int
    by_status: dict[str, int]
    by_interface_kind: dict[str, int]
    with_requirement_links: int
    with_source_reference: int
    effective_transition_status: dict[str, int]
    concrete_transition_mappings: int

class StateMachineDashboard(DashboardModel):
    total: int
    states: int
    transitions: int
    transitions_mapped: int
    transitions_unmapped: int
    transitions_with_guard: int
    transitions_with_action: int
    transitions_with_precondition: int
    transitions_with_postcondition: int
    transition_coverage: dict[str, int]

class SequenceDashboard(DashboardModel):
    total: int
    participants: int
    messages: int

class IssueDashboard(DashboardModel):
    reviewed: int
    reviewed_by_code: dict[str, int]
    including_candidates: int
    including_candidates_by_code: dict[str, int]

class M5ContractDashboard(DashboardModel):
    explicit_requirements_have_clause_ownership: bool
    explicit_transition_requirements_have_reviewed_links: bool
    duplicate_ids_validated: bool
    state_targets_validated: bool

class DocumentDashboard(DashboardModel):
    document: str
    requirements: RequirementDashboard
    requirement_links: int
    implementation_mappings: ImplementationDashboard
    state_machines: StateMachineDashboard
    sequence_diagrams: SequenceDashboard
    issues: IssueDashboard
    m5_contract: M5ContractDashboard

class DashboardTotals(DashboardModel):
    documents: int
    requirements: int
    explicit_requirements: int
    candidate_requirements: int
    deferred_requirement_candidates: int
    requirement_links: int
    implementation_mappings: int
    transitions: int
    transitions_mapped: int
    transitions_unmapped: int
    transitions_without_coverage: int
    unresolved_references: int

class DashboardReport(DashboardModel):
    documents: tuple[DocumentDashboard, ...]
    totals: DashboardTotals
    unresolved_references: tuple[ComplianceIssue, ...]

def _document_report(model: DocumentModel) -> DocumentDashboard:
    requirements = model.requirements
    explicit = tuple(item for item in requirements if item.extraction == "explicit")
    candidates = tuple(item for item in requirements if item.extraction == "candidate")
    transitions = tuple(
        transition for machine in model.state_machines for transition in machine.transitions
    )
    mapped_transitions = tuple(
        transition
        for transition in transitions
        if transition.implementation_ids
        or model.implementation_mappings_for_transition(transition.id)
    )
    link_pairs = {(link.requirement_id, link.transition_id) for link in model.requirement_links}
    transition_requirements = tuple(item for item in explicit if item.coverage_kind == "transition")
    reviewed_transition_requirements = tuple(
        item
        for item in transition_requirements
        if item.transition_ids
        and all((item.id, transition_id) in link_pairs for transition_id in item.transition_ids)
    )
    issues = model.compliance_issues()
    candidate_issues = model.compliance_issues(include_candidates=True)
    implementation_status = model.implementation_status_counts()
    return DocumentDashboard(
        document=model.document_id,
        requirements=RequirementDashboard(
            total=len(requirements),
            explicit=len(explicit),
            candidate=len(candidates),
            explicit_with_clause=sum(item.clause_id is not None for item in explicit),
            explicit_transition_covered=len(transition_requirements),
            explicit_non_transition_covered=len(explicit) - len(transition_requirements),
            explicit_transition_requirements_with_reviewed_links=len(
                reviewed_transition_requirements
            ),
            review_dispositions=model.requirement_review_counts(),
        ),
        requirement_links=len(model.requirement_links),
        implementation_mappings=ImplementationDashboard(
            total=len(model.implementations),
            by_status=dict(sorted(Counter(item.status for item in model.implementations).items())),
            by_interface_kind=dict(
                sorted(Counter(item.interface_kind for item in model.implementations).items())
            ),
            with_requirement_links=sum(
                bool(item.requirement_ids) for item in model.implementations
            ),
            with_source_reference=sum(
                bool(item.implementation_ref and item.implementation_ref.path)
                for item in model.implementations
            ),
            effective_transition_status=implementation_status,
            concrete_transition_mappings=implementation_status["implemented"]
                                         + implementation_status["verified"],
        ),
        state_machines=StateMachineDashboard(
            total=len(model.state_machines),
            states=sum(len(machine.states) for machine in model.state_machines),
            transitions=len(transitions),
            transitions_mapped=len(mapped_transitions),
            transitions_unmapped=len(transitions) - len(mapped_transitions),
            transitions_with_guard=sum(bool(item.guard.strip()) for item in transitions),
            transitions_with_action=sum(bool(item.action.strip()) for item in transitions),
            transitions_with_precondition=sum(
                bool(item.precondition.strip()) for item in transitions
            ),
            transitions_with_postcondition=sum(
                bool(item.postcondition.strip()) for item in transitions
            ),
            transition_coverage=model.transition_coverage_counts(),
        ),
        sequence_diagrams=SequenceDashboard(
            total=len(model.sequence_diagrams),
            participants=sum(len(item.participants) for item in model.sequence_diagrams),
            messages=sum(len(item.messages) for item in model.sequence_diagrams),
        ),
        issues=IssueDashboard(
            reviewed=len(issues),
            reviewed_by_code=dict(sorted(Counter(item.code for item in issues).items())),
            including_candidates=len(candidate_issues),
            including_candidates_by_code=dict(
                sorted(Counter(item.code for item in candidate_issues).items())
            ),
        ),
        m5_contract=M5ContractDashboard(
            explicit_requirements_have_clause_ownership=all(
                item.clause_id is not None for item in explicit
            ),
            explicit_transition_requirements_have_reviewed_links=len(
                reviewed_transition_requirements
            )
                                                                 == len(transition_requirements),
            duplicate_ids_validated=True,
            state_targets_validated=True,
        ),
    )

def build_dashboard(roots: tuple[Path, ...]) -> DashboardReport:
    """Load an HLA corpus at the CLI boundary and return source-only metrics."""
    from hla_lab.corpus.hla_semantic import load_hla_corpus

    corpus = load_hla_corpus(roots)
    documents = [_document_report(model) for model in corpus.documents]
    unresolved = corpus.unresolved_reference_issues()
    return DashboardReport(
        documents=tuple(documents),
        totals=DashboardTotals(
            documents=len(documents),
            requirements=sum(item.requirements.total for item in documents),
            explicit_requirements=sum(item.requirements.explicit for item in documents),
            candidate_requirements=sum(item.requirements.candidate for item in documents),
            deferred_requirement_candidates=sum(
                item.requirements.review_dispositions.get("deferred", 0) for item in documents
            ),
            requirement_links=sum(item.requirement_links for item in documents),
            implementation_mappings=sum(item.implementation_mappings.total for item in documents),
            transitions=sum(item.state_machines.transitions for item in documents),
            transitions_mapped=sum(item.state_machines.transitions_mapped for item in documents),
            transitions_unmapped=sum(
                item.state_machines.transitions_unmapped for item in documents
            ),
            transitions_without_coverage=sum(
                item.state_machines.transition_coverage.get("unclassified", 0) for item in documents
            ),
            unresolved_references=len(unresolved),
        ),
        unresolved_references=tuple(unresolved),
    )

def _default_roots() -> tuple[Path, ...]:
    return document_roots(REPO_ROOT)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        help="Document roots; defaults to all document-local build.py projects",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    report = build_dashboard(tuple(path.resolve() for path in args.roots) or _default_roots())
    if args.json:
        print(report.model_dump_json(indent=2))
        return
    totals = report.totals
    print(f"documents: {totals.documents}")
    print(
        "requirements: "
        f"{totals.explicit_requirements} explicit / "
        f"{totals.candidate_requirements} candidates"
    )
    print(
        f"transitions: {totals.transitions_mapped} mapped / {totals.transitions_unmapped} unmapped"
    )
    print(f"unresolved references: {totals.unresolved_references}")

if __name__ == "__main__":
    main()
