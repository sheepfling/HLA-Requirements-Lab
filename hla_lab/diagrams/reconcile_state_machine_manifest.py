"""Reconcile extracted-image inventory rows with canonical models and reviews."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from hla_lab.diagrams.review_policy import review_defaults

def _review_field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None

def _canonical_entries(models_dir: Path, reviews_dir: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for review_path in sorted(reviews_dir.glob("*.md")):
        if review_path.name == "README.md":
            continue
        text = review_path.read_text(encoding="utf-8")
        image = _review_field(text, r"^- Source image: `([^`]+)`$")
        model = _review_field(text, r"^- Semantic source: `([^`]+)`$")
        status = _review_field(text, r"^- Status: `([^`]+)`$")
        machine_id = _review_field(text, r"^# Review: `([^`]+)`$")
        if not image or not model or not status or not machine_id:
            continue
        entries[Path(image).name] = {
            "machine_id": machine_id,
            "model": model,
            "status": status,
        }

    # The federate-lifetime chart spans the page-41 and page-42 extracted
    # images but has one canonical prose-derived record and review packet.
    lifetime_path = models_dir / "federate-lifetime.json"
    if lifetime_path.is_file() and "source-p042-xref13871.png" not in entries:
        lifetime_status = next(
            (
                entry["status"]
                for entry in entries.values()
                if entry.get("machine_id") == "federate-lifetime"
            ),
            "draft",
        )
        entries["source-p042-xref13871.png"] = {
            "machine_id": "federate-lifetime",
            "model": lifetime_path.as_posix(),
            "status": lifetime_status,
        }
    return entries

def reconcile(
    manifest: MutableMapping[str, Any], models_dir: Path, reviews_dir: Path
) -> MutableMapping[str, Any]:
    canonical = _canonical_entries(models_dir, reviews_dir)
    diagrams = manifest.get("diagrams", [])
    if not isinstance(diagrams, list):
        raise ValueError("manifest diagrams must be an array")
    for item in diagrams:
        if not isinstance(item, dict):
            continue
        filename = Path(str(item.get("source_image", ""))).name
        model_entry = canonical.get(filename)
        if model_entry:
            item.update(
                {
                    "diagram_type": "state_machine",
                    "status": model_entry["status"],
                    "model": model_entry["model"],
                    "confidence": item.get("confidence") or 0.95,
                }
            )
            if filename == "source-p042-xref13871.png":
                item["notes"] = (
                    "Continuation/source companion image for the prose-derived "
                    "federate-lifetime model."
                )
        else:
            diagram_type = str(item.get("diagram_type") or "other_asset")
            item.update(
                {
                    "diagram_type": diagram_type,
                    "status": "classified",
                    "model": None,
                    "confidence": item.get("confidence") or 0.95,
                    "notes": item.get("notes")
                             or "Classified as a non-state or irrelevant extracted asset.",
                }
            )
        item["review_priority"], item["review_reason"] = review_defaults(
            str(item["diagram_type"]), str(item["status"])
        )

    for scope in manifest.get("document_scopes", []):
        if (
            isinstance(scope, dict)
            and scope.get("inventory_status") == "reviewed_no_state_diagrams"
        ):
            scope["inventory_status"] = "reviewed_no_state_diagrams"
            scope["notes"] = (
                "Source-page/vector audit found no Figure captions or state-chart, "
                "state-diagram, or state-machine markers; the only bundled raster is a small icon."
            )
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = reconcile(manifest, args.models, args.reviews)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        args.manifest.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

if __name__ == "__main__":
    main()
