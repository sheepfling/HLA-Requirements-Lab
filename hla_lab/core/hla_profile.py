"""HLA source vocabulary loaded from the reviewed profile manifest."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from hla_lab.adapters.latex_renderer import LatexDialect
from hla_lab.paths import document_entry_for_root

__all__ = [
    "HLA_LATEX_DIALECT",
    "HLA_SOURCE",
    "HLA_SOURCE_2010",
    "HLA_SOURCE_PROFILES",
    "SOURCE_PROFILE_MANIFEST",
    "HlaSourceCommands",
    "source_profile_for_document",
]


class HlaSourceCommands(BaseModel):
    """The HLA LaTeX vocabulary consumed by the source adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    clause_headings: tuple[str, ...]
    content_marker: str
    fixed_text_block: str
    clause_paragraph: str
    clause_labeled_item: str
    pdf_bookmark: str
    definition_environment: str
    detailed_rule_heading: str
    summary_rule: str
    normative_rule_statement: str
    bibliography_entry: str
    footnote_text: str
    additional_note_commands: tuple[str, ...]
    stable_id: str
    table_grid_cell: str
    table_cell_text: str
    table_text_line: str
    placed_block: str
    table_caption: str
    table_domain: Literal["generic", "omt"]
    figure_image: str
    figure_caption: str
    figure_anchor: str
    diagram_surface_document_id: str | None = None
    diagram_surface_bindings: tuple[tuple[int, int, str], ...] = ()
    embedded_diagram_layout: tuple[tuple[int, float, float, float, float], ...] = ()
    landscape_figure_pages: tuple[tuple[int, int, str, str], ...] = ()
    definition_at: str
    definition_anchor: str
    definition_term: str
    definition_note_at: str
    note_block: str
    definition_note_commands: tuple[str, ...]
    annex_heading: str
    annex_status: str
    annex_title: str
    toc_line_at: str
    annex_bookmark: str
    table_heading_commands: tuple[tuple[str, int, int], ...]
    hierarchy_heading_commands: tuple[tuple[str, int, int], ...]
    hierarchy_id_commands: tuple[tuple[str, int, int], ...]
    text_wrapper_commands: tuple[str, ...]
    text_note_commands: tuple[str, ...]
    layout_text_block_commands: tuple[tuple[str, int], ...]


class _DiagramSurfaceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    figure: int
    page_sequence: int
    record_id: str


class _EmbeddedDiagramLayout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    figure: int
    x: float
    y: float
    width: float
    height: float


class _LandscapeFigurePage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    figure: int
    page_sequence: int
    record_id: str
    caption: str


class _HlaSourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    diagram_surface_document_id: str | None = None
    diagram_surface_bindings: tuple[_DiagramSurfaceBinding, ...] = ()
    embedded_diagram_layout: tuple[_EmbeddedDiagramLayout, ...] = ()
    landscape_figure_pages: tuple[_LandscapeFigurePage, ...] = ()


ApiOwnerKind = Literal["service", "callback", "handler", "adapter"]


class _HlaSourceProfileManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    command_vocabulary: HlaSourceCommands
    latex_dialect: LatexDialect
    api_owners: Mapping[ApiOwnerKind, str]
    profiles: tuple[_HlaSourceProfile, ...]


SOURCE_PROFILE_MANIFEST = files("hla_lab").joinpath("source_profiles.json")


HLA_SOURCE_PROFILE_MANIFEST = _HlaSourceProfileManifest.model_validate_json(
    SOURCE_PROFILE_MANIFEST.read_text(encoding="utf-8")
)


def _load_source_profiles(manifest: _HlaSourceProfileManifest) -> dict[str, HlaSourceCommands]:
    """Load edition-specific faithful surface data from the source manifest."""

    commands = manifest.command_vocabulary
    profiles: dict[str, HlaSourceCommands] = {}
    for item in manifest.profiles:
        bindings = tuple(
            (binding.figure, binding.page_sequence, binding.record_id)
            for binding in item.diagram_surface_bindings
        )
        layout = tuple(
            (
                geometry.figure,
                geometry.x,
                geometry.y,
                geometry.width,
                geometry.height,
            )
            for geometry in item.embedded_diagram_layout
        )
        landscape_figure_pages = tuple(
            (
                page.figure,
                page.page_sequence,
                page.record_id,
                page.caption,
            )
            for page in item.landscape_figure_pages
        )
        profiles[item.id] = commands.model_copy(
            update={
                "diagram_surface_document_id": item.diagram_surface_document_id,
                "diagram_surface_bindings": bindings,
                "embedded_diagram_layout": layout,
                "landscape_figure_pages": landscape_figure_pages,
            }
        )
    return profiles


HLA_SOURCE_PROFILES = _load_source_profiles(HLA_SOURCE_PROFILE_MANIFEST)
HLA_SOURCE = HLA_SOURCE_PROFILES["hla-2025"]
HLA_SOURCE_2010 = HLA_SOURCE_PROFILES["hla-2010"]
HLA_LATEX_DIALECT = HLA_SOURCE_PROFILE_MANIFEST.latex_dialect


def source_profile_for_document(
    document_id: str, workspace_root: Path | None = None
) -> HlaSourceCommands:
    """Resolve the source profile declared by the canonical document registry."""

    profile_id = document_entry_for_root(document_id, workspace_root).profile_id
    if profile_id is None:
        raise ValueError(f"document {document_id} has no source profile")
    try:
        return HLA_SOURCE_PROFILES[profile_id]
    except KeyError as error:
        raise ValueError(
            f"document {document_id} references unknown source profile {profile_id}"
        ) from error
