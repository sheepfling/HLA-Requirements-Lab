"""Generate a human-readable derivative from validated semantic document models."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

try:
    from scripts.latex_renderer import tex_escape
    from scripts.semantic_model import DocumentModel, ImplementationMapping, Requirement, Transition
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from latex_renderer import tex_escape
    from semantic_model import DocumentModel, ImplementationMapping, Requirement, Transition


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _anchor(document_id: str, record_id: str) -> str:
    return f"\\hypertarget{{{tex_escape(document_id)}:{tex_escape(record_id)}}}{{}}"


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
        (r"\_", "_"),
        (r"\&", "&"),
        (r"\%", "%"),
        (r"\#", "#"),
        (r"\{", "{"),
        (r"\}", "}"),
    ):
        value = value.replace(escaped, plain)
    return tex_escape(value)


def _field(label: str, value: str) -> str:
    return f"\\textbf{{{_display_escape(label)}:}} {_display_escape(value)}"


def _clause_link(model: DocumentModel, clause_id: str | None) -> str:
    return _link(model.document_id, clause_id) if clause_id else r"\emph{Unassigned}"


def _source_ref(source: object) -> str:
    return _source_line(source.path, source.line, source.end_line)


def _itemize(items: Iterable[str], *, empty: str = "None recorded.") -> list[str]:
    values = tuple(items)
    if not values:
        return [f"\\emph{{{tex_escape(empty)}}}"]
    return ["\\begin{itemize}", *(f"\\item {item}" for item in values), "\\end{itemize}"]


def _heading(level: int, title: str) -> str:
    command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(level, "paragraph")
    return f"\\{command}{{{_display_escape(title)}}}"


def _render_clause_tree(model: DocumentModel, clause_id: str, document_id: str) -> list[str]:
    clause = next(item for item in model.clauses if item.id == clause_id)
    lines = [_anchor(document_id, clause.id), _heading(min(clause.level + 1, 4), clause.title)]
    lines.append(f"{_field('Semantic ID', clause.id)}\\\\")
    lines.append(f"{_field('Source', '')}{_source_ref(clause.source)}")
    for child in model.children_of(clause.id):
        lines.extend(_render_clause_tree(model, child.id, document_id))
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
    lines = [_heading(1, f"Concepts and definitions — {model.document_id}")]
    for clause in model.root_clauses():
        lines.extend(_render_clause_tree(model, clause.id, model.document_id))
    lines.extend(_render_definitions(model))
    return lines


def _render_requirement(requirement: Requirement, model: DocumentModel) -> list[str]:
    lines = [
        _anchor(model.document_id, requirement.id),
        _heading(3, requirement.title),
        f"{_field('Semantic ID', requirement.id)}\\\\",
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
    lines = [
        _anchor(model.document_id, transition.id),
        f"\\textbf{{{tex_escape(transition.id)}}}: {_transition_label(transition, model)}\\\\",
        f"{_field('Initiator', transition.initiator)}\\\\",
    ]
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


def _requirement_implementations(
    model: DocumentModel, requirement_id: str
) -> tuple[ImplementationMapping, ...]:
    return tuple(item for item in model.implementations if requirement_id in item.requirement_ids)


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


def _render_corpus(models: tuple[DocumentModel, ...]) -> str:
    lines = [
        "% Generated from validated semantic records; edit semantic source instead.",
        r"\section{Corpus scope}",
        "This derivative is generated from the validated semantic records. "
        "Reviewed requirements are rendered as conformance material; candidate "
        "records remain available in the machine-readable corpus for later review.",
    ]
    for model in models:
        lines.extend(_render_concepts(model))
        lines.extend(_render_requirements(model))
        lines.extend(_render_state_machines(model))
        lines.extend(_render_traceability(model))
    return "\n\n".join(lines)


def generate_derivative(models: Iterable[DocumentModel], output: Path) -> Path:
    """Write the derivative TeX and JSON from the same validated model inputs."""
    ordered_models = tuple(sorted(models, key=lambda item: item.document_id))
    if not ordered_models:
        raise ValueError("at least one semantic document model is required")
    output.mkdir(parents=True, exist_ok=True)
    for path in output.glob("*.tex"):
        path.unlink()
    payload = {
        "schema_version": 1,
        "documents": [model.model_dump(mode="json") for model in ordered_models],
    }
    _write(output / "semantic-model.json", json.dumps(payload, ensure_ascii=False, indent=2))
    derivative = output / "derivative.tex"
    _write(derivative, _render_corpus(ordered_models))
    return derivative


def generate_from_hla(roots: Iterable[Path], output: Path) -> Path:
    """Load the HLA profile at the adapter boundary for the initial derivative."""
    try:
        from scripts.hla_semantic import load_hla_corpus
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        from hla_semantic import load_hla_corpus

    return generate_derivative(load_hla_corpus(tuple(roots)).documents, output)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("roots", nargs="+", type=Path)
    arguments = parser.parse_args()
    print(generate_from_hla(arguments.roots, arguments.output))
