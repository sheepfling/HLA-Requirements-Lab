"""HLA-neutral LaTeX rendering for semantic records."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from hla_lab.core.semantic_model import (
    Clause,
    ContentBlock,
    ContentElement,
    CrossReference,
    Definition,
    DocumentModel,
    Figure,
    Note,
    Reference,
    Requirement,
    Table,
    TableFamily,
    Transition,
)
from hla_lab.core.text import tex_escape


@dataclass(frozen=True)
class LatexDialect:
    """Commands and environments supplied by a document's LaTeX profile."""

    clause_heading_command: str
    subclause_heading_command: str
    definition_environment: str
    detailed_rule_heading_command: str
    normative_rule_statement_command: str
    summary_rule_command: str
    table_environment: str = "table"
    tabular_environment: str = "tabular"
    anchor_command: str = "hypertarget"
    bookmark_command: str = "pdfbookmark"
    cross_reference_command: str = "hyperlink"
    heading_embeds_anchor: bool = False


def semantic_macro_name(prefix: str, record_id: str, suffix: str) -> str:
    """Return a portable TeX macro name for a semantic record field."""
    parts = [part for part in re.split(r"[^a-zA-Z0-9]+", record_id) if part]
    compact = "".join(part[:1].upper() + part[1:] for part in parts)
    digit_names = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
    compact = "".join(
        digit_names[int(character)] if character.isdigit() else character for character in compact
    )
    return f"Semantic{prefix}{compact}{suffix}"


def render_definition_data(definition: Definition) -> str:
    """Render a definition as layout-consumable TeX data macros."""
    return "\n".join(
        (
            "% Generated semantic data; layout adapters consume these macros.",
            (
                f"\\providecommand{{\\{semantic_macro_name('Definition', definition.id, 'ID')}}}"
                f"{{{tex_escape(definition.id)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Definition', definition.id, 'Term')}}}"
                f"{{{tex_escape(definition.term)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Definition', definition.id, 'Text')}}}"
                f"{{{tex_escape(definition.text)}}}"
            ),
        )
    )


def render_requirement_data(requirement: Requirement) -> str:
    """Render a requirement as layout-consumable TeX data macros."""
    return "\n".join(
        (
            "% Generated semantic data; layout adapters consume these macros.",
            (
                f"\\providecommand{{\\{semantic_macro_name('Requirement', requirement.id, 'ID')}}}"
                f"{{{tex_escape(requirement.id)}}}"
            ),
            (
                "\\providecommand{\\"
                f"{semantic_macro_name('Requirement', requirement.id, 'Title')}}}"
                f"{{{tex_escape(requirement.title)}}}"
            ),
            (
                "\\providecommand{\\"
                f"{semantic_macro_name('Requirement', requirement.id, 'Statement')}}}"
                f"{{{tex_escape(requirement.statement)}}}"
            ),
        )
    )


def render_content_block_data(block: ContentBlock) -> str:
    """Render source-owned prose as a layout-consumable TeX data macro."""
    lines = [
        "% Generated semantic data; layout adapters consume these macros.",
        (
            f"\\providecommand{{\\{semantic_macro_name('ContentBlock', block.id, 'ID')}}}"
            f"{{{tex_escape(block.id)}}}"
        ),
    ]
    if block.layout_body is None:
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('ContentBlock', block.id, 'Text')}}}"
            f"{{{tex_escape(block.text)}}}"
        )
    return "\n".join(lines)


def render_reference_data(reference: Reference) -> str:
    """Render a bibliography/reference record as visible semantic data."""
    return "\n".join(
        (
            "% Generated semantic reference data; layout adapters consume these macros.",
            (
                f"\\providecommand{{\\{semantic_macro_name('Reference', reference.id, 'ID')}}}"
                f"{{{tex_escape(reference.id)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Reference', reference.id, 'Label')}}}"
                f"{{{tex_escape(reference.label)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Reference', reference.id, 'Text')}}}"
                f"{{{tex_escape(reference.text)}}}"
            ),
        )
    )


def render_cross_reference_data(cross_reference: CrossReference) -> str:
    """Render a resolved semantic link as portable TeX metadata."""

    def command(field: str, value: str) -> str:
        macro = semantic_macro_name("CrossReference", cross_reference.id, field)
        return f"\\providecommand{{\\{macro}}}{{{tex_escape(value)}}}"

    return "\n".join(
        (
            "% Generated semantic cross-reference data; layout adapters consume these macros.",
            command("ID", cross_reference.id),
            command("OwnerID", cross_reference.owner_id),
            command("TargetDocumentID", cross_reference.target_document_id),
            command("TargetRecordID", cross_reference.target_record_id),
            command("Label", cross_reference.label),
            command("Kind", cross_reference.kind),
            command("Relation", cross_reference.relation),
        )
    )


def render_figure_data(figure: Figure) -> str:
    """Render a figure record without making its comparison image an input."""
    return "\n".join(
        (
            "% Generated semantic figure data; layout adapters consume these macros.",
            (
                f"\\providecommand{{\\{semantic_macro_name('Figure', figure.id, 'ID')}}}"
                f"{{{tex_escape(figure.id)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Figure', figure.id, 'Number')}}}"
                f"{{{tex_escape(figure.number)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Figure', figure.id, 'Caption')}}}"
                f"{{{tex_escape(figure.caption)}}}"
            ),
        )
    )


def render_note_data(note: Note) -> str:
    """Render a note or footnote record as semantic data."""
    return "\n".join(
        (
            "% Generated semantic note data; layout adapters consume these macros.",
            (
                f"\\providecommand{{\\{semantic_macro_name('Note', note.id, 'ID')}}}"
                f"{{{tex_escape(note.id)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Note', note.id, 'Kind')}}}"
                f"{{{tex_escape(note.kind)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('Note', note.id, 'Text')}}}"
                f"{{{tex_escape(note.text)}}}"
            ),
        )
    )


def render_content_block(block: ContentBlock) -> str:
    """Render the faithful body owned by a semantic content block."""
    if block.layout_body is not None:
        return block.layout_body
    return f"% Generated semantic prose block.\n{tex_escape(block.text)}"


def render_content_element_data(element: ContentElement) -> str:
    """Render a typed content element as portable TeX metadata."""
    return "\n".join(
        (
            "% Generated typed content data; layout adapters may consume these macros.",
            (
                f"\\providecommand{{\\{semantic_macro_name('ContentElement', element.id, 'ID')}}}"
                f"{{{tex_escape(element.id)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('ContentElement', element.id, 'Kind')}}}"
                f"{{{tex_escape(element.kind)}}}"
            ),
            (
                f"\\providecommand{{\\{semantic_macro_name('ContentElement', element.id, 'Text')}}}"
                f"{{{tex_escape(element.text)}}}"
            ),
            (
                "\\providecommand{\\"
                f"{semantic_macro_name('ContentElement', element.id, 'ClauseID')}}}"
                f"{{{tex_escape(element.clause_id or '')}}}"
            ),
            (
                "\\providecommand{\\"
                f"{semantic_macro_name('ContentElement', element.id, 'BlockID')}}}"
                f"{{{tex_escape(element.block_id)}}}"
            ),
            (
                "\\providecommand{\\"
                f"{semantic_macro_name('ContentElement', element.id, 'ParentID')}}}"
                f"{{{tex_escape(element.parent_id or '')}}}"
            ),
            (
                "\\providecommand{\\"
                f"{semantic_macro_name('ContentElement', element.id, 'RecordIDs')}}}"
                f"{{{tex_escape(','.join(element.record_ids))}}}"
            ),
        )
    )


def render_table_family_data(
    family: TableFamily,
    tables: Iterable[Table],
    *,
    include_cells: bool = True,
) -> str:
    """Render table-family metadata and caption macros for layout adapters."""
    ordered_tables = tuple(tables)
    lines = [
        "% Generated semantic table-family data; layout adapters consume these macros.",
        (
            f"\\providecommand{{\\{semantic_macro_name('TableFamily', family.id, 'ID')}}}"
            f"{{{tex_escape(family.id)}}}"
        ),
        (
            f"\\providecommand{{\\{semantic_macro_name('TableFamily', family.id, 'Title')}}}"
            f"{{{tex_escape(family.title)}}}"
        ),
        (
            f"\\providecommand{{\\{semantic_macro_name('TableFamily', family.id, 'TableIDs')}}}"
            f"{{{tex_escape(','.join(table.id for table in ordered_tables))}}}"
        ),
    ]
    for table in ordered_tables:
        caption = family.table_captions.get(table.id) or table.caption or table.title or table.id
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'Caption')}}}"
            f"{{{tex_escape(caption)}}}"
        )
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'FamilyID')}}}"
            f"{{{tex_escape(family.id)}}}"
        )
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'LogicalID')}}}"
            f"{{{tex_escape(table.logical_id or table.id)}}}"
        )
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'ContinuedFrom')}}}"
            f"{{{tex_escape(table.continued_from or '')}}}"
        )
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'CellIDs')}}}"
            f"{{{tex_escape(','.join(cell.id for cell in table.cells))}}}"
        )
        if include_cells:
            for cell in table.cells:
                text_macro = semantic_macro_name("TableCell", cell.id, "Text")
                row_macro = semantic_macro_name("TableCell", cell.id, "Row")
                lines.extend(
                    (
                        (f"\\providecommand{{\\{text_macro}}}{{{tex_escape(cell.text)}}}"),
                        (
                            f"\\providecommand{{\\{row_macro}}}"
                            f"{{{'' if cell.row is None else cell.row}}}"
                        ),
                        (
                            "\\providecommand{\\"
                            f"{semantic_macro_name('TableCell', cell.id, 'Column')}}}"
                            f"{{{'' if cell.column is None else cell.column}}}"
                        ),
                        (
                            "\\providecommand{\\"
                            f"{semantic_macro_name('TableCell', cell.id, 'RecordIDs')}}}"
                            f"{{{tex_escape(','.join(cell.record_ids))}}}"
                        ),
                    )
                )
    return "\n".join(lines)


def render_table_data(table: Table, *, caption_override: str | None = None) -> str:
    """Render one typed table record for caption and cell consumers."""
    caption = caption_override or table.caption or table.title or table.id
    lines = [
        "% Generated semantic table data; layout adapters consume these macros.",
        (
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'ID')}}}"
            f"{{{tex_escape(table.id)}}}"
        ),
        (
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'Caption')}}}"
            f"{{{tex_escape(caption)}}}"
        ),
        (
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'LogicalID')}}}"
            f"{{{tex_escape(table.logical_id or table.id)}}}"
        ),
        (
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'FamilyID')}}}"
            f"{{{tex_escape(table.family_id or '')}}}"
        ),
        (
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'ContinuedFrom')}}}"
            f"{{{tex_escape(table.continued_from or '')}}}"
        ),
        (
            f"\\providecommand{{\\{semantic_macro_name('Table', table.id, 'CellIDs')}}}"
            f"{{{tex_escape(','.join(cell.id for cell in table.cells))}}}"
        ),
    ]
    for cell in table.cells:
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('TableCell', cell.id, 'Text')}}}"
            f"{{{tex_escape(cell.text)}}}"
        )
        lines.append(
            f"\\providecommand{{\\{semantic_macro_name('TableCell', cell.id, 'RecordIDs')}}}"
            f"{{{tex_escape(','.join(cell.record_ids))}}}"
        )
    return "\n".join(lines)


def semantic_destination(record_id: str, document_id: str | None = None) -> str:
    """Return the stable PDF destination for a semantic record.

    Qualified destinations are the cross-document link contract. A generated
    record and a generated link use the same ``document-id:record-id`` key;
    unqualified IDs remain available for standalone compatibility output.
    """
    return f"{document_id}:{record_id}" if document_id else record_id


def render_anchor(
    record_id: str,
    dialect: LatexDialect,
    *,
    document_id: str | None = None,
) -> str:
    """Render a zero-size anchor keyed by a semantic record ID."""
    destination = semantic_destination(record_id, document_id)
    return f"\\{dialect.anchor_command}{{{tex_escape(destination)}}}{{}}"


def render_bookmark(
    label: str,
    level: int,
    dialect: LatexDialect,
    *,
    destination: str,
) -> str:
    """Render a PDF outline entry whose destination is a semantic ID."""
    return (
        f"\\{dialect.bookmark_command}[{level}]"
        f"{{{tex_escape(label)}}}{{bookmark:{tex_escape(destination)}}}"
    )


def render_cross_document_link(
    label: str,
    target_document: str,
    target_id: str,
    dialect: LatexDialect,
) -> str:
    """Render a link to a semantic ID in a combined document build."""
    destination = semantic_destination(target_id, target_document)
    return (
        f"\\{dialect.cross_reference_command}{{{tex_escape(destination)}}}{{{tex_escape(label)}}}"
    )


def render_clause_heading(
    clause: Clause,
    dialect: LatexDialect,
    *,
    document_id: str | None = None,
) -> str:
    """Render a clause node through the selected LaTeX dialect."""
    command = (
        dialect.clause_heading_command if clause.level == 1 else dialect.subclause_heading_command
    )
    destination = semantic_destination(clause.id, document_id)
    lines = []
    if not dialect.heading_embeds_anchor:
        lines.append(render_anchor(clause.id, dialect, document_id=document_id))
    lines.append(
        render_bookmark(
            clause.title,
            max(clause.level - 1, 0),
            dialect,
            destination=destination,
        )
    )
    lines.append(f"\\{command}{{{clause.id}}}{{{tex_escape(clause.title)}}}")
    return "\n".join(lines)


def render_definition(
    definition: Definition,
    dialect: LatexDialect,
    *,
    document_id: str | None = None,
) -> str:
    """Render a definition record through the selected LaTeX dialect."""
    lines = []
    if document_id:
        lines.append(render_anchor(definition.id, dialect, document_id=document_id))
    optional_gap = f"[{definition.leading_gap}]" if definition.leading_gap is not None else ""
    body = (
        definition.layout_body
        if definition.layout_body is not None
        else tex_escape(definition.text)
    )
    lines.extend(
        (
            f"\\begin{{{dialect.definition_environment}}}"
            f"{optional_gap}{{{definition.id}}}{{{tex_escape(definition.term)}}}",
            body,
            f"\\end{{{dialect.definition_environment}}}",
        )
    )
    return "\n".join(lines)


def render_requirement(
    requirement: Requirement,
    dialect: LatexDialect,
    *,
    document_id: str | None = None,
) -> str:
    """Render a normative requirement through the selected LaTeX dialect."""
    prefix = render_anchor(requirement.id, dialect, document_id=document_id) if document_id else ""
    if requirement.kind == "summary":
        body = (
            f"\\{dialect.summary_rule_command}"
            f"{{{tex_escape(requirement.id)}}}"
            f"{{{tex_escape(requirement.statement)}}}"
        )
        return "\n".join(item for item in (prefix, body) if item)
    heading = (
        f"\\{dialect.detailed_rule_heading_command}"
        f"{{{requirement.id}}}{{{tex_escape(requirement.title)}}}"
    )
    statement = (
        f"\\{dialect.normative_rule_statement_command}{{{tex_escape(requirement.statement)}}}"
    )
    return "\n".join(item for item in (prefix, heading, statement) if item)


def render_table(
    table: Table,
    dialect: LatexDialect,
    *,
    document_id: str | None = None,
) -> str:
    """Render a semantic table as a portable dialect-backed LaTeX block."""
    prefix = render_anchor(table.id, dialect, document_id=document_id) if document_id else ""
    caption = table.caption or table.title or table.id
    positioned = {}
    for cell in table.cells:
        if cell.row is not None and cell.column is not None:
            positioned.setdefault((cell.row, cell.column), []).append(cell)
    row_count = max((row for row, _ in positioned), default=-1) + 1
    column_count = max((column for _, column in positioned), default=-1) + 1
    if not row_count or not column_count:
        body = (
            f"% {table.id}\n% {tex_escape(caption)}\n"
            f"\\begin{{{dialect.tabular_environment}}}{{l}}"
            f"\\end{{{dialect.tabular_environment}}}"
        )
        return "\n".join(item for item in (prefix, body) if item)

    lines = [
        f"% {table.id}",
        f"\\begin{{{dialect.table_environment}}}[ht]",
        f"\\caption{{{tex_escape(caption)}}}",
        f"\\begin{{{dialect.tabular_environment}}}{{{'l' * column_count}}}",
    ]
    for row in range(row_count):
        values = []
        for column in range(column_count):
            cells = positioned.get((row, column), ())
            values.append(tex_escape(" ".join(cell.text for cell in cells)))
        lines.append(" & ".join(values) + r" \\")
    lines.extend(
        (
            f"\\end{{{dialect.tabular_environment}}}",
            f"\\end{{{dialect.table_environment}}}",
        )
    )
    return "\n".join(item for item in (prefix, "\n".join(lines)) if item)


def render_transition_event(transition: Transition, suffix: str = "") -> str:
    """Render an event with an optional renderer-owned suffix."""
    if not transition.event:
        return ""
    return f"{tex_escape(transition.event)}{suffix}"


def render_outline(
    model: DocumentModel,
    dialect: LatexDialect,
    *,
    document_id: str | None = None,
) -> str:
    """Render a hierarchy-only outline through the selected dialect."""
    document_id = document_id or model.document_id or None
    return "\n".join(
        _render_outline_node(model, item, dialect, document_id=document_id)
        for item in model.root_clauses()
    )


def _render_outline_node(
    model: DocumentModel,
    clause: Clause,
    dialect: LatexDialect,
    *,
    document_id: str | None = None,
) -> str:
    lines = [
        f"% {clause.id}",
        render_clause_heading(clause, dialect, document_id=document_id),
    ]
    for child in model.children_of(clause.id):
        lines.append(_render_outline_node(model, child, dialect, document_id=document_id))
    return "\n".join(lines)


def render_records(
    model: DocumentModel,
    dialect: LatexDialect,
    *,
    definitions: Iterable[Definition] = (),
    requirements: Iterable[Requirement] = (),
    tables: Iterable[Table] = (),
) -> str:
    """Render selected records in deterministic source order."""
    order = {item_id: index for index, item_id in enumerate(model.canonical_record_ids())}
    ordered_definitions = sorted(
        definitions, key=lambda item: (order.get(item.id, len(order)), item.id)
    )
    ordered_requirements = sorted(
        requirements, key=lambda item: (order.get(item.id, len(order)), item.id)
    )
    document_id = model.document_id or None
    blocks = [
        render_definition(item, dialect, document_id=document_id) for item in ordered_definitions
    ]
    blocks.extend(
        render_requirement(item, dialect, document_id=document_id) for item in ordered_requirements
    )
    blocks.extend(render_table(item, dialect, document_id=document_id) for item in tables)
    return "\n\n".join(blocks)
