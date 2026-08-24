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
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _alias(identifier: str) -> str:
    return "s_" + re.sub(r"[^A-Za-z0-9]+", "_", identifier).strip("_")


def _group_alias(identifier: str) -> str:
    return "g_" + re.sub(r"[^A-Za-z0-9]+", "_", identifier).strip("_")


def _label(value: object) -> str:
    text = str(value).replace("�", "...").replace("…", "...")
    # PlantUML does not accept backslash-escaped quotes inside a quoted state
    # declaration.  Use the renderer's supported entity form instead, which
    # preserves the visible ASCII quote without terminating the declaration.
    text = text.replace("\\", "\\\\").replace('"', "&quot;")
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


def _machine(payload: Mapping[str, Any], machine_id: str | None) -> Mapping[str, Any]:
    machines = payload.get("state_machines", [])
    if not isinstance(machines, list) or not machines:
        raise ValueError("JSON file contains no state_machines")
    if machine_id is None:
        if len(machines) != 1:
            raise ValueError("--machine is required when the file contains multiple machines")
        return machines[0]
    for machine in machines:
        if machine.get("id") == machine_id:
            return machine
    raise ValueError(f"machine not found: {machine_id}")


def _stereotype(kind: str) -> str:
    return {
        "initial": "initial",
        "final": "final",
        "choice": "choice",
        "history": "history",
        "connector": "connector",
        "ellipsis": "ellipsis",
    }.get(kind, "")


def render(machine: Mapping[str, Any]) -> str:
    """Return PlantUML source for one semantic state-machine record."""

    states = [item for item in machine.get("states", []) if isinstance(item, dict)]
    state_by_id = {str(item["id"]): item for item in states if item.get("id")}
    # Layout containers are semantic region declarations, not coordinates for
    # PlantUML.  Convert their path-like IDs into composite/orthogonal regions
    # while deliberately discarding x/y geometry.
    synthetic_groups: dict[str, dict[str, Any]] = {}
    layout = machine.get("layout") or {}
    for container in layout.get("containers", ()) if isinstance(layout, Mapping) else ():
        if not isinstance(container, Mapping) or not container.get("id"):
            continue
        container_id = str(container["id"])
        group_id = re.sub(r"\.(?:container|outer|frame)$", "", container_id)
        if not group_id or group_id in state_by_id:
            continue
        if not any(
            state_id == group_id or state_id.startswith(group_id + ".")
            for state_id in state_by_id
        ):
            continue
        synthetic_groups[group_id] = {
            "title": str(container.get("title") or group_id),
            "parallel": False,
        }

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
        state_id = str(state["id"])
        parent = state.get("parent_id")
        if parent is not None and str(parent) in state_by_id:
            parent_id: str | None = str(parent)
        else:
            parents = [
                group_id
                for group_id in synthetic_groups
                if state_id == group_id or state_id.startswith(group_id + ".")
            ]
            parent_id = max(parents, key=len) if parents else None
        children[parent_id].append(state_id)

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
    transition_records: list[tuple[dict[str, Any], str, str]] = []
    for transition in machine.get("transitions", ()):
        if not isinstance(transition, dict):
            continue
        source = transition.get("source_state")
        target = transition.get("target_state")
        if source not in state_by_id or target not in state_by_id:
            continue
        source_id = str(source)
        target_id = str(target)
        transition_records.append((transition, source_id, target_id))

    transition_pairs = {
        (str(item["source_state"]), str(item["target_state"]))
        for item, _source_id, _target_id in transition_records
    }
    layout_nodes = (layout.get("nodes", {}) if isinstance(layout, Mapping) else {})
    layout_transitions = (
        layout.get("transitions", {}) if isinstance(layout, Mapping) else {}
    )

    def transition_arrow(transition: dict[str, Any], source_id: str, target_id: str) -> str:
        layout_transition = layout_transitions.get(transition.get("id"), {})
        if source_id == target_id and isinstance(layout_transition, Mapping):
            loop_direction = layout_transition.get("loop_direction")
            if loop_direction in {"left", "right", "up", "down"}:
                return f" -{loop_direction}-> "
        if (target_id, source_id) not in transition_pairs:
            return " --> "
        source_position = layout_nodes.get(source_id, {})
        target_position = layout_nodes.get(target_id, {})
        if not isinstance(source_position, Mapping) or not isinstance(target_position, Mapping):
            return " --> "
        dx = float(target_position.get("x", 0)) - float(source_position.get("x", 0))
        dy = float(target_position.get("y", 0)) - float(source_position.get("y", 0))
        if abs(dx) >= abs(dy) and dx:
            return " -right-> " if dx > 0 else " -left-> "
        if dy:
            return " -down-> " if dy > 0 else " -up-> "
        return " --> "

    parent_for: dict[str, str | None] = {
        child: parent for parent, nested in children.items() for child in nested
    }

    def scope_chain(node_id: str | None) -> list[str | None]:
        chain: list[str | None] = []
        current = node_id
        while current is not None:
            chain.append(current)
            current = parent_for.get(current)
        chain.append(None)
        return chain

    def transition_scope(transition: dict[str, Any]) -> str | None:
        source = str(transition["source_state"])
        target = str(transition["target_state"])
        source_kind = str(state_by_id[source].get("kind", "normal"))
        target_kind = str(state_by_id[target].get("kind", "normal"))

        def relation_node(state_id: str, kind: str) -> str | None:
            if kind in {"initial", "final"}:
                return parent_for.get(state_id)
            # A leaf cannot contain a relation declaration, so put self-loops
            # and leaf-to-leaf edges in their nearest composite scope.
            return state_id if children.get(state_id) else parent_for.get(state_id)

        source_node = relation_node(source, source_kind)
        target_node = relation_node(target, target_kind)
        target_chain = set(scope_chain(target_node))
        return next((item for item in scope_chain(source_node) if item in target_chain), None)

    def direct_reference(state_id: str, scope_id: str | None) -> str:
        kind = str(state_by_id[state_id].get("kind", "normal"))
        if kind in {"initial", "final"}:
            return "[*]"
        current = state_id
        while parent_for.get(current) != scope_id and parent_for.get(current) is not None:
            current = str(parent_for[current])
        return _alias(current)

    relations_by_scope: dict[str | None, list[str]] = defaultdict(list)
    for transition, source_id, target_id in transition_records:
        scope_id = transition_scope(transition)
        source_ref = direct_reference(source_id, scope_id)
        target_ref = direct_reference(target_id, scope_id)
        event = str(transition.get("event", "")).strip()
        guard = str(transition.get("guard", "")).strip()
        action = str(transition.get("action", "")).strip()
        label_parts = [
            part
            for part in (event, f"[{guard}]" if guard else "", action)
            if part
        ]
        transition_label = r"\n".join(_label(part) for part in label_parts)
        suffix = f" : {transition_label}" if transition_label else ""
        relations_by_scope[scope_id].append(
            f"{source_ref}{transition_arrow(transition, source_id, target_id)}{target_ref}{suffix}"
        )

    def emit_scope_relations(scope_id: str | None, indent: str) -> None:
        for relation in relations_by_scope.get(scope_id, ()):
            lines.append(indent + relation)

    def emit_state(state_id: str, indent: str) -> None:
        if state_id in synthetic_groups:
            group = synthetic_groups[state_id]
            nested = children.get(state_id, [])
            lines.append(
                f'{indent}state "{_label(group["title"])}" as {_group_alias(state_id)} {{'
            )
            region_ids = [item for item in nested if item in synthetic_groups]
            for index, child_id in enumerate(nested):
                if child_id in synthetic_groups and index and len(region_ids) > 1:
                    lines.append(indent + "  --")
                emit_state(child_id, indent + "  ")
            emit_scope_relations(state_id, indent + "  ")
            lines.append(indent + "}")
            return
        state = state_by_id[state_id]
        kind = str(state.get("kind", "normal"))
        if kind in {"initial", "final"}:
            return
        raw_label = state.get("label", "")
        # PlantUML rejects an empty quoted state label.  A single space keeps
        # the alias addressable while the stereotype styling renders the
        # pseudostate as a publication-sized node without visible text.
        if not raw_label and kind in {"initial", "final"}:
            raw_label = " "
        label = _label(raw_label)
        stereotype = _stereotype(kind)
        rendered = f'{indent}state "{label}" as {_alias(state_id)}'
        if stereotype:
            rendered += f" <<{stereotype}>>"
        nested = children.get(state_id, [])
        if not nested:
            lines.append(rendered)
            return
        lines.append(rendered + " {")
        for index, child_id in enumerate(nested):
            emit_state(child_id, indent + "  ")
        emit_scope_relations(state_id, indent + "  ")
        lines.append(indent + "}")

    for state_id in children.get(None, []):
        emit_state(state_id, "")
    emit_scope_relations(None, "")

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
