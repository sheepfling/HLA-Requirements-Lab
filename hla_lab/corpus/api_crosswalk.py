"""Build generic semantic-to-binding API crosswalks.

The crosswalk deliberately keeps semantic mappings separate from exact source
declarations.  A method or protobuf message is only selected when the
source-derived name evidence supports it; otherwise the record remains
ambiguous, unmatched, or planned for a future projection.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from hla_lab.core.semantic_model import (
    ApiCrosswalk,
    ApiCrosswalkFile,
    ApiSurface,
    DocumentModel,
    ImplementationMapping,
    RequirementApiBinding,
    RequirementApiBindingFile,
)
from hla_lab.core.text import slugify

__all__ = [
    "ApiTarget",
    "build_api_crosswalk",
    "build_requirement_api_bindings",
    "write_api_crosswalk",
    "write_requirement_api_bindings",
]

BindingKind = Literal["native", "protocol", "language-adapter", "transport"]

@dataclass(frozen=True)
class ApiTarget:
    """A binding or projection target supplied by a standards profile."""

    name: str
    binding_kind: BindingKind
    language: str = "unspecified"
    protocol: str | None = None
    owner_by_interface: Mapping[str, str] = field(default_factory=dict)
    projection: bool = False

def _terms(value: str) -> tuple[str, ...]:
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    expanded = re.sub(r"[^A-Za-z0-9]+", " ", expanded.casefold())
    return tuple(item for item in expanded.split() if item)

def _surface_aliases(surface: ApiSurface) -> tuple[tuple[str, ...], ...]:
    terms = _terms(surface.name)
    aliases = [terms]
    if terms and terms[-1] in {"request", "response"}:
        aliases.append(terms[:-1])
    return tuple(alias for alias in aliases if alias)

def _mapping_terms(model: DocumentModel, mapping: ImplementationMapping) -> tuple[str, ...]:
    values = [mapping.interface_name]
    transitions = {
        transition.id: transition
        for machine in model.state_machines
        for transition in machine.transitions
    }
    for transition_id in mapping.transition_ids:
        transition = transitions.get(transition_id)
        if transition is not None:
            values.extend((transition.event, transition.action))
    return _terms(" ".join(value for value in values if value))

def _contains_term_sequence(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    """Return whether token sequence ``needle`` occurs at a token boundary."""
    width = len(needle)
    return any(haystack[index: index + width] == needle for index in range(len(haystack)))

_DECLARATION_MENTION_TAILS = {
    "callback",
    "callbacks",
    "invocation",
    "invocations",
    "service",
    "services",
}

_SEMANTIC_SURFACE_HINTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "getAutoProvideSwitch": (("auto", "provide", "switch"),),
    "localDeleteObjectInstance": (("local", "delete", "object", "instance"),),
    "publishObjectClassAttributes": (("publishing", "a", "class", "attribute"),),
    "synchronizationPointRegistrationFailed": (
        ("synchronization", "point", "registration", "failure"),
        ("synchronization", "point", "registration", "failed"),
        ("confirm", "synchronization", "point", "registration"),
    ),
    "synchronizationPointRegistrationSucceeded": (
        ("confirm", "synchronization", "point", "registration"),
    ),
    "unsubscribeObjectClassAttributes": (("unsubscribed", "class", "attributes"),),
    "unpublishObjectClassAttributes": (("unpublished", "class", "attributes"),),
}

def _surface_is_named_as_declaration(
    surface: ApiSurface,
    statement_terms: tuple[str, ...],
) -> bool:
    """Return whether a requirement explicitly names a surface as an API item."""
    for alias in _surface_aliases(surface):
        width = len(alias)
        for index in range(len(statement_terms) - width + 1):
            if statement_terms[index: index + width] != alias:
                continue
            end = index + width
            if end < len(statement_terms) and statement_terms[end] in _DECLARATION_MENTION_TAILS:
                return True
    for hint in _SEMANTIC_SURFACE_HINTS.get(surface.name, ()):
        if _contains_term_sequence(hint, statement_terms) or set(hint) <= set(statement_terms):
            return True
    return False

def _requirement_surface_candidates(
    model: DocumentModel,
    statement: str,
    language: str,
) -> tuple[ApiSurface, ...]:
    """Find source declarations explicitly named by a requirement statement.

    This is intentionally stricter than the semantic mapping matcher.  A
    phrase such as ``time advance grant`` is not enough by itself; the source
    declaration must be named as a service or callback.  That distinction
    prevents incidental prose references from becoming API links.
    """
    statement_terms = _terms(statement)
    return tuple(
        surface
        for surface in model.api_surfaces
        if surface.language == language
        and surface.binding_kind == "native"
        and _surface_is_named_as_declaration(surface, statement_terms)
    )

def _surface_candidates(
    model: DocumentModel,
    mapping: ImplementationMapping,
    target: ApiTarget,
) -> tuple[tuple[ApiSurface, str], ...]:
    if target.projection:
        return ()
    expected_owner = target.owner_by_interface.get(mapping.interface_kind)
    surfaces = tuple(
        item
        for item in model.api_surfaces
        if item.binding_kind == target.binding_kind
        and item.language == target.language
        and (target.protocol is None or item.protocol == target.protocol)
        and (expected_owner is None or item.owner == expected_owner)
    )
    mapping_terms = _mapping_terms(model, mapping)
    matches: list[tuple[ApiSurface, str, int]] = []
    for surface in surfaces:
        best: tuple[str, int] | None = None
        for alias in _surface_aliases(surface):
            if alias == mapping_terms:
                score = ("exact", 300)
            elif _contains_term_sequence(alias, mapping_terms):
                score = ("normalized", 200)
            elif set(alias) <= set(mapping_terms):
                score = ("token", 100)
            else:
                continue
            if best is None or score[1] > best[1]:
                best = score
        if best is not None:
            matches.append((surface, best[0], best[1]))
    if not matches:
        return ()
    highest = max(item[2] for item in matches)
    return tuple((surface, strategy) for surface, strategy, score in matches if score == highest)

def _crosswalk(
    model: DocumentModel,
    mapping: ImplementationMapping,
    target: ApiTarget,
) -> ApiCrosswalk:
    candidates = _surface_candidates(model, mapping, target)
    candidate_ids = tuple(sorted(surface.id for surface, _ in candidates))
    strategies = {strategy for _, strategy in candidates}
    status: Literal["matched", "ambiguous", "unmatched", "planned"]
    if target.projection:
        status = "planned"
        strategy: Literal["exact", "normalized", "token", "none", "projection"] = "projection"
        notes = "Future binding projection; no exact source declaration is expected yet."
        selected_ids: tuple[str, ...] = ()
    elif not candidates:
        status = "unmatched"
        strategy = "none"
        notes = "No source-derived declaration matched the semantic mapping name."
        selected_ids = ()
    elif len(candidates) > 1:
        status = "ambiguous"
        strategy = sorted(strategies)[0]  # type: ignore[assignment]
        notes = "Multiple source-derived declarations share the best name evidence."
        selected_ids = ()
    else:
        status = "matched"
        strategy = candidates[0][1]  # type: ignore[assignment]
        notes = "One source-derived declaration matched the semantic mapping name."
        selected_ids = candidate_ids
    return ApiCrosswalk(
        id=f"crosswalk.{mapping.id}.{target.name}",
        implementation_mapping_id=mapping.id,
        target=target.name,
        binding_kind=target.binding_kind,
        language=target.language,
        protocol=target.protocol,
        status=status,
        strategy=strategy,
        candidate_api_surface_ids=candidate_ids,
        selected_api_surface_ids=selected_ids,
        source=mapping.source,
        notes=notes,
    )

def build_api_crosswalk(
    model: DocumentModel,
    targets: tuple[ApiTarget, ...],
) -> tuple[ApiCrosswalk, ...]:
    """Build deterministic crosswalk rows for every mapping and target."""
    rows = [
        _crosswalk(model, mapping, target)
        for mapping in model.implementations
        for target in targets
    ]
    return tuple(sorted(rows, key=lambda item: item.id))

def write_api_crosswalk(output: Path, rows: tuple[ApiCrosswalk, ...]) -> None:
    """Write a Pydantic-validated source manifest."""
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = ApiCrosswalkFile(schema_version=1, api_crosswalks=rows)
    output.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

def _binding_relationship(
    mapping: ImplementationMapping,
    surfaces: tuple[ApiSurface, ...] = (),
) -> str:
    if mapping.interface_kind == "callback" or (
        surfaces and all(surface.interface_kind == "callback" for surface in surfaces)
    ):
        return "callback"
    if mapping.transition_ids:
        return "transition-backed"
    return "direct"

def build_requirement_api_bindings(
    model: DocumentModel,
    *,
    languages: tuple[str, ...] = ("cpp", "java"),
) -> tuple[RequirementApiBinding, ...]:
    """Build a complete requirement-to-declaration traceability surface.

    Requirements with an exact Java or C++ declaration are linked through the
    selected API crosswalk surface. Ambiguous and unmatched transition-backed
    requirements remain explicit gaps unless the requirement carries an
    explicit, reviewed ``all-overloads`` resolution with supporting rationale.
    Requirements that are intentionally clause-scoped or not API-facing receive
    a reviewed no-API classification.
    """
    surfaces_by_id = {item.id: item for item in model.api_surfaces}
    direct_surface_ids: dict[str, set[str]] = {}
    for surface in model.api_surfaces:
        if surface.language in languages:
            for requirement_id in surface.requirement_ids:
                direct_surface_ids.setdefault(requirement_id, set()).add(surface.id)

    mappings_by_transition: dict[str, tuple[ImplementationMapping, ...]] = {}
    for machine in model.state_machines:
        for transition in machine.transitions:
            mappings_by_transition[transition.id] = model.implementation_mappings_for_transition(
                transition.id
            )

    bindings: dict[str, RequirementApiBinding] = {}
    for requirement in model.ordered_requirements():
        direct_surfaces = sorted(direct_surface_ids.get(requirement.id, ()))
        for surface_id in direct_surfaces:
            surface = surfaces_by_id[surface_id]
            binding_id = (
                f"binding.{slugify(requirement.id)}.{surface.language}.{slugify(surface_id)}"
            )
            bindings[binding_id] = RequirementApiBinding(
                id=binding_id,
                requirement_id=requirement.id,
                api_surface_id=surface_id,
                candidate_api_surface_ids=(surface_id,),
                language=surface.language,
                relationship="callback" if surface.interface_kind == "callback" else "direct",
                status="matched",
                rationale="Requirement directly names the source-backed API surface.",
                source=surface.source or requirement.source,
            )

        mappings: dict[str, ImplementationMapping] = {}
        for transition_id in requirement.transition_ids:
            for mapping in mappings_by_transition.get(transition_id, ()):
                mappings[mapping.id] = mapping
        if not mappings or (requirement.api_surface_scope != "required" and not direct_surfaces):
            relationship = (
                requirement.api_surface_scope
                if requirement.api_surface_scope != "required"
                else (
                    "not-applicable"
                    if requirement.coverage_kind == "not-applicable"
                    else "cross-cutting"
                )
            )
            binding_id = f"binding.{slugify(requirement.id)}.no-api"
            bindings[binding_id] = RequirementApiBinding(
                id=binding_id,
                requirement_id=requirement.id,
                language="unspecified",
                relationship=relationship,
                status="reviewed",
                rationale=(
                    requirement.api_surface_note
                    or requirement.coverage_note
                    or "Requirement has no direct language API surface."
                ),
                source=requirement.source,
            )
            continue

        for language in languages:
            rows = tuple(
                row
                for mapping in mappings.values()
                for row in model.api_crosswalks_for_mapping(mapping.id)
                if row.target == language
            )
            mapped_selected = tuple(
                sorted(
                    {
                        surface_id
                        for row in rows
                        if row.status == "matched"
                        for surface_id in row.selected_api_surface_ids
                    }
                )
            )
            mapped_candidates = tuple(
                sorted(
                    {
                        surface_id
                        for row in rows
                        if row.status == "ambiguous"
                        for surface_id in row.candidate_api_surface_ids
                    }
                )
            )
            named_surfaces = _requirement_surface_candidates(
                model,
                requirement.statement,
                language,
            )
            named_by_name: dict[str, list[ApiSurface]] = {}
            for surface in named_surfaces:
                named_by_name.setdefault(surface.name, []).append(surface)
            if named_by_name:
                selected = tuple(
                    sorted(
                        surface.id
                        for surfaces in named_by_name.values()
                        if len(surfaces) == 1
                        for surface in surfaces
                    )
                )
                candidates = tuple(
                    sorted(
                        surface.id
                        for surfaces in named_by_name.values()
                        if len(surfaces) > 1
                        for surface in surfaces
                    )
                )
            else:
                selected = mapped_selected
                candidates = mapped_candidates
            if requirement.api_surface_resolution == "all-overloads":
                selected = tuple(sorted(set(selected) | set(candidates)))
                candidates = ()
            relationship = next(
                (
                    _binding_relationship(mapping)
                    for mapping in mappings.values()
                    if mapping.requirement_ids and requirement.id in mapping.requirement_ids
                ),
                "transition-backed",
            )
            source = next(
                (row.source for row in rows if row.source is not None),
                requirement.source,
            )
            if selected:
                for surface_id in selected:
                    binding_id = (
                        f"binding.{slugify(requirement.id)}.{language}.{slugify(surface_id)}"
                    )
                    bindings[binding_id] = RequirementApiBinding(
                        id=binding_id,
                        requirement_id=requirement.id,
                        api_surface_id=surface_id,
                        candidate_api_surface_ids=(surface_id,),
                        language=language,
                        relationship=_binding_relationship(
                            next(iter(mappings.values())),
                            (surfaces_by_id[surface_id],),
                        ),  # type: ignore[arg-type]
                        status="matched",
                        rationale=(
                            "Requirement names a standard service or callback; all source "
                            "overloads in the reviewed service family are in scope."
                            if requirement.api_surface_resolution == "all-overloads"
                            else "Requirement names a standard service or callback mapped to "
                                 "one source declaration."
                        ),
                        source=source,
                    )
            elif candidates:
                binding_id = f"binding.{slugify(requirement.id)}.{language}.ambiguous"
                candidate_surfaces = tuple(surfaces_by_id[surface_id] for surface_id in candidates)
                bindings[binding_id] = RequirementApiBinding(
                    id=binding_id,
                    requirement_id=requirement.id,
                    candidate_api_surface_ids=candidates,
                    language=language,
                    relationship=_binding_relationship(
                        next(iter(mappings.values())),
                        candidate_surfaces,
                    ),  # type: ignore[arg-type]
                    status="ambiguous",
                    rationale=(
                        "Multiple source declarations remain candidates for this requirement."
                    ),
                    source=source,
                )
            else:
                binding_id = f"binding.{slugify(requirement.id)}.{language}.unmatched"
                bindings[binding_id] = RequirementApiBinding(
                    id=binding_id,
                    requirement_id=requirement.id,
                    language=language,
                    relationship=relationship,  # type: ignore[arg-type]
                    status="unmatched",
                    rationale="No source declaration matched the requirement-backed transition.",
                    source=source,
                )
    return tuple(sorted(bindings.values(), key=lambda item: item.id))

def write_requirement_api_bindings(
    output: Path,
    bindings: tuple[RequirementApiBinding, ...],
) -> None:
    """Write a Pydantic-validated requirement-to-API manifest."""
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = RequirementApiBindingFile(schema_version=1, bindings=bindings)
    output.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
