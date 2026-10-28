"""Promote a source-shaped requirement candidate into reviewed semantic source."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Literal

from hla_lab.core.io import write_json
from hla_lab.core.semantic_diagram_types import SemanticDiagramFileEnvelope
from hla_lab.core.semantic_model import (
    DocumentModel,
    Requirement,
    RequirementFile,
    RequirementLink,
    RequirementLinkFile,
    StateMachine,
    StateMachineFile,
)
from hla_lab.core.text import slugify
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import DocumentResources

RequirementLinkRelation = Literal[
    "governs", "precondition", "postcondition", "enables", "prohibits"
]
CoverageKind = Literal["transition", "cross-cutting", "document-wide", "not-applicable"]


def _load_state_machine_payloads(
    root: Path,
) -> tuple[tuple[Path, StateMachineFile], ...]:
    payloads: list[tuple[Path, StateMachineFile]] = []
    for path in sorted(DocumentResources(root).semantic.glob("*.json")):
        source = path.read_text(encoding="utf-8")
        envelope = SemanticDiagramFileEnvelope.model_validate_json(source)
        if "state_machines" not in envelope.model_fields_set:
            continue
        if envelope.schema_version is None or envelope.state_machines is None:
            raise ValueError(
                f"{path}: state-machine model requires schema_version and state_machines"
            )
        payloads.append((path, StateMachineFile.model_validate_json(source)))
    return tuple(payloads)


_write_json = write_json


def _load_hla_model(root: Path) -> DocumentModel:
    """Load the HLA profile at the CLI boundary; the promotion logic is generic."""
    return load_hla_document_model(root)


def promote_requirement(
    root: Path,
    candidate_id: str,
    *,
    model: DocumentModel | None = None,
    transition_ids: tuple[str, ...] = (),
    coverage_kind: CoverageKind = "transition",
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
    candidate = _candidate_for_promotion(model, candidate_id)
    _validate_coverage(model, transition_ids, coverage_kind, coverage_note)
    promoted = _promoted_requirement(candidate, transition_ids, coverage_kind, coverage_note)
    requirement_path, requirement_file = _load_requirement_file(root, promoted)
    link_path, link_file, links, new_links = _load_requirement_links(
        root, promoted, transition_ids, relation, notes
    )
    state_payloads = _load_state_machine_payloads(root)
    updated_machines, touched = _updated_state_machine_records(model, transition_ids, promoted.id)
    _validate_touched_transitions(touched, transition_ids)
    _validated_updated_model(model, candidate, promoted, links, updated_machines)
    if not dry_run:
        _write_promotion(
            requirement_path,
            requirement_file,
            promoted,
            link_path,
            link_file,
            links,
            new_links,
            state_payloads,
            updated_machines,
        )
    return promoted


def _candidate_for_promotion(model: DocumentModel, candidate_id: str) -> Requirement:
    candidates = {item.id: item for item in model.requirements if item.extraction == "candidate"}
    candidate = candidates.get(candidate_id)
    if candidate is not None:
        return candidate
    if any(item.id == candidate_id for item in model.requirements):
        raise ValueError(f"requirement is already explicit: {candidate_id}")
    raise ValueError(f"candidate requirement not found: {candidate_id}")


def _validate_coverage(
    model: DocumentModel,
    transition_ids: Sequence[str],
    coverage_kind: CoverageKind,
    coverage_note: str,
) -> None:
    if coverage_kind == "transition" and not transition_ids:
        raise ValueError("transition coverage requires at least one --transition")
    if coverage_kind != "transition" and transition_ids:
        raise ValueError("non-transition coverage cannot name --transition")
    if coverage_kind != "transition" and not coverage_note.strip():
        raise ValueError("non-transition coverage requires --coverage-note")
    all_transitions = {
        transition.id for machine in model.state_machines for transition in machine.transitions
    }
    missing = set(transition_ids) - all_transitions
    if missing:
        raise ValueError(f"unknown transition(s): {sorted(missing)}")


def _promoted_requirement(
    candidate: Requirement,
    transition_ids: Sequence[str],
    coverage_kind: str,
    coverage_note: str,
) -> Requirement:
    payload = candidate.model_dump()
    payload.update(
        extraction="explicit",
        transition_ids=tuple(transition_ids),
        coverage_kind=coverage_kind,
        coverage_note=coverage_note,
    )
    return Requirement.model_validate(payload)


def _load_requirement_file(
    root: Path,
    promoted: Requirement,
) -> tuple[Path, RequirementFile]:
    path = DocumentResources(root).semantic_file("requirements.json")
    record = (
        RequirementFile.model_validate_json(path.read_text(encoding="utf-8"))
        if path.is_file()
        else RequirementFile(schema_version=1, requirements=())
    )
    if any(item.id == promoted.id for item in record.requirements):
        raise ValueError(f"requirement source already contains ID: {promoted.id}")
    return path, record


def _load_requirement_links(
    root: Path,
    promoted: Requirement,
    transition_ids: Sequence[str],
    relation: RequirementLinkRelation,
    notes: str,
) -> tuple[Path, RequirementLinkFile, tuple[RequirementLink, ...], tuple[RequirementLink, ...]]:
    path = DocumentResources(root).semantic_file("requirement-links.json")
    record = (
        RequirementLinkFile.model_validate_json(path.read_text(encoding="utf-8"))
        if path.is_file()
        else RequirementLinkFile(schema_version=1, links=())
    )
    existing = {(item.requirement_id, item.transition_id) for item in record.links}
    new_links: list[RequirementLink] = []
    for transition_id in transition_ids:
        if (promoted.id, transition_id) in existing:
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
    return path, record, (*record.links, *new_links), tuple(new_links)


def _updated_state_machine_records(
    model: DocumentModel,
    transition_ids: Sequence[str],
    requirement_id: str,
) -> tuple[tuple[StateMachine, ...], set[str]]:
    selected = set(transition_ids)
    touched: set[str] = set()
    machines: list[StateMachine] = []
    for machine in model.state_machines:
        transitions = []
        for transition in machine.transitions:
            if transition.id in selected:
                touched.add(transition.id)
                requirements = tuple(dict.fromkeys((*transition.requirement_ids, requirement_id)))
                transitions.append(transition.model_copy(update={"requirement_ids": requirements}))
            else:
                transitions.append(transition)
        machines.append(machine.model_copy(update={"transitions": tuple(transitions)}))
    return tuple(machines), touched


def _validate_touched_transitions(
    touched: AbstractSet[str],
    transition_ids: Sequence[str],
) -> None:
    expected = set(transition_ids)
    if touched != expected:
        raise ValueError(
            "transition IDs were validated but not found in canonical state-machine records: "
            f"{sorted(expected - touched)}"
        )


def _validated_updated_model(
    model: DocumentModel,
    candidate: Requirement,
    promoted: Requirement,
    links: Sequence[RequirementLink],
    machines: Sequence[StateMachine],
) -> DocumentModel:
    updated = model.model_copy(
        update={
            "requirements": tuple(
                promoted if item.id == candidate.id else item for item in model.requirements
            ),
            "requirement_links": tuple(links),
            "state_machines": tuple(machines),
        }
    )
    return DocumentModel.model_validate(updated.model_dump(mode="json"))


def _write_promotion(
    requirement_path: Path,
    requirement_file: RequirementFile,
    promoted: Requirement,
    link_path: Path,
    link_file: RequirementLinkFile,
    links: Sequence[RequirementLink],
    new_links: Sequence[RequirementLink],
    state_payloads: Sequence[tuple[Path, StateMachineFile]],
    updated_machines: Sequence[StateMachine],
) -> None:
    _write_json(
        requirement_path,
        RequirementFile(
            schema_version=requirement_file.schema_version,
            requirements=(*requirement_file.requirements, promoted),
        ),
    )
    if new_links:
        _write_json(
            link_path,
            RequirementLinkFile(
                schema_version=link_file.schema_version,
                links=tuple(links),
            ),
        )
    updated_by_id = {machine.id: machine for machine in updated_machines}
    for path, state_machine_file in state_payloads:
        machines = tuple(
            updated_by_id.get(machine.id, machine) for machine in state_machine_file.state_machines
        )
        if machines != state_machine_file.state_machines:
            _write_json(
                path,
                StateMachineFile(
                    schema_version=state_machine_file.schema_version,
                    state_machines=machines,
                ),
            )


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
