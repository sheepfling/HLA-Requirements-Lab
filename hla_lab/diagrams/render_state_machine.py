"""Render a canonical state-machine JSON file as a TikZ picture."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from hla_lab.core.semantic_model import (
    NodePosition,
    State,
    StateMachine,
    StateMachineFile,
    StateMachineLayout,
    Transition,
    TransitionLayout,
)


def _node_name(identifier: str) -> str:
    return "sm_" + re.sub(r"[^a-zA-Z0-9]+", "_", identifier).strip("_")


def _text(value: object) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    unicode_replacements = {
        "†": r"\ensuremath{^\dagger}",
        "ₛ": r"\ensuremath{_{\mathrm{s}}}",
        "…": r"\ldots",
        "∀": r"\ensuremath{\forall}",
        "•": r"\ensuremath{\bullet}",
    }
    escaped: list[str] = []
    for character in str(value):
        if character == "\n":
            escaped.append(r"\\\relax ")
        elif character in unicode_replacements:
            escaped.append(unicode_replacements[character])
        else:
            escaped.append(replacements.get(character, character))
    return "".join(escaped)


def _machine(payload: object, machine_id: str | None) -> StateMachine:
    state_machine_file = StateMachineFile.model_validate(payload)
    machines = state_machine_file.state_machines
    if not machines:
        raise ValueError("JSON file contains no state_machines")
    if machine_id is None:
        if len(machines) != 1:
            raise ValueError("--machine is required when the file contains multiple machines")
        return machines[0]
    for machine in machines:
        if machine.id == machine_id:
            return machine
    raise ValueError(f"machine not found: {machine_id}")


def _transition_text(transition: Transition) -> str:
    event = transition.event.strip()
    guard = transition.guard.strip()
    if event and guard:
        return f"{event}\n[{guard}]"
    if guard:
        return f"[{guard}]"
    return event


def _render_scale(
    layout: StateMachineLayout,
    nodes: Mapping[str, NodePosition],
) -> float:
    """Choose a deterministic scale that keeps large source layouts reviewable."""
    points = [(position.x, position.y) for position in nodes.values()]
    for container in layout.containers:
        points.extend(
            (
                (container.x, container.y),
                (
                    container.x + container.width,
                    container.y + container.height,
                ),
            )
        )
    for annotation in layout.annotations:
        points.append((annotation.x, annotation.y))
    for transition_layout in layout.transitions.values():
        if transition_layout.label_x is not None and transition_layout.label_y is not None:
            points.append((transition_layout.label_x, transition_layout.label_y))
    if not points:
        return 1.0
    width = max(item[0] for item in points) - min(item[0] for item in points) + 4.0
    height = max(item[1] for item in points) - min(item[1] for item in points) + 3.0
    return round(min(1.0, 16.0 / width, 11.0 / height), 3)


def _automatic_label_position(
    source: NodePosition,
    target: NodePosition,
    side: str,
    position: float | None,
) -> tuple[float, float]:
    """Place an unlabeled edge label in a stable lane away from its edge."""
    fraction = 0.5 if position is None else float(position)
    x = source.x + (target.x - source.x) * fraction
    y = source.y + (target.y - source.y) * fraction
    if side == "above":
        y += 0.72
    elif side == "below":
        y -= 0.72
    elif side == "left":
        x -= 0.92
    else:
        x += 0.92
    return round(x, 3), round(y, 3)


def _loop_label_position(source: NodePosition, side: str) -> tuple[float, float]:
    x = source.x
    y = source.y
    if side == "above":
        y += 0.9
    elif side == "below":
        y -= 0.9
    elif side == "left":
        x -= 1.1
    else:
        x += 1.1
    return round(x, 3), round(y, 3)


def _layout_nodes(machine: StateMachine, layout: StateMachineLayout) -> dict[str, NodePosition]:
    nodes = dict(layout.nodes)
    states = machine.states
    parent_by_id = {state.id: state.parent_id for state in states}
    for state in states:
        state_id = state.id
        if state_id in nodes:
            continue
        descendant_positions: list[NodePosition] = []
        for candidate_id, position in nodes.items():
            current = parent_by_id.get(candidate_id)
            while current is not None:
                if current == state_id:
                    descendant_positions.append(position)
                    break
                current = parent_by_id.get(str(current))
        if descendant_positions:
            nodes[state_id] = NodePosition(
                x=sum(position.x for position in descendant_positions) / len(descendant_positions),
                y=sum(position.y for position in descendant_positions) / len(descendant_positions),
                visible=False,
            )
    return nodes


def _tikz_preamble(layout: StateMachineLayout, scale: float) -> list[str]:
    font_commands = {"tiny": r"\tiny", "scriptsize": r"\scriptsize", "small": r"\small"}
    state_font = font_commands.get(layout.state_font or "", r"\scriptsize")
    edge_label_font = font_commands.get(layout.edge_label_font or "", r"\scriptsize")
    return [
        "% Generated by hla_lab/diagrams/render_state_machine.py; edit semantic JSON instead.",
        f"\\begin{{tikzpicture}}[x=1cm,y=1cm,scale={scale},transform shape,>=stealth,",
        "  sm-state/.style={draw,rounded corners,minimum width=2.5cm,"
        f"minimum height=0.78cm,text width=2.25cm,font={state_font},align=center}},",
        "  sm-initial/.style={circle,fill,inner sep=0.09cm},",
        "  sm-final/.style={circle,draw,double,inner sep=0.08cm},",
        "  sm-choice/.style={circle,draw,minimum size=0.48cm,inner sep=0pt},",
        "  sm-history/.style={circle,draw,inner sep=0.08cm},",
        "  sm-connector/.style={circle,draw,inner sep=0.08cm},",
        "  sm-ellipsis/.style={inner sep=0pt,font=\\large},",
        "  sm-container/.style={draw,rounded corners,line width=0.5pt},",
        "  sm-container-title/.style={font=\\small\\bfseries},",
        "  sm-annotation/.style={font=\\scriptsize,align=left},",
        "  sm-edge/.style={->,line width=0.6pt},",
        f"  sm-edge-label/.style={{font={edge_label_font},text width=2.7cm,fill=white,"
        "fill opacity=0.9,text opacity=1,inner sep=1pt},",
        "]",
    ]


def _container_lines(layout: StateMachineLayout) -> list[str]:
    lines: list[str] = []
    for container in layout.containers:
        if not container.visible:
            continue
        x, y = container.x, container.y
        width, height = container.width, container.height
        lines.append(f"\\draw[sm-container] ({x},{y}) rectangle ++({width},{height});")
        if container.title_visible:
            title_x = x + width / 2
            title_y = y + height - 0.25
            lines.append(
                f"\\node[sm-container-title] at ({title_x},{title_y}) "
                f"{{ {_text(container.title)} }};"
            )
    return lines


def _rule_lines(layout: StateMachineLayout) -> list[str]:
    return [
        f"\\draw[{('dashed' if rule.style == 'dashed' else 'solid')}] "
        f"({rule.x1},{rule.y1}) -- ({rule.x2},{rule.y2});"
        for rule in layout.rules
    ]


def _annotation_lines(layout: StateMachineLayout) -> list[str]:
    lines: list[str] = []
    for annotation in layout.annotations:
        options = ["sm-annotation", f"align={annotation.align}"]
        if annotation.width is not None:
            options.append(f"text width={annotation.width}cm")
        lines.append(
            f"\\node[{','.join(options)}] ({_node_name(annotation.id)}) at "
            f"({annotation.x},{annotation.y}) {{ {_text(annotation.text)} }};"
        )
    return lines


def _state_style(kind: str) -> str:
    return {
        "initial": "sm-initial",
        "final": "sm-final",
        "choice": "sm-choice",
        "history": "sm-history",
        "connector": "sm-connector",
        "ellipsis": "sm-ellipsis",
    }.get(kind, "sm-state")


def _state_lines(
    states: Sequence[State],
    nodes: Mapping[str, NodePosition],
) -> list[str]:
    lines: list[str] = []
    for state in states:
        position = nodes[state.id]
        kind = state.kind
        label = "" if kind in {"initial", "final"} else state.label
        if kind == "ellipsis":
            label = r"$\cdots$"
        rendered_label = label if kind == "ellipsis" else _text(label)
        lines.append(
            f"\\node[{_state_style(kind)}] ({_node_name(state.id)}) at "
            f"({position.x},{position.y}) {{ {rendered_label} }};"
        )
    return lines


def _hidden_coordinate_lines(
    machine: StateMachine,
    nodes: Mapping[str, NodePosition],
) -> list[str]:
    lines: list[str] = []
    for state in machine.states:
        position = nodes.get(state.id)
        if position is not None and not position.visible:
            lines.append(f"\\coordinate ({_node_name(state.id)}) at ({position.x},{position.y});")
    return lines


def _initial_state_lines(
    machine: StateMachine,
    nodes: Mapping[str, NodePosition],
) -> list[str]:
    lines: list[str] = []
    state_by_id = {state.id: state for state in machine.states}
    for state_id in machine.initial_state_ids:
        if state_id not in nodes:
            continue
        state = state_by_id.get(state_id)
        if state is not None and state.kind == "initial":
            continue
        position = nodes[state_id]
        x, y = position.x - 1.9, position.y
        lines.append(f"\\fill ({x},{y}) circle (0.09cm);")
        lines.append(f"\\draw[sm-edge] ({x + 0.1},{y}) -- ({position.x - 1.45},{y});")
    return lines


def _absolute_transition_label(
    transition: Transition,
    layout: TransitionLayout,
    label: str,
    source: NodePosition,
    target: NodePosition,
) -> str:
    if not layout.label_visible:
        return ""
    width = layout.label_width or 3.3
    align = layout.label_align or "center"
    options = f"sm-edge-label,text width={width}cm,align={align}"
    if layout.label_x is not None and layout.label_y is not None:
        x, y = layout.label_x, layout.label_y
    elif layout.style == "loop" or transition.source_state == transition.target_state:
        x, y = _loop_label_position(source, layout.label_side or "right")
    else:
        x, y = _automatic_label_position(
            source,
            target,
            layout.label_side or "above",
            layout.label_pos,
        )
    return f"\\node[{options}] at ({x},{y}) {{ {label} }};"


def _transition_path(style: str, layout: TransitionLayout, is_loop: bool) -> str:
    if is_loop or style == "loop":
        return f"to[loop {layout.loop_direction or 'right'}]"
    if style in {"bend-left", "bend-right"}:
        bend = layout.bend if layout.bend is not None else 20
        turn = "left" if style == "bend-left" else "right"
        return f"to[bend {turn}={bend}]"
    return "--"


def _transition_lines(
    transition: Transition,
    layout: TransitionLayout,
    nodes: Mapping[str, NodePosition],
) -> list[str]:
    source = transition.source_state
    target = transition.target_state
    if source is None or target is None or source not in nodes or target not in nodes:
        return []
    raw_label = layout.label
    label = _text(str(raw_label if raw_label is not None else _transition_text(transition)))
    source_name, target_name = _node_name(source), _node_name(target)
    is_loop = source == target
    path = _transition_path(layout.style or "straight", layout, is_loop)
    lines = [f"\\draw[sm-edge] ({source_name}) {path} ({target_name});"]
    label_node = _absolute_transition_label(transition, layout, label, nodes[source], nodes[target])
    if label_node:
        lines.append(label_node)
    return lines


def render(machine: StateMachine) -> str:
    """Render one validated state-machine model as a TikZ picture."""
    layout = machine.layout or StateMachineLayout(nodes={}, transitions={})
    nodes = _layout_nodes(machine, layout)
    states = tuple(
        state for state in machine.states if state.id in nodes and nodes[state.id].visible
    )
    lines = _tikz_preamble(layout, _render_scale(layout, nodes))
    lines.extend(_container_lines(layout))
    lines.extend(_rule_lines(layout))
    lines.extend(_annotation_lines(layout))
    lines.extend(_state_lines(states, nodes))
    lines.extend(_hidden_coordinate_lines(machine, nodes))
    lines.extend(_initial_state_lines(machine, nodes))
    for transition in machine.transitions:
        transition_layout = layout.transitions.get(transition.id, TransitionLayout())
        lines.extend(_transition_lines(transition, transition_layout, nodes))
    lines.extend([r"\end{tikzpicture}", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Canonical state-machine JSON")
    parser.add_argument("output", type=Path, help="Generated TikZ file")
    parser.add_argument("--machine", help="Machine ID when the source contains multiple machines")
    args = parser.parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(_machine(payload, args.machine)), encoding="utf-8")


if __name__ == "__main__":
    main()
