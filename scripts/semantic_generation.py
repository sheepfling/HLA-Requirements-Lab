"""Generic semantic-to-LaTeX build generation."""

from __future__ import annotations

import re
from pathlib import Path

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
    render_definition,
    render_definition_data,
    render_requirement,
    render_requirement_data,
    render_table_family_data,
    tex_escape,
)
from scripts.semantic_model import DocumentModel, load_document_model
from scripts.source_adapter import LatexSourceProfile


def _safe_name(identifier: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", identifier).strip("-")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


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
        _write(
            output / name,
            "\n".join(
                (
                    render_block_bindings(model, block, dialect, compiled=compiled_hierarchy),
                    render_content_block(block),
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
        _write(output / data_name, render_table_family_data(family, family_tables))
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    if include_outline:
        name = "clause-outline.tex"
        _write(output / name, render_hierarchy_outline(model, dialect))
        generated_files.append(name)
        semantic_inputs.append(name)

    _write(
        output / "semantic-manifest.tex",
        render_build_manifest(model, tuple(generated_files), tuple(semantic_inputs)),
    )
    return model
