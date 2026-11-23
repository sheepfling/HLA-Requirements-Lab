"""Canonical repository and corpus paths used by the public lab interface."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType

from hla_lab.core.resource_paths import DocumentResources
from hla_lab.corpus.edition_lineage import (
    EditionDocument,
    EditionLineageManifest,
    load_edition_lineage,
)

__all__ = [
    "DOCUMENT_MANIFEST",
    "IEEE_ROOT",
    "REPO_ROOT",
    "RESOURCES",
    "DocumentResources",
    "RepositoryResources",
    "document_catalog",
    "document_entry",
    "document_entry_for_path",
    "document_entry_for_root",
    "document_ids",
    "document_roots",
    "repository_root",
    "resources",
]


def repository_root(value: str | Path | None = None) -> Path:
    """Resolve an explicit or configured workspace root.

    Reusable callers pass a path. Workspace commands may set ``HLA_LAB_ROOT``;
    the package never guesses from its install location or process directory.
    """
    selected = value if value is not None else os.environ.get("HLA_LAB_ROOT") or None
    if selected is None:
        raise RuntimeError("workspace root is required; pass a path or set HLA_LAB_ROOT")
    return Path(selected).expanduser().resolve()


def _configured_root() -> Path | None:
    value = os.environ.get("HLA_LAB_ROOT")
    return Path(value).expanduser().resolve() if value else None


REPO_ROOT = _configured_root()


@dataclass(frozen=True, slots=True)
class RepositoryResources:
    """Named repository roots and manifests used by the lab."""

    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def semantic_data(self) -> Path:
        return self.data / "semantic"

    @property
    def release_data(self) -> Path:
        return self.data / "release"

    @property
    def state_machine_data(self) -> Path:
        return self.data / "state_machines"

    @property
    def topics(self) -> Path:
        return self.root / "topics"

    @property
    def ieee_topics(self) -> Path:
        return self.topics / "ieee"

    @property
    def fixture_topics(self) -> Path:
        return self.topics / "fixture"

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def temporary(self) -> Path:
        return self.root / ".tmp"

    @property
    def publications_manifest(self) -> Path:
        return self.data / "publications.json"

    @property
    def release_manifest(self) -> Path:
        return self.release_data / "documents.json"

    @property
    def authority_manifest(self) -> Path:
        return self.semantic_data / "authority.json"

    @property
    def diagram_surfaces_manifest(self) -> Path:
        return self.semantic_data / "diagram-surfaces.json"

    @property
    def edition_lineage_manifest(self) -> Path:
        return self.semantic_data / "edition-lineage.json"

    @property
    def inventory_manifest(self) -> Path:
        return self.semantic_data / "inventory.json"

    @property
    def source_profiles_manifest(self) -> Path:
        return self.semantic_data / "source-profiles.json"

    @property
    def state_machine_manifest(self) -> Path:
        return self.state_machine_data / "manifest.json"

    def document(self, document_id: str) -> DocumentResources:
        """Resolve a catalog document to its repository-owned path bundle."""

        entry = document_entry(document_id, self.root)
        relative_root = entry.root or f"topics/ieee/{entry.document_id}"
        return DocumentResources(self.root / relative_root)

    def inbox_file(self, *parts: str) -> Path:
        """Resolve a source archive or other explicitly named inbox resource."""

        return self.inbox.joinpath(*parts)


def resources(root: Path | None = None) -> RepositoryResources:
    """Return the path registry for an explicit or configured workspace."""

    return RepositoryResources(repository_root(root))


RESOURCES = resources(REPO_ROOT) if REPO_ROOT is not None else None
IEEE_ROOT = RESOURCES.ieee_topics if RESOURCES is not None else None
DOCUMENT_MANIFEST = RESOURCES.edition_lineage_manifest if RESOURCES is not None else None


def document_catalog(root: Path | None = None) -> EditionLineageManifest:
    """Load the workspace's document catalog on first corpus operation."""
    return _document_catalog(repository_root(root))


@cache
def _document_catalog(root: Path) -> EditionLineageManifest:
    manifest = resources(root).edition_lineage_manifest
    if not manifest.is_file():
        raise FileNotFoundError(f"missing document manifest: {manifest}")
    return load_edition_lineage(manifest)


def document_ids(root: Path | None = None) -> tuple[str, ...]:
    """Return supported document IDs without loading corpus data at package import."""
    return _catalog_document_ids(repository_root(root))


def _catalog_document_ids(root: Path) -> tuple[str, ...]:
    return tuple(item.document_id for item in document_catalog(root).documents)


@cache
def _documents_by_id(root: Path) -> Mapping[str, EditionDocument]:
    return MappingProxyType({item.document_id: item for item in document_catalog(root).documents})


def document_entry(document_id: str, root: Path | None = None) -> EditionDocument:
    """Return the canonical manifest entry for one corpus document."""
    entries = _documents_by_id(repository_root(root))
    try:
        return entries[document_id]
    except KeyError as error:
        known = ", ".join(entries)
        raise ValueError(f"unknown HLA document {document_id}; known: {known}") from error


def document_entry_for_root(root_name: str, root: Path | None = None) -> EditionDocument:
    """Resolve a document root, including isolated test/workspace suffixes."""
    root = repository_root(root)
    try:
        return document_entry(root_name, root)
    except ValueError:
        matches = tuple(
            item
            for item in document_catalog(root).documents
            if root_name.startswith(item.document_id + "-")
        )
        if len(matches) == 1:
            return matches[0]
        raise


def document_entry_for_path(path: Path, root: Path | None = None) -> EditionDocument:
    """Prefer a catalog's declared root, with ID-based resolution for isolated copies."""
    workspace = repository_root(root)
    candidate = Path(path).resolve()
    matches = tuple(
        item
        for item in document_catalog(workspace).documents
        if (workspace / (item.root or f"topics/ieee/{item.document_id}")).resolve() == candidate
    )
    if len(matches) != 1:
        if not matches:
            return document_entry_for_root(candidate.name, workspace)
        raise ValueError(f"document root {candidate} is declared more than once in the catalog")
    return matches[0]


def document_roots(
    repo_root: Path | None = None,
    # TODO name is shadowed from outside
    document_ids: Iterable[str] | None = None,
) -> tuple[Path, ...]:
    """Resolve requested HLA document roots and reject unknown documents."""

    repo_root = repository_root(repo_root)
    requested = tuple(document_ids or _catalog_document_ids(repo_root))
    entries = tuple(document_entry(document_id, repo_root) for document_id in requested)
    roots = tuple(resources(repo_root).document(entry.document_id).root for entry in entries)
    missing = tuple(path for path in roots if not path.is_dir())
    if missing:
        missing_ids = ", ".join(path.name for path in missing)
        raise FileNotFoundError(f"missing HLA document root(s): {missing_ids}")
    return roots
