"""Shared predicates for paths recorded in source provenance."""

from __future__ import annotations

from pathlib import PureWindowsPath

__all__ = ["is_source_frontmatter", "normalized_source_path", "source_path_parts"]


def normalized_source_path(path: str) -> str:
    """Return provenance paths in portable slash form, accepting either flavor."""
    return PureWindowsPath(path).as_posix()


def source_path_parts(path: str) -> tuple[str, ...]:
    """Parse provenance paths from either Windows or POSIX producers."""
    return tuple(part.casefold() for part in PureWindowsPath(path).parts)


def is_source_frontmatter(path: str) -> bool:
    """Identify source publication furniture excluded from Lab derivatives."""
    parts = source_path_parts(path)
    return "frontmatter" in parts or "front-matter" in parts
