"""Source-only quality gates for generated PlantUML state-chart sources."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from hla_lab.diagrams.export_plantuml import render


def _alias(identifier: str) -> str:
    return "s_" + re.sub(r"[^A-Za-z0-9]+", "_", identifier).strip("_")


def validate_source(machine: dict[str, Any], source: str) -> list[str]:
    """Validate source preservation before a PlantUML renderer is invoked."""

    failures: list[str] = []
    machine_id = str(machine.get("id", "<unknown>"))
    if not source.startswith("@startuml\n") or not source.rstrip().endswith("@enduml"):
        failures.append(f"{machine_id}: missing PlantUML document boundaries")
    if re.search(r"\b(?:x|y)\s*=", source):
        failures.append(f"{machine_id}: generated PlantUML contains manual coordinates")

    states = [item for item in machine.get("states", ()) if isinstance(item, dict)]
    missing_states = [
        str(item.get("id"))
        for item in states
        if item.get("id")
        and item.get("kind") not in {"initial", "final"}
        and f"as {_alias(str(item['id']))}" not in source
    ]
    if missing_states:
        failures.append(f"{machine_id}: omitted states {sorted(missing_states)}")

    transitions = [
        item
        for item in machine.get("transitions", ())
        if isinstance(item, dict)
        and item.get("source_state")
        and item.get("target_state")
    ]
    actual_transitions = len(re.findall(r"(?:-->|-(?:left|right|up|down)->)", source))
    if actual_transitions != len(transitions):
        failures.append(
            f"{machine_id}: emitted {actual_transitions} transitions for {len(transitions)} semantic transitions"
        )

    initial_edges = sum(
        item.get("source_state") in {state.get("id") for state in states if state.get("kind") == "initial"}
        for item in transitions
    )
    final_edges = sum(
        item.get("target_state") in {state.get("id") for state in states if state.get("kind") == "final"}
        for item in transitions
    )
    if initial_edges != source.count("[*] -->"):
        failures.append(
            f"{machine_id}: emitted {source.count('[*] -->')} initial edges for {initial_edges} semantic initial edges"
        )
    emitted_terminal_edges = source.count(" --> [*]")
    if final_edges and emitted_terminal_edges < final_edges:
        failures.append(
            f"{machine_id}: emitted {emitted_terminal_edges} terminal edges for {final_edges} semantic final edges"
        )

    for kind in ("choice", "history"):
        expected = sum(item.get("kind") == kind for item in states)
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
        payload = json.loads(path.read_text(encoding="utf-8"))
        for machine in payload.get("state_machines", ()):
            if isinstance(machine, dict):
                failures.extend(validate_source(machine, render(machine)))
    return failures
