"""Checks for reproducible field-level evidence in the HLA backflow handoff."""

from __future__ import annotations

import json

from tests.support import TEST_REPO_ROOT
from tools.backflow_export_delta import requirement_delta


def test_requirement_delta_ignores_ordinal_only_changes() -> None:
    before = {"id": "requirement-1", "ordinal": 7, "clause": "4", "statement": "Rule."}
    after = {"id": "requirement-1", "ordinal": 8, "clause": "4.1", "statement": "Rule."}
    delta = requirement_delta(before, after)
    assert delta["changed_fields"] == ["clause"]
    assert delta["readable_changes"]["clause"] == {"before": "4", "after": "4.1"}
    assert delta["before_sha256"] != delta["after_sha256"]
    assert requirement_delta(before, before | {"ordinal": 99})["changed_fields"] == []


def test_export_delta_covers_every_snapshot_issue_and_corrected_candidate() -> None:
    snapshot = json.loads(
        (TEST_REPO_ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
    )
    delta = json.loads(
        (TEST_REPO_ROOT / "data/hla-backflow-export-delta-2026-10-25.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["id"] for item in delta["issues"]] == [
        item["id"] for item in snapshot["issues"]
    ]
    assert delta["baseline"]["bundle_id"] == delta["candidate"]["bundle_id"]
    corrected_ids: set[str] = set()
    created_ids: set[str] = set()
    for issue, evidence in zip(snapshot["issues"], delta["issues"], strict=True):
        assert evidence["resolution"] == issue["resolution"]
        assert evidence["document_id"] == issue["document_id"]
        assert [item["id"] for item in evidence["affected"]] == issue[
            "affected_requirement_ids"
        ]
        assert [item["id"] for item in evidence["created"]] == issue.get(
            "created_requirement_ids", []
        )
        if issue["resolution"] == "corrected-in-lab":
            assert evidence["affected"] or evidence["created"]
            assert all(item["changed_fields"] for item in evidence["affected"])
            corrected_ids.update(item["id"] for item in evidence["affected"])
            created_ids.update(item["id"] for item in evidence["created"])
    assert len(corrected_ids) == 203
    assert len(created_ids) == 5
