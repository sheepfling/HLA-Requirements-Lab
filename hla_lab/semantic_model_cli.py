"""Command-line view of an HLA document's semantic model."""

from __future__ import annotations

import argparse
from pathlib import Path

from hla_lab.corpus.hla_semantic import load_hla_document_model


def main() -> None:
    """Print semantic-model counts or emit its JSON representation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Document source directory")
    parser.add_argument("--workspace-root", type=Path, help="Repository root for document catalog")
    parser.add_argument("--json", action="store_true", help="Print the machine-readable model")
    args = parser.parse_args()
    model = load_hla_document_model(args.root, workspace_root=args.workspace_root)
    if args.json:
        print(model.to_json())
        return
    print(f"clauses: {len(model.clauses)}")
    print(f"definitions: {len(model.definitions)}")
    print(f"requirements: {len(model.requirements)}")
    print(f"content blocks: {len(model.content_blocks)}")
    print(f"implementations: {len(model.implementations)}")
    print(f"API surfaces: {len(model.api_surfaces)}")
    print(f"verification tests: {len(model.verification_tests)}")
    print(f"state traces: {len(model.state_traces)}")
    print(
        "requirement extractions: "
        f"{sum(item.extraction == 'explicit' for item in model.requirements)} explicit, "
        f"{sum(item.extraction == 'candidate' for item in model.requirements)} candidates"
    )
    print(f"state machines: {len(model.state_machines)}")
    print(f"tables: {len(model.tables)}")
    print(f"table cells: {sum(len(item.cells) for item in model.tables)}")
    print(f"references: {len(model.references)}")
    print(f"notes: {len(model.notes)}")
    print(f"figures: {len(model.figures)}")
    print(f"examples: {len(model.examples)}")
    print(f"annexes: {len(model.annexes)}")
    for item in model.requirements:
        # Keep the diagnostic CLI usable under legacy Windows code pages.
        display = f"{item.id}: {item.statement}"
        print(display.encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    main()
