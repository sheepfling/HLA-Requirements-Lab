"""HLA-specific semantic loading and generation adapter."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

try:
    from scripts.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
    from scripts.semantic_model import (
        ComplianceCorpus,
        DocumentModel,
        load_corpus,
        load_document_model,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
    from semantic_model import ComplianceCorpus, DocumentModel, load_corpus, load_document_model


def load_hla_document_model(root: Path) -> DocumentModel:
    """Load one HLA source tree through the generic semantic model."""
    return load_document_model(root, HLA_SOURCE)


def load_hla_corpus(roots: Iterable[Path]) -> ComplianceCorpus:
    """Load HLA document roots through the generic corpus loader."""
    return load_corpus(roots, HLA_SOURCE)


__all__ = [
    "HLA_LATEX_DIALECT",
    "HLA_SOURCE",
    "load_hla_corpus",
    "load_hla_document_model",
]
