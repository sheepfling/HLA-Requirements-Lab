"""Typed, document-family-neutral contract for generated publications.

The contract describes how a validated semantic corpus is organized into a
human-facing derivative.  It deliberately contains no HLA vocabulary or
LaTeX commands; document families provide profile data at the adapter boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from hla_lab.core.semantic_model import SemanticRecord

__all__ = [
    "ProjectionContract",
    "PublicationDocument",
    "PublicationProfile",
    "PublicationSection",
    "default_publication_profile",
    "load_publication_profile",
    "publication_destination",
    "write_contract_json",
]


class PublicationDocument(SemanticRecord):
    """A source document represented in a generated publication."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    short_title: Annotated[str, Field(min_length=1)]


class ProjectionContract(SemanticRecord):
    """The semantic record families and output role of one publication view."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    purpose: Annotated[str, Field(min_length=1)]
    record_kinds: tuple[str, ...] = ()
    output: Literal["section", "table", "annex", "index"] = "section"
    per_document: bool = True
    renderer: Literal[
        "scope",
        "concepts",
        "normative",
        "operations",
        "state-logic",
        "tables",
        "traceability",
        "custom",
    ] = "custom"


class PublicationSection(SemanticRecord):
    """One ordered, addressable section in the publication outline."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    order: Annotated[int, Field(ge=1)]
    projection_id: Annotated[str, Field(min_length=1)]
    level: Annotated[int, Field(ge=1, le=3)] = 1
    per_document: bool = True
    required: bool = True


class PublicationProfile(SemanticRecord):
    """Canonical publication outline and projection contract."""

    schema_version: Annotated[int, Field(ge=1)] = 1
    profile_id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    subtitle: str = ""
    description: str = ""
    style_id: Annotated[str, Field(min_length=1)] = "semantic-reflowable-default"
    documents: tuple[PublicationDocument, ...] = ()
    projections: tuple[ProjectionContract, ...]
    sections: tuple[PublicationSection, ...]

    @model_validator(mode="after")
    def validate_contract(self) -> PublicationProfile:
        document_ids = [item.id for item in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("publication document IDs must be unique")

        projection_ids = [item.id for item in self.projections]
        if len(projection_ids) != len(set(projection_ids)):
            raise ValueError("publication projection IDs must be unique")
        projection_id_set = set(projection_ids)

        section_ids = [item.id for item in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("publication section IDs must be unique")
        section_orders = [item.order for item in self.sections]
        if section_orders != list(range(1, len(section_orders) + 1)):
            raise ValueError("publication section order must be contiguous from one")
        missing = sorted({item.projection_id for item in self.sections} - projection_id_set)
        if missing:
            raise ValueError(f"publication sections reference unknown projections: {missing}")
        return self

    def document(self, document_id: str) -> PublicationDocument:
        """Return a configured source document by semantic ID."""
        return next(item for item in self.documents if item.id == document_id)

    def projection(self, projection_id: str) -> ProjectionContract:
        """Return a projection contract by stable ID."""
        return next(item for item in self.projections if item.id == projection_id)

    def section(self, section_id: str) -> PublicationSection:
        """Return an outline section by stable ID."""
        return next(item for item in self.sections if item.id == section_id)


def publication_destination(profile_id: str, section_id: str) -> str:
    """Return the stable destination for an outline section."""
    return f"{profile_id}:{section_id}"


def load_publication_profile(path: Path) -> PublicationProfile:
    """Load and validate a source-controlled publication profile."""
    return PublicationProfile.model_validate_json(path.read_text(encoding="utf-8"))


def default_publication_profile(document_ids: tuple[str, ...]) -> PublicationProfile:
    """Provide a neutral contract for generic consumers and test fixtures."""
    documents = tuple(
        PublicationDocument(id=item, title=item, short_title=item) for item in document_ids
    )
    projections = (
        ProjectionContract(
            id="scope",
            title="Scope and corpus",
            purpose="Identify the source documents and their semantic boundaries.",
            record_kinds=("clause", "content-block"),
            per_document=False,
            renderer="scope",
        ),
        ProjectionContract(
            id="concepts",
            title="Concepts and terminology",
            purpose="Present reusable definitions and the hierarchy that owns them.",
            record_kinds=("clause", "definition"),
            renderer="concepts",
        ),
        ProjectionContract(
            id="normative",
            title="Normative requirements",
            purpose="Present reviewed requirements and their clause relationships.",
            record_kinds=("requirement",),
            renderer="normative",
        ),
        ProjectionContract(
            id="operations",
            title="Services and operational behavior",
            purpose="Present service, callback, and operational content.",
            record_kinds=("content-block", "content-element", "implementation"),
            renderer="operations",
        ),
        ProjectionContract(
            id="state-logic",
            title="State machines and message sequences",
            purpose="Present states, events, transitions, and sequence messages.",
            record_kinds=("state-machine", "state", "transition"),
            renderer="state-logic",
        ),
        ProjectionContract(
            id="tables",
            title="Semantic tables",
            purpose="Present reusable table families, rows, columns, and cells.",
            record_kinds=("table-family", "table", "table-cell"),
            renderer="tables",
        ),
        ProjectionContract(
            id="traceability",
            title="Traceability and compliance annexes",
            purpose="Connect requirements to clauses, behavior, dependencies, and evidence.",
            record_kinds=(
                "reference",
                "cross-reference",
                "requirement-link",
                "implementation",
                "figure",
                "note",
                "example",
                "annex",
            ),
            output="annex",
            renderer="traceability",
        ),
    )
    sections = tuple(
        PublicationSection(
            id=projection.id,
            title=projection.title,
            order=index,
            projection_id=projection.id,
            per_document=projection.per_document,
            level=1,
        )
        for index, projection in enumerate(projections, start=1)
    )
    return PublicationProfile(
        profile_id="generic-semantic-publication",
        title="Semantic publication",
        description="A neutral hierarchy-first publication contract.",
        documents=documents,
        projections=projections,
        sections=sections,
    )


def write_contract_json(profile: PublicationProfile, path: Path) -> None:
    """Write a deterministic generated copy of a validated profile."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
