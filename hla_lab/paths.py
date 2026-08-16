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
    "document_entry",
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

        entry = document_entry(document_id)
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
    if not DOCUMENT_MANIFEST.is_file():
        raise FileNotFoundError(f"missing document manifest: {DOCUMENT_MANIFEST}")
    return load_edition_lineage(DOCUMENT_MANIFEST)


DOCUMENT_CATALOG = _load_document_manifest()
DOCUMENT_IDS = tuple(item.document_id for item in DOCUMENT_CATALOG.documents)
_DOCUMENTS_BY_ID = {item.document_id: item for item in DOCUMENT_CATALOG.documents}


def document_entry(document_id: str) -> EditionDocument:
    """Return the canonical manifest entry for one corpus document."""

    try:
        return _DOCUMENTS_BY_ID[document_id]
    except KeyError as error:
        known = ", ".join(DOCUMENT_IDS)
        raise ValueError(f"unknown HLA document {document_id}; known: {known}") from error


def document_entry_for_root(root_name: str) -> EditionDocument:
    """Resolve a document root, including isolated test/workspace suffixes."""

    try:
        return document_entry(root_name)
    except ValueError:
        matches = tuple(
            item
            for item in DOCUMENT_CATALOG.documents
            if root_name.startswith(item.document_id + "-")
        )
        if len(matches) == 1:
            return matches[0]
        raise


def document_roots(
    repo_root: Path = REPO_ROOT,
    document_ids: Iterable[str] | None = None,
) -> tuple[Path, ...]:
    """Resolve requested HLA document roots and reject unknown documents."""

    requested = tuple(document_ids or DOCUMENT_IDS)
    entries = tuple(document_entry(document_id) for document_id in requested)
    roots = tuple(resources(repo_root).document(entry.document_id).root for entry in entries)
    missing = tuple(path for path in roots if not path.is_dir())
    if missing:
        missing_ids = ", ".join(path.name for path in missing)
        raise FileNotFoundError(f"missing HLA document root(s): {missing_ids}")
    return roots
