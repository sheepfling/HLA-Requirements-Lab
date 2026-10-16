"""HLA-specific semantic loading and generation adapter."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from hla_lab.core.hla_profile import (
    HLA_LATEX_DIALECT,
    HLA_SOURCE,
    source_profile_for_document,
)
from hla_lab.core.hla_surface_profile import (
    HLA_API_OWNERS,
    build_hla_surface_contract,
    load_hla_api_owners,
)
from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    DocumentModel,
    load_document_model,
)
from hla_lab.paths import REPO_ROOT, resources

__all__ = [
    "HLA_LATEX_DIALECT",
    "HLA_SOURCE",
    "load_hla_corpus",
    "load_hla_document_model",
    "source_profile_for_document",
]


def load_hla_document_model(
    root: Path,
    repository_root: Path = REPO_ROOT,
) -> DocumentModel:
    """Load one HLA source tree through the generic semantic model."""
    source = source_profile_for_document(root.name, repository_root)
    api_owners = (
        HLA_API_OWNERS
        if Path(repository_root).resolve() == REPO_ROOT
        else load_hla_api_owners(resources(repository_root).source_profiles_manifest)
    )
    return build_hla_surface_contract(load_document_model(root, source), api_owners=api_owners)


def load_hla_corpus(
    roots: Iterable[Path],
    repository_root: Path = REPO_ROOT,
) -> ComplianceCorpus:
    """Load HLA document roots through the generic corpus loader."""
    return ComplianceCorpus(
        documents=tuple(load_hla_document_model(root, repository_root) for root in roots)
    )
