"""Extract reusable semantic records from source-first LaTeX documents."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hla_lab.core.json_types import JsonObject, JsonValue
from hla_lab.core.parsing import balanced_group, line_number
from hla_lab.core.source_adapter import LatexSourceProfile
from hla_lab.core.text import slugify

RequirementApplicabilityRelation = Literal[
    "transition", "reviewed-link", "implementation", "clause-fallback"
]

class SemanticRecord(BaseModel):
    """Shared strict contract for semantic records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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

class SourceRef(SemanticRecord):
    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_span(self) -> SourceRef:
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError("source end_line must not precede line")
        return self

class SourceOrderedRecord(Protocol):
    source: SourceRef
    id: str

class _DocumentResources(Protocol):
    @property
    def canonical(self) -> Path: ...

    @property
    def main_tex(self) -> Path: ...

    @property
    def semantic(self) -> Path: ...

    def canonical_file(self, name: str) -> Path: ...

    def semantic_file(self, name: str) -> Path: ...

class Clause(SemanticRecord):
    id: str = Field(min_length=1)
    number: str = Field(min_length=1)
    title: str = Field(min_length=1)
    parent_id: str | None
    level: int = Field(ge=1)
    source: SourceRef

class Definition(SemanticRecord):
    id: str = Field(min_length=1)
    term: str = Field(min_length=1)
    text: str
    layout_body: str | None = None
    leading_gap: str | None = None
    source: SourceRef
    clause_id: str | None = None

class DefinitionFile(SemanticRecord):
    """Authored semantic definition records kept outside hand-written LaTeX."""

    schema_version: int = Field(ge=1)
    definitions: tuple[Definition, ...]

class Requirement(SemanticRecord):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
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
        if not self.machine_statement:
            object.__setattr__(
                self,
                "machine_statement",
                _machine_statement(self.statement),
            )
        if not self.semantic_group_id:
            object.__setattr__(self, "semantic_group_id", self.id)
        if self.extraction == "explicit":
            if self.coverage_kind == "transition" and not self.transition_ids:
                raise ValueError(
                    "explicit transition-covered requirements must name at least one transition"
                )
            if self.coverage_kind != "transition" and not self.coverage_note.strip():
                raise ValueError(
                    "explicit non-transition requirements need a coverage_note explaining scope"
                )
        if (
            self.api_surface_scope != "required" or self.api_surface_resolution == "all-overloads"
        ) and not self.api_surface_note.strip():
            raise ValueError("non-standard API surface decisions need an api_surface_note")
        return self

class RequirementMatch(SemanticRecord):
    requirement: Requirement
    score: float = Field(ge=0.0, le=1.0)
    matched_terms: tuple[str, ...]

class RequirementLink(SemanticRecord):
    """An explicit, reviewed relationship between a requirement and transition."""

    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    transition_id: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
    requirements: tuple[Requirement, ...]

    @model_validator(mode="after")
    def validate_requirement_ids(self) -> RequirementFile:
        ids = [item.id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement IDs must be unique in a requirement file")
        return self

class RequirementReview(SemanticRecord):
    """A disposition for an extracted requirement candidate."""

    requirement_id: str = Field(min_length=1)
    status: Literal["deferred", "non-normative", "layout-only"]
    reason: str = Field(min_length=1)
    source: SourceRef

    @property
    def id(self) -> str:
        """Expose the reviewed requirement as this record's stable identity."""
        return self.requirement_id

class RequirementReviewFile(SemanticRecord):
    """Authored review dispositions for unpromoted requirement candidates."""

    schema_version: int = Field(ge=1)
    reviews: tuple[RequirementReview, ...]

class RequirementLinkFile(SemanticRecord):
    """Authored requirement-to-transition relationships."""

    schema_version: int = Field(ge=1)
    links: tuple[RequirementLink, ...]

class TransitionCoverage(SemanticRecord):
    """Classify implementation coverage for every modeled transition."""

    transition_id: str = Field(min_length=1)
    status: Literal["mapped", "not-applicable", "deferred"]
    implementation_ids: tuple[str, ...] = ()
    reason: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
    transition_coverage: tuple[TransitionCoverage, ...]

class ContentBlock(SemanticRecord):
    """A source-owned prose block linked to semantic records and hierarchy."""

    id: str = Field(min_length=1)
    kind: Literal["context", "behavior", "normative", "transition-summary", "note"]
    text: str
    clause_id: str | None = None
    record_ids: tuple[str, ...] = ()
    element_ids: tuple[str, ...] = ()
    source: SourceRef
    sequence: int = Field(default=0, ge=0)
    layout_body: str | None = None

class ContentBlockFile(SemanticRecord):
    """Authored prose blocks migrated out of page-oriented LaTeX."""

    schema_version: int = Field(ge=1)
    content_blocks: tuple[ContentBlock, ...]

class ContentElement(SemanticRecord):
    """A typed, clause-owned content unit extracted from a layout adapter.

    ``ContentBlock`` remains the exact-page fidelity boundary.  This record is
    the reusable semantic representation used by queries and future document
    renderers; it must not inherit ownership from a page filename.
    """

    id: str = Field(min_length=1)
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
    block_id: str = Field(min_length=1)
    parent_id: str | None = None
    record_ids: tuple[str, ...] = ()
    source: SourceRef
    sequence: int = Field(default=0, ge=0)

class ContentElementFile(SemanticRecord):
    """Authored typed content units extracted from source layout."""

    schema_version: int = Field(ge=1)
    content_elements: tuple[ContentElement, ...]

class ImplementationReference(SemanticRecord):
    """A structured, optionally source-addressable implementation target."""

    symbol: str = Field(min_length=1)
    language: str = Field(default="unspecified", min_length=1)
    repository: str | None = None
    path: str | None = None
    line: int | None = Field(default=None, ge=1)
    version: str | None = None

class ImplementationMapping(SemanticRecord):
    """Map a semantic interface surface to an implementation entry point."""

    id: str = Field(min_length=1)
    interface_kind: Literal["service", "callback", "adapter", "handler"]
    interface_name: str = Field(min_length=1)
    implementation: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
    implementations: tuple[ImplementationMapping, ...]

class ApiParameter(SemanticRecord):
    """A language-neutral parameter contract for an API surface."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
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

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    interface_kind: Literal["service", "callback", "adapter", "handler"]
    binding_kind: Literal["semantic", "native", "protocol", "language-adapter"] = "semantic"
    owner: str = Field(min_length=1)
    language: str = Field(default="unspecified", min_length=1)
    protocol: str | None = None
    signature: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
    api_surfaces: tuple[ApiSurface, ...]

class ApiCrosswalk(SemanticRecord):
    """Crosswalk one semantic mapping to a binding or future projection."""

    id: str = Field(min_length=1)
    implementation_mapping_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    binding_kind: Literal["native", "protocol", "language-adapter", "transport"]
    language: str = Field(default="unspecified", min_length=1)
    protocol: str | None = None
    status: Literal["matched", "ambiguous", "unmatched", "planned"]
    strategy: Literal["exact", "normalized", "token", "none", "projection"]
    candidate_api_surface_ids: tuple[str, ...] = ()
    selected_api_surface_ids: tuple[str, ...] = ()
    source: SourceRef | None = None
    notes: str = ""

class ApiCrosswalkFile(SemanticRecord):
    """Authored semantic-to-binding crosswalk records."""

    schema_version: int = Field(ge=1)
    api_crosswalks: tuple[ApiCrosswalk, ...]

class RequirementApiBinding(SemanticRecord):
    """A reviewed requirement relationship to a language API surface."""

    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    api_surface_id: str | None = None
    candidate_api_surface_ids: tuple[str, ...] = ()
    language: str = Field(min_length=1)
    relationship: Literal[
        "direct",
        "transition-backed",
        "callback",
        "not-applicable",
        "cross-cutting",
    ]
    status: Literal["candidate", "reviewed", "matched", "ambiguous", "unmatched"]
    rationale: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
    bindings: tuple[RequirementApiBinding, ...]

    @model_validator(mode="after")
    def validate_binding_ids(self) -> RequirementApiBindingFile:
        ids = [item.id for item in self.bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement API binding IDs must be unique")
        return self

class VerificationTest(SemanticRecord):
    """A planned or observed verification record for semantic surfaces."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
    verification_tests: tuple[VerificationTest, ...]

class TraceStep(SemanticRecord):
    """One event/transition assertion in an executable state trace."""

    id: str = Field(min_length=1)
    event: str = ""
    source_state: str | None = None
    transition_id: str | None = None
    target_state: str | None = None
    requirement_ids: tuple[str, ...] = ()
    api_surface_ids: tuple[str, ...] = ()
    notes: str = ""

class StateTrace(SemanticRecord):
    """A replayable or planned path through a state machine."""

    id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
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
    record_id: str = Field(min_length=1)
    message: str = Field(min_length=1)

class RequirementApplicability(SemanticRecord):
    """A typed explanation for why a requirement applies to a transition."""

    document_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    state_id: str = Field(min_length=1)
    event: str
    transition_id: str = Field(min_length=1)
    target_state: str | None = None
    clause_id: str | None = None
    requirement_id: str = Field(min_length=1)
    relation: Literal[
        "transition",
        "reviewed-link",
        "implementation",
        "clause-fallback",
    ]

class TransitionImplementationCoverage(SemanticRecord):
    """Typed implementation status for one state-machine transition."""

    document_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    transition_id: str = Field(min_length=1)
    source_state: str | None = None
    target_state: str | None = None
    event: str
    mapping_ids: tuple[str, ...] = ()
    status: TransitionCoverageStatus
    concrete: bool

class ComplianceQueryResult(SemanticRecord):
    """Serializable result for the reusable compliance query surface."""

    document_id: str = Field(min_length=1)
    machine_id: str | None = None
    state_id: str | None = None
    event: str | None = None
    applicable_requirements: tuple[RequirementApplicability, ...] = ()
    transition_coverage: tuple[TransitionImplementationCoverage, ...] = ()
    implementation_status_counts: dict[str, int] = Field(default_factory=dict)
    issues: tuple[ComplianceIssue, ...] = ()

class ComplianceDependency(SemanticRecord):
    """A qualified dependency edge between corpus semantic records."""

    id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    target_document_id: str = Field(min_length=1)
    target_record_id: str = Field(min_length=1)
    target_kind: str = Field(min_length=1)
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

    document_id: str = Field(min_length=1)
    kind: Literal["state-transition", "sequence-message"]
    record_id: str = Field(min_length=1)
    parent_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    implementation_ids: tuple[str, ...] = ()
    source_state: str | None = None
    event: str | None = None
    target_state: str | None = None
    sequence_diagram_id: str | None = None
    message_order: int | None = Field(default=None, ge=1)
    response_to: str | None = None
    related_transition_ids: tuple[str, ...] = ()
    related_sequence_diagram_ids: tuple[str, ...] = ()
    relation: Literal["direct", "clause-context", "unlinked"]
    source: SourceRef | None = None

class ImplementationEvidence(SemanticRecord):
    """A corpus-qualified implementation mapping with maturity evidence."""

    document_id: str = Field(min_length=1)
    mapping_id: str = Field(min_length=1)
    interface_kind: Literal["service", "callback", "adapter", "handler"]
    interface_name: str = Field(min_length=1)
    implementation: str = Field(min_length=1)
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
    implementation_status_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    operational_implication_counts: dict[str, int] = Field(default_factory=dict)
    table_definition_coverage: dict[str, dict[str, int]] = Field(default_factory=dict)

class TableCell(SemanticRecord):
    """A semantic table cell with source provenance and logical placement."""

    id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    text: str
    row: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)
    record_ids: tuple[str, ...] = ()
    source: SourceRef

class Table(SemanticRecord):
    """A semantic table assembled from the source table primitives."""

    id: str = Field(min_length=1)
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

    schema_version: int = Field(ge=1)
    tables: tuple[Table, ...]

class TableFamily(SemanticRecord):
    """A named OMT table family grouped from typed table records."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    table_ids: tuple[str, ...] = Field(min_length=1)
    clause_id: str | None = None
    source: SourceRef

class TableFamilyFile(SemanticRecord):
    """Authored table-family groupings kept outside page layout source."""

    schema_version: int = Field(ge=1)
    table_families: tuple[TableFamily, ...]

class ReferenceTarget(SemanticRecord):
    """A resolved target for a cross-document semantic reference."""

    document_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)

class Reference(SemanticRecord):
    """A normative or bibliographic document reference."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    text: str
    kind: Literal["normative", "bibliographic", "informative"] = "informative"
    clause_id: str | None = None
    targets: tuple[ReferenceTarget, ...] = ()
    source: SourceRef

class CrossReference(SemanticRecord):
    """A typed, linkable relationship from one local record to another."""

    id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    target_document_id: str = Field(min_length=1)
    target_record_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: CrossReferenceKind = "unknown"
    relation: Literal["references", "mentions", "continues"] = "references"
    source: SourceRef

class CrossReferenceFile(SemanticRecord):
    """Authored cross-reference records with resolved semantic targets."""

    schema_version: int = Field(ge=1)
    cross_references: tuple[CrossReference, ...]

class ReferenceFile(SemanticRecord):
    """Authored reference records with optional resolved targets."""

    schema_version: int = Field(ge=1)
    references: tuple[Reference, ...]

class NoteFile(SemanticRecord):
    """Authored note records promoted from a legacy or external source."""

    schema_version: int = Field(ge=1)
    notes: tuple[Note, ...]

class FigureFile(SemanticRecord):
    """Authored figure records promoted from a legacy or external source."""

    schema_version: int = Field(ge=1)
    figures: tuple[Figure, ...]

class Note(SemanticRecord):
    """An explicitly marked note or footnote, kept separate from prose."""

    id: str = Field(min_length=1)
    text: str
    kind: NoteKind
    owner_id: str | None = None
    source: SourceRef

class Figure(SemanticRecord):
    """A figure reference without embedding its binary analogue."""

    id: str = Field(min_length=1)
    number: str = Field(min_length=1)
    caption: str = ""
    image: str | None = None
    clause_id: str | None = None
    source: SourceRef

class Example(SemanticRecord):
    """A document-marked example heading and its semantic owner."""

    id: str = Field(min_length=1)
    number: str = Field(min_length=1)
    title: str = Field(min_length=1)
    clause_id: str | None = None
    source: SourceRef

class Annex(SemanticRecord):
    """An annex boundary and status, independent of page layout."""

    id: str = Field(min_length=1)
    letter: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: AnnexStatus = "unknown"
    source: SourceRef

class State(SemanticRecord):
    """A named state in a document-defined state machine."""

    id: str = Field(min_length=1)
    label: str
    parent_id: str | None = None
    kind: str = Field(default="state", min_length=1)
    source: SourceRef | None = None

    @model_validator(mode="after")
    def validate_label(self) -> State:
        if not self.label and self.kind not in {"initial", "final", "history"}:
            raise ValueError("only initial/final/history pseudostates may have empty labels")
        return self

class Transition(SemanticRecord):
    """A state-machine transition with explicit conformance-oriented fields."""

    id: str = Field(min_length=1)
    source_state: str | None
    event: str
    target_state: str | None
    initiator: Literal["federate", "rti", "automatic", "unknown"] = "unknown"
    guard: str = ""
    action: str = ""
    precondition: str = ""
    postcondition: str = ""
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    implementation_ids: tuple[str, ...] = ()
    source: SourceRef | None = None

class DiagramProvenance(SemanticRecord):
    image: str = Field(min_length=1)
    page: int = Field(ge=1)
    xref: str | None = None
    caption: str = ""

class NodePosition(SemanticRecord):
    x: float
    y: float
    visible: bool = True

class LayoutContainer(SemanticRecord):
    id: str = Field(min_length=1)
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    title: str = Field(min_length=1)
    visible: bool = True
    title_visible: bool = True

class TransitionLayout(SemanticRecord):
    """Manual geometry hints for a rendered transition label or edge."""

    style: str = Field(default="straight", min_length=1)
    loop_direction: Literal["left", "right", "above", "below"] | None = None
    label: str | None = None
    bend: float | None = None
    label_side: Literal["above", "below", "left", "right"] | None = None
    label_pos: float | None = Field(default=None, ge=0.0, le=1.0)
    label_x: float | None = None
    label_y: float | None = None
    label_width: float | None = Field(default=None, gt=0.0)
    label_align: Literal["left", "center", "right"] | None = None
    label_visible: bool = True

class LayoutRule(SemanticRecord):
    """A manual guide line retained as layout data, not state semantics."""

    x1: float
    y1: float
    x2: float
    y2: float
    style: str = "solid"

class LayoutAnnotation(SemanticRecord):
    """A text label positioned by the diagram layout adapter."""

    id: str = Field(min_length=1)
    x: float
    y: float
    text: str = Field(min_length=1)
    width: float | None = Field(default=None, gt=0)
    align: Literal["left", "center", "right"] = "left"

class StateMachineLayout(SemanticRecord):
    engine: Literal["automatic", "manual"] = "automatic"
    direction: Literal["left-to-right", "top-to-bottom"] = "top-to-bottom"
    state_font: str | None = None
    edge_label_font: str | None = None
    edge_label_distance: float | None = Field(default=None, ge=0.0)
    containers: tuple[LayoutContainer, ...] = ()
    nodes: dict[str, NodePosition] = Field(default_factory=dict)
    transitions: dict[str, TransitionLayout] = Field(default_factory=dict)
    rules: tuple[LayoutRule, ...] = ()
    annotations: tuple[LayoutAnnotation, ...] = ()

class StateMachine(SemanticRecord):
    """A reusable state machine linked to the document hierarchy."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    states: tuple[State, ...]
    transitions: tuple[Transition, ...]
    initial_state_ids: tuple[str, ...] = ()
    clause_id: str | None = None
    source: SourceRef | None = None
    provenance: DiagramProvenance | None = None
    layout: StateMachineLayout | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_graph_ids(self) -> StateMachine:
        state_ids = [state.id for state in self.states]
        transition_ids = [transition.id for transition in self.transitions]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("state IDs must be unique within a state machine")
        if len(transition_ids) != len(set(transition_ids)):
            raise ValueError("transition IDs must be unique within a state machine")
        state_id_set = set(state_ids)
        if any(item not in state_id_set for item in self.initial_state_ids):
            raise ValueError("initial states must reference defined states")
        for state in self.states:
            if state.parent_id is not None and state.parent_id not in state_id_set:
                raise ValueError(f"state {state.id} references missing parent {state.parent_id}")
            seen: set[str] = set()
            current = state
            while current.parent_id is not None:
                if current.id in seen:
                    raise ValueError(f"state hierarchy cycle includes {current.id}")
                seen.add(current.id)
                current = next(item for item in self.states if item.id == current.parent_id)
        for transition in self.transitions:
            for endpoint in (transition.source_state, transition.target_state):
                if endpoint is not None and endpoint not in state_id_set:
                    raise ValueError(
                        f"transition {transition.id} references unknown state {endpoint}"
                    )
        return self

class StateMachineFile(SemanticRecord):
    schema_version: int = Field(ge=2)
    state_machines: tuple[StateMachine, ...]

class SequenceParticipant(SemanticRecord):
    """A lifeline in a reusable message-sequence diagram."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    role: str = ""

class SequenceMessage(SemanticRecord):
    """An ordered message with explicit direction and optional response correlation."""

    id: str = Field(min_length=1)
    order: int = Field(ge=1)
    source_participant: str = Field(min_length=1)
    target_participant: str = Field(min_length=1)
    label: str = Field(min_length=1)
    kind: Literal["message", "request", "response", "control", "note"] = "message"
    response_to: str | None = None
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    source: SourceRef | None = None

class SequenceDiagram(SemanticRecord):
    """A document-independent sequence diagram owned by semantic source."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    participants: tuple[SequenceParticipant, ...]
    messages: tuple[SequenceMessage, ...]
    clause_id: str | None = None
    source: SourceRef | None = None
    provenance: DiagramProvenance | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_sequence(self) -> SequenceDiagram:
        participant_ids = [item.id for item in self.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("sequence participant IDs must be unique")
        message_ids = [item.id for item in self.messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("sequence message IDs must be unique")
        orders = [item.order for item in self.messages]
        if len(orders) != len(set(orders)):
            raise ValueError("sequence message order values must be unique")
        participant_id_set = set(participant_ids)
        message_id_set = set(message_ids)
        for message in self.messages:
            if message.source_participant not in participant_id_set:
                raise ValueError(
                    f"sequence message {message.id} references unknown source participant "
                    f"{message.source_participant}"
                )
            if message.target_participant not in participant_id_set:
                raise ValueError(
                    f"sequence message {message.id} references unknown target participant "
                    f"{message.target_participant}"
                )
            if message.response_to is not None and message.response_to not in message_id_set:
                raise ValueError(
                    f"sequence message {message.id} references unknown response "
                    f"{message.response_to}"
                )
        return self

class SequenceDiagramFile(SemanticRecord):
    """Authored sequence diagrams kept out of page-layout source."""

    schema_version: int = Field(ge=1)
    sequence_diagrams: tuple[SequenceDiagram, ...]

class GraphPoint(SemanticRecord):
    """A point in a diagram's document-independent coordinate system."""

    x: float
    y: float

class GraphNode(SemanticRecord):
    """A positioned node used by generic relationship and architecture diagrams."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    style: Literal["box", "frame", "lifeline", "ellipse", "point", "invisible"] = "box"
    parent_id: str | None = None
    visible: bool = True

class GraphEdge(SemanticRecord):
    """A directed, undirected, dotted, or dimension relationship between nodes."""

    id: str = Field(min_length=1)
    source: str | None = None
    target: str | None = None
    label: str = ""
    style: Literal["solid", "dotted", "dashed", "dimension"] = "solid"
    direction: Literal["none", "forward", "reverse", "both"] = "forward"
    points: tuple[GraphPoint, ...] = ()
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    implementation_ids: tuple[str, ...] = ()
    source_ref: SourceRef | None = None

class GraphAnnotation(SemanticRecord):
    """Free-standing text or measurement label positioned by semantic data."""

    id: str = Field(min_length=1)
    x: float
    y: float
    text: str = Field(min_length=1)
    width: float | None = Field(default=None, gt=0)
    align: Literal["left", "center", "right"] = "center"
    rotate: float = 0.0

class GraphDiagram(SemanticRecord):
    """A reusable non-state diagram with explicit nodes, edges, and annotations."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: Literal["relationship", "conceptual", "hierarchy", "architecture"]
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    annotations: tuple[GraphAnnotation, ...] = ()
    clause_id: str | None = None
    source: SourceRef | None = None
    provenance: DiagramProvenance | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_graph(self) -> GraphDiagram:
        node_ids = [item.id for item in self.nodes]
        edge_ids = [item.id for item in self.edges]
        annotation_ids = [item.id for item in self.annotations]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node IDs must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("graph edge IDs must be unique")
        if len(annotation_ids) != len(set(annotation_ids)):
            raise ValueError("graph annotation IDs must be unique")
        node_id_set = set(node_ids)
        for node in self.nodes:
            if node.parent_id is not None and node.parent_id not in node_id_set:
                raise ValueError(f"graph node {node.id} references missing parent {node.parent_id}")
        for edge in self.edges:
            if edge.source is not None and edge.source not in node_id_set:
                raise ValueError(f"graph edge {edge.id} references missing source {edge.source}")
            if edge.target is not None and edge.target not in node_id_set:
                raise ValueError(f"graph edge {edge.id} references missing target {edge.target}")
            if not edge.points and (edge.source is None or edge.target is None):
                raise ValueError(
                    f"graph edge {edge.id} needs source/target nodes or explicit points"
                )
        return self

class GraphDiagramFile(SemanticRecord):
    """Authored generic diagrams kept out of hand-written page layout."""

    schema_version: int = Field(ge=1)
    graph_diagrams: tuple[GraphDiagram, ...]

class DiagramSurface(SemanticRecord):
    """Inventory classification for every source figure or extracted asset."""

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    figure_number: int | None = Field(default=None, ge=1)
    status: Literal["generated", "non-generatable"]
    record_id: str | None = None
    record_kind: Literal["state_machine", "sequence_diagram", "graph_diagram", "asset"]
    source_image: str | None = None
    reason: str = ""

    @model_validator(mode="after")
    def validate_surface(self) -> DiagramSurface:
        if self.status == "generated" and (self.figure_number is None or self.record_id is None):
            raise ValueError("generated diagram surfaces require figure_number and record_id")
        if self.status == "non-generatable" and not self.reason.strip():
            raise ValueError("non-generatable surfaces require a reason")
        return self

class DiagramSurfaceFile(SemanticRecord):
    """Source-controlled contract for complete figure-surface classification."""

    schema_version: int = Field(ge=1)
    surfaces: tuple[DiagramSurface, ...]

class DocumentModel(SemanticRecord):
    document_id: str = ""
    clauses: tuple[Clause, ...]
    definitions: tuple[Definition, ...]
    requirements: tuple[Requirement, ...]
    requirement_reviews: tuple[RequirementReview, ...] = ()
    requirement_links: tuple[RequirementLink, ...] = ()
    transition_coverage: tuple[TransitionCoverage, ...] = ()
    content_blocks: tuple[ContentBlock, ...] = ()
    content_elements: tuple[ContentElement, ...] = ()
    state_machines: tuple[StateMachine, ...] = ()
    sequence_diagrams: tuple[SequenceDiagram, ...] = ()
    graph_diagrams: tuple[GraphDiagram, ...] = ()
    diagram_surfaces: tuple[DiagramSurface, ...] = ()
    implementations: tuple[ImplementationMapping, ...] = ()
    api_surfaces: tuple[ApiSurface, ...] = ()
    api_crosswalks: tuple[ApiCrosswalk, ...] = ()
    requirement_api_bindings: tuple[RequirementApiBinding, ...] = ()
    verification_tests: tuple[VerificationTest, ...] = ()
    state_traces: tuple[StateTrace, ...] = ()
    tables: tuple[Table, ...] = ()
    table_families: tuple[TableFamily, ...] = ()
    references: tuple[Reference, ...] = ()
    cross_references: tuple[CrossReference, ...] = ()
    notes: tuple[Note, ...] = ()
    figures: tuple[Figure, ...] = ()
    examples: tuple[Example, ...] = ()
    annexes: tuple[Annex, ...] = ()
    clause_order: tuple[str, ...] = ()
    schema_version: int = Field(default=8, ge=4)

    @model_validator(mode="after")
    def validate_record_ids(self) -> DocumentModel:
        for label, records in (
                ("clause", self.clauses),
                ("definition", self.definitions),
                ("requirement", self.requirements),
                ("requirement review", self.requirement_reviews),
                ("requirement link", self.requirement_links),
                ("content block", self.content_blocks),
                ("content element", self.content_elements),
                ("state machine", self.state_machines),
                ("sequence diagram", self.sequence_diagrams),
                ("graph diagram", self.graph_diagrams),
                ("diagram surface", self.diagram_surfaces),
                ("implementation", self.implementations),
                ("API surface", self.api_surfaces),
                ("API crosswalk", self.api_crosswalks),
                ("requirement API binding", self.requirement_api_bindings),
                ("verification test", self.verification_tests),
                ("state trace", self.state_traces),
                ("table", self.tables),
                ("table family", self.table_families),
                ("reference", self.references),
                ("cross-reference", self.cross_references),
                ("note", self.notes),
                ("figure", self.figures),
                ("example", self.examples),
                ("annex", self.annexes),
        ):
            ids = [item.id for item in records]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} IDs must be unique")
        clause_ids = {item.id for item in self.clauses}
        expected_order = tuple(item.id for item in sorted(self.clauses, key=_clause_sort_key))
        if self.clause_order:
            if set(self.clause_order) != clause_ids or len(self.clause_order) != len(clause_ids):
                raise ValueError("clause_order must contain each clause exactly once")
        else:
            object.__setattr__(self, "clause_order", expected_order)
        transition_ids = [
            transition.id for machine in self.state_machines for transition in machine.transitions
        ]
        if len(transition_ids) != len(set(transition_ids)):
            raise ValueError("transition IDs must be unique across the document")
        requirement_ids = {item.id for item in self.requirements}
        candidate_ids = {item.id for item in self.requirements if item.extraction == "candidate"}
        review_ids = [item.requirement_id for item in self.requirement_reviews]
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("requirement review IDs must be unique")
        if not set(review_ids) <= candidate_ids:
            invalid = sorted(set(review_ids) - candidate_ids)
            raise ValueError(f"requirement reviews must target candidate requirements: {invalid}")
        if self.requirement_reviews and set(review_ids) != candidate_ids:
            missing = sorted(candidate_ids - set(review_ids))
            extra = sorted(set(review_ids) - candidate_ids)
            raise ValueError(
                "requirement review must classify every candidate "
                f"(missing={missing}, extra={extra})"
            )
        implementation_ids = {item.id for item in self.implementations}
        api_surface_ids = {item.id for item in self.api_surfaces}
        verification_test_ids = {item.id for item in self.verification_tests}
        state_trace_ids = {item.id for item in self.state_traces}
        all_transition_ids = set(transition_ids)
        machine_ids = {item.id for item in self.state_machines}
        transitions_by_id = {
            transition.id: transition
            for machine in self.state_machines
            for transition in machine.transitions
        }
        coverage_ids = [item.transition_id for item in self.transition_coverage]
        if len(coverage_ids) != len(set(coverage_ids)):
            raise ValueError("transition coverage IDs must be unique")
        if self.transition_coverage and set(coverage_ids) != all_transition_ids:
            missing = sorted(all_transition_ids - set(coverage_ids))
            extra = sorted(set(coverage_ids) - all_transition_ids)
            raise ValueError(
                "transition coverage must classify every modeled transition "
                f"(missing={missing}, extra={extra})"
            )
        for coverage in self.transition_coverage:
            if coverage.transition_id not in all_transition_ids:
                raise ValueError(
                    f"transition coverage references missing transition {coverage.transition_id}"
                )
            missing_implementations = set(coverage.implementation_ids) - implementation_ids
            if missing_implementations:
                raise ValueError(
                    f"transition coverage {coverage.transition_id} references missing "
                    f"implementations {sorted(missing_implementations)}"
                )
            if coverage.status == "mapped":
                transition = transitions_by_id[coverage.transition_id]
                if not set(coverage.implementation_ids) <= set(transition.implementation_ids):
                    raise ValueError(
                        f"mapped transition coverage {coverage.transition_id} is not "
                        "reciprocal with the transition implementation IDs"
                    )
        for clause in self.clauses:
            if clause.parent_id is not None and clause.parent_id not in clause_ids:
                raise ValueError(f"clause {clause.id} references missing parent {clause.parent_id}")
            seen: set[str] = set()
            current = clause
            while current.parent_id is not None:
                if current.id in seen:
                    raise ValueError(f"clause hierarchy cycle includes {current.id}")
                seen.add(current.id)
                parent = next(item for item in self.clauses if item.id == current.parent_id)
                current = parent
        for requirement in self.requirements:
            if requirement.clause_id is not None and requirement.clause_id not in clause_ids:
                raise ValueError(
                    f"requirement {requirement.id} references missing clause "
                    f"{requirement.clause_id}"
                )
            missing_transitions = set(requirement.transition_ids) - all_transition_ids
            if missing_transitions:
                raise ValueError(
                    f"requirement {requirement.id} references missing transitions "
                    f"{sorted(missing_transitions)}"
                )
        for record in (*self.references, *self.figures, *self.examples):
            if record.clause_id is not None and record.clause_id not in clause_ids:
                raise ValueError(f"record {record.id} references missing clause {record.clause_id}")
        for note in self.notes:
            if note.owner_id is not None and note.owner_id not in clause_ids:
                raise ValueError(f"note {note.id} references missing owner {note.owner_id}")
        for block in self.content_blocks:
            if block.clause_id is not None and block.clause_id not in clause_ids:
                raise ValueError(
                    f"content block {block.id} references missing clause {block.clause_id}"
                )
            if not set(block.element_ids) <= {item.id for item in self.content_elements}:
                missing = sorted(
                    set(block.element_ids) - {item.id for item in self.content_elements}
                )
                raise ValueError(f"content block {block.id} references missing elements {missing}")
        content_block_ids = {item.id for item in self.content_blocks}
        content_element_ids = {item.id for item in self.content_elements}
        for element in self.content_elements:
            if element.block_id not in content_block_ids:
                raise ValueError(
                    f"content element {element.id} references missing block {element.block_id}"
                )
            if element.clause_id is not None and element.clause_id not in clause_ids:
                raise ValueError(
                    f"content element {element.id} references missing clause {element.clause_id}"
                )
            if element.parent_id is not None and element.parent_id not in content_element_ids:
                raise ValueError(
                    f"content element {element.id} references missing parent {element.parent_id}"
                )
            if element.kind == "list-item":
                if element.parent_id is None:
                    raise ValueError(f"list item {element.id} must name a parent list")
                parent = next(
                    item for item in self.content_elements if item.id == element.parent_id
                )
                if parent.kind != "list":
                    raise ValueError(f"list item {element.id} parent must be a list")
            elif element.parent_id is not None:
                raise ValueError(f"only list items may name a content element parent: {element.id}")
        local_record_ids = self.semantic_record_ids()
        for block in self.content_blocks:
            missing_records = set(block.record_ids) - local_record_ids
            if missing_records:
                raise ValueError(
                    f"content block {block.id} references missing records {sorted(missing_records)}"
                )
        for element in self.content_elements:
            missing_records = set(element.record_ids) - local_record_ids
            if missing_records:
                raise ValueError(
                    "content element "
                    f"{element.id} references missing records {sorted(missing_records)}"
                )
        table_ids = {table.id for table in self.tables}
        table_cell_ids = [cell.id for table in self.tables for cell in table.cells]
        if len(table_cell_ids) != len(set(table_cell_ids)):
            raise ValueError("table cell IDs must be unique across the document")
        family_by_table: dict[str, str] = {}
        for family in self.table_families:
            if family.clause_id is not None and family.clause_id not in clause_ids:
                raise ValueError(
                    f"table family {family.id} references missing clause {family.clause_id}"
                )
            missing_tables = set(family.table_ids) - table_ids
            if missing_tables:
                raise ValueError(
                    f"table family {family.id} references missing tables {sorted(missing_tables)}"
                )
            for table_id in family.table_ids:
                prior = family_by_table.get(table_id)
                if prior is not None and prior != family.id:
                    raise ValueError(
                        f"table {table_id} belongs to multiple families: {prior}, {family.id}"
                    )
                family_by_table[table_id] = family.id
        for table in self.tables:
            expected_family = family_by_table.get(table.id)
            if table.family_id is not None and table.family_id != expected_family:
                raise ValueError(
                    f"table {table.id} family link {table.family_id} does not match "
                    f"family membership {expected_family}"
                )
        for reference in self.references:
            for target in reference.targets:
                if (
                    target.document_id == self.document_id
                    and target.record_id not in local_record_ids
                ):
                    raise ValueError(
                        f"reference {reference.id} targets missing local record {target.record_id}"
                    )
        for cross_reference in self.cross_references:
            if cross_reference.owner_id not in local_record_ids:
                raise ValueError(
                    f"cross-reference {cross_reference.id} references missing owner "
                    f"{cross_reference.owner_id}"
                )
            if (
                cross_reference.target_document_id == self.document_id
                and cross_reference.target_record_id not in local_record_ids
            ):
                raise ValueError(
                    f"cross-reference {cross_reference.id} targets missing local record "
                    f"{cross_reference.target_record_id}"
                )
        for machine in self.state_machines:
            if machine.clause_id is not None and machine.clause_id not in clause_ids:
                raise ValueError(
                    f"state machine {machine.id} references missing clause {machine.clause_id}"
                )
            for transition in machine.transitions:
                if transition.clause_id is not None and transition.clause_id not in clause_ids:
                    raise ValueError(
                        f"transition {transition.id} references missing clause "
                        f"{transition.clause_id}"
                    )
                missing_requirements = set(transition.requirement_ids) - requirement_ids
                if missing_requirements:
                    raise ValueError(
                        f"transition {transition.id} references missing requirements "
                        f"{sorted(missing_requirements)}"
                    )
                missing_implementations = set(transition.implementation_ids) - implementation_ids
                if missing_implementations:
                    raise ValueError(
                        f"transition {transition.id} references missing implementations "
                        f"{sorted(missing_implementations)}"
                    )
                for requirement_id in transition.requirement_ids:
                    requirement = next(
                        item for item in self.requirements if item.id == requirement_id
                    )
                    if transition.id not in requirement.transition_ids:
                        raise ValueError(
                            f"transition {transition.id} and requirement "
                            f"{requirement_id} must link bidirectionally"
                        )
                for implementation_id in transition.implementation_ids:
                    implementation = next(
                        item for item in self.implementations if item.id == implementation_id
                    )
                    if transition.id not in implementation.transition_ids:
                        raise ValueError(
                            f"transition {transition.id} and implementation "
                            f"{implementation_id} must link bidirectionally"
                        )
        for diagram in self.sequence_diagrams:
            if diagram.clause_id is not None and diagram.clause_id not in clause_ids:
                raise ValueError(
                    f"sequence diagram {diagram.id} references missing clause {diagram.clause_id}"
                )
            for message in diagram.messages:
                if message.clause_id is not None and message.clause_id not in clause_ids:
                    raise ValueError(
                        f"sequence message {message.id} references missing clause "
                        f"{message.clause_id}"
                    )
                missing_requirements = set(message.requirement_ids) - requirement_ids
                if missing_requirements:
                    raise ValueError(
                        f"sequence message {message.id} references missing requirements "
                        f"{sorted(missing_requirements)}"
                    )
        for diagram in self.graph_diagrams:
            if diagram.clause_id is not None and diagram.clause_id not in clause_ids:
                raise ValueError(
                    f"graph diagram {diagram.id} references missing clause {diagram.clause_id}"
                )
            for edge in diagram.edges:
                if edge.clause_id is not None and edge.clause_id not in clause_ids:
                    raise ValueError(
                        f"graph edge {edge.id} references missing clause {edge.clause_id}"
                    )
                missing_requirements = set(edge.requirement_ids) - requirement_ids
                if missing_requirements:
                    raise ValueError(
                        f"graph edge {edge.id} references missing requirements "
                        f"{sorted(missing_requirements)}"
                    )
                missing_implementations = set(edge.implementation_ids) - implementation_ids
                if missing_implementations:
                    raise ValueError(
                        f"graph edge {edge.id} references missing implementations "
                        f"{sorted(missing_implementations)}"
                    )
        for link in self.requirement_links:
            if link.requirement_id not in requirement_ids:
                raise ValueError(
                    f"requirement link {link.id} references missing requirement "
                    f"{link.requirement_id}"
                )
            transition = transitions_by_id.get(link.transition_id)
            if transition is None:
                raise ValueError(
                    f"requirement link {link.id} references missing transition {link.transition_id}"
                )
            requirement = next(item for item in self.requirements if item.id == link.requirement_id)
            if link.transition_id not in requirement.transition_ids:
                raise ValueError(
                    f"requirement link {link.id} is missing from requirement "
                    f"{link.requirement_id}.transition_ids"
                )
            if link.requirement_id not in transition.requirement_ids:
                raise ValueError(
                    f"requirement link {link.id} is missing from transition "
                    f"{link.transition_id}.requirement_ids"
                )
        link_pairs = {(link.requirement_id, link.transition_id) for link in self.requirement_links}
        for requirement in self.requirements:
            if requirement.extraction != "explicit":
                continue
            if requirement.coverage_kind == "transition":
                missing_links = {
                    transition_id
                    for transition_id in requirement.transition_ids
                    if (requirement.id, transition_id) not in link_pairs
                }
                if missing_links:
                    raise ValueError(
                        f"explicit requirement {requirement.id} is missing reviewed links "
                        f"{sorted(missing_links)}"
                    )
            elif requirement.transition_ids:
                raise ValueError(
                    f"non-transition requirement {requirement.id} cannot name transitions"
                )
        for implementation in self.implementations:
            missing_clauses = set(implementation.clause_ids) - clause_ids
            if missing_clauses:
                raise ValueError(
                    f"implementation {implementation.id} references missing clauses "
                    f"{sorted(missing_clauses)}"
                )
            missing_requirements = set(implementation.requirement_ids) - requirement_ids
            if missing_requirements:
                raise ValueError(
                    f"implementation {implementation.id} references missing requirements "
                    f"{sorted(missing_requirements)}"
                )
            missing_transitions = set(implementation.transition_ids) - all_transition_ids
            if missing_transitions:
                raise ValueError(
                    f"implementation {implementation.id} references missing transitions "
                    f"{sorted(missing_transitions)}"
                )
            for transition_id in implementation.transition_ids:
                transition = transitions_by_id[transition_id]
                if implementation.id not in transition.implementation_ids:
                    raise ValueError(
                        f"implementation {implementation.id} and transition "
                        f"{transition_id} must link bidirectionally"
                    )
            if implementation.requirement_ids and implementation.transition_ids:
                missing_pairs = {
                    (requirement_id, transition_id)
                    for requirement_id in implementation.requirement_ids
                    for transition_id in implementation.transition_ids
                    if (requirement_id, transition_id) not in link_pairs
                }
                if missing_pairs:
                    raise ValueError(
                        f"implementation {implementation.id} is missing requirement "
                        f"links {sorted(missing_pairs)}"
                    )
        for surface in self.api_surfaces:
            missing_clauses = set(surface.clause_ids) - clause_ids
            if missing_clauses:
                raise ValueError(
                    f"API surface {surface.id} references missing clauses {sorted(missing_clauses)}"
                )
            missing_requirements = set(surface.requirement_ids) - requirement_ids
            if missing_requirements:
                raise ValueError(
                    f"API surface {surface.id} references missing requirements "
                    f"{sorted(missing_requirements)}"
                )
            missing_transitions = set(surface.transition_ids) - all_transition_ids
            if missing_transitions:
                raise ValueError(
                    f"API surface {surface.id} references missing transitions "
                    f"{sorted(missing_transitions)}"
                )
            missing_mappings = set(surface.implementation_mapping_ids) - implementation_ids
            if missing_mappings:
                raise ValueError(
                    f"API surface {surface.id} references missing implementations "
                    f"{sorted(missing_mappings)}"
                )
        for crosswalk in self.api_crosswalks:
            if crosswalk.implementation_mapping_id not in implementation_ids:
                raise ValueError(
                    f"API crosswalk {crosswalk.id} references missing implementation "
                    f"{crosswalk.implementation_mapping_id}"
                )
            missing_candidates = set(crosswalk.candidate_api_surface_ids) - api_surface_ids
            if missing_candidates:
                raise ValueError(
                    f"API crosswalk {crosswalk.id} references missing candidate surfaces "
                    f"{sorted(missing_candidates)}"
                )
            missing_selected = set(crosswalk.selected_api_surface_ids) - api_surface_ids
            if missing_selected:
                raise ValueError(
                    f"API crosswalk {crosswalk.id} references missing selected surfaces "
                    f"{sorted(missing_selected)}"
                )
            if not set(crosswalk.selected_api_surface_ids) <= set(
                crosswalk.candidate_api_surface_ids
            ):
                raise ValueError(
                    f"API crosswalk {crosswalk.id} selects a surface outside its candidates"
                )
            candidate_count = len(crosswalk.candidate_api_surface_ids)
            selected_count = len(crosswalk.selected_api_surface_ids)
            if crosswalk.status == "matched" and selected_count != 1:
                raise ValueError(
                    f"matched API crosswalk {crosswalk.id} must select exactly one surface"
                )
            if crosswalk.status == "ambiguous" and candidate_count < 2:
                raise ValueError(
                    f"ambiguous API crosswalk {crosswalk.id} must have multiple candidates"
                )
            if crosswalk.status in {"unmatched", "planned"} and candidate_count:
                raise ValueError(
                    f"{crosswalk.status} API crosswalk {crosswalk.id} cannot have candidates"
                )
        for binding in self.requirement_api_bindings:
            if binding.requirement_id not in requirement_ids:
                raise ValueError(
                    f"requirement API binding {binding.id} references missing requirement "
                    f"{binding.requirement_id}"
                )
            missing_candidates = set(binding.candidate_api_surface_ids) - api_surface_ids
            if missing_candidates:
                raise ValueError(
                    f"requirement API binding {binding.id} references missing candidate surfaces "
                    f"{sorted(missing_candidates)}"
                )
            if binding.api_surface_id is not None:
                surface = next(
                    item for item in self.api_surfaces if item.id == binding.api_surface_id
                )
                if surface.language != binding.language:
                    raise ValueError(
                        f"requirement API binding {binding.id} language {binding.language} "
                        f"does not match API surface {surface.id} language {surface.language}"
                    )
            if binding.status == "matched" and binding.api_surface_id is None:
                raise ValueError(
                    f"matched requirement API binding {binding.id} must select a surface"
                )
            if binding.status == "ambiguous" and len(binding.candidate_api_surface_ids) < 2:
                raise ValueError(f"ambiguous requirement API binding {binding.id} needs candidates")
            if binding.status == "unmatched" and binding.candidate_api_surface_ids:
                raise ValueError(
                    f"unmatched requirement API binding {binding.id} cannot have candidates"
                )
        for test in self.verification_tests:
            missing_requirements = set(test.requirement_ids) - requirement_ids
            if missing_requirements:
                raise ValueError(
                    f"verification test {test.id} references missing requirements "
                    f"{sorted(missing_requirements)}"
                )
            missing_transitions = set(test.transition_ids) - all_transition_ids
            if missing_transitions:
                raise ValueError(
                    f"verification test {test.id} references missing transitions "
                    f"{sorted(missing_transitions)}"
                )
            missing_surfaces = set(test.api_surface_ids) - api_surface_ids
            if missing_surfaces:
                raise ValueError(
                    f"verification test {test.id} references missing API surfaces "
                    f"{sorted(missing_surfaces)}"
                )
            missing_traces = set(test.trace_ids) - state_trace_ids
            if missing_traces:
                raise ValueError(
                    f"verification test {test.id} references missing state traces "
                    f"{sorted(missing_traces)}"
                )
            missing_mappings = set(test.implementation_mapping_ids) - implementation_ids
            if missing_mappings:
                raise ValueError(
                    f"verification test {test.id} references missing implementations "
                    f"{sorted(missing_mappings)}"
                )
        for trace in self.state_traces:
            if trace.machine_id not in machine_ids:
                raise ValueError(
                    f"state trace {trace.id} references missing machine {trace.machine_id}"
                )
            machine = next(item for item in self.state_machines if item.id == trace.machine_id)
            machine_state_ids = {item.id for item in machine.states}
            machine_transition_ids = {item.id for item in machine.transitions}
            if (
                trace.initial_state_id is not None
                and trace.initial_state_id not in machine_state_ids
            ):
                raise ValueError(
                    f"state trace {trace.id} references missing initial state "
                    f"{trace.initial_state_id}"
                )
            if (
                trace.expected_final_state is not None
                and trace.expected_final_state not in machine_state_ids
            ):
                raise ValueError(
                    f"state trace {trace.id} references missing final state "
                    f"{trace.expected_final_state}"
                )
            missing_requirements = set(trace.requirement_ids) - requirement_ids
            if missing_requirements:
                raise ValueError(
                    f"state trace {trace.id} references missing requirements "
                    f"{sorted(missing_requirements)}"
                )
            missing_transitions = set(trace.transition_ids) - machine_transition_ids
            if missing_transitions:
                raise ValueError(
                    f"state trace {trace.id} references transitions outside machine "
                    f"{sorted(missing_transitions)}"
                )
            missing_surfaces = set(trace.api_surface_ids) - api_surface_ids
            if missing_surfaces:
                raise ValueError(
                    f"state trace {trace.id} references missing API surfaces "
                    f"{sorted(missing_surfaces)}"
                )
            missing_tests = set(trace.verification_test_ids) - verification_test_ids
            if missing_tests:
                raise ValueError(
                    f"state trace {trace.id} references missing verification tests "
                    f"{sorted(missing_tests)}"
                )
            for step in trace.steps:
                if step.source_state is not None and step.source_state not in machine_state_ids:
                    raise ValueError(
                        f"trace step {step.id} references missing source state {step.source_state}"
                    )
                if step.target_state is not None and step.target_state not in machine_state_ids:
                    raise ValueError(
                        f"trace step {step.id} references missing target state {step.target_state}"
                    )
                if (
                    step.transition_id is not None
                    and step.transition_id not in machine_transition_ids
                ):
                    raise ValueError(
                        f"trace step {step.id} references missing transition {step.transition_id}"
                    )
                missing_requirements = set(step.requirement_ids) - requirement_ids
                if missing_requirements:
                    raise ValueError(
                        f"trace step {step.id} references missing requirements "
                        f"{sorted(missing_requirements)}"
                    )
                missing_surfaces = set(step.api_surface_ids) - api_surface_ids
                if missing_surfaces:
                    raise ValueError(
                        f"trace step {step.id} references missing API surfaces "
                        f"{sorted(missing_surfaces)}"
                    )
        return self

    def find_definition(self, term: str) -> Definition | None:
        """Find a definition by case-insensitive term."""
        wanted = term.casefold()
        return next((item for item in self.definitions if item.term.casefold() == wanted), None)

    def ordered_clauses(self) -> tuple[Clause, ...]:
        """Return clauses in canonical document-number order."""
        by_id = {item.id: item for item in self.clauses}
        return tuple(by_id[item] for item in self.clause_order)

    def root_clauses(self) -> tuple[Clause, ...]:
        """Return top-level clauses in canonical document-number order."""
        return tuple(item for item in self.ordered_clauses() if item.parent_id is None)

    def ordered_definitions(self) -> tuple[Definition, ...]:
        """Return definitions grouped by owning clause and then by term."""
        clause_index = {item.id: index for index, item in enumerate(self.ordered_clauses())}
        return tuple(
            sorted(
                self.definitions,
                key=lambda item: (
                    clause_index.get(item.clause_id or "", len(clause_index)),
                    item.term.casefold(),
                    item.id,
                ),
            )
        )

    def ordered_requirements(self) -> tuple[Requirement, ...]:
        """Return requirements grouped by owning clause and stable ID."""
        clause_index = {item.id: index for index, item in enumerate(self.ordered_clauses())}
        return tuple(
            sorted(
                self.requirements,
                key=lambda item: (
                    clause_index.get(item.clause_id or "", len(clause_index)),
                    item.id,
                ),
            )
        )

    def ordered_annexes(self) -> tuple[Annex, ...]:
        """Return annexes in semantic letter order."""
        return tuple(sorted(self.annexes, key=lambda item: (item.letter.casefold(), item.id)))

    def canonical_record_ids(self) -> tuple[str, ...]:
        """Return the stable record sequence used by hierarchy generators."""
        return tuple(
            item.id
            for item in (
                *self.ordered_clauses(),
                *self.ordered_definitions(),
                *self.ordered_requirements(),
                *self.content_elements,
                *self.ordered_annexes(),
            )
        )

    def semantic_record_ids(self) -> frozenset[str]:
        """Return every locally addressable semantic record ID."""
        return (
            frozenset(
                item.id
                for item in (
                    *self.clauses,
                    *self.definitions,
                    *self.requirements,
                    *self.requirement_links,
                    *self.content_blocks,
                    *self.content_elements,
                    *self.state_machines,
                    *self.sequence_diagrams,
                    *self.graph_diagrams,
                    *self.tables,
                    *self.table_families,
                    *self.references,
                    *self.cross_references,
                    *self.notes,
                    *self.figures,
                    *self.examples,
                    *self.annexes,
                    *self.implementations,
                    *self.api_surfaces,
                    *self.api_crosswalks,
                    *self.requirement_api_bindings,
                    *self.verification_tests,
                    *self.state_traces,
                )
            )
            | frozenset(
            item.id
            for machine in self.state_machines
            for item in (*machine.states, *machine.transitions)
        )
            | frozenset(
            item.id
            for diagram in self.sequence_diagrams
            for item in (*diagram.participants, *diagram.messages)
        )
            | frozenset(
            item.id
            for diagram in self.graph_diagrams
            for item in (*diagram.nodes, *diagram.edges, *diagram.annotations)
        )
            | frozenset(cell.id for table in self.tables for cell in table.cells)
        )

    def semantic_dependencies(
        self,
        record_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return qualified ownership, reference, and implementation edges."""
        kinds: dict[str, str] = {}

        def register(identifier: str, kind: str) -> None:
            kinds.setdefault(identifier, kind)

        for record in self.clauses:
            register(record.id, "clause")
        for record in self.definitions:
            register(record.id, "definition")
        for record in self.requirements:
            register(record.id, "requirement")
        for record in self.requirement_links:
            register(record.id, "requirement-link")
        for record in self.content_blocks:
            register(record.id, "content-block")
        for record in self.content_elements:
            register(record.id, "content-element")
        for record in self.state_machines:
            register(record.id, "state-machine")
            for state in record.states:
                register(state.id, "state")
            for transition in record.transitions:
                register(transition.id, "transition")
        for record in self.sequence_diagrams:
            register(record.id, "sequence-diagram")
            for message in record.messages:
                register(message.id, "sequence-message")
        for record in self.graph_diagrams:
            register(record.id, "graph-diagram")
            for edge in record.edges:
                register(edge.id, "graph-edge")
        for record in self.implementations:
            register(record.id, "implementation")
        for record in self.api_surfaces:
            register(record.id, "api-surface")
        for record in self.api_crosswalks:
            register(record.id, "api-crosswalk")
        for record in self.requirement_api_bindings:
            register(record.id, "requirement-api-binding")
        for record in self.verification_tests:
            register(record.id, "verification-test")
        for record in self.state_traces:
            register(record.id, "state-trace")
        for record in self.tables:
            register(record.id, "table")
            for cell in record.cells:
                register(cell.id, "table-cell")
        for record in self.table_families:
            register(record.id, "table-family")
        for record in self.references:
            register(record.id, "reference")
        for record in self.cross_references:
            register(record.id, "cross-reference")
        for record in self.notes:
            register(record.id, "note")
        for record in self.figures:
            register(record.id, "figure")
        for record in self.examples:
            register(record.id, "example")
        for record in self.annexes:
            register(record.id, "annex")

        edges: dict[str, ComplianceDependency] = {}

        def add(
            source_id: str,
            target_id: str | None,
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
            ],
            source: SourceRef | None,
            *,
            source_kind: str | None = None,
            target_kind: str | None = None,
            target_document_id: str | None = None,
        ) -> None:
            if target_id is None or target_id == "":
                return
            source_kind_value = source_kind or kinds.get(source_id, "unknown")
            target_kind_value = target_kind or kinds.get(target_id, "unknown")
            target_document = target_document_id or self.document_id
            identifier = f"{self.document_id}:{source_id}->{target_document}:{target_id}:{relation}"
            if record_id is not None and record_id not in {source_id, target_id}:
                return
            edges.setdefault(
                identifier,
                ComplianceDependency(
                    id=identifier,
                    source_document_id=self.document_id,
                    source_record_id=source_id,
                    source_kind=source_kind_value,
                    target_document_id=target_document,
                    target_record_id=target_id,
                    target_kind=target_kind_value,
                    relation=relation,
                    source=source,
                ),
            )

        for clause in self.clauses:
            add(clause.id, clause.parent_id, "owned-by", clause.source)
        for definition in self.definitions:
            add(definition.id, definition.clause_id, "owned-by", definition.source)
        for requirement in self.requirements:
            add(requirement.id, requirement.clause_id, "owned-by", requirement.source)
            for transition_id in requirement.transition_ids:
                add(requirement.id, transition_id, "governs", requirement.source)
        for link in self.requirement_links:
            add(link.id, link.requirement_id, "references", link.source)
            add(link.id, link.transition_id, "references", link.source)
        for block in self.content_blocks:
            add(block.id, block.clause_id, "owned-by", block.source)
            for element_id in block.element_ids:
                add(block.id, element_id, "contains", block.source)
            for related_id in block.record_ids:
                add(block.id, related_id, "mentions", block.source)
        for element in self.content_elements:
            add(element.id, element.block_id, "member-of", element.source)
            add(element.id, element.clause_id, "owned-by", element.source)
            for related_id in element.record_ids:
                add(element.id, related_id, "mentions", element.source)
        for machine in self.state_machines:
            add(machine.id, machine.clause_id, "owned-by", machine.source)
            for transition in machine.transitions:
                add(transition.id, machine.id, "member-of", transition.source)
                add(transition.id, transition.clause_id, "owned-by", transition.source)
                for requirement_id in transition.requirement_ids:
                    add(transition.id, requirement_id, "governs", transition.source)
                for implementation_id in transition.implementation_ids:
                    add(transition.id, implementation_id, "implements", transition.source)
        for diagram in self.sequence_diagrams:
            add(diagram.id, diagram.clause_id, "owned-by", diagram.source)
            for message in diagram.messages:
                add(message.id, diagram.id, "member-of", message.source or diagram.source)
                add(message.id, message.clause_id or diagram.clause_id, "owned-by", message.source)
                for requirement_id in message.requirement_ids:
                    add(message.id, requirement_id, "governs", message.source)
        for diagram in self.graph_diagrams:
            add(diagram.id, diagram.clause_id, "owned-by", diagram.source)
            for edge in diagram.edges:
                add(edge.id, diagram.id, "member-of", edge.source_ref)
                add(edge.id, edge.clause_id, "owned-by", edge.source_ref)
                for requirement_id in edge.requirement_ids:
                    add(edge.id, requirement_id, "governs", edge.source_ref)
                for implementation_id in edge.implementation_ids:
                    add(edge.id, implementation_id, "implements", edge.source_ref)
        for implementation in self.implementations:
            for clause_id in implementation.clause_ids:
                add(implementation.id, clause_id, "implements", implementation.source)
            for requirement_id in implementation.requirement_ids:
                add(implementation.id, requirement_id, "implements", implementation.source)
            for transition_id in implementation.transition_ids:
                add(implementation.id, transition_id, "implements", implementation.source)
        for surface in self.api_surfaces:
            for mapping_id in surface.implementation_mapping_ids:
                add(surface.id, mapping_id, "implements", surface.source)
            for requirement_id in surface.requirement_ids:
                add(surface.id, requirement_id, "governs", surface.source)
            for transition_id in surface.transition_ids:
                add(surface.id, transition_id, "implements", surface.source)
        for crosswalk in self.api_crosswalks:
            add(
                crosswalk.id,
                crosswalk.implementation_mapping_id,
                "annotates",
                crosswalk.source,
            )
            for surface_id in crosswalk.candidate_api_surface_ids:
                add(crosswalk.id, surface_id, "mentions", crosswalk.source)
            for surface_id in crosswalk.selected_api_surface_ids:
                add(crosswalk.id, surface_id, "implements", crosswalk.source)
        for binding in self.requirement_api_bindings:
            add(binding.id, binding.requirement_id, "references", binding.source)
            if binding.api_surface_id is not None:
                add(binding.id, binding.api_surface_id, "maps-to", binding.source)
            for surface_id in binding.candidate_api_surface_ids:
                add(binding.id, surface_id, "mentions", binding.source)
        for test in self.verification_tests:
            for requirement_id in test.requirement_ids:
                add(test.id, requirement_id, "annotates", test.source)
            for transition_id in test.transition_ids:
                add(test.id, transition_id, "annotates", test.source)
            for surface_id in test.api_surface_ids:
                add(test.id, surface_id, "annotates", test.source)
            for trace_id in test.trace_ids:
                add(test.id, trace_id, "annotates", test.source)
            for mapping_id in test.implementation_mapping_ids:
                add(test.id, mapping_id, "annotates", test.source)
        for trace in self.state_traces:
            add(trace.id, trace.machine_id, "member-of", trace.source)
            for requirement_id in trace.requirement_ids:
                add(trace.id, requirement_id, "governs", trace.source)
            for transition_id in trace.transition_ids:
                add(trace.id, transition_id, "annotates", trace.source)
            for surface_id in trace.api_surface_ids:
                add(trace.id, surface_id, "annotates", trace.source)
            for test_id in trace.verification_test_ids:
                add(trace.id, test_id, "annotates", trace.source)
        for family in self.table_families:
            add(family.id, family.clause_id, "owned-by", family.source)
            for table_id in family.table_ids:
                add(family.id, table_id, "contains", family.source)
        for table in self.tables:
            if table.family_id:
                add(table.id, table.family_id, "member-of", table.source)
            for cell in table.cells:
                add(cell.id, table.id, "member-of", cell.source)
                for related_id in cell.record_ids:
                    add(cell.id, related_id, "annotates", cell.source)
        for reference in self.references:
            add(reference.id, reference.clause_id, "owned-by", reference.source)
            for target in reference.targets:
                add(
                    reference.id,
                    target.record_id,
                    "references",
                    reference.source,
                    target_kind=kinds.get(target.record_id, "external"),
                    target_document_id=target.document_id,
                )
        for cross_reference in self.cross_references:
            add(
                cross_reference.owner_id,
                cross_reference.target_record_id,
                cross_reference.relation,
                cross_reference.source,
                target_kind=cross_reference.kind,
                target_document_id=cross_reference.target_document_id,
            )
        for note in self.notes:
            add(note.id, note.owner_id, "owned-by", note.source)
        for figure in self.figures:
            add(figure.id, figure.clause_id, "owned-by", figure.source)
        for example in self.examples:
            add(example.id, example.clause_id, "owned-by", example.source)
        return tuple(sorted(edges.values(), key=lambda item: item.id))

    def table_definition_dependency_counts(self) -> dict[str, int]:
        """Summarize table-cell ownership and exact definition-term links."""
        definition_ids = {item.id for item in self.definitions}
        cells = tuple(cell for table in self.tables for cell in table.cells)
        linked_cells = tuple(
            cell
            for cell in cells
            if any(record_id in definition_ids for record_id in cell.record_ids)
        )
        return {
            "tables": len(self.tables),
            "table_families": len(self.table_families),
            "cells": len(cells),
            "cells_with_definition_links": len(linked_cells),
            "definition_links": sum(
                record_id in definition_ids for cell in cells for record_id in cell.record_ids
            ),
        }

    def content_elements_for_clause(
        self,
        clause_id: str,
        *,
        kinds: tuple[str, ...] = (),
    ) -> tuple[ContentElement, ...]:
        """Return typed content owned directly by a clause."""
        allowed = set(kinds)
        return tuple(
            item
            for item in self.content_elements
            if item.clause_id == clause_id and (not allowed or item.kind in allowed)
        )

    def search_content(
        self,
        text: str,
        *,
        clause_id: str | None = None,
        kinds: tuple[str, ...] = (),
    ) -> tuple[ContentElement, ...]:
        """Find typed content elements by case-insensitive text search."""
        wanted = text.casefold()
        allowed = set(kinds)
        return tuple(
            item
            for item in self.content_elements
            if wanted in item.text.casefold()
            and (clause_id is None or item.clause_id == clause_id)
            and (not allowed or item.kind in allowed)
        )

    def requirements_for_clause(self, clause: str) -> tuple[Requirement, ...]:
        """Return requirements assigned to a clause or subclause."""
        number = clause.removeprefix("clause-")
        return tuple(item for item in self.requirements if item.clause == number)

    def transitions_for_requirement(self, requirement_id: str) -> tuple[Transition, ...]:
        """Return state transitions explicitly linked to a requirement."""
        linked_transition_ids = {
            link.transition_id
            for link in self.requirement_links
            if link.requirement_id == requirement_id
        }
        return tuple(
            transition
            for machine in self.state_machines
            for transition in machine.transitions
            if transition.id in linked_transition_ids
            or requirement_id in transition.requirement_ids
            or any(
                requirement_id in implementation.requirement_ids
                and transition.id in implementation.transition_ids
                for implementation in self.implementations
            )
        )

    def transitions_by_initiator(self, initiator: str) -> tuple[Transition, ...]:
        """Return transitions initiated by a federate, RTI, or automatic guard."""
        return tuple(
            transition
            for machine in self.state_machines
            for transition in machine.transitions
            if transition.initiator == initiator
        )

    def transitions_for_state_event(
        self,
        state_id: str,
        event: str,
        machine_id: str | None = None,
    ) -> tuple[Transition, ...]:
        """Return transitions from a state on an event across selected machines."""
        machines = self._selected_machines(machine_id)
        if not any(state_id in {state.id for state in machine.states} for machine in machines):
            raise ValueError(f"unknown state {state_id}")
        wanted_event = event.casefold().strip()
        return tuple(
            transition
            for machine in machines
            for transition in machine.transitions
            if transition.source_state == state_id
            and transition.event.casefold().strip() == wanted_event
        )

    def _selected_machines(self, machine_id: str | None = None) -> tuple[StateMachine, ...]:
        if machine_id is None:
            return self.state_machines
        machines = tuple(item for item in self.state_machines if item.id == machine_id)
        if not machines:
            raise ValueError(f"unknown state machine {machine_id}")
        return machines

    def query_requirements_applicable_after(
        self,
        state_id: str,
        event: str,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
    ) -> tuple[RequirementApplicability, ...]:
        """Return typed requirement matches for a state/event query.

        The result keeps the transition and relationship that made each
        requirement applicable.  This is the machine-facing counterpart to
        :meth:`requirements_applicable_after`, which remains as a compact
        backward-compatible requirement-only helper.
        """
        machines = self._selected_machines(machine_id)
        if not any(state_id in {state.id for state in machine.states} for machine in machines):
            raise ValueError(f"unknown state {state_id}")
        wanted_event = event.casefold().strip()
        selected = tuple(
            (machine, transition)
            for machine in machines
            for transition in machine.transitions
            if transition.source_state == state_id
            and transition.event.casefold().strip() == wanted_event
        )
        requirements = {item.id: item for item in self.requirements}
        relation_priority = {
            "transition": 0,
            "reviewed-link": 1,
            "implementation": 2,
            "clause-fallback": 3,
        }

        def add_match(
            relations: dict[str, RequirementApplicabilityRelation],
            requirement_id: str,
            relation: RequirementApplicabilityRelation,
        ) -> None:
            if requirement_id not in requirements:
                return
            previous = relations.get(requirement_id)
            if previous is None or relation_priority[relation] < relation_priority[previous]:
                relations[requirement_id] = relation

        matches: list[
            tuple[
                StateMachine,
                Transition,
                dict[str, RequirementApplicabilityRelation],
            ]
        ] = []
        for machine, transition in selected:
            relations: dict[str, RequirementApplicabilityRelation] = {}

            for requirement_id in transition.requirement_ids:
                add_match(relations, requirement_id, "transition")
            for link in self.requirement_links:
                if link.transition_id == transition.id:
                    add_match(relations, link.requirement_id, "reviewed-link")
            for implementation in self.implementation_mappings_for_transition(transition.id):
                for requirement_id in implementation.requirement_ids:
                    add_match(relations, requirement_id, "implementation")
            matches.append((machine, transition, relations))

        has_direct_match = any(relations for _, _, relations in matches)
        if not has_direct_match:
            for index, (machine, transition, relations) in enumerate(matches):
                if transition.clause_id is None:
                    continue
                for requirement in self.requirements:
                    if requirement.clause_id == transition.clause_id:
                        relations[requirement.id] = "clause-fallback"
                matches[index] = (machine, transition, relations)

        result: list[RequirementApplicability] = []
        for machine, transition, relations in matches:
            for requirement_id, relation in relations.items():
                requirement = requirements[requirement_id]
                if not include_candidates and requirement.extraction != "explicit":
                    continue
                result.append(
                    RequirementApplicability(
                        document_id=self.document_id,
                        machine_id=machine.id,
                        state_id=state_id,
                        event=transition.event,
                        transition_id=transition.id,
                        target_state=transition.target_state,
                        clause_id=transition.clause_id,
                        requirement_id=requirement.id,
                        relation=relation,
                    )
                )
        return tuple(result)

    def requirements_applicable_after(
        self,
        state_id: str,
        event: str,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
    ) -> tuple[Requirement, ...]:
        """Return reviewed requirements governing a state/event transition.

        A transition's direct requirement links take precedence. Its clause
        ownership provides a fallback only when that transition has no direct
        requirement link, which prevents unrelated requirements in the same
        clause from leaking into a precise state/event query. Candidate
        extractions are excluded by default because they have not yet passed
        semantic review.
        """
        requirement_ids = {
            item.requirement_id
            for item in self.query_requirements_applicable_after(
                state_id,
                event,
                machine_id,
                include_candidates=include_candidates,
            )
        }
        return tuple(
            requirement
            for requirement in self.requirements
            if (include_candidates or requirement.extraction == "explicit")
            and requirement.id in requirement_ids
        )

    def transitions_missing_implementation_mapping(
        self, machine_id: str | None = None
    ) -> tuple[Transition, ...]:
        """Return transitions with no code-facing implementation mapping yet."""
        machines = self._selected_machines(machine_id)
        return tuple(
            transition
            for machine in machines
            for transition in machine.transitions
            if not transition.implementation_ids
            and not self.implementation_mappings_for_transition(transition.id)
        )

    def transitions_without_implementation_mapping(
        self, machine_id: str | None = None
    ) -> tuple[Transition, ...]:
        """Preferred explicit-name alias for the unmapped-transition query."""
        return self.transitions_missing_implementation_mapping(machine_id)

    def transitions_without_concrete_implementation(
        self, machine_id: str | None = None
    ) -> tuple[Transition, ...]:
        """Return transitions lacking an implemented or verified mapping."""
        machines = self._selected_machines(machine_id)
        return tuple(
            transition
            for machine in machines
            for transition in machine.transitions
            if not self.implementation_coverage_for_transition(transition.id, machine.id).concrete
        )

    def transitions_missing_coverage(self) -> tuple[Transition, ...]:
        """Return modeled transitions without an explicit coverage disposition."""
        covered = {item.transition_id for item in self.transition_coverage}
        return tuple(
            transition
            for machine in self.state_machines
            for transition in machine.transitions
            if transition.id not in covered
        )

    def transition_coverage_counts(self) -> dict[str, int]:
        """Return deterministic transition coverage disposition counts."""
        counts = {"mapped": 0, "not-applicable": 0, "deferred": 0, "unclassified": 0}
        for item in self.transition_coverage:
            counts[item.status] += 1
        counts["unclassified"] = len(self.transitions_missing_coverage())
        return counts

    def requirement_review_counts(self) -> dict[str, int]:
        """Return candidate requirement review disposition counts."""
        counts = {"deferred": 0, "non-normative": 0, "layout-only": 0, "unreviewed": 0}
        for item in self.requirement_reviews:
            counts[item.status] += 1
        counts["unreviewed"] = sum(
            requirement.extraction == "candidate"
            and requirement.id not in {item.requirement_id for item in self.requirement_reviews}
            for requirement in self.requirements
        )
        return counts

    def implementation_mappings_for_transition(
        self, transition_id: str
    ) -> tuple[ImplementationMapping, ...]:
        """Return implementation mappings attached to a transition."""
        return tuple(item for item in self.implementations if transition_id in item.transition_ids)

    def implementation_mappings_for_requirement(
        self, requirement_id: str
    ) -> tuple[ImplementationMapping, ...]:
        """Return implementation mappings attached to a requirement."""
        if requirement_id not in {item.id for item in self.requirements}:
            raise ValueError(f"unknown requirement {requirement_id}")
        return tuple(
            item for item in self.implementations if requirement_id in item.requirement_ids
        )

    def implementation_mappings_for_clause(
        self, clause_id: str
    ) -> tuple[ImplementationMapping, ...]:
        """Return implementation mappings attached to a clause."""
        if clause_id not in {item.id for item in self.clauses}:
            raise ValueError(f"unknown clause {clause_id}")
        return tuple(item for item in self.implementations if clause_id in item.clause_ids)

    def implementation_mappings_for_interface(
        self,
        interface_kind: Literal["service", "callback", "adapter", "handler"] | None = None,
        interface_name: str | None = None,
    ) -> tuple[ImplementationMapping, ...]:
        """Filter mappings by interface kind and/or human-facing name."""
        wanted_name = interface_name.casefold().strip() if interface_name else None
        return tuple(
            item
            for item in self.implementations
            if (interface_kind is None or item.interface_kind == interface_kind)
            and (wanted_name is None or item.interface_name.casefold().strip() == wanted_name)
        )

    def api_surfaces_for_transition(self, transition_id: str) -> tuple[ApiSurface, ...]:
        """Return typed API boundaries attached to one modeled transition."""
        if transition_id not in {
            transition.id for machine in self.state_machines for transition in machine.transitions
        }:
            raise ValueError(f"unknown transition {transition_id}")
        return tuple(item for item in self.api_surfaces if transition_id in item.transition_ids)

    def api_crosswalks_for_mapping(self, mapping_id: str) -> tuple[ApiCrosswalk, ...]:
        """Return binding and projection rows for one implementation mapping."""
        if mapping_id not in {item.id for item in self.implementations}:
            raise ValueError(f"unknown implementation mapping {mapping_id}")
        return tuple(
            item for item in self.api_crosswalks if item.implementation_mapping_id == mapping_id
        )

    def api_crosswalks_for_target(self, target: str) -> tuple[ApiCrosswalk, ...]:
        """Return crosswalk rows for a named language, protocol, or transport target."""
        return tuple(item for item in self.api_crosswalks if item.target == target)

    def api_crosswalk_gaps(self, target: str | None = None) -> tuple[ApiCrosswalk, ...]:
        """Return unmatched or still-planned binding projections."""
        rows = self.api_crosswalks_for_target(target) if target is not None else self.api_crosswalks
        return tuple(item for item in rows if item.status in {"unmatched", "planned"})

    def api_bindings_for_requirement(
        self,
        requirement_id: str,
        *,
        language: str | None = None,
    ) -> tuple[RequirementApiBinding, ...]:
        """Return Java/C++ traceability rows for one requirement."""
        if requirement_id not in {item.id for item in self.requirements}:
            raise ValueError(f"unknown requirement {requirement_id}")
        return tuple(
            item
            for item in self.requirement_api_bindings
            if item.requirement_id == requirement_id
            and (language is None or item.language == language)
        )

    def api_bindings_for_surface(self, api_surface_id: str) -> tuple[RequirementApiBinding, ...]:
        """Return requirements mapped to one API declaration surface."""
        if api_surface_id not in {item.id for item in self.api_surfaces}:
            raise ValueError(f"unknown API surface {api_surface_id}")
        return tuple(
            item
            for item in self.requirement_api_bindings
            if api_surface_id in item.candidate_api_surface_ids
        )

    def api_binding_gaps(self) -> tuple[RequirementApiBinding, ...]:
        """Return ambiguous or unresolved requirement-to-API relationships."""
        return tuple(
            item
            for item in self.requirement_api_bindings
            if item.status in {"candidate", "ambiguous", "unmatched"}
        )

    def verification_tests_for_requirement(
        self, requirement_id: str
    ) -> tuple[VerificationTest, ...]:
        """Return verification slots that cover one requirement."""
        if requirement_id not in {item.id for item in self.requirements}:
            raise ValueError(f"unknown requirement {requirement_id}")
        return tuple(
            item for item in self.verification_tests if requirement_id in item.requirement_ids
        )

    def state_traces_for_machine(self, machine_id: str) -> tuple[StateTrace, ...]:
        """Return trace scenarios owned by one state machine."""
        if machine_id not in {item.id for item in self.state_machines}:
            raise ValueError(f"unknown state machine {machine_id}")
        return tuple(item for item in self.state_traces if item.machine_id == machine_id)

    def implementation_coverage_for_transition(
        self,
        transition_id: str,
        machine_id: str | None = None,
    ) -> TransitionImplementationCoverage:
        """Return the effective mapping status for one transition."""
        machines = self._selected_machines(machine_id)
        selected = tuple(
            (machine, transition)
            for machine in machines
            for transition in machine.transitions
            if transition.id == transition_id
        )
        if not selected:
            raise ValueError(f"unknown transition {transition_id}")
        machine, transition = selected[0]
        mappings = self.implementation_mappings_for_transition(transition.id)
        statuses: tuple[ImplementationStatus, ...] = tuple(
            sorted({item.status for item in mappings})
        )
        status: TransitionCoverageStatus = (
            "unmapped" if not statuses else statuses[0] if len(statuses) == 1 else "mixed"
        )
        return TransitionImplementationCoverage(
            document_id=self.document_id,
            machine_id=machine.id,
            transition_id=transition.id,
            source_state=transition.source_state,
            target_state=transition.target_state,
            event=transition.event,
            mapping_ids=tuple(item.id for item in mappings),
            status=status,
            concrete=bool(mappings)
                     and all(item.status in {"implemented", "verified"} for item in mappings),
        )

    def implementation_status_counts(self, machine_id: str | None = None) -> dict[str, int]:
        """Count effective mapping statuses across selected transitions."""
        counts = {
            "unmapped": 0,
            "planned": 0,
            "partial": 0,
            "implemented": 0,
            "verified": 0,
            "mixed": 0,
        }
        machines = self._selected_machines(machine_id)
        for machine in machines:
            for transition in machine.transitions:
                status = self.implementation_coverage_for_transition(
                    transition.id, machine.id
                ).status
                counts[status] += 1
        return counts

    def implementation_evidence(
        self,
        *,
        status: Literal["planned", "partial", "implemented", "verified"] | None = None,
        concrete: bool | None = None,
    ) -> tuple[ImplementationEvidence, ...]:
        """Return implementation mappings with explicit maturity evidence."""
        evidence = tuple(
            ImplementationEvidence(
                document_id=self.document_id,
                mapping_id=item.id,
                interface_kind=item.interface_kind,
                interface_name=item.interface_name,
                implementation=item.implementation,
                status=item.status,
                concrete=item.status in {"implemented", "verified"},
                source_backed=bool(
                    item.implementation_ref
                    and (
                        item.implementation_ref.repository
                        or item.implementation_ref.path
                        or item.implementation_ref.line
                    )
                ),
                clause_ids=item.clause_ids,
                requirement_ids=item.requirement_ids,
                transition_ids=item.transition_ids,
                implementation_ref=item.implementation_ref,
                source=item.source,
            )
            for item in self.implementations
            if status is None or item.status == status
            if concrete is None or (item.status in {"implemented", "verified"}) == concrete
        )
        return tuple(sorted(evidence, key=lambda item: item.mapping_id))

    def state_sequence_implications(
        self,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        sequence_diagram_id: str | None = None,
        include_unlinked: bool = True,
    ) -> tuple[OperationalImplication, ...]:
        """Project state transitions and sequence messages into one query surface.

        Sequence diagrams currently carry clause ownership but not invented
        transition links.  When a state/event filter is supplied, messages in
        the same clause are returned as ``clause-context`` implications; all
        other messages remain visible as ``unlinked`` when requested.
        """
        if (state_id is None) != (event is None):
            raise ValueError("state_id and event must be supplied together")
        event_text = event or ""
        machines = self._selected_machines(machine_id)
        transitions = tuple(
            (machine, transition)
            for machine in machines
            for transition in machine.transitions
            if state_id is None
            or (
                transition.source_state == state_id
                and transition.event.casefold().strip() == event_text.casefold().strip()
            )
        )
        if state_id is not None and not any(
            state_id in {state.id for state in machine.states} for machine in machines
        ):
            raise ValueError(f"unknown state {state_id}")
        diagrams = tuple(
            diagram
            for diagram in self.sequence_diagrams
            if sequence_diagram_id is None or diagram.id == sequence_diagram_id
        )
        if sequence_diagram_id is not None and not diagrams:
            raise ValueError(f"unknown sequence diagram {sequence_diagram_id}")
        by_clause: dict[str, tuple[SequenceDiagram, ...]] = {}
        for diagram in diagrams:
            if diagram.clause_id is not None:
                by_clause.setdefault(diagram.clause_id, ())
                by_clause[diagram.clause_id] += (diagram,)
        result: list[OperationalImplication] = []
        for machine, transition in transitions:
            related_diagrams = by_clause.get(transition.clause_id or "", ())
            result.append(
                OperationalImplication(
                    document_id=self.document_id,
                    kind="state-transition",
                    record_id=transition.id,
                    parent_id=machine.id,
                    label=transition.event or transition.id,
                    clause_id=transition.clause_id,
                    requirement_ids=transition.requirement_ids,
                    implementation_ids=transition.implementation_ids,
                    source_state=transition.source_state,
                    event=transition.event,
                    target_state=transition.target_state,
                    related_sequence_diagram_ids=tuple(diagram.id for diagram in related_diagrams),
                    relation="direct",
                    source=transition.source,
                )
            )
        for diagram in diagrams:
            related_transitions = tuple(
                transition
                for _, transition in transitions
                if diagram.clause_id is not None and transition.clause_id == diagram.clause_id
            )
            relation: Literal["direct", "clause-context", "unlinked"] = (
                "clause-context" if related_transitions else "unlinked"
            )
            if not include_unlinked and not related_transitions:
                continue
            mapping_ids = tuple(
                item.id
                for item in self.implementations
                if (diagram.clause_id and diagram.clause_id in item.clause_ids)
                or any(
                    requirement_id in item.requirement_ids
                    for message in diagram.messages
                    for requirement_id in message.requirement_ids
                )
            )
            for message in sorted(diagram.messages, key=lambda item: item.order):
                result.append(
                    OperationalImplication(
                        document_id=self.document_id,
                        kind="sequence-message",
                        record_id=message.id,
                        parent_id=diagram.id,
                        label=message.label,
                        clause_id=message.clause_id or diagram.clause_id,
                        requirement_ids=message.requirement_ids,
                        implementation_ids=mapping_ids,
                        sequence_diagram_id=diagram.id,
                        message_order=message.order,
                        response_to=message.response_to,
                        related_transition_ids=tuple(
                            transition.id for transition in related_transitions
                        ),
                        relation=relation,
                        source=message.source or diagram.source,
                    )
                )
        return tuple(result)

    def operational_implications(
        self,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        sequence_diagram_id: str | None = None,
        include_unlinked: bool = True,
    ) -> tuple[OperationalImplication, ...]:
        """Backward-compatible descriptive alias for state/sequence queries."""
        return self.state_sequence_implications(
            state_id,
            event,
            machine_id,
            sequence_diagram_id=sequence_diagram_id,
            include_unlinked=include_unlinked,
        )

    def compliance_query(
        self,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> ComplianceQueryResult:
        """Return a complete, serializable compliance query response."""
        if (state_id is None) != (event is None):
            raise ValueError("state_id and event must be supplied together")
        event_text = event or ""
        applicable = (
            self.query_requirements_applicable_after(
                state_id,
                event,
                machine_id,
                include_candidates=include_candidates,
            )
            if state_id is not None and event is not None
            else ()
        )
        machines = self._selected_machines(machine_id)
        coverage = tuple(
            self.implementation_coverage_for_transition(transition.id, machine.id)
            for machine in machines
            for transition in machine.transitions
            if state_id is None
            or (
                transition.source_state == state_id
                and transition.event.casefold().strip() == event_text.casefold().strip()
            )
        )
        issues = self.compliance_issues(
            machine_id,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )
        return ComplianceQueryResult(
            document_id=self.document_id,
            machine_id=machine_id,
            state_id=state_id,
            event=event,
            applicable_requirements=applicable,
            transition_coverage=coverage,
            implementation_status_counts=self.implementation_status_counts(machine_id),
            issues=issues,
        )

    def orphan_requirements(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
    ) -> tuple[Requirement, ...]:
        """Return transition-covered requirements without links or clause coverage."""
        machines = self._selected_machines(machine_id)
        linked_ids = {
            requirement_id
            for machine in machines
            for transition in machine.transitions
            for requirement_id in transition.requirement_ids
        }
        linked_ids.update(
            link.requirement_id
            for machine in machines
            for transition in machine.transitions
            for link in self.requirement_links
            if link.transition_id == transition.id
        )
        linked_ids.update(
            requirement_id
            for machine in machines
            for transition in machine.transitions
            for implementation in self.implementation_mappings_for_transition(transition.id)
            for requirement_id in implementation.requirement_ids
        )
        linked_clauses = {
            transition.clause_id
            for machine in machines
            for transition in machine.transitions
            if transition.clause_id is not None
        }
        return tuple(
            requirement
            for requirement in self.requirements
            if (include_candidates or requirement.extraction == "explicit")
            and requirement.coverage_kind == "transition"
            and requirement.id not in linked_ids
            and requirement.clause_id not in linked_clauses
        )

    def compliance_issues(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> tuple[ComplianceIssue, ...]:
        """Report non-fatal compliance coverage gaps for a selected machine set."""
        machines = self._selected_machines(machine_id)
        issues: list[ComplianceIssue] = []
        for requirement in self.orphan_requirements(
            machine_id,
            include_candidates=include_candidates,
        ):
            issues.append(
                ComplianceIssue(
                    code="orphan-requirement",
                    record_id=requirement.id,
                    message=(
                        "requirement is not linked to a transition in "
                        f"{machine_id or 'the selected machines'}"
                    ),
                )
            )
        for machine in machines:
            for transition in machine.transitions:
                coverage = self.implementation_coverage_for_transition(transition.id, machine.id)
                if coverage.status == "unmapped":
                    issues.append(
                        ComplianceIssue(
                            code="unmapped-transition",
                            record_id=transition.id,
                            message=f"transition has no implementation mapping in {machine.id}",
                        )
                    )
                elif require_concrete_implementation and not coverage.concrete:
                    issues.append(
                        ComplianceIssue(
                            code="non-concrete-implementation",
                            record_id=transition.id,
                            message=(
                                f"transition mapping is {coverage.status}, not implemented or "
                                f"verified, in {machine.id}"
                            ),
                        )
                    )
        for implementation in self.implementations:
            if not (
                implementation.clause_ids
                or implementation.requirement_ids
                or implementation.transition_ids
            ):
                issues.append(
                    ComplianceIssue(
                        code="orphan-implementation",
                        record_id=implementation.id,
                        message="implementation mapping has no semantic owner or usage link",
                    )
                )
        return tuple(issues)

    def assert_compliance(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> None:
        """Raise when selected compliance coverage contains any reported issue."""
        issues = self.compliance_issues(
            machine_id,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )
        if issues:
            raise ValueError("; ".join(f"{item.code}: {item.record_id}" for item in issues))

    def children_of(self, clause_id: str) -> tuple[Clause, ...]:
        """Return the immediate child clauses of a clause node."""
        order = {item_id: index for index, item_id in enumerate(self.clause_order)}
        return tuple(
            sorted(
                (item for item in self.clauses if item.parent_id == clause_id),
                key=lambda item: order[item.id],
            )
        )

    def clause_path(self, clause_id: str) -> tuple[Clause, ...]:
        """Return a clause and its ancestors, ordered from root to leaf."""
        by_id = {item.id: item for item in self.clauses}
        path: list[Clause] = []
        current = by_id.get(clause_id)
        while current is not None:
            path.append(current)
            current = by_id.get(current.parent_id) if current.parent_id else None
        return tuple(reversed(path))

    def search_definitions(self, query: str) -> tuple[Definition, ...]:
        """Find definitions whose terms contain the query text."""
        wanted = query.casefold().strip()
        return tuple(item for item in self.definitions if wanted in item.term.casefold())

    def match_requirements(self, text: str) -> tuple[RequirementMatch, ...]:
        """Rank requirements by the proportion of query terms in each statement."""
        query_terms = _tokens(text)
        if not query_terms:
            return ()
        matches: list[RequirementMatch] = []
        for requirement in self.requirements:
            statement_terms = _tokens(requirement.statement)
            matched = tuple(sorted(query_terms & statement_terms))
            if matched:
                matches.append(
                    RequirementMatch(
                        requirement=requirement,
                        score=len(matched) / len(query_terms),
                        matched_terms=matched,
                    )
                )
        return tuple(sorted(matches, key=lambda item: (-item.score, item.requirement.id)))

    def search_tables(self, query: str) -> tuple[Table, ...]:
        """Find tables whose captions contain the query text."""
        wanted = query.casefold().strip()
        return tuple(
            item for item in self.tables if wanted in (item.caption or item.title or "").casefold()
        )

    def references_for_clause(self, clause_id: str) -> tuple[Reference, ...]:
        return tuple(item for item in self.references if item.clause_id == clause_id)

    def notes_for(self, owner_id: str) -> tuple[Note, ...]:
        return tuple(item for item in self.notes if item.owner_id == owner_id)

    def figures_for_clause(self, clause_id: str) -> tuple[Figure, ...]:
        return tuple(item for item in self.figures if item.clause_id == clause_id)

    def merged_tables(self) -> tuple[Table, ...]:
        """Return logical tables with continued fragments merged by logical ID."""
        grouped: dict[str, list[Table]] = {}
        for table in self.tables:
            grouped.setdefault(table.logical_id or table.id, []).append(table)
        merged: list[Table] = []
        for logical_id, fragments in grouped.items():
            fragments.sort(key=lambda item: (item.source.path, item.source.line, item.id))
            first = fragments[0]
            cells = tuple(
                TableCell(
                    id=cell.id,
                    table_id=logical_id,
                    text=cell.text,
                    row=cell.row,
                    column=cell.column,
                    record_ids=cell.record_ids,
                    source=cell.source,
                )
                for fragment in fragments
                for cell in fragment.cells
            )
            merged.append(
                Table(
                    id=logical_id,
                    logical_id=logical_id,
                    title=first.title,
                    caption=first.caption,
                    number=first.number,
                    continuation=False,
                    cells=cells,
                    source=first.source,
                    domain=first.domain,
                    omt_kind=first.omt_kind,
                    family_id=first.family_id,
                )
            )
        return tuple(merged)

    def to_dict(self) -> JsonObject:
        """Return a JSON-compatible representation for downstream tools."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, payload: Mapping[str, JsonValue]) -> DocumentModel:
        """Validate and load a serialized semantic model mapping."""
        return cls.model_validate(payload)

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the model using Pydantic's JSON encoder."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, payload: str | bytes | bytearray) -> DocumentModel:
        """Validate and load a serialized semantic model document."""
        return cls.model_validate_json(payload)

class ComplianceCorpus(SemanticRecord):
    """A collection of documents used to resolve cross-document targets."""

    documents: tuple[DocumentModel, ...]

    @model_validator(mode="after")
    def validate_document_ids(self) -> ComplianceCorpus:
        document_ids = [item.document_id for item in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document IDs must be unique in a compliance corpus")
        return self

    def document(self, document_id: str) -> DocumentModel:
        """Return one document by stable corpus ID."""
        document = next(
            (item for item in self.documents if item.document_id == document_id),
            None,
        )
        if document is None:
            raise ValueError(f"unknown document {document_id}")
        return document

    def _selected_documents(self, document_id: str | None = None) -> tuple[DocumentModel, ...]:
        """Return either the requested document or the complete corpus."""
        return (self.document(document_id),) if document_id is not None else self.documents

    def compliance_query(
        self,
        document_id: str,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> ComplianceQueryResult:
        """Run the generic compliance query against one corpus document."""
        return self.document(document_id).compliance_query(
            state_id,
            event,
            machine_id,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )

    def requirements_applicable_after(
        self,
        state_id: str,
        event: str,
        document_id: str | None = None,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
    ) -> tuple[RequirementApplicability, ...]:
        """Query state/event requirements across one or every corpus document."""
        result: list[RequirementApplicability] = []
        for document in self._selected_documents(document_id):
            if not document.state_machines:
                if document_id is not None:
                    raise ValueError(f"document {document.document_id} has no state machines")
                continue
            result.extend(
                document.query_requirements_applicable_after(
                    state_id,
                    event,
                    machine_id,
                    include_candidates=include_candidates,
                )
            )
        return tuple(result)

    def state_sequence_implications(
        self,
        document_id: str | None = None,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        sequence_diagram_id: str | None = None,
        include_unlinked: bool = True,
    ) -> tuple[OperationalImplication, ...]:
        """Query state and sequence implications with document-qualified results."""
        result: list[OperationalImplication] = []
        for document in self._selected_documents(document_id):
            if state_id is not None and not document.state_machines:
                if document_id is not None:
                    raise ValueError(f"document {document.document_id} has no state machines")
                continue
            result.extend(
                document.state_sequence_implications(
                    state_id,
                    event,
                    machine_id,
                    sequence_diagram_id=sequence_diagram_id,
                    include_unlinked=include_unlinked,
                )
            )
        return tuple(result)

    def semantic_dependencies(
        self,
        document_id: str | None = None,
        record_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return qualified dependency edges across the selected documents."""
        edges = [
            edge
            for document in self._selected_documents(document_id)
            for edge in document.semantic_dependencies(record_id)
        ]
        return tuple(sorted({edge.id: edge for edge in edges}.values(), key=lambda item: item.id))

    def dependencies_for_record(
        self,
        record_id: str,
        document_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return dependency edges touching a record, qualified by document."""
        return self.semantic_dependencies(document_id, record_id)

    def table_definition_dependencies(
        self,
        document_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return table/family/cell and definition dependency edges."""
        interesting = {"table", "table-family", "table-cell", "definition"}
        return tuple(
            edge
            for edge in self.semantic_dependencies(document_id)
            if edge.source_kind in interesting or edge.target_kind in interesting
        )

    def transitions_without_implementation_mappings(
        self,
        document_id: str | None = None,
        machine_id: str | None = None,
    ) -> tuple[TransitionImplementationCoverage, ...]:
        """Return qualified coverage records for transitions with no mapping."""
        result: list[TransitionImplementationCoverage] = []
        for document in self._selected_documents(document_id):
            selected_machine = machine_id if document_id is not None else None
            for transition in document.transitions_without_implementation_mapping(selected_machine):
                result.append(
                    document.implementation_coverage_for_transition(
                        transition.id,
                        selected_machine,
                    )
                )
        return tuple(result)

    def transitions_without_concrete_implementations(
        self,
        document_id: str | None = None,
        machine_id: str | None = None,
    ) -> tuple[TransitionImplementationCoverage, ...]:
        """Return qualified coverage records lacking implemented/verified evidence."""
        result: list[TransitionImplementationCoverage] = []
        for document in self._selected_documents(document_id):
            selected_machine = machine_id if document_id is not None else None
            for transition in document.transitions_without_concrete_implementation(
                selected_machine
            ):
                result.append(
                    document.implementation_coverage_for_transition(
                        transition.id,
                        selected_machine,
                    )
                )
        return tuple(result)

    def implementation_evidence(
        self,
        document_id: str | None = None,
        *,
        status: Literal["planned", "partial", "implemented", "verified"] | None = None,
        concrete: bool | None = None,
    ) -> tuple[ImplementationEvidence, ...]:
        """Return corpus-qualified planned, partial, implemented, or verified mappings."""
        evidence = tuple(
            item
            for document in self._selected_documents(document_id)
            for item in document.implementation_evidence(status=status, concrete=concrete)
        )
        return tuple(sorted(evidence, key=lambda item: (item.document_id, item.mapping_id)))

    def compliance_report(
        self,
        document_id: str | None = None,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
        dependency_record_id: str | None = None,
        include_unlinked_implications: bool = True,
    ) -> ComplianceCorpusReport:
        """Build the complete serializable M24 compliance-facing corpus report."""
        if (state_id is None) != (event is None):
            raise ValueError("state_id and event must be supplied together")
        selected = self._selected_documents(document_id)
        applicable = (
            self.requirements_applicable_after(
                state_id,
                event,
                document_id,
                machine_id,
                include_candidates=include_candidates,
            )
            if state_id is not None and event is not None
            else ()
        )
        implications = self.state_sequence_implications(
            document_id,
            state_id,
            event,
            machine_id,
            include_unlinked=include_unlinked_implications,
        )
        issues = self.compliance_issues(
            machine_id if document_id is not None else None,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )
        status_counts = {
            document.document_id: document.implementation_status_counts(
                machine_id if document_id is not None else None
            )
            for document in selected
        }
        implication_counts = {
            relation: sum(item.relation == relation for item in implications)
            for relation in ("direct", "clause-context", "unlinked")
        }
        table_definition_coverage = {
            document.document_id: document.table_definition_dependency_counts()
            for document in selected
        }
        return ComplianceCorpusReport(
            document_ids=tuple(document.document_id for document in selected),
            applicable_requirements=applicable,
            state_sequence_implications=implications,
            dependencies=self.semantic_dependencies(document_id, dependency_record_id),
            missing_implementation_mappings=self.transitions_without_implementation_mappings(
                document_id,
                machine_id,
            ),
            implementation_evidence=self.implementation_evidence(document_id),
            unresolved_references=self.unresolved_reference_issues(),
            issues=issues,
            implementation_status_counts=status_counts,
            operational_implication_counts=implication_counts,
            table_definition_coverage=table_definition_coverage,
        )

    def assert_compliance_surfaces_classified(self, document_id: str | None = None) -> None:
        """Raise unless operational surfaces are represented or explicitly unlinked."""
        selected = self._selected_documents(document_id)
        report = self.compliance_report(document_id)
        expected_messages = {
            message.id
            for document in selected
            for diagram in document.sequence_diagrams
            for message in diagram.messages
        }
        actual_messages = {
            item.record_id
            for item in report.state_sequence_implications
            if item.kind == "sequence-message"
        }
        if actual_messages != expected_messages:
            missing = sorted(expected_messages - actual_messages)
            extra = sorted(actual_messages - expected_messages)
            raise ValueError(
                f"sequence-message classification is incomplete (missing={missing}, extra={extra})"
            )
        for document in selected:
            expected_cells = sum(len(table.cells) for table in document.tables)
            observed = report.table_definition_coverage[document.document_id]["cells"]
            if observed != expected_cells:
                raise ValueError(
                    f"table-cell classification is incomplete for {document.document_id}: "
                    f"expected {expected_cells}, observed {observed}"
                )
        if report.unresolved_references:
            raise ValueError(
                "unresolved corpus references: "
                + ", ".join(item.record_id for item in report.unresolved_references)
            )

    def unresolved_reference_issues(self) -> tuple[ComplianceIssue, ...]:
        """Return unresolved external reference targets as typed issues."""
        documents = {item.document_id: item for item in self.documents}
        issues: list[ComplianceIssue] = []
        for document in self.documents:
            for reference in document.references:
                for target in reference.targets:
                    target_document = documents.get(target.document_id)
                    qualified = (
                        f"{document.document_id}:{reference.id}->"
                        f"{target.document_id}:{target.record_id}"
                    )
                    if target_document is None:
                        issues.append(
                            ComplianceIssue(
                                code="unresolved-reference",
                                severity="error",
                                record_id=qualified,
                                message=(
                                    f"reference target document does not exist: "
                                    f"{target.document_id}"
                                ),
                            )
                        )
                    elif target.record_id not in target_document.semantic_record_ids():
                        issues.append(
                            ComplianceIssue(
                                code="unresolved-reference",
                                severity="error",
                                record_id=qualified,
                                message=(
                                    f"reference target record does not exist in "
                                    f"{target.document_id}: {target.record_id}"
                                ),
                            )
                        )
            for cross_reference in document.cross_references:
                target_document = documents.get(cross_reference.target_document_id)
                qualified = (
                    f"{document.document_id}:{cross_reference.owner_id}->"
                    f"{cross_reference.target_document_id}:{cross_reference.target_record_id}"
                )
                if target_document is None:
                    issues.append(
                        ComplianceIssue(
                            code="unresolved-reference",
                            severity="error",
                            record_id=qualified,
                            message=(
                                f"cross-reference target document does not exist: "
                                f"{cross_reference.target_document_id}"
                            ),
                        )
                    )
                elif cross_reference.target_record_id not in target_document.semantic_record_ids():
                    issues.append(
                        ComplianceIssue(
                            code="unresolved-reference",
                            severity="error",
                            record_id=qualified,
                            message=(
                                f"cross-reference target record does not exist in "
                                f"{cross_reference.target_document_id}: "
                                f"{cross_reference.target_record_id}"
                            ),
                        )
                    )
        return tuple(issues)

    def compliance_issues(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> tuple[ComplianceIssue, ...]:
        """Return document coverage findings plus cross-document failures."""
        issues = []
        for document in self.documents:
            selected_machine = (
                machine_id
                if machine_id in {machine.id for machine in document.state_machines}
                else None
            )
            issues.extend(
                document.compliance_issues(
                    selected_machine,
                    include_candidates=include_candidates,
                    require_concrete_implementation=require_concrete_implementation,
                )
            )
        issues.extend(self.unresolved_reference_issues())
        return tuple(issues)

    def assert_compliance(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> None:
        """Raise when any document or cross-document compliance issue exists."""
        issues = self.compliance_issues(
            machine_id,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )
        if issues:
            raise ValueError("; ".join(f"{item.code}: {item.record_id}" for item in issues))

    def assert_references_resolved(self) -> None:
        """Raise when a cross-document target cannot be resolved."""
        issues = self.unresolved_reference_issues()
        if issues:
            raise ValueError("; ".join(f"{item.code}: {item.record_id}" for item in issues))

def _arguments(text: str, start: int, count: int) -> tuple[tuple[str, ...], int] | None:
    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if cursor < len(text) and text[cursor] == "[":
        _, cursor = balanced_group(text, cursor, "[", "]")
    values: list[str] = []
    for _ in range(count):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            return None
        value, cursor = balanced_group(text, cursor)
        values.append(value)
    return tuple(values), cursor

def _commands(text: str, name: str, count: int) -> list[tuple[int, tuple[str, ...]]]:
    return [(offset, args) for offset, args, _ in _command_events(text, name, count)]

def _command_events(text: str, name: str, count: int) -> list[tuple[int, tuple[str, ...], int]]:
    pattern = re.compile(rf"\\{re.escape(name)}\b")
    found: list[tuple[int, tuple[str, ...], int]] = []
    for match in pattern.finditer(text):
        parsed = _arguments(text, match.end(), count)
        if parsed is not None:
            found.append((match.start(), parsed[0], parsed[1]))
    return found

def _environments(text: str, name: str, count: int) -> list[tuple[int, tuple[str, ...], int]]:
    pattern = re.compile(rf"\\begin\{{{re.escape(name)}\}}")
    found: list[tuple[int, tuple[str, ...], int]] = []
    for match in pattern.finditer(text):
        parsed = _arguments(text, match.end(), count)
        if parsed is not None:
            found.append((match.start(), parsed[0], parsed[1]))
    return found

def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))

def _machine_statement(text: str, source: LatexSourceProfile | None = None) -> str:
    """Normalize a normative statement for machine-facing consumers."""
    normalized = _latex_text(text, source)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized

def _source(
    root: Path,
    path: Path,
    text: str,
    offset: int,
    end_offset: int | None = None,
) -> SourceRef:
    return SourceRef(
        path=path.relative_to(root).as_posix(),
        line=line_number(text, offset),
        end_line=(
            line_number(text, max(offset, end_offset - 1)) if end_offset is not None else None
        ),
    )

def _unwrap_commands(value: str, names: tuple[str, ...], count: int, body_index: int = 0) -> str:
    pattern = re.compile(rf"\\(?:{'|'.join(map(re.escape, names))})\b")
    replacements: list[tuple[int, int, str]] = []
    for match in pattern.finditer(value):
        parsed = _arguments(value, match.end(), count)
        if parsed is not None:
            replacements.append((match.start(), parsed[1], parsed[0][body_index]))
    for start, end, replacement in reversed(replacements):
        value = value[:start] + replacement + value[end:]
    return value

def _latex_text(value: str, source: LatexSourceProfile | None = None) -> str:
    value = re.sub(r"(?m)^\s*%.*$", "", value)
    value = value.replace("\\linebreak", " ").replace("\\par", " ")
    value = re.sub(r"\\(?:begin|end)\{[^{}]*\}", " ", value)
    value = re.sub(r"\\(?:addvspace|vspace|hspace)\*?\{[^{}]*\}", " ", value)
    value = re.sub(r"\\item\b", "; ", value)
    wrapper_names = (
        "textit",
        "textbf",
        "texttt",
        "emph",
        *(source.text_wrapper_commands if source is not None else ()),
    )
    note_names = source.text_note_commands if source is not None else ()
    wrapper_commands = "|".join(map(re.escape, wrapper_names))
    note_commands = "|".join(map(re.escape, note_names))
    for _ in range(6):
        previous = value
        value = _unwrap_commands(value, ("resizebox",), 3, 2)
        value = _unwrap_commands(value, ("mbox", "makebox", "hbox"), 1)
        value = _unwrap_commands(
            value,
            wrapper_names,
            1,
        )
        if value == previous:
            break
    value = re.sub(
        rf"\\(?:{wrapper_commands})\{{([^{{}}]*)\}}",
        r"\1",
        value,
    )
    if note_commands:
        value = re.sub(rf"\\(?:{note_commands})\{{([^{{}}]*)\}}", r"\1", value)
    value = re.sub(r"\\[a-zA-Z]+(?:\[[^]]*\])?", "", value)
    value = value.replace("{", "").replace("}", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def _definition_text(value: str, source: LatexSourceProfile | None = None) -> str:
    """Extract definition prose while excluding anchors and presentation notes."""
    if source is not None:
        note_commands = "|".join(
            map(
                re.escape,
                (source.definition_note_at, *source.definition_note_commands),
            )
        )
        value = re.split(
            rf"\\(?:{note_commands})\b",
            value,
            maxsplit=1,
        )[0]
        value = re.sub(
            rf"\\(?:{re.escape(source.definition_anchor)}|"
            rf"{re.escape(source.definition_term)})\{{[^{{}}]*\}}",
            "",
            value,
        )
    return _latex_text(value, source).lstrip(": ")

_INCLUDE_PATTERN = re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")

def _document_resources(root: Path) -> _DocumentResources:
    from hla_lab.paths import DocumentResources

    return DocumentResources(root)

def _files(root: Path) -> tuple[Path, ...]:
    """Return source files in document include order, with safe fallbacks.

    The build entry point is the authoritative physical source order. Files
    that are not reachable from ``main.tex`` are retained after the reachable
    sources in lexical order so standalone semantic fragments remain visible
    to extraction without becoming ownership hints.
    """
    excluded = {".trash", "build", "dist", "output"}
    all_files = tuple(
        path
        for path in root.rglob("*.tex")
        if not excluded.intersection(path.relative_to(root).parts)
    )
    by_relative = {path.relative_to(root).as_posix(): path for path in all_files}
    ordered: list[Path] = []
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.resolve()
        if resolved in visited or not path.is_file():
            return
        if excluded.intersection(path.relative_to(root).parts):
            return
        visited.add(resolved)
        ordered.append(path)
        text = path.read_text(encoding="utf-8")
        for match in _INCLUDE_PATTERN.finditer(text):
            include = match.group(1).strip()
            candidate = path.parent / include
            if candidate.suffix != ".tex":
                candidate = candidate.with_suffix(".tex")
            visit(candidate)

    main = _document_resources(root).main_tex
    if main.is_file():
        visit(main)
    ordered.extend(
        path for relative, path in sorted(by_relative.items()) if path.resolve() not in visited
    )
    return tuple(ordered)

def _source_order(root: Path) -> dict[str, int]:
    """Return source positions from the document include graph."""
    return {path.relative_to(root).as_posix(): index for index, path in enumerate(_files(root))}

def _source_key(
    item: SourceOrderedRecord,
    source_order: Mapping[str, int] | None = None,
) -> tuple[int, int, str]:
    """Sort records by include order, with a stable fallback for external data."""
    if source_order is not None:
        return (
            source_order.get(item.source.path, len(source_order)),
            item.source.line,
            item.id,
        )
    page = re.search(r"page-(\d+)", item.source.path)
    page_number = int(page.group(1)) if page else 0
    return page_number, item.source.line, item.id

def _clause_shape(identifier: str) -> tuple[str, str | None, int]:
    number = identifier.removeprefix("clause-")
    parts = number.split(".")
    parent = ".".join(parts[:-1]) if len(parts) > 1 else None
    return number, f"clause-{parent}" if parent else None, len(parts)

def _clause_sort_key(item: Clause) -> tuple[tuple[tuple[int, int | str], ...], int, str]:
    """Sort numeric clauses before annex-like identifiers, stably."""
    parts = re.findall(r"\d+|[A-Za-z]+", item.number)
    number_key = tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts)
    return number_key, item.level, item.id

def _source_ref(value: Mapping[str, JsonValue]) -> SourceRef | None:
    if not isinstance(value, Mapping):
        return None
    return SourceRef.model_validate(value)

@dataclass(frozen=True)
class _TableGridCell:
    x: float
    y: float
    width: float
    height: float

@dataclass(frozen=True)
class _TableCellCandidate:
    id: str
    table_id: str
    text: str
    x: float
    y: float
    width: float
    height: float
    source: SourceRef

def _table_number(caption: str) -> str | None:
    match = re.search(r"\bTable\s+(\d+)", caption, re.IGNORECASE)
    return match.group(1) if match else None

def _omt_kind(caption: str) -> str | None:
    value = caption.casefold()
    kinds = (
        "object model identification",
        "object class structure",
        "interaction class structure",
        "directed interaction",
        "attribute",
        "parameter",
        "dimension",
        "time representation",
        "user-supplied tag",
        "synchronization",
        "transportation type",
        "update rate",
        "switches",
        "basic data representation",
        "simple data type",
        "enumerated data type",
        "array data type",
        "fixed record data type",
        "variant record data type",
        "reference data type",
        "notes",
        "interface specification services usage",
        "fom and som module merge results",
    )
    return next((kind for kind in kinds if kind in value), None)

def _table_text(value: str) -> str:
    """Remove layout-only TeX wrappers while retaining cell text."""
    value = re.sub(r"(?m)^\s*%.*$", "", value)
    value = value.replace(r"\newline", " ").replace(r"\linebreak", " ")
    value = value.replace(r"\space{}", " ")
    value = re.sub(r"\\(?:hspace|vspace)\*?\{[^{}]*\}", "", value)
    for _ in range(6):
        previous = value
        value = re.sub(
            r"\\(?:mbox|textbf|textit|texttt|emph|textnormal|textsf|textrm)\{([^{}]*)\}",
            r"\1",
            value,
        )
        value = re.sub(r"\\resizebox\{[^{}]*\}\{[^{}]*\}\{([^{}]*)\}", r"\1", value)
        value = re.sub(r"\\makebox(?:\[[^]]*\]){1,2}\{([^{}]*)\}", r"\1", value)
        if value == previous:
            break
    value = re.sub(r"\\[a-zA-Z]+(?:\[[^]]*\])?", "", value)
    value = value.replace("{", "").replace("}", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()

@dataclass(frozen=True)
class _TableLayoutText:
    """A visible text primitive recovered from a faithful table layout."""

    offset: int
    text: str
    first: float
    second: float
    source: SourceRef

def _table_heading(value: str, source: LatexSourceProfile) -> tuple[str, str] | None:
    """Return a normalized table number/title from a visible layout primitive."""
    normalized = _table_text(value).replace("%", "").strip()
    match = re.search(
        r"\bTable\s+(?P<number>\d+)\s*(?:---|—|-)\s*(?P<title>.+)$",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group("number"), normalized

def _cluster_index(value: float, values: Sequence[float], tolerance: float) -> int:
    """Assign a coordinate to a stable ordered cluster."""
    centers: list[float] = []
    for candidate in sorted(values):
        if not centers or abs(candidate - centers[-1]) > tolerance:
            centers.append(candidate)
        else:
            centers[-1] = (centers[-1] + candidate) / 2
    return min(range(len(centers)), key=lambda index: abs(centers[index] - value))

def _load_layout_tables_from_file(
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> tuple[Table, ...]:
    """Recover tables that were faithfully drawn without semantic cell macros.

    Older HLA faithful pages use ``HLAFixedBlock`` for portrait tables and
    ``HLARotatedLine`` for landscape tables. Their coordinates remain layout
    data; the title, visible cell text, logical number, and source provenance
    become the reusable semantic projection.
    """
    primitives: list[tuple[int, str, tuple[str, ...]]] = []
    primitives.extend(
        (offset, "fixed", args)
        for offset, args, _end in _command_events(text, source.fixed_text_block, 7)
    )
    rotated_name = getattr(source, "table_text_line", "")
    if rotated_name:
        primitives.extend(
            (offset, "rotated", args)
            for offset, args, _end in _command_events(text, rotated_name, 5)
        )
    primitives.sort(key=lambda item: item[0])
    headings: list[tuple[int, str, str, str, SourceRef]] = []
    for offset, kind, args in primitives:
        value = args[-1]
        heading = _table_heading(value, source)
        if heading is None:
            continue
        number, title = heading
        headings.append((offset, kind, number, title, _source(root, path, text, offset)))
    if not headings:
        return ()

    tables: list[Table] = []
    for heading_index, (offset, kind, number, title, heading_source) in enumerate(headings):
        next_offset = (
            headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(text)
        )
        candidates: list[_TableLayoutText] = []
        for primitive_offset, primitive_kind, args in primitives:
            if primitive_kind != kind or not offset < primitive_offset < next_offset:
                continue
            value = _table_text(args[-1])
            if not value or _table_heading(value, source) is not None:
                continue
            if kind == "fixed":
                try:
                    font_size = float(args[4])
                except ValueError:
                    continue
                # Normal body prose uses 9.96pt. Table cells and headers are
                # 9pt or smaller; this keeps surrounding paragraph blocks out.
                if font_size > 9.2:
                    continue
                first, second = float(args[0]), float(args[1])
            else:
                first, second = float(args[0]), float(args[1])
            candidates.append(
                _TableLayoutText(
                    offset=primitive_offset,
                    text=value,
                    first=first,
                    second=second,
                    source=_source(root, path, text, primitive_offset),
                )
            )
        if not candidates:
            continue
        first_tolerance, second_tolerance = (4.0, 22.0) if kind == "fixed" else (3.0, 4.0)
        rows = [item.first for item in candidates]
        columns = [item.second for item in candidates]
        page_match = re.search(r"page-(\d+)", path.stem.casefold())
        page_label = page_match.group(1) if page_match else str(heading_source.line)
        table_id = f"table-{number}-p{page_label}"
        existing_ids = {item.id for item in tables}
        if table_id in existing_ids:
            table_id = f"{table_id}-f{heading_index + 1}"
        cells = tuple(
            TableCell(
                id=f"{table_id}.c{ordinal:04d}",
                table_id=table_id,
                text=item.text,
                row=_cluster_index(item.first, rows, first_tolerance),
                column=_cluster_index(item.second, columns, second_tolerance),
                source=item.source,
            )
            for ordinal, item in enumerate(candidates, 1)
        )
        domain: Literal["generic", "omt"] = "omt" if _omt_kind(title) else "generic"
        tables.append(
            Table(
                id=table_id,
                title=title,
                caption=title,
                number=number,
                continuation=False,
                cells=cells,
                source=heading_source,
                logical_id=f"table-{number}",
                domain=domain,
                omt_kind=_omt_kind(title),
            )
        )
    return tuple(tables)

def _table_position(
    candidate: _TableCellCandidate, grid: tuple[_TableGridCell, ...]
) -> tuple[int | None, int | None]:
    """Infer row/column from the layout grid without storing coordinates."""
    center_x = candidate.x + candidate.width / 2
    center_y = candidate.y + candidate.height / 2
    containing = [
        item
        for item in grid
        if item.x <= center_x <= item.x + item.width and item.y <= center_y <= item.y + item.height
    ]
    if not containing:
        return None, None
    target = min(
        containing,
        key=lambda item: (
            abs((item.x + item.width / 2) - center_x) + abs((item.y + item.height / 2) - center_y)
        ),
    )
    columns = sorted({item.x for item in grid})
    rows = sorted({item.y for item in grid})
    return rows.index(target.y), columns.index(target.x)

def _load_tables_from_file(
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> tuple[Table, ...]:
    """Extract semantic table captions/cells while ignoring layout geometry."""
    events: list[tuple[int, str, tuple[str, ...]]] = []
    for name, count, kind in (
            (source.stable_id, 1, "stable"),
            (source.table_grid_cell, 4, "grid"),
            (source.table_cell_text, 7, "cell"),
    ):
        events.extend((offset, kind, args) for offset, args in _commands(text, name, count))
    events.sort(key=lambda item: item[0])

    table_sources: dict[str, SourceRef] = {}
    grids: dict[str, list[_TableGridCell]] = {}
    candidates: dict[str, list[_TableCellCandidate]] = {}
    current_table: str | None = None
    current_cell: str | None = None

    table_pattern = re.compile(r"^(?P<table>.+\.t\d+)$")
    cell_pattern = re.compile(r"^(?P<table>.+\.t\d+)\.c\d+$")
    for offset, kind, args in events:
        if kind == "stable":
            identifier = args[0]
            table_match = table_pattern.match(identifier)
            cell_match = cell_pattern.match(identifier)
            if table_match:
                table_id = table_match.group("table")
                if table_id is None:
                    continue
                current_table = table_id
                current_cell = None
                table_sources.setdefault(table_id, _source(root, path, text, offset))
            elif cell_match:
                table_id = cell_match.group("table")
                if table_id is None:
                    continue
                current_table = table_id
                current_cell = identifier
            continue
        table_key = current_table
        if table_key is None:
            continue
        if kind == "grid":
            grids.setdefault(table_key, []).append(
                _TableGridCell(*(float(value) for value in args))
            )
        elif kind == "cell":
            if current_cell is None:
                continue
            candidates.setdefault(table_key, []).append(
                _TableCellCandidate(
                    current_cell,
                    table_key,
                    _table_text(args[6]),
                    float(args[0]),
                    float(args[1]),
                    float(args[2]),
                    float(args[3]),
                    _source(root, path, text, offset),
                )
            )

    captions: list[tuple[str, float, float, float, SourceRef]] = []
    for offset, args in _commands(text, source.placed_block, 4):
        for caption_offset, caption_args in _commands(args[3], source.table_caption, 1):
            captions.append(
                (
                    _table_text(caption_args[0]),
                    float(args[0]),
                    float(args[1]),
                    float(args[2]),
                    _source(root, path, text, offset + caption_offset),
                )
            )

    labels: list[tuple[str, float, float, float, SourceRef]] = []
    heading_commands = source.table_heading_commands
    for offset, args in _commands(text, source.placed_block, 4):
        for name, count, title_index in heading_commands:
            for label_offset, label_args in _commands(args[3], name, count):
                labels.append(
                    (
                        _table_text(label_args[title_index]),
                        float(args[0]),
                        float(args[1]),
                        float(args[2]),
                        _source(root, path, text, offset + label_offset),
                    )
                )

    caption_by_table: dict[str, tuple[str, SourceRef]] = {}
    table_layout: list[tuple[str, float, float, float, float]] = []
    for table_id, grid in grids.items():
        if not grid:
            continue
        left = min(item.x for item in grid)
        top = min(item.y for item in grid)
        right = max(item.x + item.width for item in grid)
        bottom = max(item.y + item.height for item in grid)
        table_layout.append((table_id, left, top, right, bottom))
    for caption, x, y, width, source_ref in captions:
        if not table_layout:
            continue
        caption_x = float(x)
        caption_y = float(y)
        caption_right = caption_x + width
        following = [item for item in table_layout if item[2] >= caption_y]
        candidates_for_caption = following or table_layout
        table_id = min(
            candidates_for_caption,
            key=lambda item: (
                abs(item[2] - caption_y),
                abs(item[1] - caption_x) + abs(item[3] - caption_right),
            ),
        )[0]
        caption_by_table[table_id] = (caption, source_ref)

    title_by_table: dict[str, tuple[str, SourceRef]] = {}
    for table_id, left, top, right, _ in table_layout:
        preceding = [
            label
            for label in labels
            if float(label[2]) <= top
               and float(label[1]) <= right
               and float(label[1]) + float(label[3]) >= left
        ]
        if preceding:
            label = max(preceding, key=lambda item: float(item[2]))
            title_by_table[table_id] = (label[0], label[4])

    tables: list[Table] = []
    table_domain = source.table_domain
    for table_id in sorted(table_sources):
        caption_info = caption_by_table.get(table_id)
        title_info = title_by_table.get(table_id)
        caption = caption_info[0] if caption_info else None
        title = title_info[0] if title_info else None
        table_source = (
            caption_info[1]
            if caption_info
            else title_info[1]
            if title_info
            else table_sources[table_id]
        )
        cells = tuple(
            TableCell(
                id=candidate.id,
                table_id=table_id,
                text=candidate.text,
                row=_table_position(candidate, tuple(grids.get(table_id, ())))[0],
                column=_table_position(candidate, tuple(grids.get(table_id, ())))[1],
                source=candidate.source,
            )
            for candidate in candidates.get(table_id, ())
        )
        tables.append(
            Table(
                id=table_id,
                title=title,
                caption=caption,
                number=_table_number(caption or title or ""),
                continuation="continued" in (caption or "").casefold(),
                cells=tuple(sorted(cells, key=lambda item: item.id)),
                source=table_source,
                logical_id=(
                    f"table-{_table_number(caption or title or '')}"
                    if _table_number(caption or title or "")
                    else table_id
                ),
                domain=table_domain,
                omt_kind=(_omt_kind(caption or title or "") if table_domain == "omt" else None),
            )
        )
    if tables:
        return tuple(tables)
    return _load_layout_tables_from_file(root, path, text, source)

def _authored_layout_units(
    root: Path,
) -> tuple[tuple[Path, str], ...]:
    """Return reachable source plus semantic layout bodies exactly once.

    Page adapters are intentionally empty of visible prose.  Their Pydantic
    ``ContentBlock`` records retain the fidelity layout body, so semantic
    surface loaders must inspect that body rather than the adapter itself.
    """
    authored_blocks = _load_authored_content_blocks(root)
    authored_by_path = {
        item.source.path: item for item in authored_blocks if item.layout_body is not None
    }
    adapter_paths = {
        path
        for path in authored_by_path
        if (root / path).is_file()
           and "\\input{output/semantic/content-block-" in (root / path).read_text(encoding="utf-8")
    }
    units: list[tuple[Path, str]] = []
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        if relative in adapter_paths:
            continue
        units.append((path, path.read_text(encoding="utf-8")))
    units.extend(
        (root / item.source.path, item.layout_body)
        for item in authored_blocks
        if item.layout_body is not None
    )
    seen_units: set[tuple[str, str]] = set()
    result: list[tuple[Path, str]] = []
    for path, text in units:
        unit_key = (path.relative_to(root).as_posix(), text)
        if unit_key in seen_units:
            continue
        seen_units.add(unit_key)
        result.append((path, text))
    return tuple(result)

def _load_tables(root: Path, source: LatexSourceProfile) -> tuple[Table, ...]:
    tables: list[Table] = []
    for path, text in _authored_layout_units(root):
        tables.extend(_load_tables_from_file(root, path, text, source))
    ordered = sorted(tables, key=lambda item: (item.source.path, item.source.line, item.id))
    previous_by_logical_id: dict[str, Table] = {}
    normalized: list[Table] = []
    for table in ordered:
        previous = previous_by_logical_id.get(table.logical_id or table.id)
        continued = table.continuation or previous is not None
        normalized.append(
            table.model_copy(
                update={
                    "continuation": continued,
                    "continued_from": previous.id
                    if continued and previous is not None
                    else table.continued_from,
                }
            )
        )
        previous_by_logical_id[table.logical_id or table.id] = normalized[-1]
    return tuple(normalized)

def _derive_table_families(
    document_id: str,
    tables: Iterable[Table],
    authored_families: Iterable[TableFamily],
    content_blocks: Iterable[ContentBlock],
) -> tuple[TableFamily, ...]:
    """Complete table-family projections for layout-only table surfaces."""
    families = list(authored_families)
    assigned = {table_id for family in families for table_id in family.table_ids}
    grouped: dict[str, list[Table]] = {}
    for table in tables:
        if table.id in assigned:
            continue
        grouped.setdefault(table.logical_id or table.id, []).append(table)
    block_clause_by_path = {
        block.source.path.replace("\\", "/"): block.clause_id
        for block in content_blocks
        if block.clause_id is not None
    }
    used_ids = {family.id for family in families}
    for logical_id, fragments in sorted(grouped.items()):
        slug = re.sub(r"[^a-z0-9]+", "-", logical_id.casefold()).strip("-")
        family_id = f"table-family-{slug}"
        if family_id in used_ids:
            family_id = f"{family_id}-{document_id}"
        used_ids.add(family_id)
        first = fragments[0]
        source_path = first.source.path.replace("\\", "/")
        families.append(
            TableFamily(
                id=family_id,
                title=first.title or first.caption or logical_id,
                table_ids=tuple(item.id for item in fragments),
                clause_id=block_clause_by_path.get(source_path),
                source=first.source,
            )
        )
    return tuple(
        sorted(
            families,
            key=lambda item: (item.source.path, item.source.line, item.id),
        )
    )

def _table_definition_key(value: str) -> str:
    """Normalize a table label for exact definition-term matching."""
    value = re.sub(r"\\[a-zA-Z]+(?:\{[^{}]*\})?", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())

def _link_table_cells_to_definitions(
    tables: Iterable[Table],
    definitions: Iterable[Definition],
) -> tuple[Table, ...]:
    """Attach only exact, source-visible definition-term matches to cells.

    This deliberately avoids substring matching: a cell containing prose
    about a federate should not acquire a dependency merely because
    ``federate`` is a defined term.  Exact normalized labels are the
    source-supported dependency boundary; unresolved cells remain queryable
    through their table/family ownership edges.
    """
    candidates: dict[str, list[str]] = {}
    for definition in definitions:
        key = _table_definition_key(definition.term)
        if len(key) < 6:
            continue
        candidates.setdefault(key, []).append(definition.id)
    unique_terms = {key: values[0] for key, values in candidates.items() if len(values) == 1}
    linked: list[Table] = []
    for table in tables:
        cells: list[TableCell] = []
        for cell in table.cells:
            definition_id = unique_terms.get(_table_definition_key(cell.text))
            record_ids = list(cell.record_ids)
            if definition_id is not None and definition_id not in record_ids:
                record_ids.append(definition_id)
            cells.append(cell.model_copy(update={"record_ids": tuple(record_ids)}))
        linked.append(table.model_copy(update={"cells": tuple(cells)}))
    return tuple(linked)

def _record_id(prefix: str, root: Path, path: Path, text: str, offset: int, ordinal: int) -> str:
    relative = path.relative_to(root).with_suffix("").as_posix()
    slug = re.sub(r"[^a-z0-9]+", "-", relative.casefold()).strip("-")
    return f"{prefix}-{slug}-l{line_number(text, offset)}-{ordinal}"

def _heading_parts(args: tuple[str, ...], source: LatexSourceProfile) -> tuple[str, str] | None:
    """Return a normalized clause ID and title from either heading shape."""
    if not args:
        return None
    if len(args) >= 2 and args[0].strip().startswith("clause-"):
        return args[0].strip(), _latex_text(args[1], source)
    last_argument = next(iter(reversed(args)), None)
    if last_argument is None:
        return None
    value = _latex_text(last_argument, source)
    direct_match = re.match(
        r"(?P<number>[A-Za-z](?:\.\d+)*|\d+(?:\.\d+)*)\.\s+(?P<title>.+)",
        value,
    )
    if direct_match:
        number = direct_match.group("number")
        return f"clause-{number}", value.strip()
    match = re.match(r"(?P<number>[A-Za-z](?:\.\d+)*|\d+(?:\.\d+)*)\s*(?P<title>.*)", value)
    if not match:
        return None
    number = match.group("number")
    title = match.group("title").strip() or value
    return f"clause-{number}", title

def _hierarchy_headings(
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> tuple[tuple[int, str, str, SourceRef], ...]:
    events: dict[int, tuple[int, str, str, SourceRef]] = {}

    for name in source.clause_headings:
        for offset, args, end_offset in _command_events(text, name, 2):
            parts = _heading_parts(args, source)
            if parts is None:
                continue
            identifier, title = parts
            events[offset] = (
                offset,
                identifier,
                title,
                _source(root, path, text, offset, end_offset),
            )
        for offset, args, end_offset in _command_events(text, name, 1):
            if offset in events:
                continue
            parts = _heading_parts(args, source)
            if parts is None:
                continue
            identifier, title = parts
            events[offset] = (
                offset,
                identifier,
                title,
                _source(root, path, text, offset, end_offset),
            )

    for name, count, title_index in source.hierarchy_heading_commands:
        for offset, args, end_offset in _command_events(text, name, count):
            if offset in events:
                continue
            parts = _heading_parts((args[title_index],), source)
            if parts is None:
                continue
            identifier, title = parts
            events[offset] = (
                offset,
                identifier,
                title,
                _source(root, path, text, offset, end_offset),
            )

    for name, identifier_index, title_index in source.hierarchy_id_commands:
        count = max(identifier_index, title_index) + 1
        for offset, args, end_offset in _command_events(text, name, count):
            number = args[identifier_index].strip()
            if not re.fullmatch(r"[A-Za-z](?:\.\d+)*|\d+(?:\.\d+)*", number):
                continue
            identifier = f"clause-{number}"
            title = f"{number} {_latex_text(args[title_index], source)}"
            events[offset] = (
                offset,
                identifier,
                title,
                _source(root, path, text, offset, end_offset),
            )

    for offset, args, end_offset in _command_events(text, source.fixed_text_block, 7):
        raw_value = args[-1]
        if r"\textbf" not in raw_value:
            continue
        value = _latex_text(raw_value, source).replace("%", "").strip()
        match = re.match(
            r"(?P<number>[A-Za-z](?:\.\d+)*|\d+(?:\.\d+)*)\.\s+.+",
            value,
        )
        if not match:
            continue
        identifier = f"clause-{match.group('number')}"
        events.setdefault(
            offset,
            (
                offset,
                identifier,
                value,
                _source(root, path, text, offset, end_offset),
            ),
        )

    for offset, args, end_offset in _command_events(text, source.annex_heading, 1):
        value = _latex_text(args[0], source)
        match = re.fullmatch(r"Annex\s+([A-Za-z])", value)
        if not match or offset in events:
            continue
        identifier = f"clause-{match.group(1).upper()}"
        events[offset] = (
            offset,
            identifier,
            value,
            _source(root, path, text, offset, end_offset),
        )

    for offset, args, end_offset in _command_events(text, source.content_marker, 1):
        identifier = args[0].strip()
        if not identifier.startswith("clause-") or offset in events:
            continue
        number = identifier.removeprefix("clause-")
        events[offset] = (
            offset,
            identifier,
            f"Content marker {number}",
            _source(root, path, text, offset, end_offset),
        )

    return tuple(events[offset] for offset in sorted(events))

def _nearest_heading(
    headings: tuple[tuple[int, str, str, SourceRef], ...], offset: int
) -> str | None:
    prior = [item for item in headings if item[0] <= offset]
    return prior[-1][1] if prior else None

def _heading_context_by_file(
    root: Path, source: LatexSourceProfile
) -> dict[Path, tuple[tuple[int, str, str, SourceRef], ...]]:
    """Carry the last semantic heading across the document include order.

    A LaTeX page fragment is often included after its heading was declared in
    a neighboring fragment.  The include graph, rather than the fragment
    filename, is therefore the ownership boundary for semantic records.
    The synthetic ``-1`` entry keeps that context available to all event
    loaders without changing source offsets in the current fragment.
    """
    context: dict[Path, tuple[tuple[int, str, str, SourceRef], ...]] = {}
    prior: tuple[int, str, str, SourceRef] | None = None
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        local_events = list(_hierarchy_headings(root, path, text, source))
        for offset, args, end_offset in _command_events(text, source.pdf_bookmark, 2):
            bookmark = args[1]
            if not bookmark.startswith("bookmark:clause:"):
                continue
            identifier = f"clause-{bookmark.removeprefix('bookmark:clause:')}"
            local_events.append(
                (
                    offset,
                    identifier,
                    _latex_text(args[0], source),
                    _source(root, path, text, offset, end_offset),
                )
            )
        local = tuple(sorted(local_events, key=lambda item: item[0]))
        effective = ((-1, prior[1], prior[2], prior[3]), *local) if prior else local
        context[path] = tuple(effective)
        if local:
            prior = local[-1]
    return context

def _load_references(root: Path, source: LatexSourceProfile) -> tuple[Reference, ...]:
    records: list[Reference] = []
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path, text in _authored_layout_units(root):
        headings = tuple(
            sorted(
                (*heading_context.get(path, ()), *_hierarchy_headings(root, path, text, source)),
                key=lambda item: item[0],
            )
        )
        for _ordinal, (offset, args, end_offset) in enumerate(
            _command_events(text, source.bibliography_entry, 3), start=1
        ):
            records.append(
                Reference(
                    id=args[0],
                    label=_latex_text(args[1], source),
                    text=_latex_text(args[2], source),
                    kind="bibliographic",
                    clause_id=_nearest_heading(headings, offset),
                    source=_source(root, path, text, offset, end_offset),
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))

def _load_notes(root: Path, source: LatexSourceProfile) -> tuple[Note, ...]:
    records: list[Note] = []
    seen: set[tuple[str, int, int | None, NoteKind, str]] = set()
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path, text in _authored_layout_units(root):
        events: list[tuple[int, NoteKind, tuple[str, ...], int]] = []
        events.extend(
            (offset, "informative", args, end_offset)
            for offset, args, end_offset in _command_events(text, source.note_block, 1)
        )
        for name in source.definition_note_commands:
            events.extend(
                (offset, "definition", args, end_offset)
                for offset, args, end_offset in _command_events(text, name, 1)
            )
        events.extend(
            (offset, "definition", args, end_offset)
            for offset, args, end_offset in _command_events(text, source.definition_note_at, 3)
        )
        events.extend(
            (offset, "footnote", args, end_offset)
            for offset, args, end_offset in _command_events(text, source.footnote_text, 1)
        )
        for name in getattr(source, "additional_note_commands", ()):
            events.extend(
                (offset, "footnote", args, end_offset)
                for offset, args, end_offset in _command_events(text, name, 2)
            )
        headings = tuple(
            sorted(
                (*heading_context.get(path, ()), *_hierarchy_headings(root, path, text, source)),
                key=lambda item: item[0],
            )
        )
        for ordinal, (offset, kind, args, end_offset) in enumerate(sorted(events), start=1):
            payload = args[-1]
            note = Note(
                id=_record_id("note", root, path, text, offset, ordinal),
                text=_latex_text(payload, source),
                kind=kind,  # type: ignore[arg-type]
                owner_id=_nearest_heading(headings, offset),
                source=_source(root, path, text, offset, end_offset),
            )
            source_key = (
                note.source.path,
                note.source.line,
                note.source.end_line,
                note.kind,
                note.text,
            )
            if source_key in seen:
                continue
            seen.add(source_key)
            records.append(note)
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))

def _load_figures(root: Path, source: LatexSourceProfile) -> tuple[Figure, ...]:
    records: list[Figure] = []
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path, text in _authored_layout_units(root):
        images = _command_events(text, source.figure_image, 5)
        captions = _command_events(text, source.figure_caption, 3)
        anchors = _command_events(text, source.figure_anchor, 1)
        headings = tuple(
            sorted(
                (*heading_context.get(path, ()), *_hierarchy_headings(root, path, text, source)),
                key=lambda item: item[0],
            )
        )
        for index, (offset, image_args, end_offset) in enumerate(images):
            number = str(index + 1)
            prior_anchors = [item for item in anchors if item[0] <= offset]
            if prior_anchors:
                number = _latex_text(prior_anchors[-1][1][0], source)
            if index < len(captions):
                caption_offset, caption_args, _ = captions[index]
                number = _latex_text(caption_args[0], source)
                caption = _latex_text(caption_args[2], source)
                if caption_offset < offset:
                    caption = ""
            else:
                caption = ""
            records.append(
                Figure(
                    id=f"figure-{number}",
                    number=number,
                    caption=caption,
                    image=_latex_text(image_args[4], source),
                    clause_id=_nearest_heading(headings, offset),
                    source=_source(root, path, text, offset, end_offset),
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))

def _load_examples(root: Path, source: LatexSourceProfile) -> tuple[Example, ...]:
    records: list[Example] = []
    source_order = _source_order(root)
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        for _offset, identifier, title, heading_source in _hierarchy_headings(
            root, path, text, source
        ):
            if not title.casefold().endswith("example"):
                continue
            number = identifier.removeprefix("clause-")
            records.append(
                Example(
                    id=f"example-{number}",
                    number=number,
                    title=title,
                    clause_id=identifier,
                    source=heading_source,
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))

def _annex_status(value: str) -> AnnexStatus:
    normalized = value.casefold()
    if normalized == "normative":
        return "normative"
    if normalized == "informative":
        return "informative"
    return "unknown"

def _load_annexes(root: Path, source: LatexSourceProfile) -> tuple[Annex, ...]:
    records: dict[str, Annex] = {}
    source_order = _source_order(root)
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        headings = _command_events(text, source.annex_heading, 1)
        statuses = _command_events(text, source.annex_status, 1)
        titles = _command_events(text, source.annex_title, 1)
        for offset, heading_args, end_offset in headings:
            match = re.search(r"Annex\s+([A-Za-z])", _latex_text(heading_args[0], source))
            if not match:
                continue
            letter = match.group(1).upper()
            next_headings = [item[0] for item in headings if item[0] > offset]
            limit = min(next_headings) if next_headings else len(text)
            status = _annex_status(
                next(
                    (
                        _latex_text(item[1][0], source).strip("() ").casefold()
                        for item in statuses
                        if offset < item[0] < limit
                    ),
                    "unknown",
                )
            )
            title = next(
                (_latex_text(item[1][0], source) for item in titles if offset < item[0] < limit),
                f"Annex {letter}",
            )
            records.setdefault(
                f"annex-{letter.casefold()}",
                Annex(
                    id=f"annex-{letter.casefold()}",
                    letter=letter,
                    title=title,
                    status=status,
                    source=_source(root, path, text, offset, end_offset),
                ),
            )

        for offset, args, end_offset in _command_events(text, source.toc_line_at, 7):
            descriptor = _latex_text(args[4], source)
            match = re.match(
                r"Annex\s+([A-Za-z])\s+\((normative|informative)\)\s*(.*)",
                descriptor,
                re.IGNORECASE,
            )
            if not match:
                continue
            letter, status, title = match.groups()
            records.setdefault(
                f"annex-{letter.casefold()}",
                Annex(
                    id=f"annex-{letter.casefold()}",
                    letter=letter.upper(),
                    title=title.strip() or f"Annex {letter.upper()}",
                    status=_annex_status(status),
                    source=_source(root, path, text, offset, end_offset),
                ),
            )

        for offset, args, end_offset in _command_events(text, source.annex_bookmark, 1):
            descriptor = _latex_text(args[0], source)
            match = re.match(
                r"Annex\s+([A-Za-z])\s+\((normative|informative)\)\s*(.*)",
                descriptor,
                re.IGNORECASE,
            )
            if not match:
                continue
            letter, status, title = match.groups()
            records.setdefault(
                f"annex-{letter.casefold()}",
                Annex(
                    id=f"annex-{letter.casefold()}",
                    letter=letter.upper(),
                    title=title.strip() or f"Annex {letter.upper()}",
                    status=_annex_status(status),
                    source=_source(root, path, text, offset, end_offset),
                ),
            )

    navigation = _document_resources(root).canonical_file("source-navigation.json")
    if navigation.is_file():
        raw = json.loads(navigation.read_text(encoding="utf-8"))
        outline = raw.get("outline", []) if isinstance(raw, dict) else []
        navigation_source = SourceRef(path=navigation.relative_to(root).as_posix(), line=1)
        for entry in outline:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            descriptor = str(entry[1]).strip()
            match = re.match(
                r"Annex\s+([A-Za-z])\s+\((normative|informative)\)\s*(.*)",
                descriptor,
                re.IGNORECASE,
            )
            if not match:
                continue
            letter, status, title = match.groups()
            records.setdefault(
                f"annex-{letter.casefold()}",
                Annex(
                    id=f"annex-{letter.casefold()}",
                    letter=letter.upper(),
                    title=title.strip() or f"Annex {letter.upper()}",
                    status=_annex_status(status),
                    source=navigation_source,
                ),
            )
    return tuple(
        sorted(
            records.values(),
            key=lambda item: _source_key(item, source_order),
        )
    )

def _load_requirement_candidates(root: Path, source: LatexSourceProfile) -> tuple[Requirement, ...]:
    """Extract reviewable normative candidates from non-semantic page sources."""
    records: list[Requirement] = []
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    authored_blocks = _load_authored_content_blocks(root)
    authored_by_path = {
        item.source.path: item for item in authored_blocks if item.layout_body is not None
    }
    adapter_paths = {
        path
        for path in authored_by_path
        if (root / path).is_file()
           and "\\input{output/semantic/content-block-" in (root / path).read_text(encoding="utf-8")
    }
    units: list[tuple[Path, str, tuple[tuple[int, str, str, SourceRef], ...]]] = []
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        if "frontmatter" in relative or "generated" in relative:
            continue
        if relative in adapter_paths:
            continue
        text = path.read_text(encoding="utf-8")
        units.append((path, text, heading_context[path]))
    for block in authored_blocks:
        if block.layout_body is None:
            continue
        if "frontmatter" in block.source.path or "generated" in block.source.path:
            continue
        virtual_path = root / block.source.path
        local_headings = list(_hierarchy_headings(root, virtual_path, block.layout_body, source))
        if block.clause_id is not None and not any(
            item[1] == block.clause_id for item in local_headings
        ):
            local_headings.insert(
                0,
                (
                    -1,
                    block.clause_id,
                    block.clause_id.removeprefix("clause-"),
                    block.source,
                ),
            )
        units.append((virtual_path, block.layout_body, tuple(local_headings)))
    seen_units: set[tuple[str, str]] = set()
    for path, text, headings in units:
        relative = path.relative_to(root).as_posix()
        unit_key = (path.relative_to(root).as_posix(), text)
        if unit_key in seen_units:
            continue
        seen_units.add(unit_key)
        events: list[tuple[int, tuple[str, ...], int]] = []
        events.extend(_command_events(text, source.fixed_text_block, 7))
        events.extend(_command_events(text, source.clause_paragraph, 1))
        events.extend(_command_events(text, source.clause_labeled_item, 2))
        for ordinal, (offset, args, end_offset) in enumerate(sorted(events), start=1):
            body = args[-1]
            statement = _machine_statement(body, source)
            if not re.search(r"\bshall\b", statement, re.IGNORECASE):
                continue
            clause_id = _nearest_heading(headings, offset)
            clause = clause_id.removeprefix("clause-") if clause_id else None
            records.append(
                Requirement(
                    id=_record_id("requirement-candidate", root, path, text, offset, ordinal),
                    title=f"Normative candidate at {relative}:{line_number(text, offset)}",
                    statement=statement,
                    kind="detailed",
                    clause=clause,
                    machine_statement=statement,
                    extraction="candidate",
                    source=_source(root, path, text, offset, end_offset),
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))

def _load_state_machines(root: Path) -> tuple[StateMachine, ...]:
    semantic_root = _document_resources(root).semantic
    if not semantic_root.exists():
        return ()
    machines: list[StateMachine] = []
    for path in sorted(semantic_root.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "state_machines" not in raw:
            continue
        payload = StateMachineFile.model_validate(raw)
        machines.extend(payload.state_machines)
    return tuple(machines)

def _load_sequence_diagrams(root: Path) -> tuple[SequenceDiagram, ...]:
    """Load authored sequence diagrams from the semantic source directory."""
    semantic_root = _document_resources(root).semantic
    if not semantic_root.exists():
        return ()
    diagrams: list[SequenceDiagram] = []
    for path in sorted(semantic_root.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "sequence_diagrams" not in raw:
            continue
        payload = SequenceDiagramFile.model_validate(raw)
        diagrams.extend(payload.sequence_diagrams)
    return tuple(diagrams)

def _load_graph_diagrams(root: Path) -> tuple[GraphDiagram, ...]:
    """Load authored generic graph diagrams from the semantic source directory."""
    semantic_root = _document_resources(root).semantic
    if not semantic_root.exists():
        return ()
    diagrams: list[GraphDiagram] = []
    for path in sorted(semantic_root.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "graph_diagrams" not in raw:
            continue
        payload = GraphDiagramFile.model_validate(raw)
        diagrams.extend(payload.graph_diagrams)
    return tuple(diagrams)

def _load_diagram_surfaces(root: Path) -> tuple[DiagramSurface, ...]:
    """Load the explicit figure/artwork classification for this document."""
    path = _document_resources(root).semantic_file("diagram-surfaces.json")
    if not path.is_file():
        return ()
    payload = DiagramSurfaceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.surfaces

def _load_authored_definitions(root: Path) -> tuple[Definition, ...]:
    """Load definitions that have already migrated to semantic source."""
    path = _document_resources(root).semantic_file("definitions.json")
    if not path.is_file():
        return ()
    payload = DefinitionFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.definitions

def _load_authored_requirements(root: Path) -> tuple[Requirement, ...]:
    """Load reviewed requirements promoted from source-shaped candidates."""
    path = _document_resources(root).semantic_file("requirements.json")
    if not path.is_file():
        return ()
    payload = RequirementFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.requirements

def _load_authored_requirement_reviews(root: Path) -> tuple[RequirementReview, ...]:
    """Load explicit dispositions for candidate requirement records."""
    path = _document_resources(root).semantic_file("requirement-review.json")
    if not path.is_file():
        return ()
    payload = RequirementReviewFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.reviews

def _load_authored_requirement_links(root: Path) -> tuple[RequirementLink, ...]:
    """Load explicit requirement-to-transition relationships."""
    path = _document_resources(root).semantic_file("requirement-links.json")
    if not path.is_file():
        return ()
    payload = RequirementLinkFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.links

def _load_authored_transition_coverage(root: Path) -> tuple[TransitionCoverage, ...]:
    """Load explicit mapped, N/A, and deferred transition dispositions."""
    path = _document_resources(root).semantic_file("transition-coverage.json")
    if not path.is_file():
        return ()
    payload = TransitionCoverageFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.transition_coverage

def _load_authored_content_blocks(root: Path) -> tuple[ContentBlock, ...]:
    """Load prose blocks that have crossed into semantic source."""
    path = _document_resources(root).semantic_file("content-blocks.json")
    if not path.is_file():
        return ()
    payload = ContentBlockFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.content_blocks

def _load_authored_content_elements(root: Path) -> tuple[ContentElement, ...]:
    """Load typed content units that sit beneath page fidelity adapters."""
    path = _document_resources(root).semantic_file("content-elements.json")
    if not path.is_file():
        return ()
    payload = ContentElementFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.content_elements

def _load_authored_table_families(root: Path) -> tuple[TableFamily, ...]:
    """Load named table families that group parsed semantic table records."""
    path = _document_resources(root).semantic_file("table-families.json")
    if not path.is_file():
        return ()
    payload = TableFamilyFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.table_families

def _load_authored_implementations(
    root: Path,
) -> tuple[ImplementationMapping, ...]:
    """Load code-facing mappings authored outside hand-written LaTeX."""
    path = _document_resources(root).semantic_file("implementations.json")
    if not path.is_file():
        return ()
    payload = ImplementationFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.implementations

def _load_authored_api_surfaces(root: Path) -> tuple[ApiSurface, ...]:
    """Load directly authored API contracts when a source provides them."""
    path = _document_resources(root).semantic_file("api-surfaces.json")
    if not path.is_file():
        return ()
    payload = ApiSurfaceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.api_surfaces

def _load_authored_api_crosswalks(root: Path) -> tuple[ApiCrosswalk, ...]:
    """Load semantic-to-binding crosswalks when a profile supplies them."""
    path = _document_resources(root).semantic_file("api-crosswalk.json")
    if not path.is_file():
        return ()
    payload = ApiCrosswalkFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.api_crosswalks

def _load_authored_requirement_api_bindings(
    root: Path,
) -> tuple[RequirementApiBinding, ...]:
    """Load requirement-to-API traceability records when supplied."""
    path = _document_resources(root).semantic_file("api-requirement-bindings.json")
    if not path.is_file():
        return ()
    payload = RequirementApiBindingFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.bindings

def _load_authored_verification_tests(root: Path) -> tuple[VerificationTest, ...]:
    """Load verification plans/evidence records from semantic source."""
    path = _document_resources(root).semantic_file("verification-tests.json")
    if not path.is_file():
        return ()
    payload = VerificationTestFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.verification_tests

def _load_authored_state_traces(root: Path) -> tuple[StateTrace, ...]:
    """Load authored state-machine trace scenarios from semantic source."""
    path = _document_resources(root).semantic_file("state-traces.json")
    if not path.is_file():
        return ()
    payload = StateTraceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.state_traces

def _load_authored_references(root: Path) -> tuple[Reference, ...]:
    """Load references with resolved cross-document semantic targets."""
    path = _document_resources(root).semantic_file("references.json")
    if not path.is_file():
        return ()
    payload = ReferenceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.references

def _load_authored_cross_references(root: Path) -> tuple[CrossReference, ...]:
    """Load explicitly authored cross-reference records when present."""
    path = _document_resources(root).semantic_file("cross-references.json")
    if not path.is_file():
        return ()
    payload = CrossReferenceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.cross_references

def _load_authored_tables(root: Path) -> tuple[Table, ...]:
    """Load tables promoted from a legacy source adapter."""
    path = _document_resources(root).semantic_file("tables.json")
    if not path.is_file():
        return ()
    payload = TableFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.tables

def _load_authored_notes(root: Path) -> tuple[Note, ...]:
    """Load notes promoted from a legacy source adapter."""
    path = _document_resources(root).semantic_file("notes.json")
    if not path.is_file():
        return ()
    payload = NoteFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.notes

def _load_authored_figures(root: Path) -> tuple[Figure, ...]:
    """Load figures promoted from a legacy source adapter."""
    path = _document_resources(root).semantic_file("figures.json")
    if not path.is_file():
        return ()
    payload = FigureFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.figures

def _cross_reference_catalog(
    *,
    clauses: Iterable[Clause],
    definitions: Iterable[Definition],
    requirements: Iterable[Requirement],
    content_blocks: Iterable[ContentBlock],
    content_elements: Iterable[ContentElement],
    tables: Iterable[Table],
    table_families: Iterable[TableFamily],
    references: Iterable[Reference],
    notes: Iterable[Note],
    figures: Iterable[Figure],
    examples: Iterable[Example],
    annexes: Iterable[Annex],
    state_machines: Iterable[StateMachine],
    sequence_diagrams: Iterable[SequenceDiagram],
    graph_diagrams: Iterable[GraphDiagram],
    implementations: Iterable[ImplementationMapping],
    api_surfaces: Iterable[ApiSurface] = (),
    api_crosswalks: Iterable[ApiCrosswalk] = (),
    verification_tests: Iterable[VerificationTest] = (),
    state_traces: Iterable[StateTrace] = (),
) -> dict[str, tuple[CrossReferenceKind, str]]:
    """Build the local target label catalog used by typed cross-references."""
    catalog: dict[str, tuple[CrossReferenceKind, str]] = {}

    def add(record_id: str, kind: CrossReferenceKind, label: str) -> None:
        catalog.setdefault(record_id, (kind, label.strip() or record_id))

    for item in clauses:
        add(item.id, "clause", f"{item.number}. {item.title}")
    for item in definitions:
        add(item.id, "definition", item.term)
    for item in requirements:
        add(item.id, "requirement", item.title)
    for item in content_blocks:
        add(item.id, "content", item.text)
    for item in content_elements:
        add(item.id, "content", item.text)
    for item in tables:
        add(item.id, "table", item.caption or item.title or item.id)
        for cell in item.cells:
            add(cell.id, "content", cell.text)
    for item in table_families:
        add(item.id, "table-family", item.title)
    for item in references:
        add(item.id, "reference", f"{item.label} {item.text}".strip())
    for item in notes:
        add(item.id, "note", item.text)
    for item in figures:
        add(item.id, "figure", f"Figure {item.number} — {item.caption}".rstrip(" —"))
    for item in examples:
        add(item.id, "example", item.title)
    for item in annexes:
        add(item.id, "annex", item.title)
    for item in state_machines:
        add(item.id, "state-machine", item.title)
        for state in item.states:
            add(state.id, "state", state.label or state.id)
        for transition in item.transitions:
            add(transition.id, "transition", transition.event or transition.id)
    for item in sequence_diagrams:
        add(item.id, "sequence-diagram", item.id)
    for item in graph_diagrams:
        add(item.id, "graph-diagram", item.id)
    for item in implementations:
        add(item.id, "implementation", item.interface_name)
    for item in api_surfaces:
        add(item.id, "api-surface", item.name)
    for item in api_crosswalks:
        add(item.id, "api-crosswalk", f"{item.target} {item.status}")
    for item in verification_tests:
        add(item.id, "verification-test", item.title)
    for item in state_traces:
        add(item.id, "state-trace", item.title)
    return catalog

def _derive_cross_references(
    document_id: str,
    content_elements: tuple[ContentElement, ...],
    catalog: Mapping[str, tuple[CrossReferenceKind, str]],
    *,
    clauses: Iterable[Clause] = (),
    definitions: Iterable[Definition] = (),
    tables: Iterable[Table] = (),
    table_families: Iterable[TableFamily] = (),
    figures: Iterable[Figure] = (),
) -> tuple[tuple[ContentElement, ...], tuple[CrossReference, ...]]:
    """Turn explicit and visible source references into typed relationships."""
    clause_records = tuple(clauses)
    definition_records = tuple(definitions)
    table_records = tuple(tables)
    family_records = tuple(table_families)
    figure_records = tuple(figures)
    aliases: dict[tuple[str, str], tuple[str, CrossReferenceKind, str]] = {}
    for item in clause_records:
        aliases.setdefault(("clause", item.number), (item.id, "clause", item.title))
    for item in definition_records:
        aliases.setdefault(("definition", item.term.casefold()), (item.id, "definition", item.term))
    for item in figure_records:
        aliases.setdefault(("figure", item.number), (item.id, "figure", f"Figure {item.number}"))
    family_by_table = {
        table_id: family for family in family_records for table_id in family.table_ids
    }
    for item in sorted(
        table_records,
        key=lambda value: (value.source.path, value.source.line, value.id),
    ):
        if item.number is None:
            continue
        family = family_by_table.get(item.id)
        target = family or item
        kind: CrossReferenceKind = "table-family" if family is not None else "table"
        label = family.title if family is not None else item.caption or item.title or item.id
        aliases.setdefault(("table", item.number), (target.id, kind, label))

    def visible_targets(text: str) -> tuple[tuple[str, CrossReferenceKind, str], ...]:
        found: list[tuple[str, CrossReferenceKind, str]] = []
        for match in re.finditer(
            r"\b(?:see|shown\s+in|specified\s+in|described\s+in|summarized\s+in|defined\s+in)"
            r"\s+(?:Clause\s+)?(\d+(?:\.\d+)*)",
            text,
            re.IGNORECASE,
        ):
            target = aliases.get(("clause", match.group(1)))
            if target is not None:
                found.append(target)
        for match in re.finditer(r"\bTable\s+(\d+)\b", text, re.IGNORECASE):
            target = aliases.get(("table", match.group(1)))
            if target is not None:
                found.append(target)
        for match in re.finditer(r"\bFigure\s+(\d+)\b", text, re.IGNORECASE):
            target = aliases.get(("figure", match.group(1)))
            if target is not None:
                found.append(target)
        see_also = re.search(r"\bsee\s+also\s*:\s*(.+)$", text, re.IGNORECASE)
        if see_also:
            suffix = see_also.group(1)
            for definition in definition_records:
                if re.search(rf"\b{re.escape(definition.term)}\b", suffix, re.IGNORECASE):
                    found.append((definition.id, "definition", definition.term))
        deduplicated: list[tuple[str, CrossReferenceKind, str]] = []
        seen: set[str] = set()
        for target in found:
            if target[0] not in seen:
                seen.add(target[0])
                deduplicated.append(target)
        return tuple(deduplicated)

    normalized: list[ContentElement] = []
    cross_references: list[CrossReference] = []
    surface_cross_references: list[CrossReference] = []
    for element in content_elements:
        text = element.text
        explicit_targets: set[str] = set()
        for ordinal, target_id in enumerate(element.record_ids, 1):
            target = catalog.get(target_id)
            if target is None:
                continue
            kind, label = target
            explicit_targets.add(target_id)
            if element.kind == "cross-reference" and text.startswith("Semantic record "):
                text = label
            cross_references.append(
                CrossReference(
                    id=f"xref-{element.id}-{ordinal:03d}",
                    owner_id=element.id,
                    target_document_id=document_id,
                    target_record_id=target_id,
                    label=label,
                    kind=kind,
                    source=element.source,
                )
            )
        for target_id, kind, label in visible_targets(text):
            if target_id in explicit_targets:
                continue
            target_slug = slugify(target_id)
            surface_cross_references.append(
                CrossReference(
                    id=f"xref-{element.id}-surface-{target_slug}",
                    owner_id=element.id,
                    target_document_id=document_id,
                    target_record_id=target_id,
                    label=label,
                    kind=kind,
                    source=element.source,
                )
            )
        normalized.append(
            element.model_copy(update={"text": text}) if text != element.text else element
        )
    cross_references.extend(surface_cross_references)
    for definition in definition_records:
        for target_id, kind, label in visible_targets(definition.text):
            target_slug = slugify(target_id)
            cross_references.append(
                CrossReference(
                    id=f"xref-{definition.id}-surface-{target_slug}",
                    owner_id=definition.id,
                    target_document_id=document_id,
                    target_record_id=target_id,
                    label=label,
                    kind=kind,
                    source=definition.source,
                )
            )
    return tuple(normalized), tuple(cross_references)

def _load_navigation_clauses(root: Path) -> tuple[Clause, ...]:
    """Load clause labels from an existing canonical navigation manifest."""
    path = _document_resources(root).canonical_file("source-navigation.json")
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    outline = raw.get("outline", []) if isinstance(raw, dict) else []
    source = SourceRef(path=path.relative_to(root).as_posix(), line=1)
    clauses: dict[str, Clause] = {}
    for entry in outline:
        if isinstance(entry, dict):
            identifier = str(entry.get("id", "")).strip()
            if not identifier:
                continue
            try:
                clauses[identifier] = Clause(
                    id=identifier,
                    number=str(entry["number"]),
                    title=str(entry["title"]),
                    parent_id=entry.get("parent_id"),
                    level=int(entry["level"]),
                    source=SourceRef.model_validate(entry.get("source", source.model_dump())),
                )
            except (KeyError, TypeError, ValueError):
                continue
            continue
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        label = str(entry[1]).strip()
        annex = re.match(r"Annex\s+([A-H])\s+\((?:normative|informative)\).+", label)
        numbered = re.match(r"(?P<number>\d+(?:\.\d+)*)\.\s+.+", label)
        if annex:
            identifier = f"clause-{annex.group(1)}"
            number = annex.group(1)
        elif numbered:
            number = numbered.group("number")
            identifier = f"clause-{number}"
        else:
            continue
        clause_number, parent_id, level = _clause_shape(identifier)
        clauses[identifier] = Clause(
            id=identifier,
            number=clause_number,
            title=label,
            parent_id=parent_id,
            level=level,
            source=source,
        )
    return tuple(clauses.values())

def load_document_model(root: Path, source: LatexSourceProfile) -> DocumentModel:
    """Load typed semantic records from a document source tree."""
    clauses: dict[str, Clause] = {}
    definitions: dict[str, Definition] = {}
    requirements: dict[str, Requirement] = {}
    state_machines = _load_state_machines(root)
    sequence_diagrams = _load_sequence_diagrams(root)
    graph_diagrams = _load_graph_diagrams(root)
    diagram_surfaces = _load_diagram_surfaces(root)
    requirement_reviews = _load_authored_requirement_reviews(root)
    requirement_links = _load_authored_requirement_links(root)
    transition_coverage = _load_authored_transition_coverage(root)
    content_blocks = _load_authored_content_blocks(root)
    content_elements = _load_authored_content_elements(root)
    table_families = _load_authored_table_families(root)
    api_surfaces = _load_authored_api_surfaces(root)
    api_crosswalks = _load_authored_api_crosswalks(root)
    requirement_api_bindings = _load_authored_requirement_api_bindings(root)
    verification_tests = _load_authored_verification_tests(root)
    state_traces = _load_authored_state_traces(root)
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)

    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        headings: list[tuple[int, str, str, SourceRef]] = list(heading_context[path])
        for _, identifier, title, heading_source in headings:
            number, parent_id, level = _clause_shape(identifier)
            item = Clause(
                id=identifier,
                number=number,
                title=title,
                parent_id=parent_id,
                level=level,
                source=heading_source,
            )
            previous = clauses.get(identifier)
            if previous is None or previous.title.startswith("Content marker "):
                clauses[identifier] = item

        headings.sort(key=lambda item: item[0])

        for offset, args, body_start in _environments(text, source.definition_environment, 2):
            end_marker = text.find(rf"\end{{{source.definition_environment}}}", body_start)
            end_offset = (
                end_marker + len(rf"\end{{{source.definition_environment}}}")
                if end_marker >= 0
                else None
            )
            item = Definition(
                id=args[0],
                term=_latex_text(args[1], source),
                text="",
                clause_id=_nearest_heading(tuple(headings), offset),
                source=_source(root, path, text, offset, end_offset),
            )
            if end_marker >= 0:
                item = Definition(
                    id=item.id,
                    term=item.term,
                    text=_definition_text(text[body_start:end_marker], source),
                    clause_id=item.clause_id,
                    source=item.source,
                )
            definitions.setdefault(item.id, item)

        for offset, args, end_offset in _command_events(text, source.definition_at, 2):
            anchor = _commands(args[1], source.definition_anchor, 1)
            term = _commands(args[1], source.definition_term, 1)
            if not anchor or not term:
                continue
            definition_id = anchor[0][1][0]
            definitions.setdefault(
                definition_id,
                Definition(
                    id=definition_id,
                    term=_latex_text(term[0][1][0], source),
                    text=_definition_text(args[1], source),
                    clause_id=_nearest_heading(tuple(headings), offset),
                    source=_source(root, path, text, offset, end_offset),
                ),
            )

        detailed_headings: list[tuple[int, int, str, str, SourceRef]] = []
        for offset, args, end_offset in _command_events(text, source.detailed_rule_heading, 2):
            title = _latex_text(args[1], source)
            # A layout adapter may delegate title text to a generated semantic
            # macro. The authored JSON record is authoritative in that case;
            # do not create an invalid empty candidate while scanning LaTeX.
            if not title:
                continue
            detailed_headings.append(
                (
                    offset,
                    end_offset,
                    args[0],
                    title,
                    _source(root, path, text, offset, end_offset),
                )
            )

        for offset, args, end_offset in _command_events(text, source.summary_rule, 2):
            prior_clause = [item for item in headings if item[0] < offset]
            clause = prior_clause[-1][1].removeprefix("clause-") if prior_clause else None
            statement = _latex_text(args[1], source)
            # Generated semantic macro references intentionally have no prose
            # for the source scanner to expand. Authored records are loaded
            # below and replace these source-shaped candidates.
            if not statement:
                continue
            item = Requirement(
                id=args[0],
                title=args[0].replace("-", " ").title(),
                statement=statement,
                kind="summary",
                clause=clause,
                machine_statement=_machine_statement(args[1], source),
                extraction="candidate",
                source=_source(root, path, text, offset, end_offset),
            )
            requirements.setdefault(item.id, item)

        detailed_headings.sort(key=lambda item: item[0])
        for offset, args, end_offset in _command_events(text, source.normative_rule_statement, 1):
            prior = [item for item in detailed_headings if item[0] < offset]
            if not prior:
                continue
            rule_offset, _, rule_id, title, _ = prior[-1]
            clause_match = re.match(r"([A-Za-z]?\d+(?:\.\d+)*)", title)
            statement = _latex_text(args[0], source)
            if not statement:
                continue
            item = Requirement(
                id=rule_id,
                title=title,
                statement=statement,
                kind="detailed",
                clause=clause_match.group(1) if clause_match else None,
                machine_statement=_machine_statement(args[0], source),
                extraction="candidate",
                source=_source(root, path, text, rule_offset, end_offset),
            )
            requirements.setdefault(item.id, item)

    # Authored semantic records are authoritative once a block has migrated
    # out of page-oriented LaTeX. They replace any legacy source duplicate.
    for item in _load_authored_definitions(root):
        definitions[item.id] = item

    # Page fidelity bodies may now be behind thin adapters. Recover hierarchy
    # from their authored layout bodies so clause identity does not disappear
    # when physical page files stop carrying prose and headings.
    for block in content_blocks:
        if block.layout_body is None:
            continue
        virtual_path = root / block.source.path
        local_headings = list(_hierarchy_headings(root, virtual_path, block.layout_body, source))
        for offset, args, end_offset in _command_events(block.layout_body, source.pdf_bookmark, 2):
            if not args[1].startswith("bookmark:clause:"):
                continue
            identifier = f"clause-{args[1].removeprefix('bookmark:clause:')}"
            local_headings.append(
                (
                    offset,
                    identifier,
                    _latex_text(args[0], source),
                    _source(root, virtual_path, block.layout_body, offset, end_offset),
                )
            )
        if block.clause_id is not None and not any(
            item[1] == block.clause_id for item in local_headings
        ):
            local_headings.insert(
                0,
                (
                    -1,
                    block.clause_id,
                    block.clause_id.removeprefix("clause-"),
                    block.source,
                ),
            )
        for offset, args, end_offset in _command_events(block.layout_body, source.definition_at, 2):
            anchor = _commands(args[1], source.definition_anchor, 1)
            term = _commands(args[1], source.definition_term, 1)
            if not anchor or not term:
                continue
            definition_id = anchor[0][1][0]
            definitions.setdefault(
                definition_id,
                Definition(
                    id=definition_id,
                    term=_latex_text(term[0][1][0], source),
                    text=_definition_text(args[1], source),
                    clause_id=_nearest_heading(tuple(sorted(local_headings)), offset),
                    source=_source(
                        root,
                        virtual_path,
                        block.layout_body,
                        offset,
                        end_offset,
                    ),
                ),
            )
        for _, identifier, title, heading_source in sorted(local_headings):
            number, parent_id, level = _clause_shape(identifier)
            clauses.setdefault(
                identifier,
                Clause(
                    id=identifier,
                    number=number,
                    title=title,
                    parent_id=parent_id,
                    level=level,
                    source=heading_source,
                ),
            )

    implementations = _load_authored_implementations(root)

    for item in _load_navigation_clauses(root):
        clauses[item.id] = item

    if not requirements:
        for item in _load_requirement_candidates(root, source):
            requirements.setdefault(item.id, item)
    for item in _load_authored_requirements(root):
        requirements[item.id] = item

    # Some source bundles begin at a subclause or use a content marker for a
    # root rather than emitting a standalone heading. Materialize those
    # inferred ancestors so every semantic record has a navigable owner.
    needed_clause_ids = {
        clause.parent_id for clause in clauses.values() if clause.parent_id is not None
    }
    needed_clause_ids.update(
        requirement.clause_id
        for requirement in requirements.values()
        if requirement.clause_id is not None
    )
    needed_clause_ids.update(
        machine.clause_id for machine in state_machines if machine.clause_id is not None
    )
    needed_clause_ids.update(
        transition.clause_id
        for machine in state_machines
        for transition in machine.transitions
        if transition.clause_id is not None
    )
    needed_clause_ids.update(
        clause_id for implementation in implementations for clause_id in implementation.clause_ids
    )
    while True:
        missing = sorted(
            identifier for identifier in needed_clause_ids if identifier not in clauses
        )
        if not missing:
            break
        for identifier in missing:
            number, parent_id, level = _clause_shape(identifier)
            dependent = next(
                (
                    item.source
                    for item in (*clauses.values(), *requirements.values())
                    if getattr(item, "parent_id", None) == identifier
                       or getattr(item, "clause_id", None) == identifier
                ),
                SourceRef(path="inferred", line=1),
            )
            clauses[identifier] = Clause(
                id=identifier,
                number=number,
                title=f"Clause {number}",
                parent_id=parent_id,
                level=level,
                source=dependent,
            )
            if parent_id is not None:
                needed_clause_ids.add(parent_id)

    annexes = _load_annexes(root, source)
    for annex in annexes:
        clause_id = f"clause-{annex.letter}"
        clause = clauses.get(clause_id)
        if clause is None:
            continue
        status = f" ({annex.status})" if annex.status != "unknown" else ""
        clauses[clause_id] = clause.model_copy(
            update={"title": f"Annex {annex.letter}{status} {annex.title}"}
        )

    references = list(_load_references(root, source))
    authored_references = {item.id: item for item in _load_authored_references(root)}
    references = [authored_references.get(item.id, item) for item in references]
    references.extend(
        item
        for item in authored_references.values()
        if item.id not in {reference.id for reference in references}
    )

    tables = list(_load_tables(root, source))
    authored_tables = {item.id: item for item in _load_authored_tables(root)}
    tables = [authored_tables.get(item.id, item) for item in tables]
    tables.extend(
        item for item in authored_tables.values() if item.id not in {table.id for table in tables}
    )
    table_families = list(
        _derive_table_families(
            root.name,
            tables,
            table_families,
            content_blocks,
        )
    )
    family_by_table: dict[str, str] = {
        table_id: family.id for family in table_families for table_id in family.table_ids
    }
    tables = [
        table.model_copy(update={"family_id": family_by_table.get(table.id)}) for table in tables
    ]
    tables = list(_link_table_cells_to_definitions(tables, definitions.values()))
    notes = list(_load_notes(root, source))
    authored_notes = {item.id: item for item in _load_authored_notes(root)}
    notes = [authored_notes.get(item.id, item) for item in notes]
    notes.extend(
        item for item in authored_notes.values() if item.id not in {note.id for note in notes}
    )
    figures = list(_load_figures(root, source))
    authored_figures = {item.id: item for item in _load_authored_figures(root)}
    figures = [authored_figures.get(item.id, item) for item in figures]
    figures.extend(
        item
        for item in authored_figures.values()
        if item.id not in {figure.id for figure in figures}
    )
    content_elements, derived_cross_references = _derive_cross_references(
        root.name,
        content_elements,
        _cross_reference_catalog(
            clauses=clauses.values(),
            definitions=definitions.values(),
            requirements=requirements.values(),
            content_blocks=content_blocks,
            content_elements=content_elements,
            tables=tables,
            table_families=table_families,
            references=references,
            notes=notes,
            figures=figures,
            examples=_load_examples(root, source),
            annexes=annexes,
            state_machines=state_machines,
            sequence_diagrams=sequence_diagrams,
            graph_diagrams=graph_diagrams,
            implementations=implementations,
            api_surfaces=api_surfaces,
            api_crosswalks=api_crosswalks,
            verification_tests=verification_tests,
            state_traces=state_traces,
        ),
        clauses=clauses.values(),
        definitions=definitions.values(),
        tables=tables,
        table_families=tuple(table_families),
        figures=figures,
    )
    authored_cross_references = {item.id: item for item in _load_authored_cross_references(root)}
    cross_references = list(derived_cross_references)
    cross_references = [authored_cross_references.get(item.id, item) for item in cross_references]
    cross_references.extend(
        item
        for item in authored_cross_references.values()
        if item.id not in {cross_reference.id for cross_reference in cross_references}
    )
    return DocumentModel(
        document_id=root.name,
        clauses=tuple(
            sorted(
                clauses.values(),
                key=lambda item: _source_key(item, source_order),
            )
        ),
        definitions=tuple(
            sorted(
                definitions.values(),
                key=lambda item: _source_key(item, source_order),
            )
        ),
        requirements=tuple(
            sorted(
                requirements.values(),
                key=lambda item: _source_key(item, source_order),
            )
        ),
        requirement_reviews=requirement_reviews,
        requirement_links=requirement_links,
        transition_coverage=transition_coverage,
        content_blocks=content_blocks,
        content_elements=content_elements,
        state_machines=state_machines,
        sequence_diagrams=sequence_diagrams,
        graph_diagrams=graph_diagrams,
        diagram_surfaces=diagram_surfaces,
        implementations=implementations,
        api_surfaces=api_surfaces,
        api_crosswalks=api_crosswalks,
        requirement_api_bindings=requirement_api_bindings,
        verification_tests=verification_tests,
        state_traces=state_traces,
        tables=tuple(tables),
        table_families=tuple(table_families),
        references=tuple(references),
        cross_references=tuple(cross_references),
        notes=tuple(notes),
        figures=tuple(figures),
        examples=_load_examples(root, source),
        annexes=annexes,
    )

def load_corpus(roots: Iterable[Path], source: LatexSourceProfile) -> ComplianceCorpus:
    """Load multiple document roots for cross-document target resolution."""
    return ComplianceCorpus(documents=tuple(load_document_model(root, source) for root in roots))

def main() -> None:
    from hla_lab.corpus.hla_semantic import load_hla_document_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Document source directory")
    parser.add_argument("--json", action="store_true", help="Print the machine-readable model")
    args = parser.parse_args()
    model = load_hla_document_model(args.root)
    if args.json:
        print(model.to_json())
        return
    print(f"clauses: {len(model.clauses)}")
    print(f"definitions: {len(model.definitions)}")
    print(f"requirements: {len(model.requirements)}")
    print(f"content blocks: {len(model.content_blocks)}")
    print(f"implementations: {len(model.implementations)}")
    print(f"API surfaces: {len(model.api_surfaces)}")
    print(f"verification tests: {len(model.verification_tests)}")
    print(f"state traces: {len(model.state_traces)}")
    print(
        "requirement extractions: "
        f"{sum(item.extraction == 'explicit' for item in model.requirements)} explicit, "
        f"{sum(item.extraction == 'candidate' for item in model.requirements)} candidates"
    )
    print(f"state machines: {len(model.state_machines)}")
    print(f"tables: {len(model.tables)}")
    print(f"table cells: {sum(len(item.cells) for item in model.tables)}")
    print(f"references: {len(model.references)}")
    print(f"notes: {len(model.notes)}")
    print(f"figures: {len(model.figures)}")
    print(f"examples: {len(model.examples)}")
    print(f"annexes: {len(model.annexes)}")
    for item in model.requirements:
        # Keep the diagnostic CLI usable under legacy Windows code pages.
        display = f"{item.id}: {item.statement}"
        print(display.encode("ascii", "backslashreplace").decode("ascii"))

if __name__ == "__main__":
    main()
