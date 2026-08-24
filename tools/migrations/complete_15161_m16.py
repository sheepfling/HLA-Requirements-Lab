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
    RequirementApiBindingFile,
    RequirementFile,
    RequirementLink,
    RequirementLinkFile,
    RequirementReviewFile,
    SourceRef,
    TransitionCoverage,
    TransitionCoverageFile,
    _load_requirement_candidates,
)
from hla_lab.core.text import slugify
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import RESOURCES, DocumentResources

ROOT = RESOURCES.document("hla-1516.1-2025").root

# These are source-coordinate corrections from the authoritative source review.
# handoff.  Candidate IDs remain immutable; only the checker-visible clause
# owner and its derived semantic group move to the active service/section.
_SOURCE_CLAUSE_OVERRIDES: dict[tuple[str, int], str] = {
    **{
        ("content/clauses/06-object-management-page-112.tex", line): "6.1.12"
        for line in (48, 51, 66)
    },
    ("content/clauses/07-ownership-management-page-150.tex", 152): "7.1.2.1",
    ("content/clauses/07-ownership-management-page-154.tex", 66): "7.1.4",
    **{
        ("content/clauses/07-ownership-management-page-157.tex", line): "7.4"
        for line in (79, 103)
    },
    **{
        ("content/clauses/07-ownership-management-page-162.tex", line): "7.8"
        for line in (16, 22, 28, 34, 43, 52, 58, 64, 76)
    },
    ("content/clauses/07-ownership-management-page-163.tex", 24): "7.8.4",
    **{
        ("content/clauses/07-ownership-management-page-166.tex", line): "7.11"
        for line in (14, 20, 41)
    },
    **{
        ("content/clauses/07-ownership-management-page-167.tex", line): "7.12"
        for line in (13, 28)
    },
    **{
        ("content/clauses/07-ownership-management-page-168.tex", line): "7.13"
        for line in (23, 35, 38, 44)
    },
    **{
        ("content/clauses/07-ownership-management-page-170.tex", line): "7.15"
        for line in (13, 16, 19, 25, 34, 46, 52)
    },
    **{
        ("content/clauses/07-ownership-management-page-171.tex", line): "7.16"
        for line in (46, 52)
    },
    ("content/clauses/10-support-services-page-252.tex", 17): "10.12",
    ("content/clauses/10-support-services-page-264.tex", 133): "10.29",
    ("content/clauses/10-support-services-page-265.tex", 45): "10.30",
    ("content/clauses/10-support-services-page-265.tex", 150): "10.31",
    ("content/clauses/10-support-services-page-266.tex", 95): "10.32",
    ("content/clauses/10-support-services-page-267.tex", 39): "10.33",
    **{
        ("content/clauses/10-support-services-page-277.tex", line): "10.47"
        for line in (28, 31, 37)
    },
    **{
        ("content/clauses/11-management-object-model-page-292.tex", line): "11.5"
        for line in (9, 18, 21, 24, 30, 57)
    },
    ("content/clauses/05-declaration-management-page-090.tex", 79): "5.2",
    **{
        ("content/clauses/05-declaration-management-page-091.tex", line): "5.3"
        for line in (121, 127)
    },
    ("content/clauses/05-declaration-management-page-093.tex", 17): "5.4",
    ("content/clauses/05-declaration-management-page-093.tex", 140): "5.5",
    **{
        ("content/clauses/05-declaration-management-page-097.tex", line): "5.8"
        for line in (20, 23, 26)
    },
    ("content/clauses/05-declaration-management-page-099.tex", 75): "5.10",
    ("content/clauses/05-declaration-management-page-100.tex", 129): "5.11",
    **{
        ("content/clauses/05-declaration-management-page-102.tex", line): "5.12"
        for line in (10, 19)
    },
    ("content/clauses/05-declaration-management-page-103.tex", 108): "5.13",
    **{
        ("content/clauses/04-federation-management-page-067.tex", line): "4.20"
        for line in (37, 40)
    },
    **{
        ("content/clauses/04-federation-management-page-068.tex", line): "4.22"
        for line in (115, 118)
    },
    **{
        ("content/clauses/04-federation-management-page-069.tex", line): "4.23"
        for line in (64, 67, 70, 76, 133)
    },
    **{
        ("content/clauses/04-federation-management-page-072.tex", line): "4.26"
        for line in (17, 20, 23, 26)
    },
    **{
        ("content/clauses/04-federation-management-page-072.tex", line): "4.27"
        for line in (131, 134, 137)
    },
    **{
        ("content/clauses/04-federation-management-page-074.tex", line): "4.29"
        for line in (112, 115, 124)
    },
    **{
        ("content/clauses/04-federation-management-page-075.tex", line): "4.30"
        for line in (44, 47)
    },
    ("content/clauses/04-federation-management-page-076.tex", 15): "4.31",
    **{
        ("content/clauses/04-federation-management-page-078.tex", line): "4.33"
        for line in (20, 29)
    },
    **{
        ("content/clauses/06-object-management-page-113.tex", line): "6.2"
        for line in (21, 24)
    },
    **{
        ("content/clauses/06-object-management-page-137.tex", line): "6.22"
        for line in (40, 43)
    },
}

# Granular source facts that are present in the faithful 2025 layout but were
# not emitted as standalone candidates by the original page extractor.  These
# are source-owned records, not inferred implementation behavior.
_SOURCE_REQUIREMENT_REFINEMENTS: tuple[tuple[str, str, int, int, str, str, str], ...] = (
    (
        "send-interaction-published-class",
        "content/clauses/05-declaration-management-page-084.tex",
        9,
        12,
        "5.1.3",
        "Send Interaction published-class precondition",
        (
            "Joined federates may invoke the Send Interaction service only with a published "
            "interaction class as an argument."
        ),
    ),
    (
        "available-attribute-declaration",
        "content/clauses/05-declaration-management-page-082.tex",
        45,
        54,
        "5.1.2",
        "Available-attribute declaration constraint",
        (
            "A class attribute may be used as an argument to Subscribe Object Class Attributes, "
            "Unsubscribe Object Class Attributes, Publish Object Class Attributes, and "
            "Unpublish Object Class Attributes service invocations for a particular object class "
            "if and only if the attribute is an available attribute of that object class."
        ),
    ),
    (
        "unpublication-pending-acquisition",
        "content/clauses/05-declaration-management-page-092.tex",
        26,
        62,
        "5.3.3",
        "Unpublication pending-acquisition guard",
        (
            "For each class attribute that is published by the joined federate and is to be "
            "unpublished, there shall be no joined federate-owned corresponding instance "
            "attributes that are unowned by this joined federate and for which the joined "
            "federate has taken a pending ownership-acquisition action."
        ),
    ),
    (
        "directed-interaction-ownership-delivery",
        "content/clauses/05-declaration-management-page-101.tex",
        87,
        93,
        "5.12",
        "Directed interaction ownership delivery predicate",
        (
            "If the optional universal subscription indicator is not present or indicates "
            "subscription by ownership, directed interactions are only delivered for target "
            "object instances for which the joined federate owns at least one attribute."
        ),
    ),
    (
        "directed-interaction-universal-delivery",
        "content/clauses/05-declaration-management-page-101.tex",
        99,
        102,
        "5.12",
        "Directed interaction universal delivery predicate",
        (
            "If the optional universal subscription indicator indicates universal subscription, "
            "directed interactions are delivered for all object instances that are known to the "
            "joined federate."
        ),
    ),
    (
        "passive-subscription-delivery",
        "content/clauses/03-definitions-page-030.tex",
        22,
        27,
        "3",
        "Passive subscription delivery semantics",
        (
            "Unlike an active subscription, a passive subscription is not used by the RTI to "
            "arrange for data to be delivered or to tell publishing joined federates that "
            "another joined federate is subscribing to that data."
        ),
    ),
    (
        "relaxed-ddm-overlap",
        "content/clauses/09-data-distribution-management-page-221.tex",
        75,
        84,
        "9.1.4",
        "Allow Relaxed DDM overlap condition",
        (
            "Region overlap may be expanded when the Allow Relaxed DDM switch is enabled and "
            "the RTI implementation determines, based on implementation-specific criteria, "
            "that the ranges are sufficiently close; neither range may ever be reduced."
        ),
    ),
    (
        "relaxed-ddm-delivery",
        "content/clauses/09-data-distribution-management-page-225.tex",
        109,
        115,
        "9.1.8",
        "Allow Relaxed DDM delivery effect",
        (
            "The Allow Relaxed DDM Switch indicates whether the RTI implementation of DDM may "
            "deliver updates and interactions to an appropriately subscribed federate where "
            "subscription and update regions do not strictly overlap."
        ),
    ),
    (
        "relaxed-ddm-advisory",
        "content/clauses/09-data-distribution-management-page-226.tex",
        25,
        34,
        "9.1.8",
        "Allow Relaxed DDM advisory effect",
        (
            "The Allow Relaxed DDM switch may relax filtering of updates and interactions a "
            "federate may receive and may alter the invocation of the Attributes In Scope, "
            "Attributes Out Of Scope, Turn Updates On For Object Instance, and Turn Updates "
            "Off For Object Instance advisories."
        ),
    ),
    (
        "mom-object-class-relevance",
        "content/clauses/11-management-object-model-page-343.tex",
        105,
        108,
        "11.6",
        "MOM Object Class Relevance Switch effect",
        "Set the joined federate's Object Class Relevance Switch to the provided value.",
    ),
    (
        "mom-attribute-relevance",
        "content/clauses/11-management-object-model-page-343.tex",
        114,
        117,
        "11.6",
        "MOM Attribute Relevance Switch effect",
        "Set the joined federate's Attribute Relevance Switch to the provided value.",
    ),
    (
        "mom-attribute-scope",
        "content/clauses/11-management-object-model-page-343.tex",
        123,
        126,
        "11.6",
        "MOM Attribute Scope Switch effect",
        "Set the joined federate's Attribute Scope Switch to the provided value.",
    ),
    (
        "mom-interaction-relevance",
        "content/clauses/11-management-object-model-page-343.tex",
        132,
        135,
        "11.6",
        "MOM Interaction Relevance Switch effect",
        "Set the joined federate's Interaction Relevance Switch to the provided value.",
    ),
    (
        "mom-convey-region-designators",
        "content/clauses/11-management-object-model-page-343.tex",
        141,
        144,
        "11.6",
        "MOM Convey Region Designator Sets Switch effect",
        "Set the joined federate's Convey Region Designator Sets Switch to the provided value.",
    ),
    (
        "mom-automatic-resign-directive",
        "content/clauses/11-management-object-model-page-343.tex",
        150,
        153,
        "11.6",
        "MOM Automatic Resign Directive Switch effect",
        "Set the joined federate's Automatic Resign Directive Switch to the provided value.",
    ),
    (
        "mom-service-reporting",
        "content/clauses/11-management-object-model-page-343.tex",
        159,
        162,
        "11.6",
        "MOM service reporting switch effect",
        "Set the joined federate's service reporting switch to the provided value.",
    ),
    (
        "mom-exception-reporting",
        "content/clauses/11-management-object-model-page-344.tex",
        33,
        36,
        "11.6",
        "MOM exception reporting switch effect",
        "Set the joined federate's exception reporting switch to the provided value.",
    ),
    (
        "mom-service-report-file",
        "content/clauses/11-management-object-model-page-344.tex",
        57,
        60,
        "11.6",
        "MOM service-report file switch effect",
        "Set the joined federate's Send Service Reports to File Switch to the provided value.",
    ),
    (
        "time-constrained-save-boundary",
        "content/clauses/04-federation-management-page-067.tex",
        37,
        48,
        "4.20",
        "Time-constrained federate-save admission and pause boundary",
        (
            "A time-constrained joined federate shall expect Initiate Federate Save only "
            "while it is Time Advancing, shall stop providing new information immediately "
            "after that invocation, and may resume only after Federation Saved."
        ),
    ),
    (
        "connection-loss-automatic-resign",
        "content/clauses/04-federation-management-page-050.tex",
        36,
        46,
        "4",
        "Connection-loss automatic-resign and federation continuation",
        (
            "After reporting lost federates, the RTI shall perform a resign on behalf of "
            "each lost federate using its Automatic Resign Directive; federation-wide "
            "synchronized operations shall continue with remaining joined federates as if "
            "the lost federates had resigned, and MOM data and advisories shall reflect the "
            "new state."
        ),
    ),
    (
        "guard-and-cross-machine-state-constraints",
        "content/clauses/04-federation-management-page-041.tex",
        1,
        68,
        "4",
        "Joined-federate guard and cross-machine state constraints",
        (
            "State-machine guards enable transitions when their assertions become true; a "
            "guard-only transition occurs immediately when its guard is true, and the "
            "parallel joined-federate machines constrain one another, including the Active "
            "and Normal Activity Permitted relationship and save admission states."
        ),
    ),
    (
        "service-exception-precedence",
        "content/clauses/01-overview-page-020.tex",
        15,
        23,
        "1",
        "Service-exception precedence",
        (
            "Service exceptions are listed in increasing precedence; when multiple exception "
            "conditions are met simultaneously, the RTI shall throw the exception appearing "
            "later in the list."
        ),
    ),
    (
        "object-state-completeness",
        "content/clauses/01-overview-page-017.tex",
        64,
        68,
        "1",
        "Federation-visible object-instance state completeness",
        (
            "The complete set of attribute values for an object instance defines its state "
            "from the federation perspective; additional non-communicated state held by a "
            "federate is outside the HLA FOM."
        ),
    ),
)

# A page-local lookup must still expose the requirements owned by the
# service whose description continues onto that page.  These are deliberately
# explicit rather than inferred from page adjacency: the next page can begin
# a different service before its first normative statement.
_SOURCE_CONTINUATION_LINKS: dict[str, tuple[str, ...]] = {
    "content/clauses/06-object-management-page-142.tex": (
        "requirement-candidate-content-clauses-06-object-management-page-141-l125-32",
        "requirement-candidate-content-clauses-06-object-management-page-141-l131-34",
        "requirement-candidate-content-clauses-06-object-management-page-141-l137-36",
        "requirement-candidate-content-clauses-06-object-management-page-141-l143-38",
    ),
    "content/clauses/06-object-management-page-143.tex": (
        "requirement-candidate-content-clauses-06-object-management-page-142-l173-48",
    ),
}


def _source_refinement_requirements() -> tuple[Requirement, ...]:
    """Build deterministic source-owned records for semantic source facts."""
    return tuple(
        Requirement(
            id=f"requirement-source-refinement-{refinement_id.casefold()}",
            title=title,
            statement=statement,
            kind="detailed",
            clause=clause,
            machine_statement=statement,
            coverage_kind="cross-cutting",
            coverage_note=(
                "Source refinement retained as an explicit semantic fact; the record "
                "preserves source traceability without asserting a state transition."
            ),
            api_surface_scope="cross-cutting",
            api_surface_note="The source fact is not itself a callable API mapping.",
            extraction="explicit",
            semantic_group_id=f"m16.clause.{clause}",
            source=SourceRef(path=path, line=line, end_line=end_line),
        )
        for refinement_id, path, line, end_line, clause, title, statement in (
            _SOURCE_REQUIREMENT_REFINEMENTS
        )
    )


def _table_row_text(value: str) -> str:
    """Normalize a Table 5 cell without turning layout punctuation into prose."""
    value = re.sub(r"\\[a-zA-Z]+(?:\{[^{}]*\})?", " ", value)
    value = value.replace("%", " ").replace("\\", " ")
    return re.sub(r"\s+", " ", value).strip(" ,")


def _table_5_row_requirements(model: object) -> tuple[Requirement, ...]:
    """Promote Table 5's typed rows as explicit, source-addressable candidates."""
    records: list[Requirement] = []
    tables = getattr(model, "tables", ())
    for table in tables:
        if getattr(table, "number", None) != "5":
            continue
        by_row: dict[int, list[object]] = defaultdict(list)
        for cell in table.cells:
            if cell.row is not None:
                by_row[cell.row].append(cell)
        start_rows: list[int] = []
        for row, cells in sorted(by_row.items()):
            type_cell = max(cells, key=lambda item: item.column if item.column is not None else -1)
            type_text = _table_row_text(type_cell.text)
            if type_text.casefold() in {"type", "(continued)", ""} or type_text in {"\\", ",", "]"}:
                continue
            if type_cell.column is None or type_cell.column < 6:
                continue
            start_rows.append(row)
        for ordinal, start_row in enumerate(start_rows, start=1):
            end_row = start_rows[ordinal] if ordinal < len(start_rows) else max(by_row) + 1
            row_cells = [cell for row in range(start_row, end_row) for cell in by_row.get(row, ())]
            if not row_cells:
                continue
            values_by_column: dict[int, list[str]] = defaultdict(list)
            for cell in row_cells:
                if cell.column is None:
                    continue
                value = _table_row_text(cell.text)
                if value and value not in {"\\", ",", "]"}:
                    values_by_column[cell.column].append(value)
            columns = sorted(values_by_column, reverse=True)
            if not columns:
                continue
            type_value = " ".join(dict.fromkeys(values_by_column[columns[0]]))
            encoding_value = (
                " ".join(dict.fromkeys(values_by_column[columns[1]]))
                if len(columns) > 1
                else ""
            )
            example_value = (
                " ".join(dict.fromkeys(values_by_column[columns[-1]]))
                if len(columns) > 2
                else ""
            )
            first_cell = min(row_cells, key=lambda item: item.source.line)
            last_line = max(cell.source.end_line or cell.source.line for cell in row_cells)
            page = table.id.rsplit("-p", 1)[-1]
            records.append(
                Requirement(
                    id=f"requirement-candidate-table-5-p{page}-r{ordinal:03d}",
                    title=f"Table 5 row: {type_value}",
                    statement=(
                        f"Table 5 defines the {type_value} row with encoding "
                        f"{encoding_value or 'unspecified'} and example "
                        f"{example_value or 'unspecified'}."
                    ),
                    kind="detailed",
                    clause="11.5.1",
                    machine_statement=(
                        f"Table 5 type {type_value}; encoding {encoding_value or 'unspecified'}; "
                        f"example {example_value or 'unspecified'}."
                    ),
                    coverage_kind="cross-cutting",
                    coverage_note=(
                        "Structured Table 5 row candidate; it records the wire-shape source "
                        "without promoting the example to a normative lexical rule."
                    ),
                    api_surface_scope="cross-cutting",
                    api_surface_note="Table structure is not itself a callable API mapping.",
                    extraction="explicit",
                    semantic_group_id="m16.table-5",
                    source=first_cell.source.model_copy(update={"end_line": last_line}),
                )
            )
    return tuple(records)


def _repair_requirement_record_links(root: Path) -> None:
    """Remove stale requirement IDs left by an earlier interrupted migration."""
    semantic_root = DocumentResources(root).semantic
    requirements_path = semantic_root / "requirements.json"
    if not requirements_path.is_file():
        return
    authored_requirements = RequirementFile.model_validate_json(
        requirements_path.read_text(encoding="utf-8")
    ).requirements
    candidate_ids = {item.id for item in _load_requirement_candidates(root, HLA_SOURCE)}
    valid_ids = candidate_ids | {
        item.id
        for item in authored_requirements
        if not item.id.startswith("requirement-candidate-")
    }

    content_blocks_path = semantic_root / "content-blocks.json"
    if content_blocks_path.is_file():
        payload = ContentBlockFile.model_validate_json(
            content_blocks_path.read_text(encoding="utf-8")
        )
        repaired = tuple(
            item.model_copy(
                update={
                    "record_ids": tuple(
                        record_id
                        for record_id in item.record_ids
                        if not record_id.startswith("requirement-") or record_id in valid_ids
                    )
                }
            )
            for item in payload.content_blocks
        )
        if repaired != payload.content_blocks:
            _write_json(
                content_blocks_path,
                ContentBlockFile(
                    schema_version=payload.schema_version,
                    content_blocks=repaired,
                ).model_dump(mode="json"),
            )

    content_elements_path = semantic_root / "content-elements.json"
    if content_elements_path.is_file():
        payload = ContentElementFile.model_validate_json(
            content_elements_path.read_text(encoding="utf-8")
        )
        repaired = tuple(
            item.model_copy(
                update={
                    "record_ids": tuple(
                        record_id
                        for record_id in item.record_ids
                        if not record_id.startswith("requirement-") or record_id in valid_ids
                    )
                }
            )
            for item in payload.content_elements
        )
        if repaired != payload.content_elements:
            _write_json(
                content_elements_path,
                ContentElementFile(
                    schema_version=payload.schema_version,
                    content_elements=repaired,
                ).model_dump(mode="json"),
            )

    links_path = semantic_root / "requirement-links.json"
    if links_path.is_file():
        payload = RequirementLinkFile.model_validate_json(
            links_path.read_text(encoding="utf-8")
        )
        repaired = tuple(item for item in payload.links if item.requirement_id in valid_ids)
        if repaired != payload.links:
            _write_json(
                links_path,
                RequirementLinkFile(
                    schema_version=payload.schema_version,
                    links=repaired,
                ).model_dump(mode="json"),
            )

    bindings_path = semantic_root / "api-requirement-bindings.json"
    if bindings_path.is_file():
        payload = RequirementApiBindingFile.model_validate_json(
            bindings_path.read_text(encoding="utf-8")
        )
        repaired = tuple(item for item in payload.bindings if item.requirement_id in valid_ids)
        if repaired != payload.bindings:
            _write_json(
                bindings_path,
                RequirementApiBindingFile(
                    schema_version=payload.schema_version,
                    bindings=repaired,
                ).model_dump(mode="json"),
            )

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
    _repair_requirement_record_links(root)
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
    candidate_ids = {item.id for item in candidates}
    authored = {
        item.id: item
        for item in model.requirements
        if item.extraction == "explicit"
        and (
            not item.id.startswith("requirement-candidate-")
            or item.id in candidate_ids
        )
    }
    source_refinements = (
        *_source_refinement_requirements(),
        *_table_5_row_requirements(model),
    )
    authored.update({item.id: item for item in source_refinements})
    # A completed migration can be run again. Reconcile the source-owned
    # metadata of already-promoted candidates before deciding which candidates
    # still need promotion. This keeps a source-heading/provenance correction
    # durable without disturbing reviewed coverage or implementation fields.
    for candidate in candidates:
        existing = authored.get(candidate.id)
        if existing is None:
            continue
        update = {
            "title": candidate.title.replace("Normative candidate", "Normative statement"),
            "statement": candidate.statement,
            "machine_statement": candidate.machine_statement,
            "source": candidate.source,
        }
        corrected_clause = _SOURCE_CLAUSE_OVERRIDES.get(
            (candidate.source.path, candidate.source.line)
        )
        if corrected_clause is not None:
            update.update(
                {
                    "clause": corrected_clause,
                    "clause_id": f"clause-{corrected_clause}",
                    "semantic_group_id": f"m16.clause.{corrected_clause}",
                }
            )
        authored[candidate.id] = existing.model_copy(
            update=update,
        )
    # Do not append source candidates that have already been promoted into the
    # authored requirement file.
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
    for path, requirement_ids in _SOURCE_CONTINUATION_LINKS.items():
        for requirement_id in requirement_ids:
            if requirement_id not in requirement_order:
                raise ValueError(
                    f"continuation link {requirement_id} is not present in the promoted model"
                )
            if requirement_id not in requirement_ids_by_path[path]:
                requirement_ids_by_path[path].append(requirement_id)
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
        non_requirement_ids = tuple(
            item for item in block.record_ids if not item.startswith("requirement-")
        )
        updated_blocks.append(
            block.model_copy(
                update={"record_ids": tuple(dict.fromkeys((*non_requirement_ids, *ids)))}
            )
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
        non_requirement_ids = tuple(
            item for item in element.record_ids if not item.startswith("requirement-")
        )
        updated_elements.append(
            element.model_copy(
                update={"record_ids": tuple(dict.fromkeys((*non_requirement_ids, *ids)))}
            )
        )
    _write_json(
        content_elements_path,
        ContentElementFile(
            schema_version=content_elements_payload.schema_version,
            content_elements=tuple(updated_elements),
        ).model_dump(mode="json"),
    )

    # Keep the API binding manifest synchronized with the expanded source
    # inventory.  Cross-cutting/table records receive explicit reviewed
    # ``no-api`` rows rather than disappearing from the traceability surface.
    binding_model = load_hla_document_model(root)
    binding_path = semantic_root / "api-requirement-bindings.json"
    binding_payload = RequirementApiBindingFile(
        schema_version=1,
        bindings=build_requirement_api_bindings(binding_model),
    )
    _write_json(binding_path, binding_payload.model_dump(mode="json"))

    # Validate the complete authored model after all reciprocal writes.
    final = load_hla_document_model(root)
    final.assert_compliance()
    return {
        "candidates_promoted": len(candidates),
        "source_refinements": len(source_refinements),
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
