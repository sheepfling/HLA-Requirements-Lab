"""Render a canonical state-machine JSON file as a TikZ picture."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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

def _transition_text(transition: Mapping[str, Any]) -> str:
    event = str(transition.get("event", "")).strip()
    guard = str(transition.get("guard", "")).strip()
    if event and guard:
        return f"{event}\n[{guard}]"
    if guard:
        return f"[{guard}]"
    return event

def _render_scale(
    machine: Mapping[str, Any],
    layout: Mapping[str, Any],
    nodes: Mapping[str, Mapping[str, Any]],
) -> float:
    """Choose a deterministic scale that keeps large source layouts reviewable."""
    points = [
        (float(position["x"]), float(position["y"]))
        for position in nodes.values()
        if "x" in position and "y" in position
    ]
    for container in layout.get("containers", []):
        points.extend(
            (
                (float(container["x"]), float(container["y"])),
                (
                    float(container["x"]) + float(container["width"]),
                    float(container["y"]) + float(container["height"]),
                ),
            )
        )
    for annotation in layout.get("annotations", []):
        points.append((float(annotation["x"]), float(annotation["y"])))
    for transition_layout in layout.get("transitions", {}).values():
        if (
            isinstance(transition_layout, dict)
            and transition_layout.get("label_x") is not None
            and transition_layout.get("label_y") is not None
        ):
            points.append(
                (
                    float(transition_layout["label_x"]),
                    float(transition_layout["label_y"]),
                )
            )
    if not points:
        return 1.0
    width = max(item[0] for item in points) - min(item[0] for item in points) + 4.0
    height = max(item[1] for item in points) - min(item[1] for item in points) + 3.0
    return round(min(1.0, 16.0 / width, 11.0 / height), 3)

def _automatic_label_position(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    side: str,
    position: float | None,
) -> tuple[float, float]:
    """Place an unlabeled edge label in a stable lane away from its edge."""
    fraction = 0.5 if position is None else float(position)
    x = float(source["x"]) + (float(target["x"]) - float(source["x"])) * fraction
    y = float(source["y"]) + (float(target["y"]) - float(source["y"])) * fraction
    if side == "above":
        y += 0.72
    elif side == "below":
        y -= 0.72
    elif side == "left":
        x -= 0.92
    else:
        x += 0.92
    return round(x, 3), round(y, 3)

def _loop_label_position(source: Mapping[str, Any], side: str) -> tuple[float, float]:
    x = float(source["x"])
    y = float(source["y"])
    if side == "above":
        y += 0.9
    elif side == "below":
        y -= 0.9
    elif side == "left":
        x -= 1.1
    else:
        x += 1.1
    return round(x, 3), round(y, 3)

def _layout_nodes(
    machine: Mapping[str, Any], layout: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    declared = layout.get("nodes", {})
    nodes = {
        str(state_id): dict(position)
        for state_id, position in declared.items()
        if isinstance(position, dict)
    }
    states = [state for state in machine.get("states", []) if isinstance(state, dict)]
    parent_by_id = {str(state["id"]): state.get("parent_id") for state in states if state.get("id")}
    for state in states:
        state_id = state.get("id")
        if not state_id or state_id in nodes:
            continue
        descendant_positions: list[dict[str, Any]] = []
        for candidate_id, position in nodes.items():
            current = parent_by_id.get(candidate_id)
            while current is not None:
                if current == state_id:
                    descendant_positions.append(position)
                    break
                current = parent_by_id.get(str(current))
        if descendant_positions:
            nodes[str(state_id)] = {
                "x": sum(float(position["x"]) for position in descendant_positions)
                     / len(descendant_positions),
                "y": sum(float(position["y"]) for position in descendant_positions)
                     / len(descendant_positions),
                "visible": False,
            }
    return nodes

def render(machine: Mapping[str, Any]) -> str:
    layout = machine.get("layout", {})
    nodes = _layout_nodes(machine, layout)
    font_commands = {"tiny": r"\tiny", "scriptsize": r"\scriptsize", "small": r"\small"}
    state_font = font_commands.get(layout.get("state_font"), r"\scriptsize")
    edge_label_font = font_commands.get(layout.get("edge_label_font"), r"\scriptsize")
    scale = _render_scale(machine, layout, nodes)
    states = [
        item
        for item in machine.get("states", [])
        if item.get("id") in nodes and nodes[item["id"]].get("visible", True)
    ]
    lines = [
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
    for container in layout.get("containers", []):
        if not container.get("visible", True):
            continue
        x = container["x"]
        y = container["y"]
        width = container["width"]
        height = container["height"]
        title_x = x + width / 2
        title_y = y + height - 0.25
        lines.append(f"\\draw[sm-container] ({x},{y}) rectangle ++({width},{height});")
        if container.get("title_visible", True):
            lines.append(
                f"\\node[sm-container-title] at ({title_x},{title_y}) "
                f"{{ {_text(container['title'])} }};"
            )
    for rule in layout.get("rules", []):
        if not isinstance(rule, dict):
            continue
        style = "dashed" if rule.get("style") == "dashed" else "solid"
        lines.append(f"\\draw[{style}] ({rule['x1']},{rule['y1']}) -- ({rule['x2']},{rule['y2']});")
    for annotation in layout.get("annotations", []):
        if not isinstance(annotation, dict):
            continue
        width = annotation.get("width")
        align = annotation.get("align", "left")
        options = ["sm-annotation", f"align={align}"]
        if width is not None:
            options.append(f"text width={width}cm")
        lines.append(
            f"\\node[{','.join(options)}] ({_node_name(annotation['id'])}) at "
            f"({annotation['x']},{annotation['y']}) {{ {_text(annotation['text'])} }};"
        )
    for state in states:
        position = nodes[state["id"]]
        kind = state.get("kind", "normal")
        style = {
            "initial": "sm-initial",
            "final": "sm-final",
            "choice": "sm-choice",
            "history": "sm-history",
            "connector": "sm-connector",
            "ellipsis": "sm-ellipsis",
        }.get(kind, "sm-state")
        label = "" if kind in {"initial", "final"} else state["label"]
        if kind == "ellipsis":
            label = r"$\cdots$"
        rendered_label = _text(label) if kind != "ellipsis" else label
        lines.append(
            f"\\node[{style}] ({_node_name(state['id'])}) at "
            f"({position['x']},{position['y']}) {{ {rendered_label} }};"
        )
    for state in machine.get("states", []):
        state_id = state.get("id")
        if state_id in nodes and not nodes[state_id].get("visible", True):
            position = nodes[state_id]
            lines.append(
                f"\\coordinate ({_node_name(state_id)}) at ({position['x']},{position['y']});"
            )
    for state_id in machine.get("initial_state_ids", []):
        if state_id not in nodes:
            continue
        state = next(
            (item for item in machine.get("states", []) if item.get("id") == state_id),
            {},
        )
        if state.get("kind") == "initial":
            continue
        position = nodes[state_id]
        x = position["x"] - 1.9
        y = position["y"]
        lines.append(f"\\fill ({x},{y}) circle (0.09cm);")
        lines.append(f"\\draw[sm-edge] ({x + 0.1},{y}) -- ({position['x'] - 1.45},{y});")
    for transition in machine.get("transitions", []):
        source = transition.get("source_state")
        target = transition.get("target_state")
        if source not in nodes or target not in nodes:
            continue
        source_name = _node_name(source)
        target_name = _node_name(target)
        transition_layout = layout.get("transitions", {}).get(transition.get("id"), {})
        if not isinstance(transition_layout, dict):
            transition_layout = {}
        raw_label = transition_layout.get("label")
        label = _text(str(raw_label if raw_label is not None else _transition_text(transition)))
        style = transition_layout.get("style") or ("loop" if source == target else "straight")
        label_side = transition_layout.get("label_side") or (
            "right" if source == target else "above"
        )
        label_pos = transition_layout.get("label_pos")
        label_width = transition_layout.get("label_width") or 3.3
        label_align = transition_layout.get("label_align") or "center"
        absolute_label = ""
        if transition_layout.get("label_visible", True):
            label_options = f"sm-edge-label,text width={label_width}cm,align={label_align}"
            if (
                transition_layout.get("label_x") is not None
                and transition_layout.get("label_y") is not None
            ):
                absolute_label = (
                    f"\\node[{label_options}] at ({transition_layout['label_x']},"
                    f"{transition_layout['label_y']}) {{ {label} }};"
                )
            else:
                label_position_x, label_position_y = (
                    _loop_label_position(nodes[source], label_side)
                    if style == "loop" or source == target
                    else _automatic_label_position(
                        nodes[source], nodes[target], label_side, label_pos
                    )
                )
                absolute_label = (
                    f"\\node[{label_options}] at ({label_position_x},{label_position_y}) "
                    f"{{ {label} }};"
                )
        if style == "loop" or source == target:
            loop_direction = transition_layout.get("loop_direction") or "right"
            lines.append(
                f"\\draw[sm-edge] ({source_name}) to[loop {loop_direction}] ({target_name});"
            )
        else:
            if style in {"bend-left", "bend-right"}:
                bend = transition_layout.get("bend", 20)
                turn = "left" if style == "bend-left" else "right"
                path = f"to[bend {turn}={bend}]"
            else:
                path = "--"
            lines.append(f"\\draw[sm-edge] ({source_name}) {path} ({target_name});")
        if absolute_label:
            lines.append(absolute_label)
    lines.extend(["\\end{tikzpicture}", ""])
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
