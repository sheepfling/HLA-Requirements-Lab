"""Explicit workspace paths for historical corpus migrations.

Migration modules can be imported without a configured workspace. Callers
supply a root, or set HLA_LAB_ROOT before invoking an operation that reads or
writes corpus files.
"""

from __future__ import annotations

from pathlib import Path

from hla_lab.paths import resources


def migration_root(workspace_root: Path | None = None) -> Path:
    return resources(workspace_root).root


def document_root(document_id: str, workspace_root: Path | None = None) -> Path:
    return resources(workspace_root).document(document_id).root


def ieee_topics_root(workspace_root: Path | None = None) -> Path:
    return resources(workspace_root).ieee_topics
