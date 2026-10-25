"""Apply reviewed 2025 HLA semantic corrections from implementation feedback.

This one-time migration edits the checked-in semantic catalog in place. It keeps
stable requirement IDs and does not regenerate the source bundle or its revision.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import cast

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.json_types import JsonObject, JsonValue
from hla_lab.core.semantic_model import load_document_model
from hla_lab.corpus.api_crosswalk import (
    build_requirement_api_bindings,
    write_requirement_api_bindings,
)
from hla_lab.corpus.hla_api_crosswalk import generate
from tools.migrations.backflow_clipped import repair_clipped_clause_statements
from tools.migrations.backflow_common import ROOT, SEMANTIC
from tools.migrations.backflow_content import (
    repair_page_192_service_narrative,
    repair_page_216,
    repair_page_219_region_relationships,
    repair_service_prose,
)
from tools.migrations.backflow_fragments import (
    repair_clause_boundaries,
    repair_contextual_fragments,
    repair_fragmented_statements,
    repair_local_fragments,
    repair_more_clause_boundaries,
    repair_remaining_section_continuations,
)
from tools.migrations.backflow_ownership import (
    repair_cross_page_statements,
    repair_ownership_overview,
    repair_time_order_and_acquisition,
)
from tools.migrations.backflow_tables import (
    repair_table_5_records,
    repair_time_table_and_caption,
    restore_missing_service_flow_candidates,
)


def rebuild_api_bindings() -> None:
    """Keep the authored manifest identical to the deterministic API crosswalk."""
    model = load_document_model(SEMANTIC.parent, HLA_SOURCE)
    write_requirement_api_bindings(
        SEMANTIC / "api-requirement-bindings.json",
        build_requirement_api_bindings(model),
    )


def rebuild_api_crosswalk() -> None:
    """Project every authored implementation mapping to every 2025 API target."""
    generate(SEMANTIC.parent, "2025", SEMANTIC / "api-crosswalk.json")


def _apply_resolution_notes(issues: MutableMapping[str, JsonObject]) -> None:
    issues["RL-248"]["resolution_note"] = (
        "Visible page-235/236 heading is §9.9.3, not the §9.5.3 suggested by the input ledger."
    )
    issues["RL-382"]["resolution_note"] = (
        "The visible §4.1.3 heading occurs after this text; §4.1.2 continues from page 43."
    )
    issues["RL-341"]["resolution_note"] = (
        "The source paragraph precedes §9.5.1 under the §9.5 service heading; the input ledger's "
        "§9.6 suggestion follows on page 230 and does not own this text."
    )
    issues["RL-357"]["resolution_note"] = (
        "The visible paragraph is within §4.8.1 Purpose/background, before §4.8.2."
    )
    issues["RL-360"]["resolution_note"] = (
        "The page contains 17 candidate records before the visible §9.1.3.3 heading; "
        "all 17 continue §9.1.3.2 from page 219."
    )
    issues["RL-359"]["verification"] = (
        "tests/test_hla_backflow.py::HlaBackflowTests::"
        "test_page_219_region_rules_precede_instance_attribute_heading"
    )
    issues["RL-359"]["resolution_note"] = (
        "Page-219 l50-16 now contains the complete Invalid region condition and belongs to "
        "§9.1.3.1. Its pending-effects continuation is complete in l62-20; the neighboring "
        "pre-heading candidates also retain §9.1.3.1 and complete statements."
    )
    issues["RL-362"]["verification"] = (
        "tests/test_hla_backflow.py::HlaBackflowTests::test_time_and_ddm_continuations"
    )
    issues["RL-362"]["resolution_note"] = (
        "All five affected candidates now belong to §8.6. The page-192 §8.6.1 heading begins "
        "after the service narrative; l93-27 and l99-29 also have complete statements."
    )
    for issue_id in ("RL-333", "RL-334"):
        issues[issue_id]["resolution_note"] = (
            "The complete page-192 statement occurs in the §8.6 service narrative before "
            "the visible §8.6.1 heading; the originating ledger's §8.6.3 attribution is too late."
        )
    for issue_id in ("RL-263", "RL-264"):
        issues[issue_id]["resolution_note"] = (
            "The repaired page-290 sentence precedes the visible §11.4.1 heading at line 88 "
            "and continues §11.3; the originating ledger's §11.4.1 attribution is too late."
        )
    issues["RL-386"]["resolution_note"] = (
        "The complete page-198 passage follows the visible §8.11 service heading; "
        "the §8.11.3 heading comes later on page 199."
    )
    issues["RL-265"]["resolution_note"] = (
        "The page-288 HLAfederate candidate belongs to the visible §11.2.1 subsection "
        "within the ledger's broader §11.2 section."
    )
    issues["RL-343"]["resolution_note"] = (
        "The affected page-204 rules belong to §8.14.4. The model stores the numbered "
        "subsection, while the ledger identifies its lettered item (d)."
    )
    issues["RL-381"]["resolution_note"] = (
        "All four stable IDs hold complete sentence-level facets and share the dedicated "
        "m16.range-definition.9.1.1 semantic group. Each has a coverage note requiring the "
        "four IDs to be mapped together before claiming the full semi-open range definition, "
        "bound order, strict upper-bound relation, and minimum unit span."
    )
    _apply_verification_notes(issues)
    boundary_check = (
        "tests/test_hla_backflow.py::HlaBackflowTests::"
        "test_corrected_candidates_have_complete_statement_boundaries"
    )
    for issue_id in (
        "RL-253",
        "RL-328",
        "RL-330",
        "RL-331",
        "RL-339",
        "RL-343",
        "RL-345",
        "RL-346",
        "RL-349",
        "RL-351",
        "RL-352",
        "RL-360",
        "RL-370",
    ):
        issue = issues[issue_id]
        if boundary_check not in issue["verification"]:
            issue["verification"] += f"; {boundary_check}"
        note = (
            "Affected clipped sentence boundaries were restored from the pinned semantic "
            "page layout."
        )
        current_note = str(issue.get("resolution_note", ""))
        if note not in current_note:
            issue["resolution_note"] = f"{current_note} {note}".strip()
    split_check = (
        "tests/test_hla_backflow.py::HlaBackflowTests::"
        "test_split_service_names_keep_the_full_condition"
    )
    for issue_id in ("RL-331", "RL-339", "RL-343"):
        issue = issues[issue_id]
        if split_check not in issue["verification"]:
            issue["verification"] += f"; {split_check}"


def _apply_verification_notes(issues: MutableMapping[str, JsonObject]) -> None:
    for issue in issues.values():
        if issue["category"] == "Clause, subsection, and source-boundary attribution":
            issue["verification"] = (
                "tests/test_hla_backflow.py::HlaBackflowTests::"
                "test_every_clause_complaint_has_reviewed_attribution"
            )
        elif issue["category"] == "Incomplete, fragmented, or corrupted candidate text":
            witness_check = (
                "tests/test_hla_backflow.py::HlaBackflowTests::"
                "test_every_fragment_complaint_retains_its_missing_rule"
            )
            if issue["verification"] == "tests/test_hla_backflow.py":
                issue["verification"] = witness_check
            elif witness_check not in issue["verification"]:
                issue["verification"] += f"; {witness_check}"
    issues["RL-256"]["verification"] = (
        "tests/test_hla_backflow.py::HlaBackflowTests::test_table_5_source_conflicts_"
        "remain_explicit"
    )
    issues["RL-256"]["resolution"] = "source-review-open"
    issues["RL-256"]["resolution_note"] = (
        "The candidate now states the clean ConfigurationResult field and message type while "
        "preserving the printed addtionalSettingsResultCode example spelling as a distinct "
        "unresolved source anomaly; the example is not treated as a lexical requirement."
    )
    table_verification = {
        "test_table_5_parent_rows_have_complete_shapes": ("RL-257", "RL-364"),
        "test_table_5_fragmented_children_keep_their_parent_type": (
            "RL-358",
            "RL-365",
            "RL-366",
            "RL-367",
            "RL-368",
        ),
        "test_time_table_and_caption": ("RL-312", "RL-387"),
    }
    for test_name, issue_group in table_verification.items():
        for issue_id in issue_group:
            issues[issue_id]["verification"] = (
                f"tests/test_hla_backflow.py::HlaBackflowTests::{test_name}"
            )
    source_check = (
        "tests/test_hla_backflow.py::HlaBackflowTests::"
        "test_table_5_sources_point_to_printed_values_and_examples"
    )
    for issue_id in (
        "RL-256",
        "RL-257",
        "RL-358",
        "RL-364",
        "RL-365",
        "RL-366",
        "RL-367",
        "RL-368",
        "RL-369",
    ):
        if source_check not in issues[issue_id]["verification"]:
            issues[issue_id]["verification"] += f"; {source_check}"
    for issue_id, test_name in (
        ("RL-319", "test_cross_page_statements_are_complete"),
        ("RL-357", "test_time_and_ddm_continuations"),
        ("RL-362", "test_time_and_ddm_continuations"),
    ):
        check = f"tests/test_hla_backflow.py::HlaBackflowTests::{test_name}"
        if check not in issues[issue_id]["verification"]:
            issues[issue_id]["verification"] += f"; {check}"
    issues["RL-387"]["resolution_note"] = (
        "The Table 2 introduction remains a reviewed non-normative candidate. Its requirement, "
        "review, and API binding now cite the complete sentence at page-181 lines 112-115; "
        "the adjacent order-type rule retains its own requirement."
    )
    for issue_id in ("RL-253", "RL-321", "RL-322"):
        issues[issue_id]["verification"] = (
            "tests/test_hla_backflow.py::HlaBackflowTests::"
            "test_missing_service_flow_items_have_source_and_direct_api_bindings"
        )
    issues["RL-253"]["created_requirement_ids"] = [
        "requirement-service-flow-get-dimension-handle-name-not-found"
    ]
    issues["RL-321"]["created_requirement_ids"] = [
        "requirement-service-flow-nmra-current-time-precondition",
        "requirement-service-flow-nmra-time-passed-exception",
    ]
    issues["RL-322"]["created_requirement_ids"] = [
        "requirement-service-flow-nmra-not-advancing-precondition",
        "requirement-service-flow-nmra-advancing-exception",
    ]
    issues["RL-253"]["resolution_note"] = (
        "The original page-259 candidate remains a §10.23.3 return rule. A distinct "
        "NameNotFound exception item now cites the dimension-not-defined list item at "
        "page-260 line 35 under §10.23.5 and the getDimensionHandle C++ API declaration."
    )
    issues["RL-321"]["resolution_note"] = (
        "The logical-time precondition at page-199 line 145 and the corresponding "
        "already-passed exception at page-200 line 62 have distinct source-backed records "
        "and direct Next Message Request Available API bindings."
    )
    issues["RL-322"]["resolution_note"] = (
        "The not-Time-Advancing precondition at page-200 line 11 and the corresponding "
        "Time-Advancing exception at page-200 line 74 have distinct source-backed records "
        "and direct Next Message Request Available API bindings."
    )


def _issues_by_id(payload: JsonObject) -> dict[str, JsonObject]:
    raw_issues: JsonValue | list[JsonValue] = payload.get("issues", [])
    if not isinstance(raw_issues, list):
        raise ValueError("backflow ledger issues must be an array")
    issues = {}
    for item in raw_issues:
        raw_issue: JsonValue | dict[str, JsonValue] = item
        if not isinstance(raw_issue, dict):
            raise ValueError("backflow ledger issue must be an object")
        issue = cast(JsonObject, raw_issue)
        issues[str(issue["id"])] = issue
    return issues


def mark_resolved(*issue_ids: str) -> None:
    path = ROOT / "data/hla-backflow-2026-10-24.json"
    raw_payload: JsonValue | dict[str, JsonValue] = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError("backflow ledger must be a JSON object")
    payload = cast(JsonObject, raw_payload)
    issues = _issues_by_id(payload)
    for issue_id in issue_ids:
        issues[issue_id]["resolution"] = "corrected-in-lab"
        issues[issue_id]["verification"] = "tests/test_hla_backflow.py"
    _apply_resolution_notes(issues)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    repair_page_216()
    repair_page_219_region_relationships()
    repair_page_192_service_narrative()
    repair_service_prose()
    repair_clause_boundaries()
    repair_more_clause_boundaries()
    repair_fragmented_statements()
    repair_remaining_section_continuations()
    repair_local_fragments()
    repair_contextual_fragments()
    repair_ownership_overview()
    repair_time_order_and_acquisition()
    repair_cross_page_statements()
    repair_clipped_clause_statements()
    repair_table_5_records()
    repair_time_table_and_caption()
    restore_missing_service_flow_candidates()
    rebuild_api_bindings()
    rebuild_api_crosswalk()
    mark_resolved(
        "RL-177",
        "RL-248",
        "RL-249",
        "RL-250",
        "RL-251",
        "RL-263",
        "RL-264",
        "RL-258",
        "RL-259",
        "RL-265",
        "RL-267",
        "RL-317",
        "RL-315",
        "RL-309",
        "RL-310",
        "RL-311",
        "RL-316",
        "RL-318",
        "RL-320",
        "RL-313",
        "RL-314",
        "RL-333",
        "RL-334",
        "RL-332",
        "RL-335",
        "RL-337",
        "RL-323",
        "RL-324",
        "RL-325",
        "RL-326",
        "RL-329",
        "RL-328",
        "RL-330",
        "RL-331",
        "RL-339",
        "RL-340",
        "RL-341",
        "RL-343",
        "RL-344",
        "RL-345",
        "RL-346",
        "RL-348",
        "RL-349",
        "RL-350",
        "RL-351",
        "RL-352",
        "RL-359",
        "RL-361",
        "RL-356",
        "RL-357",
        "RL-360",
        "RL-362",
        "RL-370",
        "RL-342",
        "RL-347",
        "RL-373",
        "RL-374",
        "RL-376",
        "RL-377",
        "RL-375",
        "RL-378",
        "RL-379",
        "RL-380",
        "RL-381",
        "RL-382",
        "RL-383",
        "RL-384",
        "RL-385",
        "RL-319",
        "RL-327",
        "RL-386",
        "RL-256",
        "RL-257",
        "RL-358",
        "RL-364",
        "RL-365",
        "RL-366",
        "RL-367",
        "RL-368",
        "RL-312",
        "RL-387",
        "RL-253",
        "RL-321",
        "RL-322",
    )


if __name__ == "__main__":
    main()
