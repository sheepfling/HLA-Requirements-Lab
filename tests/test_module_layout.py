"""Tests for repository-wide Python module layout conventions."""

from __future__ import annotations

from pathlib import Path

from tools.check_module_layout import check_paths


def test_public_api_declarations_follow_imports() -> None:
    roots = tuple(Path(name) for name in ("hla_lab", "tools", "tests", "topics"))

    assert check_paths(roots) == ()
