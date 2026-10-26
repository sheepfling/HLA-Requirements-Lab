"""Render a typed HLA state-machine record as deterministic PlantUML source.

The JSON state-machine record remains the semantic authority.  This module is
deliberately a source exporter rather than a PlantUML subprocess wrapper: the
renderer can be pinned and run in a separate, reviewable artifact step.
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from collections import defaultdict
from collections.abc import Mapping, MutableSequence, Sequence
from dataclasses import dataclass
from pathlib import Path

from hla_lab.core.semantic_model import (
    State,
    StateMachine,
    StateMachineLayout,
    Transition,
)
from hla_lab.diagrams.render_state_machine import _machine


@dataclass(frozen=True, slots=True)
class _SyntheticGroup:
    title: str


@dataclass(slots=True)
class _RenderContext:
    state_by_id: Mapping[str, State]
    synthetic_groups: Mapping[str, _SyntheticGroup]
    children: Mapping[str | None, Sequence[str]]
    parent_for: Mapping[str, str | None]
    relations_by_scope: Mapping[str | None, Sequence[str]]
    lines: MutableSequence[str]


def _alias(identifier: str) -> str:
    return "s_" + re.sub(r"[^A-Za-z0-9]+", "_", identifier).strip("_")


def _group_alias(identifier: str) -> str:
    return "g_" + re.sub(r"[^A-Za-z0-9]+", "_", identifier).strip("_")


def _label(value: object, *, quoted_context: bool = False) -> str:
    text = str(value).replace("�", "...").replace("…", "...")
    # The source audit sometimes spells the printer's dagger out as a word
    # when extracting labels from the native drawing.  PlantUML should carry
    # the publication token itself, not that extraction placeholder.
    text = re.sub(r"(?i)\bdagger\b", "†", text)
    # Some extracted source labels carry XML/HTML entities from the PDF text
    # layer. PlantUML does not decode those entities in state labels, so a
    # literal ``&quot;`` would become publication-visible diagram text. Decode
    # the small entity vocabulary used by the source before normalization.
    text = text.replace("&quot;", '"').replace("&amp;", "&")
    # State declarations are themselves quoted.  An HTML ``&quot;`` entity is
    # rendered literally by the pinned renderer, while an escaped ASCII quote
    # is rejected by some PlantUML state-parser paths.  The source records use
    # quotes only to mark placeholder words such as ``first`` and ``last``;
    # omit those delimiters in the diagram label rather than leaking markup or
    # risking a parser collision.  Transition labels follow a colon and may
    # retain ordinary ASCII quotation marks.
    text = text.replace("\\", "\\\\")
    if quoted_context:
        text = re.sub(r'&quot;|"', "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    wrapped: list[str] = []
    for line in text.split("\n"):
        wrapped.extend(
            textwrap.wrap(
                line,
                width=44,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [""]
        )
    return r"\n".join(wrapped)


def _stereotype(kind: str) -> str:
    return {
        "initial": "initial",
        "final": "final",
        "choice": "choice",
        "history": "history",
        "connector": "connector",
        "ellipsis": "ellipsis",
    }.get(kind, "")


def _synthetic_groups(
    machine: StateMachine,
    state_by_id: Mapping[str, State],
) -> dict[str, _SyntheticGroup]:
    # Layout containers are semantic region declarations, not coordinates for
    # PlantUML.  Convert their path-like IDs into composite/orthogonal regions
    # while deliberately discarding x/y geometry.
    groups: dict[str, _SyntheticGroup] = {}
    layout = machine.layout or StateMachineLayout(nodes={}, transitions={})
    for container in layout.containers:
        container_id = container.id
        group_id = re.sub(r"\.(?:container|outer|frame)$", "", container_id)
        if not group_id or group_id in state_by_id:
            continue
        if not any(
            state_id == group_id or state_id.startswith(group_id + ".") for state_id in state_by_id
        ):
            continue
        groups[group_id] = _SyntheticGroup(title=container.title or group_id)
    return groups


def _children_by_scope(
    states: Sequence[State],
    state_by_id: Mapping[str, State],
    synthetic_groups: Mapping[str, _SyntheticGroup],
) -> dict[str | None, list[str]]:
    children: dict[str | None, list[str]] = defaultdict(list)
    for group_id in synthetic_groups:
        parents = [
            candidate
            for candidate in synthetic_groups
            if candidate != group_id and group_id.startswith(candidate + ".")
        ]
        parent = max(parents, key=len) if parents else None
        children[parent].append(group_id)
    for state in states:
        state_id = state.id
        parent = state.parent_id
        if parent is not None and parent in state_by_id:
            parent_id: str | None = parent
        else:
            parents = [
                group_id
                for group_id in synthetic_groups
                if state_id == group_id or state_id.startswith(group_id + ".")
            ]
            parent_id = max(parents, key=len) if parents else None
        children[parent_id].append(state_id)
    return children


def _valid_transition_records(
    machine: StateMachine,
    state_by_id: Mapping[str, State],
) -> list[tuple[Transition, str, str]]:
    records: list[tuple[Transition, str, str]] = []
    for transition in machine.transitions:
        source = transition.source_state
        target = transition.target_state
        if (
            source is not None
            and target is not None
            and source in state_by_id
            and target in state_by_id
        ):
            records.append((transition, source, target))
    return records


def _scope_chain(node_id: str | None, parent_for: Mapping[str, str | None]) -> list[str | None]:
    chain: list[str | None] = []
    current = node_id
    while current is not None:
        chain.append(current)
        current = parent_for.get(current)
    chain.append(None)
    return chain


def _relation_node(
    state_id: str,
    kind: str,
    parent_for: Mapping[str, str | None],
    children: Mapping[str | None, Sequence[str]],
) -> str | None:
    if kind in {"initial", "final"} or not children.get(state_id):
        return parent_for.get(state_id)
    return state_id


def _transition_scope(
    transition: Transition,
    state_by_id: Mapping[str, State],
    parent_for: Mapping[str, str | None],
    children: Mapping[str | None, Sequence[str]],
) -> str | None:
    source = transition.source_state
    target = transition.target_state
    if source is None or target is None:
        return None
    source_node = _relation_node(source, state_by_id[source].kind, parent_for, children)
    target_node = _relation_node(target, state_by_id[target].kind, parent_for, children)
    if source_node != target_node and source_node is not None and target_node is not None:
        return None
    target_chain = set(_scope_chain(target_node, parent_for))
    return next(
        (item for item in _scope_chain(source_node, parent_for) if item in target_chain), None
    )


def _direct_reference(state_id: str, state_by_id: Mapping[str, State]) -> str:
    if state_by_id[state_id].kind in {"initial", "final"}:
        return "[*]"
    return _alias(state_id)


def _transition_relation(
    transition: Transition,
    source_id: str,
    target_id: str,
    context: _RenderContext,
) -> tuple[str | None, str]:
    scope_id = _transition_scope(
        transition,
        context.state_by_id,
        context.parent_for,
        context.children,
    )
    source_ref = _direct_reference(source_id, context.state_by_id)
    target_ref = _direct_reference(target_id, context.state_by_id)
    label_parts = [
        part
        for part in (
            transition.event.strip(),
            f"[{transition.guard.strip()}]" if transition.guard.strip() else "",
            transition.action.strip(),
        )
        if part
    ]
    transition_label = r"\n".join(_label(part) for part in label_parts)
    suffix = f" : {transition_label}" if transition_label else ""
    return scope_id, f"{source_ref} --> {target_ref}{suffix}"


def _relations_by_scope(
    records: Sequence[tuple[Transition, str, str]],
    context: _RenderContext,
) -> dict[str | None, list[str]]:
    relations: dict[str | None, list[str]] = defaultdict(list)
    for transition, source_id, target_id in records:
        scope_id, relation = _transition_relation(transition, source_id, target_id, context)
        relations[scope_id].append(relation)
    return relations


def _emit_scope_relations(context: _RenderContext, scope_id: str | None, indent: str) -> None:
    context.lines.extend(
        indent + relation for relation in context.relations_by_scope.get(scope_id, ())
    )


def _emit_state(context: _RenderContext, state_id: str, indent: str) -> None:
    if state_id in context.synthetic_groups:
        group = context.synthetic_groups[state_id]
        nested = context.children.get(state_id, ())
        context.lines.append(
            f'{indent}state "{_label(group.title, quoted_context=True)}" as '
            f"{_group_alias(state_id)} {{"
        )
        for child_id in nested:
            _emit_state(context, child_id, indent + "  ")
        _emit_scope_relations(context, state_id, indent + "  ")
        context.lines.append(indent + "}")
        return
    state = context.state_by_id[state_id]
    kind = state.kind
    if kind in {"initial", "final"}:
        return
    raw_label = state.label
    if not raw_label and kind in {"initial", "final"}:
        raw_label = " "
    label = _label(raw_label, quoted_context=True)
    stereotype = _stereotype(kind)
    rendered = f'{indent}state "{label}" as {_alias(state_id)}'
    if stereotype:
        rendered += f" <<{stereotype}>>"
    nested = context.children.get(state_id, ())
    if not nested:
        context.lines.append(rendered)
        return
    context.lines.append(rendered + " {")
    for child_id in nested:
        _emit_state(context, child_id, indent + "  ")
    _emit_scope_relations(context, state_id, indent + "  ")
    context.lines.append(indent + "}")


def _plantuml_preamble(direction: str) -> list[str]:
    lines = [
        "@startuml",
        "' Generated from the typed HLA state-machine record; do not edit by hand.",
        "hide empty description",
        "skinparam shadowing false",
        "skinparam state {",
        "  BackgroundColor white",
        "  BorderColor #172334",
        "  FontColor #172334",
        "  FontName Inter",
        "  FontSize 10",
        "  AttributeFontName Inter",
        "  AttributeFontColor #496B91",
        "}",
        "skinparam ArrowColor #496B91",
        "skinparam ArrowFontColor #172334",
        "skinparam ArrowFontName DejaVu Sans Mono",
        "skinparam ArrowFontSize 8",
        "skinparam state<<history>> {",
        "  BackgroundColor #EAF0F6",
        "  BorderColor #496B91",
        "}",
        "skinparam state<<initial>> {",
        "  BackgroundColor #172334",
        "  BorderColor #172334",
        "  FontColor white",
        "}",
        "skinparam state<<final>> {",
        "  BackgroundColor white",
        "  BorderColor #172334",
        "}",
        "skinparam state<<choice>> {",
        "  BackgroundColor white",
        "  BorderColor #496B91",
        "}",
    ]
    if direction == "left-to-right":
        lines.insert(3, "left to right direction")
    return lines


def render(machine: StateMachine) -> str:
    """Render one validated state-machine model as PlantUML source."""
    state_by_id = {item.id: item for item in machine.states}
    synthetic_groups = _synthetic_groups(machine, state_by_id)
    children = _children_by_scope(machine.states, state_by_id, synthetic_groups)
    parent_for = {child: parent for parent, nested in children.items() for child in nested}
    lines = _plantuml_preamble(
        machine.layout.direction if machine.layout else ""
    )
    context = _RenderContext(
        state_by_id=state_by_id,
        synthetic_groups=synthetic_groups,
        children=children,
        parent_for=parent_for,
        relations_by_scope={},
        lines=lines,
    )
    records = _valid_transition_records(machine, state_by_id)
    context.relations_by_scope = _relations_by_scope(records, context)
    for state_id in children.get(None, ()):
        _emit_state(context, state_id, "")
    _emit_scope_relations(context, None, "")
    lines.extend(["@enduml", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Canonical state-machine JSON")
    parser.add_argument("output", type=Path, help="Generated PlantUML source")
    parser.add_argument("--machine", help="Machine ID when the file contains multiple machines")
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(_machine(payload, args.machine)), encoding="utf-8")


if __name__ == "__main__":
    main()
