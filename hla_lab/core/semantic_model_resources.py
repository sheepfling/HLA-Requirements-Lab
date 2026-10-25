"""Common source indexing and provenance helpers for semantic loading."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    Mapping,
)
from pathlib import (
    Path,
)

from pydantic import (
    JsonValue,
)

from hla_lab.core.parsing import (
    line_number,
)
from hla_lab.core.resource_paths import (
    DocumentResources,
)
from hla_lab.core.semantic_types import (
    SourceOrderedRecord,
    SourceRef,
)


def _source(
    root: Path,
    path: Path,
    text: str,
    offset: int,
    end_offset: int | None = None,
) -> SourceRef:
    return SourceRef(
        path=path.relative_to(root).as_posix(),
        line=line_number(text, offset),
        end_line=(
            line_number(text, max(offset, end_offset - 1)) if end_offset is not None else None
        ),
    )


_INCLUDE_PATTERN = re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")


def _document_resources(root: Path) -> DocumentResources:
    return DocumentResources(root)


def _files(root: Path) -> tuple[Path, ...]:
    """Return source files in document include order, with safe fallbacks.

    The build entry point is the authoritative physical source order. Files
    that are not reachable from ``main.tex`` are retained after the reachable
    sources in lexical order so standalone semantic fragments remain visible
    to extraction without becoming ownership hints.
    """
    excluded = {".trash", "build", "dist", "output"}
    # Acceptance slices are standalone review fixtures, not part of the
    # source corpus. Keeping them out prevents temporary QA clauses from
    # changing the source-controlled inventory and traceability counts.
    excluded_files = {"acceptance_slice.tex"}
    all_files = tuple(
        path
        for path in root.rglob("*.tex")
        if not excluded.intersection(path.relative_to(root).parts)
        and path.name not in excluded_files
    )
    by_relative = {path.relative_to(root).as_posix(): path for path in all_files}
    ordered: list[Path] = []
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.resolve()
        if resolved in visited or not path.is_file() or path.name in excluded_files:
            return
        if excluded.intersection(path.relative_to(root).parts):
            return
        visited.add(resolved)
        ordered.append(path)
        text = path.read_text(encoding="utf-8")
        for match in _INCLUDE_PATTERN.finditer(text):
            include = match.group(1).strip()
            candidate = path.parent / include
            if candidate.suffix != ".tex":
                candidate = candidate.with_suffix(".tex")
            visit(candidate)

    main = _document_resources(root).main_tex
    if main.is_file():
        visit(main)
    ordered.extend(
        path for relative, path in sorted(by_relative.items()) if path.resolve() not in visited
    )
    return tuple(ordered)


def _source_order(root: Path) -> dict[str, int]:
    """Return source positions from the document include graph."""
    return {path.relative_to(root).as_posix(): index for index, path in enumerate(_files(root))}


def _source_key(
    item: SourceOrderedRecord,
    source_order: Mapping[str, int] | None = None,
) -> tuple[int, int, str]:
    """Sort records by include order, with a stable fallback for external data."""
    if source_order is not None:
        return (
            source_order.get(item.source.path, len(source_order)),
            item.source.line,
            item.id,
        )
    page = re.search(r"page-(\d+)", item.source.path)
    page_number = int(page.group(1)) if page else 0
    return page_number, item.source.line, item.id


def _clause_shape(identifier: str) -> tuple[str, str | None, int]:
    number = identifier.removeprefix("clause-")
    parts = number.split(".")
    parent = ".".join(parts[:-1]) if len(parts) > 1 else None
    return number, f"clause-{parent}" if parent else None, len(parts)


def _source_ref(value: Mapping[str, JsonValue]) -> SourceRef | None:
    return SourceRef.model_validate(value)
