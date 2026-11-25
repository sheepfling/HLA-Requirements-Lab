"""Repair Requirements Lab service ownership and its declaration links.

The page-layout source puts PDF-navigation bookmarks at the start of a page,
then lays out visible service headings as several fixed blocks on one baseline.
Clause extraction must follow the visible headings rather than the final
navigation bookmark from the preceding service.
"""

from __future__ import annotations

import json
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    ApiSurfaceFile,
    Requirement,
    RequirementFile,
    RequirementApiBindingFile,
    load_document_model,
)
from hla_lab.core.semantic_model_records import _load_requirement_candidates
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.backflow_common import semantic_root

FIRST_PAGE = 258
LAST_PAGE = 285
REQUIREMENT_PREFIX = "requirement-candidate-content-clauses-10-support-services-page-"


def _write_model(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def repair_service_attribution(workspace_root: Path | None = None) -> tuple[str, ...]:
    """Apply source-derived service headings to persisted candidates on pp.258–285.

    Candidate IDs and wording remain untouched. Only the clause owner and its
    derived semantic group are refreshed from the layout parser. API declaration
    links are then reassigned from the actual service headings in the API source.
    """
    semantic = semantic_root(workspace_root)
    document_root = semantic.parent
    requirements_path = semantic / "requirements.json"
    surfaces_path = semantic / "api-surfaces.json"
    bindings_path = semantic / "api-requirement-bindings.json"

    requirements = RequirementFile.model_validate_json(
        requirements_path.read_text(encoding="utf-8")
    )
    candidates = tuple(
        item
        for item in _load_requirement_candidates(document_root, HLA_SOURCE)
        if item.id.startswith(REQUIREMENT_PREFIX)
    )
    candidates_by_path: dict[str, list[Requirement]] = {}
    for candidate in candidates:
        candidates_by_path.setdefault(candidate.source.path, []).append(candidate)

    corrected = []
    changed_ids: list[str] = []
    for requirement in requirements.requirements:
        suffix = requirement.id.removeprefix(REQUIREMENT_PREFIX)
        page_text = suffix.split("-", 1)[0]
        if (
            not requirement.id.startswith(REQUIREMENT_PREFIX)
            or not page_text.isdigit()
            or not FIRST_PAGE <= int(page_text) <= LAST_PAGE
        ):
            corrected.append(requirement)
            continue

        requirement_end = requirement.source.end_line or requirement.source.line
        overlapping = [
            candidate
            for candidate in candidates_by_path.get(requirement.source.path, ())
            if candidate.source.line <= requirement_end
            and (candidate.source.end_line or candidate.source.line) >= requirement.source.line
        ]
        if not overlapping:
            corrected.append(requirement)
            continue
        clauses = {candidate.clause for candidate in overlapping}
        if len(clauses) > 1:
            raise ValueError(f"Ambiguous visible heading for {requirement.id}: {sorted(clauses)}")
        source_candidate = overlapping[0]
        clause = source_candidate.clause
        if clause is None:
            raise ValueError(f"No visible clause heading for {requirement.id}")
        semantic_group_id = f"m16.clause.{clause}"
        updates = {
            "clause": clause,
            "clause_id": f"clause-{clause}",
            "semantic_group_id": semantic_group_id,
        }
        if any(getattr(requirement, key) != value for key, value in updates.items()):
            corrected.append(requirement.model_copy(update=updates))
            changed_ids.append(requirement.id)
        else:
            corrected.append(requirement)

    updated_requirements = requirements.model_copy(update={"requirements": tuple(corrected)})
    _write_model(requirements_path, updated_requirements)

    # Resolve each changed requirement to declarations whose source clause
    # matches its visible service heading. Preserve all other API ownership.
    model = load_document_model(document_root, HLA_SOURCE)
    requirement_by_id = {item.id: item for item in model.requirements}
    surfaces = ApiSurfaceFile.model_validate_json(surfaces_path.read_text(encoding="utf-8"))
    from tools.migrations.trace_15161_api_clause_surfaces import _surface_family

    requirement_ids_by_surface: dict[str, set[str]] = {}
    for requirement_id in changed_ids:
        family = _surface_family(model, requirement_by_id[requirement_id])
        if family is None:
            raise ValueError(f"No source API family for {requirement_id}")
        _clause_id, surface_ids = family
        for surface_id in surface_ids:
            requirement_ids_by_surface.setdefault(surface_id, set()).add(requirement_id)

    changed_id_set = set(changed_ids)
    updated_surfaces = surfaces.model_copy(
        update={
            "api_surfaces": tuple(
                item.model_copy(
                    update={
                        "requirement_ids": tuple(
                            sorted(
                                (set(item.requirement_ids) - changed_id_set)
                                | requirement_ids_by_surface.get(item.id, set())
                            )
                        )
                    }
                )
                for item in surfaces.api_surfaces
            )
        }
    )
    _write_model(surfaces_path, updated_surfaces)

    rebuilt = build_requirement_api_bindings(load_document_model(document_root, HLA_SOURCE))
    _write_model(
        bindings_path,
        RequirementApiBindingFile(schema_version=1, bindings=rebuilt),
    )
    return tuple(changed_ids)
