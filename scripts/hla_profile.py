"""HLA-specific source macros and LaTeX dialect configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

try:
    from scripts.latex_renderer import LatexDialect
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from latex_renderer import LatexDialect


@dataclass(frozen=True)
class HlaSourceCommands:
    """The HLA LaTeX vocabulary consumed by the source adapter."""

    clause_headings: tuple[str, ...] = (
        "HLAClauseHeading",
        "HLASubclauseHeading",
        "HLAClause",
        "HLASubclause",
        "HLASubsubclause",
    )
    content_marker: str = "HLAContentMarker"
    fixed_text_block: str = "HLAFixedBlock"
    clause_paragraph: str = "HLAClauseParagraph"
    clause_labeled_item: str = "HLAClauseLabeledItem"
    pdf_bookmark: str = "pdfbookmark"
    definition_environment: str = "hladefinition"
    detailed_rule_heading: str = "HLADetailedRuleHeading"
    summary_rule: str = "HLASummaryRule"
    normative_rule_statement: str = "HLANormativeRuleStatement"
    bibliography_entry: str = "HLABibliographyEntry"
    footnote_text: str = "footnotetext"
    stable_id: str = "HLAStableID"
    table_grid_cell: str = "HLATableGridCell"
    table_cell_text: str = "HLATableCellText"
    placed_block: str = "HLAClausePlacedBlock"
    table_caption: str = "HLATableCaption"
    table_domain: Literal["generic", "omt"] = "omt"
    figure_image: str = "HLAFigureImageAt"
    figure_caption: str = "HLAFigureCaptionAt"
    figure_anchor: str = "HLAFigureAnchor"
    definition_at: str = "HLADefinitionAt"
    definition_anchor: str = "HLADefinitionAnchor"
    definition_term: str = "HLADefinitionTerm"
    definition_note_at: str = "HLADefinitionNoteAt"
    note_block: str = "HLANoteBlock"
    definition_note_commands: tuple[str, ...] = (
        "HLADefinitionNote",
        "HLADefinitionListNote",
    )
    annex_heading: str = "HLAAnnexHeading"
    annex_status: str = "HLAAnnexStatus"
    annex_title: str = "HLAAnnexTitle"
    toc_line_at: str = "HLATocLineAt"
    annex_bookmark: str = "bookmark"
    table_heading_commands: tuple[tuple[str, int, int], ...] = (
        ("HLAAnnexSubclauseHeading", 1, 0),
        ("HLAAnnexFittedSubclauseHeading", 2, 1),
        ("HLAMinorClauseHeading", 1, 0),
        ("HLAServiceHeadingAt", 3, 2),
    )
    hierarchy_heading_commands: tuple[tuple[str, int, int], ...] = (
        ("HLAAnnexSubclauseHeading", 1, 0),
        ("HLAAnnexFittedSubclauseHeading", 2, 1),
        ("HLAMinorClauseHeading", 1, 0),
    )
    hierarchy_id_commands: tuple[tuple[str, int, int], ...] = (("HLAServiceBookmark", 0, 2),)
    text_wrapper_commands: tuple[str, ...] = (
        "HLAService",
        "HLATermReference",
    )
    text_note_commands: tuple[str, ...] = (
        "HLASeeAlso",
        "HLADefinitionNote",
    )
    layout_text_block_commands: tuple[tuple[str, int], ...] = (
        ("HLAFixedBlock", 7),
        ("HLAFixedCenteredBlock", 7),
        ("HLAInvisibleFixedCenteredBlock", 7),
        ("HLAClausePlacedBlock", 4),
        ("HLAFrontPlacedBlock", 4),
    )


HLA_SOURCE = HlaSourceCommands()

HLA_LATEX_DIALECT = LatexDialect(
    clause_heading_command="HLAClauseHeading",
    subclause_heading_command="HLASubclauseHeading",
    definition_environment="hladefinition",
    detailed_rule_heading_command="HLADetailedRuleHeading",
    normative_rule_statement_command="HLANormativeRuleStatement",
    summary_rule_command="HLASummaryRule",
)
