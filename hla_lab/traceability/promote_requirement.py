"""Promote a source-shaped requirement candidate into reviewed semantic source."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from hla_lab.core.io import write_json
from hla_lab.core.json_types import JsonObject, JsonValue
from hla_lab.core.semantic_model import (
    DocumentModel,
    Requirement,
    RequirementFile,
    RequirementLink,
    RequirementLinkFile,
    StateMachineFile,
)
from hla_lab.core.text import slugify
from hla_lab.paths import DocumentResources

RequirementLinkRelation = Literal[
    "governs", "precondition", "postcondition", "enables", "prohibits"
]


def _json_payload(path: Path, default: Mapping[str, JsonValue]) -> JsonObject:
    if not path.is_file():
        return dict(default)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"semantic source must be a JSON object: {path}")
    return payload


def _load_state_machine_payloads(
    root: Path,
) -> tuple[tuple[Path, JsonObject, StateMachineFile], ...]:
    payloads: list[tuple[Path, JsonObject, StateMachineFile]] = []
    for path in sorted(DocumentResources(root).semantic.glob("*.json")):
        payload = _json_payload(path, {})
        if "state_machines" not in payload:
            continue
        payloads.append((path, payload, StateMachineFile.model_validate(payload)))
    return tuple(payloads)


_write_json = write_json


def _load_hla_model(root: Path) -> DocumentModel:
    """Load the HLA profile at the CLI boundary; the promotion logic is generic."""
    from hla_lab.corpus.hla_semantic import load_hla_document_model

    return load_hla_document_model(root)


def promote_requirement(
    root: Path,
    candidate_id: str,
    *,
    model: DocumentModel | None = None,
    transition_ids: tuple[str, ...] = (),
    coverage_kind: str = "transition",
    coverage_note: str = "",
    relation: RequirementLinkRelation = "governs",
    notes: str = "",
    dry_run: bool = False,
) -> Requirement:
    """Promote one candidate and validate the complete reciprocal relationship.

    The caller supplies a typed model when using a non-HLA source adapter. The
    command-line entry point supplies the HLA adapter only at its boundary.
    """
    root = root.resolve()
    model = model or _load_hla_model(root)
    candidates = {item.id: item for item in model.requirements if item.extraction == "candidate"}
    candidate = candidates.get(candidate_id)
    if candidate is None:
        if any(item.id == candidate_id for item in model.requirements):
            raise ValueError(f"requirement is already explicit: {candidate_id}")
        raise ValueError(f"candidate requirement not found: {candidate_id}")
    if coverage_kind == "transition" and not transition_ids:
        raise ValueError("transition coverage requires at least one --transition")
    if coverage_kind != "transition" and transition_ids:
        raise ValueError("non-transition coverage cannot name --transition")
    if coverage_kind != "transition" and not coverage_note.strip():
        raise ValueError("non-transition coverage requires --coverage-note")

    all_transitions = {
        transition.id for machine in model.state_machines for transition in machine.transitions
    }
    missing_transitions = set(transition_ids) - all_transitions
    if missing_transitions:
        raise ValueError(f"unknown transition(s): {sorted(missing_transitions)}")

    requirement_payload = candidate.model_dump(mode="json")
    requirement_payload.update(
        {
            "extraction": "explicit",
            "transition_ids": list(transition_ids),
            "coverage_kind": coverage_kind,
            "coverage_note": coverage_note,
        }
    )
    promoted = Requirement.model_validate(requirement_payload)

    requirements_path = DocumentResources(root).semantic_file("requirements.json")
    requirement_file = RequirementFile.model_validate(
        _json_payload(requirements_path, {"schema_version": 1, "requirements": []})
    )
    if any(item.id == promoted.id for item in requirement_file.requirements):
        raise ValueError(f"requirement source already contains ID: {promoted.id}")
    requirements = (*requirement_file.requirements, promoted)

    links_path = DocumentResources(root).semantic_file("requirement-links.json")
    link_file = RequirementLinkFile.model_validate(
        _json_payload(links_path, {"schema_version": 1, "links": []})
    )
    existing_pairs = {(item.requirement_id, item.transition_id) for item in link_file.links}
    new_links: list[RequirementLink] = []
    for transition_id in transition_ids:
        if (promoted.id, transition_id) in existing_pairs:
            raise ValueError(
                f"requirement-to-transition link already exists: {promoted.id} -> {transition_id}"
            )
        new_links.append(
            RequirementLink(
                id=f"link-{slugify(promoted.id)}-{slugify(transition_id)}",
                requirement_id=promoted.id,
                transition_id=transition_id,
                relation=relation,
                source=promoted.source,
                notes=notes or "Promoted by the semantic requirement coverage workflow.",
            )
        )
    links = (*link_file.links, *new_links)

    state_payloads = _load_state_machine_payloads(root)
    touched_transition_ids: set[str] = set()
    updated_state_machines = []
    for machine in model.state_machines:
        updated_transitions = []
        for transition in machine.transitions:
            if transition.id in transition_ids:
                touched_transition_ids.add(transition.id)
                updated_transitions.append(
                    transition.model_copy(
                        update={
                            "requirement_ids": tuple(
                                dict.fromkeys((*transition.requirement_ids, promoted.id))
                            )
                        }
                    )
                )
            else:
                updated_transitions.append(transition)
        updated_state_machines.append(
            machine.model_copy(update={"transitions": tuple(updated_transitions)})
        )
    if touched_transition_ids != set(transition_ids):
        raise ValueError(
            "transition IDs were validated but not found in canonical state-machine records: "
            f"{sorted(set(transition_ids) - touched_transition_ids)}"
        )

    updated_model = model.model_copy(
        update={
            "requirements": tuple(
                promoted if item.id == candidate.id else item for item in model.requirements
            ),
            "requirement_links": links,
            "state_machines": tuple(updated_state_machines),
        }
    )
    DocumentModel.model_validate(updated_model.model_dump(mode="json"))

    if not dry_run:
        _write_json(
            requirements_path,
            RequirementFile(
                schema_version=requirement_file.schema_version,
                requirements=requirements,
            ).model_dump(mode="json"),
        )
        if new_links:
            _write_json(
                links_path,
                RequirementLinkFile(
                    schema_version=link_file.schema_version,
                    links=links,
                ).model_dump(mode="json"),
            )
        if transition_ids:
            for path, payload, _ in state_payloads:
                changed = False
                state_machines = payload.get("state_machines", [])
                if not isinstance(state_machines, list):
                    continue
                for machine_payload in state_machines:
                    if not isinstance(machine_payload, dict):
                        continue
                    transitions = machine_payload.get("transitions", [])
                    if not isinstance(transitions, list):
                        continue
                    for transition_payload in transitions:
                        if not isinstance(transition_payload, dict):
                            continue
                        if transition_payload.get("id") not in transition_ids:
                            continue
                        raw_ids = transition_payload.get("requirement_ids", [])
                        ids = list(raw_ids) if isinstance(raw_ids, list) else []
                        if promoted.id not in ids:
                            ids.append(promoted.id)
                            transition_payload["requirement_ids"] = ids
                            changed = True
                if changed:
                    _write_json(path, payload)
    return promoted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="One document source directory")
    parser.add_argument("candidate_id", help="Candidate requirement ID to promote")
    parser.add_argument(
        "--transition",
        dest="transition_ids",
        action="append",
        default=[],
        help="Reviewed transition ID; repeat for multiple transitions",
    )
    parser.add_argument(
        "--coverage-kind",
        choices=("transition", "cross-cutting", "document-wide", "not-applicable"),
        default="transition",
    )
    parser.add_argument("--coverage-note", default="")
    parser.add_argument(
        "--relation",
        choices=("governs", "precondition", "postcondition", "enables", "prohibits"),
        default="governs",
    )
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the promotion without modifying semantic source files",
    )
    args = parser.parse_args()
    promoted = promote_requirement(
        args.root,
        args.candidate_id,
        transition_ids=tuple(args.transition_ids),
        coverage_kind=args.coverage_kind,
        coverage_note=args.coverage_note,
        relation=args.relation,
        notes=args.notes,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "document": args.root.resolve().as_posix(),
                "promoted": promoted.id,
                "coverage_kind": promoted.coverage_kind,
                "transition_ids": list(promoted.transition_ids),
                "written": not args.dry_run,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
