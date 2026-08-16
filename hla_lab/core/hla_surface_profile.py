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
    SourceRef,
    StateTrace,
    TraceStep,
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


def build_hla_surface_contract(model: DocumentModel) -> DocumentModel:
    """Attach complete HLA API, verification, and trace planning surfaces.

    Existing authored records remain authoritative.  The HLA projection fills
    only missing records from the already source-controlled implementation and
    state-machine records, so this operation never invents concrete code
    evidence or claims that a planned mapping has been implemented.
    """

    tr_id2_transition_machine = {
        transition.id: (transition, machine)
        for machine in model.state_machines
        for transition in machine.transitions
    }
    authored_surfaces = {item.id: item for item in model.api_surfaces}
    surfaces_by_id = dict(authored_surfaces)
    for mapping in model.implementations:
        related_transitions = tuple(
            transition_id
            for transition_id in mapping.transition_ids
            if transition_id in tr_id2_transition_machine
        )
        derived_requirement_ids: set[str] = set(mapping.requirement_ids)
        clause_ids: set[str] = set(mapping.clause_ids)
        for transition_id in related_transitions:
            transition, machine = tr_id2_transition_machine[transition_id]
            derived_requirement_ids.update(transition.requirement_ids)
            if transition.clause_id:
                clause_ids.add(transition.clause_id)
            if machine.clause_id:
                clause_ids.add(machine.clause_id)
        surface_id = f"surface:{mapping.id}"
        if surface_id in surfaces_by_id:
            continue
        language = "unspecified"
        if mapping.implementation_ref is not None:
            language = mapping.implementation_ref.language
        surfaces_by_id[surface_id] = ApiSurface(
            id=surface_id,
            name=mapping.interface_name,
            interface_kind=mapping.interface_kind,
            binding_kind="semantic",
            owner=HLA_API_OWNERS[mapping.interface_kind],
            language=language,
            signature=mapping.interface_name,
            clause_ids=tuple(sorted(clause_ids)),
            requirement_ids=tuple(sorted(derived_requirement_ids)),
            transition_ids=related_transitions,
            implementation_mapping_ids=(mapping.id,),
            source=_source_for(mapping),
            notes=(
                "Derived HLA specification seam from an implementation mapping; "
                "this is a planned surface and not implementation evidence."
            ),
        )

    surfaces = tuple(sorted(surfaces_by_id.values(), key=lambda item: item.id))
    surfaces_by_transition: dict[str, list[str]] = defaultdict(list)
    for surface in surfaces:
        for transition_id in surface.transition_ids:
            surfaces_by_transition[transition_id].append(surface.id)
    frozen_surfaces_by_transition = {
        key: tuple(sorted(value)) for key, value in surfaces_by_transition.items()
    }

    authored_tests = {item.id: item for item in model.verification_tests}
    tests_by_id = dict(authored_tests)
    for requirement in model.requirements:
        surface_ids = _surface_ids_for_transitions(
            requirement.transition_ids,
            frozen_surfaces_by_transition,
        )
        tests_by_id.setdefault(
            f"verify.requirement.{requirement.id}",
            VerificationTest(
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
            ),
        )
    for transition_id, (transition, _machine) in tr_id2_transition_machine.items():
        surface_ids = frozen_surfaces_by_transition.get(transition_id, ())
        tests_by_id.setdefault(
            f"verify.transition.{transition_id}",
            VerificationTest(
                id=f"verify.transition.{transition_id}",
                title=f"Verify transition {transition_id}",
                kind="trace",
                transition_ids=(transition_id,),
                requirement_ids=transition.requirement_ids,
                api_surface_ids=surface_ids,
                implementation_mapping_ids=_mapping_ids_for_surfaces(surface_ids, surfaces_by_id),
                source=transition.source,
                notes=(
                    "Planned transition replay slot. It becomes executable once the "
                    "implementation mapping has concrete evidence."
                ),
            ),
        )

    tests = tuple(sorted(tests_by_id.values(), key=lambda item: item.id))
    authored_traces = {item.id: item for item in model.state_traces}
    traces_by_id = dict(authored_traces)
    for machine in model.state_machines:
        if any(item.machine_id == machine.id for item in traces_by_id.values()):
            continue
        initial = machine.initial_state_ids[0] if machine.initial_state_ids else None
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
        if candidate is not None and initial is None:
            initial = candidate.source_state
        steps: tuple[TraceStep, ...] = ()
        transition_ids: tuple[str, ...] = ()
        requirement_ids: tuple[str, ...] = ()
        expected_final_state = None
        if candidate is not None:
            surface_ids = frozen_surfaces_by_transition.get(candidate.id, ())
            steps = (
                TraceStep(
                    id=f"{machine.id}.step-01",
                    event=candidate.event,
                    source_state=candidate.source_state,
                    transition_id=candidate.id,
                    target_state=candidate.target_state,
                    requirement_ids=candidate.requirement_ids,
                    api_surface_ids=surface_ids,
                ),
            )
            transition_ids = (candidate.id,)
            requirement_ids = candidate.requirement_ids
            expected_final_state = candidate.target_state
            api_surface_ids = surface_ids
        else:
            api_surface_ids = ()
        verification_ids = (
            tuple(item.id for item in tests if item.id == f"verify.transition.{candidate.id}")
            if candidate is not None
            else ()
        )
        traces_by_id[f"trace.{machine.id}.smoke"] = StateTrace(
            id=f"trace.{machine.id}.smoke",
            machine_id=machine.id,
            title=f"Smoke trace for {machine.title}",
            initial_state_id=initial,
            steps=steps,
            expected_final_state=expected_final_state,
            requirement_ids=requirement_ids,
            transition_ids=transition_ids,
            api_surface_ids=api_surface_ids,
            verification_test_ids=verification_ids,
            source=machine.source,
            notes=(
                "Derived planned trace seed. Diagram-derived tr_id2_transition_machine with "
                "incomplete "
                "targets remain blocked until their semantics are refined."
            ),
        )

    payload = model.model_dump(mode="python")
    payload.update(
        {
            "api_surfaces": surfaces,
            "verification_tests": tests,
            "state_traces": tuple(sorted(traces_by_id.values(), key=lambda item: item.id)),
        }
    )
    return DocumentModel.model_validate(payload)
