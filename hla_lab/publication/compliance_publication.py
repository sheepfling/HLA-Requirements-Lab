"""Build a human-readable compliance requirements publication from a semantic corpus.

The module is deliberately domain-neutral: a document-family profile selects a
corpus and supplies the publication language, while the renderer consumes only
the generic Pydantic semantic and compliance contracts.  A publication is a
planning and evidence surface, not an assertion that an implementation is
conformant without concrete implementation and test evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from hla_lab.adapters.latex_renderer import tex_escape
from hla_lab.core.json_types import JsonValue
from hla_lab.core.links import latex_anchor, qualified_id
from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    ComplianceIssue,
    DocumentModel,
    ImplementationEvidence,
    ImplementationMapping,
    SemanticRecord,
)
from hla_lab.corpus.corpus_graph import CorpusSemanticGraph

__all__ = [
    "ComplianceDependencySummary",
    "ComplianceDocumentSummary",
    "CompliancePublicationManifest",
    "CompliancePublicationProfile",
    "CompliancePublicationSummary",
    "OperationalComplianceItem",
    "RequirementComplianceItem",
    "build_compliance_manifest",
    "load_compliance_publication_profile",
    "render_compliance_document",
    "write_compliance_csv_exports",
    "write_compliance_publication",
]

ComplianceView = Literal[
    "scope",
    "requirements",
    "operations",
    "evidence",
    "gaps",
    "dependencies",
]
RequirementEvidenceStatus = Literal[
    "no-evidence",
    "planned",
    "partial",
    "implemented",
    "verified",
    "mixed",
]
_qualified_id = qualified_id
_anchor = latex_anchor


class CompliancePublicationProfile(SemanticRecord):
    """Source-controlled contract for a compliance-oriented derivative."""

    schema_version: int = Field(ge=1)
    publication_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    subtitle: str = ""
    document_ids: tuple[str, ...] = Field(min_length=1)
    scope_statement: str = Field(min_length=1)
    evidence_boundary: str = Field(min_length=1)
    views: tuple[ComplianceView, ...] = (
        "scope",
        "requirements",
        "operations",
        "evidence",
        "gaps",
        "dependencies",
    )

    @model_validator(mode="after")
    def validate_profile(self) -> CompliancePublicationProfile:
        if len(self.document_ids) != len(set(self.document_ids)):
            raise ValueError("compliance publication document IDs must be unique")
        if len(self.views) != len(set(self.views)):
            raise ValueError("compliance publication views must be unique")
        required = {
            "scope",
            "requirements",
            "operations",
            "evidence",
            "gaps",
            "dependencies",
        }
        missing = sorted(required - set(self.views))
        if missing:
            raise ValueError(f"compliance publication is missing required views: {missing}")
        return self


class ComplianceDocumentSummary(SemanticRecord):
    """One selected corpus document's coverage and evidence totals."""

    document_id: str = Field(min_length=1)
    requirement_count: int = Field(ge=0)
    definition_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    table_family_count: int = Field(ge=0)
    state_machine_count: int = Field(ge=0)
    transition_count: int = Field(ge=0)
    sequence_message_count: int = Field(ge=0)
    implementation_mapping_count: int = Field(ge=0)
    concrete_implementation_count: int = Field(ge=0)
    implementation_status_counts: dict[str, int] = Field(default_factory=dict)
    table_definition_dependency_count: int = Field(ge=0)
    cross_document_edge_count: int = Field(ge=0)
    graph_finding_counts: dict[str, int] = Field(default_factory=dict)


class RequirementComplianceItem(SemanticRecord):
    """A normative record annotated with its current implementation evidence."""

    qualified_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    statement: str
    machine_statement: str
    clause_id: str | None = None
    kind: Literal["summary", "detailed"]
    coverage_kind: Literal["transition", "cross-cutting", "document-wide", "not-applicable"]
    coverage_note: str = ""
    transition_ids: tuple[str, ...] = ()
    implementation_mapping_ids: tuple[str, ...] = ()
    evidence_status: RequirementEvidenceStatus
    concrete_mapping_count: int = Field(ge=0)


class OperationalComplianceItem(SemanticRecord):
    """A state transition expressed as an implementable conformance rule."""

    qualified_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    transition_id: str = Field(min_length=1)
    source_state: str | None = None
    target_state: str | None = None
    event: str = ""
    guard: str = ""
    action: str = ""
    precondition: str = ""
    postcondition: str = ""
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    implementation_mapping_ids: tuple[str, ...] = ()
    implementation_status: Literal[
        "unmapped",
        "planned",
        "partial",
        "implemented",
        "verified",
        "mixed",
    ]
    concrete: bool


class ComplianceDependencySummary(SemanticRecord):
    """Human-scale dependency metrics while full edges remain queryable in JSON."""

    document_id: str = Field(min_length=1)
    semantic_dependency_count: int = Field(ge=0)
    table_definition_dependency_count: int = Field(ge=0)
    cross_document_edge_count: int = Field(ge=0)
    candidate_cross_document_edge_count: int = Field(ge=0)
    graph_finding_counts: dict[str, int] = Field(default_factory=dict)


class CompliancePublicationSummary(SemanticRecord):
    """Corpus-wide headline counts for a compliance publication."""

    document_count: int = Field(ge=1)
    requirement_count: int = Field(ge=0)
    operational_transition_count: int = Field(ge=0)
    sequence_message_count: int = Field(ge=0)
    implementation_mapping_count: int = Field(ge=0)
    concrete_implementation_count: int = Field(ge=0)
    evidence_status_counts: dict[str, int] = Field(default_factory=dict)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    semantic_dependency_count: int = Field(ge=0)
    cross_document_edge_count: int = Field(ge=0)
    graph_finding_counts: dict[str, int] = Field(default_factory=dict)


class CompliancePublicationManifest(SemanticRecord):
    """Pydantic-serializable source for the PDF and downstream RTI checks."""

    schema_version: int = Field(default=1, ge=1)
    profile: CompliancePublicationProfile
    summary: CompliancePublicationSummary
    documents: tuple[ComplianceDocumentSummary, ...]
    requirements: tuple[RequirementComplianceItem, ...]
    operations: tuple[OperationalComplianceItem, ...]
    implementation_evidence: tuple[ImplementationEvidence, ...]
    gaps: tuple[ComplianceIssue, ...]
    dependencies: tuple[ComplianceDependencySummary, ...]

    @model_validator(mode="after")
    def validate_manifest(self) -> CompliancePublicationManifest:
        document_ids = tuple(item.document_id for item in self.documents)
        if document_ids != self.profile.document_ids:
            raise ValueError("compliance manifest documents must follow profile document_ids")
        qualified_ids = [item.qualified_id for item in self.requirements]
        if len(qualified_ids) != len(set(qualified_ids)):
            raise ValueError("compliance manifest requirement IDs must be unique")
        operation_ids = [item.qualified_id for item in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("compliance manifest operation IDs must be unique")
        return self

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the contract deterministically through Pydantic."""
        return self.model_dump_json(indent=indent)


def load_compliance_publication_profile(path: Path) -> CompliancePublicationProfile:
    """Load and validate a source-controlled compliance publication profile."""
    return CompliancePublicationProfile.model_validate_json(path.read_text(encoding="utf-8"))


def _display_text(value: str) -> str:
    """Normalize recovered TeX layout markers for a semantic publication.

    The source corpus preserves text as recovered from faithful layout adapters.
    A bare percent marker there is ordinarily a TeX line-joining artifact, while
    a percent attached to a numeric value is meaningful and remains intact.
    """
    for escaped, plain in (
        (r"\_", "_"),
        (r"\&", "&"),
        (r"\%", "%"),
        (r"\#", "#"),
        (r"\{", "{"),
        (r"\}", "}"),
        (r"\\", " "),
        (r"\ ", " "),
    ):
        value = value.replace(escaped, plain)
    value = re.sub(r"(?<!\d)(?<!\d\s)\s*%\s*", " ", value)
    return " ".join(value.split())


def _evidence_status(statuses: Iterable[str]) -> RequirementEvidenceStatus:
    values = tuple(sorted(set(statuses)))
    if not values:
        return "no-evidence"
    if len(values) == 1:
        return values[0]  # type: ignore[return-value]
    return "mixed"


def _selected_corpus(
    corpus: ComplianceCorpus,
    profile: CompliancePublicationProfile,
) -> ComplianceCorpus:
    models = tuple(corpus.document(document_id) for document_id in profile.document_ids)
    return ComplianceCorpus(documents=models)


def _mapping_index(
    models: Iterable[DocumentModel],
) -> dict[str, tuple[ImplementationMapping, ...]]:
    """Index mappings by requirement and transition without domain vocabulary."""
    index: dict[str, list[ImplementationMapping]] = defaultdict(list)
    for model in models:
        for mapping in model.implementations:
            for requirement_id in mapping.requirement_ids:
                index[f"requirement:{model.document_id}:{requirement_id}"].append(mapping)
            for transition_id in mapping.transition_ids:
                index[f"transition:{model.document_id}:{transition_id}"].append(mapping)
    return {key: tuple(sorted(value, key=lambda item: item.id)) for key, value in index.items()}


def _requirements(
    models: Iterable[DocumentModel],
    mapping_index: Mapping[str, tuple[ImplementationMapping, ...]],
) -> tuple[RequirementComplianceItem, ...]:
    result: list[RequirementComplianceItem] = []
    for model in models:
        for requirement in model.ordered_requirements():
            mappings = {
                item.id: item
                for item in (
                    *mapping_index.get(f"requirement:{model.document_id}:{requirement.id}", ()),
                    *(
                        mapping
                        for transition_id in requirement.transition_ids
                        for mapping in mapping_index.get(
                            f"transition:{model.document_id}:{transition_id}", ()
                        )
                    ),
                )
            }
            status = _evidence_status(item.status for item in mappings.values())
            result.append(
                RequirementComplianceItem(
                    qualified_id=_qualified_id(model.document_id, requirement.id),
                    document_id=model.document_id,
                    requirement_id=requirement.id,
                    title=requirement.title,
                    statement=_display_text(requirement.statement),
                    machine_statement=_display_text(
                        requirement.machine_statement or requirement.statement
                    ),
                    clause_id=requirement.clause_id,
                    kind=requirement.kind,
                    coverage_kind=requirement.coverage_kind,
                    coverage_note=requirement.coverage_note,
                    transition_ids=requirement.transition_ids,
                    implementation_mapping_ids=tuple(sorted(mappings)),
                    evidence_status=status,
                    concrete_mapping_count=sum(
                        item.status in {"implemented", "verified"} for item in mappings.values()
                    ),
                )
            )
    return tuple(sorted(result, key=lambda item: (item.document_id, item.requirement_id)))


def _operations(models: Iterable[DocumentModel]) -> tuple[OperationalComplianceItem, ...]:
    result: list[OperationalComplianceItem] = []
    for model in models:
        for machine in model.state_machines:
            for transition in machine.transitions:
                coverage = model.implementation_coverage_for_transition(transition.id, machine.id)
                result.append(
                    OperationalComplianceItem(
                        qualified_id=_qualified_id(model.document_id, transition.id),
                        document_id=model.document_id,
                        machine_id=machine.id,
                        transition_id=transition.id,
                        source_state=transition.source_state,
                        target_state=transition.target_state,
                        event=transition.event,
                        guard=transition.guard,
                        action=transition.action,
                        precondition=transition.precondition,
                        postcondition=transition.postcondition,
                        clause_id=transition.clause_id,
                        requirement_ids=transition.requirement_ids,
                        implementation_mapping_ids=coverage.mapping_ids,
                        implementation_status=coverage.status,
                        concrete=coverage.concrete,
                    )
                )
    return tuple(
        sorted(result, key=lambda item: (item.document_id, item.machine_id, item.transition_id))
    )


def _document_summary(
    model: DocumentModel,
    selected: ComplianceCorpus,
    graph: CorpusSemanticGraph | None,
) -> ComplianceDocumentSummary:
    transitions = tuple(
        transition for machine in model.state_machines for transition in machine.transitions
    )
    evidence = selected.implementation_evidence(model.document_id)
    graph_edges = graph.cross_document_edges(model.document_id) if graph is not None else ()
    graph_findings = graph.findings_for(model.document_id) if graph is not None else ()
    return ComplianceDocumentSummary(
        document_id=model.document_id,
        requirement_count=len(model.requirements),
        definition_count=len(model.definitions),
        table_count=len(model.tables),
        table_family_count=len(model.table_families),
        state_machine_count=len(model.state_machines),
        transition_count=len(transitions),
        sequence_message_count=sum(len(item.messages) for item in model.sequence_diagrams),
        implementation_mapping_count=len(model.implementations),
        concrete_implementation_count=sum(item.concrete for item in evidence),
        implementation_status_counts=dict(
            sorted(Counter(item.status for item in evidence).items())
        ),
        table_definition_dependency_count=len(
            selected.table_definition_dependencies(model.document_id)
        ),
        cross_document_edge_count=len(graph_edges),
        graph_finding_counts=dict(sorted(Counter(item.kind for item in graph_findings).items())),
    )


def _dependency_summaries(
    selected: ComplianceCorpus,
    graph: CorpusSemanticGraph | None,
) -> tuple[ComplianceDependencySummary, ...]:
    result: list[ComplianceDependencySummary] = []
    for model in selected.documents:
        graph_edges = graph.cross_document_edges(model.document_id) if graph is not None else ()
        findings = graph.findings_for(model.document_id) if graph is not None else ()
        result.append(
            ComplianceDependencySummary(
                document_id=model.document_id,
                semantic_dependency_count=len(selected.semantic_dependencies(model.document_id)),
                table_definition_dependency_count=len(
                    selected.table_definition_dependencies(model.document_id)
                ),
                cross_document_edge_count=len(graph_edges),
                candidate_cross_document_edge_count=sum(
                    item.evidence == "candidate" for item in graph_edges
                ),
                graph_finding_counts=dict(sorted(Counter(item.kind for item in findings).items())),
            )
        )
    return tuple(result)


def build_compliance_manifest(
    corpus: ComplianceCorpus,
    profile: CompliancePublicationProfile,
    *,
    graph: CorpusSemanticGraph | None = None,
) -> CompliancePublicationManifest:
    """Project the selected semantic corpus into a requirements/evidence contract."""
    selected = _selected_corpus(corpus, profile)
    mapping_index = _mapping_index(selected.documents)
    requirements = _requirements(selected.documents, mapping_index)
    operations = _operations(selected.documents)
    evidence = selected.implementation_evidence()
    gaps = tuple(
        sorted(
            {
                (item.code, item.record_id): item
                for item in (
                    *selected.compliance_issues(require_concrete_implementation=True),
                    *selected.unresolved_reference_issues(),
                )
            }.values(),
            key=lambda item: (item.code, item.record_id),
        )
    )
    documents = tuple(_document_summary(model, selected, graph) for model in selected.documents)
    dependencies = _dependency_summaries(selected, graph)
    graph_edges = graph.cross_document_edges() if graph is not None else ()
    graph_findings = graph.findings if graph is not None else ()
    return CompliancePublicationManifest(
        profile=profile,
        summary=CompliancePublicationSummary(
            document_count=len(selected.documents),
            requirement_count=len(requirements),
            operational_transition_count=len(operations),
            sequence_message_count=sum(
                len(item.messages)
                for model in selected.documents
                for item in model.sequence_diagrams
            ),
            implementation_mapping_count=len(evidence),
            concrete_implementation_count=sum(item.concrete for item in evidence),
            evidence_status_counts=dict(sorted(Counter(item.status for item in evidence).items())),
            issue_counts=dict(sorted(Counter(item.code for item in gaps).items())),
            semantic_dependency_count=len(selected.semantic_dependencies()),
            cross_document_edge_count=len(graph_edges),
            graph_finding_counts=dict(
                sorted(Counter(item.kind for item in graph_findings).items())
            ),
        ),
        documents=documents,
        requirements=requirements,
        operations=operations,
        implementation_evidence=evidence,
        gaps=gaps,
        dependencies=dependencies,
    )


def _text(value: str) -> str:
    """Escape semantic source text while preserving source-style punctuation."""
    return (
        tex_escape(_display_text(value))
        .replace("ₛ", r"\textsubscript{s}")
        .replace("∀", r"\ensuremath{\forall}")
        .replace("†", r"\textdagger{}")
        .replace("≤", r"\ensuremath{\leq}")
        .replace("≥", r"\ensuremath{\geq}")
        .replace("≠", r"\ensuremath{\neq}")
        .replace("∈", r"\ensuremath{\in}")
        .replace("∅", r"\ensuremath{\emptyset}")
    )


def _identifier(value: str) -> str:
    """Render a stable ID with deliberate line-break opportunities."""
    return (
        _text(value)
        .replace("-", r"-\allowbreak{}")
        .replace(".", r".\allowbreak{}")
        .replace(r"\_", r"\_\allowbreak{}")
    )


def _heading(level: int, value: str) -> str:
    command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(level, "paragraph")
    return f"\\{command}*{{{_text(value)}}}"


def _clause_label(model: DocumentModel, clause_id: str | None) -> str:
    if clause_id is None:
        return "No clause assignment"
    clause = next((item for item in model.clauses if item.id == clause_id), None)
    if clause is None:
        return clause_id
    title = clause.title.removeprefix(f"{clause.number}. ").removeprefix(f"{clause.number} ")
    return f"{clause.number} {title}".strip()


def _requirement_title(value: str) -> str:
    """Keep extracted source-location titles out of the reading flow."""
    if value.casefold().startswith("normative ") and " at " in value:
        return "Source-derived normative statement"
    return value


def _requirement_lines(
    manifest: CompliancePublicationManifest,
    models: Mapping[str, DocumentModel],
) -> list[str]:
    lines = [_heading(1, "Normative requirements catalog")]
    grouped: dict[str, dict[str | None, list[RequirementComplianceItem]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item in manifest.requirements:
        grouped[item.document_id][item.clause_id].append(item)
    for document_id in manifest.profile.document_ids:
        model = models[document_id]
        lines.append(_heading(2, document_id))
        clause_groups = grouped[document_id]
        ordered_clause_ids = [item.id for item in model.ordered_clauses()]
        for clause_id in (*ordered_clause_ids, None):
            items = clause_groups.get(clause_id, ())
            if not items:
                continue
            lines.append(_heading(3, _clause_label(model, clause_id)))
            for item in items:
                lines.extend(
                    (
                        _anchor(item.document_id, item.requirement_id),
                        "\\paragraph*{Requirement}",
                        f"\\textbf{{ID.}} \\texttt{{{_identifier(item.requirement_id)}}}",
                        f"\\textbf{{Title.}} {_text(_requirement_title(item.title))}",
                        f"\\textbf{{Requirement.}} {_text(item.statement)}",
                        f"\\textbf{{Machine expression.}} {_text(item.machine_statement)}",
                        f"\\textbf{{Coverage.}} {_text(item.coverage_kind)}"
                        + (f" — {_text(item.coverage_note)}" if item.coverage_note else ""),
                        "\\textbf{Operational bindings.} "
                        + (
                            ", ".join(
                                f"\\texttt{{{_identifier(value)}}}" for value in item.transition_ids
                            )
                            if item.transition_ids
                            else "None recorded."
                        ),
                        "\\textbf{Implementation evidence.} "
                        f"{_text(item.evidence_status)}"
                        + (
                            f" ({item.concrete_mapping_count} concrete mapping(s))"
                            if item.concrete_mapping_count
                            else ""
                        )
                        + ".",
                        "\\textbf{Mapping IDs.} "
                        + (
                            ", ".join(
                                f"\\texttt{{{_identifier(value)}}}"
                                for value in item.implementation_mapping_ids
                            )
                            if item.implementation_mapping_ids
                            else "None recorded."
                        ),
                        "\\par",
                    )
                )
    return lines


def _operations_lines(manifest: CompliancePublicationManifest) -> list[str]:
    lines = [_heading(1, "State and service compliance matrix")]
    if not manifest.operations:
        return [*lines, r"\emph{No state-machine transitions are modeled in this corpus scope.}"]
    grouped: dict[tuple[str, str], list[OperationalComplianceItem]] = defaultdict(list)
    for item in manifest.operations:
        grouped[(item.document_id, item.machine_id)].append(item)
    for (document_id, machine_id), items in sorted(grouped.items()):
        lines.append(_heading(2, f"{document_id} — {machine_id}"))
        for item in items:
            lines.extend(
                (
                    _anchor(item.document_id, item.transition_id),
                    "\\paragraph*{Transition}",
                    f"\\textbf{{ID.}} \\texttt{{{_identifier(item.transition_id)}}}",
                    f"\\textbf{{Event.}} {_text(item.event or 'automatic')}",
                    "\\textbf{State change.} "
                    f"{_text(item.source_state or 'initial')} $\\rightarrow$ "
                    f"{_text(item.target_state or 'final')}.",
                    "\\textbf{Precondition.} " + _text(item.precondition or "None recorded."),
                    "\\textbf{Postcondition.} " + _text(item.postcondition or "None recorded."),
                    "\\textbf{Guard.} " + _text(item.guard or "None recorded."),
                    "\\textbf{Action.} " + _text(item.action or "None recorded."),
                    "\\textbf{Requirements.} "
                    + (
                        ", ".join(
                            f"\\texttt{{{_identifier(value)}}}" for value in item.requirement_ids
                        )
                        if item.requirement_ids
                        else "None recorded."
                    ),
                    "\\textbf{Implementation readiness.} "
                    f"{_text(item.implementation_status)}"
                    + (" (concrete evidence present)." if item.concrete else " (not concrete)."),
                    "\\par",
                )
            )
    return lines


def _evidence_lines(manifest: CompliancePublicationManifest) -> list[str]:
    lines = [_heading(1, "Implementation evidence registry")]
    if not manifest.implementation_evidence:
        return [
            *lines,
            r"\emph{No implementation mappings are in scope. This is not evidence of compliance.}",
        ]
    lines.append(
        _text(
            "Each entry is an implementation seam. The registry deliberately repeats all "
            "mapped interfaces so evidence can be attached without reopening a source page."
        )
    )
    lines.append("\\begin{itemize}")
    for item in manifest.implementation_evidence:
        lines.append(
            f"\\item \\texttt{{{_identifier(item.mapping_id)}}} — "
            f"\\textbf{{{_text(item.status)}.}} {_text(item.document_id)}; "
            f"{_text(item.interface_kind)}: {_text(item.interface_name)}; "
            f"implementation seam: \\texttt{{{_identifier(item.implementation)}}}."
        )
    lines.append("\\end{itemize}")
    return lines


def _gap_lines(manifest: CompliancePublicationManifest) -> list[str]:
    lines = [_heading(1, "Evidence gaps and review boundary")]
    lines.append(_text(manifest.profile.evidence_boundary))
    if not manifest.gaps:
        return [*lines, r"\emph{No modeled evidence gaps are currently reported.}"]
    lines.append("\\begin{itemize}")
    for item in manifest.gaps:
        lines.append(
            f"\\item \\textbf{{{_text(item.code)}}} — "
            f"\\texttt{{{_identifier(item.record_id)}}}: {_text(item.message)}"
        )
    lines.append("\\end{itemize}")
    return lines


def _dependency_lines(manifest: CompliancePublicationManifest) -> list[str]:
    lines = [_heading(1, "Definitions, table dependencies, and corpus review")]
    lines.append(
        "The machine-readable manifest retains qualified requirement, table, definition, "
        "and cross-document dependencies. This section provides the human-scale inventory."
    )
    lines.append(
        "\\begin{longtable}{p{0.24\\textwidth}p{0.13\\textwidth}"
        "p{0.17\\textwidth}p{0.15\\textwidth}p{0.18\\textwidth}}"
    )
    lines.append(
        "\\textbf{Document} & \\textbf{Semantic edges} & \\textbf{Table/definition} & "
        "\\textbf{Cross-document} & \\textbf{Candidate cross-document} \\\\ \\hline"
    )
    for item in manifest.dependencies:
        lines.append(
            f"{_text(item.document_id)} & {item.semantic_dependency_count} & "
            f"{item.table_definition_dependency_count} & {item.cross_document_edge_count} & "
            f"{item.candidate_cross_document_edge_count} \\\\"
        )
    lines.append("\\end{longtable}")
    if manifest.summary.graph_finding_counts:
        lines.append(
            "\\textbf{Cross-document review findings.} "
            + ", ".join(
                f"{_text(kind)}: {count}"
                for kind, count in manifest.summary.graph_finding_counts.items()
            )
            + ". Candidate edges and findings are review data, not inferred normative equivalence."
        )
    return lines


def _csv_source_fields(source: SemanticRecord | None) -> dict[str, str]:
    """Flatten optional provenance into stable spreadsheet columns."""
    if source is None:
        return {"source_path": "", "source_line": "", "source_end_line": ""}
    return {
        "source_path": str(getattr(source, "path", "")),
        "source_line": str(getattr(source, "line", "")),
        "source_end_line": str(getattr(source, "end_line", "") or ""),
    }


def _write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: Iterable[Mapping[str, JsonValue]]
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "true" if value is True else "false" if value is False else value
                    for key, value in row.items()
                }
            )
    return path


def write_compliance_csv_exports(
    manifest: CompliancePublicationManifest,
    output: Path,
) -> tuple[Path, ...]:
    """Write normalized CSV projections for spreadsheet and RTI tooling.

    The Pydantic manifest remains canonical.  Primary tables contain one row per
    semantic record; link tables preserve one-to-many requirement/transition to
    mapping relationships without packing lists into CSV cells.
    """
    mapping_by_key = {
        (item.document_id, item.mapping_id): item for item in manifest.implementation_evidence
    }
    requirements_path = _write_csv(
        output / "requirements.csv",
        (
            "qualified_id",
            "document_id",
            "requirement_id",
            "clause_id",
            "title",
            "statement",
            "machine_statement",
            "kind",
            "coverage_kind",
            "coverage_note",
            "evidence_status",
            "concrete_mapping_count",
        ),
        (
            {
                "qualified_id": item.qualified_id,
                "document_id": item.document_id,
                "requirement_id": item.requirement_id,
                "clause_id": item.clause_id or "",
                "title": item.title,
                "statement": item.statement,
                "machine_statement": item.machine_statement,
                "kind": item.kind,
                "coverage_kind": item.coverage_kind,
                "coverage_note": item.coverage_note,
                "evidence_status": item.evidence_status,
                "concrete_mapping_count": item.concrete_mapping_count,
            }
            for item in manifest.requirements
        ),
    )
    transitions_path = _write_csv(
        output / "transitions.csv",
        (
            "qualified_id",
            "document_id",
            "machine_id",
            "transition_id",
            "source_state",
            "target_state",
            "event",
            "guard",
            "action",
            "precondition",
            "postcondition",
            "clause_id",
            "implementation_status",
            "concrete",
        ),
        (
            {
                "qualified_id": item.qualified_id,
                "document_id": item.document_id,
                "machine_id": item.machine_id,
                "transition_id": item.transition_id,
                "source_state": item.source_state or "",
                "target_state": item.target_state or "",
                "event": item.event,
                "guard": item.guard,
                "action": item.action,
                "precondition": item.precondition,
                "postcondition": item.postcondition,
                "clause_id": item.clause_id or "",
                "implementation_status": item.implementation_status,
                "concrete": item.concrete,
            }
            for item in manifest.operations
        ),
    )
    mappings_path = _write_csv(
        output / "implementation-mappings.csv",
        (
            "qualified_mapping_id",
            "document_id",
            "mapping_id",
            "interface_kind",
            "interface_name",
            "implementation",
            "status",
            "concrete",
            "source_backed",
            "implementation_symbol",
            "implementation_language",
            "implementation_repository",
            "implementation_path",
            "implementation_line",
            "implementation_version",
            "source_path",
            "source_line",
            "source_end_line",
        ),
        (
            {
                "qualified_mapping_id": _qualified_id(item.document_id, item.mapping_id),
                "document_id": item.document_id,
                "mapping_id": item.mapping_id,
                "interface_kind": item.interface_kind,
                "interface_name": item.interface_name,
                "implementation": item.implementation,
                "status": item.status,
                "concrete": item.concrete,
                "source_backed": item.source_backed,
                "implementation_symbol": item.implementation_ref.symbol
                if item.implementation_ref
                else "",
                "implementation_language": item.implementation_ref.language
                if item.implementation_ref
                else "",
                "implementation_repository": item.implementation_ref.repository
                if item.implementation_ref
                else "",
                "implementation_path": item.implementation_ref.path
                if item.implementation_ref
                else "",
                "implementation_line": item.implementation_ref.line
                if item.implementation_ref and item.implementation_ref.line
                else "",
                "implementation_version": item.implementation_ref.version
                if item.implementation_ref
                else "",
                **_csv_source_fields(item.source),
            }
            for item in manifest.implementation_evidence
        ),
    )
    requirement_links_path = _write_csv(
        output / "requirement-mapping-links.csv",
        (
            "qualified_requirement_id",
            "document_id",
            "requirement_id",
            "qualified_mapping_id",
            "mapping_id",
            "mapping_status",
            "mapping_concrete",
            "requirement_evidence_status",
        ),
        (
            {
                "qualified_requirement_id": item.qualified_id,
                "document_id": item.document_id,
                "requirement_id": item.requirement_id,
                "qualified_mapping_id": _qualified_id(item.document_id, mapping_id),
                "mapping_id": mapping_id,
                "mapping_status": mapping_by_key[(item.document_id, mapping_id)].status,
                "mapping_concrete": mapping_by_key[(item.document_id, mapping_id)].concrete,
                "requirement_evidence_status": item.evidence_status,
            }
            for item in manifest.requirements
            for mapping_id in item.implementation_mapping_ids
        ),
    )
    transition_links_path = _write_csv(
        output / "transition-mapping-links.csv",
        (
            "qualified_transition_id",
            "document_id",
            "machine_id",
            "transition_id",
            "qualified_mapping_id",
            "mapping_id",
            "mapping_status",
            "mapping_concrete",
            "transition_implementation_status",
        ),
        (
            {
                "qualified_transition_id": item.qualified_id,
                "document_id": item.document_id,
                "machine_id": item.machine_id,
                "transition_id": item.transition_id,
                "qualified_mapping_id": _qualified_id(item.document_id, mapping_id),
                "mapping_id": mapping_id,
                "mapping_status": mapping_by_key[(item.document_id, mapping_id)].status,
                "mapping_concrete": mapping_by_key[(item.document_id, mapping_id)].concrete,
                "transition_implementation_status": item.implementation_status,
            }
            for item in manifest.operations
            for mapping_id in item.implementation_mapping_ids
        ),
    )
    return (
        requirements_path,
        transitions_path,
        mappings_path,
        requirement_links_path,
        transition_links_path,
    )


def render_compliance_document(
    manifest: CompliancePublicationManifest,
    models: Iterable[DocumentModel],
) -> str:
    """Render a readable requirements/evidence document from a typed manifest."""
    model_index = {item.document_id: item for item in models}
    lines = ["% Generated compliance publication; edit semantic source instead."]
    lines.extend(
        (
            _heading(1, manifest.profile.title),
            _text(manifest.profile.subtitle),
            _heading(1, "Scope and compliance boundary"),
            _text(manifest.profile.scope_statement),
            "\\begin{longtable}{p{0.29\\textwidth}rrrrrr}",
            "\\textbf{Document} & \\textbf{Req.} & \\textbf{Def.} & "
            "\\textbf{Tbl.} & \\textbf{Trans.} & \\textbf{Maps} & "
            "\\textbf{Code} \\\\ \\hline",
        )
    )
    for item in manifest.documents:
        lines.append(
            f"{_text(item.document_id)} & {item.requirement_count} & {item.definition_count} & "
            f"{item.table_count} & {item.transition_count} & {item.implementation_mapping_count} & "
            f"{item.concrete_implementation_count} \\\\"
        )
    lines.append("\\end{longtable}")
    lines.append(
        _text(
            "This publication contains "
            f"{manifest.summary.requirement_count} requirements, "
            f"{manifest.summary.operational_transition_count} state transitions, and "
            f"{manifest.summary.implementation_mapping_count} implementation mappings."
        )
    )
    lines.extend(_requirement_lines(manifest, model_index))
    lines.extend(_operations_lines(manifest))
    lines.extend(_evidence_lines(manifest))
    lines.extend(_gap_lines(manifest))
    lines.extend(_dependency_lines(manifest))
    lines.extend(
        (
            _heading(1, "Machine-readable compliance contract"),
            _text(
                "The generated compliance-manifest.json is the authoritative machine-readable "
                "projection for implementation and CI consumers. It preserves qualified IDs, "
                "requirement-to-transition bindings, mapping status, evidence gaps, and "
                "dependency totals."
            ),
        )
    )
    return "\n\n".join(item for item in lines if item) + "\n"


def write_compliance_publication(
    corpus: ComplianceCorpus,
    profile: CompliancePublicationProfile,
    output: Path,
    *,
    graph: CorpusSemanticGraph | None = None,
    csv_output: Path | None = None,
) -> CompliancePublicationManifest:
    """Generate the JSON contract and LaTeX body below an ignored output directory."""
    manifest = build_compliance_manifest(corpus, profile, graph=graph)
    output.mkdir(parents=True, exist_ok=True)
    (output / "compliance-manifest.json").write_text(manifest.to_json() + "\n", encoding="utf-8")
    if graph is not None:
        (output / "corpus-graph.json").write_text(graph.to_json() + "\n", encoding="utf-8")
    if csv_output is not None:
        write_compliance_csv_exports(manifest, csv_output)
    (output / "compliance-requirements.tex").write_text(
        render_compliance_document(manifest, corpus.documents), encoding="utf-8"
    )
    return manifest


def main() -> None:
    """Validate and print a generated compliance manifest for command-line consumers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("semantic_model", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--csv-output",
        type=Path,
        help="Write normalized requirements, transitions, mappings, and link CSVs",
    )
    args = parser.parse_args()
    payload = json.loads(args.semantic_model.read_text(encoding="utf-8"))
    corpus = ComplianceCorpus.model_validate({"documents": payload["documents"]})
    profile = load_compliance_publication_profile(args.profile)
    manifest = build_compliance_manifest(corpus, profile)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(manifest.to_json() + "\n", encoding="utf-8")
    if args.csv_output:
        write_compliance_csv_exports(manifest, args.csv_output)
    else:
        print(manifest.to_json())


if __name__ == "__main__":
    main()
