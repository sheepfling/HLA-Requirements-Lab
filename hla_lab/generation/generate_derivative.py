"""Generate a human-readable derivative from validated semantic document models."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from hla_lab.adapters.latex_renderer import tex_escape
from hla_lab.core.io import write_text
from hla_lab.core.links import latex_anchor
from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    CrossReference,
    DocumentModel,
    ImplementationMapping,
    Requirement,
    SourceRef,
    Transition,
)
from hla_lab.corpus.corpus_graph import CorpusDocumentDescriptor, build_corpus_graph
from hla_lab.generation.hierarchy_compiler import CompiledHierarchy, compile_hierarchy
from hla_lab.generation.reflowable_renderer import render_reflowable_document
from hla_lab.publication.publication_contract import (
    PublicationProfile,
    default_publication_profile,
    publication_destination,
    write_contract_json,
)

_write = write_text

_anchor = latex_anchor


def _link(document_id: str, record_id: str, label: str | None = None) -> str:
    return (
        f"\\hyperlink{{{tex_escape(document_id)}:{tex_escape(record_id)}}}"
        f"{{{_display_escape(label or record_id)}}}"
    )


def _source_line(path: str, line: int, end_line: int | None) -> str:
    span = str(line) if end_line is None or end_line == line else f"{line}--{end_line}"
    return f"\\texttt{{{tex_escape(path)}:{span}}}"


def _display_escape(value: str) -> str:
    """Normalize source-style escaped punctuation before generic TeX escaping."""
    for escaped, plain in (
        (r"\$", "$"),
        (r"\_", "_"),
        (r"\&", "&"),
        (r"\%", "%"),
        (r"\#", "#"),
        (r"\{", "{"),
        (r"\}", "}"),
    ):
        value = value.replace(escaped, plain)
    # The source state-machine notation uses a Unicode subscript ``s`` in
    # symbols such as Fₛ.  Latin Modern does not contain that glyph, so keep
    # the notation semantic while emitting a portable LaTeX text subscript.
    return (
        tex_escape(value).replace("ₛ", r"\textsubscript{s}").replace("∀", r"\ensuremath{\forall}")
    )


def _field(label: str, value: str) -> str:
    return f"\\textbf{{{_display_escape(label)}:}} {_display_escape(value)}"


def _clause_link(model: DocumentModel, clause_id: str | None) -> str:
    return _link(model.document_id, clause_id) if clause_id else r"\emph{Unassigned}"


def _source_ref(source: SourceRef) -> str:
    return _source_line(source.path, source.line, source.end_line)


def _itemize(items: Iterable[str], *, empty: str = "None recorded.") -> list[str]:
    values = tuple(items)
    if not values:
        return [f"\\emph{{{tex_escape(empty)}}}"]
    return ["\\begin{itemize}", *(f"\\item {item}" for item in values), "\\end{itemize}"]


def _heading(level: int, title: str) -> str:
    command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(level, "paragraph")
    return f"\\{command}{{{_display_escape(title)}}}"


def _render_publication_outline(
    profile: PublicationProfile,
    models: tuple[DocumentModel, ...],
) -> str:
    """Render the contract's outline without rendering semantic record bodies."""
    model_ids = {model.document_id for model in models}
    documents = tuple(item for item in profile.documents if item.id in model_ids)
    lines = [
        "% Generated publication contract; edit the profile source instead.",
        _anchor(profile.profile_id, "outline"),
        _heading(1, profile.title),
    ]
    if profile.subtitle:
        lines.append(f"\\emph{{{_display_escape(profile.subtitle)}}}\\\\")
    if profile.description:
        lines.append(f"{_display_escape(profile.description)}\\\\")
    lines.append(f"{_field('Publication profile', profile.profile_id)}\\\\")
    lines.append(f"{_field('Style profile', profile.style_id)}")

    for section in profile.sections:
        projection = profile.projection(section.projection_id)
        section_destination = publication_destination(profile.profile_id, section.id)
        lines.extend(
            (
                f"\\hypertarget{{{tex_escape(section_destination)}}}{{}}",
                _heading(section.level, section.title),
                f"{_field('Projection', projection.id)}\\\\",
                f"{_field('Output role', projection.output)}\\\\",
                f"{_display_escape(projection.purpose)}\\\\",
            )
        )
        if projection.record_kinds:
            lines.append(f"{_field('Record kinds', ', '.join(projection.record_kinds))}\\\\")
        if section.per_document:
            for document in documents:
                document_destination = f"{profile.profile_id}:{section.id}:{document.id}"
                lines.extend(
                    (
                        f"\\hypertarget{{{tex_escape(document_destination)}}}{{}}",
                        _heading(min(section.level + 1, 4), document.title),
                        f"{_field('Document', document.short_title)}\\\\",
                    )
                )
        else:
            lines.append(r"\emph{This projection is corpus-wide.}")
    return "\n\n".join(lines)


def _render_clause_tree(
    compiled: CompiledHierarchy,
    clause_id: str,
    document_id: str,
) -> list[str]:
    """Render clauses in the compiler's canonical parent/child order."""
    clause = compiled.node(clause_id)
    lines = [_anchor(document_id, clause.id), _heading(min(clause.level + 1, 4), clause.title)]
    lines.append(f"{_field('Semantic ID', clause.id)}\\\\")
    lines.append(f"{_field('Source', '')}{_source_ref(clause.source)}")
    for child_id in clause.child_ids:
        lines.extend(_render_clause_tree(compiled, child_id, document_id))
    return lines


def _render_definitions(model: DocumentModel) -> list[str]:
    lines = [_heading(2, f"{model.document_id}: definitions")]
    if not model.definitions:
        lines.append(r"\emph{No definitions are currently authored for this document.}")
        return lines
    for definition in model.ordered_definitions():
        lines.extend(
            (
                _anchor(model.document_id, definition.id),
                _heading(3, definition.term),
                f"{_field('Semantic ID', definition.id)}\\\\",
                f"{_display_escape(definition.text)}\\\\",
                f"{_field('Clause', '')}{_clause_link(model, definition.clause_id)}\\\\",
                f"{_field('Source', '')}{_source_ref(definition.source)}",
            )
        )
    return lines


def _render_concepts(model: DocumentModel) -> list[str]:
    compiled = compile_hierarchy(model)
    lines = [_heading(1, f"Concepts and definitions — {model.document_id}")]
    for clause_id in compiled.root_ids:
        lines.extend(_render_clause_tree(compiled, clause_id, model.document_id))
    lines.extend(_render_definitions(model))
    lines.extend(_render_tables(model))
    return lines


def _render_tables(model: DocumentModel) -> list[str]:
    """Render logical table families and their source-owned cells."""
    lines = [_heading(2, f"{model.document_id}: table families")]
    if not model.table_families:
        lines.append(r"\emph{No semantic table families are currently authored for this document.}")
        return lines
    tables = {table.id: table for table in model.tables}
    for family in model.table_families:
        lines.extend(
            (
                _anchor(model.document_id, family.id),
                _heading(3, family.title),
                f"{_field('Semantic ID', family.id)}\\\\",
                f"{_field('Clause', '')}{_clause_link(model, family.clause_id)}\\\\",
            )
        )
        for table_id in family.table_ids:
            table = tables[table_id]
            family_link = (
                _link(model.document_id, table.family_id)
                if table.family_id
                else r"\emph{Unassigned}"
            )
            continuation = (
                _link(model.document_id, table.continued_from)
                if table.continued_from
                else r"\emph{root fragment}"
            )
            lines.extend(
                (
                    _anchor(model.document_id, table.id),
                    _heading(4, table.caption or table.title or table.id),
                    f"{_field('Table', table.id)}\\\\",
                    f"{_field('Logical ID', table.logical_id or table.id)}\\\\",
                    f"{_field('Family', '')}{family_link}\\\\",
                    f"{_field('Continued from', '')}{continuation}\\\\",
                    f"{_field('Source', '')}{_source_ref(table.source)}",
                )
            )
            lines.extend(
                _itemize(
                    f"\\texttt{{{_display_escape(cell.id)}}} "
                    f"[{cell.row if cell.row is not None else 'unknown'}, "
                    f"{cell.column if cell.column is not None else 'unknown'}]: "
                    f"{_display_escape(cell.text)}"
                    for cell in table.cells
                )
            )
    return lines


def _render_references(model: DocumentModel) -> list[str]:
    """Render reference labels and bibliography text from typed records."""
    lines = [_heading(1, f"References — {model.document_id}")]
    if not model.references:
        lines.append(r"\emph{No semantic references are currently authored for this document.}")
        return lines
    for reference in model.references:
        lines.extend(
            (
                _anchor(model.document_id, reference.id),
                _heading(3, f"{reference.label} {reference.text}"),
                f"{_field('Semantic ID', reference.id)}\\\\",
                f"{_field('Kind', reference.kind)}\\\\",
                f"{_field('Clause', '')}{_clause_link(model, reference.clause_id)}\\\\",
                f"{_field('Source', '')}{_source_ref(reference.source)}",
            )
        )
    return lines


def _render_cross_references(model: DocumentModel) -> list[str]:
    """Render resolved cross-reference edges grouped by semantic owner."""
    lines = [_heading(1, f"Cross-references — {model.document_id}")]
    if not model.cross_references:
        lines.append(r"\emph{No typed cross-references are currently authored for this document.}")
        return lines
    grouped: dict[str, list[CrossReference]] = {}
    for cross_reference in model.cross_references:
        grouped.setdefault(cross_reference.owner_id, []).append(cross_reference)
    for owner_id, cross_references in grouped.items():
        lines.extend(
            (
                _anchor(model.document_id, owner_id),
                _heading(3, f"Owner {owner_id}"),
                f"{_field('Owner', '')}{_link(model.document_id, owner_id)}\\\\",
            )
        )
        lines.extend(
            _itemize(
                (
                    f"{_anchor(model.document_id, item.id)}"
                    f"{_link(item.target_document_id, item.target_record_id, item.label)} "
                    f"({_display_escape(item.kind)}; {_display_escape(item.relation)})"
                )
                for item in cross_references
            )
        )
    return lines


def _render_figures(model: DocumentModel) -> list[str]:
    """Render figure numbers and captions without embedding comparison images."""
    lines = [_heading(1, f"Figures — {model.document_id}")]
    if not model.figures:
        lines.append(r"\emph{No semantic figures are currently authored for this document.}")
        return lines
    for figure in model.figures:
        caption = figure.caption or r"\emph{Caption not recorded.}"
        lines.extend(
            (
                _anchor(model.document_id, figure.id),
                _heading(3, f"Figure {figure.number} — {caption}"),
                f"{_field('Semantic ID', figure.id)}\\\\",
                f"{_field('Caption', '')}{_display_escape(figure.caption)}\\\\",
                f"{_field('Clause', '')}{_clause_link(model, figure.clause_id)}\\\\",
                f"{_field('Source', '')}{_source_ref(figure.source)}",
            )
        )
    return lines


def _render_notes(model: DocumentModel) -> list[str]:
    """Render explicitly marked notes and footnotes from typed records."""
    lines = [_heading(1, f"Notes and footnotes — {model.document_id}")]
    if not model.notes:
        lines.append(
            r"\emph{No semantic notes or footnotes are currently authored for this document.}"
        )
        return lines
    for note in model.notes:
        lines.extend(
            (
                _anchor(model.document_id, note.id),
                _heading(3, note.id),
                f"{_field('Kind', note.kind)}\\\\",
                f"{_display_escape(note.text)}\\\\",
                f"{_field('Owner', '')}{_clause_link(model, note.owner_id)}\\\\",
                f"{_field('Source', '')}{_source_ref(note.source)}",
            )
        )
    return lines


def _render_prose(model: DocumentModel) -> list[str]:
    """Render reusable prose elements in authored block order."""
    lines = [_heading(1, f"Semantic prose surfaces — {model.document_id}")]
    elements = {item.id: item for item in model.content_elements}
    cross_references = {}
    for item in model.cross_references:
        cross_references.setdefault(item.owner_id, []).append(item)
    blocks = sorted(model.content_blocks, key=lambda item: (item.sequence, item.id))
    rendered = False
    for block in blocks:
        block_elements = [
            elements[item_id]
            for item_id in block.element_ids
            if item_id in elements and elements[item_id].text.strip()
        ]
        if not block_elements:
            continue
        rendered = True
        lines.extend(
            (
                _anchor(model.document_id, block.id),
                _heading(2, block.id),
                f"{_field('Clause', '')}{_clause_link(model, block.clause_id)}\\\\",
            )
        )
        for element in sorted(block_elements, key=lambda item: (item.sequence, item.id)):
            if element.kind == "cross-reference":
                visible_text = ", ".join(
                    _link(
                        item.target_document_id,
                        item.target_record_id,
                        item.label,
                    )
                    for item in cross_references.get(element.id, ())
                ) or _display_escape(element.text)
            else:
                visible_text = _display_escape(element.text)
            lines.extend(
                (
                    _anchor(model.document_id, element.id),
                    _heading(4, element.kind),
                    f"{_field('Semantic ID', element.id)}\\\\",
                    f"{visible_text}\\\\",
                    f"{_field('Source', '')}{_source_ref(element.source)}",
                )
            )
    if not rendered:
        lines.append(
            r"\emph{No reusable semantic prose elements are currently authored for this document.}"
        )
    return lines


def _render_requirement(requirement: Requirement, model: DocumentModel) -> list[str]:
    lines = [
        _anchor(model.document_id, requirement.id),
        _heading(3, requirement.title),
        f"{_field('Semantic ID', requirement.id)}\\\\",
        f"{_field('Semantic group', requirement.semantic_group_id or requirement.id)}\\\\",
        f"{_display_escape(requirement.statement)}\\\\",
        f"{_field('Clause', '')}{_clause_link(model, requirement.clause_id)}\\\\",
        f"{_field('Coverage', requirement.coverage_kind)}\\\\",
    ]
    if requirement.coverage_note:
        lines.append(f"{_field('Coverage note', requirement.coverage_note)}\\\\")
    if requirement.transition_ids:
        lines.append(
            f"{_field('Transitions', '')}"
            + ", ".join(_link(model.document_id, item) for item in requirement.transition_ids)
            + r"\\"
        )
    lines.append(f"{_field('Source', '')}{_source_ref(requirement.source)}")
    return lines


def _render_requirements(model: DocumentModel) -> list[str]:
    explicit = tuple(item for item in model.ordered_requirements() if item.extraction == "explicit")
    candidates = sum(item.extraction == "candidate" for item in model.requirements)
    lines = [
        _heading(1, f"Normative requirements — {model.document_id}"),
        f"{_field('Reviewed requirements', str(len(explicit)))}\\\\",
        f"{_field('Unreviewed candidates', str(candidates))}\\\\",
    ]
    if candidates:
        lines.append(
            r"Candidate requirements remain in the machine-readable semantic corpus but are "
            r"not rendered as reviewed normative requirements."
        )
    if not explicit:
        lines.append(r"\emph{No reviewed requirements are currently promoted for this document.}")
        return lines
    for requirement in explicit:
        lines.extend(_render_requirement(requirement, model))
    return lines


def _transition_label(transition: Transition, model: DocumentModel) -> str:
    source = (
        _link(model.document_id, transition.source_state) if transition.source_state else "initial"
    )
    target = (
        _link(model.document_id, transition.target_state) if transition.target_state else "final"
    )
    return f"{source} $\\xrightarrow{{\\text{{{_display_escape(transition.event)}}}}}$ {target}"


def _render_transition(transition: Transition, model: DocumentModel) -> list[str]:
    coverage = next(
        (item for item in model.transition_coverage if item.transition_id == transition.id),
        None,
    )
    lines = [
        _anchor(model.document_id, transition.id),
        f"\\textbf{{{tex_escape(transition.id)}}}: {_transition_label(transition, model)}\\\\",
        f"{_field('Initiator', transition.initiator)}\\\\",
        f"{_field('Implementation coverage', coverage.status if coverage else 'unclassified')}\\\\",
    ]
    if coverage:
        lines.append(f"{_field('Coverage note', coverage.reason)}\\\\")
    for label, value in (
        ("Guard", transition.guard),
        ("Action", transition.action),
        ("Precondition", transition.precondition),
        ("Postcondition", transition.postcondition),
    ):
        if value.strip():
            lines.append(f"{_field(label, value)}\\\\")
    if transition.clause_id:
        lines.append(f"{_field('Clause', '')}{_link(model.document_id, transition.clause_id)}\\\\")
    if transition.requirement_ids:
        lines.append(
            f"{_field('Requirements', '')}"
            + ", ".join(_link(model.document_id, item) for item in transition.requirement_ids)
            + r"\\"
        )
    if transition.implementation_ids:
        lines.append(
            f"{_field('Implementations', '')}"
            + ", ".join(_link(model.document_id, item) for item in transition.implementation_ids)
            + r"\\"
        )
    return lines


def _render_state_machines(model: DocumentModel) -> list[str]:
    lines = [_heading(1, f"State machines and event logic — {model.document_id}")]
    if not model.state_machines:
        lines.append(r"\emph{No state machines are currently modeled for this document.}")
        return lines
    for machine in model.state_machines:
        lines.extend(
            (
                _anchor(model.document_id, machine.id),
                _heading(2, machine.title),
                f"{_field('Semantic ID', machine.id)}\\\\",
                f"{_field('States', str(len(machine.states)))}\\\\",
                f"{_field('Transitions', str(len(machine.transitions)))}\\\\",
            )
        )
        if machine.clause_id:
            lines.append(f"{_field('Clause', '')}{_link(model.document_id, machine.clause_id)}\\\\")
        lines.append(_heading(3, "States"))
        lines.extend(
            _itemize(
                f"{_link(model.document_id, state.id, state.label or state.id)}"
                + (f" ({_display_escape(state.kind)})" if state.kind != "state" else "")
                for state in machine.states
            )
        )
        lines.append(_heading(3, "Transitions"))
        for transition in machine.transitions:
            lines.extend(_render_transition(transition, model))
    return lines


def _render_sequence_diagrams(model: DocumentModel) -> list[str]:
    lines = [_heading(1, f"Message-sequence diagrams — {model.document_id}")]
    if not model.sequence_diagrams:
        lines.append(
            r"\emph{No message-sequence diagrams are currently modeled for this document.}"
        )
        return lines
    for diagram in model.sequence_diagrams:
        lines.extend(
            (
                _anchor(model.document_id, diagram.id),
                _heading(2, diagram.title),
                f"{_field('Semantic ID', diagram.id)}\\\\",
                f"{_field('Participants', str(len(diagram.participants)))}\\\\",
                f"{_field('Messages', str(len(diagram.messages)))}\\\\",
            )
        )
        if diagram.clause_id:
            lines.append(f"{_field('Clause', '')}{_link(model.document_id, diagram.clause_id)}\\\\")
        lines.append(_heading(3, "Participants"))
        lines.extend(
            _itemize(
                f"\\texttt{{{_display_escape(participant.id)}}}: "
                f"{_display_escape(participant.label)}"
                + (f" ({_display_escape(participant.role)})" if participant.role else "")
                for participant in diagram.participants
            )
        )
        lines.append(_heading(3, "Messages"))
        participants = {item.id: item.label for item in diagram.participants}
        lines.extend(
            _itemize(
                f"{message.order}. {_display_escape(participants[message.source_participant])} "
                f"$\\rightarrow$ {_display_escape(participants[message.target_participant])}: "
                f"{_display_escape(message.label)}"
                + (
                    f" (response to {_display_escape(message.response_to)})"
                    if message.response_to
                    else ""
                )
                for message in sorted(diagram.messages, key=lambda item: item.order)
            )
        )
    return lines


def _requirement_implementations(
    model: DocumentModel, requirement_id: str
) -> tuple[ImplementationMapping, ...]:
    return model.implementation_mappings_for_requirement(requirement_id)


def _render_traceability(model: DocumentModel) -> list[str]:
    explicit = tuple(item for item in model.ordered_requirements() if item.extraction == "explicit")
    lines = [_heading(1, f"Traceability — {model.document_id}")]
    if not explicit and not model.implementations:
        lines.append(
            r"\emph{No reviewed requirement or implementation mappings are currently recorded.}"
        )
        return lines
    for requirement in explicit:
        implementations = _requirement_implementations(model, requirement.id)
        lines.extend(
            (
                _anchor(model.document_id, f"trace-{requirement.id}"),
                _heading(3, requirement.title),
                f"{_field('Requirement', '')}{_link(model.document_id, requirement.id)}\\\\",
                f"{_field('Clause', '')}{_clause_link(model, requirement.clause_id)}\\\\",
                _field("Transitions", "")
                + (
                    ", ".join(_link(model.document_id, item) for item in requirement.transition_ids)
                    if requirement.transition_ids
                    else r"\emph{No transition applies.}"
                )
                + r"\\",
            )
        )
        lines.append(_field("Implementations", ""))
        lines.extend(
            _itemize(
                f"{_display_escape(item.interface_kind)} {_display_escape(item.interface_name)} "
                f"$\\rightarrow$ \\texttt{{{_display_escape(item.implementation)}}} "
                f"({_display_escape(item.status)})"
                for item in implementations
            )
        )
    if model.implementations:
        lines.append(_heading(2, "Implementation mappings"))
        lines.extend(
            _itemize(
                f"{_anchor(model.document_id, item.id)}"
                f"{_link(model.document_id, item.id, item.interface_name)}: "
                f"{_display_escape(item.interface_kind)} $\\rightarrow$ "
                f"\\texttt{{{_display_escape(item.implementation)}}} "
                f"({_display_escape(item.status)})"
                for item in model.implementations
            )
        )
    return lines


def _render_corpus(
    models: tuple[DocumentModel, ...],
    profile: PublicationProfile,
) -> str:
    lines = [
        "% Generated from validated semantic records; edit semantic source instead.",
        r"\input{output/semantic/publication-outline}",
        r"\section{Corpus scope}",
        "This derivative is generated from the validated semantic records. "
        "Reviewed requirements are rendered as conformance material; candidate "
        "records remain available in the machine-readable corpus for later review.",
    ]
    for model in models:
        lines.extend(_render_concepts(model))
        lines.extend(_render_requirements(model))
        lines.extend(_render_references(model))
        lines.extend(_render_cross_references(model))
        lines.extend(_render_figures(model))
        lines.extend(_render_notes(model))
        lines.extend(_render_prose(model))
        lines.extend(_render_state_machines(model))
        lines.extend(_render_sequence_diagrams(model))
        lines.extend(_render_traceability(model))
    return "\n\n".join(lines)


def generate_derivative(
    models: Iterable[DocumentModel],
    output: Path,
    profile: PublicationProfile | None = None,
    graph_metadata: Mapping[str, CorpusDocumentDescriptor] | None = None,
) -> Path:
    """Write the derivative TeX and JSON from the same validated model inputs."""
    ordered_models = tuple(sorted(models, key=lambda item: item.document_id))
    if not ordered_models:
        raise ValueError("at least one semantic document model is required")
    publication = profile or default_publication_profile(
        tuple(model.document_id for model in ordered_models)
    )
    configured_document_ids = tuple(item.id for item in publication.documents)
    model_document_ids = tuple(model.document_id for model in ordered_models)
    if set(configured_document_ids) != set(model_document_ids):
        raise ValueError(
            "publication profile documents must match generated model documents "
            f"(profile={configured_document_ids}, models={model_document_ids})"
        )
    output.mkdir(parents=True, exist_ok=True)
    for path in output.glob("*.tex"):
        path.unlink()
    payload = {
        "schema_version": 1,
        "documents": [model.model_dump(mode="json") for model in ordered_models],
    }
    _write(output / "semantic-model.json", json.dumps(payload, ensure_ascii=False, indent=2))
    hierarchy_payload = {
        "schema_version": 1,
        "documents": [compile_hierarchy(model).model_dump(mode="json") for model in ordered_models],
    }
    _write(output / "hierarchy.json", json.dumps(hierarchy_payload, ensure_ascii=False, indent=2))
    write_contract_json(publication, output / "publication-contract.json")
    corpus_graph = build_corpus_graph(
        ComplianceCorpus(documents=ordered_models),
        metadata=graph_metadata,
    )
    _write(output / "corpus-graph.json", corpus_graph.model_dump_json(indent=2))
    _write(
        output / "publication-outline.tex", _render_publication_outline(publication, ordered_models)
    )
    _write(
        output / "reflowable.tex",
        render_reflowable_document(ordered_models, publication, corpus_graph),
    )
    derivative = output / "derivative.tex"
    _write(derivative, _render_corpus(ordered_models, publication))
    return derivative


def generate_from_hla(
    roots: Iterable[Path],
    output: Path,
    profile: PublicationProfile | None = None,
    graph_metadata: Mapping[str, CorpusDocumentDescriptor] | None = None,
    repository_root: Path | None = None,
) -> Path:
    """Load the HLA profile at the adapter boundary for the initial derivative."""
    from hla_lab.corpus.hla_semantic import load_hla_corpus
    from hla_lab.paths import REPO_ROOT

    return generate_derivative(
        load_hla_corpus(tuple(roots), repository_root or REPO_ROOT).documents,
        output,
        profile=profile,
        graph_metadata=graph_metadata,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("roots", nargs="+", type=Path)
    arguments = parser.parse_args()
    print(generate_from_hla(arguments.roots, arguments.output))
