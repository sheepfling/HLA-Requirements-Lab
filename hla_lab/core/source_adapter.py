"""Generic LaTeX source vocabulary contract.

Document-specific command names belong in a profile module such as
``hla_profile``.  The semantic loader depends only on this structural
contract, which lets another document family provide the same vocabulary
without importing HLA constants into the model layer.
"""

from __future__ import annotations

from typing import Literal, Protocol

class LatexSourceProfile(Protocol):
    """Command vocabulary required by the source-first semantic loader."""

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
