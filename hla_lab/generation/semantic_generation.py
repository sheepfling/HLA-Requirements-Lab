"""Generic semantic-to-LaTeX build generation."""

from __future__ import (
    annotations,
)

import re
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from pathlib import (
    Path,
)

from pydantic import (
    JsonValue,
)

from hla_lab.adapters.latex_renderer import (
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
from hla_lab.core.io import write_text as _write
from hla_lab.core.semantic_model import (
    ContentBlock,
    ContentElement,
    Definition,
    DocumentModel,
    Figure,
    Reference,
    Requirement,
    StateMachine,
    Table,
    TableFamily,
    load_document_model,
)
from hla_lab.core.semantic_text import (
    _command_events,
)
from hla_lab.core.source_adapter import (
    LatexSourceProfile,
)
from hla_lab.diagrams.export_graph_diagram import (
    render_tikz as render_graph_tikz,
)
from hla_lab.diagrams.export_plantuml import (
    render as render_plantuml,
)
from hla_lab.diagrams.export_sequence_diagram import (
    render_tikz as render_sequence_tikz,
)
from hla_lab.diagrams.render_state_machine import (
    render as render_state_machine,
)
from hla_lab.generation.contracts import (
    GenerationRequest,
    GenerationResult,
)
from hla_lab.generation.faithful_renderer import (
    FaithfulLayoutProjection,
    build_faithful_layout_projection,
    render_faithful_body,
)
from hla_lab.generation.hierarchy_compiler import (
    CompiledHierarchy,
    compile_hierarchy,
    render_block_bindings,
    render_hierarchy_index,
    render_hierarchy_outline,
)
from hla_lab.generation.semantic_generation_diagrams import (
    _cross_edition_plantuml_payload,
    _embed_diagram,
    _figure_number,
    _generated_filename,
    _landscape_figure_page_body,
    _plantuml_ready,
    _plantuml_review,
    _promote_remaining_landscape_asset,
)
from hla_lab.generation.semantic_generation_mom import (
    _modern_mom_definition_rows as _modern_mom_definition_rows,
)
from hla_lab.generation.semantic_generation_mom import (
    _modern_mom_hierarchy_rows as _modern_mom_hierarchy_rows,
)
from hla_lab.generation.semantic_generation_reflow import (
    _fit_fixed_page_makeboxes,
    _modern_2025_statechart_reflow_page,
    _modern_statechart_reflow_page,
    _replace_command_arguments,
    _wrapped_macro,
)
from hla_lab.generation.semantic_generation_source_surface import (
    _modernize_2025_generated_tex,
    _modernize_2025_source_surface,
)
from hla_lab.generation.semantic_generation_special_pages import (
    _modern_api_manifest_page as _modern_api_manifest_page,
)
from hla_lab.generation.semantic_generation_special_pages import (
    _modern_java_factory_page as _modern_java_factory_page,
)
from hla_lab.generation.semantic_generation_special_pages import (
    _modern_protocol_prose_page as _modern_protocol_prose_page,
)
from hla_lab.generation.semantic_generation_special_pages import (
    _modern_service_flow_page,
    _modernize_2010_service_surface,
    _semantic_content_body,
)
from hla_lab.generation.semantic_generation_tables import (
    _modern_table5_page as _modern_table5_page,
)
from hla_lab.generation.semantic_generation_tables import (
    _modern_table_text as _modern_table_text,
)


def _semanticize_reference_labels(
    body: str,
    references: tuple[Reference, ...],
    source: LatexSourceProfile,
) -> str:
    events = _command_events(body, source.bibliography_entry, 3)
    replacements = [
        replacement
        for index, reference in enumerate(references)
        if index < len(events)
        for replacement in (
            (index, 1, f"\\{semantic_macro_name('Reference', reference.id, 'Label')}"),
            (index, 2, f"\\{semantic_macro_name('Reference', reference.id, 'Text')}"),
        )
    ]
    return _replace_command_arguments(body, events, tuple(replacements)) if replacements else body


def _semanticize_figure_captions(
    body: str,
    figures: tuple[Figure, ...],
    source: LatexSourceProfile,
) -> str:
    events = _command_events(body, source.figure_caption, 3)
    replacements: list[tuple[int, int, str]] = []
    caption_text_replacements: list[tuple[str, str]] = []
    for index, figure in enumerate(figures):
        if index >= len(events):
            break
        replacements.append((index, 2, f"\\{semantic_macro_name('Figure', figure.id, 'Caption')}"))
        if figure.caption:
            caption_text_replacements.append(
                (
                    f"Figure {figure.number}---{figure.caption}",
                    f"Figure {figure.number}---"
                    f"\\{semantic_macro_name('Figure', figure.id, 'Caption')}",
                )
            )
    if replacements:
        body = _replace_command_arguments(body, events, tuple(replacements))
    for old, new in caption_text_replacements:
        body = body.replace(old, new)
    return body


def _semanticize_table_caption_commands(
    body: str,
    tables: tuple[Table, ...],
    source: LatexSourceProfile,
) -> str:
    events = _command_events(body, source.table_caption, 1)
    captions = iter(table for table in tables if table.caption or table.title)
    replacements = []
    for event_index, _event in enumerate(events):
        table = next(captions, None)
        if table is None:
            break
        replacements.append(
            (event_index, 0, f"\\{semantic_macro_name('Table', table.id, 'Caption')}")
        )
    return _replace_command_arguments(body, events, tuple(replacements)) if replacements else body


def _semanticize_fixed_table_captions(
    body: str,
    tables: tuple[Table, ...],
    source: LatexSourceProfile,
) -> str:
    """Replace table titles inside faithful fixed-text geometry blocks."""
    tables_by_number: dict[str, list[Table]] = {}
    for table in tables:
        if table.number is not None:
            tables_by_number.setdefault(table.number, []).append(table)
    commands = (
        (source.fixed_text_block, 7),
        (getattr(source, "table_text_line", ""), 5),
    )
    for command_name, argument_count in commands:
        if not command_name:
            continue
        events = _command_events(body, command_name, argument_count)
        replacements: list[tuple[int, int, str]] = []
        for index, (_offset, args, _end) in enumerate(events):
            match = re.search(r"\\textbf\{\s*Table\s+(\d+)\b", args[-1], re.IGNORECASE)
            if match is None:
                continue
            candidates = tables_by_number.get(match.group(1), [])
            if candidates:
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
    return body


def _semanticize_requirement_summary(
    body: str, requirement_ids: AbstractSet[str], source: LatexSourceProfile
) -> str:
    events = _command_events(body, source.summary_rule, 2)
    replacements = tuple(
        (index, 1, f"\\{semantic_macro_name('Requirement', args[0], 'Statement')}")
        for index, (_offset, args, _end) in enumerate(events)
        if args[0] in requirement_ids
    )
    return _replace_command_arguments(body, events, replacements) if replacements else body


def _semanticize_requirement_headings(
    body: str, requirement_ids: AbstractSet[str], source: LatexSourceProfile
) -> tuple[str, tuple[tuple[int, tuple[str, ...], int], ...]]:
    events = _command_events(body, source.detailed_rule_heading, 2)
    replacements = tuple(
        (index, 1, f"\\{semantic_macro_name('Requirement', args[0], 'Title')}")
        for index, (_offset, args, _end) in enumerate(events)
        if args[0] in requirement_ids
    )
    if replacements:
        body = _replace_command_arguments(body, events, replacements)
    return body, events


def _semanticize_requirement_statements(
    body: str,
    requirement_ids: AbstractSet[str],
    detailed_events: Sequence[tuple[int, tuple[str, ...], int]],
    source: LatexSourceProfile,
) -> str:
    events = _command_events(body, source.normative_rule_statement, 1)
    replacements = []
    for index, (offset, _args, _end) in enumerate(events):
        prior = [item for item in detailed_events if item[0] < offset]
        if prior and prior[-1][1][0] in requirement_ids:
            requirement_id = prior[-1][1][0]
            replacements.append(
                (
                    index,
                    0,
                    f"\\{semantic_macro_name('Requirement', requirement_id, 'Statement')}",
                )
            )
    return _replace_command_arguments(body, events, tuple(replacements)) if replacements else body


def _semanticize_requirement_surfaces(
    body: str, requirements: tuple[Requirement, ...], source: LatexSourceProfile
) -> str:
    requirement_ids = {item.id for item in requirements}
    body = _semanticize_requirement_summary(body, requirement_ids, source)
    body, detailed_events = _semanticize_requirement_headings(body, requirement_ids, source)
    return _semanticize_requirement_statements(body, requirement_ids, detailed_events, source)


def _shift_page_40_fixed_block(match: re.Match[str]) -> str:
    y = float(match.group(2))
    if 408.0 <= y <= 672.9:
        return f"{match.group(1)}{{{y + 12.0:.3f}}}{match.group(3)}"
    return match.group(0)


def _correct_2025_page_40(body: str, block: ContentBlock) -> str:
    if block.sequence != 40:
        return body
    body = body.replace(
        r"\SemanticContentBlockProseConnectServiceInfrastructureText After\linebreak%",
        r"\SemanticContentBlockProseConnectServiceInfrastructureText\linebreak%",
    )
    body = body.replace(
        r"successful invocation of the \emph{Join Federation Execution}",
        r"After successful invocation of the \emph{Join Federation Execution}",
    )
    return re.sub(
        r"(\\HLAFixedBlock\{[^{}]+\})\{([0-9]+(?:\.[0-9]+)?)\}(\{)",
        _shift_page_40_fixed_block,
        body,
    )


def _correct_2025_page_48(body: str, block: ContentBlock, source: LatexSourceProfile) -> str:
    if block.sequence != 48:
        return body
    events = _command_events(body, source.fixed_text_block, 7)
    replacements = []
    for index, (_offset, args, _end) in enumerate(events):
        visible = args[-1]
        if "Comment note" in visible:
            replacements.append((index, 6, visible.split("(Comment note", 1)[0].rstrip()))
        elif "not part of FDD nor should it be and thus cannot be used for rejection" in visible:
            replacements.append((index, 6, ""))
    return _replace_command_arguments(body, events, tuple(replacements)) if replacements else body


def _correct_2025_cross_reference_typos(body: str, sequence: int) -> str:
    corrections = {
        397: (
            "Exceptions: The Annex E files define the encoding",
            "Exceptions: The Annex D files define the encoding",
        ),
        414: ("Federate Protocol API (see Annex E)", "Federate Protocol API (see Annex D)"),
    }
    correction = corrections.get(sequence)
    return body.replace(*correction) if correction is not None else body


def _correct_semantic_surface_anomalies(
    body: str, block: ContentBlock, model: DocumentModel, source: LatexSourceProfile
) -> str:
    body = re.sub(
        r"\s*\(Comment note - description is not part of FDD nor should it be "
        r"and thus cannot be used for rejection\.\)",
        "",
        body,
    ).replace("Directed interation", "Directed interaction")
    if model.document_id != "hla-1516.1-2025":
        return body
    body = _correct_2025_page_40(body, block)
    body = _correct_2025_page_48(body, block, source)
    return _correct_2025_cross_reference_typos(body, block.sequence)


def _semanticize_visible_surfaces(
    body: str,
    block: ContentBlock,
    model: DocumentModel,
    source: LatexSourceProfile,
) -> str:
    """Replace visible semantic payloads with generated-record macros."""
    block_path = block.source.path
    references = tuple(item for item in model.references if item.source.path == block_path)
    figures = tuple(item for item in model.figures if item.source.path == block_path)
    tables = tuple(item for item in model.tables if item.source.path == block_path)
    body = _semanticize_reference_labels(body, references, source)
    body = _semanticize_figure_captions(body, figures, source)
    body = _semanticize_table_caption_commands(body, tables, source)
    body = _semanticize_fixed_table_captions(body, tables, source)
    body = _semanticize_requirement_surfaces(body, model.requirements, source)
    return _correct_semantic_surface_anomalies(body, block, model, source)


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
    for name in semantic_inputs:
        input_line = f"\\input{{output/semantic/{Path(name).with_suffix('').as_posix()}}}"
        if name.startswith("content-element-"):
            # Faithful page adapters already carry their source-positioned
            # visible text.  Very large content-element text macros are only
            # needed by layout-free semantic prose, so allow a faithful
            # entrypoint to omit them when the TeX engine's memory budget is
            # tighter than the complete typed manifest.
            lines.extend(
                ("\\ifdefined\\HLASkipSemanticContentElementData", "\\else", input_line, "\\fi")
            )
        else:
            lines.append(input_line)
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


@dataclass(slots=True)
class _GenerationContext:
    request: GenerationRequest
    model: DocumentModel
    hierarchy: CompiledHierarchy
    definitions: dict[str, Definition]
    requirements: dict[str, Requirement]
    content_blocks: dict[str, ContentBlock]
    content_elements: dict[str, ContentElement]
    table_families: dict[str, TableFamily]
    tables: dict[str, Table]
    table_caption_overrides: dict[str, str]
    generated_files: list[str]
    semantic_inputs: list[str]
    faithful_layout: FaithfulLayoutProjection | None = None


@dataclass(slots=True)
class _DiagramAssets:
    diagram_inputs: dict[str, str]
    native_fallback_diagrams: set[str]
    captions: dict[str, str]
    embedded_layout: dict[int, tuple[float, float, float, float]]
    landscape_pages: dict[int, tuple[int, str, str]]
    bindings: tuple[tuple[int, int, str], ...]
    landscape_plantuml_ids: set[str]
    canonical_plantuml_payloads: dict[str, dict[str, JsonValue]]
    use_plantuml: bool
    reviewed_plantuml_ids: set[str] | None


def _prepare_generation_context(request: GenerationRequest) -> _GenerationContext:
    model = load_document_model(request.root, request.source)
    hierarchy = compile_hierarchy(model)
    request.output.mkdir(parents=True, exist_ok=True)
    for path in request.output.glob("*.tex"):
        path.unlink()
    return _GenerationContext(
        request=request,
        model=model,
        hierarchy=hierarchy,
        definitions={item.id: item for item in model.ordered_definitions()},
        requirements={item.id: item for item in model.ordered_requirements()},
        content_blocks={item.id: item for item in model.content_blocks},
        content_elements={item.id: item for item in model.content_elements},
        table_families={item.id: item for item in model.table_families},
        tables={item.id: item for item in model.tables},
        table_caption_overrides={
            table_id: caption
            for family in model.table_families
            for table_id, caption in family.table_captions.items()
        },
        generated_files=[],
        semantic_inputs=[],
    )


def _write_model_record_data(context: _GenerationContext) -> None:
    model = context.model
    output = context.request.output
    index_name = "semantic-index.tex"
    _write(output / index_name, _render_semantic_index(model))
    context.generated_files.append(index_name)
    context.semantic_inputs.append(index_name)
    for item in model.references:
        name = f"reference-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_reference_data(item))
        context.generated_files.append(name)
        context.semantic_inputs.append(name)
    for item in model.cross_references:
        name = f"cross-reference-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_cross_reference_data(item))
        context.generated_files.append(name)
    for item in model.figures:
        name = f"figure-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_figure_data(item))
        context.generated_files.append(name)
        context.semantic_inputs.append(name)
    for item in model.notes:
        name = f"note-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_note_data(item))
        context.generated_files.append(name)
        context.semantic_inputs.append(name)
    for item in model.tables:
        name = f"table-record-{_generated_filename(item.id)}-data.tex"
        _write(
            output / name,
            render_table_data(item, caption_override=context.table_caption_overrides.get(item.id)),
        )
        context.generated_files.append(name)
        context.semantic_inputs.append(name)


def _canonical_plantuml_payloads(
    context: _GenerationContext, use_plantuml: bool
) -> dict[str, dict[str, JsonValue]]:
    request = context.request
    if not use_plantuml or request.canonical_source is None:
        return {}
    canonical_root = request.root.parent / "hla-1516.1-2025"
    if not canonical_root.is_dir():
        return {}
    canonical_model = load_document_model(canonical_root, request.canonical_source)
    return {item.id: item.model_dump(mode="json") for item in canonical_model.state_machines}


def _prepare_diagram_assets(context: _GenerationContext) -> _DiagramAssets:
    request = context.request
    source = request.source
    model = context.model
    use_plantuml = request.state_machine_renderer == "plantuml"
    plantuml_review = _plantuml_review(request.root) if use_plantuml else None
    reviewed_ids = plantuml_review[0] if plantuml_review is not None else None
    landscape_ids = plantuml_review[1] if plantuml_review is not None else set()
    embedded_layout = {
        figure_number: (x, y, width, height)
        for figure_number, x, y, width, height in getattr(source, "embedded_diagram_layout", ())
    }
    landscape_pages = {
        sequence: (figure_number, record_id, caption)
        for figure_number, sequence, record_id, caption in getattr(
            source, "landscape_figure_pages", ()
        )
    }
    bindings = tuple(getattr(source, "diagram_surface_bindings", ()))
    if getattr(source, "diagram_surface_document_id", model.document_id) != model.document_id:
        bindings = ()
        embedded_layout = {}
        landscape_pages = {}
    return _DiagramAssets(
        diagram_inputs={},
        native_fallback_diagrams=set(),
        captions={},
        embedded_layout=embedded_layout,
        landscape_pages=landscape_pages,
        bindings=bindings,
        landscape_plantuml_ids=landscape_ids,
        canonical_plantuml_payloads=_canonical_plantuml_payloads(context, use_plantuml),
        use_plantuml=use_plantuml,
        reviewed_plantuml_ids=reviewed_ids,
    )


def _needs_native_plantuml_fallback(
    machine_id: str, payload: Mapping[str, JsonValue], assets: _DiagramAssets
) -> bool:
    if not assets.use_plantuml:
        return False
    return not _plantuml_ready(payload) or (
        assets.reviewed_plantuml_ids is not None and machine_id not in assets.reviewed_plantuml_ids
    )


def _write_state_machine_asset(
    context: _GenerationContext, assets: _DiagramAssets, machine: StateMachine
) -> None:
    output = context.request.output
    name = f"state-machine-{_generated_filename(machine.id)}.tex"
    source_payload: dict[str, JsonValue] = machine.model_dump(mode="json")
    plantuml_payload = _cross_edition_plantuml_payload(
        source_payload,
        document_id=context.model.document_id,
        canonical_payloads=assets.canonical_plantuml_payloads,
    )
    _write(output / name, render_state_machine(source_payload))
    context.generated_files.append(name)
    plantuml_name = f"state-machine-{_generated_filename(machine.id)}.puml"
    _write(output / plantuml_name, render_plantuml(plantuml_payload))
    context.generated_files.append(plantuml_name)
    if machine.provenance is not None:
        assets.captions[machine.id] = machine.provenance.caption
    if _needs_native_plantuml_fallback(machine.id, plantuml_payload, assets):
        assets.native_fallback_diagrams.add(machine.id)
        assets.diagram_inputs[machine.id] = name
        return
    assets.diagram_inputs[machine.id] = (
        f"state-machine-{_generated_filename(machine.id)}.pdf" if assets.use_plantuml else name
    )


def _write_sequence_diagram_assets(context: _GenerationContext, assets: _DiagramAssets) -> None:
    for diagram in context.model.sequence_diagrams:
        name = f"sequence-diagram-{_generated_filename(diagram.id)}.tex"
        _write(context.request.output / name, render_sequence_tikz(diagram))
        context.generated_files.append(name)
        assets.diagram_inputs[diagram.id] = name


def _write_graph_diagram_assets(context: _GenerationContext, assets: _DiagramAssets) -> None:
    for diagram in context.model.graph_diagrams:
        name = f"graph-diagram-{_generated_filename(diagram.id)}.tex"
        _write(context.request.output / name, render_graph_tikz(diagram))
        context.generated_files.append(name)
        assets.diagram_inputs[diagram.id] = name


def _write_diagram_assets(context: _GenerationContext) -> _DiagramAssets:
    assets = _prepare_diagram_assets(context)
    for machine in context.model.state_machines:
        _write_state_machine_asset(context, assets, machine)
    _write_sequence_diagram_assets(context, assets)
    _write_graph_diagram_assets(context, assets)
    return assets


def _write_hierarchy_assets(context: _GenerationContext) -> None:
    output = context.request.output
    _write(output / "hierarchy.json", context.hierarchy.to_json())
    context.generated_files.append("hierarchy.json")
    _write(output / "hierarchy-index.tex", render_hierarchy_index(context.hierarchy))
    context.generated_files.append("hierarchy-index.tex")
    context.semantic_inputs.append("hierarchy-index.tex")


def _write_definition(context: _GenerationContext, identifier: str) -> None:
    definition = context.definitions.get(identifier)
    if definition is None:
        raise ValueError(f"unknown definition ID: {identifier}")
    name = f"definition-{_generated_filename(identifier)}.tex"
    _write(
        context.request.output / name,
        render_definition(
            definition, context.request.dialect, document_id=context.model.document_id
        ),
    )
    context.generated_files.append(name)
    data_name = f"definition-{_generated_filename(identifier)}-data.tex"
    _write(context.request.output / data_name, render_definition_data(definition))
    context.generated_files.append(data_name)
    context.semantic_inputs.append(data_name)


def _write_requirement(context: _GenerationContext, identifier: str) -> None:
    requirement = context.requirements.get(identifier)
    if requirement is None:
        raise ValueError(f"unknown requirement ID: {identifier}")
    name = f"requirement-{_generated_filename(identifier)}.tex"
    _write(
        context.request.output / name,
        render_requirement(
            requirement, context.request.dialect, document_id=context.model.document_id
        ),
    )
    context.generated_files.append(name)
    data_name = f"requirement-{_generated_filename(identifier)}-data.tex"
    _write(context.request.output / data_name, render_requirement_data(requirement))
    context.generated_files.append(data_name)
    context.semantic_inputs.append(data_name)


def _initial_content_block_body(
    context: _GenerationContext, assets: _DiagramAssets, block: ContentBlock
) -> str:
    body = block.layout_body or ""
    landscape_page = assets.landscape_pages.get(block.sequence)
    if landscape_page is not None:
        figure_number, record_id, caption = landscape_page
        input_name = assets.diagram_inputs.get(record_id)
        if input_name is None:
            raise ValueError(
                f"landscape Figure {figure_number} references missing record {record_id}"
            )
        return _landscape_figure_page_body(
            figure_number=figure_number,
            record_id=record_id,
            caption=caption,
            input_name=input_name,
        )
    if block.layout_body is not None:
        body = _fit_fixed_page_makeboxes(body)
        return _semanticize_visible_surfaces(body, block, context.model, context.request.source)
    return _semantic_content_body(block, context.model) or body


def _modernize_content_block_body(
    body: str, context: _GenerationContext, block: ContentBlock
) -> str:
    document_id = context.model.document_id
    if (
        document_id == "hla-1516.1-2025"
        and context.request.service_page_renderer == "flow"
        and r"\HLAServiceHeadingAt" in body
    ):
        body = _modern_service_flow_page(body)
    if document_id == "hla-1516.1-2010" and context.request.service_page_renderer == "flow":
        body = _modernize_2010_service_surface(body)
    if document_id == "hla-1516.1-2025":
        body = _modernize_2025_source_surface(
            body, sequence=block.sequence, tables=context.model.tables
        )
    return body


def _reflow_statechart_pages_40_41(
    body: str, block: ContentBlock, assets: _DiagramAssets
) -> tuple[str, set[int]]:
    reflowed: set[int] = set()
    for figure_number, page_sequence, record_id in assets.bindings:
        if page_sequence != block.sequence:
            continue
        input_name = assets.diagram_inputs.get(record_id)
        caption = assets.captions.get(record_id)
        if input_name is None or caption is None:
            continue
        body = _modern_statechart_reflow_page(
            body,
            sequence=block.sequence,
            figure_number=figure_number,
            caption=caption,
            input_name=input_name,
        )
        reflowed.add(figure_number)
    return body, reflowed


def _reflow_statechart_pages_45_47(
    body: str, block: ContentBlock, assets: _DiagramAssets
) -> tuple[str, set[int]]:
    bound_figures = [
        (figure_number, assets.diagram_inputs[record_id], assets.captions[record_id])
        for figure_number, page_sequence, record_id in assets.bindings
        if page_sequence == block.sequence
        and record_id in assets.diagram_inputs
        and record_id in assets.captions
    ]
    if not bound_figures:
        return body, set()
    body = _modern_2025_statechart_reflow_page(body, sequence=block.sequence, figures=bound_figures)
    return body, {figure_number for figure_number, _input, _caption in bound_figures}


def _reflow_2025_statechart_page(
    body: str, block: ContentBlock, assets: _DiagramAssets
) -> tuple[str, set[int]]:
    if block.sequence in {40, 41}:
        return _reflow_statechart_pages_40_41(body, block, assets)
    if block.sequence in {45, 46, 47}:
        return _reflow_statechart_pages_45_47(body, block, assets)
    if block.sequence == 42:
        body = _modern_statechart_reflow_page(
            body, sequence=block.sequence, figure_number=0, caption="", input_name=""
        )
    return body, set()


def _embed_bound_diagram_surfaces(
    body: str, block: ContentBlock, assets: _DiagramAssets, reflowed_figures: AbstractSet[int]
) -> tuple[str, set[int]]:
    embedded: set[int] = set()
    for figure_number, page_sequence, record_id in assets.bindings:
        if page_sequence != block.sequence:
            continue
        if figure_number in reflowed_figures:
            embedded.add(figure_number)
            continue
        input_name = assets.diagram_inputs.get(record_id)
        if input_name is None:
            raise ValueError(
                f"diagram surface Figure {figure_number} references missing record {record_id}"
            )
        body = _embed_diagram(
            body,
            figure_number,
            input_name,
            assets.embedded_layout,
            preserve_native=record_id in assets.native_fallback_diagrams,
            caption=assets.captions.get(record_id),
            landscape=record_id in assets.landscape_plantuml_ids,
        )
        embedded.add(figure_number)
    return body, embedded


def _embed_model_diagrams(
    body: str,
    block: ContentBlock,
    context: _GenerationContext,
    assets: _DiagramAssets,
    embedded_figures: AbstractSet[int],
) -> str:
    diagrams = (
        *context.model.state_machines,
        *context.model.sequence_diagrams,
        *context.model.graph_diagrams,
    )
    for diagram in diagrams:
        if diagram.provenance is None or diagram.provenance.page - 1 != block.sequence:
            continue
        figure_number = _figure_number(diagram.provenance.caption)
        input_name = assets.diagram_inputs.get(diagram.id)
        if figure_number is None or figure_number in embedded_figures or input_name is None:
            continue
        body = _embed_diagram(
            body,
            figure_number,
            input_name,
            assets.embedded_layout,
            preserve_native=diagram.id in assets.native_fallback_diagrams,
            caption=assets.captions.get(diagram.id),
            landscape=diagram.id in assets.landscape_plantuml_ids,
        )
    return body


def _promote_2010_landscape_diagrams(
    body: str, context: _GenerationContext, assets: _DiagramAssets
) -> str:
    if context.model.document_id != "hla-1516.1-2010":
        return body
    for machine in context.model.state_machines:
        if machine.provenance is None:
            continue
        figure_match = re.search(r"figure-(\d+)$", machine.id)
        if figure_match is None:
            continue
        body = _promote_remaining_landscape_asset(
            body,
            figure_number=int(figure_match.group(1)),
            input_name=f"state-machine-{_generated_filename(machine.id)}.pdf",
            caption=machine.provenance.caption,
        )
    return body


def _render_content_block(
    context: _GenerationContext, assets: _DiagramAssets, identifier: str
) -> None:
    block = context.content_blocks.get(identifier)
    if block is None:
        raise ValueError(f"unknown content block ID: {identifier}")
    body = _initial_content_block_body(context, assets, block)
    body = _modernize_content_block_body(body, context, block)
    reflowed_figures: set[int] = set()
    if context.model.document_id == "hla-1516.1-2025":
        body, reflowed_figures = _reflow_2025_statechart_page(body, block, assets)
    body, embedded_figures = _embed_bound_diagram_surfaces(body, block, assets, reflowed_figures)
    body = _embed_model_diagrams(body, block, context, assets, embedded_figures)
    body = _promote_2010_landscape_diagrams(body, context, assets)
    render_block = block.model_copy(update={"layout_body": body})
    name = f"content-block-{_generated_filename(identifier)}.tex"
    _write(
        context.request.output / name,
        "\n".join(
            (
                render_block_bindings(
                    context.model, render_block, context.request.dialect, compiled=context.hierarchy
                ),
                render_content_block(render_block),
            )
        ),
    )
    context.generated_files.append(name)
    data_name = f"content-block-{_generated_filename(identifier)}-data.tex"
    _write(context.request.output / data_name, render_content_block_data(block))
    context.generated_files.append(data_name)
    context.semantic_inputs.append(data_name)


def _write_content_elements(context: _GenerationContext) -> None:
    for identifier in context.request.content_element_ids:
        element = context.content_elements.get(identifier)
        if element is None:
            raise ValueError(f"unknown content element ID: {identifier}")
        name = f"content-element-{_generated_filename(identifier)}-data.tex"
        _write(context.request.output / name, render_content_element_data(element))
        context.generated_files.append(name)
        context.semantic_inputs.append(name)


def _write_table_family_data(context: _GenerationContext) -> None:
    selected_ids = (
        tuple(context.table_families)
        if context.request.table_family_ids is None
        else context.request.table_family_ids
    )
    for identifier in selected_ids:
        family = context.table_families.get(identifier)
        if family is None:
            raise ValueError(f"unknown table family ID: {identifier}")
        family_tables = tuple(context.tables[table_id] for table_id in family.table_ids)
        data_name = f"table-family-{_generated_filename(identifier)}-data.tex"
        _write(
            context.request.output / data_name,
            render_table_family_data(
                family, family_tables, include_cells=context.request.include_table_cells
            ),
        )
        context.generated_files.append(data_name)
        context.semantic_inputs.append(data_name)


def _write_optional_layout_outputs(context: _GenerationContext) -> None:
    request = context.request
    if request.include_outline:
        name = "clause-outline.tex"
        _write(request.output / name, render_hierarchy_outline(context.model, request.dialect))
        context.generated_files.append(name)
        context.semantic_inputs.append(name)
    if request.include_faithful_body:
        context.faithful_layout = build_faithful_layout_projection(
            context.model,
            content_block_ids=request.content_block_ids,
            profile=request.faithful_layout_profile,
            exclude_path_parts=request.faithful_body_exclude_path_parts,
        )
        _write(
            request.output / "faithful-layout.json",
            context.faithful_layout.model_dump_json(indent=2),
        )
        context.generated_files.append("faithful-layout.json")
        _write(
            request.output / "faithful-body.tex",
            render_faithful_body(
                context.faithful_layout,
                use_generated_blocks=request.use_generated_faithful_blocks,
            ),
        )
        context.generated_files.append("faithful-body.tex")


def _finish_generation(context: _GenerationContext) -> GenerationResult:
    request = context.request
    _write(
        request.output / "semantic-manifest.tex",
        render_build_manifest(
            context.model, tuple(context.generated_files), tuple(context.semantic_inputs)
        ),
    )
    if context.model.document_id == "hla-1516.1-2025":
        for generated_path in request.output.glob("*.tex"):
            _write(
                generated_path,
                _modernize_2025_generated_tex(generated_path.read_text(encoding="utf-8")),
            )
    return GenerationResult(
        model=context.model,
        output=request.output,
        generated_files=tuple(context.generated_files),
        semantic_inputs=tuple(context.semantic_inputs),
        faithful_layout=context.faithful_layout,
    )


def generate(request: GenerationRequest) -> GenerationResult:
    """Generate selected semantic blocks and return typed build outputs."""
    context = _prepare_generation_context(request)
    _write_model_record_data(context)
    assets = _write_diagram_assets(context)
    _write_hierarchy_assets(context)
    for identifier in request.definition_ids:
        _write_definition(context, identifier)
    for identifier in request.requirement_ids:
        _write_requirement(context, identifier)
    for identifier in request.content_block_ids:
        _render_content_block(context, assets, identifier)
    _write_content_elements(context)
    _write_table_family_data(context)
    _write_optional_layout_outputs(context)
    return _finish_generation(context)
