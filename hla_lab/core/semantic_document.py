"""Extract reusable semantic records from source-first LaTeX documents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from hla_lab.core.json_types import JsonObject
from hla_lab.core.semantic_document_queries import DocumentQueryMixin
from hla_lab.core.semantic_document_validation import DocumentValidationMixin
from hla_lab.core.semantic_types import (
    Annex,
    ApiCrosswalk,
    ApiSurface,
    Clause,
    ComplianceDependency,
    ContentBlock,
    ContentElement,
    CrossReference,
    Definition,
    DiagramSurface,
    Example,
    Figure,
    GraphDiagram,
    ImplementationMapping,
    Note,
    Reference,
    Requirement,
    RequirementApiBinding,
    RequirementLink,
    RequirementReview,
    SemanticRecord,
    SequenceDiagram,
    SourceRef,
    StateMachine,
    StateTrace,
    Table,
    TableFamily,
    TransitionCoverage,
    VerificationTest,
)

__all__ = ["DocumentModel", "_SemanticDependencyBuilder"]


class DocumentModel(DocumentValidationMixin, DocumentQueryMixin, SemanticRecord):
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
    schema_version: Annotated[int, Field(ge=4)] = 8

    @model_validator(mode="after")
    def validate_record_ids(self) -> DocumentModel:
        self._validate_unique_record_ids()
        clause_ids = {item.id for item in self.clauses}

        self._validate_clause_order(clause_ids)
        transition_ids = [
            transition.id for machine in self.state_machines for transition in machine.transitions
        ]

        self._validate_transition_id_uniqueness(transition_ids)
        requirement_ids = {item.id for item in self.requirements}
        candidate_ids = {item.id for item in self.requirements if item.extraction == "candidate"}

        self._validate_requirement_reviews(candidate_ids)
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

        self._validate_transition_coverage(
            implementation_ids, all_transition_ids, transitions_by_id
        )

        self._validate_clause_hierarchy(clause_ids)

        self._validate_requirement_references(clause_ids, all_transition_ids)

        self._validate_clause_record_owners(clause_ids)

        self._validate_content_membership(clause_ids)
        local_record_ids = self.semantic_record_ids()

        self._validate_content_record_references(local_record_ids)

        self._validate_table_families(clause_ids)

        self._validate_document_references(local_record_ids)

        self._validate_state_machines(clause_ids, requirement_ids, implementation_ids)

        self._validate_sequence_diagrams(clause_ids, requirement_ids)

        self._validate_graph_diagrams(clause_ids, requirement_ids, implementation_ids)

        self._validate_requirement_links(requirement_ids, transitions_by_id)
        link_pairs = {(link.requirement_id, link.transition_id) for link in self.requirement_links}

        self._validate_explicit_requirement_links(link_pairs)

        self._validate_implementations(
            clause_ids, requirement_ids, all_transition_ids, transitions_by_id, link_pairs
        )

        self._validate_api_surfaces(
            clause_ids, requirement_ids, implementation_ids, all_transition_ids
        )

        self._validate_api_crosswalks(implementation_ids, api_surface_ids)

        self._validate_requirement_api_bindings(requirement_ids, api_surface_ids)

        self._validate_verification_tests(
            requirement_ids,
            implementation_ids,
            api_surface_ids,
            state_trace_ids,
            all_transition_ids,
        )

        self._validate_state_traces(
            requirement_ids, api_surface_ids, verification_test_ids, machine_ids
        )
        return self

    def semantic_dependencies(
        self,
        record_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return qualified ownership, reference, and implementation edges."""
        return _SemanticDependencyBuilder(self, record_id).collect()

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


class _SemanticDependencyBuilder:
    """Build typed dependency edges from one document model."""

    def __init__(self, document: DocumentModel, record_id: str | None) -> None:
        self.document = document
        self.record_id = record_id
        self.kinds: dict[str, str] = {}
        self.edges: dict[str, ComplianceDependency] = {}
        self._register_record_kinds()

    def _register(self, identifier: str, kind: str) -> None:
        self.kinds.setdefault(identifier, kind)

    def add(
        self,
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
        source_kind_value = source_kind or self.kinds.get(source_id, "unknown")
        target_kind_value = target_kind or self.kinds.get(target_id, "unknown")
        target_document = target_document_id or self.document.document_id
        identifier = (
            f"{self.document.document_id}:{source_id}->{target_document}:{target_id}:{relation}"
        )
        if self.record_id is not None and self.record_id not in {source_id, target_id}:
            return
        self.edges.setdefault(
            identifier,
            ComplianceDependency(
                id=identifier,
                source_document_id=self.document.document_id,
                source_record_id=source_id,
                source_kind=source_kind_value,
                target_document_id=target_document,
                target_record_id=target_id,
                target_kind=target_kind_value,
                relation=relation,
                source=source,
            ),
        )

    def _register_record_kinds(self) -> None:
        self._register_core_kinds()
        self._register_diagram_kinds()
        self._register_implementation_kinds()
        self._register_table_kinds()
        self._register_document_attachment_kinds()

    def _register_core_kinds(self) -> None:
        document = self.document
        for record in document.clauses:
            self._register(record.id, "clause")
        for record in document.definitions:
            self._register(record.id, "definition")
        for record in document.requirements:
            self._register(record.id, "requirement")
        for record in document.requirement_links:
            self._register(record.id, "requirement-link")
        for record in document.content_blocks:
            self._register(record.id, "content-block")
        for record in document.content_elements:
            self._register(record.id, "content-element")

    def _register_diagram_kinds(self) -> None:
        document = self.document
        for record in document.state_machines:
            self._register(record.id, "state-machine")
            for state in record.states:
                self._register(state.id, "state")
            for transition in record.transitions:
                self._register(transition.id, "transition")
        for record in document.sequence_diagrams:
            self._register(record.id, "sequence-diagram")
            for message in record.messages:
                self._register(message.id, "sequence-message")
        for record in document.graph_diagrams:
            self._register(record.id, "graph-diagram")
            for edge in record.edges:
                self._register(edge.id, "graph-edge")

    def _register_implementation_kinds(self) -> None:
        document = self.document
        for record in document.implementations:
            self._register(record.id, "implementation")
        for record in document.api_surfaces:
            self._register(record.id, "api-surface")
        for record in document.api_crosswalks:
            self._register(record.id, "api-crosswalk")
        for record in document.requirement_api_bindings:
            self._register(record.id, "requirement-api-binding")
        for record in document.verification_tests:
            self._register(record.id, "verification-test")
        for record in document.state_traces:
            self._register(record.id, "state-trace")

    def _register_table_kinds(self) -> None:
        document = self.document
        for record in document.tables:
            self._register(record.id, "table")
            for cell in record.cells:
                self._register(cell.id, "table-cell")
        for record in document.table_families:
            self._register(record.id, "table-family")

    def _register_document_attachment_kinds(self) -> None:
        document = self.document
        for record in document.references:
            self._register(record.id, "reference")
        for record in document.cross_references:
            self._register(record.id, "cross-reference")
        for record in document.notes:
            self._register(record.id, "note")
        for record in document.figures:
            self._register(record.id, "figure")
        for record in document.examples:
            self._register(record.id, "example")
        for record in document.annexes:
            self._register(record.id, "annex")

    def collect(self) -> tuple[ComplianceDependency, ...]:
        self._collect_clause_and_requirement_dependencies()
        self._collect_content_dependencies()
        self._collect_state_machine_dependencies()
        self._collect_sequence_diagram_dependencies()
        self._collect_graph_diagram_dependencies()
        self._collect_implementation_dependencies()
        self._collect_api_surface_dependencies()
        self._collect_api_crosswalk_dependencies()
        self._collect_requirement_binding_dependencies()
        self._collect_verification_dependencies()
        self._collect_trace_dependencies()
        self._collect_table_family_dependencies()
        self._collect_table_dependencies()
        self._collect_reference_dependencies()
        self._collect_cross_reference_dependencies()
        self._collect_attachment_dependencies()
        return tuple(sorted(self.edges.values(), key=lambda item: item.id))

    def _collect_clause_and_requirement_dependencies(self) -> None:
        document = self.document
        for clause in document.clauses:
            self.add(clause.id, clause.parent_id, "owned-by", clause.source)
        for definition in document.definitions:
            self.add(definition.id, definition.clause_id, "owned-by", definition.source)
        for requirement in document.requirements:
            self.add(requirement.id, requirement.clause_id, "owned-by", requirement.source)
            for transition_id in requirement.transition_ids:
                self.add(requirement.id, transition_id, "governs", requirement.source)
        for link in document.requirement_links:
            self.add(link.id, link.requirement_id, "references", link.source)
            self.add(link.id, link.transition_id, "references", link.source)

    def _collect_content_dependencies(self) -> None:
        document = self.document
        for block in document.content_blocks:
            self.add(block.id, block.clause_id, "owned-by", block.source)
            for element_id in block.element_ids:
                self.add(block.id, element_id, "contains", block.source)
            for related_id in block.record_ids:
                self.add(block.id, related_id, "mentions", block.source)
        for element in document.content_elements:
            self.add(element.id, element.block_id, "member-of", element.source)
            self.add(element.id, element.clause_id, "owned-by", element.source)
            for related_id in element.record_ids:
                self.add(element.id, related_id, "mentions", element.source)

    def _collect_state_machine_dependencies(self) -> None:
        for machine in self.document.state_machines:
            self.add(machine.id, machine.clause_id, "owned-by", machine.source)
            for transition in machine.transitions:
                self.add(transition.id, machine.id, "member-of", transition.source)
                self.add(transition.id, transition.clause_id, "owned-by", transition.source)
                for requirement_id in transition.requirement_ids:
                    self.add(transition.id, requirement_id, "governs", transition.source)
                for implementation_id in transition.implementation_ids:
                    self.add(transition.id, implementation_id, "implements", transition.source)

    def _collect_sequence_diagram_dependencies(self) -> None:
        for diagram in self.document.sequence_diagrams:
            self.add(diagram.id, diagram.clause_id, "owned-by", diagram.source)
            for message in diagram.messages:
                self.add(message.id, diagram.id, "member-of", message.source or diagram.source)
                self.add(
                    message.id,
                    message.clause_id or diagram.clause_id,
                    "owned-by",
                    message.source,
                )
                for requirement_id in message.requirement_ids:
                    self.add(message.id, requirement_id, "governs", message.source)

    def _collect_graph_diagram_dependencies(self) -> None:
        for diagram in self.document.graph_diagrams:
            self.add(diagram.id, diagram.clause_id, "owned-by", diagram.source)
            for edge in diagram.edges:
                self.add(edge.id, diagram.id, "member-of", edge.source_ref)
                self.add(edge.id, edge.clause_id, "owned-by", edge.source_ref)
                for requirement_id in edge.requirement_ids:
                    self.add(edge.id, requirement_id, "governs", edge.source_ref)
                for implementation_id in edge.implementation_ids:
                    self.add(edge.id, implementation_id, "implements", edge.source_ref)

    def _collect_implementation_dependencies(self) -> None:
        for implementation in self.document.implementations:
            for clause_id in implementation.clause_ids:
                self.add(implementation.id, clause_id, "implements", implementation.source)
            for requirement_id in implementation.requirement_ids:
                self.add(implementation.id, requirement_id, "implements", implementation.source)
            for transition_id in implementation.transition_ids:
                self.add(implementation.id, transition_id, "implements", implementation.source)

    def _collect_api_surface_dependencies(self) -> None:
        for surface in self.document.api_surfaces:
            for mapping_id in surface.implementation_mapping_ids:
                self.add(surface.id, mapping_id, "implements", surface.source)
            for requirement_id in surface.requirement_ids:
                self.add(surface.id, requirement_id, "governs", surface.source)
            for transition_id in surface.transition_ids:
                self.add(surface.id, transition_id, "implements", surface.source)

    def _collect_api_crosswalk_dependencies(self) -> None:
        for crosswalk in self.document.api_crosswalks:
            self.add(
                crosswalk.id,
                crosswalk.implementation_mapping_id,
                "annotates",
                crosswalk.source,
            )
            for surface_id in crosswalk.candidate_api_surface_ids:
                self.add(crosswalk.id, surface_id, "mentions", crosswalk.source)
            for surface_id in crosswalk.selected_api_surface_ids:
                self.add(crosswalk.id, surface_id, "implements", crosswalk.source)

    def _collect_requirement_binding_dependencies(self) -> None:
        for binding in self.document.requirement_api_bindings:
            self.add(binding.id, binding.requirement_id, "references", binding.source)
            if binding.api_surface_id is not None:
                self.add(binding.id, binding.api_surface_id, "maps-to", binding.source)
            for surface_id in binding.candidate_api_surface_ids:
                self.add(binding.id, surface_id, "mentions", binding.source)

    def _collect_verification_dependencies(self) -> None:
        for test in self.document.verification_tests:
            for requirement_id in test.requirement_ids:
                self.add(test.id, requirement_id, "annotates", test.source)
            for transition_id in test.transition_ids:
                self.add(test.id, transition_id, "annotates", test.source)
            for surface_id in test.api_surface_ids:
                self.add(test.id, surface_id, "annotates", test.source)
            for trace_id in test.trace_ids:
                self.add(test.id, trace_id, "annotates", test.source)
            for mapping_id in test.implementation_mapping_ids:
                self.add(test.id, mapping_id, "annotates", test.source)

    def _collect_trace_dependencies(self) -> None:
        for trace in self.document.state_traces:
            self.add(trace.id, trace.machine_id, "member-of", trace.source)
            for requirement_id in trace.requirement_ids:
                self.add(trace.id, requirement_id, "governs", trace.source)
            for transition_id in trace.transition_ids:
                self.add(trace.id, transition_id, "annotates", trace.source)
            for surface_id in trace.api_surface_ids:
                self.add(trace.id, surface_id, "annotates", trace.source)
            for test_id in trace.verification_test_ids:
                self.add(trace.id, test_id, "annotates", trace.source)

    def _collect_table_family_dependencies(self) -> None:
        for family in self.document.table_families:
            self.add(family.id, family.clause_id, "owned-by", family.source)
            for table_id in family.table_ids:
                self.add(family.id, table_id, "contains", family.source)

    def _collect_table_dependencies(self) -> None:
        for table in self.document.tables:
            if table.family_id:
                self.add(table.id, table.family_id, "member-of", table.source)
            for cell in table.cells:
                self.add(cell.id, table.id, "member-of", cell.source)
                for related_id in cell.record_ids:
                    self.add(cell.id, related_id, "annotates", cell.source)

    def _collect_reference_dependencies(self) -> None:
        for reference in self.document.references:
            self.add(reference.id, reference.clause_id, "owned-by", reference.source)
            for target in reference.targets:
                self.add(
                    reference.id,
                    target.record_id,
                    "references",
                    reference.source,
                    target_kind=self.kinds.get(target.record_id, "external"),
                    target_document_id=target.document_id,
                )

    def _collect_cross_reference_dependencies(self) -> None:
        for cross_reference in self.document.cross_references:
            self.add(
                cross_reference.owner_id,
                cross_reference.target_record_id,
                cross_reference.relation,
                cross_reference.source,
                target_kind=cross_reference.kind,
                target_document_id=cross_reference.target_document_id,
            )

    def _collect_attachment_dependencies(self) -> None:
        for note in self.document.notes:
            self.add(note.id, note.owner_id, "owned-by", note.source)
        for figure in self.document.figures:
            self.add(figure.id, figure.clause_id, "owned-by", figure.source)
        for example in self.document.examples:
            self.add(example.id, example.clause_id, "owned-by", example.source)
