"""Export validated state-machine records to Graphviz DOT and Mermaid."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.semantic_model import StateMachine, StateMachineFile
from hla_lab.core.text import dot_quote, safe_identifier


def _event_label(event: str, guard: str, initiator: str) -> str:
    label = event.strip()
    if guard.strip():
        label += f"\\n[{guard.strip()}]"
    if initiator != "unknown":
        label += f"\\n({initiator})"
    return label


def render_dot(machine: StateMachine) -> str:
    """Render a state machine as a deterministic Graphviz directed graph."""
    aliases = {state.id: safe_identifier(state.id, prefix="state") for state in machine.states}
    lines = [
        f"// Generated from semantic state machine {machine.id}; edit JSON instead.",
        f"digraph {dot_quote(machine.id)} {{",
        "  rankdir=LR;",
        "  graph [fontname=Helvetica];",
        "  node [shape=box, style=rounded, fontname=Helvetica];",
        "  edge [fontname=Helvetica];",
    ]
    for state in machine.states:
        label = state.label or state.id
        if state.parent_id:
            label = f"{label}\\n[parent: {state.parent_id}]"
        shape = (
            "doublecircle"
            if state.kind == "final"
            else "circle"
            if state.kind
            in {
                "initial",
                "history",
            }
            else "box"
        )
        lines.append(f"  {aliases[state.id]} [label={dot_quote(label)}, shape={shape}];")
    for index, state_id in enumerate(machine.initial_state_ids):
        initial = f"initial_{index}"
        lines.extend(
            (
                f'  {initial} [shape=point, label=""];',
                f"  {initial} -> {aliases[state_id]};",
            )
        )
    for transition in machine.transitions:
        if transition.source_state is None:
            continue
        target = aliases.get(transition.target_state or "")
        if target is None:
            target = f"final_{safe_identifier(transition.id, prefix='target')}"
            lines.append(f'  {target} [shape=point, label=""];')
        event_label = dot_quote(
            _event_label(transition.event, transition.guard, transition.initiator)
        )
        lines.append(f"  {aliases[transition.source_state]} -> {target} [label={event_label}];")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_mermaid(machine: StateMachine) -> str:
    """Render a state machine as Mermaid stateDiagram-v2 syntax."""
    aliases = {state.id: safe_identifier(state.id, prefix="state") for state in machine.states}
    lines = [
        f"%% Generated from semantic state machine {machine.id}; edit JSON instead.",
        "stateDiagram-v2",
    ]
    for state in machine.states:
        label = state.label or state.id
        if state.parent_id:
            label = f"{label} (parent: {state.parent_id})"
        lines.append(f'  state "{label.replace(chr(34), chr(39))}" as {aliases[state.id]}')
    for state_id in machine.initial_state_ids:
        lines.append(f"  [*] --> {aliases[state_id]}")
    for transition in machine.transitions:
        source = aliases.get(transition.source_state or "", "[*]")
        target = aliases.get(transition.target_state or "", "[*]")
        label = _event_label(transition.event, transition.guard, transition.initiator)
        lines.append(f"  {source} --> {target}: {label.replace(chr(92) + 'n', ' / ')}")
    return "\n".join(lines) + "\n"


def load_machines(path: Path) -> tuple[StateMachine, ...]:
    """Load and validate canonical state-machine records from JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return StateMachineFile.model_validate(payload).state_machines


def export(
    model: Path,
    output: Path,
    *,
    machine_ids: tuple[str, ...] = (),
    formats: tuple[str, ...] = ("dot", "mermaid"),
) -> tuple[Path, ...]:
    """Write selected text exports under an ignored output directory."""
    machines = load_machines(model)
    selected = (
        tuple(machine for machine in machines if machine.id in machine_ids)
        if machine_ids
        else machines
    )
    found = {machine.id for machine in selected}
    missing = set(machine_ids) - found
    if missing:
        raise ValueError(f"unknown machine IDs: {sorted(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for machine in selected:
        safe = safe_identifier(machine.id, prefix="")
        if "dot" in formats:
            path = output / f"{safe}.dot"
            path.write_text(render_dot(machine), encoding="utf-8")
            paths.append(path)
        if "mermaid" in formats:
            path = output / f"{safe}.mmd"
            path.write_text(render_mermaid(machine), encoding="utf-8")
            paths.append(path)
    return tuple(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="Canonical state-machine JSON")
    parser.add_argument("--output", type=Path, required=True, help="Ignored export directory")
    parser.add_argument("--machine", action="append", default=[])
    parser.add_argument("--format", choices=("dot", "mermaid", "both"), default="both")
    args = parser.parse_args()
    formats = ("dot", "mermaid") if args.format == "both" else (args.format,)
    for path in export(
        args.model,
        args.output,
        machine_ids=tuple(args.machine),
        formats=formats,
    ):
        print(path)


if __name__ == "__main__":
    main()
