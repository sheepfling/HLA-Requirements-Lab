"""Trace 2025 clause requirements to declarations owned by printed service headings.

The source clause title is the authority for a service family.  An exact
declaration name (after case/acronym normalization), or one of the four
reviewed callback aliases below, licenses a direct link to each overload of
that family.  Broader rules remain explicitly clause-scoped.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    ApiSurfaceFile,
    RequirementApiBindingFile,
    RequirementFile,
    load_document_model,
)
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.workspace import document_root

ALIASES: dict[str, tuple[str, ...]] = {
    "clause-4.15": (
        "synchronizationPointRegistrationSucceeded",
        "synchronizationPointRegistrationFailed",
    ),
    "clause-4.28": (
        "requestFederationRestoreSucceeded",
        "requestFederationRestoreFailed",
    ),
    "clause-6.3": ("objectInstanceNameReservationSucceeded",),
    "clause-6.6": ("multipleObjectInstanceNameReservationSucceeded",),
}
PREFIX = "requirement-candidate-content-clauses-"
FOM_SERVICE_NAMES = {
    "createFederationExecution",
    "createFederationExecutionWithMIM",
    "joinFederationExecution",
}


def _name_terms(value: str) -> tuple[str, ...]:
    # Split both ordinary camel case and acronym endings such as DDMSwitch.
    value = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", value)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _service_title(title: str) -> tuple[str, ...]:
    title = title.replace("\ufffd", "").strip()
    title = re.sub(r"^\d+(?:\.\d+)*\s+", "", title)
    if not re.search(r"\s+service\s*$", title, re.I):
        return ()
    title = re.sub(r"\s+service\s*$", "", title, flags=re.I)
    return _name_terms(title)


def _ancestors(clause_id: str | None):
    while clause_id:
        yield clause_id
        digits = clause_id.removeprefix("clause-")
        clause_id = clause_id.rsplit(".", 1)[0] if "." in digits else None


def _surface_family(model, requirement) -> tuple[str, tuple[str, ...]] | None:
    clauses = {clause.id: clause for clause in model.clauses}
    for clause_id in _ancestors(requirement.clause_id):
        clause = clauses.get(clause_id)
        if clause is None:
            continue
        title_terms = _service_title(clause.title)
        alias_names = ALIASES.get(clause_id, ())
        if not title_terms and not alias_names:
            continue
        ids = tuple(
            sorted(
                surface.id
                for surface in model.api_surfaces
                if surface.binding_kind == "native"
                and surface.language in {"java", "cpp"}
                and clause_id in surface.clause_ids
                and (
                    surface.name in alias_names
                    or (bool(title_terms) and _name_terms(surface.name) == title_terms)
                )
            )
        )
        if ids:
            return clause_id, ids
    return None


def proposal(root: Path):
    model = load_document_model(root, HLA_SOURCE)
    families: dict[str, tuple[str, tuple[str, ...]]] = {}
    scopes: dict[str, tuple[str, str]] = {}
    for requirement in model.requirements:
        if not requirement.id.startswith(PREFIX) or requirement.transition_ids:
            continue
        if requirement.extraction == "candidate":
            scopes[requirement.id] = (
                "not-applicable",
                "Reviewed explanatory table pointer; the adjacent table carries the normative cases.",
            )
            continue
        family = _surface_family(model, requirement)
        if family is not None:
            families[requirement.id] = family
        else:
            scopes[requirement.id] = (
                "cross-cutting",
                "Source clause rule with no one-to-one callable declaration in the reviewed Java/C++ API headings.",
            )
    rejection_ids = {
        requirement.id
        for requirement in model.requirements
        if requirement.id.startswith("req-fom-module-reject-")
    }
    if len(rejection_ids) != 7:
        raise ValueError(f"Expected seven reviewed FOM rejection cases; found {len(rejection_ids)}")
    fom_surfaces = tuple(
        sorted(
            surface.id
            for surface in model.api_surfaces
            if surface.binding_kind == "native"
            and surface.language in {"java", "cpp"}
            and surface.name in FOM_SERVICE_NAMES
        )
    )
    if not fom_surfaces:
        raise ValueError("No source-backed Create/Join FOM service declarations found")
    for requirement_id in rejection_ids:
        families[requirement_id] = ("clause-4.1.4.1", fom_surfaces)
    return families, scopes


def write(root: Path, families, scopes) -> None:
    requirement_path = root / "semantic/requirements.json"
    surface_path = root / "semantic/api-surfaces.json"
    binding_path = root / "semantic/api-requirement-bindings.json"
    requirements = RequirementFile.model_validate_json(requirement_path.read_text(encoding="utf-8"))
    surfaces = ApiSurfaceFile.model_validate_json(surface_path.read_text(encoding="utf-8"))
    changed_requirements = tuple(
        item.model_copy(
            update={
                "api_surface_scope": scopes[item.id][0],
                "api_surface_note": scopes[item.id][1],
            }
        )
        if item.id in scopes
        else item
        for item in requirements.requirements
    )
    reqs_by_surface: dict[str, set[str]] = defaultdict(set)
    for requirement_id, (_, surface_ids) in families.items():
        for surface_id in surface_ids:
            reqs_by_surface[surface_id].add(requirement_id)
    changed_surfaces = tuple(
        item.model_copy(
            update={
                "requirement_ids": tuple(
                    sorted(
                        set(
                            identifier
                            for identifier in item.requirement_ids
                            if not identifier.startswith(PREFIX)
                        )
                        | reqs_by_surface[item.id]
                    )
                ),
            }
        )
        for item in surfaces.api_surfaces
    )
    requirement_path.write_text(
        json.dumps(
            requirements.model_copy(update={"requirements": changed_requirements}).model_dump(
                mode="json"
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    surface_path.write_text(
        json.dumps(
            surfaces.model_copy(update={"api_surfaces": changed_surfaces}).model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    rebuilt = build_requirement_api_bindings(load_document_model(root, HLA_SOURCE))
    binding_path.write_text(
        json.dumps(
            RequirementApiBindingFile(schema_version=1, bindings=rebuilt).model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = document_root("hla-1516.1-2025", args.workspace_root)
    families, scopes = proposal(root)
    counts = Counter(scope for scope, _ in scopes.values())
    counts["direct-service-requirements"] = len(families)
    counts["direct-service-clauses"] = len({clause for clause, _ in families.values()})
    counts["direct-surface-links"] = sum(len(ids) for _, ids in families.values())
    print(dict(counts))
    if args.write:
        write(root, families, scopes)


if __name__ == "__main__":
    main()
