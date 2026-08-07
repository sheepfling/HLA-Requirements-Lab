"""Generic semantic-to-LaTeX build generation."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.export_graph_diagram import render_tikz as render_graph_tikz
from scripts.export_sequence_diagram import render_tikz as render_sequence_tikz
from scripts.faithful_renderer import (
    FaithfulLayoutProfile,
    build_faithful_layout_projection,
    render_faithful_body,
)
from scripts.hierarchy_compiler import (
    compile_hierarchy,
    render_block_bindings,
    render_hierarchy_index,
    render_hierarchy_outline,
)
from scripts.latex_renderer import (
    LatexDialect,
    render_content_block,
    render_content_block_data,
    render_content_element_data,
    render_cross_reference_data,
    render_definition,
    render_definition_data,
    render_figure_data,
    render_note_data,
    render_reference_data,
    render_requirement,
    render_requirement_data,
    render_table_data,
    render_table_family_data,
    semantic_macro_name,
    tex_escape,
)
from scripts.render_state_machine import render as render_state_machine
from scripts.semantic_model import (
    ContentBlock,
    DocumentModel,
    Table,
    _command_events,
    load_document_model,
)
from scripts.source_adapter import LatexSourceProfile


def _safe_name(identifier: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", identifier).strip("-")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _figure_number(caption: str) -> int | None:
    match = re.search(r"\bFigure\s+(\d+)\b", caption)
    return int(match.group(1)) if match else None


def _embed_diagram(
    body: str,
    figure_number: int,
    input_name: str,
    layout: dict[int, tuple[float, float, float, float]],
) -> str:
    """Insert generated TikZ before the native source caption block."""
    geometry = layout.get(figure_number)
    if geometry is None:
        return body
    x, y, width, height = geometry
    macro = (
        f"  \\HLAEmbeddedTikZAt{{{x:g}}}{{{y:g}}}{{{width:g}}}{{{height:g}}}{{%\n"
        f"    \\input{{output/semantic/{input_name}}}%\n"
        "  }\n"
    )
    lines = body.splitlines()
    marker = f"Figure {figure_number}"
    caption_marker = f"\\HLAFigureCaptionAt{{{figure_number}}}"
    caption_index = next(
        (index for index, line in enumerate(lines) if caption_marker in line),
        None,
    )
    macro_line = macro.rstrip("\n")
    if caption_index is not None:
        image_index = next(
            (
                candidate
                for candidate in range(caption_index - 1, -1, -1)
                if "\\HLAFigureImageAt{" in lines[candidate]
            ),
            None,
        )
        if image_index is not None:
            lines[image_index] = macro_line
        else:
            lines.insert(caption_index, macro_line)
        return "\n".join(lines)
    image_indices = [index for index, line in enumerate(lines) if "\\HLAFigureImageAt{" in line]
    if len(image_indices) == 1:
        lines[image_indices[0]] = macro_line
        return "\n".join(lines)
    for index, line in enumerate(lines):
        if marker not in line:
            continue
        caption_start = next(
            (
                candidate
                for candidate in range(index, -1, -1)
                if "\\HLAFixedBlock{" in lines[candidate]
            ),
            None,
        )
        if caption_start is None:
            image_index = next(
                (
                    candidate
                    for candidate, line in enumerate(lines)
                    if "\\HLAFigureImageAt{" in line
                ),
                None,
            )
            if image_index is None:
                return body
            lines[image_index] = macro_line
            return "\n".join(lines)
        image_index = next(
            (
                candidate
                for candidate in range(caption_start - 1, -1, -1)
                if "\\HLAFigureImageAt{" in lines[candidate]
            ),
            None,
        )
        if image_index is not None:
            lines[image_index] = macro_line
        else:
            lines.insert(caption_start, macro_line)
        return "\n".join(lines)
    return body


def _wrapped_macro(name: str, values: tuple[str, ...]) -> list[str]:
    """Render a long comma-separated macro without oversized TeX input lines."""
    if not values:
        return [f"\\providecommand{{\\Semantic{name}}}{{}}"]
    chunks: list[str] = []
    current = ""
    for value in values:
        item = value if not current else f",{value}"
        if current and len(current) + len(item) > 96:
            chunks.append(current)
            current = value
        else:
            current += item
    if current:
        chunks.append(current)
    return [
        f"\\providecommand{{\\Semantic{name}}}{{%",
        *(f"{tex_escape(chunk)}%" for chunk in chunks),
        "}",
    ]


def _argument_spans(text: str, start: int, count: int) -> tuple[tuple[int, int], ...]:
    """Return balanced-brace argument spans for a LaTeX command."""
    command = re.match(r"\\[A-Za-z@]+", text[start:])
    if command is None:
        return ()
    cursor = start + command.end()
    spans: list[tuple[int, int]] = []
    for _ in range(count):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            return ()
        depth = 1
        body_start = cursor + 1
        cursor += 1
        while cursor < len(text) and depth:
            if text[cursor] == "\\":
                cursor += 2
                continue
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
            cursor += 1
        if depth:
            return ()
        spans.append((body_start, cursor - 1))
    return tuple(spans)


def _replace_command_arguments(
    body: str,
    events: tuple[tuple[int, tuple[str, ...], int], ...],
    replacements: tuple[tuple[int, int, str], ...],
) -> str:
    """Replace selected balanced command arguments without disturbing geometry."""
    changes: list[tuple[int, int, str]] = []
    for event_index, argument_index, value in replacements:
        if event_index >= len(events):
            continue
        start, args, _end = events[event_index]
        spans = _argument_spans(body, start, len(args))
        if argument_index < len(spans):
            left, right = spans[argument_index]
            changes.append((left, right, value))
    for left, right, value in sorted(changes, reverse=True):
        body = body[:left] + value + body[right:]
    return body


def _semanticize_visible_surfaces(
    body: str,
    block: ContentBlock,
    model: DocumentModel,
    source: LatexSourceProfile,
) -> str:
    """Replace visible semantic payloads with generated-record macros.

    Coordinates, wrappers, and line-break hints remain in the fidelity body;
    the words that carry semantic identity are emitted by typed records.
    """
    block_path = block.source.path
    references = tuple(item for item in model.references if item.source.path == block_path)
    reference_events = _command_events(body, source.bibliography_entry, 3)
    reference_replacements: list[tuple[int, int, str]] = []
    for index, reference in enumerate(references):
        if index >= len(reference_events):
            break
        reference_replacements.extend(
            (
                (index, 1, f"\\{semantic_macro_name('Reference', reference.id, 'Label')}"),
                (index, 2, f"\\{semantic_macro_name('Reference', reference.id, 'Text')}"),
            )
        )
    if reference_replacements:
        body = _replace_command_arguments(
            body,
            reference_events,
            tuple(reference_replacements),
        )

    figures = tuple(item for item in model.figures if item.source.path == block_path)
    figure_events = _command_events(body, source.figure_caption, 3)
    figure_replacements: list[tuple[int, int, str]] = []
    figure_caption_text_replacements: list[tuple[str, str]] = []
    for index, figure in enumerate(figures):
        if index >= len(figure_events):
            break
        figure_replacements.append(
            (
                index,
                2,
                f"\\{semantic_macro_name('Figure', figure.id, 'Caption')}",
            )
        )
        if figure.caption:
            figure_caption_text_replacements.append(
                (
                    f"Figure {figure.number}---{figure.caption}",
                    f"Figure {figure.number}---"
                    f"\\{semantic_macro_name('Figure', figure.id, 'Caption')}",
                )
            )
    if figure_replacements:
        body = _replace_command_arguments(body, figure_events, tuple(figure_replacements))
    for old, new in figure_caption_text_replacements:
        body = body.replace(old, new)

    tables = tuple(item for item in model.tables if item.source.path == block_path)
    table_events = _command_events(body, source.table_caption, 1)
    table_replacements: list[tuple[int, int, str]] = []
    table_index = 0
    for event_index in range(len(table_events)):
        while table_index < len(tables) and not (
            tables[table_index].caption or tables[table_index].title
        ):
            table_index += 1
        if table_index >= len(tables):
            break
        table = tables[table_index]
        table_replacements.append(
            (
                event_index,
                0,
                f"\\{semantic_macro_name('Table', table.id, 'Caption')}",
            )
        )
        table_index += 1
    if table_replacements:
        body = _replace_command_arguments(body, table_events, tuple(table_replacements))

    # Faithful 1516.1 pages draw captions directly inside fixed text
    # primitives rather than using ``HLATableCaption``. Replace only those
    # title primitives; their coordinates and surrounding table geometry stay
    # in the page adapter while the visible caption comes from the table
    # record/family projection.
    tables_by_number: dict[str, list[Table]] = {}
    for table in tables:
        if table.number is not None:
            tables_by_number.setdefault(table.number, []).append(table)
    for command_name, argument_count in (
        (source.fixed_text_block, 7),
        (getattr(source, "table_text_line", ""), 5),
    ):
        if not command_name:
            continue
        events = _command_events(body, command_name, argument_count)
        replacements: list[tuple[int, int, str]] = []
        for index, (_offset, args, _end) in enumerate(events):
            match = re.search(r"\\textbf\{\s*Table\s+(\d+)\b", args[-1], re.IGNORECASE)
            if match is None:
                continue
            candidates = tables_by_number.get(match.group(1), [])
            if not candidates:
                continue
            table = candidates.pop(0)
            replacements.append(
                (
                    index,
                    argument_count - 1,
                    f"\\{semantic_macro_name('Table', table.id, 'Caption')}",
                )
            )
        if replacements:
            body = _replace_command_arguments(body, events, tuple(replacements))

    requirements = {item.id: item for item in model.requirements}
    summary_events = _command_events(body, source.summary_rule, 2)
    summary_replacements = tuple(
        (
            index,
            1,
            f"\\{semantic_macro_name('Requirement', args[0], 'Statement')}",
        )
        for index, (_offset, args, _end) in enumerate(summary_events)
        if args[0] in requirements
    )
    if summary_replacements:
        body = _replace_command_arguments(body, summary_events, summary_replacements)

    detailed_events = _command_events(body, source.detailed_rule_heading, 2)
    detailed_replacements = tuple(
        (
            index,
            1,
            f"\\{semantic_macro_name('Requirement', args[0], 'Title')}",
        )
        for index, (_offset, args, _end) in enumerate(detailed_events)
        if args[0] in requirements
    )
    if detailed_replacements:
        body = _replace_command_arguments(body, detailed_events, detailed_replacements)

    normative_events = _command_events(body, source.normative_rule_statement, 1)
    normative_replacements: list[tuple[int, int, str]] = []
    for index, (offset, _args, _end) in enumerate(normative_events):
        prior = [item for item in detailed_events if item[0] < offset]
        if prior and prior[-1][1][0] in requirements:
            normative_replacements.append(
                (
                    index,
                    0,
                    f"\\{semantic_macro_name('Requirement', prior[-1][1][0], 'Statement')}",
                )
            )
    if normative_replacements:
        body = _replace_command_arguments(body, normative_events, tuple(normative_replacements))
    return body


def _semantic_content_body(block: ContentBlock, model: DocumentModel) -> str | None:
    """Render a layout-free prose block from its typed content elements."""
    if block.layout_body is not None:
        return None
    elements = {item.id: item for item in model.content_elements if item.block_id == block.id}
    values = [
        f"\\{semantic_macro_name('ContentElement', element.id, 'Text')}"
        for element_id in block.element_ids
        if (element := elements.get(element_id)) is not None
        and element.kind in {"paragraph", "note", "footnote", "list-item"}
    ]
    return "\n\n".join(values) if values else None


def render_build_manifest(
    model: DocumentModel,
    generated_files: tuple[str, ...],
    semantic_inputs: tuple[str, ...] = (),
) -> str:
    """Render a small generated entrypoint consumed by every LaTeX build."""
    lines = [
        "% Generated from the typed semantic model; edit semantic source instead.",
        f"\\providecommand{{\\SemanticDocumentID}}{{{tex_escape(model.document_id)}}}",
        f"\\providecommand{{\\SemanticSchemaVersion}}{{{model.schema_version}}}",
        f"\\providecommand{{\\SemanticClauseCount}}{{{len(model.clauses)}}}",
        f"\\providecommand{{\\SemanticDefinitionCount}}{{{len(model.definitions)}}}",
        f"\\providecommand{{\\SemanticRequirementCount}}{{{len(model.requirements)}}}",
        f"\\providecommand{{\\SemanticContentElementCount}}{{{len(model.content_elements)}}}",
        f"\\providecommand{{\\SemanticStateMachineCount}}{{{len(model.state_machines)}}}",
        f"\\providecommand{{\\SemanticSequenceDiagramCount}}{{{len(model.sequence_diagrams)}}}",
        f"\\providecommand{{\\SemanticGraphDiagramCount}}{{{len(model.graph_diagrams)}}}",
        f"\\providecommand{{\\SemanticReferenceCount}}{{{len(model.references)}}}",
        f"\\providecommand{{\\SemanticCrossReferenceCount}}{{{len(model.cross_references)}}}",
        f"\\providecommand{{\\SemanticFigureCount}}{{{len(model.figures)}}}",
        f"\\providecommand{{\\SemanticNoteCount}}{{{len(model.notes)}}}",
        f"\\providecommand{{\\SemanticTableCount}}{{{len(model.tables)}}}",
        *_wrapped_macro("GeneratedFiles", generated_files),
        (
            "\\typeout{Semantic model loaded: "
            f"{tex_escape(model.document_id)} ({len(model.clauses)} clauses)}}"
        ),
    ]
    lines.extend(
        f"\\input{{output/semantic/{Path(name).with_suffix('').as_posix()}}}"
        for name in semantic_inputs
    )
    return "\n".join(lines)


def _render_semantic_index(model: DocumentModel) -> str:
    """Render model-wide IDs so every build consumes semantic source data."""
    values = {
        "CanonicalRecordIDs": model.canonical_record_ids(),
        "RootClauseIDs": tuple(item.id for item in model.root_clauses()),
        "DefinitionIDs": tuple(item.id for item in model.ordered_definitions()),
        "RequirementIDs": tuple(item.id for item in model.ordered_requirements()),
        "ContentElementIDs": tuple(item.id for item in model.content_elements),
        "StateMachineIDs": tuple(item.id for item in model.state_machines),
        "SequenceDiagramIDs": tuple(item.id for item in model.sequence_diagrams),
        "GraphDiagramIDs": tuple(item.id for item in model.graph_diagrams),
        "ReferenceIDs": tuple(item.id for item in model.references),
        "CrossReferenceIDs": tuple(item.id for item in model.cross_references),
        "FigureIDs": tuple(item.id for item in model.figures),
        "NoteIDs": tuple(item.id for item in model.notes),
        "TableIDs": tuple(item.id for item in model.tables),
    }
    lines = ["% Generated semantic index; layout adapters consume these IDs."]
    for suffix, identifiers in values.items():
        if not identifiers:
            lines.append(f"\\providecommand{{\\Semantic{suffix}}}{{}}")
            continue
        lines.append(f"\\providecommand{{\\Semantic{suffix}}}{{%")
        lines.extend(
            f"{tex_escape(identifier)}{',' if index < len(identifiers) - 1 else ''}%"
            for index, identifier in enumerate(identifiers)
        )
        lines.append("}")
    return "\n".join(lines)


def generate(
    root: Path,
    output: Path,
    *,
    source: LatexSourceProfile,
    dialect: LatexDialect,
    definition_ids: tuple[str, ...] = (),
    requirement_ids: tuple[str, ...] = (),
    content_block_ids: tuple[str, ...] = (),
    content_element_ids: tuple[str, ...] = (),
    table_family_ids: tuple[str, ...] | None = (),
    include_outline: bool = False,
    include_table_cells: bool = True,
    include_faithful_body: bool = False,
    faithful_layout_profile: FaithfulLayoutProfile | None = None,
) -> DocumentModel:
    """Generate selected semantic blocks and a build manifest."""
    model = load_document_model(root, source)
    compiled_hierarchy = compile_hierarchy(model)
    output.mkdir(parents=True, exist_ok=True)
    # This directory is a generated-only build input. Remove stale generated
    # TeX blocks before writing the current deterministic selection; unrelated
    # review/export artifacts live in separate ignored directories.
    for path in output.glob("*.tex"):
        path.unlink()
    definitions = {item.id: item for item in model.ordered_definitions()}
    requirements = {item.id: item for item in model.ordered_requirements()}
    content_blocks = {item.id: item for item in model.content_blocks}
    content_elements = {item.id: item for item in model.content_elements}
    table_families = {item.id: item for item in model.table_families}
    tables = {item.id: item for item in model.tables}
    index_name = "semantic-index.tex"
    _write(output / index_name, _render_semantic_index(model))
    generated_files: list[str] = [index_name]
    semantic_inputs: list[str] = [index_name]

    for item in model.references:
        name = f"reference-{_safe_name(item.id)}-data.tex"
        _write(output / name, render_reference_data(item))
        generated_files.append(name)
        semantic_inputs.append(name)
    for item in model.cross_references:
        name = f"cross-reference-{_safe_name(item.id)}-data.tex"
        _write(output / name, render_cross_reference_data(item))
        generated_files.append(name)
    for item in model.figures:
        name = f"figure-{_safe_name(item.id)}-data.tex"
        _write(output / name, render_figure_data(item))
        generated_files.append(name)
        semantic_inputs.append(name)
    for item in model.notes:
        name = f"note-{_safe_name(item.id)}-data.tex"
        _write(output / name, render_note_data(item))
        generated_files.append(name)
        semantic_inputs.append(name)
    for item in model.tables:
        name = f"table-record-{_safe_name(item.id)}-data.tex"
        _write(output / name, render_table_data(item))
        generated_files.append(name)
        semantic_inputs.append(name)

    # Diagram TeX is generated from the typed records and can be consumed by
    # both standalone review builds and faithful source-page adapters.
    diagram_inputs: dict[str, str] = {}
    embedded_diagram_layout = {
        figure_number: (x, y, width, height)
        for figure_number, x, y, width, height in getattr(source, "embedded_diagram_layout", ())
    }
    diagram_bindings = getattr(source, "diagram_surface_bindings", ())
    if getattr(source, "diagram_surface_document_id", model.document_id) != model.document_id:
        diagram_bindings = ()
    for machine in model.state_machines:
        name = f"state-machine-{_safe_name(machine.id)}.tex"
        _write(output / name, render_state_machine(machine.model_dump(mode="json")))
        generated_files.append(name)
        diagram_inputs[machine.id] = name
    for diagram in model.sequence_diagrams:
        name = f"sequence-diagram-{_safe_name(diagram.id)}.tex"
        _write(output / name, render_sequence_tikz(diagram))
        generated_files.append(name)
        diagram_inputs[diagram.id] = name
    for diagram in model.graph_diagrams:
        name = f"graph-diagram-{_safe_name(diagram.id)}.tex"
        _write(output / name, render_graph_tikz(diagram))
        generated_files.append(name)
        diagram_inputs[diagram.id] = name

    hierarchy_json_name = "hierarchy.json"
    _write(output / hierarchy_json_name, compiled_hierarchy.to_json())
    generated_files.append(hierarchy_json_name)
    hierarchy_name = "hierarchy-index.tex"
    _write(output / hierarchy_name, render_hierarchy_index(compiled_hierarchy))
    generated_files.append(hierarchy_name)
    semantic_inputs.append(hierarchy_name)

    for identifier in definition_ids:
        if identifier not in definitions:
            raise ValueError(f"unknown definition ID: {identifier}")
        name = f"definition-{_safe_name(identifier)}.tex"
        _write(
            output / name,
            render_definition(
                definitions[identifier],
                dialect,
                document_id=model.document_id,
            ),
        )
        generated_files.append(name)
        data_name = f"definition-{_safe_name(identifier)}-data.tex"
        _write(output / data_name, render_definition_data(definitions[identifier]))
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    for identifier in requirement_ids:
        if identifier not in requirements:
            raise ValueError(f"unknown requirement ID: {identifier}")
        name = f"requirement-{_safe_name(identifier)}.tex"
        _write(
            output / name,
            render_requirement(
                requirements[identifier],
                dialect,
                document_id=model.document_id,
            ),
        )
        generated_files.append(name)
        data_name = f"requirement-{_safe_name(identifier)}-data.tex"
        _write(output / data_name, render_requirement_data(requirements[identifier]))
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    for identifier in content_block_ids:
        if identifier not in content_blocks:
            raise ValueError(f"unknown content block ID: {identifier}")
        name = f"content-block-{_safe_name(identifier)}.tex"
        block = content_blocks[identifier]
        body = block.layout_body or ""
        if block.layout_body is not None:
            body = _semanticize_visible_surfaces(body, block, model, source)
        else:
            body = _semantic_content_body(block, model) or body
        embedded_figures: set[int] = set()
        for figure_number, page_sequence, record_id in diagram_bindings:
            if page_sequence != block.sequence:
                continue
            input_name = diagram_inputs.get(record_id)
            if input_name is None:
                raise ValueError(
                    f"diagram surface Figure {figure_number} references missing record {record_id}"
                )
            body = _embed_diagram(body, figure_number, input_name, embedded_diagram_layout)
            embedded_figures.add(figure_number)
        for diagram in (*model.state_machines, *model.sequence_diagrams, *model.graph_diagrams):
            if diagram.provenance is None or diagram.provenance.page - 1 != block.sequence:
                continue
            figure_number = _figure_number(diagram.provenance.caption)
            input_name = diagram_inputs.get(diagram.id)
            if (
                figure_number is not None
                and figure_number not in embedded_figures
                and input_name is not None
            ):
                body = _embed_diagram(body, figure_number, input_name, embedded_diagram_layout)
        render_block = block.model_copy(update={"layout_body": body})
        _write(
            output / name,
            "\n".join(
                (
                    render_block_bindings(
                        model, render_block, dialect, compiled=compiled_hierarchy
                    ),
                    render_content_block(render_block),
                )
            ),
        )
        generated_files.append(name)
        data_name = f"content-block-{_safe_name(identifier)}-data.tex"
        _write(output / data_name, render_content_block_data(content_blocks[identifier]))
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    for identifier in content_element_ids:
        if identifier not in content_elements:
            raise ValueError(f"unknown content element ID: {identifier}")
        name = f"content-element-{_safe_name(identifier)}-data.tex"
        _write(output / name, render_content_element_data(content_elements[identifier]))
        generated_files.append(name)
        semantic_inputs.append(name)
    selected_table_family_ids = (
        tuple(table_families) if table_family_ids is None else table_family_ids
    )
    for identifier in selected_table_family_ids:
        if identifier not in table_families:
            raise ValueError(f"unknown table family ID: {identifier}")
        family = table_families[identifier]
        family_tables = tuple(tables[table_id] for table_id in family.table_ids)
        data_name = f"table-family-{_safe_name(identifier)}-data.tex"
        _write(
            output / data_name,
            render_table_family_data(
                family,
                family_tables,
                include_cells=include_table_cells,
            ),
        )
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    if include_outline:
        name = "clause-outline.tex"
        _write(output / name, render_hierarchy_outline(model, dialect))
        generated_files.append(name)
        semantic_inputs.append(name)

    if include_faithful_body:
        projection = build_faithful_layout_projection(
            model,
            content_block_ids=content_block_ids,
            profile=faithful_layout_profile,
        )
        name = "faithful-layout.json"
        _write(output / name, projection.model_dump_json(indent=2))
        generated_files.append(name)
        name = "faithful-body.tex"
        _write(output / name, render_faithful_body(projection))
        generated_files.append(name)

    _write(
        output / "semantic-manifest.tex",
        render_build_manifest(model, tuple(generated_files), tuple(semantic_inputs)),
    )
    return model
