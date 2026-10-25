"""Shared behavior for validating a complete semantic document."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet

from hla_lab.core.semantic_ordering import _clause_sort_key
from hla_lab.core.semantic_types import (
    StateMachine,
    StateTrace,
    Transition,
)


class DocumentValidationMixin:
    def _validate_unique_record_ids(self) -> None:
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

    def _validate_clause_order(self, clause_ids: AbstractSet[str]) -> None:
        expected_order = tuple(item.id for item in sorted(self.clauses, key=_clause_sort_key))
        if self.clause_order:
            if set(self.clause_order) != clause_ids or len(self.clause_order) != len(clause_ids):
                raise ValueError("clause_order must contain each clause exactly once")
        else:
            object.__setattr__(self, "clause_order", expected_order)

    def _validate_transition_id_uniqueness(self, transition_ids: Sequence[str]) -> None:
        if len(transition_ids) != len(set(transition_ids)):
            raise ValueError("transition IDs must be unique across the document")

    def _validate_requirement_reviews(self, candidate_ids: AbstractSet[str]) -> None:
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

    def _validate_transition_coverage(
        self,
        implementation_ids: AbstractSet[str],
        all_transition_ids: AbstractSet[str],
        transitions_by_id: Mapping[str, Transition],
    ) -> None:
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

    def _validate_clause_hierarchy(self, clause_ids: AbstractSet[str]) -> None:
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

    def _validate_requirement_references(
        self, clause_ids: AbstractSet[str], all_transition_ids: AbstractSet[str]
    ) -> None:
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

    def _validate_clause_record_owners(self, clause_ids: AbstractSet[str]) -> None:
        for record in (*self.references, *self.figures, *self.examples):
            if record.clause_id is not None and record.clause_id not in clause_ids:
                raise ValueError(f"record {record.id} references missing clause {record.clause_id}")
        for note in self.notes:
            if note.owner_id is not None and note.owner_id not in clause_ids:
                raise ValueError(f"note {note.id} references missing owner {note.owner_id}")

    def _validate_content_membership(self, clause_ids: AbstractSet[str]) -> None:
        content_element_ids = {item.id for item in self.content_elements}
        self._validate_content_blocks(clause_ids, content_element_ids)
        self._validate_content_elements(clause_ids, content_element_ids)

    def _validate_content_blocks(
        self, clause_ids: AbstractSet[str], content_element_ids: AbstractSet[str]
    ) -> None:
        for block in self.content_blocks:
            if block.clause_id is not None and block.clause_id not in clause_ids:
                raise ValueError(
                    f"content block {block.id} references missing clause {block.clause_id}"
                )
            missing = sorted(set(block.element_ids) - content_element_ids)
            if missing:
                raise ValueError(f"content block {block.id} references missing elements {missing}")

    def _validate_content_elements(
        self, clause_ids: AbstractSet[str], content_element_ids: AbstractSet[str]
    ) -> None:
        content_block_ids = {item.id for item in self.content_blocks}
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

    def _validate_content_record_references(self, local_record_ids: AbstractSet[str]) -> None:
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

    def _validate_table_families(self, clause_ids: AbstractSet[str]) -> None:
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

    def _validate_document_references(self, local_record_ids: AbstractSet[str]) -> None:
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

    def _validate_state_machines(
        self,
        clause_ids: AbstractSet[str],
        requirement_ids: AbstractSet[str],
        implementation_ids: AbstractSet[str],
    ) -> None:
        for machine in self.state_machines:
            if machine.clause_id is not None and machine.clause_id not in clause_ids:
                raise ValueError(
                    f"state machine {machine.id} references missing clause {machine.clause_id}"
                )
            self._validate_machine_transitions(
                machine, clause_ids, requirement_ids, implementation_ids
            )

    def _validate_machine_transitions(
        self,
        machine: StateMachine,
        clause_ids: AbstractSet[str],
        requirement_ids: AbstractSet[str],
        implementation_ids: AbstractSet[str],
    ) -> None:
        for transition in machine.transitions:
            if transition.clause_id is not None and transition.clause_id not in clause_ids:
                raise ValueError(
                    f"transition {transition.id} references missing clause {transition.clause_id}"
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
                requirement = next(item for item in self.requirements if item.id == requirement_id)
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

    def _validate_sequence_diagrams(
        self, clause_ids: AbstractSet[str], requirement_ids: AbstractSet[str]
    ) -> None:
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

    def _validate_graph_diagrams(
        self,
        clause_ids: AbstractSet[str],
        requirement_ids: AbstractSet[str],
        implementation_ids: AbstractSet[str],
    ) -> None:
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

    def _validate_requirement_links(
        self, requirement_ids: AbstractSet[str], transitions_by_id: Mapping[str, Transition]
    ) -> None:
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

    def _validate_explicit_requirement_links(
        self, link_pairs: AbstractSet[tuple[str, str]]
    ) -> None:
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

    def _validate_implementations(
        self,
        clause_ids: AbstractSet[str],
        requirement_ids: AbstractSet[str],
        all_transition_ids: AbstractSet[str],
        transitions_by_id: Mapping[str, Transition],
        link_pairs: AbstractSet[tuple[str, str]],
    ) -> None:
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

    def _validate_api_surfaces(
        self,
        clause_ids: AbstractSet[str],
        requirement_ids: AbstractSet[str],
        implementation_ids: AbstractSet[str],
        all_transition_ids: AbstractSet[str],
    ) -> None:
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

    def _validate_api_crosswalks(
        self, implementation_ids: AbstractSet[str], api_surface_ids: AbstractSet[str]
    ) -> None:
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

    def _validate_requirement_api_bindings(
        self, requirement_ids: AbstractSet[str], api_surface_ids: AbstractSet[str]
    ) -> None:
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

    def _validate_verification_tests(
        self,
        requirement_ids: AbstractSet[str],
        implementation_ids: AbstractSet[str],
        api_surface_ids: AbstractSet[str],
        state_trace_ids: AbstractSet[str],
        all_transition_ids: AbstractSet[str],
    ) -> None:
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

    def _validate_state_traces(
        self,
        requirement_ids: AbstractSet[str],
        api_surface_ids: AbstractSet[str],
        verification_test_ids: AbstractSet[str],
        machine_ids: AbstractSet[str],
    ) -> None:
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
            self._validate_trace_steps(
                trace,
                machine_state_ids,
                machine_transition_ids,
                requirement_ids,
                api_surface_ids,
            )

    def _validate_trace_steps(
        self,
        trace: StateTrace,
        machine_state_ids: AbstractSet[str],
        machine_transition_ids: AbstractSet[str],
        requirement_ids: AbstractSet[str],
        api_surface_ids: AbstractSet[str],
    ) -> None:
        for step in trace.steps:
            if step.source_state is not None and step.source_state not in machine_state_ids:
                raise ValueError(
                    f"trace step {step.id} references missing source state {step.source_state}"
                )
            if step.target_state is not None and step.target_state not in machine_state_ids:
                raise ValueError(
                    f"trace step {step.id} references missing target state {step.target_state}"
                )
            if step.transition_id is not None and step.transition_id not in machine_transition_ids:
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
