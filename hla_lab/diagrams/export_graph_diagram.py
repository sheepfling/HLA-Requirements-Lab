"""Export validated generic graph-diagram records to Mermaid and TikZ."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from hla_lab.core.semantic_model import GraphDiagram, GraphDiagramFile, GraphEdge, GraphNode
from hla_lab.core.text import format_number, mermaid_text, safe_identifier, tex_escape


def _arrow(edge: GraphEdge) -> str:
    return {
        "none": "",
        "forward": "->",
        "reverse": "<-",
        "both": "<->",
    }[edge.direction]


def render_mermaid(diagram: GraphDiagram) -> str:
    """Render a graph as a portable Mermaid flowchart."""
    aliases = {node.id: safe_identifier(node.id) for node in diagram.nodes}
    lines = [
        f"%% Generated from semantic graph diagram {diagram.id}; edit JSON instead.",
        "flowchart TB",
    ]
    for node in diagram.nodes:
        if node.style == "invisible" or not node.visible:
            continue
        lines.append(f'  {aliases[node.id]}["{mermaid_text(node.label)}"]')
    for edge in diagram.edges:
        if edge.source is None or edge.target is None:
            continue
        connector = "-.->" if edge.style == "dotted" else "--->"
        label = f"|{mermaid_text(edge.label)}|" if edge.label else ""
        if edge.direction == "none":
            connector = "---"
        elif edge.direction == "both":
            connector = "<--->"
        lines.append(f"  {aliases[edge.source]} {connector}{label} {aliases[edge.target]}")
    return "\n".join(lines) + "\n"


def _draw_edge(edge: GraphEdge, nodes: Mapping[str, GraphNode]) -> str:
    options = ["line width=0.55pt"]
    if edge.style == "dotted":
        options.append("dotted")
    elif edge.style == "dashed":
        options.append("dashed")
    elif edge.style == "dimension":
        options.extend(("<->", "line width=0.45pt"))
    else:
        arrow = _arrow(edge)
        if arrow:
            options.append(arrow)
    points = edge.points
    if points:
        path = " -- ".join(
            f"({format_number(point.x)},{format_number(point.y)})" for point in points
        )
    elif edge.source is not None and edge.target is not None:
        source = nodes[edge.source]
        target = nodes[edge.target]
        source_y = (
            source.y - source.height / 2 if source.y > target.y else source.y + source.height / 2
        )
        target_y = (
            target.y + target.height / 2 if source.y > target.y else target.y - target.height / 2
        )
        if abs(source.x - target.x) < 0.001:
            path = (
                f"({format_number(source.x)},{format_number(source_y)}) -- "
                f"({format_number(target.x)},{format_number(target_y)})"
            )
        else:
            middle_y = (source_y + target_y) / 2
            path = " -- ".join(
                (
                    f"({format_number(source.x)},{format_number(source_y)})",
                    f"({format_number(source.x)},{format_number(middle_y)})",
                    f"({format_number(target.x)},{format_number(middle_y)})",
                    f"({format_number(target.x)},{format_number(target_y)})",
                )
            )
    else:  # validated records should not reach this branch
        return ""
    label = f" node[graph-label,midway] {{ {tex_escape(edge.label)} }}" if edge.label else ""
    if label:
        parts = path.split(" -- ")
        if len(parts) > 1:
            path = f"{parts[0]} --{label} " + " -- ".join(parts[1:])
    return f"\\draw[{','.join(options)}] {path};"


def _hierarchy_edge_groups(
    diagram: GraphDiagram,
) -> tuple[list[GraphEdge], dict[tuple[str, str], list[GraphEdge]]]:
    groups: dict[tuple[str, str], list[GraphEdge]] = {}
    passthrough: list[GraphEdge] = []
    for edge in diagram.edges:
        if edge.source is None or edge.target is None or edge.direction != "none" or edge.points:
            passthrough.append(edge)
            continue
        groups.setdefault((edge.source, edge.style), []).append(edge)
    return passthrough, groups


def _hierarchy_direction(source: GraphNode, targets: Sequence[GraphNode]) -> bool | None:
    if all(target.y < source.y for target in targets):
        return True
    if all(target.y > source.y for target in targets):
        return False
    return None


def _hierarchy_options(style: str) -> str:
    options = [
        "draw=RLGraphInterface!52",
        "line width=0.42pt",
        "line cap=round",
        "line join=round",
    ]
    if style == "dotted":
        options.append("dotted")
    elif style == "dashed":
        options.append("dashed")
    return ",".join(options)


def _single_hierarchy_line(
    source: GraphNode,
    target: GraphNode,
    *,
    source_y: float,
    target_y: float,
    branch_y: float,
    options: str,
) -> str:
    if abs(source.x - target.x) < 0.001:
        path = (
            f"({format_number(source.x)},{format_number(source_y)}) -- "
            f"({format_number(target.x)},{format_number(target_y)})"
        )
    else:
        path = " -- ".join(
            (
                f"({format_number(source.x)},{format_number(source_y)})",
                f"({format_number(source.x)},{format_number(branch_y)})",
                f"({format_number(target.x)},{format_number(branch_y)})",
                f"({format_number(target.x)},{format_number(target_y)})",
            )
        )
    return f"\\draw[{options}] {path};"


def _multiple_hierarchy_lines(
    source: GraphNode,
    targets: Sequence[GraphNode],
    target_ys: Sequence[float],
    *,
    source_y: float,
    branch_y: float,
    options: str,
) -> list[str]:
    left = min(target.x for target in targets)
    right = max(target.x for target in targets)
    lines = [
        f"\\draw[{options}] "
        f"({format_number(source.x)},{format_number(source_y)}) -- "
        f"({format_number(source.x)},{format_number(branch_y)}) -- "
        f"({format_number(left)},{format_number(branch_y)});"
    ]
    if right != left:
        lines.append(
            f"\\draw[{options}] "
            f"({format_number(left)},{format_number(branch_y)}) -- "
            f"({format_number(right)},{format_number(branch_y)});"
        )
    lines.extend(
        f"\\draw[{options}] "
        f"({format_number(target.x)},{format_number(branch_y)}) -- "
        f"({format_number(target.x)},{format_number(target_y)});"
        for target, target_y in zip(targets, target_ys, strict=True)
    )
    return lines


def _draw_hierarchy_group(
    source_id: str,
    style: str,
    edges: Sequence[GraphEdge],
    nodes: Mapping[str, GraphNode],
) -> list[str]:
    source = nodes[source_id]
    targets = [nodes[edge.target] for edge in edges if edge.target in nodes]
    if not targets:
        return []
    descending = _hierarchy_direction(source, targets)
    if descending is None:
        return [_draw_edge(edge, nodes) for edge in edges]
    source_y = source.y - source.height / 2 if descending else source.y + source.height / 2
    target_ys = [
        target.y + target.height / 2 if descending else target.y - target.height / 2
        for target in targets
    ]
    branch_y = (source_y + (min(target_ys) if descending else max(target_ys))) / 2
    options = _hierarchy_options(style)
    if len(targets) == 1:
        return [
            _single_hierarchy_line(
                source,
                targets[0],
                source_y=source_y,
                target_y=target_ys[0],
                branch_y=branch_y,
                options=options,
            )
        ]
    return _multiple_hierarchy_lines(
        source,
        targets,
        target_ys,
        source_y=source_y,
        branch_y=branch_y,
        options=options,
    )


def _draw_hierarchy_edges(diagram: GraphDiagram, nodes: Mapping[str, GraphNode]) -> list[str]:
    """Draw hierarchy edges as light orthogonal branch guides.

    The source model contains individual parent/child relationships, but
    drawing every relationship as an independent routed polyline makes a
    dense hierarchy look like a wiring diagram.  Grouping siblings into a
    shared trunk preserves every relationship while keeping the guides out
    of the node labels.
    """
    passthrough, groups = _hierarchy_edge_groups(diagram)
    lines = [_draw_edge(edge, nodes) for edge in passthrough]
    for (source_id, style), edges in groups.items():
        lines.extend(_draw_hierarchy_group(source_id, style, edges, nodes))
    return lines


def render_tikz(diagram: GraphDiagram) -> str:
    """Render a graph as deterministic, dependency-light TikZ."""
    hierarchy = diagram.kind == "hierarchy"
    lines = [
        "% Generated by hla_lab/diagrams/export_graph_diagram.py; edit semantic JSON instead.",
        "\\begin{tikzpicture}[x=1cm,y=1cm,>=stealth,",
        "  graph-box/.style={draw,rounded corners,align=center,font=\\scriptsize,"
        "text width=2.8cm,minimum height=0.7cm},",
        "  graph-frame/.style={draw,align=center,font=\\scriptsize,"
        "text width=3cm,minimum height=0.7cm},",
        "  graph-lifeline/.style={draw,rounded corners,align=center,font=\\small,"
        "minimum width=2.4cm,minimum height=0.65cm},",
        "  graph-ellipse/.style={draw,ellipse,align=center,font=\\scriptsize,"
        "text width=2.8cm,minimum height=0.7cm},",
        "  graph-label/.style={font=\\tiny,fill=white,inner sep=1pt,align=center,"
        "text width=3.2cm},",
        "  graph-hierarchy-box/.style={draw=RLGraphInterface!82,fill=white,rounded corners=2pt,"
        "align=center,text=RLGraphInk,font=\\RLMono\\fontsize{7.35pt}{8.7pt}\\selectfont,"
        "inner xsep=5pt,inner ysep=3pt},",
        "  graph-hierarchy-note/.style={draw=RLGraphInterface!52,fill=RLGraphInterfaceTint,"
        "rounded corners=2pt,align=center,text=RLGraphInk,font=\\RLSans\\itshape"
        "\\fontsize{7.25pt}{8.6pt}\\selectfont,inner xsep=5pt,inner ysep=3pt},",
        "]",
    ]
    nodes = {node.id: node for node in diagram.nodes}
    for node in diagram.nodes:
        if node.style == "invisible" or not node.visible:
            continue
        style = {
            "box": "graph-box",
            "frame": "graph-frame",
            "lifeline": "graph-lifeline",
            "ellipse": "graph-ellipse",
            "point": "coordinate",
        }.get(node.style, "graph-box")
        if hierarchy and node.style == "box":
            style = (
                "graph-hierarchy-note"
                if node.label.strip().startswith("(")
                else "graph-hierarchy-box"
            )
        size = (
            f",minimum width={format_number(node.width)}cm,"
            f"minimum height={format_number(node.height)}cm"
        )
        if node.style == "point":
            lines.append(
                f"\\coordinate ({safe_identifier(node.id)}) at "
                f"({format_number(node.x)},{format_number(node.y)});"
            )
            continue
        lines.append(
            f"\\node[{style}{size}] ({safe_identifier(node.id)}) at "
            f"({format_number(node.x)},{format_number(node.y)}) {{ {tex_escape(node.label)} }};"
        )
    if hierarchy:
        lines.extend(_draw_hierarchy_edges(diagram, nodes))
    else:
        for edge in diagram.edges:
            lines.append(_draw_edge(edge, nodes))
    for annotation in diagram.annotations:
        width = (
            f",text width={format_number(annotation.width)}cm"
            if annotation.width is not None
            else ""
        )
        lines.append(
            f"\\node[font=\\scriptsize,align={annotation.align}{width},"
            f"rotate={format_number(annotation.rotate)}] "
            f"at ({format_number(annotation.x)},{format_number(annotation.y)}) "
            f"{{ {tex_escape(annotation.text)} }};"
        )
    lines.extend(["\\end{tikzpicture}", ""])
    return "\n".join(lines)


def load_diagrams(path: Path) -> tuple[GraphDiagram, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return GraphDiagramFile.model_validate(payload).graph_diagrams


def export(
    model: Path,
    output: Path,
    *,
    diagram_ids: tuple[str, ...] = (),
    formats: tuple[str, ...] = ("tikz", "mermaid"),
) -> tuple[Path, ...]:
    diagrams = load_diagrams(model)
    selected = (
        tuple(item for item in diagrams if item.id in diagram_ids) if diagram_ids else diagrams
    )
    missing = set(diagram_ids) - {item.id for item in selected}
    if missing:
        raise ValueError(f"unknown graph diagram IDs: {sorted(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for diagram in selected:
        safe = safe_identifier(diagram.id, prefix="")
        if "tikz" in formats:
            path = output / f"graph-diagram-{safe}.tex"
            path.write_text(render_tikz(diagram), encoding="utf-8")
            paths.append(path)
        if "mermaid" in formats:
            path = output / f"graph-diagram-{safe}.mmd"
            path.write_text(render_mermaid(diagram), encoding="utf-8")
            paths.append(path)
    return tuple(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="Canonical graph-diagram JSON")
    parser.add_argument("--output", type=Path, required=True, help="Ignored export directory")
    parser.add_argument("--diagram", action="append", default=[])
    parser.add_argument("--format", choices=("tikz", "mermaid", "both"), default="both")
    args = parser.parse_args()
    formats = ("tikz", "mermaid") if args.format == "both" else (args.format,)
    for path in export(args.model, args.output, diagram_ids=tuple(args.diagram), formats=formats):
        print(path)


if __name__ == "__main__":
    main()
