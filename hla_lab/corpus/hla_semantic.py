"""HLA-specific semantic loading and generation adapter."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re

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


_FRONTMATTER_PATH = re.compile(r"(?:^|/)(?:frontmatter|front-matter)(?:/|$)", re.IGNORECASE)
_NOTICE_MARKER = re.compile(
    r"\bThey can also be obtained on request from IEEE or viewed at\b",
    re.IGNORECASE,
)
_CLAUSE_ONE_MARKER = re.compile(r"(?<![\w.])1\.\s+Overview\b", re.IGNORECASE)
_INTERFACE_OVERVIEW_MARKER = re.compile(r"\bOverview\s+Scope\b", re.IGNORECASE)


def _is_frontmatter(path: str) -> bool:
    return bool(_FRONTMATTER_PATH.search(path.replace("\\", "/")))


def _clean_source_surface_text(text: str, source_path: str) -> str:
    """Remove captured publisher furniture while preserving authored prose.

    Some legacy semantic captures begin with a source title page or an IEEE
    availability notice before the actual Clause 1 prose.  This cleanup is
    deliberately narrow: it applies only to those recognizable prefixes and
    does not remove ordinary references to IEEE standards in later clauses.
    """
    if not text:
        return text
    if _NOTICE_MARKER.search(text):
        clause = _CLAUSE_ONE_MARKER.search(text)
        if clause:
            return text[clause.start() :].lstrip()
        return ""
    normalized_path = source_path.replace("\\", "/").casefold()
    if normalized_path.endswith("/clauses/01-overview.tex") or normalized_path == "clauses/01-overview.tex":
        if "IEEE Standard for" in text:
            clause = _CLAUSE_ONE_MARKER.search(text) or _INTERFACE_OVERVIEW_MARKER.search(text)
            if clause:
                return text[clause.start() :].lstrip()
    return text


def _sanitize_hla_derivative_model(model: DocumentModel) -> DocumentModel:
    """Return a derivative-safe model without source front matter or prefixes."""
    frontmatter_blocks = {
        item.id for item in model.content_blocks if _is_frontmatter(item.source.path)
    }
    content_blocks = tuple(
        item.model_copy(
            update={
                "text": ""
                if item.id in frontmatter_blocks
                else _clean_source_surface_text(item.text, item.source.path)
            }
        )
        for item in model.content_blocks
    )
    content_elements = tuple(
        item.model_copy(
            update={
                "text": ""
                if item.block_id in frontmatter_blocks or _is_frontmatter(item.source.path)
                else _clean_source_surface_text(item.text, item.source.path)
            }
        )
        for item in model.content_elements
    )
    return model.model_copy(
        update={"content_blocks": content_blocks, "content_elements": content_elements}
    )


def load_hla_document_model(root: Path) -> DocumentModel:
    """Load one HLA source tree through the generic semantic model."""
    source = source_profile_for_document(root.name)
    return _sanitize_hla_derivative_model(
        build_hla_surface_contract(load_document_model(root, source))
    )


def load_hla_corpus(roots: Iterable[Path]) -> ComplianceCorpus:
    """Load HLA document roots through the generic corpus loader."""
    return ComplianceCorpus(documents=tuple(load_hla_document_model(root) for root in roots))
