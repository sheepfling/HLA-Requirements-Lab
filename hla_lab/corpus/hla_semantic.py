"""HLA-specific semantic loading and generation adapter."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from hla_lab.core.hla_profile import (
    HLA_LATEX_DIALECT,
    HLA_SOURCE,
    source_profile_for_document,
)
from hla_lab.core.hla_surface_profile import build_hla_surface_contract
from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    DocumentModel,
    load_document_model,
)

__all__ = [
    "HLA_LATEX_DIALECT",
    "HLA_SOURCE",
    "load_hla_corpus",
    "load_hla_document_model",
    "source_profile_for_document",
]


def load_hla_document_model(root: Path) -> DocumentModel:
    """Load one HLA source tree through the generic semantic model."""
    source = source_profile_for_document(root.name)
    return build_hla_surface_contract(load_document_model(root, source))


def load_hla_corpus(roots: Iterable[Path]) -> ComplianceCorpus:
    """Load HLA document roots through the generic corpus loader."""
    return ComplianceCorpus(documents=tuple(load_hla_document_model(root) for root in roots))
