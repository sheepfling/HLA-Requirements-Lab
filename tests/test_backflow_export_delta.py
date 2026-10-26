"""Checks for reproducible field-level evidence in the HLA backflow handoff."""

from __future__ import annotations

from hla_lab.core.semantic_model import ContentBlockFile, RequirementFile
from hla_lab.traceability.compliance_contract import BundleRequirement
from tests.support import TEST_REPO_ROOT
from tools.backflow_contracts import (
    BackflowExportDelta,
    BackflowSnapshot,
)
from tools.backflow_export_delta import requirement_delta


def test_requirement_delta_ignores_ordinal_only_changes() -> None:
    before = BundleRequirement(id="requirement-1", ordinal=7, clause="4", statement="Rule.")
    after = BundleRequirement(id="requirement-1", ordinal=8, clause="4.1", statement="Rule.")
    delta = requirement_delta(before, after)
    assert delta.changed_fields == ["clause"]
    assert delta.readable_changes["clause"].before == "4"
    assert delta.readable_changes["clause"].after == "4.1"
    assert delta.before_sha256 != delta.after_sha256
    assert requirement_delta(before, before.model_copy(update={"ordinal": 99})).changed_fields == []


def test_export_delta_covers_every_snapshot_issue_and_corrected_candidate() -> None:
    snapshot = BackflowSnapshot.model_validate_json(
        (TEST_REPO_ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
    )
    delta = BackflowExportDelta.model_validate_json(
        (TEST_REPO_ROOT / "data/hla-backflow-export-delta-2026-10-25.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item.id for item in delta.issues] == [item.id for item in snapshot.issues]
    assert delta.baseline.bundle_id == delta.candidate.bundle_id
    corrected_ids: set[str] = set()
    created_ids: set[str] = set()
    for issue, evidence in zip(snapshot.issues, delta.issues, strict=True):
        assert evidence.resolution == issue.resolution
        assert evidence.document_id == issue.document_id
        assert [item.id for item in evidence.affected] == issue.affected_requirement_ids
        assert [item.id for item in evidence.created] == issue.created_requirement_ids
        if issue.resolution == "corrected-in-lab":
            assert evidence.affected or evidence.created
            assert all(item.changed_fields for item in evidence.affected)
            corrected_ids.update(item.id for item in evidence.affected)
            created_ids.update(item.id for item in evidence.created)
    assert len(corrected_ids) == 203
    assert len(created_ids) == 5
    unattributed = delta.unattributed_requirement_changes
    assert len(unattributed) == 93
    assert all(item.document_id == "hla-1516.1-2025" for item in unattributed)
    assert all(item.change == "changed" for item in unattributed)
    changed = [item for item in unattributed if item.change == "changed"]
    assert all(item.changed_fields for item in changed)


def test_collateral_source_spans_include_their_opening_layout_lines() -> None:
    semantic = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025/semantic"
    requirements = {
        item.id: item
        for item in RequirementFile.model_validate_json(
            (semantic / "requirements.json").read_text(encoding="utf-8")
        ).requirements
    }
    layouts = {
        item.source.path: item.layout_body.splitlines()
        for item in ContentBlockFile.model_validate_json(
            (semantic / "content-blocks.json").read_text(encoding="utf-8")
        ).content_blocks
        if item.layout_body is not None
    }
    delta = BackflowExportDelta.model_validate_json(
        (TEST_REPO_ROOT / "data/hla-backflow-export-delta-2026-10-25.json").read_text(
            encoding="utf-8"
        )
    )
    unattributed_ids = {item.id for item in delta.unattributed_requirement_changes}
    for requirement_id in unattributed_ids:
        source = requirements[requirement_id].source
        assert source.path in layouts
        assert source.end_line is not None
        assert 0 <= source.line <= source.end_line < len(layouts[source.path])

    opening_lines = {
        "page-181-l121-4": (118, "The order type of a"),
        "page-182-l10-2": (7, "A joined federate shall request"),
        "page-182-l22-6": (19, "Lookahead"),
        "page-182-l43-13": (37, "If"),
        "page-207-l115-29": (112, "If the argument indicates"),
        "page-216-l90-27": (87, "A region"),
        "page-219-l11-3": (8, "A region specification may contain"),
        "page-219-l23-7": (17, "This situation may result"),
        "page-219-l62-20": (59, "The effects of the"),
        "page-219-l86-28": (74, "If a federate invokes"),
        "page-294-l20-6": (17, "The service"),
    }
    for suffix, (line, witness) in opening_lines.items():
        matches = [item for key, item in requirements.items() if key.endswith(suffix)]
        assert len(matches) == 1
        record = matches[0]
        assert record.id in unattributed_ids
        source = record.source
        assert source.line == line
        assert witness in layouts[source.path][line]
        assert record.title.endswith(f":{line}")
