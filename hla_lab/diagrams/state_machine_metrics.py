"""Validate state-machine records and report migration coverage."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from hla_lab.core.semantic_diagram_types import SemanticDiagramFileEnvelope, StateMachineFile
from hla_lab.diagrams.state_machine_inventory import StateMachineInventory

STATUSES = ("unmodeled", "classified", "draft", "needs_review", "validated", "rendered", "accepted")
MODEL_STATUSES = frozenset({"draft", "needs_review", "validated", "rendered", "accepted"})


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
    try:
        manifest = StateMachineInventory.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        return f"manifest error: {exc}", 1
    statuses = Counter(item.status for item in manifest.diagrams)
    priorities = Counter(item.review_priority for item in manifest.diagrams)
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
            source = path.read_text(encoding="utf-8")
            envelope = SemanticDiagramFileEnvelope.model_validate_json(source)
            if "state_machines" not in envelope.model_fields_set:
                continue
            if envelope.schema_version is None or envelope.state_machines is None:
                raise ValueError("state-machine model requires schema_version and state_machines")
            state_machine_file = StateMachineFile.model_validate_json(source)
            canonical_model_files += 1
            canonical_machines += len(state_machine_file.state_machines)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    total = len(manifest.diagrams)
    modeled = sum(statuses[status] for status in MODEL_STATUSES)
    classified = total - statuses["unmodeled"]
    coverage = modeled / total if total else 0.0
    lines = [
        f"manifest: {manifest_path}",
        "scopes: "
        + ", ".join(
            f"{item.document}={item.inventory_status}({item.extracted_candidates})"
            for item in manifest.document_scopes
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
