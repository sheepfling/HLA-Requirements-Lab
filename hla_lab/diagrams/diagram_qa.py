"""Enforce source-only diagram rendering and preview acceptance contracts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pydantic import JsonValue

from hla_lab.core.semantic_model import StateMachine, StateMachineFile, StateMachineLayout
from hla_lab.diagrams.render_state_machine import _layout_nodes, render


def _canonical_machines(models_dir: Path) -> tuple[tuple[Path, StateMachine], ...]:
    machines: list[tuple[Path, StateMachine]] = []
    for path in sorted(models_dir.glob("*.json")):
        payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "state_machines" not in payload:
            continue
        state_machine_file = StateMachineFile.model_validate(payload)
        machines.extend((path, item) for item in state_machine_file.state_machines)
    return tuple(machines)


def validate_renderable(models_dir: Path) -> list[str]:
    """Validate that every modeled state transition has a rendered endpoint."""
    failures: list[str] = []
    for path, machine in _canonical_machines(models_dir):
        layout = machine.layout or StateMachineLayout()
        nodes = _layout_nodes(machine, layout)
        missing_endpoints = [
            transition.id
            for transition in machine.transitions
            if transition.source_state not in nodes or transition.target_state not in nodes
        ]
        if missing_endpoints:
            failures.append(
                f"{path}: {machine.id} has transitions without layout endpoints: "
                f"{sorted(missing_endpoints)}"
            )
        generated = render(machine)
        visible_states = [
            state.id for state in machine.states if state.id in nodes and nodes[state.id].visible
        ]
        missing_nodes = [
            state_id
            for state_id in visible_states
            if f"sm_{re.sub(r'[^a-zA-Z0-9]+', '_', state_id).strip('_')}" not in generated
        ]
        if missing_nodes:
            failures.append(
                f"{path}: {machine.id} omitted rendered states: {sorted(missing_nodes)}"
            )
        expected_edges = sum(
            transition.source_state in nodes and transition.target_state in nodes
            for transition in machine.transitions
        )
        actual_edges = generated.count("\\draw[sm-edge]")
        if actual_edges < expected_edges:
            failures.append(
                f"{path}: {machine.id} emitted {actual_edges} edges for "
                f"{expected_edges} transitions"
            )
    return failures


def validate_artifacts(
    models_dir: Path,
    artifacts_dir: Path,
    *,
    require_previews: bool = False,
) -> list[str]:
    """Validate generated text artifacts and optional compiled preview packets."""
    failures = validate_renderable(models_dir)
    for _path, machine in _canonical_machines(models_dir):
        artifact = artifacts_dir / f"{machine.id}-review"
        for name in ("machine.tex", "machine.dot", "machine.mmd"):
            if not (artifact / name).is_file():
                failures.append(f"{machine.id}: missing {artifact / name}")
        if not require_previews:
            continue
        for name in ("review.pdf", "preview.png"):
            path = artifact / name
            if not path.is_file() or path.stat().st_size == 0:
                failures.append(f"{machine.id}: missing or empty {path}")
        log = artifact / "review.log"
        if not log.is_file():
            failures.append(f"{machine.id}: missing {log}")
        else:
            text = log.read_text(encoding="utf-8", errors="replace")
            if re.search(r"! LaTeX Error:|Emergency stop|Fatal error", text):
                failures.append(f"{machine.id}: LaTeX error reported in {log}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--require-previews", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    failures = validate_artifacts(
        args.models,
        args.artifacts,
        require_previews=args.require_previews,
    )
    report = {"passed": not failures, "failures": failures}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"diagram QA: {'passed' if not failures else 'failed'}")
        for failure in failures:
            print(f"failure: {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
