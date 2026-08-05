"""Extract reusable semantic records from source-first LaTeX documents."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from scripts.source_adapter import LatexSourceProfile
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from source_adapter import LatexSourceProfile


class SemanticRecord(BaseModel):
    """Shared strict contract for semantic records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(SemanticRecord):
    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_span(self) -> SourceRef:
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError("source end_line must not precede line")
        return self


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
    extraction: Literal["explicit", "candidate"] = "explicit"
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
        if self.extraction == "explicit":
            if self.coverage_kind == "transition" and not self.transition_ids:
                raise ValueError(
                    "explicit transition-covered requirements must name at least one transition"
                )
            if self.coverage_kind != "transition" and not self.coverage_note.strip():
                raise ValueError(
                    "explicit non-transition requirements need a coverage_note explaining scope"
                )
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


class RequirementLinkFile(SemanticRecord):
    """Authored requirement-to-transition relationships."""

    schema_version: int = Field(ge=1)
    links: tuple[RequirementLink, ...]


class ContentBlock(SemanticRecord):
    """A source-owned prose block linked to semantic records and hierarchy."""

    id: str = Field(min_length=1)
    kind: Literal["context", "behavior", "normative", "transition-summary", "note"]
    text: str
    clause_id: str | None = None
    record_ids: tuple[str, ...] = ()
    source: SourceRef


class ContentBlockFile(SemanticRecord):
    """Authored prose blocks migrated out of page-oriented LaTeX."""

    schema_version: int = Field(ge=1)
    content_blocks: tuple[ContentBlock, ...]


class ImplementationMapping(SemanticRecord):
    """Map a semantic interface surface to an implementation entry point."""

    id: str = Field(min_length=1)
    interface_kind: Literal["service", "callback", "adapter", "handler"]
    interface_name: str = Field(min_length=1)
    implementation: str = Field(min_length=1)
    status: Literal["planned", "partial", "implemented", "verified"] = "planned"
    clause_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    source: SourceRef | None = None
    notes: str = ""


class ImplementationFile(SemanticRecord):
    """Authored implementation mappings kept beside semantic document data."""

    schema_version: int = Field(ge=1)
    implementations: tuple[ImplementationMapping, ...]


class ComplianceIssue(SemanticRecord):
    """A non-fatal compliance coverage finding for query/report consumers."""

    code: Literal[
        "orphan-requirement",
        "unmapped-transition",
        "orphan-implementation",
        "unresolved-reference",
    ]
    severity: Literal["warning", "error"] = "warning"
    record_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class TableCell(SemanticRecord):
    """A semantic table cell with source provenance and logical placement."""

    id: str = Field(min_length=1)
    table_id: str = Field(min_length=1)
    text: str
    row: int | None = Field(default=None, ge=0)
    column: int | None = Field(default=None, ge=0)
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


class ReferenceFile(SemanticRecord):
    """Authored reference records with optional resolved targets."""

    schema_version: int = Field(ge=1)
    references: tuple[Reference, ...]


class Note(SemanticRecord):
    """An explicitly marked note or footnote, kept separate from prose."""

    id: str = Field(min_length=1)
    text: str
    kind: Literal["informative", "definition", "table", "figure", "footnote"]
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
    status: Literal["normative", "informative", "unknown"] = "unknown"
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


class DocumentModel(SemanticRecord):
    document_id: str = ""
    clauses: tuple[Clause, ...]
    definitions: tuple[Definition, ...]
    requirements: tuple[Requirement, ...]
    requirement_links: tuple[RequirementLink, ...] = ()
    content_blocks: tuple[ContentBlock, ...] = ()
    state_machines: tuple[StateMachine, ...] = ()
    implementations: tuple[ImplementationMapping, ...] = ()
    tables: tuple[Table, ...] = ()
    table_families: tuple[TableFamily, ...] = ()
    references: tuple[Reference, ...] = ()
    notes: tuple[Note, ...] = ()
    figures: tuple[Figure, ...] = ()
    examples: tuple[Example, ...] = ()
    annexes: tuple[Annex, ...] = ()
    clause_order: tuple[str, ...] = ()
    schema_version: int = Field(default=5, ge=4)

    @model_validator(mode="after")
    def validate_record_ids(self) -> DocumentModel:
        for label, records in (
            ("clause", self.clauses),
            ("definition", self.definitions),
            ("requirement", self.requirements),
            ("requirement link", self.requirement_links),
            ("content block", self.content_blocks),
            ("state machine", self.state_machines),
            ("implementation", self.implementations),
            ("table", self.tables),
            ("table family", self.table_families),
            ("reference", self.references),
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
        implementation_ids = {item.id for item in self.implementations}
        all_transition_ids = set(transition_ids)
        transitions_by_id = {
            transition.id: transition
            for machine in self.state_machines
            for transition in machine.transitions
        }
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
        local_record_ids = self.semantic_record_ids()
        for block in self.content_blocks:
            missing_records = set(block.record_ids) - local_record_ids
            if missing_records:
                raise ValueError(
                    f"content block {block.id} references missing records {sorted(missing_records)}"
                )
        table_ids = {table.id for table in self.tables}
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
        for reference in self.references:
            for target in reference.targets:
                if (
                    target.document_id == self.document_id
                    and target.record_id not in local_record_ids
                ):
                    raise ValueError(
                        f"reference {reference.id} targets missing local record {target.record_id}"
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
                *self.ordered_annexes(),
            )
        )

    def semantic_record_ids(self) -> frozenset[str]:
        """Return every locally addressable semantic record ID."""
        return frozenset(
            item.id
            for item in (
                *self.clauses,
                *self.definitions,
                *self.requirements,
                *self.requirement_links,
                *self.content_blocks,
                *self.state_machines,
                *self.tables,
                *self.table_families,
                *self.references,
                *self.notes,
                *self.figures,
                *self.examples,
                *self.annexes,
                *self.implementations,
            )
        ) | frozenset(
            item.id
            for machine in self.state_machines
            for item in (*machine.states, *machine.transitions)
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
        transitions = self.transitions_for_state_event(state_id, event, machine_id)
        requirement_ids = {
            requirement_id
            for transition in transitions
            for requirement_id in transition.requirement_ids
        }
        requirement_ids.update(
            link.requirement_id
            for transition in transitions
            for link in self.requirement_links
            if link.transition_id == transition.id
        )
        requirement_ids.update(
            requirement_id
            for transition in transitions
            for implementation in self.implementation_mappings_for_transition(transition.id)
            for requirement_id in implementation.requirement_ids
        )
        clause_ids = {
            transition.clause_id for transition in transitions if transition.clause_id is not None
        }
        use_clause_fallback = not requirement_ids
        return tuple(
            requirement
            for requirement in self.requirements
            if (include_candidates or requirement.extraction == "explicit")
            and (
                requirement.id in requirement_ids
                or (use_clause_fallback and requirement.clause_id in clause_ids)
            )
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

    def implementation_mappings_for_transition(
        self, transition_id: str
    ) -> tuple[ImplementationMapping, ...]:
        """Return implementation mappings attached to a transition."""
        return tuple(item for item in self.implementations if transition_id in item.transition_ids)

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
                if not transition.implementation_ids and not (
                    self.implementation_mappings_for_transition(transition.id)
                ):
                    issues.append(
                        ComplianceIssue(
                            code="unmapped-transition",
                            record_id=transition.id,
                            message=f"transition has no implementation mapping in {machine.id}",
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
    ) -> None:
        """Raise when selected compliance coverage contains any reported issue."""
        issues = self.compliance_issues(
            machine_id,
            include_candidates=include_candidates,
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
                )
            )
        return tuple(merged)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation for downstream tools."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, payload: object) -> DocumentModel:
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
        return tuple(issues)

    def compliance_issues(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
    ) -> tuple[ComplianceIssue, ...]:
        """Return document coverage findings plus cross-document failures."""
        issues = [
            issue
            for document in self.documents
            for issue in document.compliance_issues(
                machine_id,
                include_candidates=include_candidates,
            )
        ]
        issues.extend(self.unresolved_reference_issues())
        return tuple(issues)

    def assert_compliance(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
    ) -> None:
        """Raise when any document or cross-document compliance issue exists."""
        issues = self.compliance_issues(
            machine_id,
            include_candidates=include_candidates,
        )
        if issues:
            raise ValueError("; ".join(f"{item.code}: {item.record_id}" for item in issues))

    def assert_references_resolved(self) -> None:
        """Raise when a cross-document target cannot be resolved."""
        issues = self.unresolved_reference_issues()
        if issues:
            raise ValueError("; ".join(f"{item.code}: {item.record_id}" for item in issues))


def _balanced(text: str, opening: int, left: str = "{", right: str = "}") -> tuple[str, int]:
    if opening >= len(text) or text[opening] != left:
        raise ValueError(f"Expected {left!r} at offset {opening}")
    depth = 0
    escaped = False
    for index in range(opening, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == left:
            depth += 1
        elif char == right:
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index], index + 1
    raise ValueError(f"Unclosed {left!r} group at offset {opening}")


def _arguments(text: str, start: int, count: int) -> tuple[tuple[str, ...], int] | None:
    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if cursor < len(text) and text[cursor] == "[":
        _, cursor = _balanced(text, cursor, "[", "]")
    values: list[str] = []
    for _ in range(count):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            return None
        value, cursor = _balanced(text, cursor)
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


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


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
        line=_line_number(text, offset),
        end_line=(
            _line_number(text, max(offset, end_offset - 1)) if end_offset is not None else None
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

    main = root / "main.tex"
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
    item: SemanticRecord,
    source_order: dict[str, int] | None = None,
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


def _source_ref(value: object) -> SourceRef | None:
    if not isinstance(value, dict):
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
                current_table = table_match.group("table")
                current_cell = None
                table_sources.setdefault(current_table, _source(root, path, text, offset))
            elif cell_match:
                current_table = cell_match.group("table")
                current_cell = identifier
            continue
        if current_table is None:
            continue
        if kind == "grid":
            grids.setdefault(current_table, []).append(
                _TableGridCell(*(float(value) for value in args))
            )
        elif kind == "cell":
            if current_cell is None:
                continue
            candidates.setdefault(current_table, []).append(
                _TableCellCandidate(
                    current_cell,
                    current_table,
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
                    args[0],
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
                        args[0],
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
    for caption, x, y, width, source in captions:
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
        caption_by_table[table_id] = (caption, source)

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
                domain="omt" if _table_number(caption or title or "") else "generic",
                omt_kind=_omt_kind(caption or title or ""),
            )
        )
    return tuple(tables)


def _load_tables(root: Path, source: LatexSourceProfile) -> tuple[Table, ...]:
    tables: list[Table] = []
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        tables.extend(_load_tables_from_file(root, path, text, source))
    ordered = sorted(tables, key=lambda item: (item.source.path, item.source.line, item.id))
    previous_by_logical_id: dict[str, Table] = {}
    normalized: list[Table] = []
    for table in ordered:
        previous = previous_by_logical_id.get(table.logical_id or table.id)
        normalized.append(
            table.model_copy(
                update={
                    "continued_from": previous.id
                    if table.continuation and previous is not None
                    else table.continued_from
                }
            )
        )
        previous_by_logical_id[table.logical_id or table.id] = normalized[-1]
    return tuple(normalized)


def _record_id(prefix: str, root: Path, path: Path, text: str, offset: int, ordinal: int) -> str:
    relative = path.relative_to(root).with_suffix("").as_posix()
    slug = re.sub(r"[^a-z0-9]+", "-", relative.casefold()).strip("-")
    return f"{prefix}-{slug}-l{_line_number(text, offset)}-{ordinal}"


def _heading_parts(args: tuple[str, ...], source: LatexSourceProfile) -> tuple[str, str] | None:
    """Return a normalized clause ID and title from either heading shape."""
    if len(args) >= 2 and args[0].strip().startswith("clause-"):
        return args[0].strip(), _latex_text(args[1], source)
    value = _latex_text(args[-1], source)
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
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        headings = heading_context[path]
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
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        events: list[tuple[int, str, tuple[str, ...], int]] = []
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
        headings = heading_context[path]
        for ordinal, (offset, kind, args, end_offset) in enumerate(sorted(events), start=1):
            payload = args[-1]
            records.append(
                Note(
                    id=_record_id("note", root, path, text, offset, ordinal),
                    text=_latex_text(payload, source),
                    kind=kind,
                    owner_id=_nearest_heading(headings, offset),
                    source=_source(root, path, text, offset, end_offset),
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))


def _load_figures(root: Path, source: LatexSourceProfile) -> tuple[Figure, ...]:
    records: list[Figure] = []
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        images = _command_events(text, source.figure_image, 5)
        captions = _command_events(text, source.figure_caption, 3)
        anchors = _command_events(text, source.figure_anchor, 1)
        headings = heading_context[path]
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
            status = next(
                (
                    _latex_text(item[1][0], source).strip("() ").casefold()
                    for item in statuses
                    if offset < item[0] < limit
                ),
                "unknown",
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
                    status=status if status in {"normative", "informative"} else "unknown",
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
                    status=status.casefold(),
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
                    status=status.casefold(),
                    source=_source(root, path, text, offset, end_offset),
                ),
            )

    navigation = root / "canonical" / "source-navigation.json"
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
                    status=status.casefold(),
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
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        if "frontmatter" in relative or "generated" in relative:
            continue
        text = path.read_text(encoding="utf-8")
        headings = heading_context[path]
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
                    title=f"Normative candidate at {relative}:{_line_number(text, offset)}",
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
    semantic_root = root / "semantic"
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


def _load_authored_definitions(root: Path) -> tuple[Definition, ...]:
    """Load definitions that have already migrated to semantic source."""
    path = root / "semantic" / "definitions.json"
    if not path.is_file():
        return ()
    payload = DefinitionFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.definitions


def _load_authored_requirements(root: Path) -> tuple[Requirement, ...]:
    """Load reviewed requirements promoted from source-shaped candidates."""
    path = root / "semantic" / "requirements.json"
    if not path.is_file():
        return ()
    payload = RequirementFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.requirements


def _load_authored_requirement_links(root: Path) -> tuple[RequirementLink, ...]:
    """Load explicit requirement-to-transition relationships."""
    path = root / "semantic" / "requirement-links.json"
    if not path.is_file():
        return ()
    payload = RequirementLinkFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.links


def _load_authored_content_blocks(root: Path) -> tuple[ContentBlock, ...]:
    """Load prose blocks that have crossed into semantic source."""
    path = root / "semantic" / "content-blocks.json"
    if not path.is_file():
        return ()
    payload = ContentBlockFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.content_blocks


def _load_authored_table_families(root: Path) -> tuple[TableFamily, ...]:
    """Load named table families that group parsed semantic table records."""
    path = root / "semantic" / "table-families.json"
    if not path.is_file():
        return ()
    payload = TableFamilyFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.table_families


def _load_authored_implementations(
    root: Path,
) -> tuple[ImplementationMapping, ...]:
    """Load code-facing mappings authored outside hand-written LaTeX."""
    path = root / "semantic" / "implementations.json"
    if not path.is_file():
        return ()
    payload = ImplementationFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.implementations


def _load_authored_references(root: Path) -> tuple[Reference, ...]:
    """Load references with resolved cross-document semantic targets."""
    path = root / "semantic" / "references.json"
    if not path.is_file():
        return ()
    payload = ReferenceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.references


def _load_navigation_clauses(root: Path) -> tuple[Clause, ...]:
    """Load clause labels from an existing canonical navigation manifest."""
    path = root / "canonical" / "source-navigation.json"
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    outline = raw.get("outline", []) if isinstance(raw, dict) else []
    source = SourceRef(path=path.relative_to(root).as_posix(), line=1)
    clauses: dict[str, Clause] = {}
    for entry in outline:
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
    requirement_links = _load_authored_requirement_links(root)
    content_blocks = _load_authored_content_blocks(root)
    table_families = _load_authored_table_families(root)
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
            detailed_headings.append(
                (
                    offset,
                    end_offset,
                    args[0],
                    _latex_text(args[1], source),
                    _source(root, path, text, offset, end_offset),
                )
            )

        for offset, args, end_offset in _command_events(text, source.summary_rule, 2):
            prior_clause = [item for item in headings if item[0] < offset]
            clause = prior_clause[-1][1].removeprefix("clause-") if prior_clause else None
            item = Requirement(
                id=args[0],
                title=args[0].replace("-", " ").title(),
                statement=_latex_text(args[1], source),
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
            item = Requirement(
                id=rule_id,
                title=title,
                statement=_latex_text(args[0], source),
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
        requirement_links=requirement_links,
        content_blocks=content_blocks,
        state_machines=state_machines,
        implementations=implementations,
        tables=_load_tables(root, source),
        table_families=table_families,
        references=tuple(references),
        notes=_load_notes(root, source),
        figures=_load_figures(root, source),
        examples=_load_examples(root, source),
        annexes=annexes,
    )


def load_corpus(roots: Iterable[Path], source: LatexSourceProfile) -> ComplianceCorpus:
    """Load multiple document roots for cross-document target resolution."""
    return ComplianceCorpus(documents=tuple(load_document_model(root, source) for root in roots))


def main() -> None:
    try:
        from scripts.hla_semantic import load_hla_document_model
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        from hla_semantic import load_hla_document_model

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
