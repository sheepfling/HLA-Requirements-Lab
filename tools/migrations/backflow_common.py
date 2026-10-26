"""Shared paths and JSON helpers for the 1516.1 backflow repair."""

from __future__ import annotations

from pathlib import Path

from pydantic import ConfigDict

from hla_lab.core.semantic_model import (
    ApiSurface,
    ApiSurfaceFile,
    ContentBlock,
    ContentBlockFile,
    ContentElement,
    ContentElementFile,
    Requirement,
    RequirementApiBinding,
    RequirementApiBindingFile,
    RequirementFile,
    RequirementReview,
    RequirementReviewFile,
    SourceRef,
)
from hla_lab.paths import resources


class _MutableRequirement(Requirement):
    """Editable migration view based on the canonical requirement record."""

    model_config = ConfigDict(frozen=False, validate_assignment=True)


class _MutableRequirementFile(RequirementFile):
    """Requirement catalog draft used by idempotent backflow repair scripts."""

    model_config = ConfigDict(frozen=False, validate_assignment=True)

    requirements: list[_MutableRequirement]


class _MutableContentBlock(ContentBlock):
    model_config = ConfigDict(frozen=False, validate_assignment=True)


class _MutableContentBlockFile(ContentBlockFile):
    model_config = ConfigDict(frozen=False, validate_assignment=True)

    content_blocks: list[_MutableContentBlock]


class _MutableContentElement(ContentElement):
    model_config = ConfigDict(frozen=False, validate_assignment=True)


class _MutableContentElementFile(ContentElementFile):
    model_config = ConfigDict(frozen=False, validate_assignment=True)

    content_elements: list[_MutableContentElement]


class _MutableApiSurface(ApiSurface):
    model_config = ConfigDict(frozen=False, validate_assignment=True)


class _MutableApiSurfaceFile(ApiSurfaceFile):
    model_config = ConfigDict(frozen=False, validate_assignment=True)

    api_surfaces: list[_MutableApiSurface]


class _MutableRequirementReview(RequirementReview):
    model_config = ConfigDict(frozen=False, validate_assignment=True)


class _MutableRequirementReviewFile(RequirementReviewFile):
    model_config = ConfigDict(frozen=False, validate_assignment=True)

    reviews: list[_MutableRequirementReview]


class _MutableRequirementApiBinding(RequirementApiBinding):
    model_config = ConfigDict(frozen=False, validate_assignment=True)


class _MutableRequirementApiBindingFile(RequirementApiBindingFile):
    model_config = ConfigDict(frozen=False, validate_assignment=True)

    bindings: list[_MutableRequirementApiBinding]


PAGE_216 = "requirement-candidate-content-clauses-08-time-management-page-216-l"
FEDERATION = "requirement-candidate-content-clauses-04-federation-management-page-"
OBJECTS = "requirement-candidate-content-clauses-06-object-management-page-"
TIME = "requirement-candidate-content-clauses-08-time-management-page-"
DDM = "requirement-candidate-content-clauses-09-data-distribution-management-page-"
SUPPORT = "requirement-candidate-content-clauses-10-support-services-page-"
OWNERSHIP = "requirement-candidate-content-clauses-07-ownership-management-page-"
DECLARATION = "requirement-candidate-content-clauses-05-declaration-management-page-"
MOM = "requirement-candidate-content-clauses-11-management-object-model-page-"


def semantic_root(workspace_root: Path | None = None) -> Path:
    return resources(workspace_root).document("hla-1516.1-2025").semantic


def omt_semantic_root(workspace_root: Path | None = None) -> Path:
    return resources(workspace_root).document("hla-1516.2-2025").semantic


def _read_requirement_file(path: Path) -> _MutableRequirementFile:
    source = RequirementFile.model_validate_json(path.read_text(encoding="utf-8"))
    requirements = [
        _MutableRequirement.model_validate(item.model_dump(mode="python", exclude_unset=True))
        for item in source.requirements
    ]
    return _MutableRequirementFile(schema_version=source.schema_version, requirements=requirements)


def _write_requirement_file(path: Path, payload: _MutableRequirementFile) -> None:
    validated = RequirementFile(
        schema_version=payload.schema_version,
        requirements=tuple(
            Requirement.model_validate(item.model_dump(mode="python", exclude_unset=True))
            for item in payload.requirements
        ),
    )
    path.write_text(
        validated.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )


def _read_requirements() -> _MutableRequirementFile:
    return _read_requirement_file(semantic_root() / "requirements.json")


def _write_requirements(payload: _MutableRequirementFile) -> None:
    _write_requirement_file(semantic_root() / "requirements.json", payload)


def _read_content_blocks() -> _MutableContentBlockFile:
    source = ContentBlockFile.model_validate_json(
        (semantic_root() / "content-blocks.json").read_text(encoding="utf-8")
    )
    blocks = [
        _MutableContentBlock.model_validate(item.model_dump(mode="python", exclude_unset=True))
        for item in source.content_blocks
    ]
    return _MutableContentBlockFile(schema_version=source.schema_version, content_blocks=blocks)


def _write_content_blocks(payload: _MutableContentBlockFile) -> None:
    validated = ContentBlockFile(
        schema_version=payload.schema_version,
        content_blocks=tuple(
            ContentBlock.model_validate(item.model_dump(mode="python", exclude_unset=True))
            for item in payload.content_blocks
        ),
    )
    (semantic_root() / "content-blocks.json").write_text(
        validated.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )


def _read_content_elements() -> _MutableContentElementFile:
    source = ContentElementFile.model_validate_json(
        (semantic_root() / "content-elements.json").read_text(encoding="utf-8")
    )
    elements = [
        _MutableContentElement.model_validate(item.model_dump(mode="python", exclude_unset=True))
        for item in source.content_elements
    ]
    return _MutableContentElementFile(
        schema_version=source.schema_version, content_elements=elements
    )


def _write_content_elements(payload: _MutableContentElementFile) -> None:
    validated = ContentElementFile(
        schema_version=payload.schema_version,
        content_elements=tuple(
            ContentElement.model_validate(item.model_dump(mode="python", exclude_unset=True))
            for item in payload.content_elements
        ),
    )
    (semantic_root() / "content-elements.json").write_text(
        validated.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )


def _read_api_surfaces() -> _MutableApiSurfaceFile:
    source = ApiSurfaceFile.model_validate_json(
        (semantic_root() / "api-surfaces.json").read_text(encoding="utf-8")
    )
    surfaces = [
        _MutableApiSurface.model_validate(item.model_dump(mode="python", exclude_unset=True))
        for item in source.api_surfaces
    ]
    return _MutableApiSurfaceFile(schema_version=source.schema_version, api_surfaces=surfaces)


def _write_api_surfaces(payload: _MutableApiSurfaceFile) -> None:
    validated = ApiSurfaceFile(
        schema_version=payload.schema_version,
        api_surfaces=tuple(
            ApiSurface.model_validate(item.model_dump(mode="python", exclude_unset=True))
            for item in payload.api_surfaces
        ),
    )
    (semantic_root() / "api-surfaces.json").write_text(
        validated.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )


def _read_requirement_reviews() -> _MutableRequirementReviewFile:
    source = RequirementReviewFile.model_validate_json(
        (semantic_root() / "requirement-review.json").read_text(encoding="utf-8")
    )
    reviews = [
        _MutableRequirementReview.model_validate(item.model_dump(mode="python", exclude_unset=True))
        for item in source.reviews
    ]
    return _MutableRequirementReviewFile(schema_version=source.schema_version, reviews=reviews)


def _write_requirement_reviews(payload: _MutableRequirementReviewFile) -> None:
    validated = RequirementReviewFile(
        schema_version=payload.schema_version,
        reviews=tuple(
            RequirementReview.model_validate(item.model_dump(mode="python", exclude_unset=True))
            for item in payload.reviews
        ),
    )
    (semantic_root() / "requirement-review.json").write_text(
        validated.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )


def _read_requirement_api_bindings() -> _MutableRequirementApiBindingFile:
    source = RequirementApiBindingFile.model_validate_json(
        (semantic_root() / "api-requirement-bindings.json").read_text(encoding="utf-8")
    )
    bindings = [
        _MutableRequirementApiBinding.model_validate(
            item.model_dump(mode="python", exclude_unset=True)
        )
        for item in source.bindings
    ]
    return _MutableRequirementApiBindingFile(
        schema_version=source.schema_version, bindings=bindings
    )


def _write_requirement_api_bindings(payload: _MutableRequirementApiBindingFile) -> None:
    validated = RequirementApiBindingFile(
        schema_version=payload.schema_version,
        bindings=tuple(
            RequirementApiBinding.model_validate(item.model_dump(mode="python", exclude_unset=True))
            for item in payload.bindings
        ),
    )
    (semantic_root() / "api-requirement-bindings.json").write_text(
        validated.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )


def _set_statement(record: _MutableRequirement, statement: str, line: int, end_line: int) -> None:
    record.statement = statement
    record.machine_statement = statement
    record.source = SourceRef(path=record.source.path, line=line, end_line=end_line)
    record.title = f"Normative statement at {record.source.path}:{line}"


def _set_clause(record: _MutableRequirement, clause: str) -> None:
    record.clause = clause
    record.clause_id = f"clause-{clause}"
    record.semantic_group_id = f"m16.clause.{clause}"
