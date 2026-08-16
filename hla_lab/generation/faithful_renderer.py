"""Render generic, data-driven LaTeX entrypoints for faithful page layouts.

Faithful recreations retain page-sized adapters for pagination and visual
comparison.  This module makes their order a projection of semantic content
blocks instead of a hand-maintained list in ``main.tex``.  The adapters remain
layout-only: semantic ownership stays in the validated document model.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path, PurePosixPath

from pydantic import Field, model_validator

from hla_lab.adapters.latex_renderer import tex_escape
from hla_lab.core.semantic_model import ContentBlock, DocumentModel, SemanticRecord

__all__ = [
    "FaithfulLayoutEntry",
    "FaithfulLayoutInsertion",
    "FaithfulLayoutProfile",
    "FaithfulLayoutProjection",
    "FaithfulLayoutSegment",
    "FaithfulLayoutStaticEntry",
    "build_faithful_layout_projection",
    "load_faithful_layout_profile",
    "render_faithful_body",
]

class FaithfulLayoutEntry(SemanticRecord):
    """One source-controlled layout adapter selected by semantic block order."""

    source_path: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    content_block_ids: tuple[str, ...] = ()
    clause_ids: tuple[str, ...] = ()
    layout_only: bool = False
    before_latex: str = ""
    after_latex: str = ""

class FaithfulLayoutInsertion(SemanticRecord):
    """A layout-only command inserted before one semantic page sequence."""

    before_sequence: int = Field(ge=0)
    latex: str = Field(min_length=1)

class FaithfulLayoutSegment(SemanticRecord):
    """A contiguous semantic page range with optional layout wrappers."""

    id: str = Field(min_length=1)
    start_sequence: int = Field(ge=0)
    end_sequence: int = Field(ge=0)
    before_latex: str = ""
    after_latex: str = ""
    insertions: tuple[FaithfulLayoutInsertion, ...] = ()

    @model_validator(mode="after")
    def validate_sequence_range(self) -> FaithfulLayoutSegment:
        if self.end_sequence < self.start_sequence:
            raise ValueError("faithful layout segment end must not precede start")
        return self

class FaithfulLayoutStaticEntry(SemanticRecord):
    """An intentional layout-only page that has no semantic content block."""

    id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    before_latex: str = ""
    after_latex: str = ""

class FaithfulLayoutProfile(SemanticRecord):
    """Source-controlled pagination boundaries independent of semantic prose."""

    schema_version: int = Field(default=1, ge=1)
    document_id: str = Field(min_length=1)
    segments: tuple[FaithfulLayoutSegment, ...] = ()
    static_entries: tuple[FaithfulLayoutStaticEntry, ...] = ()

class FaithfulLayoutProjection(SemanticRecord):
    """A generated body include stream and its semantic provenance."""

    schema_version: int = Field(default=1, ge=1)
    document_id: str = Field(min_length=1)
    entries: tuple[FaithfulLayoutEntry, ...]

def _input_path(source_path: str) -> str:
    path = PurePosixPath(source_path)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".tex":
        raise ValueError(f"faithful layout source must be a relative .tex path: {source_path}")
    return path.with_suffix("").as_posix()

def load_faithful_layout_profile(path: PathLike[str] | str) -> FaithfulLayoutProfile:
    """Load a typed layout-boundary profile without treating it as prose."""
    location = Path(path)
    return FaithfulLayoutProfile.model_validate_json(location.read_text(encoding="utf-8"))

def _append_latex(existing: str, addition: str) -> str:
    return "\n".join(value for value in (existing, addition) if value)

def build_faithful_layout_projection(
    model: DocumentModel,
    *,
    content_block_ids: tuple[str, ...] | None = None,
    profile: FaithfulLayoutProfile | None = None,
) -> FaithfulLayoutProjection:
    """Group page adapters by semantic source and order them by block sequence."""
    selected_ids = set(content_block_ids) if content_block_ids is not None else None
    grouped: dict[str, list[ContentBlock]] = {}
    candidates = tuple(
        block for block in model.content_blocks if selected_ids is None or block.id in selected_ids
    )
    layout_blocks = tuple(block for block in candidates if block.layout_body is not None)
    # Small generic fixtures may not need an exact-page adapter. HLA's typed
    # profile always selects layout-body pages, which prevents derived prose
    # fragments from moving a physical page out of sequence.
    selected_blocks = layout_blocks or candidates
    for block in selected_blocks:
        _input_path(block.source.path)
        grouped.setdefault(block.source.path, []).append(block)

    semantic_entries = tuple(
        FaithfulLayoutEntry(
            source_path=source_path,
            sequence=min(item.sequence for item in blocks),
            content_block_ids=tuple(item.id for item in sorted(blocks, key=lambda item: item.id)),
            clause_ids=tuple(
                sorted({item.clause_id for item in blocks if item.clause_id is not None})
            ),
        )
        for source_path, blocks in grouped.items()
    )
    if profile is None:
        entries = tuple(
            sorted(semantic_entries, key=lambda item: (item.sequence, item.source_path))
        )
    else:
        if profile.document_id != model.document_id:
            raise ValueError(
                f"faithful layout profile {profile.document_id} does not match {model.document_id}"
            )
        static_entries = tuple(
            FaithfulLayoutEntry(
                source_path=entry.source_path,
                sequence=entry.sequence,
                layout_only=True,
                before_latex=entry.before_latex,
                after_latex=entry.after_latex,
            )
            for entry in profile.static_entries
        )
        for entry in static_entries:
            _input_path(entry.source_path)
        used_sources: set[str] = set()
        entries_by_segment: list[FaithfulLayoutEntry] = []
        for segment in profile.segments:
            entries = [
                entry
                for entry in (*semantic_entries, *static_entries)
                if segment.start_sequence <= entry.sequence <= segment.end_sequence
            ]
            entries.sort(key=lambda item: (item.sequence, item.layout_only, item.source_path))
            if not entries:
                raise ValueError(f"faithful layout segment {segment.id} has no entries")
            duplicates = used_sources.intersection(item.source_path for item in entries)
            if duplicates:
                raise ValueError(
                    f"faithful layout adapters appear in multiple segments: {sorted(duplicates)}"
                )
            used_sources.update(item.source_path for item in entries)
            entries[0] = entries[0].model_copy(
                update={
                    "before_latex": _append_latex(entries[0].before_latex, segment.before_latex)
                }
            )
            entries[-1] = entries[-1].model_copy(
                update={"after_latex": _append_latex(entries[-1].after_latex, segment.after_latex)}
            )
            for insertion in segment.insertions:
                index = next(
                    (
                        item
                        for item, entry in enumerate(entries)
                        if entry.sequence == insertion.before_sequence
                    ),
                    None,
                )
                if index is None:
                    raise ValueError(
                        f"faithful layout insertion in {segment.id} has no entry at "
                        f"sequence {insertion.before_sequence}"
                    )
                entries[index] = entries[index].model_copy(
                    update={
                        "before_latex": _append_latex(
                            entries[index].before_latex,
                            insertion.latex,
                        )
                    }
                )
            entries_by_segment.extend(entries)
        expected_sources = {item.source_path for item in (*semantic_entries, *static_entries)}
        if used_sources != expected_sources:
            missing = sorted(expected_sources - used_sources)
            raise ValueError(f"faithful layout profile does not place adapters: {missing}")
        entries = tuple(entries_by_segment)
    return FaithfulLayoutProjection(
        document_id=model.document_id,
        entries=entries,
    )

def render_faithful_body(projection: FaithfulLayoutProjection) -> str:
    """Render a deterministic LaTeX include stream for faithful layout adapters."""
    lines = [
        "% Generated faithful body; edit semantic content-block records instead.",
        (
            "\\providecommand{\\SemanticFaithfulBodyDocumentID}"
            f"{{{tex_escape(projection.document_id)}}}"
        ),
        f"\\providecommand{{\\SemanticFaithfulBodyEntryCount}}{{{len(projection.entries)}}}",
    ]
    for entry in projection.entries:
        block_ids = ",".join(entry.content_block_ids)
        comment = (
            f"% sequence={entry.sequence}; blocks={block_ids}; "
            f"layout-only={str(entry.layout_only).lower()}"
        )
        if entry.before_latex:
            lines.append(entry.before_latex)
        lines.extend(
            (
                comment,
                f"\\input{{{_input_path(entry.source_path)}}}",
            )
        )
        if entry.after_latex:
            lines.append(entry.after_latex)
    return "\n".join(lines)
