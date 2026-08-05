"""Reconcile extracted-image inventory rows with canonical models and reviews."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

NON_STATE_TYPES = {
    "source-p001-xref114.png": "other_asset",
    "source-p001-xref115.png": "other_asset",
    "source-p001-xref116.png": "other_asset",
    "source-p001-xref117.png": "other_asset",
    "source-p001-xref118.png": "other_asset",
    "source-p001-xref119.png": "other_asset",
    "source-p040-xref13869.png": "relationship_view",
    "source-p223-xref13896.png": "ddm_conceptual_diagram",
    "source-p289-xref13897.png": "mom_class_hierarchy",
    "source-p290-xref13898.png": "mom_class_hierarchy",
    "source-p396-xref13906.png": "protocol_architecture",
    "source-p399-xref13909.png": "message_sequence",
    "source-p399-xref13910.png": "message_sequence",
    "source-p402-xref13919.png": "message_sequence",
    "source-p440-xref11589.png": "other_asset",
    "source-p440-xref11590.png": "other_asset",
    "source-p440-xref11591.png": "other_asset",
    "source-p440-xref11592.png": "other_asset",
}

NON_STATE_NOTES = {
    "relationship_view": "Figure 2 is a federate-to-RTI relationship view, not a state machine.",
    "ddm_conceptual_diagram": "Figure 18 is a DDM conceptual diagram, not a state machine.",
    "mom_class_hierarchy": "This figure is a MOM class hierarchy, not a state machine.",
    "protocol_architecture": (
        "Figure 21 is a protocol-layer architecture diagram, not a state machine."
    ),
    "message_sequence": "This figure is a message-sequence diagram, not a state machine.",
    "other_asset": "Extracted asset is not a state diagram candidate for this backlog.",
}


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
    lifetime_image = next((path.name for path in (models_dir).glob("federate-lifetime.json")), None)
    if lifetime_image and "source-p042-xref13871.png" not in entries:
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
            "model": "topics/ieee/hla-1516.1-2025/semantic/federate-lifetime.json",
            "status": lifetime_status,
        }
    return entries


def _review_defaults(diagram_type: str, status: str) -> tuple[str, str]:
    if diagram_type != "state_machine":
        return "none", "Explicitly classified as a non-state diagram or irrelevant asset."
    if status == "needs_review":
        return "high", "Known source ambiguity or parameterization requires targeted review."
    if status == "unmodeled":
        return "high", "Candidate has no semantic record yet."
    if status == "draft":
        return "medium", "Semantic record exists; source comparison and refinement remain."
    if status == "validated":
        return "low", "Semantics compared with source; visual acceptance remains."
    return "none", "No semantic review is required for the current classification."


def reconcile(manifest: dict[str, Any], models_dir: Path, reviews_dir: Path) -> dict[str, Any]:
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
            diagram_type = NON_STATE_TYPES.get(filename, "other_asset")
            item.update(
                {
                    "diagram_type": diagram_type,
                    "status": "classified",
                    "model": None,
                    "confidence": item.get("confidence") or 0.95,
                    "notes": NON_STATE_NOTES.get(
                        diagram_type, "Classified as a non-state or irrelevant extracted asset."
                    ),
                }
            )
        item["review_priority"], item["review_reason"] = _review_defaults(
            str(item["diagram_type"]), str(item["status"])
        )

    for scope in manifest.get("document_scopes", []):
        if isinstance(scope, dict) and scope.get("document") == "hla-1516.2":
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
