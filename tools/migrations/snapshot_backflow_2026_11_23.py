"""Create a local, read-only reconciliation snapshot for the 2026-11-23 queue."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ISSUE_IDS = {
    "RL-392",
    *(f"RL-{number}" for number in range(394, 402)),
    *(f"RL-{number}" for number in range(403, 411)),
    *(f"RL-{number}" for number in range(411, 421)),
    *(f"RL-{number}" for number in range(421, 438)),
    *(f"RL-{number}" for number in range(438, 457)),
}
ISSUE_IDS.discard("RL-402")

SOURCE_ANOMALIES = {"RL-399", "RL-403", "RL-407", "RL-420", "RL-441", "RL-443", "RL-444", "RL-456"}
DOWNSTREAM_ONLY = {"RL-411", "RL-412", "RL-414", "RL-450", "RL-451"}

TABLE5_TESTS = [
    "tests/test_hla_backflow.py::HlaBackflowTests::test_2026_table_5_backflow_rows_are_complete_and_source_addressable",
    "tests/test_hla_backflow.py::HlaBackflowTests::test_table_5_parent_rows_have_complete_shapes",
    "tests/test_hla_backflow.py::HlaBackflowTests::test_table_5_sources_point_to_printed_values_and_examples",
]
SERVICE_ATTRIBUTION_TESTS = [
    "tests/test_hla_backflow.py::HlaBackflowTests::test_service_boundaries_follow_visible_headings",
    "tests/test_hla_backflow.py::HlaBackflowTests::test_support_service_clause_and_api_ownership_follow_visible_headings",
    "tests/test_hla_backflow.py::HlaBackflowTests::test_cross_page_service_attribution",
]
PROTOCOL_TABLE_TEST = (
    "tests/test_15161_acceptance_slice.py::HLA15161AcceptanceSliceTests::"
    "test_production_protocol_renderer_preserves_table_31_through_39_shapes"
)
ANOMALY_TEST = (
    "tests/test_backflow_2026_11_23.py::HLA15162BackflowTests::"
    "test_source_anomalies_have_mapped_dispositions"
)


def _local_status(issue_id: str) -> str:
    if issue_id in SOURCE_ANOMALIES:
        return "source-anomaly-mapped"
    if issue_id in DOWNSTREAM_ONLY:
        return "downstream-only-no-lab-change"
    return "corrected-in-lab"


def _verification(issue_id: str) -> list[str]:
    if issue_id == "RL-392":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_missing_service_flow_items_have_source_and_direct_api_bindings"
        ]
    if issue_id in {
        "RL-394",
        "RL-395",
        "RL-396",
        "RL-397",
        "RL-398",
        "RL-399",
        "RL-400",
        "RL-401",
        "RL-403",
        "RL-404",
        "RL-405",
        "RL-406",
        "RL-407",
        "RL-408",
        "RL-409",
        "RL-410",
    }:
        refs = list(TABLE5_TESTS)
        if issue_id in SOURCE_ANOMALIES:
            refs.extend(
                [
                    "tests/test_hla_backflow.py::HlaBackflowTests::test_table_5_source_anomalies_have_explicit_semantic_mappings",
                    "tests/test_hla_backflow.py::HlaBackflowTests::test_table_5_source_conflicts_remain_explicit",
                ]
            )
        return refs
    if issue_id in DOWNSTREAM_ONLY:
        return []
    if issue_id == "RL-413":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_page_216_ddm_sources_use_clause_9_adapter"
        ]
    if issue_id == "RL-415":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_page_185_tso_continuation_uses_the_visible_817_bookmark"
        ]
    if issue_id == "RL-416":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_receive_interaction_tag_candidate_keeps_its_source_subject"
        ]
    if issue_id == "RL-417":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_missing_service_flow_items_have_source_and_direct_api_bindings"
        ]
    if issue_id == "RL-418":
        return [
            "tests/test_requirement_candidate_boundaries.py::"
            "RequirementCandidateBoundaryTests::test_clause_12_adapter_rename_preserves_candidate_ids",
            "tests/test_requirement_candidate_boundaries.py::"
            "RequirementCandidateBoundaryTests::test_promoted_candidates_follow_visible_source_headings",
        ]
    if issue_id in {"RL-419", "RL-445"}:
        return [PROTOCOL_TABLE_TEST]
    if issue_id == "RL-420":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_table_5_source_conflicts_remain_explicit"
        ]
    if issue_id in {f"RL-{number}" for number in range(421, 438)} | {"RL-442", "RL-447", "RL-448"}:
        return list(SERVICE_ATTRIBUTION_TESTS)
    if issue_id == "RL-438":
        return [
            "tests/test_backflow_2026_11_23.py::HLA15162BackflowTests::test_annex_c7_continuations_inherit_the_correct_heading_and_source_elements"
        ]
    if issue_id == "RL-439":
        return [
            "tests/test_backflow_2026_11_23.py::HLA15162BackflowTests::test_page_40_object_class_rules_are_complete_and_separated"
        ]
    if issue_id == "RL-440":
        return [
            "tests/test_backflow_2026_11_23.py::HLA15162BackflowTests::test_interaction_parameter_table_cross_page_text_is_complete"
        ]
    if issue_id in {"RL-441", "RL-443", "RL-444", "RL-456"}:
        return [ANOMALY_TEST]
    if issue_id == "RL-442":
        return list(SERVICE_ATTRIBUTION_TESTS)
    if issue_id == "RL-446":
        return [
            "tests/test_backflow_2026_11_23.py::HLA15162BackflowTests::test_fixed_record_candidates_are_owned_by_subclause_4_14_10_1"
        ]
    if issue_id == "RL-449" or issue_id == "RL-452":
        return [
            "tests/test_backflow_2026_11_23.py::HLA15162BackflowTests::test_variant_record_continuations_have_complete_statements_and_trace_links"
        ]
    if issue_id == "RL-453":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_page_225_allow_relaxed_ddm_candidate_has_complete_sentence_and_owner"
        ]
    if issue_id == "RL-454":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_federate_protocol_argument_rules_retain_applicability"
        ]
    if issue_id == "RL-455":
        return [
            "tests/test_hla_backflow.py::HlaBackflowTests::test_transport_layer_lead_in_is_context_not_an_independent_requirement"
        ]
    raise KeyError(f"No validation mapping for {issue_id}")


def _work_completed(issue_id: str, local_status: str) -> str:
    if local_status == "source-anomaly-mapped":
        return (
            "Mapped the Lab requirement from the controlling semantic source: Table 14 enum "
            "values for RL-399; base-64 semantics for RL-403; HLAservice field identity for "
            "RL-407; an explicit addMapping/addVariant semantic crosswalk for RL-420; and the "
            "captured normative rule for RL-441, RL-443, RL-444, and RL-456. Preserved each "
            "conflicting example or API spelling in the source-anomaly ledger."
        )
    if local_status == "downstream-only-no-lab-change":
        return (
            "Reviewed against the pinned semantic record and the authoritative issue evidence. "
            "The remaining complaint concerns TCK evidence or coverage-disposition workflow; no "
            "Lab mapping or source text was changed."
        )
    return "Applied the source-backed semantic, attribution, table, renderer, service-flow, or framing correction in the Requirements Lab working tree."


def _remaining_action(issue: dict[str, Any], local_status: str) -> str:
    if issue["status"] != "open":
        return "The authoritative Umbra record is resolved; no upstream queue action remains."
    if local_status == "source-anomaly-mapped":
        return (
            "The Lab mapping is explicit and the conflicting source evidence is preserved. "
            "Umbra may review and close its open record without changing the Lab source text."
        )
    if local_status == "downstream-only-no-lab-change":
        return "No Lab data change was indicated; the upstream record remains open for its owner to review."
    return "The upstream record remains open; review the corrected Lab revision before resynchronizing status."


def build_snapshot(source_path: Path) -> dict[str, Any]:
    source_bytes = source_path.read_bytes()
    source_payload = json.loads(source_bytes.decode("utf-8"))
    issues = [item for item in source_payload["issues"] if item.get("id") in ISSUE_IDS]
    source_ids = {item["id"] for item in issues}
    if source_ids != ISSUE_IDS or len(issues) != 63:
        raise ValueError(
            f"Expected the exact 63 tracked queue IDs, received {len(issues)}: "
            f"missing={sorted(ISSUE_IDS - source_ids)}, extra={sorted(source_ids - ISSUE_IDS)}"
        )

    records: list[dict[str, Any]] = []
    for issue in issues:
        issue_id = issue["id"]
        local_status = _local_status(issue_id)
        record: dict[str, Any] = {
            "id": issue_id,
            "upstream_status": issue["status"],
            # Keep the authoritative register record intact so its symptom,
            # impact, workaround, reproduction, evidence, and prior validation
            # remain available beside the local disposition.
            "upstream_record": issue,
            "local_status": local_status,
            "work_completed": _work_completed(issue_id, local_status),
            "verification_refs": _verification(issue_id),
            "remaining_action": _remaining_action(issue, local_status),
        }
        records.append(record)

    counts: dict[str, int] = {}
    for record in records:
        status = record["local_status"]
        counts[status] = counts.get(status, 0) + 1
    upstream_counts: dict[str, int] = {}
    for record in records:
        status = record["upstream_status"]
        upstream_counts[status] = upstream_counts.get(status, 0) + 1
    return {
        "schema_version": 1,
        "as_of": "2026-11-23",
        "source": "Umbra/compliance/requirements-lab/known-issues.json",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "authority": (
            "Snapshot of the 63 issue IDs in the 2026-11-23 Requirements Lab queue. The sibling "
            "Umbra known-issues.json remains authoritative for current status and was read only. "
            "This local snapshot records Requirements Lab working-tree dispositions and does not "
            "close or resynchronize upstream issues."
        ),
        "totals": {
            "tracked_queue_records": len(records),
            "upstream_status_counts": upstream_counts,
            "open_upstream": upstream_counts.get("open", 0),
            "resolved_in_umbra": upstream_counts.get("resolved-in-umbra", 0),
            "corrected_in_lab": counts.get("corrected-in-lab", 0),
            "source_anomaly_mapped": counts.get("source-anomaly-mapped", 0),
            "downstream_only_no_lab_change": counts.get("downstream-only-no-lab-change", 0),
        },
        "issues": sorted(records, key=lambda item: int(item["id"].split("-")[1])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Read-only known-issues.json")
    parser.add_argument("--output", type=Path, required=True, help="Local snapshot JSON path")
    args = parser.parse_args()
    snapshot = build_snapshot(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
