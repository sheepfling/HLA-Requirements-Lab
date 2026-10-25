"""HLA source vocabulary loaded from the reviewed profile manifest."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from hla_lab.adapters.latex_renderer import LatexDialect
from hla_lab.core.coercions import coerce_int
from hla_lab.paths import RESOURCES, document_entry_for_root

__all__ = [
    "HLA_LATEX_DIALECT",
    "HLA_SOURCE",
    "HLA_SOURCE_2010",
    "HLA_SOURCE_PROFILES",
    "SOURCE_PROFILE_MANIFEST",
    "HlaSourceCommands",
    "source_profile_for_document",
]


# TODO: is this dataclasses mutable or immutable?
@dataclass(slots=True)
class HlaSourceCommands:
    """The HLA LaTeX vocabulary consumed by the source adapter."""

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
    diagram_surface_document_id: str | None
    diagram_surface_bindings: tuple[tuple[int, int, str], ...]
    embedded_diagram_layout: tuple[tuple[int, float, float, float, float], ...]
    landscape_figure_pages: tuple[tuple[int, int, str, str], ...]
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


SOURCE_PROFILE_MANIFEST = (
    RESOURCES.source_profiles_manifest
    if RESOURCES is not None
    else files("hla_lab").joinpath("source_profiles.json")
)


def _strings(commands: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value: JsonValue = commands[key]
    if not isinstance(value, list):
        raise ValueError(f"source profile command field {key} must be an array")
    items: list[JsonValue] = value
    return tuple(str(item) for item in items)


def _command_tuples(
    commands: Mapping[str, JsonValue], key: str, width: int
) -> tuple[tuple[JsonValue, ...], ...]:
    value: JsonValue = commands[key]
    if not isinstance(value, list):
        raise ValueError(f"source profile command field {key} must be an array")
    items: list[JsonValue] = value
    result = []
    for raw_item in items:
        item: JsonValue = raw_item
        if not isinstance(item, list) or len(item) != width:
            raise ValueError(f"source profile command field {key} has an invalid item")
        result.append(tuple(item))
    return tuple(result)


def _base_commands(commands: Mapping[str, JsonValue]) -> HlaSourceCommands:
    table_heading_commands = tuple(
        (
            str(item[0]),
            coerce_int(item[1], label="source profile command value"),
            coerce_int(item[2], label="source profile command value"),
        )
        for item in _command_tuples(commands, "table_heading_commands", 3)
    )
    hierarchy_heading_commands = tuple(
        (
            str(item[0]),
            coerce_int(item[1], label="source profile command value"),
            coerce_int(item[2], label="source profile command value"),
        )
        for item in _command_tuples(commands, "hierarchy_heading_commands", 3)
    )
    hierarchy_id_commands = tuple(
        (
            str(item[0]),
            coerce_int(item[1], label="source profile command value"),
            coerce_int(item[2], label="source profile command value"),
        )
        for item in _command_tuples(commands, "hierarchy_id_commands", 3)
    )
    layout_text_block_commands = tuple(
        (str(item[0]), coerce_int(item[1], label="source profile command value"))
        for item in _command_tuples(commands, "layout_text_block_commands", 2)
    )
    return HlaSourceCommands(
        clause_headings=_strings(commands, "clause_headings"),
        content_marker=str(commands["content_marker"]),
        fixed_text_block=str(commands["fixed_text_block"]),
        clause_paragraph=str(commands["clause_paragraph"]),
        clause_labeled_item=str(commands["clause_labeled_item"]),
        pdf_bookmark=str(commands["pdf_bookmark"]),
        definition_environment=str(commands["definition_environment"]),
        detailed_rule_heading=str(commands["detailed_rule_heading"]),
        summary_rule=str(commands["summary_rule"]),
        normative_rule_statement=str(commands["normative_rule_statement"]),
        bibliography_entry=str(commands["bibliography_entry"]),
        footnote_text=str(commands["footnote_text"]),
        additional_note_commands=_strings(commands, "additional_note_commands"),
        stable_id=str(commands["stable_id"]),
        table_grid_cell=str(commands["table_grid_cell"]),
        table_cell_text=str(commands["table_cell_text"]),
        table_text_line=str(commands["table_text_line"]),
        placed_block=str(commands["placed_block"]),
        table_caption=str(commands["table_caption"]),
        table_domain=str(commands["table_domain"]),  # type: ignore[arg-type]
        figure_image=str(commands["figure_image"]),
        figure_caption=str(commands["figure_caption"]),
        figure_anchor=str(commands["figure_anchor"]),
        diagram_surface_document_id=None,
        diagram_surface_bindings=(),
        embedded_diagram_layout=(),
        landscape_figure_pages=(),
        definition_at=str(commands["definition_at"]),
        definition_anchor=str(commands["definition_anchor"]),
        definition_term=str(commands["definition_term"]),
        definition_note_at=str(commands["definition_note_at"]),
        note_block=str(commands["note_block"]),
        definition_note_commands=_strings(commands, "definition_note_commands"),
        annex_heading=str(commands["annex_heading"]),
        annex_status=str(commands["annex_status"]),
        annex_title=str(commands["annex_title"]),
        toc_line_at=str(commands["toc_line_at"]),
        annex_bookmark=str(commands["annex_bookmark"]),
        table_heading_commands=table_heading_commands,
        hierarchy_heading_commands=hierarchy_heading_commands,
        hierarchy_id_commands=hierarchy_id_commands,
        text_wrapper_commands=_strings(commands, "text_wrapper_commands"),
        text_note_commands=_strings(commands, "text_note_commands"),
        layout_text_block_commands=layout_text_block_commands,
    )


def _load_source_profiles() -> dict[str, HlaSourceCommands]:
    """Load edition-specific faithful surface data from the source manifest."""

    payload = json.loads(SOURCE_PROFILE_MANIFEST.read_text(encoding="utf-8"))
    commands = _base_commands(payload["command_vocabulary"])
    profiles: dict[str, HlaSourceCommands] = {}
    for item in payload.get("profiles", ()):
        bindings = tuple(
            (int(binding["figure"]), int(binding["page_sequence"]), str(binding["record_id"]))
            for binding in item.get("diagram_surface_bindings", ())
        )
        layout = tuple(
            (
                int(geometry["figure"]),
                float(geometry["x"]),
                float(geometry["y"]),
                float(geometry["width"]),
                float(geometry["height"]),
            )
            for geometry in item.get("embedded_diagram_layout", ())
        )
        landscape_figure_pages = tuple(
            (
                int(page["figure"]),
                int(page["page_sequence"]),
                str(page["record_id"]),
                str(page["caption"]),
            )
            for page in item.get("landscape_figure_pages", ())
        )
        profile_id = str(item["id"])
        profiles[profile_id] = replace(
            commands,
            diagram_surface_document_id=item.get("diagram_surface_document_id"),
            diagram_surface_bindings=bindings,
            embedded_diagram_layout=layout,
            landscape_figure_pages=landscape_figure_pages,
        )
    return profiles


def _load_latex_dialect() -> LatexDialect:
    payload = json.loads(SOURCE_PROFILE_MANIFEST.read_text(encoding="utf-8"))
    return LatexDialect(**payload["latex_dialect"])


HLA_SOURCE_PROFILES = _load_source_profiles()
HLA_SOURCE = HLA_SOURCE_PROFILES["hla-2025"]
HLA_SOURCE_2010 = HLA_SOURCE_PROFILES["hla-2010"]
HLA_LATEX_DIALECT = _load_latex_dialect()


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
