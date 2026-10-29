"""Load authored semantic records from JSON resource files."""

from __future__ import annotations

import json
from pathlib import Path

from hla_lab.core.semantic_model_resources import _document_resources
from hla_lab.core.semantic_types import (
    ApiCrosswalk,
    ApiCrosswalkFile,
    ApiSurface,
    ApiSurfaceFile,
    ContentBlock,
    ContentBlockFile,
    ContentElement,
    ContentElementFile,
    CrossReference,
    CrossReferenceFile,
    Definition,
    DefinitionFile,
    Figure,
    FigureFile,
    ImplementationFile,
    ImplementationMapping,
    Note,
    NoteFile,
    Reference,
    ReferenceFile,
    Requirement,
    RequirementApiBinding,
    RequirementApiBindingFile,
    RequirementFile,
    RequirementLink,
    RequirementLinkFile,
    RequirementReview,
    RequirementReviewFile,
    StateTrace,
    StateTraceFile,
    Table,
    TableFamily,
    TableFamilyFile,
    TableFile,
    TransitionCoverage,
    TransitionCoverageFile,
    VerificationTest,
    VerificationTestFile,
)


def _load_authored_definitions(root: Path) -> tuple[Definition, ...]:
    """Load definitions that have already migrated to semantic source."""
    path = _document_resources(root).semantic_file("definitions.json")
    if not path.is_file():
        return ()
    payload = DefinitionFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.definitions


def _load_authored_requirements(root: Path) -> tuple[Requirement, ...]:
    """Load reviewed requirements promoted from source-shaped candidates."""
    path = _document_resources(root).semantic_file("requirements.json")
    if not path.is_file():
        return ()
    payload = RequirementFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.requirements


def _load_authored_requirement_reviews(root: Path) -> tuple[RequirementReview, ...]:
    """Load explicit dispositions for candidate requirement records."""
    path = _document_resources(root).semantic_file("requirement-review.json")
    if not path.is_file():
        return ()
    payload = RequirementReviewFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.reviews


def _load_authored_requirement_links(root: Path) -> tuple[RequirementLink, ...]:
    """Load explicit requirement-to-transition relationships."""
    path = _document_resources(root).semantic_file("requirement-links.json")
    if not path.is_file():
        return ()
    payload = RequirementLinkFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.links


def _load_authored_transition_coverage(root: Path) -> tuple[TransitionCoverage, ...]:
    """Load explicit mapped, N/A, and deferred transition dispositions."""
    path = _document_resources(root).semantic_file("transition-coverage.json")
    if not path.is_file():
        return ()
    payload = TransitionCoverageFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.transition_coverage


def _load_authored_content_blocks(root: Path) -> tuple[ContentBlock, ...]:
    """Load prose blocks that have crossed into semantic source."""
    path = _document_resources(root).semantic_file("content-blocks.json")
    if not path.is_file():
        return ()
    payload = ContentBlockFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.content_blocks


def _load_authored_content_elements(root: Path) -> tuple[ContentElement, ...]:
    """Load typed content units that sit beneath page fidelity adapters."""
    path = _document_resources(root).semantic_file("content-elements.json")
    if not path.is_file():
        return ()
    payload = ContentElementFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.content_elements


def _load_authored_table_families(root: Path) -> tuple[TableFamily, ...]:
    """Load named table families that group parsed semantic table records."""
    path = _document_resources(root).semantic_file("table-families.json")
    if not path.is_file():
        return ()
    payload = TableFamilyFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.table_families


def _load_authored_implementations(
    root: Path,
) -> tuple[ImplementationMapping, ...]:
    """Load code-facing mappings authored outside hand-written LaTeX."""
    path = _document_resources(root).semantic_file("implementations.json")
    if not path.is_file():
        return ()
    payload = ImplementationFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.implementations


def _load_authored_api_surfaces(root: Path) -> tuple[ApiSurface, ...]:
    """Load directly authored API contracts when a source provides them."""
    path = _document_resources(root).semantic_file("api-surfaces.json")
    if not path.is_file():
        return ()
    payload = ApiSurfaceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.api_surfaces


def _load_authored_api_crosswalks(root: Path) -> tuple[ApiCrosswalk, ...]:
    """Load semantic-to-binding crosswalks when a profile supplies them."""
    path = _document_resources(root).semantic_file("api-crosswalk.json")
    if not path.is_file():
        return ()
    payload = ApiCrosswalkFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.api_crosswalks


def _load_authored_requirement_api_bindings(
    root: Path,
) -> tuple[RequirementApiBinding, ...]:
    """Load requirement-to-API traceability records when supplied."""
    path = _document_resources(root).semantic_file("api-requirement-bindings.json")
    if not path.is_file():
        return ()
    payload = RequirementApiBindingFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.bindings


def _load_authored_verification_tests(root: Path) -> tuple[VerificationTest, ...]:
    """Load verification plans/evidence records from semantic source."""
    path = _document_resources(root).semantic_file("verification-tests.json")
    if not path.is_file():
        return ()
    payload = VerificationTestFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.verification_tests


def _load_authored_state_traces(root: Path) -> tuple[StateTrace, ...]:
    """Load authored state-machine trace scenarios from semantic source."""
    path = _document_resources(root).semantic_file("state-traces.json")
    if not path.is_file():
        return ()
    payload = StateTraceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.state_traces


def _load_authored_references(root: Path) -> tuple[Reference, ...]:
    """Load references with resolved cross-document semantic targets."""
    path = _document_resources(root).semantic_file("references.json")
    if not path.is_file():
        return ()
    payload = ReferenceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.references


def _load_authored_cross_references(root: Path) -> tuple[CrossReference, ...]:
    """Load explicitly authored cross-reference records when present."""
    path = _document_resources(root).semantic_file("cross-references.json")
    if not path.is_file():
        return ()
    payload = CrossReferenceFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.cross_references


def _load_authored_tables(root: Path) -> tuple[Table, ...]:
    """Load tables promoted from a legacy source adapter."""
    path = _document_resources(root).semantic_file("tables.json")
    if not path.is_file():
        return ()
    payload = TableFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.tables


def _load_authored_notes(root: Path) -> tuple[Note, ...]:
    """Load notes promoted from a legacy source adapter."""
    path = _document_resources(root).semantic_file("notes.json")
    if not path.is_file():
        return ()
    payload = NoteFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.notes


def _load_authored_figures(root: Path) -> tuple[Figure, ...]:
    """Load figures promoted from a legacy source adapter."""
    path = _document_resources(root).semantic_file("figures.json")
    if not path.is_file():
        return ()
    payload = FigureFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return payload.figures
