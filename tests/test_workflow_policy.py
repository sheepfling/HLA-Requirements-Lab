"""Regression tests for the repository's hosted-CI trigger policy."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


def _job_block(name: str, workflow: str) -> str:
    jobs = re.search(r"(?ms)^jobs:\n(.*)\Z", workflow)
    assert jobs is not None
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        jobs.group(1),
    )
    assert match is not None
    return match.group(1)


def test_ci_runs_after_successful_target_merges_or_manual_dispatch() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    triggers = re.search(r"(?ms)^on:\n(.*?)(?=^jobs:)", workflow)
    assert triggers is not None
    trigger_text = triggers.group(1)

    assert re.search(
        r"(?m)^  pull_request:\n    types: \[closed\]\n    branches: \[feature/hla\]$",
        trigger_text,
    )
    assert re.search(r"(?m)^  workflow_dispatch:\s*$", trigger_text)
    assert not re.search(r"(?m)^  push:", trigger_text)

    expected_condition = (
        "if: github.event_name == 'workflow_dispatch' || github.event.pull_request.merged == true"
    )
    quality = _job_block("quality", workflow)
    document_release = _job_block("document-release", workflow)
    assert expected_condition in quality
    assert expected_condition in document_release


def test_ci_matrix_checkout_and_release_dependency_are_preserved() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    quality = _job_block("quality", workflow)
    document_release = _job_block("document-release", workflow)

    assert "os: [ ubuntu-latest, windows-latest ]" in quality
    assert 'python-version: [ "3.11", "3.12", "3.13" ]' in quality
    assert "needs: quality" in document_release
    assert "actions/checkout@v4" in quality
    assert "actions/checkout@v4" in document_release
    assert not re.search(r"(?m)^\s+ref:", quality + document_release)
