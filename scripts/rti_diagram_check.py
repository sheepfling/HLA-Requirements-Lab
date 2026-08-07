"""Report diagram coverage useful when validating an HLA RTI implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.hla_semantic import load_hla_document_model
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hla_semantic import load_hla_document_model


def report(root: Path) -> dict[str, object]:
    model = load_hla_document_model(root)
    mapped_transitions = {
        item.transition_id for item in model.transition_coverage if item.status == "mapped"
    }
    transitions = [
        transition for machine in model.state_machines for transition in machine.transitions
    ]
    unmapped_transitions = sorted(
        transition.id
        for transition in transitions
        if transition.id not in mapped_transitions and not transition.implementation_ids
    )
    unmapped_messages = sorted(
        message.id
        for diagram in model.sequence_diagrams
        for message in diagram.messages
        if not message.requirement_ids
    )
    unmapped_edges = sorted(
        edge.id
        for diagram in model.graph_diagrams
        for edge in diagram.edges
        if not edge.requirement_ids and not edge.implementation_ids
    )
    return {
        "document_id": model.document_id,
        "state_machines": len(model.state_machines),
        "transitions": len(transitions),
        "mapped_transitions": len(transitions) - len(unmapped_transitions),
        "unmapped_transitions": unmapped_transitions,
        "sequence_diagrams": len(model.sequence_diagrams),
        "sequence_messages": sum(len(item.messages) for item in model.sequence_diagrams),
        "unmapped_sequence_messages": unmapped_messages,
        "graph_diagrams": len(model.graph_diagrams),
        "graph_edges": sum(len(item.edges) for item in model.graph_diagrams),
        "unmapped_graph_edges": unmapped_edges,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="HLA document source directory")
    parser.add_argument("--fail-on-unmapped", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = report(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"RTI diagram check: {result['mapped_transitions']}/{result['transitions']} "
            "transitions mapped"
        )
        print(f"unmapped sequence messages: {len(result['unmapped_sequence_messages'])}")
        print(f"unmapped graph edges: {len(result['unmapped_graph_edges'])}")
    if args.fail_on_unmapped:
        return int(
            bool(
                result["unmapped_transitions"]
                or result["unmapped_sequence_messages"]
                or result["unmapped_graph_edges"]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
