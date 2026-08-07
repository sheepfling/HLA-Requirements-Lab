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
    additional_note_commands: tuple[str, ...] = (
        "HLACompactFootnote",
        "HLAFootnote",
    )
    stable_id: str = "HLAStableID"
    table_grid_cell: str = "HLATableGridCell"
    table_cell_text: str = "HLATableCellText"
    table_text_line: str = "HLARotatedLine"
    placed_block: str = "HLAClausePlacedBlock"
    table_caption: str = "HLATableCaption"
    table_domain: Literal["generic", "omt"] = "omt"
    figure_image: str = "HLAFigureImageAt"
    figure_caption: str = "HLAFigureCaptionAt"
    figure_anchor: str = "HLAFigureAnchor"
    diagram_surface_document_id: str | None = "hla-1516.1-2025"
    # Published early figures reuse a few composite semantic state machines;
    # this binding table maps each faithful page surface to the record that
    # should render it. The generic model never depends on these HLA numbers.
    diagram_surface_bindings: tuple[tuple[int, int, str], ...] = (
        (1, 38, "federation-execution"),
        (2, 39, "hla-1516.1.figure-2-federate-rti-relationship"),
        (3, 40, "federate-lifetime"),
        (4, 41, "federate-lifetime"),
        (5, 43, "normal-activity-permitted"),
        (6, 45, "federation-execution-sync-overview"),
        (7, 46, "global-synchronization-label"),
        (8, 46, "awaiting-synchronization"),
        (9, 47, "local-synchronization-label"),
        (10, 86, "object-class"),
        (11, 87, "class-attribute"),
        (12, 88, "class-attribute-privilege-to-delete-object"),
        (13, 89, "interaction-class"),
        (14, 110, "object-instance-known"),
        (15, 111, "ownership-implications"),
        (16, 149, "establishing-ownership"),
        (17, 186, "temporal-state"),
    )
    # Source-page rectangles for semantic diagram replacements. Diagram
    # meaning remains in generic Pydantic records; only this faithful HLA
    # layout adapter knows the published figure coordinates.
    embedded_diagram_layout: tuple[tuple[int, float, float, float, float], ...] = (
        (1, 125.28, 425.64, 361.44, 247.98),
        (2, 138.66, 193.38, 334.68, 251.04),
        (3, 89.5, 71.0, 433.5, 281.0),
        (4, 77.52, 277.02, 453.48, 369.0),
        (5, 69.78, 207.24, 472.44, 397.62),
        (6, 92.82, 129.54, 448.74, 363.48),
        (7, 89.409, 81.423, 433.183, 317.035),
        (8, 89.28, 396.785, 433.44, 278.672),
        (9, 89.298, 81.119, 433.755, 373.141),
        (10, 100.92, 126.96, 403.08, 302.34),
        (11, 129.234, 140.364, 358.272, 477.432),
        (12, 125.4, 132.96, 379.98, 506.7),
        (13, 76.44, 180.84, 459.12, 336.84),
        (14, 118.259, 354.42, 375.482, 309.72),
        (15, 82.08, 103.02, 447.84, 335.88),
        (16, 84.24, 69.14, 463.32, 617.76),
        (17, 88.834, 134.718, 428.912, 523.007),
        (18, 120.0, 92.0, 400.0, 205.0),
        (19, 145.0, 92.0, 330.0, 180.0),
        (20, 100.0, 264.0, 495.0, 245.0),
        (21, 150.0, 220.0, 395.0, 155.0),
        (22, 120.0, 235.0, 400.0, 105.0),
        (23, 120.0, 440.0, 400.0, 105.0),
        (24, 120.0, 465.0, 410.0, 160.0),
        (25, 120.0, 185.0, 410.0, 160.0),
        (26, 120.0, 70.0, 410.0, 170.0),
        (27, 105.0, 325.0, 420.0, 115.0),
        (28, 105.0, 500.0, 420.0, 115.0),
        (29, 105.0, 90.0, 420.0, 125.0),
        (30, 105.0, 350.0, 420.0, 125.0),
        (31, 105.0, 555.0, 420.0, 120.0),
        (32, 105.0, 90.0, 420.0, 135.0),
        (33, 105.0, 340.0, 420.0, 135.0),
    )
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
