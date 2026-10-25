"""Extract reusable semantic records from source-first LaTeX documents."""

from __future__ import annotations

import re
from collections.abc import (
    Mapping,
)
from typing import Annotated, Literal, Protocol, TypeAlias

from pydantic import Field, model_validator

from hla_lab.core.semantic_base import (
    RequirementApplicabilityRelation,
    SemanticRecord,
    SourceRef,
)
from hla_lab.core.semantic_diagram_types import (
    ApplicabilityMatch,
    ApplicabilityMatchView,
    DiagramProvenance,
    DiagramSurface,
    DiagramSurfaceFile,
    GraphAnnotation,
    GraphDiagram,
    GraphDiagramFile,
    GraphEdge,
    GraphNode,
    GraphPoint,
    LayoutAnnotation,
    LayoutContainer,
    LayoutRule,
    NodePosition,
    SequenceDiagram,
    SequenceDiagramFile,
    SequenceMessage,
    SequenceParticipant,
    State,
    StateMachine,
    StateMachineFile,
    StateMachineLayout,
    Transition,
    TransitionLayout,
)
from hla_lab.core.semantic_text import _machine_statement

__all__ = [
    "Annex",
    "AnnexStatus",
    "ApiCrosswalk",
    "ApiCrosswalkFile",
    "ApiParameter",
    "ApiSurface",
    "ApiSurfaceFile",
    "ApplicabilityMatch",
    "ApplicabilityMatchView",
    "CatalogEntry",
    "Clause",
    "CommandArguments",
    "CommandEvent",
    "ComplianceCorpusReport",
    "ComplianceDependency",
    "ComplianceIssue",
    "ComplianceQueryResult",
    "ContentBlock",
    "ContentBlockFile",
    "ContentElement",
    "ContentElementFile",
    "CrossReference",
    "CrossReferenceFile",
    "CrossReferenceKind",
    "Definition",
    "DefinitionFile",
    "DetailedHeading",
    "DiagramProvenance",
    "DiagramSurface",
    "DiagramSurfaceFile",
    "Example",
    "Figure",
    "FigureFile",
    "GraphAnnotation",
    "GraphDiagram",
    "GraphDiagramFile",
    "GraphEdge",
    "GraphNode",
    "GraphPoint",
    "HeadingEvent",
    "HeadingParts",
    "ImplementationEvidence",
    "ImplementationFile",
    "ImplementationMapping",
    "ImplementationReference",
    "ImplementationStatus",
    "LayoutAnnotation",
    "LayoutContainer",
    "LayoutRule",
    "NodePosition",
    "Note",
    "NoteFile",
    "NoteKind",
    "OperationalImplication",
    "Reference",
    "ReferenceAlias",
    "ReferenceFile",
    "ReferenceTarget",
    "Requirement",
    "RequirementApiBinding",
    "RequirementApiBindingFile",
    "RequirementApplicability",
    "RequirementApplicabilityRelation",
    "RequirementFile",
    "RequirementLink",
    "RequirementLinkFile",
    "RequirementMatch",
    "RequirementReview",
    "RequirementReviewFile",
    "RequirementTransitionPair",
    "SemanticRecord",
    "SequenceDiagram",
    "SequenceDiagramFile",
    "SequenceMessage",
    "SequenceParticipant",
    "SourceOrderedRecord",
    "SourceRef",
    "State",
    "StateMachine",
    "StateMachineFile",
    "StateMachineLayout",
    "StateTrace",
    "StateTraceFile",
    "Table",
    "TableBounds",
    "TableCaption",
    "TableCell",
    "TableFamily",
    "TableFamilyFile",
    "TableFile",
    "TableHeading",
    "TableLabel",
    "TablePrimitive",
    "TraceStep",
    "Transition",
    "TransitionCoverage",
    "TransitionCoverageFile",
    "TransitionCoverageStatus",
    "TransitionImplementationCoverage",
    "TransitionLayout",
    "VerificationTest",
    "VerificationTestFile",
    "VisibleReferenceTarget",
]

ImplementationStatus = Literal["planned", "partial", "implemented", "verified"]
TransitionCoverageStatus = Literal[
    "unmapped", "planned", "partial", "implemented", "verified", "mixed"
]
NoteKind = Literal["informative", "definition", "table", "figure", "footnote"]
AnnexStatus = Literal["normative", "informative", "unknown"]
CrossReferenceKind = Literal[
    "clause",
    "definition",
    "requirement",
    "content",
    "table",
    "table-family",
    "reference",
    "note",
    "figure",
    "example",
    "annex",
    "state-machine",
    "state",
    "transition",
    "sequence-diagram",
    "graph-diagram",
    "implementation",
    "api-surface",
    "api-crosswalk",
    "verification-test",
    "state-trace",
    "unknown",
]


CommandArguments: TypeAlias = tuple[str, ...]
CommandEvent: TypeAlias = tuple[int, CommandArguments, int]
TablePrimitive: TypeAlias = tuple[int, str, CommandArguments]
HeadingEvent: TypeAlias = tuple[int, str, str, SourceRef]
HeadingParts: TypeAlias = tuple[str, str]
TableHeading: TypeAlias = tuple[int, str, str, str, float, SourceRef]
DetailedHeading: TypeAlias = tuple[int, int, str, str, SourceRef]
TableCaption: TypeAlias = tuple[str, float, float, float, SourceRef]
TableBounds: TypeAlias = tuple[str, float, float, float, float]
TableLabel: TypeAlias = tuple[str, SourceRef]
CatalogEntry: TypeAlias = tuple[CrossReferenceKind, str]
ReferenceAlias: TypeAlias = tuple[str, str]
VisibleReferenceTarget: TypeAlias = tuple[str, CrossReferenceKind, str]
RequirementTransitionPair: TypeAlias = tuple[str, str]


class SourceOrderedRecord(Protocol):
    source: SourceRef
    id: str


class Clause(SemanticRecord):
    id: Annotated[str, Field(min_length=1)]
    number: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    parent_id: str | None
    level: Annotated[int, Field(ge=1)]
    source: SourceRef


class Definition(SemanticRecord):
    id: Annotated[str, Field(min_length=1)]
    term: Annotated[str, Field(min_length=1)]
    text: str
    layout_body: str | None = None
    leading_gap: str | None = None
    source: SourceRef
    clause_id: str | None = None


class DefinitionFile(SemanticRecord):
    """Authored semantic definition records kept outside hand-written LaTeX."""

    schema_version: Annotated[int, Field(ge=1)]
    definitions: tuple[Definition, ...]


class Requirement(SemanticRecord):
    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    statement: str
    kind: Literal["summary", "detailed"]
    clause: str | None
    clause_id: str | None = None
    machine_statement: str | None = None
    transition_ids: tuple[str, ...] = ()
    coverage_kind: Literal["transition", "cross-cutting", "document-wide", "not-applicable"] = (
        "transition"
    )
    coverage_note: str = ""
    api_surface_scope: Literal["required", "cross-cutting", "not-applicable"] = "required"
    api_surface_note: str = ""
    api_surface_resolution: Literal["strict", "all-overloads"] = "strict"
    extraction: Literal["explicit", "candidate"] = "explicit"
    semantic_group_id: str | None = None
    source: SourceRef

    @model_validator(mode="after")
    def normalize_clause_id(self) -> Requirement:
        expected = f"clause-{self.clause}" if self.clause else None
        if self.clause_id not in (None, expected):
            raise ValueError("clause_id must match clause")
        if self.clause_id != expected:
            object.__setattr__(self, "clause_id", expected)
        self._normalize_generated_title()
        if not self.machine_statement:
            object.__setattr__(
                self,
                "machine_statement",
                _machine_statement(self.statement),
            )
        if not self.semantic_group_id:
            object.__setattr__(self, "semantic_group_id", self.id)
        if self.extraction == "explicit":
            self._validate_explicit_coverage()
        if (
            self.api_surface_scope != "required" or self.api_surface_resolution == "all-overloads"
        ) and not self.api_surface_note.strip():
            raise ValueError("non-standard API surface decisions need an api_surface_note")
        return self

    def _normalize_generated_title(self) -> None:
        # Older promoted requirement inventories generated their display title
        # from the page adapter that happened to be active during migration.
        # Keep authored titles intact, but repair the generated provenance form
        # from the authoritative source span so a title cannot point reviewers
        # at a different file than the record's source field.
        generated_title = re.fullmatch(
            r"Normative (?:statement|candidate) at .+:(\d+)",
            self.title,
        )
        if generated_title:
            label = "Normative statement" if "statement" in self.title else "Normative candidate"
            corrected_title = f"{label} at {self.source.path}:{self.source.line}"
            if self.title != corrected_title:
                object.__setattr__(self, "title", corrected_title)

    def _validate_explicit_coverage(self) -> None:
        if self.coverage_kind == "transition" and not self.transition_ids:
            raise ValueError(
                "explicit transition-covered requirements must name at least one transition"
            )
        if self.coverage_kind != "transition" and not self.coverage_note.strip():
            raise ValueError(
                "explicit non-transition requirements need a coverage_note explaining scope"
            )


class RequirementMatch(SemanticRecord):
    requirement: Requirement
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    matched_terms: tuple[str, ...]


class RequirementLink(SemanticRecord):
    """An explicit, reviewed relationship between a requirement and transition."""

    id: Annotated[str, Field(min_length=1)]
    requirement_id: Annotated[str, Field(min_length=1)]
    transition_id: Annotated[str, Field(min_length=1)]
    relation: Literal[
        "governs",
        "precondition",
        "postcondition",
        "enables",
        "prohibits",
    ] = "governs"
    source: SourceRef | None = None
    notes: str = ""


class RequirementFile(SemanticRecord):
    """Authored requirement records promoted from source-shaped candidates."""

    schema_version: Annotated[int, Field(ge=1)]
    requirements: tuple[Requirement, ...]

    @model_validator(mode="after")
    def validate_requirement_ids(self) -> RequirementFile:
        ids = [item.id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement IDs must be unique in a requirement file")
        return self


class RequirementReview(SemanticRecord):
    """A disposition for an extracted requirement candidate."""

    requirement_id: Annotated[str, Field(min_length=1)]
    status: Literal["deferred", "non-normative", "layout-only"]
    reason: Annotated[str, Field(min_length=1)]
    source: SourceRef

    @property
    def id(self) -> str:
        """Expose the reviewed requirement as this record's stable identity."""
        return self.requirement_id


class RequirementReviewFile(SemanticRecord):
    """Authored review dispositions for unpromoted requirement candidates."""

    schema_version: Annotated[int, Field(ge=1)]
    reviews: tuple[RequirementReview, ...]


class RequirementLinkFile(SemanticRecord):
    """Authored requirement-to-transition relationships."""

    schema_version: Annotated[int, Field(ge=1)]
    links: tuple[RequirementLink, ...]


class TransitionCoverage(SemanticRecord):
    """Classify implementation coverage for every modeled transition."""

    transition_id: Annotated[str, Field(min_length=1)]
    status: Literal["mapped", "not-applicable", "deferred"]
    implementation_ids: tuple[str, ...] = ()
    reason: Annotated[str, Field(min_length=1)]
    source: SourceRef | None = None

    @model_validator(mode="after")
    def validate_mapping_shape(self) -> TransitionCoverage:
        if self.status == "mapped" and not self.implementation_ids:
            raise ValueError("mapped transition coverage must name an implementation")
        if self.status != "mapped" and self.implementation_ids:
            raise ValueError("only mapped transition coverage may name implementations")
        return self


class TransitionCoverageFile(SemanticRecord):
    """Authored transition coverage dispositions for compliance planning."""

    schema_version: Annotated[int, Field(ge=1)]
    transition_coverage: tuple[TransitionCoverage, ...]


class ContentBlock(SemanticRecord):
    """A source-owned prose block linked to semantic records and hierarchy."""

    id: Annotated[str, Field(min_length=1)]
    kind: Literal["context", "behavior", "normative", "transition-summary", "note"]
    text: str
    clause_id: str | None = None
    record_ids: tuple[str, ...] = ()
    element_ids: tuple[str, ...] = ()
    source: SourceRef
    sequence: Annotated[int, Field(ge=0)] = 0
    layout_body: str | None = None


class ContentBlockFile(SemanticRecord):
    """Authored prose blocks migrated out of page-oriented LaTeX."""

    schema_version: Annotated[int, Field(ge=1)]
    content_blocks: tuple[ContentBlock, ...]


class ContentElement(SemanticRecord):
    """A typed, clause-owned content unit extracted from a layout adapter.

    ``ContentBlock`` remains the exact-page fidelity boundary.  This record is
    the reusable semantic representation used by queries and future document
    renderers; it must not inherit ownership from a page filename.
    """

    id: Annotated[str, Field(min_length=1)]
    kind: Literal[
        "paragraph",
        "list",
        "list-item",
        "note",
        "footnote",
        "formula",
        "cross-reference",
    ]
    text: str
    clause_id: str | None = None
    block_id: Annotated[str, Field(min_length=1)]
    parent_id: str | None = None
    record_ids: tuple[str, ...] = ()
    source: SourceRef
    sequence: Annotated[int, Field(ge=0)] = 0


class ContentElementFile(SemanticRecord):
    """Authored typed content units extracted from source layout."""

    schema_version: Annotated[int, Field(ge=1)]
    content_elements: tuple[ContentElement, ...]


class ImplementationReference(SemanticRecord):
    """A structured, optionally source-addressable implementation target."""

    symbol: Annotated[str, Field(min_length=1)]
    language: Annotated[str, Field(min_length=1)] = "unspecified"
    repository: str | None = None
    path: str | None = None
    line: Annotated[int | None, Field(ge=1)] = None
    version: str | None = None


class ImplementationMapping(SemanticRecord):
    """Map a semantic interface surface to an implementation entry point."""

    id: Annotated[str, Field(min_length=1)]
    interface_kind: Literal["service", "callback", "adapter", "handler"]
    interface_name: Annotated[str, Field(min_length=1)]
    implementation: Annotated[str, Field(min_length=1)]
    status: ImplementationStatus = "planned"
    clause_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    source: SourceRef | None = None
    notes: str = ""
    implementation_ref: ImplementationReference | None = None

    @model_validator(mode="after")
    def normalize_implementation_ref(self) -> ImplementationMapping:
        """Give legacy string-only mappings a stable structured target."""
        if self.implementation_ref is None:
            object.__setattr__(
                self,
                "implementation_ref",
                ImplementationReference(symbol=self.implementation),
            )
        return self


class ImplementationFile(SemanticRecord):
    """Authored implementation mappings kept beside semantic document data."""

    schema_version: Annotated[int, Field(ge=1)]
    implementations: tuple[ImplementationMapping, ...]


class ApiParameter(SemanticRecord):
    """A language-neutral parameter contract for an API surface."""

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    type: Annotated[str, Field(min_length=1)]
    direction: Literal["in", "out", "inout", "return"] = "in"
    optional: bool = False
    description: str = ""
    source: SourceRef | None = None


class ApiSurface(SemanticRecord):
    """A callable or event-facing specification surface.

    The contract deliberately does not contain HLA-specific enums or method
    names.  Profiles may assign values such as ``RTIambassador`` or
    ``FederateAmbassador`` to ``owner`` while the core model remains reusable
    for other standards.
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    interface_kind: Literal["service", "callback", "adapter", "handler"]
    binding_kind: Literal["semantic", "native", "protocol", "language-adapter"] = "semantic"
    owner: Annotated[str, Field(min_length=1)]
    language: Annotated[str, Field(min_length=1)] = "unspecified"
    protocol: str | None = None
    signature: Annotated[str, Field(min_length=1)]
    parameters: tuple[ApiParameter, ...] = ()
    result_type: str | None = None
    exception_types: tuple[str, ...] = ()
    clause_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    implementation_mapping_ids: tuple[str, ...] = ()
    source: SourceRef | None = None
    notes: str = ""


class ApiSurfaceFile(SemanticRecord):
    """Authored API surface records, when a profile supplies them directly."""

    schema_version: Annotated[int, Field(ge=1)]
    api_surfaces: tuple[ApiSurface, ...]


class ApiCrosswalk(SemanticRecord):
    """Crosswalk one semantic mapping to a binding or future projection."""

    id: Annotated[str, Field(min_length=1)]
    implementation_mapping_id: Annotated[str, Field(min_length=1)]
    target: Annotated[str, Field(min_length=1)]
    binding_kind: Literal["native", "protocol", "language-adapter", "transport"]
    language: Annotated[str, Field(min_length=1)] = "unspecified"
    protocol: str | None = None
    status: Literal["matched", "ambiguous", "unmatched", "planned"]
    strategy: Literal["exact", "normalized", "token", "none", "projection"]
    candidate_api_surface_ids: tuple[str, ...] = ()
    selected_api_surface_ids: tuple[str, ...] = ()
    source: SourceRef | None = None
    notes: str = ""


class ApiCrosswalkFile(SemanticRecord):
    """Authored semantic-to-binding crosswalk records."""

    schema_version: Annotated[int, Field(ge=1)]
    api_crosswalks: tuple[ApiCrosswalk, ...]


class RequirementApiBinding(SemanticRecord):
    """A reviewed requirement relationship to a language API surface."""

    id: Annotated[str, Field(min_length=1)]
    requirement_id: Annotated[str, Field(min_length=1)]
    api_surface_id: str | None = None
    candidate_api_surface_ids: tuple[str, ...] = ()
    language: Annotated[str, Field(min_length=1)]
    relationship: Literal[
        "direct",
        "transition-backed",
        "callback",
        "not-applicable",
        "cross-cutting",
    ]
    status: Literal["candidate", "reviewed", "matched", "ambiguous", "unmatched"]
    rationale: Annotated[str, Field(min_length=1)]
    source: SourceRef

    @model_validator(mode="after")
    def validate_binding_shape(self) -> RequirementApiBinding:
        candidates = set(self.candidate_api_surface_ids)
        if self.api_surface_id is not None and self.api_surface_id not in candidates:
            candidates.add(self.api_surface_id)
            object.__setattr__(self, "candidate_api_surface_ids", tuple(sorted(candidates)))
        if self.status == "matched" and self.api_surface_id is None:
            raise ValueError("matched requirement API bindings must select an API surface")
        if self.status == "ambiguous" and (self.api_surface_id is not None or len(candidates) < 2):
            raise ValueError("ambiguous requirement API bindings need multiple candidate surfaces")
        if self.status == "unmatched" and candidates:
            raise ValueError("unmatched requirement API bindings cannot have candidate surfaces")
        if self.relationship in {"not-applicable", "cross-cutting"}:
            if self.api_surface_id is not None or candidates:
                raise ValueError("non-API requirement bindings cannot reference API surfaces")
        elif self.status in {"candidate", "reviewed", "matched", "ambiguous"} and not candidates:
            raise ValueError("API requirement bindings need a selected or candidate surface")
        return self


class RequirementApiBindingFile(SemanticRecord):
    """Authored requirement-to-API traceability records."""

    schema_version: Annotated[int, Field(ge=1)]
    bindings: tuple[RequirementApiBinding, ...]

    @model_validator(mode="after")
    def validate_binding_ids(self) -> RequirementApiBindingFile:
        ids = [item.id for item in self.bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement API binding IDs must be unique")
        return self


class VerificationTest(SemanticRecord):
    """A planned or observed verification record for semantic surfaces."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    kind: Literal["unit", "integration", "trace", "conformance", "review"]
    status: Literal["planned", "observed", "passed", "failed", "blocked"] = "planned"
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    api_surface_ids: tuple[str, ...] = ()
    trace_ids: tuple[str, ...] = ()
    implementation_mapping_ids: tuple[str, ...] = ()
    command: str | None = None
    source: SourceRef | None = None
    notes: str = ""


class VerificationTestFile(SemanticRecord):
    """Authored verification plans and evidence references."""

    schema_version: Annotated[int, Field(ge=1)]
    verification_tests: tuple[VerificationTest, ...]


class TraceStep(SemanticRecord):
    """One event/transition assertion in an executable state trace."""

    id: Annotated[str, Field(min_length=1)]
    event: str = ""
    source_state: str | None = None
    transition_id: str | None = None
    target_state: str | None = None
    requirement_ids: tuple[str, ...] = ()
    api_surface_ids: tuple[str, ...] = ()
    notes: str = ""


class StateTrace(SemanticRecord):
    """A replayable or planned path through a state machine."""

    id: Annotated[str, Field(min_length=1)]
    machine_id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    initial_state_id: str | None = None
    steps: tuple[TraceStep, ...] = ()
    expected_final_state: str | None = None
    status: Literal["planned", "observed", "passed", "failed", "blocked"] = "planned"
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    api_surface_ids: tuple[str, ...] = ()
    verification_test_ids: tuple[str, ...] = ()
    source: SourceRef | None = None
    notes: str = ""


class StateTraceFile(SemanticRecord):
    """Authored state-trace scenarios."""

    schema_version: Annotated[int, Field(ge=1)]
    state_traces: tuple[StateTrace, ...]


class ComplianceIssue(SemanticRecord):
    """A non-fatal compliance coverage finding for query/report consumers."""

    code: Literal[
        "orphan-requirement",
        "unmapped-transition",
        "orphan-implementation",
        "unresolved-reference",
        "non-concrete-implementation",
    ]
    severity: Literal["warning", "error"] = "warning"
    record_id: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]


class RequirementApplicability(SemanticRecord):
    """A typed explanation for why a requirement applies to a transition."""

    document_id: Annotated[str, Field(min_length=1)]
    machine_id: Annotated[str, Field(min_length=1)]
    state_id: Annotated[str, Field(min_length=1)]
    event: str
    transition_id: Annotated[str, Field(min_length=1)]
    target_state: str | None = None
    clause_id: str | None = None
    requirement_id: Annotated[str, Field(min_length=1)]
    relation: Literal[
        "transition",
        "reviewed-link",
        "implementation",
        "clause-fallback",
    ]


class TransitionImplementationCoverage(SemanticRecord):
    """Typed implementation status for one state-machine transition."""

    document_id: Annotated[str, Field(min_length=1)]
    machine_id: Annotated[str, Field(min_length=1)]
    transition_id: Annotated[str, Field(min_length=1)]
    source_state: str | None = None
    target_state: str | None = None
    event: str
    mapping_ids: tuple[str, ...] = ()
    status: TransitionCoverageStatus
    concrete: bool


class ComplianceQueryResult(SemanticRecord):
    """Serializable result for the reusable compliance query surface."""

    document_id: Annotated[str, Field(min_length=1)]
    machine_id: str | None = None
    state_id: str | None = None
    event: str | None = None
    applicable_requirements: tuple[RequirementApplicability, ...] = ()
    transition_coverage: tuple[TransitionImplementationCoverage, ...] = ()
    implementation_status_counts: Annotated[Mapping[str, int], Field(default_factory=dict)]
    issues: tuple[ComplianceIssue, ...] = ()


class ComplianceDependency(SemanticRecord):
    """A qualified dependency edge between corpus semantic records."""

    id: Annotated[str, Field(min_length=1)]
    source_document_id: Annotated[str, Field(min_length=1)]
    source_record_id: Annotated[str, Field(min_length=1)]
    source_kind: Annotated[str, Field(min_length=1)]
    target_document_id: Annotated[str, Field(min_length=1)]
    target_record_id: Annotated[str, Field(min_length=1)]
    target_kind: Annotated[str, Field(min_length=1)]
    relation: Literal[
        "owned-by",
        "contains",
        "member-of",
        "references",
        "mentions",
        "continues",
        "governs",
        "implements",
        "annotates",
        "maps-to",
    ]
    source: SourceRef | None = None


class OperationalImplication(SemanticRecord):
    """A queryable state-transition or message-sequence implication."""

    document_id: Annotated[str, Field(min_length=1)]
    kind: Literal["state-transition", "sequence-message"]
    record_id: Annotated[str, Field(min_length=1)]
    parent_id: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    implementation_ids: tuple[str, ...] = ()
    source_state: str | None = None
    event: str | None = None
    target_state: str | None = None
    sequence_diagram_id: str | None = None
    message_order: Annotated[int | None, Field(ge=1)] = None
    response_to: str | None = None
    related_transition_ids: tuple[str, ...] = ()
    related_sequence_diagram_ids: tuple[str, ...] = ()
    relation: Literal["direct", "clause-context", "unlinked"]
    source: SourceRef | None = None


class ImplementationEvidence(SemanticRecord):
    """A corpus-qualified implementation mapping with maturity evidence."""

    document_id: Annotated[str, Field(min_length=1)]
    mapping_id: Annotated[str, Field(min_length=1)]
    interface_kind: Literal["service", "callback", "adapter", "handler"]
    interface_name: Annotated[str, Field(min_length=1)]
    implementation: Annotated[str, Field(min_length=1)]
    status: Literal["planned", "partial", "implemented", "verified"]
    concrete: bool
    source_backed: bool
    clause_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    implementation_ref: ImplementationReference | None = None
    source: SourceRef | None = None


class ComplianceCorpusReport(SemanticRecord):
    """Serializable M24 corpus report for compliance consumers."""

    document_ids: tuple[str, ...]
    applicable_requirements: tuple[RequirementApplicability, ...] = ()
    state_sequence_implications: tuple[OperationalImplication, ...] = ()
    dependencies: tuple[ComplianceDependency, ...] = ()
    missing_implementation_mappings: tuple[TransitionImplementationCoverage, ...] = ()
    implementation_evidence: tuple[ImplementationEvidence, ...] = ()
    unresolved_references: tuple[ComplianceIssue, ...] = ()
    issues: tuple[ComplianceIssue, ...] = ()
    implementation_status_counts: Annotated[
        Mapping[str, Mapping[str, int]], Field(default_factory=dict)
    ]
    operational_implication_counts: Annotated[Mapping[str, int], Field(default_factory=dict)]
    table_definition_coverage: Annotated[
        Mapping[str, Mapping[str, int]], Field(default_factory=dict)
    ]


class TableCell(SemanticRecord):
    """A semantic table cell with source provenance and logical placement."""

    id: Annotated[str, Field(min_length=1)]
    table_id: Annotated[str, Field(min_length=1)]
    text: str
    row: Annotated[int | None, Field(ge=0)] = None
    column: Annotated[int | None, Field(ge=0)] = None
    record_ids: tuple[str, ...] = ()
    source: SourceRef


class Table(SemanticRecord):
    """A semantic table assembled from the source table primitives."""

    id: Annotated[str, Field(min_length=1)]
    title: str | None
    caption: str | None
    number: str | None
    continuation: bool
    cells: tuple[TableCell, ...]
    source: SourceRef
    logical_id: str | None = None
    domain: Literal["generic", "omt"] = "generic"
    omt_kind: str | None = None
    continued_from: str | None = None
    family_id: str | None = None

    @model_validator(mode="after")
    def validate_cells(self) -> Table:
        if any(cell.table_id != self.id for cell in self.cells):
            raise ValueError("table cells must reference their containing table")
        cell_ids = [cell.id for cell in self.cells]
        if len(cell_ids) != len(set(cell_ids)):
            raise ValueError("table cell IDs must be unique")
        if self.logical_id is None:
            object.__setattr__(self, "logical_id", self.id)
        return self


class TableFile(SemanticRecord):
    """Authored table records promoted from a legacy or external source."""

    schema_version: Annotated[int, Field(ge=1)]
    tables: tuple[Table, ...]


class TableFamily(SemanticRecord):
    """A named OMT table family grouped from typed table records."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    table_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    table_captions: Annotated[Mapping[str, str], Field(default_factory=dict)]
    clause_id: str | None = None
    source: SourceRef


class TableFamilyFile(SemanticRecord):
    """Authored table-family groupings kept outside page layout source."""

    schema_version: Annotated[int, Field(ge=1)]
    table_families: tuple[TableFamily, ...]


class ReferenceTarget(SemanticRecord):
    """A resolved target for a cross-document semantic reference."""

    document_id: Annotated[str, Field(min_length=1)]
    record_id: Annotated[str, Field(min_length=1)]


class Reference(SemanticRecord):
    """A normative or bibliographic document reference."""

    id: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    text: str
    kind: Literal["normative", "bibliographic", "informative"] = "informative"
    clause_id: str | None = None
    targets: tuple[ReferenceTarget, ...] = ()
    source: SourceRef


class CrossReference(SemanticRecord):
    """A typed, linkable relationship from one local record to another."""

    id: Annotated[str, Field(min_length=1)]
    owner_id: Annotated[str, Field(min_length=1)]
    target_document_id: Annotated[str, Field(min_length=1)]
    target_record_id: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    kind: CrossReferenceKind = "unknown"
    relation: Literal["references", "mentions", "continues"] = "references"
    source: SourceRef


class CrossReferenceFile(SemanticRecord):
    """Authored cross-reference records with resolved semantic targets."""

    schema_version: Annotated[int, Field(ge=1)]
    cross_references: tuple[CrossReference, ...]


class ReferenceFile(SemanticRecord):
    """Authored reference records with optional resolved targets."""

    schema_version: Annotated[int, Field(ge=1)]
    references: tuple[Reference, ...]


class NoteFile(SemanticRecord):
    """Authored note records promoted from a legacy or external source."""

    schema_version: Annotated[int, Field(ge=1)]
    notes: tuple[Note, ...]


class FigureFile(SemanticRecord):
    """Authored figure records promoted from a legacy or external source."""

    schema_version: Annotated[int, Field(ge=1)]
    figures: tuple[Figure, ...]


class Note(SemanticRecord):
    """An explicitly marked note or footnote, kept separate from prose."""

    id: Annotated[str, Field(min_length=1)]
    text: str
    kind: NoteKind
    owner_id: str | None = None
    source: SourceRef


class Figure(SemanticRecord):
    """A figure reference without embedding its binary analogue."""

    id: Annotated[str, Field(min_length=1)]
    number: Annotated[str, Field(min_length=1)]
    caption: str = ""
    image: str | None = None
    clause_id: str | None = None
    source: SourceRef


class Example(SemanticRecord):
    """A document-marked example heading and its semantic owner."""

    id: Annotated[str, Field(min_length=1)]
    number: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    clause_id: str | None = None
    source: SourceRef


class Annex(SemanticRecord):
    """An annex boundary and status, independent of page layout."""

    id: Annotated[str, Field(min_length=1)]
    letter: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    status: AnnexStatus = "unknown"
    source: SourceRef
