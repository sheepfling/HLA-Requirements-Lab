"""Promote the 2010 requirement corpus with conservative coverage seams.

The source extractor is intentionally broad.  Promotion records that fact as
explicit source-derived statements, keeps unmatched statements clause-scoped,
and creates planned implementation seams only for modeled 1516.1 transitions.
No planned seam is presented as concrete implementation evidence.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE, HLA_SOURCE_2010
from hla_lab.core.io import write_json
from hla_lab.core.semantic_model import (
    ImplementationFile,
    ImplementationMapping,
    RequirementFile,
    RequirementLink,
    RequirementLinkFile,
    RequirementReviewFile,
    TransitionCoverage,
    TransitionCoverageFile,
    load_document_model,
)
from hla_lab.core.text import slugify
from hla_lab.paths import DocumentResources, RESOURCES

ROOTS = (
    RESOURCES.document("hla-1516-2010").root,
    RESOURCES.document("hla-1516.1-2010").root,
    RESOURCES.document("hla-1516.2-2010").root,
)

STOP_TERMS = {
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

def _terms(value: str) -> frozenset[str]:
    return frozenset(
        term
        for term in re.findall(r"[a-z][a-z0-9]{2,}", value.casefold())
        if term not in STOP_TERMS
    )

_write = write_json

def _figure_clause(machine_id: str) -> str | None:
    match = re.search(r"figure-(\d+)$", machine_id)
    if not match:
        return None
    figure = int(match.group(1))
    if figure <= 9:
        return "clause-4"
    if figure <= 13:
        return "clause-5"
    if figure <= 15:
        return "clause-6"
    if figure == 16:
        return "clause-7"
    if figure == 17:
        return "clause-8"
    if figure == 18:
        return "clause-9"
    return "clause-11"

def _same_clause(requirement_clause: str | None, transition_clause: str | None) -> bool:
    if not requirement_clause or not transition_clause:
        return False
    return requirement_clause == transition_clause or requirement_clause.startswith(
        f"{transition_clause}."
    )

def _matches(requirements: tuple[object, ...], transition: object) -> tuple[str, ...]:
    clause_id = getattr(transition, "clause_id", None)
    event_terms = _terms(
        " ".join(
            str(getattr(transition, field, ""))
            for field in ("event", "guard", "action", "precondition", "postcondition")
        )
    )
    if len(event_terms) < 2:
        return ()
    scored: list[tuple[int, object]] = []
    for requirement in requirements:
        if not _same_clause(getattr(requirement, "clause_id", None), clause_id):
            continue
        score = len(event_terms & _terms(str(getattr(requirement, "statement", ""))))
        if score >= 2:
            scored.append((score, requirement))
    if not scored:
        return ()
    best = max(score for score, _ in scored)
    winners = [requirement for score, requirement in scored if score == best]
    return tuple(requirement.id for requirement in winners) if len(winners) <= 3 else ()

def _update_machines(
    root: Path, updates: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]]
) -> None:
    for path in sorted(DocumentResources(root).semantic.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "state_machines" not in raw:
            continue
        changed = False
        for machine in raw["state_machines"]:
            machine_clause = _figure_clause(str(machine.get("id", "")))
            if machine.get("clause_id") != machine_clause:
                machine["clause_id"] = machine_clause
                changed = True
            for transition in machine.get("transitions", []):
                transition_id = str(transition.get("id", ""))
                if transition_id not in updates:
                    continue
                clause_id, requirement_ids, implementation_ids = updates[transition_id]
                values = {
                    "clause_id": clause_id,
                    "requirement_ids": list(requirement_ids),
                    "implementation_ids": list(implementation_ids),
                }
                for key, value in values.items():
                    if transition.get(key) != value:
                        transition[key] = value
                        changed = True
        if changed:
            _write(path, raw)

def _promote(root: Path) -> dict[str, int]:
    profile = HLA_SOURCE_2010 if root.name == "hla-1516.1-2010" else HLA_SOURCE
    model = load_document_model(root, profile)
    candidates = tuple(item for item in model.requirements if item.extraction == "candidate")
    transitions = tuple(
        transition for machine in model.state_machines for transition in machine.transitions
    )
    transition_by_id = {transition.id: transition for transition in transitions}
    links_by_pair: dict[tuple[str, str], RequirementLink] = {}
    matches_by_transition: dict[str, tuple[str, ...]] = {}
    for transition in transitions:
        clause_id = next(
            (
                _figure_clause(machine.id)
                for machine in model.state_machines
                if transition in machine.transitions
            ),
            None,
        )
        transition = transition.model_copy(update={"clause_id": clause_id})
        matches = _matches(candidates, transition)
        matches_by_transition[transition.id] = matches
        for requirement_id in matches:
            requirement = next(item for item in candidates if item.id == requirement_id)
            links_by_pair[(requirement_id, transition.id)] = RequirementLink(
                id=f"m2010.link.{slugify(requirement_id, fallback='transition')}."
                   f"{slugify(transition.id, fallback='transition')}",
                requirement_id=requirement_id,
                transition_id=transition.id,
                relation="governs",
                source=requirement.source,
                notes="Conservative same-clause event-term relationship for 2010 source review.",
            )

    promoted = []
    for candidate in candidates:
        transition_ids = tuple(
            transition_id
            for transition_id, requirement_ids in matches_by_transition.items()
            if candidate.id in requirement_ids
        )
        coverage_kind = "transition" if transition_ids else "cross-cutting"
        note = (
            "Direct same-clause event terminology match to modeled transition(s); "
            "implementation maturity is tracked separately."
            if transition_ids
            else (
                "Source-derived normative statement retained at clause scope; "
                "no modeled state transition was asserted."
            )
        )
        promoted.append(
            candidate.model_copy(
                update={
                    "title": candidate.title.replace("Normative candidate", "Normative statement"),
                    "transition_ids": transition_ids,
                    "coverage_kind": coverage_kind,
                    "coverage_note": note,
                    "extraction": "explicit",
                    "semantic_group_id": (
                        f"m2010.clause.{candidate.clause_id.removeprefix('clause-')}"
                        if candidate.clause_id
                        else "m2010.unclassified"
                    ),
                }
            )
        )

    implementations: list[ImplementationMapping] = []
    implementation_ids_by_transition: dict[str, tuple[str, ...]] = {}
    for transition in transitions:
        implementation_id = f"m2010.transition.{slugify(transition.id, fallback='transition')}"
        implementation_ids_by_transition[transition.id] = (implementation_id,)
        event = str(transition.event).strip()
        implementations.append(
            ImplementationMapping(
                id=implementation_id,
                interface_kind="callback"
                if ("rti" in event.casefold() or "†" in event)
                else "service",
                interface_name=event or f"Transition {transition.id}",
                implementation=(f"planned.hla2010.{slugify(transition.id, fallback='transition')}"),
                status="planned",
                clause_ids=(transition.clause_id,) if transition.clause_id else (),
                requirement_ids=matches_by_transition.get(transition.id, ()),
                transition_ids=(transition.id,),
                source=transition.source,
                notes=(
                    "Planned RTI/federate integration seam; replace with concrete "
                    "evidence when implemented."
                ),
            )
        )

    updates = {
        transition_id: (
            _figure_clause(
                next(
                    machine.id
                    for machine in model.state_machines
                    if transition_id in {item.id for item in machine.transitions}
                )
            ),
            matches_by_transition.get(transition_id, ()),
            implementation_ids_by_transition.get(transition_id, ()),
        )
        for transition_id in transition_by_id
    }
    _update_machines(root, updates)
    semantic = DocumentResources(root).semantic
    _write(
        semantic / "requirements.json",
        RequirementFile(schema_version=1, requirements=tuple(promoted)).model_dump(mode="json"),
    )
    _write(
        semantic / "requirement-review.json",
        RequirementReviewFile(schema_version=1, reviews=()).model_dump(mode="json"),
    )
    _write(
        semantic / "requirement-links.json",
        RequirementLinkFile(schema_version=1, links=tuple(links_by_pair.values())).model_dump(
            mode="json"
        ),
    )
    _write(
        semantic / "implementations.json",
        ImplementationFile(schema_version=1, implementations=tuple(implementations)).model_dump(
            mode="json"
        ),
    )
    _write(
        semantic / "transition-coverage.json",
        TransitionCoverageFile(
            schema_version=1,
            transition_coverage=tuple(
                TransitionCoverage(
                    transition_id=transition.id,
                    status="mapped",
                    implementation_ids=implementation_ids_by_transition[transition.id],
                    reason=(
                        "Planned implementation seam exists; concrete implementation "
                        "evidence remains separate."
                    ),
                    source=transition.source,
                )
                for transition in transitions
            ),
        ).model_dump(mode="json"),
    )
    return {
        "requirements": len(promoted),
        "transitions": len(transitions),
        "links": len(links_by_pair),
        "planned_implementations": len(implementations),
    }

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=ROOTS)
    args = parser.parse_args()
    for root in args.roots:
        print(root, _promote(root))

if __name__ == "__main__":
    main()
