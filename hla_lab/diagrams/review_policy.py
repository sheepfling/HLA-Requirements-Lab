"""Shared review defaults for extracted diagram candidates."""

from __future__ import annotations

__all__ = ["review_defaults"]

def review_defaults(diagram_type: str, status: str) -> tuple[str, str]:
    """Return the default severity and explanation for a diagram review row."""

    if diagram_type != "state_machine":
        return "none", "Explicitly classified as a non-state diagram or irrelevant asset."
    if status == "needs_review":
        return "high", "Known source ambiguity or parameterization requires targeted review."
    if status == "unmodeled":
        return "high", "Candidate has no semantic record yet."
    if status == "draft":
        return "medium", "Semantic record exists; source comparison and refinement remain."
    if status == "validated":
        return "low", "Semantics compared with source; visual acceptance remains."
    return "none", "No semantic review is required for the current classification."
