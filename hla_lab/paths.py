"""Canonical repository and corpus paths used by the public lab interface."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from hla_lab.corpus.edition_lineage import (
    EditionDocument,
    EditionLineageManifest,
    load_edition_lineage,
)

__all__ = [
    "DOCUMENT_CATALOG",
    "DOCUMENT_IDS",
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
    "document_roots",
    "resources",
]

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DocumentResources:
    """Repository-owned paths belonging to one document product."""

    root: Path

    @property
    def canonical(self) -> Path:
        return self.root / "canonical"

    @property
    def semantic(self) -> Path:
        return self.root / "semantic"

    @property
    def sections(self) -> Path:
        return self.root / "sections"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def output_semantic(self) -> Path:
        return self.output / "semantic"

    @property
    def build(self) -> Path:
        return self.root / "build"

    @property
    def dist(self) -> Path:
        return self.root / "dist"

    @property
    def main_tex(self) -> Path:
        return self.root / "main.tex"

    def canonical_file(self, name: str) -> Path:
        return self.canonical / name

    def semantic_file(self, name: str) -> Path:
        return self.semantic / name

    def output_file(self, name: str) -> Path:
        return self.output / name

    def output_semantic_file(self, name: str) -> Path:
        return self.output_semantic / name


@dataclass(frozen=True)
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
    def schemas(self) -> Path:
        return self.root / "schemas"

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


def resources(root: Path = REPO_ROOT) -> RepositoryResources:
    """Return the path registry for ``root`` without requiring a process cwd."""

    return RepositoryResources(Path(root))


RESOURCES = resources()
IEEE_ROOT = RESOURCES.ieee_topics
DOCUMENT_MANIFEST = RESOURCES.edition_lineage_manifest


def _load_document_manifest() -> EditionLineageManifest:
    return _load_document_manifest_from(RESOURCES)


def _load_document_manifest_from(repository: RepositoryResources) -> EditionLineageManifest:
    path = repository.edition_lineage_manifest
    if not path.is_file():
        raise FileNotFoundError(f"missing document manifest: {path}")
    return load_edition_lineage(path)


DOCUMENT_CATALOG = _load_document_manifest()
DOCUMENT_IDS = tuple(item.document_id for item in DOCUMENT_CATALOG.documents)
_DOCUMENTS_BY_ID = {item.document_id: item for item in DOCUMENT_CATALOG.documents}


def document_catalog(repo_root: Path = REPO_ROOT) -> EditionLineageManifest:
    """Load the document identities declared by ``repo_root``."""

    root = Path(repo_root)
    if root.resolve() == REPO_ROOT:
        return DOCUMENT_CATALOG
    return _load_document_manifest_from(resources(root))


def document_entry(document_id: str, repo_root: Path = REPO_ROOT) -> EditionDocument:
    """Return the canonical manifest entry for one corpus document."""

    catalog = document_catalog(repo_root)
    documents = (
        _DOCUMENTS_BY_ID
        if catalog is DOCUMENT_CATALOG
        else {item.document_id: item for item in catalog.documents}
    )
    document_ids = (
        DOCUMENT_IDS
        if catalog is DOCUMENT_CATALOG
        else tuple(item.document_id for item in catalog.documents)
    )
    try:
        return documents[document_id]
    except KeyError as error:
        known = ", ".join(document_ids)
        raise ValueError(f"unknown HLA document {document_id}; known: {known}") from error


def document_entry_for_root(root_name: str, repo_root: Path = REPO_ROOT) -> EditionDocument:
    """Resolve a document root, including isolated test/workspace suffixes."""

    try:
        return document_entry(root_name, repo_root)
    except ValueError:
        catalog = document_catalog(repo_root)
        matches = tuple(
            item for item in catalog.documents if root_name.startswith(item.document_id + "-")
        )
        if len(matches) == 1:
            return matches[0]
        raise


def document_entry_for_path(root: Path, repo_root: Path = REPO_ROOT) -> EditionDocument:
    """Resolve a document root path using the selected corpus identity manifest."""

    repository = resources(repo_root)
    resolved = Path(root).resolve()
    for entry in document_catalog(repository.root).documents:
        relative_root = entry.root or f"topics/ieee/{entry.document_id}"
        if (repository.root / relative_root).resolve() == resolved:
            return entry
    raise ValueError(f"unknown HLA document root {root} in corpus {repository.root}")


def document_roots(
    repo_root: Path = REPO_ROOT,
    document_ids: Iterable[str] | None = None,
) -> tuple[Path, ...]:
    """Resolve requested HLA document roots and reject unknown documents."""

    repository = resources(repo_root)
    catalog = document_catalog(repository.root)
    requested = tuple(document_ids or (item.document_id for item in catalog.documents))
    documents = {item.document_id: item for item in catalog.documents}
    known = ", ".join(documents)
    missing_ids = tuple(document_id for document_id in requested if document_id not in documents)
    if missing_ids:
        raise ValueError(f"unknown HLA document(s): {', '.join(missing_ids)}; known: {known}")
    entries = tuple(documents[document_id] for document_id in requested)
    roots = tuple(
        repository.root / (entry.root or f"topics/ieee/{entry.document_id}") for entry in entries
    )
    missing = tuple(path for path in roots if not path.is_dir())
    if missing:
        missing_ids = ", ".join(path.name for path in missing)
        raise FileNotFoundError(f"missing HLA document root(s): {missing_ids}")
    return roots
