"""Portable, HLA-neutral contracts for an external compliance sidecar.

The corpus exporter produces ``CorpusBundle`` records.  An implementation
repository produces ``ImplementationManifest`` records.  The verifier joins
them by document ID, semantic mapping ID, and binding target without importing
RTI code or this repository's internal document loaders.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AdapterDocumentRequest",
    "AdapterExpectedBinding",
    "AdapterRequest",
    "AdapterResponse",
    "BundleCrosswalk",
    "BundleDocument",
    "BundleMapping",
    "BundleParameter",
    "BundleRequirement",
    "BundleRequirementApiBinding",
    "BundleSource",
    "BundleSurface",
    "BundleTransition",
    "ComplianceCoverage",
    "ComplianceFinding",
    "ComplianceResult",
    "ComplianceTestCase",
    "ComplianceTestCatalog",
    "CorpusBundle",
    "EvidenceRecord",
    "ImplementationBinding",
    "ImplementationManifest",
]


class ContractRecord(BaseModel):
    """Strict base for portable sidecar records."""

    model_config = ConfigDict(extra="forbid")


class BundleRequirement(ContractRecord):
    id: str = Field(min_length=1)
    clause_id: str | None = None
    title: str = ""
    statement: str = ""


class BundleTransition(ContractRecord):
    id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    event: str = ""
    source_state: str | None = None
    target_state: str | None = None
    requirement_ids: tuple[str, ...] = ()


class BundleMapping(ContractRecord):
    id: str = Field(min_length=1)
    interface_kind: str = Field(min_length=1)
    interface_name: str = Field(min_length=1)
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()


class BundleParameter(ContractRecord):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    direction: Literal["in", "out", "inout", "return"] = "in"
    optional: bool = False


class BundleSource(ContractRecord):
    """Portable source location for a semantic or declaration record."""

    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_span(self) -> BundleSource:
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError("bundle source end_line must not precede line")
        return self


class BundleSurface(ContractRecord):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    binding_kind: Literal["semantic", "native", "protocol", "language-adapter", "transport"]
    owner: str = Field(min_length=1)
    language: str = Field(min_length=1)
    protocol: str | None = None
    signature: str = Field(min_length=1)
    parameters: tuple[BundleParameter, ...] = ()
    result_type: str | None = None
    exception_types: tuple[str, ...] = ()
    source: BundleSource | None = None


class BundleCrosswalk(ContractRecord):
    id: str = Field(min_length=1)
    implementation_mapping_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    binding_kind: Literal["native", "protocol", "language-adapter", "transport"]
    language: str = Field(min_length=1)
    protocol: str | None = None
    status: Literal["matched", "ambiguous", "unmatched", "planned"]
    candidate_api_surface_ids: tuple[str, ...] = ()
    selected_api_surface_ids: tuple[str, ...] = ()


class BundleRequirementApiBinding(ContractRecord):
    """Portable requirement-to-language-API traceability record."""

    id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    api_surface_id: str | None = None
    candidate_api_surface_ids: tuple[str, ...] = ()
    language: str = Field(min_length=1)
    relationship: Literal[
        "direct",
        "transition-backed",
        "callback",
        "not-applicable",
        "cross-cutting",
    ]
    status: Literal["candidate", "reviewed", "matched", "ambiguous", "unmatched"]
    rationale: str = Field(min_length=1)
    source: BundleSource

    @model_validator(mode="after")
    def validate_binding_shape(self) -> BundleRequirementApiBinding:
        candidates = set(self.candidate_api_surface_ids)
        if self.api_surface_id is not None and self.api_surface_id not in candidates:
            raise ValueError("selected API surface must be one of the binding candidates")
        if self.status == "matched" and self.api_surface_id is None:
            raise ValueError("matched requirement API bindings must select an API surface")
        if self.status == "ambiguous" and (self.api_surface_id is not None or len(candidates) < 2):
            raise ValueError("ambiguous requirement API bindings need multiple candidates")
        if self.status == "unmatched" and candidates:
            raise ValueError("unmatched requirement API bindings cannot have candidates")
        if self.relationship in {"not-applicable", "cross-cutting"} and candidates:
            raise ValueError("non-API requirement bindings cannot have API candidates")
        if (
            self.relationship not in {"not-applicable", "cross-cutting"}
            and self.status in {"candidate", "reviewed", "matched", "ambiguous"}
            and not candidates
        ):
            raise ValueError("API requirement bindings need a selected or candidate surface")
        return self


class BundleDocument(ContractRecord):
    document_id: str = Field(min_length=1)
    requirements: tuple[BundleRequirement, ...] = ()
    transitions: tuple[BundleTransition, ...] = ()
    mappings: tuple[BundleMapping, ...] = ()
    api_surfaces: tuple[BundleSurface, ...] = ()
    api_crosswalks: tuple[BundleCrosswalk, ...] = ()
    requirement_api_bindings: tuple[BundleRequirementApiBinding, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> BundleDocument:
        class IdentifiedRecord(Protocol):
            id: str

        def unique(label: str, values: tuple[IdentifiedRecord, ...]) -> set[str]:
            identifiers = [item.id for item in values]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{self.document_id}: duplicate {label} IDs")
            return set(identifiers)

        requirement_ids = unique("requirement", self.requirements)
        transition_ids = unique("transition", self.transitions)
        mapping_ids = unique("mapping", self.mappings)
        surface_ids = unique("API surface", self.api_surfaces)
        unique("API crosswalk", self.api_crosswalks)
        unique("requirement API binding", self.requirement_api_bindings)
        for transition in self.transitions:
            missing = set(transition.requirement_ids) - requirement_ids
            if missing:
                raise ValueError(
                    f"{self.document_id}: transition {transition.id} references "
                    f"missing requirements {sorted(missing)}"
                )
        for mapping in self.mappings:
            missing_requirements = set(mapping.requirement_ids) - requirement_ids
            missing_transitions = set(mapping.transition_ids) - transition_ids
            if missing_requirements or missing_transitions:
                raise ValueError(
                    f"{self.document_id}: mapping {mapping.id} has unresolved references "
                    f"requirements={sorted(missing_requirements)} "
                    f"transitions={sorted(missing_transitions)}"
                )
        for crosswalk in self.api_crosswalks:
            if crosswalk.implementation_mapping_id not in mapping_ids:
                raise ValueError(
                    f"{self.document_id}: crosswalk {crosswalk.id} references missing mapping "
                    f"{crosswalk.implementation_mapping_id}"
                )
            missing_candidates = set(crosswalk.candidate_api_surface_ids) - surface_ids
            missing_selected = set(crosswalk.selected_api_surface_ids) - surface_ids
            if missing_candidates or missing_selected:
                raise ValueError(
                    f"{self.document_id}: crosswalk {crosswalk.id} has unresolved surfaces "
                    f"candidates={sorted(missing_candidates)} "
                    f"selected={sorted(missing_selected)}"
                )
            if not set(crosswalk.selected_api_surface_ids) <= set(
                crosswalk.candidate_api_surface_ids
            ):
                raise ValueError(
                    f"{self.document_id}: crosswalk {crosswalk.id} selects a non-candidate surface"
                )
            candidates = len(crosswalk.candidate_api_surface_ids)
            selected = len(crosswalk.selected_api_surface_ids)
            if crosswalk.status == "matched" and selected != 1:
                raise ValueError(
                    f"{self.document_id}: matched crosswalk {crosswalk.id} must select one surface"
                )
            if crosswalk.status == "ambiguous" and candidates < 2:
                raise ValueError(
                    f"{self.document_id}: ambiguous crosswalk {crosswalk.id} needs candidates"
                )
            if crosswalk.status in {"unmatched", "planned"} and candidates:
                raise ValueError(
                    f"{self.document_id}: {crosswalk.status} crosswalk {crosswalk.id} "
                    "cannot contain candidates"
                )
        for binding in self.requirement_api_bindings:
            if binding.requirement_id not in requirement_ids:
                raise ValueError(
                    f"{self.document_id}: requirement API binding {binding.id} references "
                    f"missing requirement {binding.requirement_id}"
                )
            missing_candidates = set(binding.candidate_api_surface_ids) - surface_ids
            if missing_candidates:
                raise ValueError(
                    f"{self.document_id}: requirement API binding {binding.id} has unresolved "
                    f"candidate surfaces {sorted(missing_candidates)}"
                )
            if binding.api_surface_id is not None:
                if binding.api_surface_id not in surface_ids:
                    raise ValueError(
                        f"{self.document_id}: requirement API binding {binding.id} selects "
                        f"missing surface {binding.api_surface_id}"
                    )
                selected = next(
                    item for item in self.api_surfaces if item.id == binding.api_surface_id
                )
                if binding.language != selected.language:
                    raise ValueError(
                        f"{self.document_id}: requirement API binding {binding.id} language "
                        f"{binding.language} does not match selected surface language "
                        f"{selected.language}"
                    )
        return self


class CorpusBundle(ContractRecord):
    """Portable semantic slice consumed by an external implementation repo."""

    schema_version: int = Field(ge=1)
    bundle_id: str = Field(min_length=1)
    corpus_revision: str = Field(min_length=1)
    documents: tuple[BundleDocument, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_documents(self) -> CorpusBundle:
        identifiers = [item.document_id for item in self.documents]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("corpus bundle document IDs must be unique")
        return self


class EvidenceRecord(ContractRecord):
    """One externally produced build, test, trace, or review observation."""

    id: str = Field(min_length=1)
    kind: Literal[
        "build", "compile", "unit-test", "integration-test", "trace", "review", "artifact"
    ]
    status: Literal["planned", "passed", "failed", "blocked", "observed"]
    execution_mode: Literal["real", "mocked", "simulated", "unknown"] = "unknown"
    review_status: Literal["unreviewed", "accepted", "rejected"] = "unreviewed"
    reviewer: str | None = None
    reviewed_at: str | None = None
    command: str | None = None
    artifact: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def validate_review(self) -> EvidenceRecord:
        if self.review_status == "accepted" and not self.reviewer:
            raise ValueError("accepted evidence must name a reviewer")
        if self.review_status == "accepted" and not self.reviewed_at:
            raise ValueError("accepted evidence must include a review timestamp")
        return self


class ComplianceTestCase(ContractRecord):
    """One RTI-owned behavioral test mapped to a portable corpus seam."""

    id: str = Field(min_length=1)
    kind: Literal["build", "compile", "unit-test", "integration-test", "trace"]
    runner: str = Field(min_length=1)
    selector: str = Field(min_length=1)
    result_selector: str = Field(min_length=1)
    command: str | None = None
    document_id: str = Field(min_length=1)
    implementation_mapping_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    language: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    api_surface_ids: tuple[str, ...] = Field(min_length=1)
    execution_mode: Literal["real", "mocked", "simulated", "unknown"]
    notes: str = ""

    @model_validator(mode="after")
    def validate_surfaces(self) -> ComplianceTestCase:
        if any(not item for item in self.api_surface_ids):
            raise ValueError("compliance test API surface IDs cannot be empty")
        if len(self.api_surface_ids) != len(set(self.api_surface_ids)):
            raise ValueError("compliance test API surface IDs must be unique")
        return self


class ComplianceTestCatalog(ContractRecord):
    """Validated RTI-owned catalog consumed by test-result adapters."""

    schema_version: int = Field(ge=1)
    tests: tuple[ComplianceTestCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_test_ids(self) -> ComplianceTestCatalog:
        identifiers = [item.id for item in self.tests]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("compliance test catalog IDs must be unique")
        return self


class ImplementationBinding(ContractRecord):
    """Implementation-owned mapping and evidence links."""

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    implementation_mapping_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    language: str = Field(min_length=1)
    status: Literal["planned", "partial", "implemented", "verified", "not_applicable", "deferred"]
    api_surface_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    notes: str = ""


class ImplementationManifest(ContractRecord):
    """Implementation-repository input accepted by the sidecar verifier."""

    schema_version: int = Field(ge=1)
    manifest_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    corpus_revision: str = Field(min_length=1)
    document_ids: tuple[str, ...] = Field(min_length=1)
    targets: tuple[str, ...] = Field(min_length=1)
    coverage_mode: Literal["complete", "partial"] = "complete"
    bindings: tuple[ImplementationBinding, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()

    @model_validator(mode="after")
    def validate_manifest(self) -> ImplementationManifest:
        binding_ids = [item.id for item in self.bindings]
        evidence_ids = [item.id for item in self.evidence]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("implementation binding IDs must be unique")
        binding_keys = [
            (item.document_id, item.implementation_mapping_id, item.target)
            for item in self.bindings
        ]
        if len(binding_keys) != len(set(binding_keys)):
            raise ValueError("implementation binding document/mapping/target keys must be unique")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        if len(self.document_ids) != len(set(self.document_ids)):
            raise ValueError("implementation document IDs must be unique")
        if len(self.targets) != len(set(self.targets)):
            raise ValueError("implementation targets must be unique")
        known_evidence = set(evidence_ids)
        for binding in self.bindings:
            if binding.document_id not in self.document_ids:
                raise ValueError(
                    f"binding {binding.id} targets an undeclared document {binding.document_id}"
                )
            if binding.target not in self.targets:
                raise ValueError(
                    f"binding {binding.id} targets an undeclared target {binding.target}"
                )
            missing = set(binding.evidence_ids) - known_evidence
            if missing:
                raise ValueError(
                    f"binding {binding.id} references missing evidence {sorted(missing)}"
                )
        return self


class AdapterExpectedBinding(ContractRecord):
    """One binding target offered to an external RTI adapter."""

    implementation_mapping_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    binding_kind: Literal["native", "protocol", "language-adapter", "transport"]
    language: str = Field(min_length=1)
    interface_kind: str = Field(min_length=1)
    interface_name: str = Field(min_length=1)
    crosswalk_status: Literal["matched", "ambiguous", "unmatched", "planned"]
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    candidate_api_surface_ids: tuple[str, ...] = ()
    selected_api_surface_ids: tuple[str, ...] = ()
    api_surfaces: tuple[BundleSurface, ...] = ()


class AdapterDocumentRequest(ContractRecord):
    """The portion of a bundle assigned to one adapter invocation."""

    document_id: str = Field(min_length=1)
    bindings: tuple[AdapterExpectedBinding, ...] = ()


class AdapterRequest(ContractRecord):
    """JSON request sent to an RTI adapter over stdin."""

    schema_version: int = Field(ge=1)
    request_id: str = Field(min_length=1)
    bundle_id: str = Field(min_length=1)
    corpus_revision: str = Field(min_length=1)
    documents: tuple[AdapterDocumentRequest, ...] = Field(min_length=1)


class AdapterResponse(ContractRecord):
    """JSON response returned by an RTI adapter over stdout."""

    schema_version: int = Field(ge=1)
    request_id: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    coverage_mode: Literal["complete", "partial"] = "complete"
    bindings: tuple[ImplementationBinding, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()

    @model_validator(mode="after")
    def reject_accepted_evidence(self) -> AdapterResponse:
        if any(item.review_status == "accepted" for item in self.evidence):
            raise ValueError(
                "adapter responses cannot carry accepted evidence; approval is a separate step"
            )
        return self


class ComplianceFinding(ContractRecord):
    """Portable verifier diagnostic."""

    code: str = Field(min_length=1)
    severity: Literal["error", "warning", "info"]
    record_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ComplianceCoverage(ContractRecord):
    """Requirement, transition, API, and binding testing coverage summary."""

    expected_binding_count: int = Field(default=0, ge=0)
    present_binding_count: int = Field(default=0, ge=0)
    tested_binding_count: int = Field(default=0, ge=0)
    verified_binding_count: int = Field(default=0, ge=0)
    expected_requirement_count: int = Field(default=0, ge=0)
    requirements_with_verified_evidence_count: int = Field(default=0, ge=0)
    expected_transition_count: int = Field(default=0, ge=0)
    transitions_with_verified_evidence_count: int = Field(default=0, ge=0)
    expected_api_surface_count: int = Field(default=0, ge=0)
    api_surfaces_with_verified_evidence_count: int = Field(default=0, ge=0)
    binding_coverage: float = Field(default=0.0, ge=0, le=1)
    requirement_coverage: float = Field(default=0.0, ge=0, le=1)
    transition_coverage: float = Field(default=0.0, ge=0, le=1)
    api_surface_coverage: float = Field(default=0.0, ge=0, le=1)
    accepted_evidence_count: int = Field(default=0, ge=0)
    accepted_real_evidence_count: int = Field(default=0, ge=0)
    fully_verified: bool = False
    untested_binding_keys: tuple[str, ...] = ()
    untested_requirement_ids: tuple[str, ...] = ()
    untested_transition_ids: tuple[str, ...] = ()
    unverified_api_surface_ids: tuple[str, ...] = ()
    unaccepted_evidence_ids: tuple[str, ...] = ()
    non_real_evidence_ids: tuple[str, ...] = ()


class ComplianceResult(ContractRecord):
    """CI-friendly sidecar result."""

    schema_version: int = Field(ge=1)
    bundle_id: str = Field(min_length=1)
    manifest_id: str = Field(min_length=1)
    passed: bool
    binding_counts: dict[str, int] = Field(default_factory=dict)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    coverage: ComplianceCoverage = Field(default_factory=ComplianceCoverage)
    findings: tuple[ComplianceFinding, ...] = ()
