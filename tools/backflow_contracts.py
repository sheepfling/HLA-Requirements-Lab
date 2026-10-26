"""Pydantic contracts for the backflow issue ledger and export delta."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hla_lab.traceability.compliance_contract import BundleSource

BackflowResolution: TypeAlias = Literal[
    "corrected-in-lab",
    "source-conflict-dispositioned",
    "verified-in-umbra",
]
BackflowCategory: TypeAlias = Literal[
    "Clause, subsection, and source-boundary attribution",
    "Cross-source name discrepancy",
    "Incomplete, fragmented, or corrupted candidate text",
    "Missing requirement or service-flow candidates",
    "Table and structured-record extraction",
    "Umbra-local plan and traceability follow-ups",
]

RequirementField: TypeAlias = Literal[
    "id",
    "clause",
    "clause_id",
    "title",
    "statement",
    "machine_statement",
    "kind",
    "coverage_kind",
    "coverage_note",
    "transition_ids",
    "api_surface_scope",
    "api_surface_note",
    "api_surface_resolution",
    "extraction",
    "semantic_group_id",
    "source",
]
ReadableRequirementField: TypeAlias = Literal[
    "clause",
    "clause_id",
    "kind",
    "extraction",
    "semantic_group_id",
    "source",
]
ReadableChangeValue: TypeAlias = str | BundleSource | None


class BackflowIssue(BaseModel):
    """One reviewed issue from the source backflow ledger."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: Annotated[str, Field(min_length=1)]
    category: BackflowCategory
    location: Annotated[str, Field(min_length=1)]
    complaint: Annotated[str, Field(min_length=1)]
    candidate_records: Annotated[int, Field(ge=0)]
    resolution: BackflowResolution | None = None
    verification: Annotated[str, Field(min_length=1)]
    resolution_note: str | None = None
    document_id: Annotated[str, Field(min_length=1)]
    affected_requirement_ids: list[str]
    created_requirement_ids: Annotated[list[str], Field(default_factory=list)]


class BackflowSnapshot(BaseModel):
    """Versioned backflow ledger used as the input to delta generation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: Literal[1]
    source: Annotated[str, Field(min_length=1)]
    authority: Annotated[str, Field(min_length=1)]
    issues: list[BackflowIssue]

    @model_validator(mode="after")
    def validate_unique_issue_ids(self) -> BackflowSnapshot:
        issue_ids = [issue.id for issue in self.issues]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("backflow issue IDs must be unique")
        return self


class RequirementFieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before: ReadableChangeValue
    after: ReadableChangeValue


class RequirementDelta(BaseModel):
    """Field-level and hash evidence for one stable requirement ID."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1)]
    changed_fields: list[RequirementField]
    readable_changes: dict[ReadableRequirementField, RequirementFieldChange]
    before_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    after_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BundleDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: Annotated[str, Field(min_length=1)]
    corpus_revision: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CreatedRequirementDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1)]
    after_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class BackflowIssueDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1)]
    resolution: BackflowResolution
    document_id: Annotated[str, Field(min_length=1)]
    affected: list[RequirementDelta]
    created: list[CreatedRequirementDelta]


class UnattributedCreatedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: Annotated[str, Field(min_length=1)]
    change: Literal["created"]
    id: Annotated[str, Field(min_length=1)]
    after_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class UnattributedRemovedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: Annotated[str, Field(min_length=1)]
    change: Literal["removed"]
    id: Annotated[str, Field(min_length=1)]
    before_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class UnattributedChangedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: Annotated[str, Field(min_length=1)]
    change: Literal["changed"]
    id: Annotated[str, Field(min_length=1)]
    changed_fields: list[RequirementField]
    readable_changes: dict[ReadableRequirementField, RequirementFieldChange]
    before_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    after_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


UnattributedRequirementChange: TypeAlias = Annotated[
    UnattributedCreatedChange | UnattributedRemovedChange | UnattributedChangedRequirement,
    Field(discriminator="change"),
]


class BackflowExportDelta(BaseModel):
    """Versioned result of comparing the snapshot to two corpus bundles."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    baseline: BundleDigest
    candidate: BundleDigest
    issues: list[BackflowIssueDelta]
    unattributed_requirement_changes: list[UnattributedRequirementChange]
