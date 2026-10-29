"""Shared semantic destination and basic LaTeX anchor helpers."""

from __future__ import annotations

from hla_lab.core.text import tex_escape

__all__ = ["latex_anchor", "qualified_id"]


def qualified_id(document_id: str, record_id: str) -> str:
    """Return the cross-document identity used by generated links."""

    return f"{document_id}:{record_id}"


def latex_anchor(document_id: str, record_id: str) -> str:
    """Render the standard zero-size `hypertarget` for a semantic record."""

    return f"\\hypertarget{{{tex_escape(document_id)}:{tex_escape(record_id)}}}{{}}"
