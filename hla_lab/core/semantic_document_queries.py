"""Shared behavior for querying a semantic document."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from typing import TYPE_CHECKING, Literal, Protocol

from hla_lab.core.semantic_text import _tokens
from hla_lab.core.semantic_types import (
    Annex,
    ApiCrosswalk,
    ApiSurface,
    ApplicabilityMatch,
    ApplicabilityMatchView,
    Clause,
    ComplianceIssue,
    ComplianceQueryResult,
    ContentBlock,
    ContentElement,
    CrossReference,
    Definition,
    DiagramSurface,
    Example,
    Figure,
    GraphDiagram,
    ImplementationEvidence,
    ImplementationMapping,
    ImplementationStatus,
    Note,
    OperationalImplication,
    Reference,
    Requirement,
    RequirementApiBinding,
    RequirementApplicability,
    RequirementApplicabilityRelation,
    RequirementLink,
    RequirementMatch,
    RequirementReview,
    SequenceDiagram,
    StateMachine,
    StateTrace,
    Table,
    TableCell,
    TableFamily,
    Transition,
    TransitionCoverage,
    TransitionCoverageStatus,
    TransitionImplementationCoverage,
    VerificationTest,
)

if TYPE_CHECKING:

    class _SemanticDocumentFields(Protocol):
        @property
        def document_id(self) -> str: ...

        @property
        def clauses(self) -> tuple[Clause, ...]: ...

        @property
        def definitions(self) -> tuple[Definition, ...]: ...

        @property
        def requirements(self) -> tuple[Requirement, ...]: ...

        @property
        def requirement_reviews(self) -> tuple[RequirementReview, ...]: ...

        @property
        def requirement_links(self) -> tuple[RequirementLink, ...]: ...

        @property
        def transition_coverage(self) -> tuple[TransitionCoverage, ...]: ...

        @property
        def content_blocks(self) -> tuple[ContentBlock, ...]: ...

        @property
        def diagram_surfaces(self) -> tuple[DiagramSurface, ...]: ...

        @property
        def content_elements(self) -> tuple[ContentElement, ...]: ...

        @property
        def state_machines(self) -> tuple[StateMachine, ...]: ...

        @property
        def sequence_diagrams(self) -> tuple[SequenceDiagram, ...]: ...

        @property
        def graph_diagrams(self) -> tuple[GraphDiagram, ...]: ...

        @property
        def implementations(self) -> tuple[ImplementationMapping, ...]: ...

        @property
        def api_surfaces(self) -> tuple[ApiSurface, ...]: ...

        @property
        def api_crosswalks(self) -> tuple[ApiCrosswalk, ...]: ...

        @property
        def requirement_api_bindings(self) -> tuple[RequirementApiBinding, ...]: ...

        @property
        def verification_tests(self) -> tuple[VerificationTest, ...]: ...

        @property
        def state_traces(self) -> tuple[StateTrace, ...]: ...

        @property
        def tables(self) -> tuple[Table, ...]: ...

        @property
        def table_families(self) -> tuple[TableFamily, ...]: ...

        @property
        def references(self) -> tuple[Reference, ...]: ...

        @property
        def cross_references(self) -> tuple[CrossReference, ...]: ...

        @property
        def notes(self) -> tuple[Note, ...]: ...

        @property
        def figures(self) -> tuple[Figure, ...]: ...

        @property
        def examples(self) -> tuple[Example, ...]: ...

        @property
        def annexes(self) -> tuple[Annex, ...]: ...

        @property
        def clause_order(self) -> tuple[str, ...]: ...

        @property
        def schema_version(self) -> int: ...

else:

    class _SemanticDocumentFields:
        pass


class DocumentQueryMixin(_SemanticDocumentFields):
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
        """Return requirements grouped by clause and source/include position.

        Requirement IDs are semantic cross-reference keys, not display-order
        keys. Several IDs contain source coordinates, so lexical ID sorting
        puts later source material before earlier material. The loader already
        orders ``requirements`` by the authoritative include graph; preserve
        that source order within each canonical clause instead of reconstructing
        it from filenames. This keeps clause-oriented views deterministic
        across both HLA editions without making a renumbering migration look
        like an ID migration.
        """
        clause_index = {item.id: index for index, item in enumerate(self.ordered_clauses())}
        source_index = {item.id: index for index, item in enumerate(self.requirements)}
        return tuple(
            sorted(
                self.requirements,
                key=lambda item: (
                    clause_index.get(item.clause_id or "", len(clause_index)),
                    source_index[item.id],
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
        kinds: Sequence[str] = (),
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
        kinds: Sequence[str] = (),
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

    @staticmethod
    def _add_requirement_match(
        relations: MutableMapping[str, RequirementApplicabilityRelation],
        requirements: Mapping[str, Requirement],
        relation_priority: Mapping[RequirementApplicabilityRelation, int],
        requirement_id: str,
        relation: RequirementApplicabilityRelation,
    ) -> None:
        if requirement_id not in requirements:
            return
        previous = relations.get(requirement_id)
        if previous is None or relation_priority[relation] < relation_priority[previous]:
            relations[requirement_id] = relation

    def _direct_requirement_relations(
        self,
        transition: Transition,
        requirements: Mapping[str, Requirement],
        relation_priority: Mapping[RequirementApplicabilityRelation, int],
    ) -> dict[str, RequirementApplicabilityRelation]:
        relations: dict[str, RequirementApplicabilityRelation] = {}
        for requirement_id in transition.requirement_ids:
            self._add_requirement_match(
                relations, requirements, relation_priority, requirement_id, "transition"
            )
        for link in self.requirement_links:
            if link.transition_id == transition.id:
                self._add_requirement_match(
                    relations, requirements, relation_priority, link.requirement_id, "reviewed-link"
                )
        for implementation in self.implementation_mappings_for_transition(transition.id):
            for requirement_id in implementation.requirement_ids:
                self._add_requirement_match(
                    relations, requirements, relation_priority, requirement_id, "implementation"
                )
        return relations

    def _apply_clause_requirement_fallback(
        self,
        matches: MutableSequence[ApplicabilityMatch],
    ) -> None:
        if any(relations for _, _, relations in matches):
            return
        for index, (machine, transition, relations) in enumerate(matches):
            if transition.clause_id is None:
                continue
            for requirement in self.requirements:
                if requirement.clause_id == transition.clause_id:
                    relations[requirement.id] = "clause-fallback"
            matches[index] = (machine, transition, relations)

    def _applicability_results(
        self,
        matches: Sequence[ApplicabilityMatchView],
        requirements: Mapping[str, Requirement],
        state_id: str,
        *,
        include_candidates: bool,
    ) -> tuple[RequirementApplicability, ...]:
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
        relation_priority: dict[RequirementApplicabilityRelation, int] = {
            "transition": 0,
            "reviewed-link": 1,
            "implementation": 2,
            "clause-fallback": 3,
        }

        matches: list[
            tuple[
                StateMachine,
                Transition,
                dict[str, RequirementApplicabilityRelation],
            ]
        ] = []
        for machine, transition in selected:
            relations = self._direct_requirement_relations(
                transition, requirements, relation_priority
            )
            matches.append((machine, transition, relations))

        self._apply_clause_requirement_fallback(matches)
        return self._applicability_results(
            matches,
            requirements,
            state_id,
            include_candidates=include_candidates,
        )

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
