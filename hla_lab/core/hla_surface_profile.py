"""HLA-specific projection of generic specification-facing surface contracts."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping

from hla_lab.core.hla_profile import SOURCE_PROFILE_MANIFEST
from hla_lab.core.semantic_model import (
    ApiSurface,
    DocumentModel,
    ImplementationMapping,
    Requirement,
    SourceRef,
    StateMachine,
    StateTrace,
    TraceStep,
    Transition,
    VerificationTest,
)

__all__ = ["HLA_API_OWNERS", "build_hla_surface_contract"]

HLA_API_OWNERS = json.loads(SOURCE_PROFILE_MANIFEST.read_text(encoding="utf-8"))["api_owners"]


def _source_for(mapping: ImplementationMapping) -> SourceRef:
    source = getattr(mapping, "source", None)
    return source or SourceRef(path="semantic/implementations.json", line=1)


def _surface_ids_for_transitions(
    transition_ids: tuple[str, ...],
    surfaces_by_transition: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                surface_id
                for transition_id in transition_ids
                for surface_id in surfaces_by_transition.get(transition_id, ())
            }
        )
    )


def _mapping_ids_for_surfaces(
    surface_ids: tuple[str, ...],
    surfaces_by_id: Mapping[str, ApiSurface],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                mapping_id
                for surface_id in surface_ids
                for mapping_id in surfaces_by_id[surface_id].implementation_mapping_ids
            }
        )
    )


def _transition_machines(model: DocumentModel) -> dict[str, tuple[Transition, StateMachine]]:
    return {
        transition.id: (transition, machine)
        for machine in model.state_machines
        for transition in machine.transitions
    }


def _surface_for_mapping(
    mapping: ImplementationMapping,
    transition_machines: Mapping[str, tuple[Transition, StateMachine]],
) -> ApiSurface:
    related_transitions = tuple(
        transition_id
        for transition_id in mapping.transition_ids
        if transition_id in transition_machines
    )
    requirement_ids = set(mapping.requirement_ids)
    clause_ids = set(mapping.clause_ids)
    for transition_id in related_transitions:
        transition, machine = transition_machines[transition_id]
        requirement_ids.update(transition.requirement_ids)
        if transition.clause_id:
            clause_ids.add(transition.clause_id)
        if machine.clause_id:
            clause_ids.add(machine.clause_id)
    language = (
        mapping.implementation_ref.language
        if mapping.implementation_ref is not None
        else "unspecified"
    )
    return ApiSurface(
        id=f"surface:{mapping.id}",
        name=mapping.interface_name,
        interface_kind=mapping.interface_kind,
        binding_kind="semantic",
        owner=HLA_API_OWNERS[mapping.interface_kind],
        language=language,
        signature=mapping.interface_name,
        clause_ids=tuple(sorted(clause_ids)),
        requirement_ids=tuple(sorted(requirement_ids)),
        transition_ids=related_transitions,
        implementation_mapping_ids=(mapping.id,),
        source=_source_for(mapping),
        notes=(
            "Derived HLA specification seam from an implementation mapping; "
            "this is a planned surface and not implementation evidence."
        ),
    )


def _surfaces_by_id(
    model: DocumentModel,
    transition_machines: Mapping[str, tuple[Transition, StateMachine]],
) -> dict[str, ApiSurface]:
    surfaces = {item.id: item for item in model.api_surfaces}
    for mapping in model.implementations:
        surface_id = f"surface:{mapping.id}"
        if surface_id not in surfaces:
            surfaces[surface_id] = _surface_for_mapping(mapping, transition_machines)
    return surfaces


def _surfaces_by_transition(surfaces: tuple[ApiSurface, ...]) -> dict[str, tuple[str, ...]]:
    transition_surfaces: dict[str, list[str]] = defaultdict(list)
    for surface in surfaces:
        for transition_id in surface.transition_ids:
            transition_surfaces[transition_id].append(surface.id)
    return {key: tuple(sorted(value)) for key, value in transition_surfaces.items()}


def _requirement_test(
    requirement: Requirement,
    surface_index: Mapping[str, tuple[str, ...]],
    surfaces_by_id: Mapping[str, ApiSurface],
) -> VerificationTest:
    surface_ids = _surface_ids_for_transitions(requirement.transition_ids, surface_index)
    return VerificationTest(
        id=f"verify.requirement.{requirement.id}",
        title=f"Verify requirement {requirement.id}",
        kind="conformance",
        requirement_ids=(requirement.id,),
        transition_ids=requirement.transition_ids,
        api_surface_ids=surface_ids,
        implementation_mapping_ids=_mapping_ids_for_surfaces(surface_ids, surfaces_by_id),
        source=requirement.source,
        notes=(
            "Planned requirement verification slot. Populate command and evidence "
            "after an RTI implementation exists."
        ),
    )


def _transition_test(
    transition: Transition,
    surface_index: Mapping[str, tuple[str, ...]],
    surfaces_by_id: Mapping[str, ApiSurface],
) -> VerificationTest:
    surface_ids = surface_index.get(transition.id, ())
    return VerificationTest(
        id=f"verify.transition.{transition.id}",
        title=f"Verify transition {transition.id}",
        kind="trace",
        transition_ids=(transition.id,),
        requirement_ids=transition.requirement_ids,
        api_surface_ids=surface_ids,
        implementation_mapping_ids=_mapping_ids_for_surfaces(surface_ids, surfaces_by_id),
        source=transition.source,
        notes=(
            "Planned transition replay slot. It becomes executable once the "
            "implementation mapping has concrete evidence."
        ),
    )


def _verification_tests(
    model: DocumentModel,
    transition_machines: Mapping[str, tuple[Transition, StateMachine]],
    surface_index: Mapping[str, tuple[str, ...]],
    surfaces_by_id: Mapping[str, ApiSurface],
) -> tuple[VerificationTest, ...]:
    tests = {item.id: item for item in model.verification_tests}
    for requirement in model.requirements:
        test = _requirement_test(requirement, surface_index, surfaces_by_id)
        tests.setdefault(test.id, test)
    for transition, _machine in transition_machines.values():
        test = _transition_test(transition, surface_index, surfaces_by_id)
        tests.setdefault(test.id, test)
    return tuple(sorted(tests.values(), key=lambda item: item.id))


def _smoke_transition(machine: StateMachine) -> Transition | None:
    candidate = next(
        (
            item
            for item in machine.transitions
            if item.source_state in machine.initial_state_ids and item.target_state is not None
        ),
        None,
    )
    if candidate is None:
        candidate = next(
            (item for item in machine.transitions if item.source_state and item.target_state),
            None,
        )
    if candidate is None and machine.transitions:
        candidate = machine.transitions[0]
    return candidate


def _smoke_trace(
    machine: StateMachine,
    surface_index: Mapping[str, tuple[str, ...]],
    tests_by_id: Mapping[str, VerificationTest],
) -> StateTrace:
    candidate = _smoke_transition(machine)
    initial = machine.initial_state_ids[0] if machine.initial_state_ids else None
    if candidate is None:
        return StateTrace(
            id=f"trace.{machine.id}.smoke",
            machine_id=machine.id,
            title=f"Smoke trace for {machine.title}",
            initial_state_id=initial,
            steps=(),
            expected_final_state=None,
            requirement_ids=(),
            transition_ids=(),
            api_surface_ids=(),
            verification_test_ids=(),
            source=machine.source,
            notes=(
                "Derived planned trace seed. Diagram-derived transitions with incomplete "
                "targets remain blocked until their semantics are refined."
            ),
        )
    if initial is None:
        initial = candidate.source_state
    surface_ids = surface_index.get(candidate.id, ())
    verification_id = f"verify.transition.{candidate.id}"
    verification_ids = (verification_id,) if verification_id in tests_by_id else ()
    return StateTrace(
        id=f"trace.{machine.id}.smoke",
        machine_id=machine.id,
        title=f"Smoke trace for {machine.title}",
        initial_state_id=initial,
        steps=(
            TraceStep(
                id=f"{machine.id}.step-01",
                event=candidate.event,
                source_state=candidate.source_state,
                transition_id=candidate.id,
                target_state=candidate.target_state,
                requirement_ids=candidate.requirement_ids,
                api_surface_ids=surface_ids,
            ),
        ),
        expected_final_state=candidate.target_state,
        requirement_ids=candidate.requirement_ids,
        transition_ids=(candidate.id,),
        api_surface_ids=surface_ids,
        verification_test_ids=verification_ids,
        source=machine.source,
        notes=(
            "Derived planned trace seed. Diagram-derived transitions with incomplete "
            "targets remain blocked until their semantics are refined."
        ),
    )


def _state_traces(
    model: DocumentModel,
    surface_index: Mapping[str, tuple[str, ...]],
    tests: tuple[VerificationTest, ...],
) -> tuple[StateTrace, ...]:
    traces = {item.id: item for item in model.state_traces}
    tests_by_id = {item.id: item for item in tests}
    existing_machines = {item.machine_id for item in traces.values()}
    for machine in model.state_machines:
        if machine.id not in existing_machines:
            trace = _smoke_trace(machine, surface_index, tests_by_id)
            traces[trace.id] = trace
    return tuple(sorted(traces.values(), key=lambda item: item.id))


def build_hla_surface_contract(model: DocumentModel) -> DocumentModel:
    """Add missing API, verification, and trace planning surfaces."""
    transition_machines = _transition_machines(model)
    surfaces_by_id = _surfaces_by_id(model, transition_machines)
    surfaces = tuple(sorted(surfaces_by_id.values(), key=lambda item: item.id))
    surface_index = _surfaces_by_transition(surfaces)
    tests = _verification_tests(model, transition_machines, surface_index, surfaces_by_id)
    traces = _state_traces(model, surface_index, tests)
    payload = model.model_dump(mode="python")
    payload.update(
        {
            "api_surfaces": surfaces,
            "verification_tests": tests,
            "state_traces": traces,
        }
    )
    return DocumentModel.model_validate(payload)
