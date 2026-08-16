"""Regenerate review packets for every canonical state machine."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

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
    machine: Mapping[str, Any],
    model_rel: str,
    diagrams: Sequence[Mapping[str, Any]],
    record: Path,
) -> str:
    provenance = machine.get("provenance")
    if isinstance(provenance, dict) and provenance.get("image"):
        return str(provenance["image"])
    if record.exists():
        text = record.read_text(encoding="utf-8")
        match = re.search(r"^- Source image: `([^`]+)`$", text, re.MULTILINE)
        if match:
            return match.group(1)
    for diagram in diagrams:
        if diagram.get("model") == model_rel and diagram.get("source_image"):
            return str(diagram["source_image"])
    raise ValueError(f"no source image found for {machine.get('id')}")


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
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    diagrams = [item for item in manifest.get("diagrams", []) if isinstance(item, dict)]
    reviews_dir = args.reviews.resolve()
    artifacts_rel = args.artifacts.resolve().relative_to(repo_root)
    review_index = _review_index(reviews_dir)
    model_files = sorted(args.models.glob("*.json"))
    entries: list[tuple[Path, str, dict[str, Any]]] = []
    for model_path in model_files:
        model_rel = model_path.resolve().relative_to(repo_root).as_posix()
        payload = json.loads(model_path.read_text(encoding="utf-8"))
        for machine in payload.get("state_machines", []):
            entries.append((model_path, model_rel, machine))

    for index, (_model_path, model_rel, machine) in enumerate(entries, start=1):
        machine_id = str(machine["id"])
        record = review_index.get(machine_id)
        if record is None:
            record = reviews_dir / f"{machine_id}.md"
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
        print(f"[{index}/{len(entries)}] {machine_id}")


if __name__ == "__main__":
    main()
