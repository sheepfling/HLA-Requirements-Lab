"""Profile and LaTeX dialect for the non-HLA M13 fixture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scripts.latex_renderer import LatexDialect


@dataclass(frozen=True)
class DemoSourceCommands:
    """The source vocabulary supplied by this document family."""

    clause_headings: tuple[str, ...] = ("DemoClauseHeading", "DemoSubclauseHeading")
    content_marker: str = "DemoContentMarker"
    fixed_text_block: str = "DemoFixedBlock"
    clause_paragraph: str = "DemoClauseParagraph"
    clause_labeled_item: str = "DemoClauseLabeledItem"
    pdf_bookmark: str = "pdfbookmark"
    definition_environment: str = "demodefinition"
    detailed_rule_heading: str = "DemoDetailedRuleHeading"
    summary_rule: str = "DemoSummaryRule"
    normative_rule_statement: str = "DemoNormativeRuleStatement"
    bibliography_entry: str = "DemoBibliographyEntry"
    footnote_text: str = "footnotetext"
    stable_id: str = "DemoStableID"
    table_grid_cell: str = "DemoTableGridCell"
    table_cell_text: str = "DemoTableCellText"
    placed_block: str = "DemoPlacedBlock"
    table_caption: str = "DemoTableCaption"
    table_domain: Literal["generic", "omt"] = "generic"
    figure_image: str = "DemoFigureImageAt"
    figure_caption: str = "DemoFigureCaptionAt"
    figure_anchor: str = "DemoFigureAnchor"
    definition_at: str = "DemoDefinitionAt"
    definition_anchor: str = "DemoDefinitionAnchor"
    definition_term: str = "DemoDefinitionTerm"
    definition_note_at: str = "DemoDefinitionNoteAt"
    note_block: str = "DemoNoteBlock"
    definition_note_commands: tuple[str, ...] = ("DemoDefinitionNote",)
    annex_heading: str = "DemoAnnexHeading"
    annex_status: str = "DemoAnnexStatus"
    annex_title: str = "DemoAnnexTitle"
    toc_line_at: str = "DemoTocLineAt"
    annex_bookmark: str = "bookmark"
    table_heading_commands: tuple[tuple[str, int, int], ...] = ()
    hierarchy_heading_commands: tuple[tuple[str, int, int], ...] = ()
    hierarchy_id_commands: tuple[tuple[str, int, int], ...] = ()
    text_wrapper_commands: tuple[str, ...] = ("DemoTerm",)
    text_note_commands: tuple[str, ...] = ("DemoNote",)
    layout_text_block_commands: tuple[tuple[str, int], ...] = ()


DEMO_SOURCE = DemoSourceCommands()

DEMO_LATEX_DIALECT = LatexDialect(
    clause_heading_command="DemoClauseHeading",
    subclause_heading_command="DemoSubclauseHeading",
    definition_environment="demodefinition",
    detailed_rule_heading_command="DemoDetailedRuleHeading",
    normative_rule_statement_command="DemoNormativeRuleStatement",
    summary_rule_command="DemoSummaryRule",
)
