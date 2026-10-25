"""Regenerate review packets for every canonical state machine."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import JsonValue

from hla_lab.core.semantic_model import StateMachine, StateMachineFile
from hla_lab.paths import REPO_ROOT


def _review_index(reviews_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in sorted(reviews_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^# Review: `([^`]+)`$", text, re.MULTILINE)
        if match:
            index[match.group(1)] = path
    return index


def _artifact_from_record(record: Path) -> str | None:
    if not record.exists():
        return None
    text = record.read_text(encoding="utf-8")
    match = re.search(r"^- Generated TikZ: `([^`]+)/machine\.tex`$", text, re.MULTILINE)
    return match.group(1) if match else None


def _source_image(
    machine: StateMachine,
    model_rel: str,
    diagrams: Sequence[Mapping[str, JsonValue]],
    record: Path,
) -> str:
    if machine.provenance is not None and machine.provenance.image:
        return machine.provenance.image
    if record.exists():
        text = record.read_text(encoding="utf-8")
        match = re.search(r"^- Source image: `([^`]+)`$", text, re.MULTILINE)
        if match:
            return match.group(1)
    for diagram in diagrams:
        if diagram.get("model") == model_rel and diagram.get("source_image"):
            return str(diagram["source_image"])
    raise ValueError(f"no source image found for {machine.id}")


def _manifest_diagrams(path: Path) -> list[dict[str, JsonValue]]:
    manifest: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    raw_diagrams: JsonValue = manifest.get("diagrams", []) if isinstance(manifest, dict) else []
    if not isinstance(raw_diagrams, list):
        return []
    diagram_values: list[JsonValue] = raw_diagrams
    diagrams: list[dict[str, JsonValue]] = []
    for item in diagram_values:
        if isinstance(item, dict):
            diagrams.append(item)
    return diagrams


def _model_entries(
    model_files: Sequence[Path],
    repo_root: Path,
) -> list[tuple[Path, str, StateMachine]]:
    entries: list[tuple[Path, str, StateMachine]] = []
    for model_path in model_files:
        model_rel = model_path.resolve().relative_to(repo_root).as_posix()
        payload: JsonValue = json.loads(model_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "state_machines" not in payload:
            continue
        state_machine_file = StateMachineFile.model_validate(payload)
        entries.extend(
            (model_path, model_rel, machine) for machine in state_machine_file.state_machines
        )
    return entries


def _run_review(
    index: int,
    count: int,
    model_rel: str,
    machine: StateMachine,
    review_index: Mapping[str, Path],
    reviews_dir: Path,
    artifacts_rel: Path,
    diagrams: Sequence[Mapping[str, JsonValue]],
    repo_root: Path,
    args: argparse.Namespace,
) -> None:
    machine_id = machine.id
    record = review_index.get(machine_id) or reviews_dir / f"{machine_id}.md"
    artifact_rel = _artifact_from_record(record)
    artifact = Path(artifact_rel) if artifact_rel else artifacts_rel / f"{machine_id}-review"
    source_image = _source_image(machine, model_rel, diagrams, record)
    command = [
        sys.executable,
        "-m",
        "hla_lab.diagrams.review_state_machine",
        model_rel,
        "--machine",
        machine_id,
        "--source-image",
        source_image,
        "--artifacts",
        artifact.as_posix(),
        "--review-record",
        record.resolve().relative_to(repo_root).as_posix(),
        "--timeout-seconds",
        str(args.timeout_seconds),
    ]
    if args.compile:
        command.append("--compile")
    if args.graphviz:
        command.append("--graphviz")
    if args.miktex_user_root:
        miktex_root = args.miktex_user_root.resolve().relative_to(repo_root).as_posix()
        command.extend(["--miktex-user-root", miktex_root])
    if args.pdftoppm:
        command.extend(["--pdftoppm", str(args.pdftoppm.resolve())])
    subprocess.run(command, cwd=repo_root, check=True)
    print(f"[{index}/{count}] {machine_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--graphviz", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--miktex-user-root", type=Path)
    parser.add_argument("--pdftoppm", type=Path)
    args = parser.parse_args()

    repo_root = REPO_ROOT
    diagrams = _manifest_diagrams(args.manifest)
    reviews_dir = args.reviews.resolve()
    artifacts_rel = args.artifacts.resolve().relative_to(repo_root)
    review_index = _review_index(reviews_dir)
    entries = _model_entries(sorted(args.models.glob("*.json")), repo_root)
    for index, (_model_path, model_rel, machine) in enumerate(entries, start=1):
        _run_review(
            index,
            len(entries),
            model_rel,
            machine,
            review_index,
            reviews_dir,
            artifacts_rel,
            diagrams,
            repo_root,
            args,
        )


if __name__ == "__main__":
    main()
