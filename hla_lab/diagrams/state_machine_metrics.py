"""Validate state-machine records and report migration coverage."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path

from pydantic import JsonValue

from hla_lab.core.semantic_model import StateMachineFile

STATUSES = ("unmodeled", "classified", "draft", "needs_review", "validated", "rendered", "accepted")
MODEL_STATUSES = frozenset({"draft", "needs_review", "validated", "rendered", "accepted"})


def _json_objects(values: Sequence[JsonValue]) -> tuple[dict[str, JsonValue], ...]:
    records: list[dict[str, JsonValue]] = []
    for raw_value in values:
        value: JsonValue = raw_value
        if isinstance(value, dict):
            records.append(value)
    return tuple(records)


def _load(path: Path) -> dict[str, JsonValue]:
    value: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("top-level JSON value must be an object")
    return value


def _record_ids(records: Sequence[JsonValue]) -> list[JsonValue]:
    return [record.get("id") for record in records if isinstance(record, dict)]


def _duplicate_id_error(path: Path, message: str, records: Sequence[JsonValue]) -> list[str]:
    ids = _record_ids(records)
    return [f"{path}: {message}"] if len(ids) != len(set(ids)) else []


def _validate_transition(
    path: Path,
    transition: JsonValue,
    state_ids: AbstractSet[JsonValue],
) -> list[str]:
    if not isinstance(transition, dict):
        return [f"{path}: transition is not an object"]
    errors = [
        f"{path}: transition missing {field}"
        for field in ("id", "source_state", "target_state", "event")
        if field not in transition
    ]
    for endpoint in ("source_state", "target_state"):
        value = transition.get(endpoint)
        if value is not None and value not in state_ids:
            errors.append(
                f"{path}: transition {transition.get('id')} has unknown {endpoint} {value}"
            )
    return errors


def _validate_machine(path: Path, machine: JsonValue) -> list[str]:
    if not isinstance(machine, dict):
        return [f"{path}: state machine is not an object"]
    machine_id = machine.get("id")
    raw_states: JsonValue = machine.get("states", [])
    raw_transitions: JsonValue = machine.get("transitions", [])
    if not isinstance(raw_states, list) or not isinstance(raw_transitions, list):
        return [f"{path}: machine {machine_id} states/transitions must be arrays"]
    states: list[JsonValue] = raw_states
    transitions: list[JsonValue] = raw_transitions
    state_ids = _record_ids(states)
    errors = _duplicate_id_error(path, f"machine {machine_id} has duplicate state IDs", states)
    errors.extend(
        _duplicate_id_error(path, f"machine {machine_id} has duplicate transition IDs", transitions)
    )
    known_states = set(state_ids)
    for transition in transitions:
        errors.extend(_validate_transition(path, transition, known_states))
    return errors


def validate_model(path: Path, model: Mapping[str, JsonValue]) -> list[str]:
    errors = [
        f"{path}: missing {field}"
        for field in ("schema_version", "state_machines")
        if field not in model
    ]
    raw_machines = model.get("state_machines", [])
    if not isinstance(raw_machines, list):
        return [*errors, f"{path}: state_machines must be an array"]
    machines: list[JsonValue] = raw_machines
    errors.extend(_duplicate_id_error(path, "duplicate state-machine IDs", machines))
    for machine in machines:
        errors.extend(_validate_machine(path, machine))
    return errors


def _review_metrics(reviews_dir: Path, artifacts_dir: Path) -> list[str]:
    records = sorted(reviews_dir.glob("*.md")) if reviews_dir.exists() else []
    records = [path for path in records if path.name != "README.md"]
    accepted = 0
    for path in records:
        if "- Accepted: [x]" in path.read_text(encoding="utf-8"):
            accepted += 1
    artifacts = sorted(artifacts_dir.glob("*-review")) if artifacts_dir.exists() else []
    tikz = sum((path / "machine.tex").is_file() for path in artifacts)
    previews = sum((path / "preview.png").is_file() for path in artifacts)
    return [
        f"review records: {len(records)}",
        f"TikZ artifacts: {tikz}",
        f"preview PNGs: {previews}",
        f"accepted reviews: {accepted}",
    ]


def report(
    manifest_path: Path,
    models_dir: Path,
    reviews_dir: Path | None = None,
    artifacts_dir: Path | None = None,
) -> tuple[str, int]:
    manifest = _load(manifest_path)
    raw_diagrams: JsonValue = manifest.get("diagrams", [])
    if not isinstance(raw_diagrams, list):
        return "manifest error: diagrams must be an array", 1
    diagrams: list[JsonValue] = raw_diagrams
    statuses = Counter(str(item.get("status", "missing")) for item in _json_objects(diagrams))
    priorities = Counter(
        str(item.get("review_priority", "unassigned")) for item in _json_objects(diagrams)
    )
    raw_scopes: JsonValue = manifest.get("document_scopes", [])
    scopes: list[JsonValue] = raw_scopes if isinstance(raw_scopes, list) else []
    errors: list[str] = []
    model_files = (
        sorted(path for path in models_dir.glob("*.json") if path.name != manifest_path.name)
        if models_dir.exists()
        else []
    )
    canonical_machines = 0
    canonical_model_files = 0
    for path in model_files:
        try:
            model = _load(path)
            # The semantic directory also contains supporting mappings such as
            # implementations.json. Only canonical model files carry the
            # state_machines collection and should contribute to model metrics.
            if "state_machines" not in model:
                continue
            canonical_model_files += 1
            state_machine_file = StateMachineFile.model_validate(model)
            canonical_machines += len(state_machine_file.state_machines)
            errors.extend(validate_model(path, model))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    total = len(diagrams)
    modeled = sum(statuses[status] for status in MODEL_STATUSES)
    classified = total - statuses["unmodeled"]
    coverage = modeled / total if total else 0.0
    lines = [
        f"manifest: {manifest_path}",
        "scopes: "
        + ", ".join(
            f"{item.get('document')}={item.get('inventory_status')}"
            f"({item.get('extracted_candidates', 0)})"
            for item in _json_objects(scopes)
        ),
        f"diagrams: {total}",
        (
            f"classified: {classified}/{total} ({classified / total:.1%})"
            if total
            else "classified: 0/0 (0.0%)"
        ),
        f"modeled: {modeled}/{total} ({coverage:.1%})" if total else "modeled: 0/0 (0.0%)",
        "status: "
        + ", ".join(f"{status}={statuses[status]}" for status in STATUSES if statuses[status]),
        "review priority: "
        + ", ".join(
            f"{priority}={priorities[priority]}"
            for priority in ("high", "medium", "low", "none", "unassigned")
            if priorities[priority]
        ),
        f"model files: {canonical_model_files}",
        f"canonical machines: {canonical_machines}",
        f"validation errors: {len(errors)}",
    ]
    if reviews_dir is not None and artifacts_dir is not None:
        lines.extend(_review_metrics(reviews_dir, artifacts_dir))
    if errors:
        lines.extend(f"ERROR: {error}" for error in errors)
    return "\n".join(lines), 1 if errors else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, help="Tracked Markdown review directory")
    parser.add_argument("--artifacts", type=Path, help="Ignored generated-artifact directory")
    args = parser.parse_args()
    if (args.reviews is None) != (args.artifacts is None):
        parser.error("--reviews and --artifacts must be provided together")
    output, exit_code = report(args.manifest, args.models, args.reviews, args.artifacts)
    print(output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
