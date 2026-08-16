"""Typed contracts for semantic document generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hla_lab.adapters.latex_renderer import LatexDialect
from hla_lab.core.semantic_model import DocumentModel
from hla_lab.core.source_adapter import LatexSourceProfile
from hla_lab.generation.faithful_renderer import (
    FaithfulLayoutProfile,
    FaithfulLayoutProjection,
)


@dataclass(frozen=True)
class GenerationRequest:
    """All inputs that control one deterministic semantic generation run."""

    root: Path
    output: Path
    source: LatexSourceProfile
    dialect: LatexDialect
    definition_ids: tuple[str, ...] = ()
    requirement_ids: tuple[str, ...] = ()
    content_block_ids: tuple[str, ...] = ()
    content_element_ids: tuple[str, ...] = ()
    table_family_ids: tuple[str, ...] | None = ()
    include_outline: bool = False
    include_table_cells: bool = True
    include_faithful_body: bool = False
    faithful_layout_profile: FaithfulLayoutProfile | None = None
    faithful_body_exclude_path_parts: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenerationResult:
    """Typed outputs produced by one semantic generation run."""

    model: DocumentModel
    output: Path
    generated_files: tuple[str, ...]
    semantic_inputs: tuple[str, ...]
    faithful_layout: FaithfulLayoutProjection | None = None
