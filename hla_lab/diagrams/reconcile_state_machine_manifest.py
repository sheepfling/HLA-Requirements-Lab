"""Reconcile extracted-image inventory rows with canonical models and reviews."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter

from hla_lab.diagrams.review_policy import review_defaults
from hla_lab.diagrams.state_machine_inventory import (
    DiagramInventoryEntry,
    DiagramStatus,
    DiagramType,
    StateMachineInventory,
)


def _review_field(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


class _CanonicalMachine(BaseModel):
    """Canonical state-machine identity and its current review disposition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    machine_id: str
    model: str
    status: DiagramStatus


_STATUS_ADAPTER = TypeAdapter(DiagramStatus)
DEFAULT_STATE_MACHINE_STATUS: DiagramStatus = "draft"


def _canonical_entries(models_dir: Path, reviews_dir: Path) -> dict[str, _CanonicalMachine]:
    entries: dict[str, _CanonicalMachine] = {}
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
        try:
            validated_status = _STATUS_ADAPTER.validate_python(status)
            entries[Path(image).name] = _CanonicalMachine(
                machine_id=machine_id,
                model=model,
                status=validated_status,
            )
        except ValueError as error:
            raise ValueError(f"invalid review status {status!r} in {review_path}") from error

    # The federate-lifetime chart spans the page-41 and page-42 extracted
    # images but has one canonical prose-derived record and review packet.
    lifetime_path = models_dir / "federate-lifetime.json"
    if lifetime_path.is_file() and "source-p042-xref13871.png" not in entries:
        existing_lifetime_status = next(
            (entry.status for entry in entries.values() if entry.machine_id == "federate-lifetime"),
            None,
        )
        lifetime_status = _STATUS_ADAPTER.validate_python(
            existing_lifetime_status or DEFAULT_STATE_MACHINE_STATUS
        )
        entries["source-p042-xref13871.png"] = _CanonicalMachine(
            machine_id="federate-lifetime",
            model=lifetime_path.as_posix(),
            status=lifetime_status,
        )
    return entries


def reconcile(
    manifest: StateMachineInventory, models_dir: Path, reviews_dir: Path
) -> StateMachineInventory:
    canonical = _canonical_entries(models_dir, reviews_dir)
    diagrams: list[DiagramInventoryEntry] = []
    for item in manifest.diagrams:
        filename = Path(item.source_image).name
        model_entry = canonical.get(filename)
        if model_entry:
            diagram_type: DiagramType = "state_machine"
            status = model_entry.status
            model = model_entry.model
            confidence = item.confidence or 0.95
            notes = item.notes
            if filename == "source-p042-xref13871.png":
                notes = (
                    "Continuation/source companion image for the prose-derived "
                    "federate-lifetime model."
                )
        else:
            diagram_type = item.diagram_type or "other_asset"
            status = "classified"
            model = None
            confidence = item.confidence or 0.95
            notes = item.notes or "Classified as a non-state or irrelevant extracted asset."
        review_priority, review_reason = review_defaults(diagram_type, status)
        diagrams.append(
            item.model_copy(
                update={
                    "diagram_type": diagram_type,
                    "status": status,
                    "model": model,
                    "confidence": confidence,
                    "notes": notes,
                    "review_priority": review_priority,
                    "review_reason": review_reason,
                }
            )
        )
    scopes = tuple(
        scope.model_copy(
            update={
                "notes": (
                    "Source-page/vector audit found no Figure captions or state-chart, "
                    "state-diagram, or state-machine markers; the only bundled raster is "
                    "a small icon."
                )
            }
        )
        if scope.inventory_status == "reviewed_no_state_diagrams"
        else scope
        for scope in manifest.document_scopes
    )
    return manifest.model_copy(update={"diagrams": tuple(diagrams), "document_scopes": scopes})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    manifest = StateMachineInventory.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    result = reconcile(manifest, args.models, args.reviews)
    rendered = result.model_dump_json(indent=2) + "\n"
    if args.write:
        args.manifest.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
