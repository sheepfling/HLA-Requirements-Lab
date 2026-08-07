"""Typed registry for independently buildable publication destinations."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PublicationKind = Literal[
    "faithful-reconstruction",
    "hierarchy-reconstruction",
    "requirements-publication",
]


class ReleaseProject(BaseModel):
    """One independently buildable document product in the release manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    publication_id: str = Field(min_length=1)
    root: str = Field(min_length=1)
    pdf: str = Field(min_length=1)
    log: str = Field(min_length=1)
    expected_pages: int | None = Field(default=None, ge=1)
    kind: str = Field(min_length=1)


class ReleaseManifest(BaseModel):
    """Release-check inputs referenced by the publication registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    projects: tuple[ReleaseProject, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_project_ids(self) -> ReleaseManifest:
        identifiers = [item.id for item in self.projects]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("release project IDs must be unique")
        return self


class Publication(BaseModel):
    """A human-facing document destination with isolated build membership."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    kind: PublicationKind
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    project_ids: tuple[str, ...] = Field(min_length=1)
    source_document_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_project_ids(self) -> Publication:
        if len(self.project_ids) != len(set(self.project_ids)):
            raise ValueError(f"publication {self.id} has duplicate project IDs")
        return self


class PublicationRegistry(BaseModel):
    """Source-controlled collection of optional, independently built products."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    publications: tuple[Publication, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_publication_ids(self) -> PublicationRegistry:
        identifiers = [item.id for item in self.publications]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("publication IDs must be unique")
        return self

    def publication(self, identifier: str) -> Publication:
        try:
            return next(item for item in self.publications if item.id == identifier)
        except StopIteration as error:
            known = ", ".join(item.id for item in self.publications)
            raise ValueError(
                f"unknown publication {identifier}; known publications: {known}"
            ) from error


def load_release_manifest(path: Path) -> ReleaseManifest:
    """Load the source-controlled release-project inventory."""
    return ReleaseManifest.model_validate_json(path.read_text(encoding="utf-8"))


def load_publication_registry(path: Path) -> PublicationRegistry:
    """Load the source-controlled publication destination registry."""
    return PublicationRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def publication_projects(
    registry: PublicationRegistry,
    release_manifest: ReleaseManifest,
    publication_id: str,
) -> tuple[ReleaseProject, ...]:
    """Resolve a publication to its explicit, independently buildable projects."""
    publication = registry.publication(publication_id)
    projects_by_id = {item.id: item for item in release_manifest.projects}
    missing = tuple(
        identifier for identifier in publication.project_ids if identifier not in projects_by_id
    )
    if missing:
        raise ValueError(
            f"publication {publication_id} references unknown release projects: "
            f"{', '.join(missing)}"
        )
    resolved = tuple(projects_by_id[identifier] for identifier in publication.project_ids)
    mismatched = tuple(
        project.id for project in resolved if project.publication_id != publication_id
    )
    if mismatched:
        raise ValueError(
            f"publication {publication_id} has projects owned by another publication: "
            f"{', '.join(mismatched)}"
        )
    return resolved


__all__ = [
    "Publication",
    "PublicationKind",
    "PublicationRegistry",
    "ReleaseManifest",
    "ReleaseProject",
    "load_publication_registry",
    "load_release_manifest",
    "publication_projects",
]
