"""Source-only quality gates for generated PlantUML state-chart sources."""

from __future__ import annotations

import re
from pathlib import Path

from hla_lab.core.semantic_diagram_types import SemanticDiagramFileEnvelope
from hla_lab.core.semantic_model import StateMachine, StateMachineFile
from hla_lab.diagrams.export_plantuml import _alias, render


def validate_source(machine: StateMachine, source: str) -> list[str]:
    """Validate source preservation before a PlantUML renderer is invoked."""

    failures: list[str] = []
    machine_id = machine.id
    if not source.startswith("@startuml\n") or not source.rstrip().endswith("@enduml"):
        failures.append(f"{machine_id}: missing PlantUML document boundaries")
    if re.search(r"\b(?:x|y)\s*=", source):
        failures.append(f"{machine_id}: generated PlantUML contains manual coordinates")

    missing_states = [
        state.id
        for state in machine.states
        if state.kind not in {"initial", "final"} and f"as {_alias(state.id)}" not in source
    ]
    if missing_states:
        failures.append(f"{machine_id}: omitted states {sorted(missing_states)}")

    transitions = [item for item in machine.transitions if item.source_state and item.target_state]
    actual_transitions = len(re.findall(r"(?:-->|-(?:left|right|up|down)->)", source))
    if actual_transitions != len(transitions):
        failures.append(
            f"{machine_id}: emitted {actual_transitions} transitions for "
            f"{len(transitions)} semantic transitions"
        )

    initial_edges = sum(
        item.source_state in {state.id for state in machine.states if state.kind == "initial"}
        for item in transitions
    )
    final_edges = sum(
        item.target_state in {state.id for state in machine.states if state.kind == "final"}
        for item in transitions
    )
    if initial_edges != source.count("[*] -->"):
        failures.append(
            f"{machine_id}: emitted {source.count('[*] -->')} initial edges "
            f"for {initial_edges} semantic initial edges"
        )
    emitted_terminal_edges = source.count(" --> [*]")
    if final_edges and emitted_terminal_edges < final_edges:
        failures.append(
            f"{machine_id}: emitted {emitted_terminal_edges} terminal edges "
            f"for {final_edges} semantic final edges"
        )

    for kind in ("choice", "history"):
        expected = sum(item.kind == kind for item in machine.states)
        actual = len(re.findall(rf"^\s*state .*<<{kind}>>", source, flags=re.MULTILINE))
        if expected and actual != expected:
            failures.append(
                f"{machine_id}: emitted {actual} {kind} stereotypes for {expected} semantic states"
            )
    return failures


def validate_models(models_dir: Path) -> list[str]:
    """Validate all canonical state-machine models in a semantic directory."""

    failures: list[str] = []
    for path in sorted(models_dir.glob("*.json")):
        source = path.read_text(encoding="utf-8")
        envelope = SemanticDiagramFileEnvelope.model_validate_json(source)
        if "state_machines" not in envelope.model_fields_set:
            continue
        if envelope.schema_version is None or envelope.state_machines is None:
            raise ValueError(
                f"{path}: state-machine model requires schema_version and state_machines"
            )
        state_machine_file = StateMachineFile.model_validate_json(source)
        for machine in state_machine_file.state_machines:
            failures.extend(validate_source(machine, render(machine)))
    return failures
