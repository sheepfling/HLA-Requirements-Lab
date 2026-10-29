"""Portable, HLA-neutral contracts for an external compliance sidecar.

The corpus exporter produces ``CorpusBundle`` records.  An implementation
repository produces ``ImplementationManifest`` records.  The verifier joins
them by document ID, semantic mapping ID, and binding target without importing
RTI code or this repository's internal document loaders.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from typing import Annotated, Literal, Protocol

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
    """One ordered, source-addressable requirement in a portable document."""

    id: Annotated[str, Field(min_length=1)]
    # ``ordinal`` is a document-local presentation number.  It is deliberately
    # not the semantic identity; ``id`` remains the only join key.
    ordinal: Annotated[int | None, Field(ge=1)] = None
    clause: str | None = None
    clause_id: str | None = None
    title: str = ""
    statement: str = ""
    machine_statement: str = ""
    kind: Literal["summary", "detailed"] = "detailed"
    coverage_kind: Literal["transition", "cross-cutting", "document-wide", "not-applicable"] = (
        "transition"
    )
    coverage_note: str = ""
    transition_ids: tuple[str, ...] = ()
    api_surface_scope: Literal["required", "cross-cutting", "not-applicable"] = "required"
    api_surface_note: str = ""
    api_surface_resolution: Literal["strict", "all-overloads"] = "strict"
    extraction: Literal["explicit", "candidate"] = "explicit"
    semantic_group_id: str | None = None
    source: BundleSource | None = None
    additional_sources: tuple[BundleSource, ...] = ()


class BundleTransition(ContractRecord):
    id: Annotated[str, Field(min_length=1)]
    machine_id: Annotated[str, Field(min_length=1)]
    event: str = ""
    source_state: str | None = None
    target_state: str | None = None
    requirement_ids: tuple[str, ...] = ()


class BundleMapping(ContractRecord):
    id: Annotated[str, Field(min_length=1)]
    interface_kind: Annotated[str, Field(min_length=1)]
    interface_name: Annotated[str, Field(min_length=1)]
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()


class BundleParameter(ContractRecord):
    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    type: Annotated[str, Field(min_length=1)]
    direction: Literal["in", "out", "inout", "return"] = "in"
    optional: bool = False


class BundleSource(ContractRecord):
    """Portable source location for a semantic or declaration record."""

    path: Annotated[str, Field(min_length=1)]
    line: Annotated[int, Field(ge=1)]
    end_line: Annotated[int | None, Field(ge=1)] = None

    @model_validator(mode="after")
    def validate_span(self) -> BundleSource:
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError("bundle source end_line must not precede line")
        return self


class BundleSurface(ContractRecord):
    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    binding_kind: Literal["semantic", "native", "protocol", "language-adapter", "transport"]
    owner: Annotated[str, Field(min_length=1)]
    language: Annotated[str, Field(min_length=1)]
    protocol: str | None = None
    signature: Annotated[str, Field(min_length=1)]
    parameters: tuple[BundleParameter, ...] = ()
    result_type: str | None = None
    exception_types: tuple[str, ...] = ()
    source: BundleSource | None = None


class BundleCrosswalk(ContractRecord):
    id: Annotated[str, Field(min_length=1)]
    implementation_mapping_id: Annotated[str, Field(min_length=1)]
    target: Annotated[str, Field(min_length=1)]
    binding_kind: Literal["native", "protocol", "language-adapter", "transport"]
    language: Annotated[str, Field(min_length=1)]
    protocol: str | None = None
    status: Literal["matched", "ambiguous", "unmatched", "planned"]
    candidate_api_surface_ids: tuple[str, ...] = ()
    selected_api_surface_ids: tuple[str, ...] = ()


class BundleRequirementApiBinding(ContractRecord):
    """Portable requirement-to-language-API traceability record."""

    id: Annotated[str, Field(min_length=1)]
    requirement_id: Annotated[str, Field(min_length=1)]
    api_surface_id: str | None = None
    candidate_api_surface_ids: tuple[str, ...] = ()
    language: Annotated[str, Field(min_length=1)]
    relationship: Literal[
        "direct",
        "transition-backed",
        "callback",
        "not-applicable",
        "cross-cutting",
    ]
    status: Literal["candidate", "reviewed", "matched", "ambiguous", "unmatched"]
    rationale: Annotated[str, Field(min_length=1)]
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


class _IdentifiedRecord(Protocol):
    id: str


class BundleDocument(ContractRecord):
    document_id: Annotated[str, Field(min_length=1)]
    requirements: tuple[BundleRequirement, ...] = ()
    transitions: tuple[BundleTransition, ...] = ()
    mappings: tuple[BundleMapping, ...] = ()
    api_surfaces: tuple[BundleSurface, ...] = ()
    api_crosswalks: tuple[BundleCrosswalk, ...] = ()
    requirement_api_bindings: tuple[BundleRequirementApiBinding, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> BundleDocument:
        requirement_ids = self._unique_ids("requirement", self.requirements)
        transition_ids = self._unique_ids("transition", self.transitions)
        mapping_ids = self._unique_ids("mapping", self.mappings)
        surface_ids = self._unique_ids("API surface", self.api_surfaces)
        self._unique_ids("API crosswalk", self.api_crosswalks)
        self._unique_ids("requirement API binding", self.requirement_api_bindings)
        self._validate_requirement_ordinals()
        self._validate_requirement_transitions(transition_ids)
        self._validate_transition_requirements(requirement_ids)
        self._validate_mapping_references(requirement_ids, transition_ids)
        self._validate_crosswalk_references(mapping_ids, surface_ids)
        self._validate_requirement_api_references(requirement_ids, surface_ids)
        return self

    def _unique_ids(self, label: str, values: Sequence[_IdentifiedRecord]) -> set[str]:
        identifiers = [item.id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{self.document_id}: duplicate {label} IDs")
        return set(identifiers)

    def _validate_requirement_ordinals(self) -> None:
        ordinals = tuple(item.ordinal for item in self.requirements)
        if any(item is not None for item in ordinals):
            if any(item is None for item in ordinals):
                raise ValueError(f"{self.document_id}: requirement ordinals must be complete")
            expected_ordinals = tuple(range(1, len(self.requirements) + 1))
            if ordinals != expected_ordinals:
                raise ValueError(
                    f"{self.document_id}: requirement ordinals must follow catalog order"
                )

    def _validate_requirement_transitions(
        self,
        transition_ids: AbstractSet[str],
    ) -> None:
        for requirement in self.requirements:
            if len(requirement.transition_ids) != len(set(requirement.transition_ids)):
                raise ValueError(
                    f"{self.document_id}: requirement {requirement.id} "
                    "transition IDs must be unique"
                )
            missing = set(requirement.transition_ids) - transition_ids
            if missing:
                raise ValueError(
                    f"{self.document_id}: requirement {requirement.id} references missing "
                    f"transitions {sorted(missing)}"
                )

    def _validate_transition_requirements(self, requirement_ids: AbstractSet[str]) -> None:
        for transition in self.transitions:
            if len(transition.requirement_ids) != len(set(transition.requirement_ids)):
                raise ValueError(
                    f"{self.document_id}: transition {transition.id} requirement IDs must be unique"
                )
            missing = set(transition.requirement_ids) - requirement_ids
            if missing:
                raise ValueError(
                    f"{self.document_id}: transition {transition.id} references "
                    f"missing requirements {sorted(missing)}"
                )

    def _validate_mapping_references(
        self,
        requirement_ids: AbstractSet[str],
        transition_ids: AbstractSet[str],
    ) -> None:
        for mapping in self.mappings:
            if len(mapping.requirement_ids) != len(set(mapping.requirement_ids)):
                raise ValueError(
                    f"{self.document_id}: mapping {mapping.id} requirement IDs must be unique"
                )
            if len(mapping.transition_ids) != len(set(mapping.transition_ids)):
                raise ValueError(
                    f"{self.document_id}: mapping {mapping.id} transition IDs must be unique"
                )
            missing_requirements = set(mapping.requirement_ids) - requirement_ids
            missing_transitions = set(mapping.transition_ids) - transition_ids
            if missing_requirements or missing_transitions:
                raise ValueError(
                    f"{self.document_id}: mapping {mapping.id} has unresolved references "
                    f"requirements={sorted(missing_requirements)} "
                    f"transitions={sorted(missing_transitions)}"
                )

    def _validate_crosswalk_references(
        self,
        mapping_ids: AbstractSet[str],
        surface_ids: AbstractSet[str],
    ) -> None:
        for crosswalk in self.api_crosswalks:
            self._validate_crosswalk(crosswalk, mapping_ids, surface_ids)

    def _validate_crosswalk(
        self,
        crosswalk: BundleCrosswalk,
        mapping_ids: AbstractSet[str],
        surface_ids: AbstractSet[str],
    ) -> None:
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
        if not set(crosswalk.selected_api_surface_ids) <= set(crosswalk.candidate_api_surface_ids):
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

    def _validate_requirement_api_references(
        self,
        requirement_ids: AbstractSet[str],
        surface_ids: AbstractSet[str],
    ) -> None:
        surfaces_by_id = {item.id: item for item in self.api_surfaces}
        for binding in self.requirement_api_bindings:
            self._validate_requirement_api_binding(
                binding, requirement_ids, surface_ids, surfaces_by_id
            )

    def _validate_requirement_api_binding(
        self,
        binding: BundleRequirementApiBinding,
        requirement_ids: AbstractSet[str],
        surface_ids: AbstractSet[str],
        surfaces_by_id: Mapping[str, BundleSurface],
    ) -> None:
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
            selected = surfaces_by_id.get(binding.api_surface_id)
            if selected is None:
                raise ValueError(
                    f"{self.document_id}: requirement API binding {binding.id} selects "
                    f"missing surface {binding.api_surface_id}"
                )
            if binding.language != selected.language:
                raise ValueError(
                    f"{self.document_id}: requirement API binding {binding.id} language "
                    f"{binding.language} does not match selected surface language "
                    f"{selected.language}"
                )


class CorpusBundle(ContractRecord):
    """Portable semantic slice consumed by an external implementation repo."""

    schema_version: Annotated[int, Field(ge=1)]
    bundle_id: Annotated[str, Field(min_length=1)]
    corpus_revision: Annotated[str, Field(min_length=1)]
    documents: Annotated[tuple[BundleDocument, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_documents(self) -> CorpusBundle:
        identifiers = [item.document_id for item in self.documents]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("corpus bundle document IDs must be unique")
        return self


class EvidenceRecord(ContractRecord):
    """One externally produced build, test, trace, or review observation."""

    id: Annotated[str, Field(min_length=1)]
    kind: Literal[
        "build", "compile", "unit-test", "integration-test", "trace", "review", "artifact"
    ]
    status: Literal["planned", "passed", "failed", "blocked", "observed"]
    execution_mode: Literal["real", "mocked", "simulated", "unknown"] = "unknown"
    review_status: Literal["unreviewed", "accepted", "rejected"] = "unreviewed"
    reviewer: str | None = None
    reviewed_at: str | None = None
    requirement_ids: tuple[str, ...] = ()
    command: str | None = None
    artifact: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def validate_review(self) -> EvidenceRecord:
        if any(not item for item in self.requirement_ids):
            raise ValueError("evidence requirement IDs cannot be empty")
        if len(self.requirement_ids) != len(set(self.requirement_ids)):
            raise ValueError("evidence requirement IDs must be unique")
        if self.review_status == "accepted" and not self.reviewer:
            raise ValueError("accepted evidence must name a reviewer")
        if self.review_status == "accepted" and not self.reviewed_at:
            raise ValueError("accepted evidence must include a review timestamp")
        return self


class ComplianceTestCase(ContractRecord):
    """One RTI-owned behavioral test mapped to a portable corpus seam."""

    id: Annotated[str, Field(min_length=1)]
    kind: Literal["build", "compile", "unit-test", "integration-test", "trace"]
    runner: Annotated[str, Field(min_length=1)]
    selector: Annotated[str, Field(min_length=1)]
    result_selector: Annotated[str, Field(min_length=1)]
    command: str | None = None
    document_id: Annotated[str, Field(min_length=1)]
    implementation_mapping_id: Annotated[str, Field(min_length=1)]
    target: Annotated[str, Field(min_length=1)]
    language: Annotated[str, Field(min_length=1)]
    symbol: Annotated[str, Field(min_length=1)]
    api_surface_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    # Optional for schema-v1 catalogs; new catalogs should name the exact
    # requirement rows exercised by the test instead of relying only on the
    # implementation mapping join.
    requirement_ids: tuple[str, ...] = ()
    execution_mode: Literal["real", "mocked", "simulated", "unknown"]
    notes: str = ""

    @model_validator(mode="after")
    def validate_surfaces(self) -> ComplianceTestCase:
        if any(not item for item in self.api_surface_ids):
            raise ValueError("compliance test API surface IDs cannot be empty")
        if len(self.api_surface_ids) != len(set(self.api_surface_ids)):
            raise ValueError("compliance test API surface IDs must be unique")
        if any(not item for item in self.requirement_ids):
            raise ValueError("compliance test requirement IDs cannot be empty")
        if len(self.requirement_ids) != len(set(self.requirement_ids)):
            raise ValueError("compliance test requirement IDs must be unique")
        return self


class ComplianceTestCatalog(ContractRecord):
    """Validated RTI-owned catalog consumed by test-result adapters."""

    schema_version: Annotated[int, Field(ge=1)]
    tests: Annotated[tuple[ComplianceTestCase, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_test_ids(self) -> ComplianceTestCatalog:
        identifiers = [item.id for item in self.tests]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("compliance test catalog IDs must be unique")
        return self


class ImplementationBinding(ContractRecord):
    """Implementation-owned mapping and evidence links."""

    id: Annotated[str, Field(min_length=1)]
    document_id: Annotated[str, Field(min_length=1)]
    implementation_mapping_id: Annotated[str, Field(min_length=1)]
    target: Annotated[str, Field(min_length=1)]
    symbol: Annotated[str, Field(min_length=1)]
    language: Annotated[str, Field(min_length=1)]
    status: Literal["planned", "partial", "implemented", "verified", "not_applicable", "deferred"]
    requirement_ids: tuple[str, ...] = ()
    api_surface_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    notes: str = ""

    @model_validator(mode="after")
    def validate_requirement_ids(self) -> ImplementationBinding:
        if any(not item for item in self.requirement_ids):
            raise ValueError("implementation binding requirement IDs cannot be empty")
        if len(self.requirement_ids) != len(set(self.requirement_ids)):
            raise ValueError("implementation binding requirement IDs must be unique")
        return self


class ImplementationManifest(ContractRecord):
    """Implementation-repository input accepted by the sidecar verifier."""

    schema_version: Annotated[int, Field(ge=1)]
    manifest_id: Annotated[str, Field(min_length=1)]
    repository: Annotated[str, Field(min_length=1)]
    corpus_revision: Annotated[str, Field(min_length=1)]
    document_ids: Annotated[tuple[str, ...], Field(min_length=1)]
    targets: Annotated[tuple[str, ...], Field(min_length=1)]
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

    implementation_mapping_id: Annotated[str, Field(min_length=1)]
    target: Annotated[str, Field(min_length=1)]
    binding_kind: Literal["native", "protocol", "language-adapter", "transport"]
    language: Annotated[str, Field(min_length=1)]
    interface_kind: Annotated[str, Field(min_length=1)]
    interface_name: Annotated[str, Field(min_length=1)]
    crosswalk_status: Literal["matched", "ambiguous", "unmatched", "planned"]
    requirement_ids: tuple[str, ...] = ()
    transition_ids: tuple[str, ...] = ()
    candidate_api_surface_ids: tuple[str, ...] = ()
    selected_api_surface_ids: tuple[str, ...] = ()
    api_surfaces: tuple[BundleSurface, ...] = ()


class AdapterDocumentRequest(ContractRecord):
    """The portion of a bundle assigned to one adapter invocation."""

    document_id: Annotated[str, Field(min_length=1)]
    requirements: tuple[BundleRequirement, ...] = ()
    bindings: tuple[AdapterExpectedBinding, ...] = ()

    @model_validator(mode="after")
    def validate_requirement_catalog(self) -> AdapterDocumentRequest:
        identifiers = [item.id for item in self.requirements]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{self.document_id}: adapter requirement IDs must be unique")
        ordinals = tuple(item.ordinal for item in self.requirements)
        if any(item is not None for item in ordinals):
            if any(item is None for item in ordinals):
                raise ValueError(
                    f"{self.document_id}: adapter requirement ordinals must be complete"
                )
            if ordinals != tuple(range(1, len(self.requirements) + 1)):
                raise ValueError(
                    f"{self.document_id}: adapter requirement ordinals must follow catalog order"
                )
        return self


class AdapterRequest(ContractRecord):
    """JSON request sent to an RTI adapter over stdin."""

    schema_version: Annotated[int, Field(ge=1)]
    request_id: Annotated[str, Field(min_length=1)]
    bundle_id: Annotated[str, Field(min_length=1)]
    corpus_revision: Annotated[str, Field(min_length=1)]
    documents: Annotated[tuple[AdapterDocumentRequest, ...], Field(min_length=1)]


class AdapterResponse(ContractRecord):
    """JSON response returned by an RTI adapter over stdout."""

    schema_version: Annotated[int, Field(ge=1)]
    request_id: Annotated[str, Field(min_length=1)]
    adapter_id: Annotated[str, Field(min_length=1)]
    repository: Annotated[str, Field(min_length=1)]
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

    code: Annotated[str, Field(min_length=1)]
    severity: Literal["error", "warning", "info"]
    record_id: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]


class ComplianceCoverage(ContractRecord):
    """Requirement, transition, API, and binding testing coverage summary."""

    expected_binding_count: Annotated[int, Field(ge=0)] = 0
    present_binding_count: Annotated[int, Field(ge=0)] = 0
    tested_binding_count: Annotated[int, Field(ge=0)] = 0
    verified_binding_count: Annotated[int, Field(ge=0)] = 0
    expected_requirement_count: Annotated[int, Field(ge=0)] = 0
    requirements_with_verified_evidence_count: Annotated[int, Field(ge=0)] = 0
    expected_transition_count: Annotated[int, Field(ge=0)] = 0
    transitions_with_verified_evidence_count: Annotated[int, Field(ge=0)] = 0
    expected_api_surface_count: Annotated[int, Field(ge=0)] = 0
    api_surfaces_with_verified_evidence_count: Annotated[int, Field(ge=0)] = 0
    binding_coverage: Annotated[float, Field(ge=0, le=1)] = 0.0
    requirement_coverage: Annotated[float, Field(ge=0, le=1)] = 0.0
    transition_coverage: Annotated[float, Field(ge=0, le=1)] = 0.0
    api_surface_coverage: Annotated[float, Field(ge=0, le=1)] = 0.0
    accepted_evidence_count: Annotated[int, Field(ge=0)] = 0
    accepted_real_evidence_count: Annotated[int, Field(ge=0)] = 0
    fully_verified: bool = False
    untested_binding_keys: tuple[str, ...] = ()
    untested_requirement_ids: tuple[str, ...] = ()
    untested_transition_ids: tuple[str, ...] = ()
    unverified_api_surface_ids: tuple[str, ...] = ()
    unaccepted_evidence_ids: tuple[str, ...] = ()
    non_real_evidence_ids: tuple[str, ...] = ()


class ComplianceResult(ContractRecord):
    """CI-friendly sidecar result."""

    schema_version: Annotated[int, Field(ge=1)]
    bundle_id: Annotated[str, Field(min_length=1)]
    manifest_id: Annotated[str, Field(min_length=1)]
    passed: bool
    binding_counts: Annotated[dict[str, int], Field(default_factory=dict)]
    evidence_counts: Annotated[dict[str, int], Field(default_factory=dict)]
    coverage: Annotated[ComplianceCoverage, Field(default_factory=ComplianceCoverage)]
    findings: tuple[ComplianceFinding, ...] = ()
