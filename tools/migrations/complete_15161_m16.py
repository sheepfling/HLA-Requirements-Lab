"""Close the IEEE 1516.1-2025 M16 semantic migration.

This migration is deliberately deterministic and conservative:

* every source-shaped ``shall`` candidate becomes an explicit, source-owned
  requirement record;
* only same-clause transition matches with unambiguous event terminology are
  linked directly to a requirement;
* every modeled transition receives an implementation seam, while the seam is
  marked ``planned`` rather than pretending that an RTI implementation exists;
* page content records receive the requirement IDs they own by provenance.

The resulting records are useful to compliance tooling without claiming more
semantic certainty or implementation maturity than the source supports.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.io import write_json
from hla_lab.core.semantic_model import (
    ContentBlockFile,
    ContentElementFile,
    ImplementationFile,
    ImplementationMapping,
    Requirement,
    RequirementFile,
    RequirementLink,
    RequirementLinkFile,
    RequirementReviewFile,
    TransitionCoverage,
    TransitionCoverageFile,
    _load_requirement_candidates,
)
from hla_lab.core.text import slugify
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import RESOURCES, DocumentResources

ROOT = RESOURCES.document("hla-1516.1-2025").root

_STOP_TERMS = {
    "about",
    "after",
    "again",
    "allow",
    "also",
    "and",
    "any",
    "are",
    "been",
    "before",
    "being",
    "between",
    "both",
    "each",
    "from",
    "have",
    "into",
    "must",
    "not",
    "once",
    "only",
    "onto",
    "over",
    "same",
    "shall",
    "should",
    "some",
    "state",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "used",
    "using",
    "when",
    "where",
    "which",
    "with",
    "within",
    "without",
    "would",
}


def _terms(text: str) -> frozenset[str]:
    """Return conservative content terms for deterministic event matching."""
    return frozenset(
        term
        for term in re.findall(r"[a-z][a-z0-9]{2,}", text.casefold())
        if term not in _STOP_TERMS
    )


def _transition_matches(
    requirements: tuple[Requirement, ...], transition: object
) -> tuple[str, ...]:
    """Match only clear, same-clause event terminology to requirements.

    Empty/diagram-only events intentionally do not acquire invented normative
    text. A match needs at least two non-stopword event terms and must be
    unambiguous within the transition's owning clause.
    """
    clause_id = getattr(transition, "clause_id", None)
    event_terms = _terms(
        " ".join(
            str(getattr(transition, field, ""))
            for field in ("event", "guard", "action", "precondition", "postcondition")
        )
    )
    if len(event_terms) < 2:
        return ()
    scored: list[tuple[int, Requirement]] = []
    for requirement in requirements:
        if requirement.clause_id != clause_id:
            continue
        score = len(event_terms & _terms(requirement.statement))
        if score >= 2:
            scored.append((score, requirement))
    if not scored:
        return ()
    best = max(score for score, _ in scored)
    winners = [requirement for score, requirement in scored if score == best]
    if len(winners) > 3:
        return ()
    return tuple(requirement.id for requirement in winners)


def _all_transitions(model: object) -> tuple[object, ...]:
    return tuple(
        transition for machine in model.state_machines for transition in machine.transitions
    )


_write_json = write_json


def _update_state_machine_sources(
    root: Path,
    transition_updates: dict[str, tuple[tuple[str, ...], tuple[str, ...]]],
) -> None:
    """Write only reciprocal requirement/implementation fields into machine JSON."""
    for path in sorted(DocumentResources(root).semantic.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "state_machines" not in raw:
            continue
        changed = False
        for machine in raw.get("state_machines", []):
            for transition in machine.get("transitions", []):
                transition_id = transition.get("id")
                if transition_id not in transition_updates:
                    continue
                requirement_ids, implementation_ids = transition_updates[transition_id]
                if transition.get("requirement_ids", []) != list(requirement_ids):
                    transition["requirement_ids"] = list(requirement_ids)
                    changed = True
                if transition.get("implementation_ids", []) != list(implementation_ids):
                    transition["implementation_ids"] = list(implementation_ids)
                    changed = True
        if changed:
            _write_json(path, raw)


def migrate(root: Path = ROOT) -> dict[str, int]:
    """Promote 1516.1 candidates and close its operational mappings."""
    model = load_hla_document_model(root)
    candidates = _load_requirement_candidates(root, HLA_SOURCE)
    content_blocks = ContentBlockFile.model_validate_json(
        DocumentResources(root).semantic_file("content-blocks.json").read_text(encoding="utf-8")
    ).content_blocks
    annex_by_path = {}
    for block in content_blocks:
        match = re.search(r"\\textbf\{Annex ([A-I])\}", block.layout_body or "")
        if match:
            annex_by_path[block.source.path] = match.group(1)
    candidates = tuple(
        candidate.model_copy(
            update={
                "clause": annex_by_path.get(candidate.source.path, candidate.clause),
                "clause_id": (
                    f"clause-{annex_by_path[candidate.source.path]}"
                    if candidate.source.path in annex_by_path
                    else candidate.clause_id
                ),
            }
        )
        for candidate in candidates
    )
    authored = {item.id: item for item in model.requirements if item.extraction == "explicit"}
    # A completed migration can be run again. Do not append source candidates
    # that have already been promoted into the authored requirement file.
    candidates = tuple(candidate for candidate in candidates if candidate.id not in authored)
    candidate_ids = {item.id for item in candidates}
    if len(candidate_ids) != len(candidates):
        raise ValueError("candidate extraction produced duplicate IDs")

    transitions = _all_transitions(model)
    requirement_order = {
        item.id: index for index, item in enumerate((*authored.values(), *candidates))
    }
    candidate_matches: dict[str, list[str]] = defaultdict(list)
    for transition in transitions:
        for requirement_id in _transition_matches(candidates, transition):
            candidate_matches[requirement_id].append(transition.id)
    # Rebuild the candidate records with explicit ownership and an honest
    # distinction between direct state links and clause-scoped requirements.
    promoted: list[Requirement] = list(authored.values())
    for candidate in candidates:
        transition_ids = tuple(candidate_matches.get(candidate.id, ()))
        if transition_ids:
            coverage_kind = "transition"
            coverage_note = (
                "Direct same-clause event terminology match to the modeled transition(s); "
                "the requirement remains source-derived and implementation maturity is "
                "tracked separately."
            )
        else:
            coverage_kind = "cross-cutting"
            coverage_note = (
                "Source-derived normative statement retained at clause scope; no modeled "
                "state transition was asserted by the conservative event matcher."
            )
        promoted.append(
            candidate.model_copy(
                update={
                    "title": candidate.title.replace("Normative candidate", "Normative statement"),
                    "transition_ids": transition_ids,
                    "coverage_kind": coverage_kind,
                    "coverage_note": coverage_note,
                    "extraction": "explicit",
                    "semantic_group_id": (
                        f"m16.clause.{candidate.clause_id.removeprefix('clause-')}"
                        if candidate.clause_id
                        else "m16.unclassified"
                    ),
                }
            )
        )
    promoted.sort(key=lambda item: (item.source.path, item.source.line, item.id))

    reqs_by_transition: dict[str, list[str]] = defaultdict(list)
    for requirement in promoted:
        for transition_id in requirement.transition_ids:
            reqs_by_transition[transition_id].append(requirement.id)
    for transition_id in reqs_by_transition:
        reqs_by_transition[transition_id].sort(key=lambda item: requirement_order.get(item, 0))

    existing_implementations = list(model.implementations)
    implementation_by_transition: dict[str, list[str]] = defaultdict(list)
    for implementation in existing_implementations:
        for transition_id in implementation.transition_ids:
            implementation_by_transition[transition_id].append(implementation.id)
    implementations = []
    for implementation in existing_implementations:
        transition_ids = implementation.transition_ids
        requirement_ids = tuple(
            requirement_id
            for transition_id in transition_ids
            for requirement_id in reqs_by_transition.get(transition_id, ())
        )
        requirement_ids = tuple(dict.fromkeys(requirement_ids))
        clause_ids = tuple(
            dict.fromkeys(
                (
                    *implementation.clause_ids,
                    *(
                        transition.clause_id
                        for transition in transitions
                        if transition.id in transition_ids and transition.clause_id
                    ),
                )
            )
        )
        implementations.append(
            implementation.model_copy(
                update={"requirement_ids": requirement_ids, "clause_ids": clause_ids}
            )
        )
    for transition in transitions:
        if implementation_by_transition.get(transition.id):
            continue
        implementation_id = f"m16.transition.{slugify(transition.id, fallback='transition')}"
        implementation_by_transition[transition.id].append(implementation_id)
        event = transition.event.strip()
        event_lower = event.casefold()
        if "†" in event or "callback" in event_lower or "rti" in event_lower:
            interface_kind = "callback"
        elif event:
            interface_kind = "service"
        else:
            interface_kind = "handler"
        implementations.append(
            ImplementationMapping(
                id=implementation_id,
                interface_kind=interface_kind,
                interface_name=event or f"Transition {transition.id}",
                implementation=f"planned.{slugify(transition.id, fallback='transition')}",
                status="planned",
                clause_ids=(transition.clause_id,) if transition.clause_id else (),
                requirement_ids=tuple(reqs_by_transition.get(transition.id, ())),
                transition_ids=(transition.id,),
                source=transition.source,
                notes=(
                    "M16 closure mapping: planned integration seam for the modeled "
                    "transition; replace with a concrete RTI/federate symbol when available."
                ),
            )
        )
    implementations.sort(
        key=lambda item: (
            item.transition_ids[0] if item.transition_ids else "",
            item.id,
        )
    )

    transition_updates: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for transition in transitions:
        requirement_ids = tuple(reqs_by_transition.get(transition.id, ()))
        implementation_ids = tuple(implementation_by_transition[transition.id])
        transition_updates[transition.id] = (requirement_ids, implementation_ids)

    links_by_pair = {
        (item.requirement_id, item.transition_id): item for item in model.requirement_links
    }
    for requirement in promoted:
        for transition_id in requirement.transition_ids:
            pair = (requirement.id, transition_id)
            links_by_pair.setdefault(
                pair,
                RequirementLink(
                    id=(
                        f"link.{slugify(requirement.id, fallback='transition')}."
                        f"{slugify(transition_id, fallback='transition')}"
                    ),
                    requirement_id=requirement.id,
                    transition_id=transition_id,
                    relation="governs",
                    source=requirement.source,
                    notes="M16 deterministic same-clause event-term relationship.",
                ),
            )
    links = sorted(
        links_by_pair.values(),
        key=lambda item: (
            requirement_order.get(item.requirement_id, 0),
            item.transition_id,
            item.id,
        ),
    )

    coverage = [
        TransitionCoverage(
            transition_id=transition.id,
            status="mapped",
            implementation_ids=transition_updates[transition.id][1],
            reason=(
                "Explicit planned implementation seam recorded for the modeled transition; "
                "the mapping is complete while concrete code remains a separate maturity step."
            ),
            source=transition.source,
        )
        for transition in transitions
    ]

    semantic_root = DocumentResources(root).semantic
    _write_json(
        semantic_root / "requirements.json",
        RequirementFile(schema_version=1, requirements=tuple(promoted)).model_dump(mode="json"),
    )
    _write_json(
        semantic_root / "requirement-review.json",
        RequirementReviewFile(schema_version=1, reviews=()).model_dump(mode="json"),
    )
    _write_json(
        semantic_root / "requirement-links.json",
        RequirementLinkFile(schema_version=1, links=tuple(links)).model_dump(mode="json"),
    )
    _write_json(
        semantic_root / "implementations.json",
        ImplementationFile(schema_version=1, implementations=tuple(implementations)).model_dump(
            mode="json"
        ),
    )
    _write_json(
        semantic_root / "transition-coverage.json",
        TransitionCoverageFile(schema_version=1, transition_coverage=tuple(coverage)).model_dump(
            mode="json"
        ),
    )
    _update_state_machine_sources(root, transition_updates)

    requirement_ids_by_path: dict[str, list[str]] = defaultdict(list)
    for requirement in promoted:
        requirement_ids_by_path[requirement.source.path].append(requirement.id)
    content_blocks_path = semantic_root / "content-blocks.json"
    content_blocks_payload = ContentBlockFile.model_validate_json(
        content_blocks_path.read_text(encoding="utf-8")
    )
    block_requirement_ids: dict[str, tuple[str, ...]] = {}
    updated_blocks = []
    for block in content_blocks_payload.content_blocks:
        if block.layout_body is None:
            updated_blocks.append(block)
            continue
        ids = tuple(
            sorted(
                requirement_ids_by_path.get(block.source.path, ()),
                key=lambda item: requirement_order.get(item, 0),
            )
        )
        block_requirement_ids[block.id] = ids
        updated_blocks.append(
            block.model_copy(update={"record_ids": tuple(dict.fromkeys((*block.record_ids, *ids)))})
        )
    _write_json(
        content_blocks_path,
        ContentBlockFile(
            schema_version=content_blocks_payload.schema_version,
            content_blocks=tuple(updated_blocks),
        ).model_dump(mode="json"),
    )

    content_elements_path = semantic_root / "content-elements.json"
    content_elements_payload = ContentElementFile.model_validate_json(
        content_elements_path.read_text(encoding="utf-8")
    )
    updated_elements = []
    for element in content_elements_payload.content_elements:
        ids = block_requirement_ids.get(element.block_id, ())
        updated_elements.append(
            element.model_copy(
                update={"record_ids": tuple(dict.fromkeys((*element.record_ids, *ids)))}
            )
        )
    _write_json(
        content_elements_path,
        ContentElementFile(
            schema_version=content_elements_payload.schema_version,
            content_elements=tuple(updated_elements),
        ).model_dump(mode="json"),
    )

    # Validate the complete authored model after all reciprocal writes.
    final = load_hla_document_model(root)
    final.assert_compliance()
    return {
        "candidates_promoted": len(candidates),
        "requirements": len(final.requirements),
        "requirement_links": len(final.requirement_links),
        "implementations": len(final.implementations),
        "transitions": sum(len(machine.transitions) for machine in final.state_machines),
        "mapped_transitions": final.transition_coverage_counts()["mapped"],
        "deferred_transitions": final.transition_coverage_counts()["deferred"],
        "deferred_requirements": final.requirement_review_counts()["deferred"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(migrate(args.root), indent=2))


if __name__ == "__main__":
    main()
