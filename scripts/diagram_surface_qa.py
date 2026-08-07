"""Verify complete semantic ownership of document diagram surfaces."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from scripts.semantic_model import DiagramSurfaceFile
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from semantic_model import DiagramSurfaceFile


def _safe_name(identifier: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", identifier).strip("-")


def _semantic_record_ids(models_dir: Path) -> set[str]:
    record_ids: set[str] = set()
    for path in sorted(models_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        for key in ("state_machines", "sequence_diagrams", "graph_diagrams"):
            for record in raw.get(key, []):
                if isinstance(record, dict) and isinstance(record.get("id"), str):
                    record_ids.add(record["id"])
    return record_ids


def validate(
    surface_manifest: Path,
    models_dir: Path,
    generated_dir: Path,
    *,
    expected_figures: int | None = None,
) -> dict[str, object]:
    payload = json.loads(surface_manifest.read_text(encoding="utf-8"))
    manifest = DiagramSurfaceFile.model_validate(payload)
    failures: list[str] = []
    generated = [item for item in manifest.surfaces if item.status == "generated"]
    figure_numbers = [item.figure_number for item in generated]
    if len(figure_numbers) != len(set(figure_numbers)):
        failures.append("generated figure numbers are not unique")
    if expected_figures is not None:
        expected = set(range(1, expected_figures + 1))
        actual = set(figure_numbers)
        if actual != expected:
            failures.append(
                f"generated figures differ from expected set: missing={sorted(expected - actual)}, "
                f"extra={sorted(actual - expected)}"
            )
    record_ids = _semantic_record_ids(models_dir)
    for surface in generated:
        if surface.record_id not in record_ids:
            failures.append(f"{surface.id} references missing semantic record {surface.record_id}")
    figure_surface_count = len(generated)
    embedded_count = 0
    binary_commands: list[str] = []
    for path in sorted(generated_dir.glob("content-block-*.tex")):
        text = path.read_text(encoding="utf-8", errors="replace")
        embedded_count += text.count("\\HLAEmbeddedTikZAt")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "\\HLAFigureImageAt" in line or "\\includegraphics" in line:
                binary_commands.append(f"{path}:{line_number}: {line.strip()}")
    if embedded_count != figure_surface_count:
        failures.append(
            f"generated faithful content has {embedded_count} embedded diagrams for "
            f"{figure_surface_count} generated figure surfaces"
        )
    failures.extend(f"binary figure dependency: {item}" for item in binary_commands)
    excluded_assets = sum(item.status == "non-generatable" for item in manifest.surfaces)
    return {
        "passed": not failures,
        "failures": failures,
        "generated_figure_count": figure_surface_count,
        "embedded_diagram_count": embedded_count,
        "non_generatable_asset_count": excluded_assets,
        "generated_record_ids": sorted(item.record_id for item in generated if item.record_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface-manifest", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--expected-figures", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = validate(
        args.surface_manifest,
        args.models,
        args.generated,
        expected_figures=args.expected_figures,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"diagram surface QA: {'passed' if report['passed'] else 'failed'}")
        for failure in report["failures"]:
            print(f"failure: {failure}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
